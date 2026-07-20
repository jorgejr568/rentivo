# Rentivo Native iOS Demonstration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, demonstrable, iPhone-first Rentivo SwiftUI app backed only by coherent mutable mock data and prepared for later PR #138 API integration.

**Architecture:** A Swift package continuously compiles and tests Foundation-only domain, repository, fixture, and store code. The iOS application target compiles those same sources with feature-specific SwiftUI views, an observable application model, native navigation, and a reusable Rentivo design system. Focused repository protocols preserve the later HTTP boundary.

**Tech Stack:** Swift 6, SwiftUI, Observation, Foundation, Swift Testing/XCTest, Swift Package Manager, Xcode project format, iOS 17.0+

## Global Constraints

- The app is iPhone-first with an iOS 17.0 minimum deployment target.
- All user-facing copy is PT-BR; code, comments, file names, and identifiers are English.
- Money is always integer centavos; floats and doubles never represent BRL domain values.
- Public resources use deterministic UUIDs; no backend integer IDs appear in feature code.
- No HTTP calls, real credentials, persistence, email, PIX payment, PDF generation, upload, or other external side effects.
- Views must be driven by shared mutable mock state; do not hard-code fixture values in feature views.
- PR #138 enum raw values and capability concepts remain stable at the repository boundary.
- Each top-level experience supports populated, empty, loading, recoverable-error, and permission-restricted states through demo controls.
- Xcode compilation, simulator UI tests, and screenshot inspection are deferred to the final verification task at the user's request; `swift test --package-path ios` remains mandatory throughout core implementation.

---

## File Map

```text
ios/
  Package.swift                                      # Foundation-only core test harness
  Rentivo.xcodeproj/project.pbxproj                  # iOS app and test targets
  Rentivo/
    App/RentivoApp.swift                             # App entry point
    App/AppModel.swift                               # Authentication, tab, routing, notices
    App/RootView.swift                               # Authenticated/anonymous shell
    Domain/Money.swift                               # Centavo arithmetic and BRL formatting
    Domain/Models.swift                              # Shared API-aligned domain values
    Domain/BillingModels.swift                       # Billing, bill, expense, file models
    Domain/AccountModels.swift                       # Org, security, key, theme models
    Data/Repositories.swift                          # Focused repository protocols
    Data/MockFixtures.swift                          # Deterministic canonical graph
    Data/MockRentivoStore.swift                      # Mutable repository implementation
    DesignSystem/RentivoTheme.swift                  # Semantic tokens
    DesignSystem/RentivoComponents.swift             # Cards, buttons, states, badges
    Features/Auth/AuthViews.swift                    # Login/signup/recovery/MFA/passkey
    Features/Home/HomeView.swift                     # Dashboard
    Features/Billings/BillingListView.swift          # Search/filter/create
    Features/Billings/BillingDetailView.swift        # Billing summary and related domains
    Features/Billings/BillingFormView.swift          # Create/edit template
    Features/Bills/BillViews.swift                   # Generate/edit/detail/lifecycle
    Features/Bills/BillingOperationsViews.swift      # Expenses/files/communications/exports
    Features/Organizations/OrganizationViews.swift   # Org list/detail/form/members
    Features/Organizations/InvitationViews.swift     # Invite list and actions
    Features/Account/AccountView.swift               # Account navigation
    Features/Account/SecurityViews.swift              # PIX/password/TOTP/passkeys/recovery
    Features/Account/APIKeyViews.swift               # Integration key lifecycle
    Features/Account/ThemeViews.swift                # Theme edit/inheritance/preview
    Features/Demo/DemoScenariosView.swift            # Delay/failure/empty/permissions/reset
    Resources/Assets.xcassets                        # App colors and initial icon assets
  RentivoTests/
    MoneyTests.swift
    BillLifecycleTests.swift
    MockRentivoStoreTests.swift
    DashboardTests.swift
    ValidationTests.swift
  RentivoUITests/
    RentivoUITests.swift
```

---

### Task 1: Project skeleton and core money primitives

