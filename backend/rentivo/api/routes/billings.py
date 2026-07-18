from __future__ import annotations

from collections.abc import Collection
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from starlette.datastructures import UploadFile

from rentivo.api.authentication import reject_out_of_band_credentials
from rentivo.api.csrf import require_csrf
from rentivo.api.dependencies import get_services, require_resource_grant, require_scope
from rentivo.api.domain_access import BillingAccess, require_role, resolve_billing_access
from rentivo.api.errors import ProblemException, problem
from rentivo.api.principal import Principal
from rentivo.api.schemas.billings import (
    AttachmentListResponse,
    AttachmentResponse,
    BillingCapabilitiesResponse,
    BillingCreateRequest,
    BillingItemInput,
    BillingItemResponse,
    BillingListItemResponse,
    BillingListResponse,
    BillingOwnerResponse,
    BillingResponse,
    BillingStatsResponse,
    BillingTransferRequest,
    BillingUpdateRequest,
    CommunicationPreviewRequest,
    CommunicationPreviewResponse,
    CommunicationSendRequest,
    CommunicationSendResponse,
    CommunicationTemplateResponse,
    ContactInput,
    ContactListRequest,
    ContactListResponse,
    ContactResponse,
    CurrentBillResponse,
    ExpenseCreateRequest,
    ExpenseListResponse,
    ExpenseResponse,
    ExportCreateRequest,
    ExportCreateResponse,
)
from rentivo.communications.moderation import scan
from rentivo.communications.render import render_markdown
from rentivo.constants.api_scopes import APIScope
from rentivo.models.audit_log import AuditEventType
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.billing_attachment import BillingAttachment
from rentivo.models.communication import CommType, Communication
from rentivo.models.expense import Expense
from rentivo.models.recipient import Recipient
from rentivo.services.audit_serializers import (
    serialize_billing,
    serialize_billing_attachment,
    serialize_communication,
    serialize_expense,
)
from rentivo.services.billing_stats import BillingStats
from rentivo.services.container import RequestServices

router = APIRouter(
    prefix="/billings",
    tags=["billings"],
    dependencies=[Depends(reject_out_of_band_credentials)],
)

_billings_read = require_scope(APIScope.BILLINGS_READ)
_billings_write = require_scope(APIScope.BILLINGS_WRITE)
_expenses_read = require_scope(APIScope.EXPENSES_READ)
_expenses_write = require_scope(APIScope.EXPENSES_WRITE)
_files_read = require_scope(APIScope.FILES_READ)
_files_write = require_scope(APIScope.FILES_WRITE)
_communications_read = require_scope(APIScope.COMMUNICATIONS_READ)
_communications_send = require_scope(APIScope.COMMUNICATIONS_SEND)
_exports_create = require_scope(APIScope.EXPORTS_CREATE)

_EDIT_ROLES = frozenset({"owner", "admin"})
_MANAGE_ROLES = frozenset({"owner", "admin", "manager"})


def _field_problem(code: str, detail: str, field: str) -> ProblemException:
    return ProblemException(
        problem(
            status=422,
            code=code,
            title="Dados inválidos",
            detail=detail,
            fields={field: detail},
        )
    )


def _conflict(code: str, detail: str) -> ProblemException:
    return ProblemException(problem(status=409, code=code, title="Conflito", detail=detail))


def _analytics(response: Response, event: str) -> None:
    response.headers["X-Rentivo-Analytics-Event"] = event


def _capabilities(access: BillingAccess) -> BillingCapabilitiesResponse:
    return BillingCapabilitiesResponse(
        can_edit=access.role in _EDIT_ROLES,
        can_manage_bills=access.role in _MANAGE_ROLES,
        can_delete=access.role in _EDIT_ROLES,
        can_transfer=(access.role == "owner" and access.billing.owner_type == "user"),
    )


def _owner(billing: Billing, services: RequestServices) -> BillingOwnerResponse:
    if billing.owner_type != "organization":
        return BillingOwnerResponse(type="user")
    organization = services.organization.get_by_id(billing.owner_id)
    return BillingOwnerResponse(
        type="organization",
        uuid=organization.uuid if organization is not None else None,
        name=organization.name if organization is not None else None,
    )


