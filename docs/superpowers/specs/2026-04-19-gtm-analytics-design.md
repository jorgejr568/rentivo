# Google Tag Manager Analytics — Design Spec

**Status:** Approved 2026-04-19
**Author:** Jorge Junior (brainstormed with Claude)
**Scope:** Add GTM-gated analytics to the Rentivo FastAPI web app with comprehensive tracking of usage, pain points, issues, and performance.

---

## 1. Goals

1. Give the marketing team rich, actionable telemetry on what users do, where they struggle, where things break, and where they wait.
2. Zero footprint when disabled — an empty `RENTIVO_GTM_CONTAINER_ID` produces no network calls, no script tags, no cookies, no test pollution.
3. LGPD-compliant out of the gate for an authenticated B2B SaaS.
4. Maintain Rentivo conventions: no new build system, vendor-light, `.venv/bin/pytest` passes in parallel.

## 2. Non-goals / deferred

Explicitly **out of scope** for this PR; tracked as follow-ups in project memory (`project_gtm_deferred_followups.md`):

1. User-level opt-out toggle on `/security`.
2. `/privacy` policy page.
3. Content-Security-Policy headers.
4. `dead_click` detection.
5. Server-side GTM (sGTM) proxy.

## 3. Configuration

### 3.1 Environment variables

| Var | Type | Default | Purpose |
|-----|------|---------|---------|
| `RENTIVO_GTM_CONTAINER_ID` | `str` | `""` | GTM container ID (`GTM-XXXXXXX`). Empty string fully disables analytics. |
| `RENTIVO_ENVIRONMENT` | `str` | `"production"` | `production` \| `staging` \| `dev`. Populates `environment` in dataLayer so marketing can filter. |

### 3.2 Settings validation

Extend `rentivo/settings.py`:

```python
from pydantic import field_validator

class Settings(BaseSettings):
    # ... existing ...
    gtm_container_id: str = ""
    environment: str = "production"

    @field_validator("gtm_container_id")
    @classmethod
    def _validate_gtm_id(cls, v: str) -> str:
        if v and not v.startswith("GTM-"):
            raise ValueError("RENTIVO_GTM_CONTAINER_ID must start with 'GTM-' or be empty")
        return v

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, v: str) -> str:
        if v not in ("production", "staging", "dev"):
            raise ValueError("RENTIVO_ENVIRONMENT must be one of: production, staging, dev")
        return v
```

## 4. Architecture

### 4.1 Module layout

**Added:**
- `web/analytics.py` — all analytics helpers (hash, page context builder, one-shot event push/pop).
- `web/static/core/js/tracking.js` — client-side automatic listeners (~300 lines, vanilla JS, one IIFE).
- `web/static/core/vendor/web-vitals.iife.js` — vendored `web-vitals@4` IIFE build.
- `tests/web/test_gtm.py` — disabled-mode, enabled-mode, PII-absence, flash-analytics round-trip tests.

**Modified:**
- `rentivo/settings.py` — two new fields + validators.
- `web/app.py` — register `gtm_container_id` and `environment` as template globals.
- `web/deps.py` — `render()` calls `build_page_context()` and drains `pop_pending_events()` into template context.
- `web/templates/base.html` — conditional GTM loader, noscript iframe, initial-push block, tracking scripts.
- `web/flash.py` — companion `push_event()` / `pop_events()` API mirroring flash messages.
- `web/routes/billing.py`, `web/routes/bill.py`, `web/routes/organization.py`, `web/routes/invite.py`, `web/routes/security.py`, `web/auth.py` — instrument successful state-changing handlers with `push_event(request, {...})` calls before redirects.
- `CLAUDE.md` — new "Analytics" section.
- `.env.example` (if exists; otherwise skip).

### 4.2 `web/analytics.py`

