import Foundation

@MainActor
public protocol AuthRepository: AnyObject {
  var currentUser: UserProfile { get }
}

@MainActor
public protocol ProfileRepository: AnyObject {
  func profile() async throws -> UserProfile
  func updatePix(_ pix: PixConfiguration) async throws -> UserProfile
}

@MainActor
public protocol BillingRepository: AnyObject {
  func listBillings() async throws -> [Billing]
  func billing(id: BillingID) async throws -> Billing
  func createBilling(_ draft: BillingDraft) async throws -> Billing
  func updateBilling(id: BillingID, draft: BillingDraft) async throws -> Billing
  func deleteBilling(id: BillingID) async throws
}

@MainActor
public protocol BillRepository: AnyObject {
  func listBills(billingID: BillingID) async throws -> [Bill]
  func bill(billingID: BillingID, id: BillID) async throws -> Bill
  func createBill(_ draft: BillDraft) async throws -> Bill
  func updateBill(billingID: BillingID, billID: BillID, draft: BillDraft) async throws -> Bill
  func deleteBill(billingID: BillingID, billID: BillID) async throws
  func transitionBill(billingID: BillingID, billID: BillID, to status: BillStatus) async throws
  func regenerateBill(billingID: BillingID, billID: BillID) async throws -> Bill
  func addReceipt(billingID: BillingID, billID: BillID, upload: FileUpload) async throws -> Receipt
  func reorderReceipts(billingID: BillingID, billID: BillID, receiptIDs: [ReceiptID]) async throws
  func deleteReceipt(billingID: BillingID, billID: BillID, receiptID: ReceiptID) async throws
}

@MainActor
public protocol ExpenseRepository: AnyObject {
  func listExpenses(billingID: BillingID) async throws -> [Expense]
  func createExpense(
    billingID: BillingID,
    description: String,
    category: ExpenseCategory,
    incurredOn: DateOnly,
    amount: Money
  ) async throws -> Expense
  func deleteExpense(billingID: BillingID, expenseID: ExpenseID) async throws
}

@MainActor
public protocol AttachmentRepository: AnyObject {
  func listAttachments(billingID: BillingID) async throws -> [Attachment]
  func addAttachment(billingID: BillingID, upload: FileUpload) async throws -> Attachment
  func deleteAttachment(billingID: BillingID, attachmentID: AttachmentID) async throws
}

@MainActor
public protocol CommunicationRepository: AnyObject {
  func sendCommunication(
    billingID: BillingID,
    billID: BillID?,
    recipients: [String],
    subject: String,
    message: String
  ) async throws -> CommunicationRecord
}

@MainActor
public protocol FileDownloadRepository: AnyObject {
  func downloadInvoice(billingID: BillingID, billID: BillID) async throws -> DownloadedFile
  func downloadRecibo(billingID: BillingID, billID: BillID) async throws -> DownloadedFile
  func downloadReceipt(billingID: BillingID, billID: BillID, receiptID: ReceiptID) async throws -> DownloadedFile
  func downloadAttachment(billingID: BillingID, attachmentID: AttachmentID) async throws -> DownloadedFile
}

@MainActor
public protocol ExportRepository: AnyObject {
  func requestExport(billingID: BillingID, format: String) async throws
}

@MainActor
public protocol DashboardRepository: AnyObject {
  func dashboardSummary() async throws -> DashboardSummary
}

@MainActor
public protocol ActivityRepository: AnyObject {
  var recentActivities: [RecentActivity] { get }
}

@MainActor
public protocol OrganizationRepository: AnyObject {
  func listOrganizations() async throws -> [Organization]
  func organization(id: OrganizationID) async throws -> Organization
  func createOrganization(_ draft: OrganizationDraft) async throws -> Organization
  func updateOrganization(id: OrganizationID, draft: OrganizationDraft) async throws -> Organization
  func deleteOrganization(id: OrganizationID) async throws
  func updateMemberRole(
    organizationID: OrganizationID,
    userID: Int,
    role: OrganizationRole
  ) async throws
  func removeMember(organizationID: OrganizationID, userID: Int) async throws
  func inviteMember(organizationID: OrganizationID, email: String, role: OrganizationRole) async throws
    -> Invitation
  func setOrganizationMFA(organizationID: OrganizationID, required: Bool) async throws
  func transferBilling(billingID: BillingID, toOrganizationID: OrganizationID) async throws
}

@MainActor
public protocol InvitationRepository: AnyObject {
  func listPendingInvitations() async throws -> [Invitation]
  func acceptInvitation(id: InvitationID) async throws
  func declineInvitation(id: InvitationID) async throws
}

@MainActor
public protocol SecurityRepository: AnyObject {
  func securitySummary() async throws -> SecuritySummary
  func beginTOTPEnrollment() async throws -> TOTPEnrollment
  func confirmTOTPEnrollment(code: String) async throws -> [String]
  func disableTOTP(password: String) async throws
  func regenerateRecoveryCodes() async throws -> [String]
  func deletePasskey(id: PasskeyID) async throws
}

@MainActor
public protocol APIKeyRepository: AnyObject {
  func listAPIKeys() async throws -> [APIKeyMetadata]
  func createAPIKey(_ draft: APIKeyDraft) async throws -> CreatedAPIKeySecret
  func updateAPIKey(id: APIKeyID, draft: APIKeyDraft) async throws -> APIKeyMetadata
  func revokeAPIKey(id: APIKeyID) async throws
}

