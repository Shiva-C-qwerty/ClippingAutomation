from __future__ import annotations

import json
from pathlib import Path

from clipping_automation.config import DEFAULT_DB_PATH
from clipping_automation.db import archive_candidates, connect


def archive_candidates_from_plan(
    *,
    plan_path: Path,
    db_path: Path = DEFAULT_DB_PATH,
    note: str | None = None,
) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    candidate_ids = [
        int(clip["candidate_id"])
        for clip in plan.get("clips", [])
        if clip.get("candidate_id") is not None
    ]

    with connect(db_path) as conn:
        archived_count = archive_candidates(
            conn,
            candidate_ids=candidate_ids,
            archive_note=note or plan.get("name"),
        )
        conn.commit()

    return {
        "plan_path": str(plan_path),
        "candidate_ids": candidate_ids,
        "archived_count": archived_count,
    }
