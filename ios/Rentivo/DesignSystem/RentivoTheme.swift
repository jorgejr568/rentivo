import SwiftUI

enum RentivoColors {
  static let paper = Color(red: 0.97, green: 0.95, blue: 0.90)
  static let surface = Color(red: 1.00, green: 0.99, blue: 0.96)
  static let ink = Color(red: 0.12, green: 0.12, blue: 0.18)
  static let secondaryInk = Color(red: 0.34, green: 0.34, blue: 0.40)
  static let emerald = Color(red: 0.03, green: 0.53, blue: 0.37)
  static let emeraldLight = Color(red: 0.87, green: 0.96, blue: 0.93)
  static let amber = Color(red: 0.93, green: 0.62, blue: 0.16)
  static let coral = Color(red: 0.83, green: 0.31, blue: 0.25)
  static let blue = Color(red: 0.17, green: 0.42, blue: 0.76)
  static let lilac = Color(red: 0.49, green: 0.38, blue: 0.72)
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
