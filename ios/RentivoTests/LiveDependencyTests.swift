import Testing
@testable import RentivoCore

@MainActor
@Test func liveDependenciesUseTheProductionStoreForEveryRepository() {
  let store = APIRentivoStore(inMemoryCredentialStore: true)
  let dependencies = AppDependencies.live(store: store)

  let authStore = dependencies.auth as? APIRentivoStore
  let billingStore = dependencies.billings as? APIRentivoStore
  let organizationStore = dependencies.organizations as? APIRentivoStore

  #expect(authStore === store)
  #expect(billingStore === store)
  #expect(organizationStore === store)
}
