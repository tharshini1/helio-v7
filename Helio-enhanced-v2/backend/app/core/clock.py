"""Single source of 'now' for appointment validation and expiry.

Uses APP_TIMEZONE (default Asia/Kolkata) so a UTC host such as Render still
validates against hospital-local time. Returns a naive datetime.
"""
import os
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


def now() -> datetime:
    name = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
    try:
        return datetime.now(ZoneInfo(name)).replace(tzinfo=None)
    except Exception:
        return datetime.now()
