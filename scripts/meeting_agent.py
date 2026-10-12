#!/usr/bin/env python3
"""Conservative meeting-minutes pipeline for the meeting-minutes-agent skill."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SKILL_ROOT / "config" / "default.json"
MEDIA_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".webm"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
LOCAL_RUNTIME = SKILL_ROOT / ".runtime"

if LOCAL_RUNTIME.is_dir() and str(LOCAL_RUNTIME) not in sys.path:
    sys.path.insert(0, str(LOCAL_RUNTIME))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def fail(message: str, code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        fail(f"Không đọc được JSON {path}: {exc}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def safe_name(value: str) -> str:
    clean = normalize_key(value)
    clean = re.sub(r"[^a-z0-9]+", "-", clean).strip("-")
    return clean or "chua-xac-dinh"


def timestamp_to_seconds(value: str | None) -> float | None:
    if not value:
        return None
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        return float(parts[0] * 60 + parts[1])
    if len(parts) == 3:
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    return None


def seconds_to_timestamp(value: float) -> str:
    total = max(0, int(round(value)))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def load_participants(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = read_json(path)
    participants = payload.get("participants")
    if not isinstance(participants, list):
        fail("participants.json phải có khóa 'participants' là một danh sách.")
    alias_map: dict[str, dict[str, Any]] = {}
    for raw in participants:
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            fail("Mỗi người tham gia phải có trường name.")
        item = {
            "name": str(raw["name"]).strip(),
            "email": str(raw.get("email", "")).strip(),
            "aliases": [str(v).strip() for v in raw.get("aliases", []) if str(v).strip()],
        }
        raw.clear()
        raw.update(item)
        for alias in [item["name"], *item["aliases"]]:
            key = normalize_key(alias)
            if key in alias_map and alias_map[key]["name"] != item["name"]:
                fail(f"Alias trùng giữa nhiều người: {alias}")
            alias_map[key] = item
    return participants, alias_map


def decode_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1258", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    fail(f"Không xác định được encoding của {path}")
    return ""


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".txt", ".md"}:
        return decode_text(path)
    if ext == ".docx":
        try:
            from docx import Document
        except ImportError:
            fail("Thiếu python-docx. Hãy dùng Python bundled của Codex hoặc cài python-docx.")
        doc = Document(str(path))
        chunks = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                chunks.append(" | ".join(cell.text.strip() for cell in row.cells))
        text = "\n".join(chunks)
        if not text.strip():
            fail("DOCX không có nội dung chữ có thể trích xuất.")
        return text
    if ext == ".pdf":
        try:
            import pdfplumber
        except ImportError:
            fail("Thiếu pdfplumber. Hãy dùng Python bundled của Codex hoặc cài pdfplumber.")
        pages: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"[Trang {index}]\n{text}")
        if not pages:
            fail("PDF không có lớp chữ. Hãy OCR tài liệu trước khi chạy Agent.")
        return "\n".join(pages)
    fail(f"Định dạng transcript chưa được hỗ trợ: {ext}")
    return ""


def transcribe_media(path: Path, output_dir: Path, model_name: str) -> Path:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        fail(
            "Đầu vào là audio/video nhưng chưa có transcript và faster-whisper chưa được cài. "
            "Hãy truyền --transcript hoặc cài faster-whisper."
        )
    print(f"Đang phiên âm cục bộ bằng faster-whisper model={model_name}...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(path), vad_filter=True)
    lines = []
    for segment in segments:
        stamp = seconds_to_timestamp(float(segment.start))
        lines.append(f"[{stamp}] Chưa xác định: {segment.text.strip()}")
    if not lines:
        fail("Whisper không tạo được segment transcript nào.")
    generated = output_dir / "analysis" / "generated-transcript.txt"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return generated


LINE_RE = re.compile(
    r"^\s*(?:\[(?P<bracket>\d{1,2}:\d{2}(?::\d{2})?)\]|(?P<plain>\d{1,2}:\d{2}(?::\d{2})?))?\s*"
    r"(?P<speaker>[^:\n]{1,80})\s*:\s*(?P<text>.+?)\s*$"
)


def parse_segments(text: str, alias_map: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    segments: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or re.fullmatch(r"\[Trang \d+\]", line):
            continue
        match = LINE_RE.match(line)
        if match:
            source_speaker = match.group("speaker").strip()
            participant = alias_map.get(normalize_key(source_speaker))
            stamp = match.group("bracket") or match.group("plain")
            current = {
                "line": line_no,
                "timestamp": stamp,
                "timestamp_seconds": timestamp_to_seconds(stamp),
                "source_speaker": source_speaker,
                "speaker": participant["name"] if participant else "Chưa xác định",
                "speaker_email": participant["email"] if participant else "",
                "text": match.group("text").strip(),
                "evidence_ref": stamp or f"Dòng {line_no}",
                "speaker_confirmed": bool(participant),
            }
            segments.append(current)
            if not participant:
                reviews.append(
                    {
                        "type": "speaker",
                        "evidence_ref": current["evidence_ref"],
                        "message": f"Không khớp nhãn người nói '{source_speaker}' với danh sách người tham gia.",
                    }
                )
        elif current:
            current["text"] += " " + line
        else:
            current = {
                "line": line_no,
                "timestamp": None,
                "timestamp_seconds": None,
                "source_speaker": "Chưa xác định",
                "speaker": "Chưa xác định",
                "speaker_email": "",
                "text": line,
                "evidence_ref": f"Dòng {line_no}",
                "speaker_confirmed": False,
            }
            segments.append(current)
            reviews.append(
                {
                    "type": "format",
                    "evidence_ref": current["evidence_ref"],
                    "message": "Dòng không có cấu trúc người nói; không suy đoán danh tính.",
                }
            )
    if not segments:
        fail("Không tìm thấy nội dung transcript có thể xử lý.")
    return segments, reviews


def find_deadline(text: str, patterns: list[str]) -> tuple[str, str | None]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group(0).strip()
        iso_value: str | None = None
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                iso_value = datetime.strptime(raw, fmt).date().isoformat()
                break
            except ValueError:
                continue
        return raw, iso_value
    return "Chưa nêu", None


def match_owners(text: str, segment: dict[str, Any], participants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = normalize_key(text)
    candidates: list[dict[str, Any]] = []
    if re.search(r"\b(toi|em|anh|chi|minh)\s+se\b", normalized) and segment["speaker_confirmed"]:
        candidates.append({"name": segment["speaker"], "email": segment["speaker_email"]})
    for person in participants:
        aliases = sorted([person["name"], *person.get("aliases", [])], key=len, reverse=True)
        for alias in aliases:
            key = re.escape(normalize_key(alias))
            owner_pattern = rf"(?:\b{key}\b.{{0,35}}\b(?:phu trach|chiu trach nhiem|se|cam ket)\b|\b(?:giao|phan cong)\b.{{0,25}}\b{key}\b)"
            if re.search(owner_pattern, normalized):
                if not any(item["name"] == person["name"] for item in candidates):
                    candidates.append({"name": person["name"], "email": person["email"]})
                break
    return candidates


def clean_task(text: str, owners: list[dict[str, Any]], deadline_text: str) -> str:
    task = text.strip()
    task = re.sub(r"^(?:tôi|em|anh|chị|mình)\s+sẽ\s+", "", task, flags=re.IGNORECASE)
    task = re.sub(r"^.{1,80}?\s+(?:phụ trách|chịu trách nhiệm|sẽ|cam kết)\s+", "", task, count=1, flags=re.IGNORECASE)
    for owner in owners:
        aliases = [owner["name"]]
        for alias in aliases:
            task = re.sub(
                rf"^{re.escape(alias)}\s+(?:sẽ\s+|phụ trách\s+|chịu trách nhiệm\s+|cam kết\s+)",
                "",
                task,
                flags=re.IGNORECASE,
            )
    if deadline_text != "Chưa nêu":
        task = re.sub(
            rf"(?:,?\s*(?:(?:trước\s+ngày)|hạn|ngày)?\s*)?{re.escape(deadline_text)}[.!]?\s*$",
            "",
            task,
            flags=re.IGNORECASE,
        )
    return task.strip(" .,-") or text.strip()


def analyze(
    segments: list[dict[str, Any]],
    participants: list[dict[str, Any]],
    config: dict[str, Any],
    reviews: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisions: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    max_quote = int(config.get("max_evidence_quote_chars", 320))
    for segment in segments:
        lowered = segment["text"].casefold()
        if any(keyword.casefold() in lowered for keyword in config["decision_keywords"]):
            decision = {
                "id": f"D{len(decisions) + 1:02d}",
                "decision": segment["text"],
                "speaker": segment["speaker"],
                "evidence_quote": segment["text"][:max_quote],
                "evidence_ref": segment["evidence_ref"],
                "timestamp_seconds": segment["timestamp_seconds"],
                "review_status": "Đã xác định" if segment["speaker_confirmed"] else "Cần rà soát",
            }
            decisions.append(decision)
        if not any(keyword.casefold() in lowered for keyword in config["action_keywords"]):
            continue
        owners = match_owners(segment["text"], segment, participants)
        deadline_text, deadline_iso = find_deadline(segment["text"], config["deadline_patterns"])
        owner = owners[0] if len(owners) == 1 else {"name": "Chưa xác định", "email": ""}
        issues: list[str] = []
        if len(owners) == 0:
            issues.append("Không có người phụ trách được nêu rõ")
        elif len(owners) > 1:
            issues.append("Có nhiều người có thể là người phụ trách")
        if deadline_text == "Chưa nêu":
            issues.append("Không có deadline")
        if owner["name"] != "Chưa xác định" and not owner["email"]:
            issues.append("Người phụ trách chưa có email")
        item = {
            "id": f"A{len(actions) + 1:02d}",
            "task": clean_task(segment["text"], owners, deadline_text),
            "owner": owner["name"],
            "owner_email": owner["email"],
            "deadline_text": deadline_text,
            "deadline_iso": deadline_iso,
            "evidence_quote": segment["text"][:max_quote],
            "evidence_ref": segment["evidence_ref"],
            "timestamp_seconds": segment["timestamp_seconds"],
            "review_status": "Cần rà soát" if issues else "Đã xác định",
            "review_reasons": issues,
        }
        actions.append(item)
        for issue in issues:
            reviews.append({"type": "action_item", "item_id": item["id"], "evidence_ref": item["evidence_ref"], "message": issue})
    return decisions, actions


def capture_screenshots(video: Path | None, decisions: list[dict[str, Any]], actions: list[dict[str, Any]], output_dir: Path, width: int) -> tuple[list[dict[str, Any]], list[str]]:
    screenshots: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not video:
        return screenshots, warnings
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        warnings.append("Không tìm thấy FFmpeg; không tạo được screenshot từ video.")
        return screenshots, warnings
    shots_dir = output_dir / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    seen: set[int] = set()
    for kind, items in (("quyet-dinh", decisions), ("cong-viec", actions)):
        for item in items:
            second = item.get("timestamp_seconds")
            if second is None:
                continue
            rounded = int(round(float(second)))
            if rounded in seen:
                continue
            seen.add(rounded)
            filename = f"moc-{rounded:06d}-{kind}-{item['id']}.png"
            target = shots_dir / filename
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(max(0, float(second))),
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                f"scale={width}:-2",
                "-y",
                str(target),
            ]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0 or not target.exists():
                warnings.append(f"Không chụp được mốc {item['evidence_ref']} từ video: {result.stderr.strip()}")
                continue
            screenshots.append(
                {
                    "path": str(target.relative_to(output_dir)).replace("\\", "/"),
                    "timestamp": seconds_to_timestamp(float(second)),
                    "timestamp_seconds": second,
                    "kind": kind,
                    "item_id": item["id"],
                    "caption": item.get("decision") or item.get("task"),
                }
            )
    return screenshots, warnings


def html_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(value)}</th>" for value in headers)
    body = "".join("<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_html(data: dict[str, Any], output_dir: Path) -> Path:
    css = (SKILL_ROOT / "assets" / "report.css").read_text(encoding="utf-8")
    decisions = data["decisions"]
    actions = data["action_items"]
    decision_rows = [
        [
            html.escape(d["id"]),
            html.escape(d["decision"]),
            html.escape(d["speaker"]),
            html.escape(d["evidence_ref"]),
            html.escape(d["review_status"]),
        ]
        for d in decisions
    ] or [["", "Không có quyết định rõ ràng trong nguồn.", "", "", ""]]
    action_rows = [
        [
            html.escape(a["id"]),
            html.escape(a["task"]),
            html.escape(a["owner"]),
            html.escape(a["deadline_text"]),
            html.escape(a["review_status"]),
            f"<span class='muted'>{html.escape(a['evidence_ref'])}: “{html.escape(a['evidence_quote'])}”</span>",
        ]
        for a in actions
    ] or [["", "Không có Action Item rõ ràng trong nguồn.", "", "", "", ""]]
    participant_list = ", ".join(html.escape(p["name"]) for p in data["participants"]) or "Chưa cung cấp"
    review_items = "".join(f"<li>{html.escape(item['message'])} <span class='muted'>({html.escape(item.get('evidence_ref', ''))})</span></li>" for item in data["review_queue"])
    figures = "".join(
        f"<figure><img src='{html.escape(shot['path'])}' alt='Ảnh mốc {html.escape(shot['timestamp'])}'>"
        f"<figcaption>{html.escape(shot['timestamp'])} · {html.escape(shot['caption'])}</figcaption></figure>"
        for shot in data["screenshots"]
    )
    doc = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(data['title'])}</title><style>{css}</style></head><body><main>
<h1>{html.escape(data['title'])}</h1>
<p class="meta">Ngày họp: {html.escape(data['meeting_date'] or 'Chưa nêu')} · Nguồn: {html.escape(data['source']['name'])}</p>
<p><strong>Người tham gia:</strong> {participant_list}</p>
<p class="notice">Tài liệu chỉ phản ánh thông tin có trong nguồn. Các mục “Cần rà soát” chưa nên dùng để giao việc hoặc gửi email.</p>
<h2>Tóm tắt kiểm chứng</h2>
<p>Ghi nhận {len(decisions)} quyết định rõ ràng và {len(actions)} Action Item. Có {len(data['review_queue'])} vấn đề cần rà soát.</p>
<h2>Quyết định</h2>
{html_table(['Mã','Quyết định','Người nói','Dẫn chứng','Trạng thái'], decision_rows)}
<h2>Action Items</h2>
{html_table(['Mã','Công việc','Người phụ trách','Deadline','Trạng thái','Dẫn chứng'], action_rows)}
<h2>Hàng đợi rà soát</h2>
<ul>{review_items or '<li>Không có mục cần rà soát.</li>'}</ul>
<h2>Ảnh tại các mốc quan trọng</h2>
{figures or '<p class="muted">Không có ảnh mốc. Kiểm tra video và timestamp trong nguồn.</p>'}
</main></body></html>"""
    target = output_dir / "bien-ban.html"
    target.write_text(doc, encoding="utf-8")
    return target


