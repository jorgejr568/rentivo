import Foundation

@MainActor
public final class MockRentivoStore: AuthRepository, ProfileRepository, BillingRepository,
  BillRepository, ExpenseRepository, AttachmentRepository, CommunicationRepository, FileDownloadRepository, ExportRepository,
  OrganizationRepository, InvitationRepository, SecurityRepository, APIKeyRepository,
  ThemeRepository, DemoRepository, DashboardRepository, ActivityRepository
{
  public private(set) var snapshot: StoreSnapshot

  public var currentUser: UserProfile { snapshot.profile }
  public var recentActivities: [RecentActivity] { snapshot.activities }
  public var demoSettings: DemoSettings {
    DemoSettings(
      delayEnabled: delayEnabled,
      emptyMode: emptyMode,
      viewerMode: viewerMode
    )
  }

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

  public func changePassword(
    currentPassword: String, newPassword: String, confirmPassword: String
  ) async throws {
    try await prepareOperation()
    guard !currentPassword.isEmpty, !newPassword.isEmpty, newPassword == confirmPassword else {
      throw DemoError.operationFailed
    }
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

  public func billing(id: BillingID) async throws -> Billing {
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
      id: BillingID(rawValue: UUID().uuidString),
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

  public func updateBilling(id: BillingID, draft: BillingDraft) async throws -> Billing {
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

  public func deleteBilling(id: BillingID) async throws {
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

  public func listBills(billingID: BillingID) async throws -> [Bill] {
    try await prepareOperation()
    guard snapshot.billings.contains(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    guard !emptyMode else { return [] }
    return snapshot.bills
      .filter { $0.billingID == billingID }
      .sorted { $0.referenceMonth > $1.referenceMonth }
  }

  public func bill(billingID: BillingID, id: BillID) async throws -> Bill {
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
      id: BillID(rawValue: UUID().uuidString),
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

  public func updateBill(billingID: BillingID, billID: BillID, draft: BillDraft) async throws -> Bill {
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

  public func deleteBill(billingID: BillingID, billID: BillID) async throws {
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

  public func transitionBill(billingID: BillingID, billID: BillID, to status: BillStatus) async throws {
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
      title: "Fatura \(status.label.lowercased())",
      detail: billingName
    )
  }

  public func regenerateBill(billingID: BillingID, billID: BillID) async throws -> Bill {
    try await prepareOperation()
    guard let index = billIndex(billingID: billingID, billID: billID) else { throw DemoError.resourceNotFound }
    return snapshot.bills[index]
  }

  public func addReceipt(billingID: BillingID, billID: BillID, upload: FileUpload) async throws -> Receipt {
    try await prepareOperation()
    try requireWriteAccess()
    guard let index = billIndex(billingID: billingID, billID: billID) else {
      throw DemoError.resourceNotFound
    }
    let receipt = Receipt(
      id: ReceiptID(rawValue: UUID().uuidString),
      name: upload.filename,
      sortOrder: snapshot.bills[index].receipts.count
    )
    snapshot.bills[index].receipts.append(receipt)
    recordActivity(kind: .bill, title: "Comprovante adicionado", detail: upload.filename)
    return receipt
  }

  public func reorderReceipts(
    billingID: BillingID,
    billID: BillID,
    receiptIDs: [ReceiptID]
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

  public func deleteReceipt(billingID: BillingID, billID: BillID, receiptID: ReceiptID) async throws {
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

  public func listExpenses(billingID: BillingID) async throws -> [Expense] {
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
    billingID: BillingID,
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
      id: ExpenseID(rawValue: UUID().uuidString),
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

  public func deleteExpense(billingID: BillingID, expenseID: ExpenseID) async throws {
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

  public func listAttachments(billingID: BillingID) async throws -> [Attachment] {
    try await prepareOperation()
    guard snapshot.billings.contains(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    guard !emptyMode else { return [] }
    return snapshot.attachments[billingID] ?? []
  }

  public func addAttachment(billingID: BillingID, upload: FileUpload) async throws -> Attachment {
    try await prepareOperation()
    try requireWriteAccess()
    guard snapshot.billings.contains(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    let attachment = Attachment(
      id: AttachmentID(rawValue: UUID().uuidString),
      name: upload.filename,
      mediaType: upload.mediaType,
      byteCount: upload.byteCount
    )
    snapshot.attachments[billingID, default: []].append(attachment)
    recordActivity(kind: .billing, title: "Arquivo adicionado", detail: upload.filename)
    return attachment
  }

  public func deleteAttachment(billingID: BillingID, attachmentID: AttachmentID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard snapshot.attachments[billingID]?.contains(where: { $0.id == attachmentID }) == true else {
      throw DemoError.resourceNotFound
    }
    snapshot.attachments[billingID]?.removeAll { $0.id == attachmentID }
  }

  public func previewCommunication(
    billingID: BillingID, subject: String, message: String
  ) async throws -> CommunicationPreview {
    try await prepareOperation()
    guard snapshot.billings.contains(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    return CommunicationPreview(html: message, severeWarnings: [], mildWarnings: [])
  }

  public func sendCommunication(
    billingID: BillingID,
    billID: BillID?,
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
      id: CommunicationID(rawValue: UUID().uuidString),
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

  public func downloadInvoice(billingID: BillingID, billID: BillID) async throws -> DownloadedFile { throw DemoError.operationFailed }
  public func downloadRecibo(billingID: BillingID, billID: BillID) async throws -> DownloadedFile { throw DemoError.operationFailed }
  public func downloadReceipt(billingID: BillingID, billID: BillID, receiptID: ReceiptID) async throws -> DownloadedFile { throw DemoError.operationFailed }
  public func downloadAttachment(billingID: BillingID, attachmentID: AttachmentID) async throws -> DownloadedFile { throw DemoError.operationFailed }
  public func requestExport(billingID: BillingID, format: String) async throws { try await prepareOperation() }

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
    return snapshot.organizations
      .filter { organization in
        organization.members.contains { $0.userID == snapshot.profile.id }
      }
      .map(restrictIfNeeded)
  }

  public func organization(id: OrganizationID) async throws -> Organization {
    try await prepareOperation()
    guard let organization = snapshot.organizations.first(where: { $0.id == id }) else {
      throw DemoError.resourceNotFound
    }
    return restrictIfNeeded(organization)
  }

  public func createOrganization(_ draft: OrganizationDraft) async throws -> Organization {
    try await prepareOperation()
    try requireWriteAccess()
    guard draft.isValid else { throw DemoError.operationFailed }
    let organization = Organization(
      id: OrganizationID(rawValue: UUID().uuidString),
      name: draft.name,
      pix: draft.pix,
      members: [
        OrganizationMember(
          userID: snapshot.profile.id,
          email: snapshot.profile.email,
          role: .admin
        )
      ],
      requiresMFA: false,
      currentUserRole: .admin
    )
    snapshot.organizations.insert(organization, at: 0)
    recordActivity(kind: .organization, title: "Organização criada", detail: organization.name)
    return organization
  }

  public func updateOrganization(id: OrganizationID, draft: OrganizationDraft) async throws -> Organization {
    try await prepareOperation()
    try requireWriteAccess()
    try requireOrganizationCapability(id: id, \.canManage)
    guard draft.isValid else { throw DemoError.operationFailed }
    guard let index = organizationIndex(id) else { throw DemoError.resourceNotFound }
    snapshot.organizations[index].name = draft.name
    snapshot.organizations[index].pix = draft.pix
    for billingIndex in snapshot.billings.indices {
      if case .organization(let ownerID, _) = snapshot.billings[billingIndex].owner,
        ownerID == id
      {
        snapshot.billings[billingIndex].owner = .organization(id: id, name: draft.name)
      }
    }
    recordActivity(kind: .organization, title: "Organização atualizada", detail: draft.name)
    return snapshot.organizations[index]
  }

  public func deleteOrganization(id: OrganizationID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    try requireOrganizationCapability(id: id, \.canManage)
    guard let index = organizationIndex(id) else { throw DemoError.resourceNotFound }
    let hasBillings = snapshot.billings.contains { billing in
      if case .organization(let ownerID, _) = billing.owner { return ownerID == id }
      return false
    }
    guard !hasBillings else { throw DemoError.operationFailed }
    let name = snapshot.organizations[index].name
    snapshot.organizations.remove(at: index)
    snapshot.themes[.organization(id)] = nil
    recordActivity(kind: .organization, title: "Organização excluída", detail: name)
  }

  public func updateMemberRole(
    organizationID: OrganizationID,
    userID: Int,
    role: OrganizationRole
  ) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    try requireOrganizationCapability(id: organizationID, \.canManage)
    guard let organizationIndex = organizationIndex(organizationID),
      let memberIndex = snapshot.organizations[organizationIndex].members.firstIndex(where: {
        $0.userID == userID
      })
    else {
      throw DemoError.resourceNotFound
    }
    snapshot.organizations[organizationIndex].members[memberIndex].role = role
    recordActivity(
      kind: .organization,
      title: "Função atualizada",
      detail: snapshot.organizations[organizationIndex].members[memberIndex].email
    )
  }

  public func removeMember(organizationID: OrganizationID, userID: Int) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    try requireOrganizationCapability(id: organizationID, \.canManage)
    guard let index = organizationIndex(organizationID),
      let member = snapshot.organizations[index].members.first(where: { $0.userID == userID })
    else {
      throw DemoError.resourceNotFound
    }
    snapshot.organizations[index].members.removeAll { $0.userID == userID }
    recordActivity(kind: .organization, title: "Membro removido", detail: member.email)
  }

  public func inviteMember(
    organizationID: OrganizationID,
    email: String,
    role: OrganizationRole
  ) async throws -> Invitation {
    try await prepareOperation()
    try requireWriteAccess()
    try requireOrganizationCapability(id: organizationID, \.canInvite)
    guard let index = organizationIndex(organizationID), email.contains("@") else {
      throw DemoError.operationFailed
    }
    let invitation = Invitation(
      id: InvitationID(rawValue: UUID().uuidString),
      organizationID: organizationID,
      organizationName: snapshot.organizations[index].name,
      email: email,
      role: role,
      status: .pending
    )
    snapshot.invitations.insert(invitation, at: 0)
    recordActivity(kind: .invitation, title: "Convite criado", detail: email)
    return invitation
  }

  public func setOrganizationMFA(organizationID: OrganizationID, required: Bool) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    try requireOrganizationCapability(id: organizationID, \.canManage)
    guard let index = organizationIndex(organizationID) else {
      throw DemoError.resourceNotFound
    }
    snapshot.organizations[index].requiresMFA = required
    recordActivity(
      kind: .security,
      title: required ? "MFA obrigatório" : "MFA opcional",
      detail: snapshot.organizations[index].name
    )
  }

  public func transferBilling(billingID: BillingID, toOrganizationID: OrganizationID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    try requireOrganizationCapability(id: toOrganizationID, \.canCreateBilling)
    guard let billingIndex = snapshot.billings.firstIndex(where: { $0.id == billingID }),
      let organizationIndex = organizationIndex(toOrganizationID)
    else {
      throw DemoError.resourceNotFound
    }
    let organization = snapshot.organizations[organizationIndex]
    guard organization.members.contains(where: { $0.userID == snapshot.profile.id }) else {
      throw DemoError.permissionDenied
    }
    snapshot.billings[billingIndex].owner = .organization(
      id: organization.id,
      name: organization.name
    )
    recordActivity(
      kind: .billing,
      title: "Cobrança transferida",
      detail: organization.name
    )
  }

  public func transferBillingToPersonal(billingID: BillingID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard let index = snapshot.billings.firstIndex(where: { $0.id == billingID }) else {
      throw DemoError.resourceNotFound
    }
    if case .organization(let organizationID, _) = snapshot.billings[index].owner {
      try requireOrganizationCapability(id: organizationID, \.canCreateBilling)
    }
    snapshot.billings[index].owner = .user(id: snapshot.profile.id, name: "Pessoal")
    recordActivity(kind: .billing, title: "Cobrança transferida", detail: "Pessoal")
  }

  public func listPendingInvitations() async throws -> [Invitation] {
    try await prepareOperation()
    guard !emptyMode else { return [] }
    return snapshot.invitations.filter { $0.status == .pending }
  }

  public func acceptInvitation(id: InvitationID) async throws {
    try await respondToInvitation(id: id, status: .accepted)
  }

  public func declineInvitation(id: InvitationID) async throws {
    try await respondToInvitation(id: id, status: .declined)
  }

  public func securitySummary() async throws -> SecuritySummary {
    try await prepareOperation()
    return snapshot.security
  }

  public func setTOTPEnabled(_ enabled: Bool) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    snapshot.security.totpEnabled = enabled
    recordActivity(
      kind: .security,
      title: enabled ? "TOTP ativado" : "TOTP desativado",
      detail: snapshot.profile.email
    )
  }

  public func beginTOTPEnrollment() async throws -> TOTPEnrollment {
    try await prepareOperation()
    try requireWriteAccess()
    return TOTPEnrollment(
      secret: "JBSWY3DPEHPK3PXP", provisioningURI: "otpauth://totp/Rentivo:demo",
      qrCodeBase64: ""
    )
  }

  public func confirmTOTPEnrollment(code: String) async throws -> [String] {
    guard !code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      throw DemoError.operationFailed
    }
    try await setTOTPEnabled(true)
    return try await regenerateRecoveryCodes()
  }

  public func disableTOTP(password: String) async throws {
    guard !password.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      throw DemoError.operationFailed
    }
    try await setTOTPEnabled(false)
  }

  public func regenerateRecoveryCodes() async throws -> [String] {
    try await prepareOperation()
    try requireWriteAccess()
    let codes = [
      "RNTV-7K2P", "RNTV-4M9Q", "RNTV-8X3L", "RNTV-2N6C",
      "RNTV-5B1W", "RNTV-9J4R", "RNTV-3F8T", "RNTV-6D2H",
    ]
    snapshot.security.recoveryCodeCount = codes.count
    recordActivity(kind: .security, title: "Códigos renovados", detail: "\(codes.count) códigos")
    return codes
  }

  public func addPasskey(name: String) async throws -> Passkey {
    try await prepareOperation()
    try requireWriteAccess()
    guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      throw DemoError.operationFailed
    }
    let passkey = Passkey(id: PasskeyID(rawValue: UUID().uuidString), name: name, createdAt: Date(), lastUsedAt: nil)
    snapshot.security.passkeys.append(passkey)
    recordActivity(kind: .security, title: "Chave de acesso criada", detail: name)
    return passkey
  }

  public func renamePasskey(id: PasskeyID, name: String) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard let index = snapshot.security.passkeys.firstIndex(where: { $0.id == id }),
      !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      throw DemoError.resourceNotFound
    }
    snapshot.security.passkeys[index].name = name
  }

  public func deletePasskey(id: PasskeyID) async throws {
    try await prepareOperation()
    try requireWriteAccess()
    guard snapshot.security.passkeys.contains(where: { $0.id == id }) else {
      throw DemoError.resourceNotFound
    }
    snapshot.security.passkeys.removeAll { $0.id == id }
    recordActivity(
      kind: .security, title: "Chave de acesso removida", detail: snapshot.profile.email)
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
      id: APIKeyID(rawValue: UUID().uuidString),
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

  public func updateAPIKey(id: APIKeyID, draft: APIKeyDraft) async throws -> APIKeyMetadata {
    try await prepareOperation()
    try requireWriteAccess()
    guard !draft.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !draft.scopes.isEmpty,
      !draft.grants.isEmpty
    else {
      throw DemoError.operationFailed
    }
    guard let index = snapshot.apiKeys.firstIndex(where: { $0.id == id && $0.revokedAt == nil })
    else {
      throw DemoError.resourceNotFound
    }
    snapshot.apiKeys[index].name = draft.name
    snapshot.apiKeys[index].scopes = draft.scopes
    snapshot.apiKeys[index].grants = draft.grants
    snapshot.apiKeys[index].expiresAt = draft.expiresAt
    recordActivity(
      kind: .apiKey, title: "Chave de API atualizada", detail: snapshot.apiKeys[index].name
    )
    return snapshot.apiKeys[index]
  }

  public func revokeAPIKey(id: APIKeyID) async throws {
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
    let canEdit = canEditTheme(target)
    return ThemeRecord(
      ownerName: ownerName(for: target),
      stored: stored,
      effective: stored ?? inherited.values,
      effectiveSource: stored.map { _ in source(for: target) } ?? inherited.source,
      canEdit: canEdit,
      canReset: canEdit && stored != nil
    )
  }

  public func updateTheme(target: ThemeTarget, values: ThemeValues) async throws {
    try await prepareOperation()
    guard canEditTheme(target) else { throw DemoError.permissionDenied }
    snapshot.themes[target] = values
    recordActivity(kind: .theme, title: "Tema atualizado", detail: ownerName(for: target))
  }

  public func resetTheme(target: ThemeTarget) async throws {
    try await prepareOperation()
    guard canEditTheme(target) else { throw DemoError.permissionDenied }
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

  private func requireOrganizationCapability(
    id: OrganizationID,
    _ capability: KeyPath<OrganizationCapabilities, Bool>
  ) throws {
    guard let organization = snapshot.organizations.first(where: { $0.id == id }) else {
      throw DemoError.resourceNotFound
    }
    let capabilities = OrganizationCapabilities.forRole(organization.currentUserRole)
    guard capabilities[keyPath: capability] else { throw DemoError.permissionDenied }
  }

  private func canEditTheme(_ target: ThemeTarget) -> Bool {
    guard !viewerMode else { return false }
    switch target {
    case .user:
      return true
    case .organization(let id):
      guard let organization = snapshot.organizations.first(where: { $0.id == id }) else {
        return false
      }
      return OrganizationCapabilities.forRole(organization.currentUserRole).canManage
    case .billing(let id):
      return snapshot.billings.first(where: { $0.id == id })?.capabilities.canManageTheme == true
    }
  }

  private func restrictIfNeeded(_ billing: Billing) -> Billing {
    guard viewerMode else { return billing }
    var restricted = billing
    restricted.capabilities = .viewer
    return restricted
  }

  private func restrictIfNeeded(_ organization: Organization) -> Organization {
    var restricted = organization
    if viewerMode {
      restricted.currentUserRole = .viewer
      restricted.capabilities = .viewer
    } else {
      restricted.capabilities = .forRole(restricted.currentUserRole)
    }
    return restricted
  }

  private func total(for bills: [Bill]) -> Money {
    bills.map(\.total).reduce(.zero, +)
  }

  private func billIndex(billingID: BillingID, billID: BillID) -> Int? {
    snapshot.bills.firstIndex { $0.billingID == billingID && $0.id == billID }
  }

  private func organizationIndex(_ id: OrganizationID) -> Int? {
    snapshot.organizations.firstIndex { $0.id == id }
  }

  private func recordActivity(kind: ActivityKind, title: String, detail: String) {
    snapshot.activities.insert(
      RecentActivity(id: UUID(), kind: kind, title: title, detail: detail, occurredAt: Date()),
      at: 0
    )
  }

  private func respondToInvitation(id: InvitationID, status: InvitationStatus) async throws {
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
      snapshot.organizations[organizationIndex].capabilities = .forRole(invitation.role)
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
