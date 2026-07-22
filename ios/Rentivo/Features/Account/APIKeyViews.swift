import SwiftUI

struct APIKeyListView: View {
  @Environment(AppModel.self) private var app
  @State private var state: LoadState<[APIKeyMetadata]> = .idle
  @State private var showingCreate = false
  @State private var createdSecret: CreatedAPIKeySecret?
  @State private var editingKey: APIKeyMetadata?

  var body: some View {
    PageStateView(state: state) { keys in
      List {
        ForEach(keys) { key in
          VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
            HStack {
              Text(key.name).font(.headline)
              Spacer()
              Text(key.hint).font(.system(.caption, design: .monospaced))
            }
            Text(key.scopes.map(\.label).sorted().joined(separator: " · "))
              .font(.caption)
              .foregroundStyle(RentivoColors.secondaryInk)
            LabeledContent("Acessos", value: "\(key.grants.count)")
              .font(.caption)
            if !app.demoSettings.viewerMode {
              HStack {
                Button("Editar") { editingKey = key }
                  .accessibilityIdentifier("api-key.edit")
                Spacer()
                Button("Revogar", role: .destructive) { Task { await revoke(key) } }
                  .accessibilityIdentifier("api-key.revoke")
              }
              .font(.caption.weight(.semibold))
            }
          }
          .padding(.vertical, RentivoSpacing.small)
        }
      }
      .scrollContentBackground(.hidden)
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Integrações")
    .toolbar {
      if !app.demoSettings.viewerMode {
        Button {
          showingCreate = true
        } label: {
          Label("Criar chave", systemImage: "plus")
        }
        .accessibilityIdentifier("api-key.create")
      }
    }
    .sheet(isPresented: $showingCreate) {
      NavigationStack {
        APIKeyFormView { secret in
          createdSecret = secret
          await load()
        }
      }
    }
    .sheet(item: $editingKey) { key in
      NavigationStack {
        APIKeyFormView(key: key) { _ in await load() }
      }
    }
    .sheet(item: $createdSecret) { secret in
      APIKeySecretView(created: secret)
    }
    .task(id: app.dataRevision) { await load() }
  }

  private func load() async {
    state = .loading
    do {
      let keys = try await app.dependencies.apiKeys.listAPIKeys()
      state = keys.isEmpty ? .empty : .loaded(keys)
    } catch { state = .failed(DemoError(error)) }
  }