def register_pdf_fonts() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("MeetingFont", str(regular)))
            pdfmetrics.registerFont(TTFont("MeetingFontBold", str(bold)))
            return "MeetingFont", "MeetingFontBold"
    return "Helvetica", "Helvetica-Bold"


def build_pdf(data: dict[str, Any], output_dir: Path) -> Path:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Image, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        fail("Thiếu reportlab. Hãy dùng Python bundled của Codex hoặc cài reportlab.")
    regular, bold = register_pdf_fonts()
    target = output_dir / "bien-ban.pdf"
    page_size = landscape(A4)
    doc = SimpleDocTemplate(str(target), pagesize=page_size, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("MeetingTitle", parent=styles["Title"], fontName=bold, fontSize=20, leading=24, textColor=colors.HexColor("#15394A"), spaceAfter=8)
    heading_style = ParagraphStyle("MeetingHeading", parent=styles["Heading2"], fontName=bold, fontSize=13, leading=16, textColor=colors.HexColor("#195B7A"), spaceBefore=13, spaceAfter=7)
    body_style = ParagraphStyle("MeetingBody", parent=styles["BodyText"], fontName=regular, fontSize=9.3, leading=13)
    small_style = ParagraphStyle("MeetingSmall", parent=body_style, fontSize=7.5, leading=10, textColor=colors.HexColor("#43515C"))
    header_style = ParagraphStyle("MeetingHeader", parent=body_style, fontName=bold, textColor=colors.white, alignment=TA_CENTER, fontSize=8)

    def p(value: Any, style=body_style) -> Paragraph:
        return Paragraph(html.escape(str(value)).replace("\n", "<br/>"), style)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(regular, 7)
        canvas.setFillColor(colors.HexColor("#66737F"))
        canvas.drawString(16 * mm, 9 * mm, data["title"][:90])
        canvas.drawRightString(page_size[0] - 16 * mm, 9 * mm, f"Trang {document.page}")
        canvas.restoreState()

    story: list[Any] = [p(data["title"], title_style)]
    story.append(p(f"Ngày họp: {data['meeting_date'] or 'Chưa nêu'} | Nguồn: {data['source']['name']}", small_style))
    story.append(p("Người tham gia: " + (", ".join(item["name"] for item in data["participants"]) or "Chưa cung cấp")))
    story.append(Spacer(1, 5 * mm))
    story.append(p("Tóm tắt kiểm chứng", heading_style))
    story.append(p(f"Ghi nhận {len(data['decisions'])} quyết định rõ ràng và {len(data['action_items'])} Action Item. Có {len(data['review_queue'])} vấn đề cần rà soát. Không dùng mục Cần rà soát để giao việc trước khi xác nhận."))
    story.append(p("Quyết định", heading_style))
    decision_rows = [[p("Mã", header_style), p("Quyết định", header_style), p("Người nói", header_style), p("Dẫn chứng", header_style), p("Trạng thái", header_style)]]
    for item in data["decisions"]:
        decision_rows.append([p(item["id"]), p(item["decision"]), p(item["speaker"]), p(item["evidence_ref"] + ": “" + item["evidence_quote"] + "”", small_style), p(item["review_status"])])
    if len(decision_rows) == 1:
        decision_rows.append([p(""), p("Không có quyết định rõ ràng trong nguồn."), p(""), p(""), p("")])
    decision_table = LongTable(decision_rows, colWidths=[15 * mm, 83 * mm, 35 * mm, 100 * mm, 28 * mm], repeatRows=1)
    decision_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#195B7A")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6DEE5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8FA")]),
    ]))
    story.append(decision_table)
    story.append(p("Action Items", heading_style))
    action_rows = [[p("Mã", header_style), p("Công việc", header_style), p("Người phụ trách", header_style), p("Deadline", header_style), p("Trạng thái", header_style), p("Dẫn chứng", header_style)]]
    for item in data["action_items"]:
        action_rows.append([p(item["id"]), p(item["task"]), p(item["owner"]), p(item["deadline_text"]), p(item["review_status"]), p(item["evidence_ref"] + ": “" + item["evidence_quote"] + "”", small_style)])
    if len(action_rows) == 1:
        action_rows.append([p(""), p("Không có Action Item rõ ràng trong nguồn."), p(""), p(""), p(""), p("")])
    action_table = LongTable(action_rows, colWidths=[14 * mm, 73 * mm, 34 * mm, 28 * mm, 29 * mm, 83 * mm], repeatRows=1)
    action_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#195B7A")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6DEE5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8FA")]),
    ]))
    story.append(action_table)
    story.append(p("Hàng đợi rà soát", heading_style))
    if data["review_queue"]:
        for item in data["review_queue"]:
            story.append(p(f"• {item['message']} ({item.get('evidence_ref', '')})"))
    else:
        story.append(p("Không có mục cần rà soát."))
    if data["screenshots"]:
        story.append(PageBreak())
        story.append(p("Ảnh tại các mốc quan trọng", heading_style))
        figure_cells: list[list[Any]] = []
        current_row: list[Any] = []
        for shot in data["screenshots"]:
            img_path = output_dir / shot["path"]
            image = Image(str(img_path))
            max_width, max_height = 68 * mm, 39 * mm
            ratio = min(max_width / image.imageWidth, max_height / image.imageHeight)
            image.drawWidth = image.imageWidth * ratio
            image.drawHeight = image.imageHeight * ratio
            image.hAlign = "CENTER"
            current_row.append([image, p(f"{shot['timestamp']} | {shot['caption']}", small_style)])
            if len(current_row) == 2:
                figure_cells.append(current_row)
                current_row = []
        if current_row:
            current_row.append("")
            figure_cells.append(current_row)
        figure_grid = Table(figure_cells, colWidths=[128 * mm, 128 * mm], hAlign="CENTER")
        figure_grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(figure_grid)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return target


