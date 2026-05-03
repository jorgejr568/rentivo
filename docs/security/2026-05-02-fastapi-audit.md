# FastAPI Security Audit — 2026-05-02

**Auditor role:** Senior Backend Architect (high-performance Python APIs, async safety).

**Scope:** Pydantic data validation bypasses, ReDoS in user-input-facing regexes, and SQL identifier safety across `rentivo/` and `web/`. Out of scope: authn/authz logic, S3 IAM policy, Cloudflare Turnstile bypass, dependency CVEs.

**TL;DR:** No exploitable vulnerabilities found in any of the four target categories. One cosmetic SQL pattern was refactored for consistency. Four regression-guard tests were added to prevent drift.

## Findings

| # | Check | Result | CVSS 3.1 base | Vector | Event-loop impact |
|---|-------|--------|---------------|--------|-------------------|
| 1 | `ConfigDict(extra='allow')` collisions with `.dict()` / `.json()` | **None.** Only `Settings` declares an extras policy and uses `extra="ignore"` (`rentivo/settings.py:15`). All 16 `BaseModel` subclasses in `rentivo/models/` rely on the default (`extra="ignore"`). | N/A — no finding | — | None |
| 2 | `model_construct()` validation bypass | **None.** No call sites in `rentivo/`, `web/`, or `tests/`. | N/A — no finding | — | None |
| 3 | ReDoS in regexes used on user input | **None vulnerable.** Seven production regexes — five in `rentivo/pix.py:14-19` (CPF, CNPJ, email, phone, EVP), one in `rentivo/settings.py:11` (GTM ID), one in `web/routes/theme.py:30` (hex color). All anchored, none use nested quantifiers. The email pattern (`^[^@\s]+@[^@\s]+\.[^@\s]+$`) is safe because the `@` and `.` literals separate three independent `[^@\s]+` segments — backtracking cannot escalate across them. | N/A — no finding | — | None — proven by `tests/security/test_redos_safety.py` |
| 4 | Raw SQL with interpolated identifiers / values | **No SQL injection.** Two methods previously built `IN ({placeholders})` via f-string (`rentivo/repositories/sqlalchemy.py:188,393`). Inspection: `placeholders` only ever contained `:id0, :id1, ...` — bind-parameter *names* generated from `range(len(...))`, never user input. Actual IDs flowed through `params` and were properly bound by SQLAlchemy. | 0.0 — informational | N/A (not exploitable) | None |

## Remediation

| # | Action | Status |
|---|--------|--------|
| 1 | (no action — clean) | — |
| 2 | (no action — clean) | — |
| 3 | (no action — clean); added budget smoke test in `tests/security/test_redos_safety.py` to enforce linear-time matching on every CI run | Done |
| 4 | Refactored both `IN ({placeholders})` sites to `bindparam("...", expanding=True)`, matching the existing pattern in `rentivo/jobs/sqlalchemy.py:90,144` | Done |

## Regression guards

`tests/security/test_audit_guards.py` and `tests/security/test_redos_safety.py` enforce the clean state on every CI run:

- **`test_no_pydantic_extra_allow`** — fails if any production file introduces `extra='allow'`.
- **`test_no_model_construct_in_production`** — fails if any production file calls `model_construct()` / `.construct()`.
- **`test_no_fstring_text_sql_in_repositories`** — fails if any repository file passes an f-string to `text(...)`. Whole-file scan with `re.DOTALL` catches both single-line and multi-line forms (including triple-quoted `f"""..."""`).
- **`test_regex_is_linear_time_on_adversarial_input`** — fails if any production regex exceeds 100 ms on a near-match adversarial input (max-valid length + trailing disqualifier).

## CVSS rationale (event-loop priority)

The 100 ms budget chosen for the ReDoS smoke test reflects the cost of blocking a uvicorn worker on the FastAPI event loop. Hypothetical CVSS for the realistic deployment shape (every prod regex today runs behind `AuthMiddleware` on multi-worker uvicorn):

> **Vector:** `AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L` — **base score 4.3 (MEDIUM)**.
> A network-reachable, *authenticated* attacker can stall a single worker. With `--workers N > 1`, other workers continue serving traffic — partial denial of service, not total.

Worst case if a regex were ever moved to a public, single-worker endpoint:

> **Vector:** `AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` — **base score 7.5 (HIGH)**.
> Unauthenticated attacker, total worker stall, no other workers to absorb traffic — denial of service with no privilege requirement.

The 100 ms budget is set to catch the bug regardless of which deployment shape the regex ends up in.

## Re-audit triggers

Re-run this audit when any of the following lands:

- A new Pydantic model that accepts unconstrained dict input
- A new `Field(pattern=...)`, `Query(pattern=...)`, or `Path(pattern=...)`
- A new repository method or new raw `text(...)` SQL
- A bump of `pydantic`, `pydantic-settings`, or `sqlalchemy` major version

## Known follow-ups (not in scope of this audit)

- An AST-based guard that AST-walks `rentivo/`/`web/` and asserts every `re.compile(...)` callsite is registered in `tests/security/test_redos_safety.py::PRODUCTION_REGEXES`. Today, manually adding a regex without registering it is not caught — explicit imports give a tight feedback loop, but a future contributor could miss it.
