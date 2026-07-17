# Frontend/Backend Split and API-Key Foundation Design

**Date:** 2026-07-17

**Status:** Ready for user review

**Program strategy:** Big-bang production cutover

**This specification:** Foundation milestone

## Summary

Rentivo will become a monorepo containing an independently built React/Vite frontend and FastAPI backend. The existing worker remains a separate runtime built from the backend package. Production will expose one origin: the frontend owns page routes and `/api/v1/*` is routed to FastAPI.

The browser will authenticate with the same versioned API-key credential used by future mobile and integration clients. Browser login keys are stored in a secure HttpOnly cookie, live for exactly 24 hours, and are issued only after all required authentication and MFA steps succeed. Integration keys are user-managed, scoped, restricted to explicitly selected personal and organization workspaces, and disclosed only once.

The selected delivery strategy is a big-bang cutover. The legacy Jinja application remains the production interface while the replacement is developed and verified. Production traffic switches to the replacement only after every domain slice and parity gate is complete.

## Scope

This foundation milestone includes:

- the final monorepo and service boundaries;
- the versioned `/api/v1` FastAPI application and common API conventions;
- API-key persistence, issuance, validation, scope enforcement, resource grants, expiration, usage tracking, and revocation;
- password, signup, Google OAuth, TOTP, recovery-code, passkey, password-recovery, and organization-enforced MFA flows;
- the React/Vite/TypeScript application shell and all current authentication and security screens;
- a new integration-key management section using the existing Rentivo visual language;
- generated TypeScript API types from FastAPI OpenAPI;
- local development, CI, security, contract, component, end-to-end, and visual-parity tests for this milestone.

This milestone does not migrate billing, bills, expenses, organizations, invites, themes, communications, files, exports, or the public landing page to React. Those domains receive separate specifications and implementation plans, but they are developed against the architecture defined here. No production traffic is cut over during this milestone.

The future mobile application is not included. The API contract and Bearer-key transport are designed so a mobile client can be added without changing backend identity or authorization semantics.

## Repository and Runtime Boundaries

The target repository structure is:

```text
backend/
  pyproject.toml
  alembic.ini
  alembic/
  rentivo/
    api/                 # FastAPI application, routers, schemas, dependencies
    models/
    repositories/
    services/
    jobs/
    workers/
    email/
    storage/
    encryption/
    cache/
    observability/
  legacy_web/            # Existing Jinja app retained until final cutover
  tests/
  Dockerfile.api
  Dockerfile.worker
  Dockerfile.legacy
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  src/
    api/                 # Generated types and the shared request client
    app/                 # Providers, routing, shell, error boundaries
    components/
    features/
    styles/              # Existing CSS migrated without visual redesign
  tests/
infra/
  proxy/                 # Same-origin frontend/API routing
docker-compose.yml
```

The Python package remains named `rentivo`; moving it under `backend/` must not change public Python imports. Email templates move under the backend email package because they remain backend-owned. The legacy HTML application is isolated as `legacy_web` and removed only in the final cutover milestone.

There are two product services:

| Service | Responsibility | Production form |
| --- | --- | --- |
| Frontend | React application, static assets, client routing | Static build served by a minimal web container or equivalent static host |
| Backend | JSON API and all business/infrastructure code | FastAPI API container |

The worker is a second backend runtime, not a separate product boundary. It uses the same backend package, database, storage, encryption, job definitions, and observability conventions as the API.

## Public Routing

After final cutover, one public origin is used:

| Path | Destination |
| --- | --- |
| `/api/v1/*` | FastAPI backend |
| all page and asset routes | React frontend |

The browser therefore requires no production CORS configuration. Local Vite development proxies `/api/v1` to FastAPI. Future mobile and integration clients call the same API origin directly with a Bearer key.

The API version and key version are independent compatibility controls. `/api/v1` versions HTTP contracts; `rntv-v1-` versions credential parsing.

## API-Key Format and Storage

The complete credential format is:

```text
rntv-v1-<base64url of 32 cryptographically random bytes>
```

The backend creates keys with the standard-library cryptographic random generator. It stores no recoverable secret. Before persistence, the complete credential is UTF-8 encoded and hashed with SHA-256. High key entropy makes a fast hash appropriate and permits indexed lookup. Validation compares digest bytes in constant time after lookup.

