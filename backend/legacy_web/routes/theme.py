from __future__ import annotations

import re

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from legacy_web.analytics import push_event
from legacy_web.deps import render
from legacy_web.flash import flash
from legacy_web.guards import BillingContext, OrgContext, require_billing, require_org_admin
from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import ItemType
from rentivo.models.theme import AVAILABLE_FONTS, DEFAULT_THEME, Theme
from rentivo.pdf.invoice import InvoicePDF
from rentivo.services.audit_serializers import serialize_theme

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/themes")

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

THEME_FIELDS = (
    "header_font",
    "text_font",
    "primary",
    "primary_light",
    "secondary",
    "secondary_dark",
    "text_color",
    "text_contrast",
    "name",
)

COLOR_FIELDS = (
    "primary",
    "primary_light",
    "secondary",
    "secondary_dark",
    "text_color",
    "text_contrast",
)


def _parse_theme_fields(form: dict) -> dict:
    """Parse and validate theme fields from a form submission."""
    fields: dict = {}
    for key in THEME_FIELDS:
        value = str(form.get(key, "")).strip()
        if not value:
            continue
        if key in ("header_font", "text_font"):
            if value not in AVAILABLE_FONTS:
                value = "Montserrat"
        elif key in COLOR_FIELDS:
            if not _HEX_COLOR_RE.match(value):
                value = getattr(DEFAULT_THEME, key)
        fields[key] = value
    return fields


async def _save_theme(
    request: Request,
    *,
    owner_type: str,
    owner_id: int,
    scope: str,
    redirect_url: str,
    success_message: str,
    log_extra: dict | None = None,
) -> RedirectResponse:
    """Shared create-or-update theme flow for the user/org/billing save routes."""
    theme_service = request.state.services.theme
    existing = theme_service.get_theme_for_owner(owner_type, owner_id)

    form = await request.form()
    fields = _parse_theme_fields(dict(form))

    theme = theme_service.create_or_update_theme(owner_type, owner_id, **fields)
    logger.info("theme_saved", scope=scope, theme_uuid=theme.uuid, **(log_extra or {}))

    event_type = AuditEventType.THEME_UPDATE if existing else AuditEventType.THEME_CREATE
    request.state.services.audit.safe_log_for(
        request.state.actor,
        event_type,
        entity_type="theme",
        entity_id=theme.id,
        entity_uuid=theme.uuid,
        previous_state=serialize_theme(existing) if existing else None,
        new_state=serialize_theme(theme),
    )

    flash(request, success_message, "success")
    push_event(request, {"event": "rentivo_theme_changed", "scope": scope})
    return RedirectResponse(redirect_url, status_code=302)


def _delete_theme(
    request: Request,
    *,
    owner_type: str,
    owner_id: int,
    scope: str,
    redirect_url: str,
    deleted_message: str,
    log_extra: dict | None = None,
) -> RedirectResponse:
    """Shared delete-theme flow for the user/org/billing delete routes."""
    theme_service = request.state.services.theme
    existing = theme_service.get_theme_for_owner(owner_type, owner_id)
    deleted = theme_service.delete_theme(owner_type, owner_id)

    if deleted:
        logger.info("theme_deleted", scope=scope, **(log_extra or {}))
        request.state.services.audit.safe_log_for(
            request.state.actor,
            AuditEventType.THEME_DELETE,
            entity_type="theme",
            entity_id=existing.id if existing else None,
            entity_uuid=existing.uuid if existing else "",
            previous_state=serialize_theme(existing) if existing else None,
        )
        flash(request, deleted_message, "success")
    else:
        flash(request, "Nenhum tema personalizado para redefinir.", "warning")

    return RedirectResponse(redirect_url, status_code=302)


# ---------------------------------------------------------------------------
# User theme
# ---------------------------------------------------------------------------


@router.get("/user")
async def user_theme_form(request: Request):
    user_id = request.session.get("user_id")
    theme_service = request.state.services.theme
    existing = theme_service.get_theme_for_owner("user", user_id)
    theme = existing or DEFAULT_THEME

    return render(
        request,
        "theme/edit.html",
        {
            "theme": theme,
            "owner_type": "user",
            "owner_label": "Meu Tema",
            "form_action": "/themes/user",
            "delete_action": "/themes/user/delete",
            "back_url": "/billings/",
            "available_fonts": AVAILABLE_FONTS,
            "has_custom": existing is not None,
        },
    )


