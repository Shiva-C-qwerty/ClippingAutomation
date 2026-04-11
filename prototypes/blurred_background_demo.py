from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prototype: render a vertical video with a blurred background and an uncropped centered frame."
    )
    parser.add_argument("--input", type=Path, required=True, help="Input video path.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path. Defaults to <input>.blurred-bg-demo.mp4.",
    )
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument(
        "--inset-scale",
        type=float,
        default=0.9,
        help="Scale factor for the centered foreground frame to reveal some blurred background.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Input video not found: {args.input}")

    output = args.output or args.input.with_name(f"{args.input.stem}.blurred-bg-demo.mp4")
    output.parent.mkdir(parents=True, exist_ok=True)

    fg_width = int(args.width * args.inset_scale)
    fg_height = int(args.height * args.inset_scale)
    fg_x = (args.width - fg_width) // 2
    fg_y = (args.height - fg_height) // 2
    border_x = fg_x - 6
    border_y = fg_y - 6
    border_w = fg_width + 12
    border_h = fg_height + 12

    filter_complex = (
        f"[0:v]scale={args.width}:{args.height}:force_original_aspect_ratio=increase,"
        f"crop={args.width}:{args.height},boxblur=28:10[bg];"
        f"[0:v]scale={fg_width}:{fg_height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"drawbox=x={border_x}:y={border_y}:w={border_w}:h={border_h}:color=white@0.18:t=fill,"
        f"drawbox=x={border_x}:y={border_y}:w={border_w}:h={border_h}:color=white@0.08:t=6"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(args.input),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
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


if __name__ == "__main__":
    raise SystemExit(main())
