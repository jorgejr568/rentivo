"""Integration tests for GTM snippet rendering and dataLayer context."""

from __future__ import annotations

import json
import re

import pytest

from web.app import templates


@pytest.fixture
def enable_gtm(monkeypatch):
    """Enable GTM for a test and restore afterwards. Patches both settings and template globals."""
    monkeypatch.setattr("rentivo.settings.settings.gtm_container_id", "GTM-TEST123")
    monkeypatch.setattr("rentivo.settings.settings.environment", "production")
    monkeypatch.setattr("rentivo.settings.settings.secret_key", "test-secret")
    monkeypatch.setitem(templates.env.globals, "gtm_container_id", "GTM-TEST123")
    monkeypatch.setitem(templates.env.globals, "environment", "production")
    yield "GTM-TEST123"


@pytest.fixture
def disable_gtm(monkeypatch):
    monkeypatch.setattr("rentivo.settings.settings.gtm_container_id", "")
    monkeypatch.setitem(templates.env.globals, "gtm_container_id", "")
    yield


def _extract_page_context_push(html: str) -> dict | None:
    """Find the first dataLayer.push({...}) with event=page_context."""
    matches = re.findall(r"dataLayer\.push\((\{.*?\})\)", html, re.DOTALL)
    for m in matches:
        try:
            data = json.loads(m)
        except json.JSONDecodeError:
            continue
        if data.get("event") == "page_context":
            return data
    return None


# --- Task 4 scope: render() injects context, template globals set ---


class TestRenderInjection:
    def test_template_globals_registered(self):
        """Verify gtm_container_id and environment are template globals."""
        assert "gtm_container_id" in templates.env.globals
        assert "environment" in templates.env.globals