def write_email_drafts(data: dict[str, Any], output_dir: Path) -> list[Path]:
    drafts_dir = output_dir / "email-drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in data["action_items"]:
        if item["owner"] != "Chưa xác định" and item["owner_email"]:
            grouped[(item["owner"], item["owner_email"])].append(item)
    paths: list[Path] = []
    for (owner, email), items in grouped.items():
        msg = EmailMessage()
        msg["To"] = email
        msg["Subject"] = f"NHÁP - Công việc sau {data['title']}"
        msg["X-Unsent"] = "1"
        lines = [f"Chào {owner},", "", f"Dưới đây là các công việc được ghi nhận từ {data['title']}:", ""]
        for index, item in enumerate(items, start=1):
            lines.extend([
                f"{index}. {item['task']}",
                f"   Deadline: {item['deadline_text']}",
                f"   Dẫn chứng: {item['evidence_ref']} - “{item['evidence_quote']}”",
                "",
            ])
        lines.extend(["Vui lòng kiểm tra lại nội dung và deadline trước khi xác nhận.", "", "Trân trọng,"])
        msg.set_content("\n".join(lines), charset="utf-8")
        path = drafts_dir / f"nhap-{safe_name(owner)}.eml"
        path.write_bytes(msg.as_bytes())
        paths.append(path)
    unresolved = [item for item in data["action_items"] if item["owner"] == "Chưa xác định" or not item["owner_email"]]
    if unresolved:
        note = drafts_dir / "CAN-XAC-NHAN-NGUOI-NHAN.txt"
        note.write_text(
            "Không tạo email nháp cho các mục sau vì thiếu owner hoặc email đã xác nhận:\n\n"
            + "\n".join(f"- {item['id']}: {item['task']} ({'; '.join(item['review_reasons'])})" for item in unresolved),
            encoding="utf-8",
        )
        paths.append(note)
    return paths


