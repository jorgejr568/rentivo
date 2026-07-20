# Authenticated Domain Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every blank authenticated React route with the complete billing, invoice, organization, invite, and theme workflows backed by scoped `/api/v1` FastAPI endpoints.

**Architecture:** New resource-oriented FastAPI routers adapt the existing domain services into strict Pydantic contracts and authorize every request through the API-key principal, workspace grants, live memberships, and existing roles. React feature modules consume the generated OpenAPI client through TanStack Query while preserving the Jinja templates' PT-BR copy, URLs, CSS classes, responsive behavior, audit events, queued work, and files.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2, SQLAlchemy Core, React 19, Vite, TypeScript, React Router, TanStack Query, openapi-fetch, Vitest, Testing Library, Playwright, Docker Compose, MariaDB.

## Global Constraints

- Preserve all current authenticated URLs, PT-BR copy, CSS classes, layout, keyboard behavior, role gates, analytics, audit, file, storage, encryption, and background-job semantics.
- New accounts contain no synthetic billing data; lists render complete empty states and creation actions.
- Browser login keys remain hidden, expire after exactly 24 hours, and authenticate through the HttpOnly cookie.
- Authorization is API scope AND explicit/dynamic workspace grant AND live membership AND current domain role.
- Resources outside effective access return `404`; scope failures return stable `403` problems.
- Browser-cookie mutations require CSRF; Bearer mutations do not.
- Money is integer centavos in JSON; dates and datetimes are ISO 8601.
- Domain routes consume `RequestServices`; they never construct repositories or bypass storage/encryption abstractions.
- Backend and authored frontend coverage remain 100%.
- Use `uv run --project backend`; never bare `python`, `pip`, or `pytest`.
- Keep the legacy runtime and production routing unchanged until the full parity gate passes.

## Dependency Map

Task 1 is shared foundation. Tasks 2-5 own disjoint backend routers/schemas/tests and may run in parallel after Task 1. Task 6 integrates those routers and freezes the OpenAPI contract. Tasks 7-10 own disjoint frontend modules and may run in parallel after Task 6; Task 7 alone owns shared components and `router.tsx`. Task 11 integrates browser tests and infrastructure. Task 12 is final verification and review.

---

### Task 1: Domain Access Guards and Blank-Route Regression

**Files:**
- Create: `backend/rentivo/api/domain_access.py`
- Create: `backend/tests/api/test_domain_access.py`
- Modify: `frontend/src/app/router.test.tsx`

**Interfaces:**
- Produces: `BillingAccess`, `OrganizationAccess`, `resolve_billing_access(...)`, `resolve_bill_access(...)`, `resolve_organization_access(...)`, and `require_role(...)`.
- `BillingAccess` contains `billing`, `role`, and `principal`; `OrganizationAccess` contains `organization`, `member`, and `principal`.

- [ ] **Step 1: Write failing access and routing tests**

```python
def test_integration_key_cannot_resolve_billing_outside_effective_grants():
    with pytest.raises(ProblemException) as caught:
        resolve_billing_access(principal, services, "billing-uuid")
    assert caught.value.problem.status == 404

def test_manager_can_manage_bills_but_cannot_delete_billing():
    access = resolve_billing_access(manager_principal, services, "billing-uuid")
    require_role(access.role, {"owner", "admin", "manager"})
    with pytest.raises(ProblemException):
        require_role(access.role, {"owner", "admin"})
```

Add a parameterized router test that visits every `Topbar` URL and asserts a named page or the authenticated 404 heading is rendered. Assert no authenticated route object has `element: null`.

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/api/test_domain_access.py && npm --prefix frontend test -- --run frontend/src/app/router.test.tsx`

Expected: backend import failure and frontend blank-route assertion failure.

- [ ] **Step 3: Implement the access resolver**

```python
@dataclass(frozen=True, slots=True)
class BillingAccess:
    billing: Billing
    role: str
    principal: Principal

def resolve_billing_access(principal, services, billing_uuid):
    billing = services.billing.get_billing_by_uuid(billing_uuid)
    if billing is None or billing.id is None:
        raise ProblemException.not_found()
    require_resource_grant(principal, services, billing.owner_type, billing.owner_id)
    role = services.authorization.get_role_for_billing(principal.user.id, billing)
    if role is None:
        raise ProblemException.not_found()
    return BillingAccess(billing=billing, role=role, principal=principal)

