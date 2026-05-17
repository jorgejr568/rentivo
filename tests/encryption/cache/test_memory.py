from __future__ import annotations

from rentivo.encryption.cache.memory import MemoryDecryptCache


def _mk(ttl: int = 60, max_entries: int = 100, *, timer=None) -> MemoryDecryptCache:
    """Build a cache with the cleanup thread disabled — tests drive expiry
    via the injected timer."""
    return MemoryDecryptCache(
        ttl_seconds=ttl,
        max_entries=max_entries,
        timer=timer,
        enable_cleanup_thread=False,
    )


def test_get_many_returns_only_present_keys():
    cache = _mk()
    cache.set_many({"a": "alpha", "b": "beta"})
    assert cache.get_many(["a", "c"]) == {"a": "alpha"}


def test_get_many_with_empty_input_returns_empty_dict():
    cache = _mk()
    cache.set_many({"a": "alpha"})
    assert cache.get_many([]) == {}


def test_set_many_with_empty_input_is_no_op():
    cache = _mk()
    cache.set_many({})  # must not raise


def test_close_is_a_no_op_without_cleanup_thread():
    cache = _mk()
    cache.close()  # must not raise


def test_entries_expire_after_ttl():
    now = [1_000.0]

    def fake_timer() -> float:
        return now[0]

    cache = _mk(ttl=10, timer=fake_timer)
    cache.set_many({"a": "alpha"})
    assert cache.get_many(["a"]) == {"a": "alpha"}

    now[0] += 5
    assert cache.get_many(["a"]) == {"a": "alpha"}  # still fresh

    now[0] += 10
    assert cache.get_many(["a"]) == {}  # expired


def test_max_entries_bounds_residency():
    cache = _mk(max_entries=2)
    cache.set_many({"a": "alpha", "b": "beta", "c": "gamma"})
    # The oldest insert ("a") must have been evicted to make room for "c".
    result = cache.get_many(["a", "b", "c"])
    assert "a" not in result
    assert result["b"] == "beta"
    assert result["c"] == "gamma"


def test_thread_safe_under_concurrent_access():
    """Smoke test: many threads reading + writing must not raise."""
    from concurrent.futures import ThreadPoolExecutor

    cache = _mk()

    def worker(i: int) -> None:
        key = f"k{i % 8}"
        cache.set_many({key: f"v{i}"})
        cache.get_many([key])

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(200)))
