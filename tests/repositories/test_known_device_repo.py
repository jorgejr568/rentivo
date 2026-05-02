from unittest.mock import patch

import pytest

from rentivo.models.known_device import KnownDevice
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyKnownDeviceRepository,
    SQLAlchemyUserRepository,
)


class TestKnownDeviceRepo:
    def test_upsert_creates_then_updates_last_seen(
        self,
        user_repo: SQLAlchemyUserRepository,
        known_device_repo: SQLAlchemyKnownDeviceRepository,
    ):
        user = user_repo.create(User(email="kd@example.com", password_hash="x"))

        first = known_device_repo.upsert(KnownDevice(user_id=user.id, device_hash="abc", user_agent_snippet="Firefox"))
        assert first.id is not None
        assert first.first_seen_at is not None
        assert first.last_seen_at is not None

        second = known_device_repo.upsert(KnownDevice(user_id=user.id, device_hash="abc", user_agent_snippet="Firefox"))
        assert second.id == first.id
        assert second.last_seen_at >= first.last_seen_at

    def test_get_returns_none_for_unknown(
        self,
        user_repo: SQLAlchemyUserRepository,
        known_device_repo: SQLAlchemyKnownDeviceRepository,
    ):
        user = user_repo.create(User(email="kd2@example.com", password_hash="x"))
        assert known_device_repo.get(user.id, "missing") is None

    def test_upsert_runtime_error_when_get_returns_none(
        self,
        user_repo: SQLAlchemyUserRepository,
        known_device_repo: SQLAlchemyKnownDeviceRepository,
    ):
        user = user_repo.create(User(email="kd3@example.com", password_hash="x"))
        with patch.object(known_device_repo, "get", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to upsert known_device"):
                known_device_repo.upsert(KnownDevice(user_id=user.id, device_hash="zzz", user_agent_snippet="UA"))
