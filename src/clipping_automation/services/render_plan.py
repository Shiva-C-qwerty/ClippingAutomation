from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from clipping_automation.config import DEFAULT_DB_PATH, DEFAULT_EXPORT_DIR
from clipping_automation.db import connect, fetch_candidates
from clipping_automation.utils import ensure_directory, ps_quote, slugify


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


def _render_script_contents(plan: dict) -> str:
    build_dir = Path(plan["render"]["build_dir"])
    concat_file = build_dir / "concat.txt"
    output_path = plan["render"]["output_video_path"]

    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$buildDir = {ps_quote(str(build_dir))}",
        "New-Item -ItemType Directory -Force -Path $buildDir | Out-Null",
        "$clips = @(",
    ]

    for clip in plan["clips"]:
        output_clip_path = build_dir / f"{clip['rank']:02d}.mp4"
        lines.extend(
            [
                "  @{",
                f"    Input = {ps_quote(clip['local_media_path'])}",
                f"    Output = {ps_quote(str(output_clip_path))}",
                f"    Duration = {clip['clip_duration_seconds']}",
                "  }",
            ]
        )
    lines.append(")")
    lines.extend(
        [
            "",
            "foreach ($clip in $clips) {",
            '  & ffmpeg -y -i $clip.Input -t $clip.Duration -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p" -af "loudnorm=I=-16:LRA=11:TP=-1.5" -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 192k $clip.Output',
            "}",
            "",
            "$concatLines = $clips | ForEach-Object {",
            "  \"file '$($_.Output.Replace('\\', '/'))'\"",
            "}",
            f"Set-Content -Path {ps_quote(str(concat_file))} -Value $concatLines -Encoding utf8",
            f"& ffmpeg -y -f concat -safe 0 -i {ps_quote(str(concat_file))} -c copy {ps_quote(output_path)}",
        ]
    )
    return "\n".join(lines) + "\n"


def create_compilation_plan(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    style: str = "top5",
    count: int = 5,
    name: str | None = None,
    max_clip_duration: int = 18,
) -> dict:
    ensure_directory(DEFAULT_EXPORT_DIR)

    with connect(db_path) as conn:
        rows = fetch_candidates(conn, rights_status="approved", local_only=True, limit=max(count * 3, count))

    selected = [dict(row) for row in rows[:count]]
    if len(selected) < count:
        raise ValueError(
            f"Not enough approved local clips to build the compilation. Needed {count}, found {len(selected)}."
        )

    generated_at = datetime.now(UTC).isoformat()
    output_name = slugify(name or f"{style}-{generated_at[:10]}")
    plan_path = DEFAULT_EXPORT_DIR / f"{output_name}.plan.json"
    render_script_path = DEFAULT_EXPORT_DIR / f"{output_name}.render.ps1"
    output_video_path = DEFAULT_EXPORT_DIR / f"{output_name}.mp4"
    build_dir = DEFAULT_EXPORT_DIR / f"{output_name}_build"

    clips: list[dict] = []
    for index, row in enumerate(selected, start=1):
        clip_duration = min(row.get("duration_seconds") or max_clip_duration, max_clip_duration)
        clips.append(
            {
                "rank": index,
                "candidate_id": row["id"],
                "title": row["title"],
                "source_type": row["source_type"],
                "source_url": row["source_url"],
                "author": row["author"],
                "score": row["score"],
                "local_media_path": row["local_media_path"],
                "clip_duration_seconds": clip_duration,
                "rights_notes": row["rights_notes"],
            }
        )

    plan = {
        "generated_at": generated_at,
        "style": style,
        "name": output_name,
        "clips": clips,
        "render": {
            "canvas": {"width": 1080, "height": 1920, "fps": 30},
            "build_dir": str(build_dir),
            "plan_path": str(plan_path),
            "render_script_path": str(render_script_path),
            "output_video_path": str(output_video_path),
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
    render_script_path.write_text(_render_script_contents(plan), encoding="utf-8")
    return plan


def run_render(plan_path: Path, execute: bool) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    script_path = Path(plan["render"]["render_script_path"])
    output_path = Path(plan["render"]["output_video_path"])

    result = {
        "plan_path": str(plan_path),
        "render_script_path": str(script_path),
        "output_video_path": str(output_path),
        "executed": False,
    }

    if execute:
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

    return result
