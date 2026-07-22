import SwiftUI

struct AuthenticationView: View {
  var body: some View {
    LoginView()
    .background(RentivoColors.paper)
  }
}

private struct AuthScaffold<Content: View>: View {
  let title: String
  let subtitle: String
  let content: Content

  init(title: String, subtitle: String, @ViewBuilder content: () -> Content) {
    self.title = title
    self.subtitle = subtitle
    self.content = content()
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: RentivoSpacing.page) {
        BrandMark()
          .padding(.bottom, RentivoSpacing.small)
        VStack(alignment: .leading, spacing: RentivoSpacing.small) {
          Text(title)
            .font(RentivoTypography.display)
            .foregroundStyle(RentivoColors.ink)
          Text(subtitle)
            .font(.body)
            .foregroundStyle(RentivoColors.secondaryInk)
        }
        RentivoCard { content }
      }
      .padding(RentivoSpacing.page)
      .frame(maxWidth: 560)
      .frame(maxWidth: .infinity)
    }
    .scrollDismissesKeyboard(.interactively)
    .rentivoPage()
  }
}

struct LoginView: View {
  @Environment(AppModel.self) private var app
  @State private var validationMessage: String?

  var body: some View {
    AuthScaffold(
      title: "Boas-vindas",
      subtitle: "Entre com sua conta Rentivo para acessar seus dados."
    ) {
      VStack(alignment: .leading, spacing: RentivoSpacing.large) {
        if let validationMessage {
          Label(validationMessage, systemImage: "exclamationmark.circle.fill")
            .font(.footnote.weight(.semibold))
            .foregroundStyle(RentivoColors.coral)
            .accessibilityIdentifier("login.error")
        }
        Button("Entrar", action: submit)
          .buttonStyle(RentivoButtonStyle())
          .accessibilityIdentifier("login.submit")
        Text("O login continua no site seguro do Rentivo para concluir a verificação de segurança.")
          .font(.footnote)
          .foregroundStyle(RentivoColors.secondaryInk)
      }
      .textFieldStyle(.roundedBorder)
    }
    .navigationBarBackButtonHidden()
  }

  private func submit() {
    validationMessage = nil
    Task {
      do {
        try await app.signInWithWebAuthorization()
      } catch {
        validationMessage = error.localizedDescription
      }
    }
  }
}
