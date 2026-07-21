# Rentivo iOS Live API Integration Design

**Date:** 2026-07-21

**Status:** Approved for implementation planning

**API contract:** `frontend/openapi.json` on `origin/main` after PR #138

**Production API origin:** `https://rentivo.com.br`

## Summary

Replace the iOS demonstration app's production-time mock dependencies with API-backed repositories while preserving the existing SwiftUI screens, PT-BR product language, and deterministic mock mode for previews and UI tests. Swift OpenAPI Generator creates the wire client at build time from the repository's committed contract; handwritten adapters map generated request/response types to stable app-domain models.

The first live authentication release supports email/password signup and login, bearer session restoration and logout, password recovery/change, TOTP enrollment and login verification, and recovery-code verification/regeneration. Google OAuth and passkeys remain excluded because the current API's Google flow is browser-cookie based and real passkeys require Apple associated-domain provisioning.

## Goals

- Make a normal app launch use `https://rentivo.com.br` under `/api/v1`.
- Preserve mock injection for previews, unit tests, UI tests, and screenshots.
- Generate the low-level Swift client from `frontend/openapi.json` and fail CI if the iOS copy drifts.
- Store only the bearer access token in Keychain; never persist passwords, MFA codes, recovery codes, or API-key secrets.
- Restore authenticated sessions on cold launch and clear local credentials on logout or an authenticated `401`.
- Wire every existing app surface that has a corresponding API operation: profile/PIX/password, billings, bills, receipts, expenses, attachments, communications, exports, organizations, invitations, TOTP/recovery codes, API keys, and themes.
- Keep domain and UI code independent of generated OpenAPI names.
- Support real multipart uploads and binary downloads with native document picking, previewing, sharing, and export.
- Preserve an executable test suite that does not require production credentials or production data.

## Non-goals

- No Google login in the iOS app until the backend offers a native callback/token exchange.
- No passkey registration or authentication until the Apple App ID, `webcredentials` entitlement, and AASA file are provisioned.
- No cookie or CSRF authentication for native requests; iOS always sends `credential_transport: "body"` and uses returned bearer tokens.
- No offline-first cache, background sync, push notifications, analytics, or production credential fixtures.
- No automatic retry of mutations. Reads may offer an explicit retry button; a `429` honors the user-visible error without silently repeating the request.
- No new backend endpoints. Dashboard data is derived from existing billings/bills/expenses responses, and recent activity is session-local because the API exposes no activity feed.
- No backend changes to fix unrelated `origin/main` workflow-pin test failures introduced by PR #151.

## Product Decisions

### Authentication scope

The app implements:

- Email/password login and signup.
- Session restoration through `GET /api/v1/auth/session`.
- Logout through `POST /api/v1/auth/logout` plus unconditional local token deletion.
- Forgot-password request and reset-link confirmation copy.
- In-session password change.
- MFA challenge routing for TOTP and recovery codes.
- TOTP setup, confirmation, disable, and recovery-code regeneration.

The app removes all passkey and Google controls from production navigation. Mock-only previews may still instantiate excluded views while migration is in progress, but UI tests must assert that production authentication does not display them.

### Environment

`APIConfiguration.production` is exactly:

```swift
APIConfiguration(serverURL: URL(string: "https://rentivo.com.br")!)
```

The generated operations already include `/api/v1`; no extra path prefix is appended. Debug builds may accept `RENTIVO_API_BASE_URL` from the process environment for local development. Release builds ignore overrides. The transport never forwards authorization to a different host after a redirect.

### Identifier correction

The mock app currently assumes every resource is a UUID. The live contract does not:

- Public domain resources use opaque ULID/string identifiers.
- Auth bootstrap user IDs and organization member user IDs are integers.
- API-key grants use literal `"personal"` for the personal workspace and an opaque organization identifier otherwise.

The domain layer therefore adopts focused wrappers:

```swift
public struct ResourceID<Tag>: RawRepresentable, Hashable, Codable, Sendable, Identifiable {
  public let rawValue: String
  public var id: String { rawValue }
  public init(rawValue: String) { self.rawValue = rawValue }
}

public enum BillingIDTag {}
public typealias BillingID = ResourceID<BillingIDTag>
public enum BillIDTag {}
public typealias BillID = ResourceID<BillIDTag>
public enum OrganizationIDTag {}
public typealias OrganizationID = ResourceID<OrganizationIDTag>
```

Each public resource receives its own alias. `UserProfile.id` and `OrganizationMember.userID` use `Int`. Local-only activity IDs remain UUIDs. Mock fixture UUID strings remain valid opaque IDs and do not need to resemble ULIDs.