**Files:**
- Create: `ios/Package.swift`
- Create: `ios/Rentivo/Domain/Money.swift`
- Create: `ios/Rentivo/Domain/Models.swift`
- Create: `ios/RentivoTests/MoneyTests.swift`

**Interfaces:**
- Produces: `struct Money: Hashable, Codable, Sendable, Comparable`
- Produces: `enum LoadState<Value>` with idle/loading/loaded/empty/failed cases
- Produces: `struct DemoError: Error, Equatable, LocalizedError`
- Produces: deterministic `StableID` UUID helpers

- [ ] **Step 1: Write failing money tests**

```swift
import Testing
@testable import RentivoCore

@Test func moneyAddsCentavosWithoutFloatingPoint() {
    #expect(Money(centavos: 180_000) + Money(centavos: 65_000) == Money(centavos: 245_000))
}

@Test func moneyFormatsBrazilianCurrency() {
    #expect(Money(centavos: 245_000).formatted(locale: Locale(identifier: "pt_BR")) == "R$ 2.450,00")
}
```

- [ ] **Step 2: Run the tests and verify the missing-module failure**

Run: `swift test --package-path ios`

Expected: FAIL because `RentivoCore` and `Money` do not exist.

- [ ] **Step 3: Add the package and minimal core implementation**

```swift
// ios/Package.swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "RentivoCore",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [.library(name: "RentivoCore", targets: ["RentivoCore"])],
    targets: [
        .target(
            name: "RentivoCore",
            path: "Rentivo",
            exclude: ["App", "DesignSystem", "Features", "Resources"],
            sources: ["Domain", "Data"]
        ),
        .testTarget(name: "RentivoCoreTests", dependencies: ["RentivoCore"], path: "RentivoTests")
    ]
)
```

```swift
public struct Money: Hashable, Codable, Sendable, Comparable {
    public let centavos: Int
    public init(centavos: Int) { self.centavos = centavos }
    public static let zero = Money(centavos: 0)
    public static func + (lhs: Self, rhs: Self) -> Self { Money(centavos: lhs.centavos + rhs.centavos) }
    public static func < (lhs: Self, rhs: Self) -> Bool { lhs.centavos < rhs.centavos }
    public func formatted(locale: Locale = Locale(identifier: "pt_BR")) -> String {
        let amount = Decimal(centavos) / Decimal(100)
        return amount.formatted(.currency(code: "BRL").locale(locale))
    }
}
```

Implement formatting with a `Decimal` intermediary and a deterministic non-breaking-space normalization covered by the test.

- [ ] **Step 4: Run core tests**

Run: `swift test --package-path ios`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ios/Package.swift ios/Rentivo/Domain ios/RentivoTests/MoneyTests.swift
git commit -m "feat(ios): add core money primitives"
```

### Task 2: API-aligned domain graph and lifecycle rules

**Files:**
- Modify: `ios/Rentivo/Domain/Models.swift`
- Create: `ios/Rentivo/Domain/BillingModels.swift`
- Create: `ios/Rentivo/Domain/AccountModels.swift`
- Create: `ios/RentivoTests/BillLifecycleTests.swift`

**Interfaces:**
- Produces: `Billing`, `BillingItem`, `BillingOwner`, `BillingCapabilities`
- Produces: `Bill`, `BillLineItem`, `BillStatus`, `Expense`, `Attachment`, `Receipt`
- Produces: `Organization`, `OrganizationMember`, `Invitation`, security/key/theme models
- Produces: `BillStatus.allowedTransitions` and `canTransition(to:)`
- Produces: deterministic test conveniences `APIKeyDraft.demo` and `ThemeValues.sunset`

- [ ] **Step 1: Write failing lifecycle and capability tests**

```swift
@Test func draftCanPublishButCannotBecomeDelayedDirectly() {
    #expect(BillStatus.draft.canTransition(to: .published))
    #expect(!BillStatus.draft.canTransition(to: .delayedPayment))
}

