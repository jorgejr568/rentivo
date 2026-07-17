"""SEO endpoints: robots.txt and sitemap.xml.

Search-engine crawlers AND AI/LLM crawlers are explicitly welcome. The only
paths we disallow are authenticated app routes (user data) — never the public
marketing surface.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from starlette.responses import Response

from rentivo.settings import settings

router = APIRouter()

PUBLIC_PATHS: tuple[str, ...] = ("/", "/login", "/signup")

# Authenticated app routes — private user data, not for crawlers.
DISALLOWED_PATHS: tuple[str, ...] = (
    "/billings/",
    "/organizations/",
    "/invites/",
    "/themes/",
    "/security",
    "/change-password",
    "/logout",
    "/mfa-verify",
)

# AI/LLM crawlers we explicitly want to welcome. Listed individually because
# some operators publish opt-out controls (Google-Extended, Applebot-Extended)
# separate from the main crawler, and being explicit makes intent obvious.
AI_CRAWLERS: tuple[str, ...] = (
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "Claude-Web",
    "anthropic-ai",
    "PerplexityBot",
    "Perplexity-User",
    "Google-Extended",
    "Applebot-Extended",
    "Bytespider",
    "CCBot",
    "cohere-ai",
    "Meta-ExternalAgent",
    "Meta-ExternalFetcher",
    "Amazonbot",
    "DuckAssistBot",
    "Diffbot",
    "YouBot",
)


def _base_url(request: Request) -> str:
    """Resolve the canonical origin — settings.public_url if set, else the request origin."""
    if settings.public_url:
        return settings.public_url.rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}"


def _rules_block(user_agent: str) -> list[str]:
    lines = [f"User-agent: {user_agent}"]
    lines += [f"Allow: {path}" for path in PUBLIC_PATHS]
    lines += [f"Disallow: {path}" for path in DISALLOWED_PATHS]
    return lines


@router.get("/robots.txt")
async def robots_txt(request: Request) -> Response:
    base = _base_url(request)
    blocks: list[list[str]] = [_rules_block("*")]
    for agent in AI_CRAWLERS:
        blocks.append(_rules_block(agent))
    body = "\n\n".join("\n".join(block) for block in blocks)
    body += f"\n\nSitemap: {base}/sitemap.xml\n"
    return Response(content=body, media_type="text/plain")


@router.get("/sitemap.xml")
async def sitemap_xml(request: Request) -> Response:
    base = _base_url(request)
    lastmod = datetime.now(timezone.utc).date().isoformat()
    entries = []
    for path in PUBLIC_PATHS:
        priority = "1.0" if path == "/" else "0.7"
        entries.append(
            "  <url>\n"
            f"    <loc>{base}{path}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>monthly</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(entries) + "\n</urlset>\n"
    )
    return Response(content=body, media_type="application/xml")
