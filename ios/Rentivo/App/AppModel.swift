import Observation
import SwiftUI

enum AppTab: Hashable {
  case home
  case billings
  case organizations
  case account
}

struct AppNotice: Identifiable, Equatable {
  enum Kind {
    case success
    case information
    case warning
  }

  let id = UUID()
  let kind: Kind
  let message: String
}

@MainActor
@Observable
final class AppModel {
  enum Session {
    case restoring
    case anonymous
    case authenticated(UserProfile)
  }

  var session: Session = .anonymous
  var selectedTab: AppTab = .home
  var notice: AppNotice?
  var isSigningOut = false
  var isDeletingAccount = false
  var demoSettings: DemoSettings
  var dataRevision = 0
  let dependencies: AppDependencies
  private let mobileWebAuthenticator = MobileWebAuthenticator()

  init(store: MockRentivoStore = MockRentivoStore(fixtures: .canonical)) {
    dependencies = .mock(store: store)
    demoSettings = store.demoSettings
  }

  init(dependencies: AppDependencies) {
    self.dependencies = dependencies
    demoSettings = dependencies.demo.demoSettings
    if dependencies.auth is APIRentivoStore {
      session = .restoring
    }
  }

  var currentUser: UserProfile {
    if case .authenticated(let user) = session { return user }
    return dependencies.auth.currentUser
  }

  var isAuthenticated: Bool {
    if case .authenticated = session { return true }
    return false
  }

  func loadProfile() async throws -> UserProfile {
    let profile = try await dependencies.profile.profile()
    if case .authenticated = session {
      session = .authenticated(profile)
    }
    return profile
  }

  func updateProfilePIX(_ pix: PixConfiguration) async throws -> UserProfile {
    let profile = try await dependencies.profile.updatePix(pix)
    if case .authenticated = session {
      session = .authenticated(profile)
    }
    return profile
  }

  func restoreSessionIfNeeded() async {
    guard case .restoring = session else { return }
    guard let liveStore = dependencies.auth as? APIRentivoStore else {
      session = .anonymous
      return
    }
    do {
      session = try await liveStore.restoreSession().map(Session.authenticated) ?? .anonymous
    } catch {
      session = .anonymous
      notice = AppNotice(kind: .warning, message: "Não foi possível restaurar sua sessão. Entre novamente.")
    }
  }

  var usesLiveAPI: Bool { dependencies.auth is APIRentivoStore }

  func signIn() {
    session = .authenticated(currentUser)
    selectedTab = .home
    notice = AppNotice(kind: .success, message: "Bem-vinda à demonstração do Rentivo.")
  }

  func signIn(email: String, password: String) async throws {
    guard let liveStore = dependencies.auth as? APIRentivoStore else {
      session = .authenticated(currentUser)
      selectedTab = .home
      return
    }
    session = .authenticated(try await liveStore.login(email: email, password: password))
    selectedTab = .home
    notice = AppNotice(kind: .success, message: "Sessão conectada ao Rentivo.")
  }

  func signInWithWebAuthorization() async throws {
    guard let liveStore = dependencies.auth as? APIRentivoStore else { signIn(); return }
    let code = try await mobileWebAuthenticator.authorize()
    session = .authenticated(try await liveStore.exchangeMobileAuthorization(code: code))
    selectedTab = .home
    notice = AppNotice(kind: .success, message: "Sessão conectada ao Rentivo.")
  }

  func signOut() async {
    guard !isSigningOut else { return }
    guard let liveStore = dependencies.auth as? APIRentivoStore else {
      completeSignOut()
      return
    }
    isSigningOut = true
    defer { isSigningOut = false }
    do {
      try await mobileWebAuthenticator.logout()
    } catch {
      notice = AppNotice(
        kind: .warning,
        message: "Não foi possível encerrar a sessão do site. Tente sair novamente."
      )
      return
    }
    await liveStore.logout()
    completeSignOut()
  }

  func deleteAccount(password: String) async {
    guard !isDeletingAccount else { return }
    guard let liveStore = dependencies.auth as? APIRentivoStore else {
      completeSignOut()
      return
    }
    isDeletingAccount = true
    defer { isDeletingAccount = false }
    do {
      try await liveStore.deleteAccount(password: password)
      completeSignOut()
      notice = AppNotice(kind: .success, message: "Sua conta foi excluída.")
    } catch {
      notice = AppNotice(
        kind: .warning,
        message: "Não foi possível excluir a conta. Verifique sua senha e tente novamente."
      )
    }
  }

  private func completeSignOut() {
    session = .anonymous
    selectedTab = .home
    notice = nil
  }

  func showNotice(_ message: String, kind: AppNotice.Kind = .success) {
    notice = AppNotice(kind: kind, message: message)
  }

  func setDelayEnabled(_ enabled: Bool) {
    dependencies.demo.setDelayEnabled(enabled)
    refreshDemoState(reloadContent: false)
  }

  func setEmptyMode(_ enabled: Bool) {
    dependencies.demo.setEmptyMode(enabled)
    refreshDemoState(reloadContent: true)
  }

  func setViewerMode(_ enabled: Bool) {
    dependencies.demo.setViewerMode(enabled)
    refreshDemoState(reloadContent: true)
  }

  func failNextOperation() {
    dependencies.demo.failNextOperation()
  }

  func resetDemo() {
    dependencies.demo.reset()
    refreshDemoState(reloadContent: true)
  }

  private func refreshDemoState(reloadContent: Bool) {
    demoSettings = dependencies.demo.demoSettings
    if reloadContent { dataRevision += 1 }
  }
}
