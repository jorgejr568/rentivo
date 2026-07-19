from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from rentivo.api.errors import ProblemException, problem

router = APIRouter()


@router.get("/change-password")
async def change_password_alias() -> RedirectResponse:
    return RedirectResponse("/security", status_code=308)


@router.get("/security/pix")
async def pix_alias() -> RedirectResponse:
    return RedirectResponse("/security", status_code=308)


@router.get("/auth/google/login")
async def google_login_alias() -> RedirectResponse:
    return RedirectResponse("/api/v1/auth/google/start", status_code=308)


@router.get("/billings/{billing_uuid}/bills/{bill_uuid}/invoice")
async def invoice_alias(billing_uuid: str, bill_uuid: str) -> RedirectResponse:
    return RedirectResponse(
        f"/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/invoice",
        status_code=307,
    )


@router.get("/billings/{billing_uuid}/bills/{bill_uuid}/recibo")
async def recibo_alias(billing_uuid: str, bill_uuid: str) -> RedirectResponse:
    return RedirectResponse(
        f"/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/recibo",
        status_code=307,
    )


@router.get("/billings/{billing_uuid}/bills/{bill_uuid}/receipts/{receipt_uuid}")
async def receipt_alias(billing_uuid: str, bill_uuid: str, receipt_uuid: str) -> RedirectResponse:
    return RedirectResponse(
        f"/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipts/{receipt_uuid}",
        status_code=307,
    )


@router.get("/billings/{billing_uuid}/attachments/{attachment_uuid}")
async def attachment_alias(billing_uuid: str, attachment_uuid: str) -> RedirectResponse:
    return RedirectResponse(
        f"/api/v1/billings/{billing_uuid}/attachments/{attachment_uuid}",
        status_code=307,
    )


_STALE_POST_PATHS = (
    "/signup",
    "/login",
    "/mfa-verify",
    "/logout",
    "/forgot-password",
    "/reset-password",
    "/change-password",
    "/security/pix",
    "/security/change-password",
    "/security/totp/confirm",
    "/security/totp/disable",
    "/security/recovery-codes/regenerate",
    "/security/passkeys/register/begin",
    "/security/passkeys/register/complete",
    "/security/passkeys/auth/begin",
    "/security/passkeys/auth/complete",
    "/security/passkeys/{passkey_uuid}/delete",
    "/billings/create",
    "/billings/{billing_uuid}/edit",
    "/billings/{billing_uuid}/transfer",
    "/billings/{billing_uuid}/delete",
    "/billings/{billing_uuid}/attachments/upload",
    "/billings/{billing_uuid}/attachments/{attachment_uuid}/delete",
    "/billings/{billing_uuid}/expenses/add",
    "/billings/{billing_uuid}/expenses/{expense_uuid}/delete",
    "/billings/{billing_uuid}/bills/generate",
    "/billings/{billing_uuid}/bills/export",
    "/billings/{billing_uuid}/bills/{bill_uuid}/edit",
    "/billings/{billing_uuid}/bills/{bill_uuid}/regenerate-pdf",
    "/billings/{billing_uuid}/bills/{bill_uuid}/change-status",
    "/billings/{billing_uuid}/bills/{bill_uuid}/delete",
    "/billings/{billing_uuid}/bills/{bill_uuid}/receipts/upload",
    "/billings/{billing_uuid}/bills/{bill_uuid}/receipts/{receipt_uuid}/delete",
    "/billings/{billing_uuid}/bills/{bill_uuid}/receipts/reorder",
    "/billings/{billing_uuid}/bills/{bill_uuid}/communications/preview",
    "/billings/{billing_uuid}/bills/{bill_uuid}/communications/send",
    "/organizations/create",
    "/organizations/{organization_uuid}/edit",
    "/organizations/{organization_uuid}/delete",
    "/organizations/{organization_uuid}/members/{member_user_id}/role",
    "/organizations/{organization_uuid}/members/{member_user_id}/remove",
    "/organizations/{organization_uuid}/invite",
    "/organizations/{organization_uuid}/toggle-mfa",
    "/organizations/{organization_uuid}/transfer-billing",
    "/invites/{invite_uuid}/accept",
    "/invites/{invite_uuid}/decline",
    "/themes/user",
    "/themes/user/delete",
    "/themes/organization/{organization_uuid}",
    "/themes/organization/{organization_uuid}/delete",
    "/themes/billing/{billing_uuid}",
    "/themes/billing/{billing_uuid}/delete",
)


async def stale_legacy_post() -> None:
    raise ProblemException(
        problem(
            status=410,
            code="legacy_route_gone",
            title="Rota removida",
            detail="Este formulário não está mais disponível. Atualize a página e tente novamente.",
        )
    )


for stale_path in _STALE_POST_PATHS:
    router.add_api_route(stale_path, stale_legacy_post, methods=["POST"], include_in_schema=False)