```python
import hmac, hashlib
from typing import Any
from starlette.requests import Request
from rentivo.settings import settings

HASH_LEN = 16

def analytics_hash(value: Any) -> str | None:
    """HMAC-SHA256 first 16 hex chars, using app secret key as salt."""
    if value in (None, ""):
        return None
    key = settings.secret_key.encode()
    return hmac.new(key, str(value).encode(), hashlib.sha256).hexdigest()[:HASH_LEN]

PAGE_TYPE_MAP: dict[str, str] = {
    # template stem (without .html) -> page_type
    "billing/list": "list",
    "billing/detail": "detail",
    "billing/create": "form",
    "billing/edit": "form",
    "bill/generate": "form",
    "bill/detail": "detail",
    "bill/edit": "form",
    "organization/list": "list",
    "organization/detail": "detail",
    "organization/create": "form",
    "organization/edit": "form",
    "invite/list": "list",
    "security/index": "dashboard",
    "security/totp_setup": "form",
    "security/recovery_codes": "detail",
    "theme/edit": "form",
    "login": "auth",
    "signup": "auth",
    "mfa_verify": "auth",
    "landing": "landing",
    "404": "error",
}

def _infer_page_type(template_stem: str) -> str:
    if template_stem in PAGE_TYPE_MAP:
        return PAGE_TYPE_MAP[template_stem]
    if template_stem.endswith(("/create", "/edit", "/generate")):
        return "form"
    if template_stem.endswith("/list"):
        return "list"
    if template_stem.endswith("/detail"):
        return "detail"
    return "other"

def build_page_context(request: Request, template_name: str, ctx: dict) -> dict | None:
    """Build the initial `dataLayer.push({...})` payload. Returns None if GTM disabled."""
    if not settings.gtm_container_id:
        return None
    stem = template_name.removesuffix(".html")
    section = stem.split("/")[0] if "/" in stem else "root"
    user_id = request.session.get("user_id")
    return {
        "event": "page_context",
        "page_type": _infer_page_type(stem),
        "page_section": section,
        "page_template": stem,
        "user_status": "authenticated" if user_id else "anonymous",
        "user_id_hash": analytics_hash(user_id),
        "locale": "pt-BR",
        "environment": settings.environment,
        "app_version": ctx.get("asset_version", ""),
        "request_id": getattr(request.state, "request_id", None),
    }

SESSION_KEY = "_analytics_events"

def push_event(request: Request, event: dict) -> None:
    """Queue a one-shot dataLayer event for the next rendered page (flash-style)."""
    if not settings.gtm_container_id:
        return
    events = request.session.setdefault(SESSION_KEY, [])
    events.append(event)

def pop_events(request: Request) -> list[dict]:
    """Drain queued one-shot events. Called by render() once per page."""
    return request.session.pop(SESSION_KEY, [])
```

Notes:
- `push_event` is a no-op when GTM is disabled — call sites don't need to check the flag.
- `pop_events` drains unconditionally so queued events don't leak to an unrelated later page if the env var flips.
- `request.state.request_id` is already set by `RequestContextMiddleware` (see `web/middleware/logging.py`).

### 4.3 `render()` extension

In `web/deps.py`:

```python
from web.analytics import build_page_context, pop_events

def render(request: Request, template_name: str, context: dict | None = None) -> Response:
    ctx = dict(context or {})
    # ... existing common-context merge ...
    ctx["gtm_initial_push"] = build_page_context(request, template_name, ctx)
    ctx["gtm_pending_events"] = pop_events(request)
    return templates.TemplateResponse(request, template_name, ctx)
```

### 4.4 `base.html` snippet

Placement: the initial `dataLayer.push` + pending-events pushes run **synchronously and inline**, before the async GTM loader, so any GA4 / GTM tag that fires on `gtm.js` has full page context.

```jinja
{# inside <head>, after the <meta name="viewport"> tag #}
{% if gtm_container_id %}
<script>
window.dataLayer = window.dataLayer || [];
{% if gtm_initial_push %}dataLayer.push({{ gtm_initial_push|tojson }});{% endif %}
{% if gtm_pending_events %}{% for evt in gtm_pending_events %}dataLayer.push({{ evt|tojson }});{% endfor %}{% endif %}
</script>
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','{{ gtm_container_id }}');</script>
<!-- End Google Tag Manager -->
{% endif %}
```

