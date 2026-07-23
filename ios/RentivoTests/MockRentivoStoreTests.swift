import Foundation
import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

@Test @MainActor func canonicalFixturesCoverEveryInvoiceStatus() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let billings = try await store.listBillings()
  var bills: [Bill] = []
  for billing in billings {
    bills.append(contentsOf: try await store.listBills(billingID: billing.id))
  }

  #expect(billings.count == 6)
  #expect(Set(bills.map(\.status)) == Set(BillStatus.allCases))
}

@Test @MainActor func addingExpenseUpdatesDashboardNetIncome() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let before = try await store.dashboardSummary()

  _ = try await store.createExpense(
    billingID: StableID.billingAurora101,
    description: "Manutenção",
    category: .maintenance,
    incurredOn: DateOnly(year: 2026, month: 7, day: 20),
    amount: Money(centavos: 25_000)
  )

  let after = try await store.dashboardSummary()
  #expect(after.expenses == before.expenses + Money(centavos: 25_000))
  #expect(after.netIncome == before.netIncome - Money(centavos: 25_000))
}

@Test @MainActor func invalidTransitionDoesNotMutateBill() async throws {
  let store = MockRentivoStore(fixtures: .canonical)

  do {
    try await store.transitionBill(
      billingID: StableID.billingAurora101,
      billID: StableID.billDraft,
      to: .delayedPayment
    )
    Issue.record("Expected invalid transition to throw")
  } catch let error as DemoError {
    #expect(error == .invalidBillTransition)
  }

  let bill = try await store.bill(
    billingID: StableID.billingAurora101,
    id: StableID.billDraft
  )
  #expect(bill.status == .draft)
}

@Test @MainActor func validTransitionMutatesSharedBill() async throws {
  let store = MockRentivoStore(fixtures: .canonical)

  try await store.transitionBill(
    billingID: StableID.billingAurora101,
    billID: StableID.billDraft,
    to: .published
  )

  let bill = try await store.bill(
    billingID: StableID.billingAurora101,
    id: StableID.billDraft
  )
  #expect(bill.status == .published)
  #expect(store.recentActivities.first?.kind == .bill)
}

@Test @MainActor func injectedFailureIsConsumedByOneOperation() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  store.failNextOperation()

  do {
    _ = try await store.listBillings()
    Issue.record("Expected injected failure")
  } catch let error as DemoError {
    #expect(error == .operationFailed)
  }

  #expect(try await store.listBillings().count == 6)
}

@Test @MainActor func emptyModeChangesReadsWithoutDestroyingSnapshot() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let canonical = store.snapshot
  store.setEmptyMode(true)

  #expect(try await store.listBillings().isEmpty)
  #expect(store.snapshot == canonical)

  store.setEmptyMode(false)
  #expect(try await store.listBillings().count == 6)
}

@Test @MainActor func viewerModeRestrictsCapabilitiesWithoutChangingOwnership() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let original = try #require(try await store.listBillings().first)
  store.setViewerMode(true)
  let restricted = try #require(try await store.listBillings().first)

  #expect(restricted.id == original.id)
  #expect(restricted.owner == original.owner)
  #expect(restricted.capabilities == .viewer)
}

@Test @MainActor func viewerModeRestrictsOrganizationManagementCapabilities() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  store.setViewerMode(true)

  let organization = try await store.organization(id: StableID.organizationHorizonte)

  #expect(organization.currentUserRole == .viewer)
  #expect(!organization.capabilities.canManage)
  #expect(!organization.capabilities.canInvite)
  #expect(!organization.capabilities.canCreateBilling)
  #expect(organization.capabilities.canViewBillingStats)
}

@Test @MainActor func acceptingInvitationCreatesMembershipAndClearsPendingCount() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let invitation = try #require(try await store.listPendingInvitations().first)

  try await store.acceptInvitation(id: invitation.id)

  #expect(try await store.listPendingInvitations().isEmpty)
  let organization = try await store.organization(id: invitation.organizationID)
  #expect(organization.members.contains { $0.userID == store.currentUser.id })
}

@Test @MainActor func acceptedManagerCannotMutateOrganizationPolicy() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let invitation = try #require(try await store.listPendingInvitations().first)
  try await store.acceptInvitation(id: invitation.id)

  do {
    try await store.setOrganizationMFA(
      organizationID: invitation.organizationID,
      required: true
    )
    Issue.record("Expected manager policy mutation to be denied")
  } catch let error as DemoError {
    #expect(error == .permissionDenied)
  }
}

