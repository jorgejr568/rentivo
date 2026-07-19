# Big-Bang React/FastAPI Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the React/Vite frontend, FastAPI API, worker, MariaDB, and Nginx proxy as Rentivo's only production application, including the current public landing page and all required cutover compatibility.

**Architecture:** The default Compose topology runs a one-shot migration before API and worker startup, serves React through Nginx, and routes versioned API plus explicit public machine routes to FastAPI. Shared runtime code is extracted from `legacy_web`, then the legacy app, image, templates, tests, and deployment paths are deleted in the same release.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2, SQLAlchemy Core, Alembic, React 19, Vite, TypeScript, React Router, TanStack Query, Vitest, Testing Library, Playwright, Nginx, Docker Compose, MariaDB.

## Global Constraints

- Preserve the current landing page's Portuguese copy, section order, CSS, responsive behavior, and authenticated redirect to `/billings/`.
- The production runtime contains no `legacy_web` package, `Dockerfile.legacy`, or legacy Compose service.
- Existing legacy browser sessions intentionally require one fresh login.
- Browser login keys remain hidden, expire after exactly 24 hours, and authenticate through the HttpOnly cookie.
- Organization-required MFA is enforced by FastAPI on every protected login-token request.
- Exactly one migration job runs before API and worker startup; API startup never applies migrations.
- Production configuration fails closed on development credentials, origins, cookies, storage, email, or encryption.
- JSON failures use problem details with request IDs; public machine routes return accurate status codes and media types.
- Backend and authored frontend coverage remain 100%.
- Use `uv run --project backend`; never bare `python`, `pip`, or `pytest`.
- Pull requests remain human-merged.

## Dependency Map

Tasks 1, 2, 4, and 5 own disjoint surfaces and may run in parallel. Task 3 follows Tasks 1 and 2 because it integrates router-level MFA behavior. Task 6 follows Task 4 because the package cannot be removed until shared runtime code and templates are extracted. Task 7 integrates the production topology with the public routes from Task 2 and the legacy deletion from Task 6. Task 8 is final repository-wide verification.

---

### Task 1: Public React Landing Page And Metadata

**Files:**
- Create: `frontend/src/features/landing/LandingPage.tsx`
- Create: `frontend/src/features/landing/LandingPage.test.tsx`
- Create: `frontend/src/features/landing/LandingMetadata.tsx`
- Create: `frontend/src/features/landing/LandingMetadata.test.tsx`
- Create: `frontend/public/og-cover.svg`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/app/router.test.tsx`
- Modify: `frontend/index.html`
- Modify: `frontend/e2e/accessibility.spec.ts`
- Modify: `frontend/e2e/visual-parity.spec.ts`

**Interfaces:**
- Produces `LandingPage`, a public page at `/` that renders while anonymous and returns `<Navigate replace to="/billings/" />` when authenticated.
- Produces `LandingMetadata`, which owns title, canonical, Open Graph, Twitter, and JSON-LD DOM state and restores replaced values on unmount.

- [ ] **Step 1: Write failing landing and routing tests**

Add tests that render an anonymous `/` route and assert the existing heading, primary signup link, GitHub link, feature sections, footer, and no authenticated shell. Render an authenticated `/` route and assert navigation to `/billings/`. Assert the canonical URL and structured metadata are present.

```tsx
it("renders the public landing page for an anonymous visitor", async () => {
  mockAnonymousSession();
  const view = render(<RouterProvider router={createAppRouter()} />);
  expect(await view.findByRole("heading", { level: 1, name: /cobranças de imóveis/i })).toBeVisible();
  expect(view.getByRole("link", { name: /criar conta gratuita/i })).toHaveAttribute("href", "/signup");
});

