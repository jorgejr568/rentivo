from __future__ import annotations

from datetime import datetime, timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request
from sqlalchemy import text
from starlette.responses import Response

from rentivo import db
from rentivo.api.errors import ProblemException, problem
from rentivo.origins import parse_public_origin as _parse_public_origin
from rentivo.settings import settings

router = APIRouter()

PUBLIC_PATHS: tuple[str, ...] = ("/", "/login", "/signup")
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


def _public_origin(request: Request) -> str:
    if settings.public_url:
        configured_origin = _parse_public_origin(settings.public_url, allow_localhost=False)
        if configured_origin is None:
            raise ProblemException(
                problem(
                    status=500,
                    code="invalid_public_origin",
                    title="Configuração inválida",
                    detail="A origem pública configurada é inválida.",
                )
            )
        return configured_origin
    if settings.environment == "production":
        raise ProblemException(
            problem(
                status=500,
                code="public_origin_not_configured",
                title="Configuração inválida",
                detail="A origem pública precisa ser configurada em produção.",
            )
        )
    request_origin = _parse_public_origin(f"{request.url.scheme}://{request.url.netloc}", allow_localhost=True)
    if request_origin is None:
        raise ProblemException.bad_request("invalid_public_origin", "A origem pública da requisição é inválida.")
    return request_origin


def _rules_block(user_agent: str) -> list[str]:
    return [
        f"User-agent: {user_agent}",
        *(f"Allow: {path}" for path in PUBLIC_PATHS),
        *(f"Disallow: {path}" for path in DISALLOWED_PATHS),
    ]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/v1/ready")
async def ready() -> dict[str, str]:
    try:
        with db.get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        raise ProblemException(
            problem(
                status=503,
                code="not_ready",
                title="Serviço indisponível",
                detail="O banco de dados não está disponível.",
            )
        ) from None
    return {"status": "ready"}


@router.get("/robots.txt")
async def robots_txt(request: Request) -> Response:
    blocks = [_rules_block("*"), *(_rules_block(agent) for agent in AI_CRAWLERS)]
    body = "\n\n".join("\n".join(block) for block in blocks)
    body += f"\n\nSitemap: {_public_origin(request)}/sitemap.xml\n"
    return Response(content=body, media_type="text/plain")


@router.get("/sitemap.xml")
async def sitemap_xml(request: Request) -> Response:
    base = _public_origin(request)
    lastmod = datetime.now(timezone.utc).date().isoformat()
    entries = []
    for path in PUBLIC_PATHS:
        priority = "1.0" if path == "/" else "0.7"
        entries.append(
            "  <url>\n"
            f"    <loc>{escape(f'{base}{path}')}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            "    <changefreq>monthly</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(entries) + "\n</urlset>\n"
    )
    return Response(content=body, media_type="application/xml")
