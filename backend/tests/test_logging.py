"""Tests for the structlog + stdlib pipeline in rentivo.logging."""

from __future__ import annotations

import json
import logging
from io import StringIO
from unittest.mock import patch

import pytest
import structlog
from structlog.stdlib import ProcessorFormatter

from rentivo.logging import _shared_processors, configure_logging

API_KEY = "rntv-v1-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789_-abc"


def _capture(mode_json: bool, *, cli: bool = False) -> StringIO:
    """Configure logging in the requested mode with stderr redirected to a buffer."""
    buf = StringIO()
    with patch("rentivo.logging.settings") as mock_settings:
        mock_settings.log_level = "DEBUG"
        mock_settings.log_json = mode_json
        mock_settings.log_cloudwatch_enabled = False
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

    def test_logs_carry_trace_id_inside_a_span(self):
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        from rentivo.observability import span, tracing

        tracing._reset_for_tests()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
        tracing.configure_tracing(provider=provider)
        try:
            buf = _capture(mode_json=True)
            with span("op"):
                structlog.get_logger("t").info("inside-span")
            parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
            assert parsed["event"] == "inside-span"
            assert len(parsed["trace_id"]) == 32
            assert len(parsed["span_id"]) == 16
        finally:
            tracing._reset_for_tests()

    def test_structlog_recursively_redacts_credentials(self):
        buf = _capture(mode_json=True)
        structlog.get_logger("t").info(
            "credential_event",
            payload={"password": "plain-password", "items": [{"accessToken": "plain-token"}]},
            api_key_uuid="01SAFEKEYUUID",
            request_id="request-123",
        )

        parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert parsed["payload"] == {
            "password": "[REDACTED]",
            "items": [{"accessToken": "[REDACTED]"}],
        }
        assert parsed["api_key_uuid"] == "01SAFEKEYUUID"
        assert parsed["request_id"] == "request-123"

    def test_structlog_exception_does_not_render_api_key(self):
        buf = _capture(mode_json=True)
        try:
            raise RuntimeError(f"upstream rejected {API_KEY}")
        except RuntimeError:
            structlog.get_logger("t").exception("request_failed")

        output = buf.getvalue()
        assert API_KEY not in output
        assert "[REDACTED]" in output

    @pytest.mark.parametrize("mode_json", [True, False])
    def test_structlog_exception_redacts_embedded_credentials(self, mode_json):
        buf = _capture(mode_json=mode_json)
        try:
            raise RuntimeError(
                "OIDC failed id_token=oidc-secret recovery_code=recovery-secret Authorization: Bearer bearer-secret"
            )
        except RuntimeError:
            structlog.get_logger("t").exception("request_failed")

        output = buf.getvalue()
        assert "oidc-secret" not in output
        assert "recovery-secret" not in output
        assert "bearer-secret" not in output
        assert "[REDACTED]" in output

    @pytest.mark.parametrize("mode_json", [True, False])
    @pytest.mark.parametrize("logger_kind", ["structlog", "stdlib"])
    def test_exception_redacts_opaque_cookie_headers(self, mode_json, logger_kind):
        buf = _capture(mode_json=mode_json)
        try:
            raise RuntimeError("Cookie: __Host-session=opaque-session-secret; theme=dark")
        except RuntimeError:
            if logger_kind == "structlog":
                structlog.get_logger("t").exception("request_failed")
            else:
                logging.getLogger("foreign").exception("request_failed")

        output = buf.getvalue()
        assert "opaque-session-secret" not in output
        assert "[REDACTED]" in output

    def test_stdlib_log_recursively_redacts_extra_payload(self):
        buf = _capture(mode_json=True)
        logging.getLogger("foreign").warning(
            "foreign_event",
            extra={"payload": {"recoveryCode": "recovery-secret"}},
        )

        parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert parsed["payload"] == {"recoveryCode": "[REDACTED]"}

    @pytest.mark.parametrize("mode_json", [True, False])
    def test_stdlib_exception_redacts_embedded_credentials(self, mode_json):
        buf = _capture(mode_json=mode_json)
        try:
            raise RuntimeError("client_secret=client-secret Cookie: session_token=session-secret")
        except RuntimeError:
            logging.getLogger("foreign").exception("provider_failed")

        output = buf.getvalue()
        assert "client-secret" not in output
        assert "session-secret" not in output
        assert "[REDACTED]" in output

    def test_cloudwatch_formatter_redacts_embedded_credentials(self):
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(
            ProcessorFormatter(
                keep_exc_info=False,
                foreign_pre_chain=_shared_processors(json_output=True),
                processors=[ProcessorFormatter.remove_processors_meta, structlog.processors.JSONRenderer()],
            )
        )
        root = logging.getLogger()
        for existing in root.handlers[:]:
            existing.close()
        root.handlers[:] = [handler]
        root.setLevel(logging.INFO)

        try:
            raise RuntimeError("id_token=oidc-secret Authorization: Bearer bearer-secret")
        except RuntimeError:
            logging.getLogger("foreign").exception("provider_failed")

        output = buf.getvalue()
        assert "oidc-secret" not in output
        assert "bearer-secret" not in output
        assert "[REDACTED]" in output


