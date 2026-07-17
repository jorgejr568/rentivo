# Frontend/Backend API-Key Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish Rentivo's independently buildable FastAPI backend and React/Vite frontend, replace browser identity with scoped API-key login tokens, preserve every existing authentication/security workflow, and add integration-key management without changing production routing.

**Architecture:** A uv workspace contains the relocated Python backend and legacy Jinja runtime, while a separate Vite/TypeScript project owns the replacement frontend. FastAPI exposes `/api/v1`, resolves either an HttpOnly login-key cookie or Bearer integration key into a common principal, and intersects scopes, workspace grants, live memberships, and existing domain roles. The legacy deployment remains production-default until later domain plans complete the big-bang cutover.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2, SQLAlchemy Core, Alembic, MariaDB/SQLite tests, React, Vite, TypeScript, React Router, TanStack Query, openapi-typescript/openapi-fetch, Vitest, Testing Library, Playwright, Docker Compose.

## Global Constraints

- Keep all customer-facing copy in PT-BR and all identifiers/comments in English.
- Preserve current URLs, CSS, fonts, class names, responsive behavior, keyboard behavior, analytics events, authorization outcomes, and audit semantics.
- Browser login tokens use `rntv-v1-<32 random bytes as base64url>`, a fixed 24-hour lifetime, and a Secure/HttpOnly/SameSite=Lax cookie in staging and production.
- Integration keys default to 90 days, never exceed one year, expose the full secret once, and store only SHA-256 plus the first four/final two random-secret characters.
- Hidden login tokens never appear in API-key management responses or UI.
- Integration authorization is scopes AND explicit personal/organization grants AND live membership AND existing role checks.
- Account, security, API-key management, organization settings, membership, role, and ownership operations require a login token.
- Preserve repository/storage/encryption/cache abstractions and use integer centavos for money.
- Prefix backend Python commands with `uv run --project backend`; never use bare `python`, `pip`, or `pytest`.
- Backend and authored frontend coverage thresholds remain 100%.
- Keep migrations additive and maintain a single Alembic head.
- Do not switch production routing or remove the legacy Jinja runtime in this plan.

## Dependency and Parallelization Map

Task 1 is the shared repository move and must finish first. After Task 2 establishes shared backend interfaces, Task 3 (API-key persistence), Task 10 (frontend shell/styles), and the Playwright setup portion of Task 14 own disjoint files and may run in parallel. Tasks 4-9 form the backend dependency chain. Task 11 can begin after Task 6 and Task 9 publish the auth contract. Task 12 begins after Tasks 7-9. Task 13 can run after Task 4. Task 14 performs final convergence and must run last.

---

### Task 1: Convert the Repository into an Independently Buildable Monorepo

