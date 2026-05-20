from __future__ import annotations

from rentivo.cache.memory import MemoryKVCache


def _mk(ttl: int = 60, max_entries: int = 100, *, timer=None) -> MemoryKVCache:
    """Build a cache with the cleanup thread disabled — tests drive expiry
    via the injected timer."""
    return MemoryKVCache(
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


def test_cleanup_thread_starts_as_daemon_when_enabled():
    cache = MemoryKVCache(
        ttl_seconds=60,
        max_entries=10,
        enable_cleanup_thread=True,
        cleanup_interval_seconds=60,  # large; we don't want it to fire during the test
    )
    try:
        assert cache._cleanup_thread is not None
        assert cache._cleanup_thread.is_alive()
        assert cache._cleanup_thread.daemon is True
    finally:
        cache.close()


def test_close_signals_thread_and_joins():
    cache = MemoryKVCache(
        ttl_seconds=60,
        max_entries=10,
        enable_cleanup_thread=True,
        cleanup_interval_seconds=60,
    )
    thread = cache._cleanup_thread
    assert thread is not None
    cache.close()
    thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_cleanup_thread_expires_entries():
    """The daemon must remove entries whose TTL has elapsed even without a
    concurrent get_many call."""
    now = [1_000.0]

    def fake_timer() -> float:
        return now[0]

    cache = MemoryKVCache(
        ttl_seconds=1,
        max_entries=10,
        timer=fake_timer,
        enable_cleanup_thread=True,
        cleanup_interval_seconds=0.05,
    )
    try:
        cache.set_many({"a": "alpha"})
        # Advance the timer past the TTL, then wait long enough for the
        # daemon to wake at least once.
        now[0] += 10
        import time as _time

        for _ in range(40):  # up to ~2s wall clock
            with cache._lock:
                if "a" not in cache._cache:
                    break
            _time.sleep(0.05)
        with cache._lock:
            assert "a" not in cache._cache
    finally:
        cache.close()


def test_default_cleanup_interval_is_ttl_quarter_min_one():
    cache = MemoryKVCache(
        ttl_seconds=60,
        max_entries=10,
        enable_cleanup_thread=False,
    )
    assert cache._effective_cleanup_interval(60, None) == 15.0
    assert cache._effective_cleanup_interval(2, None) == 1.0  # floor at 1.0
    assert cache._effective_cleanup_interval(60, 5.0) == 5.0


def test_cleanup_loop_body_runs_synchronously():
    """Drive ``_cleanup_loop`` from the main thread so coverage observes the
    loop body. Python 3.14's ``sys.monitoring`` (the default coverage core)
    does not trace background threads, so the assertion in the daemon-based
    test above is not enough to cover lines 63-66.
    """
    import threading as _threading

    now = [1_000.0]

    def fake_timer() -> float:
        return now[0]

    cache = MemoryKVCache(
        ttl_seconds=1,
        max_entries=10,
        timer=fake_timer,
        enable_cleanup_thread=False,
    )
    cache.set_many({"a": "alpha"})
    now[0] += 10  # past TTL

    # Manually wire the loop's contract: a stop event plus a tiny interval.
    cache._stop_event = _threading.Event()
    # Stop the loop after a single wait cycle.
    timer = _threading.Timer(0.05, cache._stop_event.set)
    timer.start()
    try:
        cache._cleanup_loop(0.01)
    finally:
        timer.cancel()

    with cache._lock:
        assert "a" not in cache._cache