it("redirects an authenticated root visit to billings", async () => {
  mockAuthenticatedSession();
  render(<RouterProvider router={createAppRouter()} />);
  expect(await screen.findByRole("heading", { name: /cobranças/i })).toBeVisible();
});
```

- [ ] **Step 2: Verify red**

Run: `npm --prefix frontend test -- --run src/features/landing/LandingPage.test.tsx src/features/landing/LandingMetadata.test.tsx src/app/router.test.tsx`

Expected: imports or public-root assertions fail because the landing feature does not exist and `/` remains protected.

- [ ] **Step 3: Port the landing page into focused React sections**

Translate `backend/legacy_web/templates/landing.html` to semantic JSX without changing visible copy or CSS class names. Use `lucide-react` icons where the template uses familiar icons and retain the QR visual as decorative markup. Keep all landing cards at the existing radius and dimensions from `landing.css`.

Move `/` outside `ProtectedApp` and use a small `HomeRoute` component:

```tsx
function HomeRoute() {
  const { status } = useAuth();
  if (status === "authenticated") return <Navigate replace to="/billings/" />;
  return <LandingPage />;
}
```

Copy `backend/legacy_web/static/og-cover.svg` to `frontend/public/og-cover.svg`. Put the full landing metadata fallback in `frontend/index.html`; use `%VITE_PUBLIC_APP_URL%` only where Vite has a configured production value and fall back to relative canonical paths in tests.

- [ ] **Step 4: Verify component and browser parity**

Run: `npm --prefix frontend test -- --run src/features/landing/LandingPage.test.tsx src/features/landing/LandingMetadata.test.tsx src/app/router.test.tsx && npm --prefix frontend run build && npm --prefix frontend run e2e -- accessibility.spec.ts visual-parity.spec.ts`

Expected: unit tests, build, landing accessibility, and desktop/mobile visual checks pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/public/og-cover.svg frontend/src/app/router.tsx frontend/src/app/router.test.tsx frontend/src/features/landing frontend/e2e/accessibility.spec.ts frontend/e2e/visual-parity.spec.ts
git commit -m "feat(frontend): migrate public landing page"
```

### Task 2: Public Machine Routes And Cutover Compatibility

**Files:**
- Create: `backend/rentivo/api/routes/public.py`
- Create: `backend/rentivo/api/routes/compatibility.py`
- Create: `backend/tests/api/routes/test_public.py`
- Create: `backend/tests/api/routes/test_compatibility.py`
- Modify: `backend/rentivo/api/app.py`
- Modify: `infra/proxy/nginx.conf`
- Modify: `backend/tests/test_preview_infrastructure.py`

**Interfaces:**
- Produces root routes `GET /health`, `GET /robots.txt`, and `GET /sitemap.xml`.
- Produces `GET /api/v1/ready`, which opens a database connection and executes `SELECT 1` before returning `{"status": "ready"}`.
- Produces compatibility redirects for historical downloads and browser aliases; known legacy mutation paths return problem status `410`.

- [ ] **Step 1: Write failing public and compatibility tests**

```python
def test_root_health_is_json(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ok"}

def test_robots_uses_public_origin(client, settings_override):
    settings_override(public_url="https://rentivo.example")
    response = client.get("/robots.txt")
    assert "Sitemap: https://rentivo.example/sitemap.xml" in response.text

def test_old_invoice_url_redirects_to_versioned_download(client):
    response = client.get("/billings/billing-1/bills/bill-1/invoice", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/api/v1/billings/billing-1/bills/bill-1/invoice"
```

Cover `/change-password`, `/security/pix`, Google login, invoice, recibo, receipt, attachment, readiness database failure, crawler media types, sitemap escaping, and representative stale POST routes.

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_public.py backend/tests/api/routes/test_compatibility.py backend/tests/test_preview_infrastructure.py`

Expected: root requests return 404 and proxy assertions fail.

- [ ] **Step 3: Implement public and compatibility routers**

Keep `GET /api/v1/health` as liveness. Register root public and compatibility routers on the FastAPI app outside the `/api/v1` router. Generate canonical URLs from `settings.public_url` or the validated request origin. Return `RedirectResponse(..., status_code=307)` for authenticated file aliases and `308` only for stable browser-page aliases.

Configure Nginx exact locations for `/health`, `/robots.txt`, and `/sitemap.xml`, regex locations for historical GET downloads, and a named location that proxies non-API legacy POST requests to FastAPI for a `410` problem response. The SPA fallback remains GET/HEAD only.

- [ ] **Step 4: Verify green**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_public.py backend/tests/api/routes/test_compatibility.py backend/tests/api/routes/test_health.py backend/tests/test_preview_infrastructure.py`

Expected: all selected tests pass and no public machine route returns HTML.

- [ ] **Step 5: Commit**

