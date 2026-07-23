import SwiftUI

/// A text field that edits an `Int` centavos value as pt-BR currency, e.g. typing
/// "245000" displays "R$ 2.450,00". The bound value is always parsed from the typed
/// digits into an `Int` — the field never touches `Double`/`Float` for the amount
/// itself (display formatting alone goes through `Money.formatted()`, which uses
/// `Decimal`, mirroring the rest of the app).
///
/// Replaces the ad hoc `TextField("Valor em centavos", value:, format: .number)`
/// pattern used across screens today, which forced users to type raw centavos.
struct CurrencyCentavosField: View {
  private let label: String
  @Binding private var centavos: Int
  @State private var text: String

  /// - Parameters:
  ///   - label: Visible placeholder and accessibility label for the field.
  ///   - centavos: The bound integer amount, in centavos.
  init(_ label: String, centavos: Binding<Int>) {
    self.label = label
    self._centavos = centavos
    self._text = State(initialValue: Self.format(centavos.wrappedValue))
  }

  var body: some View {
    TextField(label, text: $text)
      .keyboardType(.numberPad)
      .accessibilityLabel(label)
      .onChange(of: text) { _, newValue in
        let digits = newValue.filter(\.isNumber)
        let parsed = Int(digits) ?? 0
        if parsed != centavos {
          centavos = parsed
        }
        let formatted = Self.format(parsed)
        if formatted != text {
          text = formatted
        }
      }
      .onChange(of: centavos) { _, newValue in
        let formatted = Self.format(newValue)
        if formatted != text {
          text = formatted
        }
      }
  }

  private static func format(_ centavos: Int) -> String {
    Money(centavos: centavos).formatted()
  }
}

private struct CurrencyCentavosFieldPreviewContainer: View {
  @State private var centavos = 245_000

  var body: some View {
    Form {
      CurrencyCentavosField("Valor da parcela", centavos: $centavos)
      Text("Centavos armazenados: \(centavos)")
        .font(.caption)
        .foregroundStyle(RentivoColors.secondaryInk)
    }
  }
}

#Preview("CurrencyCentavosField") {
  CurrencyCentavosFieldPreviewContainer()
}
