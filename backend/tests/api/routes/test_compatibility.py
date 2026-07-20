from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rentivo.api.app import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize(
    ("legacy_path", "current_path"),
    [
        ("/change-password", "/security"),
        ("/security/pix", "/security"),
        ("/auth/google/login", "/api/v1/auth/google/start"),
    ],
)
def test_browser_aliases_use_permanent_redirects(
    client: TestClient,
    legacy_path: str,
    current_path: str,
) -> None:
    response = client.get(legacy_path, follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == current_path


@pytest.mark.parametrize(
    ("legacy_path", "current_path"),
    [
        (
            "/billings/billing-1/bills/bill-1/invoice",
            "/api/v1/billings/billing-1/bills/bill-1/invoice",
        ),
        (
            "/billings/billing-1/bills/bill-1/recibo",
            "/api/v1/billings/billing-1/bills/bill-1/recibo",
        ),
        (
            "/billings/billing-1/bills/bill-1/receipts/receipt-1",
            "/api/v1/billings/billing-1/bills/bill-1/receipts/receipt-1",
        ),
        (
            "/billings/billing-1/attachments/attachment-1",
            "/api/v1/billings/billing-1/attachments/attachment-1",
        ),
    ],
)
def test_historical_downloads_use_temporary_redirects(
    client: TestClient,
    legacy_path: str,
    current_path: str,
) -> None:
    response = client.get(legacy_path, follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == current_path


@pytest.mark.parametrize(
    "legacy_path",
    [
        "/login",
        "/forgot-password",
        "/security/pix",
        "/billings/create",
        "/billings/billing-1/attachments/upload",
        "/billings/billing-1/bills/generate",
        "/billings/billing-1/bills/bill-1/receipts/upload",
        "/organizations/create",
        "/invites/invite-1/accept",
        "/themes/user",
    ],
)
def test_stale_legacy_form_posts_return_gone_problem(
    client: TestClient,
    legacy_path: str,
) -> None:
    response = client.post(legacy_path, headers={"X-Request-ID": "stale-form"})

    assert response.status_code == 410
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "https://rentivo.com.br/problems/legacy_route_gone",
        "title": "Rota removida",
        "status": 410,
        "code": "legacy_route_gone",
        "detail": "Este formulário não está mais disponível. Atualize a página e tente novamente.",
        "fields": {},
        "request_id": "stale-form",
    }


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"])
def test_unknown_spa_mutations_return_request_id_problem(
    client: TestClient,
    method: str,
) -> None:
    response = client.request(
        method,
        "/not-a-legacy-form",
        headers={"X-Request-ID": "spa-mutation"},
    )

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["X-Request-ID"] == "spa-mutation"
    assert response.json()["code"] == "not_found"
    assert response.json()["request_id"] == "spa-mutation"


def test_proxy_routes_machine_and_compatibility_requests_without_spa_fallback() -> None:
    repository_root = Path(__file__).parents[4]
    nginx = (repository_root / "infra/proxy/nginx.conf").read_text()

    for path in ("/health", "/robots.txt", "/sitemap.xml", "/change-password", "/security/pix"):
        assert f"location = {path}" in nginx
    assert "location = /auth/google/login" in nginx
    assert "location ~ ^/billings/[^/]+/bills/[^/]+/(invoice|recibo|receipts/[^/]+)$" in nginx
    assert "location ~ ^/billings/[^/]+/attachments/[^/]+$" in nginx
    assert "error_page 418 = @rentivo_api_fallback;" in nginx
    assert (
        """location @rentivo_api_fallback {
            proxy_pass http://rentivo_api;
        }"""
        in nginx
    )
    assert (
        """location / {
            if ($request_method !~ ^(GET|HEAD)$) {
                return 418;
            }

            proxy_pass http://rentivo_frontend;
        }"""
        in nginx
    )
    assert "limit_except" not in nginx
