from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GITIGNORE = REPO_ROOT / ".gitignore"
API_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile.api"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.next.yml"
REMOTE_COMPOSE_FILE = REPO_ROOT / "docker-compose.next.remote.yml"
NGINX_CONFIG = REPO_ROOT / "infra" / "proxy" / "nginx.conf"
PREVIEW_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test-pr.yaml"
LEGACY_CUSTOM_CSS = REPO_ROOT / "backend" / "legacy_web" / "static" / "core" / "css" / "custom.css"
FRONTEND_CUSTOM_CSS = REPO_ROOT / "frontend" / "src" / "styles" / "custom.css"
BILL_DETAIL_TEMPLATE = REPO_ROOT / "backend" / "legacy_web" / "templates" / "bill" / "detail.html"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_api_runtime_trusts_only_the_preview_proxy():
    dockerfile = API_DOCKERFILE.read_text()
    compose = _yaml(COMPOSE_FILE)
    command = " ".join(compose["services"]["api"]["command"])

    assert "--forwarded-allow-ips=*" not in dockerfile
    assert "--forwarded-allow-ips=127.0.0.1" in dockerfile
    assert "--forwarded-allow-ips=${RENTIVO_PROXY_IP:-172.30.0.10}" in command
    assert compose["services"]["proxy"]["networks"]["preview-edge"]["ipv4_address"] == (
        "${RENTIVO_PROXY_IP:-172.30.0.10}"
    )


def test_api_readiness_checks_the_database_and_http_endpoint():
    compose = _yaml(COMPOSE_FILE)
    api = compose["services"]["api"]
    health_command = " ".join(api["healthcheck"]["test"])

    assert "SELECT 1" in health_command
    assert "http://localhost:8000/api/v1/health" in health_command
    assert api["depends_on"]["db"]["condition"] == "service_healthy"
    assert compose["services"]["proxy"]["healthcheck"]["test"][-1] == ("http://localhost/api/v1/health")


def test_local_and_remote_preview_cookie_and_webauthn_settings_are_explicit():
    local_environment = _yaml(COMPOSE_FILE)["services"]["api"]["environment"]
    remote_environment = _yaml(REMOTE_COMPOSE_FILE)["services"]["api"]["environment"]

    assert local_environment["RENTIVO_ENVIRONMENT"] == "dev"
    assert local_environment["RENTIVO_COOKIE_SECURE"] == "false"
    assert local_environment["RENTIVO_WEBAUTHN_RP_ID"] == "localhost"
    assert local_environment["RENTIVO_ACCESS_COOKIE_NAME"] == "rentivo_access"
    assert local_environment["RENTIVO_CHALLENGE_COOKIE_NAME"] == "rentivo_challenge"
    assert local_environment["RENTIVO_CSRF_COOKIE_NAME"] == "rentivo_csrf"

    expected_remote_environment = {
        "RENTIVO_ACCESS_COOKIE_NAME": "__Host-rentivo_access",
        "RENTIVO_CHALLENGE_COOKIE_NAME": "__Host-rentivo_challenge",
        "RENTIVO_COOKIE_SECURE": "true",
        "RENTIVO_CSRF_COOKIE_NAME": "__Host-rentivo_csrf",
        "RENTIVO_ENVIRONMENT": "staging",
        "RENTIVO_PUBLIC_APP_URL": "${RENTIVO_PREVIEW_ORIGIN:?Set the public HTTPS preview origin}",
        "RENTIVO_WEBAUTHN_ORIGIN": "${RENTIVO_PREVIEW_ORIGIN:?Set the public HTTPS preview origin}",
        "RENTIVO_WEBAUTHN_RP_ID": "${RENTIVO_WEBAUTHN_RP_ID:?Set the preview hostname}",
    }
    assert expected_remote_environment.items() <= remote_environment.items()


def test_proxy_accepts_tls_metadata_only_from_a_configured_terminator():
    compose = _yaml(COMPOSE_FILE)
    remote = _yaml(REMOTE_COMPOSE_FILE)
    nginx = NGINX_CONFIG.read_text()

    assert compose["services"]["proxy"]["environment"]["RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR"] == (
        "${RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR:-127.0.0.1/32}"
    )
    assert remote["services"]["proxy"]["environment"]["RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR"] == (
        "${RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR:?Set the TLS terminator IP or CIDR}"
    )
    assert "set_real_ip_from ${RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR};" in nginx
    assert "geo $realip_remote_addr $rentivo_trusted_tls_terminator" in nginx
    assert "proxy_set_header X-Forwarded-Proto $rentivo_forwarded_proto;" in nginx
    assert "proxy_set_header X-Forwarded-Port $rentivo_forwarded_port;" in nginx


def test_proxy_replaces_forwarding_input_and_re_resolves_services():
    nginx = NGINX_CONFIG.read_text()

    assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
    assert "$proxy_add_x_forwarded_for" not in nginx
    assert "resolver 127.0.0.11" in nginx
    assert "server api:8000 resolve;" in nginx
    assert "server frontend:8080 resolve;" in nginx


def test_database_receives_only_mariadb_configuration():
    database = _yaml(COMPOSE_FILE)["services"]["db"]

    assert "env_file" not in database
    assert set(database["environment"]) == {
        "MYSQL_DATABASE",
        "MYSQL_PASSWORD",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_USER",
    }


