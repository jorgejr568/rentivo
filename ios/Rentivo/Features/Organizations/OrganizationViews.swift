import SwiftUI

private struct OrganizationListItem: Identifiable, Sendable {
  let organization: Organization
  let billingCount: Int
  var id: UUID { organization.id }
}

struct OrganizationListView: View {
  @Environment(AppModel.self) private var app
  @State private var state: LoadState<[OrganizationListItem]> = .idle
  @State private var pendingCount = 0
  @State private var showingCreate = false

  var body: some View {
    PageStateView(state: state) { organizations in
      ScrollView {
        LazyVStack(spacing: RentivoSpacing.large) {
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
      ToolbarItemGroup(placement: .topBarTrailing) {
        NavigationLink {
          InvitationListView { await load() }
        } label: {
          Label("Convites", systemImage: pendingCount > 0 ? "envelope.badge.fill" : "envelope")
        }
        .accessibilityValue("\(pendingCount) pendentes")
        Button {
          showingCreate = true
        } label: {
          Label("Criar", systemImage: "plus")
        }
      }
    }
    .sheet(isPresented: $showingCreate) {
      NavigationStack {
        OrganizationFormView { await load() }
      }
    }
    .task { await load() }
    .refreshable { await load() }
  }

  private func load() async {
    state = .loading
    do {
      let organizations = try await app.store.listOrganizations()
      let billings = try await app.store.listBillings()
      let values = organizations.map { organization in
        OrganizationListItem(
          organization: organization,
          billingCount: billings.filter { $0.owner.id == organization.id }.count
        )
      }
      pendingCount = try await app.store.listPendingInvitations().count
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
        _ = try await app.store.updateOrganization(id: organization.id, draft: draft)
      } else {
        _ = try await app.store.createOrganization(draft)
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
  let organizationID: UUID
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
    .toolbar { Button("Editar") { showingEdit = true } }
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
      Text("A política será aplicada apenas ao estado local desta demonstração.")
    }
    .confirmationDialog("Excluir organização?", isPresented: $confirmingDelete) {
      Button("Excluir", role: .destructive) { Task { await deleteOrganization() } }
      Button("Cancelar", role: .cancel) {}
    } message: {
      Text("Primeiro transfira todas as cobranças vinculadas.")
    }
    .task { await load() }
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

        Button(role: .destructive) {
          confirmingDelete = true
        } label: {
          Label("Excluir organização", systemImage: "trash").frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
      }
      .padding(RentivoSpacing.page)
    }
  }

  private func memberSection(_ organization: Organization) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      HStack {
        SectionTitle(title: "Membros", symbol: "person.2.fill")
        Spacer()
        Button {
          showingInvite = true
        } label: {
          Image(systemName: "person.badge.plus")
        }
        .accessibilityLabel("Convidar membro")
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
              if member.role != .owner {
                Menu {
                  ForEach(OrganizationRole.allCases.filter { $0 != .owner }, id: \.self) { role in
                    Button(role.label) { Task { await changeRole(member, to: role) } }
                  }
                  Divider()
                  Button("Remover", role: .destructive) { Task { await remove(member) } }
                } label: {
                  Image(systemName: "ellipsis.circle")
                }
              } else {
                Image(systemName: "crown.fill").foregroundStyle(RentivoColors.amber)
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
      }
    }
  }

  private func billingSection(_ organization: Organization) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Cobranças", symbol: "house.fill")
      let owned = billings.filter { $0.owner.id == organization.id }
      if owned.isEmpty {
        Text("Nenhuma cobrança pertence a esta organização.")
          .foregroundStyle(RentivoColors.secondaryInk)
      } else {
        ForEach(owned) { billing in
          RentivoCard {
            HStack {
              Text(billing.name).font(.subheadline.weight(.semibold))
              Spacer()
              Button("Tornar pessoal") { Task { await makePersonal(billing) } }
                .font(.caption)
            }
          }
        }
      }
      let personal = billings.filter { !$0.owner.isOrganization }
      if !personal.isEmpty {
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
      async let organization = app.store.organization(id: organizationID)
      async let values = app.store.listBillings()
      let (loadedOrganization, loadedBillings) = try await (organization, values)
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
      try await app.store.updateMemberRole(
        organizationID: organizationID,
        userID: member.userID,
        role: role
      )
      await refreshAll()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func remove(_ member: OrganizationMember) async {
    do {
      try await app.store.removeMember(organizationID: organizationID, userID: member.userID)
      await refreshAll()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func toggleMFA() async {
    guard let organization = state.value else { return }
    do {
      try await app.store.setOrganizationMFA(
        organizationID: organizationID,
        required: !organization.requiresMFA
      )
      await refreshAll()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func transfer(_ billing: Billing, to organization: Organization) async {
    do {
      try await app.store.transferBilling(
        billingID: billing.id,
        toOrganizationID: organization.id
      )
      await refreshAll()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func makePersonal(_ billing: Billing) async {
    do {
      try await app.store.transferBillingToPersonal(billingID: billing.id)
      await refreshAll()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func deleteOrganization() async {
    do {
      try await app.store.deleteOrganization(id: organizationID)
      await onMutation()
      dismiss()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}
