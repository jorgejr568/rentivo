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
    case anonymous
    case authenticated(UserProfile)
  }

  var session: Session = .anonymous
  var selectedTab: AppTab = .home
  var notice: AppNotice?
  var demoSettings: DemoSettings
  var dataRevision = 0
  let dependencies: AppDependencies

  init(store: MockRentivoStore = MockRentivoStore(fixtures: .canonical)) {
    dependencies = .mock(store: store)
    demoSettings = store.demoSettings
  }

  init(dependencies: AppDependencies) {
    self.dependencies = dependencies
    demoSettings = dependencies.demo.demoSettings
  }

  var currentUser: UserProfile { dependencies.auth.currentUser }

  var isAuthenticated: Bool {
    if case .authenticated = session { return true }
    return false
  }

  func signIn() {
    session = .authenticated(currentUser)
    selectedTab = .home
    notice = AppNotice(kind: .success, message: "Bem-vinda à demonstração do Rentivo.")
  }

  func signOut() {
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