@Test func viewerCapabilitiesAreReadOnly() {
    #expect(BillingCapabilities.viewer.canReadBills)
    #expect(!BillingCapabilities.viewer.canEdit)
    #expect(!BillingCapabilities.viewer.canDelete)
}
```

- [ ] **Step 2: Verify tests fail for missing types**

Run: `swift test --package-path ios --filter BillLifecycleTests`

Expected: FAIL with missing `BillStatus` and `BillingCapabilities`.

- [ ] **Step 3: Implement complete API-aligned models**

```swift
public enum BillStatus: String, CaseIterable, Codable, Sendable {
    case draft
    case published
    case sent
    case paid
    case cancelled
    case delayedPayment = "delayed_payment"

    public var allowedTransitions: Set<Self> {
        switch self {
        case .draft: [.published, .cancelled]
        case .published: [.sent, .paid, .cancelled]
        case .sent: [.paid, .delayedPayment, .cancelled]
        case .delayedPayment: [.paid, .cancelled]
        case .paid, .cancelled: []
        }
    }

    public func canTransition(to target: Self) -> Bool { allowedTransitions.contains(target) }
}
```

Define every model named in the specification with immutable identifiers and mutable business fields. Keep computed totals derived from line items.

- [ ] **Step 4: Run all core tests**

Run: `swift test --package-path ios`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ios/Rentivo/Domain ios/RentivoTests/BillLifecycleTests.swift
git commit -m "feat(ios): model Rentivo domain contract"
```

### Task 3: Repository protocols, fixtures, and coherent mutable store

**Files:**
- Create: `ios/Rentivo/Data/Repositories.swift`
- Create: `ios/Rentivo/Data/MockFixtures.swift`
- Create: `ios/Rentivo/Data/MockRentivoStore.swift`
- Create: `ios/RentivoTests/MockRentivoStoreTests.swift`
- Create: `ios/RentivoTests/DashboardTests.swift`

**Interfaces:**
- Produces: focused repository protocols listed in the design specification
- Produces: `@MainActor final class MockRentivoStore`
- Produces: `DashboardSummary`, `reset()`, `failNextOperation()`, `setDelayEnabled(_:)`, `setEmptyMode(_:)`, `setViewerMode(_:)`
- Consumes: all Task 2 models

- [ ] **Step 1: Write mutation-consistency tests**

```swift
@Test @MainActor func addingExpenseUpdatesDashboardNetIncome() async throws {
    let store = MockRentivoStore(fixtures: .canonical)
    let before = try await store.dashboardSummary()
    let billing = try #require(try await store.listBillings().first)
    _ = try await store.createExpense(
        billingID: billing.id,
        description: "Manutenção",
        category: .maintenance,
        incurredOn: DateOnly(year: 2026, month: 7, day: 20),
        amount: Money(centavos: 25_000)
    )
    let after = try await store.dashboardSummary()
    #expect(after.expenses == before.expenses + Money(centavos: 25_000))
    #expect(after.netIncome == before.netIncome + Money(centavos: -25_000))
}
```

Add tests for reset stability, invitation acceptance, valid invoice transition, invalid transition rejection, injected failure consumption, and viewer restrictions.

- [ ] **Step 2: Verify repository tests fail**

Run: `swift test --package-path ios --filter MockRentivoStoreTests`

Expected: FAIL because repository and fixture types are absent.

- [ ] **Step 3: Implement protocols, canonical fixtures, and store**

```swift
@MainActor
public protocol BillingRepository: AnyObject {
    func listBillings() async throws -> [Billing]
    func billing(id: UUID) async throws -> Billing
    func createBilling(_ draft: BillingDraft) async throws -> Billing
    func updateBilling(id: UUID, draft: BillingDraft) async throws -> Billing
    func deleteBilling(id: UUID) async throws
}
```

Use one `StoreSnapshot` containing all arrays/dictionaries. Every operation calls `prepareOperation()`, which applies deterministic delay once enabled and consumes one injected failure. Mutations append a `RecentActivity` entry and recompute summaries from authoritative records.

- [ ] **Step 4: Run all core tests**

Run: `swift test --package-path ios`

Expected: PASS with deterministic fixtures.

- [ ] **Step 5: Commit**

```bash
git add ios/Rentivo/Data ios/RentivoTests
git commit -m "feat(ios): add coherent mock repository"
```

### Task 4: Xcode project, design system, app model, and authentication shell

