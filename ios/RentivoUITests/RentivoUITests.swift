import XCTest

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

  func testAuthenticationValidationIsRecoverable() throws {
    let app = XCUIApplication()
    app.launchArguments = ["--ui-testing"]
    app.launch()

    app.buttons["login.submit"].tap()
    XCTAssertTrue(app.staticTexts["login.error"].waitForExistence(timeout: 2))
    signIn(app)
    XCTAssertTrue(app.tabBars.buttons["Início"].waitForExistence(timeout: 3))
  }

  func testBillingCreationToPaidReceiptAndThemeJourney() throws {
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
    XCTAssertTrue(app.buttons["Visualizar recibo"].waitForExistence(timeout: 3))
    app.buttons["Visualizar recibo"].tap()
    XCTAssertTrue(app.staticTexts["RECIBO DE PAGAMENTO"].waitForExistence(timeout: 2))
    app.buttons["Concluir"].tap()

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

  private func launchAndSignIn() -> XCUIApplication {
    let app = XCUIApplication()
    app.launchArguments = ["--ui-testing"]
    app.launch()
    signIn(app)
    return app
  }

  private func signIn(_ app: XCUIApplication) {
    let email = app.textFields["login.email"]
    XCTAssertTrue(email.waitForExistence(timeout: 3))
    email.tap()
    email.typeText("ana@example.com")
    app.secureTextFields["login.password"].tap()
    app.secureTextFields["login.password"].typeText("demonstracao")
    app.buttons["login.submit"].tap()
    let declinePasswordSave = app.buttons["Agora Não"]
    if declinePasswordSave.waitForExistence(timeout: 2) {
      declinePasswordSave.tap()
    }
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
