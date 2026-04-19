"""Tests for /robots.txt, /sitemap.xml, and landing-page SEO metadata."""

from __future__ import annotations

from unittest.mock import patch


class TestRobotsTxt:
    def test_serves_plain_text(self, client):
        r = client.get("/robots.txt")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")

    def test_allows_public_paths_and_disallows_private(self, client):
        body = client.get("/robots.txt").text
        assert "User-agent: *" in body
        for allowed in ("/", "/login", "/signup"):
            assert f"Allow: {allowed}" in body
        for blocked in ("/billings/", "/organizations/", "/security", "/change-password"):
            assert f"Disallow: {blocked}" in body

    def test_lists_sitemap(self, client):
        body = client.get("/robots.txt").text
        assert "Sitemap:" in body
        assert "/sitemap.xml" in body

    def test_welcomes_ai_crawlers(self, client):
        """AI/LLM bots are explicitly allowed."""
        body = client.get("/robots.txt").text
        for ua in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"):
            assert f"User-agent: {ua}" in body

    def test_no_unauthenticated_redirect(self, client):
        """robots.txt must bypass AuthMiddleware."""
        r = client.get("/robots.txt", follow_redirects=False)
        assert r.status_code == 200

    def test_uses_public_url_setting_when_set(self, client):
        with patch("web.routes.seo.settings") as mock_settings:
            mock_settings.public_url = "https://rentivo.app/"
            body = client.get("/robots.txt").text
        assert "Sitemap: https://rentivo.app/sitemap.xml" in body


class TestSitemapXml:
    def test_serves_xml(self, client):
        r = client.get("/sitemap.xml")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/xml")

    def test_lists_public_pages(self, client):
        body = client.get("/sitemap.xml").text
        assert "<?xml" in body
        assert "<urlset" in body
        for path in ("/", "/login", "/signup"):
            assert f"{path}</loc>" in body

    def test_does_not_list_private_pages(self, client):
        body = client.get("/sitemap.xml").text
        for blocked in ("/billings/", "/organizations/", "/security", "/change-password"):
            assert blocked not in body

    def test_uses_public_url_setting_when_set(self, client):
        with patch("web.routes.seo.settings") as mock_settings:
            mock_settings.public_url = "https://rentivo.app"
            body = client.get("/sitemap.xml").text
        assert "<loc>https://rentivo.app/</loc>" in body
        assert "<loc>https://rentivo.app/login</loc>" in body

    def test_no_unauthenticated_redirect(self, client):
        r = client.get("/sitemap.xml", follow_redirects=False)
        assert r.status_code == 200


class TestLandingPageSeo:
    def test_has_meta_description_and_og_tags(self, client):
        body = client.get("/").text
        assert '<meta name="description"' in body
        assert '<meta property="og:title"' in body
        assert '<meta property="og:image"' in body
        assert '<meta name="twitter:card"' in body

    def test_has_canonical_link(self, client):
        body = client.get("/").text
        assert '<link rel="canonical"' in body

    def test_has_structured_data(self, client):
        body = client.get("/").text
        assert "application/ld+json" in body
        assert '"SoftwareApplication"' in body

    def test_public_url_propagates_to_robots(self, client):
        """Template globals bind at import time; verify the setting flows through robots.txt."""
        with patch("web.routes.seo.settings") as mock_settings:
            mock_settings.public_url = "https://rentivo.app"
            body = client.get("/robots.txt").text
        assert "rentivo.app" in body