**Files:**
- Create: `ios/Rentivo.xcodeproj/project.pbxproj`
- Create: `ios/Rentivo/App/RentivoApp.swift`
- Create: `ios/Rentivo/App/AppModel.swift`
- Create: `ios/Rentivo/App/RootView.swift`
- Create: `ios/Rentivo/DesignSystem/RentivoTheme.swift`
- Create: `ios/Rentivo/DesignSystem/RentivoComponents.swift`
- Create: `ios/Rentivo/Features/Auth/AuthViews.swift`
- Create: `ios/Rentivo/Resources/Assets.xcassets/Contents.json`

**Interfaces:**
- Consumes: `MockRentivoStore`, `Money`, load states, user profile
- Produces: `@Observable @MainActor final class AppModel`
- Produces: `RentivoApp`, `RootView`, `AuthenticatedTabView`, all authentication screens
- Produces: reusable card/button/status/page-state components

- [ ] **Step 1: Add parser checks before implementation**

Run: `find ios/Rentivo -name '*.swift' -print0 | xargs -0 swiftc -parse`

Expected: PASS for Tasks 1–3 sources.

- [ ] **Step 2: Implement project and application state**

```swift
@MainActor @Observable
final class AppModel {
    enum Session { case anonymous, authenticated(UserProfile) }
    var session: Session = .anonymous
    var selectedTab: AppTab = .home
    var notice: AppNotice?
    let store: MockRentivoStore

    init(store: MockRentivoStore = MockRentivoStore(fixtures: .canonical)) {
        self.store = store
    }
}
```

The `project.pbxproj` uses a file-system-synchronized `Rentivo` group, an iOS 17 application target, and separate unit/UI test targets. Use bundle identifiers `app.rentivo.demo`, `app.rentivo.demo.tests`, and `app.rentivo.demo.uitests`.

- [ ] **Step 3: Implement native branded authentication flows**

Login validates a non-empty email-shaped value and password, optionally routes through MFA/passkey demonstrations, and sets `AppModel.session`. Signup, forgot password, and reset confirmation remain locally simulated with explicit demonstration copy.

- [ ] **Step 4: Parse every Swift file**

Run: `find ios/Rentivo -name '*.swift' -print0 | xargs -0 swiftc -parse`

Expected: PASS. This checks syntax only until Xcode supplies SwiftUI SDK type checking.

- [ ] **Step 5: Commit**

```bash
git add ios/Rentivo.xcodeproj ios/Rentivo/App ios/Rentivo/DesignSystem ios/Rentivo/Features/Auth ios/Rentivo/Resources
git commit -m "feat(ios): add native app and authentication shell"
```

### Task 5: Dashboard and billing portfolio

**Files:**
- Create: `ios/Rentivo/Features/Home/HomeView.swift`
- Create: `ios/Rentivo/Features/Billings/BillingListView.swift`
- Create: `ios/Rentivo/Features/Billings/BillingDetailView.swift`
- Create: `ios/Rentivo/Features/Billings/BillingFormView.swift`
- Create: `ios/RentivoTests/ValidationTests.swift`

**Interfaces:**
- Consumes: dashboard and billing repository operations
- Produces: search/filter/list/detail/create/edit/delete billing journeys
- Produces: `BillingDraft.validate() -> [ValidationIssue]`

- [ ] **Step 1: Write failing billing validation tests**

```swift
@Test func billingRequiresNameAndAtLeastOneItem() {
    let issues = BillingDraft.empty.validate()
    #expect(issues.map(\.field) == [.name, .items])
}
```

- [ ] **Step 2: Run tests and verify failure**

Run: `swift test --package-path ios --filter ValidationTests`

Expected: FAIL until validation is implemented.

- [ ] **Step 3: Implement dashboard and billing screens**

Use `Task`-driven load states, searchable billing lists, owner filters, native sheets for quick creation, pushed multi-section forms, confirmation dialogs, accessibility identifiers, and shared cards/badges. Dashboard numbers must come only from `store.dashboardSummary()`.

