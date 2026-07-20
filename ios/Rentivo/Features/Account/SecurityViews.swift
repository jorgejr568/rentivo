import SwiftUI

struct SecurityView: View {
  @Environment(AppModel.self) private var app
  @State private var state: LoadState<SecuritySummary> = .idle
  @State private var recoveryCodes: [String] = []
  @State private var showingRecoveryCodes = false
  @State private var showingPassword = false

  var body: some View {
    PageStateView(state: state) { summary in
      List {
        Section("Senha") {
          if !app.demoSettings.viewerMode {
            Button("Simular alteração de senha") { showingPassword = true }
          }
        }
        Section("Autenticação em duas etapas") {
          Toggle(
            "Aplicativo autenticador",
            isOn: Binding(
              get: { summary.totpEnabled },
              set: { value in Task { await setTOTP(value) } }
            )
          )
          .disabled(app.demoSettings.viewerMode)
          if !app.demoSettings.viewerMode {
            Button("Gerar novos códigos de recuperação") {
              Task { await regenerateCodes() }
            }
          }
          LabeledContent("Códigos disponíveis", value: "\(summary.recoveryCodeCount)")
        }
        Section("Chaves de acesso") {
          ForEach(summary.passkeys) { passkey in
            VStack(alignment: .leading, spacing: RentivoSpacing.small) {
              Text(passkey.name).font(.headline)
              Text("Criada para esta demonstração")
                .font(.caption)
                .foregroundStyle(RentivoColors.secondaryInk)
              if !app.demoSettings.viewerMode {
                HStack {
                  Button("Renomear") { Task { await rename(passkey) } }
                  Button("Excluir", role: .destructive) { Task { await remove(passkey) } }
                }
                .font(.caption.weight(.semibold))
              }
            }
          }
          if !app.demoSettings.viewerMode {
            Button {
              Task { await addPasskey() }
            } label: {
              Label("Registrar chave simulada", systemImage: "plus")
            }
            .accessibilityIdentifier("security.passkey.add")
          }
        }
      }
      .scrollContentBackground(.hidden)
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Segurança")
    .task(id: app.dataRevision) { await load() }
    .sheet(isPresented: $showingRecoveryCodes) {
      RecoveryCodeView(codes: recoveryCodes)
    }
    .alert("Senha atualizada", isPresented: $showingPassword) {
      Button("OK") {}
    } message: {
      Text("Simulação concluída. Nenhuma credencial real foi alterada.")
    }
  }

  private func load() async {
    state = .loading
    do { state = .loaded(try await app.dependencies.security.securitySummary()) } catch {
      state = .failed(DemoError(error))
    }
  }

  private func setTOTP(_ enabled: Bool) async {
    do {
      try await app.dependencies.security.setTOTPEnabled(enabled)
      await load()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func regenerateCodes() async {
    do {
      recoveryCodes = try await app.dependencies.security.regenerateRecoveryCodes()
      await load()
      showingRecoveryCodes = true
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func addPasskey() async {
    do {
      _ = try await app.dependencies.security.addPasskey(name: "iPhone de demonstração")
      await load()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func rename(_ passkey: Passkey) async {
    do {
      try await app.dependencies.security.renamePasskey(
        id: passkey.id, name: "\(passkey.name) — pessoal")
      await load()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func remove(_ passkey: Passkey) async {
    do {
      try await app.dependencies.security.deletePasskey(id: passkey.id)
      await load()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

private struct RecoveryCodeView: View {
  @Environment(\.dismiss) private var dismiss
  let codes: [String]

  var body: some View {
    NavigationStack {
      VStack(alignment: .leading, spacing: RentivoSpacing.large) {
        Label("Códigos sintéticos", systemImage: "shield.lefthalf.filled")
          .font(RentivoTypography.title)
        Text("Eles aparecem uma única vez nesta tela e não protegem nenhuma conta real.")
          .foregroundStyle(RentivoColors.secondaryInk)
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())]) {
          ForEach(codes, id: \.self) { code in
            Text(code)
              .font(.system(.body, design: .monospaced, weight: .bold))
              .padding()
              .frame(maxWidth: .infinity)
              .background(RentivoColors.surface)
              .clipShape(RoundedRectangle(cornerRadius: 10))
          }
        }
        Spacer()
      }
      .padding(RentivoSpacing.page)
      .background(RentivoColors.paper)
      .navigationTitle("Recuperação")
      .toolbar { Button("Concluir") { dismiss() } }
    }
  }
}
