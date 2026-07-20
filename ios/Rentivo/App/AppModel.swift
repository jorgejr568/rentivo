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
  let store: MockRentivoStore

  init(store: MockRentivoStore = MockRentivoStore(fixtures: .canonical)) {
    self.store = store
  }

  var isAuthenticated: Bool {
    if case .authenticated = session { return true }
    return false
  }

  func signIn() {
    session = .authenticated(store.currentUser)
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
}
