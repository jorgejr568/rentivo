import Foundation
import Testing

@testable import RentivoCore

@Test func moneyAddsCentavosWithoutFloatingPoint() {
    #expect(Money(centavos: 180_000) + Money(centavos: 65_000) == Money(centavos: 245_000))
}

@Test func moneySubtractsCentavosWithoutFloatingPoint() {
    #expect(Money(centavos: 180_000) - Money(centavos: 65_000) == Money(centavos: 115_000))
}

@Test func moneyFormatsBrazilianCurrency() {
    #expect(Money(centavos: 245_000).formatted(locale: Locale(identifier: "pt_BR")) == "R$ 2.450,00")
}

@Test func moneySortsByCentavos() {
    #expect(Money(centavos: -1) < .zero)
    #expect(Money.zero < Money(centavos: 1))
}
