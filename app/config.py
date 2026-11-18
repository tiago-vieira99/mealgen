import logging
import os
import secrets
from pathlib import Path

from sqlalchemy.engine import URL

log = logging.getLogger("mealgen")

BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _database_url() -> str | URL:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    # Built from parts so that passwords with special characters don't need URL-escaping.
    return URL.create(
        "postgresql+psycopg",
        username=os.environ.get("POSTGRES_USER", "mealgen"),
        password=os.environ.get("POSTGRES_PASSWORD", "mealgen"),
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "mealgen"),
    )


class Settings:
    def __init__(self) -> None:
        self.database_url = _database_url()
        self.secret_key = os.environ.get("SECRET_KEY", "")
        if not self.secret_key:
            log.warning("SECRET_KEY not set: using a random key, sessions will not survive restarts.")
            self.secret_key = secrets.token_urlsafe(48)
        self.base_url = os.environ.get("BASE_URL", "").rstrip("/")
        self.cookie_secure = _bool("COOKIE_SECURE", False)
        self.allow_registration = _bool("ALLOW_REGISTRATION", True)
        self.timezone = os.environ.get("APP_TIMEZONE", "Europe/Lisbon")
        self.font_dir = os.environ.get("FONT_DIR", str(BASE_DIR / "static" / "fonts"))


settings = Settings()
