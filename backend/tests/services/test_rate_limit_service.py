from datetime import UTC, datetime
from unittest.mock import MagicMock

from rentivo.services.rate_limit_service import RateLimitService


def test_reserve_hashes_the_identity_before_shared_persistence() -> None:
    repository = MagicMock()
    repository.reserve.return_value = True
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    service = RateLimitService(repository=repository, now=lambda: now)

    assert service.reserve(action="login", identity="203.0.113.42", limit=5, window_seconds=60)

    call = repository.reserve.call_args
    assert call.kwargs["action"] == "login"
    assert call.kwargs["identity_hash"] != b"203.0.113.42"
    assert len(call.kwargs["identity_hash"]) == 32
    assert call.kwargs["limit"] == 5
    assert call.kwargs["window_seconds"] == 60
    assert call.kwargs["now"] == now


def test_clear_uses_the_same_nonreversible_identity_hash() -> None:
    repository = MagicMock()
    service = RateLimitService(repository=repository)

    service.clear(action="login", identity="203.0.113.42")

    call = repository.clear.call_args
    assert call.kwargs["action"] == "login"
    assert len(call.kwargs["identity_hash"]) == 32


def test_default_clock_is_timezone_aware() -> None:
    repository = MagicMock()
    repository.reserve.return_value = True
    service = RateLimitService(repository=repository)

    service.reserve(action="login", identity="client", limit=1, window_seconds=1)

    assert repository.reserve.call_args.kwargs["now"].utcoffset() is not None


def test_cleanup_expired_is_bounded_and_uses_the_shared_clock() -> None:
    repository = MagicMock()
    repository.delete_expired.return_value = 3
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    service = RateLimitService(repository=repository, now=lambda: now)

    assert service.cleanup_expired(limit=25) == 3
    repository.delete_expired.assert_called_once_with(cutoff=now, limit=25)