def _item(item: BillingItem) -> BillingItemResponse:
    item_type = item.item_type.value if hasattr(item.item_type, "value") else str(item.item_type)
    return BillingItemResponse(description=item.description, amount=item.amount, item_type=item_type)


def _contact(recipient: Recipient) -> ContactResponse:
    return ContactResponse(uuid=recipient.uuid, name=recipient.name, email=recipient.email)


def _expense(expense: Expense) -> ExpenseResponse:
    return ExpenseResponse(
        uuid=expense.uuid,
        description=expense.description,
        amount=expense.amount,
        category=expense.category,
        incurred_on=expense.incurred_on,
        created_at=expense.created_at,
    )


def _attachment(attachment: BillingAttachment) -> AttachmentResponse:
    return AttachmentResponse(
        uuid=attachment.uuid,
        name=attachment.name,
        filename=attachment.filename,
        content_type=attachment.content_type,
        file_size=attachment.file_size,
        sort_order=attachment.sort_order,
        created_at=attachment.created_at,
    )


def _stats(stats: BillingStats) -> BillingStatsResponse:
    return BillingStatsResponse(
        year=stats.year,
        expected=stats.expected,
        received=stats.received,
        pending=stats.pending,
        overdue=stats.overdue,
        paid_count=stats.paid_count,
        pending_count=stats.pending_count,
        overdue_count=stats.overdue_count,
        active_count=stats.active_count,
        billed_count=stats.billed_count,
        total_expenses=stats.total_expenses,
        net_income=stats.net_income,
    )


def _current_bill(stats: BillingStats, billing_id: int) -> CurrentBillResponse | None:
    current = stats.current.get(billing_id)
    if current is None:
        return None
    return CurrentBillResponse(
        total_amount=current.total_amount,
        status=current.status,
        reference_month=current.reference_month,
        due_date=current.due_date,
    )


def _visible_accesses(
    principal: Principal,
    services: RequestServices,
    billings: Collection[Billing],
) -> list[BillingAccess]:
    accesses: list[BillingAccess] = []
    for billing in billings:
        if billing.id is None:
            continue
        if not services.api_key.can_access_resource(
            principal.api_key,
            billing.owner_type,
            billing.owner_id,
        ):
            continue
        role = services.authorization.get_role_for_billing(principal.user.id, billing)
        if role is not None:
            accesses.append(BillingAccess(billing=billing, role=role, principal=principal))
    return accesses


def _contact_rows(items: tuple[ContactInput, ...]) -> list[dict[str, str]]:
    return [{"name": item.name, "email": item.email} for item in items]


def _replace_contacts(
    *,
    access: BillingAccess,
    services: RequestServices,
    service_name: Literal["recipient", "reply_to"],
    items: tuple[ContactInput, ...],
    event_type: AuditEventType,
    count_key: str,
    track_previous: bool,
) -> tuple[Recipient, ...]:
    billing_id = access.billing.id
    assert billing_id is not None
    service = getattr(services, service_name)
    previous = service.list_for_billing(billing_id) if track_previous else []
    saved = service.replace_for_billing(billing_id, _contact_rows(items))
    if items or saved or previous:
        services.audit.safe_log_for(
            access.principal.actor,
            event_type,
            entity_type="billing",
            entity_id=billing_id,
            entity_uuid=access.billing.uuid,
            previous_state=({count_key: len(previous)} if track_previous else None),
            new_state={count_key: len(saved)},
        )
    return tuple(saved)


def _billing_response(access: BillingAccess, services: RequestServices) -> BillingResponse:
    billing = access.billing
    billing_id = billing.id
    assert billing_id is not None
    templates = tuple(services.communication.resolve_template(billing, comm_type.value) for comm_type in CommType)
    return BillingResponse(
        uuid=billing.uuid,
        name=billing.name,
        description=billing.description,
        pix_key=billing.pix_key,
        pix_merchant_name=billing.pix_merchant_name,
        pix_merchant_city=billing.pix_merchant_city,
        owner=_owner(billing, services),
        items=tuple(_item(item) for item in billing.items),
        recipients=tuple(_contact(recipient) for recipient in services.recipient.list_for_billing(billing_id)),
        reply_to=tuple(_contact(recipient) for recipient in services.reply_to.list_for_billing(billing_id)),
        communication_templates=tuple(
            CommunicationTemplateResponse(
                comm_type=template.comm_type,
                subject=template.subject,
                body=template.body_markdown,
            )
            for template in templates
        ),
        stats=_stats(services.billing_stats.stats_for_ids([billing_id])),
        pix_needs_setup=services.pix.billing_needs_setup(billing),
        capabilities=_capabilities(access),
        created_at=billing.created_at,
        updated_at=billing.updated_at,
    )


