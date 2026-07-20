import SwiftUI

enum AuthRoute: Hashable {
  case signup
  case recovery
  case resetConfirmation
  case mfa
  case passkey
}

struct AuthenticationView: View {
  @State private var path: [AuthRoute] = []

  var body: some View {
    NavigationStack(path: $path) {
      LoginView(path: $path)
        .navigationDestination(for: AuthRoute.self) { route in
          switch route {
          case .signup: SignupView(path: $path)
          case .recovery: RecoveryView(path: $path)
          case .resetConfirmation: ResetConfirmationView()
          case .mfa: MFAView()
          case .passkey: PasskeyLoginView()
          }
        }
    }
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
  @Binding var path: [AuthRoute]
  @State private var email = ""
  @State private var password = ""
  @State private var validationMessage: String?

  var body: some View {
    AuthScaffold(
      title: "Boas-vindas",
      subtitle: "Entre para explorar a demonstração nativa do Rentivo. Nenhum dado será enviado."
    ) {
      VStack(alignment: .leading, spacing: RentivoSpacing.large) {
        TextField("E-mail", text: $email)
          .textContentType(.emailAddress)
          .keyboardType(.emailAddress)
          .textInputAutocapitalization(.never)
          .autocorrectionDisabled()
          .accessibilityIdentifier("login.email")
        SecureField("Senha", text: $password)
          .textContentType(.password)
          .accessibilityIdentifier("login.password")
        if let validationMessage {
          Label(validationMessage, systemImage: "exclamationmark.circle.fill")
            .font(.footnote.weight(.semibold))
            .foregroundStyle(RentivoColors.coral)
            .accessibilityIdentifier("login.error")
        }
        Button("Entrar na demonstração", action: submit)
          .buttonStyle(RentivoButtonStyle())
          .accessibilityIdentifier("login.submit")
        HStack {
          Button("Criar conta") { path.append(.signup) }
          Spacer()
          Button("Esqueci a senha") { path.append(.recovery) }
        }
        .font(.subheadline.weight(.semibold))
        Divider()
        Button {
          path.append(.passkey)
        } label: {
          Label("Entrar com chave de acesso", systemImage: "person.badge.key.fill")
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
        Button("Demonstrar autenticação em duas etapas") { path.append(.mfa) }
          .font(.footnote.weight(.semibold))
          .frame(maxWidth: .infinity)
      }
      .textFieldStyle(.roundedBorder)
    }
    .navigationBarBackButtonHidden()
  }

  private func submit() {
    let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmedEmail.contains("@"), !password.isEmpty else {
      validationMessage = "Informe um e-mail válido e uma senha."
      return
    }
    validationMessage = nil
    app.signIn()
  }
}

struct SignupView: View {
  @Environment(AppModel.self) private var app
  @Binding var path: [AuthRoute]
  @State private var email = ""
  @State private var password = ""
  @State private var confirmation = ""

  var body: some View {
    AuthScaffold(
      title: "Criar conta",
      subtitle: "Este cadastro é apenas uma simulação local."
    ) {
      VStack(spacing: RentivoSpacing.large) {
        TextField("E-mail", text: $email)
          .textContentType(.emailAddress)
          .keyboardType(.emailAddress)
          .textInputAutocapitalization(.never)
        SecureField("Senha", text: $password)
        SecureField("Confirmar senha", text: $confirmation)
        Button("Criar conta de demonstração") {
          app.signIn()
        }
        .buttonStyle(RentivoButtonStyle())
        .disabled(!isValid)
      }
      .textFieldStyle(.roundedBorder)
    }
    .navigationTitle("Cadastro")
    .navigationBarTitleDisplayMode(.inline)
  }

  private var isValid: Bool {
    email.contains("@") && !password.isEmpty && password == confirmation
  }
}

struct RecoveryView: View {
  @Binding var path: [AuthRoute]
  @State private var email = ""

  var body: some View {
    AuthScaffold(
      title: "Recuperar acesso",
      subtitle: "Simularemos o envio de instruções para o endereço informado."
    ) {
      VStack(spacing: RentivoSpacing.large) {
        TextField("E-mail", text: $email)
          .keyboardType(.emailAddress)
          .textInputAutocapitalization(.never)
          .textFieldStyle(.roundedBorder)
        Button("Simular envio") { path.append(.resetConfirmation) }
          .buttonStyle(RentivoButtonStyle())
          .disabled(!email.contains("@"))
      }
    }
    .navigationTitle("Recuperação")
    .navigationBarTitleDisplayMode(.inline)
  }
}

struct ResetConfirmationView: View {
  var body: some View {
    AuthScaffold(
      title: "Instruções prontas",
      subtitle: "Na versão integrada, você receberá um link seguro por e-mail."
    ) {
      Label("Envio simulado com sucesso", systemImage: "checkmark.seal.fill")
        .font(.headline)
        .foregroundStyle(RentivoColors.emerald)
    }
    .navigationTitle("E-mail simulado")
    .navigationBarTitleDisplayMode(.inline)
  }
}

struct MFAView: View {
  @Environment(AppModel.self) private var app
  @State private var code = ""

  var body: some View {
    AuthScaffold(
      title: "Confirmação em duas etapas",
      subtitle: "Use qualquer código de seis dígitos para continuar nesta demonstração."
    ) {
      VStack(spacing: RentivoSpacing.large) {
        TextField("Código de 6 dígitos", text: $code)
          .keyboardType(.numberPad)
          .textContentType(.oneTimeCode)
          .textFieldStyle(.roundedBorder)
        Button("Confirmar código") { app.signIn() }
          .buttonStyle(RentivoButtonStyle())
          .disabled(code.count != 6)
      }
    }
    .navigationTitle("Verificação")
    .navigationBarTitleDisplayMode(.inline)
  }
}

struct PasskeyLoginView: View {
  @Environment(AppModel.self) private var app

  var body: some View {
    AuthScaffold(
      title: "Chave de acesso",
      subtitle: "O Face ID não será acionado. Esta etapa demonstra o fluxo futuro."
    ) {
      VStack(spacing: RentivoSpacing.large) {
        Image(systemName: "faceid")
          .font(.system(size: 52))
          .foregroundStyle(RentivoColors.emerald)
          .accessibilityHidden(true)
        Button("Simular autenticação") { app.signIn() }
          .buttonStyle(RentivoButtonStyle())
      }
    }
    .navigationTitle("Chave de acesso")
    .navigationBarTitleDisplayMode(.inline)
  }
}
