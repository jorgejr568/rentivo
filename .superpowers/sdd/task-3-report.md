# Task 3 Report: Billing Templates, Expenses, Attachments, and Communications API

## Status

DONE. The billing-template API was implemented with grant-aware reads, live
organization authorization, role-scoped mutations, optional child replacement,
parent-child file checks, and legacy service/audit/job behavior preserved.

## Files Changed

- `backend/rentivo/api/schemas/billings.py`
  - Added strict request/response contracts for billing templates, owners, line
    items in integer centavos, stats, contacts, expenses, attachment metadata,
    exports, and communication preview/send flows.
  - Preserved omission semantics with `None` and explicit replacement semantics
    with tuples for recipients, reply-to contacts, and line items.
- `backend/rentivo/api/routes/billings.py`
  - Added the Task 3 `/billings` collection/detail, transfer, contact, expense,
    attachment, export, and communication endpoints.
  - Intersected list results with API-key grants and live authorization roles.
  - Required a live organization admin for organization-owned creation.
  - Checked attachment and communication children against their requested parent
    before storage resolution or dispatch.
  - Preserved CSRF, scopes, role checks, analytics, audit events, cleanup jobs,
    notifications, moderation, and template-save behavior.
- `backend/tests/api/routes/test_billings.py`
  - Added 69 focused tests covering contracts, filtering, authorization, role
    matrices, validation, replacement semantics, parent scoping, files,
    moderation, communication fan-out, exports, and OpenAPI strictness.
- `.superpowers/sdd/task-3-report.md`
  - Replaced the stale report at the requested path with this Task 3 evidence.

No forbidden application-registration, scope-constant, OpenAPI artifact,
frontend, or other task files were modified.

## RED Evidence

### Initial Route RED

Command:

```text
env UV_CACHE_DIR=/tmp/rentivo-uv-cache uv run --project backend pytest -q backend/tests/api/routes/test_billings.py
```

Observed expected collection failure before implementation:

```text
ModuleNotFoundError: No module named 'rentivo.api.routes.billings'
1 error, exit code 2, in 0.76s
```

### Attachment Analytics RED

During parity review, the upload contract was tightened with an analytics-header
assertion before changing the route.

Command:

```text
env UV_CACHE_DIR=/tmp/rentivo-uv-cache uv run --project backend pytest -q backend/tests/api/routes/test_billings.py::test_attachment_collection_upload_and_metadata_never_expose_storage_key
```

Observed expected failure:

```text
KeyError: 'x-rentivo-analytics-event'
1 failed in 0.87s
```

The route then added the legacy-parity upload analytics header; the same test
passed (`1 passed in 0.67s`).

## GREEN Evidence

### New-Line Coverage

Command:

```text
env UV_CACHE_DIR=/tmp/rentivo-uv-cache uv run --project backend pytest -q --cov=rentivo.api.routes.billings --cov=rentivo.api.schemas.billings --cov-report=term-missing --cov-fail-under=100 backend/tests/api/routes/test_billings.py
```

Result:

```text
backend/rentivo/api/routes/billings.py      329      0   100%
backend/rentivo/api/schemas/billings.py     181      0   100%
TOTAL                                       510      0   100%
69 passed, 1 warning in 9.72s
```

### Required Focused and Unchanged Legacy Tests

Command:

```text
env UV_CACHE_DIR=/tmp/rentivo-uv-cache uv run --project backend pytest -q backend/tests/api/routes/test_billings.py backend/tests/web/routes/test_billing.py backend/tests/web/test_expense_routes.py backend/tests/web/test_communication_send.py
```

Result:

```text
133 passed, 1 warning in 35.60s
```

The named unchanged legacy tests had also passed before edits (`64 passed, 1
warning in 32.21s`).

### Additional Legacy Parity

Command:

```text
env UV_CACHE_DIR=/tmp/rentivo-uv-cache uv run --project backend pytest -q backend/tests/web/routes/test_billing_attachments.py backend/tests/web/routes/test_bill_export.py backend/tests/web/test_billing_recipients.py backend/tests/web/test_billing_reply_to.py backend/tests/web/test_communication_compose.py backend/tests/web/test_communication_moderation.py
```

Result:

```text
47 passed, 1 warning in 23.81s
```

### Static Checks

```text
env UV_CACHE_DIR=/tmp/rentivo-uv-cache uv run --project backend ruff format --check backend/rentivo/api/routes/billings.py backend/rentivo/api/schemas/billings.py backend/tests/api/routes/test_billings.py
3 files already formatted

env UV_CACHE_DIR=/tmp/rentivo-uv-cache uv run --project backend ruff check backend/rentivo/api/routes/billings.py backend/rentivo/api/schemas/billings.py backend/tests/api/routes/test_billings.py
All checks passed!
```

## Commit

This implementation and report are committed together as:

```text
feat(api): add billing template workflows
```

The immutable commit hash is reported in the task handoff because a commit cannot
contain its own hash.

## Concerns

- No Task 3 correctness concerns remain after the focused coverage and legacy
  parity runs.
- `backend/rentivo/api/app.py` was intentionally not modified; router registration
  belongs to the integration task and was explicitly outside this task's files.
- Test runs emit the existing Starlette `TestClient`/`httpx` deprecation warning.
- Concurrent task files were present in the worktree and index. They were left
  untouched and excluded from this task's scoped commit.
