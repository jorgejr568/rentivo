import SwiftUI

struct BillingOperationsLinks: View {
  let billingID: UUID
  let recipients: [String]
  let onMutation: () async -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Operações", symbol: "square.grid.2x2.fill")
      RentivoCard {
        VStack(spacing: RentivoSpacing.small) {
          NavigationLink {
            ExpenseListView(billingID: billingID, onMutation: onMutation)
          } label: {
            OperationRow(title: "Despesas", symbol: "wrench.and.screwdriver.fill")
          }
          Divider()
          NavigationLink {
            AttachmentListView(billingID: billingID)
          } label: {
            OperationRow(title: "Arquivos", symbol: "folder.fill")
          }
          Divider()
          NavigationLink {
            CommunicationComposerView(
              billingID: billingID,
              billID: nil,
              initialRecipients: recipients
            )
          } label: {
            OperationRow(title: "Comunicação", symbol: "paperplane.fill")
          }
          Divider()
          NavigationLink {
            ExportSimulationView(billingID: billingID)
          } label: {
            OperationRow(title: "Exportar dados", symbol: "square.and.arrow.up.fill")
          }
        }
      }
    }
  }
}

private struct OperationRow: View {
  let title: String
  let symbol: String

  var body: some View {
    HStack {
      Label(title, systemImage: symbol)
        .font(.subheadline.weight(.semibold))
        .foregroundStyle(RentivoColors.ink)
      Spacer()
      Image(systemName: "chevron.right")
        .foregroundStyle(RentivoColors.secondaryInk)
    }
    .contentShape(Rectangle())
    .padding(.vertical, RentivoSpacing.small)
  }
}

struct ExpenseListView: View {
  @Environment(AppModel.self) private var app
  let billingID: UUID
  let onMutation: () async -> Void
  @State private var state: LoadState<[Expense]> = .idle
  @State private var showingAdd = false

