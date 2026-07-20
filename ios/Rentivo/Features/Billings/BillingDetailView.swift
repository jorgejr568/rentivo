import SwiftUI

private struct BillingDetailData: Sendable {
  let billing: Billing
  let bills: [Bill]
  let expenses: [Expense]
}

struct BillingDetailView: View {
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  let billingID: UUID
  let onMutation: () async -> Void

  @State private var state: LoadState<BillingDetailData> = .idle
  @State private var showingEdit = false
  @State private var confirmingDelete = false

  var body: some View {
    PageStateView(state: state) { data in
      detail(data)
    } retry: {
      await load()
    }
    .background(RentivoColors.paper)
    .navigationTitle("Detalhes")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        if state.value?.billing.capabilities.canEdit == true {
          Button("Editar") { showingEdit = true }
        }
      }
    }
    .sheet(isPresented: $showingEdit) {
      if let billing = state.value?.billing {
        NavigationStack {
          BillingFormView(billing: billing) {
            await load()
            await onMutation()
          }
        }
      }
    }
    .confirmationDialog(
      "Excluir esta cobrança?",
      isPresented: $confirmingDelete,
      titleVisibility: .visible
    ) {
      Button("Excluir cobrança", role: .destructive) {
        Task { await deleteBilling() }
      }
      Button("Cancelar", role: .cancel) {}
    } message: {
      Text("Faturas, despesas e arquivos locais desta demonstração também serão removidos.")
    }
    .task { await load() }
  }

  private func detail(_ data: BillingDetailData) -> some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: RentivoSpacing.section) {
        RentivoCard {
          VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
            Text(data.billing.name)
              .font(RentivoTypography.title)
            Text(data.billing.description)
              .foregroundStyle(RentivoColors.secondaryInk)
            Label(data.billing.owner.name, systemImage: "person.crop.square")
              .font(.subheadline.weight(.semibold))
            HStack {
              Label(
                data.billing.pixOverride?.isComplete == true ? "PIX próprio" : "PIX herdado",
                systemImage: "qrcode"
              )
              Spacer()
              MoneyText(money: data.billing.fixedSubtotal)
            }
          }
        }

        lineItems(data.billing.items)
        bills(data.bills)
        financialSummary(data)
        recipients(data.billing)

        if data.billing.capabilities.canDelete {
          Button(role: .destructive) {
            confirmingDelete = true
          } label: {
            Label("Excluir cobrança", systemImage: "trash")
              .frame(maxWidth: .infinity)
          }
          .buttonStyle(.bordered)
        } else {
          Label(
            "Seu perfil pode consultar, mas não alterar esta cobrança.",
            systemImage: "eye.fill"
          )
          .font(.footnote.weight(.semibold))
          .foregroundStyle(RentivoColors.secondaryInk)
        }
      }
      .padding(RentivoSpacing.page)
    }
  }

  private func lineItems(_ items: [BillingItem]) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Itens recorrentes", symbol: "list.bullet.rectangle")
      RentivoCard {
        VStack(spacing: RentivoSpacing.medium) {
          ForEach(items) { item in
            HStack {
              VStack(alignment: .leading, spacing: RentivoSpacing.tiny) {
                Text(item.description)
                  .font(.subheadline.weight(.semibold))
                Text(item.type.label)
                  .font(.caption)
                  .foregroundStyle(RentivoColors.secondaryInk)
              }
              Spacer()
              MoneyText(money: item.amount)
            }
            if item.id != items.last?.id { Divider() }
          }
        }
      }
    }
  }

  private func bills(_ bills: [Bill]) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Faturas", symbol: "doc.text.fill")
      if bills.isEmpty {
        Text("Nenhuma fatura foi gerada para esta cobrança.")
          .foregroundStyle(RentivoColors.secondaryInk)
      } else {
        ForEach(bills) { bill in
          RentivoCard {
            HStack {
              VStack(alignment: .leading, spacing: RentivoSpacing.small) {
                Text(bill.referenceMonth.label.capitalized)
                  .font(.headline)
                StatusBadge(status: bill.status)
              }
              Spacer()
              VStack(alignment: .trailing, spacing: RentivoSpacing.small) {
                MoneyText(money: bill.total)
                Text("Vence \(bill.dueDate.iso8601)")
                  .font(.caption)
                  .foregroundStyle(RentivoColors.secondaryInk)
              }
            }
          }
        }
      }
    }
  }

  private func financialSummary(_ data: BillingDetailData) -> some View {
    let paid = data.bills.filter { $0.status == .paid }.map(\.total).reduce(.zero, +)
    let expenses = data.expenses.map(\.amount).reduce(.zero, +)
    return VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Resumo financeiro", symbol: "chart.bar.fill")
      RentivoCard {
        VStack(spacing: RentivoSpacing.medium) {
          valueRow("Recebido", paid, RentivoColors.emerald)
          Divider()
          valueRow("Despesas", expenses, RentivoColors.coral)
          Divider()
          valueRow("Resultado", paid - expenses, RentivoColors.blue)
        }
      }
    }
  }

  private func valueRow(_ label: String, _ money: Money, _ color: Color) -> some View {
    HStack {
      Text(label).font(.subheadline.weight(.semibold))
      Spacer()
      MoneyText(money: money, color: color)
    }
  }

  private func recipients(_ billing: Billing) -> some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      SectionTitle(title: "Destinatários", symbol: "envelope.fill")
      RentivoCard {
        VStack(alignment: .leading, spacing: RentivoSpacing.small) {
          ForEach(billing.recipients) { recipient in
            Text(recipient.name).font(.subheadline.weight(.semibold))
            Text(recipient.email)
              .font(.caption)
              .foregroundStyle(RentivoColors.secondaryInk)
          }
          if let replyTo = billing.replyTo {
            Divider()
            Label("Respostas para \(replyTo)", systemImage: "arrowshape.turn.up.left")
              .font(.caption)
          }
        }
      }
    }
  }

  private func load() async {
    state = .loading
    do {
      let data = BillingDetailData(
        billing: try await app.store.billing(id: billingID),
        bills: try await app.store.listBills(billingID: billingID),
        expenses: try await app.store.listExpenses(billingID: billingID)
      )
      state = .loaded(data)
    } catch {
      state = .failed(DemoError(error))
    }
  }

  private func deleteBilling() async {
    do {
      try await app.store.deleteBilling(id: billingID)
      await onMutation()
      app.showNotice("Cobrança excluída da demonstração.")
      dismiss()
    } catch {
      app.showNotice(DemoError(error).message, kind: .warning)
    }
  }
}
