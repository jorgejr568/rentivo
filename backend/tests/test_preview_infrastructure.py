import re
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GITIGNORE = REPO_ROOT / ".gitignore"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
API_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile.api"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
DEV_COMPOSE_FILE = REPO_ROOT / "docker-compose.dev.yml"
MAKEFILE = REPO_ROOT / "Makefile"
NGINX_CONFIG = REPO_ROOT / "infra" / "proxy" / "nginx.conf"
PREVIEW_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test-pr.yaml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
ROLLBACK_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "rollback.yml"
PREPARE_LEGACY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "prepare-legacy-rollback.yml"
SETUP_ACTION = REPO_ROOT / ".github" / "actions" / "setup" / "action.yml"
DOCKER_BUILD_ACTION = REPO_ROOT / ".github" / "actions" / "docker-build" / "action.yml"
DEPENDABOT_CONFIG = REPO_ROOT / ".github" / "dependabot.yml"
BACKEND_PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"
CLAUDE_DOC = REPO_ROOT / "CLAUDE.md"
CONTRIBUTING_DOC = REPO_ROOT / "CONTRIBUTING.md"
PRODUCTION_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "production-release.md"
CHECKOUT_SHA = "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
LOGIN_SHA = "c94ce9fb468520275223c153574b00df6fe4bcc9"
SETUP_BUILDX_SHA = "8d2750c68a42422c14e847fe6c8ac0403b4cbd6f"
BUILD_PUSH_SHA = "10e90e3645eae34f1e60eeb005ba3a3d33f178e8"
ATTEST_SHA = "977bb373ede98d70efdf65b84cb5f73e068dcc2a"
TRIVY_SHA = "ed142fd0673e97e23eac54620cfb913e5ce36c25"
SETUP_UV_SHA = "08807647e7069bb48b6ef5acd8ec9567f424441b"
SETUP_NODE_SHA = "249970729cb0ef3589644e2896645e5dc5ba9c38"
UPLOAD_ARTIFACT_SHA = "b7c566a772e6b6bfb58ed0dc250532a479d7789f"
CODECOV_SHA = "a99c28d3f0da835de33ff2feb2e15691c7b9641f"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_api_runtime_trusts_only_the_production_proxy():
    dockerfile = API_DOCKERFILE.read_text()
    compose = _yaml(COMPOSE_FILE)
    command = " ".join(compose["services"]["api"]["command"])

    assert "--forwarded-allow-ips=*" not in dockerfile
    assert "--forwarded-allow-ips=127.0.0.1" in dockerfile
    assert "--forwarded-allow-ips=${RENTIVO_PROXY_IP:-172.30.0.10}" in command
    assert compose["services"]["proxy"]["networks"]["app-edge"]["ipv4_address"] == ("${RENTIVO_PROXY_IP:-172.30.0.10}")


