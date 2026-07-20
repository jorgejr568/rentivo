import SwiftUI

struct APIKeyListView: View {
  @Environment(AppModel.self) private var app
  @State private var state: LoadState<[APIKeyMetadata]> = .idle
  @State private var showingCreate = false
  @State private var createdSecret: CreatedAPIKeySecret?

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
            Text(key.scopes.map(\.rawValue).sorted().joined(separator: " · "))
              .font(.caption)
              .foregroundStyle(RentivoColors.secondaryInk)
            LabeledContent("Acessos", value: "\(key.grants.count)")
              .font(.caption)
            Button("Revogar", role: .destructive) { Task { await revoke(key) } }
              .font(.caption.weight(.semibold))
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
      Button {
        showingCreate = true
      } label: {
        Label("Criar chave", systemImage: "plus")
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
    .sheet(item: $createdSecret) { secret in
      APIKeySecretView(created: secret)
    }
    .task { await load() }
  }

  private func load() async {
    state = .loading
    do {
      let keys = try await app.store.listAPIKeys()
      state = keys.isEmpty ? .empty : .loaded(keys)
    } catch { state = .failed(DemoError(error)) }
  }

  private func revoke(_ key: APIKeyMetadata) async {
    do {
      try await app.store.revokeAPIKey(id: key.id)
      await load()
      app.showNotice("Chave revogada.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

private struct APIKeyFormView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let onCreated: (CreatedAPIKeySecret) async -> Void
  @State private var name = "Integração de demonstração"
  @State private var scopes: Set<APIKeyScope> = [.profileRead, .billingsRead]
  @State private var grantID = StableID.userAna

  var body: some View {
    Form {
      Section("Identificação") { TextField("Nome", text: $name) }
      Section("Escopos seguros") {
        ForEach(APIKeyScope.integrationCases, id: \.self) { scope in
          Toggle(
            scope.rawValue,
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
        Picker("Recurso", selection: $grantID) {
          Text("Conta pessoal").tag(app.store.currentUser.id)
          ForEach(app.store.snapshot.organizations) { organization in
            Text(organization.name).tag(organization.id)
          }
        }
      }
    }
    .navigationTitle("Nova chave")
    .toolbar {
      ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() } }
      ToolbarItem(placement: .confirmationAction) {
        Button("Criar") { Task { await create() } }.disabled(name.isEmpty || scopes.isEmpty)
      }
    }
  }

  private func create() async {
    let resourceType: WorkspaceResourceType =
      grantID == app.store.currentUser.id
      ? .user : .organization
    let draft = APIKeyDraft(
      name: name,
      scopes: scopes,
      grants: [APIKeyGrant(resourceType: resourceType, resourceID: grantID)],
      expiresAt: Date(timeIntervalSinceNow: 31_536_000)
    )
    do {
      let secret = try await app.store.createAPIKey(draft)
      dismiss()
      await onCreated(secret)
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
        Text("Este segredo sintético não será exibido novamente.")
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
  public var id: UUID { metadata.id }
}
