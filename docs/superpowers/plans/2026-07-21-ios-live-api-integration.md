# Rentivo iOS Live API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the native iOS demonstration app's production mock store with a secure, generated-client integration to `https://rentivo.com.br`, including email/password, TOTP, recovery codes, and every existing non-passkey product surface supported by the API.

**Architecture:** Apple's build plugin generates low-level client and schema types from an exact iOS copy of `frontend/openapi.json`. A handwritten `APIRentivoStore` and focused mapper files translate generated operations into stable app-domain repositories; Keychain-backed bearer middleware and centralized problem decoding handle session and errors. Normal launches inject live dependencies, while previews, screenshots, unit tests, and UI tests explicitly inject the existing deterministic mock store.

**Tech Stack:** Swift 6, SwiftUI, Observation, Foundation, Security/Keychain, Swift Testing, XCTest/XCUITest, Swift OpenAPI Generator 1.13.x, Swift OpenAPI Runtime 1.12.x, Swift OpenAPI URLSession 1.3.x, iOS 17.0+, FastAPI OpenAPI 3.x contract

## Global Constraints

- Production origin is exactly `https://rentivo.com.br`; generated paths already include `/api/v1`.
- Debug builds may read `RENTIVO_API_BASE_URL`; release builds ignore environment overrides.
- Native auth always sends `credential_transport: "body"` and stores only the returned bearer access token.
- Email/password, password recovery/change, TOTP, and recovery codes are in scope; Google OAuth and passkeys are out of scope.
- No Apple Developer membership, associated domain, AASA file, or `webcredentials` entitlement is required for this plan.
- Generated OpenAPI types never escape `ios/Rentivo/Data/API/`.
- Public resource identifiers are opaque strings; user/member identifiers are integers; never parse API identifiers as UUID.
- BRL remains integer centavos throughout the domain and UI.
- Upload APIs receive bytes, filename, and media type; download APIs return app-owned temporary files.
- Passwords, bearer tokens, MFA codes, recovery codes, API-key secrets, and request bodies must never be logged.
- Mutations are never retried automatically.
- Normal app launches use live dependencies. `--ui-testing` and screenshot arguments use mock dependencies and never contact the network.
- All customer-facing copy is PT-BR; source identifiers remain English.
- Preserve the iOS 17.0 deployment target and current four-tab navigation.
- Do not modify backend behavior or fix the unrelated PR #151 workflow action-pin failures in this branch.

---

## File Map

```text
Makefile
scripts/sync-ios-openapi.sh
ios/Package.swift
ios/Rentivo.xcodeproj/project.pbxproj
ios/Rentivo/openapi.json
ios/Rentivo/openapi-generator-config.yaml
ios/Rentivo/App/AppModel.swift
ios/Rentivo/App/RentivoApp.swift
ios/Rentivo/App/RootView.swift
ios/Rentivo/Domain/Identifiers.swift
ios/Rentivo/Domain/Models.swift
ios/Rentivo/Domain/BillingModels.swift
ios/Rentivo/Domain/AccountModels.swift
ios/Rentivo/Data/Repositories.swift
ios/Rentivo/Data/API/APIConfiguration.swift
ios/Rentivo/Data/API/APIProblem.swift
ios/Rentivo/Data/API/CredentialStore.swift
ios/Rentivo/Data/API/KeychainCredentialStore.swift
ios/Rentivo/Data/API/BearerAuthMiddleware.swift
ios/Rentivo/Data/API/GeneratedClientFactory.swift
ios/Rentivo/Data/API/APIRentivoStore.swift
ios/Rentivo/Data/API/Mappers/AuthMapper.swift
ios/Rentivo/Data/API/Mappers/BillingMapper.swift
ios/Rentivo/Data/API/Mappers/OrganizationMapper.swift
ios/Rentivo/Data/API/Mappers/AccountMapper.swift
ios/Rentivo/Data/API/FileTransfer.swift
ios/Rentivo/Data/API/SessionActivityRepository.swift
ios/Rentivo/Data/MockRentivoStore.swift
ios/Rentivo/Features/Auth/AuthViews.swift
ios/Rentivo/Features/Home/HomeView.swift
ios/Rentivo/Features/Account/AccountView.swift
ios/Rentivo/Features/Account/SecurityViews.swift
ios/Rentivo/Features/Account/APIKeyViews.swift
ios/Rentivo/Features/Account/ThemeViews.swift
ios/Rentivo/Features/Billings/BillingListView.swift
ios/Rentivo/Features/Billings/BillingDetailView.swift
ios/Rentivo/Features/Bills/BillViews.swift
ios/Rentivo/Features/Bills/BillingOperationsViews.swift
ios/Rentivo/Features/Organizations/OrganizationViews.swift
ios/Rentivo/Features/Organizations/InvitationViews.swift
ios/RentivoTests/IdentifierMigrationTests.swift
ios/RentivoTests/APIConfigurationTests.swift
ios/RentivoTests/APIProblemTests.swift
ios/RentivoTests/CredentialStoreTests.swift
ios/RentivoTests/BearerAuthMiddlewareTests.swift
ios/RentivoTests/AuthMapperTests.swift
ios/RentivoTests/AuthStateTests.swift
ios/RentivoTests/ProfileSecurityRepositoryTests.swift
ios/RentivoTests/BillingRepositoryTests.swift
ios/RentivoTests/BillOperationsRepositoryTests.swift
ios/RentivoTests/OrganizationRepositoryTests.swift
ios/RentivoTests/AccountRepositoryTests.swift
ios/RentivoTests/FileTransferTests.swift
ios/RentivoTests/LiveDependencyTests.swift
ios/RentivoUITests/RentivoUITests.swift
ios/README.md
```

---

### Task 1: Generate the Swift client from the canonical contract

**Files:**
- Create: `scripts/sync-ios-openapi.sh`
- Create: `ios/Rentivo/openapi.json`
- Create: `ios/Rentivo/openapi-generator-config.yaml`
- Modify: `Makefile`
- Modify: `ios/Package.swift`
- Modify: `ios/Rentivo.xcodeproj/project.pbxproj`

**Interfaces:**
- Consumes: canonical `frontend/openapi.json`
- Produces: generated `Client`, `Operations`, and `Components` in both the SwiftPM core target and Xcode application target
- Produces: `make ios-openapi-sync` and `make ios-openapi-check`

- [ ] **Step 1: Add a failing drift check**

Create the executable sync script with this exact content:

```sh
#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_contract="$repo_root/frontend/openapi.json"
ios_contract="$repo_root/ios/Rentivo/openapi.json"

case "${1:-sync}" in
  sync)
    cp "$source_contract" "$ios_contract"
    ;;
  check)
    if ! cmp -s "$source_contract" "$ios_contract"; then
      echo "ios/Rentivo/openapi.json is stale; run make ios-openapi-sync" >&2
      exit 1
    fi
    ;;
  *)
    echo "usage: $0 [sync|check]" >&2
    exit 64
    ;;
esac
```

Add these Make targets:

