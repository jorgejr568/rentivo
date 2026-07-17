"""Unit tests for web/login_flow.py, exercised directly with a stub request.

Route-level integration coverage lives in tests/web/test_auth.py,
tests/web/routes/test_security.py and tests/web/routes/test_google_auth.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from legacy_web.login_flow import begin_mfa_challenge, complete_login
from rentivo.models.audit_log import AuditEventType
from rentivo.models.user import User


def _make_request(*, requires_mfa_setup: bool = False, user_agent: str = "UA-test"):
    services = SimpleNamespace(
        audit=MagicMock(),
        mfa=MagicMock(),
        known_device=MagicMock(),
        job=MagicMock(),
    )
    services.mfa.user_requires_mfa_setup.return_value = requires_mfa_setup
    return SimpleNamespace(
        # Pre-populated stale keys prove session.clear() runs first.
        session={"stale": "value", "google_oauth_state": "tok"},
        state=SimpleNamespace(services=services),
        headers={"user-agent": user_agent},
    )


def _user() -> User:
    return User(id=7, email="user@example.com")


class TestCompleteLogin:
    def test_clears_session_then_sets_auth_keys(self):
        request = _make_request()
        response = complete_login(request, _user(), via="password", client_ip="1.2.3.4")
        assert request.session == {"user_id": 7, "email": "user@example.com"}
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/"

    def test_sets_mfa_setup_required_when_org_enforces(self):
        request = _make_request(requires_mfa_setup=True)
        complete_login(request, _user(), via="password")
        assert request.session["mfa_setup_required"] is True

    def test_no_mfa_setup_flag_when_not_required(self):
        request = _make_request(requires_mfa_setup=False)
        complete_login(request, _user(), via="password")
        assert "mfa_setup_required" not in request.session

    def test_audits_user_login_with_ip_only_by_default(self):
        request = _make_request()
        complete_login(request, _user(), via="password", client_ip="1.2.3.4")
        args, kwargs = request.state.services.audit.safe_log_for.call_args
        actor = args[0]
        assert (actor.user_id, actor.email, actor.source) == (7, "user@example.com", "web")
        assert args[1] == AuditEventType.USER_LOGIN
        assert kwargs["entity_type"] == "user"
        assert kwargs["entity_id"] == 7
        assert kwargs["new_state"] == {"user_id": 7, "email": "user@example.com"}
        assert kwargs["metadata"] == {"ip": "1.2.3.4"}

    def test_metadata_kwarg_merges_after_ip(self):
        request = _make_request()
        complete_login(
            request, _user(), via="passkey", client_ip="1.2.3.4", metadata={"mfa": True, "method": "passkey"}
        )
        kwargs = request.state.services.audit.safe_log_for.call_args.kwargs
        assert kwargs["metadata"] == {"ip": "1.2.3.4", "mfa": True, "method": "passkey"}

    def test_default_client_ip_is_unknown(self):
        request = _make_request()
        complete_login(request, _user(), via="password")
        kwargs = request.state.services.audit.safe_log_for.call_args.kwargs
        assert kwargs["metadata"] == {"ip": "unknown"}

    def test_queues_login_success_event_after_session_clear(self, monkeypatch):
        # push_event no-ops without a GTM container id; enable it so the queue
        # is observable, and assert it landed in the POST-clear session.
        monkeypatch.setattr("rentivo.settings.settings.gtm_container_id", "GTM-TEST")
        request = _make_request()
        complete_login(request, _user(), via="mfa")
        from legacy_web.analytics import SESSION_KEY

        assert request.session[SESSION_KEY] == [{"event": "rentivo_login_success", "via": "mfa"}]

    def test_notifies_known_device_service(self):
        request = _make_request(user_agent="Firefox/1.0")
        user = _user()
        complete_login(request, user, via="google", client_ip="9.8.7.6")
        request.state.services.known_device.notify_if_new.assert_called_once_with(
            user=user,
            user_agent="Firefox/1.0",
            client_ip="9.8.7.6",
            job_service=request.state.services.job,
        )

    def test_missing_user_agent_header_defaults_to_empty_string(self):
        request = _make_request()
        request.headers = {}
        complete_login(request, _user(), via="password")
        kwargs = request.state.services.known_device.notify_if_new.call_args.kwargs
        assert kwargs["user_agent"] == ""


class TestBeginMfaChallenge:
    def test_clears_session_then_sets_pending_keys(self):
        request = _make_request()
        response = begin_mfa_challenge(request, _user(), client_ip="1.2.3.4")
        assert request.session == {"mfa_pending_user_id": 7, "mfa_pending_email": "user@example.com"}
        assert response.status_code == 302
        assert response.headers["location"] == "/mfa-verify"

    def test_audits_challenge_issued_with_ip_only_by_default(self):
        request = _make_request()
        begin_mfa_challenge(request, _user(), client_ip="1.2.3.4")
        args, kwargs = request.state.services.audit.safe_log_for.call_args
        actor = args[0]
        assert (actor.user_id, actor.email, actor.source) == (7, "user@example.com", "web")
        assert args[1] == AuditEventType.MFA_CHALLENGE_ISSUED
        assert kwargs["entity_type"] == "user"
        assert kwargs["entity_id"] == 7
        assert kwargs["metadata"] == {"ip": "1.2.3.4"}
        assert "new_state" not in kwargs

    def test_metadata_kwarg_merges_after_ip(self):
        request = _make_request()
        begin_mfa_challenge(request, _user(), client_ip="1.2.3.4", metadata={"method": "google"})
        kwargs = request.state.services.audit.safe_log_for.call_args.kwargs
        assert kwargs["metadata"] == {"ip": "1.2.3.4", "method": "google"}

    def test_default_client_ip_is_unknown(self):
        request = _make_request()
        begin_mfa_challenge(request, _user())
        kwargs = request.state.services.audit.safe_log_for.call_args.kwargs
        assert kwargs["metadata"] == {"ip": "unknown"}

    def test_does_not_complete_login_side_effects(self):
        request = _make_request()
        begin_mfa_challenge(request, _user())
        request.state.services.known_device.notify_if_new.assert_not_called()
        request.state.services.mfa.user_requires_mfa_setup.assert_not_called()
