from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
DEV_COMPOSE_FILE = REPO_ROOT / "docker-compose.dev.yml"
NEXT_COMPOSE_FILE = REPO_ROOT / "docker-compose.next.yml"
NEXT_REMOTE_COMPOSE_FILE = REPO_ROOT / "docker-compose.next.remote.yml"
API_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile.api"
WORKER_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile.worker"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
NGINX_CONFIG = REPO_ROOT / "infra" / "proxy" / "nginx.conf"
MAKEFILE = REPO_ROOT / "Makefile"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_default_compose_is_the_replacement_production_stack():
    compose = _yaml(COMPOSE_FILE)

    default_services = {name for name, service in compose["services"].items() if "profiles" not in service}
    assert default_services == {"db", "migrate", "api", "worker", "frontend", "proxy"}
    assert compose["services"]["jaeger"]["profiles"] == ["observability"]
    assert compose["services"]["temporal"]["profiles"] == ["temporal"]
    assert compose["services"]["temporal-ui"]["profiles"] == ["temporal"]
    assert "rentivo" not in compose["services"]
    assert not NEXT_COMPOSE_FILE.exists()
    assert not NEXT_REMOTE_COMPOSE_FILE.exists()


def test_migration_completes_before_api_and_worker_start():
    services = _yaml(COMPOSE_FILE)["services"]

    assert services["migrate"]["command"] == [
        "alembic",
        "-c",
        "backend/alembic.ini",
        "upgrade",
        "head",
    ]
    assert services["migrate"]["restart"] == "no"
    assert services["migrate"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert sum(service.get("command") == services["migrate"]["command"] for service in services.values()) == 1
    for service_name in ("api", "worker"):
        assert services[service_name]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"


def test_application_services_share_runtime_environment_and_invoice_storage():
    services = _yaml(COMPOSE_FILE)["services"]

    for service_name in ("migrate", "api", "worker"):
        assert services[service_name]["env_file"] == [
            {
                "path": "${RENTIVO_APP_ENV_FILE:-.env}",
                "required": True,
            }
        ]
        assert services[service_name]["volumes"] == ["invoices:/app/invoices"]


def test_proxy_and_database_publish_only_on_loopback():
    services = _yaml(COMPOSE_FILE)["services"]

    assert services["db"]["ports"] == ["127.0.0.1:${MYSQL_PORT:-3306}:3306"]
    assert services["proxy"]["ports"] == ["127.0.0.1:${RENTIVO_PORT:-8080}:80"]
    assert services["proxy"]["healthcheck"]["test"][-1] == "http://localhost/api/v1/ready"
    assert "ports" not in services["api"]
    assert "ports" not in services["frontend"]


def test_api_healthcheck_uses_database_readiness_endpoint():
    healthcheck = _yaml(COMPOSE_FILE)["services"]["api"]["healthcheck"]["test"]

    assert healthcheck[-1] == "http://localhost:8000/api/v1/ready"


def test_compose_sets_explicit_production_web_security_environment():
    services = _yaml(COMPOSE_FILE)["services"]
    api_environment = services["api"]["environment"]

    for service_name in ("migrate", "api", "worker"):
        assert services[service_name]["environment"]["RENTIVO_ENVIRONMENT"] == "production"
    assert api_environment["RENTIVO_PUBLIC_URL"] == ("${RENTIVO_PUBLIC_ORIGIN:?Set the public HTTPS origin}")
    assert api_environment["RENTIVO_PUBLIC_APP_URL"] == api_environment["RENTIVO_PUBLIC_URL"]
    assert api_environment["RENTIVO_WEBAUTHN_ORIGIN"] == api_environment["RENTIVO_PUBLIC_URL"]
    assert api_environment["RENTIVO_WEBAUTHN_RP_ID"] == ("${RENTIVO_WEBAUTHN_RP_ID:?Set the public hostname}")
    assert api_environment["RENTIVO_COOKIE_SECURE"] == "true"
    assert api_environment["RENTIVO_ACCESS_COOKIE_NAME"] == "__Host-rentivo_access"
    assert api_environment["RENTIVO_CHALLENGE_COOKIE_NAME"] == "__Host-rentivo_challenge"
    assert api_environment["RENTIVO_CSRF_COOKIE_NAME"] == "__Host-rentivo_csrf"


def test_internal_edge_network_exposes_only_the_proxy():
    compose = _yaml(COMPOSE_FILE)

    assert compose["networks"]["app-edge"]["internal"] is True
    assert compose["networks"]["ingress"].get("internal", False) is False
    assert set(compose["services"]["proxy"]["networks"]) == {"app-edge", "ingress"}
    for service_name in ("db", "migrate", "api", "worker", "frontend"):
        assert "ingress" not in compose["services"][service_name].get("networks", [])


def test_runtime_dockerfiles_do_not_scaffold_the_legacy_package():
    for path in (API_DOCKERFILE, WORKER_DOCKERFILE):
        contents = path.read_text()
        assert "legacy_web" not in contents
        assert "backend/rentivo/__init__.py" in contents


def test_development_override_targets_api_and_worker_only():
    override = _yaml(DEV_COMPOSE_FILE)["services"]

    assert set(override) == {"api", "worker", "frontend"}
    assert "legacy_web" not in DEV_COMPOSE_FILE.read_text()


def test_proxy_replaces_forwarding_input_and_re_resolves_services():
    nginx = NGINX_CONFIG.read_text()

    assert "set_real_ip_from ${RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR};" in nginx
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
    assert "$proxy_add_x_forwarded_for" not in nginx
    assert "resolver 127.0.0.11" in nginx
    assert "server api:8000 resolve;" in nginx
    assert "server frontend:8080 resolve;" in nginx


def test_frontend_runs_unprivileged_and_read_only():
    dockerfile = FRONTEND_DOCKERFILE.read_text()
    frontend = _yaml(COMPOSE_FILE)["services"]["frontend"]

    assert "FROM nginxinc/nginx-unprivileged:1.28-alpine" in dockerfile
    assert "USER 101" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert frontend["read_only"] is True
    assert frontend["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in frontend["security_opt"]
    assert frontend["tmpfs"] == ["/tmp"]


def test_database_and_application_environment_sources_are_separate():
    services = _yaml(COMPOSE_FILE)["services"]

    assert "env_file" not in services["db"]
    assert set(services["db"]["environment"]) == {
        "MYSQL_DATABASE",
        "MYSQL_PASSWORD",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_USER",
    }
    for service_name in ("migrate", "api", "worker"):
        assert "MYSQL_ROOT_PASSWORD" not in services[service_name].get("environment", {})
        assert "RENTIVO_DB_URL" not in services[service_name].get("environment", {})


def test_api_runtime_source_and_virtualenv_are_read_only_to_appuser():
    dockerfile = API_DOCKERFILE.read_text()

    assert "chown -R appuser:appuser /app" not in dockerfile
    assert "chmod -R a-w /app/.venv /app/backend" in dockerfile
    assert "chown appuser:appuser /app/invoices /app/outbox" in dockerfile


def test_makefile_promotes_stack_targets_and_keeps_non_legacy_preview_aliases():
    makefile = MAKEFILE.read_text()

    for target in ("stack-config", "stack-build", "stack-migrate", "stack-up", "stack-stop"):
        assert f".PHONY: {target}" in makefile
    for alias, target in (
        ("preview-config", "stack-config"),
        ("preview-build", "stack-build"),
        ("preview-migrate", "stack-migrate"),
        ("preview-up", "stack-up"),
        ("preview-stop", "stack-stop"),
    ):
        assert f"{alias}: {target}" in makefile
    assert "docker-compose.next" not in makefile
