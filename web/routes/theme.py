from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import ItemType
from rentivo.models.theme import AVAILABLE_FONTS, DEFAULT_THEME, Theme
from rentivo.pdf.invoice import InvoicePDF
from web.deps import (
    get_audit_service,
    get_authorization_service,
    get_billing_service,
    get_organization_service,
    get_theme_service,
    render,
)
from web.flash import flash

logger = logging.getLogger(__name__)

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


def _serialize_theme(theme: Theme) -> dict:
    """Serialize a Theme to a dict for audit logging."""
    return {
        "uuid": theme.uuid,
        "owner_type": theme.owner_type,
        "owner_id": theme.owner_id,
        "name": theme.name,
        "header_font": theme.header_font,
        "text_font": theme.text_font,
        "primary": theme.primary,
        "primary_light": theme.primary_light,
        "secondary": theme.secondary,
        "secondary_dark": theme.secondary_dark,
        "text_color": theme.text_color,
        "text_contrast": theme.text_contrast,
    }


# ---------------------------------------------------------------------------
# User theme
# ---------------------------------------------------------------------------


@router.get("/user")
async def user_theme_form(request: Request):
    logger.info("GET /themes/user — rendering user theme form")
    user_id = request.session.get("user_id")
    theme_service = get_theme_service(request)
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
    logger.info("POST /themes/user — saving user theme")
    user_id = request.session.get("user_id")
    theme_service = get_theme_service(request)

    existing = theme_service.get_theme_for_owner("user", user_id)

    form = await request.form()
    fields = _parse_theme_fields(dict(form))

    theme = theme_service.create_or_update_theme("user", user_id, **fields)
    logger.info("User theme saved: uuid=%s user=%s", theme.uuid, user_id)

    event_type = AuditEventType.THEME_UPDATE if existing else AuditEventType.THEME_CREATE
    audit = get_audit_service(request)
    audit.safe_log(
        event_type,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="theme",
        entity_id=theme.id,
        entity_uuid=theme.uuid,
        previous_state=_serialize_theme(existing) if existing else None,
        new_state=_serialize_theme(theme),
    )

    flash(request, "Tema salvo com sucesso!", "success")
    return RedirectResponse("/themes/user", status_code=302)


@router.post("/user/delete")
async def user_theme_delete(request: Request):
    logger.info("POST /themes/user/delete — resetting user theme")
    user_id = request.session.get("user_id")
    theme_service = get_theme_service(request)

    existing = theme_service.get_theme_for_owner("user", user_id)
    deleted = theme_service.delete_theme("user", user_id)

    if deleted:
        logger.info("User theme deleted: user=%s", user_id)
        audit = get_audit_service(request)
        audit.safe_log(
            AuditEventType.THEME_DELETE,
            actor_id=user_id,
            actor_username=request.session.get("username", ""),
            source="web",
            entity_type="theme",
            entity_id=existing.id if existing else None,
            entity_uuid=existing.uuid if existing else "",
            previous_state=_serialize_theme(existing) if existing else None,
        )
        flash(request, "Tema redefinido para o padrão.", "success")
    else:
        flash(request, "Nenhum tema personalizado para redefinir.", "warning")

    return RedirectResponse("/themes/user", status_code=302)


# ---------------------------------------------------------------------------
# Organization theme
# ---------------------------------------------------------------------------


def _check_org_admin(request: Request, org_uuid: str):
    """Look up org and verify the current user is an admin.

    Returns (org, user_id) on success, or a RedirectResponse on failure.
    """
    org_service = get_organization_service(request)
    org = org_service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("Organization not found: uuid=%s", org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302), None

    user_id = request.session.get("user_id")
    member = org_service.get_member(org.id, user_id)
    if not member or member.role != "admin":
        logger.warning("Organization theme access denied: uuid=%s user=%s", org_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302), None

    return org, user_id


@router.get("/organization/{org_uuid}")
async def org_theme_form(request: Request, org_uuid: str):
    logger.info("GET /themes/organization/%s — rendering org theme form", org_uuid)
    result, user_id = _check_org_admin(request, org_uuid)
    if isinstance(result, RedirectResponse):
        return result
    org = result

    theme_service = get_theme_service(request)
    existing = theme_service.get_theme_for_owner("organization", org.id)
    theme = existing or DEFAULT_THEME

    return render(
        request,
        "theme/edit.html",
        {
            "theme": theme,
            "owner_type": "organization",
            "owner_label": f"{org.name} \u2014 Tema",
            "form_action": f"/themes/organization/{org_uuid}",
            "delete_action": f"/themes/organization/{org_uuid}/delete",
            "back_url": f"/organizations/{org_uuid}",
            "available_fonts": AVAILABLE_FONTS,
            "has_custom": existing is not None,
        },
    )


