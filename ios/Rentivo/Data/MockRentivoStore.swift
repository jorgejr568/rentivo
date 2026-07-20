import Foundation

@MainActor
public final class MockRentivoStore: AuthRepository, ProfileRepository, BillingRepository,
  BillRepository, ExpenseRepository, AttachmentRepository, CommunicationRepository,
  OrganizationRepository, InvitationRepository, SecurityRepository, APIKeyRepository,
  ThemeRepository
{
  public private(set) var snapshot: StoreSnapshot

  public var currentUser: UserProfile { snapshot.profile }
  public var recentActivities: [RecentActivity] { snapshot.activities }

  private let baseline: StoreSnapshot
  private var emptyMode = false
  private var viewerMode = false
  private var delayEnabled = false
  private var shouldFailNextOperation = false

  public init(fixtures: MockFixtures = .canonical) {
    baseline = fixtures.snapshot
    snapshot = fixtures.snapshot
  }

  public func failNextOperation() {
    shouldFailNextOperation = true
  }

  public func setEmptyMode(_ enabled: Bool) {
    emptyMode = enabled
  }

  public func setViewerMode(_ enabled: Bool) {
    viewerMode = enabled
  }

  public func setDelayEnabled(_ enabled: Bool) {
    delayEnabled = enabled
  }

  public func reset() {
    snapshot = baseline
    emptyMode = false
    viewerMode = false
    delayEnabled = false
    shouldFailNextOperation = false
  }

  public func profile() async throws -> UserProfile {
    try await prepareOperation()
    return snapshot.profile
  }

  public func updatePix(_ pix: PixConfiguration) async throws -> UserProfile {
    try await prepareOperation()
    guard !viewerMode else { throw DemoError.permissionDenied }
    snapshot.profile.pix = pix
    recordActivity(kind: .billing, title: "PIX atualizado", detail: pix.key)
    return snapshot.profile
  }

  public func listBillings() async throws -> [Billing] {
    try await prepareOperation()
    guard !emptyMode else { return [] }
    return snapshot.billings.map(restrictIfNeeded)
  }

  public func billing(id: UUID) async throws -> Billing {
    try await prepareOperation()
    guard let billing = snapshot.billings.first(where: { $0.id == id }) else {
      throw DemoError.resourceNotFound
    }
    return restrictIfNeeded(billing)
  }

  public func createBilling(_ draft: BillingDraft) async throws -> Billing {
    try await prepareOperation()
    try requireWriteAccess()
    let billing = Billing(
      id: UUID(),
      name: draft.name,
      description: draft.description,
      owner: draft.owner,
      items: draft.items,
      pixOverride: draft.pixOverride,
      recipients: draft.recipients,
      replyTo: draft.replyTo
    )
    snapshot.billings.insert(billing, at: 0)
    recordActivity(kind: .billing, title: "Cobrança criada", detail: billing.name)
    return billing
  }

  public func updateBilling(id: UUID, draft: BillingDraft) async throws -> Billing {
    try await prepareOperation()
    try requireWriteAccess()
    guard let index = snapshot.billings.firstIndex(where: { $0.id == id }) else {
      throw DemoError.resourceNotFound
    }
    let capabilities = snapshot.billings[index].capabilities
    let billing = Billing(
      id: id,
      name: draft.name,
      description: draft.description,
      owner: draft.owner,
      items: draft.items,
      pixOverride: draft.pixOverride,
      recipients: draft.recipients,
      replyTo: draft.replyTo,
      capabilities: capabilities
    )
    snapshot.billings[index] = billing
    recordActivity(kind: .billing, title: "Cobrança atualizada", detail: billing.name)
    return billing
  }

  public func deleteBilling(id: UUID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard let index = snapshot.billings.firstIndex(where: { $0.id == id }) else {
      throw DemoError.resourceNotFound
    }
    let name = snapshot.billings[index].name
    snapshot.billings.remove(at: index)
    snapshot.bills.removeAll { $0.billingID == id }
    snapshot.expenses.removeAll { $0.billingID == id }
    snapshot.attachments[id] = nil
    snapshot.themes[.billing(id)] = nil
    recordActivity(kind: .billing, title: "Cobrança excluída", detail: name)
  }

  public func listBills(billingID: UUID) async throws -> [Bill] {
    try await prepareOperation()
    guard snapshot.billings.contains(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    guard !emptyMode else { return [] }
    return snapshot.bills
      .filter { $0.billingID == billingID }
      .sorted { $0.referenceMonth > $1.referenceMonth }
  }

  public func bill(billingID: UUID, id: UUID) async throws -> Bill {
    try await prepareOperation()
    guard let bill = snapshot.bills.first(where: { $0.billingID == billingID && $0.id == id })
    else {
      throw DemoError.resourceNotFound
    }
    return bill
  }

  public func createBill(_ draft: BillDraft) async throws -> Bill {
    try await prepareOperation()
    try requireWriteAccess()
    guard snapshot.billings.contains(where: { $0.id == draft.billingID }) else {
      throw DemoError.resourceNotFound
    }
    guard draft.validate().isEmpty else { throw DemoError.operationFailed }
    let bill = Bill(
      id: UUID(),
      billingID: draft.billingID,
      referenceMonth: draft.referenceMonth,
      dueDate: draft.dueDate,
      paidAt: nil,
      notes: draft.notes,
      status: .draft,
      lineItems: draft.lineItems,
      receipts: []
    )
    snapshot.bills.insert(bill, at: 0)
    recordActivity(kind: .bill, title: "Fatura criada", detail: draft.referenceMonth.label)
    return bill
  }

  public func updateBill(billingID: UUID, billID: UUID, draft: BillDraft) async throws -> Bill {
    try await prepareOperation()
    try requireWriteAccess()
    guard draft.billingID == billingID, draft.validate().isEmpty else {
      throw DemoError.operationFailed
    }
    guard
      let index = snapshot.bills.firstIndex(where: {
        $0.billingID == billingID && $0.id == billID
      })
    else {
      throw DemoError.resourceNotFound
    }
    guard snapshot.bills[index].status == .draft else { throw DemoError.permissionDenied }
    snapshot.bills[index].referenceMonth = draft.referenceMonth
    snapshot.bills[index].dueDate = draft.dueDate
    snapshot.bills[index].notes = draft.notes
    snapshot.bills[index].lineItems = draft.lineItems
    recordActivity(kind: .bill, title: "Fatura atualizada", detail: draft.referenceMonth.label)
    return snapshot.bills[index]
  }

  public func deleteBill(billingID: UUID, billID: UUID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard
      let index = snapshot.bills.firstIndex(where: {
        $0.billingID == billingID && $0.id == billID
      })
    else {
      throw DemoError.resourceNotFound
    }
    let reference = snapshot.bills[index].referenceMonth.label
    snapshot.bills.remove(at: index)
    recordActivity(kind: .bill, title: "Fatura excluída", detail: reference)
  }

  public func transitionBill(billingID: UUID, billID: UUID, to status: BillStatus) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard
      let index = snapshot.bills.firstIndex(where: {
        $0.billingID == billingID && $0.id == billID
      })
    else {
      throw DemoError.resourceNotFound
    }
    guard snapshot.bills[index].status.canTransition(to: status) else {
      throw DemoError.invalidBillTransition
    }
    snapshot.bills[index].status = status
    if status == .paid {
      snapshot.bills[index].paidAt = DateOnly(year: 2026, month: 7, day: 20)
    }
    let billingName = snapshot.billings.first(where: { $0.id == billingID })?.name ?? "Cobrança"
    recordActivity(
      kind: .bill,
      title: "Fatura (status.label.lowercased())",
      detail: billingName
    )
  }

  public func addReceipt(billingID: UUID, billID: UUID, name: String) async throws -> Receipt {
    try await prepareOperation()
    try requireWriteAccess()
    guard let index = billIndex(billingID: billingID, billID: billID) else {
      throw DemoError.resourceNotFound
    }
    let receipt = Receipt(
      id: UUID(),
      name: name,
      sortOrder: snapshot.bills[index].receipts.count
    )
    snapshot.bills[index].receipts.append(receipt)
    recordActivity(kind: .bill, title: "Comprovante adicionado", detail: name)
    return receipt
  }

  public func reorderReceipts(
    billingID: UUID,
    billID: UUID,
    receiptIDs: [UUID]
  ) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard let index = billIndex(billingID: billingID, billID: billID) else {
      throw DemoError.resourceNotFound
    }
    let current = snapshot.bills[index].receipts
    guard Set(current.map(\.id)) == Set(receiptIDs), current.count == receiptIDs.count else {
      throw DemoError.operationFailed
    }
    let byID = Dictionary(uniqueKeysWithValues: current.map { ($0.id, $0) })
    snapshot.bills[index].receipts = receiptIDs.enumerated().compactMap { offset, id in
      guard var receipt = byID[id] else { return nil }
      receipt.sortOrder = offset
      return receipt
    }
  }

  public func deleteReceipt(billingID: UUID, billID: UUID, receiptID: UUID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard let index = billIndex(billingID: billingID, billID: billID) else {
      throw DemoError.resourceNotFound
    }
    guard snapshot.bills[index].receipts.contains(where: { $0.id == receiptID }) else {
      throw DemoError.resourceNotFound
    }
    snapshot.bills[index].receipts.removeAll { $0.id == receiptID }
    for offset in snapshot.bills[index].receipts.indices {
      snapshot.bills[index].receipts[offset].sortOrder = offset
    }
  }

  public func listExpenses(billingID: UUID) async throws -> [Expense] {
    try await prepareOperation()
    guard snapshot.billings.contains(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    guard !emptyMode else { return [] }
    return snapshot.expenses
      .filter { $0.billingID == billingID }
      .sorted { $0.incurredOn > $1.incurredOn }
  }

  public func createExpense(
    billingID: UUID,
    description: String,
    category: ExpenseCategory,
    incurredOn: DateOnly,
    amount: Money
  ) async throws -> Expense {
    try await prepareOperation()
    try requireWriteAccess()
    guard snapshot.billings.contains(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    let expense = Expense(
      id: UUID(),
      billingID: billingID,
      description: description,
      amount: amount,
      category: category,
      incurredOn: incurredOn
    )
    snapshot.expenses.insert(expense, at: 0)
    recordActivity(kind: .expense, title: "Despesa adicionada", detail: description)
    return expense
  }

  public func deleteExpense(billingID: UUID, expenseID: UUID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard
      let index = snapshot.expenses.firstIndex(where: {
        $0.billingID == billingID && $0.id == expenseID
      })
    else {
      throw DemoError.resourceNotFound
    }
    let description = snapshot.expenses[index].description
    snapshot.expenses.remove(at: index)
    recordActivity(kind: .expense, title: "Despesa excluída", detail: description)
  }

  public func listAttachments(billingID: UUID) async throws -> [Attachment] {
    try await prepareOperation()
    guard snapshot.billings.contains(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    guard !emptyMode else { return [] }
    return snapshot.attachments[billingID] ?? []
  }

  public func addAttachment(
    billingID: UUID,
    name: String,
    mediaType: String
  ) async throws -> Attachment {
    try await prepareOperation()
    try requireWriteAccess()
    guard snapshot.billings.contains(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    let attachment = Attachment(
      id: UUID(),
      name: name,
      mediaType: mediaType,
      byteCount: 96_000
    )
    snapshot.attachments[billingID, default: []].append(attachment)
    recordActivity(kind: .billing, title: "Arquivo adicionado", detail: name)
    return attachment
  }

  public func deleteAttachment(billingID: UUID, attachmentID: UUID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard snapshot.attachments[billingID]?.contains(where: { $0.id == attachmentID }) == true else {
      throw DemoError.resourceNotFound
    }
    snapshot.attachments[billingID]?.removeAll { $0.id == attachmentID }
  }

  public func sendCommunication(
    billingID: UUID,
    billID: UUID?,
    recipients: [String],
    subject: String,
    message: String
  ) async throws -> CommunicationRecord {
    try await prepareOperation()
    try requireWriteAccess()
    guard snapshot.billings.contains(where: { $0.id == billingID }), !recipients.isEmpty else {
      throw DemoError.operationFailed
    }
    let communication = CommunicationRecord(
      id: UUID(),
      billingID: billingID,
      billID: billID,
      recipients: recipients,
      subject: subject,
      message: message,
      sentAt: Date()
    )
    snapshot.communications.insert(communication, at: 0)
    recordActivity(kind: .bill, title: "Comunicação simulada", detail: subject)
    return communication
  }

  public func dashboardSummary() async throws -> DashboardSummary {
    try await prepareOperation()
    guard !emptyMode else {
      return DashboardSummary(
        received: .zero,
        expenses: .zero,
        netIncome: .zero,
        overdue: .zero,
        upcoming: .zero,
        collectionRatePercent: 0
      )
    }
    let activeBills = snapshot.bills.filter { $0.status != .cancelled }
    let received = total(for: activeBills.filter { $0.status == .paid })
    let overdue = total(for: activeBills.filter { $0.status == .delayedPayment })
    let upcoming = total(
      for: activeBills.filter { [.draft, .published, .sent].contains($0.status) }
    )
    let expenses = snapshot.expenses.map(\.amount).reduce(.zero, +)
    let eligibleCount = activeBills.count
    let paidCount = activeBills.filter { $0.status == .paid }.count
    let collectionRate =
      eligibleCount == 0 ? 0 : Int((Double(paidCount) / Double(eligibleCount)) * 100)
    return DashboardSummary(
      received: received,
      expenses: expenses,
      netIncome: received - expenses,
      overdue: overdue,
      upcoming: upcoming,
      collectionRatePercent: collectionRate
    )
  }

  public func listOrganizations() async throws -> [Organization] {
    try await prepareOperation()
    guard !emptyMode else { return [] }
    return snapshot.organizations.filter { organization in
      organization.members.contains { $0.userID == snapshot.profile.id }
    }
  }

  public func organization(id: UUID) async throws -> Organization {
    try await prepareOperation()
    guard let organization = snapshot.organizations.first(where: { $0.id == id }) else {
      throw DemoError.resourceNotFound
    }
    return organization
  }

  public func listPendingInvitations() async throws -> [Invitation] {
    try await prepareOperation()
    guard !emptyMode else { return [] }
    return snapshot.invitations.filter { $0.status == .pending }
  }

  public func acceptInvitation(id: UUID) async throws {
    try await respondToInvitation(id: id, status: .accepted)
  }

  public func declineInvitation(id: UUID) async throws {
    try await respondToInvitation(id: id, status: .declined)
  }

  public func securitySummary() async throws -> SecuritySummary {
    try await prepareOperation()
    return snapshot.security
  }

  public func listAPIKeys() async throws -> [APIKeyMetadata] {
    try await prepareOperation()
    guard !emptyMode else { return [] }
    return snapshot.apiKeys.filter { $0.revokedAt == nil }
  }

  public func createAPIKey(_ draft: APIKeyDraft) async throws -> CreatedAPIKeySecret {
    try await prepareOperation()
    try requireWriteAccess()
    let metadata = APIKeyMetadata(
      id: UUID(),
      name: draft.name,
      hint: "rntv-v1-demo••42",
      scopes: draft.scopes,
      grants: draft.grants,
      expiresAt: draft.expiresAt,
      lastUsedAt: nil,
      createdAt: Date(),
      revokedAt: nil
    )
    snapshot.apiKeys.insert(metadata, at: 0)
    recordActivity(kind: .apiKey, title: "Chave de API criada", detail: metadata.name)
    return CreatedAPIKeySecret(metadata: metadata, secret: "rntv-v1-demo-8K2P-N4M7-X9Q3")
  }

  public func revokeAPIKey(id: UUID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard let index = snapshot.apiKeys.firstIndex(where: { $0.id == id }) else {
      throw DemoError.resourceNotFound
    }
    snapshot.apiKeys[index].revokedAt = Date()
    recordActivity(
      kind: .apiKey, title: "Chave de API revogada", detail: snapshot.apiKeys[index].name)
  }

  public func theme(target: ThemeTarget) async throws -> ThemeRecord {
    try await prepareOperation()
    let stored = snapshot.themes[target]
    let inherited = inheritedTheme(for: target)
    return ThemeRecord(
      ownerName: ownerName(for: target),
      stored: stored,
      effective: stored ?? inherited.values,
      effectiveSource: stored.map { _ in source(for: target) } ?? inherited.source,
      canEdit: !viewerMode,
      canReset: !viewerMode && stored != nil
    )
  }

  public func updateTheme(target: ThemeTarget, values: ThemeValues) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    snapshot.themes[target] = values
    recordActivity(kind: .theme, title: "Tema atualizado", detail: ownerName(for: target))
  }

  public func resetTheme(target: ThemeTarget) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    snapshot.themes[target] = nil
    recordActivity(kind: .theme, title: "Tema restaurado", detail: ownerName(for: target))
  }

  private func prepareOperation() async throws {
    if delayEnabled {
      try await Task.sleep(for: .milliseconds(350))
    }
    if shouldFailNextOperation {
      shouldFailNextOperation = false
      throw DemoError.operationFailed
    }
  }

  private func requireWriteAccess() throws {
    if viewerMode { throw DemoError.permissionDenied }
  }

  private func restrictIfNeeded(_ billing: Billing) -> Billing {
    guard viewerMode else { return billing }
    var restricted = billing
    restricted.capabilities = .viewer
    return restricted
  }

  private func total(for bills: [Bill]) -> Money {
    bills.map(\.total).reduce(.zero, +)
  }

  private func billIndex(billingID: UUID, billID: UUID) -> Int? {
    snapshot.bills.firstIndex { $0.billingID == billingID && $0.id == billID }
  }

  private func recordActivity(kind: ActivityKind, title: String, detail: String) {
    snapshot.activities.insert(
      RecentActivity(id: UUID(), kind: kind, title: title, detail: detail, occurredAt: Date()),
      at: 0
    )
  }

  private func respondToInvitation(id: UUID, status: InvitationStatus) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard
      let invitationIndex = snapshot.invitations.firstIndex(where: {
        $0.id == id && $0.status == .pending
      })
    else {
      throw DemoError.resourceNotFound
    }
    snapshot.invitations[invitationIndex].status = status
    let invitation = snapshot.invitations[invitationIndex]
    if status == .accepted,
      let organizationIndex = snapshot.organizations.firstIndex(where: {
        $0.id == invitation.organizationID
      })
    {
      let membership = OrganizationMember(
        userID: snapshot.profile.id,
        email: snapshot.profile.email,
        role: invitation.role
      )
      snapshot.organizations[organizationIndex].members.append(membership)
      snapshot.organizations[organizationIndex].currentUserRole = invitation.role
    }
    recordActivity(
      kind: .invitation,
      title: status == .accepted ? "Convite aceito" : "Convite recusado",
      detail: invitation.organizationName
    )
  }

  private func inheritedTheme(for target: ThemeTarget) -> (values: ThemeValues, source: ThemeSource)
  {
    switch target {
    case .user:
      return (.rentivo, .default)
    case .organization:
      if let values = snapshot.themes[.user] { return (values, .user) }
      return (.rentivo, .default)
    case .billing(let billingID):
      if let billing = snapshot.billings.first(where: { $0.id == billingID }),
        case .organization(let organizationID, _) = billing.owner,
        let values = snapshot.themes[.organization(organizationID)]
      {
        return (values, .organization)
      }
      if let values = snapshot.themes[.user] { return (values, .user) }
      return (.rentivo, .default)
    }
  }

  private func source(for target: ThemeTarget) -> ThemeSource {
    switch target {
    case .user: .user
    case .organization: .organization
    case .billing: .billing
    }
  }

  private func ownerName(for target: ThemeTarget) -> String {
    switch target {
    case .user:
      snapshot.profile.email
    case .organization(let id):
      snapshot.organizations.first(where: { $0.id == id })?.name ?? "Organização"
    case .billing(let id):
      snapshot.billings.first(where: { $0.id == id })?.name ?? "Cobrança"
    }
  }
}
