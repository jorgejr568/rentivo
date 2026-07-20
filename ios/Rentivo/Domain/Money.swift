import Foundation

public struct Money: Hashable, Codable, Sendable, Comparable {
  public let centavos: Int

  public init(centavos: Int) {
    self.centavos = centavos
  }

  public static let zero = Money(centavos: 0)

  public static func + (lhs: Money, rhs: Money) -> Money {
    Money(centavos: lhs.centavos + rhs.centavos)
  }

  public static func - (lhs: Money, rhs: Money) -> Money {
    Money(centavos: lhs.centavos - rhs.centavos)
  }

  public static func < (lhs: Money, rhs: Money) -> Bool {
    lhs.centavos < rhs.centavos
  }

  public func formatted(locale: Locale = Locale(identifier: "pt_BR")) -> String {
    let formatter = NumberFormatter()
    formatter.locale = locale
    formatter.numberStyle = .currency
    formatter.currencyCode = "BRL"
    formatter.minimumFractionDigits = 2
    formatter.maximumFractionDigits = 2
    let decimal = Decimal(centavos) / Decimal(100)
    return formatter.string(from: NSDecimalNumber(decimal: decimal)) ?? "R$ 0,00"
  }
}
