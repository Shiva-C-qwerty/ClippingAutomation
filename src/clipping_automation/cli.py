from __future__ import annotations

import argparse
from pathlib import Path

from clipping_automation.config import DEFAULT_CONFIG_PATH, DEFAULT_DB_PATH, bootstrap_workspace
from clipping_automation.db import connect, fetch_candidates, initialize_database
from clipping_automation.services.approval import approve_candidate
from clipping_automation.services.discovery import run_discovery
from clipping_automation.services.render_plan import create_compilation_plan, run_render
from clipping_automation.services.upload import upload_from_plan
from clipping_automation.utils import truncate


def _print_candidates(rows: list[dict]) -> None:
    if not rows:
        print("No candidates found.")
        return

    header = f"{'ID':<5} {'SRC':<8} {'STATUS':<14} {'SCORE':<8} {'DUR':<6} TITLE"
    print(header)
    print("-" * len(header))
    for row in rows:
        duration = row["duration_seconds"] if row["duration_seconds"] is not None else "-"
        print(
            f"{row['id']:<5} "
            f"{row['source_type']:<8} "
            f"{row['rights_status']:<14} "
            f"{row['score']:<8.2f} "
            f"{str(duration):<6} "
            f"{truncate(row['title'], 80)}"
        )


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
    list_cmd.add_argument("--status", choices=["needs_review", "approved", "rejected"])
    list_cmd.add_argument("--local-only", action="store_true")
    list_cmd.add_argument("--limit", type=int, default=20)

    approve = subparsers.add_parser("approve", help="Approve or reject a candidate and optionally attach a local file.")
    approve.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    approve.add_argument("--candidate", type=int, required=True)
    approve.add_argument("--status", choices=["approved", "rejected", "needs_review"], default="approved")
    approve.add_argument("--notes", help="Rights or review notes.")
    approve.add_argument("--file", type=Path, help="Local clip file to copy into data/assets/approved.")

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
        _print_candidates(rows)
        return 0

    if args.command == "approve":
        bootstrap_workspace()
        initialize_database(args.db)
        result = approve_candidate(
            candidate_id=args.candidate,
            rights_status=args.status,
            rights_notes=args.notes,
            local_file=args.file,
            db_path=args.db,
        )
        print(f"Candidate {result['candidate_id']} updated to {result['rights_status']}.")
        if result["local_media_path"]:
            print(f"Copied media to: {result['local_media_path']}")
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
        print(f"Planned duration: {plan['render']['planned_total_duration_seconds']}s / 45s")
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

    if args.command == "upload":
        result = upload_from_plan(args.plan)
        print(f"Upload complete: {result['video_url']}")
        return 0

    parser.print_help()
    return 1
