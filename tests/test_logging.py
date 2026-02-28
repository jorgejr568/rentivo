import logging
from unittest.mock import patch

from rentivo.logging import configure_logging


class TestConfigureLogging:
    def test_json_format(self):
        """Cover log_json=True branch (lines 20-22)."""
        with patch("rentivo.logging.settings") as mock_settings:
            mock_settings.log_level = "INFO"
            mock_settings.log_json = True
            configure_logging()

        root = logging.getLogger()
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        from pythonjsonlogger.json import JsonFormatter

        assert isinstance(handler.formatter, JsonFormatter)
