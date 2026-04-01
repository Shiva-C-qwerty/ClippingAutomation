from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


WINDOWS_FONT = Path("C:/Windows/Fonts/arialbd.ttf")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prototype: add countdown number overlays to an existing compilation export."
    )
    parser.add_argument("--plan", type=Path, required=True, help="Path to the compilation .plan.json file.")
    parser.add_argument(
        "--input-video",
        type=Path,
        help="Optional input video. Defaults to the plan's output_video_path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path. Defaults to <input>.numbered-demo.mp4.",
    )
    return parser.parse_args()


def load_plan(plan_path: Path) -> dict:
    return json.loads(plan_path.read_text(encoding="utf-8"))


def _ffmpeg_path(path: Path) -> str:
    return path.as_posix().replace(":", r"\:")


def _clean_text(value: str, limit: int = 48) -> str:
    collapsed = " ".join(value.split())
    return collapsed[:limit].strip()


def build_drawtext_filter(plan: dict, title_dir: Path) -> str:
    clips = plan.get("clips", [])
    intro = plan.get("intro")
    intro_seconds = int(intro.get("duration_seconds", 0)) if intro else 0
    total_clips = len(clips)

    if not WINDOWS_FONT.exists():
        raise FileNotFoundError(f"Expected font file not found: {WINDOWS_FONT}")

    escaped_font = _ffmpeg_path(WINDOWS_FONT)

    filters: list[str] = []
    total_duration = float(plan["render"]["planned_total_duration_seconds"])
    current_start = float(intro_seconds)

    filters.extend(
        [
            "drawtext="
            f"fontfile='{escaped_font}':"
            "text='Ranking The':"
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
            "text='Best Animal Moments':"
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
            "text='(BEST ONE LAST)':"
            "x=(w-text_w)/2:y=124:"
            "fontsize=26:"
            "fontcolor=0xFFD84A:"
            "borderw=2:"
            "bordercolor=black@0.82:"
            "shadowx=2:"
            "shadowy=2:"
            "shadowcolor=black@0.45",
        ]
    )

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

    for index, clip in enumerate(clips, start=1):
        clip_duration = float(clip["clip_duration_seconds"])
        countdown_value = total_clips - index + 1
        title_text = _clean_text(str(clip.get("title") or f"Clip {countdown_value}"))
        title_file = title_dir / f"title_{index:02d}.txt"
        title_file.write_text(title_text, encoding="utf-8")
        escaped_title_file = _ffmpeg_path(title_file)

        flash_end = min(current_start + 0.12, current_start + clip_duration)
        banner_end = min(current_start + 2.20, current_start + clip_duration)
        active_y = rank_y + ((countdown_value - 1) * rank_gap) - 4

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
            f"enable='between(t,{current_start:.3f},{current_start + clip_duration:.3f})'"
        )
        filters.append(
            "drawbox="
            "x=70:y=h-136:w=iw-140:h=64:"
            "color=black@0.34:t=fill:"
            f"enable='between(t,{current_start:.3f},{banner_end:.3f})'"
        )
        filters.append(
            "drawtext="
            f"fontfile='{escaped_font}':"
            f"textfile='{escaped_title_file}':"
            "reload=0:"
            "x=(w-text_w)/2:y=h-118:"
            "fontsize=32:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black@0.55:"
            f"enable='between(t,{current_start:.3f},{banner_end:.3f})'"
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

    filters.extend(
        [
            "drawtext="
            f"fontfile='{escaped_font}':"
            "text='@clipbot demo':"
            "x=(w-text_w)/2:y=h-38:"
            "fontsize=24:"
            "fontcolor=white@0.78:"
            "borderw=2:"
            "bordercolor=black@0.55",
        ]
    )

    return ",".join(filters)


def main() -> int:
    args = parse_args()
    plan = load_plan(args.plan)

    input_video = args.input_video or Path(plan["render"]["output_video_path"])
    if not input_video.exists():
        raise FileNotFoundError(f"Input video not found: {input_video}")

    output = args.output or input_video.with_name(f"{input_video.stem}.numbered-demo.mp4")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = output.parent / f"{output.stem}_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        video_filter = build_drawtext_filter(plan, temp_dir)
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            "-vf",
            video_filter,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
        subprocess.run(command, check=True)
        print(output)
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
