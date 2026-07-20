import SwiftUI

struct DemoScenariosView: View {
  @Environment(AppModel.self) private var app
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
        settingButton(
          title: "Atraso de 350 ms",
          enabled: app.demoSettings.delayEnabled,
          identifier: "demo.delay-mode"
        ) {
          app.setDelayEnabled(!app.demoSettings.delayEnabled)
        }
        settingButton(
          title: "Conteúdo vazio",
          enabled: app.demoSettings.emptyMode,
          identifier: "demo.empty-mode"
        ) {
          app.setEmptyMode(!app.demoSettings.emptyMode)
        }
        settingButton(
          title: "Permissões de visualizador",
          enabled: app.demoSettings.viewerMode,
          identifier: "demo.viewer-mode"
        ) {
          app.setViewerMode(!app.demoSettings.viewerMode)
        }
      }
      Section("Falhas recuperáveis") {
        Button {
          app.failNextOperation()
          app.showNotice("A próxima operação falhará de forma controlada.", kind: .information)
        } label: {
          Label(
            "Falhar a próxima operação", systemImage: "exclamationmark.arrow.triangle.2.circlepath")
        }
        .accessibilityIdentifier("demo.fail-next")
      }
      Section("Dados canônicos") {
        Button("Restaurar toda a demonstração", role: .destructive) {
          confirmingReset = true
        }
        .accessibilityIdentifier("demo.reset")
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
    app.resetDemo()
    app.showNotice("Demonstração restaurada.")
  }

  private func settingButton(
    title: String,
    enabled: Bool,
    identifier: String,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack {
        Text(title)
        Spacer()
        Label(
          enabled ? "Ativo" : "Inativo",
          systemImage: enabled ? "checkmark.circle.fill" : "circle"
        )
        .foregroundStyle(enabled ? RentivoColors.emerald : RentivoColors.secondaryInk)
      }
    }
    .foregroundStyle(RentivoColors.ink)
    .accessibilityIdentifier(identifier)
    .accessibilityValue(enabled ? "Ativo" : "Inativo")
  }
}
