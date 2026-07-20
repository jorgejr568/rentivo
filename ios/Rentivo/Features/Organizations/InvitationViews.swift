import SwiftUI

struct InvitationListView: View {
  @Environment(AppModel.self) private var app
  let onMutation: () async -> Void
  @State private var state: LoadState<[Invitation]> = .idle

  var body: some View {
    PageStateView(state: state) { invitations in
      List {
        ForEach(invitations) { invitation in
          VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
            Text(invitation.organizationName).font(.headline)
            Label(invitation.role.label, systemImage: "person.badge.shield.checkmark")
              .font(.caption)
            HStack {
              Button("Aceitar") { Task { await respond(invitation, accept: true) } }
                .buttonStyle(.borderedProminent)
              Button("Recusar", role: .destructive) {
                Task { await respond(invitation, accept: false) }
              }
              .buttonStyle(.bordered)
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
    .navigationTitle("Convites")
    .task { await load() }
  }

  private func load() async {
    state = .loading
    do {
      let invitations = try await app.store.listPendingInvitations()
      state = invitations.isEmpty ? .empty : .loaded(invitations)
    } catch { state = .failed(DemoError(error)) }
  }

  private func respond(_ invitation: Invitation, accept: Bool) async {
    do {
      if accept {
        try await app.store.acceptInvitation(id: invitation.id)
      } else {
        try await app.store.declineInvitation(id: invitation.id)
      }
      await load()
      await onMutation()
      app.showNotice(accept ? "Convite aceito." : "Convite recusado.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

struct InviteMemberView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let organization: Organization
  let onSaved: () async -> Void
  @State private var email = ""
  @State private var role: OrganizationRole = .viewer

  var body: some View {
    Form {
      TextField("E-mail", text: $email)
        .keyboardType(.emailAddress)
        .textInputAutocapitalization(.never)
      Picker("Função", selection: $role) {
        ForEach(OrganizationRole.allCases.filter { $0 != .owner }, id: \.self) { role in
          Text(role.label).tag(role)
        }
      }
      Label("O convite ficará pendente apenas na memória do app.", systemImage: "info.circle")
        .font(.footnote)
    }
    .navigationTitle("Convidar membro")
    .toolbar {
      ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() } }
      ToolbarItem(placement: .confirmationAction) {
        Button("Convidar") { Task { await invite() } }.disabled(!email.contains("@"))
      }
    }
  }

  private func invite() async {
    do {
      _ = try await app.store.inviteMember(
        organizationID: organization.id,
        email: email,
        role: role
      )
      await onSaved()
      dismiss()
      app.showNotice("Convite simulado criado.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}
