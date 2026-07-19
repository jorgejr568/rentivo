from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Response

from rentivo.api.csrf import require_csrf
from rentivo.api.dependencies import get_services, require_login_scope, require_resource_grant, require_scope
from rentivo.api.domain_access import OrganizationAccess, require_role, resolve_organization_access
from rentivo.api.errors import Problem, ProblemException, problem
from rentivo.api.principal import Principal
from rentivo.api.schemas.billings import BillingStatsResponse
from rentivo.api.schemas.organizations import (
    BillingTransferRequest,
    BillingTransferResponse,
    OrganizationCapabilitiesResponse,
    OrganizationCreateRequest,
    OrganizationIntegrationDetailResponse,
    OrganizationInviteCreateRequest,
    OrganizationInviteResponse,
    OrganizationListResponse,
    OrganizationLoginDetailResponse,
    OrganizationMemberResponse,
    OrganizationMemberUpdateRequest,
    OrganizationMFAPolicyRequest,
    OrganizationMFAPolicyResponse,
    OrganizationResponse,
    OrganizationSettingsResponse,
    OrganizationUpdateRequest,
)
from rentivo.constants.api_scopes import APIScope
from rentivo.models.audit_log import AuditEventType
from rentivo.models.invite import Invite
from rentivo.models.organization import Organization, OrganizationMember, OrgRole
from rentivo.services.audit_serializers import serialize_invite, serialize_organization
from rentivo.services.billing_stats import BillingStats
from rentivo.services.container import RequestServices
from rentivo.settings import settings

router = APIRouter(prefix="/organizations", tags=["organizations"])
_read_principal = require_scope(APIScope.ORGANIZATIONS_READ)
_write_principal = require_login_scope(APIScope.ORGANIZATIONS_WRITE)
_members_principal = require_login_scope(APIScope.ORGANIZATIONS_MEMBERS)
_ADMIN_ROLES = frozenset({OrgRole.ADMIN.value})
_BILLING_ROLES = frozenset({OrgRole.ADMIN.value, OrgRole.MANAGER.value})
_ANALYTICS_HEADER = "X-Rentivo-Analytics-Event"


def _conflict(code: str, detail: str) -> ProblemException:
    return ProblemException(
        problem(
            status=409,
            code=code,
            title="Conflito",
            detail=detail,
        )
    )


def _validation_error() -> ProblemException:
    return ProblemException(
        problem(
            status=422,
            code="validation_error",
            title="Dados inválidos",
            detail="As configurações da organização são inválidas.",
        )
    )


def _capabilities(principal: Principal, role: str) -> OrganizationCapabilitiesResponse:
    scopes = principal.api_key.scopes
    return OrganizationCapabilitiesResponse(
        can_manage=(
            principal.api_key.is_login_token
            and role == OrgRole.ADMIN.value
            and APIScope.ORGANIZATIONS_WRITE.value in scopes
        ),
        can_invite=(
            principal.api_key.is_login_token
            and role == OrgRole.ADMIN.value
            and APIScope.ORGANIZATIONS_MEMBERS.value in scopes
        ),
        can_create_billing=role in _BILLING_ROLES and APIScope.BILLINGS_WRITE.value in scopes,
        can_view_billing_stats=APIScope.BILLINGS_READ.value in scopes,
    )


