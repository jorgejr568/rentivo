import Foundation

public enum BillingItemType: String, CaseIterable, Codable, Sendable {
  case fixed
  case variable

  public var label: String { self == .fixed ? "Fixo" : "Variável" }
}

public struct BillingItem: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public var description: String
  public var amount: Money
  public var type: BillingItemType
  public var sortOrder: Int

  public init(id: UUID, description: String, amount: Money, type: BillingItemType, sortOrder: Int) {
    self.id = id
    self.description = description
    self.amount = amount
    self.type = type
    self.sortOrder = sortOrder
  }
}

public enum BillingOwner: Hashable, Codable, Sendable {
  case user(id: UUID, name: String)
  case organization(id: UUID, name: String)

  public var id: UUID {
    switch self {
    case .user(let id, _), .organization(let id, _): id
    }
  }

  public var name: String {
    switch self {
    case .user(_, let name), .organization(_, let name): name
    }
  }

  public var isOrganization: Bool {
    if case .organization = self { return true }
    return false
  }
}

public struct PixConfiguration: Hashable, Codable, Sendable {
  public var key: String
  public var merchantName: String
  public var merchantCity: String

  public init(key: String, merchantName: String, merchantCity: String) {
    self.key = key
    self.merchantName = merchantName
    self.merchantCity = merchantCity
  }

  public var isComplete: Bool {
    !key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      && !merchantName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      && !merchantCity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }
}

public struct BillingRecipient: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public var name: String
  public var email: String

  public init(id: UUID, name: String, email: String) {
    self.id = id
    self.name = name
    self.email = email
  }
}

public struct BillingCapabilities: Hashable, Codable, Sendable {
  public var canEdit: Bool
  public var canReadBills: Bool
  public var canCreateBills: Bool
  public var canManageBills: Bool
  public var canReadExpenses: Bool
  public var canWriteExpenses: Bool
  public var canCreateExports: Bool
  public var canReadAttachments: Bool
  public var canWriteAttachments: Bool
  public var canReadTheme: Bool
  public var canManageTheme: Bool
  public var canUploadBillReceipts: Bool
  public var canDelete: Bool
  public var canTransfer: Bool

  public init(
    canEdit: Bool,
    canReadBills: Bool,
    canCreateBills: Bool,
    canManageBills: Bool,
    canReadExpenses: Bool,
    canWriteExpenses: Bool,
    canCreateExports: Bool,
    canReadAttachments: Bool,
    canWriteAttachments: Bool,
    canReadTheme: Bool,
    canManageTheme: Bool,
    canUploadBillReceipts: Bool,
    canDelete: Bool,
    canTransfer: Bool
  ) {
    self.canEdit = canEdit
    self.canReadBills = canReadBills
    self.canCreateBills = canCreateBills
    self.canManageBills = canManageBills
    self.canReadExpenses = canReadExpenses
    self.canWriteExpenses = canWriteExpenses
    self.canCreateExports = canCreateExports
    self.canReadAttachments = canReadAttachments
    self.canWriteAttachments = canWriteAttachments
    self.canReadTheme = canReadTheme
    self.canManageTheme = canManageTheme
    self.canUploadBillReceipts = canUploadBillReceipts
    self.canDelete = canDelete
    self.canTransfer = canTransfer
  }

  public static let full = BillingCapabilities(
    canEdit: true, canReadBills: true, canCreateBills: true, canManageBills: true,
    canReadExpenses: true, canWriteExpenses: true, canCreateExports: true,
    canReadAttachments: true, canWriteAttachments: true, canReadTheme: true,
    canManageTheme: true, canUploadBillReceipts: true, canDelete: true, canTransfer: true
  )

  public static let viewer = BillingCapabilities(
    canEdit: false, canReadBills: true, canCreateBills: false, canManageBills: false,
    canReadExpenses: true, canWriteExpenses: false, canCreateExports: false,
    canReadAttachments: true, canWriteAttachments: false, canReadTheme: true,
    canManageTheme: false, canUploadBillReceipts: false, canDelete: false, canTransfer: false
  )

  public var allowsEveryAction: Bool {
    [
      canEdit, canReadBills, canCreateBills, canManageBills, canReadExpenses,
      canWriteExpenses, canCreateExports, canReadAttachments, canWriteAttachments,
      canReadTheme, canManageTheme, canUploadBillReceipts, canDelete, canTransfer,
    ].allSatisfy { $0 }
  }
}

public struct Billing: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public var name: String
  public var description: String
  public var owner: BillingOwner
  public var items: [BillingItem]
  public var pixOverride: PixConfiguration?
  public var recipients: [BillingRecipient]
  public var replyTo: String?
  public var capabilities: BillingCapabilities

  public init(
    id: UUID,
    name: String,
    description: String,
    owner: BillingOwner,
    items: [BillingItem],
    pixOverride: PixConfiguration? = nil,
    recipients: [BillingRecipient] = [],
    replyTo: String? = nil,
    capabilities: BillingCapabilities = .full
  ) {
    self.id = id
    self.name = name
    self.description = description
    self.owner = owner
    self.items = items
    self.pixOverride = pixOverride
    self.recipients = recipients
    self.replyTo = replyTo
    self.capabilities = capabilities
  }

  public var fixedSubtotal: Money {
    items.filter { $0.type == .fixed }.map(\.amount).reduce(.zero, +)
  }
}

