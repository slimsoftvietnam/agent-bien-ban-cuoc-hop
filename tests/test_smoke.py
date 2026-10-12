#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VIDEO = ROOT / "sample" / "du-lieu-mau-cuoc-hop.mp4"
SAMPLE_VIDEO_SHA256 = "106438e461836d42c746c33fdfff7285ee2b04a926afa3a30df7e0bb40c376e1"


def run_checked(command: list[str]) -> None:
    result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise AssertionError(f"Lệnh thất bại: {command}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


def main() -> None:
    assert SAMPLE_VIDEO.is_file(), f"Thiếu video mẫu {SAMPLE_VIDEO}"
    digest = hashlib.sha256()
    with SAMPLE_VIDEO.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    assert digest.hexdigest() == SAMPLE_VIDEO_SHA256, "Video mẫu sai SHA-256"

    temp_root = ROOT / "tests" / ".tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="meeting-agent-test-", dir=str(temp_root)) as temp:
        temp_dir = Path(temp)
        video = temp_dir / "sample.mp4"
        output = temp_dir / "output"
        run_checked([sys.executable, str(ROOT / "scripts" / "create_sample_video.py"), "--output", str(video)])
        run_checked([
            sys.executable,
            str(ROOT / "scripts" / "meeting_agent.py"),
            "--input", str(ROOT / "sample" / "transcript.txt"),
            "--participants", str(ROOT / "sample" / "participants.json"),
            "--video", str(video),
            "--output", str(output),
            "--title", "Họp thử nghiệm AI Agent",
            "--meeting-date", "2026-10-11",
        ])
        expected = [
            output / "bien-ban.html",
            output / "bien-ban.pdf",
            output / "action-items.xlsx",
            output / "analysis" / "meeting_data.json",
            output / "analysis" / "peas-report.json",
            output / "manifest.json",
        ]
        for path in expected:
            assert path.is_file() and path.stat().st_size > 0, f"Thiếu đầu ra {path}"
        data = json.loads((output / "analysis" / "meeting_data.json").read_text(encoding="utf-8"))
        assert len(data["decisions"]) == 1
        assert len(data["action_items"]) == 4
        assert any(item["owner"] == "Chưa xác định" for item in data["action_items"])
        assert all(item["evidence_ref"] and item["evidence_quote"] for item in data["action_items"])
        assert data["safety"]["email_sent"] is False
        assert len(data["screenshots"]) >= 4
        assert len(PdfReader(str(output / "bien-ban.pdf")).pages) >= 1
        with zipfile.ZipFile(output / "action-items.xlsx") as workbook:
            assert "xl/workbook.xml" in workbook.namelist()
        drafts = list((output / "email-drafts").glob("*.eml"))
        assert len(drafts) == 2
        for draft in drafts:
            assert b"X-Unsent: 1" in draft.read_bytes()
        report = json.loads((output / "analysis" / "peas-report.json").read_text(encoding="utf-8"))
        assert report["A"]["email_sent"] is False
        assert report["result"] == "PASS_WITH_REVIEW"
    print("SMOKE TEST PASS")


if __name__ == "__main__":
    main()