Organization roles match the API's `admin`, `manager`, and `viewer` values. Ownership is represented separately by capabilities and resource ownership instead of a client-only `owner` role.

## Architecture

### Contract generation

`ios/Rentivo/openapi.json` is an exact copy of `frontend/openapi.json`. A repository script copies it and a check command compares the files byte-for-byte. The app and `RentivoCore` SwiftPM target attach Apple's `OpenAPIGenerator` build plugin with:

```yaml
generate:
  - types
  - client
accessModifier: internal
```

Generated source is build output and is never committed. The generated `Client`, `Operations`, and `Components` types stay inside the data layer.

### Layering

```text
SwiftUI feature views
        ↓
AppModel and focused repository protocols
        ↓
APIRentivoStore domain adapters and mappers
        ↓
generated OpenAPI Client + auth/error middleware
        ↓
URLSessionTransport → https://rentivo.com.br
```

The existing `MockRentivoStore` continues to conform to the same protocols. `AppDependencies.live()` constructs one shared API store; `AppDependencies.mock()` constructs the deterministic local store.

### Transport and credentials

`CredentialStore` exposes asynchronous `readAccessToken()`, `saveAccessToken(_:)`, and `deleteAccessToken()` operations. `KeychainCredentialStore` uses a generic-password item scoped to the bundle ID and account `rentivo.access-token`; tests use `MemoryCredentialStore`.

`BearerAuthMiddleware` reads the token for every authenticated operation, writes `Authorization: Bearer <token>`, and never logs headers or bodies. Public auth operations are invoked through an unauthenticated generated client. A centralized response middleware observes authenticated `401` responses, deletes the token, and emits one session-expired event consumed by `AppModel`.

Tokens are not refreshed because the contract does not expose a refresh operation. Session expiry returns the user to login with the PT-BR notice `Sua sessão expirou. Entre novamente.`

### API errors

All repository methods normalize generated non-success outputs and transport failures into:

```swift
public struct APIProblem: Error, Equatable, Sendable {
  public let status: Int?
  public let code: String?
  public let title: String
  public let detail: String
  public let fields: [String: [String]]
  public let requestID: String?
}
```

The mapper preserves field-level validation messages and request IDs. UI copy distinguishes invalid credentials, forbidden actions, missing resources, conflicts, validation, rate limiting, unavailable service, offline transport, cancellation, and unknown failure. Secrets, tokens, request bodies, and recovery codes never appear in logs.

### Authentication state machine

`AppModel.Session` becomes:

```swift
enum Session: Equatable {
  case restoring
  case anonymous
  case submitting
  case mfaRequired(MFAChallenge)
  case authenticated(UserProfile)
}
```

On launch, `restoreSession()` checks Keychain. With no token it becomes anonymous; with a token it calls the session endpoint. Login/signup either return an authenticated bearer payload or an MFA challenge. MFA verification returns the same authenticated payload and persists its token before publishing the authenticated state. Recovery codes are accepted as single-use secrets and immediately discarded from view state.

### Domain repositories

Protocols remain feature-focused, but signatures are corrected for live behavior:

- `AuthRepository`: restore, login, signup, verify TOTP, verify recovery code, forgot password, logout.
- `ProfileRepository`: load profile and update PIX.
- `SecurityRepository`: change password; load security summary; set up, confirm, and disable TOTP; regenerate recovery codes.
- `BillingRepository`: list/get/create/update/delete and transfer billings.
- `BillRepository`: list/get/create/update/delete, transition, regenerate, receipt lifecycle, and document downloads.
- `ExpenseRepository`: list/create/delete.
- `AttachmentRepository`: list/upload/download/delete using a `FileUpload` value containing bytes, name, and media type.
- `CommunicationRepository`: preview and send.
- `ExportRepository`: request and download generated exports according to the contract response.
- `OrganizationRepository`: organization lifecycle, member roles, invitations, MFA policy, and transfers.
- `InvitationRepository`: pending/accept/decline.
- `APIKeyRepository`: options, list/get/create/update/revoke. One-time secrets exist only in `CreatedAPIKeySecret`.
- `ThemeRepository`: get/update/reset user, organization, and billing themes, plus preview.

Generated output switching occurs only inside adapters. Each adapter treats explicitly documented `2xx` cases as success and maps every other case through `APIProblemMapper`.

### Dashboard and recent activity

