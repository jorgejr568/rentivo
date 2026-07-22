import SwiftUI

private struct OrganizationListItem: Identifiable, Sendable {
  let organization: Organization
  let billingCount: Int
  var id: OrganizationID { organization.id }
}

struct OrganizationListView: View {
  @Environment(AppModel.self) private var app
  @State private var state: LoadState<[OrganizationListItem]> = .idle
  @State private var pendingCount = 0
  @State private var showingCreate = false
  @State private var showingInvitations = false

  var body: some View {
    PageStateView(state: state) { organizations in
      ScrollView {
        LazyVStack(spacing: RentivoSpacing.large) {
          if pendingCount > 0 {
            Button {
              showingInvitations = true
            } label: {
              RentivoCard {
                HStack {
                  Label(
                    "\(pendingCount) convite pendente",
                    systemImage: "envelope.badge.fill"
                  )
                  .font(.headline)
                  Spacer()
                  Image(systemName: "chevron.right")
                }
              }
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("organization.invitations.open")
          }
          ForEach(organizations) { item in
            NavigationLink {
              OrganizationDetailView(organizationID: item.id) { await load() }
            } label: {
              OrganizationCard(item: item)
            }
            .buttonStyle(.plain)
          }
        }
        .padding(RentivoSpacing.page)
      }
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Organizações")
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        if !app.demoSettings.viewerMode {
          Button {
            showingCreate = true
          } label: {
            Label("Criar", systemImage: "plus")
          }
        }
      }
    }
    .sheet(isPresented: $showingCreate) {
      NavigationStack {
        OrganizationFormView { await load() }
      }
    }
    .sheet(isPresented: $showingInvitations) {
      NavigationStack {
        InvitationListView { await load() }
      }
    }
    .task(id: app.dataRevision) { await load() }
    .refreshable { await load() }
  }

  private func load() async {
    state = .loading
    do {
      let organizations = try await app.dependencies.organizations.listOrganizations()
      let billings = try await app.dependencies.billings.listBillings()
      let values = organizations.map { organization in
        OrganizationListItem(
          organization: organization,
          billingCount: billings.filter { $0.owner.workspaceID.rawValue == organization.id.rawValue }.count
        )
      }
      pendingCount = try await app.dependencies.invitations.listPendingInvitations().count
      state = values.isEmpty ? .empty : .loaded(values)
    } catch { state = .failed(DemoError(error)) }
  }
}

private struct OrganizationCard: View {
  let item: OrganizationListItem

  var body: some View {
    RentivoCard {
      VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
        HStack(alignment: .top) {
          Image(systemName: "building.2.fill")
            .font(.title2)
            .foregroundStyle(RentivoColors.emerald)
          VStack(alignment: .leading, spacing: RentivoSpacing.tiny) {
            Text(item.organization.name)
              .font(RentivoTypography.cardTitle)
              .foregroundStyle(RentivoColors.ink)
            Text(item.organization.currentUserRole.label)
              .font(.caption.weight(.semibold))
              .foregroundStyle(RentivoColors.secondaryInk)
          }
          Spacer()
          Image(systemName: "chevron.right")
            .foregroundStyle(RentivoColors.secondaryInk)
        }
        HStack {
          Label("\(item.organization.members.count) membros", systemImage: "person.2.fill")
          Spacer()
          Label("\(item.billingCount) cobranças", systemImage: "house.fill")
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(RentivoColors.secondaryInk)
        Label(
          item.organization.requiresMFA ? "MFA obrigatório" : "MFA opcional",
          systemImage: item.organization.requiresMFA ? "lock.shield.fill" : "lock.open"
        )
        .font(.caption.weight(.semibold))
        .foregroundStyle(
          item.organization.requiresMFA ? RentivoColors.emerald : RentivoColors.secondaryInk
        )
      }
    }
  }
}

