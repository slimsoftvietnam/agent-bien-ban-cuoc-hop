"""Biên bản dạng gọn (mặc định): tối đa N trang, ảnh dẫn chứng nằm ngay trong từng mục Diễn biến."""
from __future__ import annotations

import base64
import time
from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

import illustrate as ill
from emails import deadline_label
from mmlib import ASSETS, UNKNOWN, sec_to_ts


def _signature(path: Path):
    from PIL import Image
    with Image.open(path) as im:
        return list(im.convert("L").resize((32, 18)).getdata())


def _same(a, b, tol: float = 6.0) -> bool:
    return a is not None and b is not None and sum(abs(x - y) for x, y in zip(a, b)) / len(a) < tol


def _thumb_b64(path: Path, width: int = 760) -> str:
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, int(im.height * width / im.width)))
        buf = BytesIO()
        im.save(buf, "JPEG", quality=72, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def timeline_images(m: dict[str, Any], out: Path, images: dict[str, Any]) -> list[dict[str, Any] | None]:
    """Gán cho mỗi mục diễn biến 1 hình: ảnh chụp video tại mốc quan trọng nằm trong mục (hoặc tại thời điểm
    dẫn chứng của mục); bỏ hình trùng slide với hình đã dùng. Audio/transcript: hình minh hoạ của mốc trong mục."""
    from render import grab_frame
    media = m["_media"]
    tl = m.get("timeline", [])
    moments = images.get("moments", [])
    used_sigs: list = []
    result: list[dict[str, Any] | None] = []
    for i, t in enumerate(tl):
        a = t.get("_start")
        b = t.get("_end") if t.get("_end") is not None else float("inf")
        km = next((e for e in moments if e["moment"].get("seconds") is not None and a is not None
                   and a <= e["moment"]["seconds"] < b), None)
        entry = None
        if media["kind"] == "video":
            f = km["file"] if km and km["kind"] == "screenshot" else None
            if f is None and t.get("evidence") and t["evidence"][0].get("seconds") is not None:
                f = out / "hinh-anh" / f"dien-bien-{i + 1:02d}.jpg"
                if not grab_frame(media["path"], t["evidence"][0]["seconds"] + 1.0, f):
                    f = None
            if f is not None:
                sig = _signature(f)
                if any(_same(sig, s) for s in used_sigs):
                    f = None  # cùng slide với hình đã hiển thị → không lặp lại
                else:
                    used_sigs.append(sig)
            if f is not None:
                when = km["moment"]["time"] if km else sec_to_ts(t["evidence"][0]["seconds"] + 1.0)
                entry = {"kind": "screenshot", "src": _thumb_b64(f), "caption": f"Ảnh chụp từ video lúc {when}"}
        elif km is not None:
            entry = {"kind": "illustration", "svg": km["file"].read_text(encoding="utf-8"),
                     "caption": "Hình minh hoạ (không phải ảnh chụp)"}
        result.append(entry)
    return result


def build_compact(m: dict[str, Any], out: Path, images: dict[str, Any], level: int = 0,
                  tl_imgs: list | None = None) -> Path:
    css = (ASSETS / "compact.css").read_text(encoding="utf-8")
    meeting, media, val = m.get("meeting", {}), m["_media"], m["_validation"]
    st = val["stats"]
    title = meeting.get("title") or "Biên bản cuộc họp"
    try:
        d_fmt = date.fromisoformat(meeting["date"]).strftime("%d/%m/%Y") if meeting.get("date") else "Chưa nêu"
    except ValueError:
        d_fmt = meeting.get("date")
    participants = m.get("_participants", [])
    smap = m.get("speaker_map", {})
    names = sorted({(v.get("name") if isinstance(v, dict) else v) for v in smap.values()} - {UNKNOWN, None, ""})
    people = ", ".join(p["name"] for p in participants) or ", ".join(names) or "Chưa nêu"
    src = {"video": "Video", "audio": "Ghi âm", "transcript": "Transcript"}[media["kind"]]
    acts, decs, issues = m.get("action_items", []), m.get("decisions", []), m.get("open_issues", [])

    meta = [("Ngày", d_fmt), ("Thời lượng", media.get("duration_ts") or "—"), ("Chủ trì", meeting.get("chair") or "Chưa nêu"),
            ("Thành phần", people), ("Nguồn", src)]
    if meeting.get("location"):
        meta.insert(2, ("Địa điểm", meeting["location"]))
    head = (f'<header class="head"><div class="kicker">Biên bản cuộc họp</div><h1>{escape(title)}</h1>'
            f'<div class="meta">{"".join(f"<span>{escape(k)}: <b>{escape(v)}</b></span>" for k, v in meta)}</div>'
            f'<div class="stats"><div class="stat"><b>{len(decs)}</b>quyết định</div><div class="stat"><b>{len(acts)}</b>công việc</div>'
            f'<div class="stat"><b>{len(issues)}</b>vấn đề còn mở</div>'
            f'<div class="stat"><b>{st["evidence_exact"] + st["evidence_near"]}/{st["evidence_total"]}</b>dẫn chứng khớp bản ghi</div></div></header>')

    n = 0

    def sec(t: str, body: str) -> str:
        nonlocal n
        n += 1
        return f'<section><h2><span>{n}.</span>{escape(t)}</h2>{body}</section>'

    parts = [head]
    if meeting.get("purpose"):
        parts.append(f'<p style="margin:0 0 4px"><b>Mục đích:</b> {escape(meeting["purpose"])}</p>')
    parts.append(sec("Tóm tắt", '<ul class="points">' + "".join(f"<li>{escape(s.get('text', ''))}</li>"
                                                                 for s in m.get("summary", [])) + "</ul>"))

    rows = []
    tl_imgs = tl_imgs or [None] * len(m.get("timeline", []))
    for t, img in zip(m.get("timeline", []), tl_imgs):
        tm = sec_to_ts(t.get("_start")) if t.get("_start") is not None else (t["evidence"][0]["time"] if t.get("evidence") else "")
        ev = t["evidence"][0] if t.get("evidence") else None
        quote = f'<div class="q">{escape(ev["quote"])}</div>' if ev else ""
        fig = ""
        if img:
            vis = f'<img src="{img["src"]}" alt="">' if img["kind"] == "screenshot" else img["svg"]
            fig = f'<figure class="thumb">{vis}<figcaption>{escape(img["caption"])}</figcaption></figure>'
        rows.append(f'<div class="row{" has-img" if fig else ""}"><div class="t">{escape(tm[:8].removeprefix("00:"))}</div>'
                    f'<div><h3>{escape(t.get("topic", ""))}</h3><p>{escape(t.get("summary", ""))}</p>{quote}</div>{fig}</div>')
    parts.append(sec("Diễn biến cuộc họp", "".join(rows)))

    if decs:
        body = "<table><tr><th style='width:9%'>Mã</th><th>Quyết định</th><th style='width:13%'>Thời điểm</th></tr>" + "".join(
            f"<tr><td><b>{escape(d['id'])}</b></td><td>{escape(d.get('text', ''))}"
            + (f"<div class='small'>{escape(d['rationale'])}</div>" if d.get("rationale") else "")
            + f"</td><td>{escape(d['evidence'][0]['time'] if d.get('evidence') else '')}</td></tr>" for d in decs) + "</table>"
    else:
        body = '<p class="none">Không có quyết định nào được chốt trong cuộc họp.</p>'
    parts.append(sec("Quyết định", body))

    if acts:
        body = ("<table><tr><th style='width:8%'>Mã</th><th>Công việc</th><th style='width:20%'>Phụ trách</th>"
                "<th style='width:19%'>Thời hạn</th><th style='width:11%'>Căn cứ</th></tr>" + "".join(
                    f"<tr><td><b>{escape(a['id'])}</b></td><td>{escape(a.get('task', ''))}</td>"
                    f"<td>{'<span class=unk>' + UNKNOWN + '</span>' if a['owner'] == UNKNOWN else escape(a['owner'])}</td>"
                    f"<td>{escape(deadline_label(a))}</td><td>{escape(a['evidence'][0]['time'] if a.get('evidence') else '')}</td></tr>"
                    for a in acts) + "</table>")
    else:
        body = '<p class="none">Không có công việc nào được giao cho người cụ thể.</p>'
    parts.append(sec("Kế hoạch hành động", body))

    if issues:
        parts.append(sec("Vấn đề còn mở", '<ul class="points">' + "".join(
            f"<li>{escape(x.get('text', ''))} <span class='small'>({escape(x['evidence'][0]['time'] if x.get('evidence') else '')})</span></li>"
            for x in issues) + "</ul>"))

    notes = [n for n in m.get("notes_for_reviewer", [])][:4]
    spk = "; ".join(f"{k} = {(v.get('name') if isinstance(v, dict) else v)}" for k, v in smap.items())
    gen = time.strftime("%d/%m/%Y %H:%M")
    parts.append(f'<div class="foot"><b>Kiểm chứng:</b> {st["evidence_exact"]}/{st["evidence_total"]} câu trích dẫn khớp nguyên văn bản ghi'
                 f'{", " + str(st["evidence_near"]) + " gần khớp" if st["evidence_near"] else ""}. Mốc thời gian (phút:giây) dẫn về bản ghi gốc.'
                 f' Người nói: {escape(spk or "—")}.'
                 + (f'<ul>{"".join(f"<li>{escape(x)}</li>" for x in notes)}</ul>' if notes else "")
                 + f'<div>Lập tự động bởi Agent Biên bản họp · {gen}</div></div>')

    html = (f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)} — Biên bản</title>'
            '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            '<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;700&family=Lora:ital,wght@0,700;1,400&display=swap" rel="stylesheet">'
            f'<style>{css}</style></head><body class="c{level}">'
            '<div class="noprint"><button onclick="window.print()">In / Lưu PDF</button></div>'
            f'<main class="sheet">{"".join(parts)}</main></body></html>')
    path = out / "bien-ban.html"
    path.write_text(html, encoding="utf-8")
    return path