```make
.PHONY: ios-openapi-sync ios-openapi-check
ios-openapi-sync:
	./scripts/sync-ios-openapi.sh sync

ios-openapi-check:
	./scripts/sync-ios-openapi.sh check
```

- [ ] **Step 2: Verify the check fails before the copy exists**

Run: `chmod +x scripts/sync-ios-openapi.sh && make ios-openapi-check`

Expected: exit 1 with `ios/Rentivo/openapi.json is stale`.

- [ ] **Step 3: Copy the contract and add generator configuration**

Run: `make ios-openapi-sync`

Create `ios/Rentivo/openapi-generator-config.yaml`:

```yaml
generate:
  - types
  - client
accessModifier: internal
```

Update `ios/Package.swift` dependencies and core target:

```swift
dependencies: [
  .package(url: "https://github.com/apple/swift-openapi-generator", from: "1.13.0"),
  .package(url: "https://github.com/apple/swift-openapi-runtime", from: "1.12.0"),
  .package(url: "https://github.com/apple/swift-openapi-urlsession", from: "1.3.1"),
],
targets: [
  .target(
    name: "RentivoCore",
    dependencies: [
      .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
      .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession"),
    ],
    path: "Rentivo",
    exclude: ["App", "DesignSystem", "Features", "Resources"],
    sources: ["Domain", "Data"],
    plugins: [.plugin(name: "OpenAPIGenerator", package: "swift-openapi-generator")]
  ),
  .testTarget(
    name: "RentivoCoreTests",
    dependencies: ["RentivoCore"],
    path: "RentivoTests"
  ),
]
```

In `project.pbxproj`, add exact-version-up-to-next-major remote package references for the three Apple URLs, link `OpenAPIRuntime` and `OpenAPIURLSession` to `Rentivo`, and attach the `OpenAPIGenerator` product as a build-tool plug-in to the Rentivo target. Do not link these products to UI-test targets.

- [ ] **Step 4: Resolve packages and compile generated operations**

Run: `make ios-openapi-check && swift package --package-path ios resolve && swift test --package-path ios`

Expected: contract check passes; SwiftPM resolves generator 1.13.x, runtime 1.12.x, URLSession 1.3.x; existing 44 tests pass.

Run: `xcodebuild -resolvePackageDependencies -project ios/Rentivo.xcodeproj -scheme Rentivo`

Expected: exit 0 and all three Apple packages appear in resolved dependencies.

- [ ] **Step 5: Commit the contract toolchain**

```bash
git add Makefile scripts/sync-ios-openapi.sh ios/Package.swift ios/Rentivo/openapi.json ios/Rentivo/openapi-generator-config.yaml ios/Rentivo.xcodeproj/project.pbxproj
git commit -m "build(ios): generate client from OpenAPI contract"
```

---

### Task 2: Correct identifiers and repository interfaces

**Files:**
- Create: `ios/Rentivo/Domain/Identifiers.swift`
- Modify: `ios/Rentivo/Domain/Models.swift`
- Modify: `ios/Rentivo/Domain/BillingModels.swift`
- Modify: `ios/Rentivo/Domain/AccountModels.swift`
- Modify: `ios/Rentivo/Data/Repositories.swift`
- Modify: `ios/Rentivo/Data/MockFixtures.swift`
- Modify: `ios/Rentivo/Data/MockRentivoStore.swift`
- Create: `ios/RentivoTests/IdentifierMigrationTests.swift`
- Modify: all existing `ios/RentivoTests/*.swift` fixtures that pass UUID identifiers

**Interfaces:**
- Produces: `ResourceID<Tag>`, resource-specific type aliases, `FileUpload`, `DownloadedFile`, `CommunicationPreview`, `ExportRequest`, and expanded repository protocols
- Consumes: existing domain screens and mock graph
- Preserves: complete mock behavior and all existing test expectations after mechanical ID conversion

- [ ] **Step 1: Write failing identifier and protocol tests**

```swift
import Foundation
import Testing
@testable import RentivoCore

@Test func opaqueIdentifiersDoNotRequireUUIDParsing() {
  let billing = BillingID(rawValue: "01K0RENTIVO7QVK5R9H5G2Z0AB")
  let organization = OrganizationID(rawValue: "org_public_slug_like_value")
  #expect(billing.rawValue == "01K0RENTIVO7QVK5R9H5G2Z0AB")
  #expect(organization.rawValue == "org_public_slug_like_value")
}

@Test func fileUploadCarriesActualBytes() {
  let upload = FileUpload(
    data: Data([0x25, 0x50, 0x44, 0x46]),
    filename: "recibo.pdf",
    mediaType: "application/pdf"
  )
  #expect(upload.byteCount == 4)
}

@Test func personalAPIKeyGrantUsesLiteralPersonalWorkspace() {
  #expect(WorkspaceID.personal.rawValue == "personal")
}
```

- [ ] **Step 2: Run the new test and verify type failures**

Run: `swift test --package-path ios --filter IdentifierMigrationTests`

Expected: compile failure for missing `BillingID`, `OrganizationID`, `FileUpload`, and `WorkspaceID.personal`.

- [ ] **Step 3: Implement opaque identifiers and live file values**

```swift
public struct ResourceID<Tag>: RawRepresentable, Hashable, Codable, Sendable, Identifiable {
  public let rawValue: String
  public var id: String { rawValue }
  public init(rawValue: String) { self.rawValue = rawValue }
}

public enum BillingIDTag: Sendable {}
public typealias BillingID = ResourceID<BillingIDTag>
public enum BillIDTag: Sendable {}
public typealias BillID = ResourceID<BillIDTag>
public enum BillingItemIDTag: Sendable {}
public typealias BillingItemID = ResourceID<BillingItemIDTag>
public enum BillLineItemIDTag: Sendable {}
public typealias BillLineItemID = ResourceID<BillLineItemIDTag>
public enum ReceiptIDTag: Sendable {}
public typealias ReceiptID = ResourceID<ReceiptIDTag>
public enum ExpenseIDTag: Sendable {}
public typealias ExpenseID = ResourceID<ExpenseIDTag>
public enum AttachmentIDTag: Sendable {}
public typealias AttachmentID = ResourceID<AttachmentIDTag>
public enum OrganizationIDTag: Sendable {}
public typealias OrganizationID = ResourceID<OrganizationIDTag>
public enum InvitationIDTag: Sendable {}
public typealias InvitationID = ResourceID<InvitationIDTag>
public enum APIKeyIDTag: Sendable {}
public typealias APIKeyID = ResourceID<APIKeyIDTag>
public enum WorkspaceIDTag: Sendable {}
public typealias WorkspaceID = ResourceID<WorkspaceIDTag>

public extension ResourceID where Tag == WorkspaceIDTag {
  static let personal = Self(rawValue: "personal")
}

public struct FileUpload: Hashable, Sendable {
  public let data: Data
  public let filename: String
  public let mediaType: String
  public var byteCount: Int { data.count }
}

public struct DownloadedFile: Hashable, Sendable {
  public let fileURL: URL
  public let filename: String
  public let mediaType: String
}
```