For display, the backend stores the first four and final two characters of the random secret portion. The standard version prefix is not counted among those characters. The UI renders a hint such as:

```text
rntv-v1-aBcD••••yZ
```

An integration-key creation response contains the complete key exactly once and carries `Cache-Control: no-store`. Subsequent reads return only metadata and the masked hint. A lost key must be revoked and replaced.

Secrets, hashes, Authorization headers, authentication cookies, MFA codes, and one-time creation responses must be excluded from application logs, traces, analytics, audit state payloads, and exception reports.

## Data Model

### `api_keys`

| Column | Rule |
| --- | --- |
| `id` | Internal integer primary key |
| `uuid` | Public ULID, unique |
| `user_id` | Owning user foreign key, indexed |
| `name` | Required; user supplied for integration keys and service supplied for login keys |
| `secret_hash` | 32-byte SHA-256 digest, unique and indexed |
| `key_start` | First four random-secret characters |
| `key_end` | Final two random-secret characters |
| `is_login_token` | Internal boolean, default `false`; never serialized by management APIs |
| `expires_at` | Required UTC timestamp |
| `last_used_at` | Nullable UTC timestamp |
| `created_at` | Required UTC timestamp |
| `revoked_at` | Nullable UTC timestamp; integration keys only |

`is_login_token` is an internal implementation field. List, detail, creation, and update schemas for API-key management must not include it, even as a false value.

Login-token rows are hard-deleted on logout. Expired login-token rows are removed by an idempotent cleanup job. Integration-key revocation sets `revoked_at` and retains the row and masked metadata for audit history.

`last_used_at` is updated at most once per five-minute interval per key to avoid a database write on every request. Authentication correctness never depends on this timestamp.

### `api_key_scopes`

| Column | Rule |
| --- | --- |
| `api_key_id` | Foreign key with delete cascade |
| `scope` | Validated scope identifier |

The composite primary key is `(api_key_id, scope)`. Login tokens receive every first-party scope at issuance. Since they expire in 24 hours, newly introduced scopes become available after the next login rather than being granted retroactively to existing tokens.

### `api_key_resource_grants`

| Column | Rule |
| --- | --- |
| `api_key_id` | Foreign key with delete cascade |
| `resource_type` | `user` or `organization` |
| `resource_id` | User or organization internal ID |

The composite primary key is `(api_key_id, resource_type, resource_id)`. Integration keys must receive at least one grant when created. A `user` grant may target only the key owner. An `organization` grant may target only an organization where the owner is currently a member.

Login tokens do not need persisted grant rows. They dynamically receive the owner's personal workspace and every organization membership that exists when each request is authorized.

Removing a user from an organization immediately denies every key owned by that user in that organization. A stale grant row may remain for audit/UI purposes but confers no access.

### `auth_challenges`

A short-lived server-side challenge record replaces authentication state currently kept in the signed browser session. It stores a public challenge ULID, an opaque nonce digest, user ID, authentication phase, allowed MFA methods, WebAuthn challenge data when needed, failure count, creation time, expiration time, and consumption time.

For browser flows, FastAPI places the random nonce in a five-minute `Secure`, `HttpOnly`, `SameSite=Lax` `__Host-rentivo_challenge` cookie and returns only the public challenge ULID and allowed methods to React. Verification requests submit the public ULID and must also carry the matching nonce cookie. A future native-client login transport may return that nonce once for header transport, but that extension is outside this milestone.

Challenges expire after five minutes, are single-use, and enforce existing login/MFA rate limits. Successful completion atomically consumes the challenge before issuing a login key, then clears the challenge cookie. Expired and consumed rows are removed by the same cleanup mechanism used for expired login tokens.

## Scope Model

Every protected endpoint declares one required scope. Scopes express capability, not ownership. Passing a scope check never bypasses resource grants, organization membership, or domain roles.

The stable scope catalog is:

