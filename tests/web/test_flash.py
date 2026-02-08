from unittest.mock import MagicMock

from web.flash import flash, get_flashed_messages


class TestFlash:
    def _mock_request(self):
        request = MagicMock()
        request.session = {}
        return request

    def test_flash_adds_message(self):
        request = self._mock_request()
        flash(request, "Hello", "info")
        assert request.session["_messages"] == [
            {"message": "Hello", "category": "info"}
        ]

    def test_flash_appends_multiple(self):
        request = self._mock_request()
        flash(request, "First", "info")
        flash(request, "Second", "danger")
        assert len(request.session["_messages"]) == 2

    def test_get_flashed_messages_returns_and_clears(self):
        request = self._mock_request()
        flash(request, "Test", "success")
        messages = get_flashed_messages(request)
        assert len(messages) == 1
        assert messages[0]["message"] == "Test"
        # Should be cleared
        assert get_flashed_messages(request) == []

    def test_get_flashed_messages_empty(self):
        request = self._mock_request()
        assert get_flashed_messages(request) == []
