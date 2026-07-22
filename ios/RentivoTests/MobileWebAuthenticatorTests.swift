import Testing
@testable import RentivoCore

@MainActor
@Test func explicitLogoutForcesTheNextWebAuthorizationToUseAnIsolatedBrowserSession() {
  let authenticator = MobileWebAuthenticator()

  #expect(!authenticator.shouldUseEphemeralSession)

  authenticator.requireFreshAuthentication()

  #expect(authenticator.shouldUseEphemeralSession)

  authenticator.completeAuthentication()

  #expect(!authenticator.shouldUseEphemeralSession)
}