def test_preview_ports_are_loopback_only_and_remote_database_has_no_fallbacks():
    compose = _yaml(COMPOSE_FILE)
    remote = _yaml(REMOTE_COMPOSE_FILE)

    assert compose["services"]["db"]["ports"] == ["127.0.0.1:${MYSQL_PORT:-3306}:3306"]
    assert compose["services"]["rentivo"]["ports"] == ["127.0.0.1:8000:8000"]
    assert compose["services"]["proxy"]["ports"] == ["127.0.0.1:${RENTIVO_PREVIEW_PORT:-8080}:80"]
    assert remote["services"]["proxy"]["ports"] == [
        "127.0.0.1:${RENTIVO_PREVIEW_PORT:?Set the host-only preview port}:80"
    ]
    assert remote["services"]["db"]["environment"] == {
        "MYSQL_DATABASE": "${MYSQL_DATABASE:?Set the remote database name}",
        "MYSQL_PASSWORD": "${MYSQL_PASSWORD:?Set the remote database password}",
        "MYSQL_ROOT_PASSWORD": "${MYSQL_ROOT_PASSWORD:?Set the remote database root password}",
        "MYSQL_USER": "${MYSQL_USER:?Set the remote database user}",
    }


def test_proxy_uses_a_dedicated_non_internal_ingress_network():
    compose = _yaml(COMPOSE_FILE)

    assert compose["networks"]["preview-edge"]["internal"] is True
    assert compose["networks"]["preview-ingress"].get("internal", False) is False
    assert set(compose["services"]["proxy"]["networks"]) == {"preview-edge", "preview-ingress"}
    for service_name in ("db", "rentivo", "worker", "api", "frontend"):
        assert "preview-ingress" not in compose["services"][service_name].get("networks", [])


def test_database_interpolation_and_application_runtime_env_are_separate():
    compose = _yaml(COMPOSE_FILE)
    remote = _yaml(REMOTE_COMPOSE_FILE)

    for service_name in ("rentivo", "worker", "api"):
        service = compose["services"][service_name]
        assert service["env_file"] == [
            {
                "path": "${RENTIVO_APP_ENV_FILE:-.env.preview-app}",
                "required": False,
            }
        ]
        assert "MYSQL_ROOT_PASSWORD" not in service.get("environment", {})
        assert "RENTIVO_DB_URL" not in service.get("environment", {})
        assert remote["services"][service_name]["env_file"] == [
            {
                "path": "${RENTIVO_APP_ENV_FILE:?Set the remote application environment file}",
                "required": True,
            }
        ]
    assert "RENTIVO_ENV_FILE" not in COMPOSE_FILE.read_text()
    assert "mysql+pymysql://${MYSQL_USER" not in COMPOSE_FILE.read_text()


def test_preview_secret_files_are_ignored_but_examples_remain_trackable():
    patterns = set(GITIGNORE.read_text().splitlines())

    assert ".env.preview-app" in patterns
    assert ".env.preview-db" in patterns
    assert "!.env.example" in patterns


def test_frontend_runs_unprivileged_and_read_only_on_port_8080():
    dockerfile = FRONTEND_DOCKERFILE.read_text()
    compose = _yaml(COMPOSE_FILE)
    frontend = compose["services"]["frontend"]

    assert "FROM node:22-alpine AS builder" in dockerfile
    assert "FROM nginxinc/nginx-unprivileged:1.28-alpine" in dockerfile
    assert "listen 8080 default_server;" in dockerfile
    assert "USER 101" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert frontend["read_only"] is True
    assert frontend["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in frontend["security_opt"]
    assert frontend["tmpfs"] == ["/tmp"]
    assert frontend["healthcheck"]["test"][-1] == "http://localhost:8080/"


def test_preview_ci_is_consolidated_under_existing_required_gate():
    assert not PREVIEW_WORKFLOW.exists()
    workflow = _yaml(PR_WORKFLOW)
    jobs = workflow["jobs"]

    required_jobs = {
        "backend",
        "e2e",
        "frontend",
        "migrations",
        "compose-config",
        "preview-images",
    }
    assert required_jobs <= jobs.keys()
    assert set(jobs["all-checks-pass"]["needs"]) == required_jobs
    assert {item["name"] for item in jobs["preview-images"]["strategy"]["matrix"]["include"]} == {
        "legacy",
        "api",
        "worker",
        "frontend",
    }


def test_status_menu_host_style_survives_frontend_split():
    selector = ".panel--menu-host { overflow: visible; }"

    assert 'class="panel panel--menu-host"' in BILL_DETAIL_TEMPLATE.read_text()
    assert selector in LEGACY_CUSTOM_CSS.read_text()
    assert selector in FRONTEND_CUSTOM_CSS.read_text()


def test_api_runtime_source_and_virtualenv_are_read_only_to_appuser():
    dockerfile = API_DOCKERFILE.read_text()

    assert "chown -R appuser:appuser /app" not in dockerfile
    assert "chmod -R a-w /app/.venv /app/backend" in dockerfile
    assert "chown appuser:appuser /app/invoices /app/outbox" in dockerfile
