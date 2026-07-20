from fastapi import Request

from rentivo.api.errors import ProblemException
from rentivo.api.principal import Principal
from rentivo.constants.api_scopes import APIScope
from rentivo.services.container import RequestServices


async def get_services(request: Request) -> RequestServices:
    return request.state.services.get()


def require_scope(scope: APIScope):
    from fastapi import Depends

    from rentivo.api.authentication import get_principal

    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if scope.value not in principal.api_key.scopes:
            raise ProblemException.forbidden("missing_scope", "A chave não possui o escopo necessário.")
        return principal

    return dependency


def require_login_scope(scope: APIScope):
    from fastapi import Depends

    scoped_dependency = require_scope(scope)

    async def dependency(principal: Principal = Depends(scoped_dependency)) -> Principal:
        if not principal.api_key.is_login_token:
            raise ProblemException.forbidden(
                "login_token_required",
                "Esta operação requer login interativo.",
            )
        return principal

    return dependency


def require_resource_grant(
    principal: Principal,
    services: RequestServices,
    resource_type: str,
    resource_id: int,
) -> None:
    if not services.api_key.can_access_resource(principal.api_key, resource_type, resource_id):
        raise ProblemException.not_found()
