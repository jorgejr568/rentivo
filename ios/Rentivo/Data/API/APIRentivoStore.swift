import Foundation

@MainActor
public final class APIRentivoStore: AuthRepository, ProfileRepository, BillingRepository,
  BillRepository, ExpenseRepository, AttachmentRepository, CommunicationRepository, FileDownloadRepository, ExportRepository,
  DashboardRepository, ActivityRepository, OrganizationRepository, InvitationRepository,
  SecurityRepository, APIKeyRepository, ThemeRepository
{
  private let client: LiveAPIClient
  private var user = UserProfile(id: 0, email: "")

  public init(inMemoryCredentialStore: Bool = false) {
    let credentials: any CredentialStore = inMemoryCredentialStore
      ? MemoryCredentialStore()
      : KeychainCredentialStore()
    client = LiveAPIClient(credentials: credentials)
  }

  init(client: LiveAPIClient) {
    self.client = client
  }

  public var currentUser: UserProfile { user }
  public var recentActivities: [RecentActivity] { [] }

  public func exchangeMobileAuthorization(code: String) async throws -> UserProfile {
    user = try await client.exchangeMobileAuthorization(code: code).profile
    return user
  }

  public func restoreSession() async throws -> UserProfile? {
    guard let session = try await client.restoreSession() else { return nil }
    user = session.profile
    return user
  }

  public func logout() async {
    try? await execute(path: "/api/v1/auth/logout", method: "POST")
    await client.logout()
    user = UserProfile(id: 0, email: "")
  }

  public func deleteAccount(password: String) async throws {
    struct DeleteAccountPayload: Encodable { let password: String }
    try await execute(
      path: "/api/v1/security/delete-account", method: "POST",
      body: DeleteAccountPayload(password: password)
    )
    await client.logout()
    user = UserProfile(id: 0, email: "")
  }

  public func profile() async throws -> UserProfile {
    // GET /api/v1/profile only returns `CurrentProfileResponse` ({email}); the pix fields live on
    // `SecuritySummaryResponse.profile` (a full `ProfileResponse`), so fetch security instead.
    let response: RemoteSecuritySummary = try await decode(path: "/api/v1/security")
    let remote = response.profile
    user = UserProfile(id: user.id, email: remote.email, pix: pix(key: remote.pixKey, name: remote.pixMerchantName, city: remote.pixMerchantCity))
    return user
  }
  public func updatePix(_ pix: PixConfiguration) async throws -> UserProfile {
    let response: RemotePixUpdateResponse = try await decode(
      path: "/api/v1/security/pix", method: "POST", body: RemotePixUpdate(pix: pix)
    )
    let remote = response.profile
    user = UserProfile(id: user.id, email: remote.email, pix: self.pix(key: remote.pixKey, name: remote.pixMerchantName, city: remote.pixMerchantCity))
    return user
  }
  public func listBillings() async throws -> [Billing] {
    let response: RemoteBillingList = try await decode(path: "/api/v1/billings")
    var billings: [Billing] = []
    billings.reserveCapacity(response.items.count)
    for item in response.items {
      billings.append(try await billing(id: BillingID(rawValue: item.uuid)))
    }
    return billings
  }
  public func billing(id: BillingID) async throws -> Billing {
    let response: RemoteBilling = try await decode(path: "/api/v1/billings/\(id.rawValue)")
    return billing(from: response)
  }
  public func createBilling(_ draft: BillingDraft) async throws -> Billing {
    let remote: RemoteBilling = try await decode(
      path: "/api/v1/billings", method: "POST", body: RemoteBillingDraft(draft: draft)
    )
    return billing(from: remote)
  }
  public func updateBilling(id: BillingID, draft: BillingDraft) async throws -> Billing {
    let remote: RemoteBilling = try await decode(
      path: "/api/v1/billings/\(id.rawValue)", method: "PATCH", body: RemoteBillingUpdate(draft: draft)
    )
    return billing(from: remote)
  }
  public func deleteBilling(id: BillingID) async throws {
    try await execute(path: "/api/v1/billings/\(id.rawValue)", method: "DELETE")
  }
  public func listBills(billingID: BillingID) async throws -> [Bill] {
    let response: RemoteBillList = try await decode(path: "/api/v1/billings/\(billingID.rawValue)/bills")
    return try response.items.map { try bill(from: $0, billingID: billingID) }
  }
  public func bill(billingID: BillingID, id: BillID) async throws -> Bill {
    let response: RemoteBill = try await decode(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(id.rawValue)"
    )
    return try bill(from: response, billingID: billingID)
  }
  public func createBill(_ draft: BillDraft) async throws -> Bill {
    let remote: RemoteBill = try await decode(
      path: "/api/v1/billings/\(draft.billingID.rawValue)/bills", method: "POST",
      body: RemoteBillCreateDraft(draft: draft)
    )
    return try bill(from: remote, billingID: draft.billingID)
  }
  public func updateBill(billingID: BillingID, billID: BillID, draft: BillDraft) async throws -> Bill {
    let remote: RemoteBill = try await decode(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)", method: "PATCH",
      body: RemoteBillUpdateDraft(draft: draft)
    )
    return try bill(from: remote, billingID: billingID)
  }
  public func deleteBill(billingID: BillingID, billID: BillID) async throws {
    try await execute(path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)", method: "DELETE")
  }
  public func transitionBill(billingID: BillingID, billID: BillID, to status: BillStatus) async throws {
    try await execute(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)/transitions",
      method: "POST", body: RemoteBillTransition(target: status.rawValue)
    )
  }
  public func regenerateBill(billingID: BillingID, billID: BillID) async throws -> Bill {
    let remote: RemoteBill = try await decode(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)/regenerate", method: "POST"
    )
    return try bill(from: remote, billingID: billingID)
  }
  public func addReceipt(billingID: BillingID, billID: BillID, upload: FileUpload) async throws -> Receipt {
    let response: RemoteReceiptUpload = try await decodeMultipart(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)/receipts",
      files: [(field: "receipt_files", upload: upload)]
    )
    guard let receipt = response.items.first else { throw LiveAPIError.invalidResponse }
    return Receipt(id: ReceiptID(rawValue: receipt.uuid), name: receipt.filename, sortOrder: receipt.sortOrder)
  }
  public func reorderReceipts(billingID: BillingID, billID: BillID, receiptIDs: [ReceiptID]) async throws {
    let _: RemoteReceiptList = try await decode(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)/receipt-order",
      method: "PUT", body: RemoteReceiptOrder(order: receiptIDs.map(\.rawValue))
    )
  }
  public func deleteReceipt(billingID: BillingID, billID: BillID, receiptID: ReceiptID) async throws {
    try await execute(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)/receipts/\(receiptID.rawValue)",
      method: "DELETE"
    )
  }
  public func listExpenses(billingID: BillingID) async throws -> [Expense] {
    let response: RemoteExpenseList = try await decode(path: "/api/v1/billings/\(billingID.rawValue)/expenses")
    return try response.items.map {
      Expense(
        id: ExpenseID(rawValue: $0.uuid), billingID: billingID, description: $0.description,
        amount: Money(centavos: $0.amount), category: ExpenseCategory(rawValue: $0.category) ?? .other,
        incurredOn: try dateOnly($0.incurredOn)
      )
    }
  }
  public func createExpense(billingID: BillingID, description: String, category: ExpenseCategory, incurredOn: DateOnly, amount: Money) async throws -> Expense {
    let remote: RemoteExpense = try await decode(
      path: "/api/v1/billings/\(billingID.rawValue)/expenses", method: "POST",
      body: RemoteExpenseCreate(description: description, category: category.rawValue, incurredOn: incurredOn.iso8601, amount: amount.centavos)
    )
    return Expense(id: ExpenseID(rawValue: remote.uuid), billingID: billingID, description: remote.description,
      amount: Money(centavos: remote.amount), category: ExpenseCategory(rawValue: remote.category) ?? .other,
      incurredOn: try dateOnly(remote.incurredOn))
  }
  public func deleteExpense(billingID: BillingID, expenseID: ExpenseID) async throws {
    try await execute(path: "/api/v1/billings/\(billingID.rawValue)/expenses/\(expenseID.rawValue)", method: "DELETE")
  }
  public func listAttachments(billingID: BillingID) async throws -> [Attachment] {
    let response: RemoteAttachmentList = try await decode(path: "/api/v1/billings/\(billingID.rawValue)/attachments")
    return response.items.map(attachment(from:))
  }
  public func addAttachment(billingID: BillingID, upload: FileUpload) async throws -> Attachment {
    let response: RemoteAttachment = try await decodeMultipart(
      path: "/api/v1/billings/\(billingID.rawValue)/attachments",
      name: upload.filename, files: [(field: "file", upload: upload)]
    )
    return attachment(from: response)
  }
  public func deleteAttachment(billingID: BillingID, attachmentID: AttachmentID) async throws {
    try await execute(path: "/api/v1/billings/\(billingID.rawValue)/attachments/\(attachmentID.rawValue)", method: "DELETE")
  }
  public func previewCommunication(
    billingID: BillingID, subject: String, message: String
  ) async throws -> CommunicationPreview {
    let response: RemoteCommunicationPreview = try await decode(
      path: "/api/v1/billings/\(billingID.rawValue)/communications/preview", method: "POST",
      body: RemoteCommunicationPreviewRequest(subject: subject, body: message)
    )
    return CommunicationPreview(
      html: response.html, severeWarnings: response.severe, mildWarnings: response.mild
    )
  }
  public func sendCommunication(billingID: BillingID, billID: BillID?, recipients: [String], subject: String, message: String) async throws -> CommunicationRecord {
    guard let billID else {
      throw LiveAPIError.server(message: "Escolha uma fatura antes de enviar a comunicação.")
    }
    guard !recipients.isEmpty else {
      throw LiveAPIError.server(message: "Informe ao menos um destinatário.")
    }
    // PUT /recipients is a full replace, so we must resend every existing contact (preserving
    // their names) plus only the genuinely new ad-hoc emails, or we'd delete the billing's
    // configured recipients every time someone sends a one-off communication.
    let existingRecipients = try await billing(id: billingID).recipients
    var mergedContacts = existingRecipients.map(RemoteContactInput.init)
    var knownEmails = Set(existingRecipients.map { $0.email.lowercased() })
    for email in recipients {
      let key = email.lowercased()
      guard !knownEmails.contains(key) else { continue }
      knownEmails.insert(key)
      let localPart = email.split(separator: "@", maxSplits: 1).first.map(String.init) ?? email
      mergedContacts.append(RemoteContactInput(name: localPart, email: email))
    }

    let contactResponse: RemoteContactList = try await decode(
      path: "/api/v1/billings/\(billingID.rawValue)/recipients", method: "PUT",
      body: RemoteContactListPayload(items: mergedContacts)
    )

    // The server recreates every recipient row (with fresh uuids) on each replace, so we can
    // only resolve the uuids to send to by matching the just-saved contacts back by email.
    let requestedEmails = Set(recipients.map { $0.lowercased() })
    let recipientIDs = contactResponse.items.compactMap { contact -> String? in
      guard let email = contact.email?.lowercased(), requestedEmails.contains(email) else { return nil }
      return contact.uuid
    }
    guard recipientIDs.count == requestedEmails.count else { throw LiveAPIError.invalidResponse }

    let sendResponse: RemoteCommunicationSend = try await decode(
      path: "/api/v1/billings/\(billingID.rawValue)/communications/send", method: "POST",
      body: RemoteCommunicationSendRequest(
        billID: billID.rawValue, recipients: recipientIDs, subject: subject, message: message
      )
    )
    guard sendResponse.queuedCount > 0 else { throw LiveAPIError.invalidResponse }

    return CommunicationRecord(
      id: CommunicationID(rawValue: UUID().uuidString), billingID: billingID,
      billID: billID, recipients: recipients, subject: subject, message: message, sentAt: Date()
    )
  }
  public func downloadInvoice(billingID: BillingID, billID: BillID) async throws -> DownloadedFile {
    try await client.download(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)/invoice",
      filename: "fatura-\(billID.rawValue)"
    )
  }
  public func downloadRecibo(billingID: BillingID, billID: BillID) async throws -> DownloadedFile {
    try await client.download(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)/recibo",
      filename: "recibo-\(billID.rawValue)"
    )
  }
  public func downloadReceipt(billingID: BillingID, billID: BillID, receiptID: ReceiptID) async throws -> DownloadedFile {
    try await client.download(
      path: "/api/v1/billings/\(billingID.rawValue)/bills/\(billID.rawValue)/receipts/\(receiptID.rawValue)",
      filename: "comprovante-\(receiptID.rawValue)"
    )
  }
  public func downloadAttachment(billingID: BillingID, attachmentID: AttachmentID) async throws -> DownloadedFile {
    try await client.download(
      path: "/api/v1/billings/\(billingID.rawValue)/attachments/\(attachmentID.rawValue)",
      filename: "arquivo-\(attachmentID.rawValue)"
    )
  }
  public func requestExport(billingID: BillingID, format: String) async throws {
    let _: RemoteExport = try await decode(
      path: "/api/v1/billings/\(billingID.rawValue)/exports", method: "POST", body: RemoteExportRequest(format: format)
    )
  }
  public func dashboardSummary() async throws -> DashboardSummary {
    // `GET /api/v1/billings` already returns a `stats` rollup (`BillingStatsResponse`) computed
    // server-side across every billing visible to the user, so a single request gives us every
    // money figure the dashboard needs. This also sidesteps the previous ~3N fan-out entirely,
    // so an individual billing lacking bill/expense read capability can no longer break the
    // whole dashboard (the aggregate isn't gated by those per-billing capabilities).
    let response: RemoteBillingList = try await decode(path: "/api/v1/billings")
    let stats = response.stats
    let collectionRate = stats.billedCount == 0 ? 0 : stats.paidCount * 100 / stats.billedCount
    return DashboardSummary(
      received: Money(centavos: stats.received),
      expenses: Money(centavos: stats.totalExpenses),
      netIncome: Money(centavos: stats.netIncome),
      overdue: Money(centavos: stats.overdue),
      upcoming: Money(centavos: stats.pending),
      collectionRatePercent: collectionRate
    )
  }
  public func listOrganizations() async throws -> [Organization] {
    let response: RemoteOrganizationList = try await decode(path: "/api/v1/organizations")
    var organizations: [Organization] = []
    organizations.reserveCapacity(response.items.count)
    for item in response.items {
      organizations.append(try await organization(id: OrganizationID(rawValue: item.uuid)))
    }
    return organizations
  }
  public func organization(id: OrganizationID) async throws -> Organization {
    let response: RemoteOrganization = try await decode(path: "/api/v1/organizations/\(id.rawValue)")
    return organization(from: response)
  }
  public func createOrganization(_ draft: OrganizationDraft) async throws -> Organization {
    // OrganizationCreateRequest only accepts `name`; PIX has no create-time slot, so when the
    // draft carries PIX data we follow up with the PATCH that does accept pix fields.
    let response: RemoteOrganization = try await decode(path: "/api/v1/organizations", method: "POST", body: RemoteOrganizationCreate(name: draft.name))
    guard draft.pix != nil else { return organization(from: response) }
    do {
      let updated: RemoteOrganization = try await decode(
        path: "/api/v1/organizations/\(response.uuid)", method: "PATCH", body: RemoteOrganizationUpdate(draft: draft)
      )
      return organization(from: updated)
    } catch {
      // The organization already exists on the server from the POST above, so throwing here
      // would surface as a failure to the caller, who would retry and create a duplicate
      // organization. Return the created organization (without PIX) instead; the form-side
      // validation makes this follow-up PATCH fail rarely, and the user can still edit the
      // organization afterward to add PIX.
      return organization(from: response)
    }
  }
  public func updateOrganization(id: OrganizationID, draft: OrganizationDraft) async throws -> Organization {
    let response: RemoteOrganization = try await decode(path: "/api/v1/organizations/\(id.rawValue)", method: "PATCH", body: RemoteOrganizationUpdate(draft: draft))
    return organization(from: response)
  }
  public func deleteOrganization(id: OrganizationID) async throws { try await execute(path: "/api/v1/organizations/\(id.rawValue)", method: "DELETE") }
  public func updateMemberRole(organizationID: OrganizationID, userID: Int, role: OrganizationRole) async throws { try await execute(path: "/api/v1/organizations/\(organizationID.rawValue)/members/\(userID)", method: "PATCH", body: RemoteMemberRole(role: role.rawValue)) }
  public func removeMember(organizationID: OrganizationID, userID: Int) async throws { try await execute(path: "/api/v1/organizations/\(organizationID.rawValue)/members/\(userID)", method: "DELETE") }
  public func inviteMember(organizationID: OrganizationID, email: String, role: OrganizationRole) async throws -> Invitation {
    let response: RemoteInvitation = try await decode(path: "/api/v1/organizations/\(organizationID.rawValue)/invites", method: "POST", body: RemoteInviteCreate(email: email, role: role.rawValue))
    // Best-effort enrichment: the invite already succeeded, so a failure here shouldn't fail the whole call.
    let organizationName = (try? await organization(id: organizationID))?.name ?? "Organização"
    return Invitation(id: InvitationID(rawValue: response.uuid), organizationID: organizationID, organizationName: organizationName, email: response.invitedEmail, role: OrganizationRole(rawValue: response.role) ?? .viewer, status: InvitationStatus(rawValue: response.status) ?? .pending)
  }
  public func setOrganizationMFA(organizationID: OrganizationID, required: Bool) async throws { try await execute(path: "/api/v1/organizations/\(organizationID.rawValue)/mfa-policy", method: "PUT", body: RemoteMFAPolicy(enforceMFA: required)) }
  public func transferBilling(billingID: BillingID, toOrganizationID: OrganizationID) async throws { try await execute(path: "/api/v1/billings/\(billingID.rawValue)/transfer", method: "POST", body: RemoteBillingTransfer(organizationID: toOrganizationID.rawValue)) }
  public func listPendingInvitations() async throws -> [Invitation] {
    let response: RemotePendingInvitationList = try await decode(path: "/api/v1/invites")
    return response.items.map {
      Invitation(
        id: InvitationID(rawValue: $0.uuid), organizationID: OrganizationID(rawValue: $0.organizationUUID),
        organizationName: $0.organizationName, email: user.email,
        role: OrganizationRole(rawValue: $0.role) ?? .viewer, status: .pending
      )
    }
  }
  public func acceptInvitation(id: InvitationID) async throws { try await execute(path: "/api/v1/invites/\(id.rawValue)/accept", method: "POST") }
  public func declineInvitation(id: InvitationID) async throws { try await execute(path: "/api/v1/invites/\(id.rawValue)/decline", method: "POST") }
  public func changePassword(
    currentPassword: String, newPassword: String, confirmPassword: String
  ) async throws {
    try await execute(
      path: "/api/v1/security/change-password", method: "POST",
      body: RemotePasswordChange(
        currentPassword: currentPassword, newPassword: newPassword, confirmPassword: confirmPassword
      )
    )
  }
  public func securitySummary() async throws -> SecuritySummary {
    let response: RemoteSecuritySummary = try await decode(path: "/api/v1/security")
    return SecuritySummary(totpEnabled: response.totp.enabled, recoveryCodeCount: response.totp.recoveryCodesRemaining,
      passkeys: try response.passkeys.map { Passkey(id: PasskeyID(rawValue: $0.uuid), name: $0.name, createdAt: try isoDate($0.createdAt), lastUsedAt: try $0.lastUsedAt.map(isoDate)) })
  }
  public func beginTOTPEnrollment() async throws -> TOTPEnrollment {
    let response: RemoteTOTPSetup = try await decode(path: "/api/v1/security/totp/setup", method: "POST")
    return TOTPEnrollment(secret: response.secret, provisioningURI: response.provisioningURI, qrCodeBase64: response.qrCodeBase64)
  }
  public func confirmTOTPEnrollment(code: String) async throws -> [String] {
    let response: RemoteRecoveryCodes = try await decode(
      path: "/api/v1/security/totp/confirm", method: "POST", body: RemoteTOTPConfirm(code: code)
    )
    return response.recoveryCodes
  }
  public func disableTOTP(password: String) async throws {
    try await execute(path: "/api/v1/security/totp/disable", method: "POST", body: RemoteTOTPDisable(password: password))
  }
  public func regenerateRecoveryCodes() async throws -> [String] {
    let response: RemoteRecoveryCodes = try await decode(path: "/api/v1/security/recovery-codes/regenerate", method: "POST")
    return response.recoveryCodes
  }
  public func deletePasskey(id: PasskeyID) async throws { try await execute(path: "/api/v1/security/passkeys/\(id.rawValue)", method: "DELETE") }
  public func listAPIKeys() async throws -> [APIKeyMetadata] {
    let response: RemoteAPIKeyList = try await decode(path: "/api/v1/api-keys")
    // The server returns revoked keys too (it doesn't filter them); match the mock and hide them.
    return try response.items.filter { $0.revokedAt == nil }.map(apiKey(from:))
  }
  public func createAPIKey(_ draft: APIKeyDraft) async throws -> CreatedAPIKeySecret {
    let response: RemoteCreatedAPIKey = try await decode(
      path: "/api/v1/api-keys", method: "POST", body: RemoteAPIKeyCreate(draft: draft)
    )
    return CreatedAPIKeySecret(metadata: try apiKey(from: response.apiKey), secret: response.secret)
  }
  public func updateAPIKey(id: APIKeyID, draft: APIKeyDraft) async throws -> APIKeyMetadata {
    let response: RemoteAPIKey = try await decode(
      path: "/api/v1/api-keys/\(id.rawValue)", method: "PATCH", body: RemoteAPIKeyUpdate(draft: draft)
    )
    return try apiKey(from: response)
  }
  public func revokeAPIKey(id: APIKeyID) async throws {
    try await execute(path: "/api/v1/api-keys/\(id.rawValue)", method: "DELETE")
  }
  public func theme(target: ThemeTarget) async throws -> ThemeRecord {
    let response: RemoteTheme = try await decode(path: themePath(for: target))
    return theme(from: response)
  }
  public func updateTheme(target: ThemeTarget, values: ThemeValues) async throws {
    try await execute(path: themePath(for: target), method: "PUT", body: RemoteThemeValues(values))
  }
  public func resetTheme(target: ThemeTarget) async throws {
    try await execute(path: themePath(for: target), method: "DELETE")
  }

  private func decode<Response: Decodable>(path: String) async throws -> Response {
    let data = try await client.request(path: path)
    do { return try JSONDecoder().decode(Response.self, from: data) }
    catch { throw LiveAPIError.invalidResponse }
  }

  private func decode<Response: Decodable>(path: String, method: String) async throws -> Response {
    let data = try await client.request(path: path, method: method)
    do { return try JSONDecoder().decode(Response.self, from: data) }
    catch { throw LiveAPIError.invalidResponse }
  }

  private func decode<Response: Decodable, Body: Encodable>(path: String, method: String, body: Body) async throws -> Response {
    let data = try await client.request(path: path, method: method, body: try JSONEncoder().encode(body))
    do { return try JSONDecoder().decode(Response.self, from: data) }
    catch { throw LiveAPIError.invalidResponse }
  }

  private func decodeMultipart<Response: Decodable>(
    path: String, name: String? = nil, files: [(field: String, upload: FileUpload)]
  ) async throws -> Response {
    let boundary = "RentivoBoundary-\(UUID().uuidString)"
    let data = multipartBody(boundary: boundary, name: name, files: files)
    let response = try await client.request(
      path: path, method: "POST", body: data,
      contentType: "multipart/form-data; boundary=\(boundary)"
    )
    do { return try JSONDecoder().decode(Response.self, from: response) }
    catch { throw LiveAPIError.invalidResponse }
  }

  private func execute(path: String, method: String) async throws {
    _ = try await client.request(path: path, method: method)
  }

  private func execute<Body: Encodable>(path: String, method: String, body: Body) async throws {
    _ = try await client.request(path: path, method: method, body: try JSONEncoder().encode(body))
  }

  private func multipartBody(
    boundary: String, name: String?, files: [(field: String, upload: FileUpload)]
  ) -> Data {
    var body = Data()
    func append(_ string: String) { body.append(string.data(using: .utf8)!) }
    if let name {
      append("--\(boundary)\r\n")
      append("Content-Disposition: form-data; name=\"name\"\r\n\r\n\(name)\r\n")
    }
    for file in files {
      append("--\(boundary)\r\n")
      append("Content-Disposition: form-data; name=\"\(file.field)\"; filename=\"\(sanitizedFilename(file.upload.filename))\"\r\n")
      append("Content-Type: \(file.upload.mediaType)\r\n\r\n")
      body.append(file.upload.data)
      append("\r\n")
    }
    append("--\(boundary)--\r\n")
    return body
  }

  // Strips characters that could break out of the quoted `filename="..."` attribute (or the
  // header line entirely) and inject extra multipart headers/parts.
  private func sanitizedFilename(_ filename: String) -> String {
    var sanitized = filename
    for token in ["\r\n", "\r", "\n", "\""] {
      sanitized = sanitized.replacingOccurrences(of: token, with: "")
    }
    return sanitized
  }

  private func owner(from owner: RemoteOwner) -> BillingOwner {
    if owner.type == "organization", let uuid = owner.uuid {
      return .organization(id: OrganizationID(rawValue: uuid), name: owner.name ?? "Organização")
    }
    return .user(id: user.id, name: owner.name ?? "Pessoal")
  }

  private func pix(key: String, name: String, city: String) -> PixConfiguration? {
    guard !key.isEmpty || !name.isEmpty || !city.isEmpty else { return nil }
    return PixConfiguration(key: key, merchantName: name, merchantCity: city)
  }

  // Absent dates (a legitimate `null` from the server) fall back to the epoch default, as before.
  // A *present but malformed* date string, however, now surfaces as a decode error via `DateOnly`'s
  // failable wire initializer instead of reaching the precondition-enforcing `DateOnly.init(year:month:day:)`
  // and trapping the process on out-of-range components.
  private func dateOnly(_ value: String?) throws -> DateOnly {
    guard let value else { return DateOnly(year: 1970, month: 1, day: 1) }
    guard let parsed = DateOnly(iso8601String: value) else { throw LiveAPIError.invalidResponse }
    return parsed
  }

  // The backend emits fractional-second timestamps (microseconds); try that format first and
  // fall back to the plain internet-date-time form. A total parse failure surfaces as a decode
  // error instead of silently defaulting to `.distantPast`.
  private static let isoDateTimeFormatterWithFraction: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
  }()
  private static let isoDateTimeFormatter = ISO8601DateFormatter()

  private func isoDate(_ value: String) throws -> Date {
    if let date = Self.isoDateTimeFormatterWithFraction.date(from: value) { return date }
    if let date = Self.isoDateTimeFormatter.date(from: value) { return date }
    throw LiveAPIError.invalidResponse
  }

  private func paidAt(from remote: RemoteBill) throws -> DateOnly? {
    guard remote.status == "paid", let statusUpdatedAt = remote.statusUpdatedAt else { return nil }
    let datePart = statusUpdatedAt.split(separator: "T", maxSplits: 1).first.map(String.init) ?? statusUpdatedAt
    return try dateOnly(datePart)
  }

  private func bill(from remote: RemoteBill, billingID: BillingID) throws -> Bill {
    // `ReferenceMonth`'s failable wire initializer replaces the previous manual split + the
    // precondition-enforcing `ReferenceMonth.init(year:month:)`, so a malformed `reference_month`
    // (e.g. an out-of-range month) now throws a decode error instead of trapping the process.
    guard let referenceMonth = ReferenceMonth(apiValue: remote.referenceMonth) else {
      throw LiveAPIError.invalidResponse
    }
    return Bill(
      id: BillID(rawValue: remote.uuid), billingID: billingID,
      referenceMonth: referenceMonth,
      dueDate: try dateOnly(remote.dueDate), paidAt: try paidAt(from: remote),
      notes: remote.notes, status: BillStatus(rawValue: remote.status) ?? .draft,
      lineItems: remote.lineItems.enumerated().map { index, line in
        BillLineItem(id: BillLineItemID(rawValue: "\(remote.uuid)-\(index)"), description: line.description,
          amount: Money(centavos: line.amount), kind: BillLineItemKind(rawValue: line.itemType) ?? .fixed)
      }, receipts: (remote.receipts ?? []).map {
        Receipt(id: ReceiptID(rawValue: $0.uuid), name: $0.filename, sortOrder: $0.sortOrder)
      },
      // Server-authoritative transitions/total for this bill (see `Bill.effectiveTransitions` /
      // `Bill.effectiveTotal`); unrecognized transition targets are dropped rather than failing the
      // whole decode, since a missing action button is a much smaller failure than a hard error.
      availableTransitions: remote.availableTransitions.compactMap { BillStatus(rawValue: $0.target) },
      serverTotal: Money(centavos: remote.totalAmount)
    )
  }

  private func billing(from remote: RemoteBilling) -> Billing {
    Billing(
      id: BillingID(rawValue: remote.uuid), name: remote.name, description: remote.description,
      owner: owner(from: remote.owner),
      items: remote.items.enumerated().map { index, item in
        BillingItem(id: BillingItemID(rawValue: item.uuid), description: item.description,
          amount: Money(centavos: item.amount), type: BillingItemType(rawValue: item.itemType) ?? .fixed,
          sortOrder: index)
      },
      pixOverride: pix(key: remote.pixKey, name: remote.pixMerchantName, city: remote.pixMerchantCity),
      recipients: remote.recipients.compactMap { contact in
        guard let name = contact.name, let email = contact.email else { return nil }
        return BillingRecipient(id: RecipientID(rawValue: contact.uuid), name: name, email: email)
      },
      replyTo: remote.replyTo.first?.email,
      capabilities: capabilities(from: remote.capabilities)
    )
  }

  private func capabilities(from remote: RemoteBillingCapabilities) -> BillingCapabilities {
    BillingCapabilities(
      canEdit: remote.canEdit, canReadBills: remote.canReadBills,
      canCreateBills: remote.canCreateBills, canManageBills: remote.canManageBills,
      canReadExpenses: remote.canReadExpenses, canWriteExpenses: remote.canWriteExpenses,
      canCreateExports: remote.canCreateExports, canReadAttachments: remote.canReadAttachments,
      canWriteAttachments: remote.canWriteAttachments, canReadTheme: remote.canReadTheme,
      canManageTheme: remote.canManageTheme,
      canUploadBillReceipts: remote.canUploadBillReceipts, canDelete: remote.canDelete,
      canTransfer: remote.canTransfer
    )
  }

  private func organization(from remote: RemoteOrganization) -> Organization {
    Organization(id: OrganizationID(rawValue: remote.uuid), name: remote.name,
      pix: remote.settings.flatMap { pix(key: $0.pixKey, name: $0.pixMerchantName, city: $0.pixMerchantCity) },
      members: (remote.members ?? []).map {
        OrganizationMember(userID: $0.userID, email: $0.email, role: OrganizationRole(rawValue: $0.role) ?? .viewer)
      },
      requiresMFA: remote.enforceMFA, currentUserRole: OrganizationRole(rawValue: remote.currentRole) ?? .viewer,
      capabilities: OrganizationCapabilities(canManage: remote.capabilities.canManage, canInvite: remote.capabilities.canInvite,
        canCreateBilling: remote.capabilities.canCreateBilling, canViewBillingStats: remote.capabilities.canViewBillingStats))
  }

  private func apiKey(from remote: RemoteAPIKey) throws -> APIKeyMetadata {
    APIKeyMetadata(
      id: APIKeyID(rawValue: remote.uuid), name: remote.name, hint: remote.hint,
      scopes: Set(remote.scopes.compactMap(APIKeyScope.init(rawValue:))),
      grants: remote.grants.compactMap { grant in
        guard let resourceID = grant.resourceID,
          let resourceType = WorkspaceResourceType(rawValue: grant.resourceType)
        else { return nil }
        return APIKeyGrant(
          resourceType: resourceType, resourceID: WorkspaceID(rawValue: resourceID),
          available: grant.available
        )
      },
      expiresAt: try isoDate(remote.expiresAt), lastUsedAt: try remote.lastUsedAt.map(isoDate),
      createdAt: try isoDate(remote.createdAt), revokedAt: try remote.revokedAt.map(isoDate)
    )
  }

  private func attachment(from remote: RemoteAttachment) -> Attachment {
    Attachment(
      id: AttachmentID(rawValue: remote.uuid), name: remote.name,
      mediaType: remote.contentType, byteCount: remote.fileSize
    )
  }

  private func themePath(for target: ThemeTarget) -> String {
    switch target {
    case .user: "/api/v1/themes/user"
    case .organization(let id): "/api/v1/themes/organizations/\(id.rawValue)"
    case .billing(let id): "/api/v1/themes/billings/\(id.rawValue)"
    }
  }

  private func theme(from remote: RemoteTheme) -> ThemeRecord {
    ThemeRecord(
      ownerName: remote.ownerName, stored: remote.stored.map(ThemeValues.init),
      effective: ThemeValues(remote.effective),
      effectiveSource: ThemeSource(rawValue: remote.effectiveSource) ?? .default,
      canEdit: remote.capabilities.canEdit, canReset: remote.capabilities.canReset
    )
  }
}