Change `UserProfile.id` and `OrganizationMember.userID` to `Int`. Replace resource UUID fields and method parameters with their specific aliases. Remove `.owner` from `OrganizationRole`; update fixture owners to `.admin` and rely on server capabilities for owner-equivalent actions.

- [ ] **Step 4: Expand protocols with exact live operations**

```swift
@MainActor public protocol AuthRepository: AnyObject {
  func restoreSession() async throws -> UserProfile?
  func login(email: String, password: String) async throws -> AuthResult
  func signup(email: String, password: String) async throws -> AuthResult
  func verifyTOTP(challenge: MFAChallenge, code: String) async throws -> UserProfile
  func verifyRecoveryCode(challenge: MFAChallenge, code: String) async throws -> UserProfile
  func requestPasswordReset(email: String) async throws
  func resetPassword(token: String, newPassword: String) async throws
  func logout() async
}

@MainActor public protocol SecurityRepository: AnyObject {
  func securitySummary() async throws -> SecuritySummary
  func changePassword(current: String, new: String) async throws
  func beginTOTPSetup() async throws -> TOTPSetup
  func confirmTOTP(code: String) async throws -> [String]
  func disableTOTP(password: String, code: String) async throws
  func regenerateRecoveryCodes(password: String, code: String) async throws -> [String]
}

@MainActor public protocol AttachmentRepository: AnyObject {
  func listAttachments(billingID: BillingID) async throws -> [Attachment]
  func uploadAttachment(billingID: BillingID, file: FileUpload) async throws -> Attachment
  func downloadAttachment(billingID: BillingID, attachmentID: AttachmentID) async throws -> DownloadedFile
  func deleteAttachment(billingID: BillingID, attachmentID: AttachmentID) async throws
}
```

Apply the same specific-ID rule to every existing repository signature. Add `previewCommunication`, invoice/receipt/recibo downloads, receipt upload with `[FileUpload]`, bill regeneration, export creation, API-key options/get, and theme preview operations present in `frontend/openapi.json`.

- [ ] **Step 5: Migrate mock fixtures and make all core tests pass**

Convert each stable fixture with raw values, for example:

```swift
public static let billingAurora101 = BillingID(rawValue: "00000000-0000-0000-0000-000000000101")
public static let billDraft = BillID(rawValue: "00000000-0000-0000-0000-000000001001")
public static let organizationHorizonte = OrganizationID(rawValue: "00000000-0000-0000-0000-000000000010")
public static let userAna = 1
```

Implement newly required mock methods with deterministic bytes and values. The mock download helper writes to `FileManager.default.temporaryDirectory/appending(path: filename)` and returns `DownloadedFile`; tests delete these files in `defer` blocks.

Run: `swift test --package-path ios`

Expected: all existing and new tests pass; no `UUID` remains in public API resource fields except local `AppNotice` and `RecentActivity` IDs.

- [ ] **Step 6: Commit the domain correction**

```bash
git add ios/Rentivo/Domain ios/Rentivo/Data/Repositories.swift ios/Rentivo/Data/MockFixtures.swift ios/Rentivo/Data/MockRentivoStore.swift ios/RentivoTests
git commit -m "refactor(ios): align domain identifiers with API"
```

---

### Task 3: Build the secure transport, credentials, and error boundary

**Files:**
- Create: `ios/Rentivo/Data/API/APIConfiguration.swift`
- Create: `ios/Rentivo/Data/API/APIProblem.swift`
- Create: `ios/Rentivo/Data/API/CredentialStore.swift`
- Create: `ios/Rentivo/Data/API/KeychainCredentialStore.swift`
- Create: `ios/Rentivo/Data/API/BearerAuthMiddleware.swift`
- Create: `ios/Rentivo/Data/API/GeneratedClientFactory.swift`
- Create: `ios/RentivoTests/APIConfigurationTests.swift`
- Create: `ios/RentivoTests/APIProblemTests.swift`
- Create: `ios/RentivoTests/CredentialStoreTests.swift`
- Create: `ios/RentivoTests/BearerAuthMiddlewareTests.swift`

**Interfaces:**
- Produces: `APIConfiguration.production`, `CredentialStore`, `KeychainCredentialStore`, `MemoryCredentialStore`, `SessionExpiryBus`, `BearerAuthMiddleware`, `APIProblem`, and `GeneratedClientFactory`
- Consumes: `OpenAPIRuntime.ClientMiddleware` and `OpenAPIURLSession.URLSessionTransport`

- [ ] **Step 1: Write failing configuration and credential tests**

```swift
@Test func productionURLIsRentivoOriginWithoutExtraPrefix() {
  #expect(APIConfiguration.production.serverURL.absoluteString == "https://rentivo.com.br")
}

@Test func memoryCredentialStoreRoundTripsAndDeletes() async throws {
  let store = MemoryCredentialStore()
  #expect(try await store.readAccessToken() == nil)
  try await store.saveAccessToken("secret-token")
  #expect(try await store.readAccessToken() == "secret-token")
  try await store.deleteAccessToken()
  #expect(try await store.readAccessToken() == nil)
}
```

- [ ] **Step 2: Verify the boundary types are missing**

Run: `swift test --package-path ios --filter APIConfigurationTests --filter CredentialStoreTests`

Expected: compile failure for `APIConfiguration` and `MemoryCredentialStore`.

- [ ] **Step 3: Implement fixed configuration and credential abstraction**

```swift
public struct APIConfiguration: Equatable, Sendable {
  public let serverURL: URL
  public static let production = APIConfiguration(
    serverURL: URL(string: "https://rentivo.com.br")!
  )

  public static func current(environment: [String: String] = ProcessInfo.processInfo.environment) -> Self {
    #if DEBUG
      if let value = environment["RENTIVO_API_BASE_URL"],
         let url = URL(string: value),
         url.scheme == "https" || ["localhost", "127.0.0.1"].contains(url.host) {
        return Self(serverURL: url)
      }
    #endif
    return .production
  }
}

public protocol CredentialStore: Sendable {
  func readAccessToken() async throws -> String?
  func saveAccessToken(_ token: String) async throws
  func deleteAccessToken() async throws
}

public actor MemoryCredentialStore: CredentialStore {
  private var token: String?
  public init(token: String? = nil) { self.token = token }
  public func readAccessToken() -> String? { token }
  public func saveAccessToken(_ token: String) { self.token = token }
  public func deleteAccessToken() { token = nil }
}
```

