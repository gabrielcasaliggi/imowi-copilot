"""Cookies HttpOnly para JWT de consola y portal (dual con Bearer)."""

from __future__ import annotations

from fastapi import Request, Response

from app.config import AUTH_TOKEN_HOURS, PORTAL_TOKEN_HOURS, es_produccion

CONSOLE_COOKIE = "ops_console_token"
PORTAL_COOKIE = "ops_portal_token"


def _secure(request: Request | None = None) -> bool:
    if es_produccion():
        return True
    if request is None:
        return False
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto == "https":
        return True
    return (request.url.scheme or "").lower() == "https"


def _base_kwargs(request: Request | None, *, max_age: int) -> dict:
    return {
        "httponly": True,
        "secure": _secure(request),
        "samesite": "lax",
        "path": "/api",
        "max_age": max_age,
    }


def set_console_cookie(response: Response, token: str, *, request: Request | None = None) -> None:
    response.set_cookie(
        CONSOLE_COOKIE,
        token,
        **_base_kwargs(request, max_age=int(AUTH_TOKEN_HOURS * 3600)),
    )


def clear_console_cookie(response: Response) -> None:
    response.delete_cookie(CONSOLE_COOKIE, path="/api")


def set_portal_cookie(response: Response, token: str, *, request: Request | None = None) -> None:
    response.set_cookie(
        PORTAL_COOKIE,
        token,
        **_base_kwargs(request, max_age=int(PORTAL_TOKEN_HOURS * 3600)),
    )


def clear_portal_cookie(response: Response) -> None:
    response.delete_cookie(PORTAL_COOKIE, path="/api")


def console_token_from_request(request: Request, bearer: str | None) -> str | None:
    raw = (bearer or "").strip()
    if raw:
        return raw[7:].strip() if raw.lower().startswith("bearer ") else raw
    cookie = (request.cookies.get(CONSOLE_COOKIE) or "").strip()
    return cookie or None


def portal_token_from_request(request: Request, authorization: str | None) -> str | None:
    raw = (authorization or "").strip()
    if raw:
        return raw[7:].strip() if raw.lower().startswith("bearer ") else raw
    cookie = (request.cookies.get(PORTAL_COOKIE) or "").strip()
    return cookie or None
