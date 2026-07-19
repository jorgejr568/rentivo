from __future__ import annotations

from datetime import timedelta

import pytest

from rentivo.constants.api_scopes import APIScope
from rentivo.models.api_key import APIKeyGrant
from tests.api.routes.test_organizations import (
    INTEGRATION_KEY,
    INTEGRATION_SECRET,
    LOGIN_KEY,
    LOGIN_SECRET,
    ORGANIZATION,
    TARGET_USER,
    USER,
    OrganizationHarness,
    build_organization_harness,
    integration_headers,
    login_headers,
)


@pytest.fixture()
def organization_harness(monkeypatch: pytest.MonkeyPatch) -> OrganizationHarness:
    return build_organization_harness(monkeypatch)


def test_pending_invite_list_uses_personal_grant_without_internal_ids(
    organization_harness: OrganizationHarness,
) -> None:
    organization_harness.invite.invites[0].invited_user_id = USER.id

    response = organization_harness.client.get("/api/v1/invites", headers=login_headers(csrf=False))

    assert response.status_code == 200
    assert response.json()["items"][0] == {
        "uuid": "01JINVITE0000000000000000",
        "organization_uuid": ORGANIZATION.uuid,
        "organization_name": ORGANIZATION.name,
        "invited_by_email": USER.email,
        "role": "viewer",
        "enforce_mfa": False,
        "created_at": organization_harness.invite.invites[0].created_at.isoformat().replace("+00:00", "Z"),
    }
    assert "invited_user_id" not in response.text
    assert "organization_id" not in response.text


def test_pending_invite_list_rejects_integration_without_personal_grant(
    organization_harness: OrganizationHarness,
) -> None:
    response = organization_harness.client.get("/api/v1/invites", headers=integration_headers())

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_pending_invite_list_allows_explicit_personal_grant(organization_harness: OrganizationHarness) -> None:
    organization_harness.invite.invites[0].invited_user_id = USER.id
    personal_key = INTEGRATION_KEY.model_copy(
        update={
            "scopes": frozenset({APIScope.ORGANIZATIONS_READ.value}),
            "grants": (APIKeyGrant(resource_type="user", resource_id=USER.id),),
        }
    )
    organization_harness.services.api_key.credentials[INTEGRATION_SECRET] = personal_key

    response = organization_harness.client.get("/api/v1/invites", headers=integration_headers())

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "uuid": "01JINVITE0000000000000000",
                "organization_uuid": ORGANIZATION.uuid,
                "organization_name": ORGANIZATION.name,
                "role": "viewer",
                "enforce_mfa": False,
                "created_at": organization_harness.invite.invites[0].created_at.isoformat().replace("+00:00", "Z"),
            }
        ]
    }
    assert USER.email not in response.text
    assert TARGET_USER.email not in response.text
    assert '"user_id"' not in response.text


def test_pending_invite_list_requires_organization_read_scope(organization_harness: OrganizationHarness) -> None:
    organization_harness.services.api_key.credentials[LOGIN_SECRET] = LOGIN_KEY.model_copy(
        update={"scopes": frozenset()}
    )

    response = organization_harness.client.get("/api/v1/invites", headers=login_headers(csrf=False))

    assert response.status_code == 403
    assert response.json()["code"] == "missing_scope"


def test_pending_invite_with_missing_organization_is_non_disclosing(
    organization_harness: OrganizationHarness,
) -> None:
    organization_harness.invite.invites[0].invited_user_id = USER.id
    organization_harness.organization.organizations.pop(ORGANIZATION.uuid)

    response = organization_harness.client.get("/api/v1/invites", headers=login_headers(csrf=False))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_invite_mutations_are_login_only_and_require_csrf(organization_harness: OrganizationHarness) -> None:
    invite_uuid = organization_harness.invite.invites[0].uuid

    bearer = organization_harness.client.post(
        f"/api/v1/invites/{invite_uuid}/accept",
        headers=integration_headers(),
    )
    missing_csrf = organization_harness.client.post(
        f"/api/v1/invites/{invite_uuid}/decline",
        headers=login_headers(csrf=False),
    )

    assert bearer.status_code == 403
    assert bearer.json()["code"] == "login_token_required"
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "csrf_failed"


