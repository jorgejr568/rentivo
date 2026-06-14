from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any, Coroutine

from rentivo.jobs.temporal.config import TemporalConfig

if TYPE_CHECKING:
    from temporalio.client import Client


class AsyncBridge:
    """Run coroutines from synchronous code on a dedicated background loop.

    The Temporal client is async; ``JobService.enqueue`` (and the web request
    path) is sync. One daemon thread owns one event loop for the process; every
    enqueue submits its coroutine via ``run_coroutine_threadsafe`` and blocks for
    the result. Thread-safe across the request thread pool.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="temporal-bridge", daemon=True)
        self._thread.start()
        self._closed = False

    def run(self, coro: Coroutine[Any, Any, Any]) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._loop.close()


async def build_client(cfg: TemporalConfig) -> "Client":
    from temporalio.client import Client

    return await Client.connect(cfg.host, namespace=cfg.namespace, tls=cfg.tls)