Implement Keychain with `kSecClassGenericPassword`, service equal to bundle identifier fallback `app.rentivo.demo`, account `rentivo.access-token`, `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, update-then-add behavior, and idempotent deletion. Translate non-success OSStatus into `CredentialStoreError.keychain(status:)` without including token data.

- [ ] **Step 4: Write and satisfy middleware/error tests**

Tests construct `HTTPRequest(path: "/api/v1/profile", method: .get)` and a recording `next` closure. Assert the middleware adds `Bearer abc`, omits auth with no token, refuses a request whose URL host differs from the configured host, and deletes credentials/emits exactly one expiry event after a `401` response.

Implement the problem value:

```swift
public struct APIProblem: Error, Equatable, LocalizedError, Sendable {
  public let status: Int?
  public let code: String?
  public let title: String
  public let detail: String
  public let fields: [String: [String]]
  public let requestID: String?
  public var errorDescription: String? { detail }
}
```

Decode `application/problem+json` keys `status`, `code`, `title`, `detail`, `fields`, and `request_id`. Map `URLError.notConnectedToInternet` to `Sem conexão com a internet.`, cancellation to `CancellationError`, `401` to `E-mail ou senha inválidos.` only for login and otherwise `Sua sessão expirou. Entre novamente.`, and preserve all server field messages.

Run: `swift test --package-path ios --filter APIProblemTests --filter BearerAuthMiddlewareTests`

Expected: all boundary tests pass and recorded headers never appear in failure messages.

- [ ] **Step 5: Construct public and authenticated generated clients**

```swift
public struct GeneratedClientFactory: Sendable {
  public let publicClient: Client
  public let authenticatedClient: Client

  public init(
    configuration: APIConfiguration,
    credentials: any CredentialStore,
    expiryBus: SessionExpiryBus,
    session: URLSession = .shared
  ) {
    let transport = URLSessionTransport(configuration: .init(session: session))
    publicClient = Client(serverURL: configuration.serverURL, transport: transport)
    authenticatedClient = Client(
      serverURL: configuration.serverURL,
      transport: transport,
      middlewares: [BearerAuthMiddleware(
        serverURL: configuration.serverURL,
        credentials: credentials,
        expiryBus: expiryBus
      )]
    )
  }
}
```

Run: `swift test --package-path ios`

Expected: all core tests pass.

- [ ] **Step 6: Commit the API boundary**

```bash
git add ios/Rentivo/Data/API ios/RentivoTests/APIConfigurationTests.swift ios/RentivoTests/APIProblemTests.swift ios/RentivoTests/CredentialStoreTests.swift ios/RentivoTests/BearerAuthMiddlewareTests.swift
git commit -m "feat(ios): add secure API transport boundary"
```

---

### Task 4: Implement authentication, session restoration, TOTP, and recovery login

**Files:**
- Create: `ios/Rentivo/Data/API/Mappers/AuthMapper.swift`
- Create: `ios/Rentivo/Data/API/APIRentivoStore.swift`
- Modify: `ios/Rentivo/App/AppModel.swift`
- Modify: `ios/Rentivo/Features/Auth/AuthViews.swift`
- Create: `ios/RentivoTests/AuthMapperTests.swift`
- Create: `ios/RentivoTests/AuthStateTests.swift`

**Interfaces:**
- Produces: `AuthResult`, `MFAChallenge`, auth mapper functions, `APIRentivoStore` auth conformance, and the five-state `AppModel.Session`
- Consumes: public/authenticated generated clients, credentials, expiry bus

- [ ] **Step 1: Write failing auth-state tests with a fake repository**

```swift
@Test @MainActor func loginChallengeMovesToMFAWithoutPersistingPassword() async {
  let challenge = MFAChallenge(id: "challenge-1", token: "challenge-token", methods: [.totp, .recoveryCode])
  let auth = FakeAuthRepository(loginResult: .mfaRequired(challenge))
  let model = AppModel(dependencies: .test(auth: auth))

  await model.login(email: "ana@example.com", password: "senha-correta")

  #expect(model.session == .mfaRequired(challenge))
  #expect(auth.lastPassword == nil)
}

@Test @MainActor func failedRestoreReturnsToAnonymous() async {
  let auth = FakeAuthRepository(restoreError: APIProblem.sessionExpired)
  let model = AppModel(dependencies: .test(auth: auth))
  await model.restoreSession()
  #expect(model.session == .anonymous)
}
```

The fake captures a password only during the awaited call and clears it in `defer`, making the second assertion meaningful.

- [ ] **Step 2: Verify authentication tests fail**

Run: `swift test --package-path ios --filter AuthStateTests`

Expected: compile failure because the new session cases and async methods do not exist.

- [ ] **Step 3: Implement auth wire mapping and token persistence**

```swift
public enum MFAMethod: String, Hashable, Sendable {
  case totp
  case recoveryCode = "recovery_code"
}

public struct MFAChallenge: Equatable, Sendable {
  public let id: String
  public let token: String
  public let methods: Set<MFAMethod>
}

public enum AuthResult: Equatable, Sendable {
  case authenticated(UserProfile)
  case mfaRequired(MFAChallenge)
}
```

`APIRentivoStore.login` calls `login_api_v1_auth_login_post` with email, password, and body credential transport. `signup` does the same through the signup operation. For an authenticated body, save `access_token` before returning `.authenticated(AuthMapper.profile(bootstrap.user))`. For an MFA body, return `.mfaRequired` without saving a token. TOTP and recovery verification send challenge ID, challenge token, code, and body transport; both persist the resulting access token. Password recovery calls `password_forgot_api_v1_auth_password_forgot_post`; reset calls `password_reset_api_v1_auth_password_reset_post` with the token and confirmed new password and never creates an authenticated session implicitly.

`restoreSession` returns nil immediately when Keychain has no token; otherwise it calls the authenticated session operation. Any `401` deletes the token and returns nil. `logout` attempts the server operation and always deletes local credentials in `defer`.

- [ ] **Step 4: Implement the app session state machine**

```swift
enum Session: Equatable {
  case restoring
  case anonymous
  case submitting
  case mfaRequired(MFAChallenge)
  case authenticated(UserProfile)
}

