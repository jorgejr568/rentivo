import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GITIGNORE = REPO_ROOT / ".gitignore"
API_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile.api"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
NGINX_CONFIG = REPO_ROOT / "infra" / "proxy" / "nginx.conf"
PREVIEW_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test-pr.yaml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
DOCKER_BUILD_ACTION = REPO_ROOT / ".github" / "actions" / "docker-build" / "action.yml"
DEPENDABOT_CONFIG = REPO_ROOT / ".github" / "dependabot.yml"
BACKEND_PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"
CHECKOUT_SHA = "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
LOGIN_SHA = "c94ce9fb468520275223c153574b00df6fe4bcc9"
SETUP_BUILDX_SHA = "8d2750c68a42422c14e847fe6c8ac0403b4cbd6f"
BUILD_PUSH_SHA = "10e90e3645eae34f1e60eeb005ba3a3d33f178e8"
ATTEST_SHA = "977bb373ede98d70efdf65b84cb5f73e068dcc2a"
TRIVY_SHA = "ed142fd0673e97e23eac54620cfb913e5ce36c25"
SETUP_UV_SHA = "08807647e7069bb48b6ef5acd8ec9567f424441b"


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


def test_api_readiness_checks_the_database_and_http_endpoint():
    compose = _yaml(COMPOSE_FILE)
    api = compose["services"]["api"]
    health_command = " ".join(api["healthcheck"]["test"])

    assert "http://localhost:8000/api/v1/ready" in health_command
    assert api["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert compose["services"]["proxy"]["healthcheck"]["test"][-1] == ("http://localhost/api/v1/ready")


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
    for service_name in ("db", "migrate", "worker", "api", "frontend"):
        assert "ingress" not in compose["services"][service_name].get("networks", [])


def test_database_interpolation_and_application_runtime_env_are_separate():
    compose = _yaml(COMPOSE_FILE)

    for service_name in ("migrate", "worker", "api"):
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
    assert disposable_environment.count("RENTIVO_ENVIRONMENT: dev") == 3


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
    assert "validate_production_settings" in startup
    assert "up --build -d db migrate api worker" in startup
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
    assert image_scan["uses"] == f"aquasecurity/trivy-action@{TRIVY_SHA}"
    assert image_scan["with"] == {
        "exit-code": "1",
        "ignore-unfixed": "true",
        "image-ref": "${{ matrix.image }}:${{ github.sha }}",
        "scanners": "vuln",
        "severity": "HIGH,CRITICAL",
    }
    assert set(jobs["all-checks-pass"]["needs"]) == {"release-gate", "production-images"}


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
    assert deploy["needs"] == "publish-images"
    assert deploy["permissions"] == {"contents": "read"}
    assert deploy["environment"]["name"] == "production"
    assert deploy_script.count("curl ") == 1
    assert "X-Idempotency-Key" in deploy_script
    assert "Authorization: Bearer" in deploy_script
    assert "schema_version" in deploy_script
    for field in ("migration", "rollout", "smoke", "deployment_count"):
        assert field in deploy_script
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
        for path in (DOCKER_BUILD_ACTION, PR_WORKFLOW, DEPLOY_WORKFLOW, RELEASE_WORKFLOW, DEPENDABOT_CONFIG)
    )

    for deleted_path in ("docker-compose.next", "Dockerfile.legacy", "legacy_web", ".env.preview"):
        assert deleted_path not in contract


def test_backend_version_matches_the_breaking_release():
    metadata = tomllib.loads(BACKEND_PYPROJECT.read_text())

    assert metadata["project"]["version"] == "5.0.0"
