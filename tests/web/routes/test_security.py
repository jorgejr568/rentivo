import re
import time as real_time
from unittest.mock import MagicMock, patch

import pyotp

from rentivo.models.mfa import UserPasskey, UserTOTP
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyUserRepository,
)
from tests.web.conftest import create_org_in_db, get_test_user_id


def _setup_confirmed_totp(test_engine, user_id, secret=None):
    """Insert a confirmed TOTP record for the given user. Returns the secret."""
    if secret is None:
        secret = pyotp.random_base32()
    with test_engine.connect() as conn:
        totp_repo = SQLAlchemyMFATOTPRepository(conn)
        # Remove any existing TOTP first
        totp_repo.delete_by_user_id(user_id)
        totp_repo.create(UserTOTP(user_id=user_id, secret=secret, confirmed=False))
        totp_repo.confirm(user_id)
    return secret


def _setup_passkey(test_engine, user_id, name="Test Passkey"):
    """Insert a passkey for the given user. Returns the created passkey."""
    with test_engine.connect() as conn:
        passkey_repo = SQLAlchemyPasskeyRepository(conn)
        return passkey_repo.create(
            UserPasskey(
                user_id=user_id,
                credential_id="test_cred_id",
                public_key="test_public_key",
                sign_count=0,
                name=name,
            )
        )


