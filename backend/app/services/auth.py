"""Optional password protection for the dashboard and API.

Set DASHBOARD_PASSWORD to turn it on. Browsers log in once and get a signed
session cookie; scripts can send `Authorization: Bearer <password>` instead.
"""

import hashlib
import hmac
import os
import secrets
import time
from http.cookies import SimpleCookie


COOKIE_NAME = "sp_session"
SESSION_SECONDS = int(os.getenv("SESSION_HOURS", "12")) * 3600

# Static files and the login endpoints must load before signing in.
PUBLIC_PATHS = {
    "/", "/index.html", "/app.css", "/app.js", "/screens.css",
    "/arrival.html", "/arrival.js", "/plate-test.html", "/plate-test.js",
    "/health", "/auth/login", "/auth/status", "/auth/logout",
}


class Auth:
    def __init__(self, password=None, secret=None):
        self.password = password if password is not None else os.getenv("DASHBOARD_PASSWORD") or None
        # A per-process secret means restarting the server logs everyone out
        # unless SESSION_SECRET is set.
        self.secret = (secret or os.getenv("SESSION_SECRET") or secrets.token_hex(32)).encode()

    @property
    def enabled(self):
        return bool(self.password)

    def check_password(self, attempt):
        return self.enabled and hmac.compare_digest(
            str(attempt).encode(), self.password.encode()
        )

    def make_token(self):
        expires = str(int(time.time()) + SESSION_SECONDS)
        signature = hmac.new(self.secret, expires.encode(), hashlib.sha256).hexdigest()
        return f"{expires}.{signature}"

    def valid_token(self, token):
        try:
            expires, signature = token.split(".", 1)
        except (AttributeError, ValueError):
            return False
        expected = hmac.new(self.secret, expires.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected) and int(expires) > time.time()

    def request_allowed(self, headers):
        """headers: dict of lower-case header name -> value."""
        if not self.enabled:
            return True

        authorization = headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
            if self.check_password(supplied) or self.valid_token(supplied):
                return True

        cookie = SimpleCookie()
        try:
            cookie.load(headers.get("cookie", ""))
        except Exception:
            return False
        morsel = cookie.get(COOKIE_NAME)
        return bool(morsel and self.valid_token(morsel.value))


class AuthMiddleware:
    """Pure ASGI so it also guards the WebSocket and the MJPEG stream."""

    def __init__(self, app, auth):
        self.app = app
        self.auth = auth

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not self.auth.enabled:
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if path in PUBLIC_PATHS or self.auth.request_allowed(headers):
            return await self.app(scope, receive, send)

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401})
            return

        body = b'{"detail":"Please sign in."}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
