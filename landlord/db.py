import os

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, event
from sqlalchemy.engine import Engine

from landlord.settings import settings

_engine: Engine | None = None
_connection: Connection | None = None


def _get_url() -> str:
    if settings.db_url:
        return settings.db_url
    if settings.db_backend == "sqlite":
        return f"sqlite:///{os.path.abspath(settings.db_path)}"
    raise ValueError(f"Unsupported DB backend: {settings.db_backend}")


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = _get_url()
        connect_args = {}
        if not url.startswith("sqlite"):
            connect_args["pool_pre_ping"] = True
            connect_args["pool_recycle"] = 1800
        _engine = create_engine(url, **connect_args)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA busy_timeout = 5000")
                cursor.close()

    return _engine


def get_connection() -> Connection:
    global _connection
    if _connection is None:
        _connection = get_engine().connect()
    return _connection


def _get_alembic_config() -> Config:
    """Build Alembic config pointing at the project root alembic.ini."""
    project_root = os.path.dirname(os.path.dirname(__file__))
    ini_path = os.path.join(project_root, "alembic.ini")
    cfg = Config(ini_path)
    return cfg


def initialize_db() -> None:
    """Run all pending Alembic migrations."""
    cfg = _get_alembic_config()
    command.upgrade(cfg, "head")