def _billing_items(items: tuple[BillingItemInput, ...]) -> list[BillingItem]:
    return [
        BillingItem(
            description=item.description,
            amount=item.amount,
            item_type=ItemType(item.item_type),
            sort_order=index,
        )
        for index, item in enumerate(items)
    ]


@router.get("", response_model=BillingListResponse)
async def list_billings(
    principal: Principal = Depends(_billings_read),
    services: RequestServices = Depends(get_services),
) -> BillingListResponse:
    accesses = _visible_accesses(
        principal,
        services,
        services.billing.list_billings_for_user(principal.user.id),
    )
    billing_ids = [access.billing.id for access in accesses]
    stats = services.billing_stats.stats_for_ids(billing_ids)
    return BillingListResponse(
        items=tuple(
            BillingListItemResponse(
                uuid=access.billing.uuid,
                name=access.billing.name,
                description=access.billing.description,
                owner=_owner(access.billing, services),
                item_count=len(access.billing.items),
                pix_needs_setup=services.pix.billing_needs_setup(access.billing),
                current_bill=_current_bill(stats, access.billing.id),
                capabilities=_capabilities(access),
            )
            for access in accesses
        ),
        user_pix_incomplete=services.pix.owner_needs_setup("user", principal.user.id),
        stats=_stats(stats),
    )


def _create_owner(
    payload: BillingCreateRequest,
    principal: Principal,
    services: RequestServices,
) -> tuple[Literal["user", "organization"], int]:
    if payload.owner.type == "user":
        require_resource_grant(principal, services, "user", principal.user.id)
        return "user", principal.user.id
    organization = services.organization.get_by_uuid(payload.owner.uuid)
    if organization is None or organization.id is None:
        raise ProblemException.not_found()
    require_resource_grant(principal, services, "organization", organization.id)
    member = services.organization.get_member(organization.id, principal.user.id)
    if member is None:
        raise ProblemException.not_found()
    require_role(member.role, {"admin"})
    return "organization", organization.id


