from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.models.expense import ExpenseCategory
from rentivo.services.audit_serializers import serialize_expense
from web.analytics import analytics_hash, push_event
from web.flash import flash, flash_redirect
from web.forms import parse_brl
from web.guards import BillingContext, require_billing

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billings/{billing_uuid}/expenses")

_VALID_CATEGORIES = {c.value for c in ExpenseCategory}


@router.post("/add")
async def expense_add(request: Request, ctx: BillingContext = Depends(require_billing("manage"))):
    billing = ctx.billing
    detail_url = f"/billings/{billing.uuid}"

    form = await request.form()
    description = str(form.get("description", "")).strip()
    category = str(form.get("category", "")).strip()
    incurred_on = str(form.get("incurred_on", "")).strip()
    amount = parse_brl(str(form.get("amount", "")))

    if not description:
        return flash_redirect(request, "Descrição é obrigatória.", detail_url)
    if category not in _VALID_CATEGORIES:
        return flash_redirect(request, "Categoria inválida.", detail_url)
    if amount is None:
        return flash_redirect(request, "Valor inválido.", detail_url)

    expense = request.state.services.expense.create_expense(
        billing_id=billing.id,
        description=description,
        amount=amount,
        category=category,
        incurred_on=incurred_on,
    )

    request.state.services.audit.safe_log_for(
        request.state.actor,
        AuditEventType.EXPENSE_CREATE,
        entity_type="expense",
        entity_id=expense.id,
        entity_uuid=expense.uuid,
        new_state=serialize_expense(expense),
    )

    flash(request, "Despesa registrada.", "success")
    push_event(
        request,
        {
            "event": "rentivo_expense_created",
            "billing_uuid_hash": analytics_hash(billing.uuid),
            "category": expense.category,
            "amount_brl": round(expense.amount / 100),
        },
    )
    return RedirectResponse(detail_url, status_code=302)


@router.post("/{expense_uuid}/delete")
async def expense_delete(request: Request, expense_uuid: str, ctx: BillingContext = Depends(require_billing("manage"))):
    billing = ctx.billing
    detail_url = f"/billings/{billing.uuid}"
    expense_service = request.state.services.expense

    expense = expense_service.get_by_uuid(expense_uuid)
    if expense is None or expense.billing_id != billing.id:
        logger.warning("expense_not_found", expense_uuid=expense_uuid)
        return flash_redirect(request, "Despesa não encontrada.", detail_url)

    previous_state = serialize_expense(expense)
    expense_service.delete_expense(expense)

    request.state.services.audit.safe_log_for(
        request.state.actor,
        AuditEventType.EXPENSE_DELETE,
        entity_type="expense",
        entity_id=expense.id,
        entity_uuid=expense.uuid,
        previous_state=previous_state,
    )

    flash(request, "Despesa removida.", "success")
    push_event(request, {"event": "rentivo_expense_deleted", "billing_uuid_hash": analytics_hash(billing.uuid)})
    return RedirectResponse(detail_url, status_code=302)
