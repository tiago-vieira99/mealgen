import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.security import csrf_protect, flash, hash_password, safe_next, verify_password
from app.web import redirect, render

router = APIRouter(dependencies=[Depends(csrf_protect)])

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,50}$")
# Hash used when the username doesn't exist, so the response time doesn't reveal it.
_DUMMY_HASH = hash_password("dummy-password")


def _normalize(username: str) -> str:
    return username.strip().lower()


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    if request.session.get("user_id"):
        return redirect("/")
    return render(request, "auth/login.html", next=safe_next(next))


@router.post("/login")
def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == _normalize(username)))
    valid = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not user or not valid:
        return render(
            request,
            "auth/login.html",
            status_code=400,
            error="Wrong username or password.",
            username=username,
            next=safe_next(next),
        )
    request.session.clear()
    request.session["user_id"] = user.id
    return redirect(safe_next(next))


@router.get("/register")
def register_form(request: Request):
    if not settings.allow_registration:
        raise HTTPException(404, "Sign-ups are disabled.")
    return render(request, "auth/register.html")


@router.post("/register")
def register(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    db: Session = Depends(get_db),
):
    if not settings.allow_registration:
        raise HTTPException(404, "Sign-ups are disabled.")

    username = _normalize(username)
    error = None
    if not USERNAME_RE.match(username):
        error = "Usernames must be 3–50 characters: letters, numbers, '.', '_' or '-'."
    elif len(password) < 8:
        error = "Passwords must be at least 8 characters."
    elif len(password) > 256:
        error = "That password is too long."
    elif password != password_confirm:
        error = "Passwords don't match."
    elif db.scalar(select(User.id).where(User.username == username)):
        error = "That username is already taken."
    if error:
        return render(request, "auth/register.html", status_code=400, error=error, username=username)

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    request.session.clear()
    request.session["user_id"] = user.id
    flash(request, "Welcome! Start by adding a few meals you like to cook.", "success")
    return redirect("/meals")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")
