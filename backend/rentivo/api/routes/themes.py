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
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, ItemType
from rentivo.models.theme import DEFAULT_THEME, Theme
from rentivo.pdf.invoice import InvoicePDF
from rentivo.services.audit_serializers import serialize_theme
from rentivo.services.container import RequestServices

router = APIRouter(prefix="/themes", tags=["themes"])
_read_principal = require_scope(APIScope.THEMES_READ)
_write_principal = require_scope(APIScope.THEMES_WRITE)
_THEME_ADMIN_ROLES = frozenset({"owner", "admin"})


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
    stored: Theme | None,
    effective: Theme,
    source: ThemeSource,
) -> ThemeResponse:
    return ThemeResponse(
        stored=_values(stored) if stored is not None else None,
        effective=_values(effective),
        effective_source=source,
        options=ThemeOptionsResponse(),
        capabilities=ThemeCapabilitiesResponse(can_reset=stored is not None),
    )


def _require_user_access(principal: Principal, services: RequestServices) -> tuple[str, int]:
    require_resource_grant(principal, services, "user", principal.user.id)
    return "user", principal.user.id


def _require_organization_admin(
    principal: Principal,
    services: RequestServices,
    org_uuid: str,
) -> tuple[str, int]:
    access = resolve_organization_access(principal, services, org_uuid)
    require_role(access.role, {"admin"})
    return "organization", cast(int, access.organization.id)


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
) -> ThemeResponse:
    stored = services.theme.get_theme_for_owner(owner_type, owner_id)
    source = cast(ThemeSource, owner_type if stored is not None else "default")
    return _response(stored, stored or DEFAULT_THEME, source)


def _billing_theme_response(services: RequestServices, billing: Billing, billing_id: int) -> ThemeResponse:
    stored = services.theme.get_theme_for_owner("billing", billing_id)
    resolved = services.theme.resolve_theme_with_source(billing)
    return _response(stored, resolved.theme, cast(ThemeSource, resolved.source))


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
    return _direct_theme_response(services, owner_type, owner_id)


@router.put("/user", response_model=ThemeResponse)
async def update_user_theme(
    payload: ThemeUpdateRequest,
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
    return _response(saved, saved, "user")


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
    owner_type, owner_id = _require_organization_admin(principal, services, org_uuid)
    return _direct_theme_response(services, owner_type, owner_id)


@router.put("/organizations/{org_uuid}", response_model=ThemeResponse)
async def update_organization_theme(
    payload: ThemeUpdateRequest,
    org_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ThemeResponse:
    owner_type, owner_id = _require_organization_admin(principal, services, org_uuid)
    saved = _save_theme(
        services=services,
        principal=principal,
        owner_type=owner_type,
        owner_id=owner_id,
        payload=payload,
    )
    return _response(saved, saved, "organization")


@router.delete("/organizations/{org_uuid}", status_code=204)
async def reset_organization_theme(
    org_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    owner_type, owner_id = _require_organization_admin(principal, services, org_uuid)
    _reset_theme(services=services, principal=principal, owner_type=owner_type, owner_id=owner_id)
    return Response(status_code=204)


@router.get("/billings/{billing_uuid}", response_model=ThemeResponse)
async def get_billing_theme(
    billing_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_read_principal),
    services: RequestServices = Depends(get_services),
) -> ThemeResponse:
    billing, _owner_type, billing_id = _require_billing_admin(principal, services, billing_uuid)
    return _billing_theme_response(services, billing, billing_id)


@router.put("/billings/{billing_uuid}", response_model=ThemeResponse)
async def update_billing_theme(
    payload: ThemeUpdateRequest,
    billing_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ThemeResponse:
    _billing, owner_type, owner_id = _require_billing_admin(principal, services, billing_uuid)
    saved = _save_theme(
        services=services,
        principal=principal,
        owner_type=owner_type,
        owner_id=owner_id,
        payload=payload,
    )
    return _response(saved, saved, "billing")


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
async def preview_theme(
    payload: ThemeUpdateRequest,
    _principal: Principal = Depends(_read_principal),
    _csrf: None = Depends(require_csrf),
) -> Response:
    theme = Theme(**payload.model_dump())
    sample_bill = Bill(
        billing_id=0,
        reference_month="2026-01",
        total_amount=150000,
        line_items=[
            BillLineItem(description="Aluguel", amount=120000, item_type=ItemType.FIXED, sort_order=0),
            BillLineItem(description="Água", amount=15000, item_type=ItemType.VARIABLE, sort_order=1),
            BillLineItem(description="Luz", amount=15000, item_type=ItemType.VARIABLE, sort_order=2),
        ],
        notes="Exemplo de fatura para visualização do tema.",
        due_date="2026-01-15",
    )
    pdf_bytes = InvoicePDF().generate(sample_bill, "Exemplo", theme=theme)
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="theme-preview.pdf"',
        },
    )