def _cw_settings(monkeypatch_target, *, stream="", access_key="", secret=""):
    """Patch rentivo.logging.settings for the cloudwatch handler tests."""
    monkeypatch_target.log_cloudwatch_region = "us-east-1"
    monkeypatch_target.log_cloudwatch_group = "rentivo"
    monkeypatch_target.log_cloudwatch_stream = stream
    monkeypatch_target.log_cloudwatch_access_key_id = access_key
    monkeypatch_target.log_cloudwatch_secret_access_key = secret


class TestCloudWatchHandler:
    def teardown_method(self):
        logging.getLogger().handlers.clear()

    def test_handler_uses_explicit_creds_and_default_stream(self):
        from rentivo.logging import _cloudwatch_handler

        with (
            patch("rentivo.logging.settings") as s,
            patch("boto3.client") as mock_client,
            patch("watchtower.CloudWatchLogHandler") as mock_handler,
        ):
            _cw_settings(s, stream="", access_key="AKIA", secret="shh")
            _cloudwatch_handler()

        kwargs = mock_client.call_args.kwargs
        assert kwargs["aws_access_key_id"] == "AKIA"
        assert mock_handler.call_args.kwargs["log_stream_name"] == "{machine_name}/{program_name}"
        assert mock_handler.call_args.kwargs["log_group_name"] == "rentivo"

    def test_handler_falls_back_to_chain_with_custom_stream(self):
        from rentivo.logging import _cloudwatch_handler

        with (
            patch("rentivo.logging.settings") as s,
            patch("boto3.client") as mock_client,
            patch("watchtower.CloudWatchLogHandler") as mock_handler,
        ):
            _cw_settings(s, stream="web-1", access_key="", secret="")
            _cloudwatch_handler()

        assert "aws_access_key_id" not in mock_client.call_args.kwargs
        assert mock_handler.call_args.kwargs["log_stream_name"] == "web-1"

    def test_configure_adds_cloudwatch_handler_when_enabled(self):
        import logging as _logging

        with (
            patch("rentivo.logging.settings") as s,
            patch("rentivo.logging.sys") as mock_sys,
            patch("rentivo.logging._cloudwatch_handler", return_value=_logging.NullHandler()) as builder,
        ):
            s.log_level = "INFO"
            s.log_json = True
            s.log_cloudwatch_enabled = True
            mock_sys.stderr = StringIO()
            mock_sys.stderr.isatty = lambda: False
            configure_logging()

        builder.assert_called_once()
        # stdout StreamHandler + the CloudWatch handler.
        assert len(_logging.getLogger().handlers) == 2


class TestCloudWatchSettings:
    def test_defaults_off(self):
        from rentivo.settings import Settings

        s = Settings(_env_file=None)
        assert s.log_cloudwatch_enabled is False
        assert s.log_cloudwatch_group == "rentivo"

    def test_region_required_when_enabled(self):
        from rentivo.settings import Settings

        with pytest.raises(ValueError, match="LOG_CLOUDWATCH_REGION"):
            Settings(_env_file=None, log_cloudwatch_enabled=True, log_cloudwatch_region="")
