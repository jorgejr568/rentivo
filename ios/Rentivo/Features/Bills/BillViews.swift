import SwiftUI
import UniformTypeIdentifiers

private struct EditableBillLine: Identifiable {
  let id: BillLineItemID
  var description: String
  var centavos: Int
  var kind: BillLineItemKind

  init(line: BillLineItem) {
    id = line.id
    description = line.description
    centavos = line.amount.centavos
    kind = line.kind
  }

  init(description: String = "", centavos: Int = 0, kind: BillLineItemKind) {
    id = BillLineItemID(rawValue: UUID().uuidString)
    self.description = description
    self.centavos = centavos
    self.kind = kind
  }

  var domain: BillLineItem {
    BillLineItem(
      id: id,
      description: description,
      amount: Money(centavos: centavos),
      kind: kind
    )
  }
}

struct BillFormView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let billing: Billing
  let bill: Bill?
  let onSaved: () async -> Void

  @State private var year: Int
  @State private var month: Int
  @State private var dueDay: Int
  @State private var notes: String
  @State private var lines: [EditableBillLine]
  @State private var issues: [ValidationIssue] = []
  @State private var saving = false

  init(billing: Billing, bill: Bill? = nil, onSaved: @escaping () async -> Void) {
    self.billing = billing
    self.bill = bill
    self.onSaved = onSaved
    _year = State(initialValue: bill?.referenceMonth.year ?? 2026)
    _month = State(initialValue: bill?.referenceMonth.month ?? 7)
    _dueDay = State(initialValue: bill?.dueDate.day ?? 10)
    _notes = State(initialValue: bill?.notes ?? "")
    let initialLines =
      bill?.lineItems.map(EditableBillLine.init)
      ?? billing.items.map { item in
        EditableBillLine(
          description: item.description,
          centavos: item.amount.centavos,
          kind: item.type == .fixed ? .fixed : .variable
        )
      }
    _lines = State(initialValue: initialLines)
  }

  var body: some View {
    Form {
      Section("Competência e vencimento") {
        Picker("Mês", selection: $month) {
          ForEach(1...12, id: \.self) { Text(monthName($0)).tag($0) }
        }
        Stepper("Ano: \(year)", value: $year, in: 2024...2035)
        Stepper("Dia do vencimento: \(dueDay)", value: $dueDay, in: 1...28)
      }

      ForEach(BillLineItemKind.allCases, id: \.self) { kind in
        Section(kind.sectionTitle) {
          ForEach($lines) { $line in
            if line.kind == kind {
              VStack(alignment: .leading, spacing: RentivoSpacing.small) {
                TextField("Descrição", text: $line.description)
                TextField("Valor em centavos", value: $line.centavos, format: .number)
                  .keyboardType(.numberPad)
              }
            }
          }
          if kind != .fixed {
            Button {
              lines.append(EditableBillLine(kind: kind))
            } label: {
              Label("Adicionar \(kind.actionLabel)", systemImage: "plus.circle.fill")
            }
          }
        }
      }

      Section("Observações") {
        TextField("Mensagem opcional", text: $notes, axis: .vertical)
          .lineLimit(3...6)
      }

      Section("Total") {
        MoneyText(money: total)
      }

      if !issues.isEmpty {
        Section("Revise a fatura") {
          ForEach(issues, id: \.self) { issue in
            Label(issue.message, systemImage: "exclamationmark.circle.fill")
              .foregroundStyle(RentivoColors.coral)
          }
        }
      }
    }
    .navigationTitle(bill == nil ? "Gerar fatura" : "Editar fatura")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .cancellationAction) {
        Button("Cancelar") { dismiss() }
      }
      ToolbarItem(placement: .confirmationAction) {
        Button("Salvar") { Task { await save() } }
          .disabled(saving)
          .accessibilityIdentifier("bill.form.save")
      }
    }
  }

  private var total: Money {
    lines.map { Money(centavos: $0.centavos) }.reduce(.zero, +)
  }

  private func save() async {
    let draft = BillDraft(
      billingID: billing.id,
      referenceMonth: ReferenceMonth(year: year, month: month),
      dueDate: DateOnly(year: year, month: month, day: dueDay),
      notes: notes,
      lineItems: lines.map(\.domain)
    )
    issues = draft.validate()
    guard issues.isEmpty else { return }
    saving = true
    defer { saving = false }
    do {
      if let bill {
        _ = try await app.dependencies.bills.updateBill(
          billingID: billing.id,
          billID: bill.id,
          draft: draft
        )
      } else {
        _ = try await app.dependencies.bills.createBill(draft)
      }
      await onSaved()
      app.showNotice(bill == nil ? "Fatura criada como rascunho." : "Fatura atualizada.")
      dismiss()
    } catch {
      app.showNotice(DemoError(error).message, kind: .warning)
    }
  }

  private func monthName(_ month: Int) -> String {
    ReferenceMonth(year: year, month: month).label.components(separatedBy: " de ").first?
      .capitalized
      ?? "Mês"
  }
}

