import SwiftUI

struct AccountView: View {
  @Environment(AppModel.self) private var app

  var body: some View {
    List {
      Section {
        HStack(spacing: RentivoSpacing.medium) {
          BrandMark(compact: true)
          VStack(alignment: .leading, spacing: RentivoSpacing.tiny) {
            Text(app.usesLiveAPI ? "Sua conta" : "Conta de demonstração").font(.headline)
            Text(app.currentUser.email)
              .font(.subheadline)
              .foregroundStyle(RentivoColors.secondaryInk)
          }
        }
        .padding(.vertical, RentivoSpacing.small)
      }

      Section("Perfil") {
        NavigationLink {
          ProfilePixView()
        } label: {
          AccountRow(title: "Dados e PIX", subtitle: "Chave e dados do recebedor", symbol: "qrcode")
        }
        NavigationLink {
          SecurityView()
        } label: {
          AccountRow(
            title: "Segurança", subtitle: "Senha, TOTP e chaves de acesso",
            symbol: "lock.shield.fill")
        }
      }

      Section("Personalização e integrações") {
        NavigationLink {
          APIKeyListView()
        } label: {
          AccountRow(
            title: "Chaves de integração", subtitle: "Escopos e acessos", symbol: "key.fill")
        }
        NavigationLink {
          ThemeEditorView(target: .user)
        } label: {
          AccountRow(
            title: "Aparência", subtitle: "Fontes, cores e prévia", symbol: "paintpalette.fill")
        }
      }

      if !app.usesLiveAPI {
        Section("Demonstração") {
          NavigationLink {
            DemoScenariosView()
          } label: {
            AccountRow(
              title: "Cenários do app",
              subtitle: "Atraso, falha, vazio e permissões",
              symbol: "slider.horizontal.3"
            )
          }
          .accessibilityIdentifier("account.demo")
        }
      }

      Section {
        Button(role: .destructive) {
          app.signOut()
        } label: {
          Label("Sair", systemImage: "rectangle.portrait.and.arrow.right")
            .frame(maxWidth: .infinity)
        }
      }
    }
    .scrollContentBackground(.hidden)
    .background(RentivoColors.paper)
    .navigationTitle("Conta")
  }
}

private struct AccountRow: View {
  let title: String
  let subtitle: String
  let symbol: String

  var body: some View {
    Label {
      VStack(alignment: .leading, spacing: RentivoSpacing.tiny) {
        Text(title).font(.headline)
        Text(subtitle)
          .font(.caption)
          .foregroundStyle(RentivoColors.secondaryInk)
      }
    } icon: {
      Image(systemName: symbol).foregroundStyle(RentivoColors.emerald)
    }
  }
}

struct ProfilePixView: View {
  @Environment(AppModel.self) private var app
  @State private var key: String
  @State private var merchantName: String
  @State private var city: String

  init() {
    _key = State(initialValue: "")
    _merchantName = State(initialValue: "")
    _city = State(initialValue: "")
  }

  var body: some View {
    Form {
      Section("Conta") {
        LabeledContent("E-mail", value: app.currentUser.email)
        LabeledContent("Ambiente", value: "Demonstração local")
      }
      Section("PIX pessoal") {
        TextField("Chave PIX", text: $key)
          .textInputAutocapitalization(.never)
        TextField("Nome do recebedor", text: $merchantName)
        TextField("Cidade", text: $city)
          .textInputAutocapitalization(.characters)
      }
      .disabled(app.demoSettings.viewerMode)
      Section {
        Label(
          "Cobranças pessoais sem PIX próprio herdam esta configuração.",
          systemImage: "arrow.triangle.branch"
        )
        .font(.footnote)
      }
    }
    .navigationTitle("Dados e PIX")
    .toolbar {
      if !app.demoSettings.viewerMode {
        Button("Salvar") { Task { await save() } }
          .disabled(
            !PixConfiguration(key: key, merchantName: merchantName, merchantCity: city).isComplete
          )
          .accessibilityIdentifier("profile.pix.save")
      }
    }
    .task {
      guard let pix = app.currentUser.pix else { return }
      key = pix.key
      merchantName = pix.merchantName
      city = pix.merchantCity
    }
  }

  private func save() async {
    do {
      _ = try await app.dependencies.profile.updatePix(
        PixConfiguration(key: key, merchantName: merchantName, merchantCity: city)
      )
      app.showNotice("PIX pessoal atualizado.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}
