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


def test_native_auth_transport_contracts_are_discriminated() -> None:
    schema = create_app().openapi()
    components = schema["components"]["schemas"]

    authenticated = components["AuthenticatedResponse"]
    assert authenticated["discriminator"]["propertyName"] == "credential_transport"
    assert {item["$ref"].rsplit("/", 1)[-1] for item in authenticated["oneOf"]} == {
        "BodyAuthenticatedResponse",
        "CookieAuthenticatedResponse",
    }
    assert {
        "access_token",
        "bootstrap",
        "credential_transport",
        "expires_in",
        "token_type",
    } <= set(components["BodyAuthenticatedResponse"]["required"])
    assert "access_token" not in components["CookieAuthenticatedResponse"]["properties"]

    mfa_required = components["MFARequiredResponse"]
    assert mfa_required["discriminator"]["propertyName"] == "credential_transport"
    assert "challenge_token" in components["BodyMFARequiredResponse"]["required"]
    assert "challenge_token" not in components["CookieMFARequiredResponse"]["properties"]

    mfa_request = components["MFACodeVerifyRequest"]
    assert mfa_request["discriminator"]["propertyName"] == "credential_transport"
    assert "challenge_token" in components["BodyMFACodeVerifyRequest"]["required"]
    assert "challenge_token" not in components["CookieMFACodeVerifyRequest"]["properties"]

    session_schema = schema["paths"]["/api/v1/auth/session"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert session_schema["$ref"].endswith("/SessionResponse")


def test_validation_errors_use_the_runtime_problem_contract_everywhere() -> None:
    schema = create_app().openapi()
    expected = {
        "description": "Request validation problem",
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/Problem"},
            }
        },
    }
    validation_responses = [
        operation["responses"]["422"]
        for path in schema["paths"].values()
        for method, operation in path.items()
        if method in {"delete", "get", "patch", "post", "put"} and "422" in operation["responses"]
    ]

    assert validation_responses
    assert all(response == expected for response in validation_responses)
    assert "Problem" in schema["components"]["schemas"]
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    assert "ValidationError" not in schema["components"]["schemas"]


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

    def fail_if_connected() -> None:
        raise AssertionError("OpenAPI export started the application lifespan")

    monkeypatch.setattr(app_module, "get_engine", fail_if_connected)
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
