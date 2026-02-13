from unittest.mock import MagicMock, patch

import landlord.db as db_module


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
    @patch("landlord.db.command")
    @patch("landlord.db._get_alembic_config")
    def test_calls_alembic_upgrade(self, mock_config, mock_command):
        mock_cfg = MagicMock()
        mock_config.return_value = mock_cfg
        db_module.initialize_db()
        mock_command.upgrade.assert_called_once_with(mock_cfg, "head")


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
