import Foundation

struct LiveSession: Sendable {
  let accessToken: String
  let profile: UserProfile
}

enum LiveAPIError: LocalizedError, Sendable {
  case server(message: String, statusCode: Int? = nil)
  case invalidResponse
  case sessionExpired

  var errorDescription: String? {
    switch self {
    case .server(let message, _): message
    case .invalidResponse: "Não foi possível interpretar a resposta do Rentivo."
    case .sessionExpired: "Sua sessão expirou. Entre novamente para continuar."
    }
  }

  var statusCode: Int? {
    guard case let .server(_, statusCode) = self else { return nil }
    return statusCode
  }
}

extension Notification.Name {
  /// Posted whenever `LiveAPIClient` observes a 401 response (or discovers it
  /// has no stored token) while serving an authenticated request. `AppModel`
  /// observes this to move the app back to the anonymous state; posting is
  /// harmless if nothing is listening (e.g. before the app has authenticated).
  static let liveAPIClientSessionExpired = Notification.Name("LiveAPIClient.sessionExpired")
}

actor LiveAPIClient {
  static let productionURL = URL(string: "https://rentivo.com.br")!

  private let session: URLSession
  private let credentials: any CredentialStore
  private var accessToken: String?

  init(session: URLSession = .shared, credentials: any CredentialStore) {
    self.session = session
    self.credentials = credentials
  }

  func exchangeMobileAuthorization(code: String) async throws -> LiveSession {
    let response: LoginResponse = try await send(
      path: "/api/v1/auth/mobile/exchange", method: "POST",
      body: MobileAuthorizationExchangeRequest(authorizationCode: code), token: nil
    )
    guard response.credentialTransport == "body", let accessToken = response.accessToken,
      let user = response.bootstrap?.user
    else { throw LiveAPIError.invalidResponse }
    self.accessToken = accessToken
    try await credentials.saveAccessToken(accessToken)
    return LiveSession(accessToken: accessToken, profile: UserProfile(id: user.id, email: user.email))
  }

  func restoreSession() async throws -> LiveSession? {
    guard let storedToken = try await credentials.readAccessToken() else { return nil }
    do {
      let response: SessionResponse = try await send(
        path: "/api/v1/auth/session", method: "GET", body: Optional<String>.none, token: storedToken
      )
      accessToken = storedToken
      return LiveSession(
        accessToken: storedToken,
        profile: UserProfile(id: response.bootstrap.user.id, email: response.bootstrap.user.email)
      )
    } catch let error as LiveAPIError where error.statusCode == 401 {
      await invalidateSession()
      return nil
    }
  }

  func request(
    path: String, method: String = "GET", body: Data? = nil,
    contentType: String = "application/json"
  ) async throws -> Data {
    guard let accessToken else {
      throw LiveAPIError.sessionExpired
    }
    var request = URLRequest(url: Self.productionURL.appending(path: path))
    request.httpMethod = method
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
    if let body {
      request.setValue(contentType, forHTTPHeaderField: "Content-Type")
      request.httpBody = body
    }
    let (data, response) = try await session.data(for: request)
    guard let http = response as? HTTPURLResponse else { throw LiveAPIError.invalidResponse }
    if http.statusCode == 401 {
      await invalidateSession()
      throw LiveAPIError.sessionExpired
    }
    guard (200..<300).contains(http.statusCode) else {
      let problem = try? JSONDecoder().decode(ProblemResponse.self, from: data)
      throw LiveAPIError.server(
        message: problem?.detail ?? "Não foi possível concluir a solicitação.", statusCode: http.statusCode
      )
    }
    return data
  }

  func logout() async {
    accessToken = nil
    try? await credentials.deleteAccessToken()
  }

  /// Clears the in-memory token and the persisted credential, then notifies
  /// any observers (see `AppModel`) that the session is no longer valid.
  private func invalidateSession() async {
    accessToken = nil
    try? await credentials.deleteAccessToken()
    NotificationCenter.default.post(name: .liveAPIClientSessionExpired, object: nil)
  }

  func download(path: String, filename: String, mediaType: String = "application/pdf") async throws -> DownloadedFile {
    guard let accessToken else {
      throw LiveAPIError.sessionExpired
    }
    var request = URLRequest(url: Self.productionURL.appending(path: path))
    request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
    request.setValue(mediaType, forHTTPHeaderField: "Accept")
    let (data, response) = try await session.data(for: request)
    guard let http = response as? HTTPURLResponse else { throw LiveAPIError.invalidResponse }
    if http.statusCode == 401 {
      await invalidateSession()
      throw LiveAPIError.sessionExpired
    }
    guard (200..<300).contains(http.statusCode) else {
      throw LiveAPIError.server(message: "Não foi possível baixar o arquivo.")
    }
    let responseMediaType = (http.value(forHTTPHeaderField: "Content-Type") ?? mediaType)
      .split(separator: ";", maxSplits: 1).first.map(String.init) ?? mediaType
    let resolvedFilename = filename.contains(".")
      ? filename
      : "\(filename).\(fileExtension(for: responseMediaType))"
    let destination = FileManager.default.temporaryDirectory
      .appendingPathComponent(UUID().uuidString)
      .appendingPathExtension((resolvedFilename as NSString).pathExtension)
    try data.write(to: destination, options: .atomic)
    return DownloadedFile(fileURL: destination, filename: resolvedFilename, mediaType: responseMediaType)
  }

  private func fileExtension(for mediaType: String) -> String {
    switch mediaType.lowercased() {
    case "application/pdf": "pdf"
    case "image/jpeg": "jpg"
    case "image/png": "png"
    case "image/heic": "heic"
    case "text/plain": "txt"
    default: "bin"
    }
  }

  private func send<Body: Encodable, Response: Decodable>(
    path: String,
    method: String,
    body: Body?,
    token: String?
  ) async throws -> Response {
    var request = URLRequest(url: Self.productionURL.appending(path: path))
    request.httpMethod = method
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    if let token {
      request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }
    if let body {
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
      request.httpBody = try JSONEncoder().encode(body)
    }
    let (data, response) = try await session.data(for: request)
    guard let http = response as? HTTPURLResponse else { throw LiveAPIError.invalidResponse }
    guard (200..<300).contains(http.statusCode) else {
      let problem = try? JSONDecoder().decode(ProblemResponse.self, from: data)
      throw LiveAPIError.server(
        message: problem?.detail ?? "Não foi possível concluir a solicitação.", statusCode: http.statusCode
      )
    }
    do {
      return try JSONDecoder().decode(Response.self, from: data)
    } catch {
      throw LiveAPIError.invalidResponse
    }
  }
}

private struct LoginResponse: Decodable {
  let credentialTransport: String
  let accessToken: String?
  let bootstrap: BootstrapResponse?

  enum CodingKeys: String, CodingKey {
    case credentialTransport = "credential_transport"
    case accessToken = "access_token"
    case bootstrap
  }
}

private struct SessionResponse: Decodable {
  let bootstrap: BootstrapResponse
}

private struct BootstrapResponse: Decodable {
  let user: BootstrapUser
}

private struct BootstrapUser: Decodable {
  let id: Int
  let email: String
}

private struct MobileAuthorizationExchangeRequest: Encodable {
  let authorizationCode: String
  enum CodingKeys: String, CodingKey { case authorizationCode = "authorization_code" }
}

private struct ProfileResponse: Decodable {
  let email: String
}

private struct ProblemResponse: Decodable {
  let detail: String?
}
