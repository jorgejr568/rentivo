# Rentivo Native iOS Demonstration Design

**Date:** 2026-07-20

**Status:** Approved for specification

**API reference:** GitHub PR #138, `frontend/openapi.json` at commit `934f07932b9240d97fec95c95fe67497810b9e29`

## Summary

Build an iPhone-first native SwiftUI application that demonstrates Rentivo's complete product experience without contacting a backend. The application preserves Rentivo's PT-BR copy and refined neobrutalist brand while adopting native iOS navigation, presentation, form, and accessibility conventions.

All screens read and mutate one coherent in-memory data graph. Repository protocols isolate feature code from the mock implementation so a later API-backed implementation can replace the local store without restructuring the UI.

## Goals

- Deliver a buildable, navigable iOS application suitable for a product demonstration.
- Cover the authenticated domain exposed by PR #138: authentication, recurring billings, invoices, receipts, expenses, attachments, communications, exports, organizations, members, invitations, security, integration keys, and themes.
- Demonstrate complete user journeys instead of disconnected static screenshots.
- Use realistic Brazilian fixtures, BRL values stored as integer centavos, PIX details, PT-BR copy, and public UUID identifiers.
- Preserve API concepts and capability rules so backend integration is additive.
- Include populated, empty, loading, recoverable-error, and permission-restricted states.
- Make the principal experience accessible and verifiable with unit, view-model, and UI tests.

## Non-goals

- No HTTP requests, server authentication, persistent database, analytics delivery, push notifications, or background jobs.
- No production handling of API keys or secrets. Demonstration secrets are synthetic and remain in memory.
- No real PDF generation, email delivery, file upload, biometric credential registration, PIX payment, or export delivery. These actions use credible native previews and simulated completion.
- No iPad-specific layout in the first implementation. The UI must remain usable when resized, but iPhone is the design and test target.
- No independent admin, manager, or viewer persona switcher in the primary flow. Permission-restricted states remain available from the demonstration scenarios screen.
- No attempt to reproduce the mobile web layout pixel-for-pixel.

## Product Assumptions

- The primary persona is a landlord who owns personal billings and an organization, with all capabilities enabled.
- The application is iPhone-first with an iOS 17.0 minimum deployment target.
- All customer-facing copy is PT-BR; source names and identifiers remain English.
- The demo starts logged out. A clearly labeled demonstration login accepts any non-empty valid-looking email and password.
- Local mutations persist for the current process only. A reset action restores the canonical fixtures.
- The implementation lives under `ios/` in this repository and does not alter the existing backend or React application.

## Experience and Navigation

### Authentication shell

The logged-out experience uses a branded, focused navigation stack:

1. Login
2. Signup
3. Forgot password
4. Reset-password confirmation
5. MFA method selection and verification
6. Passkey demonstration

Successful completion enters the authenticated tab shell. Logout returns to login and resets only authentication state, not the mutable demo dataset.

### Authenticated tab shell

The application has four primary tabs, each owning an independent `NavigationStack`:

| Tab | Purpose |
| --- | --- |
| Início | Portfolio overview, alerts, upcoming invoices, and quick actions |
| Cobranças | Recurring billing templates, invoices, expenses, files, and communications |
| Organizações | Organizations, members, roles, invitations, policy, and transfers |
| Conta | Profile, PIX, security, integration keys, appearance, and demo controls |

Deep navigation stays within the relevant tab. Creation and editing use sheets when the task is short and a pushed screen when it is multi-section or benefits from progress continuity.

## Screen Inventory and Behavior

### Início

- Greeting and current workspace summary.
- Revenue, expenses, net income, overdue balance, and collection-rate cards.
- Upcoming invoices with due dates and status badges.
- Overdue alert linking to the relevant invoice.
- Quick actions for creating a billing template and generating an invoice.
- Recent activity derived from local mutations.

Dashboard values are computed from the same billing, bill, and expense records shown elsewhere. They are not separate hard-coded totals.

### Cobranças

#### Billing list

- Search by name, description, or owner.
- Segmented filter for all, personal, and organization-owned billings.
- Cards show fixed subtotal, owner, PIX readiness, invoice count, and current status summary.
- Create action and a meaningful empty state.

#### Create and edit billing

- Name, description, owner, PIX override, recipients, reply-to address, and ordered line items.
- Fixed and variable item types.
- Add, edit, delete, and reorder line items.
- Field-level validation with PT-BR messages.
- Saving updates the list, detail screen, and dashboard where applicable.

#### Billing detail