@router.post("", response_model=BillingResponse, status_code=201)
async def create_billing(
    payload: BillingCreateRequest,
    response: Response,
    principal: Principal = Depends(_billings_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> BillingResponse:
    owner_type, owner_id = _create_owner(payload, principal, services)
    try:
        billing = services.billing.create_billing(
            payload.name,
            payload.description,
            _billing_items(payload.items),
            pix_key=payload.pix_key,
            pix_merchant_name=payload.pix_merchant_name,
            pix_merchant_city=payload.pix_merchant_city,
            owner_type=owner_type,
            owner_id=owner_id,
        )
    except ValueError as exc:
        raise _field_problem("invalid_billing", str(exc), "pix_key") from None
    assert billing.id is not None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILLING_CREATE,
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        new_state=serialize_billing(billing),
    )
    access = resolve_billing_access(principal, services, billing.uuid)
    if payload.recipients is not None:
        _replace_contacts(
            access=access,
            services=services,
            service_name="recipient",
            items=payload.recipients,
            event_type=AuditEventType.BILLING_RECIPIENTS_UPDATED,
            count_key="recipient_count",
            track_previous=False,
        )
    if payload.reply_to is not None:
        _replace_contacts(
            access=access,
            services=services,
            service_name="reply_to",
            items=payload.reply_to,
            event_type=AuditEventType.BILLING_REPLY_TO_UPDATED,
            count_key="reply_to_count",
            track_previous=False,
        )
    _analytics(response, "rentivo_billing_created")
    return _billing_response(access, services)


@router.get("/{billing_uuid}", response_model=BillingResponse)
async def get_billing(
    billing_uuid: str,
    principal: Principal = Depends(_billings_read),
    services: RequestServices = Depends(get_services),
) -> BillingResponse:
    return _billing_response(resolve_billing_access(principal, services, billing_uuid), services)


@router.patch("/{billing_uuid}", response_model=BillingResponse)
async def update_billing(
    billing_uuid: str,
    payload: BillingUpdateRequest,
    response: Response,
    principal: Principal = Depends(_billings_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> BillingResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _EDIT_ROLES)
    previous_state = serialize_billing(access.billing)
    candidate = access.billing.model_copy(deep=True)
    for field_name in ("name", "description", "pix_key", "pix_merchant_name", "pix_merchant_city"):
        value = getattr(payload, field_name)
        if value is not None:
            setattr(candidate, field_name, value)
    if payload.items is not None:
        candidate.items = _billing_items(payload.items)
    try:
        updated = services.billing.update_billing(candidate)
    except ValueError as exc:
        raise _field_problem("invalid_billing", str(exc), "pix_key") from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILLING_UPDATE,
        entity_type="billing",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state=previous_state,
        new_state=serialize_billing(updated),
    )
    updated_access = BillingAccess(billing=updated, role=access.role, principal=principal)
    if payload.recipients is not None:
        _replace_contacts(
            access=updated_access,
            services=services,
            service_name="recipient",
            items=payload.recipients,
            event_type=AuditEventType.BILLING_RECIPIENTS_UPDATED,
            count_key="recipient_count",
            track_previous=True,
        )
    if payload.reply_to is not None:
        _replace_contacts(
            access=updated_access,
            services=services,
            service_name="reply_to",
            items=payload.reply_to,
            event_type=AuditEventType.BILLING_REPLY_TO_UPDATED,
            count_key="reply_to_count",
            track_previous=True,
        )
    _analytics(response, "rentivo_billing_edited")
    return _billing_response(updated_access, services)


@router.delete("/{billing_uuid}", status_code=204)
async def delete_billing(
    billing_uuid: str,
    principal: Principal = Depends(_billings_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _EDIT_ROLES)
    billing = access.billing
    assert billing.id is not None
    previous_state = serialize_billing(billing)
    services.storage_cleanup.enqueue_billing_delete_cascade(principal.actor, billing)
    services.billing.delete_billing(billing.id)
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILLING_DELETE,
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_state,
    )
    return Response(status_code=204, headers={"X-Rentivo-Analytics-Event": "rentivo_billing_deleted"})


@router.post("/{billing_uuid}/transfer", status_code=204)
async def transfer_billing(
    billing_uuid: str,
    payload: BillingTransferRequest,
    principal: Principal = Depends(_billings_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, {"owner"})
    if access.billing.owner_type != "user":
        raise ProblemException.forbidden(
            "insufficient_role",
            "Você não possui permissão para esta operação.",
        )
    organization = services.organization.get_by_uuid(payload.organization_uuid)
    if organization is None or organization.id is None:
        raise ProblemException.not_found()
    require_resource_grant(principal, services, "organization", organization.id)
    if services.organization.get_member(organization.id, principal.user.id) is None:
        raise ProblemException.not_found()
    billing = access.billing
    assert billing.id is not None
    previous_owner = {"owner_type": billing.owner_type, "owner_id": billing.owner_id}
    try:
        services.billing.transfer_to_organization(billing.id, organization.id)
    except ValueError as exc:
        raise _conflict("billing_transfer_conflict", str(exc)) from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILLING_TRANSFER,
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_owner,
        new_state={"owner_type": "organization", "owner_id": organization.id},
    )
    services.billing_notification.notify_transferred(
        billing=billing,
        previous_owner=previous_owner,
        new_org_id=organization.id,
        actor_user_id=principal.user.id,
        actor_email=principal.user.email,
    )
    return Response(status_code=204, headers={"X-Rentivo-Analytics-Event": "rentivo_billing_transferred"})


async def _put_contacts(
    *,
    billing_uuid: str,
    payload: ContactListRequest,
    principal: Principal,
    services: RequestServices,
    service_name: Literal["recipient", "reply_to"],
    event_type: AuditEventType,
    count_key: str,
) -> ContactListResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _EDIT_ROLES)
    saved = _replace_contacts(
        access=access,
        services=services,
        service_name=service_name,
        items=payload.items,
        event_type=event_type,
        count_key=count_key,
        track_previous=True,
    )
    return ContactListResponse(items=tuple(_contact(recipient) for recipient in saved))


