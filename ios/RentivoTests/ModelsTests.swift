import Foundation
import Testing

@testable import RentivoCore

@Test func stableIdentifiersAreDeterministic() {
  #expect(StableID.userAna.uuidString == "00000000-0000-0000-0000-000000000001")
  #expect(StableID.billingAurora101.uuidString == "00000000-0000-0000-0000-000000000101")
  #expect(StableID.billPaid.uuidString == "00000000-0000-0000-0000-000000001004")
}

@Test func loadStateExposesLoadedValueOnly() {
  #expect(LoadState<Int>.idle.value == nil)
  #expect(LoadState<Int>.loading.value == nil)
  #expect(LoadState.loaded(42).value == 42)
  #expect(LoadState<Int>.empty.value == nil)
}

@Test func demoErrorUsesPortugueseRecoveryCopy() {
  let error = DemoError.operationFailed
  #expect(error.localizedDescription == "Não foi possível concluir esta ação de demonstração.")
}
