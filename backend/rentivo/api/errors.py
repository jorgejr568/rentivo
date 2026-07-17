import structlog
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class Problem(BaseModel):
    type: str
    title: str
    status: int
    code: str
    detail: str
    fields: dict[str, str] = Field(default_factory=dict)
    request_id: str


def get_request_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("request_id", ""))


def problem(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    fields: dict[str, str] | None = None,
) -> Problem:
    return Problem(
        type=f"https://rentivo.app/problems/{code}",
        title=title,
        status=status,
        code=code,
        detail=detail,
        fields=fields or {},
        request_id=get_request_id(),
    )


def problem_response(value: Problem) -> JSONResponse:
    return JSONResponse(
        content=value.model_dump(mode="json"),
        status_code=value.status,
        media_type="application/problem+json",
    )


class ProblemException(Exception):
    def __init__(self, problem: Problem, *, headers: dict[str, str] | None = None) -> None:
        self.problem = problem
        self.headers = headers or {}
        super().__init__(problem.detail)

    @classmethod
    def forbidden(cls, code: str, detail: str) -> "ProblemException":
        return cls(problem(status=403, code=code, title="Acesso negado", detail=detail))

    @classmethod
    def bad_request(cls, code: str, detail: str) -> "ProblemException":
        return cls(problem(status=400, code=code, title="Requisição inválida", detail=detail))

    @classmethod
    def unauthorized(cls, code: str, detail: str) -> "ProblemException":
        return cls(problem(status=401, code=code, title="Não autenticado", detail=detail))

    @classmethod
    def not_found(cls) -> "ProblemException":
        return cls(problem(status=404, code="not_found", title="Não encontrado", detail="Recurso não encontrado."))
