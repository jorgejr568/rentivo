import XCTest

// These UI tests drive the app in `--ui-testing` (mock store) mode against
// `MockFixtures.canonical`. Two constraints shape what's testable here:
//
// - `AppModel.signInWithWebAuthorization()` short-circuits to the synchronous,
//   unconditional `signIn()` whenever `dependencies.auth` isn't `APIRentivoStore`
//   (always true in `--ui-testing` mode, see `RentivoApp.swift`). There is no
//   launch argument, demo setting, or injectable seam that makes mock sign-in
//   fail, and `LoginView` no longer has any credential fields to submit invalid
//   values into — it is just a single "Entrar" button. A prior
//   `testAuthenticationValidationIsRecoverable` test (typing a wrong
//   password to trigger `login.error`) is therefore not reproducible without
//   adding a test-only failure hook to `AppModel`/`MockRentivoStore`/
//   `RentivoApp.swift`, which is out of scope for a test-only fix. Dropped.
// - Every `FileDownloadRepository` method on `MockRentivoStore` (invoice,
//   recibo, receipt, attachment downloads) unconditionally throws
//   `DemoError.operationFailed` — the mock store never produces a real file.
//   Any flow that taps a "download"/"open PDF" action in mock mode ends in
//   the demonstration failure notice, never a document preview sheet.
@MainActor
final class RentivoUITests: XCTestCase {
  override func setUpWithError() throws {
    continueAfterFailure = false
  }

  func testPrimaryDemonstrationJourney() throws {
    let app = launchAndSignIn()

    XCTAssertTrue(app.tabBars.buttons["Início"].waitForExistence(timeout: 3))
    app.tabBars.buttons["Cobranças"].tap()
    XCTAssertTrue(app.navigationBars["Cobranças"].waitForExistence(timeout: 2))
    XCTAssertTrue(app.buttons["billing.create"].exists)

    app.tabBars.buttons["Organizações"].tap()
    XCTAssertTrue(app.navigationBars["Organizações"].waitForExistence(timeout: 2))

    app.tabBars.buttons["Conta"].tap()
    XCTAssertTrue(app.navigationBars["Conta"].waitForExistence(timeout: 2))
  }

  func testBillingCreationValidation() throws {
    let app = launchAndSignIn()
    app.tabBars.buttons["Cobranças"].tap()
    app.buttons["billing.create"].tap()

    XCTAssertTrue(app.navigationBars["Nova cobrança"].waitForExistence(timeout: 2))
    app.buttons["billing.form.save"].tap()
    app.swipeUp()
    app.swipeUp()
    XCTAssertTrue(
      app.staticTexts.matching(identifier: "billing.form.validation").firstMatch
        .waitForExistence(timeout: 2)
    )
  }

  func testBillingCreationToPaidAndThemeJourney() throws {
    let app = launchAndSignIn()
    app.tabBars.buttons["Cobranças"].tap()
    openCanonicalBilling(in: app)

    scrollTo(app.buttons["bill.create"], in: app)
    app.buttons["bill.create"].tap()
    XCTAssertTrue(app.navigationBars["Gerar fatura"].waitForExistence(timeout: 2))
    app.buttons["bill.form.save"].tap()
    XCTAssertTrue(app.staticTexts["Fatura criada como rascunho."].waitForExistence(timeout: 3))

    let draft = app.buttons["bill.card.00000000-0000-0000-0000-000000001001"]
    scrollTo(draft, in: app)
    draft.tap()
    transition("published", in: app)
    transition("sent", in: app)
    transition("paid", in: app)

    // "Abrir recibo" only appears once the bill is paid. The mock store's
    // download stub always fails (see file-level comment above), so this
    // verifies the recoverable failure notice rather than a document preview.
    let openReceipt = app.buttons["Abrir recibo"]
    scrollTo(openReceipt, in: app)
    openReceipt.tap()
    XCTAssertTrue(
      app.staticTexts["Não foi possível concluir esta ação de demonstração."]
        .waitForExistence(timeout: 3)
    )
    app.buttons["Fechar aviso"].tap()

    app.navigationBars.buttons.element(boundBy: 0).tap()
    let theme = app.buttons["billing.theme"]
    scrollTo(theme, in: app)
    theme.tap()
    XCTAssertTrue(app.navigationBars["Aparência"].waitForExistence(timeout: 2))
    XCTAssertTrue(app.buttons["theme.save"].exists)
    let primary = app.textFields["Primária"]
    primary.tap()
    primary.typeText("0")
    app.buttons["theme.save"].tap()
    XCTAssertTrue(waitForValue(of: primary, containing: "0"))
  }

