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
        FeaturePlaceholder(
          title: "Início",
          message: "Sua visão financeira aparecerá aqui.",
          symbol: "house.fill"
        )
      }
      .tag(AppTab.home)
      .tabItem { Label("Início", systemImage: "house") }

      NavigationStack {
        FeaturePlaceholder(
          title: "Cobranças",
          message: "Gerencie imóveis, faturas e despesas.",
          symbol: "doc.text.fill"
        )
      }
      .tag(AppTab.billings)
      .tabItem { Label("Cobranças", systemImage: "doc.text") }

      NavigationStack {
        FeaturePlaceholder(
          title: "Organizações",
          message: "Colabore com sua equipe e seus imóveis.",
          symbol: "building.2.fill"
        )
      }
      .tag(AppTab.organizations)
      .tabItem { Label("Organizações", systemImage: "building.2") }

      NavigationStack {
        FeaturePlaceholder(
          title: "Conta",
          message: "Configure PIX, segurança e integrações.",
          symbol: "person.crop.circle.fill"
        )
        .toolbar {
          Button("Sair") { app.signOut() }
        }
      }
      .tag(AppTab.account)
      .tabItem { Label("Conta", systemImage: "person.crop.circle") }
    }
  }
}

private struct FeaturePlaceholder: View {
  let title: String
  let message: String
  let symbol: String

  var body: some View {
    VStack(spacing: RentivoSpacing.large) {
      Image(systemName: symbol)
        .font(.system(size: 44, weight: .bold))
        .foregroundStyle(RentivoColors.emerald)
      Text(message)
        .font(.title3.weight(.semibold))
        .multilineTextAlignment(.center)
        .foregroundStyle(RentivoColors.ink)
    }
    .padding(RentivoSpacing.page)
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(RentivoColors.paper)
    .navigationTitle(title)
  }
}
