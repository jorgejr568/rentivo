"""Static-analysis-style guards locking in the clean state of the 2026-05-02 audit.

Each test scans the production source tree (``rentivo/`` and ``web/``) for an
anti-pattern that the audit ruled out. A failure means a regression has slipped
in: either fix the code, or — if the pattern is genuinely necessary — document
the exception in ``docs/security/`` and update the regex below to allow it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_DIRS = (REPO_ROOT / "rentivo", REPO_ROOT / "web")


def _iter_production_py_files() -> list[Path]:
    files: list[Path] = []
    for prod_dir in PROD_DIRS:
        files.extend(p for p in prod_dir.rglob("*.py") if "__pycache__" not in p.parts)
    return files


@pytest.fixture(scope="module")
def production_files() -> list[Path]:
    files = _iter_production_py_files()
    assert files, "expected at least one production .py file under rentivo/ or web/"
    return files


_EXTRA_ALLOW_RE = re.compile(r"""extra\s*=\s*['"]allow['"]""")


def test_no_pydantic_extra_allow(production_files: list[Path]) -> None:
    """Pydantic models with extra='allow' let arbitrary input fields collide with .dict()/.json()."""
    offenders: list[str] = []
    for path in production_files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _EXTRA_ALLOW_RE.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Pydantic extra='allow' is forbidden — see docs/security/2026-05-02-fastapi-audit.md\n" + "\n".join(offenders)
    )


_MODEL_CONSTRUCT_RE = re.compile(r"\.model_construct\s*\(|(?<![\w.])model_construct\s*\(|\.construct\s*\(")


def test_no_model_construct_in_production(production_files: list[Path]) -> None:
    """model_construct() / .construct() bypass Pydantic validation and must not be used in prod code."""
    offenders: list[str] = []
    for path in production_files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _MODEL_CONSTRUCT_RE.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "model_construct() bypasses validation — see docs/security/2026-05-02-fastapi-audit.md\n" + "\n".join(offenders)
    )


_FSTRING_SQL_RE = re.compile(
    r"""text\(\s*f['"][^'"]*\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|VALUES)\b""",
    re.IGNORECASE,
)


def test_no_fstring_text_sql_in_repositories() -> None:
    """SQL strings passed to text() must not be f-strings — use bindparam(expanding=True) for IN clauses."""
    repo_dir = REPO_ROOT / "rentivo" / "repositories"
    offenders: list[str] = []
    for path in repo_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _FSTRING_SQL_RE.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "f-string SQL is forbidden in repositories — use bindparam(expanding=True)\n" + "\n".join(
        offenders
    )