func login(email: String, password: String) async {
  session = .submitting
  do {
    switch try await dependencies.auth.login(email: email, password: password) {
    case .authenticated(let profile): completeAuthentication(profile)
    case .mfaRequired(let challenge): session = .mfaRequired(challenge)
    }
  } catch is CancellationError {
    session = .anonymous
  } catch {
    session = .anonymous
    authError = APIProblem.userMessage(for: error)
  }
}
```

Add equivalent `signup`, `verifyTOTP`, `verifyRecoveryCode`, `requestPasswordReset`, `resetPassword`, `restoreSession`, and `logout`. Consume `SessionExpiryBus.events` in one task owned by AppModel; on expiry set anonymous and show `Sua sessão expirou. Entre novamente.`.

- [ ] **Step 5: Replace simulated authentication UI**

Remove `AuthRoute.passkey` and `PasskeyLoginView`. Login and signup call async AppModel methods; button labels become `Entrar` and `Criar conta`. Disable controls while `.submitting`. MFA shows a segmented choice only for methods present in the challenge, uses `.oneTimeCode` for six-digit TOTP, and a secure text field for a recovery code. Forgot password calls the repository and always displays `Se houver uma conta para este e-mail, enviaremos as instruções.`. The confirmation screen offers `Já tenho um token`; its reset form collects the token, new password, and confirmation, calls `resetPassword`, clears all three fields, and returns to login with `Senha redefinida. Entre com a nova senha.`. This manual-token path exercises the reset endpoint without universal-link or associated-domain provisioning.

Add accessibility IDs:

```swift
"login.email"
"login.password"
"login.submit"
"login.error"
"mfa.method.totp"
"mfa.method.recovery"
"mfa.code"
"mfa.submit"
```

- [ ] **Step 6: Run auth and regression tests**

Run: `swift test --package-path ios --filter AuthMapperTests --filter AuthStateTests`

Expected: auth mapper and state tests pass for authenticated, MFA, invalid session, logout failure/local deletion, TOTP, and recovery code.

Run: `swift test --package-path ios`

Expected: all core tests pass.

- [ ] **Step 7: Commit the authentication slice**

```bash
git add ios/Rentivo/Data/API/APIRentivoStore.swift ios/Rentivo/Data/API/Mappers/AuthMapper.swift ios/Rentivo/App/AppModel.swift ios/Rentivo/Features/Auth/AuthViews.swift ios/RentivoTests/AuthMapperTests.swift ios/RentivoTests/AuthStateTests.swift
git commit -m "feat(ios): authenticate with email and MFA"
```

---

### Task 5: Wire profile, password, TOTP enrollment, recovery codes, and dashboard

**Files:**
- Create: `ios/Rentivo/Data/API/Mappers/AccountMapper.swift`
- Create: `ios/Rentivo/Data/API/SessionActivityRepository.swift`
- Modify: `ios/Rentivo/Data/API/APIRentivoStore.swift`
- Modify: `ios/Rentivo/Features/Account/AccountView.swift`
- Modify: `ios/Rentivo/Features/Account/SecurityViews.swift`
- Modify: `ios/Rentivo/Features/Home/HomeView.swift`
- Create: `ios/RentivoTests/ProfileSecurityRepositoryTests.swift`
- Modify: `ios/RentivoTests/DashboardTests.swift`

**Interfaces:**
- Produces: live `ProfileRepository`, `SecurityRepository`, `DashboardRepository`, and `ActivityRepository` behavior
- Consumes: generated profile/security/billing operations and current domain models

- [ ] **Step 1: Write failing repository tests**

Use a scripted test transport with response fixtures. Assert:

```swift
@Test @MainActor func confirmingTOTPReturnsOneTimeRecoveryCodes() async throws {
  let harness = APIHarness.responding(
    operation: "confirm_totp_api_v1_security_totp_confirm_post",
    status: 200,
    json: #"{"recovery_codes":["AAAA-BBBB","CCCC-DDDD"]}"#
  )
  let codes = try await harness.store.confirmTOTP(code: "123456")
  #expect(codes == ["AAAA-BBBB", "CCCC-DDDD"])
  #expect(harness.requests.last?.bodyString.contains("123456") == true)
}
```

Also test PIX mapping, password-change validation error mapping, TOTP setup secret/URI, TOTP disable, recovery regeneration, and dashboard totals from two billings.

- [ ] **Step 2: Verify the live security tests fail**

Run: `swift test --package-path ios --filter ProfileSecurityRepositoryTests`

Expected: failure because APIRentivoStore does not yet conform to profile/security protocols.

- [ ] **Step 3: Implement account/security operations**

Map the exact operations:

```text
current_profile_api_v1_profile_get
update_pix_api_v1_security_pix_post
security_summary_api_v1_security_get
change_password_api_v1_security_change_password_post
setup_totp_api_v1_security_totp_setup_post
confirm_totp_api_v1_security_totp_confirm_post
disable_totp_api_v1_security_totp_disable_post
regenerate_recovery_codes_api_v1_security_recovery_codes_regenerate_post
```

Every password/code value exists only in the generated input local and is never captured by activity records. Successful PIX/password/TOTP mutations append a metadata-only session activity.

- [ ] **Step 4: Implement real security UI**

Remove passkey list/registration/rename/delete controls. Add:

- Current/new/confirmation password form.
- TOTP setup sheet that displays issuer/account, manual secret, and the `otpauth` URI as a copyable value. Render the URI with Core Image's `CIQRCodeGenerator`, scale with nearest-neighbor interpolation, and label the image `Código QR para configurar o autenticador`.
- Six-digit confirmation field.
- One-time recovery-code sheet with copy/share and an acknowledgement checkbox before dismissal.
- Disable and regenerate forms that collect the exact password/code fields required by the schema.

Clear all secret/code/password `@State` values in `onDisappear` and after success.

- [ ] **Step 5: Derive dashboard and hide empty activity**

`dashboardSummary()` loads billings, then concurrently loads allowed bills and expenses per billing with `withThrowingTaskGroup`. Sum paid bills, overdue open bills, upcoming open bills, and expenses using `Money`; compute collection percent only when collectible total is positive. Permission-denied subresources contribute zero rather than failing the entire dashboard; transport/server errors still fail it.

`SessionActivityRepository` begins with `[]`, prepends successful live mutations, and caps the array at 50. Update HomeView so the recent-activity card is absent when empty.

- [ ] **Step 6: Run focused and full tests**

Run: `swift test --package-path ios --filter ProfileSecurityRepositoryTests --filter DashboardTests`

Expected: all profile/security/dashboard tests pass with exact centavo totals.

Run: `swift test --package-path ios`

Expected: all core tests pass.

- [ ] **Step 7: Commit account/security/dashboard**

```bash
git add ios/Rentivo/Data/API/APIRentivoStore.swift ios/Rentivo/Data/API/Mappers/AccountMapper.swift ios/Rentivo/Data/API/SessionActivityRepository.swift ios/Rentivo/Features/Account ios/Rentivo/Features/Home/HomeView.swift ios/RentivoTests/ProfileSecurityRepositoryTests.swift ios/RentivoTests/DashboardTests.swift
git commit -m "feat(ios): connect account security and dashboard"
```

---

### Task 6: Wire billing templates and ownership

**Files:**
- Create: `ios/Rentivo/Data/API/Mappers/BillingMapper.swift`
- Modify: `ios/Rentivo/Data/API/APIRentivoStore.swift`
- Modify: `ios/Rentivo/Features/Billings/BillingListView.swift`
- Modify: `ios/Rentivo/Features/Billings/BillingFormView.swift`
- Modify: `ios/Rentivo/Features/Billings/BillingDetailView.swift`
- Create: `ios/RentivoTests/BillingRepositoryTests.swift`

**Interfaces:**
- Produces: live `BillingRepository` mappings for list/get/create/update/delete/transfer, recipients, and reply-to
- Consumes: opaque identifiers, capabilities, PIX, organizations, and generated billing operations

- [ ] **Step 1: Write failing billing mapper/repository tests**

Fixtures must cover personal owner, organization owner, fixed/variable items, inherited/override PIX, recipient list, reply-to, and viewer capabilities. Assert an opaque ID is preserved:

```swift
#expect(billing.id == BillingID(rawValue: "01K0BILLING7QVK5R9H5G2Z0AB"))
#expect(billing.owner == .organization(
  id: OrganizationID(rawValue: "01K0ORG7QVK5R9H5G2Z0ABCDE"),
  name: "Imobiliária Horizonte"
))
```

Test that a `422` response exposes `name` and `items` field messages and that delete accepts the contract's success/no-content case.

- [ ] **Step 2: Verify billing tests fail**

Run: `swift test --package-path ios --filter BillingRepositoryTests`

Expected: failures for unimplemented live billing operations.

- [ ] **Step 3: Map every billing operation**

Implement these generated calls with complete success/output switches:

```text
list_billings_api_v1_billings_get
get_billing_api_v1_billings__billing_uuid__get
create_billing_api_v1_billings_post
update_billing_api_v1_billings__billing_uuid__patch
delete_billing_api_v1_billings__billing_uuid__delete
replace_recipients_api_v1_billings__billing_uuid__recipients_put
replace_reply_to_api_v1_billings__billing_uuid__reply_to_put
transfer_billing_api_v1_billings__billing_uuid__transfer_post
```

Creation/update maps centavos directly, sends API role/owner vocabulary exactly, and uses `.rawValue` for path parameters. After create/update, replace recipients and reply-to only when the primary operation does not already accept them; return the final GET result so UI state reflects server capabilities.

- [ ] **Step 4: Make billing views server-authoritative**

Keep optimistic form editing local, but after save replace local state with the returned server resource. Disable edit/delete/transfer buttons from returned capabilities. Present field errors beside name/items/recipient/reply-to controls. Remove any mutation that assumes synchronous mock success.

- [ ] **Step 5: Run billing and regression tests**

Run: `swift test --package-path ios --filter BillingRepositoryTests`

Expected: all billing mapping, error, and capability tests pass.

Run: `swift test --package-path ios`

Expected: all core tests pass.

- [ ] **Step 6: Commit billing templates**

```bash
git add ios/Rentivo/Data/API/Mappers/BillingMapper.swift ios/Rentivo/Data/API/APIRentivoStore.swift ios/Rentivo/Features/Billings ios/RentivoTests/BillingRepositoryTests.swift
git commit -m "feat(ios): connect billing templates to API"
```

---

### Task 7: Wire bills, lifecycle, expenses, communications, exports, and files

**Files:**
- Create: `ios/Rentivo/Data/API/FileTransfer.swift`
- Modify: `ios/Rentivo/Data/API/Mappers/BillingMapper.swift`
- Modify: `ios/Rentivo/Data/API/APIRentivoStore.swift`
- Modify: `ios/Rentivo/Features/Bills/BillViews.swift`
- Modify: `ios/Rentivo/Features/Bills/BillingOperationsViews.swift`
- Create: `ios/RentivoTests/BillOperationsRepositoryTests.swift`
- Create: `ios/RentivoTests/FileTransferTests.swift`

**Interfaces:**
- Produces: live bill/expense/attachment/communication/export repositories and temporary-file handling
- Consumes: generated JSON, multipart, and binary-body operations

- [ ] **Step 1: Write failing operation/file tests**

Cover list/create/update/delete bill, every legal transition, server-rejected transition, regeneration, expense lifecycle, attachment upload/download/delete, multi-receipt upload/reorder/download/delete, invoice/recibo download, communication preview/send, and export response.

Use real byte assertions:

```swift
@Test @MainActor func downloadedReceiptWritesExactBytesToTemporaryFile() async throws {
  let expected = Data([0x25, 0x50, 0x44, 0x46, 0x2D])
  let harness = APIHarness.binary(status: 200, mediaType: "application/pdf", bytes: expected)
  let file = try await harness.store.downloadReceipt(
    billingID: BillingID(rawValue: "billing-1"),
    billID: BillID(rawValue: "bill-1"),
    receiptID: ReceiptID(rawValue: "receipt-1")
  )
  defer { try? FileManager.default.removeItem(at: file.fileURL) }
  #expect(try Data(contentsOf: file.fileURL) == expected)
  #expect(file.mediaType == "application/pdf")
}
```

- [ ] **Step 2: Verify focused tests fail**

Run: `swift test --package-path ios --filter BillOperationsRepositoryTests --filter FileTransferTests`

Expected: failures for unimplemented operation and file methods.

- [ ] **Step 3: Implement bill and expense operations**

Map list/get/create/update/delete, transitions, and regenerate. Do not pre-validate transitions as authoritative; keep local validation for UX, send the operation, and show a normalized conflict/validation response if server state changed. Map expense list/create/delete with integer centavos and API date strings.

- [ ] **Step 4: Implement multipart upload and safe binary download**

`FileTransfer.write` creates a unique directory beneath `FileManager.default.temporaryDirectory/app.rentivo.demo-downloads`, sanitizes suggested names with `URL(fileURLWithPath:).lastPathComponent`, writes atomically, and returns `DownloadedFile`. Reject empty filenames and responses larger than 50 MiB with `APIProblem` code `file_too_large`.

Build generated multipart values from each `FileUpload` byte stream, filename, and media type. Never pass only a displayed filename. Reorder receipts using `[ReceiptID.rawValue]` in the exact requested order.

- [ ] **Step 5: Implement communications and exports**

Call preview before showing the final composer preview and send only after explicit confirmation. Activity records store recipient count and billing/bill identifiers, never message contents. Export sends `ExportCreateRequest(format: .csv | .xlsx)`, accepts only the generated `202` case, and maps `ExportCreateResponse(format:, status: "queued")` to `ExportSubmission`. Because the contract exposes no export download/poll endpoint, show `Exportação CSV enfileirada.` or `Exportação XLSX enfileirada.` and do not manufacture a file or download URL.

- [ ] **Step 6: Add native file presentation**

Use `.fileImporter` for attachments and receipts. Read security-scoped URLs within `startAccessingSecurityScopedResource`/`defer stopAccessing...`, determine MIME with `UTType`, and create `FileUpload`. Use Quick Look for local previews and `ShareLink(item:)` for downloads. Delete temporary files in presentation dismissal handlers.

- [ ] **Step 7: Run focused/full tests and parser**

Run: `swift test --package-path ios --filter BillOperationsRepositoryTests --filter FileTransferTests`

Expected: all operation and byte-level file tests pass.

Run: `swift test --package-path ios && find ios/Rentivo -name '*.swift' -print0 | xargs -0 swiftc -parse`

Expected: all tests pass and all Swift sources parse.

- [ ] **Step 8: Commit billing operations**

```bash
git add ios/Rentivo/Data/API/FileTransfer.swift ios/Rentivo/Data/API/Mappers/BillingMapper.swift ios/Rentivo/Data/API/APIRentivoStore.swift ios/Rentivo/Features/Bills ios/RentivoTests/BillOperationsRepositoryTests.swift ios/RentivoTests/FileTransferTests.swift
git commit -m "feat(ios): connect bills files and operations"
```

---

### Task 8: Wire organizations, members, invitations, MFA policy, and transfers

**Files:**
- Create: `ios/Rentivo/Data/API/Mappers/OrganizationMapper.swift`
- Modify: `ios/Rentivo/Data/API/APIRentivoStore.swift`
- Modify: `ios/Rentivo/Features/Organizations/OrganizationViews.swift`
- Modify: `ios/Rentivo/Features/Organizations/InvitationViews.swift`
- Create: `ios/RentivoTests/OrganizationRepositoryTests.swift`

**Interfaces:**
- Produces: live organization and invitation repositories
- Consumes: integer member IDs, opaque organization/invitation IDs, API role values, and server capabilities

- [ ] **Step 1: Write failing organization tests**

Test organization list/get/create/update/delete, admin/manager/viewer roles, member role change with integer `user_id`, member removal, invite, MFA policy, pending invites, accept/decline, transfer to organization, and transfer to personal.

```swift
#expect(organization.members.first?.userID == 42)
#expect(organization.members.first?.role == .admin)
#expect(organization.capabilities.canManage)
```

- [ ] **Step 2: Verify tests fail**

Run: `swift test --package-path ios --filter OrganizationRepositoryTests`

Expected: failures for missing mapper/live operations.

- [ ] **Step 3: Implement organization and invitation operation mappings**

Map the exact `/api/v1/organizations`, member, invite, MFA-policy, billing-transfer, and `/api/v1/invites` operations. Send integer user IDs untouched. Never manufacture `.owner`; map only admin/manager/viewer. Let capability fields govern actions.

- [ ] **Step 4: Correct organization UI assumptions**

Remove owner from role pickers. Display ownership wording from capability/owner metadata returned by the API. Disable management controls when capabilities deny them. Refresh organization and billing views after a transfer; refresh pending invites after accept/decline.

- [ ] **Step 5: Run focused and full tests**

Run: `swift test --package-path ios --filter OrganizationRepositoryTests && swift test --package-path ios`

Expected: all organization and core tests pass.

- [ ] **Step 6: Commit organizations**

```bash
git add ios/Rentivo/Data/API/Mappers/OrganizationMapper.swift ios/Rentivo/Data/API/APIRentivoStore.swift ios/Rentivo/Features/Organizations ios/RentivoTests/OrganizationRepositoryTests.swift
git commit -m "feat(ios): connect organizations and invitations"
```

---

### Task 9: Wire API keys and themes

**Files:**
- Modify: `ios/Rentivo/Data/API/Mappers/AccountMapper.swift`
- Modify: `ios/Rentivo/Data/API/APIRentivoStore.swift`
- Modify: `ios/Rentivo/Features/Account/APIKeyViews.swift`
- Modify: `ios/Rentivo/Features/Account/ThemeViews.swift`
- Create: `ios/RentivoTests/AccountRepositoryTests.swift`

**Interfaces:**
- Produces: live API-key options/list/get/create/update/revoke and user/org/billing theme get/update/reset/preview
- Consumes: `WorkspaceID.personal`, opaque org grants, one-time API-key secrets, and theme inheritance values

- [ ] **Step 1: Write failing account repository tests**

Assert personal and organization grant mapping, scope round-trip, expiration, one-time secret separation, idempotent revoke success, user/org/billing theme targets, inheritance source, and preview without persistence.

```swift
#expect(created.secret == "rentivo_live_once_only")
#expect(created.metadata.hint == "...only")
#expect(created.metadata.grants.first?.resourceID == .personal)
```

- [ ] **Step 2: Verify account tests fail**

Run: `swift test --package-path ios --filter AccountRepositoryTests`

Expected: failures for unimplemented API-key/theme operations.

- [ ] **Step 3: Implement API-key operations and secret hygiene**

Call options before rendering the creation form. Map all server-returned scopes/grants; preserve unknown scopes as unavailable display strings instead of crashing. Return the creation secret only through `CreatedAPIKeySecret`, never add it to metadata or activity. Clear secret view state on dismissal/background and do not write to pasteboard automatically.

- [ ] **Step 4: Implement theme target dispatch**

Switch `ThemeTarget` once inside APIRentivoStore to dispatch user, organization, or billing get/update/reset. Preview calls the preview endpoint with unsaved values. Map stored/effective/source/can-edit/can-reset exactly and refresh the screen with the returned record after mutation.

- [ ] **Step 5: Run focused/full tests**

Run: `swift test --package-path ios --filter AccountRepositoryTests && swift test --package-path ios`

Expected: all account and core tests pass.

- [ ] **Step 6: Commit keys and themes**

```bash
git add ios/Rentivo/Data/API/Mappers/AccountMapper.swift ios/Rentivo/Data/API/APIRentivoStore.swift ios/Rentivo/Features/Account/APIKeyViews.swift ios/Rentivo/Features/Account/ThemeViews.swift ios/RentivoTests/AccountRepositoryTests.swift
git commit -m "feat(ios): connect API keys and themes"
```

---

### Task 10: Select live dependencies safely and preserve deterministic mock mode

**Files:**
- Modify: `ios/Rentivo/Data/Repositories.swift`
- Modify: `ios/Rentivo/App/RentivoApp.swift`
- Modify: `ios/Rentivo/App/RootView.swift`
- Modify: `ios/Rentivo/Features/Demo/DemoScenariosView.swift`
- Create: `ios/RentivoTests/LiveDependencyTests.swift`
- Modify: `ios/RentivoUITests/RentivoUITests.swift`

**Interfaces:**
- Produces: `AppDependencies.live(configuration:credentials:)`, `AppDependencies.forLaunch(arguments:)`, and a launch-safe restoring shell
- Consumes: shared APIRentivoStore, MockRentivoStore, and launch arguments

- [ ] **Step 1: Write failing dependency-selection tests**

```swift
@Test @MainActor func normalLaunchSelectsLiveDependencies() {
  #expect(AppDependencies.mode(for: []) == .live)
}

