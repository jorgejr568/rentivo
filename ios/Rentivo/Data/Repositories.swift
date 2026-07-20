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
  func billing(id: UUID) async throws -> Billing
  func createBilling(_ draft: BillingDraft) async throws -> Billing
  func updateBilling(id: UUID, draft: BillingDraft) async throws -> Billing
  func deleteBilling(id: UUID) async throws
}

@MainActor
public protocol BillRepository: AnyObject {
  func listBills(billingID: UUID) async throws -> [Bill]
  func bill(billingID: UUID, id: UUID) async throws -> Bill
  func transitionBill(billingID: UUID, billID: UUID, to status: BillStatus) async throws
}

@MainActor
public protocol ExpenseRepository: AnyObject {
  func listExpenses(billingID: UUID) async throws -> [Expense]
  func createExpense(
    billingID: UUID,
    description: String,
    category: ExpenseCategory,
    incurredOn: DateOnly,
    amount: Money
  ) async throws -> Expense
  func deleteExpense(billingID: UUID, expenseID: UUID) async throws
}

@MainActor
public protocol OrganizationRepository: AnyObject {
  func listOrganizations() async throws -> [Organization]
  func organization(id: UUID) async throws -> Organization
}

@MainActor
public protocol InvitationRepository: AnyObject {
  func listPendingInvitations() async throws -> [Invitation]
  func acceptInvitation(id: UUID) async throws
  func declineInvitation(id: UUID) async throws
}

@MainActor
public protocol SecurityRepository: AnyObject {
  func securitySummary() async throws -> SecuritySummary
}

@MainActor
public protocol APIKeyRepository: AnyObject {
  func listAPIKeys() async throws -> [APIKeyMetadata]
  func createAPIKey(_ draft: APIKeyDraft) async throws -> CreatedAPIKeySecret
  func revokeAPIKey(id: UUID) async throws
}

@MainActor
public protocol ThemeRepository: AnyObject {
  func theme(target: ThemeTarget) async throws -> ThemeRecord
  func updateTheme(target: ThemeTarget, values: ThemeValues) async throws
  func resetTheme(target: ThemeTarget) async throws
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
  public var attachments: [UUID: [Attachment]]
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
    attachments: [UUID: [Attachment]],
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
