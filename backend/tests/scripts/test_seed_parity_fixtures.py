from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "seed_parity_fixtures.py"


def _load_script():
    assert SCRIPT_PATH.exists(), "parity fixture seeder has not been implemented"
    spec = importlib.util.spec_from_file_location("seed_parity_fixtures", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_production_environment_is_always_rejected():
    script = _load_script()

    with pytest.raises(RuntimeError, match="non-production"):
        script.ensure_non_production("production")


@pytest.mark.parametrize(
    ("password", "totp_secret", "message"),
    [
        ("short", "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", "at least 12"),
        ("preview-password", "", "base32"),
        ("preview-password", "JBSWY3DPEHPK3PXP", "at least 32"),
        ("preview-password", "not base32!", "base32"),
    ],
)
def test_fixture_credentials_are_validated(password: str, totp_secret: str, message: str):
    script = _load_script()

    with pytest.raises(ValueError, match=message):
        script.validate_fixture_credentials(password, totp_secret)


class FakeUserRepository:
    def __init__(self, users=()):
        self.users = {user.email: user for user in users}
        self.deleted_ids: list[int] = []
        self.next_id = max((user.id or 0 for user in users), default=0) + 1

    def get_by_email(self, email: str):
        return self.users.get(email)

    def create(self, user):
        created = user.model_copy(update={"id": self.next_id})
        self.next_id += 1
        self.users[created.email] = created
        return created

    def delete(self, user_id: int) -> bool:
        self.deleted_ids.append(user_id)
        email = next(email for email, user in self.users.items() if user.id == user_id)
        del self.users[email]
        return True


class FakeTOTPRepository:
    def __init__(self):
        self.created = []

    def create(self, totp):
        self.created.append(totp)
        return totp


class FailingTOTPRepository(FakeTOTPRepository):
    def create(self, totp):
        raise RuntimeError("simulated TOTP failure")


def test_seeder_recreates_known_accounts_with_a_confirmed_totp_fixture():
    script = _load_script()
    existing = (
        script.User(id=40, email=script.PARITY_USER_EMAIL, password_hash="stale"),
        script.User(id=41, email=script.PARITY_MFA_USER_EMAIL, password_hash="stale"),
    )
    user_repo = FakeUserRepository(existing)
    totp_repo = FakeTOTPRepository()

    result = script.seed_parity_fixtures(
        environment="dev",
        password="preview-password",
        totp_secret="JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
        user_repo=user_repo,
        totp_repo=totp_repo,
        password_hasher=lambda value: f"hash::{value}",
    )

    assert user_repo.deleted_ids == [40, 41]
    assert set(user_repo.users) == {script.PARITY_USER_EMAIL, script.PARITY_MFA_USER_EMAIL}
    assert {user.password_hash for user in user_repo.users.values()} == {"hash::preview-password"}
    mfa_user = user_repo.users[script.PARITY_MFA_USER_EMAIL]
    assert totp_repo.created == [
        script.UserTOTP(
            user_id=mfa_user.id,
            secret="JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
            confirmed=True,
        )
    ]
    assert result == script.SeedResult(
        accounts=(
            script.SeededAccount(email=script.PARITY_USER_EMAIL, mfa_enabled=False),
            script.SeededAccount(email=script.PARITY_MFA_USER_EMAIL, mfa_enabled=True),
        )
    )


def test_production_rejection_happens_before_any_repository_access():
    script = _load_script()

    class ExplodingRepository:
        def get_by_email(self, email: str):
            raise AssertionError(f"repository was accessed for {email}")

    with pytest.raises(RuntimeError, match="non-production"):
        script.seed_parity_fixtures(
            environment="production",
            password="preview-password",
            totp_secret="JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
            user_repo=ExplodingRepository(),
            totp_repo=ExplodingRepository(),
        )


def test_seeder_removes_all_fixture_accounts_after_a_mid_run_failure():
    script = _load_script()
    existing = (
        script.User(id=40, email=script.PARITY_USER_EMAIL, password_hash="stale"),
        script.User(id=41, email=script.PARITY_MFA_USER_EMAIL, password_hash="stale"),
    )
    user_repo = FakeUserRepository(existing)

    with pytest.raises(RuntimeError, match="simulated TOTP failure"):
        script.seed_parity_fixtures(
            environment="staging",
            password="preview-password",
            totp_secret="JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
            user_repo=user_repo,
            totp_repo=FailingTOTPRepository(),
            password_hasher=lambda value: f"hash::{value}",
        )

    assert user_repo.users == {}
    assert set(user_repo.deleted_ids) == {40, 41, 42, 43}


def test_cli_refuses_production_before_opening_a_database(monkeypatch):
    script = _load_script()
    from rentivo.settings import settings

    monkeypatch.setattr(settings, "environment", "production")

    with pytest.raises(RuntimeError, match="non-production"):
        script.main()