def _organization_response(
    organization: Organization,
    member: OrganizationMember,
    principal: Principal,
) -> OrganizationResponse:
    return OrganizationResponse(
        uuid=organization.uuid,
        name=organization.name,
        enforce_mfa=organization.enforce_mfa,
        current_role=member.role,
        capabilities=_capabilities(principal, member.role),
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


def _member_response(member: OrganizationMember, current_user_id: int) -> OrganizationMemberResponse:
    return OrganizationMemberResponse(
        user_id=member.user_id,
        email=member.email,
        role=member.role,
        is_current_user=member.user_id == current_user_id,
        created_at=member.created_at,
    )


def _invite_response(invite: Invite) -> OrganizationInviteResponse:
    return OrganizationInviteResponse(
        uuid=invite.uuid,
        invited_email=invite.invited_email,
        role=invite.role,
        status=invite.status,
        created_at=invite.created_at,
        responded_at=invite.responded_at,
    )


def _stats_response(stats: BillingStats) -> BillingStatsResponse:
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


def _organization_stats(
    access: OrganizationAccess,
    services: RequestServices,
    capabilities: OrganizationCapabilitiesResponse,
) -> BillingStatsResponse | None:
    if not capabilities.can_view_billing_stats:
        return None
    billing_ids = [
        billing.id
        for billing in services.billing.list_billings_for_user(access.principal.user.id)
        if billing.id is not None
        and billing.owner_type == "organization"
        and billing.owner_id == access.organization.id
    ]
    return _stats_response(services.billing_stats.stats_for_ids(billing_ids))


def _detail_response(
    access: OrganizationAccess,
    services: RequestServices,
) -> OrganizationLoginDetailResponse | OrganizationIntegrationDetailResponse:
    organization = access.organization
    summary = _organization_response(organization, access.member, access.principal)
    capabilities = summary.capabilities
    stats = _organization_stats(access, services, capabilities)
    if not access.principal.api_key.is_login_token:
        return OrganizationIntegrationDetailResponse(**summary.model_dump(), stats=stats)
    settings_response = None
    if capabilities.can_manage:
        settings_response = OrganizationSettingsResponse(
            pix_key=organization.pix_key,
            pix_merchant_name=organization.pix_merchant_name,
            pix_merchant_city=organization.pix_merchant_city,
        )
    invites = services.invite.list_org_invites(organization.id) if capabilities.can_invite else []
    return OrganizationLoginDetailResponse(
        **summary.model_dump(),
        stats=stats,
        settings=settings_response,
        members=tuple(
            _member_response(member, access.principal.user.id)
            for member in services.organization.list_members(organization.id)
        ),
        invites=tuple(_invite_response(invite) for invite in invites),
    )


def _admin_access(
    principal: Principal,
    services: RequestServices,
    organization_uuid: str,
) -> OrganizationAccess:
    access = resolve_organization_access(principal, services, organization_uuid)
    require_role(access.role, _ADMIN_ROLES)
    return access


@router.get("", response_model=OrganizationListResponse)
async def list_organizations(
    principal: Principal = Depends(_read_principal),
    services: RequestServices = Depends(get_services),
) -> OrganizationListResponse:
    items: list[OrganizationResponse] = []
    for organization in services.organization.list_user_organizations(principal.user.id):
        member = services.organization.get_member(organization.id, principal.user.id)
        if member is None or not services.api_key.can_access_resource(
            principal.api_key,
            "organization",
            organization.id,
        ):
            continue
        items.append(_organization_response(organization, member, principal))
    return OrganizationListResponse(items=tuple(items))


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=201,
    responses={422: {"model": Problem}},
)
async def create_organization(
    payload: OrganizationCreateRequest,
    response: Response,
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> OrganizationResponse:
    organization = services.organization.create_organization(payload.name, principal.user.id)
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.ORGANIZATION_CREATE,
        entity_type="organization",
        entity_id=organization.id,
        entity_uuid=organization.uuid,
        new_state=serialize_organization(organization),
    )
    member = services.organization.get_member(organization.id, principal.user.id)
    response.headers[_ANALYTICS_HEADER] = "rentivo_organization_created"
    return _organization_response(organization, member, principal)


@router.get(
    "/{organization_uuid}",
    response_model=OrganizationLoginDetailResponse | OrganizationIntegrationDetailResponse,
    responses={404: {"model": Problem}},
)
async def get_organization(
    organization_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_read_principal),
    services: RequestServices = Depends(get_services),
) -> OrganizationLoginDetailResponse | OrganizationIntegrationDetailResponse:
    access = resolve_organization_access(principal, services, organization_uuid)
    return _detail_response(access, services)


