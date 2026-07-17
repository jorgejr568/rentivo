import pytest


@pytest.fixture(autouse=True)
def disable_api_migrations(monkeypatch):
    import rentivo.api.app as api_app

    monkeypatch.setattr(api_app, "initialize_db", lambda: None)