First child of `<body>`:

```jinja
{% if gtm_container_id %}
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={{ gtm_container_id }}"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
{% endif %}
```

Before `{% endblock %}`-equivalent end of body (after existing `app.js`):

```jinja
{% if gtm_container_id %}
<script src="{{ url_for('static', path='core/vendor/web-vitals.iife.js') }}?v={{ asset_version }}"></script>
<script src="{{ url_for('static', path='core/js/tracking.js') }}?v={{ asset_version }}"></script>
{% endif %}
```

### 4.5 `tracking.js` responsibilities

Single IIFE that no-ops when `window.dataLayer` is absent. Structure:

```js
(function () {
  if (!window.dataLayer) return;
  const dl = window.dataLayer;
  const push = (evt) => dl.push(evt);

  // --- helpers ---
  // pathFor(el): short selector string for rage/dead click correlation
  // sanitizeUrl(url): strip UUIDs/ULIDs/numeric IDs → ":uuid" / ":id"
  // throttle(fn, n): limit per-page firing
  // elementText(el): innerText trimmed to 80 chars

  // --- form tracking (delegated) ---
  // form_start on first focus/input within a <form>
  // form_submit on submit
  // form_field_error: on load, scan .invalid-feedback server-rendered errors
  // form_abandon on beforeunload if form_start fired and no form_submit

  // --- click tracking (delegated on document) ---
  // button_click for <button>, [role=button]
  // link_click for <a[href]>, branched:
  //   - internal / outbound / download / mailto / tel
  //   - download_click with file_kind (invoice/receipt) if path matches
  // dropdown_open/close observe existing topbar dropdown

  // --- file upload tracking ---
  // input[type=file] change: file_upload_start per file (size/type)
  // form submit containing file input: record startTime; postNav web-vitals onTTFB or pagehide
  //   → file_upload_complete (success) or file_upload_error (error_code derived from page)

  // --- performance ---
  // PerformanceObserver longtask: long_task (throttle 10/page)
  // After web-vitals LCP/TTFB callbacks, emit slow_page/interaction_slow/layout_shift_bad when rating==='poor'
  // (web-vitals.js in base.html already pushes `web_vital` for each metric)

  // --- errors ---
  // window.addEventListener('error', e => push({event:'js_error',...}))
  // window.addEventListener('unhandledrejection', e => push({event:'promise_rejection',...}))
  // monkeypatch fetch: on non-2xx or throw → network_error {url_path:sanitizeUrl, status, method, duration_ms}
  // XMLHttpRequest.prototype.send wrap: same

  // --- engagement ---
  // scroll_depth at 25/50/75/100% (once each)
  // page_engaged after 15s of activity (mousemove/scroll/keydown/click reset idle timer)
  // page_idle after 30s of no activity
  // time_on_page on pagehide/visibilitychange(hidden)

  // --- rage clicks ---
  // Ring buffer of last 3 click timestamps + element paths
  // If 3 clicks on same path within 1000ms → rage_click
})();
```

web-vitals init runs inside the vendored IIFE or the base template inline — **using the vendored IIFE build** means a small adapter in `tracking.js` that calls `webVitals.onLCP(...)` etc. (global exposed by the IIFE bundle).

### 4.6 Route instrumentation

Pattern: right before `return RedirectResponse(...)` on successful state changes, call `push_event(request, {...})`. The event fires on the destination page's initial render.