  func testExpenseCreationJourney() throws {
    let app = launchAndSignIn()
    app.tabBars.buttons["Cobranças"].tap()
    openCanonicalBilling(in: app)

    let expenses = app.buttons["Despesas"]
    scrollTo(expenses, in: app)
    expenses.tap()
    XCTAssertTrue(app.navigationBars["Despesas"].waitForExistence(timeout: 2))
    app.buttons["Adicionar"].tap()
    app.textFields["Descrição"].tap()
    app.textFields["Descrição"].typeText("Reparo da fechadura")
    app.textFields["Valor em centavos"].tap()
    app.textFields["Valor em centavos"].typeText("12500")
    app.buttons["Salvar"].tap()
    XCTAssertTrue(app.staticTexts["Reparo da fechadura"].waitForExistence(timeout: 3))
  }

  func testInvitationAcceptanceJourney() throws {
    let app = launchAndSignIn()
    app.tabBars.buttons["Organizações"].tap()
    let invitations = app.buttons["organization.invitations.open"]
    XCTAssertTrue(invitations.waitForExistence(timeout: 3))
    invitations.tap()
    XCTAssertTrue(app.navigationBars["Convites"].waitForExistence(timeout: 2))
    app.buttons["Aceitar"].tap()
    XCTAssertTrue(
      app.descendants(matching: .any)["page.empty"].waitForExistence(timeout: 3)
    )
  }

  func testViewerModeHidesMutationActions() throws {
    let app = launchAndSignIn()
    openDemoScenarios(in: app)
    app.buttons["demo.viewer-mode"].tap()
    XCTAssertTrue(waitForValue(of: app.buttons["demo.viewer-mode"], equalTo: "Ativo"))

    app.tabBars.buttons["Cobranças"].tap()
    XCTAssertFalse(app.buttons["billing.create"].exists)
    openCanonicalBilling(in: app)
    XCTAssertFalse(app.buttons["billing.edit"].exists)
    XCTAssertFalse(app.buttons["bill.create"].exists)

    let draft = app.buttons["bill.card.00000000-0000-0000-0000-000000001001"]
    scrollTo(draft, in: app)
    draft.tap()
    XCTAssertFalse(app.buttons["bill.transition.published"].exists)
    XCTAssertTrue(
      app.staticTexts["Ciclo disponível somente para quem pode gerenciar faturas."]
        .waitForExistence(timeout: 2)
    )
  }

  func testFailureRecoveryEmptyStateAndResetJourney() throws {
    let app = launchAndSignIn()
    openDemoScenarios(in: app)
    app.buttons["demo.fail-next"].tap()

    app.tabBars.buttons["Cobranças"].tap()
    XCTAssertTrue(app.staticTexts["Não foi possível carregar"].waitForExistence(timeout: 3))
    app.buttons["Tentar novamente"].tap()
    XCTAssertTrue(
      app.buttons["billing.card.00000000-0000-0000-0000-000000000101"]
        .waitForExistence(timeout: 3)
    )

    app.tabBars.buttons["Conta"].tap()
    app.buttons["demo.empty-mode"].tap()
    app.tabBars.buttons["Cobranças"].tap()
    XCTAssertTrue(
      app.descendants(matching: .any)["page.empty"].waitForExistence(timeout: 3)
    )

    app.tabBars.buttons["Conta"].tap()
    app.buttons["demo.reset"].tap()
    app.buttons["Restaurar"].tap()
    app.tabBars.buttons["Cobranças"].tap()
    XCTAssertTrue(
      app.buttons["billing.card.00000000-0000-0000-0000-000000000101"]
        .waitForExistence(timeout: 3)
    )
  }

