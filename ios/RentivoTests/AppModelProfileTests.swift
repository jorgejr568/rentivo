import Testing
@testable import RentivoCore

@Test func profilePIXFormUsesTheAuthoritativeProfileValues() {
  let savedPIX = PixConfiguration(
    key: "jorge@example.com", merchantName: "JORGE JUNIOR", merchantCity: "SALVADOR"
  )
  let profile = UserProfile(id: 7, email: "jorge@example.com", pix: savedPIX)

  let form = ProfilePIXForm(profile: profile)

  #expect(form.configuration == savedPIX)
}
