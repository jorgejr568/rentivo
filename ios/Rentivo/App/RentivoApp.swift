import SwiftUI

@main
struct RentivoApp: App {
  @State private var app: AppModel

  init() {
    #if DEBUG
      let arguments = ProcessInfo.processInfo.arguments
      let usesMockData = arguments.contains("--ui-testing") || arguments.contains("--screenshot-authenticated")
      let model = usesMockData
        ? AppModel(store: MockRentivoStore(fixtures: .canonical))
        : AppModel(dependencies: .live())
    #else
      let model = AppModel(dependencies: .live())
    #endif
    #if DEBUG
      if arguments.contains("--screenshot-authenticated") {
        model.signIn()
        if let tabIndex = arguments.firstIndex(of: "--screenshot-tab"),
          arguments.indices.contains(tabIndex + 1)
        {
          switch arguments[tabIndex + 1] {
          case "billings": model.selectedTab = .billings
          case "organizations": model.selectedTab = .organizations
          case "account": model.selectedTab = .account
          default: model.selectedTab = .home
          }
        }
        model.notice = nil
      }
    #endif
    _app = State(initialValue: model)
  }

  var body: some Scene {
    WindowGroup {
      RootView()
        .environment(app)
        .tint(RentivoColors.emerald)
    }
  }
}
