from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def days_ago_iso(days: int) -> str:
    return (utc_now() - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def slugify(value: str, max_length: int = 64) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    if not value:
        return "item"
    return value[:max_length].strip("-") or "item"


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def safe_int(value: object | None) -> int | None:
    if value in (None, "", False):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_iso8601_duration(value: str | None) -> int | None:
    if not value:
        return None

    pattern = re.compile(
        r"^P"
        r"(?:(?P<days>\d+)D)?"
        r"(?:T"
        r"(?:(?P<hours>\d+)H)?"
        r"(?:(?P<minutes>\d+)M)?"
        r"(?:(?P<seconds>\d+)S)?"
        r")?$"
    )
    match = pattern.match(value)
    if not match:
        return None

    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def compute_age_days(created_at: str | None) -> float | None:
    created = parse_datetime(created_at)
    if created is None:
        return None
    delta = utc_now() - created.astimezone(UTC)
    return max(delta.total_seconds() / 86400.0, 0.0)


def log_scaled(value: int | float | None, divisor: float) -> float:
    if not value or value <= 0:
        return 0.0
    return clamp(math.log1p(value) / divisor)


def truncate(value: str | None, length: int) -> str:
    if not value:
        return ""
    return value if len(value) <= length else value[: length - 3].rstrip() + "..."


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
