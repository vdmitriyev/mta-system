"""Times: stored in UTC (without time zone), shown and entered in local time.

Local time is the time zone of the server (TZ, e.g. Europe/Berlin).
"""

from datetime import UTC, datetime

DATE_TIME = "%d.%m.%Y %H:%M"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def to_local(value: datetime | None) -> datetime | None:
    """UTC from the database -> local time"""

    if value is None:
        return None
    return value.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)


def to_utc(value: datetime | None) -> datetime | None:
    """Local time (e.g. of a form) -> UTC for the database"""

    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None)


def local_text(value: datetime | None, fmt: str = DATE_TIME) -> str:
    """UTC from the database as local time text; empty for None"""

    local = to_local(value)
    return local.strftime(fmt) if local else ""
