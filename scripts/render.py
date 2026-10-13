"""Bước 4 – Xuất bản: hình ảnh (screenshot video / minh hoạ audio), biên bản HTML + PDF dạng ebook, Excel, email."""
from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

import illustrate as ill
from emails import build_emails, deadline_label
from excel import build_xlsx
from mmlib import (ASSETS, UNKNOWN, AgentError, find_browser, find_ffmpeg, load_config, log, read_json, sec_to_ts,
                   ts_to_sec, write_json)


# ------------------------------------------------------------------ hình ảnh
def grab_frame(video: str, t: float, dst: Path) -> bool:
    ff = find_ffmpeg()
    from PIL import Image, ImageStat
    for dt in (0, 1.5, 3.0, -1.5):
        tt = max(0.0, t + dt)
        r = subprocess.run([ff, "-y", "-v", "error", "-ss", f"{tt:.2f}", "-i", video, "-frames:v", "1",
                            "-vf", "scale='min(1280,iw)':-2", "-q:v", "4", str(dst)], capture_output=True, timeout=120)
        if r.returncode == 0 and dst.exists() and dst.stat().st_size > 0:
            with Image.open(dst) as im:
                if sum(ImageStat.Stat(im.convert("L")).mean) > 14:  # bỏ khung hình đen
                    return True
    return dst.exists()


