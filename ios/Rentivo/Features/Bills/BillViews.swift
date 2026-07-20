import SwiftUI

private struct EditableBillLine: Identifiable {
  let id: UUID
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
    id = UUID()
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
        _ = try await app.store.updateBill(
          billingID: billing.id,
          billID: bill.id,
          draft: draft
        )
      } else {
        _ = try await app.store.createBill(draft)
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
  let billingID: UUID
  let billID: UUID
  let onMutation: () async -> Void

  @State private var state: LoadState<Bill> = .idle
  @State private var billing: Billing?
  @State private var showingEdit = false
  @State private var showingDocument = false
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
      if state.value?.status == .draft {
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
    .sheet(isPresented: $showingDocument) {
      if let bill = state.value {
        BillDocumentPreview(bill: bill, billingName: billing?.name ?? "Cobrança")
      }
    }
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
    .task { await load() }
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
        lifecycle(bill)

        VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
          SectionTitle(title: "Documento", symbol: "doc.richtext.fill")
          Button {
            showingDocument = true
          } label: {
            Label("Visualizar PDF simulado", systemImage: "doc.text.magnifyingglass")
          }
          .buttonStyle(RentivoButtonStyle(color: RentivoColors.blue))
        }

        ReceiptManagerView(billingID: billingID, bill: bill) { await refreshAll() }

        Button {
          showingCommunication = true
        } label: {
          Label("Enviar comunicação simulada", systemImage: "paperplane.fill")
        }
        .buttonStyle(RentivoButtonStyle())

        Button(role: .destructive) {
          confirmingDelete = true
        } label: {
          Label("Excluir fatura", systemImage: "trash")
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
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
        }
      }
    }
  }

  private func load() async {
    state = .loading
    do {
      billing = try await app.store.billing(id: billingID)
      state = .loaded(try await app.store.bill(billingID: billingID, id: billID))
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
      try await app.store.transitionBill(billingID: billingID, billID: billID, to: status)
      await refreshAll()
      app.showNotice("Fatura marcada como \(status.label.lowercased()).")
    } catch {
      app.showNotice(DemoError(error).message, kind: .warning)
    }
  }

  private func deleteBill() async {
    do {
      try await app.store.deleteBill(billingID: billingID, billID: billID)
      await onMutation()
      dismiss()
    } catch {
      app.showNotice(DemoError(error).message, kind: .warning)
    }
  }
}

private struct ReceiptManagerView: View {
  @Environment(AppModel.self) private var app
  let billingID: UUID
  let bill: Bill
  let onMutation: () async -> Void

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
                Button(role: .destructive) {
                  Task { await remove(receipt) }
                } label: {
                  Image(systemName: "trash")
                }
              }
            }
            if bill.receipts.count > 1 {
              Button("Inverter ordem") { Task { await reverse() } }
                .buttonStyle(.bordered)
            }
          }
        }
      }
      Button {
        Task { await add() }
      } label: {
        Label("Adicionar comprovante simulado", systemImage: "plus")
      }
      .buttonStyle(.bordered)
    }
  }

  private func add() async {
    do {
      _ = try await app.store.addReceipt(
        billingID: billingID,
        billID: bill.id,
        name: "comprovante-demo.pdf"
      )
      await onMutation()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func remove(_ receipt: Receipt) async {
    do {
      try await app.store.deleteReceipt(
        billingID: billingID,
        billID: bill.id,
        receiptID: receipt.id
      )
      await onMutation()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func reverse() async {
    do {
      try await app.store.reorderReceipts(
        billingID: billingID,
        billID: bill.id,
        receiptIDs: Array(bill.receipts.map(\.id).reversed())
      )
      await onMutation()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

struct BillDocumentPreview: View {
  @Environment(\.dismiss) private var dismiss
  let bill: Bill
  let billingName: String

  var body: some View {
    NavigationStack {
      ScrollView {
        VStack(alignment: .leading, spacing: RentivoSpacing.large) {
          BrandMark()
          Text("FATURA")
            .font(.system(.largeTitle, design: .monospaced, weight: .black))
          Text(billingName).font(RentivoTypography.title)
          Text(bill.referenceMonth.label.capitalized)
          Divider()
          ForEach(bill.lineItems) { line in
            HStack {
              Text(line.description)
              Spacer()
              Text(line.amount.formatted()).monospacedDigit()
            }
          }
          Divider()
          HStack {
            Text("TOTAL").font(.headline)
            Spacer()
            MoneyText(money: bill.total)
          }
          Label("Prévia local — nenhum PDF foi gerado.", systemImage: "info.circle.fill")
            .font(.footnote)
            .foregroundStyle(RentivoColors.blue)
        }
        .padding(RentivoSpacing.page)
        .background(RentivoColors.surface)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .padding(RentivoSpacing.page)
      }
      .background(RentivoColors.paper)
      .navigationTitle("Prévia")
      .toolbar {
        Button("Concluir") { dismiss() }
      }
    }
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
