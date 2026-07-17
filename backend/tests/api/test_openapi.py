from __future__ import annotations

import json
from pathlib import Path

from rentivo.api.app import create_app


def test_openapi_contains_auth_and_key_operations() -> None:
    schema = create_app().openapi()

    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/api-keys" in schema["paths"]


def test_export_is_deterministic_without_starting_database_connections(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from rentivo.api import app as app_module
    from rentivo.api.export_openapi import export_openapi, main

    def fail_if_initialized() -> None:
        raise AssertionError("OpenAPI export started the application lifespan")

    monkeypatch.setattr(app_module, "initialize_db", fail_if_initialized)
    output = tmp_path / "openapi.json"

    export_openapi(output)
    first = output.read_text(encoding="utf-8")
    main([str(output)])
    second = output.read_text(encoding="utf-8")

    assert first == second
    assert first.endswith("\n")
    assert json.loads(first)["paths"]["/api/v1/auth/login"]["post"]