| Route | Event | Key params |
|---|---|---|
| `POST /signup` (success) | `rentivo_signup_completed` | — |
| `POST /login` (success) | `rentivo_login_success` | `via`: `"password"` \| `"mfa"` \| `"passkey"` |
| `POST /login` (failure — re-renders same page) | `rentivo_login_failed` | `reason`: `"bad_credentials"` \| `"locked"` |
| `POST /logout` | `rentivo_logout` | — |
| `POST /mfa-verify` (success) | `rentivo_mfa_verify_success` | — |
| `POST /billings/create` | `rentivo_billing_created` | `billing_uuid_hash`, `item_count`, `has_pix` |
| `POST /billings/{uuid}/edit` | `rentivo_billing_edited` | `billing_uuid_hash`, `fields_changed` |
| `POST /billings/{uuid}/delete` | `rentivo_billing_deleted` | `billing_uuid_hash` |
| `POST /billings/{uuid}/transfer` | `rentivo_billing_transferred` | `billing_uuid_hash` |
| `POST /billings/{uuid}/bills/generate` | `rentivo_bill_generated` | `billing_uuid_hash`, `bill_uuid_hash`, `reference_month`, `line_item_count`, `total_amount_brl` (reais rounded), `receipt_count` |
| `POST /billings/{uuid}/bills/{id}/edit` | `rentivo_bill_edited` | `bill_uuid_hash`, `fields_changed` |
| `POST /billings/{uuid}/bills/{id}/regenerate-pdf` | `rentivo_bill_regenerated` | `bill_uuid_hash` |
| `POST /billings/{uuid}/bills/{id}/change-status` | `rentivo_bill_status_changed` | `bill_uuid_hash`, `new_status` |
| `POST /billings/{uuid}/bills/{id}/delete` | `rentivo_bill_deleted` | `bill_uuid_hash` |
| `POST /.../receipts/upload` | `rentivo_receipt_uploaded` | `bill_uuid_hash`, `count`, `total_bytes` |
| `POST /.../receipts/{id}/delete` | `rentivo_receipt_deleted` | `bill_uuid_hash` |
| `GET /.../invoice` | `rentivo_invoice_downloaded` | `bill_uuid_hash` (server-pushed to next dataLayer OR emitted client-side on the link click — we use client-side `download_click` instead to avoid noise from prefetches) |
| `POST /security/change-password` | `rentivo_password_changed` | — |
| `POST /security/totp/confirm` | `rentivo_mfa_enabled` | `method`: `"totp"` |
| `POST /security/totp/disable` | `rentivo_mfa_disabled` | — |
| `POST /security/passkeys/register/complete` | `rentivo_passkey_added` | — |
| `POST /security/passkeys/{id}/delete` | `rentivo_passkey_removed` | — |
| `POST /security/recovery-codes/regenerate` | `rentivo_recovery_codes_regenerated` | — |
| `POST /organizations/create` | `rentivo_organization_created` | `org_id_hash` |
| `POST /organizations/{id}/invite` | `rentivo_invite_sent` | `org_id_hash` |
| `POST /invites/{id}/accept` | `rentivo_invite_accepted` | `org_id_hash` |
| `POST /invites/{id}/decline` | `rentivo_invite_declined` | — |
| `POST /themes/...` | `rentivo_theme_changed` | `scope`: `"user"` \| `"billing"` |

**Invoice download** is tracked client-side via `download_click` (from `tracking.js`) rather than server-side, because:
- The GET `/invoice` route returns FileResponse/Redirect — no chance to `render()` a destination page.
- Client-side captures both S3-redirect and local-file cases uniformly.

## 5. Event taxonomy reference

See `tracking.js` inline comments for exhaustive parameter lists. Summary table:

| Pillar | Events |
|---|---|
| **Page context** | `page_context` (initial push per page) |
| **Using** | `form_start`, `form_submit`, `button_click`, `link_click`, `outbound_link_click`, `download_click`, `dropdown_open/close`, `file_upload_start/complete`, `scroll_depth`, `page_engaged`, `page_idle`, `time_on_page`, `rentivo_*` business events |
| **Suffering** | `form_submit_error`, `form_field_error`, `form_abandon`, `rage_click`, `js_error`, `promise_rejection` |
| **Issues** | `network_error`, `file_upload_error` |
| **Waiting** | `web_vital` (LCP/INP/CLS/TTFB/FCP), `slow_page`, `interaction_slow`, `layout_shift_bad`, `long_task`, `slow_form_submit` |

## 6. Privacy / LGPD