def test_accept_invite_audits_notifies_and_reports_mfa_bootstrap(
    organization_harness: OrganizationHarness,
) -> None:
    invite = organization_harness.invite.invites[0]
    invite.invited_user_id = USER.id
    organization_harness.mfa.requires_setup_results = [False, True]

    response = organization_harness.client.post(
        f"/api/v1/invites/{invite.uuid}/accept",
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 200
    assert response.headers["X-Rentivo-Analytics-Event"] == "rentivo_invite_accepted"
    assert response.json() == {
        "status": "accepted",
        "organization_uuid": ORGANIZATION.uuid,
        "mfa_setup_required": True,
    }
    assert invite.status == "accepted"
    assert organization_harness.audit.calls[-1][0][1] == "invite.accept"
    payload = organization_harness.job.calls[-1][2]
    assert payload["event"] == "invite_responded"
    assert payload["to_email"] == USER.email
    assert payload["ctx"]["response_label"] == "aceitou"


def test_decline_invite_audits_and_notifies_without_mfa_check(
    organization_harness: OrganizationHarness,
) -> None:
    invite = organization_harness.invite.invites[0]
    invite.invited_user_id = USER.id

    response = organization_harness.client.post(
        f"/api/v1/invites/{invite.uuid}/decline",
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 200
    assert response.headers["X-Rentivo-Analytics-Event"] == "rentivo_invite_declined"
    assert response.json() == {"status": "declined", "organization_uuid": ORGANIZATION.uuid}
    assert invite.status == "declined"
    assert organization_harness.audit.calls[-1][0][1] == "invite.decline"
    payload = organization_harness.job.calls[-1][2]
    assert payload["event"] == "invite_responded"
    assert payload["ctx"]["response_label"] == "recusou"


def test_wrong_user_invite_is_non_disclosing_and_has_no_side_effects(
    organization_harness: OrganizationHarness,
) -> None:
    invite = organization_harness.invite.invites[0]
    invite.invited_user_id = TARGET_USER.id

    response = organization_harness.client.post(
        f"/api/v1/invites/{invite.uuid}/accept",
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert organization_harness.audit.calls == []
    assert organization_harness.job.calls == []


def test_already_answered_invite_is_conflict_without_side_effects(
    organization_harness: OrganizationHarness,
) -> None:
    invite = organization_harness.invite.invites[0]
    invite.invited_user_id = USER.id
    invite.status = "accepted"
    invite.responded_at = invite.created_at + timedelta(minutes=1)

    response = organization_harness.client.post(
        f"/api/v1/invites/{invite.uuid}/decline",
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "invite_response_conflict"
    assert organization_harness.audit.calls == []
    assert organization_harness.job.calls == []


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_invite_response_maps_post_preflight_transition_race_to_conflict(
    organization_harness: OrganizationHarness,
    action: str,
) -> None:
    invite = organization_harness.invite.invites[0]
    invite.invited_user_id = USER.id
    organization_harness.invite.response_conflict = True

    response = organization_harness.client.post(
        f"/api/v1/invites/{invite.uuid}/{action}",
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "invite_response_conflict"
    assert invite.status == "pending"
    assert organization_harness.audit.calls == []
    assert organization_harness.job.calls == []


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_invite_response_resolves_organization_before_mutation(
    organization_harness: OrganizationHarness,
    action: str,
) -> None:
    invite = organization_harness.invite.invites[0]
    invite.invited_user_id = USER.id
    organization_harness.organization.organizations.pop(ORGANIZATION.uuid)

    response = organization_harness.client.post(
        f"/api/v1/invites/{invite.uuid}/{action}",
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert invite.status == "pending"
    assert organization_harness.audit.calls == []
    assert organization_harness.job.calls == []
    assert organization_harness.mfa.requires_setup_calls == [USER.id]
