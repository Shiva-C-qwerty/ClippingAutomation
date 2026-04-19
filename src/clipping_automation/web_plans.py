from __future__ import annotations

import json
from pathlib import Path

from clipping_automation.config import AUDIO_BEDS_DIR, DEFAULT_DB_PATH, DEFAULT_EXPORT_DIR
from clipping_automation.db import connect, get_candidate

SUPPORTED_AUDIO_BED_SUFFIXES = {".mp3", ".wav", ".m4a"}


def list_plan_paths() -> list[Path]:
    return sorted(
        DEFAULT_EXPORT_DIR.glob("*.plan.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def resolve_plan_path(plan_filename: str) -> Path:
    if not plan_filename or Path(plan_filename).name != plan_filename:
        raise ValueError("Invalid plan filename.")
    if not plan_filename.endswith(".plan.json"):
        raise ValueError("Plan filename must end with .plan.json.")

    path = (DEFAULT_EXPORT_DIR / plan_filename).resolve()
    exports_root = DEFAULT_EXPORT_DIR.resolve()
    if not path.is_relative_to(exports_root):
        raise ValueError("Plan path is outside exports.")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Plan not found: {plan_filename}")
    return path


def load_plan(plan_path: Path) -> dict:
    return json.loads(plan_path.read_text(encoding="utf-8-sig"))


def save_plan(plan_path: Path, plan: dict) -> None:
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")


def list_audio_bed_paths() -> list[Path]:
    if not AUDIO_BEDS_DIR.exists():
        return []
    return sorted(
        [
            path
            for path in AUDIO_BEDS_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_BED_SUFFIXES
        ],
        key=lambda path: path.name.lower(),
    )


def audio_bed_options() -> list[dict]:
    options: list[dict] = []
    for path in list_audio_bed_paths():
        options.append(
            {
                "filename": path.name,
                "display_name": path.stem.replace("_", " ").replace("-", " "),
                "path": str(path.resolve()),
            }
        )
    return options


def resolve_audio_bed_filename(filename: str | None) -> Path | None:
    if not filename:
        return None
    if Path(filename).name != filename:
        raise ValueError("Invalid audio bed filename.")

    path = (AUDIO_BEDS_DIR / filename).resolve()
    root = AUDIO_BEDS_DIR.resolve()
    if not path.is_relative_to(root):
        raise ValueError("Audio bed path is outside audio library.")
    if path.suffix.lower() not in SUPPORTED_AUDIO_BED_SUFFIXES:
        raise ValueError("Unsupported audio bed file type.")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Audio bed not found: {filename}")
    return path


def effective_music_status_from_metadata(metadata: dict | None) -> str:
    metadata = metadata or {}
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


def _archive_summary(candidate_ids: list[int], db_path: Path) -> dict:
    if not candidate_ids:
        return {
            "candidate_ids": [],
            "total_candidates": 0,
            "archived_candidates": 0,
            "all_archived": False,
        }

    archived_candidates = 0
    with connect(db_path) as conn:
        for candidate_id in candidate_ids:
            row = get_candidate(conn, candidate_id)
            if row and row["rights_status"] == "archived":
                archived_candidates += 1

    return {
        "candidate_ids": candidate_ids,
        "total_candidates": len(candidate_ids),
        "archived_candidates": archived_candidates,
        "all_archived": archived_candidates == len(candidate_ids),
    }


def update_plan_audio_beds(
    plan_path: Path,
    selections: dict[int, str | None],
) -> dict:
    plan = load_plan(plan_path)
    updated = 0

    for clip in plan.get("clips", []):
        candidate_id = clip.get("candidate_id")
        if candidate_id is None:
            continue
        candidate_id = int(candidate_id)
        if candidate_id not in selections:
            continue

        selected_filename = selections[candidate_id]
        if selected_filename:
            audio_bed_path = resolve_audio_bed_filename(selected_filename)
            clip["audio_bed"] = {
                "filename": audio_bed_path.name,
                "path": str(audio_bed_path),
            }
        else:
            clip.pop("audio_bed", None)
        updated += 1

    save_plan(plan_path, plan)
    return {
        "updated": updated,
        "plan_path": str(plan_path),
    }


def _clip_view_model(clip: dict) -> dict:
    metadata = clip.get("metadata") or {}
    effective_music_status = effective_music_status_from_metadata(metadata)
    audio_bed = clip.get("audio_bed") or {}
    selected_audio_bed_filename = audio_bed.get("filename") or ""
    selected_audio_bed_path = audio_bed.get("path") or ""

    return {
        **clip,
        "effective_music_status": effective_music_status,
        "is_no_audio": effective_music_status == "no_audio",
        "selected_audio_bed_filename": selected_audio_bed_filename,
        "selected_audio_bed_path": selected_audio_bed_path,
    }


def plan_view_model(plan_path: Path, *, db_path: Path = DEFAULT_DB_PATH) -> dict:
    plan = load_plan(plan_path)
    render = plan.get("render") or {}
    raw_clips = plan.get("clips") or []
    clips = [_clip_view_model(clip) for clip in raw_clips]
    no_audio_clip_count = len([clip for clip in clips if clip["is_no_audio"]])
    output_video_path = Path(render.get("output_video_path", DEFAULT_EXPORT_DIR / f"{plan_path.stem}.mp4"))
    render_script_path = Path(render.get("render_script_path", DEFAULT_EXPORT_DIR / f"{plan_path.stem}.render.ps1"))
    candidate_ids = [
        int(clip["candidate_id"])
        for clip in clips
        if clip.get("candidate_id") is not None
    ]
    archive = _archive_summary(candidate_ids, db_path)

    return {
        "filename": plan_path.name,
        "name": plan.get("name") or plan_path.stem,
        "generated_at": plan.get("generated_at") or "",
        "style": plan.get("style") or "-",
        "clip_count": len(clips),
        "no_audio_clip_count": no_audio_clip_count,
        "clips": clips,
        "intro": plan.get("intro"),
        "outro": plan.get("outro"),
        "has_intro": bool(plan.get("intro")),
        "has_outro": bool(plan.get("outro")),
        "planned_total_duration_seconds": render.get("planned_total_duration_seconds"),
        "output_video_path": str(output_video_path),
        "output_exists": output_video_path.exists(),
        "output_filename": output_video_path.name,
        "render_script_path": str(render_script_path),
        "render_script_filename": render_script_path.name,
        "plan_path": str(plan_path),
        "plan_filename_only": plan_path.name,
        "plan_download_name": plan_path.name,
        "archive": archive,
        "audio_bed_options": audio_bed_options(),
    }