@MainActor
public protocol ThemeRepository: AnyObject {
  func theme(target: ThemeTarget) async throws -> ThemeRecord
  func updateTheme(target: ThemeTarget, values: ThemeValues) async throws
  func resetTheme(target: ThemeTarget) async throws
}

public struct DemoSettings: Hashable, Sendable {
  public var delayEnabled: Bool
  public var emptyMode: Bool
  public var viewerMode: Bool

  public init(delayEnabled: Bool, emptyMode: Bool, viewerMode: Bool) {
    self.delayEnabled = delayEnabled
    self.emptyMode = emptyMode
    self.viewerMode = viewerMode
  }

  public static let standard = DemoSettings(
    delayEnabled: false, emptyMode: false, viewerMode: false
  )
}

@MainActor
public protocol DemoRepository: AnyObject {
  var demoSettings: DemoSettings { get }
  func failNextOperation()
  func setEmptyMode(_ enabled: Bool)
  func setViewerMode(_ enabled: Bool)
  func setDelayEnabled(_ enabled: Bool)
  func reset()
}

@MainActor
public struct AppDependencies {
  public let auth: any AuthRepository
  public let profile: any ProfileRepository
  public let billings: any BillingRepository
  public let bills: any BillRepository
  public let expenses: any ExpenseRepository
  public let attachments: any AttachmentRepository
  public let communications: any CommunicationRepository
  public let downloads: any FileDownloadRepository
  public let exports: any ExportRepository
  public let dashboard: any DashboardRepository
  public let activities: any ActivityRepository
  public let organizations: any OrganizationRepository
  public let invitations: any InvitationRepository
  public let security: any SecurityRepository
  public let apiKeys: any APIKeyRepository
  public let themes: any ThemeRepository
  public let demo: any DemoRepository

  public init(
    auth: any AuthRepository,
    profile: any ProfileRepository,
    billings: any BillingRepository,
    bills: any BillRepository,
    expenses: any ExpenseRepository,
    attachments: any AttachmentRepository,
    communications: any CommunicationRepository,
    downloads: any FileDownloadRepository,
    exports: any ExportRepository,
    dashboard: any DashboardRepository,
    activities: any ActivityRepository,
    organizations: any OrganizationRepository,
    invitations: any InvitationRepository,
    security: any SecurityRepository,
    apiKeys: any APIKeyRepository,
    themes: any ThemeRepository,
    demo: any DemoRepository
  ) {
    self.auth = auth
    self.profile = profile
    self.billings = billings
    self.bills = bills
    self.expenses = expenses
    self.attachments = attachments
    self.communications = communications
    self.downloads = downloads
    self.exports = exports
    self.dashboard = dashboard
    self.activities = activities
    self.organizations = organizations
    self.invitations = invitations
    self.security = security
    self.apiKeys = apiKeys
    self.themes = themes
    self.demo = demo
  }

  public static func mock(store: MockRentivoStore = MockRentivoStore()) -> AppDependencies {
    AppDependencies(
      auth: store,
      profile: store,
      billings: store,
      bills: store,
      expenses: store,
      attachments: store, communications: store, downloads: store, exports: store,
      dashboard: store,
      activities: store,
      organizations: store,
      invitations: store,
      security: store,
      apiKeys: store,
      themes: store,
      demo: store
    )
  }

  public static func live(store: APIRentivoStore = APIRentivoStore()) -> AppDependencies {
    let demo = LiveDemoRepository()
    return AppDependencies(
      auth: store, profile: store, billings: store, bills: store, expenses: store,
      attachments: store, communications: store, downloads: store, exports: store, dashboard: store, activities: store,
      organizations: store, invitations: store, security: store, apiKeys: store,
      themes: store, demo: demo
    )
  }
}

public struct DashboardSummary: Hashable, Sendable {
  public var received: Money
  public var expenses: Money
  public var netIncome: Money
  public var overdue: Money
  public var upcoming: Money
  public var collectionRatePercent: Int

  public init(
    received: Money,
    expenses: Money,
    netIncome: Money,
    overdue: Money,
    upcoming: Money,
    collectionRatePercent: Int
  ) {
    self.received = received
    self.expenses = expenses
    self.netIncome = netIncome
    self.overdue = overdue
    self.upcoming = upcoming
    self.collectionRatePercent = collectionRatePercent
  }
}

public struct StoreSnapshot: Equatable, Sendable {
  public var profile: UserProfile
  public var billings: [Billing]
  public var bills: [Bill]
  public var expenses: [Expense]
  public var attachments: [BillingID: [Attachment]]
  public var organizations: [Organization]
  public var invitations: [Invitation]
  public var communications: [CommunicationRecord]
  public var security: SecuritySummary
  public var apiKeys: [APIKeyMetadata]
  public var themes: [ThemeTarget: ThemeValues]
  public var activities: [RecentActivity]

  public init(
    profile: UserProfile,
    billings: [Billing],
    bills: [Bill],
    expenses: [Expense],
    attachments: [BillingID: [Attachment]],
    organizations: [Organization],
    invitations: [Invitation],
    communications: [CommunicationRecord],
    security: SecuritySummary,
    apiKeys: [APIKeyMetadata],
    themes: [ThemeTarget: ThemeValues],
    activities: [RecentActivity]
  ) {
    self.profile = profile
    self.billings = billings
    self.bills = bills
    self.expenses = expenses
    self.attachments = attachments
    self.organizations = organizations
    self.invitations = invitations
    self.communications = communications
    self.security = security
    self.apiKeys = apiKeys
    self.themes = themes
    self.activities = activities
  }
}
