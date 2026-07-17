from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Response

from rentivo.api.csrf import require_csrf
from rentivo.api.dependencies import get_services, require_login_scope
from rentivo.api.errors import Problem, ProblemException, problem
from rentivo.api.principal import Principal
from rentivo.api.schemas.api_keys import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyGrantRequest,
    APIKeyGrantResponse,
    APIKeyListResponse,
    APIKeyOptionsResponse,
    APIKeyResponse,
    APIKeyUpdateRequest,
    OrganizationWorkspaceOption,
    PersonalWorkspaceOption,
)
from rentivo.constants.api_scopes import APIScope
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.services.container import RequestServices

router = APIRouter(prefix="/api-keys", tags=["api-keys"])
_management_principal = require_login_scope(APIScope.API_KEYS_MANAGE)
_INTEGRATION_CREATION_LIMIT = 10
_INTEGRATION_CREATION_WINDOW_SECONDS = 60 * 60


def _grant_model(
    grant: APIKeyGrantRequest,
    *,
    user_id: int,
    services: RequestServices,
) -> APIKeyGrant:
    if grant.resource_type == "user":
        return APIKeyGrant(resource_type="user", resource_id=user_id)
    organization = services.organization.get_by_uuid(grant.resource_id)
    if organization is None or organization.id is None:
        raise ValueError("Organization workspace does not exist")
    return APIKeyGrant(resource_type="organization", resource_id=organization.id)


def _grant_response(
    grant: APIKeyGrant,
    *,
    user_id: int,
    services: RequestServices,
) -> APIKeyGrantResponse:
    if grant.resource_type == "user":
        return APIKeyGrantResponse(resource_type="user", resource_id="personal", available=True)
    organization = services.organization.get_by_id(grant.resource_id)
    if organization is None:
        return APIKeyGrantResponse(resource_type="organization", resource_id=None, available=False)
    return APIKeyGrantResponse(
        resource_type="organization",
        resource_id=organization.uuid,
        available=services.organization.get_member(organization.id, user_id) is not None,
    )


def _key_response(key: APIKey, services: RequestServices) -> APIKeyResponse:
    return APIKeyResponse(
        uuid=key.uuid,
        name=key.name,
        hint=f"rntv-v1-{key.key_start}••••{key.key_end}",
        scopes=tuple(sorted(key.scopes)),
        grants=tuple(_grant_response(grant, user_id=key.user_id, services=services) for grant in key.grants),
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        created_at=key.created_at,
        revoked_at=key.revoked_at,
    )


def _audit_state(key: APIKey) -> dict[str, object]:
    return {
        "name": key.name,
        "scopes": sorted(key.scopes),
        "grants": [grant.model_dump(mode="json") for grant in key.grants],
        "revoked": key.revoked_at is not None,
    }


def _validation_error() -> ProblemException:
    return ProblemException(
        problem(
            status=422,
            code="validation_error",
            title="Dados inválidos",
            detail="Os dados da chave de integração são inválidos.",
        )
    )


def _creation_rate_limited() -> ProblemException:
    return ProblemException(
        problem(
            status=429,
            code="api_key_creation_rate_limited",
            title="Muitas solicitações",
            detail="Muitas chaves de integração foram criadas. Tente novamente mais tarde.",
        )
    )


def _get_integration(services: RequestServices, user_id: int, key_uuid: str) -> APIKey:
    key = services.api_key.get_integration(user_id, key_uuid)
    if key is None:
        raise ProblemException.not_found()
    return key


