from unittest.mock import MagicMock

from fastapi import Depends
from fastapi.testclient import TestClient

from rentivo.api.app import create_app
from rentivo.api.dependencies import get_services
from rentivo.api.errors import ProblemException
from rentivo.services.container import RequestServices


def test_health_is_versioned_and_json():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_api_route_uses_problem_json():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "not_found"


def test_method_not_allowed_uses_problem_json():
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.json()["code"] == "http_error"


def test_problem_exception_uses_problem_json():
    app = create_app()

    @app.get("/api/v1/problem")
    async def raise_problem() -> None:
        raise ProblemException.forbidden("missing_scope", "A chave não possui o escopo necessário.")

    with TestClient(app) as client:
        response = client.get("/api/v1/problem")

    assert response.status_code == 403
    assert response.json()["code"] == "missing_scope"


def test_validation_errors_use_problem_json():
    app = create_app()

    @app.get("/api/v1/value")
    async def value(number: int) -> dict[str, int]:
        return {"number": number}

    with TestClient(app) as client:
        response = client.get("/api/v1/value?number=invalid")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["fields"] == {
        "query.number": "Input should be a valid integer, unable to parse string as an integer"
    }


def test_services_dependency_uses_and_closes_a_request_connection(monkeypatch):
    import rentivo.api.app as api_app

    connection = MagicMock()
    engine = MagicMock()
    engine.connect.return_value = connection
    monkeypatch.setattr(api_app, "get_engine", lambda: engine)
    monkeypatch.setattr(api_app, "get_encryption", MagicMock())
    app = create_app()

    @app.get("/api/v1/services")
    async def services(services: RequestServices = Depends(get_services)) -> dict[str, bool]:
        return {"is_shared_container": isinstance(services, RequestServices)}

    with TestClient(app) as client:
        response = client.get("/api/v1/services")

    assert response.json() == {"is_shared_container": True}
    connection.close.assert_called_once_with()
