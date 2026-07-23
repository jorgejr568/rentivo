import SwiftUI
import UIKit

struct RentivoCard<Content: View>: View {
  private let content: Content

  init(@ViewBuilder content: () -> Content) {
    self.content = content()
  }

  var body: some View {
    content
      .padding(RentivoSpacing.large)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(RentivoColors.surface)
      .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
      .overlay {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
          .stroke(RentivoColors.ink, lineWidth: 2)
      }
      .shadow(color: RentivoColors.ink, radius: 0, x: 4, y: 4)
      .padding(.trailing, 4)
      .padding(.bottom, 4)
  }
}

struct RentivoButtonStyle: ButtonStyle {
  var color = RentivoColors.emerald

  /// Buttons render as a solid, saturated fill with a white label. Some accent tones
  /// are intentionally brightened in dark mode so they stay legible as body text/icons
  /// elsewhere in the app, but that same brightness fails contrast against a white
  /// label. Resolving the fill against a forced light trait collection keeps every
  /// solid button legible (white text stays >=4.5:1) in both appearances — see the
  /// design-system report for the verified ratios.
  private var fill: Color {
    Color(
      uiColor: UIColor(color).resolvedColor(
        with: UITraitCollection(userInterfaceStyle: .light)
      )
    )
  }

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.headline.weight(.bold))
      .foregroundStyle(Color.white)
      .frame(maxWidth: .infinity, minHeight: 48)
      .padding(.horizontal, RentivoSpacing.medium)
      .background(configuration.isPressed ? fill.opacity(0.75) : fill)
      .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
      .overlay {
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .stroke(RentivoColors.ink, lineWidth: 2)
      }
      .shadow(
        color: configuration.isPressed ? .clear : RentivoColors.ink,
        radius: 0,
        x: 3,
        y: 3
      )
      .offset(x: configuration.isPressed ? 3 : 0, y: configuration.isPressed ? 3 : 0)
      .animation(.easeOut(duration: 0.08), value: configuration.isPressed)
  }
}

struct BrandMark: View {
  var compact: Bool

  // Two independent scaled metrics (rather than one derived from `compact`) so each
  // size class tracks Dynamic Type against a text style of comparable weight.
  @ScaledMetric(relativeTo: .title) private var compactGlyphSize: CGFloat = 20
  @ScaledMetric(relativeTo: .largeTitle) private var fullGlyphSize: CGFloat = 30
  @ScaledMetric(relativeTo: .title) private var compactBoxSize: CGFloat = 34
  @ScaledMetric(relativeTo: .largeTitle) private var fullBoxSize: CGFloat = 48

  // Explicit init: a struct's synthesized memberwise initializer takes the access
  // level of its most-restrictive stored property, so the `private` @ScaledMetric
  // properties above would otherwise make the implicit init `private` too and break
  // existing cross-file call sites like `BrandMark(compact: true)`.
  init(compact: Bool = false) {
    self.compact = compact
  }

  private var glyphSize: CGFloat { compact ? compactGlyphSize : fullGlyphSize }
  private var boxSize: CGFloat { compact ? compactBoxSize : fullBoxSize }
  private var cornerRadius: CGFloat { compact ? 9 : 13 }

  var body: some View {
    HStack(spacing: RentivoSpacing.small) {
      Text("R")
        .font(.system(size: glyphSize, weight: .black, design: .rounded))
        .foregroundStyle(Color.white)
        .frame(width: boxSize, height: boxSize)
        .background(RentivoColors.emerald)
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
        .overlay {
          RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            .stroke(RentivoColors.ink, lineWidth: 2)
        }
      if !compact {
        Text("rentivo")
          .font(.system(.largeTitle, design: .rounded, weight: .black))
          .foregroundStyle(RentivoColors.ink)
      }
    }
    .accessibilityElement(children: .ignore)
    .accessibilityLabel("Rentivo")
  }
}

struct StatusBadge: View {
  let status: BillStatus

  private var color: Color {
    switch status {
    case .draft: RentivoColors.secondaryInk
    case .published: RentivoColors.lilac
    case .sent: RentivoColors.blue
    case .paid: RentivoColors.emerald
    case .cancelled: RentivoColors.coral
    case .delayedPayment: RentivoColors.amber
    }
  }

