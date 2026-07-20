from unittest.mock import MagicMock, patch

import pytest

import rentivo.api.app as api_app
import rentivo.db as db_module
import rentivo.workers.__main__ as worker_main


class TestGetEngine:
    def test_creates_engine(self, monkeypatch):
        monkeypatch.setattr(db_module, "_engine", None)
        with patch.object(db_module, "settings") as mock_settings:
            mock_settings.db_url = "sqlite:///:memory:"
            engine = db_module.get_engine()
            assert engine is not None
            assert db_module._engine is engine

    def test_returns_cached_engine(self, monkeypatch):
        sentinel = MagicMock()
        monkeypatch.setattr(db_module, "_engine", sentinel)
        engine = db_module.get_engine()
        assert engine is sentinel


class TestGetConnection:
    def test_creates_connection(self, monkeypatch):
        monkeypatch.setattr(db_module, "_connection", None)
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value = mock_conn
        with patch.object(db_module, "get_engine", return_value=mock_engine):
            conn = db_module.get_connection()
            assert conn is mock_conn

    def test_returns_cached_connection(self, monkeypatch):
        sentinel = MagicMock()
        monkeypatch.setattr(db_module, "_connection", sentinel)
        conn = db_module.get_connection()
        assert conn is sentinel


class TestInitializeDb:
    @patch("rentivo.db.command")
    @patch("rentivo.db._get_alembic_config")
    def test_calls_alembic_upgrade(self, mock_config, mock_command):
        mock_cfg = MagicMock()
        mock_config.return_value = mock_cfg
        db_module.initialize_db()
        mock_command.upgrade.assert_called_once_with(mock_cfg, "head")


@pytest.mark.asyncio
async def test_api_lifespan_validates_settings_without_running_migrations(monkeypatch):
    validate = MagicMock()
    migrate = MagicMock()
    monkeypatch.setattr(api_app, "validate_production_settings", validate, raising=False)
    monkeypatch.setattr(api_app, "initialize_db", migrate, raising=False)
    monkeypatch.setattr(api_app, "configure_tracing", MagicMock())
    monkeypatch.setattr(api_app, "reconfigure", MagicMock())

    async with api_app.lifespan(MagicMock()):
        pass

    validate.assert_called_once_with()
    migrate.assert_not_called()


def test_worker_validates_settings_before_starting_driver(monkeypatch):
    calls = []
    monkeypatch.setattr(worker_main, "validate_production_settings", lambda: calls.append("validate"), raising=False)
    monkeypatch.setattr(worker_main, "configure_logging", MagicMock())
    monkeypatch.setattr(worker_main, "configure_tracing", MagicMock())
    monkeypatch.setattr(worker_main.settings, "job_backend", "temporal")
    monkeypatch.setattr(
        "rentivo.jobs.temporal.runner.run_temporal_worker",
        lambda: calls.append("worker"),
    )

    worker_main.main()

    assert calls == ["validate", "worker"]


class TestGetAlembicConfig:
    def test_primary_path_exists(self):
        """When alembic.ini exists at project root, use it."""
        cfg = db_module._get_alembic_config()
        assert cfg is not None

    @patch("os.path.exists")
    def test_fallback_to_cwd(self, mock_exists):
        """When project root path doesn't have alembic.ini, fall back to CWD."""
        # First call (project root) returns False, second call is not checked
        mock_exists.return_value = False
        cfg = db_module._get_alembic_config()
        assert cfg is not None
        # Verify it was called with the project root path
        mock_exists.assert_called_once()