| Scope | Integration-selectable | Purpose |
| --- | --- | --- |
| `profile:read` | yes | Read the key owner's non-security profile |
| `account:write` | no | Change password or account-level settings |
| `security:manage` | no | Manage MFA, passkeys, and recovery codes |
| `api_keys:manage` | no | Create, edit, list, or revoke integration keys |
| `organizations:read` | yes | Read allowed organization metadata |
| `organizations:write` | no | Create or change organization settings |
| `organizations:members` | no | Invite, remove, or change member roles |
| `billings:read` | yes | Read billing templates and summaries |
| `billings:write` | yes | Create, edit, transfer, or delete billings when domain role permits |
| `bills:read` | yes | Read bills, status, and generated metadata |
| `bills:write` | yes | Generate, edit, transition, regenerate, or delete bills |
| `expenses:read` | yes | Read expenses |
| `expenses:write` | yes | Create or delete expenses |
| `files:read` | yes | Download invoices, receipts, and attachments |
| `files:write` | yes | Upload, reorder, or delete receipts and attachments |
| `communications:read` | yes | Preview and inspect communications |
| `communications:send` | yes | Send communications |
| `themes:read` | yes | Read effective theme settings |
| `themes:write` | yes | Change allowed theme settings |
| `exports:create` | yes | Request exports and read their status/result |

Login tokens receive all scopes. Integration-key forms show only integration-selectable scopes whose domain endpoints are present in the deployed API. The catalog reserves stable names for later domain milestones without showing unusable choices early. Backend validation rejects privileged or unavailable scopes even if a caller manually sends them.

## Effective Authorization

A request is authorized only when every applicable check succeeds:

1. The credential parses as a supported version and its digest matches an existing key.
2. The key is not expired or revoked.
3. The key contains the endpoint's required scope.
4. The target is in the key's effective personal/organization access set.
5. The owner still has live access to the target organization.
6. Existing owner/admin/manager/viewer domain authorization permits the action.

Integration-key capabilities are therefore the intersection of scopes, explicit grants, live membership, and existing domain roles. Hidden login tokens use dynamic grants but still obey domain roles.

Resources outside the effective access set return `404` rather than revealing their existence. A known resource blocked only by a missing scope returns `403` with a stable error code.

## Credential Transport

### Browser

After successful final authentication, FastAPI sets the complete login API key in a `Secure`, `HttpOnly`, `SameSite=Lax` cookie named `__Host-rentivo_access`. The cookie has `Path=/`, no `Domain`, and an absolute maximum age of 24 hours. React never reads or stores the secret. The database `expires_at` value is authoritative even if a client retains an old cookie.

Plain-HTTP local development uses environment-specific cookie names without `Secure`; staging and production must use `__Host-` names and secure flags for access, challenge, and CSRF cookies. Tests assert that insecure settings cannot be used in staging or production.

Browser requests use `credentials: "same-origin"`. Cookie-authenticated mutations also require a double-submit CSRF token sent through `X-CSRF-Token`. Bearer-authenticated requests are not subject to CSRF because the credential is not ambient.

### Mobile and integrations

Non-browser clients send the complete key only as:

```http
Authorization: Bearer rntv-v1-...
```

Keys are never accepted in URLs, query parameters, form fields, or arbitrary custom headers. If a request supplies different cookie and Bearer credentials, the backend rejects it as ambiguous rather than choosing one identity.

## Authentication Flows

All current authentication entry points remain available and preserve PT-BR copy, validation semantics, analytics events, audit behavior, rate limits, Turnstile integration, known-device notification, and organization-enforced MFA.

### Password or signup without MFA

1. React sends credentials and Turnstile response to the appropriate auth endpoint.
2. FastAPI validates the primary credential and account state.
3. FastAPI creates a hidden login key with all scopes and a fixed `now + 24 hours` expiration.
4. FastAPI sets `__Host-rentivo_access`, records audit/analytics events, and returns the authenticated bootstrap payload.

### Login requiring MFA

1. FastAPI validates the primary credential but creates no API key.
2. FastAPI creates a five-minute `auth_challenges` row, sets the challenge nonce cookie, and returns `202` with the public challenge ID and allowed verification methods.
3. React completes TOTP, recovery-code, or passkey verification using the public challenge ID and nonce cookie.
4. FastAPI atomically consumes the challenge and creates the login key.
5. The cookie and bootstrap response are issued only after successful verification.

### Google OAuth

The backend owns OAuth state, callback validation, user lookup/creation, and audit events. The callback either issues the login key or creates an MFA challenge, sets the challenge nonce cookie, and redirects to the React MFA route with the non-secret challenge ULID. OAuth state and login challenges are short-lived, single-use, and do not rely on an authenticated browser session.