```bash
git add backend/rentivo/api/app.py backend/rentivo/api/routes/public.py backend/rentivo/api/routes/compatibility.py backend/tests/api/routes/test_public.py backend/tests/api/routes/test_compatibility.py backend/tests/test_preview_infrastructure.py infra/proxy/nginx.conf
git commit -m "feat(api): preserve public cutover routes"
```

### Task 3: Continuous Organization MFA Enforcement And Session Cutover

**Files:**
- Create: `frontend/src/features/auth/MfaSetupGuard.tsx`
- Create: `frontend/src/features/auth/MfaSetupGuard.test.tsx`
- Modify: `backend/rentivo/api/authentication.py`
- Modify: `backend/rentivo/api/routes/auth.py`
- Modify: `backend/rentivo/api/app.py`
- Modify: `backend/tests/api/test_authentication.py`
- Modify: `backend/tests/api/routes/test_auth.py`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/features/auth/AuthProvider.tsx`
- Modify: `frontend/src/features/auth/AuthProvider.test.tsx`

**Interfaces:**
- Produces `enforce_login_mfa(request, principal, services) -> None`, called after principal construction for login tokens.
- Produces request-state exemption `request.state.allow_mfa_setup` for session, logout, and MFA completion routes.
- Produces `MfaSetupGuard`, which routes an authenticated bootstrap with `capabilities.mfa_setup_required` to `/security/totp/setup`.

- [ ] **Step 1: Write failing enforcement tests**

```python
def test_login_token_with_required_mfa_cannot_read_billings(api_client, login_key):
    require_org_mfa_for(login_key.user_id)
    response = api_client.get("/api/v1/billings", cookies=access_cookie(login_key))
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_setup_required"

def test_required_mfa_can_open_setup(api_client, login_key):
    require_org_mfa_for(login_key.user_id)
    response = api_client.post("/api/v1/security/totp/setup", cookies=access_cookie(login_key), headers=csrf_headers())
    assert response.status_code == 200
```

Add frontend tests for direct navigation, setup exemptions, and redirect removal after a refreshed bootstrap reports MFA complete. Add an auth-session assertion that expires the legacy `session` cookie.

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/api/test_authentication.py backend/tests/api/routes/test_auth.py && npm --prefix frontend test -- --run src/features/auth/MfaSetupGuard.test.tsx src/features/auth/AuthProvider.test.tsx src/app/router.test.tsx`

Expected: protected API access succeeds and direct React navigation is not guarded.

- [ ] **Step 3: Implement server and browser guards**

Resolve the user's live organization MFA requirement after key authentication. Apply the rule only to `is_login_token` principals, including cookie and mobile Bearer login tokens; integration keys retain their normal scope/grant checks. Use explicit dependency exemptions rather than path-prefix string matching.

On every `/api/v1/auth/session` response, expire the old cookie:

```python
response.delete_cookie("session", path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")
```

Wrap authenticated routes with `MfaSetupGuard` inside `ProtectedApp`; exempt only `/security/totp/setup`, `/security/recovery-codes`, and logout behavior.

- [ ] **Step 4: Verify green and security regressions**

Run: `uv run --project backend pytest -q backend/tests/api/test_authentication.py backend/tests/api/routes/test_auth.py backend/tests/api/routes/test_mfa_auth.py backend/tests/api/routes/test_security.py && npm --prefix frontend test -- --run src/features/auth/MfaSetupGuard.test.tsx src/features/auth/AuthProvider.test.tsx src/app/router.test.tsx`

Expected: all selected tests pass, including integration-key and MFA setup exemptions.

- [ ] **Step 5: Commit**

```bash
git add backend/rentivo/api/authentication.py backend/rentivo/api/routes/auth.py backend/rentivo/api/app.py backend/tests/api/test_authentication.py backend/tests/api/routes/test_auth.py frontend/src/features/auth/MfaSetupGuard.tsx frontend/src/features/auth/MfaSetupGuard.test.tsx frontend/src/features/auth/AuthProvider.tsx frontend/src/features/auth/AuthProvider.test.tsx frontend/src/app/router.tsx
git commit -m "fix(auth): enforce required organization mfa"
```

### Task 4: Extract Shared Runtime Code From Legacy