@Test @MainActor func UIAndScreenshotLaunchesSelectMockDependencies() {
  #expect(AppDependencies.mode(for: ["--ui-testing"]) == .mock)
  #expect(AppDependencies.mode(for: ["--screenshot-authenticated"]) == .mock)
}
```

- [ ] **Step 2: Verify selection tests fail**

Run: `swift test --package-path ios --filter LiveDependencyTests`

Expected: compile failure for missing dependency mode/factory.

- [ ] **Step 3: Construct one shared live store**

```swift
public static func live(
  configuration: APIConfiguration = .current(),
  credentials: any CredentialStore = KeychainCredentialStore()
) -> AppDependencies {
  let expiryBus = SessionExpiryBus()
  let factory = GeneratedClientFactory(
    configuration: configuration,
    credentials: credentials,
    expiryBus: expiryBus
  )
  let store = APIRentivoStore(
    publicClient: factory.publicClient,
    authenticatedClient: factory.authenticatedClient,
    credentials: credentials,
    expiryBus: expiryBus
  )
  return AppDependencies(
    auth: store, profile: store, billings: store, bills: store,
    expenses: store, attachments: store, communications: store,
    exports: store, dashboard: store, activities: store,
    organizations: store, invitations: store, security: store,
    apiKeys: store, themes: store, demo: DisabledDemoRepository()
  )
}
```

`forLaunch(arguments:)` returns mock if arguments include `--ui-testing` or any `--screenshot-` prefix; otherwise live.

- [ ] **Step 4: Update app launch and restoring shell**

Construct dependencies before AppModel. On first task, call `await app.restoreSession()`. RootView shows a branded `ProgressView("Restaurando sessão…")` for `.restoring` and `.submitting`, AuthenticationView for anonymous/MFA, and the tab shell for authenticated.

Compile DemoScenarios controls only in `#if DEBUG`; hide the row when `dependencies.mode == .live`.

