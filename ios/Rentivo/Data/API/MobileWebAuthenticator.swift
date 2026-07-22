// The package target is also compiled by the macOS test runner. The actual
// authorization session is available only to the iOS app target.
#if canImport(UIKit)
import AuthenticationServices
import UIKit

@MainActor
final class MobileWebAuthenticator: NSObject, ASWebAuthenticationPresentationContextProviding {
  private var session: ASWebAuthenticationSession?

  func authorize() async throws -> String {
    let state = UUID().uuidString
    var components = URLComponents(url: LiveAPIClient.productionURL.appending(path: "/login"), resolvingAgainstBaseURL: false)!
    components.queryItems = [URLQueryItem(name: "mobile_state", value: state)]
    let url = components.url!
    return try await withCheckedThrowingContinuation { continuation in
      let session = ASWebAuthenticationSession(url: url, callbackURLScheme: "rentivo") { [weak self] callbackURL, error in
        self?.session = nil
        if let error { continuation.resume(throwing: error); return }
        guard let callbackURL,
          let callback = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false),
          callback.scheme == "rentivo", callback.host == "auth",
          callback.queryItems?.first(where: { $0.name == "state" })?.value == state,
          let code = callback.queryItems?.first(where: { $0.name == "code" })?.value,
          !code.isEmpty
        else { continuation.resume(throwing: LiveAPIError.invalidResponse); return }
        continuation.resume(returning: code)
      }
      session.presentationContextProvider = self
      session.prefersEphemeralWebBrowserSession = true
      self.session = session
      session.start()
    }
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
}
#endif
