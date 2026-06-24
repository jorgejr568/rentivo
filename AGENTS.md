# AGENTS.md — rules for automated contributors

This file is read by AI agents and automation working in this repository. Humans should read [CONTRIBUTING.md](CONTRIBUTING.md); everything there applies to agents too. This file calls out the rules that are non-negotiable for non-human contributors.

## Pull requests are human-merged — agents NEVER merge

**Never merge a pull request on this repo. Only ever CREATE pull requests.** A human reviews and performs the merge.

This is a hard rule, no exceptions:

- Do **not** use the merge button, `gh pr merge`, squash/rebase/auto-merge, or enable auto-merge settings.
- Do **not** push directly to the default/protected branch (`main`) to bypass the PR flow, and do not fast-forward or otherwise land changes without a PR.
- After opening a PR, hand it off for human review and merge. Report the PR link and leave the PR open.
- If a task asks you to "merge", interpret it as "open a PR and request review". Only a human may perform or explicitly authorize the actual merge.

This rule is also enforced technically (see [CONTRIBUTING.md → Merging policy](CONTRIBUTING.md#merging-policy--human-only)): `main` is protected, direct pushes are blocked for everyone, and auto-merge is disabled repo-wide.

## Everything else

- Follow [CONTRIBUTING.md](CONTRIBUTING.md): Conventional Commit titles, fill out every PR template section, keep coverage at 100%, use `uv run ...` (never bare `pip`/`pytest`), and respect the storage/encryption/cache abstractions.
- Do not commit secrets or credentials. Deploy credentials are environment-injected.
- For vulnerabilities, follow [SECURITY.md](SECURITY.md) — do not open public issues.
