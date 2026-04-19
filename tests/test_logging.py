"""Tests for the structlog + stdlib pipeline in rentivo.logging."""

from __future__ import annotations

import json
import logging
from io import StringIO
from unittest.mock import patch

import pytest
import structlog

from rentivo.logging import configure_logging


def _capture(mode_json: bool, *, cli: bool = False) -> StringIO:
    """Configure logging in the requested mode with stderr redirected to a buffer."""
    buf = StringIO()
    with patch("rentivo.logging.settings") as mock_settings:
        mock_settings.log_level = "DEBUG"
        mock_settings.log_json = mode_json
        with patch("rentivo.logging.sys") as mock_sys:
            mock_sys.stderr = buf
            mock_sys.stderr.isatty = lambda: False
            configure_logging(cli=cli)
    return buf


class TestConfigureLogging:
    def teardown_method(self):
        # Reset contextvars between tests
        structlog.contextvars.clear_contextvars()

    def test_json_mode_emits_json(self):
        buf = _capture(mode_json=True)
        log = structlog.get_logger("t")
        log.info("hello", foo=1)
        line = buf.getvalue().strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["event"] == "hello"
        assert parsed["foo"] == 1
        assert parsed["level"] == "info"
        assert "timestamp" in parsed

    def test_text_mode_uses_console_renderer(self):
        buf = _capture(mode_json=False)
        log = structlog.get_logger("t")
        log.info("hello", foo=1)
        output = buf.getvalue()
        assert "hello" in output
        # Should not be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(output.splitlines()[-1])

    def test_cli_mode_forces_console_even_when_json(self):
        buf = _capture(mode_json=True, cli=True)
        log = structlog.get_logger("t")
        log.info("hello")
        with pytest.raises(json.JSONDecodeError):
            json.loads(buf.getvalue().splitlines()[-1])

    def test_foreign_stdlib_log_passes_through(self):
        buf = _capture(mode_json=True)
        logging.getLogger("some.foreign").warning("foo bar")
        line = buf.getvalue().strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["event"] == "foo bar"
        assert parsed["level"] == "warning"

    def test_reconfigure_idempotent(self):
        _capture(mode_json=True)
        _capture(mode_json=True)
        root = logging.getLogger()
        assert len(root.handlers) == 1

    def test_uvicorn_access_suppressed_to_warning(self):
        _capture(mode_json=False)
        assert logging.getLogger("uvicorn.access").level == logging.WARNING

    def test_contextvars_merged_into_event(self):
        buf = _capture(mode_json=True)
        structlog.contextvars.bind_contextvars(request_id="rid-123", user_id=42)
        structlog.get_logger("t").info("inside")
        structlog.contextvars.clear_contextvars()
        line = buf.getvalue().strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["request_id"] == "rid-123"
        assert parsed["user_id"] == 42
