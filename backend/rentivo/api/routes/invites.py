from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from rentivo.api.csrf import require_csrf
from rentivo.api.dependencies import get_services, require_login_scope, require_resource_grant, require_scope
from rentivo.api.errors import Problem, ProblemException, problem
from rentivo.api.principal import Principal
from rentivo.api.schemas.organizations import (
    InviteAcceptResponse,
    InviteDeclineResponse,
    PendingInviteListResponse,
    PendingInviteResponse,
)
from rentivo.constants.api_scopes import APIScope
from rentivo.models.audit_log import AuditEventType
from rentivo.models.invite import Invite
from rentivo.services.container import RequestServices

router = APIRouter(prefix="/invites", tags=["invites"])
_read_principal = require_scope(APIScope.ORGANIZATIONS_READ)
_members_principal = require_login_scope(APIScope.ORGANIZATIONS_MEMBERS)


def _response_conflict() -> ProblemException:
    return ProblemException(
        problem(
            status=409,
            code="invite_response_conflict",
            title="Conflito",
            detail="Este convite não está mais pendente.",
        )
    )


def _organization_uuid(invite: Invite, services: RequestServices) -> str:
    organization = services.organization.get_by_id(invite.organization_id)
    if organization is None:
        raise ProblemException.not_found()
    return organization.uuid


def _pending_invite_response(invite: Invite, services: RequestServices) -> PendingInviteResponse:
    return PendingInviteResponse(
        uuid=invite.uuid,
        organization_uuid=_organization_uuid(invite, services),
        organization_name=invite.organization_name,
        invited_by_email=invite.invited_by_email,
        role=invite.role,
        enforce_mfa=invite.enforce_mfa,
        created_at=invite.created_at,
    )


def _responded_invite(
    services: RequestServices,
    invite_uuid: str,
    user_id: int,
    *,
    action: str,
) -> Invite:
    try:
        if action == "accept":
            return services.invite.accept_invite(invite_uuid, user_id)
        return services.invite.decline_invite(invite_uuid, user_id)
    except ValueError as exc:
        if str(exc) == "Invite is no longer pending":
            raise _response_conflict() from None
        raise ProblemException.not_found() from None


def _notify_response(
    invite: Invite,
    principal: Principal,
    services: RequestServices,
    *,
    response_label: str,
) -> None:
    services.job.enqueue_for(
        principal.actor,
        "email.send",
        {
            "event": "invite_responded",
            "to_email": invite.invited_by_email,
            "ctx": {
                "invitee_email": invite.invited_email,
                "org_name": invite.organization_name,
                "response_label": response_label,
            },
        },
    )


@router.get("", response_model=PendingInviteListResponse)
async def list_pending_invites(
    principal: Principal = Depends(_read_principal),
    services: RequestServices = Depends(get_services),
) -> PendingInviteListResponse:
    require_resource_grant(principal, services, "user", principal.user.id)
    return PendingInviteListResponse(
        items=tuple(
            _pending_invite_response(invite, services) for invite in services.invite.list_pending(principal.user.id)
        )
    )


@router.post(
    "/{invite_uuid}/accept",
    response_model=InviteAcceptResponse,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
)
async def accept_invite(
    invite_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_members_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> InviteAcceptResponse:
    require_resource_grant(principal, services, "user", principal.user.id)
    invite = _responded_invite(services, invite_uuid, principal.user.id, action="accept")
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.INVITE_ACCEPT,
        entity_type="invite",
        entity_id=invite.id,
        entity_uuid=invite.uuid,
        previous_state={"status": "pending"},
        new_state={"status": "accepted"},
    )
    _notify_response(invite, principal, services, response_label="aceitou")
    return InviteAcceptResponse(
        organization_uuid=_organization_uuid(invite, services),
        mfa_setup_required=services.mfa.user_requires_mfa_setup(principal.user.id),
    )


@router.post(
    "/{invite_uuid}/decline",
    response_model=InviteDeclineResponse,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
)
async def decline_invite(
    invite_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_members_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> InviteDeclineResponse:
    require_resource_grant(principal, services, "user", principal.user.id)
    invite = _responded_invite(services, invite_uuid, principal.user.id, action="decline")
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.INVITE_DECLINE,
        entity_type="invite",
        entity_id=invite.id,
        entity_uuid=invite.uuid,
        previous_state={"status": "pending"},
        new_state={"status": "declined"},
    )
    _notify_response(invite, principal, services, response_label="recusou")
    return InviteDeclineResponse(organization_uuid=_organization_uuid(invite, services))
