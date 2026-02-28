from __future__ import annotations

import base64
import io
import logging
import secrets

import bcrypt
import pyotp
import qrcode

from rentivo.models.mfa import UserPasskey, UserTOTP
from rentivo.repositories.base import (
    MFATOTPRepository,
    OrganizationRepository,
    PasskeyRepository,
    RecoveryCodeRepository,
)

logger = logging.getLogger(__name__)

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 8


class MFAService:
    def __init__(
        self,
        totp_repo: MFATOTPRepository,
        recovery_repo: RecoveryCodeRepository,
        passkey_repo: PasskeyRepository,
        org_repo: OrganizationRepository,
    ) -> None:
        self.totp_repo = totp_repo
        self.recovery_repo = recovery_repo
        self.passkey_repo = passkey_repo
        self.org_repo = org_repo

    # --- TOTP ---

    def get_totp(self, user_id: int) -> UserTOTP | None:
        return self.totp_repo.get_by_user_id(user_id)

    def has_confirmed_totp(self, user_id: int) -> bool:
        totp = self.totp_repo.get_by_user_id(user_id)
        return totp is not None and totp.confirmed

    def setup_totp(self, user_id: int, username: str) -> tuple[UserTOTP, str, str]:
        """Begin TOTP setup. Returns (totp_record, provisioning_uri, qr_code_base64).

        If an unconfirmed TOTP exists, it is replaced. If a confirmed TOTP
        exists, raises ValueError.
        """
        existing = self.totp_repo.get_by_user_id(user_id)
        if existing is not None and existing.confirmed:
            raise ValueError("TOTP já está ativado")
        if existing is not None:
            self.totp_repo.delete_by_user_id(user_id)

        secret = pyotp.random_base32()
        totp_record = UserTOTP(user_id=user_id, secret=secret, confirmed=False)
        created = self.totp_repo.create(totp_record)

        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=username, issuer_name="Rentivo")

        qr = qrcode.make(provisioning_uri)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        qr_base64 = base64.b64encode(buf.getvalue()).decode()

        logger.info("TOTP setup initiated for user=%s", user_id)
        return created, provisioning_uri, qr_base64

    def confirm_totp(self, user_id: int, code: str) -> list[str]:
        """Confirm TOTP with a valid code. Returns list of plaintext recovery codes."""
        totp_record = self.totp_repo.get_by_user_id(user_id)
        if totp_record is None:
            raise ValueError("Nenhuma configuração TOTP em andamento")
        if totp_record.confirmed:
            raise ValueError("TOTP já está confirmado")

        totp = pyotp.TOTP(totp_record.secret)
        if not totp.verify(code, valid_window=1):
            raise ValueError("Código TOTP inválido")

        self.totp_repo.confirm(user_id)
        recovery_codes = self._generate_recovery_codes(user_id)

        logger.info("TOTP confirmed for user=%s", user_id)
        return recovery_codes

    def verify_totp(self, user_id: int, code: str) -> bool:
        """Verify a TOTP code during login."""
        totp_record = self.totp_repo.get_by_user_id(user_id)
        if totp_record is None or not totp_record.confirmed:
            return False
        totp = pyotp.TOTP(totp_record.secret)
        return totp.verify(code, valid_window=1)

    def disable_totp(self, user_id: int) -> None:
        """Disable TOTP and delete all recovery codes."""
        self.totp_repo.delete_by_user_id(user_id)
        self.recovery_repo.delete_all_by_user(user_id)
        logger.info("TOTP disabled for user=%s", user_id)

    # --- Recovery Codes ---

    def _generate_recovery_codes(self, user_id: int) -> list[str]:
        """Generate new recovery codes, replacing any existing ones."""
        self.recovery_repo.delete_all_by_user(user_id)
        codes: list[str] = []
        hashes: list[str] = []
        for _ in range(RECOVERY_CODE_COUNT):
            code = secrets.token_hex(RECOVERY_CODE_LENGTH // 2)
            codes.append(code)
            hashes.append(bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode())
        self.recovery_repo.create_batch(user_id, hashes)
        logger.info("Generated %d recovery codes for user=%s", len(codes), user_id)
        return codes

    def regenerate_recovery_codes(self, user_id: int) -> list[str]:
        """Regenerate recovery codes. Requires confirmed TOTP."""
        totp = self.totp_repo.get_by_user_id(user_id)
        if totp is None or not totp.confirmed:
            raise ValueError("TOTP não está ativado")
        return self._generate_recovery_codes(user_id)

    def verify_recovery_code(self, user_id: int, code: str) -> bool:
        """Verify and consume a recovery code."""
        unused = self.recovery_repo.list_unused_by_user(user_id)
        for rc in unused:
            if bcrypt.checkpw(code.encode(), rc.code_hash.encode()):
                self.recovery_repo.mark_used(rc.id)
                logger.info("Recovery code used for user=%s", user_id)
                return True
        return False

    def count_unused_recovery_codes(self, user_id: int) -> int:
        return len(self.recovery_repo.list_unused_by_user(user_id))

    # --- Passkeys ---

    def list_passkeys(self, user_id: int) -> list[UserPasskey]:
        return self.passkey_repo.list_by_user(user_id)

    def register_passkey(self, passkey: UserPasskey) -> UserPasskey:
        created = self.passkey_repo.create(passkey)
        logger.info("Passkey registered for user=%s name=%s", passkey.user_id, passkey.name)
        return created

    def get_passkey_by_credential_id(self, credential_id: str) -> UserPasskey | None:
        return self.passkey_repo.get_by_credential_id(credential_id)

    def update_passkey_sign_count(self, passkey_id: int, sign_count: int) -> None:
        self.passkey_repo.update_sign_count(passkey_id, sign_count)
        self.passkey_repo.update_last_used(passkey_id)

    def delete_passkey(self, passkey_uuid: str, user_id: int) -> None:
        passkey = self.passkey_repo.get_by_uuid(passkey_uuid)
        if passkey is None or passkey.user_id != user_id:
            raise ValueError("Passkey não encontrada")
        self.passkey_repo.delete(passkey.id)
        logger.info("Passkey deleted: uuid=%s user=%s", passkey_uuid, user_id)

    # --- MFA Status ---

    def has_any_mfa(self, user_id: int) -> bool:
        """Check if user has any confirmed MFA method."""
        if self.has_confirmed_totp(user_id):
            return True
        passkeys = self.passkey_repo.list_by_user(user_id)
        return len(passkeys) > 0

    def user_requires_mfa_setup(self, user_id: int) -> bool:
        """Check if user belongs to an enforcing org but has no MFA."""
        if self.has_any_mfa(user_id):
            return False
        return self.org_repo.user_has_enforcing_org(user_id)

    def user_in_enforcing_org(self, user_id: int) -> bool:
        """Check if user belongs to any MFA-enforcing org (regardless of MFA status)."""
        return self.org_repo.user_has_enforcing_org(user_id)
