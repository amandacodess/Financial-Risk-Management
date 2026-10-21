from datetime import date

from fastapi import HTTPException

from services.analytics import parse_month


def month_query(value: str | None, default: date | None = None) -> date | None:
    """Parse an optional ?month=YYYY-MM query value, 422 on anything malformed."""
    if value is None:
        return default
    try:
        return parse_month(value)
    except ValueError:
        raise HTTPException(422, "month must be in YYYY-MM format") from None