- [ ] **Step 5: Make every UI test explicitly mock-only**

At UI-test setup:

```swift
app = XCUIApplication()
app.launchArguments = ["--ui-testing"]
app.launch()
```

Add one test that asserts passkey and Google buttons do not exist, and a mock MFA test using deterministic fixture credentials. Preserve existing navigation/screenshot tests.

- [ ] **Step 6: Run core and simulator tests**

Run: `swift test --package-path ios --filter LiveDependencyTests && swift test --package-path ios`

Expected: all core tests pass.

Run: `xcodebuild test -project ios/Rentivo.xcodeproj -scheme Rentivo -destination 'platform=iOS Simulator,name=iPhone 17 Pro'`

Expected: application unit tests and UI tests pass with no requests to `rentivo.com.br` in test logs.

- [ ] **Step 7: Commit dependency selection**

```bash
git add ios/Rentivo/Data/Repositories.swift ios/Rentivo/App ios/Rentivo/Features/Demo/DemoScenariosView.swift ios/RentivoTests/LiveDependencyTests.swift ios/RentivoUITests/RentivoUITests.swift
git commit -m "feat(ios): enable live app dependencies"
```

---

### Task 11: Document, verify, smoke-test, and prepare the PR

**Files:**
- Create: `ios/README.md`
- Modify: `Makefile`
- Modify: `.github/workflows/test-pr.yaml`

