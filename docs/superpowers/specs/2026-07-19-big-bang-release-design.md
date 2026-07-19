# Big-Bang React/FastAPI Release Design

## Goal

Replace the production legacy web application in one release with the React/Vite frontend, versioned FastAPI API, background worker, MariaDB, and Nginx proxy. The same release migrates the public home page, closes the remaining route and security parity gaps, promotes the replacement topology to the production default, and removes the legacy runtime and source package.

## Release Boundary

The release is atomic from the user's perspective. One tested commit supplies every runtime artifact and the production deployment switches directly to the replacement stack. The legacy container is not retained as a rollback target. Users with an existing legacy browser session must perform one fresh login after deployment.

The production topology is:

```text
MariaDB -> one-shot Alembic migration -> FastAPI API + worker
                                      -> React static frontend
                                      -> Nginx edge proxy
```

The proxy routes `/api/v1` and explicit public machine endpoints to FastAPI and all browser routes to the React frontend. The worker and API start only after the migration job succeeds. API startup never runs Alembic directly.

## Public Home Page

The current Jinja landing page becomes a public React route at `/`. Its Portuguese copy, section order, visual hierarchy, responsive behavior, and existing CSS remain unchanged. The landing feature is divided into focused header, hero, trust, feature, steps, showcase, call-to-action, and footer components. Existing landing and shared CSS remain the visual source of truth.

Anonymous visitors see the landing page immediately. The authentication provider resolves a session in the background; authenticated visitors to `/` are redirected to `/billings/`. Public authentication routes remain outside the authenticated application shell.

The initial frontend HTML contains the landing title, description, canonical URL, Open Graph fields, Twitter fields, and SoftwareApplication JSON-LD so crawlers receive useful metadata without executing JavaScript. Route-level metadata updates the browser document for login, signup, and authenticated views. The favicon and Open Graph image live in `frontend/public`.

## Public Machine Routes

FastAPI owns public machine-readable responses while Nginx exposes them at their historical paths:

- `/health` and `/api/v1/health` return JSON health documents.
- `/robots.txt` preserves the existing crawler allow/disallow policy and references the canonical sitemap.
- `/sitemap.xml` lists `/`, `/login`, and `/signup` using the configured public origin.

Health is split into liveness and dependency-aware readiness. The proxy health check uses readiness so HTML fallback responses cannot produce false positives.

## Authentication And MFA

The cutover intentionally invalidates legacy signed sessions. The first replacement session check expires the obsolete `session` cookie; users then authenticate through the existing API-key login-token flow. Logout continues to revoke the hidden login key and expire browser cookies.

Organization-required MFA is enforced in FastAPI for every browser login-token request, not only during the login response. Authentication, logout, MFA setup, MFA confirmation, and recovery endpoints are exempt as required to complete setup. Other requests receive the stable `mfa_setup_required` problem. React mirrors this rule with a route guard that sends the user to `/security/totp/setup` without relying on a one-time login response.

## Compatibility Surface

Historical bookmarkable GET routes remain usable where doing so is safe:

- Legacy invoice, receipt, recibo, and billing-attachment URLs resolve to authenticated FastAPI file responses.
- `/change-password` redirects to `/security`.
- `/security/pix` redirects to `/security`.
- `/auth/google/login` redirects to the FastAPI Google authorization start endpoint.

Legacy form POSTs are not translated into new JSON contracts. An old page submitted during the deployment window receives `410 Gone` with a request ID and a clear refresh response rather than a soft 404 or partial mutation.

Unknown browser routes render the React not-found view. Machine routes and removed compatibility routes return accurate non-HTML status codes. SEO tests guard against soft-404 regressions.

## Legacy Extraction And Removal

Code still imported from `legacy_web` is moved under `rentivo` before deletion:

- Analytics event construction becomes a framework-neutral backend module.
- Bill transition helpers become a domain module consumed by API routes and services.
- Email templates and rendering lookup move into the packaged email subsystem.

