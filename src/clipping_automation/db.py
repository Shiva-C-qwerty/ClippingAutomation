from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from clipping_automation.utils import utc_now_iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    source_context TEXT,
    title TEXT NOT NULL,
    description TEXT,
    author TEXT,
    source_url TEXT NOT NULL,
    media_url TEXT,
    permalink TEXT,
    created_at TEXT,
    discovered_at TEXT NOT NULL,
    duration_seconds INTEGER,
    aspect_ratio REAL,
    views INTEGER,
    upvotes INTEGER,
    comments INTEGER,
    score REAL NOT NULL DEFAULT 0,
    score_breakdown_json TEXT NOT NULL DEFAULT '{}',
    rights_status TEXT NOT NULL DEFAULT 'needs_review',
    rights_notes TEXT,
    license_hint TEXT,
    local_media_path TEXT,
    local_copied_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(score DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_rights ON candidates(rights_status);
CREATE INDEX IF NOT EXISTS idx_candidates_local_media ON candidates(local_media_path);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def initialize_database(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def upsert_candidate(conn: sqlite3.Connection, candidate: dict) -> None:
    payload = {
        "source_type": candidate["source_type"],
        "external_id": candidate["external_id"],
        "source_context": candidate.get("source_context"),
        "title": candidate.get("title") or "Untitled",
        "description": candidate.get("description"),
        "author": candidate.get("author"),
        "source_url": candidate["source_url"],
        "media_url": candidate.get("media_url"),
        "permalink": candidate.get("permalink"),
        "created_at": candidate.get("created_at"),
        "discovered_at": candidate.get("discovered_at") or utc_now_iso(),
        "duration_seconds": candidate.get("duration_seconds"),
        "aspect_ratio": candidate.get("aspect_ratio"),
        "views": candidate.get("views"),
        "upvotes": candidate.get("upvotes"),
        "comments": candidate.get("comments"),
        "score": candidate.get("score", 0),
        "score_breakdown_json": json.dumps(candidate.get("score_breakdown", {})),
        "license_hint": candidate.get("license_hint"),
        "metadata_json": json.dumps(candidate.get("metadata", {})),
    }

    conn.execute(
        """
        INSERT INTO candidates (
            source_type, external_id, source_context, title, description, author,
            source_url, media_url, permalink, created_at, discovered_at,
            duration_seconds, aspect_ratio, views, upvotes, comments,
            score, score_breakdown_json, license_hint, metadata_json
        ) VALUES (
            :source_type, :external_id, :source_context, :title, :description, :author,
            :source_url, :media_url, :permalink, :created_at, :discovered_at,
            :duration_seconds, :aspect_ratio, :views, :upvotes, :comments,
            :score, :score_breakdown_json, :license_hint, :metadata_json
        )
        ON CONFLICT(source_type, external_id) DO UPDATE SET
            source_context = excluded.source_context,
            title = excluded.title,
            description = excluded.description,
            author = excluded.author,
            source_url = excluded.source_url,
            media_url = excluded.media_url,
            permalink = excluded.permalink,
            created_at = excluded.created_at,
            discovered_at = excluded.discovered_at,
            duration_seconds = excluded.duration_seconds,
            aspect_ratio = excluded.aspect_ratio,
            views = excluded.views,
            upvotes = excluded.upvotes,
            comments = excluded.comments,
            score = excluded.score,
            score_breakdown_json = excluded.score_breakdown_json,
            license_hint = excluded.license_hint,
            metadata_json = excluded.metadata_json
        """,
        payload,
    )


def fetch_candidates(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
    source_type: str | None = None,
    rights_status: str | None = None,
    local_only: bool = False,
    usable_only: bool = False,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[object] = []

    if source_type:
        clauses.append("source_type = ?")
        params.append(source_type)
    if rights_status:
        clauses.append("rights_status = ?")
        params.append(rights_status)
    if local_only:
        clauses.append("local_media_path IS NOT NULL")
    if usable_only:
        clauses.append("(local_media_path IS NOT NULL OR media_url IS NOT NULL)")

    where_clause = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)

    cursor = conn.execute(
        f"""
        SELECT *
        FROM candidates
        {where_clause}
        ORDER BY score DESC, discovered_at DESC
        LIMIT ?
        """,
        params,
    )
    return cursor.fetchall()


def get_candidate(conn: sqlite3.Connection, candidate_id: int) -> sqlite3.Row | None:
    cursor = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    return cursor.fetchone()


def update_candidate_review(
    conn: sqlite3.Connection,
    *,
    candidate_id: int,
    rights_status: str,
    rights_notes: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE candidates
        SET rights_status = ?,
            rights_notes = ?
        WHERE id = ?
        """,
        (rights_status, rights_notes, candidate_id),
    )


def attach_local_media(
    conn: sqlite3.Connection,
    *,
    candidate_id: int,
    local_media_path: str,
) -> None:
    conn.execute(
        """
        UPDATE candidates
        SET local_media_path = ?,
            local_copied_at = ?
        WHERE id = ?
        """,
        (local_media_path, utc_now_iso(), candidate_id),
    )


def update_candidate_music_review(
    conn: sqlite3.Connection,
    *,
    candidate_id: int,
    music_status: str,
    music_notes: str | None = None,
) -> None:
    candidate = get_candidate(conn, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} was not found.")

    metadata: dict = {}
    raw_metadata = candidate["metadata_json"]
    if raw_metadata:
        try:
            metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            metadata = {}

    metadata["music_review"] = {
        "status": music_status,
        "notes": music_notes,
        "reviewed_at": utc_now_iso(),
    }

    conn.execute(
        """
        UPDATE candidates
        SET metadata_json = ?
        WHERE id = ?
        """,
        (json.dumps(metadata), candidate_id),
    )


def update_candidate_music_detection(
    conn: sqlite3.Connection,
    *,
    candidate_id: int,
    detection: dict,
) -> None:
    candidate = get_candidate(conn, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} was not found.")

    metadata: dict = {}
    raw_metadata = candidate["metadata_json"]
    if raw_metadata:
        try:
            metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            metadata = {}

    metadata["music_detection"] = detection

    conn.execute(
        """
        UPDATE candidates
        SET metadata_json = ?
        WHERE id = ?
        """,
        (json.dumps(metadata), candidate_id),
    )


def update_candidate_clip_title(
    conn: sqlite3.Connection,
    *,
    candidate_id: int,
    clip_title: str | None,
) -> None:
    candidate = get_candidate(conn, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} was not found.")

    metadata: dict = {}
    raw_metadata = candidate["metadata_json"]
    if raw_metadata:
        try:
            metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            metadata = {}

    if clip_title:
        metadata["clip_title"] = clip_title
    else:
        metadata.pop("clip_title", None)

    conn.execute(
        """
        UPDATE candidates
        SET metadata_json = ?
        WHERE id = ?
        """,
        (json.dumps(metadata), candidate_id),
    )


def delete_candidates_by_status(
    conn: sqlite3.Connection,
    *,
    rights_status: str,
) -> int:
    cursor = conn.execute(
        """
        DELETE FROM candidates
        WHERE rights_status = ?
        """,
        (rights_status,),
    )
    return int(cursor.rowcount or 0)


def archive_candidates(
    conn: sqlite3.Connection,
    *,
    candidate_ids: list[int],
    archive_note: str | None = None,
) -> int:
    if not candidate_ids:
        return 0

    placeholders = ", ".join("?" for _ in candidate_ids)
    note_prefix = "Archived after compilation"
    note_value = note_prefix if not archive_note else f"{note_prefix}: {archive_note}"
    cursor = conn.execute(
        f"""
        UPDATE candidates
        SET rights_status = 'archived',
            rights_notes = CASE
                WHEN rights_notes = ? THEN rights_notes
                WHEN rights_notes LIKE ? THEN rights_notes
                WHEN rights_notes IS NULL OR rights_notes = '' THEN ?
                ELSE rights_notes || ' | ' || ?
            END
        WHERE id IN ({placeholders})
        """,
        [note_value, f"%{note_value}%", note_value, note_value, *candidate_ids],
    )
    return int(cursor.rowcount or 0)
