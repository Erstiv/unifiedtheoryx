"""Simple admin authentication — single-user, session-based."""
import hashlib
import secrets
from fastapi import Request, Depends
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

ADMIN_USERNAME = "elliot"
# Password hash — default: "gutx2026" — change via set_password()
_DEFAULT_HASH = hashlib.sha256("gutx2026".encode()).hexdigest()
_password_hash = _DEFAULT_HASH


def get_password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str) -> bool:
    return get_password_hash(password) == _password_hash


def is_admin(request: Request) -> bool:
    """Check if the current request is from an authenticated admin."""
    return request.session.get("is_admin", False)


def require_admin(request: Request):
    """Dependency that redirects to login if not admin."""
    if not is_admin(request):
        return None
    return True


def login_user(request: Request):
    """Mark the session as authenticated."""
    request.session["is_admin"] = True
    request.session["user"] = ADMIN_USERNAME


def logout_user(request: Request):
    """Clear the session."""
    request.session.clear()
