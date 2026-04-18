from __future__ import annotations

from sqlalchemy import Connection

_MISSING = object()


def validate_transaction_binding(db_conn: Connection | None, *repos: object | None) -> None:
    if db_conn is None:
        return

    for repo in repos:
        if repo is None:
            continue
        repo_conn = getattr(getattr(repo, "__dict__", {}), "get", lambda *_: _MISSING)("conn", _MISSING)
        if repo_conn is _MISSING:
            continue
        if repo_conn is not db_conn:
            raise ValueError("Transactional service repositories must use the same database connection as db_conn")
