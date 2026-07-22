import SwiftUI
import UniformTypeIdentifiers

struct BillingOperationsLinks: View {
  let billingID: BillingID
  let recipients: [String]
  let capabilities: BillingCapabilities
  let onMutation: () async -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Operações", symbol: "square.grid.2x2.fill")
      RentivoCard {
        VStack(spacing: RentivoSpacing.small) {
          if capabilities.canReadExpenses {
            NavigationLink {
              ExpenseListView(
                billingID: billingID,
                canWrite: capabilities.canWriteExpenses,
                onMutation: onMutation
              )
            } label: {
              OperationRow(title: "Despesas", symbol: "wrench.and.screwdriver.fill")
            }
          }
          if capabilities.canReadAttachments {
            Divider()
            NavigationLink {
              AttachmentListView(
                billingID: billingID,
                canWrite: capabilities.canWriteAttachments
              )
            } label: {
              OperationRow(title: "Arquivos", symbol: "folder.fill")
            }
          }
          if capabilities.canCreateExports {
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
  let billingID: BillingID
  let canWrite: Bool
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
            if canWrite {
              Button("Excluir", role: .destructive) { Task { await remove(expense) } }
            }
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
      if canWrite {
        Button {
          showingAdd = true
        } label: {
          Label("Adicionar", systemImage: "plus")
        }
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
    .task(id: app.dataRevision) { await load() }
  }

  private func load() async {
    state = .loading
    do {
      let expenses = try await app.dependencies.expenses.listExpenses(billingID: billingID)
      state = expenses.isEmpty ? .empty : .loaded(expenses)
    } catch { state = .failed(DemoError(error)) }
  }

  private func remove(_ expense: Expense) async {
    do {
      try await app.dependencies.expenses.deleteExpense(billingID: billingID, expenseID: expense.id)
      await load()
      await onMutation()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

private struct ExpenseFormView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let billingID: BillingID
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
      _ = try await app.dependencies.expenses.createExpense(
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
  let billingID: BillingID
  let canWrite: Bool
  @State private var state: LoadState<[Attachment]> = .idle
  @State private var previewingAttachment: Attachment?
  @State private var showingFileImporter = false

  var body: some View {
    PageStateView(state: state) { attachments in
      List {
        ForEach(attachments) { attachment in
          HStack {
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
            Spacer()
            Menu {
              Button("Visualizar") { previewingAttachment = attachment }
              Button("Simular download") {
                app.showNotice("Download local de \(attachment.name) simulado.")
              }
            } label: {
              Image(systemName: "ellipsis.circle")
            }
          }
          .swipeActions {
            if canWrite {
              Button("Excluir", role: .destructive) { Task { await remove(attachment) } }
            }
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
      if canWrite {
        Button {
          showingFileImporter = true
        } label: {
          Label("Adicionar", systemImage: "plus")
        }
      }
    }
    .sheet(item: $previewingAttachment) { attachment in
      LocalFilePreview(title: attachment.name, detail: "Arquivo da cobrança")
    }
    .fileImporter(
      isPresented: $showingFileImporter,
      allowedContentTypes: [.pdf, .image],
      allowsMultipleSelection: false
    ) { result in
      guard case .success(let urls) = result, let url = urls.first else { return }
      Task { await add(fileURL: url) }
    }
    .task(id: app.dataRevision) { await load() }
  }

  private func load() async {
    state = .loading
    do {
      let values = try await app.dependencies.attachments.listAttachments(billingID: billingID)
      state = values.isEmpty ? .empty : .loaded(values)
    } catch { state = .failed(DemoError(error)) }
  }

  private func add(fileURL: URL) async {
    do {
      let accessGranted = fileURL.startAccessingSecurityScopedResource()
      defer { if accessGranted { fileURL.stopAccessingSecurityScopedResource() } }
      let upload = try FileUpload.from(url: fileURL)
      _ = try await app.dependencies.attachments.addAttachment(
        billingID: billingID,
        upload: upload
      )
      await load()
      app.showNotice("Arquivo enviado.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private func remove(_ attachment: Attachment) async {
    do {
      try await app.dependencies.attachments.deleteAttachment(
        billingID: billingID, attachmentID: attachment.id)
      await load()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

private struct LocalFilePreview: View {
  @Environment(\.dismiss) private var dismiss
  let title: String
  let detail: String

  var body: some View {
    NavigationStack {
      VStack(spacing: RentivoSpacing.large) {
        Image(systemName: "doc.text.magnifyingglass")
          .font(.system(size: 64))
          .foregroundStyle(RentivoColors.blue)
        Text(title).font(RentivoTypography.title)
        Text(detail).foregroundStyle(RentivoColors.secondaryInk)
        Label("O download será aberto no navegador do sistema.", systemImage: "info.circle")
          .font(.footnote)
        Spacer()
      }
      .padding(RentivoSpacing.page)
      .navigationTitle("Prévia")
      .toolbar { Button("Concluir") { dismiss() } }
    }
  }
}

struct CommunicationComposerView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let billingID: BillingID
  let billID: BillID?
  @State private var recipients: String
  @State private var subject = "Sua fatura está disponível"
  @State private var message = "Olá! Confira os detalhes da sua cobrança no Rentivo."
  @State private var previewing = false

  init(billingID: BillingID, billID: BillID?, initialRecipients: [String]) {
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
        Label("O envio será enfileirado para os destinatários da cobrança.", systemImage: "paperplane.circle")
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
          Button("Enviar") { Task { await send() } }
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
      _ = try await app.dependencies.communications.sendCommunication(
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
      app.showNotice("Comunicação enfileirada para envio.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

struct ExportSimulationView: View {
  @Environment(AppModel.self) private var app
  let billingID: BillingID
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
