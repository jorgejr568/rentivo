#!/usr/bin/env python3
"""Seed deterministic authentication fixtures for preview parity checks."""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Callable
from dataclasses import dataclass

from rentivo.models.mfa import UserTOTP
from rentivo.models.user import User
from rentivo.repositories.base import MFATOTPRepository, UserRepository
from rentivo.services.user_service import UserService

PARITY_USER_EMAIL = "parity.user@example.com"
PARITY_MFA_USER_EMAIL = "parity.mfa@example.com"


@dataclass(frozen=True)
class SeededAccount:
    email: str
    mfa_enabled: bool


@dataclass(frozen=True)
class SeedResult:
    accounts: tuple[SeededAccount, ...]


def ensure_non_production(environment: str) -> None:
    """Refuse to mutate a production database."""
    if environment not in {"dev", "staging"}:
        raise RuntimeError(
            "Parity fixtures are restricted to non-production environments."
        )


def validate_fixture_credentials(password: str, totp_secret: str) -> None:
    if len(password) < 12:
        raise ValueError("RENTIVO_PARITY_PASSWORD must contain at least 12 characters.")
    if not totp_secret:
        raise ValueError("RENTIVO_PARITY_TOTP_SECRET must be valid uppercase base32.")
    if len(totp_secret) < 32:
        raise ValueError(
            "RENTIVO_PARITY_TOTP_SECRET must contain at least 32 base32 characters."
        )
    try:
        base64.b32decode(totp_secret, casefold=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            "RENTIVO_PARITY_TOTP_SECRET must be valid uppercase base32."
        ) from exc


def _delete_fixture_accounts(user_repo: UserRepository) -> None:
    for email in (PARITY_USER_EMAIL, PARITY_MFA_USER_EMAIL):
        existing = user_repo.get_by_email(email)
        if existing is None:
            continue
        if existing.id is None:
            raise RuntimeError(f"Existing parity account has no database ID: {email}")
        user_repo.delete(existing.id)


def seed_parity_fixtures(
    *,
    environment: str,
    password: str,
    totp_secret: str,
    user_repo: UserRepository,
    totp_repo: MFATOTPRepository,
    password_hasher: Callable[[str], str] = UserService.hash_password,
) -> SeedResult:
    """Recreate dedicated preview accounts with stable authentication states."""
    ensure_non_production(environment)
    validate_fixture_credentials(password, totp_secret)

    accounts = (
        SeededAccount(email=PARITY_USER_EMAIL, mfa_enabled=False),
        SeededAccount(email=PARITY_MFA_USER_EMAIL, mfa_enabled=True),
    )
    try:
        _delete_fixture_accounts(user_repo)
        for account in accounts:
            created = user_repo.create(
                User(
                    email=account.email,
                    password_hash=password_hasher(password),
                )
            )
            if account.mfa_enabled:
                if created.id is None:
                    raise RuntimeError(
                        f"Created parity account has no database ID: {account.email}"
                    )
                totp_repo.create(
                    UserTOTP(
                        user_id=created.id,
                        secret=totp_secret,
                        confirmed=True,
                    )
                )
    except Exception:
        _delete_fixture_accounts(user_repo)
        raise

    return SeedResult(accounts=accounts)


def main() -> int:
    from rentivo.repositories.factory import (
        get_mfa_totp_repository,
        get_user_repository,
    )
    from rentivo.settings import settings

    environment = settings.environment
    password = os.environ.get("RENTIVO_PARITY_PASSWORD", "")
    totp_secret = os.environ.get("RENTIVO_PARITY_TOTP_SECRET", "")

    # Check safety and inputs before repository construction opens a database connection.
    ensure_non_production(environment)
    validate_fixture_credentials(password, totp_secret)

    result = seed_parity_fixtures(
        environment=environment,
        password=password,
        totp_secret=totp_secret,
        user_repo=get_user_repository(),
        totp_repo=get_mfa_totp_repository(),
    )
    print("Seeded deterministic preview accounts:")
    for account in result.accounts:
        mfa = "TOTP enabled" if account.mfa_enabled else "TOTP disabled"
        print(f"- {account.email} ({mfa})")
    print("Credentials were read from the environment and were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
