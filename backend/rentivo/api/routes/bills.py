from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import ValidationError

from rentivo.analytics import analytics_hash
from rentivo.api.csrf import require_csrf
from rentivo.api.dependencies import get_services, require_scope
from rentivo.api.domain_access import (
    BillAccess,
    require_role,
    resolve_bill_access,
    resolve_billing_access,
)
from rentivo.api.errors import Problem, ProblemException, problem
from rentivo.api.principal import Principal
from rentivo.api.schemas.bills import (
    AvailableTransitionResponse,
    BillCapabilitiesResponse,
    BillCreateRequest,
    BillDetailResponse,
    BillLineItemResponse,
    BillListResponse,
    BillResponse,
    BillTransitionRequest,
    BillUpdateRequest,
    CommunicationHistoryResponse,
    ReceiptListResponse,
    ReceiptOrderRequest,
    ReceiptResponse,
    ReceiptUploadResponse,
    ReceiptUploadSummary,
    ReciboDownloadResponse,
    RedactedCommunicationHistoryResponse,
)
from rentivo.bill_transitions import StatusTransition, transitions_for
from rentivo.constants.api_scopes import APIScope
from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill, BillLineItem, BillStatus, InvalidStatusTransition
from rentivo.models.billing import Billing, ItemType
from rentivo.models.communication import Communication
from rentivo.models.receipt import ALLOWED_RECEIPT_TYPES, MAX_RECEIPT_SIZE, Receipt
from rentivo.services.audit_serializers import serialize_bill, serialize_receipt
from rentivo.services.bill_service import StaleBillDeleteError, StaleBillStatusError, StaleReceiptDeleteError
from rentivo.services.container import RequestServices
from rentivo.storage.base import FileRef

router = APIRouter(prefix="/billings/{billing_uuid}/bills", tags=["bills"])

_bills_read = require_scope(APIScope.BILLS_READ)
_bills_write = require_scope(APIScope.BILLS_WRITE)
_files_read = require_scope(APIScope.FILES_READ)
_files_write = require_scope(APIScope.FILES_WRITE)
_MANAGE_ROLES = frozenset({"owner", "admin", "manager"})
_DELETE_ROLES = frozenset({"owner", "admin"})
_BILL_CREATE_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/BillCreateRequest"},
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["payload"],
                    "properties": {
                        "payload": {"$ref": "#/components/schemas/BillCreateRequest"},
                        "receipt_files": {
                            "type": "array",
                            "items": {"type": "string", "format": "binary"},
                        },
                    },
                },
                "encoding": {"payload": {"contentType": "application/json"}},
            },
        },
    },
}


class BrowserUploadFile(UploadFile):
    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {"type": "string", "format": "binary"}


def _analytics(response: Response, event: str, **metadata: str | int) -> None:
    response.headers["X-Rentivo-Analytics-Event"] = event
    for name, value in metadata.items():
        header = "-".join(part.title() for part in name.split("_"))
        response.headers[f"X-Rentivo-Analytics-{header}"] = str(value)


def _conflict(code: str, detail: str) -> ProblemException:
    return ProblemException(problem(status=409, code=code, title="Conflito", detail=detail))


def _validation_error(exc: ValidationError | json.JSONDecodeError) -> ProblemException:
    fields: dict[str, str] = {}
    if isinstance(exc, ValidationError):
        fields = {".".join(str(part) for part in error["loc"]): error["msg"] for error in exc.errors()}
    return ProblemException(
        problem(
            status=422,
            code="validation_error",
            title="Dados inválidos",
            detail="Os dados da fatura são inválidos.",
            fields=fields,
        )
    )


