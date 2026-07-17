"""Guard: .env.example stays in sync with rentivo.settings.Settings.

Every Settings field must be documented in .env.example, and .env.example
must not contain keys the app does not read (catches stale prefixes like
the old LANDLORD_* vars, and typos that would be silently ignored).
"""

import re
from pathlib import Path

from rentivo.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
CURRENT_GUIDES = (
    REPO_ROOT / ".env.example",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "docs" / "configuration.md",
)
STALE_RELOCATION_REFERENCES = (
    "see rentivo/settings.py",
    "`rentivo/settings.py`",
    "`tests/test_env_example.py`",
    "`tests/web/conftest.py`",
    "uv run alembic revision",
)

# Consumed by docker-compose.yml to provision the MariaDB container,
# not read by the application's Settings.
COMPOSE_ONLY_KEYS = {
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_PORT",
}


def _env_example_keys() -> set[str]:
    keys = set()
    for raw_line in ENV_EXAMPLE.read_text().splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", raw_line.strip())
        if match:
            keys.add(match.group(1))
    return keys


def _settings_env_keys() -> set[str]:
    return {f"RENTIVO_{name.upper()}" for name in Settings.model_fields}


def test_every_setting_is_documented_in_env_example():
    missing = _settings_env_keys() - _env_example_keys()
    assert not missing, f".env.example is missing: {sorted(missing)}"


def test_env_example_has_no_unknown_keys():
    unknown = _env_example_keys() - _settings_env_keys() - COMPOSE_ONLY_KEYS
    assert unknown == set(), f".env.example has unknown keys (typo or stale prefix?): {sorted(unknown)}"


def test_current_guides_use_relocated_backend_paths():
    stale_matches = {
        str(path.relative_to(REPO_ROOT)): [
            reference for reference in STALE_RELOCATION_REFERENCES if reference in path.read_text()
        ]
        for path in CURRENT_GUIDES
    }
    stale_matches = {path: matches for path, matches in stale_matches.items() if matches}
    assert stale_matches == {}, f"Current guides contain pre-monorepo paths: {stale_matches}"