struct OrganizationFormView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let organization: Organization?
  let onSaved: () async -> Void
  @State private var name: String
  @State private var pixKey: String
  @State private var merchantName: String
  @State private var city: String

  init(organization: Organization? = nil, onSaved: @escaping () async -> Void) {
    self.organization = organization
    self.onSaved = onSaved
    _name = State(initialValue: organization?.name ?? "")
    _pixKey = State(initialValue: organization?.pix?.key ?? "")
    _merchantName = State(initialValue: organization?.pix?.merchantName ?? "")
    _city = State(initialValue: organization?.pix?.merchantCity ?? "")
  }

  var body: some View {
    Form {
      Section("Organização") {
        TextField("Nome", text: $name)
      }
      Section("PIX") {
        TextField("Chave", text: $pixKey)
        TextField("Nome do recebedor", text: $merchantName)
        TextField("Cidade", text: $city)
          .textInputAutocapitalization(.characters)
      }
    }
    .navigationTitle(organization == nil ? "Nova organização" : "Editar organização")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() } }
      ToolbarItem(placement: .confirmationAction) {
        Button("Salvar") { Task { await save() } }.disabled(name.isEmpty)
      }
    }
  }

  private func save() async {
    let pix: PixConfiguration? =
      pixKey.isEmpty
      ? nil
      : PixConfiguration(key: pixKey, merchantName: merchantName, merchantCity: city)
    let draft = OrganizationDraft(name: name, pix: pix)
    do {
      if let organization {
        _ = try await app.dependencies.organizations.updateOrganization(
          id: organization.id, draft: draft)
      } else {
        _ = try await app.dependencies.organizations.createOrganization(draft)
      }
      await onSaved()
      dismiss()
      app.showNotice(organization == nil ? "Organização criada." : "Organização atualizada.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

struct OrganizationDetailView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let organizationID: OrganizationID
  let onMutation: () async -> Void
  @State private var state: LoadState<Organization> = .idle
  @State private var billings: [Billing] = []
  @State private var showingEdit = false
  @State private var showingInvite = false
  @State private var confirmingMFA = false
  @State private var confirmingDelete = false

  var body: some View {
    PageStateView(state: state) { organization in
      content(organization)
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Organização")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      if state.value?.capabilities.canManage == true {
        Button("Editar") { showingEdit = true }
      }
    }
    .sheet(isPresented: $showingEdit) {
      if let organization = state.value {
        NavigationStack {
          OrganizationFormView(organization: organization) { await refreshAll() }
        }
      }
    }
    .sheet(isPresented: $showingInvite) {
      if let organization = state.value {
        NavigationStack {
          InviteMemberView(organization: organization) { await refreshAll() }
        }
      }
    }
    .confirmationDialog(
      state.value?.requiresMFA == true ? "Tornar MFA opcional?" : "Exigir MFA?",
      isPresented: $confirmingMFA
    ) {
      Button("Confirmar") { Task { await toggleMFA() } }
      Button("Cancelar", role: .cancel) {}
    } message: {
      Text("A política será aplicada a todos os membros desta organização.")
    }
    .confirmationDialog("Excluir organização?", isPresented: $confirmingDelete) {
      Button("Excluir", role: .destructive) { Task { await deleteOrganization() } }
      Button("Cancelar", role: .cancel) {}
    } message: {
      Text("Primeiro transfira todas as cobranças vinculadas.")
    }
    .task(id: app.dataRevision) { await load() }
  }

  private func content(_ organization: Organization) -> some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: RentivoSpacing.section) {
        RentivoCard {
          VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
            Text(organization.name).font(RentivoTypography.title)
            Label(organization.currentUserRole.label, systemImage: "person.badge.shield.checkmark")
            Label(
              organization.pix?.isComplete == true ? "PIX configurado" : "PIX pendente",
              systemImage: "qrcode"
            )
          }
        }

        memberSection(organization)
        policySection(organization)
        billingSection(organization)

        NavigationLink {
          ThemeEditorView(target: .organization(organizationID))
        } label: {
          Label("Aparência da organização", systemImage: "paintpalette.fill")
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(RentivoButtonStyle(color: RentivoColors.blue))
        .accessibilityIdentifier("organization.theme")

        if organization.capabilities.canManage {
          Button(role: .destructive) {
            confirmingDelete = true
          } label: {
            Label("Excluir organização", systemImage: "trash").frame(maxWidth: .infinity)
          }
          .buttonStyle(.bordered)
        } else {
          Label(
            "Seu papel permite consultar esta organização, sem alterar sua configuração.",
            systemImage: "eye.fill"
          )
          .font(.footnote.weight(.semibold))
          .foregroundStyle(RentivoColors.secondaryInk)
        }
      }
      .padding(RentivoSpacing.page)
    }
  }

  private func memberSection(_ organization: Organization) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      HStack {
        SectionTitle(title: "Membros", symbol: "person.2.fill")
        Spacer()
        if organization.capabilities.canInvite {
          Button {
            showingInvite = true
          } label: {
            Image(systemName: "person.badge.plus")
          }
          .accessibilityLabel("Convidar membro")
        }
      }
      RentivoCard {
        VStack(spacing: RentivoSpacing.medium) {
          ForEach(organization.members) { member in
            HStack {
              VStack(alignment: .leading) {
                Text(member.email).font(.subheadline.weight(.semibold))
                Text(member.role.label)
                  .font(.caption)
                  .foregroundStyle(RentivoColors.secondaryInk)
              }
              Spacer()
              if member.role == .admin {
                Image(systemName: "crown.fill").foregroundStyle(RentivoColors.amber)
              } else if organization.capabilities.canManage {
                Menu {
                  ForEach(OrganizationRole.allCases.filter { $0 != .admin }, id: \.self) { role in
                    Button(role.label) { Task { await changeRole(member, to: role) } }
                  }
                  Divider()
                  Button("Remover", role: .destructive) { Task { await remove(member) } }
                } label: {
                  Image(systemName: "ellipsis.circle")
                }
              }
            }
          }
        }
      }
    }
  }

  private func policySection(_ organization: Organization) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Política de segurança", symbol: "lock.shield.fill")
      RentivoCard {
        HStack {
          VStack(alignment: .leading) {
            Text("Autenticação em duas etapas").font(.headline)
            Text(organization.requiresMFA ? "Obrigatória para membros" : "Opcional")
              .font(.caption)
              .foregroundStyle(RentivoColors.secondaryInk)
          }
          Spacer()
          Toggle("MFA", isOn: .constant(organization.requiresMFA))
            .labelsHidden()
            .allowsHitTesting(false)
        }
        .contentShape(Rectangle())
        .onTapGesture { confirmingMFA = true }
        .allowsHitTesting(organization.capabilities.canManage)
      }
    }
  }

  private func billingSection(_ organization: Organization) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Cobranças", symbol: "house.fill")
      let owned = billings.filter { $0.owner.workspaceID.rawValue == organization.id.rawValue }
      if owned.isEmpty {
        Text("Nenhuma cobrança pertence a esta organização.")
          .foregroundStyle(RentivoColors.secondaryInk)
      } else {
        ForEach(owned) { billing in
          RentivoCard {
            HStack {
              Text(billing.name).font(.subheadline.weight(.semibold))
              Spacer()
            }
          }
        }
      }
      let personal = billings.filter { !$0.owner.isOrganization }
      if !personal.isEmpty && organization.capabilities.canCreateBilling {
        Menu {
          ForEach(personal) { billing in
            Button(billing.name) { Task { await transfer(billing, to: organization) } }
          }
        } label: {
          Label("Transferir cobrança para cá", systemImage: "arrow.right.square.fill")
        }
        .buttonStyle(.bordered)
      }
    }
  }

  private func load() async {
    state = .loading
    do {
      let loadedOrganization = try await app.dependencies.organizations.organization(
        id: organizationID
      )
      let loadedBillings = try await app.dependencies.billings.listBillings()
      billings = loadedBillings
      state = .loaded(loadedOrganization)
    } catch { state = .failed(DemoError(error)) }
  }

  private func refreshAll() async {
    await load()
    await onMutation()
  }

  private func changeRole(_ member: OrganizationMember, to role: OrganizationRole) async {
    do {
      try await app.dependencies.organizations.updateMemberRole(
        organizationID: organizationID,
        userID: member.userID,
        role: role
      )
      await refreshAll()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func remove(_ member: OrganizationMember) async {
    do {
      try await app.dependencies.organizations.removeMember(
        organizationID: organizationID, userID: member.userID)
      await refreshAll()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func toggleMFA() async {
    guard let organization = state.value else { return }
    do {
      try await app.dependencies.organizations.setOrganizationMFA(
        organizationID: organizationID,
        required: !organization.requiresMFA
      )
      await refreshAll()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func transfer(_ billing: Billing, to organization: Organization) async {
    do {
      try await app.dependencies.organizations.transferBilling(
        billingID: billing.id,
        toOrganizationID: organization.id
      )
      await refreshAll()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func deleteOrganization() async {
    do {
      try await app.dependencies.organizations.deleteOrganization(id: organizationID)
      await onMutation()
      dismiss()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}