private struct RemoteOrganizationList: Decodable { let items: [RemoteOrganization] }
private struct RemoteOrganization: Decodable {
  let uuid, name, currentRole: String; let enforceMFA: Bool; let capabilities: RemoteOrganizationCapabilities
  let settings: RemoteOrganizationSettings?
  let members: [RemoteOrganizationMember]?
  enum CodingKeys: String, CodingKey { case uuid, name, capabilities, settings, members; case currentRole = "current_role"; case enforceMFA = "enforce_mfa" }
}
private struct RemoteOrganizationCapabilities: Decodable { let canManage, canInvite, canCreateBilling, canViewBillingStats: Bool; enum CodingKeys: String, CodingKey { case canManage = "can_manage"; case canInvite = "can_invite"; case canCreateBilling = "can_create_billing"; case canViewBillingStats = "can_view_billing_stats" } }
private struct RemoteOrganizationSettings: Decodable { let pixKey, pixMerchantName, pixMerchantCity: String; enum CodingKeys: String, CodingKey { case pixKey = "pix_key"; case pixMerchantName = "pix_merchant_name"; case pixMerchantCity = "pix_merchant_city" } }
private struct RemoteOrganizationMember: Decodable { let userID: Int; let email, role: String; enum CodingKeys: String, CodingKey { case email, role; case userID = "user_id" } }
private struct RemoteOrganizationCreate: Encodable { let name: String }
private struct RemoteOrganizationUpdate: Encodable { let name, pixKey, pixMerchantName, pixMerchantCity: String?; enum CodingKeys: String, CodingKey { case name; case pixKey = "pix_key"; case pixMerchantName = "pix_merchant_name"; case pixMerchantCity = "pix_merchant_city" }; init(draft: OrganizationDraft) { name = draft.name; pixKey = draft.pix?.key; pixMerchantName = draft.pix?.merchantName; pixMerchantCity = draft.pix?.merchantCity } }
private struct RemoteMemberRole: Encodable { let role: String }
private struct RemoteInviteCreate: Encodable { let email, role: String }
private struct RemoteMFAPolicy: Encodable { let enforceMFA: Bool; enum CodingKeys: String, CodingKey { case enforceMFA = "enforce_mfa" } }
private struct RemoteBillingTransfer: Encodable { let organizationID: String; enum CodingKeys: String, CodingKey { case organizationID = "organization_uuid" } }
private struct RemoteInvitation: Decodable { let uuid, invitedEmail, role, status: String; enum CodingKeys: String, CodingKey { case uuid, role, status; case invitedEmail = "invited_email" } }
private struct RemotePendingInvitationList: Decodable { let items: [RemotePendingInvitation] }
private struct RemotePendingInvitation: Decodable {
  let uuid, organizationUUID, organizationName, role: String
  enum CodingKeys: String, CodingKey {
    case uuid, role
    case organizationUUID = "organization_uuid"
    case organizationName = "organization_name"
  }
}
private struct RemoteSecuritySummary: Decodable { let profile: RemoteProfile; let totp: RemoteTOTPStatus; let passkeys: [RemotePasskey] }
private struct RemoteTOTPStatus: Decodable { let enabled: Bool; let recoveryCodesRemaining: Int; enum CodingKeys: String, CodingKey { case enabled; case recoveryCodesRemaining = "recovery_codes_remaining" } }
private struct RemoteTOTPSetup: Decodable {
  let secret, provisioningURI, qrCodeBase64: String
  enum CodingKeys: String, CodingKey {
    case secret
    case provisioningURI = "provisioning_uri"
    case qrCodeBase64 = "qr_code_base64"
  }
}
private struct RemoteTOTPConfirm: Encodable { let code: String }
private struct RemoteTOTPDisable: Encodable { let password: String }
struct RemotePasswordChange: Encodable {
  let currentPassword, newPassword, confirmPassword: String
  enum CodingKeys: String, CodingKey {
    case currentPassword = "current_password"
    case newPassword = "new_password"
    case confirmPassword = "confirm_password"
  }
}
private struct RemotePasskey: Decodable { let uuid, name, createdAt: String; let lastUsedAt: String?; enum CodingKeys: String, CodingKey { case uuid, name; case createdAt = "created_at"; case lastUsedAt = "last_used_at" } }
private struct RemoteRecoveryCodes: Decodable { let recoveryCodes: [String]; enum CodingKeys: String, CodingKey { case recoveryCodes = "recovery_codes" } }
private struct RemoteContactList: Decodable { let items: [RemoteContactRecord] }
// The send endpoint's response shape is `ContactReferenceResponse` (uuid only) for integration
// keys, or `ContactResponse` (uuid+name+email) for login-token sessions (which is what the app
// always uses). Both decode fine into this with name/email left nil when absent.
private struct RemoteContactRecord: Decodable { let uuid: String; let name, email: String? }
private struct RemoteContactListPayload: Encodable { let items: [RemoteContactInput] }
private struct RemoteContactInput: Encodable {
  let name, email: String
  init(name: String, email: String) { self.name = name; self.email = email }
  init(_ recipient: BillingRecipient) { name = recipient.name; email = recipient.email }
}
struct RemoteCommunicationPreviewRequest: Encodable {
  let subject: String
  let body: String
}
private struct RemoteCommunicationPreview: Decodable {
  let html: String
  let severe: [String]
  let mild: [String]
}
private struct RemoteCommunicationSendRequest: Encodable {
  let billID, commType, subject, body: String
  let recipientIDs: [String]
  let acknowledgeWarning = true
  enum CodingKeys: String, CodingKey {
    case subject, body
    case billID = "bill_uuid"
    case commType = "comm_type"
    case recipientIDs = "recipient_uuids"
    case acknowledgeWarning = "acknowledge_warning"
  }
  init(billID: String, recipients: [String], subject: String, message: String) {
    self.billID = billID; commType = "bill_ready"; self.subject = subject; body = message
    recipientIDs = recipients
  }
}
private struct RemoteCommunicationSend: Decodable { let queuedCount: Int; enum CodingKeys: String, CodingKey { case queuedCount = "queued_count" } }
private struct RemoteExportRequest: Encodable { let format: String }
private struct RemoteExport: Decodable { let format, status: String }
private struct RemoteReceiptUpload: Decodable { let items: [RemoteReceipt] }
private struct RemoteReceiptList: Decodable { let items: [RemoteReceipt] }
private struct RemoteReceiptOrder: Encodable { let order: [String] }
private struct RemoteReceipt: Decodable {
  let uuid, filename, contentType: String
  let fileSize, sortOrder: Int
  enum CodingKeys: String, CodingKey {
    case uuid, filename
    case contentType = "content_type"
    case fileSize = "file_size"
    case sortOrder = "sort_order"
  }
}
private struct RemoteAttachmentList: Decodable { let items: [RemoteAttachment] }
private struct RemoteAttachment: Decodable {
  let uuid, name, contentType: String
  let fileSize: Int
  enum CodingKeys: String, CodingKey {
    case uuid, name
    case contentType = "content_type"
    case fileSize = "file_size"
  }
}
private struct RemoteAPIKeyList: Decodable { let items: [RemoteAPIKey] }
private struct RemoteAPIKey: Decodable {
  let uuid, name, hint, expiresAt, createdAt: String
  let scopes: [String]
  let grants: [RemoteAPIKeyGrant]
  let lastUsedAt, revokedAt: String?
  enum CodingKeys: String, CodingKey {
    case uuid, name, hint, scopes, grants
    case expiresAt = "expires_at"
    case lastUsedAt = "last_used_at"
    case createdAt = "created_at"
    case revokedAt = "revoked_at"
  }
}
private struct RemoteCreatedAPIKey: Decodable {
  let secret: String
  let apiKey: RemoteAPIKey
  enum CodingKeys: String, CodingKey {
    case secret, uuid, name, hint, scopes, grants
    case expiresAt = "expires_at"
    case lastUsedAt = "last_used_at"
    case createdAt = "created_at"
    case revokedAt = "revoked_at"
  }
  init(from decoder: Decoder) throws {
    secret = try decoder.container(keyedBy: CodingKeys.self).decode(String.self, forKey: .secret)
    apiKey = try RemoteAPIKey(from: decoder)
  }
}
private struct RemoteAPIKeyGrant: Decodable {
  let resourceType: String
  let resourceID: String?
  let available: Bool
  enum CodingKeys: String, CodingKey {
    case available
    case resourceType = "resource_type"
    case resourceID = "resource_id"
  }
}
private struct RemoteAPIKeyCreate: Encodable {
  let name: String
  let scopes: [String]
  let grants: [RemoteAPIKeyGrantInput]
  let expiresAt: String
  enum CodingKeys: String, CodingKey { case name, scopes, grants; case expiresAt = "expires_at" }
  init(draft: APIKeyDraft) {
    name = draft.name
    scopes = draft.scopes.map(\.rawValue).sorted()
    grants = draft.grants.map(RemoteAPIKeyGrantInput.init)
    expiresAt = ISO8601DateFormatter().string(from: draft.expiresAt)
  }
}
private struct RemoteAPIKeyUpdate: Encodable {
  let name: String
  let scopes: [String]
  let grants: [RemoteAPIKeyGrantInput]
  init(draft: APIKeyDraft) {
    name = draft.name
    scopes = draft.scopes.map(\.rawValue).sorted()
    grants = draft.grants.map(RemoteAPIKeyGrantInput.init)
  }
}
private struct RemoteAPIKeyGrantInput: Encodable {
  let resourceType: String
  let resourceID: String
  enum CodingKeys: String, CodingKey { case resourceType = "resource_type"; case resourceID = "resource_id" }
  init(_ grant: APIKeyGrant) { resourceType = grant.resourceType.rawValue; resourceID = grant.resourceID.rawValue }
}
private struct RemoteTheme: Decodable {
  let ownerName, effectiveSource: String
  let stored: RemoteThemeValues?
  let effective: RemoteThemeValues
  let capabilities: RemoteThemeCapabilities
  enum CodingKeys: String, CodingKey {
    case stored, effective, capabilities
    case ownerName = "owner_name"
    case effectiveSource = "effective_source"
  }
}
private struct RemoteThemeCapabilities: Decodable {
  let canEdit, canReset: Bool
  enum CodingKeys: String, CodingKey { case canEdit = "can_edit"; case canReset = "can_reset" }
}
private struct RemoteThemeValues: Codable {
  let headerFont, textFont: String
  let primary, primaryLight, secondary, secondaryDark, textColor, textContrast: String
  enum CodingKeys: String, CodingKey {
    case primary, secondary
    case headerFont = "header_font"
    case textFont = "text_font"
    case primaryLight = "primary_light"
    case secondaryDark = "secondary_dark"
    case textColor = "text_color"
    case textContrast = "text_contrast"
  }
  init(_ values: ThemeValues) {
    headerFont = values.headerFont.rawValue; textFont = values.textFont.rawValue
    primary = values.primary; primaryLight = values.primaryLight; secondary = values.secondary
    secondaryDark = values.secondaryDark; textColor = values.textColor; textContrast = values.textContrast
  }
}
private extension ThemeValues {
  init(_ remote: RemoteThemeValues) {
    self.init(
      headerFont: ThemeFont(rawValue: remote.headerFont) ?? .montserrat,
      textFont: ThemeFont(rawValue: remote.textFont) ?? .openSans,
      primary: remote.primary, primaryLight: remote.primaryLight, secondary: remote.secondary,
      secondaryDark: remote.secondaryDark, textColor: remote.textColor,
      textContrast: remote.textContrast
    )
  }
}