@router.post("/organization/{org_uuid}")
async def org_theme_save(request: Request, org_uuid: str):
    logger.info("POST /themes/organization/%s — saving org theme", org_uuid)
    result, user_id = _check_org_admin(request, org_uuid)
    if isinstance(result, RedirectResponse):
        return result
    org = result

    theme_service = get_theme_service(request)
    existing = theme_service.get_theme_for_owner("organization", org.id)

    form = await request.form()
    fields = _parse_theme_fields(dict(form))

    theme = theme_service.create_or_update_theme("organization", org.id, **fields)
    logger.info("Org theme saved: uuid=%s org=%s", theme.uuid, org_uuid)

    event_type = AuditEventType.THEME_UPDATE if existing else AuditEventType.THEME_CREATE
    audit = get_audit_service(request)
    audit.safe_log(
        event_type,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="theme",
        entity_id=theme.id,
        entity_uuid=theme.uuid,
        previous_state=_serialize_theme(existing) if existing else None,
        new_state=_serialize_theme(theme),
    )

    flash(request, "Tema da organização salvo com sucesso!", "success")
    return RedirectResponse(f"/themes/organization/{org_uuid}", status_code=302)


@router.post("/organization/{org_uuid}/delete")
async def org_theme_delete(request: Request, org_uuid: str):
    logger.info("POST /themes/organization/%s/delete — resetting org theme", org_uuid)
    result, user_id = _check_org_admin(request, org_uuid)
    if isinstance(result, RedirectResponse):
        return result
    org = result

    theme_service = get_theme_service(request)
    existing = theme_service.get_theme_for_owner("organization", org.id)
    deleted = theme_service.delete_theme("organization", org.id)

    if deleted:
        logger.info("Org theme deleted: org=%s", org_uuid)
        audit = get_audit_service(request)
        audit.safe_log(
            AuditEventType.THEME_DELETE,
            actor_id=user_id,
            actor_username=request.session.get("username", ""),
            source="web",
            entity_type="theme",
            entity_id=existing.id if existing else None,
            entity_uuid=existing.uuid if existing else "",
            previous_state=_serialize_theme(existing) if existing else None,
        )
        flash(request, "Tema da organização redefinido para o padrão.", "success")
    else:
        flash(request, "Nenhum tema personalizado para redefinir.", "warning")

    return RedirectResponse(f"/themes/organization/{org_uuid}", status_code=302)


# ---------------------------------------------------------------------------
# Billing theme
# ---------------------------------------------------------------------------