def require_role(role: str, allowed: Collection[str]) -> None:
    if role not in allowed:
        raise ProblemException.forbidden("insufficient_role", "Você não possui permissão para esta operação.")
```

`resolve_bill_access` must resolve the parent billing first and then verify that the bill belongs to that billing before returning it. Organization resolution must require the organization grant and a live member row.

- [ ] **Step 4: Verify green**

Run: `uv run --project backend pytest -q backend/tests/api/test_domain_access.py backend/tests/api/test_principal.py && npm --prefix frontend test -- --run frontend/src/app/router.test.tsx`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/rentivo/api/domain_access.py backend/tests/api/test_domain_access.py frontend/src/app/router.test.tsx
git commit -m "test: guard authenticated domain routes"
```

### Task 2: Organizations and Invitations API

**Files:**
- Create: `backend/rentivo/api/schemas/organizations.py`
- Create: `backend/rentivo/api/routes/organizations.py`
- Create: `backend/rentivo/api/routes/invites.py`
- Create: `backend/tests/api/routes/test_organizations.py`
- Create: `backend/tests/api/routes/test_invites.py`

**Interfaces:**
- Produces collection/detail contracts with `capabilities` booleans computed by the backend.
- Login-only mutations use `ORGANIZATIONS_WRITE` or `ORGANIZATIONS_MEMBERS`; reads use `ORGANIZATIONS_READ`.

- [ ] **Step 1: Write failing route tests**

Cover zero organizations, populated lists, grant filtering, member detail, create, patch settings, delete, role update, member removal, invite creation, MFA policy update, billing transfer, pending invite list, accept, and decline. For every mutation assert CSRF, role denial, audit event, notification/job side effect, and conflict behavior.

```python
def test_new_user_lists_no_organizations(api_client):
    response = api_client.get("/api/v1/organizations")
    assert response.status_code == 200
    assert response.json() == {"items": []}

def test_create_organization_rejects_bearer_integration_key(api_client):
    response = api_client.post("/api/v1/organizations", json={"name": "Acme"}, headers=bearer_headers)
    assert response.status_code == 403
    assert response.json()["code"] == "login_token_required"
```

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_organizations.py backend/tests/api/routes/test_invites.py`

Expected: routes return 404.

- [ ] **Step 3: Implement strict schemas and routes**

Use these resource paths:

```text
GET,POST                 /api/v1/organizations
GET,PATCH,DELETE         /api/v1/organizations/{org_uuid}
PATCH,DELETE             /api/v1/organizations/{org_uuid}/members/{user_id}
POST                     /api/v1/organizations/{org_uuid}/invites
PUT                      /api/v1/organizations/{org_uuid}/mfa-policy
POST                     /api/v1/organizations/{org_uuid}/billing-transfers
GET                      /api/v1/invites
POST                     /api/v1/invites/{invite_uuid}/accept
POST                     /api/v1/invites/{invite_uuid}/decline
```

Normalize names and emails once in Pydantic validators. Return permissions such as `can_manage`, `can_invite`, and `can_create_billing`; do not reconstruct roles in React. Accept/decline must preserve organization-enforced MFA bootstrap behavior.

- [ ] **Step 4: Verify green and legacy stability**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_organizations.py backend/tests/api/routes/test_invites.py backend/tests/web/routes/test_organization.py backend/tests/web/routes/test_invite.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/rentivo/api/schemas/organizations.py backend/rentivo/api/routes/organizations.py backend/rentivo/api/routes/invites.py backend/tests/api/routes/test_organizations.py backend/tests/api/routes/test_invites.py
git commit -m "feat(api): add organizations and invitations"
```

### Task 3: Billing Templates, Expenses, Attachments, and Communications API

**Files:**
- Create: `backend/rentivo/api/schemas/billings.py`
- Create: `backend/rentivo/api/routes/billings.py`
- Create: `backend/tests/api/routes/test_billings.py`

