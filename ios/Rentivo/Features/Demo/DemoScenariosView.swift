import SwiftUI

struct DemoScenariosView: View {
  @Environment(AppModel.self) private var app
  @State private var delayEnabled = false
  @State private var emptyMode = false
  @State private var viewerMode = false
  @State private var confirmingReset = false

  var body: some View {
    Form {
      Section {
        Label(
          "Estas opções alteram apenas o repositório em memória e serão removidas da navegação de produção.",
          systemImage: "hammer.fill"
        )
        .font(.footnote)
      }
      Section("Estados de leitura") {
        Toggle("Atraso de 350 ms", isOn: $delayEnabled)
          .onChange(of: delayEnabled) { _, value in app.store.setDelayEnabled(value) }
        Toggle("Conteúdo vazio", isOn: $emptyMode)
          .onChange(of: emptyMode) { _, value in app.store.setEmptyMode(value) }
        Toggle("Permissões de visualizador", isOn: $viewerMode)
          .onChange(of: viewerMode) { _, value in app.store.setViewerMode(value) }
      }
      Section("Falhas recuperáveis") {
        Button {
          app.store.failNextOperation()
          app.showNotice("A próxima operação falhará de forma controlada.", kind: .information)
        } label: {
          Label(
            "Falhar a próxima operação", systemImage: "exclamationmark.arrow.triangle.2.circlepath")
        }
      }
      Section("Dados canônicos") {
        Button("Restaurar toda a demonstração", role: .destructive) {
          confirmingReset = true
        }
      }
    }
    .navigationTitle("Cenários")
    .confirmationDialog("Restaurar todos os dados?", isPresented: $confirmingReset) {
      Button("Restaurar", role: .destructive) { reset() }
      Button("Cancelar", role: .cancel) {}
    } message: {
      Text("Cobranças, faturas, despesas, organizações e configurações voltarão ao estado inicial.")
    }
  }

  private func reset() {
    app.store.reset()
    delayEnabled = false
    emptyMode = false
    viewerMode = false
    app.showNotice("Demonstração restaurada.")
  }
}
