import Foundation
import Testing
@testable import RentivoCore

@MainActor
@Test func liveOrganizationListHydratesMembersForTheOrganizationCardCount() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: organizationSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  let organization = try #require(try await store.listOrganizations().first)

  #expect(organization.members.map(\.userID) == [7, 11])
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
    switch path {
    case "/api/v1/auth/session":
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case "/api/v1/organizations":
      body = #"{"items":[{"uuid":"organization-1","name":"Horizonte","enforce_mfa":false,"current_role":"admin","capabilities":{"can_manage":true,"can_invite":true,"can_create_billing":true,"can_view_billing_stats":true}}]}"#
    case "/api/v1/organizations/organization-1":
      body = #"{"uuid":"organization-1","name":"Horizonte","enforce_mfa":false,"current_role":"admin","capabilities":{"can_manage":true,"can_invite":true,"can_create_billing":true,"can_view_billing_stats":true},"settings":null,"members":[{"user_id":7,"email":"ana@rentivo.com.br","role":"admin"},{"user_id":11,"email":"bruno@rentivo.com.br","role":"viewer"}]}"#
    default:
      body = #"{"detail":"Endpoint inesperado: \#(path ?? "nil")"}"#
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