@Test @MainActor func acceptedManagerCannotMutateOrganizationTheme() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let invitation = try #require(try await store.listPendingInvitations().first)
  try await store.acceptInvitation(id: invitation.id)

  let theme = try await store.theme(target: .organization(invitation.organizationID))
  #expect(!theme.canEdit)

  do {
    try await store.updateTheme(
      target: .organization(invitation.organizationID),
      values: .sunset
    )
    Issue.record("Expected manager theme mutation to be denied")
  } catch let error as DemoError {
    #expect(error == .permissionDenied)
  }
}

@Test @MainActor func resetRestoresCanonicalSnapshotAndBehavior() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  _ = try await store.createExpense(
    billingID: StableID.billingAurora101,
    description: "Pintura",
    category: .maintenance,
    incurredOn: DateOnly(year: 2026, month: 7, day: 20),
    amount: Money(centavos: 10_000)
  )
  store.setEmptyMode(true)
  store.setViewerMode(true)

  store.reset()

  #expect(store.snapshot == MockFixtures.canonical.snapshot)
  #expect(try await store.listBillings().count == 6)
  #expect(try #require(try await store.listBillings().first).capabilities == .full)
}

@Test @MainActor func receiptOrderPersists() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let bill = try await store.bill(
    billingID: StableID.billingAurora101,
    id: StableID.billPaid
  )
  let reversed = Array(bill.receipts.map(\.id).reversed())

  try await store.reorderReceipts(
    billingID: bill.billingID,
    billID: bill.id,
    receiptIDs: reversed
  )

  let updated = try await store.bill(billingID: bill.billingID, id: bill.id)
  #expect(bill.receipts.count == 2)
  #expect(updated.receipts.map(\.id) == reversed)
}

@Test @MainActor func communicationMutationUsesSharedActivityGraph() async throws {
  let store = MockRentivoStore(fixtures: .canonical)

  let communication = try await store.sendCommunication(
    billingID: StableID.billingAurora101,
    billID: StableID.billPublished,
    recipients: ["locatario@example.com"],
    subject: "Sua fatura está disponível",
    message: "Olá! Consulte os detalhes no Rentivo."
  )

  #expect(store.snapshot.communications.contains { $0.id == communication.id })
  #expect(store.recentActivities.first?.detail == communication.subject)
}

@Test @MainActor func creatingExpenseRejectsZeroOrNegativeAmounts() async throws {
  // Matches the server contract: `ExpenseCreateRequest.amount` requires
  // `exclusiveMinimum: 0`.
  let store = MockRentivoStore(fixtures: .canonical)

  do {
    _ = try await store.createExpense(
      billingID: StableID.billingAurora101,
      description: "Reparo",
      category: .maintenance,
      incurredOn: DateOnly(year: 2026, month: 7, day: 20),
      amount: .zero
    )
    Issue.record("Expected zero-amount expense to be rejected")
  } catch let error as DemoError {
    #expect(error == .invalidAmount)
  }

  do {
    _ = try await store.createExpense(
      billingID: StableID.billingAurora101,
      description: "Reparo",
      category: .maintenance,
      incurredOn: DateOnly(year: 2026, month: 7, day: 20),
      amount: Money(centavos: -100)
    )
    Issue.record("Expected negative-amount expense to be rejected")
  } catch let error as DemoError {
    #expect(error == .invalidAmount)
  }
}

@Test @MainActor func deletingExpenseUpdatesDashboard() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let expense = try #require(
    try await store.listExpenses(billingID: StableID.billingAurora101).first
  )
  let before = try await store.dashboardSummary()

  try await store.deleteExpense(billingID: expense.billingID, expenseID: expense.id)

  let after = try await store.dashboardSummary()
  #expect(after.expenses == before.expenses - expense.amount)
  #expect(after.netIncome == before.netIncome + expense.amount)
}

@Test @MainActor func transferringBillingChangesOwnerAcrossRepositoryReads() async throws {
  let store = MockRentivoStore(fixtures: .canonical)

  try await store.transferBilling(
    billingID: StableID.billingAurora101,
    toOrganizationID: StableID.organizationHorizonte
  )

  let billing = try await store.billing(id: StableID.billingAurora101)
  #expect(billing.owner.workspaceID.rawValue == StableID.organizationHorizonte.rawValue)
  #expect(billing.owner.isOrganization)
}

