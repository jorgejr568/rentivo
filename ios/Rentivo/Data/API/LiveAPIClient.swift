import Foundation

struct LiveSession: Sendable {
  let accessToken: String
  let profile: UserProfile
}

enum LiveAPIError: LocalizedError, Sendable {
  case server(message: String)
  case invalidResponse

  var errorDescription: String? {
    switch self {
    case .server(let message): message
    case .invalidResponse: "Não foi possível interpretar a resposta do Rentivo."
    }
  }
}

actor LiveAPIClient {
  static let productionURL = URL(string: "https://rentivo.com.br")!

  private let session: URLSession
  private var accessToken: String?

  init(session: URLSession = .shared) {
    self.session = session
  }

  func login(email: String, password: String) async throws -> LiveSession {
    let request = LoginRequest(
      email: email,
      password: password,
      credentialTransport: "body",
      turnstileToken: ""
    )
    let response: LoginResponse = try await send(
      path: "/api/v1/auth/login",
      method: "POST",
      body: request,
      token: nil
    )
    guard response.credentialTransport == "body", let accessToken = response.accessToken else {
      throw LiveAPIError.server(message: "O servidor solicitou uma etapa adicional de autenticação.")
    }
    let profile: ProfileResponse = try await send(
      path: "/api/v1/profile",
      method: "GET",
      body: Optional<String>.none,
      token: accessToken
    )
    self.accessToken = accessToken
    return LiveSession(
      accessToken: accessToken,
      profile: UserProfile(id: response.bootstrap?.user.id ?? 0, email: profile.email)
    )
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
    return LiveSession(accessToken: accessToken, profile: UserProfile(id: user.id, email: user.email))
  }

  func request(
    path: String, method: String = "GET", body: Data? = nil,
    contentType: String = "application/json"
  ) async throws -> Data {
    guard let accessToken else {
      throw LiveAPIError.server(message: "Sua sessão expirou. Entre novamente para continuar.")
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
    guard (200..<300).contains(http.statusCode) else {
      let problem = try? JSONDecoder().decode(ProblemResponse.self, from: data)
      throw LiveAPIError.server(message: problem?.detail ?? "Não foi possível concluir a solicitação.")
    }
    return data
  }

  func logout() { accessToken = nil }

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
      throw LiveAPIError.server(message: problem?.detail ?? "Não foi possível concluir a solicitação.")
    }
    do {
      return try JSONDecoder().decode(Response.self, from: data)
    } catch {
      throw LiveAPIError.invalidResponse
    }
  }
}

private struct LoginRequest: Encodable {
  let email: String
  let password: String
  let credentialTransport: String
  let turnstileToken: String

  enum CodingKeys: String, CodingKey {
    case email, password
    case credentialTransport = "credential_transport"
    case turnstileToken = "turnstile_token"
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
