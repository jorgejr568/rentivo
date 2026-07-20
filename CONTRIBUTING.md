# Contributing to Rentivo

Thanks for contributing! This guide covers the workflow; for environment setup see [docs/development.md](docs/development.md).

## TL;DR checklist

1. Fork / branch from `main`.
2. `make install && cp .env.example .env && cp .env.db.example .env.db && make compose-dev`
3. Write tests first where practical - **coverage must stay at 100%**.
4. `make lint && make test`; for frontend changes also run `make openapi-check && make frontend-test-cov && make frontend-build`.
5. Open a PR with a [Conventional Commit](https://www.conventionalcommits.org/) title and fill out every section of the PR template.

## Code conventions

- The browser UI is React/Vite under `frontend/src`; the JSON API is FastAPI under `backend/rentivo/api`.
- Code, comments, and identifiers in **English**; all customer-facing React, PDF, and email text in **PT-BR**.
- Money is stored as **centavos (int)** - never floats. Format with `rentivo.models.format_brl()`.
- Currency is **BRL (R$)**.
- Keep the repository / storage / encryption / cache abstractions intact — backends must stay swappable.
- Dependencies are managed with **uv**: edit `backend/pyproject.toml`, run `uv lock`, commit `uv.lock`. Never bare `pip`/`python`/`pytest` - use `uv run --project backend ...`.
- Lint and formatting are enforced by ruff (`make fmt` to fix).

## Tests

- `make test` runs the suite in parallel; it must pass with **100% coverage** (`fail_under = 100`). New code needs tests or an explicit `# pragma: no cover` with justification.
- Most backend tests use in-memory SQLite. Temporal contracts start an ephemeral Temporal test server, and MariaDB CI covers migrations plus database-specific concurrency behavior.
- API mutation tests use the CSRF helpers and fixtures in `backend/tests/api/conftest.py`.
- `make frontend-test-cov` enforces 100% coverage for authored React code; `make openapi-check` verifies the committed FastAPI snapshot and generated TypeScript contract.
- `make e2e` runs Playwright workflows and visual parity. Use `make e2e-update` only after reviewing and approving an intentional UI difference.

## Database migrations

- Generate revisions with `uv run --project backend alembic -c backend/alembic.ini revision -m "description"` — **never hand-write revision IDs**.
- Migrations that drop or rename columns are breaking changes (see Versioning below).

## Commits & pull requests

- PR titles and merge commits follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `perf:`, `refactor:`, `chore:`, `docs:`, `test:`, `ci:`, `build:`, with optional scope (`feat(web): ...`). Breaking changes carry a `BREAKING CHANGE:` footer.
- Fill out **every** section of [.github/pull_request_template.md](.github/pull_request_template.md) — summary (lead with the why), what changed, test plan, screenshots for UI changes, config/deployment notes, risk & rollback.
- CI on PRs (`test-pr.yaml`) runs the `backend`, `frontend`, `e2e`, `migrations`, `compose-config`, `functional-stack`, `production-startup`, and `security-scan` jobs behind `release-gate`. The `production-images` matrix then builds API, worker, and frontend locally with `load: true`, scans each exact SHA tag, and `all-checks-pass` requires both phases.
- The functional stack uses CI-only local email/storage/encryption backends. The production-startup job exercises production setting validation; deploy automation alone validates reachability of real production integrations.

## Merging policy — human-only

**Merges to `main` are performed by a human, never by an automated agent.** Agents and CI bots **open** pull requests and stop there; a human reviews and clicks merge.

This is enforced both behaviorally and at the repo level:

- `main` is a protected branch: **direct pushes are blocked for everyone (including admins)** - all changes land through a PR.
- **Auto-merge is disabled** repo-wide, so no agent can queue a merge to happen automatically.
- Force-pushes and branch deletion on `main` are blocked.

Rules for everyone, especially automated contributors:

- Never use the merge button, `gh pr merge`, squash/rebase/auto-merge, or any equivalent to land a PR. Open the PR and request human review.
- Never push directly to `main` (or any protected branch) to bypass the PR flow.
- If a task says "merge X", read it as "open a PR for X and request review". Only a human maintainer performs the actual merge.

See [AGENTS.md](AGENTS.md) for the agent-facing version of this rule.

## Versioning & releases

Rentivo follows [SemVer 2.0.0](https://semver.org/); the release history lives in [CHANGELOG.md](CHANGELOG.md) (Keep a Changelog format). Releases are cut by maintainers: version bump + changelog PR (`chore(release): vX.Y.Z`), then a `vX.Y.Z` tag triggers the release workflow. When unsure which component to bump, bump higher.

## Security issues

Please do **not** open public issues for vulnerabilities - see [SECURITY.md](SECURITY.md).