  private func revoke(_ key: APIKeyMetadata) async {
    do {
      try await app.dependencies.apiKeys.revokeAPIKey(id: key.id)
      await load()
      app.showNotice("Chave revogada.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

private struct APIKeyFormView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let key: APIKeyMetadata?
  let onSaved: (CreatedAPIKeySecret?) async -> Void
  @State private var name: String
  @State private var scopes: Set<APIKeyScope>
  @State private var grantIDs: Set<WorkspaceID>
  @State private var expiresAt: Date
  @State private var organizations: [Organization] = []
  private let originalGrants: [WorkspaceID: APIKeyGrant]

  init(
    key: APIKeyMetadata? = nil,
    onSaved: @escaping (CreatedAPIKeySecret?) async -> Void
  ) {
    self.key = key
    self.onSaved = onSaved
    let grants = key?.grants ?? [APIKeyGrant(resourceType: .user, resourceID: .personal)]
    originalGrants = Dictionary(uniqueKeysWithValues: grants.map { ($0.resourceID, $0) })
    _name = State(initialValue: key?.name ?? "Nova integração")
    _scopes = State(initialValue: key?.scopes ?? [.profileRead, .billingsRead])
    _grantIDs = State(initialValue: Set(grants.map(\.resourceID)))
    _expiresAt = State(initialValue: key?.expiresAt ?? Date(timeIntervalSinceNow: 31_536_000))
  }

  var body: some View {
    Form {
      Section("Identificação") { TextField("Nome", text: $name) }
      Section("Escopos seguros") {
        ForEach(APIKeyScope.integrationCases, id: \.self) { scope in
          Toggle(
            scope.label,
            isOn: Binding(
              get: { scopes.contains(scope) },
              set: { enabled in
                if enabled { scopes.insert(scope) } else { scopes.remove(scope) }
              }
            )
          )
        }
      }
      Section("Acesso") {
        resourceToggle("Conta pessoal", id: .personal)
        ForEach(organizations) { organization in
          resourceToggle(organization.name, id: WorkspaceID(rawValue: organization.id.rawValue))
        }
      }
      Section("Validade") {
        DatePicker("Expira em", selection: $expiresAt, displayedComponents: .date)
      }
    }
    .navigationTitle(key == nil ? "Nova chave" : "Editar chave")
    .toolbar {
      ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() } }
      ToolbarItem(placement: .confirmationAction) {
        Button(key == nil ? "Criar" : "Salvar") { Task { await save() } }
          .disabled(name.isEmpty || scopes.isEmpty || grantIDs.isEmpty)
      }
    }
    .task {
      organizations = (try? await app.dependencies.organizations.listOrganizations()) ?? []
    }
  }

  private func resourceToggle(_ label: String, id: WorkspaceID) -> some View {
    Toggle(
      label,
      isOn: Binding(
        get: { grantIDs.contains(id) },
        set: { enabled in
          if enabled { grantIDs.insert(id) } else { grantIDs.remove(id) }
        }
      )
    )
  }

  private func save() async {
    let grants =
      grantIDs
      .sorted { $0.rawValue < $1.rawValue }
      .map { resourceID in
        originalGrants[resourceID]
          ?? APIKeyGrant(
            resourceType: resourceID == .personal ? .user : .organization,
            resourceID: resourceID
          )
      }
    let draft = APIKeyDraft(
      name: name,
      scopes: scopes,
      grants: grants,
      expiresAt: expiresAt
    )
    do {
      if let key {
        _ = try await app.dependencies.apiKeys.updateAPIKey(id: key.id, draft: draft)
        dismiss()
        await onSaved(nil)
        app.showNotice("Metadados da chave atualizados.")
      } else {
        let secret = try await app.dependencies.apiKeys.createAPIKey(draft)
        dismiss()
        await onSaved(secret)
      }
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

private struct APIKeySecretView: View {
  @Environment(\.dismiss) private var dismiss
  let created: CreatedAPIKeySecret

  var body: some View {
    NavigationStack {
      VStack(alignment: .leading, spacing: RentivoSpacing.large) {
        Label("Copie agora", systemImage: "exclamationmark.shield.fill")
          .font(RentivoTypography.title)
          .foregroundStyle(RentivoColors.amber)
        Text("Este segredo não será exibido novamente.")
        Text(created.secret)
          .font(.system(.body, design: .monospaced, weight: .bold))
          .textSelection(.enabled)
          .padding()
          .frame(maxWidth: .infinity, alignment: .leading)
          .background(RentivoColors.surface)
          .clipShape(RoundedRectangle(cornerRadius: 12))
        Spacer()
        Button("Já copiei") { dismiss() }
          .buttonStyle(RentivoButtonStyle())
      }
      .padding(RentivoSpacing.page)
      .background(RentivoColors.paper)
      .navigationTitle("Segredo da chave")
    }
  }
}

extension CreatedAPIKeySecret: Identifiable {
  public var id: APIKeyID { metadata.id }
}

extension APIKeyScope {
  fileprivate var label: String {
    switch self {
    case .profileRead: "Ler perfil"
    case .accountWrite: "Alterar conta"
    case .securityManage: "Gerenciar segurança"
    case .apiKeysManage: "Gerenciar chaves de API"
    case .organizationsRead: "Ler organizações"
    case .organizationsWrite: "Alterar organizações"
    case .organizationsMembers: "Gerenciar membros"
    case .billingsRead: "Ler cobranças"
    case .billingsWrite: "Alterar cobranças"
    case .billsRead: "Ler faturas"
    case .billsWrite: "Alterar faturas"
    case .expensesRead: "Ler despesas"
    case .expensesWrite: "Alterar despesas"
    case .filesRead: "Ler arquivos"
    case .filesWrite: "Alterar arquivos"
    case .communicationsRead: "Ler comunicações"
    case .communicationsSend: "Enviar comunicações"
    case .themesRead: "Ler temas"
    case .themesWrite: "Alterar temas"
    case .exportsCreate: "Criar exportações"
    }
  }
}
