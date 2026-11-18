import base64
import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request
from markupsafe import Markup

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_CSRF_KEY = "csrf_token"
_FLASH_KEY = "_flashes"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def csrf_token(request: Request) -> str:
    token = request.session.get(_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[_CSRF_KEY] = token
    return token


def csrf_input(request: Request) -> Markup:
    return Markup('<input type="hidden" name="csrf_token" value="{}">').format(csrf_token(request))


async def csrf_protect(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    form = await request.form()
    sent = form.get("csrf_token")
    expected = request.session.get(_CSRF_KEY)
    if not expected or not isinstance(sent, str) or not hmac.compare_digest(sent, expected):
        raise HTTPException(400, "This form has expired. Reload the page and try again.")


def flash(request: Request, message: str, category: str = "info") -> None:
    request.session[_FLASH_KEY] = [*request.session.get(_FLASH_KEY, []), [category, message]]


def pop_flashes(request: Request) -> list[list[str]]:
    return request.session.pop(_FLASH_KEY, [])


def safe_next(url: str | None) -> str:
    """Only allow local redirects after login."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return "/"
