import SwiftUI

private struct HomeData: Sendable {
  let summary: DashboardSummary
  let overdueBills: [Bill]
  let upcomingBills: [Bill]
  let billingNames: [BillingID: String]
  let activities: [RecentActivity]
  let hasBillings: Bool
}

struct HomeView: View {
  @Environment(AppModel.self) private var app
  @State private var state: LoadState<HomeData> = .idle

  var body: some View {
    PageStateView(state: state) { data in
      HomeContent(data: data)
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Início")
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        BrandMark(compact: true)
      }
    }
    .task(id: app.dataRevision) { await load() }
    .refreshable { await load() }
  }

  private func load() async {
    // Only blank the screen with a spinner when nothing has been shown yet
    // (first launch or a previously-failed load). Pull-to-refresh and every
    // tab revisit (`.task(id: app.dataRevision)`) otherwise refresh the
    // dashboard in place, keeping the current cards on screen.
    switch state {
    case .idle, .failed:
      state = .loading
    case .loading, .loaded, .empty:
      break
    }
    do {
      let summary = try await app.dependencies.dashboard.dashboardSummary()
      let billings = try await app.dependencies.billings.listBillings()
      var bills: [Bill] = []
      for billing in billings {
        bills.append(contentsOf: try await app.dependencies.bills.listBills(billingID: billing.id))
      }
      let names = Dictionary(uniqueKeysWithValues: billings.map { ($0.id, $0.name) })
      let upcomingStatuses: Set<BillStatus> = [.draft, .published, .sent]
      let data = HomeData(
        summary: summary,
        overdueBills: bills.filter { $0.status == .delayedPayment },
        upcomingBills: bills.filter { upcomingStatuses.contains($0.status) }.sorted {
          $0.dueDate < $1.dueDate
        },
        billingNames: names,
        activities: app.dependencies.activities.recentActivities,
        hasBillings: !billings.isEmpty
      )
      // The dashboard (summary cards, activity) is always meaningful, even
      // with zero billings — show it with zeroed cards plus an explainer
      // section rather than replacing the whole screen with a generic empty
      // state that has no create action on this screen.
      state = .loaded(data)
    } catch {
      if state.value != nil {
        app.showNotice(DemoError(error).message, kind: .warning)
      } else {
        state = .failed(DemoError(error))
      }
    }
  }
}

private struct HomeContent: View {
  @Environment(AppModel.self) private var app
  let data: HomeData

  private let columns = [
    GridItem(.flexible(), spacing: RentivoSpacing.medium),
    GridItem(.flexible(), spacing: RentivoSpacing.medium),
  ]