  var body: some View {
    Text(status.label)
      .font(RentivoTypography.metadata)
      .foregroundStyle(color)
      .padding(.horizontal, 10)
      .padding(.vertical, 6)
      .background(color.opacity(0.14))
      .clipShape(Capsule())
      .overlay { Capsule().stroke(color, lineWidth: 1.5) }
      .accessibilityLabel("Status: \(status.label)")
  }
}

struct MoneyText: View {
  let money: Money
  var color: Color = RentivoColors.ink
  var font: Font = RentivoTypography.money
  var minimumScaleFactor: CGFloat = 1
  var lineLimit: Int? = nil
  /// Overrides the default "Valor: <amount>" accessibility label, e.g. for a card that
  /// wants "Recebido: R$ 1.200,00" instead.
  var accessibilityLabelOverride: String? = nil

  var body: some View {
    Text(money.formatted())
      .font(font)
      .foregroundStyle(color)
      .monospacedDigit()
      .minimumScaleFactor(minimumScaleFactor)
      .lineLimit(lineLimit)
      .accessibilityLabel(accessibilityLabelOverride ?? "Valor: \(money.formatted())")
  }
}

struct PageStateView<Value: Sendable, Content: View>: View {
  let state: LoadState<Value>
  let content: (Value) -> Content
  let retry: () async -> Void
  var emptyTitle: String
  var emptyMessage: String
  var emptySystemImage: String
  var emptyActionTitle: String?
  var emptyAction: (() -> Void)?

  init(
    state: LoadState<Value>,
    emptyTitle: String = "Nada por aqui ainda",
    emptyMessage: String = "Crie o primeiro item para começar.",
    emptySystemImage: String = "sparkles",
    emptyActionTitle: String? = nil,
    emptyAction: (() -> Void)? = nil,
    @ViewBuilder content: @escaping (Value) -> Content,
    retry: @escaping () async -> Void
  ) {
    self.state = state
    self.emptyTitle = emptyTitle
    self.emptyMessage = emptyMessage
    self.emptySystemImage = emptySystemImage
    self.emptyActionTitle = emptyActionTitle
    self.emptyAction = emptyAction
    self.content = content
    self.retry = retry
  }

  var body: some View {
    switch state {
    case .idle, .loading:
      ProgressView("Carregando…")
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityIdentifier("page.loading")
    case .loaded(let value):
      content(value)
    case .empty:
      ContentUnavailableView {
        Label(emptyTitle, systemImage: emptySystemImage)
      } description: {
        Text(emptyMessage)
      } actions: {
        if let emptyActionTitle, let emptyAction {
          Button(emptyActionTitle, action: emptyAction)
            .buttonStyle(.borderedProminent)
            .accessibilityIdentifier("page.empty.action")
        }
      }
      .accessibilityIdentifier("page.empty")
    case .failed(let error):
      ContentUnavailableView {
        Label("Não foi possível carregar", systemImage: "exclamationmark.triangle")
      } description: {
        Text(error.message)
      } actions: {
        Button("Tentar novamente") { Task { await retry() } }
          .buttonStyle(.borderedProminent)
          .accessibilityIdentifier("page.retry")
      }
      .accessibilityIdentifier("page.error")
    }
  }
}

struct NoticeBanner: View {
  let notice: AppNotice
  let dismiss: () -> Void

  var body: some View {
    HStack(spacing: RentivoSpacing.medium) {
      Image(systemName: symbol)
        .foregroundStyle(color)
      Text(notice.message)
        .font(.subheadline.weight(.semibold))
        .foregroundStyle(RentivoColors.ink)
        .frame(maxWidth: .infinity, alignment: .leading)
      Button(action: dismiss) {
        Image(systemName: "xmark")
      }
      .foregroundStyle(RentivoColors.ink)
      .accessibilityLabel("Fechar aviso")
    }
    .padding(RentivoSpacing.medium)
    .background(RentivoColors.surface)
    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    .overlay {
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .stroke(RentivoColors.ink, lineWidth: 2)
    }
    .shadow(color: RentivoColors.ink, radius: 0, x: 3, y: 3)
  }

