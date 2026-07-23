import SwiftUI

struct ThemeEditorView: View {
  @Environment(AppModel.self) private var app
  let target: ThemeTarget
  @State private var record: ThemeRecord?
  @State private var values = ThemeValues.rentivo
  @State private var loadedValues: ThemeValues?
  @State private var error: DemoError?

  /// True once the user has changed a field since the last successful load/save.
  /// Guards against `.task(id:)` reloads (triggered by unrelated `app.dataRevision`
  /// bumps) silently overwriting in-progress, unsaved color edits.
  private var isDirty: Bool {
    guard let loadedValues else { return false }
    return values != loadedValues
  }

  var body: some View {
    Form {
      if let record {
        Section("Herança") {
          LabeledContent("Responsável", value: record.ownerName)
          LabeledContent("Origem efetiva", value: record.effectiveSource.label)
            .accessibilityIdentifier("theme.source")
          if record.stored == nil {
            Label(
              "Este nível herda o tema de \(record.effectiveSource.label.lowercased()).",
              systemImage: "arrow.triangle.branch"
            )
            .font(.footnote)
          }
        }
      }

      Section("Tipografia") {
        Picker("Fonte de títulos", selection: $values.headerFont) {
          ForEach(ThemeFont.allCases, id: \.self) { Text($0.rawValue).tag($0) }
        }
        Picker("Fonte de texto", selection: $values.textFont) {
          ForEach(ThemeFont.allCases, id: \.self) { Text($0.rawValue).tag($0) }
        }
      }

      Section("Cores da API") {
        ThemeColorField(title: "Primária", value: $values.primary)
        ThemeColorField(title: "Primária clara", value: $values.primaryLight)
        ThemeColorField(title: "Secundária", value: $values.secondary)
        ThemeColorField(title: "Secundária escura", value: $values.secondaryDark)
        ThemeColorField(title: "Texto", value: $values.textColor)
        ThemeColorField(title: "Texto de contraste", value: $values.textContrast)
      }

      Section("Prévia") {
        ThemePreview(values: values)
      }

      if record?.canReset == true {
        Section {
          Button("Restaurar herança", role: .destructive) { Task { await reset() } }
        }
      }
    }
    .navigationTitle("Aparência")
    .toolbar {
      if record?.canEdit == true {
        Button("Salvar") { Task { await save() } }
          .accessibilityIdentifier("theme.save")
      }
    }
    .task(id: app.dataRevision) {
      guard !isDirty else { return }
      await load()
    }
    .alert(
      "Não foi possível atualizar",
      isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })
    ) {
      Button("OK") { error = nil }
    } message: {
      Text(error?.message ?? "")
    }
  }

  private func load() async {
    do {
      let loaded = try await app.dependencies.themes.theme(target: target)
      record = loaded
      values = loaded.stored ?? loaded.effective
      loadedValues = values
    } catch { self.error = DemoError(error) }
  }

  private func save() async {
    do {
      try await app.dependencies.themes.updateTheme(target: target, values: values)
      await load()
      app.showNotice("Tema atualizado.")
    } catch { self.error = DemoError(error) }
  }

  private func reset() async {
    do {
      try await app.dependencies.themes.resetTheme(target: target)
      await load()
      app.showNotice("Herança de tema restaurada.")
    } catch { self.error = DemoError(error) }
  }
}

private struct ThemeColorField: View {
  let title: String
  @Binding var value: String

  var body: some View {
    HStack {
      Circle()
        .fill(Color(hex: value) ?? .clear)
        .frame(width: 24, height: 24)
        .overlay { Circle().stroke(RentivoColors.ink.opacity(0.4)) }
      TextField(title, text: $value)
        .textInputAutocapitalization(.characters)
        .font(.system(.body, design: .monospaced))
    }
  }
}

private struct ThemePreview: View {
  let values: ThemeValues

  var body: some View {
    VStack(alignment: .leading, spacing: RentivoSpacing.medium) {
      Text("Fatura Rentivo")
        .font(.title2.bold())
        .foregroundStyle(Color(hex: values.textColor) ?? RentivoColors.ink)
      Text("Uma prévia local das cores do documento.")
        .foregroundStyle(Color(hex: values.textColor) ?? RentivoColors.ink)
      Text("R$ 2.450,00")
        .font(.system(.title3, design: .monospaced, weight: .bold))
        .foregroundStyle(Color(hex: values.textContrast) ?? .white)
        .padding()
        .frame(maxWidth: .infinity)
        .background(Color(hex: values.primary) ?? RentivoColors.emerald)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
    .padding()
    .background(Color(hex: values.primaryLight) ?? RentivoColors.emeraldLight)
    .clipShape(RoundedRectangle(cornerRadius: 16))
  }
}

extension ThemeSource {
  fileprivate var label: String {
    switch self {
    case .billing: "Cobrança"
    case .organization: "Organização"
    case .user: "Usuário"
    case .default: "Padrão Rentivo"
    }
  }
}

extension Color {
  init?(hex: String) {
    let value = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
    guard value.count == 6, let rgb = Int(value, radix: 16) else { return nil }
    self.init(
      red: Double((rgb >> 16) & 0xFF) / 255,
      green: Double((rgb >> 8) & 0xFF) / 255,
      blue: Double(rgb & 0xFF) / 255
    )
  }
}