@router.post("/user")
async def user_theme_save(request: Request):
    return await _save_theme(
        request,
        owner_type="user",
        owner_id=request.session.get("user_id"),
        scope="user",
        redirect_url="/themes/user",
        success_message="Tema salvo com sucesso!",
    )


@router.post("/user/delete")
async def user_theme_delete(request: Request):
    return _delete_theme(
        request,
        owner_type="user",
        owner_id=request.session.get("user_id"),
        scope="user",
        redirect_url="/themes/user",
        deleted_message="Tema redefinido para o padrão.",
    )


# ---------------------------------------------------------------------------
# Organization theme
# ---------------------------------------------------------------------------


@router.get("/organization/{org_uuid}")
async def org_theme_form(request: Request, ctx: OrgContext = Depends(require_org_admin)):
    org = ctx.org
    theme_service = request.state.services.theme
    existing = theme_service.get_theme_for_owner("organization", org.id)
    theme = existing or DEFAULT_THEME

    return render(
        request,
        "theme/edit.html",
        {
            "theme": theme,
            "owner_type": "organization",
            "owner_label": f"{org.name} — Tema",
            "form_action": f"/themes/organization/{org.uuid}",
            "delete_action": f"/themes/organization/{org.uuid}/delete",
            "back_url": f"/organizations/{org.uuid}",
            "available_fonts": AVAILABLE_FONTS,
            "has_custom": existing is not None,
        },
    )


@router.post("/organization/{org_uuid}")
async def org_theme_save(request: Request, ctx: OrgContext = Depends(require_org_admin)):
    org = ctx.org
    return await _save_theme(
        request,
        owner_type="organization",
        owner_id=org.id,
        scope="organization",
        redirect_url=f"/themes/organization/{org.uuid}",
        success_message="Tema da organização salvo com sucesso!",
        log_extra={"org_uuid": org.uuid},
    )


@router.post("/organization/{org_uuid}/delete")
async def org_theme_delete(request: Request, ctx: OrgContext = Depends(require_org_admin)):
    org = ctx.org
    return _delete_theme(
        request,
        owner_type="organization",
        owner_id=org.id,
        scope="organization",
        redirect_url=f"/themes/organization/{org.uuid}",
        deleted_message="Tema da organização redefinido para o padrão.",
        log_extra={"org_uuid": org.uuid},
    )


# ---------------------------------------------------------------------------
# Billing theme
# ---------------------------------------------------------------------------


@router.get("/billing/{billing_uuid}")
async def billing_theme_form(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    billing = ctx.billing
    theme_service = request.state.services.theme
    existing = theme_service.get_theme_for_owner("billing", billing.id)
    theme = existing or DEFAULT_THEME
    resolved = theme_service.resolve_theme_with_source(billing)

    return render(
        request,
        "theme/edit.html",
        {
            "theme": theme,
            "owner_type": "billing",
            "owner_label": f"{billing.name} — Tema",
            "form_action": f"/themes/billing/{billing.uuid}",
            "delete_action": f"/themes/billing/{billing.uuid}/delete",
            "back_url": f"/billings/{billing.uuid}",
            "available_fonts": AVAILABLE_FONTS,
            "has_custom": existing is not None,
            "effective_theme": resolved.theme,
            "effective_source": resolved.source,
        },
    )


@router.post("/billing/{billing_uuid}")
async def billing_theme_save(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    billing = ctx.billing
    return await _save_theme(
        request,
        owner_type="billing",
        owner_id=billing.id,
        scope="billing",
        redirect_url=f"/themes/billing/{billing.uuid}",
        success_message="Tema da cobrança salvo com sucesso!",
        log_extra={"billing_uuid": billing.uuid},
    )


@router.post("/billing/{billing_uuid}/delete")
async def billing_theme_delete(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    billing = ctx.billing
    return _delete_theme(
        request,
        owner_type="billing",
        owner_id=billing.id,
        scope="billing",
        redirect_url=f"/themes/billing/{billing.uuid}",
        deleted_message="Tema da cobrança redefinido para o padrão.",
        log_extra={"billing_uuid": billing.uuid},
    )


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@router.get("/preview")
async def theme_preview(request: Request):
    fields = _parse_theme_fields(dict(request.query_params))

    theme = Theme(**fields)

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
    logger.info("theme_preview_generated", bytes=len(pdf_bytes))

    return Response(content=bytes(pdf_bytes), media_type="application/pdf")