**Interfaces:**
- Produces billing collection/detail forms, nested expense, attachment, recipient, reply-to, transfer, export, communication preview/send contracts.
- Reads use `BILLINGS_READ`; changes use the corresponding `BILLINGS_WRITE`, `EXPENSES_*`, `FILES_*`, `COMMUNICATIONS_*`, or `EXPORTS_CREATE` scope.

- [ ] **Step 1: Write failing route tests**

Test new-account empty list first, then personal and organization filtering, stats, PIX setup flags, create/update replacement semantics, validation, role matrix, transfer, delete, expense CRUD, recipient/reply-to omission versus explicit replacement, attachment validation/download/delete, communication preview/moderation/send, and exports.

```python
def test_new_user_lists_no_billings(api_client):
    response = api_client.get("/api/v1/billings")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["user_pix_incomplete"] is True

def test_create_org_billing_requires_live_membership_and_admin_role(api_client):
    response = api_client.post("/api/v1/billings", json=organization_payload)
    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"
```

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_billings.py`

Expected: route import or 404 failures.

- [ ] **Step 3: Implement resource routes**

```text
GET,POST                 /api/v1/billings
GET,PATCH,DELETE         /api/v1/billings/{billing_uuid}
POST                     /api/v1/billings/{billing_uuid}/transfer
PUT                      /api/v1/billings/{billing_uuid}/recipients
PUT                      /api/v1/billings/{billing_uuid}/reply-to
GET,POST                 /api/v1/billings/{billing_uuid}/expenses
DELETE                   /api/v1/billings/{billing_uuid}/expenses/{expense_uuid}
GET,POST                 /api/v1/billings/{billing_uuid}/attachments
GET,DELETE               /api/v1/billings/{billing_uuid}/attachments/{attachment_uuid}
POST                     /api/v1/billings/{billing_uuid}/exports
POST                     /api/v1/billings/{billing_uuid}/communications/preview
POST                     /api/v1/billings/{billing_uuid}/communications/send
```

The create/update schema carries integer-centavo line items. Optional child collections use `None` for omission and tuples for explicit replacement so omitted encrypted recipients are never erased. Downloads verify parent-child linkage before storage resolution.

- [ ] **Step 4: Verify green and legacy stability**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_billings.py backend/tests/web/routes/test_billing.py backend/tests/web/test_expense_routes.py backend/tests/web/test_communication_send.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/rentivo/api/schemas/billings.py backend/rentivo/api/routes/billings.py backend/tests/api/routes/test_billings.py
git commit -m "feat(api): add billing template workflows"
```

### Task 4: Bills, Receipts, PDFs, and Status API

**Files:**
- Create: `backend/rentivo/api/schemas/bills.py`
- Create: `backend/rentivo/api/routes/bills.py`
- Create: `backend/tests/api/routes/test_bills.py`

**Interfaces:**
- Produces nested invoice CRUD, transition capabilities, invoice/receipt files, receipt ordering, regeneration, and communication history.

- [ ] **Step 1: Write failing route tests**

Cover bill generation with fixed/variable/extras values, due-date validation, detail, edit, allowed transitions from `transitions_for`, invalid/stale transitions, role matrix, PIX gates, regeneration jobs, deletion, invoice and recibo downloads, receipt MIME/size/linkage/upload/delete/order, and inaccessible parent-child combinations.

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_bills.py`

Expected: routes return 404.

- [ ] **Step 3: Implement nested routes**

```text
GET,POST                 /api/v1/billings/{billing_uuid}/bills
GET,PATCH,DELETE         /api/v1/billings/{billing_uuid}/bills/{bill_uuid}
POST                     /api/v1/billings/{billing_uuid}/bills/{bill_uuid}/transitions
POST                     /api/v1/billings/{billing_uuid}/bills/{bill_uuid}/regenerate
GET                      /api/v1/billings/{billing_uuid}/bills/{bill_uuid}/invoice
GET                      /api/v1/billings/{billing_uuid}/bills/{bill_uuid}/recibo
GET,POST                 /api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipts
GET,DELETE               /api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipts/{receipt_uuid}
PUT                      /api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipt-order
```

Return `available_transitions` with `target`, `label`, `style`, and `requires_confirmation`. Preserve the single-render ordering for generate plus receipt upload. Stream files through storage and never expose paths.

- [ ] **Step 4: Verify green and legacy stability**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_bills.py backend/tests/web/routes/test_bill.py backend/tests/web/test_bill_transitions.py backend/tests/services/test_bill_service.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/rentivo/api/schemas/bills.py backend/rentivo/api/routes/bills.py backend/tests/api/routes/test_bills.py
git commit -m "feat(api): add invoice and receipt workflows"
```