@router.patch(
    "/{organization_uuid}",
    response_model=OrganizationLoginDetailResponse,
    responses={404: {"model": Problem}, 422: {"model": Problem}},
)
async def update_organization(
    payload: OrganizationUpdateRequest,
    organization_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> OrganizationLoginDetailResponse:
    access = _admin_access(principal, services, organization_uuid)
    organization = access.organization
    previous_state = serialize_organization(organization)
    for field_name in payload.model_fields_set:
        setattr(organization, field_name, getattr(payload, field_name))
    try:
        updated = services.organization.update_organization(organization)
    except ValueError:
        raise _validation_error() from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.ORGANIZATION_UPDATE,
        entity_type="organization",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state=previous_state,
        new_state=serialize_organization(updated),
    )
    return _detail_response(
        OrganizationAccess(organization=updated, member=access.member, principal=principal),
        services,
    )


@router.delete(
    "/{organization_uuid}",
    status_code=204,
    responses={404: {"model": Problem}},
)
async def delete_organization(
    organization_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = _admin_access(principal, services, organization_uuid)
    previous_state = serialize_organization(access.organization)
    services.organization.delete_organization(access.organization.id)
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.ORGANIZATION_DELETE,
        entity_type="organization",
        entity_id=access.organization.id,
        entity_uuid=access.organization.uuid,
        previous_state=previous_state,
    )
    return Response(status_code=204)