```swift
struct HomeView: View {
    @Environment(AppModel.self) private var app
    @State private var state: LoadState<DashboardSummary> = .idle

    var body: some View {
        PageStateView(state: state) { summary in
            DashboardContent(summary: summary, activities: app.store.recentActivities)
        } retry: { await load() }
        .navigationTitle("Início")
        .task { await load() }
    }

    private func load() async {
        state = .loading
        do { state = .loaded(try await app.store.dashboardSummary()) }
        catch { state = .failed(DemoError(error)) }
    }
}
```

- [ ] **Step 4: Run core tests and syntax parser**

Run: `swift test --package-path ios`

Run: `find ios/Rentivo -name '*.swift' -print0 | xargs -0 swiftc -parse`

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add ios/Rentivo/Features/Home ios/Rentivo/Features/Billings ios/RentivoTests/ValidationTests.swift
git commit -m "feat(ios): add dashboard and billing portfolio"
```

### Task 6: Invoice lifecycle and billing operations

**Files:**
- Create: `ios/Rentivo/Features/Bills/BillViews.swift`
- Create: `ios/Rentivo/Features/Bills/BillingOperationsViews.swift`
- Modify: `ios/Rentivo/Features/Billings/BillingDetailView.swift`
- Modify: `ios/RentivoTests/MockRentivoStoreTests.swift`
- Modify: `ios/RentivoTests/ValidationTests.swift`

**Interfaces:**
- Consumes: bill, expense, attachment, receipt, communication, and export repository operations
- Produces: invoice generation/edit/detail/lifecycle/delete flows
- Produces: expense/file/receipt/communication/export simulations

- [ ] **Step 1: Add failing invoice and operation tests**

Test centavo totals for fixed/variable/extra items, guarded transitions, receipt reorder stability, expense deletion summary updates, and communication activity creation.

```swift
@Test @MainActor func invalidInvoiceTransitionIsRejectedWithoutMutation() async throws {
    let store = MockRentivoStore(fixtures: .canonical)
    let draft = try #require(try await store.listBills(billingID: StableID.billingAurora101).first { $0.status == .draft })
    await #expect(throws: DemoError.self) {
        try await store.transitionBill(billingID: draft.billingID, billID: draft.id, to: .delayedPayment)
    }
    #expect(try await store.bill(billingID: draft.billingID, id: draft.id).status == .draft)
}

@Test @MainActor func receiptOrderPersists() async throws {
    let store = MockRentivoStore(fixtures: .canonical)
    let bill = try await store.bill(billingID: StableID.billingAurora101, id: StableID.billPaid)
    let reversed = bill.receipts.map(\.id).reversed()
    try await store.reorderReceipts(billingID: bill.billingID, billID: bill.id, receiptIDs: Array(reversed))
    #expect(try await store.bill(billingID: bill.billingID, id: bill.id).receipts.map(\.id) == Array(reversed))
}
```

- [ ] **Step 2: Verify targeted tests fail**

Run: `swift test --package-path ios --filter MockRentivoStoreTests`

Expected: FAIL for the newly asserted operations.

- [ ] **Step 3: Implement invoice and operation screens**

Invoice detail exposes only `allowedTransitions`; status labels map exact raw values to `Rascunho`, `Publicada`, `Enviada`, `Paga`, `Cancelada`, and `Pagamento atrasado`. PDF, receipt, attachment, export, and delivery actions use native previews and label themselves as simulations.

- [ ] **Step 4: Run core and parser checks**

Run: `swift test --package-path ios`

Run: `find ios/Rentivo -name '*.swift' -print0 | xargs -0 swiftc -parse`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ios/Rentivo/Features/Bills ios/Rentivo/Features/Billings/BillingDetailView.swift ios/RentivoTests
git commit -m "feat(ios): demonstrate complete invoice lifecycle"
```

### Task 7: Organizations, members, invitations, and transfers

**Files:**
- Create: `ios/Rentivo/Features/Organizations/OrganizationViews.swift`
- Create: `ios/Rentivo/Features/Organizations/InvitationViews.swift`
- Modify: `ios/RentivoTests/MockRentivoStoreTests.swift`
- Modify: `ios/RentivoTests/ValidationTests.swift`