@router.get("", response_model=APIKeyListResponse)
async def list_api_keys(
    principal: Principal = Depends(_management_principal),
    services: RequestServices = Depends(get_services),
) -> APIKeyListResponse:
    keys = services.api_key.list_integrations(principal.user.id)
    return APIKeyListResponse(items=tuple(_key_response(key, services) for key in keys if not key.is_login_token))


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=201,
    responses={422: {"model": Problem}, 429: {"model": Problem}},
)
async def create_api_key(
    payload: APIKeyCreateRequest,
    response: Response,
    principal: Principal = Depends(_management_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> APIKeyCreateResponse:
    try:
        grants = tuple(_grant_model(grant, user_id=principal.user.id, services=services) for grant in payload.grants)
        services.api_key.validate_integration(
            user_id=principal.user.id,
            name=payload.name,
            scopes=payload.scopes,
            grants=grants,
            expires_at=payload.expires_at,
        )
    except ValueError:
        raise _validation_error() from None
    if not services.auth_rate_limit.reserve(
        action="api_key_create",
        identity=f"user:{principal.user.id}",
        limit=_INTEGRATION_CREATION_LIMIT,
        window_seconds=_INTEGRATION_CREATION_WINDOW_SECONDS,
    ):
        raise _creation_rate_limited()
    try:
        issued = services.api_key.issue_integration(
            user_id=principal.user.id,
            name=payload.name,
            scopes=payload.scopes,
            grants=grants,
            expires_at=payload.expires_at,
        )
    except ValueError:
        raise _validation_error() from None

    key = issued.key
    services.audit.safe_log_for(
        principal.actor,
        "api_key.create",
        entity_type="api_key",
        entity_id=key.id,
        entity_uuid=key.uuid,
        new_state=_audit_state(key),
    )
    response.headers["Cache-Control"] = "no-store"
    return APIKeyCreateResponse(**_key_response(key, services).model_dump(), secret=issued.secret)


@router.get("/options", response_model=APIKeyOptionsResponse)
async def api_key_options(
    principal: Principal = Depends(_management_principal),
    services: RequestServices = Depends(get_services),
) -> APIKeyOptionsResponse:
    organizations = tuple(
        OrganizationWorkspaceOption(
            resource_id=organization.uuid,
            name=organization.name,
        )
        for organization in services.organization.list_user_organizations(principal.user.id)
        if organization.id is not None
    )
    return APIKeyOptionsResponse(
        scopes=tuple(sorted(services.api_key.integration_scopes)),
        personal_workspace=PersonalWorkspaceOption(),
        organizations=organizations,
    )


@router.get(
    "/{key_uuid}",
    response_model=APIKeyResponse,
    responses={404: {"model": Problem}},
)
async def get_api_key(
    key_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_management_principal),
    services: RequestServices = Depends(get_services),
) -> APIKeyResponse:
    return _key_response(_get_integration(services, principal.user.id, key_uuid), services)


@router.patch(
    "/{key_uuid}",
    response_model=APIKeyResponse,
    responses={404: {"model": Problem}, 422: {"model": Problem}},
)
async def update_api_key(
    payload: APIKeyUpdateRequest,
    key_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_management_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> APIKeyResponse:
    existing = _get_integration(services, principal.user.id, key_uuid)
    try:
        grants = (
            existing.grants
            if payload.grants is None
            else tuple(_grant_model(grant, user_id=principal.user.id, services=services) for grant in payload.grants)
        )
        updated = services.api_key.update_integration(
            user_id=principal.user.id,
            uuid=key_uuid,
            name=existing.name if payload.name is None else payload.name,
            scopes=existing.scopes if payload.scopes is None else payload.scopes,
            grants=grants,
        )
    except ValueError:
        raise _validation_error() from None
    if updated is None:
        raise ProblemException.not_found()

    services.audit.safe_log_for(
        principal.actor,
        "api_key.update",
        entity_type="api_key",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state=_audit_state(existing),
        new_state=_audit_state(updated),
    )
    return _key_response(updated, services)


@router.delete(
    "/{key_uuid}",
    status_code=204,
    responses={404: {"model": Problem}},
)
async def revoke_api_key(
    key_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_management_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    existing = _get_integration(services, principal.user.id, key_uuid)
    transitioned = services.api_key.revoke_integration(principal.user.id, key_uuid)
    if not transitioned and services.api_key.get_integration(principal.user.id, key_uuid) is None:
        raise ProblemException.not_found()
    if transitioned:
        revoked = _get_integration(services, principal.user.id, key_uuid)
        services.audit.safe_log_for(
            principal.actor,
            "api_key.revoke",
            entity_type="api_key",
            entity_id=revoked.id,
            entity_uuid=revoked.uuid,
            previous_state=_audit_state(existing),
            new_state=_audit_state(revoked),
        )
    return Response(status_code=204)
