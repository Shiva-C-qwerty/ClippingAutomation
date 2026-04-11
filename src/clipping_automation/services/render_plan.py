from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from clipping_automation.config import DEFAULT_DB_PATH, DEFAULT_EXPORT_DIR
from clipping_automation.db import connect, fetch_candidates
from clipping_automation.services.media import (
    cleanup_temp_dir,
    create_temp_download_dir,
    downloadable_media_url,
    download_media,
    download_reddit_media,
)
from clipping_automation.utils import ensure_directory, ps_quote, slugify

SHORTS_MAX_SECONDS = 180
DEFAULT_INTRO_SECONDS = 3
DEFAULT_OUTRO_SECONDS = 3
WINDOWS_FONT_PATH = Path("C:/Windows/Fonts/arialbd.ttf")


def _build_title(style: str, generated_on: str) -> str:
    stamp = generated_on[:10]
    if style == "top5":
        return f"Top 5 Funny Clips | {stamp} #shorts"
    return f"Funny Clip Compilation | {stamp} #shorts"


def _build_description(selected: list[dict]) -> str:
    lines = [
        "Compilation generated with ClippingAutomation MVP.",
        "Only upload this if you have the rights to reuse every clip.",
        "",
        "Sources:",
    ]
    for index, clip in enumerate(selected, start=1):
        lines.append(f"{index}. {clip['title']} - {clip['source_url']}")
    return "\n".join(lines)


def _ffprobe_duration(path: Path) -> int | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        return max(int(float(raw)), 0)
    except ValueError:
        return None


def _clip_block(input_path: str, output_path: str, duration: int) -> list[str]:
    return [
        "  @{",
        f"    Input = {ps_quote(input_path)}",
        f"    Output = {ps_quote(output_path)}",
        f"    Duration = {duration}",
        "  }",
    ]


def _ffmpeg_filter_path(path: Path) -> str:
    return path.as_posix().replace(":", r"\:")