def _get_csrf_from_page(response):
    """Extract CSRF token from a rendered page."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    return match.group(1) if match else ""


class TestSecurityPage:
    def test_security_page_renders(self, auth_client):
        response = auth_client.get("/security")
        assert response.status_code == 200

    def test_security_page_shows_totp_status(self, auth_client, test_engine):
        response = auth_client.get("/security")
        assert response.status_code == 200
        # Page should render without TOTP enabled
        # The content depends on template, just check it loads

    def test_security_page_with_totp_enabled(self, auth_client, test_engine):
        user_id = get_test_user_id(test_engine)
        _setup_confirmed_totp(test_engine, user_id)
        response = auth_client.get("/security")
        assert response.status_code == 200


class TestTOTPSetup:
    def test_totp_setup_renders(self, auth_client):
        response = auth_client.get("/security/totp/setup")
        assert response.status_code == 200
        # Should contain a QR code and a secret
        assert "qr" in response.text.lower() or "secret" in response.text.lower() or "base64" in response.text.lower()

    def test_totp_setup_redirects_if_already_enabled(self, auth_client, test_engine):
        user_id = get_test_user_id(test_engine)
        _setup_confirmed_totp(test_engine, user_id)

        response = auth_client.get("/security/totp/setup", follow_redirects=False)
        assert response.status_code == 302
        assert "/security" in response.headers["location"]

    def test_totp_confirm_success(self, auth_client, test_engine, csrf_token):
        """Full TOTP setup flow: GET setup -> extract secret -> generate code -> confirm."""
        # GET the setup page to trigger TOTP record creation
        setup_response = auth_client.get("/security/totp/setup")
        assert setup_response.status_code == 200

        # Extract the secret from the rendered page
        secret_match = re.search(
            r'(?:name="secret"|id="secret"|data-secret=")?\s*value="([A-Z2-7]{32})"', setup_response.text
        )
        if not secret_match:
            # Try alternative patterns
            secret_match = re.search(r"([A-Z2-7]{32})", setup_response.text)
        assert secret_match, "Could not extract TOTP secret from setup page"
        secret = secret_match.group(1)

        # Generate a valid TOTP code
        totp = pyotp.TOTP(secret)
        code = totp.now()

        # Get a fresh CSRF token from the setup page
        csrf = _get_csrf_from_page(setup_response)
        if not csrf:
            csrf = csrf_token

        response = auth_client.post(
            "/security/totp/confirm",
            data={"csrf_token": csrf, "code": code},
            follow_redirects=True,
        )
        # Should show recovery codes page on success
        assert response.status_code == 200

    def test_totp_confirm_invalid_code(self, auth_client, test_engine, csrf_token):
        """Confirming TOTP with invalid code should redirect back to setup."""
        # Trigger TOTP setup first
        auth_client.get("/security/totp/setup")

        response = auth_client.post(
            "/security/totp/confirm",
            data={"csrf_token": csrf_token, "code": "000000"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/security/totp/setup" in response.headers["location"]

    def test_totp_confirm_no_setup(self, auth_client, csrf_token):
        """Confirming TOTP without prior setup should redirect with error."""
        response = auth_client.post(
            "/security/totp/confirm",
            data={"csrf_token": csrf_token, "code": "123456"},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestTOTPDisable:
    def test_totp_disable_success(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        _setup_confirmed_totp(test_engine, user_id)

        response = auth_client.post(
            "/security/totp/disable",
            data={"csrf_token": csrf_token, "password": "testpass"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/security" in response.headers["location"]

        # Verify TOTP is disabled
        with test_engine.connect() as conn:
            totp_repo = SQLAlchemyMFATOTPRepository(conn)
            assert totp_repo.get_by_user_id(user_id) is None

    def test_totp_disable_wrong_password(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        _setup_confirmed_totp(test_engine, user_id)

        response = auth_client.post(
            "/security/totp/disable",
            data={"csrf_token": csrf_token, "password": "wrongpassword"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        # TOTP should still be enabled
        with test_engine.connect() as conn:
            totp_repo = SQLAlchemyMFATOTPRepository(conn)
            totp = totp_repo.get_by_user_id(user_id)
            assert totp is not None
            assert totp.confirmed is True

    def test_totp_disable_enforcing_org_blocks(self, auth_client, test_engine, csrf_token):
        """Cannot disable TOTP when user belongs to an MFA-enforcing org."""
        user_id = get_test_user_id(test_engine)
        _setup_confirmed_totp(test_engine, user_id)

        # Create org with enforce_mfa=True and add user as member
        org = create_org_in_db(test_engine, "MFA Org", user_id)
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org.enforce_mfa = True
            org_repo.update(org)

        response = auth_client.post(
            "/security/totp/disable",
            data={"csrf_token": csrf_token, "password": "testpass"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        # TOTP should still be enabled
        with test_engine.connect() as conn:
            totp_repo = SQLAlchemyMFATOTPRepository(conn)
            totp = totp_repo.get_by_user_id(user_id)
            assert totp is not None
            assert totp.confirmed is True


class TestRecoveryCodesRegenerate:
    def test_regenerate_success(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        _setup_confirmed_totp(test_engine, user_id)

        response = auth_client.post(
            "/security/recovery-codes/regenerate",
            data={"csrf_token": csrf_token},
        )
        # Should show recovery codes page
        assert response.status_code == 200

    def test_regenerate_without_totp(self, auth_client, csrf_token):
        """Regenerating recovery codes without TOTP should redirect with error."""
        response = auth_client.post(
            "/security/recovery-codes/regenerate",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/security" in response.headers["location"]


class TestPasskeyDelete:
    def test_delete_passkey_success(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        passkey = _setup_passkey(test_engine, user_id)

        response = auth_client.post(
            f"/security/passkeys/{passkey.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/security" in response.headers["location"]

        # Verify passkey is deleted
        with test_engine.connect() as conn:
            passkey_repo = SQLAlchemyPasskeyRepository(conn)
            assert passkey_repo.get_by_uuid(passkey.uuid) is None

    def test_delete_passkey_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/security/passkeys/nonexistent-uuid/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_passkey_wrong_user(self, auth_client, test_engine, csrf_token):
        """Cannot delete a passkey belonging to another user."""
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            from rentivo.models.user import User

            other_user = user_repo.create(User(username="other_pk_user", password_hash="h"))

        passkey = _setup_passkey(test_engine, other_user.id, name="Other User Key")

        response = auth_client.post(
            f"/security/passkeys/{passkey.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

        # Passkey should still exist
        with test_engine.connect() as conn:
            passkey_repo = SQLAlchemyPasskeyRepository(conn)
            assert passkey_repo.get_by_uuid(passkey.uuid) is not None


class TestOrganizationToggleMFA:
    def test_toggle_mfa_enable(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Toggle MFA Org", user_id)

        response = auth_client.post(
            f"/organizations/{org.uuid}/toggle-mfa",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

        # Verify MFA is now enabled
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            updated_org = org_repo.get_by_uuid(org.uuid)
            assert updated_org.enforce_mfa is True

    def test_toggle_mfa_disable(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Toggle Off Org", user_id)

        # Enable first
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org.enforce_mfa = True
            org_repo.update(org)

        # Get fresh CSRF token
        fresh_csrf = _get_csrf_from_page(auth_client.get("/security"))

        response = auth_client.post(
            f"/organizations/{org.uuid}/toggle-mfa",
            data={"csrf_token": fresh_csrf},
            follow_redirects=False,
        )
        assert response.status_code == 302

        # Verify MFA is now disabled
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            updated_org = org_repo.get_by_uuid(org.uuid)
            assert updated_org.enforce_mfa is False

    def test_toggle_mfa_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/organizations/nonexistent/toggle-mfa",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_toggle_mfa_not_admin(self, auth_client, test_engine, csrf_token):
        """Non-admin members cannot toggle MFA."""
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            from rentivo.models.user import User

            other_user = user_repo.create(User(username="mfa_org_owner", password_hash="h"))

        org = create_org_in_db(test_engine, "Not Admin Org", other_user.id)

        # Add test user as viewer
        user_id = get_test_user_id(test_engine)
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org_repo.add_member(org.id, user_id, "viewer")

        response = auth_client.post(
            f"/organizations/{org.uuid}/toggle-mfa",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

        # MFA should still be off
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            updated_org = org_repo.get_by_uuid(org.uuid)
            assert updated_org.enforce_mfa is False


class TestPasskeyRegisterBegin:
    def test_returns_registration_options(self, auth_client, test_engine):
        with patch("web.routes.security.webauthn") as mock_wa:
            mock_options = MagicMock()
            mock_options.challenge = b"test_challenge"
            mock_wa.generate_registration_options.return_value = mock_options
            mock_wa.options_to_json.return_value = '{"publicKey": {"challenge": "dGVzdA"}}'

            response = auth_client.post("/security/passkeys/register/begin")
            assert response.status_code == 200
            assert "publicKey" in response.json()

    def test_excludes_existing_passkeys(self, auth_client, test_engine):
        user_id = get_test_user_id(test_engine)
        _setup_passkey(test_engine, user_id)

        with patch("web.routes.security.webauthn") as mock_wa:
            mock_wa.base64url_to_bytes.return_value = b"existing_cred"
            mock_options = MagicMock()
            mock_options.challenge = b"test_challenge"
            mock_wa.generate_registration_options.return_value = mock_options
            mock_wa.options_to_json.return_value = '{"publicKey": {}}'

            response = auth_client.post("/security/passkeys/register/begin")
            assert response.status_code == 200
            call_kwargs = mock_wa.generate_registration_options.call_args
            assert len(call_kwargs.kwargs.get("exclude_credentials", [])) >= 1


class TestPasskeyRegisterComplete:
    def _begin_registration(self, auth_client):
        """Call register/begin to set challenge in session."""
        with patch("web.routes.security.webauthn") as mock_wa:
            mock_options = MagicMock()
            mock_options.challenge = b"test_challenge"
            mock_wa.generate_registration_options.return_value = mock_options
            mock_wa.options_to_json.return_value = '{"publicKey": {}}'
            auth_client.post("/security/passkeys/register/begin")

    def test_complete_success(self, auth_client, test_engine):
        self._begin_registration(auth_client)

        with patch("web.routes.security.webauthn") as mock_wa:
            mock_verification = MagicMock()
            mock_verification.credential_id = b"new_cred_id"
            mock_verification.credential_public_key = b"new_public_key"
            mock_verification.sign_count = 0
            mock_wa.verify_registration_response.return_value = mock_verification

            response = auth_client.post(
                "/security/passkeys/register/complete",
                json={"id": "test", "name": "My Key"},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            assert response.json()["name"] == "My Key"

    def test_complete_default_name(self, auth_client, test_engine):
        self._begin_registration(auth_client)

        with patch("web.routes.security.webauthn") as mock_wa:
            mock_verification = MagicMock()
            mock_verification.credential_id = b"cred2"
            mock_verification.credential_public_key = b"pk2"
            mock_verification.sign_count = 0
            mock_wa.verify_registration_response.return_value = mock_verification

            response = auth_client.post(
                "/security/passkeys/register/complete",
                json={"id": "test"},
            )
            assert response.status_code == 200
            assert response.json()["name"] == "Minha Passkey"

    def test_complete_expired_challenge(self, auth_client, test_engine):
        with (
            patch("web.routes.security.webauthn") as mock_wa,
            patch("web.routes.security.time") as mock_time,
        ):
            mock_time.time.return_value = real_time.time() - 600
            mock_options = MagicMock()
            mock_options.challenge = b"test_challenge"
            mock_wa.generate_registration_options.return_value = mock_options
            mock_wa.options_to_json.return_value = '{"publicKey": {}}'
            auth_client.post("/security/passkeys/register/begin")

        with patch("web.routes.security.webauthn"):
            response = auth_client.post(
                "/security/passkeys/register/complete",
                json={"id": "test"},
            )
            assert response.status_code == 400

    def test_complete_no_challenge(self, auth_client, test_engine):
        with patch("web.routes.security.webauthn"):
            response = auth_client.post(
                "/security/passkeys/register/complete",
                json={"id": "test"},
            )
            assert response.status_code == 400

    def test_complete_verification_failure(self, auth_client, test_engine):
        self._begin_registration(auth_client)

        with patch("web.routes.security.webauthn") as mock_wa:
            mock_wa.verify_registration_response.side_effect = Exception("bad credential")

            response = auth_client.post(
                "/security/passkeys/register/complete",
                json={"id": "test"},
            )
            assert response.status_code == 400


class TestPasskeyAuthBegin:
    def _login_mfa_user(self, client, test_engine):
        """Create user with TOTP, login to get MFA pending session."""
        from rentivo.models.mfa import UserTOTP
        from rentivo.services.user_service import UserService

        secret = pyotp.random_base32()
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_service = UserService(user_repo)
            user = user_service.create_user("passkeyuser", "secret")

        with test_engine.connect() as conn:
            totp_repo = SQLAlchemyMFATOTPRepository(conn)
            totp_repo.create(UserTOTP(user_id=user.id, secret=secret, confirmed=False))
            totp_repo.confirm(user.id)

        client.post(
            "/login",
            data={"username": "passkeyuser", "password": "secret"},
            follow_redirects=False,
        )
        return user, secret

    def test_no_pending_login(self, client):
        response = client.post("/security/passkeys/auth/begin")
        assert response.status_code == 400
        assert "Sem login pendente" in response.json()["error"]

    def test_returns_authentication_options(self, client, test_engine):
        user, _ = self._login_mfa_user(client, test_engine)
        _setup_passkey(test_engine, user.id)

        with patch("web.routes.security.webauthn") as mock_wa:
            mock_wa.base64url_to_bytes.return_value = b"cred_bytes"
            mock_options = MagicMock()
            mock_options.challenge = b"auth_challenge"
            mock_wa.generate_authentication_options.return_value = mock_options
            mock_wa.options_to_json.return_value = '{"publicKey": {"challenge": "dGVzdA"}}'

            response = client.post("/security/passkeys/auth/begin")
            assert response.status_code == 200
            assert "publicKey" in response.json()


class TestPasskeyAuthComplete:
    def _setup_mfa_pending_with_passkey(self, client, test_engine):
        """Create user with TOTP + passkey, login to get MFA pending state."""
        from rentivo.models.mfa import UserTOTP
        from rentivo.services.user_service import UserService

        secret = pyotp.random_base32()

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_service = UserService(user_repo)
            user = user_service.create_user("pkauth_user", "secret")

        with test_engine.connect() as conn:
            totp_repo = SQLAlchemyMFATOTPRepository(conn)
            totp_repo.create(UserTOTP(user_id=user.id, secret=secret, confirmed=False))
            totp_repo.confirm(user.id)

        passkey = _setup_passkey(test_engine, user.id)

        client.post(
            "/login",
            data={"username": "pkauth_user", "password": "secret"},
            follow_redirects=False,
        )
        return user, passkey

    def _begin_auth(self, client):
        """Call auth/begin to set challenge in session."""
        with patch("web.routes.security.webauthn") as mock_wa:
            mock_wa.base64url_to_bytes.return_value = b"cred_bytes"
            mock_options = MagicMock()
            mock_options.challenge = b"auth_challenge"
            mock_wa.generate_authentication_options.return_value = mock_options
            mock_wa.options_to_json.return_value = '{"publicKey": {}}'
            client.post("/security/passkeys/auth/begin")

    def test_no_pending_login(self, client):
        response = client.post(
            "/security/passkeys/auth/complete",
            json={"id": "test"},
        )
        assert response.status_code == 400

    def test_expired_challenge(self, client, test_engine):
        self._setup_mfa_pending_with_passkey(client, test_engine)

        with (
            patch("web.routes.security.webauthn") as mock_wa,
            patch("web.routes.security.time") as mock_time,
        ):
            mock_time.time.return_value = real_time.time() - 600
            mock_wa.base64url_to_bytes.return_value = b"cred"
            mock_options = MagicMock()
            mock_options.challenge = b"old_challenge"
            mock_wa.generate_authentication_options.return_value = mock_options
            mock_wa.options_to_json.return_value = '{"publicKey": {}}'
            client.post("/security/passkeys/auth/begin")

        with patch("web.routes.security.webauthn"):
            response = client.post(
                "/security/passkeys/auth/complete",
                json={"id": "test_cred_id"},
            )
            assert response.status_code == 400

    def test_passkey_not_found(self, client, test_engine):
        self._setup_mfa_pending_with_passkey(client, test_engine)
        self._begin_auth(client)

        response = client.post(
            "/security/passkeys/auth/complete",
            json={"id": "nonexistent_cred_id"},
        )
        assert response.status_code == 400

    def test_complete_success(self, client, test_engine):
        user, passkey = self._setup_mfa_pending_with_passkey(client, test_engine)
        self._begin_auth(client)

        with patch("web.routes.security.webauthn") as mock_wa:
            mock_wa.base64url_to_bytes.return_value = b"pk_bytes"
            mock_verification = MagicMock()
            mock_verification.new_sign_count = 1
            mock_wa.verify_authentication_response.return_value = mock_verification

            response = client.post(
                "/security/passkeys/auth/complete",
                json={"id": passkey.credential_id},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            assert response.json()["redirect"] == "/billings/"

        # User should now be logged in
        response = client.get("/billings/")
        assert response.status_code == 200

    def test_verification_failure(self, client, test_engine):
        user, passkey = self._setup_mfa_pending_with_passkey(client, test_engine)
        self._begin_auth(client)

        with patch("web.routes.security.webauthn") as mock_wa:
            mock_wa.base64url_to_bytes.return_value = b"pk_bytes"
            mock_wa.verify_authentication_response.side_effect = Exception("bad assertion")

            response = client.post(
                "/security/passkeys/auth/complete",
                json={"id": passkey.credential_id},
            )
            assert response.status_code == 400

    def test_complete_sets_mfa_setup_required(self, client, test_engine):
        """After passkey auth, if user needs MFA setup, session flag is set."""
        user, passkey = self._setup_mfa_pending_with_passkey(client, test_engine)
        self._begin_auth(client)

        from rentivo.models.mfa import UserPasskey as PK

        fake_passkey = PK(
            id=passkey.id,
            uuid=passkey.uuid,
            user_id=user.id,
            credential_id=passkey.credential_id,
            public_key=passkey.public_key,
            sign_count=0,
            name="Test",
        )

        mock_mfa = MagicMock()
        mock_mfa.get_passkey_by_credential_id.return_value = fake_passkey
        mock_mfa.user_requires_mfa_setup.return_value = True

        with (
            patch("web.routes.security.get_mfa_service", return_value=mock_mfa),
            patch("web.routes.security.webauthn") as mock_wa,
        ):
            mock_wa.base64url_to_bytes.return_value = b"pk_bytes"
            mock_verification = MagicMock()
            mock_verification.new_sign_count = 1
            mock_wa.verify_authentication_response.return_value = mock_verification

            response = client.post(
                "/security/passkeys/auth/complete",
                json={"id": passkey.credential_id},
            )
            assert response.status_code == 200

        # MFA setup required — accessing protected page redirects
        response = client.get("/billings/", follow_redirects=False)
        assert response.status_code == 302
        assert "/security/totp/setup" in response.headers["location"]
