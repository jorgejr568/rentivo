from unittest.mock import MagicMock, patch

import bcrypt
import pytest

from rentivo.models.mfa import RecoveryCode, UserPasskey, UserTOTP
from rentivo.services.mfa_service import MFAService


class TestMFAServiceTOTP:
    def setup_method(self):
        self.totp_repo = MagicMock()
        self.recovery_repo = MagicMock()
        self.passkey_repo = MagicMock()
        self.org_repo = MagicMock()
        self.service = MFAService(
            totp_repo=self.totp_repo,
            recovery_repo=self.recovery_repo,
            passkey_repo=self.passkey_repo,
            org_repo=self.org_repo,
        )

    def test_get_totp(self):
        totp = UserTOTP(id=1, user_id=10, secret="SECRET", confirmed=True)
        self.totp_repo.get_by_user_id.return_value = totp
        result = self.service.get_totp(10)
        assert result == totp
        self.totp_repo.get_by_user_id.assert_called_once_with(10)

    def test_get_totp_none(self):
        self.totp_repo.get_by_user_id.return_value = None
        result = self.service.get_totp(10)
        assert result is None

    def test_has_confirmed_totp_true(self):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="S", confirmed=True)
        assert self.service.has_confirmed_totp(10) is True

    def test_has_confirmed_totp_false_unconfirmed(self):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="S", confirmed=False)
        assert self.service.has_confirmed_totp(10) is False

    def test_has_confirmed_totp_false_none(self):
        self.totp_repo.get_by_user_id.return_value = None
        assert self.service.has_confirmed_totp(10) is False

    @patch("rentivo.services.mfa_service.qrcode")
    @patch("rentivo.services.mfa_service.pyotp")
    def test_setup_totp_no_existing(self, mock_pyotp, mock_qrcode):
        self.totp_repo.get_by_user_id.return_value = None
        mock_pyotp.random_base32.return_value = "FAKESECRET"
        created_totp = UserTOTP(id=1, user_id=10, secret="FAKESECRET", confirmed=False)
        self.totp_repo.create.return_value = created_totp

        mock_totp_instance = MagicMock()
        mock_totp_instance.provisioning_uri.return_value = "otpauth://totp/Rentivo:user?secret=FAKESECRET"
        mock_pyotp.TOTP.return_value = mock_totp_instance

        mock_qr_img = MagicMock()
        mock_qrcode.make.return_value = mock_qr_img

        record, uri, qr_b64 = self.service.setup_totp(10, "user")

        assert record == created_totp
        assert uri == "otpauth://totp/Rentivo:user?secret=FAKESECRET"
        assert isinstance(qr_b64, str)
        self.totp_repo.delete_by_user_id.assert_not_called()
        self.totp_repo.create.assert_called_once()

    @patch("rentivo.services.mfa_service.qrcode")
    @patch("rentivo.services.mfa_service.pyotp")
    def test_setup_totp_replaces_unconfirmed(self, mock_pyotp, mock_qrcode):
        existing = UserTOTP(id=1, user_id=10, secret="OLD", confirmed=False)
        self.totp_repo.get_by_user_id.return_value = existing
        mock_pyotp.random_base32.return_value = "NEWSECRET"
        self.totp_repo.create.return_value = UserTOTP(id=2, user_id=10, secret="NEWSECRET", confirmed=False)

        mock_totp_instance = MagicMock()
        mock_totp_instance.provisioning_uri.return_value = "otpauth://..."
        mock_pyotp.TOTP.return_value = mock_totp_instance
        mock_qrcode.make.return_value = MagicMock()

        self.service.setup_totp(10, "user")

        self.totp_repo.delete_by_user_id.assert_called_once_with(10)
        self.totp_repo.create.assert_called_once()

    def test_setup_totp_raises_if_already_confirmed(self):
        existing = UserTOTP(id=1, user_id=10, secret="S", confirmed=True)
        self.totp_repo.get_by_user_id.return_value = existing
        with pytest.raises(ValueError, match="já está ativado"):
            self.service.setup_totp(10, "user")

    @patch("rentivo.services.mfa_service.pyotp")
    def test_confirm_totp_success(self, mock_pyotp):
        totp_record = UserTOTP(id=1, user_id=10, secret="SECRET", confirmed=False)
        self.totp_repo.get_by_user_id.return_value = totp_record

        mock_totp_instance = MagicMock()
        mock_totp_instance.verify.return_value = True
        mock_pyotp.TOTP.return_value = mock_totp_instance

        result = self.service.confirm_totp(10, "123456")

        assert isinstance(result, list)
        assert len(result) == 10  # RECOVERY_CODE_COUNT
        self.totp_repo.confirm.assert_called_once_with(10)
        self.recovery_repo.delete_all_by_user.assert_called_once_with(10)
        self.recovery_repo.create_batch.assert_called_once()
        # Verify create_batch received 10 hashes
        batch_call_args = self.recovery_repo.create_batch.call_args
        assert batch_call_args[0][0] == 10  # user_id
        assert len(batch_call_args[0][1]) == 10  # 10 hashes

    def test_confirm_totp_raises_no_totp(self):
        self.totp_repo.get_by_user_id.return_value = None
        with pytest.raises(ValueError, match="Nenhuma configuração TOTP"):
            self.service.confirm_totp(10, "123456")

    def test_confirm_totp_raises_already_confirmed(self):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="S", confirmed=True)
        with pytest.raises(ValueError, match="já está confirmado"):
            self.service.confirm_totp(10, "123456")

    @patch("rentivo.services.mfa_service.pyotp")
    def test_confirm_totp_raises_invalid_code(self, mock_pyotp):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="SECRET", confirmed=False)
        mock_totp_instance = MagicMock()
        mock_totp_instance.verify.return_value = False
        mock_pyotp.TOTP.return_value = mock_totp_instance

        with pytest.raises(ValueError, match="Código TOTP inválido"):
            self.service.confirm_totp(10, "000000")

    @patch("rentivo.services.mfa_service.pyotp")
    def test_verify_totp_success(self, mock_pyotp):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="SECRET", confirmed=True)
        mock_totp_instance = MagicMock()
        mock_totp_instance.verify.return_value = True
        mock_pyotp.TOTP.return_value = mock_totp_instance

        assert self.service.verify_totp(10, "123456") is True
        mock_totp_instance.verify.assert_called_once_with("123456", valid_window=1)

    @patch("rentivo.services.mfa_service.pyotp")
    def test_verify_totp_invalid_code(self, mock_pyotp):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="SECRET", confirmed=True)
        mock_totp_instance = MagicMock()
        mock_totp_instance.verify.return_value = False
        mock_pyotp.TOTP.return_value = mock_totp_instance

        assert self.service.verify_totp(10, "000000") is False

    def test_verify_totp_no_totp(self):
        self.totp_repo.get_by_user_id.return_value = None
        assert self.service.verify_totp(10, "123456") is False

    def test_verify_totp_unconfirmed(self):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="S", confirmed=False)
        assert self.service.verify_totp(10, "123456") is False

    def test_disable_totp(self):
        self.service.disable_totp(10)
        self.totp_repo.delete_by_user_id.assert_called_once_with(10)
        self.recovery_repo.delete_all_by_user.assert_called_once_with(10)


