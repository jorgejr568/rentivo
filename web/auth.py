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

    user_service = get_user_service(request)
    user = user_service.authenticate(str(username), str(password))

    if user is None:
        return render(request, "login.html", {"error": "Usuário ou senha inválidos."})

    request.session["user"] = user.username
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
    username = request.session.get("user", "")
    user = user_service.authenticate(username, current_password)

    if user is None:
        return render(request, "change_password.html", {"error": "Senha atual incorreta."})

    user_service.change_password(username, new_password)
    flash(request, "Senha alterada com sucesso!", "success")
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
