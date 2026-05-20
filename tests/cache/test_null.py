from __future__ import annotations

from rentivo.cache.null import NullKVCache


def test_get_many_returns_empty_dict():
    cache = NullKVCache()
    assert cache.get_many(["a", "b"]) == {}


def test_get_many_with_empty_input_returns_empty_dict():
    cache = NullKVCache()
    assert cache.get_many([]) == {}


def test_set_many_is_a_no_op():
    cache = NullKVCache()
    cache.set_many({"a": "alpha"})  # must not raise


def test_close_is_a_no_op():
    cache = NullKVCache()
    cache.close()  # must not raise
