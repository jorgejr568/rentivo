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


def test_register_login_returns_false_for_new_device():
    repo = MagicMock()
    repo.get.return_value = None
    repo.upsert.side_effect = lambda d: d
    svc = KnownDeviceService(repo)
    assert svc.register_login(1, "Firefox", "1.2.3.4") is False
    repo.upsert.assert_called_once()


def test_register_login_returns_true_for_known_device():
    repo = MagicMock()
    repo.get.return_value = KnownDevice(id=1, user_id=7, device_hash="x")
    repo.upsert.side_effect = lambda d: d
    svc = KnownDeviceService(repo)
    assert svc.register_login(7, "Firefox", "1.2.3.4") is True
    repo.upsert.assert_called_once()  # still touches last_seen


def test_register_login_truncates_long_user_agent():
    repo = MagicMock()
    repo.get.return_value = None
    repo.upsert.side_effect = lambda d: d
    svc = KnownDeviceService(repo)
    svc.register_login(1, "U" * 1000, "1.2.3.4")
    saved = repo.upsert.call_args[0][0]
    assert len(saved.user_agent_snippet) == 255


def test_register_login_uses_ipv4_24_grouping():
    repo = MagicMock()
    repo.get.return_value = None
    repo.upsert.side_effect = lambda d: d
    svc = KnownDeviceService(repo)
    svc.register_login(1, "Firefox", "203.0.113.42")
    fp_a = repo.upsert.call_args[0][0].device_hash
    repo.upsert.reset_mock()
    svc.register_login(1, "Firefox", "203.0.113.99")
    fp_b = repo.upsert.call_args[0][0].device_hash
    assert fp_a == fp_b
