
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def session_requires_confirmation(
    last_activity_at: datetime,
    now: datetime | None = None,
) -> bool:

    if last_activity_at.tzinfo is None:
        raise ValueError(
            "last_activity_at must be timezone-aware"
        )

    current_time = now or utc_now()

    timeout = timedelta(
        minutes=get_settings().session_inactivity_minutes
    )

    return current_time - last_activity_at >= timeout
