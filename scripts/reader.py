"""Trình đọc biên bản dạng web (một file HTML): trang sách một cột, đơn sắc kiểu e-ink, thanh công cụ ở đáy
(Mục lục · Tìm không dấu · Chia sẻ · Hiển thị), tuỳ chọn khoá mật khẩu (AES-GCM). Ảnh dẫn chứng nằm trong Diễn biến."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from emails import deadline_label
from mmlib import ASSETS, UNKNOWN, AgentError, sec_to_ts

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Literata:opsz,wght@7..72,400;7..72,600;'
         '7..72,700&family=Be+Vietnam+Pro:wght@500;600;700&display=swap">')


PRI_HI = "<span class='pri hi'>ƯU TIÊN CAO</span>"
KIND_RISK = "<span class='kind r'>RỦI RO</span>"
KIND_OPEN = "<span class='kind'>CÒN MỞ</span>"


def _ts(t: str | None) -> str:
    return (t or "").removeprefix("00:") if t and t.startswith("00:") else (t or "")


def _initial(name: str) -> str:
    w = [x for x in name.replace("(", " ").split() if x[:1].isalpha()]
    return (w[-1][0] if w else "?").upper()


def _fmt_date(d: str | None) -> str:
    try:
        return date.fromisoformat(d).strftime("%d/%m/%Y") if d else ""
    except ValueError:
        return d or ""


def _sentences(text: str) -> list[str]:
    parts = [p.strip(" .;") for p in re.split(r"(?<=[.;])\s+", text or "") if p.strip(" .;")]
    return parts[:3]


def build_content(m: dict[str, Any], tl_imgs: list | None) -> tuple[str, dict[str, Any]]:
    meeting, media, val = m.get("meeting", {}), m["_media"], m["_validation"]
    st = val["stats"]
    title = meeting.get("title") or "Biên bản cuộc họp"
    participants = m.get("_participants", [])
    smap = m.get("speaker_map", {})
    spk_names = sorted({(v.get("name") if isinstance(v, dict) else v) for v in smap.values()} - {UNKNOWN, None, ""})
    people = [p["name"] for p in participants] or spk_names
    acts, decs, issues = m.get("action_items", []), m.get("decisions", []), m.get("open_issues", [])
    tl = m.get("timeline", [])
    tl_imgs = tl_imgs or [None] * len(tl)
    src = {"video": "Video", "audio": "Ghi âm", "transcript": "Transcript"}[media["kind"]]
    d_fmt = _fmt_date(meeting.get("date")) or "Chưa nêu"

    secs: list[tuple[str, str, str, str]] = []  # (id, tiêu đề, phụ chú mục lục, html)

    # 1. Tóm tắt nhanh
    tldr = "".join(f"<li>{escape(s.get('text', ''))}</li>" for s in m.get("summary", []))
    count = (f'<p class="count"><b>{len(decs)}</b> quyết định · <b>{len(acts)}</b> việc · <b>{len(issues)}</b> vấn đề còn mở · '
             f'<b>{st["evidence_exact"] + st["evidence_near"]}/{st["evidence_total"]}</b> trích dẫn khớp bản ghi</p>')
    secs.append(("tom-tat", "Tóm tắt nhanh", f"{len(m.get('summary', []))} ý", f'<div class="tldr"><ul>{tldr}</ul></div>{count}'))

    # 2. Kế hoạch hành động
    if acts:
        items = []
        for a in acts:
            owner = a["owner"] if a["owner"] != UNKNOWN else "Chưa rõ"
            ev = a["evidence"][0] if a.get("evidence") else {}
            pri = a.get("priority", "")
            due = (f'<span class="due" data-deadline="{escape(a["deadline"])}">{escape(_fmt_date(a["deadline"]))}</span>' if a.get("deadline")
                   else f'<span class="due">{escape(deadline_label(a))}</span>')
            items.append(
                f'<li class="task{" unknown" if owner == "Chưa rõ" else ""}" id="task-{escape(a["id"])}" data-owner="{escape(owner)}" '
                f'data-deadline="{escape(a.get("deadline") or "")}"><div class="who"><span class="av sm">{escape(_initial(owner) if owner != "Chưa rõ" else "?")}</span>'
                f'{escape(owner if owner != "Chưa rõ" else "Chưa rõ người nhận")}'
                f'{"<span class=\'pri hi\'>ƯU TIÊN CAO</span>" if pri == "Cao" else ""}</div>'
                f'<p class="what">{escape(a.get("task", ""))}</p>'
                f'<div class="when">{due}<span>{escape(a["id"])} · căn cứ {escape(_ts(ev.get("time")))}</span></div>'
                f'<div class="task-actions"><button type="button" data-owner-copy="{escape(owner)}">Sao chép việc của '
                f'{escape(owner if owner != "Chưa rõ" else "mục chưa rõ người")}</button></div></li>')
        body = ('<p class="plan-sub">Ai làm gì, khi nào. Hạn màu đỏ là đã quá hạn, màu vàng là còn ≤ 3 ngày.</p>'
                '<div class="plan-tools"><div class="seg" role="group" aria-label="Sắp xếp"><button type="button" id="by-date" class="on">Theo hạn</button>'
                '<button type="button" id="by-owner">Theo người</button></div><button type="button" class="ghost" id="copy-plan">Sao chép kế hoạch</button></div>'
                f'<ul class="tasks" id="tasks">{"".join(items)}</ul>')
    else:
        body = '<p class="plan-sub">Ai làm gì, khi nào.</p><p class="empty">Cuộc họp không giao công việc cho người cụ thể.</p>'
    secs.append(("ke-hoach", "Kế hoạch hành động", f"{len(acts)} việc", body))

    # 3. Quyết định
    if decs:
        body = '<ul class="decisions">' + "".join(
            f'<li id="d-{escape(d["id"])}"><p>{escape(d.get("text", ""))}</p>'
            + (f'<span class="src">Lý do: {escape(d["rationale"])}</span>' if d.get("rationale") else "")
            + (f'<span class="src">{escape(_ts(d["evidence"][0]["time"]))} · {escape(d["evidence"][0]["speaker"])} · “{escape(d["evidence"][0]["quote"])}”</span>'
               if d.get("evidence") else "") + "</li>" for d in decs) + "</ul>"
    else:
        body = '<p class="empty">Không có quyết định nào được chốt trong cuộc họp.</p>'
    secs.append(("quyet-dinh", "Quyết định", f"{len(decs)} mục", body))

    # 4. Sơ đồ
    branches = "".join(
        f'<li><p class="b">{escape(t.get("topic", ""))}</p><ul>{"".join(f"<li>{escape(x)}</li>" for x in _sentences(t.get("summary", "")))}</ul></li>'
        for t in tl)
    secs.append(("so-do", "Sơ đồ nội dung", f"{len(tl)} nhánh",
                 f'<p class="root">{escape(title)}</p><ul class="branches">{branches}</ul>'))

    # 5. Diễn biến (ảnh dẫn chứng nằm ngay trong từng chủ đề)
    folds = []
    for i, (t, img) in enumerate(zip(tl, tl_imgs), 1):
        start = sec_to_ts(t.get("_start")) if t.get("_start") is not None else (t["evidence"][0]["time"] if t.get("evidence") else "")
        fig = ""
        if img:
            vis = f'<img src="{img["src"]}" alt="{escape(t.get("topic", ""))}" loading="lazy">' if img["kind"] == "screenshot" else img["svg"]
            fig = f'<figure class="shot">{vis}<figcaption>{escape(img["caption"])}</figcaption></figure>'
        lines = "".join(
            f'<li class="{"key" if j == 0 else ""}" id="q-{i}-{j}"><span class="ts">{escape(_ts(e["time"]))}</span>'
            f'<p>“{escape(e["quote"])}” <span class="tag">{escape(e["speaker"])}</span></p></li>'
            for j, e in enumerate(t.get("evidence", [])))
        folds.append(f'<details class="topic-fold" id="t-{i}" open><summary><span class="ts0">{escape(_ts(start))}</span>'
                     f'<span class="topic">{escape(t.get("topic", ""))}</span><span class="cnt">{"ảnh · " if img else ""}'
                     f'{len(t.get("evidence", []))} trích dẫn</span></summary><div class="fold-body">{fig}'
                     f'<p class="sum">{escape(t.get("summary", ""))}</p><ul class="tl">{lines}</ul></div></details>')
    tools = ('<div class="db-tools"><button type="button" class="linkish" id="fold-all">Thu gọn tất cả</button></div>')
    secs.append(("dien-bien", "Diễn biến cuộc họp", f"{len(tl)} chủ đề", tools + "".join(folds)))

    # 6. Vấn đề còn mở
    if issues:
        body = '<ul class="open">' + "".join(
            f'<li>{"<span class=\'kind r\'>RỦI RO</span>" if re.search("rủi ro|chậm|nguy", x.get("text", ""), re.I) else "<span class=\'kind\'>CÒN MỞ</span>"}'
            f'{escape(x.get("text", ""))}<span class="src">{escape(_ts(x["evidence"][0]["time"]) if x.get("evidence") else "")} · '
            f'“{escape(x["evidence"][0]["quote"]) if x.get("evidence") else ""}”</span></li>' for x in issues) + "</ul>"
        secs.append(("van-de", "Vấn đề còn mở", f"{len(issues)} mục", body))

    # 7. Ghi chú & kiểm chứng
    notes = "".join(f"<li>{escape(n)}</li>" for n in m.get("notes_for_reviewer", []))
    talk = {}
    overrides = m.get("speaker_overrides") or {}
    for s in m.get("_segments", []):
        v = overrides.get(s["id"]) or smap.get(s["speaker"])
        nm = (v.get("name") if isinstance(v, dict) else v) or UNKNOWN
        if s.get("start") is not None and s.get("end") is not None:
            talk[nm] = talk.get(nm, 0) + max(0, s["end"] - s["start"])
    talk_html = ""
    if len(talk) > 1:
        tot = sum(talk.values()) or 1
        talk_html = '<p class="b">Thời lượng phát biểu</p><ul class="talk">' + "".join(
            f'<li><span>{escape(_initial(k))}</span><i style="--w:{v / tot * 100:.0f}%"></i><em>{v / tot:.0%}</em></li>'
            for k, v in sorted(talk.items(), key=lambda x: -x[1])) + "</ul>"
    spk = "; ".join(f"{escape(k)} = {escape((v.get('name') if isinstance(v, dict) else v) or UNKNOWN)}"
                    + (f" ({escape(v.get('basis', ''))})" if isinstance(v, dict) and v.get("basis") else "") for k, v in smap.items())
    body = (f'<ul class="tips"><li><span class="kind">KIỂM CHỨNG</span>{st["evidence_exact"]}/{st["evidence_total"]} câu trích dẫn khớp '
            f'nguyên văn bản ghi{", " + str(st["evidence_near"]) + " gần khớp" if st["evidence_near"] else ""}. '
            f'Mốc thời gian (phút:giây) dẫn về bản ghi gốc.</li><li><span class="kind">NGƯỜI NÓI</span>{spk or "—"}</li>{notes}</ul>{talk_html}')
    secs.append(("ghi-chu", "Ghi chú & kiểm chứng", "", body))

    toc = "".join(f'<li><a href="#s-{sid}"><span class="tn">{n}</span><span class="tt">{escape(t)}</span>'
                  f'<span class="n">{escape(sub)}</span></a></li>' for n, (sid, t, sub, _) in enumerate(secs, 1))
    meta = [("Ngày", d_fmt), ("Thời lượng", media.get("duration_ts") or "—"), ("Nguồn", src)]
    if meeting.get("chair"):
        meta.append(("Chủ trì", meeting["chair"]))
    if meeting.get("location"):
        meta.append(("Địa điểm", meeting["location"]))
    head = (f'<header class="head" id="top"><p class="eyebrow">Biên bản họp · {escape(src)} {escape(media.get("duration_ts") or "")}</p>'
            f'<h1>{escape(title)}</h1>' + (f'<p class="purpose">{escape(meeting["purpose"])}</p>' if meeting.get("purpose") else "")
            + '<dl class="meta">' + "".join(f"<div><dt>{escape(k)}</dt><dd>{escape(v)}</dd></div>" for k, v in meta) + "</dl>"
            + '<ul class="people">' + "".join(f'<li><span class="av">{escape(_initial(p))}</span>{escape(p)}</li>' for p in people) + "</ul></header>"
            + f'<nav class="toc" aria-label="Mục lục"><p class="toc-title">Nội dung</p><ol>{toc}</ol></nav>')
    body_secs = "".join(
        f'<section class="sec{" plan" if sid == "ke-hoach" else ""}" id="s-{sid}"><h2><span class="num">{n}</span>'
        f'<span class="ht">{escape(t)}</span></h2>{html}</section>' for n, (sid, t, _, html) in enumerate(secs, 1))
    foot = f'<footer class="foot">Biên bản lập tự động bởi Agent Biên bản họp · Nguồn: {escape(m.get("_transcript_source", ""))}</footer>'

    plain = _plain_text(m, d_fmt)
    info = {"title": title, "date": d_fmt, "plain": plain}
    return head + body_secs + foot, info


def _plain_text(m: dict[str, Any], d_fmt: str) -> str:
    meeting = m.get("meeting", {})
    lines = [f"📝 BIÊN BẢN: {meeting.get('title', '')} ({d_fmt})", "", "TÓM TẮT"]
    lines += [f"• {s.get('text', '')}" for s in m.get("summary", [])]
    if m.get("decisions"):
        lines += ["", "QUYẾT ĐỊNH"] + [f"• {d.get('text', '')}" for d in m["decisions"]]
    if m.get("action_items"):
        lines += ["", "VIỆC CẦN LÀM"] + [f"• {a['owner']}: {a.get('task', '')} — hạn: {deadline_label(a)}" for a in m["action_items"]]
    if m.get("open_issues"):
        lines += ["", "CÒN MỞ"] + [f"• {x.get('text', '')}" for x in m["open_issues"]]
    return "\n".join(lines)


def _encrypt(content: str, password: str) -> dict[str, Any]:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise AgentError("Cần thư viện cryptography để khoá biên bản bằng mật khẩu.", "python -m pip install cryptography")
    salt, iv, it = os.urandom(16), os.urandom(12), 310000
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, it, 32)
    data = AESGCM(key).encrypt(iv, content.encode("utf-8"), None)
    b = lambda x: base64.b64encode(x).decode()  # noqa: E731
    return {"salt": b(salt), "iv": b(iv), "data": b(data), "iter": it}


def build_reader(m: dict[str, Any], out: Path, tl_imgs: list | None, password: str = "") -> tuple[Path, Path]:
    content, info = build_content(m, tl_imgs)
    css = (ASSETS / "reader.css").read_text(encoding="utf-8")
    js = (ASSETS / "reader.js").read_text(encoding="utf-8")
    enc = _encrypt(content, password) if password else None
    cfg = {"title": info["title"], "date": info["date"], "plain": info["plain"], "enc": enc}
    gate = ""
    if enc:
        gate = (f'<div class="gate" id="gate"><form id="gate-form" autocomplete="off"><p class="kicker">Biên bản họp</p>'
                f'<h1>{escape(info["title"])}</h1><p>Nội dung được bảo vệ. Nhập mật khẩu được gửi kèm đường link để mở.</p>'
                '<label for="pw">Mật khẩu</label><input id="pw" type="password" autocomplete="off" required>'
                '<button class="btn" id="open-btn" type="submit">Mở biên bản</button><p class="err" id="err" role="alert"></p></form></div>')
    page = (f'<title>{escape(info["title"])}</title>{FONTS}<style>{css}</style>{gate}'
            f'<main class="wrap" id="app"{" hidden" if enc else ""}><div id="content">{"" if enc else content}</div></main>'
            '<div class="progress" id="progress" aria-hidden="true"><i id="prog-bar"></i></div>'
            '<div class="searchbar" id="searchbar" hidden><div class="in"><input id="q" type="search" placeholder="Tìm (gõ không dấu cũng được)" '
            'aria-label="Tìm trong biên bản"><span class="c" id="q-count">0/0</span><button type="button" id="q-prev" aria-label="Kết quả trước">↑</button>'
            '<button type="button" id="q-next" aria-label="Kết quả sau">↓</button><button type="button" id="q-close">Đóng</button></div></div>'
            f'<nav class="dock" id="dock"{" hidden" if enc else ""} aria-label="Công cụ đọc"><div class="dock-in">'
            '<button type="button" data-sheet="sheet-toc"><b>☰</b>Mục lục</button><button type="button" id="open-search"><b>⌕</b>Tìm</button>'
            '<button type="button" data-sheet="sheet-share"><b>↗</b>Chia sẻ</button><button type="button" data-sheet="sheet-view"><b class="aa">Aa</b>Hiển thị</button>'
            '</div></nav><div class="sheet-bg" id="sheet-bg" hidden></div>'
            '<section class="sheet" id="sheet-toc" hidden aria-label="Mục lục"><div class="sheet-head"><span class="sh-t">Mục lục</span>'
            '<span class="prog-txt" id="prog-txt"></span><button type="button" class="x">Đóng</button></div><ol class="sheet-toc" id="sheet-toc-list"></ol></section>'
            '<section class="sheet" id="sheet-share" hidden aria-label="Chia sẻ"><div class="sheet-head"><span class="sh-t">Chia sẻ</span>'
            '<button type="button" class="x">Đóng</button></div><div class="share-list">'
            '<button type="button" id="copy-all">Sao chép bản tóm tắt<small>Tóm tắt, quyết định, việc cần làm — dán vào Zalo, email</small></button>'
            '<button type="button" id="copy-plan-2">Sao chép kế hoạch hành động<small>Danh sách việc theo hạn</small></button>'
            '<p class="tip">Bản in A4 có trong file <b>bien-ban.pdf</b> đi kèm.</p></div></section>'
            '<section class="sheet" id="sheet-view" hidden aria-label="Hiển thị"><div class="sheet-head"><span class="sh-t">Hiển thị</span>'
            '<button type="button" class="x">Đóng</button></div>'
            '<div class="opt-row"><span class="opt-lab">Cỡ chữ</span><div class="opt" id="opt-fs">'
            + "".join(f'<button type="button" data-v="{i}" style="font-size:{s}px">Aa</button>' for i, s in [(1, 13), (2, 15), (3, 17), (4, 20)])
            + '</div></div><div class="opt-row"><span class="opt-lab">Giãn dòng</span><div class="opt" id="opt-lh">'
            '<button type="button" data-v="normal">Vừa</button><button type="button" data-v="wide">Rộng</button></div></div>'
            '<div class="opt-row"><span class="opt-lab">Nền</span><div class="opt" id="opt-bg"><button type="button" data-v="auto">Tự động</button>'
            '<button type="button" data-v="paper">Giấy</button><button type="button" data-v="sepia">Sepia</button><button type="button" data-v="dark">Tối</button>'
            '</div></div></section><div class="toast" id="toast" role="status" hidden></div>'
            f'<script>const BB={json.dumps(cfg, ensure_ascii=False)};\n{js}</script>')
    artifact = out / "artifact" / "bien-ban-doc.html"
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(page, encoding="utf-8")  # bản đăng claude.ai (khung trang do nền tảng thêm)
    local = out / "bien-ban-doc.html"
    local.write_text('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
                     '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body>'
                     + page + "</body></html>", encoding="utf-8")
    return local, artifact
