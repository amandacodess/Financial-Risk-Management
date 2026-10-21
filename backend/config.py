"""Settings read once from the environment. Nothing here is ever logged."""

import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from zoneinfo import ZoneInfo

from fastapi import Depends


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    # Supabase → Project Settings → Database → Connection string (session pooler).
    # It contains the database password, so it stays server-side only.
    database_url: str
    # Comma-separated browser origins allowed to call the API.
    cors_origins: list[str]
    # "This month" is decided in this timezone, not the server's (often UTC).
    timezone: ZoneInfo
    # Off to freeze a deployment (every write, including sign-ups, returns 403).
    allow_writes: bool
    # Risk thresholds, as a percentage of a category's monthly budget.
    budget_warning_pct: Decimal
    budget_exceeded_pct: Decimal
    # How long a login lasts before the user must sign in again.
    session_days: int


@lru_cache
def get_config() -> Config:
    return Config(
        database_url=os.getenv("DATABASE_URL", ""),
        cors_origins=[
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if o.strip()
        ],
        timezone=ZoneInfo(os.getenv("APP_TZ", "Asia/Kolkata")),
        allow_writes=_flag("ALLOW_WRITES", True),
        budget_warning_pct=Decimal(os.getenv("BUDGET_WARNING_PCT", "80")),
        budget_exceeded_pct=Decimal(os.getenv("BUDGET_EXCEEDED_PCT", "100")),
        session_days=int(os.getenv("SESSION_DAYS", "7")),
    )


def get_today(config: Config = Depends(get_config)) -> date:
    """Today's date in APP_TZ. A dependency so tests can pin the clock."""
    return datetime.now(config.timezone).date()
