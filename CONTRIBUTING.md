# Contributing to Rentivo

Thanks for contributing! This guide covers the workflow; for environment setup see [docs/development.md](docs/development.md).

## TL;DR checklist

1. Fork / branch from `main`.
2. `make install && cp .env.example .env && docker compose up -d db && make migrate`
3. Write tests first where practical — **coverage must stay at 100%**.
4. `make lint && make test` (pre-commit hooks run these on every commit anyway).
5. Open a PR with a [Conventional Commit](https://www.conventionalcommits.org/) title and fill out every section of the PR template.

## Code conventions

- Code, comments, and identifiers in **English**; all customer-facing text (web templates, PDFs, emails) in **PT-BR**.
- Money is stored as **centavos (int)** — never floats. Format with `rentivo.models.format_brl()`.
- Currency is **BRL (R$)**.
- Keep the repository / storage / encryption / cache abstractions intact — backends must stay swappable.
- Dependencies are managed with **uv**: edit `pyproject.toml`, run `uv lock`, commit `uv.lock`. Never bare `pip`/`python`/`pytest` — use `uv run ...`.
- Lint and formatting are enforced by ruff (`make fmt` to fix).

## Tests

- `make test` runs the suite in parallel; it must pass with **100% coverage** (`fail_under = 100`). New code needs tests or an explicit `# pragma: no cover` with justification.
- Tests run against in-memory SQLite — no services required.
- Web POST tests need a CSRF token (see the `csrf_token` fixture in `tests/web/conftest.py`).

## Database migrations

- Generate revisions with `uv run alembic revision -m "description"` — **never hand-write revision IDs**.
- Migrations that drop or rename columns are breaking changes (see Versioning below).

## Commits & pull requests

- PR titles and merge commits follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `perf:`, `refactor:`, `chore:`, `docs:`, `test:`, `ci:`, `build:`, with optional scope (`feat(web): ...`). Breaking changes carry a `BREAKING CHANGE:` footer.
- Fill out **every** section of [.github/pull_request_template.md](.github/pull_request_template.md) — summary (lead with the why), what changed, test plan, screenshots for UI changes, config/deployment notes, risk & rollback.
- CI on PRs (`test-pr.yaml`) runs ruff check, ruff format, pytest, and both Docker image builds; all must pass.

## Merging policy — human-only

**Merges to `main` are performed by a human, never by an automated agent.** Agents (Claude, Paperclip, CI bots, or any non-human account) **open** pull requests and stop there; a human reviews and clicks merge.

This is enforced both behaviorally and at the repo level:

- `main` is a protected branch: **direct pushes are blocked for everyone (including admins)** — all changes land through a PR.
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

Please do **not** open public issues for vulnerabilities — see [SECURITY.md](SECURITY.md).