- Billing identity, ownership, capabilities, and PIX readiness.
- Recurring line items and fixed subtotal.
- PIX inheritance or override summary.
- Invoice history.
- Annual received, expense, and net-income summaries.
- Expense list and create/delete flows.
- Billing attachments with simulated add, preview, download, and delete actions.
- Recipient and reply-to management.
- CSV/XLSX export simulation.
- Transfer to an organization.
- Billing-level theme editor.
- Destructive delete confirmation.

#### Generate and edit invoice

- Reference month, due date, variable values, extras, and notes.
- Live total computed in centavos.
- Clear fixed, variable, and extra sections.
- Validation prevents invalid dates, negative values, and duplicate empty rows.
- Completion creates a draft invoice and navigates to its detail screen.

#### Invoice detail

- Reference, total, due date, paid date, notes, line items, and status.
- Guarded lifecycle actions matching the API domain exactly: draft, published, sent, paid, cancelled, and delayed payment.
- Edit and regenerate simulations.
- Invoice PDF preview placeholder and simulated share/download.
- Receipt list with simulated add, preview, reorder, download, and delete.
- Payment receipt (`recibo`) preview when the invoice is paid.
- Communication composer entry point.
- Destructive delete confirmation.

#### Communication composer

- Template selection, recipients, subject, message, and attachment summary.
- Preview mode before sending.
- Simulated delivery result appended to recent activity.

### Organizações

#### Organization list and detail

- Personal organization cards with role, member count, billing count, and MFA policy.
- Create and edit organization flows.
- PIX configuration inherited by organization-owned billings.
- Member list with owner, admin, manager, and viewer roles.
- Invite member, change role, and remove member simulations.
- Organization-enforced MFA toggle with impact confirmation.
- Billing transfer into the organization.
- Organization-level theme editor.
- Organization deletion guard and confirmation.

#### Invitations

- Pending invitations accessible from the organizations experience and account notifications.
- Accept and decline actions mutate membership and pending counts.
- Empty state after all invitations are resolved.

### Conta

#### Profile and PIX

- Current email and demonstration account metadata.
- Personal PIX key, merchant name, and city.
- Saving immediately affects personal billings that inherit PIX settings.

#### Security

- Change-password simulation.
- TOTP setup, confirmation, disable, and recovery-code regeneration.
- Recovery-code reveal screen using synthetic values.
- Passkey list, registration simulation, rename, and delete.
- Clear success and destructive-action feedback.

#### Integration keys

- Masked key list with name, scopes, grants, expiration, last-used metadata, and revoked state.
- Creation form using safe scopes and personal/organization access grants aligned to PR #138.
- One-time synthetic secret reveal and copy action.
- Metadata update and idempotent revoke actions.
- Login tokens never appear in this management surface.

#### Appearance

- User-level theme editor with header/text fonts and the six API-defined colors: primary, primary light, secondary, secondary dark, text, and contrast text.
- Organization and billing editors reuse the same component with inheritance and reset behavior.
- Changes update the in-app preview and relevant branded document placeholders.

#### Demonstration scenarios

- Reset all data.
- Toggle deterministic operation delay.
- Fail the next read or mutation with a recoverable error.
- Switch the selected screen's data source between populated and empty fixtures.
- Preview viewer-style capability restrictions without changing the primary persona.

These controls are explicitly labeled as demonstration tools and are excluded from the future production navigation configuration.

## Visual System

The iOS design translates, rather than copies, the React preview's system:

- Warm paper background and slightly lighter card surfaces.
- Near-black indigo ink for text and borders.
- Emerald primary actions and success states.
- Harmonized colors for draft, published, sent, paid, cancelled, and delayed-payment states.
- Rounded rectangles with two-point ink borders and restrained hard shadows.
- Strong display hierarchy, compact metadata, monospaced numeric treatment where useful, and tabular BRL values.
- A compact `R` brand mark and the `rentivo` wordmark on authentication and high-level account surfaces.

SwiftUI-native behavior takes precedence for tab bars, navigation bars, sheets, menus, swipe actions, pickers, date selection, safe areas, keyboard avoidance, Dynamic Type, and VoiceOver.

The design system exposes semantic tokens and reusable components rather than feature-specific styling:

- `RentivoColors`
- `RentivoSpacing`
- `RentivoTypography`
- `RentivoCard`
- `RentivoButtonStyle`
- `StatusBadge`
- `MoneyText`
- `PageStateView`
- `ConfirmationAction`

## Architecture

### Project layout