def build_xlsx(data_path: Path, output_dir: Path) -> Path:
    node = shutil.which("node")
    if not node:
        fail("Không tìm thấy Node.js; không thể tạo action-items.xlsx bằng Artifact Tool.")
    script = SKILL_ROOT / "scripts" / "generate_xlsx.mjs"
    target = output_dir / "action-items.xlsx"
    preview = output_dir / "analysis" / "action-items-preview.png"
    command = [node, str(script), str(data_path), str(target), str(preview)]
    result = subprocess.run(command, cwd=str(SKILL_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout.strip():
        print(result.stdout.strip())
    for _ in range(25):
        if target.exists() and target.stat().st_size > 0:
            break
        time.sleep(0.2)
    if not target.exists() or target.stat().st_size == 0:
        fail(f"Không tạo được Excel (exit={result.returncode}): {result.stderr.strip()}")
    try:
        with zipfile.ZipFile(target) as archive:
            if "xl/workbook.xml" not in archive.namelist():
                fail("File Excel đã tạo nhưng thiếu cấu trúc workbook.xml.")
    except zipfile.BadZipFile:
        fail("File Excel đã tạo không phải là XLSX hợp lệ.")
    inspect_sidecar = Path(str(target) + ".inspect.ndjson")
    if inspect_sidecar.exists():
        inspect_target = output_dir / "analysis" / "xlsx-inspect.ndjson"
        inspect_target.write_bytes(inspect_sidecar.read_bytes())
        inspect_sidecar.unlink()
    return target


def write_peas_report(data: dict[str, Any], output_dir: Path, warnings: list[str]) -> tuple[Path, Path]:
    unresolved = len(data["review_queue"])
    report = {
        "P": {
            "goal": "Tóm tắt chính xác; giữ quyết định, Action Items, owner, deadline và dẫn chứng; không bịa.",
            "observed": {
                "decisions": len(data["decisions"]),
                "action_items": len(data["action_items"]),
                "review_items": unresolved,
                "all_decisions_have_evidence": all(bool(item["evidence_ref"] and item["evidence_quote"]) for item in data["decisions"]),
                "all_actions_have_evidence": all(bool(item["evidence_ref"] and item["evidence_quote"]) for item in data["action_items"]),
            },
        },
        "E": {
            "local_source": data["source"]["path"],
            "google_drive": "Không truy cập trong lần chạy cục bộ này",
            "gmail": "Không truy cập; chỉ tạo file nháp .eml",
        },
        "A": {
            "read_transcript": True,
            "speaker_matching": True,
            "screenshots_created": len(data["screenshots"]),
            "action_items_extracted": len(data["action_items"]),
            "email_drafts_created": len([item for item in data["action_items"] if item["owner"] != "Chưa xác định" and item["owner_email"]]),
            "email_sent": False,
        },
        "S": {
            "input_type": data["source"]["type"],
            "participants": len(data["participants"]),
            "segments": len(data["segments"]),
        },
        "warnings": warnings,
        "result": "PASS_WITH_REVIEW" if unresolved or warnings else "PASS",
    }
    json_path = output_dir / "analysis" / "peas-report.json"
    write_json(json_path, report)
    md_lines = [
        "# Báo cáo kiểm thử theo PEAS",
        "",
        f"Kết quả: **{report['result']}**",
        "",
        "## P Hiệu quả",
        "",
        f"- {len(data['decisions'])} quyết định; {len(data['action_items'])} Action Item; {unresolved} mục cần rà soát.",
        f"- Dẫn chứng quyết định đầy đủ: {report['P']['observed']['all_decisions_have_evidence']}.",
        f"- Dẫn chứng Action Item đầy đủ: {report['P']['observed']['all_actions_have_evidence']}.",
        "",
        "## E Môi trường",
        "",
        "- Đã xử lý tệp cục bộ. Google Drive và Gmail không được truy cập trong lần chạy này.",
        "",
        "## A Hành động",
        "",
        f"- Tạo {len(data['screenshots'])} screenshot, {len(data['action_items'])} Action Item và email nháp cục bộ. Không gửi email.",
        "",
        "## S Đầu vào",
        "",
        f"- Loại nguồn: {data['source']['type']}; {len(data['participants'])} người tham gia; {len(data['segments'])} lượt nói.",
    ]
    if warnings:
        md_lines.extend(["", "## Cảnh báo", "", *[f"- {warning}" for warning in warnings]])
    md_path = output_dir / "analysis" / "peas-report.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return json_path, md_path


def write_manifest(output_dir: Path) -> Path:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append(
                {
                    "path": str(path.relative_to(output_dir)).replace("\\", "/"),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    target = output_dir / "manifest.json"
    write_json(target, {"generated_at": datetime.now().astimezone().isoformat(), "files": files})
    return target


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input).expanduser().resolve()
    participants_path = Path(args.participants).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if not input_path.is_file():
        fail(f"Không tìm thấy đầu vào: {input_path}")
    if not participants_path.is_file():
        fail(f"Không tìm thấy danh sách người tham gia: {participants_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis").mkdir(exist_ok=True)
    config = read_json(Path(args.config).resolve() if args.config else DEFAULT_CONFIG)
    participants, alias_map = load_participants(participants_path)

    transcript_path: Path
    if args.transcript:
        transcript_path = Path(args.transcript).expanduser().resolve()
        if not transcript_path.is_file():
            fail(f"Không tìm thấy transcript: {transcript_path}")
    elif input_path.suffix.lower() in MEDIA_EXTS:
        transcript_path = transcribe_media(input_path, output_dir, args.whisper_model)
    else:
        transcript_path = input_path
    transcript_text = extract_text(transcript_path)
    normalized_copy = output_dir / "analysis" / "transcript-normalized.txt"
    normalized_copy.write_text(transcript_text.strip() + "\n", encoding="utf-8")
    segments, reviews = parse_segments(transcript_text, alias_map)
    decisions, actions = analyze(segments, participants, config, reviews)

    video: Path | None = None
    if args.video:
        video = Path(args.video).expanduser().resolve()
    elif input_path.suffix.lower() in VIDEO_EXTS:
        video = input_path
    if video and not video.is_file():
        fail(f"Không tìm thấy video: {video}")
    screenshots, warnings = capture_screenshots(video, decisions, actions, output_dir, int(config.get("screenshot_width", 960)))
    for warning in warnings:
        reviews.append({"type": "screenshot", "evidence_ref": "", "message": warning})

    source_kind = "media" if input_path.suffix.lower() in MEDIA_EXTS else input_path.suffix.lower().lstrip(".")
    data = {
        "title": args.title,
        "meeting_date": args.meeting_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": {"path": str(input_path), "name": input_path.name, "type": source_kind, "sha256": sha256_file(input_path)},
        "transcript_source": {"path": str(transcript_path), "sha256": sha256_file(transcript_path)},
        "participants": participants,
        "segments": segments,
        "decisions": decisions,
        "action_items": actions,
        "screenshots": screenshots,
        "review_queue": reviews,
        "safety": {"email_sent": False, "external_upload": False},
    }
    data_path = output_dir / "analysis" / "meeting_data.json"
    write_json(data_path, data)
    write_json(output_dir / "analysis" / "review_queue.json", reviews)
    build_html(data, output_dir)
    build_pdf(data, output_dir)
    build_xlsx(data_path, output_dir)
    write_email_drafts(data, output_dir)
    write_peas_report(data, output_dir, warnings)
    write_manifest(output_dir)
    print(json.dumps({"status": "ok", "output": str(output_dir), "decisions": len(decisions), "actions": len(actions), "review_items": len(reviews)}, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tạo biên bản họp có dẫn chứng, Action Items, Excel và email nháp.")
    parser.add_argument("--input", required=True, help="Transcript TXT/DOCX/PDF hoặc audio/video")
    parser.add_argument("--transcript", help="Transcript đi kèm khi --input là audio/video")
    parser.add_argument("--participants", required=True, help="JSON danh sách người tham gia")
    parser.add_argument("--video", help="Video dùng để chụp ảnh tại các mốc")
    parser.add_argument("--output", required=True, help="Thư mục đầu ra")
    parser.add_argument("--title", default="Biên bản cuộc họp", help="Tiêu đề biên bản")
    parser.add_argument("--meeting-date", default="", help="Ngày họp; chỉ dùng để hiển thị, không suy ra deadline")
    parser.add_argument("--config", help="JSON cấu hình; mặc định config/default.json")
    parser.add_argument("--whisper-model", default="small", help="Model faster-whisper cục bộ")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
