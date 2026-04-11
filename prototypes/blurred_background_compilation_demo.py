from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from clipping_automation.services.media import download_reddit_media


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prototype: rebuild a compilation from raw clip sources using blurred-background framing."
    )
    parser.add_argument("--plan", type=Path, required=True, help="Path to the existing plan JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file. Defaults to <plan name>.blurred-raw-demo.mp4 in data/exports.",
    )
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--inset-scale", type=float, default=0.88)
    return parser.parse_args()


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in cleaned.split("-") if part) or "clip"


def _render_segment(
    *,
    input_path: Path,
    output_path: Path,
    duration_seconds: int,
    width: int,
    height: int,
    fps: int,
    inset_scale: float,
) -> None:
    fg_width = int(width * inset_scale)
    fg_height = int(height * inset_scale)
    border_x = ((width - fg_width) // 2) - 6
    border_y = ((height - fg_height) // 2) - 6
    border_w = fg_width + 12
    border_h = fg_height + 12

    filter_complex = (
        f"[0:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=28:10[bg];"
        f"[0:v]fps={fps},scale={fg_width}:{fg_height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"drawbox=x={border_x}:y={border_y}:w={border_w}:h={border_h}:color=white@0.14:t=fill,"
        f"drawbox=x={border_x}:y={border_y}:w={border_w}:h={border_h}:color=white@0.08:t=6[vout]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-t",
        str(duration_seconds),
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run(command)


def main() -> int:
    args = parse_args()
    if not args.plan.exists():
        raise FileNotFoundError(f"Plan not found: {args.plan}")

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    exports_dir = args.plan.parent
    output_path = args.output or exports_dir / f"{plan['name']}.blurred-raw-demo.mp4"
    work_dir = Path(tempfile.mkdtemp(prefix="blurred_compilation_demo_", dir=exports_dir))

    try:
        segments: list[Path] = []
        concat_path = work_dir / "concat.txt"

        for clip in plan.get("clips", []):
            media_url = clip.get("media_url")
            metadata = clip.get("metadata") or {}
            if clip.get("source_type") != "reddit" or not media_url:
                continue

            raw_path = work_dir / f"{clip['rank']:02d}_{_slug(clip['title'])}_raw.mp4"
            segment_path = work_dir / f"{clip['rank']:02d}_{_slug(clip['title'])}_segment.mp4"

            download_reddit_media(
                media_url=media_url,
                dash_url=metadata.get("dash_url"),
                destination=raw_path,
            )

            _render_segment(
                input_path=raw_path,
                output_path=segment_path,
                duration_seconds=int(clip.get("clip_duration_seconds") or 0),
                width=args.width,
                height=args.height,
                fps=args.fps,
                inset_scale=args.inset_scale,
            )
            segments.append(segment_path)

        if not segments:
            raise ValueError("No Reddit clips were available to render in the prototype.")

        concat_lines = [f"file '{segment.as_posix()}'" for segment in segments]
        concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        print(output_path)
        return 0
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