**Interfaces:**
- Produces: reproducible developer setup, contract check, full local verification, and human-merge PR handoff
- Consumes: all previous tasks

- [ ] **Step 1: Document local and production-safe workflows**

`ios/README.md` must include these commands verbatim:

```sh
make ios-openapi-sync
make ios-openapi-check
swift test --package-path ios
xcodebuild test -project ios/Rentivo.xcodeproj -scheme Rentivo -destination 'platform=iOS Simulator,name=iPhone 17 Pro'
```

Document default production origin, debug-only `RENTIVO_API_BASE_URL`, Keychain token behavior, mock launch arguments, email/password + TOTP/recovery scope, passkey/Google exclusions, and manual credential handling. Explicitly prohibit committing scheme credentials.

- [ ] **Step 2: Add one aggregate iOS verification target**

```make
.PHONY: ios-check
ios-check: ios-openapi-check
	swift test --package-path ios
	xcodebuild test -project ios/Rentivo.xcodeproj -scheme Rentivo -destination 'platform=iOS Simulator,name=iPhone 17 Pro'
```

In the existing `frontend` job, add this step immediately after `Verify generated API contract is current`:

```yaml
      - name: Verify iOS OpenAPI copy is current
        working-directory: .
        run: make ios-openapi-check
```

This Linux-safe comparison enforces contract drift in CI. Do not add Xcode execution to the Ubuntu workflow and do not alter action references; the known mutable-tag mismatch belongs to PR #151 follow-up work.

- [ ] **Step 3: Run contract and static secret scans**

Run: `make ios-openapi-check`

Expected: exit 0.

Run: `rg -n 'Bearer [A-Za-z0-9._-]+|rentivo_live_|password\s*=\s*"[^"\\]*"|recovery_codes\s*=' ios --glob '!openapi.json'`

Expected: no committed credential, bearer, API-key secret, password fixture, or recovery-code assignment outside explicitly synthetic test values.

- [ ] **Step 4: Run complete iOS verification**

Run: `swift test --package-path ios`

Expected: all core tests pass.

Run: `xcodebuild clean test -project ios/Rentivo.xcodeproj -scheme Rentivo -destination 'platform=iOS Simulator,name=iPhone 17 Pro'`

Expected: clean build, unit tests, and UI tests pass.

Run: `xcodebuild build -project ios/Rentivo.xcodeproj -scheme Rentivo -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO`

Expected: unsigned generic-device build succeeds.

- [ ] **Step 5: Run the backend baseline and record the upstream failures without changing them**

Run: `make test`

Expected on the current `origin/main` baseline: 2,612 passed, 3 skipped, and the same 5 `backend/tests/test_preview_infrastructure.py` failures caused by mutable action tags from PR #151. If the baseline has been repaired upstream by execution time, expect all backend tests to pass. Any new or different failure blocks completion.

- [ ] **Step 6: Perform a reversible manual live smoke test**

In Xcode, launch without `--ui-testing` or screenshot arguments. Use a developer-provided account typed into the simulator. Verify:

1. Login reaches authenticated tabs.
2. Force-quit/relaunch restores session from Keychain.
3. Profile and billing lists load from `https://rentivo.com.br`.
4. If the account requires MFA, TOTP or a recovery code completes login.
5. Logout returns to login and the next relaunch does not restore the session.

Do not create/delete production billings, organizations, API keys, or files during this smoke test.

- [ ] **Step 7: Commit documentation and verification wiring**

```bash
git add ios/README.md Makefile .github/workflows/test-pr.yaml
git commit -m "docs(ios): document live API workflows"
```

- [ ] **Step 8: Review the final branch and open a PR without merging**

Run: `git status --short && git diff --check && git log --oneline origin/main..HEAD`

Expected: clean worktree, no whitespace errors, and conventional commits for every task.

Run: `git push -u origin codex/ios-api-integration-plan`

After implementation work is committed on its implementation branch, open a PR with every repository template section completed. Include the iOS verification results and separately disclose the unchanged PR #151 backend baseline failures. Leave the PR open for human review; never merge or enable auto-merge.

---

## Operation Coverage Audit

Before marking implementation complete, use this checklist against generated client calls:

- [ ] Auth: login, signup, session, logout, forgot password, password reset, TOTP verify, recovery verify.
- [ ] Profile/security: profile, PIX, password change, security summary, TOTP setup/confirm/disable, recovery regeneration.
- [ ] Billings: list/get/create/update/delete, recipients, reply-to, transfer.
- [ ] Bills: list/get/create/update/delete, transition, regenerate, invoice, receipts, receipt order, recibo/content/download.
- [ ] Billing operations: expenses, attachments, communication preview/send, exports.
- [ ] Organizations: CRUD, member role/remove, invites, MFA policy, transfers.
- [ ] Invitations: pending, accept, decline.
- [ ] API keys: options, list/get/create/update/revoke.
- [ ] Themes: user/org/billing get/update/reset and preview.
- [ ] Explicit exclusions remain unreachable: Google routes and all passkey routes.
