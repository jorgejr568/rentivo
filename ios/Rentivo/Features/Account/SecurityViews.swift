import SwiftUI

struct SecurityView: View {
  @Environment(AppModel.self) private var app
  @State private var state: LoadState<SecuritySummary> = .idle
  @State private var recoveryCodes: [String] = []
  @State private var showingRecoveryCodes = false
  @State private var enrollment: TOTPEnrollment?
  @State private var showingDisableTOTP = false
  @State private var password = ""
  @State private var passkeyPendingDelete: Passkey?

  /// Demo "viewer mode" is a local demo/mock-backend concept only. Once the app is
  /// connected to the live API, the signed-in user owns their own account and this
  /// screen should be fully enabled regardless of the demo viewer-mode toggle.
  private var isDemoViewerLocked: Bool {
    !app.usesLiveAPI && app.demoSettings.viewerMode
  }

  var body: some View {
    PageStateView(state: state) { summary in
      List {
        Section("Senha") {
          NavigationLink {
            ChangePasswordView()
          } label: {
            Label("Alterar senha", systemImage: "key.fill")
          }
        }
        Section("Autenticação em duas etapas") {
          LabeledContent("Aplicativo autenticador", value: summary.totpEnabled ? "Ativado" : "Desativado")
          if !isDemoViewerLocked {
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
          if summary.passkeys.isEmpty {
            Text("Nenhuma chave de acesso registrada ainda.")
              .font(.footnote)
              .foregroundStyle(RentivoColors.secondaryInk)
          } else {
            ForEach(summary.passkeys) { passkey in
              VStack(alignment: .leading, spacing: RentivoSpacing.small) {
                Text(passkey.name).font(.headline)
                Text("Último uso: \(passkey.lastUsedAt?.formattedPTBR(time: .shortened) ?? "nunca")")
                  .font(.caption)
                  .foregroundStyle(RentivoColors.secondaryInk)
                if !isDemoViewerLocked {
                  Button("Excluir", role: .destructive) { passkeyPendingDelete = passkey }
                    .font(.caption.weight(.semibold))
                    .accessibilityIdentifier("security.passkey.delete")
                }
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
    .confirmationDialog(
      "Excluir esta chave de acesso?",
      isPresented: Binding(
        get: { passkeyPendingDelete != nil },
        set: { if !$0 { passkeyPendingDelete = nil } }
      ),
      presenting: passkeyPendingDelete
    ) { passkey in
      Button("Excluir chave de acesso", role: .destructive) {
        Task { await remove(passkey) }
      }
      .accessibilityIdentifier("security.passkey.delete.confirm")
      Button("Cancelar", role: .cancel) {}
        .accessibilityIdentifier("security.passkey.delete.cancel")
    } message: { passkey in
      Text("\"\(passkey.name)\" não poderá mais ser usada para entrar neste dispositivo. Esta ação não pode ser desfeita.")
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

private struct ChangePasswordView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  @State private var currentPassword = ""
  @State private var newPassword = ""
  @State private var confirmPassword = ""
  @State private var isSaving = false
  @State private var validationMessage: String?

  var body: some View {
    Form {
      Section {
        SecureField("Senha atual", text: $currentPassword)
          .textContentType(.password)
        SecureField("Nova senha", text: $newPassword)
          .textContentType(.newPassword)
        SecureField("Confirmar nova senha", text: $confirmPassword)
          .textContentType(.newPassword)
      } header: {
        Text("Alterar senha")
      } footer: {
        Text("Use uma senha forte e exclusiva para sua conta Rentivo.")
      }

      if let validationMessage {
        Section {
          Label(validationMessage, systemImage: "exclamationmark.circle.fill")
            .foregroundStyle(RentivoColors.coral)
        }
      }

      Section {
        Button("Salvar nova senha", action: save)
          .disabled(isSaving || currentPassword.isEmpty || newPassword.isEmpty || confirmPassword.isEmpty)
      }
    }
    .navigationTitle("Senha")
  }

  private func save() {
    guard newPassword == confirmPassword else {
      validationMessage = "As senhas não coincidem."
      return
    }
    validationMessage = nil
    isSaving = true
    Task {
      defer { isSaving = false }
      do {
        try await app.dependencies.security.changePassword(
          currentPassword: currentPassword, newPassword: newPassword, confirmPassword: confirmPassword
        )
        currentPassword = ""
        newPassword = ""
        confirmPassword = ""
        app.showNotice("Senha alterada com sucesso.")
        dismiss()
      } catch {
        validationMessage = DemoError(error).message
      }
    }
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

extension Date {
  /// Formats this date pinned to the pt-BR locale, so PT-BR sentences never leak a
  /// device-locale date string (e.g. "Jul 23, 2026" showing up on an en-US device
  /// inside otherwise-Portuguese copy).
  func formattedPTBR(
    date dateStyle: Date.FormatStyle.DateStyle = .abbreviated,
    time timeStyle: Date.FormatStyle.TimeStyle = .omitted
  ) -> String {
    formatted(Date.FormatStyle(date: dateStyle, time: timeStyle, locale: Locale(identifier: "pt_BR")))
  }
}
