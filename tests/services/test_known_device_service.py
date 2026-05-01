from unittest.mock import MagicMock

from rentivo.models.known_device import KnownDevice
from rentivo.services.known_device_service import KnownDeviceService


def test_fingerprint_strips_ipv4_last_octet():
    a = KnownDeviceService.fingerprint("Firefox", "203.0.113.42")
    b = KnownDeviceService.fingerprint("Firefox", "203.0.113.99")
    assert a == b  # /24 grouping
    c = KnownDeviceService.fingerprint("Firefox", "203.0.114.42")
    assert a != c


def test_fingerprint_handles_non_ipv4():
    # IPv6 / "unknown" / malformed -- should not crash and should still produce a hash.
    h = KnownDeviceService.fingerprint("Firefox", "unknown")
    assert isinstance(h, str)
    assert len(h) == 64


def test_is_known_delegates_to_repo():
    repo = MagicMock()
    repo.get.return_value = KnownDevice(id=1, user_id=7, device_hash="x")
    svc = KnownDeviceService(repo)
    assert svc.is_known(7, "Firefox", "1.2.3.4") is True


def test_is_known_false_when_repo_empty():
    repo = MagicMock()
    repo.get.return_value = None
    svc = KnownDeviceService(repo)
    assert svc.is_known(7, "Firefox", "1.2.3.4") is False


def test_remember_truncates_long_user_agent():
    repo = MagicMock()
    repo.upsert.side_effect = lambda d: d
    svc = KnownDeviceService(repo)
    svc.remember(1, "U" * 1000, "1.2.3.4")
    saved = repo.upsert.call_args[0][0]
    assert len(saved.user_agent_snippet) == 255