private struct RemoteBillingDraft: Encodable {
  let name: String; let description: String; let owner: RemoteOwnerInput; let items: [RemoteBillingItemInput]
  let pixKey: String; let pixMerchantName: String; let pixMerchantCity: String
  let recipients, replyTo: [RemoteContactInput]
  enum CodingKeys: String, CodingKey { case name, description, owner, items, recipients; case replyTo = "reply_to"; case pixKey = "pix_key"; case pixMerchantName = "pix_merchant_name"; case pixMerchantCity = "pix_merchant_city" }
  init(draft: BillingDraft) {
    name = draft.name; description = draft.description; items = draft.items.map(RemoteBillingItemInput.init)
    pixKey = draft.pixOverride?.key ?? ""; pixMerchantName = draft.pixOverride?.merchantName ?? ""; pixMerchantCity = draft.pixOverride?.merchantCity ?? ""
    recipients = draft.recipients.map(RemoteContactInput.init)
    replyTo = draft.replyTo.map { [RemoteContactInput(name: "Resposta", email: $0)] } ?? []
    switch draft.owner { case .user: owner = RemoteOwnerInput(type: "user", uuid: nil); case .organization(let id, _): owner = RemoteOwnerInput(type: "organization", uuid: id.rawValue) }
  }
}
private struct RemoteBillingUpdate: Encodable {
  let name, description, pixKey, pixMerchantName, pixMerchantCity: String
  let items: [RemoteBillingItemInput]
  let recipients, replyTo: [RemoteContactInput]
  enum CodingKeys: String, CodingKey { case name, description, items, recipients; case replyTo = "reply_to"; case pixKey = "pix_key"; case pixMerchantName = "pix_merchant_name"; case pixMerchantCity = "pix_merchant_city" }
  init(draft: BillingDraft) {
    name = draft.name; description = draft.description; items = draft.items.map(RemoteBillingItemInput.init)
    pixKey = draft.pixOverride?.key ?? ""; pixMerchantName = draft.pixOverride?.merchantName ?? ""; pixMerchantCity = draft.pixOverride?.merchantCity ?? ""
    recipients = draft.recipients.map(RemoteContactInput.init)
    replyTo = draft.replyTo.map { [RemoteContactInput(name: "Resposta", email: $0)] } ?? []
  }
}
private struct RemoteOwnerInput: Encodable { let type: String; let uuid: String? }
// Billing items minted client-side (a new row added in the form) carry a 36-char UUID as their
// id; the server only accepts a 26-char Crockford-base32 ULID (or null) for `uuid`, so only
// ids that already look like a server-issued ULID may be sent through — everything else must
// be nil so the server mints its own.
private let ulidAllowedCharacters = Set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
private func isULID(_ value: String) -> Bool {
  value.count == 26 && value.allSatisfy(ulidAllowedCharacters.contains)
}
private struct RemoteBillingItemInput: Encodable {
  let uuid: String?; let description: String; let amount: Int; let itemType: String
  enum CodingKeys: String, CodingKey { case uuid, description, amount; case itemType = "item_type" }
  init(_ item: BillingItem) {
    uuid = isULID(item.id.rawValue) ? item.id.rawValue : nil
    description = item.description; amount = item.amount.centavos; itemType = item.type.rawValue
  }
}
private struct RemoteBillCreateDraft: Encodable {
  let referenceMonth: String; let dueDate: String; let notes: String; let extras: [RemoteBillExtra]
  let variableAmounts: [String: Int]
  enum CodingKeys: String, CodingKey {
    case referenceMonth = "reference_month"; case dueDate = "due_date"; case notes, extras
    case variableAmounts = "variable_amounts"
  }
  init(draft: BillDraft) {
    referenceMonth = draft.referenceMonth.apiValue; dueDate = draft.dueDate.iso8601; notes = draft.notes
    extras = draft.lineItems.filter { $0.kind == .extra }.map(RemoteBillExtra.init)
    // The server requires the variable_amounts key set to exactly match the billing's own
    // variable BillingItem uuids, so only line items whose id is already a real ULID (i.e. one
    // sourced from the billing's items, not a freshly client-minted id) can be included.
    var amounts: [String: Int] = [:]
    for item in draft.lineItems where item.kind == .variable {
      guard isULID(item.id.rawValue) else { continue }
      amounts[item.id.rawValue] = item.amount.centavos
    }
    variableAmounts = amounts
  }
}
private struct RemoteBillExtra: Encodable { let description: String; let amount: Int; init(_ item: BillLineItem) { description = item.description; amount = item.amount.centavos } }
private struct RemoteBillUpdateDraft: Encodable {
  let dueDate: String; let notes: String; let lineItems: [RemoteBillLineItemInput]
  enum CodingKeys: String, CodingKey { case dueDate = "due_date"; case notes; case lineItems = "line_items" }
  init(draft: BillDraft) { dueDate = draft.dueDate.iso8601; notes = draft.notes; lineItems = draft.lineItems.map(RemoteBillLineItemInput.init) }
}
private struct RemoteBillLineItemInput: Encodable { let description: String; let amount: Int; let itemType: String; enum CodingKeys: String, CodingKey { case description, amount; case itemType = "item_type" }; init(_ item: BillLineItem) { description = item.description; amount = item.amount.centavos; itemType = item.kind.rawValue } }
private struct RemoteBillTransition: Encodable { let target: String }
private struct RemoteExpenseCreate: Encodable { let description: String; let category: String; let incurredOn: String; let amount: Int; enum CodingKeys: String, CodingKey { case description, category, amount; case incurredOn = "incurred_on" } }

