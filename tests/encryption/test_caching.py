from __future__ import annotations

from unittest.mock import MagicMock

from rentivo.cache.null import NullKVCache as NullDecryptCache
from rentivo.encryption.base import EncryptionBackend
from rentivo.encryption.caching import CachingEncryptionBackend


class _StubBackend(EncryptionBackend):
    """Deterministic backend for wrapper tests."""

    def __init__(self) -> None:
        self.encrypt_calls = 0
        self.decrypt_calls: list[str] = []
        self.decrypt_many_calls: list[list[str]] = []

    def encrypt(self, plaintext: str) -> str:
        self.encrypt_calls += 1
        return "enc:" + plaintext

    def decrypt(self, value: str) -> str:
        self.decrypt_calls.append(value)
        return value.removeprefix("enc:")

    def decrypt_many(self, values: list[str]) -> list[str]:
        self.decrypt_many_calls.append(list(values))
        return [v.removeprefix("enc:") for v in values]

    def is_encrypted(self, value: str) -> bool:
        return value.startswith("enc:")


def test_encrypt_bypasses_cache():
    inner = _StubBackend()
    cache = MagicMock(spec=NullDecryptCache)
    wrapper = CachingEncryptionBackend(inner=inner, cache=cache)

    assert wrapper.encrypt("hello") == "enc:hello"
    cache.get_many.assert_not_called()
    cache.set_many.assert_not_called()


def test_is_encrypted_bypasses_cache():
    inner = _StubBackend()
    cache = MagicMock(spec=NullDecryptCache)
    wrapper = CachingEncryptionBackend(inner=inner, cache=cache)

    assert wrapper.is_encrypted("enc:x") is True
    assert wrapper.is_encrypted("x") is False
    cache.get_many.assert_not_called()


def test_decrypt_hit_skips_inner():
    inner = _StubBackend()
    cache = MagicMock()
    cache.get_many.return_value = {"enc:x": "x-cached"}
    wrapper = CachingEncryptionBackend(inner=inner, cache=cache)

    assert wrapper.decrypt("enc:x") == "x-cached"
    assert inner.decrypt_calls == []
    cache.set_many.assert_not_called()


def test_decrypt_miss_calls_inner_and_stores():
    inner = _StubBackend()
    cache = MagicMock()
    cache.get_many.return_value = {}
    wrapper = CachingEncryptionBackend(inner=inner, cache=cache)

    assert wrapper.decrypt("enc:x") == "x"
    assert inner.decrypt_calls == ["enc:x"]
    cache.set_many.assert_called_once_with({"enc:x": "x"})


def test_decrypt_many_empty_short_circuits():
    inner = _StubBackend()
    cache = MagicMock()
    wrapper = CachingEncryptionBackend(inner=inner, cache=cache)

    assert wrapper.decrypt_many([]) == []
    cache.get_many.assert_not_called()
    assert inner.decrypt_many_calls == []


def test_decrypt_many_full_hit_skips_inner():
    inner = _StubBackend()
    cache = MagicMock()
    cache.get_many.return_value = {"enc:a": "a", "enc:b": "b"}
    wrapper = CachingEncryptionBackend(inner=inner, cache=cache)

    assert wrapper.decrypt_many(["enc:a", "enc:b"]) == ["a", "b"]
    assert inner.decrypt_many_calls == []
    cache.set_many.assert_not_called()


def test_decrypt_many_partial_hit_preserves_order_and_dedupes_misses():
    inner = _StubBackend()
    cache = MagicMock()
    # "enc:b" is cached; "enc:a" and "enc:c" miss; "enc:a" appears twice.
    cache.get_many.return_value = {"enc:b": "B-cached"}
    wrapper = CachingEncryptionBackend(inner=inner, cache=cache)

    result = wrapper.decrypt_many(["enc:a", "enc:b", "enc:a", "enc:c"])

    assert result == ["a", "B-cached", "a", "c"]
    # Inner must be called with the de-duplicated misses, in first-seen order.
    assert inner.decrypt_many_calls == [["enc:a", "enc:c"]]
    cache.set_many.assert_called_once_with({"enc:a": "a", "enc:c": "c"})


def test_decrypt_many_does_not_store_when_no_misses():
    inner = _StubBackend()
    cache = MagicMock()
    cache.get_many.return_value = {"enc:a": "A"}
    wrapper = CachingEncryptionBackend(inner=inner, cache=cache)

    wrapper.decrypt_many(["enc:a"])
    cache.set_many.assert_not_called()
