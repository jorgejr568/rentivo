import Foundation
import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

// MARK: - `LiveAPIClient.request` non-2xx error mapping
//
// Extends the stubbed-URLProtocol pattern from `LiveSessionTests`/`SessionExpiryTests` to cover
// the generic (non-401) failure path: a server-supplied `detail` message must surface verbatim,
// and an undecodable error body must fall back to a fixed PT-BR message, in both cases carrying
// the original HTTP status code. Swift Testing runs `@Test` functions concurrently by default, so
// (matching the rest of this suite, see `APIRentivoStoreEncodingTests`) each scenario below gets
// its own `URLProtocol` subclass with its own static state instead of sharing one across tests.

@Test func requestSurfacesServerProblemDetailAndStatusCodeOnNon2xxResponse() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [ProblemDetailURLProtocol.self]
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  _ = try #require(try await client.restoreSession())

  do {
    _ = try await client.request(path: "/api/v1/billings")
    Issue.record("Expected the stubbed 422 response to throw")
  } catch let error as LiveAPIError {
    guard case .server(let message, let statusCode) = error else {
      Issue.record("Expected .server, got \(error)")
      return
    }
    #expect(message == "Chave PIX inválida.")
    #expect(statusCode == 422)
  }
}

private final class ProblemDetailURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let isSessionRestore = request.url?.path == "/api/v1/auth/session"
    let statusCode = isSessionRestore ? 200 : 422
    let body =
      isSessionRestore
      ? #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
      : #"{"detail":"Chave PIX inválida."}"#
    let response = HTTPURLResponse(
      url: request.url!, statusCode: statusCode, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

@Test func requestFallsBackToGenericMessageWhenErrorBodyIsNotDecodable() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [UndecodableErrorBodyURLProtocol.self]
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  _ = try #require(try await client.restoreSession())

  do {
    _ = try await client.request(path: "/api/v1/billings")
    Issue.record("Expected the stubbed 500 response to throw")
  } catch let error as LiveAPIError {
    guard case .server(let message, let statusCode) = error else {
      Issue.record("Expected .server, got \(error)")
      return
    }
    #expect(message == "Não foi possível concluir a solicitação.")
    #expect(statusCode == 500)
  }
}