@Test @MainActor func memberRoleAndMFAPolicyMutationsPersist() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let organization = try await store.organization(id: StableID.organizationHorizonte)
  let member = try #require(organization.members.first { $0.role == .viewer })

  try await store.updateMemberRole(
    organizationID: organization.id,
    userID: member.userID,
    role: .manager
  )
  try await store.setOrganizationMFA(organizationID: organization.id, required: false)

  let updated = try await store.organization(id: organization.id)
  #expect(updated.members.first { $0.userID == member.userID }?.role == .manager)
  #expect(!updated.requiresMFA)
}

@Test @MainActor func memberRoleCanBePromotedToAdmin() async throws {
  // Regression coverage for the role picker bug: promoting a member to admin
  // must be a supported mutation (the API accepts admin/manager/viewer).
  let store = MockRentivoStore(fixtures: .canonical)
  let organization = try await store.organization(id: StableID.organizationHorizonte)
  let member = try #require(organization.members.first { $0.role == .manager })

  try await store.updateMemberRole(
    organizationID: organization.id,
    userID: member.userID,
    role: .admin
  )

  let updated = try await store.organization(id: organization.id)
  #expect(updated.members.first { $0.userID == member.userID }?.role == .admin)
}

@Test @MainActor func createdKeySecretIsSeparateFromMetadata() async throws {
  let store = MockRentivoStore(fixtures: .canonical)

  let created = try await store.createAPIKey(.demo)
  let metadata = try await store.listAPIKeys()

  #expect(created.secret.hasPrefix("rntv-v1-"))
  #expect(metadata.contains { $0.id == created.metadata.id })
  #expect(!String(describing: metadata).contains(created.secret))
}

@Test @MainActor func apiKeyMetadataCanBeUpdatedWithoutRotatingSecret() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let key = try #require(try await store.listAPIKeys().first)
  let updatedDraft = APIKeyDraft(
    name: "Integração contábil",
    scopes: [.profileRead, .expensesRead],
    grants: [APIKeyGrant(resourceType: .user, resourceID: .personal)],
    expiresAt: Date(timeIntervalSince1970: 1_830_297_600)
  )

  let updated = try await store.updateAPIKey(id: key.id, draft: updatedDraft)

  #expect(updated.id == key.id)
  #expect(updated.hint == key.hint)
  #expect(updated.name == updatedDraft.name)
  #expect(updated.scopes == updatedDraft.scopes)
  #expect(updated.grants == updatedDraft.grants)
  #expect(updated.expiresAt == updatedDraft.expiresAt)
}

@Test @MainActor func demoSettingsAreAuthoritativeAndResetTogether() async throws {
  let store = MockRentivoStore(fixtures: .canonical)

  store.setDelayEnabled(true)
  store.setEmptyMode(true)
  store.setViewerMode(true)

  #expect(
    store.demoSettings
      == DemoSettings(delayEnabled: true, emptyMode: true, viewerMode: true)
  )

  store.reset()
  #expect(store.demoSettings == .standard)
}

@Test @MainActor func appDependenciesExposeFocusedRepositoryBoundary() {
  let store = MockRentivoStore(fixtures: .canonical)
  let dependencies = AppDependencies.mock(store: store)

  #expect(dependencies.auth === store)
  #expect(dependencies.billings === store)
  #expect(dependencies.bills === store)
  #expect(dependencies.organizations === store)
  #expect(dependencies.demo === store)
}

@Test @MainActor func themeResetRestoresUserInheritance() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let target = ThemeTarget.billing(StableID.billingAurora101)

  try await store.updateTheme(target: target, values: .sunset)
  try await store.resetTheme(target: target)

  let theme = try await store.theme(target: target)
  #expect(theme.stored == nil)
  #expect(theme.effectiveSource == .user)
  #expect(theme.effective == .rentivo)
}

@Test @MainActor func securityMutationsUpdateTOTPRecoveryCodesAndPasskeys() async throws {
  let store = MockRentivoStore(fixtures: .canonical)

  try await store.setTOTPEnabled(false)
  let codes = try await store.regenerateRecoveryCodes()
  let passkey = try await store.addPasskey(name: "iPhone de demonstração")
  try await store.renamePasskey(id: passkey.id, name: "iPhone pessoal")

  let summary = try await store.securitySummary()
  #expect(!summary.totpEnabled)
  #expect(codes.count == 8)
  #expect(summary.recoveryCodeCount == 8)
  #expect(summary.passkeys.contains { $0.id == passkey.id && $0.name == "iPhone pessoal" })
}