def _check_billing_access(request: Request, billing_uuid: str):
    """Look up billing and verify the current user can edit it.

    Returns (billing, user_id) on success, or a RedirectResponse on failure.
    """
    billing_service = get_billing_service(request)
    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("Billing not found: uuid=%s", billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/billings/", status_code=302), None

    user_id = request.session.get("user_id")
    auth_service = get_authorization_service(request)
    if not auth_service.can_edit_billing(user_id, billing):
        logger.warning("Billing theme access denied: uuid=%s user=%s", billing_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302), None

    return billing, user_id


def _resolve_effective_source(theme_service, billing) -> str:
    """Determine where the effective theme comes from for a billing."""
    # Check billing-level theme
    if billing.id is not None:
        if theme_service.get_theme_for_owner("billing", billing.id) is not None:
            return "billing"

    # Check owner-level theme (organization or user)
    owner_theme = theme_service.get_theme_for_owner(billing.owner_type, billing.owner_id)
    if owner_theme is not None:
        return billing.owner_type

    return "default"


@router.get("/billing/{billing_uuid}")
async def billing_theme_form(request: Request, billing_uuid: str):
    logger.info("GET /themes/billing/%s — rendering billing theme form", billing_uuid)
    result, user_id = _check_billing_access(request, billing_uuid)
    if isinstance(result, RedirectResponse):
        return result
    billing = result

    theme_service = get_theme_service(request)
    existing = theme_service.get_theme_for_owner("billing", billing.id)
    theme = existing or DEFAULT_THEME
    effective_theme = theme_service.resolve_theme_for_billing(billing)
    effective_source = _resolve_effective_source(theme_service, billing)

    return render(
        request,
        "theme/edit.html",
        {
            "theme": theme,
            "owner_type": "billing",
            "owner_label": f"{billing.name} \u2014 Tema",
            "form_action": f"/themes/billing/{billing_uuid}",
            "delete_action": f"/themes/billing/{billing_uuid}/delete",
            "back_url": f"/billings/{billing_uuid}",
            "available_fonts": AVAILABLE_FONTS,
            "has_custom": existing is not None,
            "effective_theme": effective_theme,
            "effective_source": effective_source,
        },
    )


@router.post("/billing/{billing_uuid}")
async def billing_theme_save(request: Request, billing_uuid: str):
    logger.info("POST /themes/billing/%s — saving billing theme", billing_uuid)
    result, user_id = _check_billing_access(request, billing_uuid)
    if isinstance(result, RedirectResponse):
        return result
    billing = result

    theme_service = get_theme_service(request)
    existing = theme_service.get_theme_for_owner("billing", billing.id)

    form = await request.form()
    fields = _parse_theme_fields(dict(form))

    theme = theme_service.create_or_update_theme("billing", billing.id, **fields)
    logger.info("Billing theme saved: uuid=%s billing=%s", theme.uuid, billing_uuid)

    event_type = AuditEventType.THEME_UPDATE if existing else AuditEventType.THEME_CREATE
    audit = get_audit_service(request)
    audit.safe_log(
        event_type,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="theme",
        entity_id=theme.id,
        entity_uuid=theme.uuid,
        previous_state=_serialize_theme(existing) if existing else None,
        new_state=_serialize_theme(theme),
    )

    flash(request, "Tema da cobrança salvo com sucesso!", "success")
    return RedirectResponse(f"/themes/billing/{billing_uuid}", status_code=302)


@router.post("/billing/{billing_uuid}/delete")
async def billing_theme_delete(request: Request, billing_uuid: str):
    logger.info("POST /themes/billing/%s/delete — resetting billing theme", billing_uuid)
    result, user_id = _check_billing_access(request, billing_uuid)
    if isinstance(result, RedirectResponse):
        return result
    billing = result

    theme_service = get_theme_service(request)
    existing = theme_service.get_theme_for_owner("billing", billing.id)
    deleted = theme_service.delete_theme("billing", billing.id)

    if deleted:
        logger.info("Billing theme deleted: billing=%s", billing_uuid)
        audit = get_audit_service(request)
        audit.safe_log(
            AuditEventType.THEME_DELETE,
            actor_id=user_id,
            actor_username=request.session.get("username", ""),
            source="web",
            entity_type="theme",
            entity_id=existing.id if existing else None,
            entity_uuid=existing.uuid if existing else "",
            previous_state=_serialize_theme(existing) if existing else None,
        )
        flash(request, "Tema da cobrança redefinido para o padrão.", "success")
    else:
        flash(request, "Nenhum tema personalizado para redefinir.", "warning")

    return RedirectResponse(f"/themes/billing/{billing_uuid}", status_code=302)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@router.get("/preview")
async def theme_preview(request: Request):
    logger.info("GET /themes/preview — generating sample PDF")
    fields = _parse_theme_fields(dict(request.query_params))

    theme = Theme(**fields)

    sample_bill = Bill(
        billing_id=0,
        reference_month="2026-01",
        total_amount=150000,
        line_items=[
            BillLineItem(description="Aluguel", amount=120000, item_type=ItemType.FIXED, sort_order=0),
            BillLineItem(description="\u00c1gua", amount=15000, item_type=ItemType.VARIABLE, sort_order=1),
            BillLineItem(description="Luz", amount=15000, item_type=ItemType.VARIABLE, sort_order=2),
        ],
        notes="Exemplo de fatura para visualiza\u00e7\u00e3o do tema.",
        due_date="2026-01-15",
    )

    pdf_bytes = InvoicePDF().generate(sample_bill, "Exemplo", theme=theme)
    logger.info("Preview PDF generated: %d bytes", len(pdf_bytes))

    return Response(content=bytes(pdf_bytes), media_type="application/pdf")