class TestMFAServiceRecoveryCodes:
    def setup_method(self):
        self.totp_repo = MagicMock()
        self.recovery_repo = MagicMock()
        self.passkey_repo = MagicMock()
        self.org_repo = MagicMock()
        self.service = MFAService(
            totp_repo=self.totp_repo,
            recovery_repo=self.recovery_repo,
            passkey_repo=self.passkey_repo,
            org_repo=self.org_repo,
        )

    def test_verify_recovery_code_success(self):
        code = "abcd1234"
        hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
        rc = RecoveryCode(id=5, user_id=10, code_hash=hashed)
        self.recovery_repo.list_unused_by_user.return_value = [rc]

        result = self.service.verify_recovery_code(10, code)
        assert result is True
        self.recovery_repo.mark_used.assert_called_once_with(5)

    def test_verify_recovery_code_wrong_code(self):
        hashed = bcrypt.hashpw(b"abcd1234", bcrypt.gensalt()).decode()
        rc = RecoveryCode(id=5, user_id=10, code_hash=hashed)
        self.recovery_repo.list_unused_by_user.return_value = [rc]

        result = self.service.verify_recovery_code(10, "wrongcode")
        assert result is False
        self.recovery_repo.mark_used.assert_not_called()

    def test_verify_recovery_code_no_codes(self):
        self.recovery_repo.list_unused_by_user.return_value = []
        result = self.service.verify_recovery_code(10, "anything")
        assert result is False

    def test_verify_recovery_code_matches_second_code(self):
        code = "match1234"
        hashed_wrong = bcrypt.hashpw(b"other1234", bcrypt.gensalt()).decode()
        hashed_right = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
        rc1 = RecoveryCode(id=1, user_id=10, code_hash=hashed_wrong)
        rc2 = RecoveryCode(id=2, user_id=10, code_hash=hashed_right)
        self.recovery_repo.list_unused_by_user.return_value = [rc1, rc2]

        result = self.service.verify_recovery_code(10, code)
        assert result is True
        self.recovery_repo.mark_used.assert_called_once_with(2)

    def test_regenerate_recovery_codes_success(self):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="S", confirmed=True)
        result = self.service.regenerate_recovery_codes(10)
        assert isinstance(result, list)
        assert len(result) == 10
        self.recovery_repo.delete_all_by_user.assert_called_once_with(10)
        self.recovery_repo.create_batch.assert_called_once()

    def test_regenerate_recovery_codes_raises_no_totp(self):
        self.totp_repo.get_by_user_id.return_value = None
        with pytest.raises(ValueError, match="TOTP não está ativado"):
            self.service.regenerate_recovery_codes(10)

    def test_regenerate_recovery_codes_raises_unconfirmed(self):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="S", confirmed=False)
        with pytest.raises(ValueError, match="TOTP não está ativado"):
            self.service.regenerate_recovery_codes(10)

    def test_count_unused_recovery_codes(self):
        self.recovery_repo.list_unused_by_user.return_value = [
            RecoveryCode(id=1, user_id=10, code_hash="h1"),
            RecoveryCode(id=2, user_id=10, code_hash="h2"),
            RecoveryCode(id=3, user_id=10, code_hash="h3"),
        ]
        assert self.service.count_unused_recovery_codes(10) == 3
        self.recovery_repo.list_unused_by_user.assert_called_once_with(10)

    def test_count_unused_recovery_codes_zero(self):
        self.recovery_repo.list_unused_by_user.return_value = []
        assert self.service.count_unused_recovery_codes(10) == 0


