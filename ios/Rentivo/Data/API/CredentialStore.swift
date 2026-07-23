import Foundation
import Security

public protocol CredentialStore: Sendable {
  func readAccessToken() async throws -> String?
  func saveAccessToken(_ token: String) async throws
  func deleteAccessToken() async throws
}

public enum CredentialStoreError: Error, LocalizedError, Sendable {
  case keychain(status: Int32)

  public var errorDescription: String? {
    "Não foi possível acessar a sessão segura neste dispositivo."
  }
}

public actor MemoryCredentialStore: CredentialStore {
  private var token: String?

  public init(token: String? = nil) {
    self.token = token
  }

  public func readAccessToken() -> String? { token }
  public func saveAccessToken(_ token: String) { self.token = token }
  public func deleteAccessToken() { token = nil }
}

public actor KeychainCredentialStore: CredentialStore {
  private let service: String
  private let account = "rentivo.access-token"

  public init(service: String = Bundle.main.bundleIdentifier ?? "app.rentivo.demo") {
    self.service = service
  }

  public func readAccessToken() throws -> String? {
    var query = baseQuery
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne

    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound { return nil }
    guard status == errSecSuccess, let data = result as? Data,
      let token = String(data: data, encoding: .utf8)
    else { throw CredentialStoreError.keychain(status: status) }
    return token
  }

  public func saveAccessToken(_ token: String) throws {
    let data = Data(token.utf8)
    // Re-assert the accessibility class on every update: an item created
    // before this attribute was enforced (or by a future laxer write) would
    // otherwise keep whatever class it was originally saved with.
    let update: [String: Any] = [
      kSecValueData as String: data,
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
    ]
    let status = SecItemUpdate(baseQuery as CFDictionary, update as CFDictionary)
    if status == errSecSuccess { return }
    guard status == errSecItemNotFound else { throw CredentialStoreError.keychain(status: status) }

    var add = baseQuery
    add[kSecValueData as String] = data
    add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    let addStatus = SecItemAdd(add as CFDictionary, nil)
    guard addStatus == errSecSuccess else { throw CredentialStoreError.keychain(status: addStatus) }
  }

  public func deleteAccessToken() throws {
    let status = SecItemDelete(baseQuery as CFDictionary)
    guard status == errSecSuccess || status == errSecItemNotFound
    else { throw CredentialStoreError.keychain(status: status) }
  }

  private var baseQuery: [String: Any] {
    [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
  }
}