**Interfaces:**
- Consumes: organization and invitation repository operations
- Produces: organization CRUD, PIX, members, roles, MFA policy, invitation, and transfer journeys

- [ ] **Step 1: Add failing organization tests**

```swift
@Test @MainActor func acceptingInviteCreatesMembershipAndClearsPendingCount() async throws {
    let store = MockRentivoStore(fixtures: .canonical)
    let invite = try #require(try await store.listPendingInvitations().first)
    try await store.acceptInvitation(id: invite.id)
    #expect(try await store.listPendingInvitations().isEmpty)
    #expect(try await store.organization(id: invite.organizationID).members.contains { $0.userID == store.currentUser.id })
}
```

- [ ] **Step 2: Verify the new test fails**

Run: `swift test --package-path ios --filter MockRentivoStoreTests`

Expected: FAIL until membership mutation is complete.

- [ ] **Step 3: Implement organization and invitation views**

Use role-aware menus, confirmation dialogs for policy/destructive actions, a pending-count badge, and transfer pickers that update billing ownership across both feature areas.

- [ ] **Step 4: Run core and parser checks**

Run: `swift test --package-path ios`

Run: `find ios/Rentivo -name '*.swift' -print0 | xargs -0 swiftc -parse`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ios/Rentivo/Features/Organizations ios/RentivoTests
git commit -m "feat(ios): add organization collaboration flows"
```

### Task 8: Account security, API keys, themes, and demo scenarios

**Files:**
- Create: `ios/Rentivo/Features/Account/AccountView.swift`
- Create: `ios/Rentivo/Features/Account/SecurityViews.swift`
- Create: `ios/Rentivo/Features/Account/APIKeyViews.swift`
- Create: `ios/Rentivo/Features/Account/ThemeViews.swift`
- Create: `ios/Rentivo/Features/Demo/DemoScenariosView.swift`
- Modify: `ios/RentivoTests/MockRentivoStoreTests.swift`

**Interfaces:**
- Consumes: profile, security, key, theme, and demo repository operations
- Produces: PIX/password/TOTP/recovery/passkey/key/theme/reset/failure/empty/viewer journeys

- [ ] **Step 1: Add failing security, key, and theme tests**

Test that created key secrets appear only once, revoked keys stay masked and idempotently revoked, theme reset restores inheritance, personal PIX updates inherited billing readiness, and reset restores the canonical snapshot byte-for-byte.

```swift
@Test @MainActor func createdKeySecretIsSeparateFromMetadata() async throws {
    let store = MockRentivoStore(fixtures: .canonical)
    let created = try await store.createAPIKey(APIKeyDraft.demo)
    #expect(created.secret.hasPrefix("rntv-v1-"))
    #expect(try await store.listAPIKeys().contains { $0.id == created.metadata.id })
    #expect(!String(describing: try await store.listAPIKeys()).contains(created.secret))
}

@Test @MainActor func themeResetRestoresInheritance() async throws {
    let store = MockRentivoStore(fixtures: .canonical)
    try await store.updateTheme(target: .billing(StableID.billingAurora101), values: .sunset)
    try await store.resetTheme(target: .billing(StableID.billingAurora101))
    let theme = try await store.theme(target: .billing(StableID.billingAurora101))
    #expect(theme.stored == nil)
    #expect(theme.effectiveSource == .user)
}

@Test @MainActor func resetRestoresCanonicalSnapshot() async throws {
    let store = MockRentivoStore(fixtures: .canonical)
    _ = try await store.createAPIKey(APIKeyDraft.demo)
    store.reset()
    #expect(store.snapshot == MockFixtures.canonical.snapshot)
}
```

- [ ] **Step 2: Verify tests fail**

Run: `swift test --package-path ios --filter MockRentivoStoreTests`

Expected: FAIL for missing account mutations.

- [ ] **Step 3: Implement account and demo screens**

Theme form fields exactly match PR #138: header font, text font, primary, primary light, secondary, secondary dark, text, and contrast text. Key scopes and grants come from domain options. Secret reveal is a one-time sheet backed by a separate `CreatedAPIKeySecret` value.

- [ ] **Step 4: Run core and parser checks**

Run: `swift test --package-path ios`

Run: `find ios/Rentivo -name '*.swift' -print0 | xargs -0 swiftc -parse`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ios/Rentivo/Features/Account ios/Rentivo/Features/Demo ios/RentivoTests
git commit -m "feat(ios): add account and demo controls"
```