def b64img(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def make_images(m: dict[str, Any], out: Path) -> dict[str, Any]:
    media = m["_media"]
    img = out / "hinh-anh"
    img.mkdir(exist_ok=True)
    res: dict[str, Any] = {"mode": media["kind"], "moments": [], "notes": []}
    for n, km in enumerate(m.get("key_moments", []), 1):
        entry = {"n": n, "moment": km, "file": None, "kind": None}
        if media["kind"] == "video" and km.get("seconds") is not None:
            f = img / f"moc-{n:02d}-{sec_to_ts(km['seconds']).replace(':', '')}.jpg"
            if grab_frame(media["path"], km["seconds"], f):
                entry.update(file=f, kind="screenshot")
            else:
                res["notes"].append(f"Không chụp được hình tại {km['time']} → dùng hình minh hoạ thay thế")
        if entry["file"] is None and media["kind"] != "video" or (media["kind"] == "video" and entry["file"] is None):
            f = img / f"minh-hoa-{n:02d}.svg"
            f.write_text(ill.moment_card(km, n), encoding="utf-8")
            entry.update(file=f, kind="illustration")
        res["moments"].append(entry)
    # đồ hoạ tổng quan
    for t in m.get("timeline", []):
        t["_start"] = ts_to_sec(t.get("start")) if t.get("start") else (t["evidence"][0]["seconds"] if t.get("evidence") else None)
        t["_end"] = ts_to_sec(t.get("end")) if t.get("end") else None
    tl = m.get("timeline", [])
    for i, t in enumerate(tl):
        if t["_end"] is None:
            t["_end"] = tl[i + 1]["_start"] if i + 1 < len(tl) else media.get("duration")
    if media.get("path") and media.get("duration"):
        env = ill.audio_envelope(media["path"])
        if env:
            svg = ill.waveform_svg(env, media["duration"], m.get("key_moments", []), tl)
            (img / "dang-song-cuoc-hop.svg").write_text(svg, encoding="utf-8")
            res["waveform"] = svg
    return res


# ------------------------------------------------------------------ HTML
def ev_html(evs: list[dict[str, Any]], media: dict[str, Any]) -> str:
    out = []
    for e in evs:
        where = e["time"] or (f'dòng {e["line"]}' if e.get("line") else "")
        if e["time"] and media.get("path") and media["kind"] in ("video", "audio"):
            uri = Path(media["path"]).as_uri() + f"#t={int(e['seconds'] or 0)}"
            where = f'<a href="{uri}" title="Mở bản ghi tại thời điểm này">{escape(e["time"])}</a>'
        cls = "ev near" if e["status"] != "nguyên văn" else "ev"
        out.append(f'<blockquote class="{cls}"><span class="meta">⏱ {where} · {escape(e["speaker"])} · {e["seg"]}'
                   f'{" · gần khớp" if e["status"] != "nguyên văn" else ""}</span>“{escape(e["quote"])}”</blockquote>')
    return "".join(out)


def opt(pre: str, value: Any, post: str) -> str:
    return pre + escape(str(value)) + post if value else ""


def li_task(a: dict[str, Any]) -> str:
    return "<li>" + escape(a.get("task", "")) + " — <b>" + escape(deadline_label(a)) + "</b></li>"


def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return (parts[-1][0] if parts else "?").upper()


def build_html(m: dict[str, Any], out: Path, images: dict[str, Any]) -> Path:
    css = (ASSETS / "ebook.css").read_text(encoding="utf-8")
    meeting, media, val = m.get("meeting", {}), m["_media"], m["_validation"]
    title = meeting.get("title") or "Biên bản cuộc họp"
    d = meeting.get("date")
    try:
        d_fmt = date.fromisoformat(d).strftime("%d/%m/%Y") if d else "Chưa nêu"
    except ValueError:
        d_fmt = d
    participants = m.get("_participants", [])
    smap = m.get("speaker_map", {})
    speakers_named = sorted({(v.get("name") if isinstance(v, dict) else v) for v in smap.values()} - {UNKNOWN, None, ""})
    n_people = len(participants) or len(speakers_named)
    dur = media.get("duration_ts") or "—"
    acts, decs = m.get("action_items", []), m.get("decisions", [])
    gen = time.strftime("%d/%m/%Y %H:%M")
    st = val["stats"]

    first_shot = next((e for e in images["moments"] if e["kind"] == "screenshot"), None)
    cover_shot = f'<img class="cover-shot" src="{b64img(first_shot["file"])}" alt="Khung hình từ video">' if first_shot else ""
    chips = [f"📅 {escape(d_fmt)}", f"⏱ {escape(dur)}", f"👥 {n_people} người",
             {"video": "🎬 Có video", "audio": "🎙 Bản ghi âm", "transcript": "📝 Transcript"}[media["kind"]]]

    ch = 0

    def chapter(title_: str, kicker: str, body: str, anchor: str) -> str:
        nonlocal ch
        ch += 1
        return (f'<section class="page chapter" id="{anchor}"><div class="ch-head"><div class="ch-num">{ch:02d}</div>'
                f'<div><small>{escape(kicker)}</small><h2>{escape(title_)}</h2></div></div>{body}</section>')

    # --- tổng quan
    info_rows = [("Thời gian", f'{d_fmt}{" · " + meeting["start_time"] if meeting.get("start_time") else ""} · thời lượng {dur}'),
                 ("Địa điểm / hình thức", meeting.get("location") or "Chưa nêu"),
                 ("Chủ trì", meeting.get("chair") or "Chưa nêu"),
                 ("Mục đích", meeting.get("purpose") or "Chưa nêu"),
                 ("Thành phần", ", ".join(p["name"] for p in participants) or ", ".join(speakers_named) or "Chưa nêu"),
                 ("Nguồn dữ liệu", m.get("_transcript_source", ""))]
    def chips_of(evs):
        return "".join("<span class=evchip>⏱ " + escape(e["time"] or e["seg"]) + "</span>" for e in evs[:2])

    summary_items = "".join(f'<li>{escape(s.get("text", ""))}{chips_of(s["evidence"])}</li>' for s in m.get("summary", []))
    toc = ['<a href="#dien-bien"><span>01</span>Diễn biến cuộc họp</a>', '<a href="#quyet-dinh"><span>02</span>Quyết định & ý chính</a>',
           '<a href="#hinh-anh"><span>03</span>Khoảnh khắc quan trọng</a>', '<a href="#ke-hoach"><span>04</span>Kế hoạch hành động</a>',
           '<a href="#van-de"><span>05</span>Vấn đề còn mở</a>', '<a href="#phu-luc"><span>06</span>Phụ lục & kiểm chứng</a>']
    overview = f"""<section class="page" id="tong-quan">
<div class="ch-head"><div><small>Tổng quan</small><h2>Tóm tắt điều hành</h2></div></div>
<div class="kpis"><div class="kpi"><b>{len(decs)}</b><span>Quyết định</span></div><div class="kpi"><b>{len(acts)}</b><span>Công việc</span></div>
<div class="kpi"><b>{n_people}</b><span>Người tham dự</span></div><div class="kpi"><b>{st['evidence_verified_rate']:.0%}</b><span>Dẫn chứng đã kiểm chứng</span></div></div>
<table class="info">{''.join(f'<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>' for k, v in info_rows)}</table>
<h3>Những điểm cốt lõi</h3><ul class="summary">{summary_items}</ul></section>"""

    # --- 1. diễn biến
    tl_html = []
    for t in m.get("timeline", []):
        rng = " – ".join(x for x in [sec_to_ts(t.get("_start")) if t.get("_start") is not None else "",
                                     sec_to_ts(t.get("_end")) if t.get("_end") is not None else ""] if x)
        tl_html.append(f'<div class="tl-item"><div class="tl-time">{escape(rng)}</div><h4>{escape(t.get("topic", ""))}</h4>'
                       f'<p>{escape(t.get("summary", ""))}</p>{ev_html(t["evidence"][:1], media)}</div>')
    wave = ""
    if images.get("waveform"):
        wave = (f'<div class="figure-wide">{images["waveform"]}<p class="small muted">Dạng sóng âm thanh thật của bản ghi; '
                f'thanh màu phía trên là các chủ đề, số tròn cam là các mốc quan trọng ở chương 03.</p></div>')
    talk: dict[str, float] = {}
    overrides = m.get("speaker_overrides") or {}
    for s in read_json(out / "work" / "transcript.json")["segments"]:
        v = overrides.get(s["id"]) or smap.get(s["speaker"])
        nm = v.get("name") if isinstance(v, dict) else (v or s["speaker"])
        if s.get("start") is not None and s.get("end") is not None:
            talk[nm or UNKNOWN] = talk.get(nm or UNKNOWN, 0) + max(0, s["end"] - s["start"])
    charts = ""
    owner_counts: dict[str, int] = {}
    for a in acts:
        owner_counts[a["owner"]] = owner_counts.get(a["owner"], 0) + 1
    donut = ill.donut_svg(sorted(talk.items(), key=lambda x: -x[1])[:6], "Thời lượng phát biểu") if talk and sum(talk.values()) > 0 else ""
    bars = ill.bars_svg(sorted(owner_counts.items(), key=lambda x: -x[1]), "Số việc theo người phụ trách") if owner_counts else ""
    if donut or bars:
        charts = f'<div class="charts"><div>{donut}</div><div>{bars}</div></div>'
    lead = escape(meeting.get("purpose") or (m.get("summary") or [{"text": ""}])[0].get("text", ""))
    body1 = f'<p class="lead">{lead}</p>{wave}<div class="timeline">{"".join(tl_html)}</div>{charts}'

    # --- 2. quyết định
    dec_html = "".join(
        f'<div class="card decision"><span class="tag green">{escape(x["id"])}</span><span class="tag">Đã chốt</span>'
        f'<h4>{escape(x.get("text", ""))}</h4>{opt("<p class=muted>", x.get("rationale"), "</p>")}'
        f'{ev_html(x["evidence"], media)}</div>' for x in decs) or '<p class="muted">Cuộc họp không có quyết định nào được chốt rõ ràng.</p>'

    # --- 3. hình ảnh
    figs = []
    notice = ""
    if images["mode"] == "video":
        notice = '<p class="notice">Các hình dưới đây là <b>ảnh chụp thật từ video</b> cuộc họp tại đúng thời điểm ghi bên dưới.</p>'
    else:
        notice = ('<p class="notice">Nguồn chỉ có <b>âm thanh</b>' if images["mode"] == "audio" else '<p class="notice">Nguồn chỉ có <b>văn bản</b>') + \
                 (', nên các hình dưới đây là <b>hình minh hoạ được tạo tự động từ nội dung</b> — không phải ảnh chụp cuộc họp '
                  'và không dùng làm bằng chứng.</p>')
    for e in images["moments"]:
        km = e["moment"]
        if e["kind"] == "screenshot":
            visual = f'<img src="{b64img(e["file"])}" alt="{escape(km.get("title", ""))}">'
            kind = "Ảnh chụp từ video"
        else:
            visual = f'<div class="svgwrap">{e["file"].read_text(encoding="utf-8")}</div>'
            kind = "Hình minh hoạ"
        figs.append(f'<figure>{visual}<figcaption><b>Hình {e["n"]}. {escape(km.get("title", ""))}</b> — {kind}, '
                    f'⏱ {escape(km.get("time", ""))}. {escape(km.get("caption", ""))}{ev_html(km["evidence"][:1], media)}</figcaption></figure>')
    body3 = notice + ("".join(figs) or '<p class="muted">Không có mốc quan trọng nào được chọn.</p>')

    # --- 4. kế hoạch hành động
    rows = []
    for a in acts:
        owner = (f'<span class="unknown">{UNKNOWN}</span>' if a["owner"] == UNKNOWN else escape(a["owner"]))
        sup = f'<br><span class="small muted">Phối hợp: {escape(", ".join(a["supporters"]))}</span>' if a.get("supporters") else ""
        pr = {"Cao": "red", "Thấp": "plum"}.get(a.get("priority"), "orange")
        rows.append(f'<tr><td><b>{escape(a["id"])}</b></td><td>{escape(a.get("task", ""))}'
                    f'{opt("<br><span class=muted style=font-size:13px>Bàn giao: ", a.get("deliverable"), "</span>")}</td>'
                    f'<td>{owner}{sup}</td><td>{escape(deadline_label(a))}</td><td><span class="tag {pr}">{escape(a.get("priority", ""))}</span></td>'
                    f'<td class="small">{"<br>".join(escape((e["time"] or e["seg"]) + " · " + e["speaker"]) for e in a["evidence"])}</td></tr>')
    table = ('<table class="actions"><tr><th>Mã</th><th>Công việc</th><th>Phụ trách</th><th>Thời hạn</th><th>Ưu tiên</th><th>Căn cứ</th></tr>'
             + "".join(rows) + "</table>") if rows else '<p class="muted">Không có công việc nào được giao.</p>'
    people = []
    for i, (owner, n) in enumerate(sorted(owner_counts.items(), key=lambda x: -x[1])):
        if owner == UNKNOWN:
            continue
        col = ill.PALETTE[i % len(ill.PALETTE)]
        mine = [a for a in acts if a["owner"] == owner]
        p = next((p for p in participants if p["name"] == owner), {})
        people.append(f'<div class="card person"><div class="avatar" style="background:{col}">{escape(initials(owner))}</div><div>'
                      f'<h4 style="margin:0">{escape(owner)} <span class="small muted">{escape(p.get("role", ""))}</span></h4>'
                      f'<ul>{"".join(li_task(a) for a in mine)}</ul></div></div>')
    unk = [a for a in acts if a["owner"] == UNKNOWN]
    unk_note = (f'<p class="notice">Có {len(unk)} công việc <b>chưa xác định người phụ trách</b> vì cuộc họp không nêu rõ — '
                f'cần chủ trì phân công.</p>') if unk else ""
    body4 = table + unk_note + "<h3>Theo từng người</h3>" + "".join(people)

    # --- 5. vấn đề mở
    body5 = "".join(f'<div class="card issue"><span class="tag orange">{escape(x["id"])}</span><span class="tag orange">Chưa giải quyết</span>'
                    f'<h4>{escape(x.get("text", ""))}</h4>{ev_html(x["evidence"], media)}</div>' for x in m.get("open_issues", [])) \
        or '<p class="muted">Không có vấn đề nào còn bỏ ngỏ.</p>'

    # --- 6. phụ lục
    prow = "".join(f'<tr><td>{escape(p["name"])}</td><td>{escape(p.get("role", ""))}</td>'
                   f'<td>{escape(p.get("email", "")) or "<span class=bad>Chưa có</span>"}</td></tr>' for p in participants)
    srow = "".join(f'<tr><td>{escape(k)}</td><td>{escape((v.get("name") if isinstance(v, dict) else v) or UNKNOWN)}</td>'
                   f'<td>{escape(v.get("basis", "") if isinstance(v, dict) else "")}</td>'
                   f'<td>{escape(v.get("confidence", "") if isinstance(v, dict) else "")}</td></tr>' for k, v in smap.items())
    if overrides:
        srow += "".join(f'<tr><td>Đoạn {escape(k)}</td><td>{escape(v.get("name", ""))}</td><td>{escape(v.get("basis", ""))}</td>'
                        f'<td>sửa theo ngữ cảnh</td></tr>' for k, v in overrides.items() if isinstance(v, dict))
    warn = "".join(f"<li>{escape(w)}</li>" for w in val["warnings"]) or "<li>Không có cảnh báo.</li>"
    notes = "".join(f"<li>{escape(n)}</li>" for n in m.get("notes_for_reviewer", []))
    body6 = f"""<h3>A. Thành phần tham dự</h3><table class="plain"><tr><th>Họ tên</th><th>Vai trò</th><th>Email</th></tr>{prow or '<tr><td colspan=3>Không có danh sách</td></tr>'}</table>
<h3>B. Nhận diện người nói</h3><table class="plain"><tr><th>Nhãn trong bản ghi</th><th>Xác định là</th><th>Căn cứ</th><th>Độ tin cậy</th></tr>{srow}</table>
<h3>C. Kiểm chứng tự động</h3><table class="plain">
<tr><th>Dẫn chứng khớp nguyên văn transcript</th><td class="ok">{st['evidence_exact']}/{st['evidence_total']}</td></tr>
<tr><th>Dẫn chứng gần khớp (lỗi phiên âm nhỏ)</th><td>{st['evidence_near']}</td></tr>
<tr><th>Dẫn chứng không tìm thấy</th><td class="{'ok' if st['evidence_failed'] == 0 else 'bad'}">{st['evidence_failed']}</td></tr>
<tr><th>Công việc có người phụ trách</th><td>{st['actions_with_owner']}/{st['action_items']}</td></tr>
<tr><th>Công việc có thời hạn</th><td>{st['actions_with_deadline']}/{st['action_items']}</td></tr>
<tr><th>Đoạn có từ khoá quyết định/giao việc chưa xử lý</th><td class="ok">{st['coverage_keywords_unhandled']}</td></tr></table>
<p class="small muted">Mọi quyết định, công việc và nhận định trong tài liệu đều gắn với câu nói gốc (mã đoạn S…, thời điểm, người nói). Thông tin cuộc họp không nêu được ghi “Chưa nêu” / “{UNKNOWN}”, không suy đoán.</p>
<h3>D. Lưu ý khi đọc</h3><ul class="small">{warn}{notes}</ul>
<p class="colophon">Biên bản được lập tự động bởi Agent Biên bản họp · {gen}<br>Nguồn: {escape(m.get('_transcript_source', ''))}</p>"""

    html = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} — Biên bản</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;700;800&family=Lora:ital,wght@0,500;0,700;1,500&display=swap" rel="stylesheet">
