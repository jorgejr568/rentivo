from fastapi import APIRouter, Depends

from rentivo.api.dependencies import get_services, require_resource_grant, require_scope
from rentivo.api.principal import Principal
from rentivo.api.schemas.security import CurrentProfileResponse
from rentivo.constants.api_scopes import APIScope
from rentivo.services.container import RequestServices

router = APIRouter(prefix="/profile", tags=["profile"])
_profile_principal = require_scope(APIScope.PROFILE_READ)


@router.get("", response_model=CurrentProfileResponse)
async def current_profile(
    principal: Principal = Depends(_profile_principal),
    services: RequestServices = Depends(get_services),
) -> CurrentProfileResponse:
    require_resource_grant(
        principal,
        services,
        "user",
        principal.user.id,
    )
    return CurrentProfileResponse(email=principal.user.email)
