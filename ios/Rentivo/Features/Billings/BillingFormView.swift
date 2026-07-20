import SwiftUI

private struct EditableBillingItem: Identifiable {
  let id: UUID
  var description: String
  var centavos: Int
  var type: BillingItemType

  init(item: BillingItem) {
    id = item.id
    description = item.description
    centavos = item.amount.centavos
    type = item.type
  }

  init(type: BillingItemType = .fixed) {
    id = UUID()
    description = ""
    centavos = 0
    self.type = type
  }

  func domain(sortOrder: Int) -> BillingItem {
    BillingItem(
      id: id,
      description: description,
      amount: Money(centavos: centavos),
      type: type,
      sortOrder: sortOrder
    )
  }
}

struct BillingFormView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  private let billing: Billing?
  private let onSaved: () async -> Void

  @State private var name: String
  @State private var billingDescription: String
  @State private var ownerID: UUID
  @State private var items: [EditableBillingItem]
  @State private var pixKey: String
  @State private var recipientName: String
  @State private var recipientEmail: String
  @State private var replyTo: String
  @State private var validationIssues: [ValidationIssue] = []
  @State private var saving = false
  @State private var organizations: [Organization] = []
  @State private var organizationsLoaded = false

  init(billing: Billing? = nil, onSaved: @escaping () async -> Void) {
    self.billing = billing
    self.onSaved = onSaved
    _name = State(initialValue: billing?.name ?? "")
    _billingDescription = State(initialValue: billing?.description ?? "")
    _ownerID = State(initialValue: billing?.owner.id ?? StableID.userAna)
    _items = State(initialValue: billing?.items.map(EditableBillingItem.init) ?? [])
    _pixKey = State(initialValue: billing?.pixOverride?.key ?? "")
    _recipientName = State(initialValue: billing?.recipients.first?.name ?? "")
    _recipientEmail = State(initialValue: billing?.recipients.first?.email ?? "")
    _replyTo = State(initialValue: billing?.replyTo ?? "")
  }

  var body: some View {
    Form {
      Section("Identificação") {
        TextField("Nome", text: $name)
          .accessibilityIdentifier("billing.form.name")
        TextField("Descrição", text: $billingDescription, axis: .vertical)
          .lineLimit(2...4)
        Picker("Responsável", selection: $ownerID) {
          ForEach(ownerChoices, id: \.id) { owner in
            Text(owner.name).tag(owner.id)
          }
        }
      }

      Section {
        ForEach($items) { $item in
          VStack(alignment: .leading, spacing: RentivoSpacing.small) {
            TextField("Descrição do item", text: $item.description)
            Picker("Tipo", selection: $item.type) {
              ForEach(BillingItemType.allCases, id: \.self) { type in
                Text(type.label).tag(type)
              }
            }
            .pickerStyle(.segmented)
            TextField("Valor em centavos", value: $item.centavos, format: .number)
              .keyboardType(.numberPad)
          }
          .padding(.vertical, RentivoSpacing.tiny)
        }
        .onDelete { items.remove(atOffsets: $0) }
        .onMove { items.move(fromOffsets: $0, toOffset: $1) }
        Button {
          items.append(EditableBillingItem())
        } label: {
          Label("Adicionar item", systemImage: "plus.circle.fill")
        }
      } header: {
        HStack {
          Text("Itens recorrentes")
          Spacer()
          EditButton()
        }
      } footer: {
        Text("Use valor zero para itens variáveis que serão preenchidos em cada fatura.")
      }

      Section("PIX opcional") {
        TextField("Chave PIX própria", text: $pixKey)
          .textInputAutocapitalization(.never)
        Text("Deixe em branco para herdar o PIX do responsável.")
          .font(.caption)
          .foregroundStyle(RentivoColors.secondaryInk)
      }

      Section("Comunicação") {
        TextField("Nome do destinatário", text: $recipientName)
        TextField("E-mail do destinatário", text: $recipientEmail)
          .keyboardType(.emailAddress)
          .textInputAutocapitalization(.never)
        TextField("Responder para", text: $replyTo)
          .keyboardType(.emailAddress)
          .textInputAutocapitalization(.never)
      }

      if !validationIssues.isEmpty {
        Section("Revise os campos") {
          ForEach(validationIssues, id: \.self) { issue in
            Label(issue.message, systemImage: "exclamationmark.circle.fill")
              .foregroundStyle(RentivoColors.coral)
              .accessibilityIdentifier("billing.form.validation")
          }
        }
      }
    }
    .navigationTitle(billing == nil ? "Nova cobrança" : "Editar cobrança")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .cancellationAction) {
        Button("Cancelar") { dismiss() }
      }
      ToolbarItem(placement: .confirmationAction) {
        Button("Salvar") { Task { await save() } }
          .disabled(saving || !organizationsLoaded)
          .accessibilityIdentifier("billing.form.save")
      }
    }
    .interactiveDismissDisabled(saving)
    .task {
      organizations = (try? await app.dependencies.organizations.listOrganizations()) ?? []
      organizationsLoaded = true
    }
  }

  private var ownerChoices: [BillingOwner] {
    var owners: [BillingOwner] = [
      .user(id: app.currentUser.id, name: "Pessoal")
    ]
    if let currentOwner = billing?.owner,
      !owners.contains(where: { $0.id == currentOwner.id })
    {
      owners.append(currentOwner)
    }
    let existingIDs = Set(owners.map(\.id))
    let organizationOwners =
      organizations
      .map { BillingOwner.organization(id: $0.id, name: $0.name) }
      .filter { !existingIDs.contains($0.id) }
    owners.append(contentsOf: organizationOwners)
    return owners
  }

  private func save() async {
    guard let owner = ownerChoices.first(where: { $0.id == ownerID }) else {
      app.showNotice("Não foi possível confirmar o responsável.", kind: .warning)
      return
    }
    let recipients: [BillingRecipient]
    if recipientName.isEmpty && recipientEmail.isEmpty {
      recipients = []
    } else {
      recipients = [
        BillingRecipient(
          id: billing?.recipients.first?.id ?? UUID(),
          name: recipientName,
          email: recipientEmail
        )
      ]
    }
    let pix = pixKey.trimmingCharacters(in: .whitespacesAndNewlines)
    let draft = BillingDraft(
      name: name,
      description: billingDescription,
      owner: owner,
      items: items.enumerated().map { $0.element.domain(sortOrder: $0.offset) },
      pixOverride: pix.isEmpty
        ? nil
        : PixConfiguration(key: pix, merchantName: "ANA SILVA", merchantCity: "SAO PAULO"),
      recipients: recipients,
      replyTo: replyTo.isEmpty ? nil : replyTo
    )
    validationIssues = draft.validate()
    guard validationIssues.isEmpty else { return }
    saving = true
    defer { saving = false }
    do {
      if let billing {
        _ = try await app.dependencies.billings.updateBilling(id: billing.id, draft: draft)
      } else {
        _ = try await app.dependencies.billings.createBilling(draft)
      }
      await onSaved()
      app.showNotice(billing == nil ? "Cobrança criada." : "Cobrança atualizada.")
      dismiss()
    } catch {
      app.showNotice(DemoError(error).message, kind: .warning)
    }
  }
}