  // A `testAPIKeyRevocationRequiresConfirmation` test (tapping the "Chaves de integração" row's
  // small in-row "Editar"/"Revogar" buttons — see `APIKeyListView` in `APIKeyViews.swift`) was
  // attempted here to cover the API-key revoke confirmation dialog. It was dropped: on this
  // simulator, XCUITest's synthesized tap on either button in that row (not just the one opening
  // the confirmationDialog) reliably fails to invoke the button's action — confirmed by "Editar"
  // also never presenting its edit sheet, which rules out anything specific to confirmationDialog.
  // Reproducing or fixing that would mean changing `APIKeyViews.swift`, which is out of scope for
  // a test-only fix. The passkey-delete and expense/attachment/receipt-delete confirmation
  // dialogs use the same `.confirmationDialog(_:isPresented:presenting:actions:message:)` pattern
  // and may share this risk; a future change to those rows' layout should re-attempt UI coverage.

  private func launchAndSignIn() -> XCUIApplication {
    let app = XCUIApplication()
    app.launchArguments = ["--ui-testing"]
    app.launch()
    signIn(app)
    return app
  }

  /// Current `LoginView` (see `AuthViews.swift`) has no credential fields —
  /// it is a single "Entrar" button that, in `--ui-testing` mode, resolves
  /// synchronously via `AppModel.signIn()` without any browser hand-off.
  private func signIn(_ app: XCUIApplication) {
    let submit = app.buttons["login.submit"]
    XCTAssertTrue(submit.waitForExistence(timeout: 3))
    submit.tap()
    XCTAssertTrue(app.tabBars.buttons["Início"].waitForExistence(timeout: 3))
  }

  private func openCanonicalBilling(in app: XCUIApplication) {
    let billing = app.buttons["billing.card.00000000-0000-0000-0000-000000000101"]
    XCTAssertTrue(billing.waitForExistence(timeout: 3))
    billing.tap()
    XCTAssertTrue(app.navigationBars["Detalhes"].waitForExistence(timeout: 2))
  }

  private func openDemoScenarios(in app: XCUIApplication) {
    app.tabBars.buttons["Conta"].tap()
    let scenarios = app.buttons["account.demo"]
    scrollTo(scenarios, in: app)
    scenarios.tap()
    XCTAssertTrue(app.navigationBars["Cenários"].waitForExistence(timeout: 2))
  }

  private func transition(_ status: String, in app: XCUIApplication) {
    let button = app.buttons["bill.transition.\(status)"]
    scrollTo(button, in: app)
    button.tap()
    XCTAssertFalse(button.waitForExistence(timeout: 1))
  }

  private func scrollTo(_ element: XCUIElement, in app: XCUIApplication) {
    var attempts = 0
    while !element.exists && attempts < 8 {
      app.swipeUp()
      attempts += 1
    }
    XCTAssertTrue(element.exists)
  }

  private func waitForValue(of element: XCUIElement, equalTo value: String) -> Bool {
    XCTWaiter.wait(
      for: [
        XCTNSPredicateExpectation(
          predicate: NSPredicate(format: "value == %@", value),
          object: element
        )
      ],
      timeout: 3
    ) == .completed
  }

  private func waitForValue(of element: XCUIElement, containing value: String) -> Bool {
    XCTWaiter.wait(
      for: [
        XCTNSPredicateExpectation(
          predicate: NSPredicate(format: "value CONTAINS %@", value),
          object: element
        )
      ],
      timeout: 3
    ) == .completed
  }
}
