from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from web.deps import get_user_service, render
from web.flash import flash

router = APIRouter()


@router.get("/login")
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/", status_code=302)
    return render(request, "login.html")


@router.post("/login")
async def login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user_service = get_user_service()
    user = user_service.authenticate(str(username), str(password))

    if user is None:
        return render(request, "login.html", {"error": "Usuário ou senha inválidos."})

    request.session["user"] = user.username
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