<style>{css}</style></head><body>
<div class="toolbar"><b>📘 {escape(title)}</b><button onclick="window.print()">In / Lưu PDF</button></div>
<main class="book">
<section class="cover"><div class="cover-art">{ill.cover_art(title)}</div>
<div><div class="kicker">Biên bản cuộc họp</div><h1>{escape(title)}</h1>
<div class="sub">{escape(meeting.get("purpose") or "")}</div>
<div class="cover-meta">{''.join(f'<span class="chip">{escape(c)}</span>' for c in chips)}</div>{cover_shot}</div>
<nav class="toc cover-toc"><div class="kicker">Nội dung</div>{''.join(toc)}</nav>
<div class="cover-foot"><span>Chủ trì: {escape(meeting.get("chair") or "Chưa nêu")}</span><span>Lập ngày {gen}</span></div></section>
{overview}
{chapter("Diễn biến cuộc họp", "Chương 1", body1, "dien-bien")}
{chapter("Quyết định & ý chính", "Chương 2", dec_html, "quyet-dinh")}
{chapter("Khoảnh khắc quan trọng", "Chương 3", body3, "hinh-anh")}
{chapter("Kế hoạch hành động", "Chương 4", body4, "ke-hoach")}
{chapter("Vấn đề còn mở", "Chương 5", body5, "van-de")}
{chapter("Phụ lục & kiểm chứng", "Chương 6", body6, "phu-luc")}
</main></body></html>"""
    path = out / "bien-ban.html"
    path.write_text(html, encoding="utf-8")
    return path


def html_to_pdf(html: Path, pdf: Path) -> Path | None:
    browser = find_browser()
    if not browser:
        log("   ⚠ Không tìm thấy Edge/Chrome để xuất PDF → mở file HTML và bấm 'In / Lưu PDF'.")
        return None
    with tempfile.TemporaryDirectory() as prof:
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               f"--user-data-dir={prof}", "--no-pdf-header-footer", "--virtual-time-budget=15000",
               "--run-all-compositor-stages-before-draw", f"--print-to-pdf={pdf.resolve()}", html.resolve().as_uri()]
        try:
            pdf.unlink(missing_ok=True)
            subprocess.run(cmd, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired:
            log("   ⚠ Xuất PDF quá thời gian chờ.")
    if pdf.exists() and pdf.stat().st_size > 1000 and pdf_pages(pdf) > 0:
        return pdf
    log("   ⚠ Xuất PDF thất bại → mở bien-ban.html và bấm 'In / Lưu PDF' (chọn Save as PDF).")
    return None


def pdf_pages(pdf: Path) -> int:
    import re
    data = pdf.read_bytes()
    return len(re.findall(rb"/Type\s*/Page(?!s)", data))


def write_peas(m: dict[str, Any], out: Path, images: dict[str, Any], outputs: dict[str, Any], emails: dict[str, Any]) -> Path:
    val, media = m["_validation"], m["_media"]
    st = val["stats"]
    run_log = read_json(out / "work" / "run_log.json")
    shots = sum(1 for e in images["moments"] if e["kind"] == "screenshot")
    illus = sum(1 for e in images["moments"] if e["kind"] == "illustration")
    lines = [f"# Báo cáo PEAS — {m.get('meeting', {}).get('title', '')}", "",
             f"Thời điểm lập: {time.strftime('%Y-%m-%d %H:%M')}", "",
             "## P — Kết quả (Performance)", "",
             "| Tiêu chí | Kết quả |", "|---|---|",
             f"| Dẫn chứng khớp transcript | {st['evidence_exact'] + st['evidence_near']}/{st['evidence_total']} "
             f"({st['evidence_verified_rate']:.0%}); không tìm thấy: {st['evidence_failed']} |",
             f"| Quyết định được ghi nhận | {st['decisions']} |",
             f"| Công việc | {st['action_items']} — có người phụ trách {st['actions_with_owner']}, có thời hạn {st['actions_with_deadline']} |",
             f"| Chống bỏ sót: đoạn có từ khoá quyết định/giao việc chưa xử lý | {st['coverage_keywords_unhandled']} |",
             f"| Đoạn transcript được trích dẫn | {st['segments_cited']}/{st['segments']} |",
             f"| Hình ảnh | {shots} ảnh chụp từ video, {illus} hình minh hoạ |",
             f"| Email giao việc | {len(emails['emails'])} bản nháp; thiếu email: {', '.join(emails['missing']) or 'không'} |", "",
             "## E — Môi trường (Environment)", "",
             f"- Thư mục đầu ra: `{out}`",
             f"- Đầu vào: {', '.join(run_log.get('inputs', []))}",
             f"- Gmail/Google Drive: dùng connector có sẵn của Claude; email chỉ gửi sau phê duyệt.", "",
             "## A — Hành động (Actions)", "", "| Bước | Trạng thái | Chi tiết | Giây |", "|---|---|---|---|"]
    for s in run_log.get("steps", []) + outputs.get("steps", []):
        lines.append(f"| {s['step']} | {s['status']} | {s.get('detail', '')} | {s.get('seconds', '')} |")
    lines += ["", "## S — Đầu vào (Sensors)", "",
              f"- Loại nguồn: **{media['kind']}**{' — thời lượng ' + media.get('duration_ts', '') if media.get('duration_ts') else ''}",
              f"- Transcript: {m.get('_transcript_source', '')}",
              f"- Người tham gia: {len(m.get('_participants', []))} người", "",
              "## Cảnh báo & việc cần người dùng xử lý", ""]
    lines += [f"- {w}" for w in val["warnings"]] or ["- Không có"]
    if emails["missing"]:
        lines.append(f"- **Cần bổ sung email** cho: {', '.join(emails['missing'])}")
    lines += [f"- {n}" for n in images.get("notes", [])]
    p = out / "bao-cao-PEAS.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def manifest(out: Path) -> None:
    files = []
    for f in sorted(out.rglob("*")):
        if f.is_file() and "work" not in f.relative_to(out).parts[:1]:
            files.append({"file": str(f.relative_to(out)), "bytes": f.stat().st_size,
                          "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    write_json(out / "manifest.json", {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "files": files})


def open_file(p: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except Exception as e:  # không mở được cũng không sao
        log(f"   (không tự mở được {p.name}: {e})")


def render(out: Path, open_after: bool = True, only_emails: bool = False, minutes_link: str = "",
           layout: str | None = None, password: str = "") -> dict[str, Any]:
    rp = out / "work" / "minutes.resolved.json"
    if not rp.exists():
        raise AgentError("Chưa có dữ liệu đã kiểm chứng.", "Chạy bước validate và sửa hết lỗi trước khi xuất bản.")
    m = read_json(rp)
    if not m["_validation"]["ok"]:
        raise AgentError("Kiểm chứng chưa đạt — không xuất bản biên bản có thông tin chưa kiểm chứng.")
    # cập nhật email mới nhất từ danh sách người tham gia
    m["_participants"] = read_json(out / "work" / "participants.json")
    emails_by = {p["name"]: p.get("email", "") for p in m["_participants"]}
    for a in m.get("action_items", []):
        a["owner_email"] = emails_by.get(a["owner"], "")
    steps = []
    t0 = time.time()
    pdf = out / "bien-ban.pdf"
    if only_emails:
        build_xlsx(m, out / "action-items.xlsx")
        em = build_emails(m, out, pdf if pdf.exists() else None, minutes_link)
        log(f"✅ Đã soạn lại {len(em['emails'])} email. Thiếu email: {', '.join(em['missing']) or 'không'}")
        return {"emails": em}
    images = make_images(m, out)
    steps.append({"step": "Tạo hình ảnh", "status": "ok", "seconds": round(time.time() - t0, 1),
                  "detail": f"{sum(1 for e in images['moments'] if e['kind'] == 'screenshot')} ảnh chụp video, "
                            f"{sum(1 for e in images['moments'] if e['kind'] == 'illustration')} minh hoạ"})
    t1 = time.time()
    cfg = load_config()
    layout = layout or cfg.get("layout", "compact")
    max_pages = int(cfg.get("max_pages", 4))
    if layout == "compact":
        from compact import render_compact
        html, pdf_ok, pages, n_img, tl_imgs = render_compact(m, out, images, max_pages)
        steps.append({"step": "Dựng biên bản gọn (HTML + PDF)", "status": "ok" if pdf_ok else "lỗi", "seconds": round(time.time() - t1, 1),
                      "detail": f"{pages} trang (tối đa {max_pages}), {n_img} hình trong phần diễn biến" if pdf_ok else "dùng HTML thay thế"})
        if pdf_ok and pages > max_pages:
            images.setdefault("notes", []).append(f"Biên bản dài {pages} trang, vượt mức tối đa {max_pages} dù đã thu gọn — "
                                                  "nên rút gọn nội dung minutes.json (ít mục diễn biến hơn, câu ngắn hơn)")
    else:
        tl_imgs = None
        html = build_html(m, out, images)
        steps.append({"step": "Dựng biên bản HTML (ebook)", "status": "ok", "detail": html.name, "seconds": round(time.time() - t1, 1)})
        t1 = time.time()
        pdf_ok = html_to_pdf(html, pdf)
        steps.append({"step": "Xuất PDF", "status": "ok" if pdf_ok else "lỗi",
                      "detail": f"{pdf_pages(pdf)} trang" if pdf_ok else "dùng HTML thay thế", "seconds": round(time.time() - t1, 1)})
    reader_html = None
    if cfg.get("reader", True):
        t1 = time.time()
        from reader import build_reader
        if tl_imgs is None:
            from compact import timeline_images
            tl_imgs = timeline_images(m, out, images)
        m["_segments"] = read_json(out / "work" / "transcript.json")["segments"]
        reader_html, _ = build_reader(m, out, tl_imgs, password)
        steps.append({"step": "Tạo trình đọc biên bản (web)", "status": "ok", "seconds": round(time.time() - t1, 1),
                      "detail": "có mật khẩu" if password else "không đặt mật khẩu"})
    t1 = time.time()
    xlsx = build_xlsx(m, out / "action-items.xlsx")
    steps.append({"step": "Xuất Excel Action Items", "status": "ok", "detail": xlsx.name, "seconds": round(time.time() - t1, 1)})
    t1 = time.time()
    em = build_emails(m, out, pdf_ok, minutes_link)
    steps.append({"step": "Soạn email giao việc", "status": "ok", "seconds": round(time.time() - t1, 1),
                  "detail": f"{len(em['emails'])} email, thiếu địa chỉ: {len(em['missing'])}"})
    peas = write_peas(m, out, images, {"steps": steps}, em)
    manifest(out)
    log("")
    log("✅ ĐÃ XUẤT BẢN BIÊN BẢN")
    log(f"   📘 HTML : {html}")
    log(f"   📄 PDF  : {pdf if pdf_ok else '(chưa tạo được)'}" + (f" — {pdf_pages(pdf)} trang" if pdf_ok else ""))
    if reader_html:
        log(f"   📱 Đọc web: {reader_html}  (bản đăng claude.ai: {out / 'artifact' / 'bien-ban-doc.html'})")
    log(f"   📊 Excel: {xlsx}")
    log(f"   ✉  Email: {out / 'email' / 'xem-truoc-email.html'} ({len(em['emails'])} bản nháp)")
    log(f"   📋 PEAS : {peas}")
    if em["missing"]:
        log(f"   ⚠ THIẾU EMAIL: {', '.join(em['missing'])} → hỏi người dùng rồi chạy: mm.py set-email")
    for n in images.get("notes", []):
        log(f"   ⚠ {n}")
    if open_after:
        open_file(html)
        if pdf_ok:
            open_file(pdf)
    return {"html": html, "pdf": pdf_ok, "xlsx": xlsx, "emails": em, "images": images}
