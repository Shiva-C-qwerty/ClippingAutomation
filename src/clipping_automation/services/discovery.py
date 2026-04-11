from __future__ import annotations

import json
from pathlib import Path

from clipping_automation.config import DEFAULT_DB_PATH, DEFAULT_EXPORT_DIR, load_source_config
from clipping_automation.db import connect, fetch_candidates, initialize_database, upsert_candidate
from clipping_automation.sources.reddit import discover_reddit_candidates
from clipping_automation.sources.youtube import discover_youtube_candidates
from clipping_automation.utils import ensure_directory


def run_discovery(config_path: Path, db_path: Path = DEFAULT_DB_PATH) -> dict:
    config = load_source_config(config_path)
    initialize_database(db_path)
    scoring_config = config.get("scoring", {})

    errors: list[str] = []

    try:
        reddit_candidates = discover_reddit_candidates(config, scoring_config=scoring_config)
    except Exception as exc:  # noqa: BLE001
        reddit_candidates = []
        errors.append(f"reddit: {exc}")

    try:
        youtube_candidates = discover_youtube_candidates(config, scoring_config=scoring_config)
    except Exception as exc:  # noqa: BLE001
        youtube_candidates = []
        errors.append(f"youtube: {exc}")

    all_candidates = reddit_candidates + youtube_candidates

    with connect(db_path) as conn:
        for candidate in all_candidates:
            upsert_candidate(conn, candidate)
        conn.commit()

        review_candidates = [
            dict(row)
            for row in fetch_candidates(
                conn,
                limit=100,
                rights_status="needs_review",
            )
        ]

    export_path = ensure_directory(DEFAULT_EXPORT_DIR) / "review_candidates.json"
    export_path.write_text(json.dumps(review_candidates, indent=2), encoding="utf-8")

    return {
        "total_discovered": len(all_candidates),
        "reddit_discovered": len(reddit_candidates),
        "youtube_discovered": len(youtube_candidates),
        "snapshot_path": export_path,
        "errors": errors,
    }
