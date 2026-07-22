import Foundation

public enum OrganizationRole: String, CaseIterable, Codable, Sendable {
  case owner
  case admin
  case manager
  case viewer

  public var label: String {
    switch self {
    case .owner: "Proprietário"
    case .admin: "Administrador"
    case .manager: "Gerente"
    case .viewer: "Visualizador"
    }
  }
}

public struct OrganizationCapabilities: Hashable, Codable, Sendable {
  public var canManage: Bool
  public var canInvite: Bool
  public var canCreateBilling: Bool
  public var canViewBillingStats: Bool

  public init(canManage: Bool, canInvite: Bool, canCreateBilling: Bool, canViewBillingStats: Bool) {
    self.canManage = canManage
    self.canInvite = canInvite
    self.canCreateBilling = canCreateBilling
    self.canViewBillingStats = canViewBillingStats
  }

  public static let full = OrganizationCapabilities(
    canManage: true, canInvite: true, canCreateBilling: true, canViewBillingStats: true
  )

  public static let manager = OrganizationCapabilities(
    canManage: false, canInvite: true, canCreateBilling: true, canViewBillingStats: true
  )

  public static let viewer = OrganizationCapabilities(
    canManage: false, canInvite: false, canCreateBilling: false, canViewBillingStats: true
  )

  public static func forRole(_ role: OrganizationRole) -> OrganizationCapabilities {
    switch role {
    case .owner, .admin: .full
    case .manager: .manager
    case .viewer: .viewer
    }
  }
}

public struct OrganizationMember: Identifiable, Hashable, Codable, Sendable {
  public var id: Int { userID }
  public let userID: Int
  public var email: String
  public var role: OrganizationRole

  public init(userID: Int, email: String, role: OrganizationRole) {
    self.userID = userID
    self.email = email
    self.role = role
  }
}

public struct Organization: Identifiable, Hashable, Codable, Sendable {
  public let id: OrganizationID
  public var name: String
  public var pix: PixConfiguration?
  public var members: [OrganizationMember]
  public var requiresMFA: Bool
  public var currentUserRole: OrganizationRole
  public var capabilities: OrganizationCapabilities

  public init(
    id: OrganizationID,
    name: String,
    pix: PixConfiguration?,
    members: [OrganizationMember],
    requiresMFA: Bool,
    currentUserRole: OrganizationRole,
    capabilities: OrganizationCapabilities = .full
  ) {
    self.id = id
    self.name = name
    self.pix = pix
    self.members = members
    self.requiresMFA = requiresMFA
    self.currentUserRole = currentUserRole
    self.capabilities = capabilities
  }
}

public struct OrganizationDraft: Hashable, Sendable {
  public var name: String
  public var pix: PixConfiguration?

  public init(name: String, pix: PixConfiguration?) {
    self.name = name
    self.pix = pix
  }

  public var isValid: Bool {
    !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }
}

public enum InvitationStatus: String, CaseIterable, Codable, Sendable {
  case pending
  case accepted
  case declined
}

public struct Invitation: Identifiable, Hashable, Codable, Sendable {
  public let id: InvitationID
  public let organizationID: OrganizationID
  public var organizationName: String
  public var email: String
  public var role: OrganizationRole
  public var status: InvitationStatus

  public init(
    id: InvitationID,
    organizationID: OrganizationID,
    organizationName: String,
    email: String,
    role: OrganizationRole,
    status: InvitationStatus
  ) {
    self.id = id
    self.organizationID = organizationID
    self.organizationName = organizationName
    self.email = email
    self.role = role
    self.status = status
  }
}

public struct Passkey: Identifiable, Hashable, Codable, Sendable {
  public let id: PasskeyID
  public var name: String
  public var createdAt: Date
  public var lastUsedAt: Date?

  public init(id: PasskeyID, name: String, createdAt: Date, lastUsedAt: Date?) {
    self.id = id
    self.name = name
    self.createdAt = createdAt
    self.lastUsedAt = lastUsedAt
  }
}

public struct SecuritySummary: Hashable, Codable, Sendable {
  public var totpEnabled: Bool
  public var recoveryCodeCount: Int
  public var passkeys: [Passkey]

  public init(totpEnabled: Bool, recoveryCodeCount: Int, passkeys: [Passkey]) {
    self.totpEnabled = totpEnabled
    self.recoveryCodeCount = recoveryCodeCount
    self.passkeys = passkeys
  }
}

public struct TOTPEnrollment: Hashable, Sendable {
  public let secret: String
  public let provisioningURI: String
  public let qrCodeBase64: String

  public init(secret: String, provisioningURI: String, qrCodeBase64: String) {
    self.secret = secret
    self.provisioningURI = provisioningURI
    self.qrCodeBase64 = qrCodeBase64
  }
}

public enum APIKeyScope: String, CaseIterable, Codable, Sendable {
  case profileRead = "profile:read"
  case accountWrite = "account:write"
  case securityManage = "security:manage"
  case apiKeysManage = "api_keys:manage"
  case organizationsRead = "organizations:read"
  case organizationsWrite = "organizations:write"
  case organizationsMembers = "organizations:members"
  case billingsRead = "billings:read"
  case billingsWrite = "billings:write"
  case billsRead = "bills:read"
  case billsWrite = "bills:write"
  case expensesRead = "expenses:read"
  case expensesWrite = "expenses:write"
  case filesRead = "files:read"
  case filesWrite = "files:write"
  case communicationsRead = "communications:read"
  case communicationsSend = "communications:send"
  case themesRead = "themes:read"
  case themesWrite = "themes:write"
  case exportsCreate = "exports:create"

