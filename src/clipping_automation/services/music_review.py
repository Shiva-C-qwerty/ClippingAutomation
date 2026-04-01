from __future__ import annotations

from pathlib import Path

from clipping_automation.config import DEFAULT_DB_PATH
from clipping_automation.db import connect, update_candidate_music_review


def review_candidate_music(
    *,
    candidate_id: int,
    music_status: str,
    music_notes: str | None,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict:
    with connect(db_path) as conn:
        update_candidate_music_review(
            conn,
            candidate_id=candidate_id,
            music_status=music_status,
            music_notes=music_notes,
        )
        conn.commit()

    return {
        "candidate_id": candidate_id,
        "music_status": music_status,
        "music_notes": music_notes,
    }