### Task 5: Theme Configuration API

**Files:**
- Create: `backend/rentivo/api/schemas/themes.py`
- Create: `backend/rentivo/api/routes/themes.py`
- Create: `backend/tests/api/routes/test_themes.py`

**Interfaces:**
- Produces `ThemeResponse`, `ThemeUpdateRequest`, `ThemeOptionsResponse`, and a PDF preview response for user, organization, and billing scopes.

- [ ] **Step 1: Write failing tests**

Cover default/inherited values for a new account, user save/reset, organization admin enforcement, billing owner/admin enforcement, key scope/grant filtering, strict color/font validation, effective precedence, preview PDF response, CSRF, and audit state.

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_themes.py`

Expected: routes return 404.

- [ ] **Step 3: Implement routes**

```text
GET,PUT,DELETE           /api/v1/themes/user
GET,PUT,DELETE           /api/v1/themes/organizations/{org_uuid}
GET,PUT,DELETE           /api/v1/themes/billings/{billing_uuid}
POST                     /api/v1/themes/preview
```

Use `Literal` font values and `^#[0-9A-Fa-f]{6}$` colors. Return both stored and effective values so React can show inheritance without guessing.

- [ ] **Step 4: Verify green and legacy stability**

Run: `uv run --project backend pytest -q backend/tests/api/routes/test_themes.py backend/tests/web/routes/test_theme.py backend/tests/services/test_theme_service.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/rentivo/api/schemas/themes.py backend/rentivo/api/routes/themes.py backend/tests/api/routes/test_themes.py
git commit -m "feat(api): add theme configuration"
```

### Task 6: Register Domain API and Freeze OpenAPI

**Files:**
- Modify: `backend/rentivo/api/app.py`
- Modify: `backend/rentivo/constants/api_scopes.py`
- Modify: `backend/tests/api/test_openapi.py`
- Create: `backend/tests/test_api_scopes.py`
- Regenerate: `frontend/openapi.json`
- Regenerate: `frontend/src/lib/api/schema.d.ts`

**Interfaces:**
- Consumes routers from Tasks 2-5.
- Produces the typed frontend paths and deploys every now-functional integration-safe scope.

- [ ] **Step 1: Write failing OpenAPI and scope assertions**

Assert every route prefix appears in OpenAPI with unique operation IDs and that `DEPLOYED_API_SCOPES` includes only implemented integration-safe domains.

- [ ] **Step 2: Verify red**

Run: `uv run --project backend pytest -q backend/tests/api/test_openapi.py backend/tests/test_api_scopes.py`

- [ ] **Step 3: Register routers and deployed scopes**

Include routers in deterministic order and deploy billing, bills, expenses, files, communications, themes, exports, and organization-read scopes. Organization mutations remain login-only even though their routers are present.

- [ ] **Step 4: Regenerate and verify the contract**

Run: `make openapi-export openapi-generate openapi-check`

Expected: the second regeneration creates no diff.

- [ ] **Step 5: Run backend API coverage and commit**

Run: `env UV_CACHE_DIR=/tmp/rentivo-uv-cache uv run --project backend pytest -q --cov=rentivo --cov=legacy_web --cov-report=term-missing backend/tests/api backend/tests/constants`

Expected: selected suite passes with no uncovered new backend lines.

```bash
git add backend/rentivo/api/app.py backend/rentivo/constants/api_scopes.py backend/tests/api/test_openapi.py backend/tests/test_api_scopes.py frontend/openapi.json frontend/src/lib/api/schema.d.ts
git commit -m "feat(api): publish authenticated domain contract"
```

### Task 7: Shared React Page States and Complete Router