private final class UndecodableErrorBodyURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let isSessionRestore = request.url?.path == "/api/v1/auth/session"
    let statusCode = isSessionRestore ? 200 : 500
    let body =
      isSessionRestore
      ? #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
      : "internal server error, not json"
    let response = HTTPURLResponse(
      url: request.url!, statusCode: statusCode, httpVersion: nil,
      headerFields: ["Content-Type": "text/plain"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

// MARK: - `LiveAPIClient.download` status handling

@Test func downloadMapsNon2xxNon401ResponseToAFixedFileMessage() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [DownloadForbiddenURLProtocol.self]
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  _ = try #require(try await client.restoreSession())

  do {
    _ = try await client.download(path: "/api/v1/billings/b/bills/1/invoice", filename: "fatura")
    Issue.record("Expected the stubbed 403 response to throw")
  } catch let error as LiveAPIError {
    guard case .server(let message, let statusCode) = error else {
      Issue.record("Expected .server, got \(error)")
      return
    }
    // `download()` never attempts to decode a `ProblemResponse` (unlike `request()`); every
    // non-2xx/non-401 status collapses to this one fixed message, and no status code is kept.
    #expect(message == "Não foi possível baixar o arquivo.")
    #expect(statusCode == nil)
  }
}

private final class DownloadForbiddenURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let isSessionRestore = request.url?.path == "/api/v1/auth/session"
    let statusCode = isSessionRestore ? 200 : 403
    let body =
      isSessionRestore
      ? #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
      : #"{"detail":"Acesso negado, mas ignorado pelo download."}"#
    let response = HTTPURLResponse(
      url: request.url!, statusCode: statusCode, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

@Test func downloadAppendsExtensionFromContentTypeWhenFilenameHasNoDot() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [DownloadJPEGURLProtocol.self]
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  _ = try #require(try await client.restoreSession())

  let file = try await client.download(
    path: "/api/v1/billings/b/attachments/1", filename: "comprovante", mediaType: "application/pdf"
  )

  #expect(file.filename == "comprovante.jpg")
  #expect(file.mediaType == "image/jpeg")
  #expect(try Data(contentsOf: file.fileURL) == Data([0xFF, 0xD8, 0xFF]))
  #expect(file.fileURL.pathExtension == "jpg")
}

private final class DownloadJPEGURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let isSessionRestore = request.url?.path == "/api/v1/auth/session"
    if isSessionRestore {
      let response = HTTPURLResponse(
        url: request.url!, statusCode: 200, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"]
      )!
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(
        self, didLoad: Data(#"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#.utf8)
      )
      client?.urlProtocolDidFinishLoading(self)
      return
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 200, httpVersion: nil,
      headerFields: ["Content-Type": "image/jpeg"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data([0xFF, 0xD8, 0xFF]))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

@Test func downloadPreservesAnAlreadyExtensionedFilenameRegardlessOfContentType() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [DownloadPDFURLProtocol.self]
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  _ = try #require(try await client.restoreSession())

  let file = try await client.download(
    path: "/api/v1/billings/b/bills/1/invoice", filename: "fatura-julho.pdf"
  )

  #expect(file.filename == "fatura-julho.pdf")
  #expect(file.fileURL.pathExtension == "pdf")
}

private final class DownloadPDFURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let isSessionRestore = request.url?.path == "/api/v1/auth/session"
    if isSessionRestore {
      let response = HTTPURLResponse(
        url: request.url!, statusCode: 200, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"]
      )!
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(
        self, didLoad: Data(#"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#.utf8)
      )
      client?.urlProtocolDidFinishLoading(self)
      return
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 200, httpVersion: nil,
      headerFields: ["Content-Type": "application/pdf"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data("%PDF-1.4".utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

// MARK: - Transport error mapping (timeout / offline)
//
// A stalled request (e.g. the iOS Simulator's flaky HTTP/3 path, or a real device losing
// connectivity) surfaces as a `URLError` from `URLSession`. Those must be translated into a
// `LiveAPIError` carrying a clear, actionable PT-BR message — otherwise the login screen (and the
// app-wide `DemoError` mapping) fall through to a generic message with no "check your connection /
// try again" signal. Each scenario uses its own `URLProtocol` subclass (Swift Testing runs tests
// concurrently).

@Test func exchangeMapsARequestTimeoutToARetryableLiveAPIError() async throws {
  let credentials = MemoryCredentialStore()
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [TimeoutURLProtocol.self]
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)

  do {
    _ = try await client.exchangeMobileAuthorization(code: "any-code")
    Issue.record("Expected a timeout to throw")
  } catch let error as LiveAPIError {
    guard case .server(let message, _) = error else {
      Issue.record("Expected .server, got \(error)")
      return
    }
    #expect(message.contains("demorou"))
  }
}

@Test func exchangeMapsAnOfflineErrorToAConnectivityLiveAPIError() async throws {
  let credentials = MemoryCredentialStore()
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [OfflineURLProtocol.self]
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)

  do {
    _ = try await client.exchangeMobileAuthorization(code: "any-code")
    Issue.record("Expected an offline error to throw")
  } catch let error as LiveAPIError {
    guard case .server(let message, _) = error else {
      Issue.record("Expected .server, got \(error)")
      return
    }
    #expect(message.contains("conexão"))
  }
}

private final class TimeoutURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() { client?.urlProtocol(self, didFailWithError: URLError(.timedOut)) }
  override func stopLoading() {}
}

private final class OfflineURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() { client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet)) }
  override func stopLoading() {}
}
