from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

from rentivo.api.app import create_app


def test_openapi_contains_auth_and_key_operations() -> None:
    schema = create_app().openapi()

    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/api-keys" in schema["paths"]


def test_openapi_contains_authenticated_domain_operations() -> None:
    paths = create_app().openapi()["paths"]

    assert {
        "/api/v1/billings",
        "/api/v1/billings/{billing_uuid}",
        "/api/v1/billings/{billing_uuid}/bills",
        "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}",
        "/api/v1/billings/{billing_uuid}/expenses",
        "/api/v1/billings/{billing_uuid}/attachments",
        "/api/v1/organizations",
        "/api/v1/organizations/{organization_uuid}",
        "/api/v1/invites",
        "/api/v1/themes/user",
        "/api/v1/themes/organizations/{org_uuid}",
        "/api/v1/themes/billings/{billing_uuid}",
    }.issubset(paths)


def test_openapi_operation_ids_are_unique() -> None:
    paths = create_app().openapi()["paths"]
    operation_ids = [
        operation["operationId"]
        for path in paths.values()
        for method, operation in path.items()
        if method in {"delete", "get", "patch", "post", "put"}
    ]

    assert len(operation_ids) == len(set(operation_ids))


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


def test_export_module_entrypoint_writes_the_requested_schema(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "entrypoint.json"
    monkeypatch.setattr(sys, "argv", ["rentivo.api.export_openapi", str(output)])
    monkeypatch.delitem(sys.modules, "rentivo.api.export_openapi", raising=False)

    runpy.run_module("rentivo.api.export_openapi", run_name="__main__")

    assert "/api/v1/auth/login" in json.loads(output.read_text(encoding="utf-8"))["paths"]