**Files:**
- Create: `frontend/src/components/PageState.tsx`
- Create: `frontend/src/components/PageState.test.tsx`
- Create: `frontend/src/components/FieldError.tsx`
- Create: `frontend/src/components/FieldError.test.tsx`
- Create: `frontend/src/features/notFound/NotFoundPage.tsx`
- Create: `frontend/src/features/notFound/NotFoundPage.test.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/app/router.test.tsx`
- Modify: `frontend/vite.config.ts`

**Interfaces:**
- Produces loading, load-error/retry, empty-state, forbidden, field-error, and authenticated not-found components.
- Owns all final route registration; feature tasks export page components without modifying `router.tsx`.

- [ ] **Step 1: Write failing component, route, and Vite proxy tests**

Assert accessible headings/live regions, stable dimensions, retry focus, every legacy URL mapping, a non-null catch-all, and `/api/v1` proxy configuration for local Vite development.

- [ ] **Step 2: Verify red**

Run: `npm --prefix frontend test -- --run frontend/src/components/PageState.test.tsx frontend/src/components/FieldError.test.tsx frontend/src/features/notFound/NotFoundPage.test.tsx frontend/src/app/router.test.tsx`

- [ ] **Step 3: Implement shared states and route table**

Register exact existing page paths and lazy-load feature pages. The catch-all must render `Página não encontrada` inside `AppShell`. Keep content headings panel-sized and preserve the current topbar.

- [ ] **Step 4: Verify green**

Run: `npm --prefix frontend test -- --run frontend/src/components frontend/src/features/notFound frontend/src/app/router.test.tsx`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components frontend/src/features/notFound frontend/src/app/router.tsx frontend/src/app/router.test.tsx frontend/vite.config.ts
git commit -m "feat(frontend): complete authenticated route handling"
```

### Task 8: Organization and Invite React Workflows

**Files:**
- Create: `frontend/src/features/organizations/OrganizationListPage.tsx`
- Create: `frontend/src/features/organizations/OrganizationListPage.test.tsx`
- Create: `frontend/src/features/organizations/OrganizationForm.tsx`
- Create: `frontend/src/features/organizations/OrganizationForm.test.tsx`
- Create: `frontend/src/features/organizations/OrganizationCreatePage.tsx`
- Create: `frontend/src/features/organizations/OrganizationCreatePage.test.tsx`
- Create: `frontend/src/features/organizations/OrganizationDetailPage.tsx`
- Create: `frontend/src/features/organizations/OrganizationDetailPage.test.tsx`
- Create: `frontend/src/features/organizations/OrganizationEditPage.tsx`
- Create: `frontend/src/features/organizations/OrganizationEditPage.test.tsx`
- Create: `frontend/src/features/organizations/OrganizationMembers.tsx`
- Create: `frontend/src/features/organizations/OrganizationMembers.test.tsx`
- Create: `frontend/src/features/invites/InviteListPage.tsx`
- Create: `frontend/src/features/invites/InviteListPage.test.tsx`

**Interfaces:**
- Exports `OrganizationListPage`, `OrganizationCreatePage`, `OrganizationDetailPage`, `OrganizationEditPage`, and `InviteListPage` for Task 7's route table.

- [ ] **Step 1: Write failing page tests**

Cover loading, fresh-account empty list, populated cards, create/edit validation, capability-hidden controls, member role/update/remove, invite, MFA, transfer, delete confirmations, accept/decline, error retry, toasts, invalidation, and keyboard focus.

- [ ] **Step 2: Verify red**

Run: `npm --prefix frontend test -- --run frontend/src/features/organizations frontend/src/features/invites`

- [ ] **Step 3: Implement pages from legacy templates**

Preserve `organization/list.html`, `create.html`, `detail.html`, and `edit.html` DOM class structure. Use generated client methods and backend `capabilities`; do not infer permissions from role strings.

- [ ] **Step 4: Verify green and 100% slice coverage**

Run: `npm --prefix frontend run test:coverage -- --run frontend/src/features/organizations frontend/src/features/invites`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/organizations frontend/src/features/invites
git commit -m "feat(frontend): migrate organization workflows"
```

### Task 9: Billing and Invoice React Workflows

