import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

// `AppModel` lives under `App/`, which the RentivoCore SPM package excludes (see
// `Package.swift`), so these tests only compile/run as part of the Xcode-hosted `RentivoTests`
// target (the full "Rentivo" app module), like the `AppModel`-only section of
// `SessionExpiryTests.swift`.
#if !canImport(RentivoCore)

  @MainActor
  @Test func mockSignInAuthenticatesSelectsHomeAndShowsTheDemoWelcomeNotice() {
    let app = AppModel(store: MockRentivoStore(fixtures: .canonical))
    app.selectedTab = .account

    app.signIn()

    guard case .authenticated(let profile) = app.session else {
      Issue.record("Expected an authenticated session after signIn()")
      return
    }
    #expect(profile.email == app.currentUser.email)
    #expect(app.selectedTab == .home)
    #expect(app.notice?.message == "Bem-vinda à demonstração do Rentivo.")
    guard case .success = app.notice?.kind else {
      Issue.record("Expected a success-kind notice, got \(String(describing: app.notice?.kind))")
      return
    }
  }

  @MainActor
  @Test func mockSignOutCompletesSynchronouslyWithoutTogglingIsSigningOut() async {
    let app = AppModel(store: MockRentivoStore(fixtures: .canonical))
    app.signIn()
    app.selectedTab = .billings

    await app.signOut()

    guard case .anonymous = app.session else {
      Issue.record("Expected an anonymous session after signOut() against the mock store")
      return
    }
    // The mock store has no `APIRentivoStore` to revoke a token against, so `signOut()` takes the
    // `completeSignOut()` shortcut directly and never flips `isSigningOut` to true in between.
    #expect(app.isSigningOut == false)
    #expect(app.selectedTab == .home)
    #expect(app.notice == nil)
  }

  @MainActor
  @Test func delayToggleSkipsDataRevisionButEmptyAndViewerToggleBumpIt() {
    let app = AppModel(store: MockRentivoStore(fixtures: .canonical))
    let initialRevision = app.dataRevision

    // Only the delay toggle is a "how content loads" setting, not a "what content loads" setting;
    // bumping `dataRevision` for it would force every visible screen to redundantly reload.
    app.setDelayEnabled(true)
    #expect(app.demoSettings.delayEnabled == true)
    #expect(app.dataRevision == initialRevision)

    app.setEmptyMode(true)
    #expect(app.demoSettings.emptyMode == true)
    #expect(app.dataRevision == initialRevision + 1)

    app.setViewerMode(true)
    #expect(app.demoSettings.viewerMode == true)
    #expect(app.dataRevision == initialRevision + 2)
  }

  @MainActor
  @Test func resetDemoRestoresDefaultSettingsAndBumpsDataRevision() {
    let app = AppModel(store: MockRentivoStore(fixtures: .canonical))
    app.setDelayEnabled(true)
    app.setEmptyMode(true)
    app.setViewerMode(true)
    let revisionBeforeReset = app.dataRevision

    app.resetDemo()

    #expect(app.demoSettings == .standard)
    #expect(app.dataRevision == revisionBeforeReset + 1)
  }

  @MainActor
  @Test func restoreSessionIfNeededIsANoOpForTheMockStoreSinceItNeverStartsRestoring() async {
    let app = AppModel(store: MockRentivoStore(fixtures: .canonical))
    guard case .anonymous = app.session else {
      Issue.record("Expected the mock-backed AppModel to start anonymous, not restoring")
      return
    }

    await app.restoreSessionIfNeeded()

    guard case .anonymous = app.session else {
      Issue.record("Expected restoreSessionIfNeeded() to leave an already-anonymous session alone")
      return
    }
  }

#endif
