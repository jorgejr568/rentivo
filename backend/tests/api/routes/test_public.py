from __future__ import annotations

from unittest.mock import MagicMock
from xml.etree import ElementTree

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from rentivo.api.app import create_app
from rentivo.api.errors import ProblemException
from rentivo.api.routes.public import _parse_public_origin, _public_origin
from rentivo.settings import settings


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(), base_url="https://preview.rentivo.test:8443")


def test_root_health_is_json(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_ready_opens_connection_executes_probe_and_closes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import rentivo.db as db

    connection = MagicMock()
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(db, "get_engine", lambda: engine)

    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ready"}
    engine.connect.assert_called_once_with()
    statement = connection.execute.call_args.args[0]
    assert str(statement) == "SELECT 1"
    engine.connect.return_value.__exit__.assert_called_once()


def test_ready_database_failure_is_problem_json(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import rentivo.db as db

    engine = MagicMock()
    engine.connect.side_effect = OperationalError("SELECT 1", {}, RuntimeError("database detail"))
    monkeypatch.setattr(db, "get_engine", lambda: engine)

    response = client.get("/api/v1/ready", headers={"X-Request-ID": "ready-request"})

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "https://rentivo.app/problems/not_ready",
        "title": "Serviço indisponível",
        "status": 503,
        "code": "not_ready",
        "detail": "O banco de dados não está disponível.",
        "fields": {},
        "request_id": "ready-request",
    }
    assert "database detail" not in response.text


def test_robots_preserves_policy_and_uses_configured_public_origin(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "public_url", "https://rentivo.example")

    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "User-agent: *\nAllow: /\nAllow: /login\nAllow: /signup" in response.text
    assert "Disallow: /billings/" in response.text
    assert "User-agent: GPTBot" in response.text
    assert response.text.endswith("Sitemap: https://rentivo.example/sitemap.xml\n")


@pytest.mark.parametrize("environment", ["dev", "staging"])
def test_crawler_routes_derive_origin_from_request_only_outside_production(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setattr(settings, "environment", environment)
    monkeypatch.setattr(settings, "public_url", "")

    robots = client.get("/robots.txt")
    sitemap = client.get("/sitemap.xml")

    assert "Sitemap: https://preview.rentivo.test:8443/sitemap.xml" in robots.text
    assert "<loc>https://preview.rentivo.test:8443/</loc>" in sitemap.text


def test_crawler_routes_reject_non_http_request_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "dev")
    monkeypatch.setattr(settings, "public_url", "")
    request = Request(
        {
            "type": "http",
            "scheme": "ftp",
            "server": ("invalid.example", 21),
            "path": "/robots.txt",
            "query_string": b"",
            "headers": [(b"host", b"invalid.example")],
        }
    )

    with pytest.raises(ProblemException) as captured:
        _public_origin(request)

    assert captured.value.problem.status == 400
    assert captured.value.problem.code == "invalid_public_origin"


def test_nonproduction_request_origin_allows_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "dev")
    monkeypatch.setattr(settings, "public_url", "")
    request = Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("localhost", 8000),
            "path": "/robots.txt",
            "query_string": b"",
            "headers": [(b"host", b"localhost:8000")],
        }
    )

    assert _public_origin(request) == "http://localhost:8000"


@pytest.mark.parametrize("path", ["/robots.txt", "/sitemap.xml"])
def test_crawler_routes_require_configured_origin_in_production(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "public_url", "")

    response = client.get(
        path,
        headers={"Host": "attacker.example", "X-Request-ID": "canonical-origin"},
    )

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["X-Request-ID"] == "canonical-origin"
    assert response.json()["code"] == "public_origin_not_configured"
    assert response.json()["request_id"] == "canonical-origin"
    assert "attacker.example" not in response.text


def test_configured_origin_is_canonical_regardless_of_host(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "public_url", "https://rentivo.example")

    robots = client.get("/robots.txt", headers={"Host": "attacker.example"})
    sitemap = client.get("/sitemap.xml", headers={"Host": "attacker.example"})

    assert "Sitemap: https://rentivo.example/sitemap.xml" in robots.text
    assert "<loc>https://rentivo.example/</loc>" in sitemap.text
    assert "attacker.example" not in robots.text
    assert "attacker.example" not in sitemap.text


@pytest.mark.parametrize(
    "configured_origin",
    [
        "ftp://rentivo.example",
        "//rentivo.example",
        "https://user@rentivo.example",
        "https://rentivo.example/",
        "https://rentivo.example/path",
        "https://rentivo.example?brand=one",
        "https://rentivo.example#fragment",
        "https://rentivo example",
        "https://rentivo.example\\bad",
        "https://%zz",
        "https://rentivo%2eexample",
        "https://-rentivo.example",
        "https://rentivo-.example",
        "https://rentivo..example",
        "https://rentivo_example",
        "https://rentivo.example:",
        "https://rentivo.example:invalid",
        "https://rentivo.example:99999",
        "https://localhost",
    ],
)
def test_crawler_routes_reject_malformed_configured_origins(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    configured_origin: str,
) -> None:
    monkeypatch.setattr(settings, "public_url", configured_origin)

    response = client.get("/robots.txt", headers={"X-Request-ID": "invalid-origin"})

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["X-Request-ID"] == "invalid-origin"
    assert response.json()["code"] == "invalid_public_origin"
    assert response.json()["request_id"] == "invalid-origin"


@pytest.mark.parametrize(
    ("origin", "expected_origin"),
    [
        ("https://rentivo.example", "https://rentivo.example"),
        ("https://sub-domain.rentivo.example:8443", "https://sub-domain.rentivo.example:8443"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
        ("https://[2001:db8::1]:8443", "https://[2001:db8::1]:8443"),
    ],
)
def test_parse_public_origin_accepts_valid_dns_and_ip_hosts(origin: str, expected_origin: str) -> None:
    assert _parse_public_origin(origin, allow_localhost=False) == expected_origin


def test_sitemap_is_xml_with_canonical_urls(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_url", "https://rentivo.example")

    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    root = ElementTree.fromstring(response.content)
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locations = [node.text for node in root.findall(f"{namespace}url/{namespace}loc")]
    assert locations == [
        "https://rentivo.example/",
        "https://rentivo.example/login",
        "https://rentivo.example/signup",
    ]