def _build_blurred_background_filter(
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    inset_scale: float = 0.88,
) -> str:
    fg_width = int(width * inset_scale)
    fg_height = int(height * inset_scale)
    border_x = ((width - fg_width) // 2) - 6
    border_y = ((height - fg_height) // 2) - 6
    border_w = fg_width + 12
    border_h = fg_height + 12

    return (
        f"[0:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=28:10[bg];"
        f"[0:v]fps={fps},scale={fg_width}:{fg_height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"drawbox=x={border_x}:y={border_y}:w={border_w}:h={border_h}:color=white@0.14:t=fill,"
        f"drawbox=x={border_x}:y={border_y}:w={border_w}:h={border_h}:color=white@0.08:t=6,"
        "setsar=1,format=yuv420p[vout]"
    )


def _clean_overlay_text(value: str | None, limit: int = 28) -> str:
    if not value:
        return ""
    return " ".join(value.split())[:limit].strip()


def _build_overlay_heading(plan: dict) -> tuple[str, str, str]:
    clips = plan.get("clips", [])
    categories = {
        ((clip.get("metadata") or {}).get("category") or "").strip().lower()
        for clip in clips
        if (clip.get("metadata") or {}).get("category")
    }
    if len(categories) == 1 and "animal" in categories:
        return ("Ranking The", "Best Animal Moments", "(BEST ONE LAST)")
    return ("Ranking The", "Best Funny Clips", "(BEST ONE LAST)")


def _prepare_overlay_assets(plan: dict) -> dict | None:
    if plan.get("style") != "top5":
        return None
    if not WINDOWS_FONT_PATH.exists():
        return None

    build_dir = Path(plan["render"]["build_dir"])
    overlay_dir = ensure_directory(build_dir / "overlay")
    title_files: list[str | None] = []
    for index, clip in enumerate(plan.get("clips", []), start=1):
        overlay_title = _clean_overlay_text(clip.get("overlay_title"))
        if not overlay_title:
            title_files.append(None)
            continue
        title_file = overlay_dir / f"title_{index:02d}.txt"
        title_file.write_text(overlay_title, encoding="utf-8")
        title_files.append(str(title_file))

    heading_top, heading_main, heading_sub = _build_overlay_heading(plan)
    return {
        "enabled": True,
        "font_path": str(WINDOWS_FONT_PATH),
        "title_files": title_files,
        "heading_top": heading_top,
        "heading_main": heading_main,
        "heading_sub": heading_sub,
    }


def _build_reference_overlay_filter(plan: dict) -> str | None:
    overlay = plan["render"].get("overlay")
    if not overlay or not overlay.get("enabled"):
        return None

    font_path = Path(overlay["font_path"])
    escaped_font = _ffmpeg_filter_path(font_path)
    clips = plan.get("clips", [])
    intro_seconds = int((plan.get("intro") or {}).get("duration_seconds", 0))
    total_clips = len(clips)
    rank_palette = {
        1: "0xFFD84A",
        2: "0xAFAFAF",
        3: "0xFF4D4D",
        4: "0xFF9E3D",
        5: "0xFFFFFF",
    }
    rank_x = 58
    rank_y = 360
    rank_gap = 78

    filters: list[str] = [
        "drawtext="
        f"fontfile='{escaped_font}':"
        f"text='{overlay['heading_top']}':"
        "x=(w-text_w)/2:y=26:"
        "fontsize=42:"
        "fontcolor=white:"
        "borderw=3:"
        "bordercolor=black@0.82:"
        "shadowx=2:"
        "shadowy=3:"
        "shadowcolor=black@0.55",
        "drawtext="
        f"fontfile='{escaped_font}':"
        f"text='{overlay['heading_main']}':"
        "x=(w-text_w)/2:y=68:"
        "fontsize=54:"
        "fontcolor=0x3DFF57:"
        "borderw=3:"
        "bordercolor=black@0.85:"
        "shadowx=2:"
        "shadowy=3:"
        "shadowcolor=black@0.55",
        "drawtext="
        f"fontfile='{escaped_font}':"
        f"text='{overlay['heading_sub']}':"
        "x=(w-text_w)/2:y=124:"
        "fontsize=26:"
        "fontcolor=0xFFD84A:"
        "borderw=2:"
        "bordercolor=black@0.82:"
        "shadowx=2:"
        "shadowy=2:"
        "shadowcolor=black@0.45",
    ]

    for rank in range(1, total_clips + 1):
        base_y = rank_y + ((rank - 1) * rank_gap)
        rank_color = rank_palette.get(rank, "0xFFFFFF")
        filters.append(
            "drawtext="
            f"fontfile='{escaped_font}':"
            f"text='{rank}.':"
            f"x={rank_x}:y={base_y}:"
            "fontsize=48:"
            f"fontcolor={rank_color}@0.68:"
            "borderw=2:"
            "bordercolor=black@0.55"
        )

    current_start = float(intro_seconds)
    for index, clip in enumerate(clips, start=1):
        clip_duration = float(clip["clip_duration_seconds"])
        countdown_value = total_clips - index + 1
        active_y = rank_y + ((countdown_value - 1) * rank_gap) - 4
        flash_end = min(current_start + 0.12, current_start + clip_duration)
        clip_end = current_start + clip_duration

        filters.append(
            "drawtext="
            f"fontfile='{escaped_font}':"
            f"text='{countdown_value}.':"
            f"x={rank_x-6}:y={active_y}:"
            "fontsize=60:"
            f"fontcolor={rank_palette.get(countdown_value, '0xFFFFFF')}:"
            "borderw=3:"
            "bordercolor=black@0.75:"
            "shadowx=3:"
            "shadowy=3:"
            "shadowcolor=black@0.55:"
            f"enable='between(t,{current_start:.3f},{clip_end:.3f})'"
        )

        title_file = overlay["title_files"][index - 1] if index - 1 < len(overlay["title_files"]) else None
        if title_file:
            escaped_title_file = _ffmpeg_filter_path(Path(title_file))
            filters.append(
                "drawtext="
                f"fontfile='{escaped_font}':"
                f"textfile='{escaped_title_file}':"
                "reload=0:"
                f"x={rank_x+58}:y={active_y+8}:"
                "fontsize=30:"
                "fontcolor=white:"
                "borderw=2:"
                "bordercolor=black@0.65:"
                "shadowx=2:"
                "shadowy=2:"
                "shadowcolor=black@0.45:"
                f"enable='between(t,{current_start:.3f},{clip_end:.3f})'"
            )

        filters.append(
            "drawbox="
            "x=0:y=0:w=iw:h=ih:"
            "color=white@0.10:t=fill:"
            f"enable='between(t,{current_start:.3f},{flash_end:.3f})'"
        )
        filters.append(
            "drawbox="
            "x=0:y=166:w=iw:h=8:"
            "color=white@0.18:t=fill:"
            f"enable='between(t,{current_start:.3f},{flash_end:.3f})'"
        )
        current_start += clip_duration

    filters.append(
        "drawtext="
        f"fontfile='{escaped_font}':"
        "text='@clipbot demo':"
        "x=(w-text_w)/2:y=h-38:"
        "fontsize=24:"
        "fontcolor=white@0.78:"
        "borderw=2:"
        "bordercolor=black@0.55"
    )
    return ",".join(filters)


def _render_script_contents(plan: dict) -> str:
    build_dir = Path(plan["render"]["build_dir"])
    concat_file = build_dir / "concat.txt"
    combined_output_path = build_dir / "combined.mp4"
    output_path = plan["render"]["output_video_path"]
    overlay_filter = _build_reference_overlay_filter(plan)
    clip_filter = _build_blurred_background_filter()
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "function Invoke-CheckedCommand {",
        "  param([scriptblock]$Command)",
        "  & $Command",
        "  if ($LASTEXITCODE -ne 0) {",
        "    throw \"External command failed with exit code $LASTEXITCODE\"",
        "  }",
        "}",
        "function Test-HasAudio {",
        "  param([string]$InputPath)",
        "  $audioProbe = & ffprobe -v error -select_streams a:0 -show_entries stream=index -of csv=p=0 $InputPath",
        "  if ($LASTEXITCODE -ne 0) {",
        "    throw \"ffprobe failed while checking audio for $InputPath\"",
        "  }",
        "  return -not [string]::IsNullOrWhiteSpace(($audioProbe | Out-String).Trim())",
        "}",
        f"$buildDir = {ps_quote(str(build_dir))}",
        "New-Item -ItemType Directory -Force -Path $buildDir | Out-Null",
        "$clips = @(",
    ]

    clip_index = 0
    intro = plan.get("intro")
    if intro:
        clip_index += 1
        lines.extend(
            _clip_block(
                intro["input_path"],
                str(build_dir / f"{clip_index:02d}.mp4"),
                int(intro["duration_seconds"]),
            )
        )

    for clip in plan["clips"]:
        clip_index += 1
        lines.extend(
            _clip_block(
                clip["resolved_input_path"],
                str(build_dir / f"{clip_index:02d}.mp4"),
                int(clip["clip_duration_seconds"]),
            )
        )

    outro = plan.get("outro")
    if outro:
        clip_index += 1
        lines.extend(
            _clip_block(
                outro["input_path"],
                str(build_dir / f"{clip_index:02d}.mp4"),
                int(outro["duration_seconds"]),
            )
        )

    lines.append(")")
    lines.extend(
        [
            "",
            "foreach ($clip in $clips) {",
            "  if (Test-HasAudio -InputPath $clip.Input) {",
            f"    Invoke-CheckedCommand {{ ffmpeg -y -i $clip.Input -t $clip.Duration -filter_complex {ps_quote(clip_filter)} -af \"loudnorm=I=-16:LRA=11:TP=-1.5\" -map [vout] -map 0:a:0 -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -ar 48000 -b:a 192k $clip.Output }}",
            "  } else {",
            f"    Invoke-CheckedCommand {{ ffmpeg -y -i $clip.Input -f lavfi -t $clip.Duration -i anullsrc=channel_layout=stereo:sample_rate=48000 -filter_complex {ps_quote(clip_filter)} -shortest -map [vout] -map 1:a:0 -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -ar 48000 -b:a 192k $clip.Output }}",
            "  }",
            "}",
            "",
            "$concatLines = $clips | ForEach-Object {",
            "  \"file '$($_.Output.Replace('\\', '/'))'\"",
            "}",
            f"[System.IO.File]::WriteAllLines({ps_quote(str(concat_file))}, $concatLines, [System.Text.UTF8Encoding]::new($false))",
            f"Invoke-CheckedCommand {{ ffmpeg -y -f concat -safe 0 -i {ps_quote(str(concat_file))} -vf format=yuv420p -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -ar 48000 -b:a 192k -movflags +faststart {ps_quote(str(combined_output_path))} }}",
        ]
    )
    if overlay_filter:
        lines.extend(
            [
                f"$overlayFilter = {ps_quote(overlay_filter)}",
                f"Invoke-CheckedCommand {{ ffmpeg -y -i {ps_quote(str(combined_output_path))} -vf $overlayFilter -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a copy -movflags +faststart {ps_quote(output_path)} }}",
            ]
        )
    else:
        lines.append(f"Copy-Item -LiteralPath {ps_quote(str(combined_output_path))} -Destination {ps_quote(output_path)} -Force")
    return "\n".join(lines) + "\n"


def _usable_rows(conn, allow_remote_media: bool, count: int) -> list[dict]:
    rows = fetch_candidates(
        conn,
        rights_status="approved",
        local_only=not allow_remote_media,
        usable_only=allow_remote_media,
        limit=max(count * 6, count),
    )
    usable: list[dict] = []
    for row in rows:
        item = dict(row)
        if item.get("metadata_json"):
            try:
                item["metadata"] = json.loads(item["metadata_json"])
            except json.JSONDecodeError:
                item["metadata"] = {}
        else:
            item["metadata"] = {}
        music_review = item["metadata"].get("music_review") or {}
        detection = item["metadata"].get("music_detection") or {}
        effective_music_status = music_review.get("status")
        if not effective_music_status:
            legacy_risk = music_review.get("risk")
            if legacy_risk == "low":
                effective_music_status = "safe"
            elif legacy_risk == "medium":
                effective_music_status = "needs_review"
            elif legacy_risk == "high":
                effective_music_status = "unsafe"
        if not effective_music_status:
            effective_music_status = detection.get("status") or "unknown"
        if effective_music_status in {"unsafe", "needs_review"}:
            continue
        if item.get("local_media_path"):
            usable.append(item)
        elif allow_remote_media and downloadable_media_url(item["source_type"], item.get("media_url")):
            usable.append(item)
    return usable


def _asset_duration(path: Path | None, fallback_seconds: int) -> int:
    if not path:
        return 0
    if not path.exists():
        raise FileNotFoundError(f"Asset not found: {path}")
    return _ffprobe_duration(path) or fallback_seconds


def _best_last_order(rows: list[dict]) -> list[dict]:
    return list(reversed(rows))


def create_compilation_plan(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    style: str = "top5",
    count: int = 5,
    name: str | None = None,
    max_clip_duration: int = 18,
    intro_path: Path | None = None,
    outro_path: Path | None = None,
    allow_remote_media: bool = False,
) -> dict:
    ensure_directory(DEFAULT_EXPORT_DIR)

    intro_seconds = _asset_duration(intro_path, DEFAULT_INTRO_SECONDS)
    outro_seconds = _asset_duration(outro_path, DEFAULT_OUTRO_SECONDS)
    available_seconds = SHORTS_MAX_SECONDS - intro_seconds - outro_seconds
    if available_seconds <= 0:
        raise ValueError("Intro/outro leave no room for clips inside the 180 second limit.")

    with connect(db_path) as conn:
        usable_rows = _usable_rows(conn, allow_remote_media=allow_remote_media, count=count)

    if len(usable_rows) < count:
        raise ValueError(
            f"Not enough approved usable clips to build the compilation. Needed {count}, found {len(usable_rows)}."
        )

    selected = _best_last_order(usable_rows[:count])
    base_per_clip = max(1, available_seconds // count)
    generated_at = datetime.now(UTC).isoformat()
    output_name = slugify(name or f"{style}-{generated_at[:10]}")
    plan_path = DEFAULT_EXPORT_DIR / f"{output_name}.plan.json"
    render_script_path = DEFAULT_EXPORT_DIR / f"{output_name}.render.ps1"
    output_video_path = DEFAULT_EXPORT_DIR / f"{output_name}.mp4"
    build_dir = DEFAULT_EXPORT_DIR / f"{output_name}_build"

    clips: list[dict] = []
    used_seconds = 0
    for index, row in enumerate(selected, start=1):
        remaining_clips = count - index
        remaining_budget = available_seconds - used_seconds
        reserve_for_remaining = remaining_clips
        allowed_now = max(1, remaining_budget - reserve_for_remaining)
        clip_duration = min(
            row.get("duration_seconds") or base_per_clip,
            max_clip_duration,
            base_per_clip if remaining_clips else remaining_budget,
            allowed_now,
        )
        used_seconds += clip_duration
        clips.append(
            {
                "rank": index,
                "candidate_id": row["id"],
                "title": row["title"],
                "overlay_title": (row.get("metadata") or {}).get("clip_title"),
                "source_type": row["source_type"],
                "source_url": row["source_url"],
                "author": row["author"],
                "score": row["score"],
                "local_media_path": row["local_media_path"],
                "media_url": row["media_url"],
                "metadata": row.get("metadata", {}),
                "clip_duration_seconds": clip_duration,
                "rights_notes": row["rights_notes"],
            }
        )

    total_duration = intro_seconds + outro_seconds + sum(int(clip["clip_duration_seconds"]) for clip in clips)
    plan = {
        "generated_at": generated_at,
        "style": style,
        "name": output_name,
        "clips": clips,
        "intro": {
            "input_path": str(intro_path.resolve()),
            "duration_seconds": intro_seconds,
        } if intro_path else None,
        "outro": {
            "input_path": str(outro_path.resolve()),
            "duration_seconds": outro_seconds,
        } if outro_path else None,
        "render": {
            "canvas": {"width": 1080, "height": 1920, "fps": 30},
            "build_dir": str(build_dir),
            "plan_path": str(plan_path),
            "render_script_path": str(render_script_path),
            "output_video_path": str(output_video_path),
            "download_remote_media": allow_remote_media,
            "cleanup_downloads_after_render": True,
            "max_total_duration_seconds": SHORTS_MAX_SECONDS,
            "planned_total_duration_seconds": total_duration,
        },
        "youtube": {
            "title": _build_title(style, generated_at),
            "description": _build_description(clips),
            "tags": ["funny", "shorts", "compilation", "viral", "clips"],
            "privacy_status": "private",
            "category_id": "23",
            "made_for_kids": False,
        },
    }

    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    render_script_path.write_text(
        "# Inputs are resolved at render time.\n"
        "# Run `clipbot render --plan <path> --execute` after FFmpeg is installed.\n",
        encoding="utf-8",
    )
    return plan


def _resolve_clip_inputs(plan: dict) -> tuple[dict, Path | None]:
    build_dir = Path(plan["render"]["build_dir"])
    downloads_dir: Path | None = None

    try:
        for clip in plan["clips"]:
            local_media_path = clip.get("local_media_path")
            if local_media_path:
                clip["resolved_input_path"] = str(Path(local_media_path))
                continue

            media_url = clip.get("media_url")
            if not plan["render"].get("download_remote_media"):
                raise ValueError(f"Clip {clip['candidate_id']} has no local file and remote downloads are disabled.")
            if not downloadable_media_url(clip["source_type"], media_url):
                raise ValueError(
                    f"Clip {clip['candidate_id']} cannot be auto-downloaded safely from source type {clip['source_type']}."
                )

            if downloads_dir is None:
                downloads_dir = create_temp_download_dir(build_dir)
            target_path = downloads_dir / f"{clip['rank']:02d}_{slugify(clip['title'])}.mp4"
            if clip["source_type"] == "reddit":
                download_reddit_media(
                    media_url=media_url,
                    destination=target_path,
                    dash_url=(clip.get("metadata") or {}).get("dash_url"),
                )
            else:
                download_media(media_url, target_path)
            clip["resolved_input_path"] = str(target_path)
    except Exception:
        cleanup_temp_dir(downloads_dir)
        raise

    return plan, downloads_dir


def run_render(plan_path: Path, execute: bool) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    output_path = Path(plan["render"]["output_video_path"])
    temp_download_dir: Path | None = None

    if execute:
        plan, temp_download_dir = _resolve_clip_inputs(plan)
        plan["render"]["overlay"] = _prepare_overlay_assets(plan)
        script_path = Path(plan["render"]["render_script_path"])
        script_path.write_text(_render_script_contents(plan), encoding="utf-8")
    else:
        script_path = Path(plan["render"]["render_script_path"])

    result = {
        "plan_path": str(plan_path),
        "render_script_path": str(script_path),
        "output_video_path": str(output_path),
        "executed": False,
        "temp_download_dir": str(temp_download_dir) if temp_download_dir else None,
    }

    if execute:
        try:
            subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                ],
                check=True,
            )
            result["executed"] = True
        finally:
            cleanup_temp_dir(temp_download_dir)
            build_dir = Path(plan["render"]["build_dir"])
            if build_dir.exists():
                shutil.rmtree(build_dir, ignore_errors=True)

    return result
