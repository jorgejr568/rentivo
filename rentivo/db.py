import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from alembic.config import Config
from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import Engine

from alembic import command
from rentivo.settings import settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.db_url,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        logger.info("Database engine created")
    return _engine


@contextmanager
def open_connection() -> Iterator[Connection]:
    """Open a fresh database connection and close it when the scope exits."""
    conn = get_engine().connect()
    logger.debug("Managed DB connection created")
    try:
        yield conn
    finally:
        conn.close()
        logger.debug("Managed DB connection closed")


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
    logger.info("Running Alembic migrations")
    cfg = _get_alembic_config()
    command.upgrade(cfg, "head")
    logger.info("Migrations complete")
