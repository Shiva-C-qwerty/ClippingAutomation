from __future__ import annotations

import shutil
from pathlib import Path

from clipping_automation.config import APPROVED_ASSETS_DIR, DEFAULT_DB_PATH
from clipping_automation.db import attach_local_media, connect, get_candidate, update_candidate_review
from clipping_automation.utils import ensure_directory, slugify


def approve_candidate(
    *,
    candidate_id: int,
    rights_status: str,
    rights_notes: str | None,
    local_file: Path | None,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict:
    ensure_directory(APPROVED_ASSETS_DIR)

    with connect(db_path) as conn:
        candidate = get_candidate(conn, candidate_id)
        if candidate is None:
            raise ValueError(f"Candidate {candidate_id} was not found.")

        copied_to: Path | None = None
        if local_file:
            if not local_file.exists():
                raise FileNotFoundError(f"Local file not found: {local_file}")
            suffix = local_file.suffix or ".mp4"
            filename = f"{candidate_id:04d}_{slugify(candidate['title'])}{suffix}"
            copied_to = APPROVED_ASSETS_DIR / filename
            shutil.copy2(local_file, copied_to)
            attach_local_media(conn, candidate_id=candidate_id, local_media_path=str(copied_to))

        update_candidate_review(
            conn,
            candidate_id=candidate_id,
            rights_status=rights_status,
            rights_notes=rights_notes,
        )
        conn.commit()

    return {
        "candidate_id": candidate_id,
        "rights_status": rights_status,
        "local_media_path": str(copied_to) if copied_to else None,
    }
