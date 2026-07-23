import Foundation
import Testing
@testable import RentivoCore

@MainActor
@Test func liveProfileLoadsPixFieldsFromTheSecuritySummaryEndpoint() async throws {
  // Regression test: GET /api/v1/profile only returns `CurrentProfileResponse` ({email}); the
  // pix fields must come from GET /api/v1/security's `profile` (a full `ProfileResponse`).
  // Every profile load used to fail because RemoteProfile required pix fields the endpoint omits.
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: profileSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  let profile = try await store.profile()

  #expect(profile.email == "ana@rentivo.com.br")
  #expect(profile.pix == PixConfiguration(key: "chave-abc", merchantName: "Ana", merchantCity: "Sao Paulo"))
}

@MainActor
@Test func liveSecuritySummaryDecodesFractionalSecondTimestamps() async throws {
  // Regression test: the old `ISO8601DateFormatter()` had no fractional-seconds support and fell
  // back to `.distantPast` on failure, so backend timestamps with microseconds decoded as year 1.
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: profileSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  let summary = try await store.securitySummary()

  let passkey = try #require(summary.passkeys.first)
  let year = Calendar(identifier: .gregorian).component(.year, from: passkey.createdAt)
  #expect(year == 2026)
  #expect(passkey.createdAt != .distantPast)
}

@MainActor
@Test func liveListAPIKeysHidesRevokedKeysLikeTheMock() async throws {
  // Regression test: the server returns revoked integration keys too; the mock filters them out
  // and the live store must match.
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: profileSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  let keys = try await store.listAPIKeys()

  #expect(keys.map(\.name) == ["Ativa"])
}

private func profileSession() -> URLSession {
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [ProfileURLProtocol.self]
  return URLSession(configuration: configuration)
}

private final class ProfileURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch path {
    case "/api/v1/auth/session":
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case "/api/v1/security":
      body = #"""
      {
        "profile": {"email":"ana@rentivo.com.br","pix_key":"chave-abc","pix_merchant_name":"Ana","pix_merchant_city":"Sao Paulo"},
        "totp": {"enabled": true, "recovery_codes_remaining": 5},
        "mfa": {},
        "passkeys": [
          {"uuid":"passkey-1","name":"iPhone de Ana","created_at":"2026-07-20T10:15:30.123456+00:00","last_used_at": null}
        ]
      }
      """#
    case "/api/v1/api-keys":
      body = #"""
      {"items": [
        {"uuid":"key-1","name":"Ativa","hint":"rntv-v1-ab••cd","scopes":["profile:read"],"grants":[{"resource_type":"user","resource_id":"personal","available":true}],"expires_at":"2026-12-31T23:59:59.000000+00:00","last_used_at": null,"created_at":"2026-01-01T00:00:00.000000+00:00","revoked_at": null},
        {"uuid":"key-2","name":"Revogada","hint":"rntv-v1-ef••gh","scopes":["profile:read"],"grants":[{"resource_type":"user","resource_id":"personal","available":true}],"expires_at":"2026-12-31T23:59:59.000000+00:00","last_used_at": null,"created_at":"2026-01-01T00:00:00.000000+00:00","revoked_at":"2026-02-01T00:00:00.000000+00:00"}
      ]}
      """#
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
