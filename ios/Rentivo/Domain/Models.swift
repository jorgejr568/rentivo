import Foundation

public enum LoadState<Value: Sendable>: Sendable {
  case idle
  case loading
  case loaded(Value)
  case empty
  case failed(DemoError)

  public var value: Value? {
    guard case .loaded(let value) = self else { return nil }
    return value
  }
}

public struct DemoError: Error, Equatable, LocalizedError, Sendable {
  public let message: String

  public init(message: String) {
    self.message = message
  }

  public init(_ error: any Error) {
    if let demoError = error as? DemoError {
      self = demoError
    } else {
      self.init(message: "Não foi possível concluir esta ação de demonstração.")
    }
  }

  public var errorDescription: String? { message }

  public static let operationFailed = DemoError(
    message: "Não foi possível concluir esta ação de demonstração."
  )
  public static let invalidBillTransition = DemoError(
    message: "Esta mudança de status não é permitida."
  )
  public static let resourceNotFound = DemoError(
    message: "O item solicitado não foi encontrado."
  )
  public static let permissionDenied = DemoError(
    message: "Seu perfil de demonstração não permite esta ação."
  )
}

public enum StableID {
  public static let userAna = 1
  public static let organizationHorizonte = OrganizationID(rawValue: "00000000-0000-0000-0000-000000000010")
  public static let billingAurora101 = BillingID(rawValue: "00000000-0000-0000-0000-000000000101")
  public static let billingAurora202 = BillingID(rawValue: "00000000-0000-0000-0000-000000000102")
  public static let billingSolNascente303 = BillingID(rawValue: "00000000-0000-0000-0000-000000000103")
  public static let billingVilaFlores1 = BillingID(rawValue: "00000000-0000-0000-0000-000000000104")
  public static let billingTorreNorte501 = BillingID(rawValue: "00000000-0000-0000-0000-000000000105")
  public static let billingCentro12 = BillingID(rawValue: "00000000-0000-0000-0000-000000000106")
  public static let billDraft = BillID(rawValue: "00000000-0000-0000-0000-000000001001")
  public static let billPublished = BillID(rawValue: "00000000-0000-0000-0000-000000001002")
  public static let billSent = BillID(rawValue: "00000000-0000-0000-0000-000000001003")
  public static let billPaid = BillID(rawValue: "00000000-0000-0000-0000-000000001004")
  public static let billCancelled = BillID(rawValue: "00000000-0000-0000-0000-000000001005")
  public static let billDelayed = BillID(rawValue: "00000000-0000-0000-0000-000000001006")
  public static let invitationHorizonte = InvitationID(rawValue: "00000000-0000-0000-0000-000000003001")
  public static let apiKeyDashboard = APIKeyID(rawValue: "00000000-0000-0000-0000-000000004001")
}

public struct DateOnly: Hashable, Codable, Sendable, Comparable {
  public let year: Int
  public let month: Int
  public let day: Int

  public init(year: Int, month: Int, day: Int) {
    precondition((1...12).contains(month), "Month must be between 1 and 12")
    precondition((1...31).contains(day), "Day must be between 1 and 31")
    self.year = year
    self.month = month
    self.day = day
  }

  public var iso8601: String {
    String(format: "%04d-%02d-%02d", year, month, day)
  }

  public static func < (lhs: DateOnly, rhs: DateOnly) -> Bool {
    (lhs.year, lhs.month, lhs.day) < (rhs.year, rhs.month, rhs.day)
  }
}

public struct ReferenceMonth: Hashable, Codable, Sendable, Comparable {
  public let year: Int
  public let month: Int

  public init(year: Int, month: Int) {
    precondition((1...12).contains(month), "Month must be between 1 and 12")
    self.year = year
    self.month = month
  }

  public var apiValue: String {
    String(format: "%04d-%02d", year, month)
  }

  public var label: String {
    let monthNames = [
      "janeiro", "fevereiro", "março", "abril", "maio", "junho",
      "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    return "\(monthNames[month - 1]) de \(year)"
  }

  public static func < (lhs: ReferenceMonth, rhs: ReferenceMonth) -> Bool {
    (lhs.year, lhs.month) < (rhs.year, rhs.month)
  }
}

public struct UserProfile: Hashable, Codable, Sendable {
  public let id: Int
  public var email: String
  public var pix: PixConfiguration?

  public init(id: Int, email: String, pix: PixConfiguration? = nil) {
    self.id = id
    self.email = email
    self.pix = pix
  }
}

public enum ActivityKind: String, Codable, Sendable {
  case billing
  case bill
  case expense
  case organization
  case invitation
  case security
  case apiKey = "api_key"
  case theme
}

public struct RecentActivity: Identifiable, Hashable, Codable, Sendable {
  public let id: UUID
  public let kind: ActivityKind
  public let title: String
  public let detail: String
  public let occurredAt: Date

  public init(id: UUID, kind: ActivityKind, title: String, detail: String, occurredAt: Date) {
    self.id = id
    self.kind = kind
    self.title = title
    self.detail = detail
    self.occurredAt = occurredAt
  }
}
