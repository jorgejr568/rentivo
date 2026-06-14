import asyncio
from unittest.mock import AsyncMock, patch

from rentivo.jobs.temporal.client import AsyncBridge, build_client
from rentivo.jobs.temporal.config import TemporalConfig


def test_async_bridge_runs_a_coroutine_and_returns_result():
    bridge = AsyncBridge()
    try:

        async def work():
            await asyncio.sleep(0)
            return 21 * 2

        assert bridge.run(work()) == 42
    finally:
        bridge.close()


def test_async_bridge_close_is_idempotent():
    bridge = AsyncBridge()
    bridge.close()
    bridge.close()  # no raise


def test_build_client_connects_with_config():
    cfg = TemporalConfig(host="h:7233", namespace="ns", task_queue="q", tls=True, activity_timeout_seconds=600)
    with patch("temporalio.client.Client.connect", new=AsyncMock(return_value="CLIENT")) as connect:
        bridge = AsyncBridge()
        try:
            client = bridge.run(build_client(cfg))
        finally:
            bridge.close()
    assert client == "CLIENT"
    connect.assert_awaited_once_with("h:7233", namespace="ns", tls=True)
