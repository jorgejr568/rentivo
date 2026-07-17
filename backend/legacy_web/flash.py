from __future__ import annotations

from fastapi.responses import RedirectResponse
from starlette.requests import Request


def flash(request: Request, message: str, category: str = "info") -> None:
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})


def get_flashed_messages(request: Request) -> list[dict[str, str]]:
    return request.session.pop("_messages", [])


def flash_redirect(
    request: Request,
    message: str,
    url: str,
    category: str = "danger",
) -> RedirectResponse:
    """Queue a flash message and return a 302 redirect to ``url``.

    Collapses the ``flash(...); return RedirectResponse(url, status_code=302)``
    pair that nearly every POST handler repeats. ``category`` defaults to
    ``"danger"`` because the overwhelming majority of call sites are rejection
    paths; success/info/warning sites pass it explicitly.
    """
    flash(request, message, category)
    return RedirectResponse(url, status_code=302)