**Files:**
- Create: `pyproject.toml` (uv workspace manifest)
- Create: `backend/pyproject.toml`
- Move: `rentivo/` to `backend/rentivo/`
- Move: `web/` to `backend/legacy_web/`
- Move: `tests/` to `backend/tests/`
- Move: `alembic/` to `backend/alembic/`
- Move: `alembic.ini` to `backend/alembic.ini`
- Move: `Dockerfile` to `backend/Dockerfile.legacy`
- Move: `Dockerfile.worker` to `backend/Dockerfile.worker`
- Modify: `Makefile`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.dev.yml`
- Modify: `.github/workflows/test-pr.yaml`
- Modify: `.github/workflows/deploy.yml`
- Modify: `.pre-commit-config.yaml`
- Modify: `README.md`
- Modify: `docs/development.md`
- Modify: all moved Python imports from `web` to `legacy_web`

**Interfaces:**
- Consumes: current `rentivo` and `web` packages and root uv project.
- Produces: importable `rentivo` and `legacy_web` packages under `backend/`; commands `make test`, `make lint`, `make web-run`, and `make worker` continue to work.

- [ ] **Step 1: Capture the clean baseline**

Run:

```bash
uv run pytest -n auto -q
uv run ruff check .
uv run ruff format --check .
```

Expected: all existing tests and both Ruff checks pass before any move.

- [ ] **Step 2: Move backend-owned files with git history**

Run:

```bash
mkdir -p backend
git mv rentivo backend/rentivo
git mv web backend/legacy_web
git mv tests backend/tests
git mv alembic backend/alembic
git mv alembic.ini backend/alembic.ini
git mv pyproject.toml backend/pyproject.toml
git mv Dockerfile backend/Dockerfile.legacy
git mv Dockerfile.worker backend/Dockerfile.worker
```

Expected: Git reports only renames before content edits.

- [ ] **Step 3: Create the uv workspace and update backend packaging**

Write root `pyproject.toml`:

```toml
[tool.uv.workspace]
members = ["backend"]
```

In `backend/pyproject.toml`, keep the existing project/dependencies and set:

```toml
[tool.setuptools.packages.find]
include = ["rentivo*", "legacy_web*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "strict"
asyncio_default_fixture_loop_scope = "function"

[tool.coverage.run]
source = ["rentivo", "legacy_web"]
```

Run:

```bash
uv lock
uv sync --all-extras
```

Expected: one root `uv.lock` resolves the backend workspace member.

- [ ] **Step 4: Rename the legacy Python package consistently**

Replace Python imports and monkeypatch strings from `web.` to `legacy_web.` under `backend/legacy_web` and `backend/tests`, then update runtime entrypoints to `legacy_web.app:app`. Do not rename route URLs or template/static directories.

Verify no stale imports remain:

```bash
rg -n '(^|["'"'])web\.' backend --glob '*.py'
```

Expected: no matches.

- [ ] **Step 5: Update commands, Alembic, containers, and CI paths**

Use these command forms in `Makefile`, hooks, docs, and workflows:

```make
PYTHON  := uv run --project backend python
PYTEST  := uv run --project backend pytest
RUFF    := uv run --project backend ruff
UVICORN := uv run --project backend uvicorn
ALEMBIC := uv run --project backend alembic -c backend/alembic.ini
```

Set `backend/alembic.ini` to `script_location = %(here)s/alembic`. Build legacy and worker images with root build context and their Dockerfiles under `backend/`. Mount `backend/rentivo` and `backend/legacy_web` in development Compose.

- [ ] **Step 6: Verify all legacy behavior after relocation**

Run:

```bash
make lint
make test-cov
uv run --project backend alembic -c backend/alembic.ini heads
docker build -f backend/Dockerfile.legacy -t rentivo-legacy:test .
docker build -f backend/Dockerfile.worker -t rentivo-worker:test .
```

Expected: lint passes, tests retain 100% coverage, Alembic prints one head, and both images build.

- [ ] **Step 7: Commit the monorepo move**

```bash
git add pyproject.toml backend Makefile docker-compose.yml docker-compose.dev.yml .github .pre-commit-config.yaml README.md docs uv.lock
git commit -m "refactor: split backend into monorepo service"
```

---

### Task 2: Add the Shared FastAPI API Foundation

**Files:**
- Create: `backend/rentivo/api/__init__.py`
- Create: `backend/rentivo/api/app.py`
- Create: `backend/rentivo/api/errors.py`
- Create: `backend/rentivo/api/dependencies.py`
- Create: `backend/rentivo/api/routes/__init__.py`
- Create: `backend/rentivo/api/routes/health.py`
- Create: `backend/rentivo/context.py`
- Create: `backend/rentivo/services/container.py`
- Modify: `backend/legacy_web/app.py`
- Modify: `backend/legacy_web/context.py`
- Modify: `backend/legacy_web/deps.py`
- Modify: `backend/legacy_web/services_container.py`
- Test: `backend/tests/api/test_app.py`
- Test: `backend/tests/api/test_errors.py`
- Test: `backend/tests/services/test_container.py`

**Interfaces:**
- Consumes: existing DB engine, tracing, logging, encryption factory, and per-request services.
- Produces: `create_app() -> FastAPI`, `Problem`, `ProblemException`, `problem(status: int, code: str, title: str, detail: str, fields: dict[str, str] | None = None) -> Problem`, `problem_response(value: Problem) -> JSONResponse`, `get_services(request: Request) -> RequestServices`, and shared `Actor`.

- [ ] **Step 1: Write failing API foundation tests**

Create `backend/tests/api/test_app.py`:

```python
from fastapi.testclient import TestClient

from rentivo.api.app import create_app


def test_health_is_versioned_and_json():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_api_route_uses_problem_json():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "not_found"
```

- [ ] **Step 2: Verify the tests fail**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_app.py -q
```

Expected: collection fails because `rentivo.api` does not exist.

- [ ] **Step 3: Extract shared actor and service-container types**

Define `backend/rentivo/context.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: int | None
    email: str
    source: str
    api_key_uuid: str | None = None
    is_login_token: bool | None = None


ANON_ACTOR = Actor(user_id=None, email="", source="anonymous")
```

Move `RequestServices` into `rentivo.services.container` and leave temporary re-exports in `legacy_web.context` and `legacy_web.services_container` so existing imports and test patches remain stable during this milestone.

- [ ] **Step 4: Implement API lifecycle, dependencies, and problem responses**

Define the stable error shape in `errors.py`:

```python
class Problem(BaseModel):
    type: str
    title: str
    status: int
    code: str
    detail: str
    fields: dict[str, str] = Field(default_factory=dict)
    request_id: str


def get_request_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("request_id", ""))


def problem(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    fields: dict[str, str] | None = None,
) -> Problem:
    request_id = get_request_id()
    return Problem(
        type=f"https://rentivo.app/problems/{code}",
        title=title,
        status=status,
        code=code,
        detail=detail,
        fields=fields or {},
        request_id=request_id,
    )


class ProblemException(Exception):
    def __init__(self, problem: Problem) -> None:
        self.problem = problem
        super().__init__(problem.detail)

    @classmethod
    def forbidden(cls, code: str, detail: str) -> "ProblemException":
        return cls(problem(status=403, code=code, title="Acesso negado", detail=detail))

    @classmethod
    def not_found(cls) -> "ProblemException":
        return cls(problem(status=404, code="not_found", title="Não encontrado", detail="Recurso não encontrado."))
```

`create_app()` must initialize DB/tracing, attach per-request connection/services, mount only `/api/v1`, install exception handlers for FastAPI validation and HTTP errors, and leave CORS disabled.

- [ ] **Step 5: Run focused and legacy tests**

```bash
uv run --project backend pytest backend/tests/api backend/tests/web/test_app.py backend/tests/web/test_services_container.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/rentivo/api backend/rentivo/context.py backend/rentivo/services/container.py backend/legacy_web backend/tests/api backend/tests/services/test_container.py
git commit -m "feat(api): add versioned FastAPI foundation"
```

---

### Task 3: Persist API Keys, Scopes, and Workspace Grants

**Files:**
- Create: `backend/rentivo/models/api_key.py`
- Create: `backend/rentivo/repositories/sqlalchemy/api_key.py`
- Modify: `backend/rentivo/models/__init__.py`
- Modify: `backend/rentivo/repositories/base.py`
- Modify: `backend/rentivo/repositories/sqlalchemy/__init__.py`
- Create: generated `backend/alembic/versions/*_create_api_keys.py`
- Test: `backend/tests/models/test_api_key.py`
- Test: `backend/tests/repositories/test_api_key_repository.py`
- Test: `backend/tests/test_alembic_heads.py`

**Interfaces:**
- Consumes: SQLAlchemy connection and existing ULID/time conventions.
- Produces: `APIKey`, `APIKeyGrant`, `APIKeyRepository`, and `SQLAlchemyAPIKeyRepository` with atomic aggregate operations.

- [ ] **Step 1: Write failing model and repository tests**

```python
def test_repository_round_trips_scopes_and_grants(api_key_repo, integration_key):
    saved = api_key_repo.create(
        integration_key,
        scopes=frozenset({"profile:read", "billings:read"}),
        grants=(APIKeyGrant(resource_type="user", resource_id=7),),
    )
    loaded = api_key_repo.get_by_secret_hash(integration_key.secret_hash)
    assert loaded == saved
    assert loaded.scopes == frozenset({"profile:read", "billings:read"})
    assert loaded.grants == (APIKeyGrant(resource_type="user", resource_id=7),)


def test_list_integration_keys_never_returns_login_tokens(api_key_repo, login_key, integration_key):
    api_key_repo.create(login_key, scopes=frozenset(), grants=())
    api_key_repo.create(integration_key, scopes=frozenset(), grants=())
    assert [key.uuid for key in api_key_repo.list_integrations(7)] == [integration_key.uuid]
```

- [ ] **Step 2: Verify repository tests fail**

```bash
uv run --project backend pytest backend/tests/models/test_api_key.py backend/tests/repositories/test_api_key_repository.py -q
```

Expected: imports fail for missing API-key model/repository.

- [ ] **Step 3: Generate and implement the additive Alembic migration**

```bash
uv run --project backend alembic -c backend/alembic.ini revision -m "create api keys"
```

Create `api_keys`, `api_key_scopes`, and `api_key_resource_grants` exactly as specified. Use `BINARY(32)` for `secret_hash`, unique indexes on `uuid` and `secret_hash`, indexes on `user_id` and expiration/revocation cleanup columns, delete cascades for scopes/grants, and UTC microsecond timestamps. The downgrade drops only these three tables in dependency order.

- [ ] **Step 4: Implement models and the aggregate repository**

Use these public types:

```python
class APIKeyGrant(BaseModel, frozen=True):
    resource_type: Literal["user", "organization"]
    resource_id: int


class APIKey(BaseModel):
    id: int | None = None
    uuid: str = ""
    user_id: int
    name: str
    secret_hash: bytes = Field(exclude=True)
    key_start: str
    key_end: str
    is_login_token: bool = False
    scopes: frozenset[str] = frozenset()
    grants: tuple[APIKeyGrant, ...] = ()
    expires_at: datetime
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    revoked_at: datetime | None = None
```

Repository `create` and `update_integration` must write the key/scopes/grants in one transaction. Add methods `get_by_secret_hash`, `get_integration_by_uuid`, `list_integrations`, `delete_login_token`, `revoke_integration`, `revoke_all_login_tokens`, `delete_expired_login_tokens`, and `touch_last_used`.

- [ ] **Step 5: Run repository and migration tests**

```bash
uv run --project backend pytest backend/tests/models/test_api_key.py backend/tests/repositories/test_api_key_repository.py backend/tests/test_alembic_heads.py -q
```

Expected: all pass and Alembic reports one head.

- [ ] **Step 6: Commit**

```bash
git add backend/rentivo/models backend/rentivo/repositories backend/alembic backend/tests/models/test_api_key.py backend/tests/repositories/test_api_key_repository.py
git commit -m "feat(auth): persist scoped API keys"
```

---

### Task 4: Implement API-Key Generation and Lifecycle Services

**Files:**
- Create: `backend/rentivo/services/api_key_service.py`
- Create: `backend/rentivo/constants/api_scopes.py`
- Modify: `backend/rentivo/services/container.py`
- Test: `backend/tests/services/test_api_key_service.py`
- Test: `backend/tests/security/test_api_key_secrets.py`

**Interfaces:**
- Consumes: `APIKeyRepository`, user/org repositories, clock, and cryptographic randomness.
- Produces: `IssuedAPIKey`, `APIKeyService.issue_login`, `issue_integration`, `authenticate`, `can_access_resource`, `update_integration`, `logout`, `revoke_all_logins`, and `cleanup_expired_logins`.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_issue_login_has_fixed_lifetime_and_full_scopes(service, freezer):
    freezer.move_to("2026-07-17T12:00:00Z")
    issued = service.issue_login(user_id=7, name="Web login")
    assert issued.secret.startswith("rntv-v1-")
    assert issued.key.is_login_token is True
    assert issued.key.expires_at == datetime(2026, 7, 18, 12, tzinfo=UTC)
    assert issued.key.scopes == ALL_FIRST_PARTY_SCOPES


def test_issue_integration_discloses_secret_once_and_stores_hint(service, repository):
    issued = service.issue_integration(
        user_id=7,
        name="Accounting export",
        scopes={"profile:read"},
        grants=[APIKeyGrant(resource_type="user", resource_id=7)],
        expires_at=datetime.now(UTC) + timedelta(days=90),
    )
    persisted = repository.get_integration_by_uuid(7, issued.key.uuid)
    assert issued.secret.startswith("rntv-v1-")
    assert persisted.secret_hash == sha256(issued.secret.encode()).digest()
    assert issued.key.key_start in issued.secret
    assert issued.secret.endswith(issued.key.key_end)
```

- [ ] **Step 2: Verify tests fail**

```bash
uv run --project backend pytest backend/tests/services/test_api_key_service.py backend/tests/security/test_api_key_secrets.py -q
```

Expected: missing service and scope registry.

- [ ] **Step 3: Implement the scope registry and key primitives**

Define `APIScope(StrEnum)`, `ALL_FIRST_PARTY_SCOPES`, `INTEGRATION_SCOPES`, and deployed-scope filtering. Generate 32 random bytes with `secrets.token_urlsafe(32)`, prepend `rntv-v1-`, hash the complete credential with SHA-256, and reject malformed/unsupported key versions before querying the repository.

```python
class IssuedAPIKey(NamedTuple):
    key: APIKey
    secret: str
```

- [ ] **Step 4: Implement lifecycle and validation rules**

`issue_integration` requires a nonblank name, at least one grant, integration-safe deployed scopes, an expiration after now, and an expiration no later than now plus 365 days. It validates user grants against the owner and organization grants against current membership. `authenticate` rejects expired/revoked rows and throttles `last_used_at` writes to five minutes. `logout` hard-deletes only a matching login token. Integration revoke is idempotent.

`can_access_resource(key, resource_type, resource_id)` grants login tokens the owner's personal workspace plus live organization memberships. For integration keys it requires a matching persisted grant and, for organizations, a current membership. Existing domain authorization remains responsible for owner/admin/manager/viewer action checks.

- [ ] **Step 5: Run service and security tests**

```bash
uv run --project backend pytest backend/tests/services/test_api_key_service.py backend/tests/security/test_api_key_secrets.py -q
```

Expected: all pass, including log-capture assertions that raw keys/hashes are absent.

- [ ] **Step 6: Commit**

```bash
git add backend/rentivo/constants backend/rentivo/services backend/tests/services/test_api_key_service.py backend/tests/security/test_api_key_secrets.py
git commit -m "feat(auth): issue and validate API keys"
```

---

### Task 5: Resolve Principals, Scopes, Resource Grants, and CSRF

**Files:**
- Create: `backend/rentivo/api/authentication.py`
- Create: `backend/rentivo/api/csrf.py`
- Create: `backend/rentivo/api/principal.py`
- Modify: `backend/rentivo/api/dependencies.py`
- Modify: `backend/rentivo/context.py`
- Test: `backend/tests/api/test_authentication.py`
- Test: `backend/tests/api/test_authorization.py`
- Test: `backend/tests/api/test_csrf.py`

**Interfaces:**
- Consumes: `APIKeyService`, `RequestServices`, user/org authorization.
- Produces: `Principal`, `get_optional_principal`, `require_scope`, `require_login_scope`, `require_resource_grant`, and CSRF dependencies.

- [ ] **Step 1: Write failing transport and authorization tests**

```python
@pytest.mark.parametrize("transport", ["cookie", "bearer"])
def test_valid_key_resolves_same_principal(api_client, issued_key, transport):
    response = api_client.get("/api/v1/test/principal", auth=auth_for(issued_key.secret, transport))
    assert response.status_code == 200
    assert response.json()["user_id"] == issued_key.key.user_id


def test_mismatched_cookie_and_bearer_are_rejected(api_client, login_key, integration_key):
    response = api_client.get(
        "/api/v1/test/principal",
        cookies={"__Host-rentivo_access": login_key.secret},
        headers={"Authorization": f"Bearer {integration_key.secret}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "ambiguous_credentials"


def test_integration_key_requires_scope_grant_membership_and_role(api_client, integration_key):
    response = api_client.get("/api/v1/test/organizations/01ABC", auth=bearer(integration_key.secret))
    assert response.status_code == 404
```

- [ ] **Step 2: Verify tests fail**

```bash
uv run --project backend pytest backend/tests/api/test_authentication.py backend/tests/api/test_authorization.py backend/tests/api/test_csrf.py -q
```

Expected: missing principal/authentication modules.

- [ ] **Step 3: Implement the principal contract**

```python
@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    api_key: APIKey
    source: Literal["web", "mobile", "integration"]

    @property
    def actor(self) -> Actor:
        return Actor(
            user_id=self.user.id,
            email=self.user.email,
            source=self.source,
            api_key_uuid=self.api_key.uuid,
            is_login_token=self.api_key.is_login_token,
        )
```

Reject non-Bearer Authorization schemes, credentials in query/body, and mismatched cookie/Bearer keys. A stale cookie `401` response clears access and CSRF cookies.

- [ ] **Step 4: Implement scope/login-token/resource dependencies**

```python
def require_scope(scope: APIScope) -> Callable[..., Principal]:
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if scope.value not in principal.api_key.scopes:
            raise ProblemException.forbidden("missing_scope", "A chave não possui o escopo necessário.")
        return principal

    return dependency


def require_login_scope(scope: APIScope) -> Callable[..., Principal]:
    scoped_dependency = require_scope(scope)

    async def dependency(principal: Principal = Depends(scoped_dependency)) -> Principal:
        if not principal.api_key.is_login_token:
            raise ProblemException.forbidden("login_token_required", "Esta operação requer login interativo.")
        return principal

    return dependency


def require_resource_grant(
    principal: Principal,
    services: RequestServices,
    resource_type: Literal["user", "organization"],
    resource_id: int,
) -> None:
    if not services.api_key.can_access_resource(principal.api_key, resource_type, resource_id):
        raise ProblemException.not_found()
```

Return `403 missing_scope` for a known scope failure and `404 not_found` for a resource outside effective grants/membership/role. Login tokens dynamically include personal/current organization access; integration keys use persisted grants intersected with live membership.

- [ ] **Step 5: Implement double-submit CSRF**

Issue a non-HttpOnly CSRF cookie and bootstrap token bound by HMAC to the authenticated key UUID. Require exact header/cookie/token binding on cookie-authenticated POST/PUT/PATCH/DELETE requests. Skip CSRF only when the request authenticates exclusively by Bearer header.

- [ ] **Step 6: Run tests and commit**

```bash
uv run --project backend pytest backend/tests/api/test_authentication.py backend/tests/api/test_authorization.py backend/tests/api/test_csrf.py -q
git add backend/rentivo/api backend/rentivo/context.py backend/tests/api
git commit -m "feat(api): enforce scoped API-key principals"
```

---

### Task 6: Replace Session Login State with Authentication Challenges

**Files:**
- Create: `backend/rentivo/models/auth_challenge.py`
- Create: `backend/rentivo/repositories/sqlalchemy/auth_challenge.py`
- Create: `backend/rentivo/services/auth_challenge_service.py`
- Create: generated `backend/alembic/versions/*_create_auth_challenges.py`
- Modify: `backend/rentivo/repositories/base.py`
- Modify: `backend/rentivo/repositories/sqlalchemy/__init__.py`
- Modify: `backend/rentivo/services/container.py`
- Test: `backend/tests/repositories/test_auth_challenge_repository.py`
- Test: `backend/tests/services/test_auth_challenge_service.py`

**Interfaces:**
- Consumes: cryptographic randomness, DB connection, MFA service, and five-minute expiry.
- Produces: `AuthChallenge`, `IssuedAuthChallenge`, and single-use challenge issue/verify/consume operations.

- [ ] **Step 1: Write failing expiry and consumption tests**

```python
def test_challenge_is_single_use(service):
    issued = service.issue(user_id=7, phase="mfa", allowed_methods=("totp", "passkey"))
    first = service.consume(issued.challenge.uuid, issued.nonce)
    second = service.consume(issued.challenge.uuid, issued.nonce)
    assert first.user_id == 7
    assert second is None


def test_challenge_expires_after_five_minutes(service, freezer):
    issued = service.issue(user_id=7, phase="mfa", allowed_methods=("totp",))
    freezer.tick(timedelta(minutes=5, seconds=1))
    assert service.get_valid(issued.challenge.uuid, issued.nonce) is None
```

- [ ] **Step 2: Verify tests fail and generate migration**

```bash
uv run --project backend pytest backend/tests/repositories/test_auth_challenge_repository.py backend/tests/services/test_auth_challenge_service.py -q
uv run --project backend alembic -c backend/alembic.ini revision -m "create auth challenges"
```

Expected: tests fail before implementation; Alembic generates a new revision from the API-key head.

- [ ] **Step 3: Implement challenge persistence and service**

Store public ULID, nonce SHA-256, user ID, phase, allowed-method JSON, optional WebAuthn challenge bytes, failures, timestamps, and consumed timestamp. `consume` must mark the row consumed conditionally in the same transaction so concurrent completions cannot issue two login keys.

```python
class IssuedAuthChallenge(NamedTuple):
    challenge: AuthChallenge
    nonce: str
```

- [ ] **Step 4: Run tests and commit**

```bash
uv run --project backend pytest backend/tests/repositories/test_auth_challenge_repository.py backend/tests/services/test_auth_challenge_service.py backend/tests/test_alembic_heads.py -q
git add backend/rentivo/models backend/rentivo/repositories backend/rentivo/services backend/alembic backend/tests
git commit -m "feat(auth): add single-use login challenges"
```

---

### Task 7: Implement Primary Authentication and Session Bootstrap APIs

**Files:**
- Create: `backend/rentivo/api/schemas/auth.py`
- Create: `backend/rentivo/api/routes/auth.py`
- Create: `backend/rentivo/services/login_service.py`
- Modify: `backend/rentivo/api/app.py`
- Modify: `backend/rentivo/settings.py`
- Modify: `backend/rentivo/services/password_reset_service.py`
- Test: `backend/tests/api/routes/test_auth.py`
- Test: `backend/tests/services/test_login_service.py`

**Interfaces:**
- Consumes: user, API-key, challenge, MFA, audit, job, known-device, Turnstile, and password-reset services.
- Produces: signup/login/bootstrap/logout/password-recovery endpoints and shared `LoginResult`.

- [ ] **Step 1: Write failing route tests for both login outcomes**

```python
def test_password_login_without_mfa_sets_key_cookie(api_client, user):
    response = api_client.post("/api/v1/auth/login", json={"email": user.email, "password": "correct"})
    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"
    assert "rntv-v1-" not in response.text
    assert response.cookies[access_cookie_name()].startswith("rntv-v1-")


def test_password_login_with_mfa_sets_challenge_not_access_cookie(api_client, mfa_user):
    response = api_client.post("/api/v1/auth/login", json={"email": mfa_user.email, "password": "correct"})
    assert response.status_code == 202
    assert response.json()["status"] == "mfa_required"
    assert response.json()["methods"] == ["totp", "recovery", "passkey"]
    assert challenge_cookie_name() in response.cookies
    assert access_cookie_name() not in response.cookies
```

- [ ] **Step 2: Verify tests fail**

```bash
uv run --project backend pytest backend/tests/api/routes/test_auth.py backend/tests/services/test_login_service.py -q
```

Expected: auth router and login service are missing.

- [ ] **Step 3: Implement login orchestration and cookie settings**

```python
class LoginResult(BaseModel):
    status: Literal["authenticated", "mfa_required"]
    bootstrap: BootstrapResponse | None = None
    challenge_id: str | None = None
    methods: tuple[str, ...] = ()
```

Move existing complete-login side effects into `LoginService`: audit, analytics event payload, known-device notification, organization MFA setup requirement, and login-key issuance. Add validated environment-specific access/challenge/CSRF cookie settings; staging/production reject non-Secure or non-`__Host-` values.

- [ ] **Step 4: Implement the endpoint set**

Implement:

```text
POST /api/v1/auth/signup
POST /api/v1/auth/login
GET  /api/v1/auth/session
POST /api/v1/auth/logout
POST /api/v1/auth/password/forgot
POST /api/v1/auth/password/reset
GET  /api/v1/auth/csrf
```

Preserve rate limits, Turnstile, PT-BR errors, audit types, analytics names, email jobs, concurrent sessions, current-token-only logout, and global login-token revocation after password recovery.

- [ ] **Step 5: Run auth tests and commit**

```bash
uv run --project backend pytest backend/tests/api/routes/test_auth.py backend/tests/services/test_login_service.py backend/tests/services/test_password_reset_service.py -q
git add backend/rentivo/api backend/rentivo/services backend/rentivo/settings.py backend/tests
git commit -m "feat(api): add API-key login and bootstrap"
```

---

### Task 8: Port MFA, Passkey, and Google OAuth Authentication

**Files:**
- Create: `backend/rentivo/api/routes/mfa_auth.py`
- Create: `backend/rentivo/api/routes/google_auth.py`
- Modify: `backend/rentivo/api/schemas/auth.py`
- Modify: `backend/rentivo/api/app.py`
- Modify: `backend/rentivo/services/google_auth_service.py`
- Modify: `backend/rentivo/services/login_service.py`
- Test: `backend/tests/api/routes/test_mfa_auth.py`
- Test: `backend/tests/api/routes/test_google_auth.py`
- Test: `backend/tests/api/routes/test_passkey_auth.py`

**Interfaces:**
- Consumes: `AuthChallengeService`, `LoginService`, existing `MFAService`, WebAuthn library, Google service.
- Produces: challenge completion endpoints that issue exactly one login token after successful MFA.

- [ ] **Step 1: Write failing TOTP/recovery/passkey tests**

```python
@pytest.mark.parametrize("method", ["totp", "recovery"])
def test_code_mfa_consumes_challenge_and_sets_access_cookie(api_client, pending_challenge, method):
    response = api_client.post(
        f"/api/v1/auth/mfa/{method}/verify",
        json={"challenge_id": pending_challenge.uuid, "code": valid_code(method)},
        cookies={challenge_cookie_name(): pending_challenge.nonce},
    )
    assert response.status_code == 200
    assert access_cookie_name() in response.cookies
    assert challenge_cookie_name() not in response.cookies


def test_replayed_passkey_completion_cannot_issue_second_key(api_client, passkey_completion):
    first = complete_passkey(api_client, passkey_completion)
    second = complete_passkey(api_client, passkey_completion)
    assert first.status_code == 200
    assert second.status_code == 401
```

- [ ] **Step 2: Verify tests fail**

```bash
uv run --project backend pytest backend/tests/api/routes/test_mfa_auth.py backend/tests/api/routes/test_google_auth.py backend/tests/api/routes/test_passkey_auth.py -q
```

Expected: route modules are missing.

- [ ] **Step 3: Implement MFA and passkey authentication routes**

Implement:

```text
POST /api/v1/auth/mfa/totp/verify
POST /api/v1/auth/mfa/recovery/verify
POST /api/v1/auth/mfa/passkeys/begin
POST /api/v1/auth/mfa/passkeys/complete
```

WebAuthn begin stores the generated challenge bytes on the server-side challenge row. Completion validates challenge, RP ID, origin, credential owner, and sign count before atomically consuming the login challenge. Preserve existing MFA audit event types and rate limits.

- [ ] **Step 4: Implement Google OAuth without authenticated sessions**

Implement:

```text
GET /api/v1/auth/google/start
GET /api/v1/auth/google/callback
```

Store OAuth state as a short-lived challenge phase. Callback validates and consumes state, resolves/creates the user, then either issues the access cookie or sets the MFA challenge cookie and redirects to `/mfa-verify?challenge=<public-ulid>`. Preserve current audit/analytics/email behavior.

- [ ] **Step 5: Run tests and commit**

```bash
uv run --project backend pytest backend/tests/api/routes/test_mfa_auth.py backend/tests/api/routes/test_google_auth.py backend/tests/api/routes/test_passkey_auth.py -q
git add backend/rentivo/api backend/rentivo/services backend/tests/api/routes
git commit -m "feat(api): port MFA and OAuth authentication"
```

---

### Task 9: Port Security and Integration-Key Management APIs

**Files:**
- Create: `backend/rentivo/api/schemas/security.py`
- Create: `backend/rentivo/api/schemas/api_keys.py`
- Create: `backend/rentivo/api/routes/security.py`
- Create: `backend/rentivo/api/routes/api_keys.py`
- Create: `backend/rentivo/api/routes/profile.py`
- Modify: `backend/rentivo/api/app.py`
- Modify: `backend/rentivo/services/login_service.py`
- Test: `backend/tests/api/routes/test_security.py`
- Test: `backend/tests/api/routes/test_api_keys.py`
- Test: `backend/tests/api/routes/test_profile.py`

**Interfaces:**
- Consumes: login-token-only principal dependencies and existing user/PIX/MFA/passkey services.
- Produces: complete React Security-page API and integration-key CRUD.

- [ ] **Step 1: Write failing login-token-only tests**

```python
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/security",
        "/api/v1/security/totp/setup",
        "/api/v1/security/passkeys/register/begin",
        "/api/v1/api-keys",
    ],
)
def test_integration_key_cannot_access_privileged_routes(api_client, integration_key, path):
    response = api_client.get(path, auth=bearer(integration_key.secret))
    assert response.status_code == 403
    assert response.json()["code"] == "login_token_required"


def test_api_key_list_omits_hidden_login_tokens(api_client, login_auth, integration_key):
    response = api_client.get("/api/v1/api-keys", auth=login_auth)
    assert response.status_code == 200
    assert [item["uuid"] for item in response.json()["items"]] == [integration_key.key.uuid]
    assert all("is_login_token" not in item for item in response.json()["items"])
```

- [ ] **Step 2: Verify tests fail**

```bash
uv run --project backend pytest backend/tests/api/routes/test_security.py backend/tests/api/routes/test_api_keys.py backend/tests/api/routes/test_profile.py -q
```

Expected: schemas and routers are missing.

- [ ] **Step 3: Port the Security-page API**

Implement login-token-only JSON endpoints for profile/PIX update, password change, TOTP setup/confirm/disable, recovery-code regeneration, passkey registration begin/complete/list/delete, and organization-enforced MFA setup state. Reuse existing services; move HTTP parsing and redirects out of service logic. Password change revokes other login tokens, while password recovery and MFA reset revoke all login tokens.

- [ ] **Step 4: Implement integration-key CRUD**

Implement:

```text
GET    /api/v1/api-keys
POST   /api/v1/api-keys
GET    /api/v1/api-keys/{key_uuid}
PATCH  /api/v1/api-keys/{key_uuid}
DELETE /api/v1/api-keys/{key_uuid}
GET    /api/v1/api-keys/options
```

Creation returns `secret` only in its `201` response with `Cache-Control: no-store`. List/detail use masked `rntv-v1-aBcD••••yZ`. Patch accepts only name, deployed safe scopes, and grants. Delete is idempotent soft revocation. Options returns personal workspace, current organizations, safe deployed scopes, 90-day default, and 365-day maximum.

- [ ] **Step 5: Run tests and commit**

```bash
uv run --project backend pytest backend/tests/api/routes/test_security.py backend/tests/api/routes/test_api_keys.py backend/tests/api/routes/test_profile.py -q
git add backend/rentivo/api backend/rentivo/services backend/tests/api/routes
git commit -m "feat(api): add security and API-key management"
```

---

### Task 10: Scaffold the React/Vite Application Shell and Preserve Existing Styles

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/router.tsx`
- Create: `frontend/src/app/providers.tsx`
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/Topbar.tsx`
- Create: `frontend/src/components/ToastRegion.tsx`
- Create: `frontend/src/components/ConfirmDialog.tsx`
- Create: `frontend/src/styles/custom.css`
- Create: `frontend/src/styles/landing.css`
- Create: `frontend/public/favicon.svg`
- Test: `frontend/src/components/AppShell.test.tsx`
- Test: `frontend/src/components/ConfirmDialog.test.tsx`

**Interfaces:**
- Consumes: existing legacy templates/CSS/static assets.
- Produces: `App`, route shell, providers, navigation, toast and confirmation primitives; no backend contract dependency yet.

- [ ] **Step 1: Create Vite/TypeScript test configuration and install locked dependencies**

Use React, React DOM, React Router, TanStack Query, openapi-fetch, and lucide-react at runtime. Use Vite, TypeScript, Vitest, Testing Library, user-event, jsdom, ESLint, openapi-typescript, and Playwright as development dependencies. Configure `npm test -- --run`, `npm run typecheck`, and 100% coverage thresholds.

- [ ] **Step 2: Write failing shell interaction tests**

```tsx
it("opens and closes the account menu with focus restored", async () => {
  const user = userEvent.setup();
  render(<AppShell currentUser={{ email: "user@example.com" }} />);
  const trigger = screen.getByRole("button", { name: /user@example.com/i });
  await user.click(trigger);
  expect(screen.getByRole("link", { name: "Segurança" })).toBeVisible();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
});


it("traps focus in a destructive confirmation", async () => {
  const user = userEvent.setup();
  render(<ConfirmDialog open title="Revogar chave" onConfirm={vi.fn()} onClose={vi.fn()} />);
  await user.tab();
  await user.tab();
  expect(screen.getByRole("button", { name: "Voltar" })).toHaveFocus();
});
```

- [ ] **Step 3: Verify tests fail**

```bash
npm --prefix frontend test -- --run src/components/AppShell.test.tsx src/components/ConfirmDialog.test.tsx
```

Expected: components do not exist.

- [ ] **Step 4: Port shell markup and styles without redesign**

Copy existing CSS and favicon, preserving selectors. Translate `base.html` and `app.js` behavior into focused components: mobile topbar, account dropdown, invite badge, dismissible toasts, outside-click/Escape handling, and accessible confirmation dialog. Use lucide-react icons at the current rendered dimensions.

- [ ] **Step 5: Verify shell tests, typecheck, and coverage**

```bash
npm --prefix frontend run typecheck
npm --prefix frontend test -- --run --coverage
```

Expected: both pass at 100% authored-code coverage.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): add React application shell"
```

---

### Task 11: Generate the OpenAPI Client and Port Authentication Screens

**Files:**
- Create: `backend/rentivo/api/export_openapi.py`
- Create: `frontend/openapi.json`
- Create: `frontend/scripts/generate-api.mjs`
- Create: `frontend/src/api/schema.d.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/features/auth/AuthProvider.tsx`
- Create: `frontend/src/features/auth/LoginPage.tsx`
- Create: `frontend/src/features/auth/SignupPage.tsx`
- Create: `frontend/src/features/auth/MfaVerifyPage.tsx`
- Create: `frontend/src/features/auth/ForgotPasswordPage.tsx`
- Create: `frontend/src/features/auth/ResetPasswordPage.tsx`
- Create: `frontend/src/features/auth/GoogleCallbackPage.tsx`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/src/api/client.test.ts`
- Test: `frontend/src/features/auth/AuthProvider.test.tsx`
- Test: `frontend/src/features/auth/LoginPage.test.tsx`
- Test: `backend/tests/api/test_openapi.py`

**Interfaces:**
- Consumes: Task 7-9 OpenAPI paths and Task 10 shell.
- Produces: checked-in API schema/types, `apiRequest`, `AuthProvider`, and all current auth routes.

- [ ] **Step 1: Write failing OpenAPI freshness and request-client tests**

```python
def test_openapi_contains_auth_and_key_operations():
    schema = create_app().openapi()
    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/api-keys" in schema["paths"]
```

```tsx
it("clears auth state and redirects on a problem+json 401", async () => {
  server.use(http.get("/api/v1/auth/session", () => HttpResponse.json(problem401, { status: 401 })));
  render(<AuthProvider><SessionProbe /></AuthProvider>);
  expect(await screen.findByText("anonymous")).toBeVisible();
  expect(window.location.pathname).toBe("/login");
});
```

- [ ] **Step 2: Verify tests fail**

```bash
uv run --project backend pytest backend/tests/api/test_openapi.py -q
npm --prefix frontend test -- --run src/api/client.test.ts src/features/auth/AuthProvider.test.tsx
```

- [ ] **Step 3: Implement deterministic OpenAPI export and generation**

`python -m rentivo.api.export_openapi ../frontend/openapi.json` writes sorted/indented JSON without starting DB connections. `npm run api:generate` runs openapi-typescript and must be deterministic. Add `npm run api:check` that regenerates and exits nonzero when Git detects differences.

- [ ] **Step 4: Implement the shared request client and auth provider**

The client always uses `/api/v1`, `credentials: "same-origin"`, problem-details parsing, request-ID capture, and CSRF headers for cookie-authenticated mutations. It never exposes access-cookie contents. `AuthProvider` stores only bootstrap user/capabilities and redirects on `401`.

- [ ] **Step 5: Port every authentication page**

Preserve the current URLs and PT-BR text for `/login`, `/signup`, `/mfa-verify`, `/forgot-password`, and `/reset-password`. Port Turnstile, password validation, MFA method switching, WebAuthn browser calls, Google redirects/callback, loading/error states, focus placement, analytics event names, and post-login redirects.

- [ ] **Step 6: Run backend/frontend tests and commit**

```bash
uv run --project backend pytest backend/tests/api/test_openapi.py -q
npm --prefix frontend run api:check
npm --prefix frontend run typecheck
npm --prefix frontend test -- --run --coverage
git add backend/rentivo/api/export_openapi.py backend/tests/api/test_openapi.py frontend
git commit -m "feat(frontend): port API-key authentication flows"
```

---

### Task 12: Port Security Screens and Add Integration-Key Management

**Files:**
- Create: `frontend/src/features/security/SecurityPage.tsx`
- Create: `frontend/src/features/security/TotpSetupPage.tsx`
- Create: `frontend/src/features/security/RecoveryCodesPage.tsx`
- Create: `frontend/src/features/security/PasskeyManager.tsx`
- Create: `frontend/src/features/apiKeys/ApiKeySection.tsx`
- Create: `frontend/src/features/apiKeys/ApiKeyForm.tsx`
- Create: `frontend/src/features/apiKeys/ApiKeySecretDialog.tsx`
- Create: `frontend/src/features/apiKeys/ApiKeyList.tsx`
- Modify: `frontend/src/app/router.tsx`
- Test: corresponding `*.test.tsx` files beside each component

**Interfaces:**
- Consumes: generated Security/API-key contracts and shared shell/dialog/client.
- Produces: parity-complete `/security` routes plus one-time integration-key creation/edit/revoke UI.

- [ ] **Step 1: Write failing one-time secret and grant-form tests**

```tsx
it("shows the integration secret once and requires acknowledgement before closing", async () => {
  const user = userEvent.setup();
  render(<ApiKeySecretDialog secret="rntv-v1-secret" open onClose={onClose} />);
  expect(screen.getByText("rntv-v1-secret")).toBeVisible();
  expect(screen.getByRole("button", { name: "Concluir" })).toBeDisabled();
  await user.click(screen.getByRole("checkbox", { name: /guardei esta chave/i }));
  await user.click(screen.getByRole("button", { name: "Concluir" }));
  expect(onClose).toHaveBeenCalledOnce();
});


it("requires at least one personal or organization workspace", async () => {
  render(<ApiKeyForm options={options} onSubmit={onSubmit} />);
  await userEvent.click(screen.getByRole("button", { name: "Criar chave" }));
  expect(screen.getByText("Selecione pelo menos um espaço de trabalho.")).toBeVisible();
  expect(onSubmit).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Verify tests fail**

```bash
npm --prefix frontend test -- --run src/features/security src/features/apiKeys
```

Expected: feature components are missing.

- [ ] **Step 3: Port existing Security features exactly**

Port PIX profile, password change, TOTP setup/disable, recovery-code display/regeneration, passkey registration/list/delete, organization-enforced MFA notices, confirmations, success/error toasts, and WebAuthn behavior. Preserve current route URLs, copy, responsive layout, and analytics events.

- [ ] **Step 4: Implement the API-key section in the existing visual language**

Show required name, safe scopes, explicit personal workspace, current organization multiselect, and expiration control defaulted to 90 days/capped at 365. List only visible integration keys with masked hint, created/expiry/last-use times, scopes, and workspaces. Support metadata/grant/scope editing and confirmed idempotent revocation. Never render or count login tokens.

- [ ] **Step 5: Run frontend verification and commit**

```bash
npm --prefix frontend run typecheck
npm --prefix frontend test -- --run --coverage
git add frontend/src/features frontend/src/app/router.tsx
git commit -m "feat(frontend): add security and API-key management"
```

---

### Task 13: Add Cleanup, Audit Attribution, Secret Redaction, and Operational Settings

**Files:**
- Create: `backend/rentivo/jobs/handlers/auth_cleanup.py`
- Modify: `backend/rentivo/jobs/registry.py`
- Modify: `backend/rentivo/services/audit_service.py`
- Modify: `backend/rentivo/pii_redaction.py`
- Modify: `backend/rentivo/observability/middleware.py`
- Modify: `backend/rentivo/settings.py`
- Modify: `.env.example`
- Modify: `docs/configuration.md`
- Test: `backend/tests/jobs/test_auth_cleanup_handler.py`
- Test: `backend/tests/security/test_api_key_redaction.py`
- Test: `backend/tests/observability/test_api_key_attribution.py`
- Test: `backend/tests/test_settings.py`

**Interfaces:**
- Consumes: API-key/challenge repositories, Actor metadata, existing jobs/audit/tracing.
- Produces: idempotent cleanup job and credential-safe telemetry/configuration.

- [ ] **Step 1: Write failing cleanup and redaction tests**

```python
def test_cleanup_removes_only_expired_login_tokens_and_challenges(handler, repository):
    result = handler.handle({"now": "2026-07-17T12:00:00Z"})
    assert result == {"login_tokens_deleted": 2, "challenges_deleted": 3}
    assert repository.integration_key.revoked_at is None


@pytest.mark.parametrize("field", ["authorization", "cookie", "secret", "secret_hash"])
def test_api_key_material_is_redacted(field):
    assert redact({field: "rntv-v1-very-secret"})[field] == "[REDACTED]"
```

- [ ] **Step 2: Implement cleanup and attribution**

Register an `auth.cleanup` job that hard-deletes expired login tokens and expired/consumed challenges in bounded batches. Add API-key UUID/class/source to audit/tracing metadata, but exclude key name/hint/secret/hash from trace attributes and audit state. Keep cleanup safe to retry.

- [ ] **Step 3: Add and validate cookie/key settings**

Document configurable cookie names/security flags, 24-hour login TTL, five-minute challenge TTL, 90-day integration default, 365-day maximum, and five-minute last-used write throttle. Add settings tests that staging/production reject insecure cookies.

- [ ] **Step 4: Run tests and commit**

```bash
uv run --project backend pytest backend/tests/jobs/test_auth_cleanup_handler.py backend/tests/security/test_api_key_redaction.py backend/tests/observability/test_api_key_attribution.py backend/tests/test_settings.py -q
git add backend/rentivo backend/tests .env.example docs/configuration.md
git commit -m "feat(auth): add credential cleanup and observability"
```

---

### Task 14: Add Preview Routing, CI, End-to-End Flows, and Visual Parity Gates

**Files:**
- Create: `backend/Dockerfile.api`
- Create: `frontend/Dockerfile`
- Create: `infra/proxy/nginx.conf`
- Create: `docker-compose.next.yml`
- Create: `e2e/package.json`
- Create: `e2e/playwright.config.ts`
- Create: `e2e/tests/auth.spec.ts`
- Create: `e2e/tests/security.spec.ts`
- Create: `e2e/tests/api-keys.spec.ts`
- Create: `e2e/tests/parity.spec.ts`
- Create: `e2e/baselines/` screenshot assets
- Modify: `.github/workflows/test-pr.yaml`
- Modify: `.github/workflows/deploy.yml`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `docs/development.md`

**Interfaces:**
- Consumes: completed backend API, frontend, legacy app, worker, and generated client.
- Produces: local preview stack, four image builds, full CI, deterministic E2E/parity gate, and no production route switch.

- [ ] **Step 1: Write failing E2E scenarios**

Implement exact scenarios:

```ts
test("password login, reload, and logout revoke the current token", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill("user@example.com");
  await page.getByLabel("Senha").fill("correct-password");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/security/);
  await page.reload();
  await expect(page.getByText("user@example.com")).toBeVisible();
  await page.getByRole("button", { name: /user@example.com/i }).click();
  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page).toHaveURL(/login/);
});


test("create, acknowledge, edit, and revoke an integration key", async ({ page }) => {
  await login(page);
  await page.goto("/security");
  await page.getByRole("button", { name: "Nova chave" }).click();
  await page.getByLabel("Nome").fill("Accounting export");
  await page.getByLabel("Meu espaço pessoal").check();
  await page.getByLabel("Ler perfil").check();
  await page.getByRole("button", { name: "Criar chave" }).click();
  await expect(page.getByText(/^rntv-v1-/)).toBeVisible();
  await page.getByLabel(/guardei esta chave/i).check();
  await page.getByRole("button", { name: "Concluir" }).click();
  await page.getByRole("button", { name: "Revogar" }).click();
  await page.getByRole("button", { name: "Confirmar revogação" }).click();
  await expect(page.getByText("Chave revogada")).toBeVisible();
});
```

- [ ] **Step 2: Build the non-production preview stack**

`docker-compose.next.yml` adds `api`, `frontend`, and `proxy` without changing the existing default legacy service. Proxy `/api/v1/*` to API and all other preview traffic to frontend. API and worker share backend code/storage/database settings. Add health checks for frontend and API.

- [ ] **Step 3: Capture deterministic parity baselines**

Run the legacy app with seeded fixtures and capture Chromium screenshots for login, signup, MFA verify, forgot/reset password, Security, TOTP setup, and recovery codes at 1440x900 and 390x844. Freeze timestamps and mask generated IDs/codes. The React screenshots must have no unapproved pixel differences in the same container/browser/font environment.

- [ ] **Step 4: Update CI and developer commands**

CI must run backend Ruff/pytest/coverage, frontend lint/typecheck/Vitest/coverage, OpenAPI freshness, Alembic single-head, Playwright accessibility/E2E/parity, and builds for legacy/API/worker/frontend images. Keep deployment targeting legacy; build but do not route production traffic to the replacement.

- [ ] **Step 5: Run the complete verification suite**

```bash
make lint
make test-cov
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend test -- --run --coverage
npm --prefix frontend run api:check
npm --prefix e2e test
uv run --project backend alembic -c backend/alembic.ini heads
docker build -f backend/Dockerfile.legacy -t rentivo-legacy:test .
docker build -f backend/Dockerfile.api -t rentivo-api:test .
docker build -f backend/Dockerfile.worker -t rentivo-worker:test .
docker build -f frontend/Dockerfile -t rentivo-frontend:test .
git diff --check
git status --short
```

Expected: every command passes; Alembic prints one head; Git status shows only intentional plan-tracking changes before the final commit.

- [ ] **Step 6: Commit**

```bash
git add backend frontend e2e infra docker-compose.next.yml .github Makefile README.md docs
git commit -m "feat: complete API-key frontend backend foundation"
```

## Final Review Gate

Before handing off the foundation milestone, compare every success criterion in `docs/superpowers/specs/2026-07-17-frontend-backend-api-key-foundation-design.md` with test evidence. Confirm that production Compose/deployment still defaults to the legacy app, integration keys cannot reach privileged routes, hidden login tokens are absent from every management response, raw credentials never appear in logs or frontend state, and all required coverage/parity gates pass.
