import SwiftUI
import UIKit

extension Color {
  /// Builds a color that adapts to the system appearance via a dynamic `UIColor`
  /// provider, so every consumer (backgrounds, text, borders, tints) automatically
  /// tracks light/dark mode without extra call-site logic.
  ///
  /// Components expressed as 0...1 sRGB triples, matching the existing
  /// `Color(red:green:blue:)` literals this design system already used.
  init(light: (Double, Double, Double), dark: (Double, Double, Double)) {
    self.init(
      uiColor: UIColor { traitCollection in
        let rgb = traitCollection.userInterfaceStyle == .dark ? dark : light
        return UIColor(red: rgb.0, green: rgb.1, blue: rgb.2, alpha: 1)
      }
    )
  }
}

/// Semantic color tokens for the app. Every color is adaptive (light + dark variant)
/// so screens built on system `Form`/`List` backgrounds stay legible in both
/// appearances. Accent hues (`emerald`, `amber`, `coral`, `blue`, `lilac`) are tuned so
/// that, used as-is, they meet WCAG AA (>=4.5:1) as foreground text/icon color against
/// both `paper` and `surface` in their own mode, AND against their own 14%-opacity tint
/// (the pattern `StatusBadge` uses) — see the design-system report for the exact
/// contrast ratios verified for this palette.
enum RentivoColors {
  static let paper = Color(light: (0.97, 0.95, 0.90), dark: (0.07, 0.075, 0.09))
  static let surface = Color(light: (1.00, 0.99, 0.96), dark: (0.145, 0.155, 0.185))
  static let ink = Color(light: (0.12, 0.12, 0.18), dark: (0.93, 0.94, 0.96))
  static let secondaryInk = Color(light: (0.34, 0.34, 0.40), dark: (0.72, 0.735, 0.78))

  static let emerald = Color(light: (0.026, 0.456, 0.318), dark: (0.208, 0.782, 0.584))
  static let emeraldLight = Color(light: (0.87, 0.96, 0.93), dark: (0.10, 0.16, 0.14))
  static let amber = Color(light: (0.539, 0.36, 0.093), dark: (0.98, 0.723, 0.327))
  static let coral = Color(light: (0.681, 0.254, 0.205), dark: (0.972, 0.494, 0.448))
  static let blue = Color(light: (0.16, 0.395, 0.714), dark: (0.456, 0.653, 0.97))
  static let lilac = Color(light: (0.446, 0.346, 0.655), dark: (0.743, 0.604, 0.941))
}

enum RentivoSpacing {
  static let tiny: CGFloat = 4
  static let small: CGFloat = 8
  static let medium: CGFloat = 12
  static let large: CGFloat = 20
  static let page: CGFloat = 24
  static let section: CGFloat = 32
}

enum RentivoTypography {
  static let display = Font.system(.largeTitle, design: .rounded, weight: .black)
  static let title = Font.system(.title2, design: .rounded, weight: .bold)
  static let cardTitle = Font.system(.headline, design: .rounded, weight: .bold)
  static let metadata = Font.system(.caption, design: .rounded, weight: .semibold)
  static let money = Font.system(.title3, design: .monospaced, weight: .bold)
}

extension View {
  func rentivoPage() -> some View {
    frame(maxWidth: .infinity, maxHeight: .infinity)
      .background(RentivoColors.paper)
  }
}

/// Formats a PT-BR count string with correct singular/plural noun agreement, e.g.
/// `ptBRCount(1, singular: "fatura", plural: "faturas")` -> "1 fatura" and
/// `ptBRCount(3, singular: "fatura", plural: "faturas")` -> "3 faturas".
func ptBRCount(_ count: Int, singular: String, plural: String) -> String {
  "\(count) \(count == 1 ? singular : plural)"
}