@router.put("/{billing_uuid}/recipients", response_model=ContactListResponse)
async def replace_recipients(
    billing_uuid: str,
    payload: ContactListRequest,
    principal: Principal = Depends(_billings_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ContactListResponse:
    return await _put_contacts(
        billing_uuid=billing_uuid,
        payload=payload,
        principal=principal,
        services=services,
        service_name="recipient",
        event_type=AuditEventType.BILLING_RECIPIENTS_UPDATED,
        count_key="recipient_count",
    )


@router.put("/{billing_uuid}/reply-to", response_model=ContactListResponse)
async def replace_reply_to(
    billing_uuid: str,
    payload: ContactListRequest,
    principal: Principal = Depends(_billings_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ContactListResponse:
    return await _put_contacts(
        billing_uuid=billing_uuid,
        payload=payload,
        principal=principal,
        services=services,
        service_name="reply_to",
        event_type=AuditEventType.BILLING_REPLY_TO_UPDATED,
        count_key="reply_to_count",
    )


@router.get("/{billing_uuid}/expenses", response_model=ExpenseListResponse)
async def list_expenses(
    billing_uuid: str,
    principal: Principal = Depends(_expenses_read),
    services: RequestServices = Depends(get_services),
) -> ExpenseListResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    assert access.billing.id is not None
    return ExpenseListResponse(
        items=tuple(_expense(expense) for expense in services.expense.list_for_billing(access.billing.id))
    )


@router.post("/{billing_uuid}/expenses", response_model=ExpenseResponse, status_code=201)
async def create_expense(
    billing_uuid: str,
    payload: ExpenseCreateRequest,
    response: Response,
    principal: Principal = Depends(_expenses_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ExpenseResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _MANAGE_ROLES)
    assert access.billing.id is not None
    expense = services.expense.create_expense(
        billing_id=access.billing.id,
        description=payload.description,
        amount=payload.amount,
        category=payload.category,
        incurred_on=payload.incurred_on.isoformat(),
    )
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.EXPENSE_CREATE,
        entity_type="expense",
        entity_id=expense.id,
        entity_uuid=expense.uuid,
        new_state=serialize_expense(expense),
    )
    _analytics(response, "rentivo_expense_created")
    return _expense(expense)


@router.delete("/{billing_uuid}/expenses/{expense_uuid}", status_code=204)
async def delete_expense(
    billing_uuid: str,
    expense_uuid: str,
    principal: Principal = Depends(_expenses_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _MANAGE_ROLES)
    expense = services.expense.get_by_uuid(expense_uuid)
    if expense is None or expense.billing_id != access.billing.id:
        raise ProblemException.not_found()
    previous_state = serialize_expense(expense)
    services.expense.delete_expense(expense)
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.EXPENSE_DELETE,
        entity_type="expense",
        entity_id=expense.id,
        entity_uuid=expense.uuid,
        previous_state=previous_state,
    )
    return Response(status_code=204, headers={"X-Rentivo-Analytics-Event": "rentivo_expense_deleted"})


@router.get("/{billing_uuid}/attachments", response_model=AttachmentListResponse)
async def list_attachments(
    billing_uuid: str,
    principal: Principal = Depends(_files_read),
    services: RequestServices = Depends(get_services),
) -> AttachmentListResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    assert access.billing.id is not None
    return AttachmentListResponse(
        items=tuple(
            _attachment(attachment) for attachment in services.billing_attachment.list_attachments(access.billing.id)
        )
    )


@router.post("/{billing_uuid}/attachments", response_model=AttachmentResponse, status_code=201)
async def upload_attachment(
    billing_uuid: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(_files_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> AttachmentResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _EDIT_ROLES)
    form = await request.form()
    file = form.get("file")
    if not isinstance(file, UploadFile) or not file.filename:
        raise _field_problem("invalid_attachment", "Nenhum arquivo selecionado.", "file")
    try:
        attachment = services.billing_attachment.add_attachment(
            billing=access.billing,
            name=str(form.get("name", "")).strip(),
            filename=file.filename,
            file_bytes=await file.read(),
            content_type=file.content_type or "",
        )
    except ValueError as exc:
        raise _field_problem("invalid_attachment", str(exc), "file") from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.ATTACHMENT_UPLOAD,
        entity_type="billing_attachment",
        entity_id=attachment.id,
        entity_uuid=attachment.uuid,
        new_state=serialize_billing_attachment(attachment, billing_uuid=access.billing.uuid),
    )
    _analytics(response, "rentivo_billing_attachment_uploaded")
    return _attachment(attachment)


def _billing_attachment(
    *,
    access: BillingAccess,
    services: RequestServices,
    attachment_uuid: str,
) -> BillingAttachment:
    attachment = services.billing_attachment.get_attachment_by_uuid(attachment_uuid)
    if attachment is None or attachment.billing_id != access.billing.id or not attachment.storage_key:
        raise ProblemException.not_found()
    return attachment


@router.get("/{billing_uuid}/attachments/{attachment_uuid}")
async def download_attachment(
    billing_uuid: str,
    attachment_uuid: str,
    principal: Principal = Depends(_files_read),
    services: RequestServices = Depends(get_services),
):
    access = resolve_billing_access(principal, services, billing_uuid)
    attachment = _billing_attachment(access=access, services=services, attachment_uuid=attachment_uuid)
    reference = services.billing_attachment.get_attachment_ref(attachment)
    if reference.kind == "local":
        return FileResponse(
            reference.location,
            media_type=attachment.content_type,
            filename=attachment.filename,
        )
    return RedirectResponse(reference.location, status_code=302)


@router.delete("/{billing_uuid}/attachments/{attachment_uuid}", status_code=204)
async def delete_attachment(
    billing_uuid: str,
    attachment_uuid: str,
    principal: Principal = Depends(_files_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _EDIT_ROLES)
    attachment = _billing_attachment(access=access, services=services, attachment_uuid=attachment_uuid)
    previous_state = serialize_billing_attachment(attachment, billing_uuid=access.billing.uuid)
    services.billing_attachment.delete_attachment(attachment)
    services.storage_cleanup.enqueue_attachment_delete(principal.actor, attachment)
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.ATTACHMENT_DELETE,
        entity_type="billing_attachment",
        entity_id=attachment.id,
        entity_uuid=attachment.uuid,
        previous_state=previous_state,
    )
    return Response(
        status_code=204,
        headers={"X-Rentivo-Analytics-Event": "rentivo_billing_attachment_deleted"},
    )


@router.post("/{billing_uuid}/exports", response_model=ExportCreateResponse, status_code=202)
async def create_export(
    billing_uuid: str,
    payload: ExportCreateRequest,
    response: Response,
    principal: Principal = Depends(_exports_create),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ExportCreateResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    assert access.billing.id is not None
    services.job.enqueue_for(
        principal.actor,
        "export.generate",
        {
            "billing_id": access.billing.id,
            "format": payload.format,
            "requested_by_user_id": principal.user.id,
        },
    )
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILLING_EXPORT,
        entity_type="billing",
        entity_id=access.billing.id,
        entity_uuid=access.billing.uuid,
        new_state={"format": payload.format},
    )
    _analytics(response, "rentivo_data_exported")
    return ExportCreateResponse(format=payload.format)


@router.post("/{billing_uuid}/communications/preview", response_model=CommunicationPreviewResponse)
async def preview_communication(
    billing_uuid: str,
    payload: CommunicationPreviewRequest,
    principal: Principal = Depends(_communications_read),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> CommunicationPreviewResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _MANAGE_ROLES)
    moderation = scan(f"{payload.subject}\n{payload.body}")
    return CommunicationPreviewResponse(
        html=render_markdown(payload.body),
        severe=moderation.severe,
        mild=moderation.mild,
    )


def _communication_bill(access: BillingAccess, services: RequestServices, bill_uuid: str):
    bill = services.bill.get_bill_by_uuid(bill_uuid)
    if bill is None or bill.id is None or bill.billing_id != access.billing.id:
        raise ProblemException.not_found()
    return bill


def _selected_recipients(
    access: BillingAccess,
    services: RequestServices,
    recipient_uuids: tuple[str, ...],
) -> list[Recipient]:
    assert access.billing.id is not None
    by_uuid = {recipient.uuid: recipient for recipient in services.recipient.list_for_billing(access.billing.id)}
    if any(recipient_uuid not in by_uuid for recipient_uuid in recipient_uuids):
        raise _field_problem(
            "invalid_recipients",
            "Selecione somente destinatários desta cobrança.",
            "recipient_uuids",
        )
    return [by_uuid[recipient_uuid] for recipient_uuid in recipient_uuids]


def _audit_communications(
    communications: Collection[Communication],
    principal: Principal,
    services: RequestServices,
) -> None:
    for communication in communications:
        services.audit.safe_log_for(
            principal.actor,
            AuditEventType.COMMUNICATION_SENT,
            entity_type="communication",
            entity_id=communication.id,
            entity_uuid=communication.uuid,
            new_state=serialize_communication(communication),
        )


@router.post(
    "/{billing_uuid}/communications/send",
    response_model=CommunicationSendResponse,
    status_code=202,
)
async def send_communication(
    billing_uuid: str,
    payload: CommunicationSendRequest,
    response: Response,
    principal: Principal = Depends(_communications_send),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> CommunicationSendResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _MANAGE_ROLES)
    bill = _communication_bill(access, services, payload.bill_uuid)
    if payload.save_scope == "owner":
        require_role(access.role, _EDIT_ROLES)
    if payload.comm_type == CommType.PAYMENT_RECEIPT.value:
        if not bill.recibo_pdf_path:
            raise _conflict("receipt_unavailable", "O recibo ainda não está disponível para envio.")
    elif not bill.pdf_path:
        raise _conflict("invoice_unavailable", "Gere o PDF da fatura antes de enviar a comunicação.")
    recipients = _selected_recipients(access, services, payload.recipient_uuids)
    moderation = scan(f"{payload.subject}\n{payload.body}")
    if moderation.blocked:
        services.audit.safe_log_for(
            principal.actor,
            AuditEventType.COMMUNICATION_BLOCKED,
            entity_type="bill",
            entity_id=bill.id,
            entity_uuid=bill.uuid,
            new_state={"severe_count": len(moderation.severe), "mild_count": len(moderation.mild)},
        )
        raise _field_problem(
            "communication_blocked",
            "A mensagem contém conteúdo não permitido e não pode ser enviada.",
            "body",
        )
    if moderation.flagged and not payload.acknowledge_warning:
        raise _field_problem(
            "communication_warning_unacknowledged",
            "Reconheça o aviso de conteúdo antes de enviar.",
            "acknowledge_warning",
        )
    communications = services.communication.send(
        bill=bill,
        billing=access.billing,
        recipients=recipients,
        subject_template=payload.subject,
        body_template=payload.body,
        actor=principal.actor,
        comm_type=payload.comm_type,
    )
    if payload.save_scope == "billing":
        services.communication.save_template(
            "billing",
            access.billing.id,
            payload.comm_type,
            payload.subject,
            payload.body,
        )
    elif payload.save_scope == "owner":
        services.communication.save_template(
            access.billing.owner_type,
            access.billing.owner_id,
            payload.comm_type,
            payload.subject,
            payload.body,
        )
    if payload.save_scope is not None:
        services.audit.safe_log_for(
            principal.actor,
            AuditEventType.COMMUNICATION_TEMPLATE_SAVED,
            entity_type="billing",
            entity_id=access.billing.id,
            entity_uuid=access.billing.uuid,
            new_state={"scope": payload.save_scope, "comm_type": payload.comm_type},
        )
    _audit_communications(communications, principal, services)
    if moderation.flagged:
        services.audit.safe_log_for(
            principal.actor,
            AuditEventType.COMMUNICATION_FLAGGED_OVERRIDE,
            entity_type="bill",
            entity_id=bill.id,
            entity_uuid=bill.uuid,
            new_state={"mild_count": len(moderation.mild)},
        )
    _analytics(response, "rentivo_communication_sent")
    return CommunicationSendResponse(queued_count=len(communications))