def test_api_healthcheck_uses_liveness_while_proxy_checks_readiness():
    compose = _yaml(COMPOSE_FILE)
    api = compose["services"]["api"]
    health_command = " ".join(api["healthcheck"]["test"])
    dockerfile = API_DOCKERFILE.read_text()

    assert "curl --fail --silent --show-error --max-time 2 --output /dev/null" in health_command
    assert 'CMD ["curl", "--fail", "--silent", "--show-error", "--max-time", "2", "--output", "/dev/null"' in dockerfile
    assert "http://localhost:8000/api/v1/health" in health_command
    assert "http://localhost:8000/api/v1/health" in dockerfile
    assert "get_engine" not in dockerfile.split("HEALTHCHECK", maxsplit=1)[1]
    assert api["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert compose["services"]["proxy"]["healthcheck"]["test"][-1] == ("http://localhost/api/v1/ready")


def test_production_validation_is_a_one_shot_migration_prerequisite():
    compose = _yaml(COMPOSE_FILE)
    validate = compose["services"]["validate"]
    migrate = compose["services"]["migrate"]

    assert validate["build"] == {
        "context": ".",
        "dockerfile": "backend/Dockerfile.api",
    }
    assert "validate_production_settings" in " ".join(validate["command"])
    assert validate["restart"] == "no"
    assert validate["depends_on"] == {"db": {"condition": "service_healthy"}}
    assert migrate["depends_on"] == {
        "db": {"condition": "service_healthy"},
        "validate": {"condition": "service_completed_successfully"},
    }
    assert _yaml(DEV_COMPOSE_FILE)["services"]["validate"]["environment"] == {"RENTIVO_ENVIRONMENT": "dev"}
    assert "build validate migrate api worker frontend" in MAKEFILE.read_text()


def test_production_cookie_and_webauthn_settings_are_explicit():
    environment = _yaml(COMPOSE_FILE)["services"]["api"]["environment"]
    expected_environment = {
        "RENTIVO_ACCESS_COOKIE_NAME": "__Host-rentivo_access",
        "RENTIVO_CHALLENGE_COOKIE_NAME": "__Host-rentivo_challenge",
        "RENTIVO_COOKIE_SECURE": "true",
        "RENTIVO_CSRF_COOKIE_NAME": "__Host-rentivo_csrf",
        "RENTIVO_ENVIRONMENT": "production",
        "RENTIVO_PUBLIC_APP_URL": "${RENTIVO_PUBLIC_ORIGIN:?Set the public HTTPS origin}",
        "RENTIVO_PUBLIC_URL": "${RENTIVO_PUBLIC_ORIGIN:?Set the public HTTPS origin}",
        "RENTIVO_WEBAUTHN_ORIGIN": "${RENTIVO_PUBLIC_ORIGIN:?Set the public HTTPS origin}",
        "RENTIVO_WEBAUTHN_RP_ID": "${RENTIVO_WEBAUTHN_RP_ID:?Set the public hostname}",
    }
    assert expected_environment.items() <= environment.items()


def test_proxy_accepts_tls_metadata_only_from_a_configured_terminator():
    compose = _yaml(COMPOSE_FILE)
    nginx = NGINX_CONFIG.read_text()

    assert compose["services"]["proxy"]["environment"]["RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR"] == (
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


def test_production_ports_are_loopback_only_and_database_has_no_fallbacks():
    compose = _yaml(COMPOSE_FILE)

    assert compose["services"]["db"]["ports"] == ["127.0.0.1:${MYSQL_PORT:-3306}:3306"]
    assert compose["services"]["proxy"]["ports"] == ["127.0.0.1:${RENTIVO_PORT:-8080}:80"]
    assert compose["services"]["db"]["environment"] == {
        "MYSQL_DATABASE": "${MYSQL_DATABASE:?Set the database name}",
        "MYSQL_PASSWORD": "${MYSQL_PASSWORD:?Set the database password}",
        "MYSQL_ROOT_PASSWORD": "${MYSQL_ROOT_PASSWORD:?Set the database root password}",
        "MYSQL_USER": "${MYSQL_USER:?Set the database user}",
    }


def test_proxy_uses_a_dedicated_non_internal_ingress_network():
    compose = _yaml(COMPOSE_FILE)

    assert compose["networks"]["app-edge"]["internal"] is True
    assert compose["networks"]["ingress"].get("internal", False) is False
    assert set(compose["services"]["proxy"]["networks"]) == {"app-edge", "ingress"}
    for service_name in ("db", "validate", "migrate", "worker", "api", "frontend"):
        assert "ingress" not in compose["services"][service_name].get("networks", [])


def test_database_interpolation_and_application_runtime_env_are_separate():
    compose = _yaml(COMPOSE_FILE)

    for service_name in ("validate", "migrate", "worker", "api"):
        service = compose["services"][service_name]
        assert service["env_file"] == [
            {
                "path": "${RENTIVO_APP_ENV_FILE:-.env}",
                "required": True,
            }
        ]
        assert "MYSQL_ROOT_PASSWORD" not in service.get("environment", {})
        assert "RENTIVO_DB_URL" not in service.get("environment", {})
    assert "RENTIVO_ENV_FILE" not in COMPOSE_FILE.read_text()
    assert "mysql+pymysql://${MYSQL_USER" not in COMPOSE_FILE.read_text()


def test_environment_examples_remain_trackable():
    patterns = set(GITIGNORE.read_text().splitlines())

    assert "!.env.example" in patterns


def test_docker_build_context_excludes_environment_files_except_examples():
    patterns = DOCKERIGNORE.read_text().splitlines()

    assert "**/.env*" in patterns
    assert "!.env.example" in patterns
    assert "!.env.db.example" in patterns


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


def test_image_builds_are_consolidated_under_the_complete_release_gate():
    assert not PREVIEW_WORKFLOW.exists()
    workflow = _yaml(PR_WORKFLOW)
    jobs = workflow["jobs"]

    required_jobs = {
        "backend",
        "e2e",
        "frontend",
        "migrations",
        "compose-config",
        "functional-stack",
        "production-startup",
        "security-scan",
    }
    assert set(jobs["release-gate"]["needs"]) == required_jobs
    assert set(jobs["all-checks-pass"]["needs"]) == {"release-gate", "production-images"}
    assert {item["name"] for item in jobs["production-images"]["strategy"]["matrix"]["include"]} == {
        "api",
        "worker",
        "frontend",
    }


def test_compose_ci_renders_the_promoted_production_and_development_topologies():
    workflow = _yaml(PR_WORKFLOW)
    job = workflow["jobs"]["compose-config"]
    steps = {step["name"]: step for step in job["steps"] if "name" in step}

    assert job["env"] == {
        "MYSQL_DATABASE": "rentivo_compose_ci",
        "MYSQL_PASSWORD": "ci-only-database-password",
        "MYSQL_ROOT_PASSWORD": "ci-only-root-password",
        "MYSQL_USER": "rentivo_compose_ci",
        "RENTIVO_APP_ENV_FILE": "${{ runner.temp }}/rentivo-compose-app.env",
        "RENTIVO_PUBLIC_ORIGIN": "https://rentivo.example.test",
        "RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR": "127.0.0.1/32",
        "RENTIVO_WEBAUTHN_RP_ID": "rentivo.example.test",
    }
    disposable_environment = steps["Create disposable application environment"]["run"]
    assert "umask 077" in disposable_environment
    for variable in (
        "RENTIVO_DB_URL",
        "RENTIVO_SECRET_KEY",
        "RENTIVO_EMAIL_BACKEND",
        "RENTIVO_SES_REGION",
        "RENTIVO_SES_FROM_EMAIL",
        "RENTIVO_STORAGE_BACKEND",
        "RENTIVO_S3_BUCKET",
        "RENTIVO_S3_REGION",
        "RENTIVO_ENCRYPTION_BACKEND",
        "RENTIVO_KMS_KEY_ID",
        "RENTIVO_KMS_REGION",
        "RENTIVO_LOG_JSON",
    ):
        assert f"'{variable}=" in disposable_environment
    assert "change-me-in-production" not in disposable_environment
    assert steps["Validate production Compose"]["run"] == "docker compose -f docker-compose.yml config --quiet"
    assert steps["Validate development Compose"]["run"] == (
        "docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet"
    )
    assert "docker-compose.next" not in PR_WORKFLOW.read_text()
    assert "compose-config" in workflow["jobs"]["release-gate"]["needs"]


def test_api_runtime_source_and_virtualenv_are_read_only_to_appuser():
    dockerfile = API_DOCKERFILE.read_text()

    assert "chown -R appuser:appuser /app" not in dockerfile
    assert "chmod -R a-w /app/.venv /app/backend" in dockerfile
    assert "chown appuser:appuser /app/invoices /app/outbox" in dockerfile


def test_pr_gate_boots_and_exercises_the_functional_stack():
    workflow = _yaml(PR_WORKFLOW)
    jobs = workflow["jobs"]
    stack = jobs["functional-stack"]
    steps = {step["name"]: step for step in stack["steps"] if "name" in step}

    assert {
        "backend",
        "frontend",
        "e2e",
        "migrations",
        "compose-config",
        "functional-stack",
        "production-startup",
        "security-scan",
    } <= set(jobs["release-gate"]["needs"])
    assert jobs["production-images"]["needs"] == "release-gate"
    assert set(jobs["all-checks-pass"]["needs"]) == {"release-gate", "production-images"}
    assert "functional" in stack["name"].lower()
    assert "Create secure disposable stack environment" in steps
    assert "Start functional stack" in steps
    assert "Test production smoke parser" in steps
    assert steps["Test production smoke parser"]["run"] == "npm run pretest"
    assert "Run functional stack smoke" in steps
    assert "Run real-stack Playwright project" in steps
    assert steps["Run real-stack Playwright project"]["env"]["PLAYWRIGHT_PRODUCTION_STACK"] == "1"
    assert "--project=production-stack" in steps["Run real-stack Playwright project"]["run"]
    assert "route(" not in steps["Run real-stack Playwright project"]["run"]
    assert steps["Capture functional stack logs"]["if"] == "always()"
    assert steps["Stop functional stack"]["if"] == "always()"
    disposable_environment = steps["Create secure disposable stack environment"]["run"]
    assert disposable_environment.count("RENTIVO_ENVIRONMENT: dev") == 4
    assert "validate:" in disposable_environment


def test_pr_migrations_rehearse_a_populated_production_head_to_5_0():
    workflow = _yaml(PR_WORKFLOW)
    scripts = "\n".join(str(step.get("run", "")) for step in workflow["jobs"]["migrations"]["steps"])

    assert "upgrade 55dc25bae00d" in scripts
    assert "upgrade head" in scripts
    assert scripts.index("upgrade 55dc25bae00d") < scripts.index("upgrade head")
    assert "downgrade" not in scripts
    for table in ("users", "mfa_totp", "passkeys", "organizations", "billings", "billing_items", "bills"):
        assert table in scripts
    assert "FIXED" in scripts
    assert "VARIABLE" in scripts
    assert "migration-before.json" in scripts
    assert "actual_rows == expected_rows" in scripts
    assert "COUNT(uuid)" in scripts
    assert "COUNT(DISTINCT uuid)" in scripts
    assert "total == populated == distinct" in scripts
    assert "api_keys" in scripts
    assert "auth_challenges" in scripts
    assert "auth_rate_limits" in scripts
    assert "e0f1a2b3c4d5" in scripts


def test_pr_gate_starts_services_with_validated_production_settings():
    workflow = _yaml(PR_WORKFLOW)
    job = workflow["jobs"]["production-startup"]
    steps = {step["name"]: step for step in job["steps"] if "name" in step}
    environment = steps["Create secure production startup environment"]["run"]
    startup = steps["Migrate and start production services"]["run"]

    assert job["env"] == {
        "MYSQL_DATABASE": "rentivo_production_ci",
        "MYSQL_USER": "rentivo_production_ci",
        "RENTIVO_APP_ENV_FILE": "${{ runner.temp }}/rentivo-production-app.env",
        "RENTIVO_PUBLIC_ORIGIN": "https://rentivo.example.test",
        "RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR": "127.0.0.1/32",
        "RENTIVO_WEBAUTHN_RP_ID": "rentivo.example.test",
        "STACK_OVERRIDE": "${{ runner.temp }}/rentivo-production.override.yml",
        "STACK_PROJECT": "rentivo-production-startup",
    }
    assert "RENTIVO_ENVIRONMENT=production" in environment
    assert "RENTIVO_PUBLIC_URL=https://rentivo.example.test" in environment
    assert "RENTIVO_WEBAUTHN_ORIGIN=https://rentivo.example.test" in environment
    assert "RENTIVO_WEBAUTHN_RP_ID=rentivo.example.test" in environment
    assert "RENTIVO_COOKIE_SECURE=true" in environment
    for cookie_name in ("__Host-rentivo_access", "__Host-rentivo_challenge", "__Host-rentivo_csrf"):
        assert cookie_name in environment
    for variable in (
        "RENTIVO_EMAIL_BACKEND=ses",
        "RENTIVO_SES_ENDPOINT_URL=https://ses.example.test",
        "RENTIVO_STORAGE_BACKEND=s3",
        "RENTIVO_S3_ENDPOINT_URL=https://s3.example.test",
        "RENTIVO_ENCRYPTION_BACKEND=kms",
        "RENTIVO_KMS_ENDPOINT_URL=https://kms.example.test",
        "RENTIVO_LOG_JSON=true",
    ):
        assert variable in environment
    assert "RENTIVO_ENVIRONMENT: dev" not in environment
    assert re.search(r"\bAKIA[A-Z0-9]{16}\b", environment) is None
    assert "up --build -d db validate migrate api worker" in startup
    assert "ps -aq validate" in startup
    assert "Production validation failed" in startup
    assert startup.index("ps -aq validate") < startup.index("ps -aq migrate")
    assert "run --rm --no-deps migrate" not in startup
    assert "/api/v1/ready" in startup
    assert "ps --status running --services" in startup
    assert "worker" in startup
    assert steps["Capture production startup logs"]["if"] == "always()"
    assert steps["Stop production startup services"]["if"] == "always()"
    assert "down --volumes --remove-orphans" in steps["Stop production startup services"]["run"]


def test_docker_build_action_supports_exact_immutable_publication():
    action = _yaml(DOCKER_BUILD_ACTION)
    build = action["runs"]["steps"][-1]
    inputs = action["inputs"]

    assert {"dockerfile", "image-name", "image-tag", "cache-scope", "load", "push"} <= inputs.keys()
    assert inputs["load"]["default"] == "false"
    assert inputs["push"]["default"] == "false"
    assert build["id"] == "build"
    assert build["with"]["push"] == "${{ inputs.push }}"
    assert build["with"]["load"] == "${{ inputs.load }}"
    assert build["with"]["tags"] == "${{ inputs.image-name }}:${{ inputs.image-tag }}"
    assert "org.opencontainers.image.revision=${{ github.sha }}" in build["with"]["labels"]
    source_label = "org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}"
    assert source_label in build["with"]["labels"]
    assert action["runs"]["steps"][0]["uses"] == f"docker/setup-buildx-action@{SETUP_BUILDX_SHA}"
    assert build["uses"] == f"docker/build-push-action@{BUILD_PUSH_SHA}"
    assert action["outputs"]["digest"]["value"] == "${{ steps.build.outputs.digest }}"
    assert action["outputs"]["image-ref"]["value"].endswith("@${{ steps.build.outputs.digest }}")
    assert ":latest" not in DOCKER_BUILD_ACTION.read_text()
    assert ":ci" not in DOCKER_BUILD_ACTION.read_text()


def test_dependabot_covers_the_frontend_npm_lockfile():
    updates = _yaml(DEPENDABOT_CONFIG)["updates"]

    assert any(update["package-ecosystem"] == "npm" and update["directory"] == "/frontend" for update in updates)


def test_complete_gate_runs_dependency_repository_and_image_security_scans():
    workflow = _yaml(PR_WORKFLOW)
    jobs = workflow["jobs"]
    scan = jobs["security-scan"]
    scan_steps = {step["name"]: step for step in scan["steps"] if "name" in step}
    image_steps = jobs["production-images"]["steps"]
    image_scan = next(step for step in image_steps if step.get("name") == "Scan immutable image")
    image_build = next(step for step in image_steps if step.get("uses") == "./.github/actions/docker-build")

    assert workflow["permissions"] == {"contents": "read"}
    assert scan["permissions"] == {"contents": "read"}
    assert scan_steps["Checkout"]["uses"] == f"actions/checkout@{CHECKOUT_SHA}"
    assert scan_steps["Audit frontend dependencies"]["run"] == "npm --prefix frontend audit --audit-level=high"
    assert scan_steps["Install uv for locked SAST"]["uses"] == f"astral-sh/setup-uv@{SETUP_UV_SHA}"
    assert scan_steps["Install uv for locked SAST"]["with"] == {"version": "0.11.16"}
    assert scan_steps["Install locked SAST dependencies"]["run"] == ("uv sync --project backend --extra dev --frozen")
    assert scan_steps["Run backend static security analysis"]["run"] == (
        "uv run --project backend --no-sync bandit -r backend/rentivo -ll -ii"
    )
    assert scan_steps["Export locked backend dependencies"]["run"] == (
        "uv export --project backend --all-extras --frozen --no-hashes --no-emit-project "
        '--output-file "$RUNNER_TEMP/rentivo-backend-requirements.txt"'
    )
    for name in ("Audit backend dependencies", "Scan repository secrets and misconfigurations"):
        step = scan_steps[name]
        assert step["uses"] == f"aquasecurity/trivy-action@{TRIVY_SHA}"
        assert step["with"]["exit-code"] == "1"
        assert step["with"]["severity"] == "HIGH,CRITICAL"
    assert scan_steps["Audit backend dependencies"]["with"]["scanners"] == "vuln"
    assert scan_steps["Audit backend dependencies"]["with"]["scan-ref"] == (
        "${{ runner.temp }}/rentivo-backend-requirements.txt"
    )
    assert "skip-dirs" not in scan_steps["Audit backend dependencies"]["with"]
    assert scan_steps["Scan repository secrets and misconfigurations"]["with"]["scanners"] == "secret,misconfig"
    assert scan_steps["Scan repository secrets and misconfigurations"]["with"]["skip-dirs"] == ".venv"
    assert "security-scan" in jobs["release-gate"]["needs"]
    assert image_build["with"]["load"] == "true"
    assert image_build["with"]["push"] == "false"
    assert jobs["production-images"].get("permissions", {"contents": "read"}) == {"contents": "read"}
    assert image_scan["uses"] == f"aquasecurity/trivy-action@{TRIVY_SHA}"
    assert image_scan["with"] == {
        "exit-code": "1",
        "ignore-unfixed": "true",
        "image-ref": "${{ matrix.image }}:${{ github.sha }}",
        "scanners": "vuln",
        "severity": "HIGH,CRITICAL",
    }
    assert set(jobs["all-checks-pass"]["needs"]) == {"release-gate", "production-images"}


def test_every_external_action_is_pinned_to_an_expected_commit():
    paths = tuple(sorted((REPO_ROOT / ".github" / "workflows").glob("*.y*ml"))) + tuple(
        sorted((REPO_ROOT / ".github" / "actions").glob("**/action.yml"))
    )
    expected = {
        "actions/checkout": CHECKOUT_SHA,
        "actions/setup-node": SETUP_NODE_SHA,
        "actions/upload-artifact": UPLOAD_ARTIFACT_SHA,
        "astral-sh/setup-uv": SETUP_UV_SHA,
        "codecov/codecov-action": CODECOV_SHA,
        "docker/login-action": LOGIN_SHA,
        "docker/build-push-action": BUILD_PUSH_SHA,
        "docker/setup-buildx-action": SETUP_BUILDX_SHA,
        "actions/attest-build-provenance": ATTEST_SHA,
        "aquasecurity/trivy-action": TRIVY_SHA,
    }
    found: set[str] = set()

    for path in paths:
        for action_spec in re.findall(r"uses:\s+([^\s#]+)", path.read_text()):
            if action_spec.startswith("./"):
                continue
            assert "@" in action_spec, f"{path}: {action_spec} is not pinned"
            action, ref = action_spec.rsplit("@", 1)
            assert re.fullmatch(r"[0-9a-f]{40}", ref), f"{path}: {action}@{ref} is mutable"
            assert action in expected, f"Add the reviewed SHA for {action}"
            assert ref == expected[action]
            found.add(action)

    assert found == set(expected)


def test_backend_sast_tool_is_exactly_pinned_in_the_lock_contract():
    metadata = tomllib.loads(BACKEND_PYPROJECT.read_text())

    assert "bandit[toml]==1.9.4" in metadata["project"]["optional-dependencies"]["dev"]


def test_backend_dependency_floors_exclude_audited_high_vulnerabilities():
    project = tomllib.loads(BACKEND_PYPROJECT.read_text())["project"]
    dependencies = project["dependencies"]

    assert "cryptography>=48.0.1,<49" in dependencies
    assert "starlette>=1.3.1,<2" in dependencies
    assert project["optional-dependencies"]["temporal"] == ["temporalio>=1.30,<2"]


def test_deploy_runs_one_protected_atomic_webhook_for_the_tested_sha():
    workflow = _yaml(DEPLOY_WORKFLOW)
    jobs = workflow["jobs"]
    deploy = jobs["deploy"]
    publish = jobs["publish-images"]
    resolve = jobs["resolve-images"]
    verify = jobs["verify-images"]
    deploy_script = next(step["run"] for step in deploy["steps"] if step.get("name") == "Deploy tested images once")

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert jobs["gate"]["uses"] == "./.github/workflows/test-pr.yaml"
    assert publish["needs"] == "gate"
    assert publish["permissions"] == {
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
        "packages": "write",
    }
    assert publish["outputs"] == {
        "api-digest": "${{ steps.api.outputs.digest }}",
        "api-ref": "${{ steps.api.outputs.image-ref }}",
        "frontend-digest": "${{ steps.frontend.outputs.digest }}",
        "frontend-ref": "${{ steps.frontend.outputs.image-ref }}",
        "worker-digest": "${{ steps.worker.outputs.digest }}",
        "worker-ref": "${{ steps.worker.outputs.image-ref }}",
    }
    assert "matrix" not in publish.get("strategy", {})
    build_steps = [step for step in publish["steps"] if step.get("uses") == "./.github/actions/docker-build"]
    assert {step["id"] for step in build_steps} == {"api", "worker", "frontend"}
    assert all(step["with"]["image-tag"] == "${{ github.sha }}" for step in build_steps)
    assert all(step["with"]["push"] == "true" for step in build_steps)
    for image in ("API", "worker", "frontend"):
        build_index = next(
            index for index, step in enumerate(publish["steps"]) if step.get("name") == f"Publish {image} image"
        )
        scan_index = next(
            index for index, step in enumerate(publish["steps"]) if step.get("name") == f"Scan {image} image"
        )
        attest_index = next(
            index
            for index, step in enumerate(publish["steps"])
            if step.get("name") == f"Attest {image} image provenance"
        )
        scan = publish["steps"][scan_index]
        image_id = image.lower()
        assert build_index < scan_index < attest_index
        assert scan["uses"] == f"aquasecurity/trivy-action@{TRIVY_SHA}"
        assert scan["with"]["image-ref"] == f"${{{{ steps.{image_id}.outputs.image-ref }}}}"
        assert scan["with"]["exit-code"] == "1"
        assert scan["with"]["severity"] == "HIGH,CRITICAL"
    attestation_steps = [
        step for step in publish["steps"] if step.get("uses") == f"actions/attest-build-provenance@{ATTEST_SHA}"
    ]
    assert len(attestation_steps) == 3
    assert {step["with"]["subject-name"].rsplit("/", 1)[-1] for step in attestation_steps} == {
        "api",
        "frontend",
        "worker",
    }
    assert all(step["with"]["push-to-registry"] is True for step in attestation_steps)
    assert {step["with"]["subject-digest"] for step in attestation_steps} == {
        "${{ steps.api.outputs.digest }}",
        "${{ steps.frontend.outputs.digest }}",
        "${{ steps.worker.outputs.digest }}",
    }
    assert next(step for step in publish["steps"] if step.get("name") == "Checkout")["uses"] == (
        f"actions/checkout@{CHECKOUT_SHA}"
    )
    assert next(step for step in publish["steps"] if step.get("name") == "Authenticate to GHCR")["uses"] == (
        f"docker/login-action@{LOGIN_SHA}"
    )
    assert resolve["needs"] == "publish-images"
    assert resolve["permissions"] == {"attestations": "read", "contents": "read", "packages": "read"}
    assert resolve["outputs"] == {
        "api-digest": "${{ steps.resolve.outputs.api-digest }}",
        "api-ref": "${{ steps.resolve.outputs.api-ref }}",
        "frontend-digest": "${{ steps.resolve.outputs.frontend-digest }}",
        "frontend-ref": "${{ steps.resolve.outputs.frontend-ref }}",
        "worker-digest": "${{ steps.resolve.outputs.worker-digest }}",
        "worker-ref": "${{ steps.resolve.outputs.worker-ref }}",
    }
    resolve_script = next(step["run"] for step in resolve["steps"] if step.get("name") == "Resolve and verify images")
    assert resolve["env"] == {
        "PUBLISHED_API_DIGEST": "${{ needs.publish-images.outputs.api-digest }}",
        "PUBLISHED_API_REF": "${{ needs.publish-images.outputs.api-ref }}",
        "PUBLISHED_FRONTEND_DIGEST": "${{ needs.publish-images.outputs.frontend-digest }}",
        "PUBLISHED_FRONTEND_REF": "${{ needs.publish-images.outputs.frontend-ref }}",
        "PUBLISHED_WORKER_DIGEST": "${{ needs.publish-images.outputs.worker-digest }}",
        "PUBLISHED_WORKER_REF": "${{ needs.publish-images.outputs.worker-ref }}",
    }
    assert 'docker buildx imagetools inspect "$tag_ref"' in resolve_script
    assert 'local published_digest="$2" published_ref="$3"' in resolve_script
    assert '[ "$digest" = "$published_digest" ]' in resolve_script
    assert '[ "$digest_ref" = "$published_ref" ]' in resolve_script
    assert 'docker pull "$digest_ref"' in resolve_script
    assert "org.opencontainers.image.revision" in resolve_script
    assert "org.opencontainers.image.source" in resolve_script
    assert 'gh attestation verify "oci://$digest_ref"' in resolve_script
    assert ".github/workflows/deploy.yml" in resolve_script
    assert resolve_script.count("resolve_verified_image ") == 3
    for image in ("API", "WORKER", "FRONTEND"):
        assert f'"$PUBLISHED_{image}_DIGEST" "$PUBLISHED_{image}_REF"' in resolve_script
    assert 'echo "${image}-digest=$digest"' in resolve_script
    assert 'echo "${image}-ref=$digest_ref"' in resolve_script

    assert verify["needs"] == "resolve-images"
    assert verify["permissions"] == {"contents": "read", "packages": "read"}
    assert verify["env"] == {
        "API_REF": "${{ needs.resolve-images.outputs.api-ref }}",
        "FRONTEND_REF": "${{ needs.resolve-images.outputs.frontend-ref }}",
        "WORKER_REF": "${{ needs.resolve-images.outputs.worker-ref }}",
    }
    verify_steps = {step["name"]: step for step in verify["steps"] if "name" in step}
    override = verify_steps["Create exact-image stack environment"]["run"]
    assert "RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR=127.0.0.1/32" in override
    for local_backend in (
        "RENTIVO_EMAIL_BACKEND=local",
        "RENTIVO_STORAGE_BACKEND=local",
        "RENTIVO_ENCRYPTION_BACKEND=base64",
    ):
        assert local_backend in override
    for service in ("validate", "migrate", "api"):
        assert f"{service}:" in override
        assert "image: ${API_REF:?API_REF is required}" in override
    assert "image: ${WORKER_REF:?WORKER_REF is required}" in override
    assert "image: ${FRONTEND_REF:?FRONTEND_REF is required}" in override
    assert override.count("RENTIVO_ENVIRONMENT: dev") == 4
    startup = verify_steps["Start and verify exact-image stack"]["run"]
    assert "RENTIVO_PORT=18080" in startup
    assert "--no-build" in startup
    assert "docker build" not in startup
    assert " up " in startup
    assert "validate migrate api worker frontend proxy" in startup
    assert verify_steps["Run exact-image shell smoke"]["run"].endswith("http://127.0.0.1:18080")
    assert verify_steps["Run exact-image Playwright smoke"]["env"] == {
        "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:18080",
        "PLAYWRIGHT_PRODUCTION_STACK": "1",
    }
    assert "--project=production-stack" in verify_steps["Run exact-image Playwright smoke"]["run"]

    assert set(deploy["needs"]) == {"resolve-images", "verify-images"}
    assert deploy["permissions"] == {"contents": "read"}
    assert deploy["environment"]["name"] == "production"
    assert deploy["env"]["EXPECTED_ALEMBIC_REVISION"] == "e0f1a2b3c4d5"
    assert deploy_script.count("curl ") == 1
    assert "X-Idempotency-Key" in deploy_script
    assert "Authorization: Bearer" in deploy_script
    assert 'schema_version "rentivo.deploy.v2"' in deploy_script
    assert "expected_alembic_revision" in deploy_script
    assert ".migration.revision == $expected_alembic_revision" in deploy_script
    assert ".migration.exit_code == 0" in deploy_script
    assert ".migration.log_sha256" in deploy_script
    assert ".stage_order == $required_stages" in deploy_script
    for stage in ("configuration", "production_integrations", "migration", "rollout", "smoke"):
        assert f".{stage}.started_at" in deploy_script
        assert f".{stage}.completed_at" in deploy_script
    assert "fromdateiso8601" in deploy_script
    assert ".configuration.started_at <=" not in deploy_script
    for field in (
        "configuration",
        "production_integrations",
        "migration",
        "rollout",
        "smoke",
        "deployment_count",
    ):
        assert field in deploy_script
    assert 'required_stages: ["configuration", "production_integrations", "migration", "rollout", "smoke"]' in (
        deploy_script
    )
    for image in ("api", "worker", "frontend"):
        assert f".images.{image}.reference == ${image}_ref" in deploy_script
        assert f".images.{image}.digest == ${image}_digest" in deploy_script
    assert "sha256:[0-9a-f]" in deploy_script
    assert "from urllib.parse import urlsplit" in deploy_script
    assert 'parsed.scheme != "https"' in deploy_script
    assert "not parsed.hostname" in deploy_script
    assert "parsed.username is not None" in deploy_script
    assert "parsed.password is not None" in deploy_script
    assert "--insecure" not in deploy_script
    assert " -k" not in deploy_script
    assert "for " not in deploy_script
    assert "sleep " not in deploy_script
    assert "DEPLOY_TRIGGER_URL" not in DEPLOY_WORKFLOW.read_text()


def test_protected_rollback_workflow_can_restore_legacy_or_new_stack_artifacts():
    workflow = _yaml(ROLLBACK_WORKFLOW)
    trigger = workflow.get("on", workflow.get(True))["workflow_dispatch"]
    inputs = trigger["inputs"]
    job = workflow["jobs"]["rollback"]
    script = next(step["run"] for step in job["steps"] if step.get("name") == "Execute protected rollback")

    assert inputs["rollback_kind"]["options"] == ["first-5.0-cutover", "new-stack", "new-stack-restore"]
    assert {
        "target_sha",
        "expected_alembic_revision",
        "database_backup_id",
        "database_backup_sha256",
        "legacy_attestation_source_sha",
        "legacy_web_ref",
        "legacy_worker_ref",
        "api_ref",
        "worker_ref",
        "frontend_ref",
    } <= set(inputs)
    assert inputs["database_backup_id"]["required"] is False
    assert inputs["database_backup_sha256"]["required"] is False
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {"group": "rentivo-production", "cancel-in-progress": False}
    assert job["environment"]["name"] == "production"
    assert job["permissions"] == {"attestations": "read", "contents": "read", "packages": "read"}
    assert script.count("curl ") == 1
    assert 'schema_version "rentivo.rollback.v1"' in script
    assert "X-Idempotency-Key" in script
    assert "Authorization: Bearer" in script
    assert "first-5.0-cutover" in script
    assert '[[ "$EXPECTED_ALEMBIC_REVISION" == "55dc25bae00d" ]]' in script
    assert "new-stack" in script
    assert "new-stack-restore" in script
    assert "database_backup_id" in script
    assert "database_backup_sha256" in script
    assert "expected_alembic_revision" in script
    assert '["maintenance", "drain", "schema_check", "rollout", "smoke"]' in script
    assert '["maintenance", "drain", "database_restore", "rollout", "smoke"]' in script
    assert ".database_restore.revision == $expected_alembic_revision" in script
    assert ".database_restore.backup_id == $database_backup_id" in script
    assert ".database_restore.backup_sha256 == $database_backup_sha256" in script
    assert ".schema_check.revision == $expected_alembic_revision" in script
    assert ".stage_order == $required_stages" in script
    assert "legacy-web" in script
    assert "legacy-worker" in script
    assert "org.opencontainers.image.revision" in script
    assert "org.opencontainers.image.source" in script
    assert "gh attestation verify" in script
    assert '--source-digest "$provenance_sha"' in script
    assert "LEGACY_ATTESTATION_SOURCE_SHA" in script
    assert 'legacy-web legacy-web "$LEGACY_WEB_REF"' in script
    assert script.count('.github/workflows/prepare-legacy-rollback.yml "$LEGACY_ATTESTATION_SOURCE_SHA"') == 2
    assert 'api api "$API_REF" .github/workflows/deploy.yml "$TARGET_SHA"' in script
    assert ".github/workflows/prepare-legacy-rollback.yml" in script
    assert ".github/workflows/deploy.yml" in script
    assert "sha256sum" in script
    assert "rentivo-rollback-${payload_hash}" in script
    assert "fromdateiso8601" in script
    assert ".maintenance.started_at <=" not in script
    assert "@sha256:" in script
    assert "docker build" not in script
    assert "imagetools inspect" not in script
    assert ":latest" not in script


def test_legacy_rollback_artifacts_are_built_tested_scanned_and_attested_once():
    workflow = _yaml(PREPARE_LEGACY_WORKFLOW)
    trigger = workflow.get("on", workflow.get(True))["workflow_dispatch"]
    job = workflow["jobs"]["prepare"]
    steps = job["steps"]
    scripts = "\n".join(str(step.get("run", "")) for step in steps)

    assert set(trigger["inputs"]) == {"legacy_sha"}
    assert trigger["inputs"]["legacy_sha"]["required"] is True
    assert workflow["permissions"] == {"contents": "read"}
    assert job["environment"]["name"] == "production"
    assert job["permissions"] == {
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
        "packages": "write",
    }
    assert "merge-base --is-ancestor" in scripts
    assert "GITHUB_SHA" in scripts
    assert "Attestation workflow source" in scripts
    assert "uv sync --all-extras --frozen" in scripts
    assert "pytest" in scripts
    builds = [step for step in steps if step.get("uses", "").startswith("docker/build-push-action@")]
    assert len(builds) == 2
    assert {step["with"]["file"] for step in builds} == {"Dockerfile", "Dockerfile.worker"}
    assert {step["with"]["tags"].split("/")[-1].split(":")[0] for step in builds} == {
        "legacy-web",
        "legacy-worker",
    }
    assert all(step["with"]["push"] is True for step in builds)
    assert all("org.opencontainers.image.revision" in step["with"]["labels"] for step in builds)
    assert all("org.opencontainers.image.source" in step["with"]["labels"] for step in builds)
    assert "LEGACY_ARTIFACT_TAG" in job["env"]
    assert "github.run_id" in job["env"]["LEGACY_ARTIFACT_TAG"]
    assert "github.run_attempt" in job["env"]["LEGACY_ARTIFACT_TAG"]
    assert all("${{ env.LEGACY_ARTIFACT_TAG }}" in step["with"]["tags"] for step in builds)
    assert "Reject existing mutable legacy tags" not in PREPARE_LEGACY_WORKFLOW.read_text()
    scans = [step for step in steps if step.get("uses", "").startswith("aquasecurity/trivy-action@")]
    attestations = [step for step in steps if step.get("uses", "").startswith("actions/attest-build-provenance@")]
    assert len(scans) == len(attestations) == 2
    assert all(step["with"]["exit-code"] == "1" for step in scans)
    assert all(step["with"]["severity"] == "HIGH,CRITICAL" for step in scans)
    assert all(step["with"]["push-to-registry"] is True for step in attestations)
    assert ":latest" not in PREPARE_LEGACY_WORKFLOW.read_text()


def test_release_requires_the_exact_commit_gate_and_published_images():
    workflow = _yaml(RELEASE_WORKFLOW)
    jobs = workflow["jobs"]
    verification = jobs["verify-images"]
    release = jobs["release"]
    verification_script = next(
        step["run"] for step in verification["steps"] if step.get("name") == "Require exact commit images"
    )

    assert workflow["permissions"] == {"contents": "read"}
    assert jobs["gate"]["uses"] == "./.github/workflows/test-pr.yaml"
    assert verification["needs"] == "gate"
    assert verification["permissions"] == {"attestations": "read", "contents": "read", "packages": "read"}
    assert "docker buildx imagetools inspect \"$tag_ref\" --format '{{json .Manifest}}'" in verification_script
    assert "jq -er '.digest'" in verification_script
    assert "sha256sum" not in verification_script
    assert "org.opencontainers.image.revision" in verification_script
    assert "org.opencontainers.image.source" in verification_script
    assert 'gh attestation verify "oci://$digest_ref"' in verification_script
    assert '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/deploy.yml"' in verification_script
    for argument in ("--repo", "--signer-workflow", "--source-digest", "--deny-self-hosted-runners"):
        assert argument in verification_script
    assert verification_script.count("require_verified_image") == 4
    assert ":latest" not in verification_script
    verify_steps = {step["name"]: step for step in verification["steps"] if "name" in step}
    assert verify_steps["Authenticate to GHCR"]["uses"] == f"docker/login-action@{LOGIN_SHA}"
    assert verify_steps["Enable Docker Buildx"]["uses"] == f"docker/setup-buildx-action@{SETUP_BUILDX_SHA}"
    assert set(release["needs"]) == {"gate", "verify-images"}
    assert release["permissions"] == {"contents": "write"}
    checkout = next(step for step in release["steps"] if step.get("name") == "Checkout")
    assert checkout["uses"] == f"actions/checkout@{CHECKOUT_SHA}"


def test_release_contract_has_no_deleted_preview_or_legacy_paths():
    contract = "\n".join(
        path.read_text()
        for path in (
            DOCKER_BUILD_ACTION,
            PR_WORKFLOW,
            DEPLOY_WORKFLOW,
            RELEASE_WORKFLOW,
            DEPENDABOT_CONFIG,
            GITIGNORE,
            MAKEFILE,
        )
    )

    for deleted_path in (
        "docker-compose.next",
        "Dockerfile.legacy",
        "legacy_web",
        ".env.preview",
        "preview-config",
        "preview-build",
        "preview-migrate",
        "preview-up",
        "preview-stop",
    ):
        assert deleted_path not in contract


def test_contributor_docs_describe_the_current_react_fastapi_contract():
    docs = CLAUDE_DOC.read_text() + "\n" + CONTRIBUTING_DOC.read_text()
    forbidden = (
        "backend/legacy_web",
        "backend/tests/web",
        "Dockerfile.legacy",
        "make web-createuser",
        "make web-run",
    )

    for stale in forbidden:
        assert stale not in docs
    for current in ("React", "FastAPI", "frontend/src", "backend/rentivo/api"):
        assert current in docs

    contributing = CONTRIBUTING_DOC.read_text()
    for contract in (
        "SQLite",
        "ephemeral Temporal",
        "MariaDB",
        "backend/tests/api/conftest.py",
        "functional-stack",
        "production-startup",
        "production-images",
    ):
        assert contract in contributing


def test_runbook_defines_the_one_time_5_0_rollback_artifact_and_release_guards():
    runbook = PRODUCTION_RUNBOOK.read_text()

    assert "first 5.0 cutover" in runbook
    assert "verified pre-cutover legacy web and worker image digests" in runbook
    assert "database backup" in runbook
    assert "one rollback artifact" in runbook
    assert "Later releases must not use the legacy images" in runbook
    assert "prepare-legacy-rollback.yml" in runbook
    assert "55dc25bae00d" in runbook
    assert "e0f1a2b3c4d5" in runbook
    assert "populated production migration rehearsal" in runbook
    assert "legacy_web_ref" in runbook
    assert "legacy_worker_ref" in runbook
    assert "legacy_attestation_source_sha" in runbook
    assert "new-stack-restore" in runbook
    assert "image-only" in runbook
    assert "schema_check" in runbook
    assert "full normalized rollback payload" in runbook
    assert "fractional seconds" in runbook
    for procedure in (
        "Enter maintenance mode",
        "Stop the API and worker",
        "Restore the verified pre-cutover database backup",
        "Redeploy the verified pre-cutover legacy web and worker images by digest",
        "Run the pre-cutover smoke suite",
        "Re-enable traffic",
    ):
        assert procedure in runbook
    for integration in ("KMS", "S3", "SES", "job backend"):
        assert integration in runbook
    assert "before migration" in runbook
    assert "never rebuilt after verification" in runbook


def test_backend_version_matches_the_breaking_release():
    metadata = tomllib.loads(BACKEND_PYPROJECT.read_text())

    assert metadata["project"]["version"] == "5.0.0"
