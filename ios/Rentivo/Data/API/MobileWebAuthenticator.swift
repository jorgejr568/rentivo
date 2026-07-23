import Foundation

enum MobileWebAuthenticationFlow {
  static func authorizationURL(baseURL: URL, state: String) -> URL {
    url(baseURL: baseURL, path: "/login", queryItem: URLQueryItem(name: "mobile_state", value: state))
  }

  static func logoutURL(baseURL: URL, state: String) -> URL {
    url(baseURL: baseURL, path: "/mobile-logout", queryItem: URLQueryItem(name: "state", value: state))
  }

  static func authorizationCode(from callbackURL: URL, expectedState: String) -> String? {
    guard let callback = callback(callbackURL, path: "/callback", expectedState: expectedState),
      let code = callback.queryItems?.first(where: { $0.name == "code" })?.value,
      !code.isEmpty
    else { return nil }
    return code
  }

  static func isLogoutCallback(_ callbackURL: URL, expectedState: String) -> Bool {
    callback(callbackURL, path: "/logout", expectedState: expectedState) != nil
  }

  private static func url(baseURL: URL, path: String, queryItem: URLQueryItem) -> URL {
    var components = URLComponents(
      url: baseURL.appending(path: path), resolvingAgainstBaseURL: false)!
    components.queryItems = [queryItem]
    return components.url!
  }

  private static func callback(
    _ callbackURL: URL, path: String, expectedState: String
  ) -> URLComponents? {
    guard let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false),
      components.scheme == "rentivo",
      components.host == "auth",
      components.path == path,
      components.queryItems?.first(where: { $0.name == "state" })?.value == expectedState
    else { return nil }
    return components
  }
}

// The package target is also compiled by the macOS test runner. The actual
// browser authentication session is available only to the iOS app target.
#if canImport(UIKit)
import AuthenticationServices
import UIKit

@MainActor
final class MobileWebAuthenticator: NSObject, ASWebAuthenticationPresentationContextProviding {
  private var session: ASWebAuthenticationSession?

  func authorize() async throws -> String {
    let state = UUID().uuidString
    let url = MobileWebAuthenticationFlow.authorizationURL(
      baseURL: LiveAPIClient.productionURL, state: state)
    return try await withCheckedThrowingContinuation { continuation in
      let webSession = ASWebAuthenticationSession(
        url: url, callbackURLScheme: "rentivo"
      ) { callbackURL, error in
        // The completion handler is invoked by AuthenticationServices off the
        // main actor, but it needs to mutate `self.session` (main-actor
        // state). Hop explicitly instead of touching it from this closure.
        Task { @MainActor [self] in
          session = nil
          if let error {
            continuation.resume(throwing: error)
            return
          }
          guard let callbackURL,
            let code = MobileWebAuthenticationFlow.authorizationCode(
              from: callbackURL, expectedState: state)
          else {
            continuation.resume(throwing: LiveAPIError.invalidResponse)
            return
          }
          continuation.resume(returning: code)
        }
      }
      configure(webSession)
      guard webSession.start() else {
        session = nil
        continuation.resume(throwing: LiveAPIError.invalidResponse)
        return
      }
    }
  }

  func logout() async throws {
    let state = UUID().uuidString
    let url = MobileWebAuthenticationFlow.logoutURL(
      baseURL: LiveAPIClient.productionURL, state: state)
    try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
      let webSession = ASWebAuthenticationSession(
        url: url, callbackURLScheme: "rentivo"
      ) { callbackURL, error in
        // Same as `authorize()`: hop to the main actor before touching
        // `self.session`, since this completion runs off the main actor.
        Task { @MainActor [self] in
          session = nil
          if let error {
            continuation.resume(throwing: error)
            return
          }
          guard let callbackURL,
            MobileWebAuthenticationFlow.isLogoutCallback(callbackURL, expectedState: state)
          else {
            continuation.resume(throwing: LiveAPIError.invalidResponse)
            return
          }
          continuation.resume()
        }
      }
      configure(webSession)
      guard webSession.start() else {
        session = nil
        continuation.resume(throwing: LiveAPIError.invalidResponse)
        return
      }
    }
  }

  /// Whether `error` represents the user dismissing the authentication sheet
  /// themselves, as opposed to a genuine failure. Shared by `AppModel`
  /// (best-effort browser logout) and the login screen (silence expected
  /// cancellations instead of surfacing an English system message).
  static func isUserCancellation(_ error: Error) -> Bool {
    (error as? ASWebAuthenticationSessionError)?.code == .canceledLogin
  }

  private func configure(_ webSession: ASWebAuthenticationSession) {
    webSession.presentationContextProvider = self
    // Login and logout must use the same shared browser cookie jar as the website.
    webSession.prefersEphemeralWebBrowserSession = false
    session = webSession
  }

  func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
    UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .flatMap(\.windows)
      .first(where: \.isKeyWindow) ?? UIWindow()
  }
}
#else
@MainActor
final class MobileWebAuthenticator {
  func authorize() async throws -> String {
    throw LiveAPIError.server(message: "A autenticação pelo navegador requer o app para iOS.")
  }

  func logout() async throws {
    throw LiveAPIError.server(message: "A saída pelo navegador requer o app para iOS.")
  }
}
#endif