**Files:**
- Create: `backend/rentivo/analytics.py`
- Create: `backend/rentivo/bill_transitions.py`
- Create: `backend/rentivo/email/templates/*.html`
- Create: `backend/rentivo/email/templates/*.txt`
- Create: `backend/tests/test_analytics.py`
- Create: `backend/tests/test_bill_transitions.py`
- Modify: `backend/rentivo/api/routes/billings.py`
- Modify: `backend/rentivo/api/routes/bills.py`
- Modify: `backend/rentivo/services/email_service.py`
- Modify: `backend/tests/api/routes/test_billings.py`
- Modify: `backend/tests/api/routes/test_bills.py`
- Modify: `backend/tests/services/test_email_service.py`
- Modify: `backend/rentivo/services/audit_service.py`
- Modify: `backend/rentivo/services/job_service.py`
- Modify: `backend/rentivo/services/storage_cleanup_service.py`

**Interfaces:**
- Produces `rentivo.analytics.analytics_hash(value) -> str | None` with identical HMAC output.
- Produces `rentivo.bill_transitions.StatusTransition` and `transitions_for(status)` with identical policy.
- Changes email rendering to `PackageLoader("rentivo.email", "templates")` while retaining every current HTML/text output.

- [ ] **Step 1: Write failing package-independence tests**

Move the existing analytics and transition policy assertions into tests importing `rentivo.analytics` and `rentivo.bill_transitions`. Add a subprocess/package test that blocks imports whose module name starts with `legacy_web` and renders every registered email template.

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/test_analytics.py backend/tests/test_bill_transitions.py backend/tests/services/test_email_service.py`

Expected: imports fail because shared modules and packaged email templates do not exist.

- [ ] **Step 3: Move framework-neutral modules and templates**

Copy only `analytics_hash` and its constants into `rentivo.analytics`; do not move Starlette session/page helpers. Move the complete transition policy unchanged. Move every file under `legacy_web/templates/emails` to `rentivo/email/templates` and update `EmailService` to load the new package. Replace runtime/test imports and remove legacy references from service docstrings.

- [ ] **Step 4: Verify byte-level behavior**

Run: `uv run --project backend pytest -q backend/tests/test_analytics.py backend/tests/test_bill_transitions.py backend/tests/services/test_email_service.py backend/tests/api/routes/test_billings.py backend/tests/api/routes/test_bills.py backend/tests/services/test_bill_service.py`

Expected: hashes, transition metadata, rendered subjects/bodies, API analytics headers, and bill behavior remain unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/rentivo/analytics.py backend/rentivo/bill_transitions.py backend/rentivo/email/templates backend/rentivo/api/routes/billings.py backend/rentivo/api/routes/bills.py backend/rentivo/services backend/tests/test_analytics.py backend/tests/test_bill_transitions.py backend/tests/services/test_email_service.py backend/tests/api/routes/test_billings.py backend/tests/api/routes/test_bills.py
git commit -m "refactor: extract legacy shared runtime code"
```

### Task 5: Production-Only Compose And Migration Ordering

**Files:**
- Replace: `docker-compose.yml`
- Modify: `docker-compose.dev.yml`
- Delete: `docker-compose.next.yml`
- Delete: `docker-compose.next.remote.yml`
- Modify: `backend/rentivo/api/app.py`
- Modify: `backend/rentivo/settings.py`
- Modify: `backend/tests/test_db.py`
- Modify: `backend/tests/test_settings.py`
- Modify: `backend/tests/test_preview_infrastructure.py`
- Modify: `backend/Dockerfile.api`
- Modify: `backend/Dockerfile.worker`
- Modify: `Makefile`

**Interfaces:**
- Default services are exactly `db`, `migrate`, `api`, `worker`, `frontend`, and `proxy` plus opt-in observability/Temporal profiles.
- `migrate` runs `alembic -c backend/alembic.ini upgrade head` and is required with `condition: service_completed_successfully` by API and worker.
- `validate_production_settings()` raises one aggregated `ValueError` listing every insecure production setting.

- [ ] **Step 1: Write failing topology, migration, and settings tests**

Assert the service set, no legacy Dockerfile reference, migrate dependency ordering, readiness health check, shared invoice volume, internal frontend/API network, loopback-only proxy/database publishing, and production environment values. Assert API lifespan never calls `initialize_db`.

