import Foundation
import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

@MainActor
@Test func liveOrganizationListHydratesMembersForTheOrganizationCardCount() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: organizationSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  let organization = try #require(try await store.listOrganizations().first)

  #expect(organization.members.map(\.userID) == [7, 11])
}

@MainActor
@Test func liveInviteMemberUsesTheRealOrganizationNameInsteadOfAPlaceholder() async throws {
  // Regression test: inviteMember used to hardcode organizationName to "Organização".
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: organizationSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  let invitation = try await store.inviteMember(
    organizationID: OrganizationID(rawValue: "organization-1"), email: "bruno@rentivo.com.br", role: .viewer
  )

  #expect(invitation.organizationName == "Horizonte")
  #expect(invitation.email == "bruno@rentivo.com.br")
}

@MainActor
@Test func liveCreateOrganizationFollowsUpWithAPatchWhenTheDraftIncludesPix() async throws {
  // Regression test: OrganizationCreateRequest only accepts `name`, so PIX collected on the
  // creation form used to be silently dropped.
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: organizationSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  let draft = OrganizationDraft(
    name: "Nova Org",
    pix: PixConfiguration(key: "chave-pix", merchantName: "Nova Org", merchantCity: "Sao Paulo")
  )
  let organization = try await store.createOrganization(draft)

  #expect(organization.id == OrganizationID(rawValue: "organization-2"))
  #expect(organization.pix == PixConfiguration(key: "chave-pix", merchantName: "Nova Org", merchantCity: "Sao Paulo"))
}

private func organizationSession() -> URLSession {
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [OrganizationURLProtocol.self]
  return URLSession(configuration: configuration)
}

private final class OrganizationURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch (request.httpMethod, path) {
    case ("GET", "/api/v1/auth/session"):
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case ("GET", "/api/v1/organizations"):
      body = #"{"items":[{"uuid":"organization-1","name":"Horizonte","enforce_mfa":false,"current_role":"admin","capabilities":{"can_manage":true,"can_invite":true,"can_create_billing":true,"can_view_billing_stats":true}}]}"#
    case ("GET", "/api/v1/organizations/organization-1"):
      body = #"{"uuid":"organization-1","name":"Horizonte","enforce_mfa":false,"current_role":"admin","capabilities":{"can_manage":true,"can_invite":true,"can_create_billing":true,"can_view_billing_stats":true},"settings":null,"members":[{"user_id":7,"email":"ana@rentivo.com.br","role":"admin"},{"user_id":11,"email":"bruno@rentivo.com.br","role":"viewer"}]}"#
    case ("POST", "/api/v1/organizations/organization-1/invites"):
      body = #"{"uuid":"invite-1","invited_email":"bruno@rentivo.com.br","role":"viewer","status":"pending"}"#
    case ("POST", "/api/v1/organizations"):
      body = #"{"uuid":"organization-2","name":"Nova Org","enforce_mfa":false,"current_role":"admin","capabilities":{"can_manage":true,"can_invite":true,"can_create_billing":true,"can_view_billing_stats":true}}"#
    case ("PATCH", "/api/v1/organizations/organization-2"):
      body = #"{"uuid":"organization-2","name":"Nova Org","enforce_mfa":false,"current_role":"admin","capabilities":{"can_manage":true,"can_invite":true,"can_create_billing":true,"can_view_billing_stats":true},"settings":{"pix_key":"chave-pix","pix_merchant_name":"Nova Org","pix_merchant_city":"Sao Paulo"},"members":[{"user_id":7,"email":"ana@rentivo.com.br","role":"admin"}]}"#
    default:
      body = #"{"detail":"Endpoint inesperado: \#(request.httpMethod ?? "?") \#(path ?? "nil")"}"#
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 200, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}
