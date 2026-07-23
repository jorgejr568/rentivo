import Foundation
import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

// MARK: - LiveAPIClient behavior
//
// These exercise the `Data` layer only (LiveAPIClient + CredentialStore), so
// they compile and run both under `swift test` (the RentivoCore SPM package,
// which excludes App/Features) and under the Xcode-hosted RentivoTests
// target. This extends the stubbed-URLProtocol pattern from
// `LiveSessionTests.swift` to cover the 401-during-a-request path.

@Test func requestClearsStoredCredentialAndThrowsSessionExpiredOn401() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: expiringSession(), credentials: credentials)

  _ = try #require(try await client.restoreSession())
  #expect(await credentials.readAccessToken() == "stored-token")

  do {
    _ = try await client.request(path: "/api/v1/billings")
    Issue.record("Expected the stubbed 401 response to throw")
  } catch let error as LiveAPIError {
    guard case .sessionExpired = error else {
      Issue.record("Expected .sessionExpired, got \(error)")
      return
    }
  }

  #expect(await credentials.readAccessToken() == nil)
}

@Test func downloadClearsStoredCredentialAndThrowsSessionExpiredOn401() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: expiringSession(), credentials: credentials)

  _ = try #require(try await client.restoreSession())

  do {
    _ = try await client.download(path: "/api/v1/billings/b/bills/1/invoice", filename: "fatura")
    Issue.record("Expected the stubbed 401 response to throw")
  } catch let error as LiveAPIError {
    guard case .sessionExpired = error else {
      Issue.record("Expected .sessionExpired, got \(error)")
      return
    }
  }

  #expect(await credentials.readAccessToken() == nil)
}

@Test func requestWithoutAStoredTokenThrowsSessionExpiredImmediately() async throws {
  let credentials = MemoryCredentialStore()
  let client = LiveAPIClient(session: expiringSession(), credentials: credentials)

  do {
    _ = try await client.request(path: "/api/v1/billings")
    Issue.record("Expected the missing token to throw")
  } catch let error as LiveAPIError {
    guard case .sessionExpired = error else {
      Issue.record("Expected .sessionExpired, got \(error)")
      return
    }
  }
}

private func expiringSession() -> URLSession {
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [ExpiringSessionURLProtocol.self]
  return URLSession(configuration: configuration)
}

/// Returns a valid `/api/v1/auth/session` bootstrap once (so tests can first
/// establish an access token via `restoreSession()`), then 401s every other
/// path — simulating a token that expired server-side after login.
private final class ExpiringSessionURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let isSessionRestore = request.url?.path == "/api/v1/auth/session"
    let statusCode = isSessionRestore ? 200 : 401
    let body =
      isSessionRestore
      ? #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
      : #"{"detail":"Sessão expirada."}"#
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

#if !canImport(RentivoCore)
  // MARK: - AppModel reaction
  //
  // `AppModel` lives under `App/`, which the RentivoCore SPM package excludes
  // (see Package.swift), so it is only visible when this file is compiled as
  // part of the full "Rentivo" app module (the Xcode-hosted RentivoTests
  // target). Guarded out entirely under `swift test`.

  @MainActor
  @Test func sessionExpiryNotificationSignsOutAndShowsPTBRNotice() async throws {
    let credentials = MemoryCredentialStore(token: "stored-token")
    let client = LiveAPIClient(session: expiringSession(), credentials: credentials)
    let store = APIRentivoStore(client: client)
    let app = AppModel(dependencies: .live(store: store))

    await app.restoreSessionIfNeeded()
    guard case .authenticated = app.session else {
      Issue.record("Expected restoreSessionIfNeeded to authenticate from the stubbed session response")
      return
    }

    do {
      _ = try await store.listBillings()
      Issue.record("Expected the stubbed 401 response to throw")
    } catch {
      // Expected: the stubbed billings call 401s.
    }

    await waitUntilAnonymous(app)

    guard case .anonymous = app.session else {
      Issue.record("Expected the session to become anonymous after the token expired")
      return
    }
    #expect(app.notice?.message == "Sua sessão expirou. Entre novamente para continuar.")
  }

  @MainActor
  private func waitUntilAnonymous(_ app: AppModel, attempts: Int = 200) async {
    for _ in 0..<attempts {
      if case .anonymous = app.session { return }
      try? await Task.sleep(nanoseconds: 5_000_000)
    }
  }
#endif
