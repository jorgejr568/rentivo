import SwiftUI

struct SecurityView: View {
  @Environment(AppModel.self) private var app
  @State private var state: LoadState<SecuritySummary> = .idle
  @State private var recoveryCodes: [String] = []
  @State private var showingRecoveryCodes = false
  @State private var enrollment: TOTPEnrollment?
  @State private var showingDisableTOTP = false
  @State private var password = ""

  var body: some View {
    PageStateView(state: state) { summary in
      List {
        Section("Autenticação em duas etapas") {
          LabeledContent("Aplicativo autenticador", value: summary.totpEnabled ? "Ativado" : "Desativado")
          if !app.demoSettings.viewerMode {
            if summary.totpEnabled {
              Button("Desativar", role: .destructive) { showingDisableTOTP = true }
            } else {
              Button("Configurar aplicativo autenticador") { Task { await beginTOTP() } }
            }
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
              Text("Último uso: \(passkey.lastUsedAt?.formatted(date: .abbreviated, time: .shortened) ?? "nunca")")
                .font(.caption)
                .foregroundStyle(RentivoColors.secondaryInk)
              if !app.demoSettings.viewerMode {
                Button("Excluir", role: .destructive) { Task { await remove(passkey) } }
                  .font(.caption.weight(.semibold))
              }
            }
          }
          Text("Para registrar uma nova chave de acesso, entre pelo navegador do Rentivo. Ela ficará disponível automaticamente neste aplicativo.")
            .font(.footnote)
            .foregroundStyle(RentivoColors.secondaryInk)
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
    .sheet(isPresented: Binding(get: { enrollment != nil }, set: { if !$0 { enrollment = nil } })) {
      if let enrollment {
        TOTPEnrollmentView(enrollment: enrollment) { code in
          await confirmTOTP(code: code)
        }
      }
    }
    .alert("Desativar autenticação em duas etapas", isPresented: $showingDisableTOTP) {
      SecureField("Senha atual", text: $password)
      Button("Desativar", role: .destructive) { Task { await disableTOTP() } }
      Button("Cancelar", role: .cancel) { password = "" }
    } message: {
      Text("Confirme sua senha para desativar o aplicativo autenticador.")
    }
  }

  private func load() async {
    state = .loading
    do { state = .loaded(try await app.dependencies.security.securitySummary()) } catch {
      state = .failed(DemoError(error))
    }
  }

  private func beginTOTP() async {
    do {
      enrollment = try await app.dependencies.security.beginTOTPEnrollment()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func confirmTOTP(code: String) async {
    do {
      recoveryCodes = try await app.dependencies.security.confirmTOTPEnrollment(code: code)
      enrollment = nil
      await load()
      showingRecoveryCodes = true
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func disableTOTP() async {
    do {
      try await app.dependencies.security.disableTOTP(password: password)
      password = ""
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
        Label("Códigos de recuperação", systemImage: "shield.lefthalf.filled")
          .font(RentivoTypography.title)
        Text("Guarde estes códigos em local seguro. Eles aparecem uma única vez.")
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

private struct TOTPEnrollmentView: View {
  @Environment(\.dismiss) private var dismiss
  let enrollment: TOTPEnrollment
  let onConfirm: (String) async -> Void
  @State private var code = ""

  var body: some View {
    NavigationStack {
      VStack(alignment: .leading, spacing: RentivoSpacing.large) {
        Label("Configure seu autenticador", systemImage: "qrcode")
          .font(RentivoTypography.title)
        Text("Adicione esta chave manualmente ao seu aplicativo autenticador e informe o código de seis dígitos.")
        Text(enrollment.secret)
          .font(.system(.body, design: .monospaced, weight: .bold))
          .textSelection(.enabled)
          .padding()
          .frame(maxWidth: .infinity, alignment: .leading)
          .background(RentivoColors.surface)
          .clipShape(RoundedRectangle(cornerRadius: 12))
        TextField("Código do autenticador", text: $code)
          .keyboardType(.numberPad)
          .textContentType(.oneTimeCode)
        Button("Confirmar") { Task { await onConfirm(code) } }
          .buttonStyle(RentivoButtonStyle())
          .disabled(code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        Spacer()
      }
      .padding(RentivoSpacing.page)
      .background(RentivoColors.paper)
      .navigationTitle("Autenticador")
      .toolbar { Button("Cancelar") { dismiss() } }
    }
  }
}
