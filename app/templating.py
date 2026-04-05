"""Shared Jinja2 template instance with admin context injection."""
from starlette.templating import Jinja2Templates

_base = Jinja2Templates(directory="app/templates")
_orig = _base.TemplateResponse


def _inject_admin(request, name, context=None, **kwargs):
    if context is None:
        context = {}
    context["is_admin"] = request.session.get("is_admin", False) if hasattr(request, "session") else False
    return _orig(request, name, context, **kwargs)

_base.TemplateResponse = _inject_admin
templates = _base
