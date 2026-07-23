import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

@Test func memoryCredentialStoreRoundTripsAndDeletesToken() async {
  let credentials = MemoryCredentialStore()

  #expect(await credentials.readAccessToken() == nil)

  await credentials.saveAccessToken("session-token")
  #expect(await credentials.readAccessToken() == "session-token")

  await credentials.deleteAccessToken()
  #expect(await credentials.readAccessToken() == nil)
}
