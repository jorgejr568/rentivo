import json

from rentivo.api.errors import ProblemException, problem, problem_response


def test_problem_response_uses_rfc_7807_content_type():
    value = problem(
        status=403,
        code="forbidden",
        title="Acesso negado",
        detail="Você não pode acessar este recurso.",
        fields={"organization_id": "required"},
    )

    response = problem_response(value)

    assert response.status_code == 403
    assert response.media_type == "application/problem+json"
    assert json.loads(response.body) == {
        "type": "https://rentivo.com.br/problems/forbidden",
        "title": "Acesso negado",
        "status": 403,
        "code": "forbidden",
        "detail": "Você não pode acessar este recurso.",
        "fields": {"organization_id": "required"},
        "request_id": "",
    }


def test_not_found_problem_exception_has_stable_problem_shape():
    error = ProblemException.not_found()

    assert error.problem.status == 404
    assert error.problem.code == "not_found"
    assert error.problem.fields == {}
