import SwiftUI

struct RootView: View {
  @Environment(AppModel.self) private var app

  var body: some View {
    Group {
      switch app.session {
      case .anonymous:
        AuthenticationView()
      case .authenticated:
        AuthenticatedTabView()
      }
    }
    .background(RentivoColors.paper.ignoresSafeArea())
    .overlay(alignment: .top) {
      if let notice = app.notice {
        NoticeBanner(notice: notice) {
          withAnimation { app.notice = nil }
        }
        .padding(.horizontal, RentivoSpacing.page)
        .padding(.top, RentivoSpacing.small)
        .transition(.move(edge: .top).combined(with: .opacity))
      }
    }
  }
}

struct AuthenticatedTabView: View {
  @Environment(AppModel.self) private var app

  var body: some View {
    @Bindable var app = app
    TabView(selection: $app.selectedTab) {
      NavigationStack {
        HomeView()
      }
      .tag(AppTab.home)
      .tabItem { Label("Início", systemImage: "house") }

      NavigationStack {
        BillingListView()
      }
      .tag(AppTab.billings)
      .tabItem { Label("Cobranças", systemImage: "doc.text") }

      NavigationStack {
        OrganizationListView()
      }
      .tag(AppTab.organizations)
      .tabItem { Label("Organizações", systemImage: "building.2") }

      NavigationStack {
        AccountView()
      }
      .tag(AppTab.account)
      .tabItem { Label("Conta", systemImage: "person.crop.circle") }
    }
  }
}
