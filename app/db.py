import logging
import time
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

log = logging.getLogger("mealgen")

_connect_args = {"check_same_thread": False} if str(settings.database_url).startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def init_db(retries: int = 30) -> None:
    """Wait for the database to accept connections, then create missing tables."""
    from app import models  # noqa: F401  (registers the models on Base.metadata)

    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except OperationalError:
            if attempt == retries:
                raise
            log.info("Database not ready yet (attempt %s/%s), retrying...", attempt, retries)
            time.sleep(1)
    Base.metadata.create_all(engine)
    _add_missing_columns()


# Columns added after the first release; create_all() doesn't alter existing tables.
_ADDED_COLUMNS = {
    "plan_entries": {"skipped": "BOOLEAN NOT NULL DEFAULT false"},
}


def _add_missing_columns() -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    log.info("Adding column %s.%s", table, name)
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
