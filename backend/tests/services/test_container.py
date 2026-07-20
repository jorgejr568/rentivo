def test_api_key_service_is_lazily_cached(db_connection, fake_encryption):
    from rentivo.services.api_key_service import APIKeyService
    from rentivo.services.container import RequestServices

    services = RequestServices(conn=db_connection, encryption=fake_encryption)

    assert isinstance(services.api_key, APIKeyService)
    assert services.api_key is services.api_key


def test_api_key_service_uses_the_configured_login_lifetime(
    db_connection,
    fake_encryption,
    monkeypatch,
):
    from datetime import timedelta

    from rentivo.services.container import RequestServices
    from rentivo.settings import settings

    monkeypatch.setattr(settings, "api_key_login_ttl_seconds", 6 * 60 * 60)
    services = RequestServices(conn=db_connection, encryption=fake_encryption)

    assert services.api_key.login_ttl == timedelta(hours=6)


def test_api_key_service_uses_the_configured_integration_lifetimes_and_throttle(
    db_connection,
    fake_encryption,
    monkeypatch,
):
    from datetime import timedelta

    from rentivo.services.container import RequestServices
    from rentivo.settings import settings

    monkeypatch.setattr(settings, "api_key_integration_default_ttl_days", 30)
    monkeypatch.setattr(settings, "api_key_integration_max_ttl_days", 180)
    monkeypatch.setattr(settings, "api_key_last_used_throttle_seconds", 15 * 60)
    services = RequestServices(conn=db_connection, encryption=fake_encryption)

    assert services.api_key.integration_default_ttl == timedelta(days=30)
    assert services.api_key.integration_max_ttl == timedelta(days=180)
    assert services.api_key.last_used_interval == timedelta(minutes=15)


def test_auth_challenge_service_is_lazily_cached(db_connection, fake_encryption):
    from rentivo.services.auth_challenge_service import AuthChallengeService
    from rentivo.services.container import RequestServices

    services = RequestServices(conn=db_connection, encryption=fake_encryption)

    assert isinstance(services.auth_challenge, AuthChallengeService)
    assert services.auth_challenge is services.auth_challenge


def test_auth_rate_limit_service_is_lazily_cached(db_connection, fake_encryption):
    from rentivo.services.container import RequestServices
    from rentivo.services.rate_limit_service import RateLimitService

    services = RequestServices(conn=db_connection, encryption=fake_encryption)

    assert isinstance(services.auth_rate_limit, RateLimitService)
    assert services.auth_rate_limit is services.auth_rate_limit


def test_login_service_builds_the_api_bootstrap(db_connection, fake_encryption):
    from datetime import UTC, datetime

    from rentivo.models.api_key import APIKey
    from rentivo.models.user import User
    from rentivo.services.container import RequestServices

    services = RequestServices(conn=db_connection, encryption=fake_encryption)
    login = services.login
    bootstrap = login.bootstrap_builder(
        user=User(id=41, email="bootstrap@example.com"),
        api_key=APIKey(
            user_id=41,
            name="Web login",
            secret_hash=b"hash",
            key_start="aBcD",
            key_end="yZ",
            is_login_token=True,
            scopes=frozenset({"profile:read", "security:write"}),
            expires_at=datetime.now(UTC),
        ),
        mfa_setup_required=True,
    )

    assert bootstrap == {
        "user": {"id": 41, "email": "bootstrap@example.com"},
        "capabilities": {
            "scopes": ["profile:read", "security:write"],
            "mfa_setup_required": True,
        },
        "pending_invite_count": 0,
        "feature_flags": {
            "google_auth": services.google_auth.is_enabled,
            "turnstile": services.turnstile.is_enabled,
            "turnstile_site_key": services.turnstile.site_key if services.turnstile.is_enabled else "",
        },
        "analytics": {"gtm_container_id": ""},
    }


def test_mfa_and_pix_services_resolve_with_their_own_repositories(db_connection, fake_encryption):
    from rentivo.services.container import RequestServices
    from rentivo.services.mfa_service import MFAService
    from rentivo.services.pix_service import PixService

    services = RequestServices(conn=db_connection, encryption=fake_encryption)

    assert isinstance(services.mfa, MFAService)
    assert isinstance(services.pix, PixService)
    assert services.mfa is services.mfa
    assert services.pix is services.pix


def test_all_retained_request_services_resolve_and_are_cached(db_connection, fake_encryption):
    from rentivo.services.api_key_service import APIKeyService
    from rentivo.services.audit_service import AuditService
    from rentivo.services.auth_challenge_service import AuthChallengeService
    from rentivo.services.authorization_service import AuthorizationService
    from rentivo.services.bill_service import BillService
    from rentivo.services.billing_attachment_service import BillingAttachmentService
    from rentivo.services.billing_notification_service import BillingNotificationService
    from rentivo.services.billing_service import BillingService
    from rentivo.services.billing_stats_service import BillingStatsService
    from rentivo.services.communication_service import CommunicationService
    from rentivo.services.container import RequestServices
    from rentivo.services.expense_service import ExpenseService
    from rentivo.services.google_auth_service import GoogleAuthService
    from rentivo.services.invite_service import InviteService
    from rentivo.services.job_service import JobService
    from rentivo.services.known_device_service import KnownDeviceService
    from rentivo.services.login_service import LoginService
    from rentivo.services.mfa_service import MFAService
    from rentivo.services.organization_service import OrganizationService
    from rentivo.services.password_reset_service import PasswordResetService
    from rentivo.services.pix_service import PixService
    from rentivo.services.rate_limit_service import RateLimitService
    from rentivo.services.recipient_service import RecipientService
    from rentivo.services.storage_cleanup_service import StorageCleanupService
    from rentivo.services.theme_service import ThemeService
    from rentivo.services.turnstile_service import TurnstileService
    from rentivo.services.user_service import UserService

    services = RequestServices(conn=db_connection, encryption=fake_encryption)
    expected_types = {
        "billing": BillingService,
        "api_key": APIKeyService,
        "auth_challenge": AuthChallengeService,
        "auth_rate_limit": RateLimitService,
        "login": LoginService,
        "billing_attachment": BillingAttachmentService,
        "billing_stats": BillingStatsService,
        "expense": ExpenseService,
        "user": UserService,
        "organization": OrganizationService,
        "theme": ThemeService,
        "pix": PixService,
        "invite": InviteService,
        "authorization": AuthorizationService,
        "audit": AuditService,
        "mfa": MFAService,
        "job": JobService,
        "known_device": KnownDeviceService,
        "turnstile": TurnstileService,
        "google_auth": GoogleAuthService,
        "password_reset": PasswordResetService,
        "bill": BillService,
        "recipient": RecipientService,
        "reply_to": RecipientService,
        "communication": CommunicationService,
        "storage_cleanup": StorageCleanupService,
        "billing_notification": BillingNotificationService,
    }

    for property_name, expected_type in expected_types.items():
        service = getattr(services, property_name)
        assert isinstance(service, expected_type)
        assert getattr(services, property_name) is service
