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

  func signOut() {
    if let liveStore = dependencies.auth as? APIRentivoStore {
      Task { await liveStore.logout() }
    }
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