  var body: some View {
    PageStateView(state: state) { expenses in
      List {
        ForEach(expenses) { expense in
          VStack(alignment: .leading, spacing: RentivoSpacing.small) {
            HStack {
              Text(expense.description).font(.headline)
              Spacer()
              MoneyText(money: expense.amount)
            }
            Label(expense.category.label, systemImage: "tag.fill")
              .font(.caption)
              .foregroundStyle(RentivoColors.secondaryInk)
          }
          .swipeActions {
            Button("Excluir", role: .destructive) { Task { await remove(expense) } }
          }
        }
      }
      .scrollContentBackground(.hidden)
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Despesas")
    .toolbar {
      Button {
        showingAdd = true
      } label: {
        Label("Adicionar", systemImage: "plus")
      }
    }
    .sheet(isPresented: $showingAdd) {
      NavigationStack {
        ExpenseFormView(billingID: billingID) {
          await load()
          await onMutation()
        }
      }
    }
    .task { await load() }
  }

  private func load() async {
    state = .loading
    do {
      let expenses = try await app.store.listExpenses(billingID: billingID)
      state = expenses.isEmpty ? .empty : .loaded(expenses)
    } catch { state = .failed(DemoError(error)) }
  }

  private func remove(_ expense: Expense) async {
    do {
      try await app.store.deleteExpense(billingID: billingID, expenseID: expense.id)
      await load()
      await onMutation()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

private struct ExpenseFormView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let billingID: UUID
  let onSaved: () async -> Void
  @State private var description = ""
  @State private var centavos = 0
  @State private var category: ExpenseCategory = .maintenance

  var body: some View {
    Form {
      TextField("Descrição", text: $description)
      TextField("Valor em centavos", value: $centavos, format: .number)
        .keyboardType(.numberPad)
      Picker("Categoria", selection: $category) {
        ForEach(ExpenseCategory.allCases, id: \.self) { category in
          Text(category.label).tag(category)
        }
      }
      Text("A data usada nesta demonstração será 20/07/2026.")
        .font(.footnote)
    }
    .navigationTitle("Nova despesa")
    .toolbar {
      ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() } }
      ToolbarItem(placement: .confirmationAction) {
        Button("Salvar") { Task { await save() } }
          .disabled(description.isEmpty || centavos <= 0)
      }
    }
  }

  private func save() async {
    do {
      _ = try await app.store.createExpense(
        billingID: billingID,
        description: description,
        category: category,
        incurredOn: DateOnly(year: 2026, month: 7, day: 20),
        amount: Money(centavos: centavos)
      )
      await onSaved()
      dismiss()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

struct AttachmentListView: View {
  @Environment(AppModel.self) private var app
  let billingID: UUID
  @State private var state: LoadState<[Attachment]> = .idle

  var body: some View {
    PageStateView(state: state) { attachments in
      List {
        ForEach(attachments) { attachment in
          Label {
            VStack(alignment: .leading) {
              Text(attachment.name).font(.headline)
              Text(
                ByteCountFormatter.string(
                  fromByteCount: Int64(attachment.byteCount), countStyle: .file)
              )
              .font(.caption)
            }
          } icon: {
            Image(systemName: "doc.fill")
          }
          .swipeActions {
            Button("Excluir", role: .destructive) { Task { await remove(attachment) } }
          }
        }
      }
      .scrollContentBackground(.hidden)
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Arquivos")
    .toolbar {
      Button {
        Task { await add() }
      } label: {
        Label("Adicionar", systemImage: "plus")
      }
    }
    .task { await load() }
  }

  private func load() async {
    state = .loading
    do {
      let values = try await app.store.listAttachments(billingID: billingID)
      state = values.isEmpty ? .empty : .loaded(values)
    } catch { state = .failed(DemoError(error)) }
  }

  private func add() async {
    do {
      _ = try await app.store.addAttachment(
        billingID: billingID,
        name: "vistoria-demo.pdf",
        mediaType: "application/pdf"
      )
      await load()
      app.showNotice("Arquivo local simulado adicionado.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func remove(_ attachment: Attachment) async {
    do {
      try await app.store.deleteAttachment(billingID: billingID, attachmentID: attachment.id)
      await load()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

struct CommunicationComposerView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let billingID: UUID
  let billID: UUID?
  @State private var recipients: String
  @State private var subject = "Sua fatura está disponível"
  @State private var message = "Olá! Confira os detalhes da sua cobrança no Rentivo."
  @State private var previewing = false

  init(billingID: UUID, billID: UUID?, initialRecipients: [String]) {
    self.billingID = billingID
    self.billID = billID
    _recipients = State(initialValue: initialRecipients.joined(separator: ", "))
  }

  var body: some View {
    Form {
      Section("Mensagem") {
        TextField("Destinatários", text: $recipients, axis: .vertical)
        TextField("Assunto", text: $subject)
        TextField("Mensagem", text: $message, axis: .vertical)
          .lineLimit(5...10)
      }
      Section {
        Label("O envio é local e não dispara e-mails reais.", systemImage: "shield.checkered")
      }
    }
    .navigationTitle("Comunicação")
    .toolbar {
      ToolbarItem(placement: .confirmationAction) {
        Button("Visualizar") { previewing = true }
          .disabled(recipients.isEmpty || subject.isEmpty)
      }
    }
    .sheet(isPresented: $previewing) {
      NavigationStack {
        VStack(alignment: .leading, spacing: RentivoSpacing.large) {
          Text(subject).font(RentivoTypography.title)
          Text("Para: \(recipients)").font(.caption)
          Divider()
          Text(message)
          Spacer()
          Button("Simular envio") { Task { await send() } }
            .buttonStyle(RentivoButtonStyle())
        }
        .padding(RentivoSpacing.page)
        .background(RentivoColors.paper)
        .navigationTitle("Prévia")
      }
    }
  }

  private func send() async {
    do {
      _ = try await app.store.sendCommunication(
        billingID: billingID,
        billID: billID,
        recipients: recipients.split(separator: ",").map {
          $0.trimmingCharacters(in: .whitespacesAndNewlines)
        },
        subject: subject,
        message: message
      )
      previewing = false
      dismiss()
      app.showNotice("Comunicação registrada como simulação.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

struct ExportSimulationView: View {
  @Environment(AppModel.self) private var app
  let billingID: UUID
  @State private var format = "CSV"

  var body: some View {
    Form {
      Picker("Formato", selection: $format) {
        Text("CSV").tag("CSV")
        Text("XLSX").tag("XLSX")
      }
      .pickerStyle(.segmented)
      Section("Conteúdo") {
        Label("Faturas", systemImage: "doc.text")
        Label("Despesas", systemImage: "wrench.and.screwdriver")
        Label("Resumo financeiro", systemImage: "chart.bar")
      }
      Button("Preparar exportação simulada") {
        app.showNotice("Arquivo \(format) preparado localmente — nenhum download foi criado.")
      }
      .buttonStyle(RentivoButtonStyle(color: RentivoColors.blue))
      .listRowBackground(Color.clear)
    }
    .navigationTitle("Exportar")
  }
}
