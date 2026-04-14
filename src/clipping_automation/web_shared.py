from __future__ import annotations

import json
from pathlib import Path

from clipping_automation.config import APPROVED_ASSETS_DIR


def metadata_for_row(row: dict) -> dict:
    if row.get("metadata") is not None:
        return row.get("metadata") or {}
    raw = row.get("metadata_json")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def effective_music_status_for_row(row: dict) -> str:
    metadata = metadata_for_row(row)
    music_review = metadata.get("music_review") or {}
    review_status = music_review.get("status")
    if review_status:
        return review_status

    legacy_risk = music_review.get("risk")
    if legacy_risk == "low":
        return "safe"
    if legacy_risk == "medium":
        return "needs_review"
    if legacy_risk == "high":
        return "unsafe"

    detection = metadata.get("music_detection") or {}
    return detection.get("status") or "unknown"


def candidate_view_model(row: dict) -> dict:
    metadata = metadata_for_row(row)
    local_media_path = row.get("local_media_path")
    local_media_url = None
    if local_media_path:
        path = Path(local_media_path)
        try:
            if path.resolve().is_relative_to(APPROVED_ASSETS_DIR.resolve()):
                local_media_url = f"/media/approved/{path.name}"
        except ValueError:
            local_media_url = None

    music_status = effective_music_status_for_row(row)
    usable_for_planning = (
        row.get("rights_status") == "approved"
        and music_status not in {"unsafe", "needs_review"}
        and bool(local_media_path or row.get("media_url"))
    )

    return {
        **row,
        "metadata": metadata,
        "music_status": music_status,
        "category": metadata.get("category") or "-",
        "source_label": metadata.get("source_label") or row.get("source_context") or "-",
        "clip_title": metadata.get("clip_title") or "",
        "music_notes": ((metadata.get("music_review") or {}).get("notes")) or "",
        "music_detected_status": ((metadata.get("music_detection") or {}).get("status")) or "",
        "music_detected_confidence": ((metadata.get("music_detection") or {}).get("confidence")),
        "dash_url": metadata.get("dash_url"),
        "local_media_url": local_media_url,
        "usable_for_planning": usable_for_planning,
    }
