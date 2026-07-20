import SwiftUI

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

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.headline.weight(.bold))
      .foregroundStyle(Color.white)
      .frame(maxWidth: .infinity, minHeight: 48)
      .padding(.horizontal, RentivoSpacing.medium)
      .background(configuration.isPressed ? color.opacity(0.75) : color)
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
  var compact = false

  var body: some View {
    HStack(spacing: RentivoSpacing.small) {
      Text("R")
        .font(.system(size: compact ? 20 : 30, weight: .black, design: .rounded))
        .foregroundStyle(Color.white)
        .frame(width: compact ? 34 : 48, height: compact ? 34 : 48)
        .background(RentivoColors.emerald)
        .clipShape(RoundedRectangle(cornerRadius: compact ? 9 : 13, style: .continuous))
        .overlay {
          RoundedRectangle(cornerRadius: compact ? 9 : 13, style: .continuous)
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
  var color = RentivoColors.ink

  var body: some View {
    Text(money.formatted())
      .font(RentivoTypography.money)
      .foregroundStyle(color)
      .monospacedDigit()
      .accessibilityLabel("Valor: \(money.formatted())")
  }
}

struct PageStateView<Value: Sendable, Content: View>: View {
  let state: LoadState<Value>
  let content: (Value) -> Content
  let retry: () async -> Void

  init(
    state: LoadState<Value>,
    @ViewBuilder content: @escaping (Value) -> Content,
    retry: @escaping () async -> Void
  ) {
    self.state = state
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
      ContentUnavailableView(
        "Nada por aqui ainda",
        systemImage: "sparkles",
        description: Text("Crie o primeiro item para começar.")
      )
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
