import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

@MainActor
@Test func liveDependenciesUseTheProductionStoreForEveryRepository() {
  let store = APIRentivoStore(inMemoryCredentialStore: true)
  let dependencies = AppDependencies.live(store: store)

  let authStore = dependencies.auth as? APIRentivoStore
  let billingStore = dependencies.billings as? APIRentivoStore
  let organizationStore = dependencies.organizations as? APIRentivoStore
  let downloadStore = dependencies.downloads as? APIRentivoStore
  let exportStore = dependencies.exports as? APIRentivoStore

  #expect(authStore === store)
  #expect(billingStore === store)
  #expect(organizationStore === store)
  #expect(downloadStore === store)
  #expect(exportStore === store)
}