### Logout and expiry

`POST /api/v1/auth/logout` authenticates the current cookie key, hard-deletes that login-token row, clears the access and CSRF cookies, and records the logout audit event. It does not revoke tokens on other devices.

An expired, missing, deleted, or revoked browser key returns `401`, clears stale authentication cookies, and causes React to discard user state and navigate to `/login`. Login-token expiration is absolute; activity never extends it.

### Security events

Password recovery and MFA reset revoke all hidden login tokens across devices. Explicit integration keys remain active and visible for manual revocation. Concurrent browser/device login tokens are allowed.

## API Surface for This Milestone

The exact request and response schemas are generated from Pydantic models and exposed in OpenAPI. The foundation endpoint groups are:

| Prefix | Responsibility |
| --- | --- |
| `/api/v1/auth` | Signup, login, session bootstrap, MFA challenge completion, Google OAuth, logout, password recovery |
| `/api/v1/security` | Password change, PIX profile, TOTP, recovery codes, passkey registration and deletion |
| `/api/v1/api-keys` | Integration-key creation, masked listing, metadata/grant/scope update, and revocation |
| `/api/v1/profile` | Current non-security profile required by the application shell |
| `/api/v1/health` | Liveness/readiness without authentication |

Integration-key list endpoints always filter out `is_login_token=true` before serialization. Integration-key creation returns the secret only in the `201` response. Updating a key may change its name, safe scopes, and resource grants. Expiration and secret are immutable; changing either requires creating a replacement key. Revocation is idempotent.

Account, security, API-key management, organization settings, membership, role, and ownership endpoints require both their privileged scope and `is_login_token=true`. Possessing a manually constructed scope row on an integration key cannot unlock these operations.

The application bootstrap response contains the current user, effective frontend capabilities, pending-invite count, non-secret feature flags, analytics configuration, and CSRF token. It never contains the login key.

## API Conventions and Errors

JSON field names use `snake_case`, timestamps use UTC RFC 3339 strings, and public resource identifiers use existing ULIDs/UUIDs rather than internal integer IDs.

Errors use `application/problem+json` with:

```json
{
  "type": "https://rentivo.app/problems/invalid_credentials",
  "title": "Credenciais inválidas",
  "status": 401,
  "code": "invalid_credentials",
  "detail": "E-mail ou senha inválidos.",
  "fields": {},
  "request_id": "..."
}
```

Stable status behavior is:

| Status | Use |
| --- | --- |
| `400` | Malformed or ambiguous request/credential transport |
| `401` | Missing, invalid, expired, deleted, or revoked credential |
| `403` | Authenticated credential lacks a required scope or privileged login-token capability |
| `404` | Resource is absent or outside effective resource access |
| `409` | Uniqueness, stale-state, or lifecycle conflict |
| `422` | Field validation errors |
| `429` | Login, MFA, password-reset, or key-creation rate limit |

Every response includes or propagates a request ID. Existing structured logging and tracing remain, with actor metadata extended by API-key UUID, key class, and source (`web`, `mobile`, or `integration`). Key names may appear in audit metadata; secrets, hashes, and masked hints do not.

## Frontend Architecture

The frontend uses React, Vite, TypeScript, React Router, and a query/cache layer for server state. FastAPI OpenAPI generates TypeScript contract types in CI. A small shared request client owns same-origin credentials, CSRF headers, problem-details parsing, request IDs, and global `401` handling.

The authentication secret is never frontend state. The frontend stores only the current user, capabilities, challenge progress, and non-secret bootstrap data.

The application shell contains:

- the existing top bar, responsive navigation, account dropdown, invite badge, toasts, and confirmation modal;
- route guards based on bootstrap authentication and capabilities;
- an error boundary and route-level loading/not-found states;
- analytics event dispatch preserving current names and payload semantics.

The current CSS, font imports, class names, copy, responsive breakpoints, DOM semantics, focus behavior, keyboard interactions, and URLs are migrated without redesign. Existing imperative JavaScript behaviors become focused React components and hooks. The new API-key section uses existing Security-page spacing, controls, tables, dialogs, and typography rather than introducing a new visual system.

The integration-key UI supports:

