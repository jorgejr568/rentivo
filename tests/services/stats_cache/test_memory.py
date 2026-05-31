from __future__ import annotations

from rentivo.services.stats_cache.memory import MemoryStatsCache


def _cache(ttl=60, max_entries=64, **kw):
    return MemoryStatsCache(ttl_seconds=ttl, max_entries=max_entries, enable_cleanup_thread=False, **kw)


def test_set_get_round_trips_same_object(sample_stats):
    cache = _cache()
    try:
        assert cache.get("k") is None
        cache.set("k", sample_stats)
        assert cache.get("k") is sample_stats
    finally:
        cache.close()


def test_clear_empties_cache(sample_stats):
    cache = _cache()
    try:
        cache.set("k", sample_stats)
        cache.clear()
        assert cache.get("k") is None
    finally:
        cache.close()


def test_entries_expire_under_a_controllable_timer(sample_stats):
    clock = {"t": 1000.0}
    cache = _cache(ttl=10, timer=lambda: clock["t"])
    try:
        cache.set("k", sample_stats)
        assert cache.get("k") is sample_stats
        clock["t"] += 11  # advance past the TTL
        assert cache.get("k") is None
    finally:
        cache.close()


def test_max_entries_evicts_oldest(sample_stats):
    cache = _cache(max_entries=2)
    try:
        cache.set("a", sample_stats)
        cache.set("b", sample_stats)
        cache.set("c", sample_stats)  # exceeds maxsize → evicts the oldest
        present = [k for k in ("a", "b", "c") if cache.get(k) is not None]
        assert len(present) == 2
    finally:
        cache.close()


def test_cleanup_thread_starts_and_stops():
    cache = MemoryStatsCache(ttl_seconds=4, max_entries=8, enable_cleanup_thread=True)
    assert cache._cleanup_thread is not None
    assert cache._cleanup_thread.is_alive()
    cache.close()
    assert cache._cleanup_thread is None


def test_effective_cleanup_interval_floors_at_one_second():
    assert MemoryStatsCache._effective_cleanup_interval(2, None) == 1.0
    assert MemoryStatsCache._effective_cleanup_interval(40, None) == 10.0
    assert MemoryStatsCache._effective_cleanup_interval(40, 3.0) == 3.0


def test_cleanup_loop_body_runs_synchronously(sample_stats):
    """Drive ``_cleanup_loop`` from the main thread so coverage observes the
    loop body (Python 3.14's default coverage core does not trace background
    threads)."""
    import threading

    now = [1000.0]
    cache = MemoryStatsCache(ttl_seconds=1, max_entries=10, timer=lambda: now[0], enable_cleanup_thread=False)
    cache.set("a", sample_stats)
    now[0] += 10  # past the TTL

    cache._stop_event = threading.Event()
    timer = threading.Timer(0.05, cache._stop_event.set)  # stop after one wait cycle
    timer.start()
    try:
        cache._cleanup_loop(0.01)
    finally:
        timer.cancel()

    with cache._lock:
        assert "a" not in cache._cache
