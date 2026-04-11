from __future__ import annotations

import argparse
import json
from pathlib import Path

from clipping_automation.config import DEFAULT_CONFIG_PATH, DEFAULT_DB_PATH, bootstrap_workspace
from clipping_automation.db import connect, delete_candidates_by_status, fetch_candidates, initialize_database
from clipping_automation.services.approval import approve_candidate
from clipping_automation.services.archive import archive_candidates_from_plan
from clipping_automation.services.discovery import run_discovery
from clipping_automation.services.music_detection import scan_candidates_for_music
from clipping_automation.services.music_review import review_candidate_music
from clipping_automation.services.render_plan import create_compilation_plan, run_render
from clipping_automation.services.upload import upload_from_plan
from clipping_automation.utils import truncate


def _metadata_for_row(row: dict) -> dict:
    if not row.get("metadata_json"):
        return {}
    try:
        return json.loads(row["metadata_json"])
    except json.JSONDecodeError:
        return {}


def _effective_music_status_for_row(row: dict) -> str:
    metadata = row.get("metadata") or _metadata_for_row(row)
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


def _print_candidates(rows: list[dict]) -> None:
    if not rows:
        print("No candidates found.")
        return

    header = (
        f"{'ID':<5} {'SRC':<8} {'STATUS':<14} {'MUSIC':<8} "
        f"{'CAT':<10} {'FROM':<24} {'SCORE':<8} {'DUR':<6} TITLE"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        duration = row["duration_seconds"] if row["duration_seconds"] is not None else "-"
        metadata = row.get("metadata") or _metadata_for_row(row)
        category = metadata.get("category") or "-"
        source_label = metadata.get("source_label") or row.get("source_context") or "-"
        music_status = _effective_music_status_for_row(row)
        print(
            f"{row['id']:<5} "
            f"{row['source_type']:<8} "
            f"{row['rights_status']:<14} "
            f"{truncate(music_status, 8):<8} "
            f"{truncate(category, 10):<10} "
            f"{truncate(source_label, 24):<24} "
            f"{row['score']:<8.2f} "
            f"{str(duration):<6} "
            f"{truncate(row['title'], 60)}"
        )
        print(f"      LINK  {row.get('source_url') or '-'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Funny clip discovery and Shorts workflow.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create workspace folders, config, and the SQLite database.")

    discover = subparsers.add_parser("discover", help="Fetch candidate metadata from configured sources.")
    discover.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    discover.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    list_cmd = subparsers.add_parser("list", help="List stored candidates.")
    list_cmd.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    list_cmd.add_argument("--source", choices=["reddit", "youtube"])
    list_cmd.add_argument("--status", choices=["needs_review", "approved", "rejected", "archived"])
    list_cmd.add_argument("--music-status", choices=["unknown", "safe", "needs_review", "unsafe", "no_audio", "scan_failed"])
    list_cmd.add_argument("--local-only", action="store_true")
    list_cmd.add_argument("--limit", type=int, default=20)

    flush = subparsers.add_parser("flush", help="Delete candidates by review status.")
    flush.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    flush.add_argument(
        "--status",
        choices=["needs_review"],
        default="needs_review",
        help="Only `needs_review` is flushable right now.",
    )

    scan_music = subparsers.add_parser("scan-music", help="Automatically scan clips and flag likely music presence.")
    scan_music.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    scan_music.add_argument("--candidate", type=int)
    scan_music.add_argument("--source", choices=["reddit", "youtube"])
    scan_music.add_argument("--status", choices=["needs_review", "approved", "rejected", "archived"])
    scan_music.add_argument("--limit", type=int, default=20)
    scan_music.add_argument(
        "--download-remote",
        action="store_true",
        help="Temporarily download direct remote media for scanning when no local file exists.",
    )

    approve = subparsers.add_parser("approve", help="Approve or reject a candidate and optionally attach a local file.")
    approve.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    approve.add_argument("--candidate", type=int, required=True)
    approve.add_argument("--status", choices=["approved", "rejected", "needs_review", "archived"], default="approved")
    approve.add_argument("--notes", help="Rights or review notes.")
    approve.add_argument("--file", type=Path, help="Local clip file to copy into data/assets/approved.")
    approve.add_argument("--clip-title", help="Short overlay title to show with the ranked clip in the final render.")

    archive = subparsers.add_parser("archive-plan", help="Archive the clips used in a completed plan so they are not reused.")
    archive.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    archive.add_argument("--plan", type=Path, required=True)
    archive.add_argument("--note", help="Extra note to append while archiving.")

    music_review = subparsers.add_parser("music-review", help="Flag a candidate for music risk before approval.")
    music_review.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    music_review.add_argument("--candidate", type=int, required=True)
    music_review.add_argument("--status", choices=["safe", "needs_review", "unsafe"], required=True)
    music_review.add_argument("--notes", help="Notes about detected or suspected music.")

    plan = subparsers.add_parser("plan", help="Create a compilation plan and FFmpeg render script.")
    plan.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    plan.add_argument("--style", choices=["top5", "compilation"], default="top5")
    plan.add_argument("--count", type=int, default=5)
    plan.add_argument("--name", help="Output name without extension.")
    plan.add_argument("--max-clip-duration", type=int, default=18)
    plan.add_argument("--intro", type=Path, help="Local intro clip to prepend.")
    plan.add_argument("--outro", type=Path, help="Local outro clip to append.")
    plan.add_argument(
        "--download-approved",
        action="store_true",
        help="Temporarily download approved clips that have direct remote media URLs.",
    )

    render = subparsers.add_parser("render", help="Show or execute the generated FFmpeg render script.")
    render.add_argument("--plan", type=Path, required=True)
    render.add_argument("--execute", action="store_true")

    upload = subparsers.add_parser("upload", help="Upload a rendered compilation using the YouTube Data API.")
    upload.add_argument("--plan", type=Path, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        paths = bootstrap_workspace()
        initialize_database(paths["db_path"])
        print("Workspace initialized.")
        print(f"Config: {paths['config_path']}")
        print(f"Database: {paths['db_path']}")
        print("Next: edit config/sources.toml and run `clipbot discover`.")
        return 0

    if args.command == "discover":
        bootstrap_workspace()
        summary = run_discovery(config_path=args.config, db_path=args.db)
        print(f"Discovery complete. Total candidates: {summary['total_discovered']}")
        print(f"Reddit: {summary['reddit_discovered']}")
        print(f"YouTube: {summary['youtube_discovered']}")
        print(f"Snapshot: {summary['snapshot_path']}")
        if summary["errors"]:
            print("Warnings:")
            for error in summary["errors"]:
                print(f"- {error}")
        return 0

    if args.command == "list":
        bootstrap_workspace()
        initialize_database(args.db)
        with connect(args.db) as conn:
            rows = [
                dict(row)
                for row in fetch_candidates(
                    conn,
                    limit=args.limit,
                    source_type=args.source,
                    rights_status=args.status,
                    local_only=args.local_only,
                )
            ]
        for row in rows:
            row["metadata"] = _metadata_for_row(row)
        if args.music_status:
            rows = [row for row in rows if _effective_music_status_for_row(row) == args.music_status]
        _print_candidates(rows)
        return 0

    if args.command == "flush":
        bootstrap_workspace()
        initialize_database(args.db)
        with connect(args.db) as conn:
            deleted = delete_candidates_by_status(conn, rights_status=args.status)
            conn.commit()
        print(f"Deleted candidates with status `{args.status}`: {deleted}")
        return 0

    if args.command == "scan-music":
        bootstrap_workspace()
        initialize_database(args.db)
        summary = scan_candidates_for_music(
            db_path=args.db,
            candidate_id=args.candidate,
            source_type=args.source,
            rights_status=args.status,
            limit=args.limit,
            allow_remote_media=args.download_remote,
        )
        print(f"Music scan complete. Scanned: {summary['scanned']}")
        print(f"Skipped: {summary['skipped']}")
        for result in summary["results"]:
            if result["status"] == "skipped":
                print(f"- Candidate {result['candidate_id']}: skipped ({result['reason']})")
            elif result["status"] == "scan_failed":
                print(f"- Candidate {result['candidate_id']}: scan_failed ({result['reason']})")
            else:
                print(
                    f"- Candidate {result['candidate_id']}: {result['status']}"
                    f" (confidence {result['confidence']})"
                )
        return 0

    if args.command == "approve":
        bootstrap_workspace()
        initialize_database(args.db)
        result = approve_candidate(
            candidate_id=args.candidate,
            rights_status=args.status,
            rights_notes=args.notes,
            local_file=args.file,
            clip_title=args.clip_title,
            db_path=args.db,
        )
        print(f"Candidate {result['candidate_id']} updated to {result['rights_status']}.")
        if result["local_media_path"]:
            print(f"Copied media to: {result['local_media_path']}")
        if result["clip_title"]:
            print(f"Clip title: {result['clip_title']}")
        return 0

    if args.command == "music-review":
        bootstrap_workspace()
        initialize_database(args.db)
        result = review_candidate_music(
            candidate_id=args.candidate,
            music_status=args.status,
            music_notes=args.notes,
            db_path=args.db,
        )
        print(f"Candidate {result['candidate_id']} music review set to: {result['music_status']}.")
        if result["music_notes"]:
            print(f"Notes: {result['music_notes']}")
        return 0

    if args.command == "plan":
        bootstrap_workspace()
        initialize_database(args.db)
        plan = create_compilation_plan(
            db_path=args.db,
            style=args.style,
            count=args.count,
            name=args.name,
            max_clip_duration=args.max_clip_duration,
            intro_path=args.intro,
            outro_path=args.outro,
            allow_remote_media=args.download_approved,
        )
        print(f"Plan: {plan['render']['plan_path']}")
        print(f"Render script: {plan['render']['render_script_path']}")
        print(f"Output video: {plan['render']['output_video_path']}")
        print(f"Planned duration: {plan['render']['planned_total_duration_seconds']}s / 180s")
        return 0

    if args.command == "render":
        result = run_render(plan_path=args.plan, execute=args.execute)
        print(f"Plan: {result['plan_path']}")
        print(f"Render script: {result['render_script_path']}")
        if result["executed"]:
            print(f"Rendered video: {result['output_video_path']}")
            print("Temporary downloaded clips were cleaned up after render.")
        else:
            print("Render script ready. Re-run with --execute after installing FFmpeg.")
        return 0

    if args.command == "archive-plan":
        bootstrap_workspace()
        initialize_database(args.db)
        result = archive_candidates_from_plan(
            plan_path=args.plan,
            db_path=args.db,
            note=args.note,
        )
        print(f"Archived clips from plan: {result['plan_path']}")
        print(f"Archived candidates: {result['archived_count']}")
        return 0

    if args.command == "upload":
        result = upload_from_plan(args.plan)
        print(f"Upload complete: {result['video_url']}")
        return 0

    parser.print_help()
    return 1
