import Foundation
import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

@Test func billingRequiresNameAndAtLeastOneItem() {
  let issues = BillingDraft.empty.validate()

  #expect(issues.map(\.field) == [.name, .items])
}

@Test func billingRejectsBlankItemDescriptionsAndNegativeAmounts() {
  let draft = BillingDraft(
    name: "Apartamento",
    description: "",
    owner: .user(id: StableID.userAna, name: "Pessoal"),
    items: [
      BillingItem(
        id: UUID(),
        description: "  ",
        amount: Money(centavos: -1),
        type: .fixed,
        sortOrder: 0
      )
    ]
  )

  #expect(draft.validate().map(\.field) == [.itemDescription, .itemAmount])
}

@Test func canonicalBillingDraftIsValid() {
  let draft = BillingDraft(
    name: "Apt 101",
    description: "Contrato mensal",
    owner: .user(id: StableID.userAna, name: "Pessoal"),
    items: [
      BillingItem(
        id: UUID(),
        description: "Aluguel",
        amount: Money(centavos: 180_000),
        type: .fixed,
        sortOrder: 0
      )
    ]
  )

  #expect(draft.validate().isEmpty)
}

@Test func invoiceDraftRejectsBlankRowsAndNegativeValues() {
  let draft = BillDraft(
    billingID: StableID.billingAurora101,
    referenceMonth: ReferenceMonth(year: 2026, month: 8),
    dueDate: DateOnly(year: 2026, month: 8, day: 10),
    notes: "",
    lineItems: [
      BillLineItem(
        id: UUID(),
        description: "",
        amount: Money(centavos: -100),
        kind: .variable
      )
    ]
  )

  #expect(draft.validate().map(\.field) == [.itemDescription, .itemAmount])
}

@Test func invoiceDraftAllowsZeroAmountForFixedAndVariableLineItems() {
  // Variable items (e.g. water/electricity meters) legitimately start at zero
  // before this month's reading is filled in; only extras must be positive.
  let draft = BillDraft(
    billingID: StableID.billingAurora101,
    referenceMonth: ReferenceMonth(year: 2026, month: 8),
    dueDate: DateOnly(year: 2026, month: 8, day: 10),
    notes: "",
    lineItems: [
      BillLineItem(id: UUID(), description: "Aluguel", amount: Money(centavos: 180_000), kind: .fixed),
      BillLineItem(id: UUID(), description: "Água", amount: .zero, kind: .variable),
    ]
  )

  #expect(draft.validate().isEmpty)
}

@Test func invoiceDraftRejectsZeroOrNegativeExtraLineItems() {
  // The server requires `BillExtraRequest.amount` to be strictly positive
  // (`exclusiveMinimum: 0`), so a zero-value extra must fail client-side too.
  let zeroExtraDraft = BillDraft(
    billingID: StableID.billingAurora101,
    referenceMonth: ReferenceMonth(year: 2026, month: 8),
    dueDate: DateOnly(year: 2026, month: 8, day: 10),
    notes: "",
    lineItems: [
      BillLineItem(id: UUID(), description: "Pintura", amount: .zero, kind: .extra)
    ]
  )
  #expect(zeroExtraDraft.validate().map(\.field) == [.itemAmount])

  let negativeExtraDraft = BillDraft(
    billingID: StableID.billingAurora101,
    referenceMonth: ReferenceMonth(year: 2026, month: 8),
    dueDate: DateOnly(year: 2026, month: 8, day: 10),
    notes: "",
    lineItems: [
      BillLineItem(id: UUID(), description: "Pintura", amount: Money(centavos: -500), kind: .extra)
    ]
  )
  #expect(negativeExtraDraft.validate().map(\.field) == [.itemAmount])
}

@Test func invoiceDraftAcceptsPositiveExtraLineItems() {
  let draft = BillDraft(
    billingID: StableID.billingAurora101,
    referenceMonth: ReferenceMonth(year: 2026, month: 8),
    dueDate: DateOnly(year: 2026, month: 8, day: 10),
    notes: "",
    lineItems: [
      BillLineItem(id: UUID(), description: "Pintura", amount: Money(centavos: 5_000), kind: .extra)
    ]
  )

  #expect(draft.validate().isEmpty)
}
