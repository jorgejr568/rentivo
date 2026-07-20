import Foundation
import Testing

@testable import RentivoCore

@Test func draftCanPublishButCannotBecomeDelayedDirectly() {
  #expect(BillStatus.draft.canTransition(to: .published))
  #expect(BillStatus.draft.canTransition(to: .cancelled))
  #expect(!BillStatus.draft.canTransition(to: .delayedPayment))
}

@Test func paidAndCancelledBillsAreTerminal() {
  #expect(BillStatus.paid.allowedTransitions.isEmpty)
  #expect(BillStatus.cancelled.allowedTransitions.isEmpty)
}

@Test func billStatusesKeepAPIValuesAndPortugueseLabels() {
  #expect(BillStatus.delayedPayment.rawValue == "delayed_payment")
  #expect(BillStatus.delayedPayment.label == "Pagamento atrasado")
  #expect(BillStatus.published.label == "Publicada")
}

@Test func viewerCapabilitiesAreReadOnly() {
  #expect(BillingCapabilities.viewer.canReadBills)
  #expect(BillingCapabilities.viewer.canReadExpenses)
  #expect(!BillingCapabilities.viewer.canEdit)
  #expect(!BillingCapabilities.viewer.canDelete)
  #expect(!BillingCapabilities.viewer.canWriteExpenses)
}

@Test func fullCapabilitiesExposeEveryBillingAction() {
  let capabilities = BillingCapabilities.full
  #expect(capabilities.allowsEveryAction)
}

@Test func billTotalIsDerivedFromLineItems() {
  let bill = Bill(
    id: StableID.billPaid,
    billingID: StableID.billingAurora101,
    referenceMonth: ReferenceMonth(year: 2026, month: 7),
    dueDate: DateOnly(year: 2026, month: 7, day: 10),
    paidAt: DateOnly(year: 2026, month: 7, day: 8),
    notes: "",
    status: .paid,
    lineItems: [
      BillLineItem(
        id: UUID(), description: "Aluguel", amount: Money(centavos: 180_000), kind: .fixed),
      BillLineItem(
        id: UUID(), description: "Água", amount: Money(centavos: 12_340), kind: .variable),
      BillLineItem(
        id: UUID(), description: "Pintura", amount: Money(centavos: 5_000), kind: .extra),
    ],
    receipts: []
  )

  #expect(bill.total == Money(centavos: 197_340))
}

@Test func dateAndReferenceMonthHaveStableAPIRepresentations() {
  #expect(DateOnly(year: 2026, month: 7, day: 9).iso8601 == "2026-07-09")
  #expect(ReferenceMonth(year: 2026, month: 7).apiValue == "2026-07")
  #expect(ReferenceMonth(year: 2026, month: 7).label == "julho de 2026")
}

@Test func integrationScopesExcludePrivilegedAccountOperations() {
  #expect(APIKeyScope.integrationCases.contains(.billingsRead))
  #expect(APIKeyScope.integrationCases.contains(.communicationsSend))
  #expect(!APIKeyScope.integrationCases.contains(.securityManage))
  #expect(!APIKeyScope.integrationCases.contains(.apiKeysManage))
}

@Test func apiEnumsPreserveRawValues() {
  #expect(ExpenseCategory.maintenance.rawValue == "manutencao")
  #expect(OrganizationRole.viewer.rawValue == "viewer")
  #expect(ThemeSource.organization.rawValue == "organization")
}
