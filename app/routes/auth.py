"""Routes — Admin login/logout."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.auth import verify_password, login_user, logout_user, is_admin
from app.templating import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_admin(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    if verify_password(password):
        login_user(request)
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {
        "error": "Invalid password"
    })


@router.get("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/", status_code=303)


@router.post("/toggle-danger")
async def toggle_danger(request: Request):
    current = request.session.get("danger_mode", False)
    request.session["danger_mode"] = not current
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=303)


@router.post("/toggle-pope")
async def toggle_pope(request: Request):
    current = request.session.get("pope_mode", False)
    request.session["pope_mode"] = not current
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=303)