class TestMFAServicePasskeys:
    def setup_method(self):
        self.totp_repo = MagicMock()
        self.recovery_repo = MagicMock()
        self.passkey_repo = MagicMock()
        self.org_repo = MagicMock()
        self.service = MFAService(
            totp_repo=self.totp_repo,
            recovery_repo=self.recovery_repo,
            passkey_repo=self.passkey_repo,
            org_repo=self.org_repo,
        )

    def test_list_passkeys(self):
        passkeys = [
            UserPasskey(id=1, user_id=10, name="Key1"),
            UserPasskey(id=2, user_id=10, name="Key2"),
        ]
        self.passkey_repo.list_by_user.return_value = passkeys
        result = self.service.list_passkeys(10)
        assert len(result) == 2
        self.passkey_repo.list_by_user.assert_called_once_with(10)

    def test_register_passkey(self):
        passkey = UserPasskey(user_id=10, name="MyKey", credential_id="cred1", public_key="pk1")
        created = UserPasskey(id=1, user_id=10, name="MyKey", credential_id="cred1", public_key="pk1")
        self.passkey_repo.create.return_value = created
        result = self.service.register_passkey(passkey)
        assert result.id == 1
        self.passkey_repo.create.assert_called_once_with(passkey)

    def test_get_passkey_by_credential_id(self):
        passkey = UserPasskey(id=1, user_id=10, credential_id="cred1")
        self.passkey_repo.get_by_credential_id.return_value = passkey
        result = self.service.get_passkey_by_credential_id("cred1")
        assert result == passkey
        self.passkey_repo.get_by_credential_id.assert_called_once_with("cred1")

    def test_get_passkey_by_credential_id_not_found(self):
        self.passkey_repo.get_by_credential_id.return_value = None
        result = self.service.get_passkey_by_credential_id("nonexistent")
        assert result is None

    def test_update_passkey_sign_count(self):
        self.service.update_passkey_sign_count(1, 42)
        self.passkey_repo.update_sign_count.assert_called_once_with(1, 42)
        self.passkey_repo.update_last_used.assert_called_once_with(1)

    def test_delete_passkey_success(self):
        passkey = UserPasskey(id=5, uuid="pk-uuid", user_id=10, name="Key")
        self.passkey_repo.get_by_uuid.return_value = passkey
        self.service.delete_passkey("pk-uuid", 10)
        self.passkey_repo.get_by_uuid.assert_called_once_with("pk-uuid")
        self.passkey_repo.delete.assert_called_once_with(5)

    def test_delete_passkey_not_found(self):
        self.passkey_repo.get_by_uuid.return_value = None
        with pytest.raises(ValueError, match="Passkey não encontrada"):
            self.service.delete_passkey("nonexistent", 10)

    def test_delete_passkey_wrong_user(self):
        passkey = UserPasskey(id=5, uuid="pk-uuid", user_id=99, name="Key")
        self.passkey_repo.get_by_uuid.return_value = passkey
        with pytest.raises(ValueError, match="Passkey não encontrada"):
            self.service.delete_passkey("pk-uuid", 10)