  var body: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: RentivoSpacing.section) {
        greeting
        LazyVGrid(columns: columns, spacing: RentivoSpacing.medium) {
          SummaryCard(
            title: "Recebido",
            value: data.summary.received,
            symbol: "arrow.down.circle.fill",
            color: RentivoColors.emerald
          )
          SummaryCard(
            title: "Despesas",
            value: data.summary.expenses,
            symbol: "arrow.up.circle.fill",
            color: RentivoColors.coral
          )
          SummaryCard(
            title: "Resultado",
            value: data.summary.netIncome,
            symbol: "chart.line.uptrend.xyaxis",
            color: RentivoColors.blue
          )
          CollectionCard(percent: data.summary.collectionRatePercent)
        }
        if data.hasBillings {
          if !data.overdueBills.isEmpty {
            overdueSection
          }
          quickActions
          if !data.upcomingBills.isEmpty {
            billsSection(
              title: "Próximas faturas",
              bills: Array(data.upcomingBills.prefix(4))
            )
          }
        } else {
          noBillingsSection
        }
        activitySection
      }
      .padding(RentivoSpacing.page)
    }
  }

  private var greeting: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.small) {
      Text("Olá!")
        .font(RentivoTypography.display)
        .foregroundStyle(RentivoColors.ink)
      Text(app.usesLiveAPI ? "Seu portfólio está conectado ao Rentivo." : "Seu portfólio está pronto para a demonstração.")
        .foregroundStyle(RentivoColors.secondaryInk)
      HStack {
        Label("Saldo em atraso", systemImage: "clock.badge.exclamationmark")
          .font(.caption.weight(.semibold))
        Spacer()
        MoneyText(money: data.summary.overdue, color: RentivoColors.coral)
      }
      .padding(.top, RentivoSpacing.small)
    }
  }

  private var overdueSection: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Atenção necessária", symbol: "exclamationmark.triangle.fill")
      RentivoCard {
        VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
          Text(
            "Há \(ptBRCount(data.overdueBills.count, singular: "fatura em acompanhamento", plural: "faturas em acompanhamento"))"
          )
          .font(RentivoTypography.cardTitle)
          Text("Abra Cobranças para registrar o pagamento ou cancelar a fatura.")
            .font(.subheadline)
            .foregroundStyle(RentivoColors.secondaryInk)
          Button("Ver cobranças") { app.selectedTab = .billings }
            .buttonStyle(.borderedProminent)
        }
      }
    }
  }

  private var quickActions: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Ações rápidas", symbol: "bolt.fill")
      Button {
        app.selectedTab = .billings
      } label: {
        // This action only switches to the Billings tab — it does not open a
        // create flow (that would require the Billings tab to observe a
        // cross-tab "present create sheet" signal, which lives outside the
        // files this fix owns). Naming it "Ver cobranças" keeps the label
        // honest about what actually happens.
        Label("Ver cobranças", systemImage: "list.bullet.rectangle.fill")
      }
      .buttonStyle(RentivoButtonStyle())
    }
  }

  private var noBillingsSection: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Comece por aqui", symbol: "sparkles")
      RentivoCard {
        VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
          Text("Nenhuma cobrança cadastrada ainda")
            .font(RentivoTypography.cardTitle)
          Text(
            "Crie sua primeira cobrança recorrente na aba Cobranças para começar a acompanhar recebimentos, despesas e faturas por aqui."
          )
          .font(.subheadline)
          .foregroundStyle(RentivoColors.secondaryInk)
          Button("Ver cobranças") { app.selectedTab = .billings }
            .buttonStyle(RentivoButtonStyle())
        }
      }
    }
  }

  private func billsSection(title: String, bills: [Bill]) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: title, symbol: "calendar")
      ForEach(bills) { bill in
        RentivoCard {
          VStack(alignment: .leading, spacing: RentivoSpacing.small) {
            HStack(alignment: .top) {
              VStack(alignment: .leading, spacing: RentivoSpacing.tiny) {
                Text(data.billingNames[bill.billingID] ?? "Cobrança")
                  .font(RentivoTypography.cardTitle)
                Text(bill.referenceMonth.label.capitalized)
                  .font(.subheadline)
                  .foregroundStyle(RentivoColors.secondaryInk)
              }
              Spacer()
              StatusBadge(status: bill.status)
            }
            HStack {
              Label("Vence em \(bill.dueDate.displayFormatted)", systemImage: "calendar")
                .font(.caption)
              Spacer()
              MoneyText(money: bill.effectiveTotal)
            }
          }
        }
      }
    }
  }

  private var activitySection: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Atividade recente", symbol: "clock.arrow.circlepath")
      if data.activities.isEmpty {
        Text(app.usesLiveAPI ? "Nenhuma atividade recente." : "As mudanças feitas na demonstração aparecerão aqui.")
          .foregroundStyle(RentivoColors.secondaryInk)
      } else {
        ForEach(data.activities.prefix(5)) { activity in
          HStack(alignment: .top, spacing: RentivoSpacing.medium) {
            Image(systemName: activity.kind.symbol)
              .foregroundStyle(RentivoColors.emerald)
              .frame(width: 24)
            VStack(alignment: .leading, spacing: RentivoSpacing.tiny) {
              Text(activity.title)
                .font(.subheadline.weight(.semibold))
              Text(activity.detail)
                .font(.caption)
                .foregroundStyle(RentivoColors.secondaryInk)
            }
            Spacer()
          }
          .padding(.vertical, RentivoSpacing.tiny)
        }
      }
    }
  }
}

private struct SummaryCard: View {
  let title: String
  let value: Money
  let symbol: String
  let color: Color

  var body: some View {
    RentivoCard {
      VStack(alignment: .leading, spacing: RentivoSpacing.small) {
        Image(systemName: symbol)
          .font(.title2)
          .foregroundStyle(color)
        Text(title)
          .font(.caption.weight(.semibold))
          .foregroundStyle(RentivoColors.secondaryInk)
        MoneyText(
          money: value,
          color: RentivoColors.ink,
          font: .system(.subheadline, design: .monospaced, weight: .bold),
          minimumScaleFactor: 0.7,
          lineLimit: 1,
          accessibilityLabelOverride: "\(title): \(value.formatted())"
        )
      }
    }
  }
}

private struct CollectionCard: View {
  let percent: Int

  var body: some View {
    RentivoCard {
      VStack(alignment: .leading, spacing: RentivoSpacing.small) {
        Image(systemName: "percent")
          .font(.title2)
          .foregroundStyle(RentivoColors.lilac)
        Text("Taxa de recebimento")
          .font(.caption.weight(.semibold))
          .foregroundStyle(RentivoColors.secondaryInk)
        Text("\(percent)%")
          .font(.system(.title3, design: .monospaced, weight: .bold))
          .foregroundStyle(RentivoColors.ink)
      }
    }
  }
}

struct SectionTitle: View {
  let title: String
  let symbol: String

  var body: some View {
    Label(title, systemImage: symbol)
      .font(RentivoTypography.title)
      .foregroundStyle(RentivoColors.ink)
  }
}

extension ActivityKind {
  fileprivate var symbol: String {
    switch self {
    case .billing: "house.fill"
    case .bill: "doc.text.fill"
    case .expense: "wrench.and.screwdriver.fill"
    case .organization: "building.2.fill"
    case .invitation: "envelope.fill"
    case .security: "lock.shield.fill"
    case .apiKey: "key.fill"
    case .theme: "paintpalette.fill"
    }
  }
}