### Task 9: UI smoke tests, Xcode verification, and visual repair

**Files:**
- Create: `ios/RentivoUITests/RentivoUITests.swift`
- Modify: SwiftUI files identified by Xcode diagnostics or screenshot review
- Modify: `ios/Rentivo.xcodeproj/project.pbxproj` if Xcode migration or target settings require correction

**Interfaces:**
- Consumes: all prior screens and accessibility identifiers
- Produces: build/test/screenshot evidence for acceptance criteria

- [ ] **Step 1: Write UI smoke tests**

```swift
func testPrimaryDemonstrationJourney() throws {
    let app = XCUIApplication()
    app.launchArguments = ["--ui-testing"]
    app.launch()
    app.textFields["login.email"].tap()
    app.textFields["login.email"].typeText("ana@example.com")
    app.secureTextFields["login.password"].tap()
    app.secureTextFields["login.password"].typeText("demonstracao")
    app.buttons["login.submit"].tap()
    XCTAssertTrue(app.tabBars.buttons["Início"].waitForExistence(timeout: 2))
    app.tabBars.buttons["Cobranças"].tap()
    XCTAssertTrue(app.navigationBars["Cobranças"].exists)
}
```

Add smoke journeys for billing/invoice creation, expense summary update, invite acceptance, theme change, failure recovery, and reset.

- [ ] **Step 2: Confirm Xcode availability and list schemes/destinations**

Run: `env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild -version`

Run: `env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild -project ios/Rentivo.xcodeproj -list`

Run: `env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcrun simctl list devices available`

Expected: Xcode 26.6, the `Rentivo` scheme, and at least one available iPhone simulator. If the device list remains empty, install the iOS 26.5 simulator runtime through Xcode Settings > Components before running UI tests; generic iOS Simulator builds remain available without that runtime.

- [ ] **Step 3: Build and test**

Run: `env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild -project ios/Rentivo.xcodeproj -scheme Rentivo -destination 'generic/platform=iOS Simulator' build`

Run after the runtime is available: `env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild -project ios/Rentivo.xcodeproj -scheme Rentivo -destination 'platform=iOS Simulator,OS=26.5,name=iPhone 17 Pro' test`

Expected: `** BUILD SUCCEEDED **` and `** TEST SUCCEEDED **`.

- [ ] **Step 4: Launch and capture principal screenshots**

Capture login, dashboard, billing list, billing detail, invoice detail, organization detail, security, and theme editor. Inspect each for safe-area errors, clipping, contrast, keyboard obstruction, Dynamic Type issues, and inconsistent native navigation.

- [ ] **Step 5: Repair every observed issue and rerun verification**

For each failure, use `superpowers:systematic-debugging`, add a regression test where possible, implement one root-cause fix, and rerun the narrow check followed by the full build/test commands.

- [ ] **Step 6: Run repository-wide checks**

Run: `git diff --check`

Run: `swift test --package-path ios`

Run: repository pre-commit hooks through a final conventional commit.

Expected: all checks pass.

- [ ] **Step 7: Commit**

```bash
git add ios
git commit -m "test(ios): verify native demonstration app"
```

---

## Completion Audit

Before claiming completion, map each acceptance criterion in `docs/superpowers/specs/2026-07-20-native-ios-demo-design.md` to current evidence:

1. Xcode build output proves the native project builds.
2. Source search and runtime observation prove no network interactions exist.
3. UI tests and manual navigation prove all screen groups are reachable.
4. Store tests and UI journeys prove coherent mutations across every domain.
5. Reset test proves deterministic restoration.
6. Protocol declarations and dependency wiring prove API replaceability.
7. Scenario controls and targeted UI checks prove alternate states.
8. Current core, unit, and UI test output proves automation coverage.
9. Simulator screenshots plus inspection notes prove visual review.
10. secret/network searches and synthetic fixture inspection prove no production side effects.
