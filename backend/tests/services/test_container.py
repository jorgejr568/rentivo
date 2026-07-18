def test_legacy_request_services_reexports_shared_container():
    from legacy_web.services_container import RequestServices as LegacyRequestServices
    from rentivo.services.container import RequestServices

    assert LegacyRequestServices is RequestServices


def test_legacy_service_container_preserves_module_patch_points():
    import legacy_web.services_container as legacy_container
    import rentivo.services.container as shared_container

    assert legacy_container is shared_container


def test_api_key_service_is_lazily_cached(db_connection, fake_encryption):
    from rentivo.services.api_key_service import APIKeyService
    from rentivo.services.container import RequestServices

    services = RequestServices(conn=db_connection, encryption=fake_encryption)

    assert isinstance(services.api_key, APIKeyService)
    assert services.api_key is services.api_key


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