The backend has no dashboard or activity endpoint. `APIDashboardRepository` loads the same billing/bill/expense records used by feature screens and computes totals using integer centavos. It may cache only within one screen load to avoid duplicate fan-out; there is no persistent cache.

`SessionActivityRepository` starts empty and records successful mutations made in the current app process. Home hides the recent-activity section when empty. It never presents mock history as server history.

### Files and documents

Uploads use generated multipart request bodies from `FileUpload.data`. Downloads are copied from response body streams to an app-owned temporary file, validated against the expected media type and suggested filename, and presented with Quick Look or the system share sheet. Temporary files are cleaned when the presentation ends. The repository never builds file URLs from untrusted server strings; it calls generated download operations on the fixed server origin.

### Dependency selection

Normal launch uses `.live()`. The following launch arguments select `.mock()` before `AppModel` is constructed:

- `--ui-testing`
- `--screenshot-authenticated`
- `--screenshot-tab <tab>`

SwiftUI previews always inject mock dependencies. Demo scenario controls are compiled in `DEBUG` and hidden when live dependencies are active.

## UI Changes

- Login and signup buttons show progress, disable duplicate submission, and display normalized API errors.
- MFA offers TOTP and recovery-code modes only when present in the server challenge.
- Forgot password sends the real request but always shows neutral confirmation copy to avoid account enumeration.
- Security replaces the simulated TOTP toggle with setup secret/QR metadata, six-digit confirmation, explicit disable confirmation, and one-time recovery-code display.
- Passkey controls are absent from live account security.
- File surfaces use document picker/importer and Quick Look/share presentation.
- Every screen preserves its current loading, empty, content, and retry states.
- Destructive actions retain confirmation dialogs and become disabled while submitted.
- A session-expired notice appears on return to the authentication shell.

## Test Strategy

### Contract and generated client

- `make ios-openapi-sync` copies the canonical file.
- `make ios-openapi-check` fails if the two files differ.
- `swift test --package-path ios` proves the plugin can generate and compile the client.
- Xcode build proves the same plugin wiring on the app target.

### Unit tests

- Identifier wrappers accept UUID and ULID-shaped strings and never parse them as UUID.
- Mappers cover representative success payloads and nullable/unknown values from fixtures derived from the committed schema.
- Credential tests cover save/read/delete/update and Keychain error translation without using a real production token.
- Middleware tests prove bearer injection, public-request omission, no cross-host forwarding, and `401` expiry signaling.
- Auth state tests cover no token, valid session, invalid session, email/password success, MFA challenge, TOTP success, recovery success, logout failure with local deletion, and cancellation.
- Repository tests use a deterministic `MockClientTransport`/test transport; they never contact production.
- Dashboard calculations use integer-centavo expectations.
- File tests cover multipart metadata and safe temporary download handling.

### UI tests

UI tests always launch with `--ui-testing` and remain deterministic. They cover login, MFA, core navigation, one billing mutation, TOTP setup, and session expiry using mock repositories. No test creates data at `rentivo.com.br`.

### Manual live smoke test

A developer-provided account may exercise login, session restoration, list reads, one reversible profile edit, and logout against `https://rentivo.com.br`. Credentials are typed interactively or injected through local Xcode scheme environment values excluded from source control. Destructive production mutations are not part of automated verification.

## Delivery Sequence

1. Contract generation, transport, credentials, error model, and deterministic tests.
2. Identifier migration and protocol corrections while keeping all mock tests green.
3. Authentication/session/TOTP/recovery vertical slice and live dependency selection.
4. Profile/security and dashboard.
5. Billings, bills, expenses, files, communications, and exports.
6. Organizations, invitations, API keys, and themes.
7. UI polishing, full regression, live smoke test, documentation, and PR.

Every step remains reviewable and runnable. Mock mode stays functional after each vertical slice, so an incomplete live adapter cannot break demonstration and UI-test workflows.

## Acceptance Criteria

- A production-configured launch calls only `https://rentivo.com.br` and restores a bearer session from Keychain.
- Email/password and required TOTP/recovery-code login work end-to-end without Apple Developer associated-domain setup.
- Logout and authenticated `401` both delete the local token.
- All existing non-passkey product screens use API repositories where the contract has a matching operation.
- Generated types do not escape the data layer.
- ULID/string and integer identifiers round-trip without UUID assumptions.
- Uploads and downloads use real bytes rather than filenames alone.
- Mock previews and UI tests never make network calls.
- OpenAPI drift, unit tests, Xcode build, and UI tests pass, apart from the separately documented pre-existing backend workflow-pin failures on `origin/main`.
