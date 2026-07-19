import pytest


@pytest.fixture(autouse=True)
def disable_api_production_validation(monkeypatch):
    import rentivo.api.app as api_app

    monkeypatch.setattr(api_app, "validate_production_settings", lambda: None, raising=False)