**Files:**
- Create: `frontend/src/features/billings/BillingListPage.tsx`
- Create: `frontend/src/features/billings/BillingListPage.test.tsx`
- Create: `frontend/src/features/billings/BillingForm.tsx`
- Create: `frontend/src/features/billings/BillingForm.test.tsx`
- Create: `frontend/src/features/billings/BillingCreatePage.tsx`
- Create: `frontend/src/features/billings/BillingCreatePage.test.tsx`
- Create: `frontend/src/features/billings/BillingDetailPage.tsx`
- Create: `frontend/src/features/billings/BillingDetailPage.test.tsx`
- Create: `frontend/src/features/billings/BillingEditPage.tsx`
- Create: `frontend/src/features/billings/BillingEditPage.test.tsx`
- Create: `frontend/src/features/billings/RecipientFormset.tsx`
- Create: `frontend/src/features/billings/RecipientFormset.test.tsx`
- Create: `frontend/src/features/billings/AttachmentManager.tsx`
- Create: `frontend/src/features/billings/AttachmentManager.test.tsx`
- Create: `frontend/src/features/bills/BillGeneratePage.tsx`
- Create: `frontend/src/features/bills/BillGeneratePage.test.tsx`
- Create: `frontend/src/features/bills/BillDetailPage.tsx`
- Create: `frontend/src/features/bills/BillDetailPage.test.tsx`
- Create: `frontend/src/features/bills/BillEditPage.tsx`
- Create: `frontend/src/features/bills/BillEditPage.test.tsx`
- Create: `frontend/src/features/bills/BillStatusActions.tsx`
- Create: `frontend/src/features/bills/BillStatusActions.test.tsx`
- Create: `frontend/src/features/bills/ReceiptManager.tsx`
- Create: `frontend/src/features/bills/ReceiptManager.test.tsx`
- Create: `frontend/src/features/bills/CommunicationComposePage.tsx`
- Create: `frontend/src/features/bills/CommunicationComposePage.test.tsx`
- Create: `frontend/src/lib/format.ts`
- Create: `frontend/src/lib/format.test.ts`

**Interfaces:**
- Exports list/create/detail/edit billing pages and generate/detail/edit/communication bill pages.

- [ ] **Step 1: Write failing format, empty-state, form, detail, and file tests**

Cover integer-centavo formatting/parsing, fresh-account billing empty state, all dynamic form rows, subtotal, owner selection, PIX notices, stats, expenses, attachments, export, transfer/delete, bill generation/edit/detail/status, receipts/order, file downloads, communications, all errors, confirmations, invalidations, and focus.

- [ ] **Step 2: Verify red**

Run: `npm --prefix frontend test -- --run frontend/src/lib/format.test.ts frontend/src/features/billings frontend/src/features/bills`

- [ ] **Step 3: Implement billing pages**

Port the legacy template structures and replace `formset.js`, native confirms, status menu JS, and SortableJS behavior with controlled React components and the existing `ConfirmDialog`. Keep stable list keys independent of sparse backend indices. Use anchor downloads for API file URLs with same-origin cookies.

- [ ] **Step 4: Verify green and slice coverage**

Run: `npm --prefix frontend run test:coverage -- --run frontend/src/lib/format.test.ts frontend/src/features/billings frontend/src/features/bills`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/billings frontend/src/features/bills frontend/src/lib/format.ts frontend/src/lib/format.test.ts
git commit -m "feat(frontend): migrate billing and invoice workflows"
```

### Task 10: Theme React Workflow

**Files:**
- Create: `frontend/src/features/themes/ThemeEditorPage.tsx`
- Create: `frontend/src/features/themes/ThemeEditorPage.test.tsx`
- Create: `frontend/src/features/themes/useThemePreview.ts`
- Create: `frontend/src/features/themes/useThemePreview.test.ts`

**Interfaces:**
- Exports one route-aware editor for user, organization, and billing themes.

- [ ] **Step 1: Write failing tests**

Cover new-account defaults, inherited/stored values, six color swatches, two font selects, validation, save/reset, capability gates, 300 ms debounced preview cancellation, PDF object URL cleanup, retry, and keyboard behavior.

- [ ] **Step 2: Verify red**

Run: `npm --prefix frontend test -- --run frontend/src/features/themes`

- [ ] **Step 3: Implement editor and preview hook**

Preserve `theme/edit.html` classes and dimensions. Use native color inputs plus visible swatches, generated API payloads, and an unframed PDF iframe. Revoke replaced object URLs.

- [ ] **Step 4: Verify green and slice coverage**

Run: `npm --prefix frontend run test:coverage -- --run frontend/src/features/themes`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/themes
git commit -m "feat(frontend): migrate theme configuration"
```

