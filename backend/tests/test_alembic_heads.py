"""Guard test: the Alembic migration chain must have exactly one head.

Background: ``initialize_db()`` runs ``alembic upgrade head`` for web/worker/sweep
on startup. If the migration chain forks into more than one head (e.g. two feature
branches each add a migration off the same parent and both merge to ``main``),
``head`` becomes ambiguous and ``alembic upgrade head`` raises, crashing startup.

This happened on ``origin/main`` (REN-32 verification): two heads slipped through
because the test suite builds its schema from the hand-maintained SQLite
``SCHEMA_DDL`` in ``conftest``, not from the Alembic chain. This test closes that
gap by parsing the migration scripts directly — no database required — so any
branch that introduces a second head fails CI before merge.

The fix when this test fails is a merge migration:
``uv run alembic merge -m "merge heads" <head1> <head2> ...``
"""

from alembic.script import ScriptDirectory

from rentivo.db import _get_alembic_config


def test_single_alembic_head() -> None:
    """The migration chain must resolve to exactly one head.

    More than one head makes ``alembic upgrade head`` ambiguous and breaks
    ``initialize_db()`` on a fresh migrate. Collapse extra heads with a merge
    migration (``alembic merge``) before merging to main.
    """
    script = ScriptDirectory.from_config(_get_alembic_config())
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"Expected exactly one Alembic head, found {len(heads)}: {sorted(heads)}. "
        "Two or more heads make `alembic upgrade head` ambiguous and crash "
        "startup. Resolve with: alembic merge -m 'merge heads' "
        f"{' '.join(sorted(heads))}"
    )
