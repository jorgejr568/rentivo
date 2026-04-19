import os

import structlog
from alembic.config import Config
from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import Engine

from alembic import command
from rentivo.settings import settings

logger = structlog.get_logger(__name__)

_engine: Engine | None = None
_connection: Connection | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.db_url,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        logger.info("db_engine_created")
    return _engine


def get_connection() -> Connection:
    """Return a global singleton connection — CLI use only.

    The web app uses per-request connections via DBConnectionMiddleware instead.
    """
    global _connection
    if _connection is None:
        _connection = get_engine().connect()
        logger.debug("db_singleton_connection_created")
    return _connection


def _get_alembic_config() -> Config:
    """Build Alembic config pointing at the project root alembic.ini."""
    project_root = os.path.dirname(os.path.dirname(__file__))
    ini_path = os.path.join(project_root, "alembic.ini")
    if not os.path.exists(ini_path):
        ini_path = os.path.join(os.getcwd(), "alembic.ini")
    cfg = Config(ini_path)
    return cfg


def initialize_db() -> None:
    """Run all pending Alembic migrations."""
    logger.info("alembic_migrations_started")
    cfg = _get_alembic_config()
    command.upgrade(cfg, "head")
    logger.info("alembic_migrations_complete")
