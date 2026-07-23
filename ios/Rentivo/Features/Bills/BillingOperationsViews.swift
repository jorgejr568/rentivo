import SwiftUI
import UniformTypeIdentifiers
import WebKit

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
  @State private var pendingDeletion: Expense?

  var body: some View {
    PageStateView(state: state) { expenses in
      List {
        Section {
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
                Button("Excluir", role: .destructive) { pendingDeletion = expense }
              }
            }
          }
        } header: {
          Text(ptBRCount(expenses.count, singular: "despesa", plural: "despesas"))
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
    .confirmationDialog(
      "Excluir esta despesa?",
      isPresented: Binding(
        get: { pendingDeletion != nil },
        set: { isPresented in if !isPresented { pendingDeletion = nil } }
      ),
      titleVisibility: .visible
    ) {
      Button("Excluir despesa", role: .destructive) {
        if let expense = pendingDeletion { Task { await remove(expense) } }
      }
      Button("Cancelar", role: .cancel) { pendingDeletion = nil }
    } message: {
      Text("A despesa será removida permanentemente do registro desta cobrança.")
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
  @State private var incurredOn = Date()

  var body: some View {
    Form {
      TextField("Descrição", text: $description)
      CurrencyCentavosField("Valor em centavos", centavos: $centavos)
      Picker("Categoria", selection: $category) {
        ForEach(ExpenseCategory.allCases, id: \.self) { category in
          Text(category.label).tag(category)
        }
      }
      DatePicker("Data", selection: $incurredOn, displayedComponents: .date)
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
        incurredOn: selectedDate,
        amount: Money(centavos: centavos)
      )
      await onSaved()
      dismiss()
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  private var selectedDate: DateOnly {
    let components = Calendar.current.dateComponents([.year, .month, .day], from: incurredOn)
    return DateOnly(year: components.year ?? 1970, month: components.month ?? 1, day: components.day ?? 1)
  }
}

struct AttachmentListView: View {
  @Environment(AppModel.self) private var app
  let billingID: BillingID
  let canWrite: Bool
  @State private var state: LoadState<[Attachment]> = .idle
  @State private var downloadedFile: DownloadedFile?
  @State private var showingFileImporter = false
  @State private var pendingDeletion: Attachment?

  var body: some View {
    PageStateView(state: state) { attachments in
      List {
        Section {
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
              // A single-action menu behind an unlabeled "..." icon added an extra tap for no
              // reason; this was the only action, so it is now a direct, accessibly-labeled button.
              Button {
                Task { await download(attachment) }
              } label: {
                Label("Abrir", systemImage: "arrow.down.circle")
              }
              .labelStyle(.iconOnly)
              .buttonStyle(.borderless)
            }
            .swipeActions {
              if canWrite {
                Button("Excluir", role: .destructive) { pendingDeletion = attachment }
              }
            }
          }
        } header: {
          Text(ptBRCount(attachments.count, singular: "arquivo", plural: "arquivos"))
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
    .sheet(item: $downloadedFile) { file in DownloadShareView(file: file) }
    .fileImporter(
      isPresented: $showingFileImporter,
      allowedContentTypes: [UTType.pdf, UTType.image],
      allowsMultipleSelection: false
    ) { result in
      guard case .success(let urls) = result, let url = urls.first else { return }
      Task { await add(fileURL: url) }
    }
    .confirmationDialog(
      "Excluir este arquivo?",
      isPresented: Binding(
        get: { pendingDeletion != nil },
        set: { isPresented in if !isPresented { pendingDeletion = nil } }
      ),
      titleVisibility: .visible
    ) {
      Button("Excluir arquivo", role: .destructive) {
        if let attachment = pendingDeletion { Task { await remove(attachment) } }
      }
      Button("Cancelar", role: .cancel) { pendingDeletion = nil }
    } message: {
      Text("O arquivo será removido permanentemente e não poderá ser recuperado.")
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

  private func download(_ attachment: Attachment) async {
    do {
      downloadedFile = try await app.dependencies.downloads.downloadAttachment(
        billingID: billingID, attachmentID: attachment.id
      )
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}

struct DownloadShareView: View {
  @Environment(\.dismiss) private var dismiss
  let file: DownloadedFile

  var body: some View {
    NavigationStack {
      VStack(spacing: RentivoSpacing.large) {
        Image(systemName: "doc.text.fill")
          .font(.system(size: 64))
          .foregroundStyle(RentivoColors.blue)
        Text(file.filename).font(RentivoTypography.title)
        Text("Arquivo baixado do Rentivo.").foregroundStyle(RentivoColors.secondaryInk)
        ShareLink(item: file.fileURL) {
          Label("Compartilhar ou salvar arquivo", systemImage: "square.and.arrow.up")
        }
        .buttonStyle(RentivoButtonStyle(color: RentivoColors.blue))
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
  @State private var preview: CommunicationPreview?
  @State private var isLoadingPreview = false
  @State private var isSending = false

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
        Button("Visualizar") { Task { await loadPreview() } }
          .disabled(isLoadingPreview || recipients.isEmpty || subject.isEmpty)
      }
    }
    .sheet(item: $preview) { preview in
      NavigationStack {
        VStack(alignment: .leading, spacing: RentivoSpacing.large) {
          Text(subject).font(RentivoTypography.title)
          Text("Para: \(recipients)").font(.caption)
          Divider()
          HTMLPreviewView(html: preview.html)
            .frame(minHeight: 180)
          if !preview.mildWarnings.isEmpty {
            WarningList(title: "Revise antes de enviar", warnings: preview.mildWarnings, color: RentivoColors.coral)
          }
          if !preview.severeWarnings.isEmpty {
            WarningList(title: "Envio bloqueado", warnings: preview.severeWarnings, color: RentivoColors.coral)
          }
          Spacer()
          Button {
            Task { await send() }
          } label: {
            HStack(spacing: RentivoSpacing.small) {
              if isSending {
                ProgressView()
                  .tint(.white)
              }
              Text("Enviar")
            }
          }
          .buttonStyle(RentivoButtonStyle())
          .disabled(isSending || !preview.severeWarnings.isEmpty)
        }
        .padding(RentivoSpacing.page)
        .background(RentivoColors.paper)
        .navigationTitle("Prévia")
      }
    }
  }

  private func send() async {
    guard !isSending else { return }
    let parsedRecipients = recipients
      .split(separator: ",")
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    guard !parsedRecipients.isEmpty else {
      app.showNotice("Informe ao menos um destinatário válido.", kind: .warning)
      return
    }
    let invalidRecipients = parsedRecipients.filter { !Self.isValidEmail($0) }
    guard invalidRecipients.isEmpty else {
      app.showNotice(
        "E-mail inválido: \(invalidRecipients.joined(separator: ", ")). Revise os destinatários.",
        kind: .warning
      )
      return
    }

    isSending = true
    defer { isSending = false }
    do {
      _ = try await app.dependencies.communications.sendCommunication(
        billingID: billingID,
        billID: billID,
        recipients: parsedRecipients,
        subject: subject,
        message: message
      )
      preview = nil
      dismiss()
      app.showNotice("Comunicação enfileirada para envio.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }

  // A pragmatic wire-boundary check (not full RFC 5322 validation): rejects obviously malformed
  // addresses (missing "@", missing domain dot, embedded whitespace) before they ever reach the
  // API, without blocking legitimate addresses on edge-case grammar the server itself accepts.
  private static func isValidEmail(_ email: String) -> Bool {
    let pattern = #"^[^\s@]+@[^\s@]+\.[^\s@]+$"#
    return email.range(of: pattern, options: .regularExpression) != nil
  }

  private func loadPreview() async {
    isLoadingPreview = true
    defer { isLoadingPreview = false }
    do {
      preview = try await app.dependencies.communications.previewCommunication(
        billingID: billingID, subject: subject, message: message
      )
    } catch {
      app.showNotice(DemoError(error).message, kind: .warning)
    }
  }
}

private struct WarningList: View {
  let title: String
  let warnings: [String]
  let color: Color

  var body: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.small) {
      Text(title).font(.headline).foregroundStyle(color)
      ForEach(warnings, id: \.self) { warning in
        Label(warning, systemImage: "exclamationmark.triangle.fill")
          .font(.footnote)
          .foregroundStyle(color)
      }
    }
  }
}

private struct HTMLPreviewView: UIViewRepresentable {
  let html: String

  func makeUIView(context: Context) -> WKWebView {
    let webView = WKWebView()
    webView.isOpaque = false
    webView.backgroundColor = .clear
    webView.scrollView.isScrollEnabled = false
    return webView
  }

  func updateUIView(_ webView: WKWebView, context: Context) {
    webView.loadHTMLString(html, baseURL: nil)
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
      Button("Solicitar exportação") {
        Task { await requestExport() }
      }
      .buttonStyle(RentivoButtonStyle(color: RentivoColors.blue))
      .listRowBackground(Color.clear)
    }
    .navigationTitle("Exportar")
  }

  private func requestExport() async {
    do {
      try await app.dependencies.exports.requestExport(billingID: billingID, format: format.lowercased())
      app.showNotice("Exportação \(format) enfileirada.")
    } catch { app.showNotice(DemoError(error).message, kind: .warning) }
  }
}