- required key name;
- safe scope selection;
- an explicit personal-workspace choice;
- multi-select organization grants limited to current memberships;
- expiration selection with a 90-day default and one-year maximum;
- one-time secret display with a clear completion acknowledgement;
- masked list rows showing name, hint, created time, expiry, last use, scopes, and workspaces;
- editing name, scopes, and grants;
- confirmed revocation.

Hidden login tokens never appear in counts, lists, filters, or UI copy.

## Visual and Behavioral Parity

Parity covers more than appearance. The replacement preserves:

- every existing public and authenticated URL unless a later domain specification explicitly documents a redirect;
- PT-BR text, validation errors, flash/toast meaning, empty states, and confirmation language;
- responsive layouts at existing breakpoints;
- keyboard navigation, focus restoration, dialog focus traps, and accessibility semantics;
- file upload/download behavior;
- GTM event names and privacy constraints;
- authorization outcomes and audit events.

Visual baselines are captured from the legacy app in a deterministic browser environment before each page is migrated. Dynamic timestamps, generated identifiers, and other nondeterministic regions are fixed or masked. Unexpected screenshot differences fail the parity gate and require explicit human approval.

## Testing and Verification

Backend tests retain the repository's 100% coverage requirement and cover:

- key generation, parsing, hashing, hint extraction, and one-time disclosure;
- repository CRUD, unique constraints, cleanup, throttled `last_used_at`, and migration behavior;
- fixed login expiry, concurrent sessions, current-token logout, global security-event revocation, and integration-key soft revocation;
- scope validation and privileged-scope rejection;
- personal and organization grants, removed memberships, and role intersections;
- cookie and Bearer transport, ambiguous credentials, CSRF, and secret redaction;
- password, signup, OAuth, TOTP, recovery code, passkey, password reset, and enforced-MFA flows;
- problem-detail responses and non-enumerating `404` behavior;
- audit and observability metadata without credential leakage.

Frontend tests use Vitest and Testing Library with 100% statement, branch, function, and line thresholds for authored frontend code. They cover route guards, auth transitions, errors, form validation, CSRF/request behavior, one-time key disclosure, scope/grant editing, revocation, focus management, and current UI interactions.

Playwright covers the complete browser flows at desktop and mobile viewports. It exercises password and MFA login, passkeys with supported browser fixtures, Google callback handling through deterministic test doubles, expiry, logout, password recovery, security management, key creation/edit/revocation, responsive navigation, accessibility checks, and screenshot parity.

CI verifies Python lint/format/tests, frontend lint/typecheck/unit tests, OpenAPI/client generation freshness, API/worker/frontend image builds, Alembic single-head state, dependency lockfiles, Playwright flows, and visual baselines.

## Delivery and Cutover

This milestone is merged without changing production routing. The legacy deployment remains the default while later specifications migrate every domain into `/api/v1` and React.

The final cutover gate requires:

1. every current route and workflow represented in a parity matrix;
2. all backend, frontend, contract, end-to-end, accessibility, and visual tests passing;
3. additive database migrations applied successfully in staging and production rehearsal;
4. frontend and API health/readiness checks passing behind the production proxy;
5. storage, email, worker, analytics, tracing, and audit behavior verified;
6. a documented route-only rollback to the legacy deployment.

The production switch changes proxy targets atomically. Database migrations remain backward-compatible with the legacy application throughout the rollback window. Rolling back restores legacy routing and may require users who authenticated only after cutover to log in again; it does not require a database rollback.

Legacy Jinja routes, session-authentication code, compatibility images, and server-rendered page assets are removed only after the replacement has remained stable beyond the rollback window.

## Success Criteria

The foundation milestone is complete when:

- the monorepo builds the legacy app, new API, worker, and React frontend independently;
- all existing authentication and security behavior is available through `/api/v1` and the React screens;
- browser identity is exclusively a hidden 24-hour API key in an HttpOnly cookie within the replacement app;
- integration keys can be created, disclosed once, listed by masked hint, scoped, workspace-limited, edited, and revoked;
- no API or management response can expose hidden login tokens or stored key material;
- generated TypeScript contracts match FastAPI OpenAPI;
- the complete verification suite passes at required coverage;
- production still routes to the unchanged legacy interface pending completion of later domain milestones.
