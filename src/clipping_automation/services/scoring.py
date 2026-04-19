from __future__ import annotations

from clipping_automation.utils import clamp, compute_age_days, log_scaled


def _keyword_score(text: str, keywords: list[str]) -> float:
    lowered = text.lower()
    hits = sum(1 for keyword in keywords if keyword.lower() in lowered)
    if not keywords:
        return 0.5
    return clamp(hits / min(max(len(keywords), 1), 4))


def _duration_score(duration_seconds: int | None, minimum: int, maximum: int) -> float:
    if duration_seconds is None:
        return 0.45
    if minimum <= duration_seconds <= maximum:
        return 1.0
    if duration_seconds < minimum:
        return clamp(duration_seconds / max(minimum, 1), 0.05, 1.0)

    hard_max = max(maximum * 2, maximum + 5)
    if duration_seconds >= hard_max:
        return 0.05
    return clamp(1.0 - ((duration_seconds - maximum) / max(hard_max - maximum, 1)), 0.05, 1.0)


def _vertical_score(aspect_ratio: float | None) -> float:
    if aspect_ratio is None:
        return 0.5
    if 0.50 <= aspect_ratio <= 0.62:
        return 1.0
    if 0.63 <= aspect_ratio <= 1.05:
        return 0.55
    return 0.25


def _rights_score(license_hint: str | None, source_type: str) -> float:
    if not license_hint:
        return 0.2
    lowered = license_hint.lower()
    if "creative commons" in lowered or "creator-approved" in lowered:
        return 0.95
    if source_type == "reddit":
        return 0.15
    return 0.25


def compute_score(
    *,
    source_type: str,
    title: str,
    description: str,
    created_at: str | None,
    duration_seconds: int | None,
    aspect_ratio: float | None,
    views: int | None,
    upvotes: int | None,
    comments: int | None,
    license_hint: str | None,
    scoring_config: dict | None,
) -> tuple[float, dict[str, float]]:
    scoring_config = scoring_config or {}
    minimum = int(scoring_config.get("preferred_duration_min", 5))
    maximum = int(scoring_config.get("preferred_duration_max", 10))
    max_age_days = int(scoring_config.get("max_candidate_age_days", 21))
    keywords = list(scoring_config.get("keywords", []))

    text = f"{title} {description}".strip()
    keyword_score = _keyword_score(text, keywords)
    duration_score = _duration_score(duration_seconds, minimum, maximum)
    vertical_score = _vertical_score(aspect_ratio)
    age_days = compute_age_days(created_at)
    freshness_score = 0.45 if age_days is None else clamp(1.0 - (age_days / max_age_days))
    rights_score = _rights_score(license_hint, source_type)

    if source_type == "youtube":
        engagement_signal = (views or 0) + ((comments or 0) * 50)
        engagement_score = log_scaled(engagement_signal, 12.0)
    else:
        engagement_signal = (upvotes or 0) + ((comments or 0) * 10)
        engagement_score = log_scaled(engagement_signal, 8.0)

    score = (
        0.35 * engagement_score
        + 0.25 * duration_score
        + 0.15 * freshness_score
        + 0.10 * keyword_score
        + 0.05 * vertical_score
        + 0.10 * rights_score
    ) * 100.0

    breakdown = {
        "engagement": round(engagement_score, 4),
        "duration": round(duration_score, 4),
        "freshness": round(freshness_score, 4),
        "keyword": round(keyword_score, 4),
        "vertical": round(vertical_score, 4),
        "rights": round(rights_score, 4),
    }
    return round(score, 2), breakdown