### Task 11: Real New-Account E2E and Visual Parity

**Files:**
- Modify: `frontend/e2e/support/api-mocks.ts`
- Create: `frontend/e2e/domain-empty-states.spec.ts`
- Create: `frontend/e2e/domain-workflows.spec.ts`
- Modify: `frontend/e2e/visual-parity.spec.ts`
- Create: reviewed snapshots under `frontend/e2e/snapshots/{platform}/{desktop,mobile}/`
- Create: `frontend/e2e/real-stack.spec.ts`
- Modify: `frontend/playwright.config.ts`
- Modify: `.github/workflows/test-pr.yaml`
- Modify: `docs/runbooks/frontend-backend-preview.md`

**Interfaces:**
- Adds deterministic mocked visual tests and a separate non-intercepted Compose smoke project.

- [ ] **Step 1: Write failing browser tests**

The empty-state test must authenticate as a fixture with no records and visit every top-level navigation link. Assert each page has a heading plus its expected empty/config action and that `<main>` has visible nonzero content. The real-stack test signs up a unique account, verifies `/billings/`, creates its first billing and organization, reloads, logs out/in, and confirms a second account receives `404` for those UUIDs.

- [ ] **Step 2: Verify red**

Run: `npm --prefix frontend run e2e -- domain-empty-states.spec.ts real-stack.spec.ts`

Expected: missing mock handlers/pages and blank content failures.

- [ ] **Step 3: Complete mocks, CI stack, accessibility, and reviewed baselines**

Do not intercept requests in the real-stack project. Start migrated Compose services with a fresh MariaDB volume, run migrations, and collect API/proxy logs on failure. Add desktop/mobile snapshots for each list and editor empty state, then inspect every image before committing.

- [ ] **Step 4: Verify browser suites**

Run: `npm --prefix frontend run e2e` and repeat with the repository's Linux Playwright container command from CI.

Expected: mocked, accessibility, visual, and real-stack projects all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e frontend/playwright.config.ts .github/workflows/test-pr.yaml docs/runbooks/frontend-backend-preview.md
git commit -m "test: cover authenticated domain parity"
```

### Task 12: Full Verification and Review

**Files:**
- Modify only files required by discovered regressions.

- [ ] **Step 1: Run formatting, lint, generated-contract, migration, and unit coverage gates**

```bash
uv run --project backend ruff check backend
uv run --project backend ruff format --check backend
env UV_CACHE_DIR=/tmp/rentivo-uv-cache uv run --project backend pytest -n auto -q
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run test:coverage
npm --prefix frontend run build
make openapi-check
uv run --project backend alembic heads
```

Expected: backend reports 100% total coverage, frontend reports 100% statements/branches/functions/lines, generated files are current, and Alembic has one head.

- [ ] **Step 2: Run browser, Compose, and image gates**

Run the complete macOS and official Linux Playwright suites, visual stress repeats, local and remote Compose config validation, and all legacy/API/worker/frontend image builds.

- [ ] **Step 3: Reproduce the original report in the in-app browser**

Create a temporary local account, verify nonblank `/billings/`, `/organizations/`, `/invites/`, `/themes/user`, and `/security` pages at desktop and mobile widths, create the first billing and organization, and remove only the dedicated test account through supported cleanup tooling.

- [ ] **Step 4: Request broad code review**

Review the full branch diff for authorization leaks, parent-child file access, destructive replacement, audit/job regressions, stale queries, accessibility, and visual parity. Resolve every Critical or Important finding and rerun its covering tests.

- [ ] **Step 5: Commit final fixes, push, and update the existing PR**

```bash
git add backend frontend .github/workflows/test-pr.yaml docs/runbooks/frontend-backend-preview.md
git commit -m "fix: complete authenticated domain parity"
git push origin codex/frontend-backend-api-key-foundation
```

Leave the pull request open for human merge.
