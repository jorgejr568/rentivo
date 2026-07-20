import SwiftUI

private enum BillingOwnerFilter: String, CaseIterable, Identifiable {
  case all = "Todas"
  case personal = "Pessoais"
  case organization = "Organizações"

  var id: Self { self }
}

private struct BillingPortfolioItem: Identifiable, Sendable {
  let billing: Billing
  let bills: [Bill]
  var id: UUID { billing.id }
}

struct BillingListView: View {
  @Environment(AppModel.self) private var app
  @State private var state: LoadState<[BillingPortfolioItem]> = .idle
  @State private var searchText = ""
  @State private var ownerFilter: BillingOwnerFilter = .all
  @State private var showingCreate = false

  var body: some View {
    PageStateView(state: state) { items in
      portfolio(items)
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Cobranças")
    .searchable(text: $searchText, prompt: "Buscar por nome ou responsável")
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        if !app.demoSettings.viewerMode {
          Button {
            showingCreate = true
          } label: {
            Label("Nova cobrança", systemImage: "plus")
          }
          .accessibilityIdentifier("billing.create")
        }
      }
    }
    .sheet(isPresented: $showingCreate) {
      NavigationStack {
        BillingFormView { await load() }
      }
    }
    .navigationDestination(for: UUID.self) { id in
      BillingDetailView(billingID: id) { await load() }
    }
    .task(id: app.dataRevision) { await load() }
    .refreshable { await load() }
  }

  private func portfolio(_ items: [BillingPortfolioItem]) -> some View {
    let filtered = filteredItems(items)
    return ScrollView {
      LazyVStack(spacing: RentivoSpacing.large) {
        Picker("Responsável", selection: $ownerFilter) {
          ForEach(BillingOwnerFilter.allCases) { filter in
            Text(filter.rawValue).tag(filter)
          }
        }
        .pickerStyle(.segmented)

        if filtered.isEmpty {
          ContentUnavailableView.search(text: searchText)
            .padding(.top, RentivoSpacing.section)
        } else {
          ForEach(filtered) { item in
            NavigationLink(value: item.id) {
              BillingPortfolioCard(item: item)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("billing.card.\(item.id.uuidString)")
          }
        }
      }
      .padding(RentivoSpacing.page)
    }
  }

  private func filteredItems(_ items: [BillingPortfolioItem]) -> [BillingPortfolioItem] {
    items.filter { item in
      let matchesOwner: Bool
      switch ownerFilter {
      case .all: matchesOwner = true
      case .personal: matchesOwner = !item.billing.owner.isOrganization
      case .organization: matchesOwner = item.billing.owner.isOrganization
      }
      let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
      let matchesSearch =
        query.isEmpty
        || item.billing.name.localizedCaseInsensitiveContains(query)
        || item.billing.description.localizedCaseInsensitiveContains(query)
        || item.billing.owner.name.localizedCaseInsensitiveContains(query)
      return matchesOwner && matchesSearch
    }
  }

  private func load() async {
    state = .loading
    do {
      let billings = try await app.dependencies.billings.listBillings()
      var items: [BillingPortfolioItem] = []
      for billing in billings {
        items.append(
          BillingPortfolioItem(
            billing: billing,
            bills: try await app.dependencies.bills.listBills(billingID: billing.id)
          )
        )
      }
      state = items.isEmpty ? .empty : .loaded(items)
    } catch {
      state = .failed(DemoError(error))
    }
  }
}

private struct BillingPortfolioCard: View {
  let item: BillingPortfolioItem

  var body: some View {
    RentivoCard {
      VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
        HStack(alignment: .top) {
          VStack(alignment: .leading, spacing: RentivoSpacing.tiny) {
            Text(item.billing.name)
              .font(RentivoTypography.cardTitle)
              .foregroundStyle(RentivoColors.ink)
              .multilineTextAlignment(.leading)
            Label(item.billing.owner.name, systemImage: ownerSymbol)
              .font(.caption.weight(.semibold))
              .foregroundStyle(RentivoColors.secondaryInk)
          }
          Spacer()
          Image(systemName: "chevron.right")
            .foregroundStyle(RentivoColors.secondaryInk)
        }
        Text(item.billing.description)
          .font(.subheadline)
          .foregroundStyle(RentivoColors.secondaryInk)
          .lineLimit(2)
        HStack {
          VStack(alignment: .leading, spacing: RentivoSpacing.tiny) {
            Text("Subtotal fixo")
              .font(.caption)
              .foregroundStyle(RentivoColors.secondaryInk)
            MoneyText(money: item.billing.fixedSubtotal)
          }
          Spacer()
          VStack(alignment: .trailing, spacing: RentivoSpacing.tiny) {
            Label("\(item.bills.count) faturas", systemImage: "doc.text")
            Label(pixLabel, systemImage: pixSymbol)
          }
          .font(.caption.weight(.semibold))
          .foregroundStyle(RentivoColors.secondaryInk)
        }
        if let status = item.bills.first?.status {
          StatusBadge(status: status)
        }
      }
    }
  }

  private var ownerSymbol: String {
    item.billing.owner.isOrganization ? "building.2" : "person"
  }

  private var pixLabel: String {
    item.billing.pixOverride?.isComplete == true ? "PIX próprio" : "PIX herdado"
  }

  private var pixSymbol: String {
    item.billing.pixOverride?.isComplete == true ? "qrcode" : "arrow.triangle.branch"
  }
}
