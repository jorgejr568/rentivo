from unittest.mock import MagicMock, patch

import pytest

import landlord.db as db_module


class TestGetUrl:
    def test_explicit_db_url(self):
        with patch.object(db_module, "settings") as mock_settings:
            mock_settings.db_url = "sqlite:///custom.db"
            mock_settings.db_backend = "sqlite"
            result = db_module._get_url()
            assert result == "sqlite:///custom.db"

    def test_sqlite_default(self):
        with patch.object(db_module, "settings") as mock_settings:
            mock_settings.db_url = ""
            mock_settings.db_backend = "sqlite"
            mock_settings.db_path = "landlord.db"
            result = db_module._get_url()
            assert result.startswith("sqlite:///")
            assert result.endswith("landlord.db")

    def test_unsupported_backend(self):
        with patch.object(db_module, "settings") as mock_settings:
            mock_settings.db_url = ""
            mock_settings.db_backend = "postgres"
            with pytest.raises(ValueError, match="Unsupported DB backend"):
                db_module._get_url()


class TestGetEngine:
    def test_creates_engine(self, monkeypatch):
        monkeypatch.setattr(db_module, "_engine", None)
        with patch.object(db_module, "settings") as mock_settings:
            mock_settings.db_url = "sqlite:///:memory:"
            mock_settings.db_backend = "sqlite"
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