  public static let integrationCases: [APIKeyScope] = [
    .profileRead, .organizationsRead, .billingsRead, .billingsWrite, .billsRead,
    .billsWrite, .expensesRead, .expensesWrite, .filesRead, .filesWrite,
    .communicationsRead, .communicationsSend, .themesRead, .themesWrite, .exportsCreate,
  ]
}

public enum WorkspaceResourceType: String, Codable, Sendable {
  case user
  case organization
}

public struct APIKeyGrant: Hashable, Codable, Sendable {
  public var resourceType: WorkspaceResourceType
  public var resourceID: WorkspaceID
  public var available: Bool

  public init(resourceType: WorkspaceResourceType, resourceID: WorkspaceID, available: Bool = true) {
    self.resourceType = resourceType
    self.resourceID = resourceID
    self.available = available
  }
}

public struct APIKeyMetadata: Identifiable, Hashable, Codable, Sendable {
  public let id: APIKeyID
  public var name: String
  public var hint: String
  public var scopes: Set<APIKeyScope>
  public var grants: [APIKeyGrant]
  public var expiresAt: Date
  public var lastUsedAt: Date?
  public var createdAt: Date
  public var revokedAt: Date?

  public init(
    id: APIKeyID,
    name: String,
    hint: String,
    scopes: Set<APIKeyScope>,
    grants: [APIKeyGrant],
    expiresAt: Date,
    lastUsedAt: Date?,
    createdAt: Date,
    revokedAt: Date?
  ) {
    self.id = id
    self.name = name
    self.hint = hint
    self.scopes = scopes
    self.grants = grants
    self.expiresAt = expiresAt
    self.lastUsedAt = lastUsedAt
    self.createdAt = createdAt
    self.revokedAt = revokedAt
  }
}

public struct APIKeyDraft: Hashable, Sendable {
  public var name: String
  public var scopes: Set<APIKeyScope>
  public var grants: [APIKeyGrant]
  public var expiresAt: Date

  public init(name: String, scopes: Set<APIKeyScope>, grants: [APIKeyGrant], expiresAt: Date) {
    self.name = name
    self.scopes = scopes
    self.grants = grants
    self.expiresAt = expiresAt
  }

  public static let demo = APIKeyDraft(
    name: "Painel financeiro",
    scopes: [.profileRead, .billingsRead],
    grants: [APIKeyGrant(resourceType: .user, resourceID: .personal)],
    expiresAt: Date(timeIntervalSince1970: 1_798_761_600)
  )
}

public struct CreatedAPIKeySecret: Hashable, Sendable {
  public let metadata: APIKeyMetadata
  public let secret: String

  public init(metadata: APIKeyMetadata, secret: String) {
    self.metadata = metadata
    self.secret = secret
  }
}

public enum ThemeFont: String, CaseIterable, Codable, Sendable {
  case montserrat = "Montserrat"
  case roboto = "Roboto"
  case lora = "Lora"
  case playfairDisplay = "Playfair Display"
  case openSans = "Open Sans"
  case sourceSans3 = "Source Sans 3"
  case merriweather = "Merriweather"
  case raleway = "Raleway"
  case oswald = "Oswald"
  case nunito = "Nunito"
}

public struct ThemeValues: Hashable, Codable, Sendable {
  public var headerFont: ThemeFont
  public var textFont: ThemeFont
  public var primary: String
  public var primaryLight: String
  public var secondary: String
  public var secondaryDark: String
  public var textColor: String
  public var textContrast: String

  public init(
    headerFont: ThemeFont,
    textFont: ThemeFont,
    primary: String,
    primaryLight: String,
    secondary: String,
    secondaryDark: String,
    textColor: String,
    textContrast: String
  ) {
    self.headerFont = headerFont
    self.textFont = textFont
    self.primary = primary
    self.primaryLight = primaryLight
    self.secondary = secondary
    self.secondaryDark = secondaryDark
    self.textColor = textColor
    self.textContrast = textContrast
  }

  public static let rentivo = ThemeValues(
    headerFont: .montserrat, textFont: .openSans,
    primary: "#07875F", primaryLight: "#DDF6EC",
    secondary: "#252635", secondaryDark: "#171822",
    textColor: "#252635", textContrast: "#FFFFFF"
  )

  public static let sunset = ThemeValues(
    headerFont: .playfairDisplay, textFont: .lora,
    primary: "#C95A3D", primaryLight: "#FAE5DF",
    secondary: "#47324A", secondaryDark: "#2B1D2D",
    textColor: "#2B1D2D", textContrast: "#FFFFFF"
  )
}

public enum ThemeSource: String, CaseIterable, Codable, Sendable {
  case billing
  case organization
  case user
  case `default`
}

public enum ThemeTarget: Hashable, Sendable {
  case user
  case organization(OrganizationID)
  case billing(BillingID)
}

public struct ThemeRecord: Hashable, Sendable {
  public var ownerName: String
  public var stored: ThemeValues?
  public var effective: ThemeValues
  public var effectiveSource: ThemeSource
  public var canEdit: Bool
  public var canReset: Bool

  public init(
    ownerName: String,
    stored: ThemeValues?,
    effective: ThemeValues,
    effectiveSource: ThemeSource,
    canEdit: Bool,
    canReset: Bool
  ) {
    self.ownerName = ownerName
    self.stored = stored
    self.effective = effective
    self.effectiveSource = effectiveSource
    self.canEdit = canEdit
    self.canReset = canReset
  }
}