struct BillDetailView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let billingID: BillingID
  let billID: BillID
  let onMutation: () async -> Void

  @State private var state: LoadState<Bill> = .idle
  @State private var billing: Billing?
  @State private var showingEdit = false
  @State private var downloadedFile: DownloadedFile?
  @State private var showingCommunication = false
  @State private var confirmingDelete = false

  var body: some View {
    PageStateView(state: state) { bill in
      content(bill)
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Fatura")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      if state.value?.status == .draft && billing?.capabilities.canManageBills == true {
        Button("Editar") { showingEdit = true }
      }
    }
    .sheet(isPresented: $showingEdit) {
      if let billing, let bill = state.value {
        NavigationStack {
          BillFormView(billing: billing, bill: bill) {
            await refreshAll()
          }
        }
      }
    }
    .sheet(item: $downloadedFile) { file in DownloadShareView(file: file) }
    .sheet(isPresented: $showingCommunication) {
      if let billing {
        NavigationStack {
          CommunicationComposerView(
            billingID: billing.id,
            billID: billID,
            initialRecipients: billing.recipients.map(\.email)
          )
        }
      }
    }
    .confirmationDialog("Excluir esta fatura?", isPresented: $confirmingDelete) {
      Button("Excluir fatura", role: .destructive) { Task { await deleteBill() } }
      Button("Cancelar", role: .cancel) {}
    }
    .task(id: app.dataRevision) { await load() }
  }

  private func content(_ bill: Bill) -> some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: RentivoSpacing.section) {
        RentivoCard {
          VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
            HStack {
              VStack(alignment: .leading, spacing: RentivoSpacing.tiny) {
                Text(billing?.name ?? "Cobrança")
                  .font(.subheadline.weight(.semibold))
                  .foregroundStyle(RentivoColors.secondaryInk)
                Text(bill.referenceMonth.label.capitalized)
                  .font(RentivoTypography.title)
              }
              Spacer()
              StatusBadge(status: bill.status)
            }
            MoneyText(money: bill.total)
            Label("Vencimento: \(bill.dueDate.iso8601)", systemImage: "calendar")
              .font(.subheadline)
            if let paidAt = bill.paidAt {
              Label("Pago em \(paidAt.iso8601)", systemImage: "checkmark.seal.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(RentivoColors.emerald)
            }
          }
        }

        lineItems(bill)
        if billing?.capabilities.canManageBills == true {
          lifecycle(bill)
        } else {
          Label("Ciclo disponível somente para quem pode gerenciar faturas.", systemImage: "eye")
            .font(.footnote)
            .foregroundStyle(RentivoColors.secondaryInk)
        }

        VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
          SectionTitle(title: "Documento", symbol: "doc.richtext.fill")
          Button {
            Task { await downloadInvoice() }
          } label: {
            Label("Abrir fatura em PDF", systemImage: "doc.text.magnifyingglass")
          }
          .buttonStyle(RentivoButtonStyle(color: RentivoColors.blue))
          HStack {
            Button("Regenerar documento") { Task { await regenerate(bill) } }
              .disabled(billing?.capabilities.canManageBills != true)
            if bill.status == .paid {
              Button("Abrir recibo") { Task { await downloadRecibo() } }
            }
          }
          .buttonStyle(.bordered)
        }

        ReceiptManagerView(
          billingID: billingID,
          bill: bill,
          canWrite: billing?.capabilities.canUploadBillReceipts == true
        ) { await refreshAll() }

        if billing?.capabilities.canManageBills == true {
          Button {
            showingCommunication = true
          } label: {
            Label("Enviar comunicação", systemImage: "paperplane.fill")
          }
          .buttonStyle(RentivoButtonStyle())
        }

        if billing?.capabilities.canManageBills == true {
          Button(role: .destructive) {
            confirmingDelete = true
          } label: {
            Label("Excluir fatura", systemImage: "trash")
              .frame(maxWidth: .infinity)
          }
          .buttonStyle(.bordered)
        }
      }
      .padding(RentivoSpacing.page)
    }
  }

  private func lineItems(_ bill: Bill) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Composição", symbol: "list.bullet")
      RentivoCard {
        VStack(spacing: RentivoSpacing.medium) {
          ForEach(bill.lineItems) { line in
            HStack {
              VStack(alignment: .leading) {
                Text(line.description).font(.subheadline.weight(.semibold))
                Text(line.kind.sectionTitle)
                  .font(.caption)
                  .foregroundStyle(RentivoColors.secondaryInk)
              }
              Spacer()
              MoneyText(money: line.amount)
            }
          }
          if !bill.notes.isEmpty {
            Divider()
            Text(bill.notes)
              .font(.footnote)
              .foregroundStyle(RentivoColors.secondaryInk)
          }
        }
      }
    }
  }

  private func lifecycle(_ bill: Bill) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Ciclo da fatura", symbol: "arrow.triangle.2.circlepath")
      if bill.status.allowedTransitions.isEmpty {
        Label("Esta fatura está em um estado final.", systemImage: "checkmark.circle")
          .foregroundStyle(RentivoColors.secondaryInk)
      } else {
        ForEach(
          bill.status.allowedTransitions.sorted { $0.rawValue < $1.rawValue },
          id: \.self
        ) { status in
          Button {
            Task { await transition(to: status) }
          } label: {
            Label("Marcar como \(status.label.lowercased())", systemImage: status.symbol)
              .frame(maxWidth: .infinity)
          }
          .buttonStyle(.borderedProminent)
          .accessibilityIdentifier("bill.transition.\(status.rawValue)")
        }
      }
    }
  }

  private func load() async {
    state = .loading
    do {
      billing = try await app.dependencies.billings.billing(id: billingID)
      state = .loaded(try await app.dependencies.bills.bill(billingID: billingID, id: billID))
    } catch {
      state = .failed(DemoError(error))
    }
  }

  private func refreshAll() async {
    await load()
    await onMutation()
  }

  private func transition(to status: BillStatus) async {
    do {
      try await app.dependencies.bills.transitionBill(
        billingID: billingID, billID: billID, to: status)
      await refreshAll()
      app.showNotice("Fatura marcada como \(status.label.lowercased()).")
    } catch {
      app.showNotice(DemoError(error).message, kind: .warning)
    }
  }

  private func deleteBill() async {
    do {
      try await app.dependencies.bills.deleteBill(billingID: billingID, billID: billID)
      await onMutation()
      dismiss()
    } catch {
      app.showNotice(DemoError(error).message, kind: .warning)
    }
  }

  private func regenerate(_ bill: Bill) async {
    do {
      _ = try await app.dependencies.bills.regenerateBill(billingID: billingID, billID: bill.id)
      await refreshAll()
      await onMutation()
      app.showNotice("Documento enfileirado para regeneração.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func downloadInvoice() async {
    do { downloadedFile = try await app.dependencies.downloads.downloadInvoice(billingID: billingID, billID: billID) }
    catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func downloadRecibo() async {
    do { downloadedFile = try await app.dependencies.downloads.downloadRecibo(billingID: billingID, billID: billID) }
    catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

private struct ReceiptManagerView: View {
  @Environment(AppModel.self) private var app
  let billingID: BillingID
  let bill: Bill
  let canWrite: Bool
  let onMutation: () async -> Void
  @State private var downloadedFile: DownloadedFile?
  @State private var showingFileImporter = false

  var body: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Comprovantes", symbol: "paperclip")
      if bill.receipts.isEmpty {
        Text("Nenhum comprovante anexado.")
          .foregroundStyle(RentivoColors.secondaryInk)
      } else {
        RentivoCard {
          VStack(spacing: RentivoSpacing.medium) {
            ForEach(bill.receipts) { receipt in
              HStack {
                Label(receipt.name, systemImage: "doc.fill")
                  .font(.subheadline)
                Spacer()
                Menu {
                  Button("Abrir") { Task { await download(receipt) } }
                  if canWrite {
                    Button("Excluir", role: .destructive) { Task { await remove(receipt) } }
                  }
                } label: {
                  Image(systemName: "ellipsis.circle")
                }
              }
            }
            if bill.receipts.count > 1 && canWrite {
              Button("Inverter ordem") { Task { await reverse() } }
                .buttonStyle(.bordered)
            }
          }
        }
      }
      if canWrite {
        Button {
          showingFileImporter = true
        } label: {
          Label("Adicionar comprovante", systemImage: "plus")
        }
        .buttonStyle(.bordered)
      }
    }
    .sheet(item: $downloadedFile) { file in DownloadShareView(file: file) }
    .fileImporter(
      isPresented: $showingFileImporter,
      allowedContentTypes: [UTType.pdf, UTType.image],
      allowsMultipleSelection: false
    ) { result in
      guard case .success(let urls) = result, let url = urls.first else { return }
      Task { await add(fileURL: url) }
    }
  }

  private func add(fileURL: URL) async {
    do {
      let accessGranted = fileURL.startAccessingSecurityScopedResource()
      defer { if accessGranted { fileURL.stopAccessingSecurityScopedResource() } }
      let upload = try FileUpload.from(url: fileURL)
      _ = try await app.dependencies.bills.addReceipt(
        billingID: billingID,
        billID: bill.id,
        upload: upload
      )
      await onMutation()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func remove(_ receipt: Receipt) async {
    do {
      try await app.dependencies.bills.deleteReceipt(
        billingID: billingID,
        billID: bill.id,
        receiptID: receipt.id
      )
      await onMutation()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func reverse() async {
    do {
      try await app.dependencies.bills.reorderReceipts(
        billingID: billingID, billID: bill.id, receiptIDs: Array(bill.receipts.map(\.id).reversed())
      )
      await onMutation()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func download(_ receipt: Receipt) async {
    do {
      downloadedFile = try await app.dependencies.downloads.downloadReceipt(
        billingID: billingID, billID: bill.id, receiptID: receipt.id
      )
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

}

extension BillLineItemKind {
  fileprivate var sectionTitle: String {
    switch self {
    case .fixed: "Itens fixos"
    case .variable: "Itens variáveis"
    case .extra: "Itens extras"
    }
  }

  fileprivate var actionLabel: String {
    switch self {
    case .fixed: "item fixo"
    case .variable: "valor variável"
    case .extra: "item extra"
    }
  }
}

extension BillStatus {
  fileprivate var symbol: String {
    switch self {
    case .draft: "pencil.circle"
    case .published: "megaphone.fill"
    case .sent: "paperplane.fill"
    case .paid: "checkmark.seal.fill"
    case .cancelled: "xmark.circle.fill"
    case .delayedPayment: "clock.badge.exclamationmark.fill"
    }
  }
}
