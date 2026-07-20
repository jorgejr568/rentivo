import Testing

@testable import RentivoCore

@Test @MainActor func dashboardSummaryIsDerivedFromAuthoritativeRecords() async throws {
  let store = MockRentivoStore(fixtures: .canonical)
  let summary = try await store.dashboardSummary()
  let billings = try await store.listBillings()
  var paid = Money.zero
  var delayed = Money.zero
  var expenses = Money.zero

  for billing in billings {
    for bill in try await store.listBills(billingID: billing.id) {
      if bill.status == .paid { paid = paid + bill.total }
      if bill.status == .delayedPayment { delayed = delayed + bill.total }
    }
    for expense in try await store.listExpenses(billingID: billing.id) {
      expenses = expenses + expense.amount
    }
  }

  #expect(summary.received == paid)
  #expect(summary.overdue == delayed)
  #expect(summary.expenses == expenses)
  #expect(summary.netIncome == paid - expenses)
  #expect(summary.collectionRatePercent > 0)
  #expect(summary.collectionRatePercent < 100)
}
