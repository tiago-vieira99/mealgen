"""Shared web helpers: templates, auth dependency and redirects."""

from datetime import timedelta

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import dates
from app.config import BASE_DIR, settings
from app.db import get_db
from app.icons import icon
from app.models import MEAL_TYPE_LABELS, User
from app.security import csrf_input, pop_flashes

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals.update(
    icon=icon,
    csrf_input=csrf_input,
    pop_flashes=pop_flashes,
    meal_types=MEAL_TYPE_LABELS,
    fmt_day=dates.fmt_day,
    fmt_weekday=dates.fmt_weekday,
    fmt_short=dates.fmt_short,
    fmt_week=dates.fmt_week,
    week_label=dates.week_label,
    weekdays=dates.WEEKDAYS,
    allow_registration=lambda: settings.allow_registration,
)
templates.env.filters["days"] = lambda n: timedelta(days=n)


class LoginRequired(Exception):
    def __init__(self, next_url: str) -> None:
        self.next_url = next_url


def render(request: Request, template: str, status_code: int = 200, **context):
    context.setdefault("user", getattr(request.state, "user", None))
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def absolute_url(request: Request, path: str) -> str:
    base = settings.base_url or str(request.base_url).rstrip("/")
    return base + path


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        request.session.pop("user_id", None)
        raise LoginRequired(request.url.path)
    request.state.user = user
    return user


async def form_data(request: Request):
    """Raw form, for endpoints with dynamic field names (keeps the endpoint itself sync)."""
    return await request.form()
