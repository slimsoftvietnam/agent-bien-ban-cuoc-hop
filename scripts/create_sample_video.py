#!/usr/bin/env python3
"""Create a small synthetic MP4 used by the smoke test."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def font(size: int):
    for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    target = Path(args.output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("Không tìm thấy FFmpeg")
    slides = [
        ("Mở đầu", "Mục tiêu và phạm vi", "#15394A"),
        ("Quyết định", "Chọn phương án B", "#195B7A"),
        ("Phân công", "Checklist và cấu hình thử nghiệm", "#6B4F2A"),
        ("Kết thúc", "Xác nhận deadline", "#355B44"),
    ]
    with tempfile.TemporaryDirectory(prefix="meeting-agent-", dir=str(target.parent)) as tmp:
        tmp_dir = Path(tmp)
        concat_lines = []
        for index, (title, subtitle, color) in enumerate(slides, start=1):
            image = Image.new("RGB", (1280, 720), color)
            draw = ImageDraw.Draw(image)
            draw.text((80, 250), title, font=font(56), fill="white")
            draw.text((80, 335), subtitle, font=font(30), fill="#E8F1F5")
            draw.text((80, 620), "Video kiểm thử tổng hợp", font=font(20), fill="#D8E2E8")
            frame = tmp_dir / f"slide-{index}.png"
            image.save(frame)
            concat_lines.append(f"file '{frame.as_posix()}'")
            concat_lines.append("duration 12")
        concat_lines.append(f"file '{(tmp_dir / 'slide-4.png').as_posix()}'")
        concat_file = tmp_dir / "concat.txt"
        concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-vf", "fps=1,format=yuv420p", "-c:v", "libx264", "-movflags", "+faststart", "-y", str(target),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(result.stderr)
    print(target)


if __name__ == "__main__":
    main()
