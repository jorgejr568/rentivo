from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Path, Response

from rentivo.api.csrf import require_csrf
from rentivo.api.dependencies import get_services, require_resource_grant, require_scope
from rentivo.api.domain_access import require_role, resolve_billing_access, resolve_organization_access
from rentivo.api.principal import Principal
from rentivo.api.schemas.themes import (
    ThemeCapabilitiesResponse,
    ThemeOptionsResponse,
    ThemeResponse,
    ThemeSource,
    ThemeUpdateRequest,
    ThemeValuesResponse,
)
from rentivo.constants.api_scopes import APIScope
from rentivo.models.audit_log import AuditEventType
from rentivo.models.billing import Billing
from rentivo.models.theme import DEFAULT_THEME, Theme
from rentivo.services.audit_serializers import serialize_theme
from rentivo.services.container import RequestServices

router = APIRouter(prefix="/themes", tags=["themes"])
_read_principal = require_scope(APIScope.THEMES_READ)
_write_principal = require_scope(APIScope.THEMES_WRITE)
_THEME_ADMIN_ROLES = frozenset({"owner", "admin"})
_ANALYTICS_EVENT_HEADER = "X-Rentivo-Analytics-Event"
_ANALYTICS_SCOPE_HEADER = "X-Rentivo-Analytics-Scope"


def _values(theme: Theme) -> ThemeValuesResponse:
    return ThemeValuesResponse(
        header_font=theme.header_font,
        text_font=theme.text_font,
        primary=theme.primary,
        primary_light=theme.primary_light,
        secondary=theme.secondary,
        secondary_dark=theme.secondary_dark,
        text_color=theme.text_color,
        text_contrast=theme.text_contrast,
    )


def _response(
    owner_name: str,
    stored: Theme | None,
    effective: Theme,
    source: ThemeSource,
    *,
    can_edit: bool,
) -> ThemeResponse:
    return ThemeResponse(
        owner_name=owner_name,
        stored=_values(stored) if stored is not None else None,
        effective=_values(effective),
        effective_source=source,
        options=ThemeOptionsResponse(),
        capabilities=ThemeCapabilitiesResponse(
            can_edit=can_edit,
            can_reset=stored is not None and can_edit,
        ),
    )


def _can_edit(principal: Principal) -> bool:
    return APIScope.THEMES_WRITE.value in principal.api_key.scopes


def _set_theme_analytics(response: Response, scope: str) -> None:
    response.headers[_ANALYTICS_EVENT_HEADER] = "rentivo_theme_changed"
    response.headers[_ANALYTICS_SCOPE_HEADER] = scope


def _require_user_access(principal: Principal, services: RequestServices) -> tuple[str, int]:
    require_resource_grant(principal, services, "user", principal.user.id)
    return "user", principal.user.id


def _require_organization_admin(
    principal: Principal,
    services: RequestServices,
    org_uuid: str,
) -> tuple[str, int, str]:
    access = resolve_organization_access(principal, services, org_uuid)
    require_role(access.role, {"admin"})
    return "organization", cast(int, access.organization.id), access.organization.name


def _require_billing_admin(
    principal: Principal,
    services: RequestServices,
    billing_uuid: str,
) -> tuple[Billing, str, int]:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _THEME_ADMIN_ROLES)
    return access.billing, "billing", cast(int, access.billing.id)


def _direct_theme_response(
    services: RequestServices,
    owner_type: str,
    owner_id: int,
    owner_name: str,
    *,
    can_edit: bool,
) -> ThemeResponse:
    stored = services.theme.get_theme_for_owner(owner_type, owner_id)
    source = cast(ThemeSource, owner_type if stored is not None else "default")
    return _response(owner_name, stored, stored or DEFAULT_THEME, source, can_edit=can_edit)


def _billing_theme_response(
    services: RequestServices,
    billing: Billing,
    billing_id: int,
    *,
    can_edit: bool,
) -> ThemeResponse:
    stored = services.theme.get_theme_for_owner("billing", billing_id)
    resolved = services.theme.resolve_theme_with_source(billing)
    return _response(
        billing.name,
        stored,
        resolved.theme,
        cast(ThemeSource, resolved.source),
        can_edit=can_edit,
    )


def _save_theme(
    *,
    services: RequestServices,
    principal: Principal,
    owner_type: str,
    owner_id: int,
    payload: ThemeUpdateRequest,
) -> Theme:
    existing = services.theme.get_theme_for_owner(owner_type, owner_id)
    previous_state = serialize_theme(existing) if existing is not None else None
    saved = services.theme.create_or_update_theme(owner_type, owner_id, **payload.model_dump())
    audit_kwargs: dict[str, object] = {
        "entity_type": "theme",
        "entity_id": saved.id,
        "entity_uuid": saved.uuid,
        "new_state": serialize_theme(saved),
    }
    event_type = AuditEventType.THEME_CREATE
    if previous_state is not None:
        event_type = AuditEventType.THEME_UPDATE
        audit_kwargs["previous_state"] = previous_state
    services.audit.safe_log_for(principal.actor, event_type, **audit_kwargs)
    return saved