After imports are redirected, the release deletes the legacy FastAPI app, Jinja page templates, route modules, static JavaScript/CSS copies, legacy Dockerfile, legacy Compose service, legacy-only tests, and legacy-first documentation. Shared domain, storage, encryption, cache, PDF, job, and database abstractions remain unchanged.

## Production Deployment

The replacement manifest becomes the default production Compose definition and contains only `db`, `migrate`, `api`, `worker`, `frontend`, and `proxy`. Development overrides may add bind mounts and local ports, but cannot add the legacy service. Preview-era names and commands are retired or renamed to describe the production stack accurately.

CI builds the API, worker, and frontend artifacts from one release SHA. Release artifacts are immutable and identified by digest or immutable commit tag. The deployment workflow deploys exactly the commit that passed the complete PR/release gate; a GitHub release and a production deployment cannot refer to different source states.

Production configuration fails closed. Startup rejects default database credentials, generated-on-boot secrets, insecure cookies, localhost public/WebAuthn origins, local-only email or storage, and reversible development encryption. Production requires the canonical HTTPS origin, stable WebAuthn RP ID, secure `__Host-` cookies, durable storage, configured email, KMS-backed encryption, and structured logging.

## Migration And Recovery

Exactly one migration job runs before application services. CI rehearses the migration on both an empty database and a production-shaped anonymized snapshot, verifies the Alembic revision, and validates critical row counts, UUID uniqueness, indexes, and foreign keys. The release process records migration duration and lock behavior before scheduling the cutover.

Before deployment, operators verify a restorable database backup. Recovery uses the previous React/FastAPI artifacts when the schema remains compatible. When it is not compatible, operators choose a forward fix or restore the verified backup under maintenance mode. The runbook records decision thresholds, maximum acceptable data loss, ownership, and post-recovery verification. It never routes traffic to the deleted legacy service.

The worker drains in-flight work on shutdown or the deployment process explicitly drains the queue before replacement. Retries remain idempotent for emails, exports, PDFs, and storage side effects.

## Observability And Failure Handling

The production stack exposes separate liveness and readiness checks for API dependencies, worker heartbeat and queue age, structured request IDs, and release markers. Dashboards and alerts cover HTTP errors/latency, frontend runtime errors and Web Vitals, worker dead letters, and queue backlog. The release runbook defines abort and forward-fix thresholds.

JSON API failures retain the existing problem-details contract. Public machine endpoints return their declared content types. Frontend route failures retain the established loading, retry, empty, confirmation, field-error, and toast patterns. Production configuration errors stop startup with actionable messages instead of falling back to development behavior.

## Testing And Release Gates

Backend and authored frontend coverage remain 100%. Tests cover the landing components, anonymous/authenticated root behavior, route metadata, crawler files, public health aliases, compatibility redirects/downloads, stale form responses, forced legacy-cookie expiry, and server-side MFA enforcement.

Playwright retains fast mocked component workflows and adds a MariaDB-backed production-topology suite. The integrated suite covers signup, login, forced MFA setup, session cookies, fresh-account empty states, organization-scoped API keys, billing and invoice workflows, worker execution, logout revocation, inaccessible organizations, landing accessibility, metadata, crawler responses, and desktop/mobile layout.

CI validates the default production Compose manifest, migration ordering, health dependencies, image builds, OpenAPI freshness, security scans, and the integrated smoke suite. The deployment workflow either promotes these exact tested artifacts or reruns an equivalent gate for the immutable release SHA.

## Delivery Workstreams

Implementation proceeds in parallel but lands as one release:

1. Public React landing, metadata, assets, and browser tests.
2. FastAPI public/compatibility endpoints and MFA enforcement.
3. Shared-code extraction and complete legacy package removal.
4. Production Compose, migration ordering, configuration validation, and proxy health.
5. CI, integrated E2E, deployment contract, observability, release notes, and recovery runbook.

The work is release-ready only when all five workstreams pass together and repository-wide searches find no production or runtime dependency on `legacy_web`, `Dockerfile.legacy`, or the legacy Compose service.