  private var color: Color {
    switch notice.kind {
    case .success: RentivoColors.emerald
    case .information: RentivoColors.blue
    case .warning: RentivoColors.amber
    }
  }

  private var symbol: String {
    switch notice.kind {
    case .success: "checkmark.circle.fill"
    case .information: "info.circle.fill"
    case .warning: "exclamationmark.triangle.fill"
    }
  }
}

#Preview("RentivoCard") {
  RentivoCard {
    VStack(alignment: .leading, spacing: RentivoSpacing.small) {
      Text("Cobrança de Julho")
        .font(RentivoTypography.cardTitle)
      Text("Vence em 10/07/2026")
        .font(.subheadline)
        .foregroundStyle(RentivoColors.secondaryInk)
    }
  }
  .padding()
  .rentivoPage()
}

#Preview("RentivoButtonStyle") {
  VStack(spacing: RentivoSpacing.medium) {
    Button("Salvar cobrança") {}
      .buttonStyle(RentivoButtonStyle())
    Button("Ver detalhes") {}
      .buttonStyle(RentivoButtonStyle(color: RentivoColors.blue))
  }
  .padding()
  .rentivoPage()
}

#Preview("BrandMark") {
  VStack(spacing: RentivoSpacing.large) {
    BrandMark()
    BrandMark(compact: true)
  }
  .padding()
  .rentivoPage()
}

#Preview("BrandMark - Dynamic Type XXL") {
  VStack(spacing: RentivoSpacing.large) {
    BrandMark()
    BrandMark(compact: true)
  }
  .padding()
  .rentivoPage()
  .environment(\.sizeCategory, .accessibilityExtraExtraExtraLarge)
}

#Preview("StatusBadge") {
  VStack(alignment: .leading, spacing: RentivoSpacing.small) {
    ForEach(BillStatus.allCases, id: \.self) { status in
      StatusBadge(status: status)
    }
  }
  .padding()
  .rentivoPage()
}

#Preview("MoneyText") {
  VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
    MoneyText(money: Money(centavos: 245_000))
    MoneyText(money: Money(centavos: 18_900), color: RentivoColors.coral)
    MoneyText(
      money: Money(centavos: 120_000),
      color: RentivoColors.emerald,
      font: .system(.subheadline, design: .monospaced, weight: .bold),
      minimumScaleFactor: 0.7,
      lineLimit: 1
    )
  }
  .padding()
  .rentivoPage()
}

private struct PageStateViewPreviewContainer: View {
  let state: LoadState<String>

  var body: some View {
    PageStateView(state: state) { value in
      Text(value).padding()
    } retry: {}
  }
}

#Preview("PageStateView - loaded") {
  PageStateViewPreviewContainer(state: .loaded("Conteúdo carregado"))
}

#Preview("PageStateView - empty (default copy)") {
  PageStateViewPreviewContainer(state: .empty)
}

#Preview("PageStateView - empty (custom copy + action)") {
  PageStateView(
    state: LoadState<String>.empty,
    emptyTitle: "Nenhuma cobrança ainda",
    emptyMessage: "Crie a primeira cobrança recorrente para este imóvel.",
    emptySystemImage: "doc.text",
    emptyActionTitle: "Nova cobrança",
    emptyAction: {}
  ) { value in
    Text(value).padding()
  } retry: {}
}

#Preview("PageStateView - failed") {
  PageStateViewPreviewContainer(state: .failed(.operationFailed))
}

#Preview("NoticeBanner") {
  VStack(spacing: RentivoSpacing.medium) {
    NoticeBanner(notice: AppNotice(kind: .success, message: "Cobrança salva com sucesso."), dismiss: {})
    NoticeBanner(notice: AppNotice(kind: .information, message: "Sua sessão foi atualizada."), dismiss: {})
    NoticeBanner(notice: AppNotice(kind: .warning, message: "Não foi possível restaurar sua sessão."), dismiss: {})
  }
  .padding()
  .rentivoPage()
}