def _reset_theme(
    *,
    services: RequestServices,
    principal: Principal,
    owner_type: str,
    owner_id: int,
) -> None:
    existing = services.theme.get_theme_for_owner(owner_type, owner_id)
    if existing is not None and services.theme.delete_theme(owner_type, owner_id):
        services.audit.safe_log_for(
            principal.actor,
            AuditEventType.THEME_DELETE,
            entity_type="theme",
            entity_id=existing.id,
            entity_uuid=existing.uuid,
            previous_state=serialize_theme(existing),
        )


@router.get("/user", response_model=ThemeResponse)
async def get_user_theme(
    principal: Principal = Depends(_read_principal),
    services: RequestServices = Depends(get_services),
) -> ThemeResponse:
    owner_type, owner_id = _require_user_access(principal, services)
    return _direct_theme_response(
        services,
        owner_type,
        owner_id,
        "Meu Tema",
        can_edit=_can_edit(principal),
    )


@router.put("/user", response_model=ThemeResponse)
async def update_user_theme(
    payload: ThemeUpdateRequest,
    response: Response,
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ThemeResponse:
    owner_type, owner_id = _require_user_access(principal, services)
    saved = _save_theme(
        services=services,
        principal=principal,
        owner_type=owner_type,
        owner_id=owner_id,
        payload=payload,
    )
    _set_theme_analytics(response, "user")
    return _response("Meu Tema", saved, saved, "user", can_edit=_can_edit(principal))


@router.delete("/user", status_code=204)
async def reset_user_theme(
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    owner_type, owner_id = _require_user_access(principal, services)
    _reset_theme(services=services, principal=principal, owner_type=owner_type, owner_id=owner_id)
    return Response(status_code=204)


@router.get("/organizations/{org_uuid}", response_model=ThemeResponse)
async def get_organization_theme(
    org_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_read_principal),
    services: RequestServices = Depends(get_services),
) -> ThemeResponse:
    owner_type, owner_id, owner_name = _require_organization_admin(principal, services, org_uuid)
    return _direct_theme_response(
        services,
        owner_type,
        owner_id,
        owner_name,
        can_edit=_can_edit(principal),
    )


@router.put("/organizations/{org_uuid}", response_model=ThemeResponse)
async def update_organization_theme(
    payload: ThemeUpdateRequest,
    response: Response,
    org_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ThemeResponse:
    owner_type, owner_id, owner_name = _require_organization_admin(principal, services, org_uuid)
    saved = _save_theme(
        services=services,
        principal=principal,
        owner_type=owner_type,
        owner_id=owner_id,
        payload=payload,
    )
    _set_theme_analytics(response, "organization")
    return _response(owner_name, saved, saved, "organization", can_edit=_can_edit(principal))


@router.delete("/organizations/{org_uuid}", status_code=204)
async def reset_organization_theme(
    org_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    owner_type, owner_id, _owner_name = _require_organization_admin(principal, services, org_uuid)
    _reset_theme(services=services, principal=principal, owner_type=owner_type, owner_id=owner_id)
    return Response(status_code=204)


@router.get("/billings/{billing_uuid}", response_model=ThemeResponse)
async def get_billing_theme(
    billing_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_read_principal),
    services: RequestServices = Depends(get_services),
) -> ThemeResponse:
    billing, _owner_type, billing_id = _require_billing_admin(principal, services, billing_uuid)
    return _billing_theme_response(
        services,
        billing,
        billing_id,
        can_edit=_can_edit(principal),
    )


@router.put("/billings/{billing_uuid}", response_model=ThemeResponse)
async def update_billing_theme(
    payload: ThemeUpdateRequest,
    response: Response,
    billing_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ThemeResponse:
    billing, owner_type, owner_id = _require_billing_admin(principal, services, billing_uuid)
    saved = _save_theme(
        services=services,
        principal=principal,
        owner_type=owner_type,
        owner_id=owner_id,
        payload=payload,
    )
    _set_theme_analytics(response, "billing")
    return _response(billing.name, saved, saved, "billing", can_edit=_can_edit(principal))


@router.delete("/billings/{billing_uuid}", status_code=204)
async def reset_billing_theme(
    billing_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    _billing, owner_type, owner_id = _require_billing_admin(principal, services, billing_uuid)
    _reset_theme(services=services, principal=principal, owner_type=owner_type, owner_id=owner_id)
    return Response(status_code=204)


@router.post(
    "/preview",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/pdf": {
                    "schema": {"type": "string", "format": "binary"},
                }
            }
        }
    },
)
def preview_theme(
    payload: ThemeUpdateRequest,
    _principal: Principal = Depends(_read_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    theme = Theme(**payload.model_dump())
    pdf_bytes = services.theme.render_preview(theme)
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="theme-preview.pdf"',
        },
    )
