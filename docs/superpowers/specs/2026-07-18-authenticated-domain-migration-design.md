# Authenticated Domain Migration Design

**Date:** 2026-07-18

**Status:** Approved under the user's continuous-execution instruction

**Parent specification:** `2026-07-17-frontend-backend-api-key-foundation-design.md`

## Problem

The replacement preview sends every page route to React, but only authentication,
security, and API-key management were implemented. The authenticated navigation
still links to billing, invoice, organization, invite, and theme URLs. Those URLs
fall through to a `null` catch-all route, producing a blank content area after a
successful signup or login.

Signup is not failing and new accounts should not receive synthetic financial
records. A new account should see complete, useful empty-state pages with the same
PT-BR design and the actions needed to create its first organization or billing.

## Approaches Considered

### 1. Complete React and JSON API migration (selected)

Port the authenticated Jinja workflows to React and expose their existing domain
services through scoped `/api/v1` endpoints. This satisfies the original service
split, supports future mobile clients, and removes the blank-route failure at its
source. It is the largest option, but it is the only one that completes the stated
architecture.

### 2. Proxy unsupported routes to the legacy web process

This would restore screens quickly, but browser identity would cross between the
API-key cookie and the legacy session model. It would also leave customer-facing
HTML rendering inside the backend and would not provide a reusable mobile API.
This is rejected except as an emergency rollback mechanism.

### 3. Render explicit unavailable or empty placeholders

This would eliminate blank pages but would still leave creation, editing, invoice,
organization, and configuration workflows unusable. It is rejected because it
masks the missing product behavior instead of completing it.

## Scope

This migration includes all currently exposed authenticated navigation and linked
workflows:

- billing list, create, detail, edit, ownership transfer, attachments, and delete;
- invoice generation, detail, edit, status transitions, PDF regeneration,
  invoice/receipt downloads, receipt upload/reorder/delete, and bill export;
- expenses and billing communications;
- organization list, create, detail, edit, member roles/removal, invitations,
  organization MFA policy, billing transfer, ownership transfer, and delete;
- pending invitation list, acceptance, and decline;
- user, organization, and billing theme configuration and preview;
- stable not-found and load-error pages for authenticated routes.

Existing React authentication, security, and API-key management remain unchanged.
Existing domain services, repositories, storage, encryption, audit, job, PDF, and
authorization behavior remain the source of truth.

## Architecture

### Backend

FastAPI gains resource-oriented routers under `/api/v1`:

- `/billings` for billing templates and their nested resources;
- `/billings/{billing_uuid}/bills` for invoices and invoice files;
- `/organizations` for organizations, membership, invitations, and policy;
- `/invites` for the current user's pending invitations;
- `/themes` for user, organization, and billing themes.

Routes use the existing `RequestServices` container and domain services. They do
not call SQLAlchemy repositories directly. Pydantic request/response models own
validation and serialization. Money remains integer centavos in JSON; date and
datetime values use ISO 8601. File endpoints stream the existing stored artifacts.
Multipart upload endpoints retain current size, MIME, storage, and encryption
rules.

Every endpoint requires one declared API scope and then applies resource access:

- login keys receive the established first-party scopes and dynamic workspaces;
- integration keys require their selected scope and grant;
- organization resources intersect the grant with live membership and role;
- inaccessible resource identifiers return `404`;
- role or policy violations return stable `403`/`409` problem codes.

Mutations preserve CSRF checks for browser-cookie authentication, audit events,
analytics headers, queued jobs, notifications, and transaction boundaries.

### Frontend

React gains feature modules for `billings`, `bills`, `organizations`, `invites`,
and `themes`. Components reuse the existing CSS classes and copy from the Jinja
templates, with Lucide icons only where the current component system already uses
icons. Route URLs remain unchanged.

TanStack Query owns server state and invalidation. Forms use controlled React
state and the generated OpenAPI client. Shared page states cover loading, retry,
not found, forbidden, mutation progress, validation errors, destructive
confirmation, and toast feedback.

The authenticated catch-all renders a real PT-BR not-found page. No route may use
`element: null`. New-account list pages render the existing empty-state visual and
primary actions:

- `/billings/`: create the first billing;
- `/organizations/`: create an organization;
- `/invites/`: state that there are no pending invitations;
- theme pages: editable inherited/default values;
- invoice routes: reached through a billing and never presented as a blank global
  list.

## Data Flow

1. Signup or login issues the hidden 24-hour API-key cookie and bootstrap data.
2. React navigates to `/billings/`.
3. The billing list query calls `GET /api/v1/billings` with the cookie and CSRF
   context already managed by the API client.
4. FastAPI resolves the API-key principal, checks `billings:read`, computes dynamic
   personal and organization access, and calls `BillingService`.
5. React renders records or the complete empty state. Mutations send typed payloads,
   show progress, invalidate affected queries, and navigate only after success.
6. The same principal and resource intersection applies to future mobile Bearer
   clients without browser-specific domain logic.

## Error Handling

All JSON failures use the existing problem-details contract with stable codes and
request IDs. The frontend maps field errors to their controls and displays other
failures in the existing toast/panel language. Queries retain the current screen
while refreshing, abort on navigation, and expose an explicit retry action after a
terminal load failure. Downloads report expired or missing files without replacing
the current page.

Destructive actions require the existing confirmation-dialog pattern. Concurrent
deletes, ownership changes, stale memberships, invalid status transitions, and
already-answered invitations return conflict responses and trigger targeted query
refreshes.

## Testing

Backend tests exercise each schema, scope, workspace grant, live membership, role,
not-found behavior, mutation side effect, audit event, queued job, upload, and file
response while retaining 100% coverage.

Frontend tests cover every route and page state, including zero-record accounts,
success/error mutations, field validation, query invalidation, confirmation, and
responsive rendering at 100% authored-code coverage.

Playwright creates a fresh account and proves that every top-level authenticated
navigation renders meaningful content and a primary action instead of a blank
outlet. Separate seeded fixtures cover the full create/edit/generate/status/file,
organization/member/invite, and theme workflows. Desktop and mobile visual parity
baselines compare the React pages with the current Jinja design.

An application-router regression test asserts that all links emitted by the
authenticated shell resolve to non-null route elements.

## Delivery

Implementation is divided into independently reviewable slices: shared API/page
contracts, organizations and invites, billings, bills and files, themes/config,
then cross-domain E2E and visual parity. The preview remains non-production until
all slices pass. The legacy runtime remains available for parity comparison and
rollback, but replacement traffic does not proxy authenticated page rendering to
it.