public struct BillingDraft: Hashable, Sendable {
  public var name: String
  public var description: String
  public var owner: BillingOwner
  public var items: [BillingItem]
  public var pixOverride: PixConfiguration?
  public var recipients: [BillingRecipient]
  public var replyTo: String?

  public init(
    name: String,
    description: String,
    owner: BillingOwner,
    items: [BillingItem],
    pixOverride: PixConfiguration? = nil,
    recipients: [BillingRecipient] = [],
    replyTo: String? = nil
  ) {
    self.name = name
    self.description = description
    self.owner = owner
    self.items = items
    self.pixOverride = pixOverride
    self.recipients = recipients
    self.replyTo = replyTo
  }
}

public enum BillLineItemKind: String, CaseIterable, Codable, Sendable {
  case fixed
  case variable
  case extra
}

public struct BillLineItem: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public var description: String
  public var amount: Money
  public var kind: BillLineItemKind

  public init(id: UUID, description: String, amount: Money, kind: BillLineItemKind) {
    self.id = id
    self.description = description
    self.amount = amount
    self.kind = kind
  }
}

public enum BillStatus: String, CaseIterable, Codable, Sendable {
  case draft
  case published
  case sent
  case paid
  case cancelled
  case delayedPayment = "delayed_payment"

  public var allowedTransitions: Set<BillStatus> {
    switch self {
    case .draft: [.published, .cancelled]
    case .published: [.sent, .paid, .cancelled]
    case .sent: [.paid, .delayedPayment, .cancelled]
    case .delayedPayment: [.paid, .cancelled]
    case .paid, .cancelled: []
    }
  }

  public func canTransition(to target: BillStatus) -> Bool {
    allowedTransitions.contains(target)
  }

  public var label: String {
    switch self {
    case .draft: "Rascunho"
    case .published: "Publicada"
    case .sent: "Enviada"
    case .paid: "Paga"
    case .cancelled: "Cancelada"
    case .delayedPayment: "Pagamento atrasado"
    }
  }
}

public struct Receipt: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public var name: String
  public var sortOrder: Int

  public init(id: UUID, name: String, sortOrder: Int) {
    self.id = id
    self.name = name
    self.sortOrder = sortOrder
  }
}

public struct Attachment: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public var name: String
  public var mediaType: String
  public var byteCount: Int

  public init(id: UUID, name: String, mediaType: String, byteCount: Int) {
    self.id = id
    self.name = name
    self.mediaType = mediaType
    self.byteCount = byteCount
  }
}

public struct Bill: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public let billingID: UUID
  public var referenceMonth: ReferenceMonth
  public var dueDate: DateOnly
  public var paidAt: DateOnly?
  public var notes: String
  public var status: BillStatus
  public var lineItems: [BillLineItem]
  public var receipts: [Receipt]

  public init(
    id: UUID,
    billingID: UUID,
    referenceMonth: ReferenceMonth,
    dueDate: DateOnly,
    paidAt: DateOnly?,
    notes: String,
    status: BillStatus,
    lineItems: [BillLineItem],
    receipts: [Receipt]
  ) {
    self.id = id
    self.billingID = billingID
    self.referenceMonth = referenceMonth
    self.dueDate = dueDate
    self.paidAt = paidAt
    self.notes = notes
    self.status = status
    self.lineItems = lineItems
    self.receipts = receipts
  }

  public var total: Money {
    lineItems.map(\.amount).reduce(.zero, +)
  }
}

public enum ExpenseCategory: String, CaseIterable, Codable, Sendable {
  case propertyTax = "iptu"
  case condominium = "condominio"
  case maintenance = "manutencao"
  case insurance = "seguro"
  case other = "outros"

  public var label: String {
    switch self {
    case .propertyTax: "IPTU"
    case .condominium: "Condomínio"
    case .maintenance: "Manutenção"
    case .insurance: "Seguro"
    case .other: "Outros"
    }
  }
}

public struct Expense: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public let billingID: UUID
  public var description: String
  public var amount: Money
  public var category: ExpenseCategory
  public var incurredOn: DateOnly

  public init(
    id: UUID,
    billingID: UUID,
    description: String,
    amount: Money,
    category: ExpenseCategory,
    incurredOn: DateOnly
  ) {
    self.id = id
    self.billingID = billingID
    self.description = description
    self.amount = amount
    self.category = category
    self.incurredOn = incurredOn
  }
}

public struct CommunicationRecord: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public let billingID: UUID
  public var billID: UUID?
  public var recipients: [String]
  public var subject: String
  public var message: String
  public var sentAt: Date

  public init(
    id: UUID,
    billingID: UUID,
    billID: UUID?,
    recipients: [String],
    subject: String,
    message: String,
    sentAt: Date
  ) {
    self.id = id
    self.billingID = billingID
    self.billID = billID
    self.recipients = recipients
    self.subject = subject
    self.message = message
    self.sentAt = sentAt
  }
}
