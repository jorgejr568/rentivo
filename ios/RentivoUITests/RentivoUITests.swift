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
  }
}