class TestMFAServiceStatus:
    def setup_method(self):
        self.totp_repo = MagicMock()
        self.recovery_repo = MagicMock()
        self.passkey_repo = MagicMock()
        self.org_repo = MagicMock()
        self.service = MFAService(
            totp_repo=self.totp_repo,
            recovery_repo=self.recovery_repo,
            passkey_repo=self.passkey_repo,
            org_repo=self.org_repo,
        )

    def test_has_any_mfa_with_totp(self):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="S", confirmed=True)
        assert self.service.has_any_mfa(10) is True
        # Should not need to check passkeys when TOTP is confirmed
        self.passkey_repo.list_by_user.assert_not_called()

    def test_has_any_mfa_with_passkeys(self):
        self.totp_repo.get_by_user_id.return_value = None
        self.passkey_repo.list_by_user.return_value = [UserPasskey(id=1, user_id=10, name="Key")]
        assert self.service.has_any_mfa(10) is True

    def test_has_any_mfa_false(self):
        self.totp_repo.get_by_user_id.return_value = None
        self.passkey_repo.list_by_user.return_value = []
        assert self.service.has_any_mfa(10) is False

    def test_has_any_mfa_unconfirmed_totp_no_passkeys(self):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="S", confirmed=False)
        self.passkey_repo.list_by_user.return_value = []
        assert self.service.has_any_mfa(10) is False

    def test_user_requires_mfa_setup_has_mfa(self):
        self.totp_repo.get_by_user_id.return_value = UserTOTP(id=1, user_id=10, secret="S", confirmed=True)
        assert self.service.user_requires_mfa_setup(10) is False
        # Should not check org enforcement when MFA exists
        self.org_repo.user_has_enforcing_org.assert_not_called()

    def test_user_requires_mfa_setup_no_mfa_enforcing_org(self):
        self.totp_repo.get_by_user_id.return_value = None
        self.passkey_repo.list_by_user.return_value = []
        self.org_repo.user_has_enforcing_org.return_value = True
        assert self.service.user_requires_mfa_setup(10) is True

    def test_user_requires_mfa_setup_no_mfa_no_enforcing_org(self):
        self.totp_repo.get_by_user_id.return_value = None
        self.passkey_repo.list_by_user.return_value = []
        self.org_repo.user_has_enforcing_org.return_value = False
        assert self.service.user_requires_mfa_setup(10) is False

    def test_user_in_enforcing_org_true(self):
        self.org_repo.user_has_enforcing_org.return_value = True
        assert self.service.user_in_enforcing_org(10) is True
        self.org_repo.user_has_enforcing_org.assert_called_once_with(10)

    def test_user_in_enforcing_org_false(self):
        self.org_repo.user_has_enforcing_org.return_value = False
        assert self.service.user_in_enforcing_org(10) is False
        self.org_repo.user_has_enforcing_org.assert_called_once_with(10)
