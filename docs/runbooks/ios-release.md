# iOS Release Runbook

This runbook records the current state of iOS distribution and the path to
TestFlight/App Store Connect. Unlike the
[production release runbook](production-release.md), there is no live iOS
release automation yet: this document is intentionally a snapshot of what
exists today plus the steps still needed, not a procedure to execute.

## Current state

- **Bundle identifiers are placeholders.** `ios/Rentivo.xcodeproj/project.pbxproj`
  sets `PRODUCT_BUNDLE_IDENTIFIER = app.rentivo.demo` for the app target, with
  `app.rentivo.demo.tests` and `app.rentivo.demo.uitests` for the test targets.
  None of these are registered to an Apple Developer account or intended as a
  production identifier.
- **Marketing version is static.** `MARKETING_VERSION` is `0.1` in the same
  project file. Nothing bumps it; it is not derived from a tag, a release SHA,
  or any workflow.
- **No signing team is configured.** The targets use `CODE_SIGN_STYLE =
  Automatic` with no `DEVELOPMENT_TEAM` set. The project cannot produce a
  signed archive without a developer assigning a team locally in Xcode first.
- **CI covers unit tests only.** `.github/workflows/test-pr.yaml` runs
  `swift test --package-path ios` (the `RentivoCore` package's test suite) on
  `macos-15` runners. It does not run `xcodebuild test`, `xcodebuild build`, or
  `xcodebuild archive` for the `Rentivo` app or `RentivoUITests` targets. The
  `xcodebuild test` action is currently broken — the `RentivoTests` target does
  not correctly link `RentivoCore` — and is tracked as separate work; do not
  assume `xcodebuild` builds succeed until that is fixed and this runbook is
  updated.
- **iOS is outside the backend/frontend release workflow.**
  `.github/workflows/release.yml`, which publishes API/worker/frontend images
  for a Git SHA, does not reference `ios/` at all. There is no versioning,
  tagging, or artifact publishing tied to iOS from that workflow.
- **No App Store Connect integration exists.** There is no App Store Connect
  API key, provisioning profile, Fastlane configuration, or Xcode Cloud setup
  anywhere in this repository.

## Checks that must pass before any release build

Regardless of how distribution is eventually wired up, do not produce a
release build from a commit unless:

1. `swift test --package-path ios` (`make ios-test`) passes — the
   `RentivoCore` package's tests, run with a full Xcode toolchain.
2. `./scripts/sync-ios-openapi.sh check` (`make ios-openapi-check`) passes —
   `ios/Rentivo/openapi.json` must be byte-identical to `frontend/openapi.json`
   so the shipped app talks to the deployed `/api/v1` contract.
3. The backend/frontend release gate (`.github/workflows/test-pr.yaml`) passes
   for the commit the app is built from, since the iOS app is a client of the
   same versioned API.

## Steps still needed before TestFlight distribution

This is the path, not a schedule. None of the following is implemented yet.

1. **Decide the production bundle identifier(s)** to replace
   `app.rentivo.demo` (and its `.tests`/`.uitests` suffixes), registered to the
   organization's Apple Developer account.
2. **Assign a signing team and provisioning profiles.** Set `DEVELOPMENT_TEAM`
   in `ios/Rentivo.xcodeproj/project.pbxproj` (or an xcconfig) and decide
   between Automatic and manual signing for CI-driven archiving.
3. **Introduce version stamping.** Decide how `MARKETING_VERSION` and the
   build number (`CURRENT_PROJECT_VERSION`) are bumped for each release —
   manually, from a Git tag, or by a script — and whether iOS releases share a
   cadence with `release.yml` or ship independently. Today neither is decided
   and iOS versioning happens outside `release.yml` entirely.
4. **Create the App Store Connect app record** under the chosen bundle ID,
   including app name, category, and PT-BR customer-facing metadata
   (description, screenshots) consistent with the product's copy rules.
5. **Fix and extend CI to build/archive the app.** This depends on the
   `RentivoTests`/`RentivoCore` link being fixed first (see Current state
   above), then adding an `xcodebuild archive` + `xcodebuild -exportArchive`
   step with a signed export options plist, followed by upload via
   `xcrun altool` / `xcrun notarytool` or the App Store Connect API.
6. **Add App Store Connect API credentials as CI secrets**, scoped the same
   way production deployment secrets are scoped for `deploy.yml`, once the app
   record and signing exist.
7. **Decide and document the release cadence and gate** — whether iOS ships on
   the same SHA as backend/frontend or on its own schedule — and update this
   runbook once that decision is made and implemented.

## Non-goals of this document

This runbook does not describe TestFlight submission, App Store review, or
phased rollout steps, because none of the prerequisite infrastructure (bundle
ID, signing team, App Store Connect app record, archive/upload automation)
exists yet. Treat any description of a live iOS release pipeline elsewhere as
incorrect until this document is updated alongside the change that implements
it.
