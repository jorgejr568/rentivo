from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from web.deps import get_user_service, render
from web.flash import flash

logger = logging.getLogger(__name__)

router = APIRouter()

# Simple in-memory rate limiter for login attempts
_login_attempts: dict[str, list[float]] = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60


def _is_rate_limited(ip: str) -> bool:
    """Check if an IP is rate-limited. Returns True if locked out."""
    now = time.monotonic()
    attempts = _login_attempts.get(ip, [])
    # Remove attempts older than lockout window
    attempts = [t for t in attempts if now - t < _LOCKOUT_SECONDS]
    _login_attempts[ip] = attempts
    return len(attempts) >= _MAX_ATTEMPTS


def _record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt for rate limiting."""
    now = time.monotonic()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _LOCKOUT_SECONDS]
    attempts.append(now)
    _login_attempts[ip] = attempts


def _clear_attempts(ip: str) -> None:
    """Clear failed attempts after successful login."""
    _login_attempts.pop(ip, None)


@router.get("/signup")
async def signup_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=302)
    return render(request, "signup.html")


@router.post("/signup")
async def signup(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    username = str(form.get("username", "")).strip()
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", ""))
    confirm_password = str(form.get("confirm_password", ""))

    if not username or not email or not password:
        return render(request, "signup.html", {"error": "Preencha todos os campos."})

    if password != confirm_password:
        return render(request, "signup.html", {"error": "As senhas não coincidem."})

    user_service = get_user_service(request)
    try:
        user = user_service.register_user(username, email, password)
    except ValueError:
        return render(request, "signup.html", {"error": "Nome de usuário já existe."})

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    logger.info("User %s signed up", user.username)
    return RedirectResponse("/", status_code=302)


@router.get("/login")
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=302)
    return render(request, "login.html")


@router.post("/login")
async def login(request: Request):
    client_ip = request.client.host if request.client else "unknown"

    if _is_rate_limited(client_ip):
        logger.warning("Rate-limited login attempt from %s", client_ip)
        return render(request, "login.html", {
            "error": "Muitas tentativas. Aguarde um momento antes de tentar novamente.",
        })

    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user_service = get_user_service(request)
    user = user_service.authenticate(str(username), str(password))

    if user is None:
        _record_failed_attempt(client_ip)
        logger.warning("Failed login attempt for username=%s from %s", username, client_ip)
        return render(request, "login.html", {"error": "Usuário ou senha inválidos."})

    _clear_attempts(client_ip)
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    logger.info("User %s logged in", user.username)
    return RedirectResponse("/", status_code=302)


@router.get("/change-password")
async def change_password_page(request: Request):
    return render(request, "change_password.html")


@router.post("/change-password")
async def change_password(request: Request):
    form = await request.form()
    current_password = str(form.get("current_password", ""))
    new_password = str(form.get("new_password", ""))
    confirm_password = str(form.get("confirm_password", ""))

    if not current_password or not new_password:
        return render(request, "change_password.html", {"error": "Preencha todos os campos."})

    if new_password != confirm_password:
        return render(request, "change_password.html", {"error": "As senhas não coincidem."})

    user_service = get_user_service(request)
    username = request.session.get("username", "")
    user = user_service.authenticate(username, current_password)

    if user is None:
        return render(request, "change_password.html", {"error": "Senha atual incorreta."})

    user_service.change_password(username, new_password)
    flash(request, "Senha alterada com sucesso!", "success")
    return RedirectResponse("/", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