**Legal basis:** Legitimate interest (LGPD art. 7 IX) for authenticated B2B SaaS product analytics. Not marketing retargeting.

**Hashing:** Server-side HMAC-SHA256 with `settings.secret_key` as the salt, first 16 hex chars. Applied to `user_id`, `organization_id`, `billing.uuid`, `bill.uuid`.

**Forbidden in dataLayer** (enforced by code review + PII-absence test):

| Field | Why |
|---|---|
| username | User-chosen identifier, potentially PII |
| email | Direct PII |
| PIX key | Can be CPF/CNPJ/phone/email — LGPD sensitive |
| PIX merchant name / city | Identifies the user |
| Bill item descriptions | Free-text, may name tenants |
| Receipt filenames | User-chosen, may contain names/CPF |
| Organization name | May be a person's name |
| Raw UUIDs | Linkable to business records |
| Individual amounts on per-user events (aggregate in GA4 OK) | Financial surveillance concern |

**URL sanitization** for `network_error` / any pushed URL:
- `/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/` → `:uuid`
- `/\b[0-9A-HJKMNP-TV-Z]{26}\b/` → `:ulid`
- `/\/\d+(?=\/|$)/` → `/:id`

## 7. Testing

**File:** `tests/web/test_gtm.py`.

**Classes:**

1. `TestGTMDisabled` — with `gtm_container_id=""`:
   - `test_snippet_absent` — `googletagmanager.com`, `dataLayer`, `GTM-` strings absent from `/`, `/login`, `/billings/`.
   - `test_push_event_is_noop` — `push_event(request, {...})` does not mutate `request.session`.

2. `TestGTMEnabled` — with `gtm_container_id="GTM-TEST123"`:
   - `test_loader_renders` — loader + noscript with correct ID.
   - `test_initial_push_anonymous` — `/login` has `user_status: "anonymous"`, `user_id_hash: null`.
   - `test_initial_push_authenticated` — `/billings/` has `user_status: "authenticated"`, hash is 16 hex chars.
   - `test_pii_absent` — slice initial-push block; `username`, `email`, raw user ID absent.
   - `test_flash_event_round_trip` — POST a billing create, follow redirect, assert `rentivo_billing_created` appears in pushed events on destination page.
   - `test_page_type_inferred` — `/billings/` → `list`, `/billings/create` → `form`, etc.

3. `TestAnalyticsHash`:
   - `test_deterministic` — same input → same output.
   - `test_different_secrets_differ` — monkeypatching secret changes hash.
   - `test_none_and_empty_return_none`.
   - `test_length_is_16` — always 16 hex chars when input non-empty.

**Run:** `.venv/bin/python -m pytest -n auto tests/web/test_gtm.py`.

## 8. Rollout

1. **PR 1 (this one)** — ship with `RENTIVO_GTM_CONTAINER_ID=""` in all environments. Tests pass. Zero behavior change.
2. **Post-merge** — set `RENTIVO_GTM_CONTAINER_ID=GTM-STAGING` in staging, validate in GTM Preview.
3. **Production flip** — set prod container ID. Monitor GA4 for event volume anomalies.
4. **Follow-ups** (separate PRs) — see `Non-goals` §2.

## 9. Risks

| Risk | Mitigation |
|---|---|
| PII leaks into dataLayer | Allowlisted payload construction in `build_page_context` + `push_event` sites reviewed; PII-absence test |
| web-vitals CDN dependency | Vendored locally — no runtime external dep |
| GA4 double-counts page_view | We do NOT push `event: 'pageview'`; GA4 auto-fires on `gtm.dom`/`gtm.load`; our initial event name is `page_context` |
| Session size bloat from `pending_analytics` | `pop_events` drains every render; each event is a small dict |
| GTM slowdown on slow connections | Loader is `async`; non-blocking |
| Bad GTM ID breaks page | Pydantic validator rejects at boot; template still renders loader only when var set |
| Tests hit Google servers | `TestClient` doesn't execute JS — nothing to mock |

## 10. Open questions

None at time of writing. All approach decisions signed off 2026-04-19.