```python
def test_production_rejects_insecure_defaults(settings_override):
    settings_override(environment="production", cookie_secure=False, public_url="http://localhost:8000")
    with pytest.raises(ValueError, match="RENTIVO_COOKIE_SECURE"):
        validate_production_settings()
```

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/test_preview_infrastructure.py backend/tests/test_settings.py backend/tests/test_db.py`

Expected: the default Compose service set is legacy-first, API lifespan migrates, and production validation is absent.

- [ ] **Step 3: Promote and harden the replacement topology**

Use the current replacement network isolation and proxy, remove `rentivo`, add a one-shot `migrate` service, and make API/worker depend on it. Preserve optional Jaeger and Temporal profiles. Remove `legacy_web` scaffolding from Docker build stages. Make local development an override of this same topology.

Call `validate_production_settings()` from API and worker startup. Required production failures cover default DB credentials, missing stable secret, non-HTTPS origins, mismatched WebAuthn RP ID, insecure/non-`__Host-` cookies, local email/storage, base64 encryption, and non-JSON logging.

Rename Make targets from preview semantics to `stack-*`; keep compatibility aliases for one release only when they execute the new stack and emit no legacy behavior.

- [ ] **Step 4: Verify Compose and startup**

Run: `docker compose config >/dev/null && uv run --project backend pytest -q backend/tests/test_preview_infrastructure.py backend/tests/test_settings.py backend/tests/test_db.py && docker build -f backend/Dockerfile.api . && docker build -f backend/Dockerfile.worker . && docker build -f frontend/Dockerfile .`

Expected: Compose validates, tests pass, and all three runtime images build without `legacy_web` scaffolding.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml docker-compose.dev.yml docker-compose.next.yml docker-compose.next.remote.yml backend/rentivo/api/app.py backend/rentivo/settings.py backend/tests/test_db.py backend/tests/test_settings.py backend/tests/test_preview_infrastructure.py backend/Dockerfile.api backend/Dockerfile.worker Makefile
git commit -m "feat(deploy): promote replacement production stack"
```

### Task 6: Delete The Legacy Application Package

**Files:**
- Delete: `backend/legacy_web/**`
- Delete: `backend/Dockerfile.legacy`
- Delete: `backend/tests/web/**`
- Modify: `backend/pyproject.toml`
- Modify: `backend/tests/services/test_bill_service.py`
- Modify: `backend/tests/services/test_container.py`
- Modify: `backend/tests/services/test_storage_cleanup_service.py`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/test-pr.yaml`

**Interfaces:**
- The installable backend exposes only `rentivo*` packages and coverage measures only `rentivo`.
- Service tests use `rentivo.context.Actor`; no compatibility actor or legacy services container remains.

- [ ] **Step 1: Add a failing repository independence test**

Add an infrastructure assertion that production/runtime paths contain none of these strings: `legacy_web`, `Dockerfile.legacy`, or a Compose service named `rentivo`. Assert `importlib.util.find_spec("legacy_web") is None` in the installed backend.

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/test_preview_infrastructure.py`

Expected: the package, image, tests, and packaging configuration still reference legacy.

- [ ] **Step 3: Delete legacy and update retained tests**

Delete the full legacy package and legacy-only route/template tests. Replace `WebActor` fixtures in retained service tests with `rentivo.context.Actor(user_id=..., email=..., source="web")`. Remove `legacy_web*` from setuptools, coverage, Ruff first-party names, workspace coverage sources, and CI image matrices.

- [ ] **Step 4: Verify package and retained behavior**

Run: `uv sync --project backend --frozen && uv run --project backend pytest -q backend/tests && rg -n 'legacy_web|Dockerfile\.legacy' backend/rentivo backend/pyproject.toml pyproject.toml docker-compose*.yml Makefile .github`

Expected: backend tests pass at 100%; `rg` exits 1 with no runtime/deployment matches.

- [ ] **Step 5: Commit**

```bash
git add -A backend/legacy_web backend/Dockerfile.legacy backend/tests/web backend/pyproject.toml backend/tests pyproject.toml .github/workflows/test-pr.yaml
git commit -m "refactor: remove legacy web application"
```

### Task 7: Integrated Release Gate, Deployment Contract, And Runbooks