```text
ios/
  Rentivo.xcodeproj
  Rentivo/
    App/
    DesignSystem/
    Domain/
    Data/
      Repositories/
      Mock/
    Features/
      Auth/
      Home/
      Billings/
      Bills/
      Organizations/
      Invites/
      Security/
      APIKeys/
      Themes/
      Demo/
    Resources/
  RentivoTests/
  RentivoUITests/
```

Feature files remain small and purpose-specific. Views render state and send intents; observable feature models coordinate validation, repository calls, routing, and presentation state.

### Domain models

Models mirror the stable concepts in PR #138 without copying generated TypeScript declarations mechanically. Important invariants include:

- Public identifiers are typed UUID wrappers or `UUID` values, never backend integer IDs.
- Monetary values are integer centavos and use checked arithmetic.
- Dates and timestamps remain distinct domain types.
- API enum raw values match the contract where practical.
- Capabilities are explicit value types supplied with resources.
- Secrets are separate response values and are never retained in list models.

Core model groups are:

- `UserProfile`, `AuthenticationState`, `MFAChallenge`
- `Billing`, `BillingItem`, `BillingOwner`, `BillingCapabilities`
- `Bill`, `BillLineItem`, `BillStatus`, `Receipt`
- `Expense`, `Attachment`, `CommunicationDraft`
- `Organization`, `OrganizationMember`, `OrganizationRole`, `Invitation`
- `SecuritySummary`, `Passkey`, `RecoveryCodeSet`
- `APIKeyMetadata`, `APIKeyScope`, `ResourceGrant`, `CreatedAPIKeySecret`
- `Theme`, `ThemeTarget`, `ThemeInheritance`

### Repository boundary

Features depend on focused protocols grouped by domain, not on one unbounded service object:

- `AuthRepository`
- `ProfileRepository`
- `BillingRepository`
- `BillRepository`
- `OrganizationRepository`
- `InvitationRepository`
- `SecurityRepository`
- `APIKeyRepository`
- `ThemeRepository`

The application injects one `AppDependencies` value that provides these protocols. The first implementation routes every protocol to a shared, main-actor `MockRentivoStore`, preserving cross-feature consistency.

A later `APIRentivoRepository` layer will translate between these domain models and the OpenAPI wire models. View and navigation code must not know whether data came from mock memory or HTTP.

### State flow

1. A view appears and asks its feature model to load.
2. The feature model calls the relevant repository protocol.
3. The mock repository optionally delays or fails, then reads or mutates the shared store.
4. The feature model exposes loading, content, empty, or error state.
5. Related screens recompute from store snapshots after mutations.
6. User feedback appears through native alerts, confirmation dialogs, sheets, and transient success banners.

No fixture values are embedded directly in feature views.

## Mock Dataset

The canonical dataset is deterministic and derived from the repository's existing PT-BR seed vocabulary. It includes:

- User `ana@example.com` with configured personal PIX.
- Organization `Imobiliária Horizonte` with owner, admin, manager, and viewer members.
- At least one pending invitation.
- At least six personal and organization-owned billings, including `Apt 101 - Edifício Aurora`, `Apt 202 - Edifício Aurora`, `Apt 303 - Residencial Sol Nascente`, and `Casa 1 - Vila das Flores`.
- Fixed items such as aluguel, condomínio, and IPTU; variable items such as água, luz, and gás.
- Invoice examples in every supported lifecycle state across recent months.
- Paid, overdue, and upcoming invoices that produce meaningful dashboard summaries.
- Expenses in multiple API-supported categories.
- Synthetic attachments and receipts with safe local metadata.
- A configured passkey, enabled TOTP, recovery-code count, and masked integration key.
- Personal, organization, and billing theme examples that demonstrate inheritance.

Fixtures use stable identifiers so UI tests can address the same resources on every run.

## Loading, Empty, Error, and Permission States

Every top-level feature uses an explicit load-state type rather than inferring state from optional values. Requirements are:

- Loading state announces progress accessibly and avoids layout jumps where reasonable.
- Empty state explains the missing content and offers the primary permitted action.
- Recoverable failures show a PT-BR explanation and retry action.
- Validation failures attach to the responsible field and move accessibility focus appropriately.
- Permission-restricted actions are absent or disabled with an explanation, based on capability data.
- Destructive operations require confirmation and describe their impact.
- Simulated file, export, passkey, and communication actions never imply real external delivery.

## Accessibility and Localization