class _DuplicateVariableAmount(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result and len(key) == 26:
            raise _DuplicateVariableAmount
        result[key] = value
    return result


def _duplicate_variable_amount_error() -> ProblemException:
    return ProblemException(
        problem(
            status=422,
            code="validation_error",
            title="Dados inválidos",
            detail="Os dados da fatura são inválidos.",
            fields={"variable_amounts": "Cada item variável deve aparecer uma única vez."},
        )
    )


async def _create_request(request: Request, form_payload: str | None) -> BillCreateRequest:
    try:
        raw_payload: str | bytes = form_payload if form_payload is not None else await request.body()
        decoded = json.loads(raw_payload, object_pairs_hook=_unique_json_object)
        return BillCreateRequest.model_validate(decoded)
    except _DuplicateVariableAmount:
        raise _duplicate_variable_amount_error() from None
    except (ValidationError, json.JSONDecodeError) as exc:
        raise _validation_error(exc) from None


def _has_scope(principal: Principal, scope: APIScope) -> bool:
    return scope.value in principal.api_key.scopes


def _transition_responses(status: str, *, enabled: bool) -> tuple[AvailableTransitionResponse, ...]:
    if not enabled:
        return ()
    primary, others = transitions_for(status)
    transitions: list[StatusTransition] = ([] if primary is None else [primary]) + list(others)
    return tuple(
        AvailableTransitionResponse(
            target=transition.to,
            label=transition.label,
            style=transition.variant,
            requires_confirmation=transition.confirm,
        )
        for transition in transitions
    )


def _iso_due_date(value: str | None) -> str | None:
    if not value:
        return None
    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _domain_due_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value is not None else ""


def _capabilities(
    bill: Bill,
    billing: Billing,
    role: str,
    principal: Principal,
    services: RequestServices,
) -> BillCapabilitiesResponse:
    can_manage = role in _MANAGE_ROLES
    can_delete = role in _DELETE_ROLES
    bills_write = _has_scope(principal, APIScope.BILLS_WRITE)
    files_read = _has_scope(principal, APIScope.FILES_READ)
    files_write = _has_scope(principal, APIScope.FILES_WRITE)
    communications_ready = _has_scope(principal, APIScope.COMMUNICATIONS_READ) and _has_scope(
        principal,
        APIScope.COMMUNICATIONS_SEND,
    )
    pix_ready = not services.pix.billing_needs_setup(billing)
    can_compose = can_manage and communications_ready
    return BillCapabilitiesResponse(
        can_edit=can_manage and bills_write,
        can_delete=can_delete and bills_write,
        can_transition=can_manage and bills_write,
        can_regenerate=can_manage and bills_write and pix_ready,
        can_upload_receipts=can_manage and files_write and pix_ready,
        can_delete_receipts=can_manage and files_write,
        can_reorder_receipts=can_manage and files_write,
        can_download_invoice=files_read and bool(bill.pdf_path),
        can_download_recibo=(files_read and bill.status == BillStatus.PAID.value and bool(bill.recibo_pdf_path)),
        can_compose=can_compose,
        can_send_invoice=can_compose and bool(bill.pdf_path),
        can_send_recibo=(can_compose and bill.status == BillStatus.PAID.value and bool(bill.recibo_pdf_path)),
    )


def _bill_response(
    bill: Bill,
    billing: Billing,
    role: str,
    principal: Principal,
    services: RequestServices,
) -> BillResponse:
    capabilities = _capabilities(bill, billing, role, principal, services)
    return BillResponse(
        uuid=bill.uuid,
        reference_month=bill.reference_month,
        total_amount=bill.total_amount,
        line_items=tuple(
            BillLineItemResponse(
                description=item.description,
                amount=item.amount,
                item_type=item.item_type,
                sort_order=item.sort_order,
            )
            for item in bill.line_items
        ),
        notes=bill.notes,
        due_date=_iso_due_date(bill.due_date),
        status=bill.status,
        status_updated_at=bill.status_updated_at,
        pdf_render_status=bill.pdf_render_status,
        created_at=bill.created_at,
        has_invoice=bool(bill.pdf_path),
        has_recibo=bool(bill.recibo_pdf_path),
        available_transitions=_transition_responses(bill.status, enabled=capabilities.can_transition),
        capabilities=capabilities,
    )


def _receipt_response(receipt: Receipt) -> ReceiptResponse:
    return ReceiptResponse(
        uuid=receipt.uuid,
        filename=receipt.filename,
        content_type=receipt.content_type,
        file_size=receipt.file_size,
        sort_order=receipt.sort_order,
        created_at=receipt.created_at,
    )


def _communication_response(
    communication: Communication,
    *,
    expose_pii: bool,
) -> CommunicationHistoryResponse | RedactedCommunicationHistoryResponse:
    common = {
        "uuid": communication.uuid,
        "comm_type": communication.comm_type,
        "status": communication.status,
        "created_at": communication.created_at,
        "sent_at": communication.sent_at,
    }
    if not expose_pii:
        return RedactedCommunicationHistoryResponse(**common)
    return CommunicationHistoryResponse(
        **common,
        recipient_name=communication.recipient_name,
        recipient_email=communication.recipient_email,
        subject=communication.subject,
    )


def _bill_detail_response(
    access: BillAccess,
    services: RequestServices,
    *,
    receipt_upload: ReceiptUploadSummary | None = None,
) -> BillDetailResponse:
    bill = access.bill
    receipts = (
        services.bill.list_receipts(bill.id)
        if bill.id is not None and _has_scope(access.principal, APIScope.FILES_READ)
        else []
    )
    communications = (
        services.communication.list_for_bill(bill.id)
        if bill.id is not None and _has_scope(access.principal, APIScope.COMMUNICATIONS_READ)
        else []
    )
    response = _bill_response(bill, access.billing, access.role, access.principal, services)
    return BillDetailResponse(
        **response.model_dump(),
        receipts=tuple(_receipt_response(receipt) for receipt in receipts),
        communications=tuple(
            _communication_response(item, expose_pii=access.principal.api_key.is_login_token) for item in communications
        ),
        receipt_upload=receipt_upload or ReceiptUploadSummary(),
    )


def _require_pix(billing: Billing, services: RequestServices) -> None:
    if services.pix.billing_needs_setup(billing):
        raise _conflict(
            "pix_setup_required",
            "Configure a chave PIX, o nome e a cidade do recebedor antes de continuar.",
        )


def _receipt_for_bill(access: BillAccess, services: RequestServices, receipt_uuid: str) -> Receipt:
    receipt = services.bill.get_receipt_by_uuid(receipt_uuid)
    if receipt is None or receipt.bill_id != access.bill.id:
        raise ProblemException.not_found()
    return receipt


def _file_response(ref: FileRef, *, content_type: str, filename: str) -> Response:
    if ref.kind == "local":
        return FileResponse(ref.location, media_type=content_type, filename=filename)
    return RedirectResponse(ref.location, status_code=302)


def _audit_recibo_download(access: BillAccess, services: RequestServices) -> None:
    services.audit.safe_log_for(
        access.principal.actor,
        AuditEventType.BILL_RECIBO_DOWNLOAD,
        entity_type="bill",
        entity_id=access.bill.id,
        entity_uuid=access.bill.uuid,
    )


@dataclass(frozen=True, slots=True)
class _ValidatedReceiptUpload:
    filename: str
    file_bytes: bytes
    content_type: str


async def _validate_receipt_uploads(
    uploads: Sequence[UploadFile],
) -> tuple[tuple[_ValidatedReceiptUpload, ...], int]:
    valid: list[_ValidatedReceiptUpload] = []
    skipped = 0
    for upload in uploads:
        file_bytes = await upload.read()
        content_type = upload.content_type or ""
        if content_type not in ALLOWED_RECEIPT_TYPES or not file_bytes or len(file_bytes) > MAX_RECEIPT_SIZE:
            skipped += 1
            continue
        valid.append(
            _ValidatedReceiptUpload(
                filename=upload.filename or "comprovante",
                file_bytes=file_bytes,
                content_type=content_type,
            )
        )
    return tuple(valid), skipped


def _audit_receipt_uploads(
    receipts: Sequence[Receipt],
    access: BillAccess,
    services: RequestServices,
) -> None:
    for receipt in receipts:
        services.audit.safe_log_for(
            access.principal.actor,
            AuditEventType.RECEIPT_UPLOAD,
            entity_type="receipt",
            entity_id=receipt.id,
            entity_uuid=receipt.uuid,
            new_state=serialize_receipt(
                receipt,
                bill_uuid=access.bill.uuid,
                billing_uuid=access.billing.uuid,
            ),
        )


def _attach_receipts(
    uploads: Sequence[_ValidatedReceiptUpload],
    skipped: int,
    access: BillAccess,
    services: RequestServices,
    *,
    regenerate: bool,
    audit: bool,
) -> tuple[ReceiptUploadResponse, tuple[Receipt, ...]]:
    attached: list[Receipt] = []
    try:
        for upload in uploads:
            receipt, _failed = services.bill.add_receipt(
                bill=access.bill,
                billing=access.billing,
                filename=upload.filename,
                file_bytes=upload.file_bytes,
                content_type=upload.content_type,
                actor=access.principal.actor,
                render=False,
            )
            attached.append(receipt)
    except Exception:
        services.bill.rollback_receipt_batch(tuple(attached))
        raise
    if audit:
        _audit_receipt_uploads(attached, access, services)
    if regenerate and attached:
        services.bill.regenerate_pdf(access.bill, access.billing, actor=access.principal.actor)
    total_bytes = sum(len(upload.file_bytes) for upload in uploads)
    receipts = tuple(attached)
    return (
        ReceiptUploadResponse(
            attached=len(receipts),
            skipped=skipped,
            total_bytes=total_bytes,
            items=tuple(_receipt_response(receipt) for receipt in receipts),
        ),
        receipts,
    )


async def _upload_receipts(
    uploads: Sequence[UploadFile],
    access: BillAccess,
    services: RequestServices,
    *,
    regenerate: bool,
) -> ReceiptUploadResponse:
    valid, skipped = await _validate_receipt_uploads(uploads)
    response, _receipts = _attach_receipts(
        valid,
        skipped,
        access,
        services,
        regenerate=regenerate,
        audit=True,
    )
    return response


@router.get("", response_model=BillListResponse, responses={404: {"model": Problem}})
async def list_bills(
    billing_uuid: str,
    principal: Principal = Depends(_bills_read),
    services: RequestServices = Depends(get_services),
) -> BillListResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    bills = services.bill.list_bills(access.billing.id)
    return BillListResponse(
        items=tuple(_bill_response(bill, access.billing, access.role, principal, services) for bill in bills)
    )


@router.post(
    "",
    response_model=BillDetailResponse,
    status_code=201,
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}, 422: {"model": Problem}},
    openapi_extra=_BILL_CREATE_OPENAPI,
)
async def create_bill(
    request: Request,
    billing_uuid: str,
    response: Response,
    payload: Annotated[str | BillCreateRequest | None, Form()] = None,
    receipt_files: Annotated[list[BrowserUploadFile] | None, File()] = None,
    principal: Principal = Depends(_bills_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> BillDetailResponse:
    access = resolve_billing_access(principal, services, billing_uuid)
    require_role(access.role, _MANAGE_ROLES)
    if receipt_files and not _has_scope(principal, APIScope.FILES_WRITE):
        raise ProblemException.forbidden("missing_scope", "A chave não possui o escopo necessário.")
    _require_pix(access.billing, services)
    create = await _create_request(request, cast(str | None, payload))
    required_variable_uuids = {item.uuid for item in access.billing.items if item.item_type == ItemType.VARIABLE}
    if set(create.variable_amounts) != required_variable_uuids:
        message = "Informe o valor de todos os itens variáveis."
        raise ProblemException(
            problem(
                status=422,
                code="invalid_variable_amounts",
                title="Dados inválidos",
                detail=message,
                fields={"variable_amounts": message},
            )
        )
    valid_uploads, skipped = await _validate_receipt_uploads(receipt_files or ())
    try:
        bill = services.bill.generate_bill(
            billing=access.billing,
            reference_month=create.reference_month,
            variable_amounts=create.variable_amounts,
            extras=[(extra.description, extra.amount) for extra in create.extras],
            notes=create.notes,
            due_date=_domain_due_date(create.due_date),
            actor=principal.actor,
            render=False,
        )
    except ValueError as exc:
        raise ProblemException(
            problem(
                status=422,
                code="invalid_variable_amounts",
                title="Dados inválidos",
                detail=str(exc),
                fields={"variable_amounts": str(exc)},
            )
        ) from None
    bill_access = BillAccess(bill=bill, billing=access.billing, role=access.role, principal=principal)
    try:
        upload, attached_receipts = _attach_receipts(
            valid_uploads,
            skipped,
            bill_access,
            services,
            regenerate=False,
            audit=False,
        )
        services.bill.regenerate_pdf(bill, access.billing, actor=principal.actor)
    except Exception:
        services.bill.rollback_bill_creation(bill, access.billing)
        raise
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILL_CREATE,
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        new_state=serialize_bill(bill),
    )
    _audit_receipt_uploads(attached_receipts, bill_access, services)
    _analytics(
        response,
        "rentivo_bill_generated",
        billing_uuid_hash=analytics_hash(access.billing.uuid) or "",
        bill_uuid_hash=analytics_hash(bill.uuid) or "",
        reference_month=bill.reference_month,
        line_item_count=len(bill.line_items),
        total_amount_brl=round(bill.total_amount / 100),
        receipt_count=upload.attached,
    )
    return _bill_detail_response(
        bill_access,
        services,
        receipt_upload=ReceiptUploadSummary(
            attached=upload.attached,
            skipped=upload.skipped,
            total_bytes=upload.total_bytes,
        ),
    )


@router.get("/{bill_uuid}", response_model=BillDetailResponse, responses={404: {"model": Problem}})
async def get_bill(
    billing_uuid: str,
    bill_uuid: str,
    principal: Principal = Depends(_bills_read),
    services: RequestServices = Depends(get_services),
) -> BillDetailResponse:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    return _bill_detail_response(access, services)


@router.patch(
    "/{bill_uuid}",
    response_model=BillDetailResponse,
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}},
)
async def update_bill(
    payload: BillUpdateRequest,
    billing_uuid: str,
    bill_uuid: str,
    response: Response,
    principal: Principal = Depends(_bills_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> BillDetailResponse:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    require_role(access.role, _MANAGE_ROLES)
    _require_pix(access.billing, services)
    previous_state = serialize_bill(access.bill)
    fields = payload.model_fields_set
    line_items = (
        access.bill.line_items
        if "line_items" not in fields
        else [
            BillLineItem(
                description=item.description,
                amount=item.amount,
                item_type=item.item_type,
                sort_order=index,
            )
            for index, item in enumerate(payload.line_items or ())
        ]
    )
    notes = access.bill.notes if "notes" not in fields else payload.notes or ""
    if "due_date" not in fields:
        due_date = access.bill.due_date or ""
    else:
        due_date = _domain_due_date(payload.due_date)
    updated = services.bill.update_bill(
        bill=access.bill,
        billing=access.billing,
        line_items=line_items,
        notes=notes,
        due_date=due_date,
        actor=principal.actor,
    )
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILL_UPDATE,
        entity_type="bill",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state=previous_state,
        new_state=serialize_bill(updated),
    )
    _analytics(
        response,
        "rentivo_bill_edited",
        bill_uuid_hash=analytics_hash(updated.uuid) or "",
    )
    return _bill_detail_response(
        BillAccess(bill=updated, billing=access.billing, role=access.role, principal=principal),
        services,
    )


@router.delete(
    "/{bill_uuid}",
    status_code=204,
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}},
)
async def delete_bill(
    billing_uuid: str,
    bill_uuid: str,
    principal: Principal = Depends(_bills_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    require_role(access.role, _DELETE_ROLES)
    previous_state = serialize_bill(access.bill)
    try:
        services.bill.delete_bill(access.bill.id)
    except StaleBillDeleteError:
        raise _conflict("stale_bill_delete", "A fatura já foi excluída por outra operação.") from None
    # Cleanup jobs are idempotent and are scheduled only after the conditional
    # soft-delete confirms this request won the race.
    services.storage_cleanup.enqueue_bill_delete_cascade(principal.actor, access.bill)
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILL_DELETE,
        entity_type="bill",
        entity_id=access.bill.id,
        entity_uuid=access.bill.uuid,
        previous_state=previous_state,
    )
    response = Response(status_code=204)
    _analytics(response, "rentivo_bill_deleted", bill_uuid_hash=analytics_hash(access.bill.uuid) or "")
    return response


@router.post(
    "/{bill_uuid}/transitions",
    response_model=BillDetailResponse,
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}},
)
async def transition_bill(
    payload: BillTransitionRequest,
    billing_uuid: str,
    bill_uuid: str,
    response: Response,
    principal: Principal = Depends(_bills_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> BillDetailResponse:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    require_role(access.role, _MANAGE_ROLES)
    if payload.current_status is not None and payload.current_status.value != access.bill.status:
        raise _conflict("stale_bill_status", "O status da fatura foi alterado. Atualize a página e tente novamente.")
    target = payload.target.value
    offered = {item.target for item in _transition_responses(access.bill.status, enabled=True)}
    if target not in offered:
        raise _conflict("invalid_status_transition", "Transição de status inválida.")
    previous_status = access.bill.status
    try:
        updated = services.bill.change_status(
            access.bill,
            target,
            billing=access.billing,
            actor=principal.actor,
        )
    except InvalidStatusTransition:
        raise _conflict("invalid_status_transition", "Transição de status inválida.") from None
    except StaleBillStatusError:
        raise _conflict(
            "stale_bill_status",
            "O status da fatura foi alterado. Atualize a página e tente novamente.",
        ) from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILL_STATUS_CHANGE,
        entity_type="bill",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state={"status": previous_status},
        new_state={"status": updated.status},
    )
    _analytics(
        response,
        "rentivo_bill_status_changed",
        bill_uuid_hash=analytics_hash(updated.uuid) or "",
        new_status=updated.status,
    )
    return _bill_detail_response(
        BillAccess(bill=updated, billing=access.billing, role=access.role, principal=principal),
        services,
    )


@router.post(
    "/{bill_uuid}/regenerate",
    response_model=BillResponse,
    status_code=202,
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}},
)
async def regenerate_bill(
    billing_uuid: str,
    bill_uuid: str,
    response: Response,
    principal: Principal = Depends(_bills_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> BillResponse:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    require_role(access.role, _MANAGE_ROLES)
    _require_pix(access.billing, services)
    previous_status = access.bill.pdf_render_status
    services.bill.regenerate_pdf(access.bill, access.billing, actor=principal.actor)
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILL_REGENERATE_PDF,
        entity_type="bill",
        entity_id=access.bill.id,
        entity_uuid=access.bill.uuid,
        previous_state={"pdf_render_status": previous_status},
        new_state={"pdf_render_status": access.bill.pdf_render_status},
    )
    _analytics(
        response,
        "rentivo_bill_regenerated",
        bill_uuid_hash=analytics_hash(access.bill.uuid) or "",
    )
    return _bill_response(access.bill, access.billing, access.role, principal, services)


@router.get("/{bill_uuid}/invoice", responses={403: {"model": Problem}, 404: {"model": Problem}})
async def download_invoice(
    billing_uuid: str,
    bill_uuid: str,
    principal: Principal = Depends(_files_read),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    if not access.bill.pdf_path:
        raise ProblemException.not_found()
    ref = services.bill.get_invoice_ref(access.bill)
    return _file_response(ref, content_type="application/pdf", filename=f"fatura-{access.bill.uuid}.pdf")


@router.get(
    "/{bill_uuid}/recibo", responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}}
)
async def download_recibo(
    billing_uuid: str,
    bill_uuid: str,
    principal: Principal = Depends(_files_read),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    if access.bill.status != BillStatus.PAID.value:
        raise _conflict("recibo_unavailable", "O recibo só fica disponível quando a fatura está paga.")
    filename = f"recibo-{access.bill.uuid}.pdf"
    if access.bill.recibo_pdf_path:
        response = _file_response(
            services.bill.get_recibo_ref(access.bill),
            content_type="application/pdf",
            filename=filename,
        )
    else:
        pdf_bytes = services.bill.render_recibo(access.bill, access.billing)
        response = Response(
            content=bytes(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    _audit_recibo_download(access, services)
    _analytics(
        response,
        "rentivo_recibo_downloaded",
        bill_uuid_hash=analytics_hash(access.bill.uuid) or "",
    )
    return response


@router.get(
    "/{bill_uuid}/recibo/download",
    response_model=ReciboDownloadResponse,
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}},
)
async def get_recibo_download(
    billing_uuid: str,
    bill_uuid: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(_files_read),
    services: RequestServices = Depends(get_services),
) -> ReciboDownloadResponse:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    if access.bill.status != BillStatus.PAID.value:
        raise _conflict("recibo_unavailable", "O recibo só fica disponível quando a fatura está paga.")
    if not access.bill.recibo_pdf_path:
        raise _conflict("recibo_not_ready", "O recibo ainda está sendo gerado.")

    ref = services.bill.get_recibo_ref(access.bill)
    if ref.kind == "local":
        download_url = str(
            request.url_for(
                "download_recibo_content",
                billing_uuid=access.billing.uuid,
                bill_uuid=access.bill.uuid,
            )
        )
    else:
        download_url = ref.location
        _audit_recibo_download(access, services)
    filename = f"recibo-{access.bill.uuid}.pdf"
    _analytics(
        response,
        "rentivo_recibo_downloaded",
        bill_uuid_hash=analytics_hash(access.bill.uuid) or "",
    )
    return ReciboDownloadResponse(download_url=download_url, filename=filename)


@router.get(
    "/{bill_uuid}/recibo/content",
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}},
)
async def download_recibo_content(
    billing_uuid: str,
    bill_uuid: str,
    principal: Principal = Depends(_files_read),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    if access.bill.status != BillStatus.PAID.value:
        raise _conflict("recibo_unavailable", "O recibo só fica disponível quando a fatura está paga.")
    if not access.bill.recibo_pdf_path:
        raise _conflict("recibo_not_ready", "O recibo ainda está sendo gerado.")
    ref = services.bill.get_recibo_ref(access.bill)
    _audit_recibo_download(access, services)
    return _file_response(
        ref,
        content_type="application/pdf",
        filename=f"recibo-{access.bill.uuid}.pdf",
    )


@router.get(
    "/{bill_uuid}/receipts",
    response_model=ReceiptListResponse,
    responses={403: {"model": Problem}, 404: {"model": Problem}},
)
async def list_receipts(
    billing_uuid: str,
    bill_uuid: str,
    principal: Principal = Depends(_files_read),
    services: RequestServices = Depends(get_services),
) -> ReceiptListResponse:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    receipts = services.bill.list_receipts(access.bill.id)
    return ReceiptListResponse(items=tuple(_receipt_response(receipt) for receipt in receipts))


@router.post(
    "/{bill_uuid}/receipts",
    response_model=ReceiptUploadResponse,
    status_code=201,
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}},
)
async def upload_receipts(
    billing_uuid: str,
    bill_uuid: str,
    response: Response,
    receipt_files: Annotated[list[BrowserUploadFile], File()],
    principal: Principal = Depends(_files_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ReceiptUploadResponse:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    require_role(access.role, _MANAGE_ROLES)
    _require_pix(access.billing, services)
    uploaded = await _upload_receipts(receipt_files, access, services, regenerate=True)
    if uploaded.attached:
        _analytics(
            response,
            "rentivo_receipt_uploaded",
            bill_uuid_hash=analytics_hash(access.bill.uuid) or "",
            count=uploaded.attached,
            total_bytes=uploaded.total_bytes,
        )
    return uploaded


@router.get(
    "/{bill_uuid}/receipts/{receipt_uuid}",
    responses={403: {"model": Problem}, 404: {"model": Problem}},
)
async def download_receipt(
    billing_uuid: str,
    bill_uuid: str,
    receipt_uuid: str,
    principal: Principal = Depends(_files_read),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    receipt = _receipt_for_bill(access, services, receipt_uuid)
    if not receipt.storage_key:
        raise ProblemException.not_found()
    return _file_response(
        services.bill.get_receipt_ref(receipt),
        content_type=receipt.content_type,
        filename=receipt.filename,
    )


@router.delete(
    "/{bill_uuid}/receipts/{receipt_uuid}",
    status_code=204,
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}},
)
async def delete_receipt(
    billing_uuid: str,
    bill_uuid: str,
    receipt_uuid: str,
    principal: Principal = Depends(_files_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    require_role(access.role, _MANAGE_ROLES)
    receipt = _receipt_for_bill(access, services, receipt_uuid)
    previous_state = serialize_receipt(receipt, bill_uuid=access.bill.uuid, billing_uuid=access.billing.uuid)
    try:
        services.bill.delete_receipt(receipt, access.bill, access.billing, actor=principal.actor)
    except StaleReceiptDeleteError:
        raise _conflict(
            "stale_receipt_delete",
            "O comprovante foi alterado por outra operação. Atualize a página e tente novamente.",
        ) from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.RECEIPT_DELETE,
        entity_type="receipt",
        entity_id=receipt.id,
        entity_uuid=receipt.uuid,
        previous_state=previous_state,
    )
    response = Response(status_code=204)
    _analytics(response, "rentivo_receipt_deleted", bill_uuid_hash=analytics_hash(access.bill.uuid) or "")
    return response


@router.put(
    "/{bill_uuid}/receipt-order",
    response_model=ReceiptListResponse,
    responses={403: {"model": Problem}, 404: {"model": Problem}, 409: {"model": Problem}},
)
async def reorder_receipts(
    payload: ReceiptOrderRequest,
    billing_uuid: str,
    bill_uuid: str,
    principal: Principal = Depends(_files_write),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ReceiptListResponse:
    access = resolve_bill_access(principal, services, billing_uuid, bill_uuid)
    require_role(access.role, _MANAGE_ROLES)
    order = list(payload.order)
    try:
        services.bill.reorder_receipts(access.bill, access.billing, order, actor=principal.actor)
    except ValueError as exc:
        raise _conflict("invalid_receipt_order", str(exc)) from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.RECEIPT_REORDER,
        entity_type="bill",
        entity_id=access.bill.id,
        entity_uuid=access.bill.uuid,
        new_state={"order": order},
    )
    receipts = services.bill.list_receipts(access.bill.id)
    return ReceiptListResponse(items=tuple(_receipt_response(receipt) for receipt in receipts))
