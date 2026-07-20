import Foundation
import Testing

@testable import RentivoCore

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