private struct RemoteBillingList: Decodable { let items: [RemoteBillingListItem]; let stats: RemoteBillingStats }
private struct RemoteBillingStats: Decodable {
  let received, pending, overdue, totalExpenses, netIncome, paidCount, billedCount: Int
  enum CodingKeys: String, CodingKey {
    case received, pending, overdue
    case totalExpenses = "total_expenses"
    case netIncome = "net_income"
    case paidCount = "paid_count"
    case billedCount = "billed_count"
  }
}
private struct RemoteProfile: Decodable {
  let email: String; let pixKey, pixMerchantName, pixMerchantCity: String
  enum CodingKeys: String, CodingKey { case email; case pixKey = "pix_key"; case pixMerchantName = "pix_merchant_name"; case pixMerchantCity = "pix_merchant_city" }
}
private struct RemotePixUpdate: Encodable {
  let pixKey, pixMerchantName, pixMerchantCity: String
  enum CodingKeys: String, CodingKey { case pixKey = "pix_key"; case pixMerchantName = "pix_merchant_name"; case pixMerchantCity = "pix_merchant_city" }
  init(pix: PixConfiguration) { pixKey = pix.key; pixMerchantName = pix.merchantName; pixMerchantCity = pix.merchantCity }
}
private struct RemotePixUpdateResponse: Decodable { let profile: RemoteProfile }
private struct RemoteBillingListItem: Decodable { let uuid, name, description: String; let owner: RemoteOwner; let capabilities: RemoteBillingCapabilities }
private struct RemoteBilling: Decodable {
  let uuid, name, description: String
  let owner: RemoteOwner
  let items: [RemoteBillingItem]
  let pixKey, pixMerchantName, pixMerchantCity: String
  let recipients, replyTo: [RemoteBillingContact]
  let capabilities: RemoteBillingCapabilities
  enum CodingKeys: String, CodingKey { case uuid, name, description, owner, items, recipients, capabilities; case replyTo = "reply_to"; case pixKey = "pix_key"; case pixMerchantName = "pix_merchant_name"; case pixMerchantCity = "pix_merchant_city" }
}
private struct RemoteBillingContact: Decodable { let uuid: String; let name, email: String? }
private struct RemoteBillingCapabilities: Decodable {
  let canEdit, canReadBills, canCreateBills, canManageBills, canReadExpenses, canWriteExpenses: Bool
  let canCreateExports, canReadAttachments, canWriteAttachments, canReadTheme, canManageTheme: Bool
  let canUploadBillReceipts, canDelete, canTransfer: Bool
  enum CodingKeys: String, CodingKey {
    case canEdit = "can_edit"; case canReadBills = "can_read_bills"; case canCreateBills = "can_create_bills"
    case canManageBills = "can_manage_bills"; case canReadExpenses = "can_read_expenses"; case canWriteExpenses = "can_write_expenses"
    case canCreateExports = "can_create_exports"; case canReadAttachments = "can_read_attachments"; case canWriteAttachments = "can_write_attachments"
    case canReadTheme = "can_read_theme"; case canManageTheme = "can_manage_theme"; case canUploadBillReceipts = "can_upload_bill_receipts"
    case canDelete = "can_delete"; case canTransfer = "can_transfer"
  }
}
private struct RemoteOwner: Decodable { let type: String; let uuid, name: String? }
private struct RemoteBillingItem: Decodable { let uuid, description: String; let amount: Int; let itemType: String; enum CodingKeys: String, CodingKey { case uuid, description, amount; case itemType = "item_type" } }
private struct RemoteBillList: Decodable { let items: [RemoteBill] }
private struct RemoteBill: Decodable {
  let uuid, referenceMonth, notes, status: String; let dueDate: String?; let statusUpdatedAt: String?
  let lineItems: [RemoteBillLine]; let receipts: [RemoteReceipt]?
  let totalAmount: Int
  let availableTransitions: [RemoteAvailableTransition]
  enum CodingKeys: String, CodingKey {
    case uuid, notes, status, receipts
    case referenceMonth = "reference_month"; case dueDate = "due_date"
    case statusUpdatedAt = "status_updated_at"; case lineItems = "line_items"
    case totalAmount = "total_amount"; case availableTransitions = "available_transitions"
  }
}
// `AvailableTransitionResponse` on the server also carries `label`/`style`/`requires_confirmation`,
// but the domain only models the allowed target statuses today, so only `target` is decoded.
private struct RemoteAvailableTransition: Decodable { let target: String }
private struct RemoteBillLine: Decodable { let description: String; let amount: Int; let itemType: String; enum CodingKeys: String, CodingKey { case description, amount; case itemType = "item_type" } }
private struct RemoteExpenseList: Decodable { let items: [RemoteExpense] }
private struct RemoteExpense: Decodable { let uuid, description, category, incurredOn: String; let amount: Int; enum CodingKeys: String, CodingKey { case uuid, description, category, amount; case incurredOn = "incurred_on" } }

@MainActor
public final class LiveDemoRepository: DemoRepository {
  public private(set) var demoSettings = DemoSettings.standard
  public init() {}
  public func failNextOperation() {}
  public func setEmptyMode(_ enabled: Bool) { demoSettings.emptyMode = enabled }
  public func setViewerMode(_ enabled: Bool) { demoSettings.viewerMode = enabled }
  public func setDelayEnabled(_ enabled: Bool) { demoSettings.delayEnabled = enabled }
  public func reset() { demoSettings = .standard }
}
