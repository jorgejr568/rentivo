import Foundation
import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

@Test func storedBearerTokenRestoresProfileAndDeletesExpiredToken() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: session(statusCode: 200, body: """
  {"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}
  """), credentials: credentials)

  let restored = try await client.restoreSession()

  #expect(restored?.profile.id == 7)
  #expect(restored?.profile.email == "ana@rentivo.com.br")

  let expiredCredentials = MemoryCredentialStore(token: "expired-token")
  let expiredClient = LiveAPIClient(session: session(statusCode: 401, body: """
  {"detail":"Credencial inválida ou expirada."}
  """), credentials: expiredCredentials)

  #expect(try await expiredClient.restoreSession() == nil)
  #expect(await expiredCredentials.readAccessToken() == nil)
}

private func session(statusCode: Int, body: String) -> URLSession {
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [LiveSessionURLProtocol.self]
  LiveSessionURLProtocol.statusCode = statusCode
  LiveSessionURLProtocol.body = Data(body.utf8)
  return URLSession(configuration: configuration)
}

private final class LiveSessionURLProtocol: URLProtocol, @unchecked Sendable {
  nonisolated(unsafe) static var statusCode = 200
  nonisolated(unsafe) static var body = Data()

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let response = HTTPURLResponse(
      url: request.url!, statusCode: Self.statusCode, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Self.body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}
