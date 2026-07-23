import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

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

@Test @MainActor func collectionRateIsComputedWithIntegerMathOnly() async throws {
  // No floating point: paid * 100 / non-cancelled count, matching the live store.
  let store = MockRentivoStore(fixtures: .canonical)
  let summary = try await store.dashboardSummary()
  let billings = try await store.listBillings()
  var allBills: [Bill] = []
  for billing in billings {
    allBills.append(contentsOf: try await store.listBills(billingID: billing.id))
  }
  let activeBills = allBills.filter { $0.status != .cancelled }
  let paidCount = activeBills.filter { $0.status == .paid }.count
  let expectedRate = activeBills.isEmpty ? 0 : (paidCount * 100) / activeBills.count

  #expect(summary.collectionRatePercent == expectedRate)
}