def render_compact(m: dict[str, Any], out: Path, images: dict[str, Any], max_pages: int):
    """Dựng HTML + PDF; nếu vượt số trang tối đa thì thu gọn dần (ảnh nhỏ hơn, chữ nhỏ hơn, ẩn trích dẫn phụ)."""
    from render import html_to_pdf, pdf_pages
    tl_imgs = timeline_images(m, out, images)
    pdf = out / "bien-ban.pdf"
    pages, pdf_ok, html = 0, None, None
    level = 0
    for level in range(0, 4):
        html = build_compact(m, out, images, level, tl_imgs)
        pdf_ok = html_to_pdf(html, pdf)
        if not pdf_ok:
            break
        pages = pdf_pages(pdf)
        if pages <= max_pages:
            break
    # Dọn trang lẻ: nếu thu gọn thêm 1 mức mà bớt được 1 trang (vd. trang cuối chỉ còn phần ghi chú) thì dùng bản đó
    if pdf_ok and pages > 1 and level < 3:
        trial = out / "work" / "_thu-gon.pdf"
        h2 = build_compact(m, out, images, level + 1, tl_imgs)
        if html_to_pdf(h2, trial) and pdf_pages(trial) < pages:
            trial.replace(pdf)
            pages = pdf_pages(pdf)
        else:
            trial.unlink(missing_ok=True)
            html = build_compact(m, out, images, level, tl_imgs)
    return html, pdf_ok, pages, sum(1 for x in tl_imgs if x), tl_imgs