**Files:**
- Create: `frontend/e2e/production-stack.spec.ts`
- Create: `scripts/smoke-production-stack.sh`
- Create: `docs/runbooks/production-release.md`
- Modify: `frontend/playwright.config.ts`
- Modify: `.github/actions/docker-build/action.yml`
- Modify: `.github/workflows/test-pr.yaml`
- Modify: `.github/workflows/deploy.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `.github/dependabot.yml`
- Modify: `README.md`
- Modify: `docs/development.md`
- Modify: `docs/jobs.md`
- Modify: `docs/observability.md`
- Modify: `CHANGELOG.md`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Produces a real-stack Playwright project selected with `PLAYWRIGHT_PRODUCTION_STACK=1` that performs no API interception.
- Produces `scripts/smoke-production-stack.sh BASE_URL`, which fails on incorrect media types, readiness, root, signup/login, or protected-session behavior.
- Deployment consumes immutable `${GITHUB_SHA}` image tags/digests that were built by the complete release gate.

- [ ] **Step 1: Write failing release-gate assertions**

Add tests that require a non-mocked Playwright project, production Compose boot in CI, immutable published image references, npm Dependabot coverage, and a release runbook without a legacy rollback path.

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/test_preview_infrastructure.py && npm --prefix frontend run e2e -- production-stack.spec.ts`

Expected: infrastructure assertions and real-stack startup fail because the deployment gate does not exist.

- [ ] **Step 3: Implement the release gate and deployment contract**

Run the production stack with disposable MariaDB credentials, execute migration, wait for readiness, and run Playwright without request interception. Cover public metadata/crawlers, signup, login, fresh-account empty states, organization-scoped API key denial, billing/invoice creation, worker-produced output, logout revocation, and required MFA navigation.

Build and publish immutable API/worker/frontend images only after the full gate. Require the protected production environment and deploy the tested SHA exactly once. Keep external webhook support only if the payload includes the immutable SHA/digests and the receiver reports migration, rollout, and smoke status atomically.

Document backup verification, maintenance mode, worker drain, migration revision, readiness/alert thresholds, previous-new-stack redeploy, forward fix, restore, ownership, and post-release checks. Update version and changelog for the breaking replacement release.

- [ ] **Step 4: Verify release workflow locally**

Run: `make lint && make test && make frontend-check && make openapi-check && docker compose config >/dev/null && ./scripts/smoke-production-stack.sh http://127.0.0.1:8080`

Expected: every gate passes against the real stack and the smoke script reports each endpoint/workflow as healthy.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/production-stack.spec.ts frontend/playwright.config.ts scripts/smoke-production-stack.sh docs/runbooks/production-release.md .github README.md docs/development.md docs/jobs.md docs/observability.md CHANGELOG.md backend/pyproject.toml
git commit -m "ci: gate big-bang production release"
```

### Task 8: Final Integration, Visual Verification, And Review

**Files:**
- Modify only files required by failures discovered during full verification.

**Interfaces:**
- Produces one clean release commit set with no legacy runtime dependency and a healthy local production stack.

- [ ] **Step 1: Run repository-wide legacy and placeholder scans**

Run: `rg -n 'legacy_web|Dockerfile\.legacy|production remains legacy|legacy-first' backend frontend infra docker-compose*.yml Makefile .github README.md docs pyproject.toml`

Expected: no runtime/deployment/documentation matches; historical design documents may be excluded explicitly.

- [ ] **Step 2: Run the complete backend and frontend gates**

Run: `make lint && make test && make frontend-check && make openapi-check && make e2e`

Expected: all checks pass with backend and authored frontend coverage at 100%.

- [ ] **Step 3: Rebuild and inspect the production topology**

Run: `docker compose build && docker compose up -d && docker compose ps && ./scripts/smoke-production-stack.sh http://127.0.0.1:8080`

Expected: migrate exits successfully; db, API, worker, frontend, and proxy are healthy; smoke checks pass.

- [ ] **Step 4: Verify desktop and mobile rendering**

Use Playwright screenshots at 1440x900 and 390x844 for `/`, `/login`, `/billings/`, and `/security`. Confirm no overlap, clipping, blank canvas, layout shift, or missing asset; confirm the landing leaves the next section visible and matches the approved design.

- [ ] **Step 5: Request code review and fix all release blockers**

Run focused tests for every review correction, then repeat Steps 1-4. Commit only after all findings are resolved.

- [ ] **Step 6: Push the branch and update the existing pull request**

```bash
git push origin codex/frontend-backend-api-key-foundation
gh pr view 138 --web
```

Expected: PR 138 contains the full coordinated release, CI is green, and the PR remains open for human merge.
