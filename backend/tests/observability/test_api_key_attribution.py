from unittest.mock import MagicMock

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from rentivo.context import Actor
from rentivo.observability.middleware import TracingMiddleware
from rentivo.services.audit_service import AuditService

API_KEY_UUID = "01J2Y9QJ6M6J8G6Q1SX4FJ2QWZ"


@pytest.mark.parametrize(
    ("source", "is_login_token", "key_class"),
    [
        ("web", True, "login"),
        ("mobile", True, "login"),
        ("integration", False, "integration"),
    ],
)
def test_audit_attribution_uses_only_safe_api_key_actor_metadata(source, is_login_token, key_class):
    repository = MagicMock()
    repository.create.side_effect = lambda audit_log: audit_log
    service = AuditService(repository)
    actor = Actor(
        user_id=42,
        email="owner@example.com",
        source=source,
        api_key_uuid=API_KEY_UUID,
        is_login_token=is_login_token,
    )

    result = service.safe_log_for(actor, "billing.view", metadata={"request_id": "request-123"})

    assert result is not None
    assert result.source == source
    assert result.metadata == {
        "request_id": "request-123",
        "api_key_uuid": API_KEY_UUID,
        "api_key_class": key_class,
    }
    serialized = repr(result.model_dump())
    for forbidden in ("api_key_name", "key_start", "key_end", "secret", "secret_hash"):
        assert forbidden not in serialized


def test_request_span_attributes_api_key_actor_without_sensitive_metadata(span_exporter):
    actor = Actor(
        user_id=42,
        email="owner@example.com",
        source="integration",
        api_key_uuid=API_KEY_UUID,
        is_login_token=False,
    )

    async def attributed(request: Request):
        request.state.actor = actor
        request.state.api_key_name = "accounting automation"
        request.state.api_key_hint = "aBcD...yZ"
        request.state.api_key_secret_hash = "digest-must-not-be-traced"
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/attributed", attributed)])
    app.add_middleware(TracingMiddleware)

    assert TestClient(app).get("/attributed").status_code == 200
    request_span = span_exporter.get_finished_spans()[0]
    assert request_span.attributes["actor.api_key_uuid"] == API_KEY_UUID
    assert request_span.attributes["actor.api_key_class"] == "integration"
    assert request_span.attributes["actor.source"] == "integration"

    serialized = repr(dict(request_span.attributes))
    for forbidden in ("accounting automation", "aBcD...yZ", "digest-must-not-be-traced"):
        assert forbidden not in serialized
