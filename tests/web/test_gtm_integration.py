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


# --- Task 5 scope: GTM snippet renders in base.html ---


class TestSnippetDisabled:
    def test_no_gtm_urls_when_disabled(self, disable_gtm, client):
        response = client.get("/login")
        assert "googletagmanager.com" not in response.text
        assert "GTM-" not in response.text
        assert "dataLayer" not in response.text
        assert "web-vitals" not in response.text
        assert "tracking.js" not in response.text

    def test_no_gtm_urls_when_disabled_on_authed_page(self, disable_gtm, auth_client):
        response = auth_client.get("/billings/")
        assert "googletagmanager.com" not in response.text
        assert "dataLayer" not in response.text

    def test_no_gtm_urls_on_landing_when_disabled(self, disable_gtm, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "googletagmanager.com" not in response.text
        assert "dataLayer" not in response.text


class TestSnippetEnabled:
    def test_loader_renders(self, enable_gtm, client):
        response = client.get("/login")
        assert "googletagmanager.com/gtm.js" in response.text
        assert "'GTM-TEST123'" in response.text

    def test_noscript_iframe_renders(self, enable_gtm, client):
        response = client.get("/login")
        assert "googletagmanager.com/ns.html?id=GTM-TEST123" in response.text

    def test_tracking_scripts_load(self, enable_gtm, client):
        response = client.get("/login")
        assert "core/js/tracking.js" in response.text
        assert "core/vendor/web-vitals.iife.js" in response.text

    def test_initial_push_anonymous(self, enable_gtm, client):
        response = client.get("/login")
        push = _extract_page_context_push(response.text)
        assert push is not None
        assert push["user_status"] == "anonymous"
        assert push["user_id_hash"] is None
        assert push["page_template"] == "login"
        assert push["page_type"] == "auth"
        assert push["locale"] == "pt-BR"

    def test_initial_push_authenticated(self, enable_gtm, auth_client):
        response = auth_client.get("/billings/")
        push = _extract_page_context_push(response.text)
        assert push is not None
        assert push["user_status"] == "authenticated"
        assert push["user_id_hash"] is not None
        assert re.fullmatch(r"[0-9a-f]{16}", push["user_id_hash"])
        assert push["page_template"] == "billing/list"
        assert push["page_section"] == "billing"

    def test_pii_absent_from_initial_push(self, enable_gtm, auth_client):
        """Security: no username, email, or raw user_id in the page_context JSON."""
        response = auth_client.get("/billings/")
        # Slice out just the inline dataLayer block
        match = re.search(r"<script>\s*window\.dataLayer.*?</script>", response.text, re.DOTALL)
        assert match is not None
        snippet = match.group(0)
        assert "testuser" not in snippet
        assert "test@pix.com" not in snippet

    def test_initial_push_includes_request_id(self, enable_gtm, client):
        response = client.get("/login")
        rid = response.headers.get("X-Request-ID")
        assert rid
        push = _extract_page_context_push(response.text)
        assert push["request_id"] == rid

    def test_initial_push_environment(self, enable_gtm, client):
        response = client.get("/login")
        push = _extract_page_context_push(response.text)
        assert push["environment"] == "production"

    def test_landing_page_renders_gtm(self, enable_gtm, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "googletagmanager.com/gtm.js" in response.text
        assert "'GTM-TEST123'" in response.text
        assert "googletagmanager.com/ns.html?id=GTM-TEST123" in response.text
        assert "core/js/tracking.js" in response.text
        push = _extract_page_context_push(response.text)
        assert push is not None
        assert push["page_template"] == "landing"
        assert push["page_type"] == "landing"


# Additionally, add the two Task-4-originally-planned tests that belong here:


class TestRenderInjectionDeferred:
    def test_render_injects_gtm_initial_push_when_enabled(self, enable_gtm, client):
        response = client.get("/login")
        assert response.status_code == 200
        push = _extract_page_context_push(response.text)
        assert push is not None, f"No page_context push found in:\n{response.text[:500]}"
        assert push["event"] == "page_context"
        assert push["user_status"] == "anonymous"
        assert push["page_template"] == "login"

    def test_render_skips_gtm_when_disabled(self, disable_gtm, client):
        response = client.get("/login")
        assert "dataLayer.push" not in response.text
        assert "page_context" not in response.text
