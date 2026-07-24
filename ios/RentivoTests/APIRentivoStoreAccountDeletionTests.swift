import Foundation
import Testing
@testable import RentivoCore

@MainActor
@Test func deleteAccountPostsPasswordAndClearsCredentials() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: deleteAccountSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  try await store.deleteAccount(password: "s3cret")

  #expect(DeleteAccountURLProtocol.recordedPath == "/api/v1/security/delete-account")
  #expect(DeleteAccountURLProtocol.recordedMethod == "POST")
  let body = try #require(DeleteAccountURLProtocol.recordedBody)
  let json = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
  #expect(json["password"] as? String == "s3cret")
  #expect(await credentials.readAccessToken() == nil)
}

private func deleteAccountSession() -> URLSession {
  DeleteAccountURLProtocol.reset()
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [DeleteAccountURLProtocol.self]
  return URLSession(configuration: configuration)
}

private final class DeleteAccountURLProtocol: URLProtocol, @unchecked Sendable {
  nonisolated(unsafe) static var recordedPath: String?
  nonisolated(unsafe) static var recordedMethod: String?
  nonisolated(unsafe) static var recordedBody: Data?

  static func reset() {
    recordedPath = nil
    recordedMethod = nil
    recordedBody = nil
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let statusCode: Int
    let body: Data
    switch path {
    case "/api/v1/auth/session":
      statusCode = 200
      body = Data(#"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#.utf8)
    case "/api/v1/security/delete-account":
      Self.recordedPath = path
      Self.recordedMethod = request.httpMethod
      Self.recordedBody = Self.requestBody(from: request)
      statusCode = 204
      body = Data()
    default:
      statusCode = 500
      body = Data(#"{"detail":"Endpoint inesperado."}"#.utf8)
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: statusCode, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func requestBody(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let bufferSize = 1024
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let read = stream.read(buffer, maxLength: bufferSize)
      if read <= 0 { break }
      data.append(buffer, count: read)
    }
    return data
  }
}