- All user-facing copy is PT-BR and centralized sufficiently to support future localization.
- VoiceOver labels describe icons, status badges, totals, charts, and destructive actions.
- Dynamic Type is supported without truncating primary actions or monetary values.
- Color is never the only indication of status.
- Interactive targets meet minimum iOS sizing.
- Form errors are readable, programmatically associated, and not conveyed only by border color.
- Reduced Motion removes decorative transitions while preserving task feedback.
- Currency uses `pt_BR` BRL formatting while retaining centavos internally.

## Testing and Verification

### Unit tests

- BRL formatting and centavo arithmetic.
- Date and reference-month formatting.
- Invoice lifecycle transition rules.
- Capability and organization-role decisions.
- Theme inheritance and reset behavior.
- Dashboard aggregation from bills and expenses.
- Mock repository CRUD, mutation consistency, injected failure, delay, and reset.
- Validation for authentication, billing, invoice, expense, organization, and API-key forms.

### Feature-model tests

- Login and MFA completion.
- Create/edit/delete billing.
- Generate/edit/transition/delete invoice.
- Add/remove expense and update dashboard summaries.
- Accept/decline invitation and update pending count.
- Organization member and policy changes.
- Security, passkey, recovery-code, API-key, and theme flows.
- Loading, empty, failure, retry, and permission-restricted states.

### UI smoke tests

- Login to dashboard.
- Navigate the four primary tabs.
- Create a billing and generate its first invoice.
- Move an invoice through a valid lifecycle and view its receipt state.
- Add an expense and observe updated financial summaries.
- Accept an invitation and open the resulting organization.
- Change a theme and verify its preview.
- Inject and recover from a failure.
- Reset demonstration data.

### Build and visual verification

- Build the application and test targets with `xcodebuild` against an available iPhone simulator.
- Run unit and UI tests in proportion to local simulator availability.
- Capture principal screens: login, dashboard, billing list, billing detail, invoice detail, organization detail, security, and theme editor.
- Review screenshots for clipping, safe-area issues, unreadable contrast, inconsistent spacing, and Dynamic Type problems.

## API Contract Alignment

The following mapping ensures the mock app covers the PR #138 surface while keeping transport out of scope:

| API group | iOS experience |
| --- | --- |
| `auth` | Login, signup, logout, password recovery, MFA, Google/passkey placeholders |
| `profile` | Current account profile and shell identity |
| `billings` | Billing CRUD, items, recipients, reply-to, attachments, expenses, exports, communications, transfer |
| `bills` | Invoice CRUD, lifecycle, regenerate, invoice/receipt/recibo previews and ordering |
| `organizations` | Organization CRUD, members, roles, invites, MFA policy, transfers |
| `invites` | Pending invitation list, accept, and decline |
| `security` | PIX, password, TOTP, recovery codes, and passkeys |
| `api-keys` | Safe scopes, grants, creation secret, metadata update, and revoke |
| `themes` | User, organization, and billing themes, inheritance, preview, and reset |

Wire details remain isolated for later integration:

- Bearer transport and secure Keychain persistence.
- `application/problem+json` decoding into domain errors.
- Snake-case JSON conversion and RFC 3339 timestamps.
- OpenAPI-generated or hand-written transport DTOs.
- HTTP cancellation, retry, authorization expiry, and 404/403 privacy semantics.

## Implementation Sequence

The implementation plan should preserve working vertical slices:

1. Xcode project, design system, domain primitives, repository protocols, and canonical mock store.
2. Authentication shell and tab navigation.
3. Dashboard and billing list/detail.
4. Billing and invoice creation/editing/lifecycle.
5. Expenses, attachments, receipts, communications, and exports.
6. Organizations, members, invitations, and transfers.
7. Account security, passkeys, recovery codes, and integration keys.
8. Theme inheritance/editing and demonstration scenarios.
9. Accessibility, tests, simulator verification, and screenshot review.

Each slice must build before the next begins. The application should remain demonstrable throughout development.

## Acceptance Criteria

The design is implemented when all of the following are evidenced in the current workspace:

1. A native SwiftUI iOS project exists under `ios/` and builds for an available iPhone simulator.
2. The application runs without backend availability or network interaction.
3. All four primary tabs and every screen group in this specification are navigable.
4. Authentication, billing, invoice, expense, organization, invitation, security, API-key, and theme actions produce coherent in-memory changes.
5. Reset restores deterministic fixtures.
6. API-aligned domain and repository boundaries make transport replaceable without changing feature views.
7. Populated, empty, loading, recoverable-error, and permission-restricted states can be demonstrated.
8. Principal flows have automated coverage and current passing evidence.
9. Principal screens have been rendered on a simulator and visually inspected.
10. No production secrets, credentials, or real external side effects are included.