@router.patch(
    "/{organization_uuid}/members/{user_id}",
    response_model=OrganizationMemberResponse,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
)
async def update_member_role(
    payload: OrganizationMemberUpdateRequest,
    organization_uuid: str = Path(min_length=1),
    user_id: int = Path(gt=0),
    principal: Principal = Depends(_members_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> OrganizationMemberResponse:
    access = _admin_access(principal, services, organization_uuid)
    member = services.organization.get_member(access.organization.id, user_id)
    if member is None:
        raise _conflict("membership_conflict", "A associação do membro foi alterada ou removida.")
    old_role = member.role
    services.organization.update_member_role(access.organization.id, user_id, payload.role)
    updated_member = member.model_copy(update={"role": payload.role})
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.ORGANIZATION_UPDATE_MEMBER_ROLE,
        entity_type="organization",
        entity_id=access.organization.id,
        entity_uuid=access.organization.uuid,
        previous_state={"role": old_role},
        new_state={"role": payload.role},
    )
    member_user = services.user.get_by_id(user_id)
    if member_user is not None:
        services.job.enqueue_for(
            principal.actor,
            "email.send",
            {
                "event": "member_changed",
                "to_email": member_user.email,
                "ctx": {
                    "change_message": (
                        f"Sua função mudou de {OrgRole.label(old_role)} para {OrgRole.label(payload.role)}."
                    ),
                    "org_name": access.organization.name,
                    "actor_email": principal.user.email,
                },
            },
        )
    return _member_response(updated_member, principal.user.id)


@router.delete(
    "/{organization_uuid}/members/{user_id}",
    status_code=204,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
)
async def remove_member(
    organization_uuid: str = Path(min_length=1),
    user_id: int = Path(gt=0),
    principal: Principal = Depends(_members_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    access = _admin_access(principal, services, organization_uuid)
    if user_id == principal.user.id:
        raise _conflict("membership_conflict", "Você não pode remover a si mesmo.")
    member = services.organization.get_member(access.organization.id, user_id)
    if member is None:
        raise _conflict("membership_conflict", "A associação do membro foi alterada ou removida.")
    removed = services.organization.remove_member(
        access.organization.id,
        user_id,
        expected_role=member.role,
    )
    if not removed:
        raise _conflict("membership_conflict", "A associação do membro foi alterada ou removida.")
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.ORGANIZATION_REMOVE_MEMBER,
        entity_type="organization",
        entity_id=access.organization.id,
        entity_uuid=access.organization.uuid,
        previous_state={
            "org_id": access.organization.id,
            "user_id": user_id,
            "role": member.role,
        },
    )
    return Response(status_code=204)


@router.post(
    "/{organization_uuid}/invites",
    response_model=OrganizationInviteResponse,
    status_code=201,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
)
async def create_invite(
    payload: OrganizationInviteCreateRequest,
    response: Response,
    organization_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_members_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> OrganizationInviteResponse:
    access = _admin_access(principal, services, organization_uuid)
    try:
        invite = services.invite.send_invite(
            access.organization.id,
            payload.email,
            payload.role,
            principal.user.id,
        )
    except ValueError:
        raise _conflict("invite_conflict", "Não foi possível criar este convite.") from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.INVITE_SEND,
        entity_type="invite",
        entity_id=invite.id,
        entity_uuid=invite.uuid,
        new_state=serialize_invite(invite),
    )
    services.job.enqueue_for(
        principal.actor,
        "email.send",
        {
            "event": "invite_received",
            "to_email": payload.email,
            "ctx": {
                "inviter_email": principal.user.email,
                "org_name": access.organization.name,
                "role_label": OrgRole.label(payload.role),
                "invites_url": f"{settings.public_app_url.rstrip('/')}/invites/",
            },
        },
    )
    response.headers[_ANALYTICS_HEADER] = "rentivo_invite_sent"
    return _invite_response(invite)


@router.put(
    "/{organization_uuid}/mfa-policy",
    response_model=OrganizationMFAPolicyResponse,
    responses={404: {"model": Problem}},
)
async def update_mfa_policy(
    payload: OrganizationMFAPolicyRequest,
    organization_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> OrganizationMFAPolicyResponse:
    access = _admin_access(principal, services, organization_uuid)
    previous_value = access.organization.enforce_mfa
    updated = services.organization.set_enforce_mfa(access.organization.id, payload.enforce_mfa)
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.ORGANIZATION_UPDATE_MFA,
        entity_type="organization",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state={"enforce_mfa": previous_value},
        new_state={"enforce_mfa": updated.enforce_mfa},
    )
    mfa_setup_required = payload.enforce_mfa and not services.mfa.has_any_mfa(principal.user.id)
    return OrganizationMFAPolicyResponse(
        enforce_mfa=updated.enforce_mfa,
        mfa_setup_required=mfa_setup_required,
    )


@router.post(
    "/{organization_uuid}/billing-transfers",
    response_model=BillingTransferResponse,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
)
async def transfer_billing(
    payload: BillingTransferRequest,
    organization_uuid: str = Path(min_length=1),
    principal: Principal = Depends(_write_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> BillingTransferResponse:
    access = _admin_access(principal, services, organization_uuid)
    billing = services.billing.get_billing_by_uuid(payload.billing_uuid)
    if billing is None or billing.id is None:
        raise ProblemException.not_found()
    require_resource_grant(principal, services, billing.owner_type, billing.owner_id)
    if not services.authorization.can_transfer_billing(principal.user.id, billing):
        raise ProblemException.not_found()
    previous_owner = {"owner_type": billing.owner_type, "owner_id": billing.owner_id}
    try:
        services.billing.transfer_to_organization(
            billing.id,
            access.organization.id,
            expected_owner_id=principal.user.id,
        )
    except ValueError:
        raise _conflict(
            "billing_transfer_conflict",
            "A cobrança não pode mais ser transferida para esta organização.",
        ) from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.BILLING_TRANSFER,
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_owner,
        new_state={"owner_type": "organization", "owner_id": access.organization.id},
    )
    services.billing_notification.notify_transferred(
        billing=billing,
        previous_owner=previous_owner,
        new_org_id=access.organization.id,
        actor_user_id=principal.user.id,
        actor_email=principal.user.email,
    )
    return BillingTransferResponse(
        billing_uuid=billing.uuid,
        organization_uuid=access.organization.uuid,
    )
