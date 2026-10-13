"""Soạn email giao việc riêng cho từng người: bản .eml (mở bằng Outlook/Thunderbird), bản xem trước HTML,
và payload JSON để Claude gửi qua Gmail connector SAU KHI người dùng phê duyệt."""
from __future__ import annotations

import base64
import mimetypes
import time
import uuid
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from pathlib import Path
from typing import Any

from excel import build_xlsx
from mmlib import EMAIL_RE, UNKNOWN, load_config, read_json, slugify, write_json


def _fmt_date(d: str | None) -> str:
    if not d:
        return ""
    try:
        return date.fromisoformat(str(d)).strftime("%d/%m/%Y")
    except ValueError:
        return str(d)


def deadline_label(a: dict[str, Any]) -> str:
    if a.get("deadline"):
        t = _fmt_date(a["deadline"])
        dt = a.get("deadline_text")
        return f"{t} (“{dt}”)" if dt and dt not in t else t
    return f"“{a['deadline_text']}”" if a.get("deadline_text") else "Chưa nêu trong cuộc họp"


def build_ics(tasks: list[dict[str, Any]], meeting: dict[str, Any]) -> str | None:
    ev = []
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for a in tasks:
        if not a.get("deadline"):
            continue
        try:
            d = date.fromisoformat(str(a["deadline"]))
        except ValueError:
            continue
        summary = (f"[Hạn] {a.get('task', '')}")[:120].replace(",", "\\,").replace(";", "\\;")
        desc = (f"Từ cuộc họp: {meeting.get('title', '')}. Mã việc {a['id']}.").replace(",", "\\,")
        ev += ["BEGIN:VEVENT", f"UID:{uuid.uuid4()}@bien-ban-hop", f"DTSTAMP:{stamp}",
               f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
               f"SUMMARY:{summary}", f"DESCRIPTION:{desc}",
               "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY", "DESCRIPTION:Nhắc hạn công việc", "END:VALARM",
               "END:VEVENT"]
    if not ev:
        return None
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//bien-ban-hop//VI", "CALSCALE:GREGORIAN", *ev,
                        "END:VCALENDAR"]) + "\r\n"


def compose(m: dict[str, Any], owner: str, tasks: list[dict[str, Any]], cfg: dict[str, Any],
            minutes_link: str = "") -> dict[str, str]:
    meeting = m.get("meeting", {})
    title = meeting.get("title") or "cuộc họp"
    when = _fmt_date(meeting.get("date")) or ""
    sender = cfg.get("sender_name") or "Thư ký cuộc họp"
    subject = f"[Giao việc] {title}{' – ' + when if when else ''} – {owner}"
    decisions = m.get("decisions", [])[:6]

    lines = [f"Chào {owner},", "",
             f"Sau cuộc họp “{title}”{' ngày ' + when if when else ''}, dưới đây là {len(tasks)} công việc anh/chị phụ trách:", ""]
    for i, a in enumerate(tasks, 1):
        ev = a["evidence"][0] if a.get("evidence") else None
        lines += [f"{i}. {a.get('task', '')}",
                  f"   - Thời hạn: {deadline_label(a)}",
                  *( [f"   - Kết quả cần bàn giao: {a['deliverable']}"] if a.get("deliverable") else []),
                  *( [f"   - Phối hợp: {', '.join(a['supporters'])}"] if a.get("supporters") else []),
                  *( [f"   - Căn cứ: “{ev['quote']}” — {ev['speaker']}, {ev['time'] or 'dòng ' + str(ev.get('line'))}"] if ev else []),
                  ""]
    if decisions:
        lines += ["Các quyết định chính của cuộc họp:"] + [f"• {d.get('text', '')}" for d in decisions] + [""]
    if minutes_link:
        lines += [f"Biên bản đầy đủ: {minutes_link}", ""]
    lines += ["Đính kèm: phiếu giao việc (Excel)" + (" và lịch nhắc hạn (.ics)" if any(t.get("deadline") for t in tasks) else "") + ".",
              "Nếu có điểm nào chưa chính xác (nội dung, thời hạn, người phụ trách), anh/chị vui lòng phản hồi email này.",
              "", "Trân trọng,", sender]
    text = "\n".join(lines)

    rows = []
    for i, a in enumerate(tasks, 1):
        ev = a["evidence"][0] if a.get("evidence") else None
        extra = ""
        if a.get("deliverable"):
            extra += f'<div style="color:#5A636B;font-size:13px;margin-top:4px">Bàn giao: {escape(a["deliverable"])}</div>'
        if a.get("supporters"):
            extra += f'<div style="color:#5A636B;font-size:13px">Phối hợp: {escape(", ".join(a["supporters"]))}</div>'
        if ev:
            extra += (f'<div style="margin-top:6px;padding:6px 10px;border-left:3px solid #B8862B;background:#F7F0DE;'
                      f'font-style:italic;font-size:13px;color:#3D3A33">“{escape(ev["quote"])}”'
                      f'<br><span style="font-style:normal;color:#B8862B;font-size:12px">{escape(ev["speaker"])} · '
                      f'{escape(ev["time"] or "dòng " + str(ev.get("line")))}</span></div>')
        rows.append(f'<tr><td style="padding:12px;border-bottom:1px solid #E4DDD0;vertical-align:top;font-weight:700;color:#D9693A">{i}</td>'
                    f'<td style="padding:12px;border-bottom:1px solid #E4DDD0;vertical-align:top"><b>{escape(a.get("task", ""))}</b>{extra}</td>'
                    f'<td style="padding:12px;border-bottom:1px solid #E4DDD0;vertical-align:top;white-space:nowrap;font-weight:600">'
                    f'{escape(deadline_label(a))}</td></tr>')
    dec_html = "".join(f'<li style="margin:4px 0">{escape(d.get("text", ""))}</li>' for d in decisions)
    link_html = (f'<p><a href="{escape(minutes_link)}" style="display:inline-block;background:#1F5C6B;color:#fff;'
                 f'padding:10px 18px;border-radius:999px;text-decoration:none;font-weight:600">Xem biên bản đầy đủ</a></p>'
                 if minutes_link else "")
    html = f"""<div style="font-family:'Segoe UI',Arial,sans-serif;color:#1D2329;max-width:680px;line-height:1.6">
<div style="background:#1F5C6B;color:#FBF8F2;padding:20px 24px;border-radius:14px 14px 0 0">
<div style="font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:#F2B66D;font-weight:700">Giao việc sau cuộc họp</div>
<div style="font-size:21px;font-weight:700;margin-top:4px">{escape(title)}</div>
<div style="font-size:13px;opacity:.85">{escape(when)}</div></div>
<div style="border:1px solid #E4DDD0;border-top:0;padding:20px 24px;border-radius:0 0 14px 14px">
<p>Chào {escape(owner)},</p>
<p>Dưới đây là <b>{len(tasks)} công việc</b> anh/chị phụ trách theo kết luận cuộc họp:</p>
<table style="width:100%;border-collapse:collapse;font-size:14px">
<tr style="background:#FAF6EE"><th style="text-align:left;padding:8px 12px">#</th><th style="text-align:left;padding:8px 12px">Công việc</th>
<th style="text-align:left;padding:8px 12px">Thời hạn</th></tr>{''.join(rows)}</table>
{('<p style="margin-top:20px"><b>Các quyết định chính:</b></p><ul>' + dec_html + '</ul>') if dec_html else ''}
{link_html}
<p style="color:#5A636B;font-size:13px">Đính kèm: phiếu giao việc (Excel){' và lịch nhắc hạn (.ics)' if any(t.get('deadline') for t in tasks) else ''}.
Nếu có điểm nào chưa chính xác, anh/chị vui lòng phản hồi email này.</p>
<p>Trân trọng,<br>{escape(sender)}</p></div></div>"""
    return {"subject": subject, "text": text, "html": html}


def build_emails(m: dict[str, Any], out: Path, pdf: Path | None, minutes_link: str = "") -> dict[str, Any]:
    cfg = load_config()
    edir = out / "email"
    (edir / "gmail").mkdir(parents=True, exist_ok=True)
    participants = {p["name"]: p for p in m.get("_participants", [])}
    old = {}
    if (edir / "email_plan.json").exists():
        old = {e["name"]: e for e in read_json(edir / "email_plan.json").get("emails", [])}
    owners: dict[str, list] = {}
    for a in m.get("action_items", []):
        if a["owner"] != UNKNOWN:
            owners.setdefault(a["owner"], []).append(a)
        for s in a.get("supporters") or []:
            owners.setdefault(s, [])
    plan = []
    max_kb = cfg.get("gmail_attachment_max_kb", 300)
    for owner, tasks in owners.items():
        if not tasks:
            continue
        slug = slugify(owner)
        p = participants.get(owner, {})
        email = (p.get("email") or "").strip()
        valid = bool(EMAIL_RE.fullmatch(email))
        c = compose(m, owner, tasks, cfg, minutes_link)
        xlsx = build_xlsx(m, edir / "phieu-giao-viec" / f"phieu-giao-viec-{slug}.xlsx", only_owner=owner)
        ics = build_ics(tasks, m.get("meeting", {}))
        atts = [(xlsx.name, xlsx.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
        if ics:
            atts.append((f"nhac-han-{slug}.ics", ics.encode("utf-8"), "text/calendar"))
        gmail_atts = [{"filename": n, "mimeType": t, "content": base64.b64encode(b).decode()} for n, b, t in atts]
        if pdf and pdf.exists() and pdf.stat().st_size / 1024 <= cfg.get("attach_pdf_to_gmail_if_under_kb", 0):
            gmail_atts.append({"filename": pdf.name, "mimeType": "application/pdf",
                               "content": base64.b64encode(pdf.read_bytes()).decode()})
        total_kb = sum(len(a["content"]) * 3 / 4 for a in gmail_atts) / 1024
        if total_kb > max_kb:  # quá nặng để gửi qua connector → chỉ gửi nội dung
            gmail_atts = []
        payload = {"to": [email] if valid else [], "subject": c["subject"], "body": c["text"], "htmlBody": c["html"],
                   "attachments": gmail_atts}
        pfile = edir / "gmail" / f"{slug}.json"
        write_json(pfile, payload)

        msg = EmailMessage()
        msg["Subject"] = c["subject"]
        msg["To"] = email if valid else ""
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="bien-ban-hop.local")
        msg["X-Unsent"] = "1"  # Outlook mở ở chế độ soạn thảo
        msg.set_content(c["text"])
        msg.add_alternative(c["html"], subtype="html")
        for n, b, t in atts + ([(pdf.name, pdf.read_bytes(), "application/pdf")] if pdf and pdf.exists() else []):
            maintype, subtype = t.split("/", 1)
            msg.add_attachment(b, maintype=maintype, subtype=subtype, filename=n)
        eml = edir / f"{slug}.eml"
        eml.write_bytes(bytes(msg))

        prev = old.get(owner, {})
        status = prev.get("status") if prev.get("status") == "đã gửi" else ("chờ phê duyệt" if valid else "thiếu email")
        plan.append({"name": owner, "email": email, "email_valid": valid, "subject": c["subject"], "tasks": len(tasks),
                     "task_ids": [t["id"] for t in tasks], "payload": str(pfile.relative_to(out)),
                     "eml": str(eml.relative_to(out)), "gmail_attachments": [a["filename"] for a in gmail_atts],
                     "status": status, "sent_at": prev.get("sent_at"), "message_id": prev.get("message_id"),
                     "preview_text": c["text"], "html": c["html"]})
    write_json(edir / "email_plan.json", {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                          "rule": "CHỈ gửi khi người dùng đã phê duyệt rõ ràng trong chat. "
                                                  "Thiếu email → hỏi người dùng, không suy đoán.",
                                          "emails": [{k: v for k, v in e.items() if k != "html"} for e in plan]})
    _preview(plan, m, edir / "xem-truoc-email.html")
    return {"emails": plan, "missing": [e["name"] for e in plan if not e["email_valid"]]}


def _preview(plan: list[dict[str, Any]], m: dict[str, Any], path: Path) -> None:
    cards = []
    for i, e in enumerate(plan, 1):
        badge = ('<span style="background:#E3F0E6;color:#3C7A4F">Đã gửi</span>' if e["status"] == "đã gửi" else
                 '<span style="background:#FBE7E4;color:#B23A2B">THIẾU EMAIL — cần bổ sung</span>' if not e["email_valid"] else
                 '<span style="background:#F7F0DE;color:#8A6416">Chờ phê duyệt</span>')
        cards.append(f"""<section class="mail"><div class="head"><div><b>Email {i}/{len(plan)}</b> {badge}</div>
<table><tr><th>Người nhận</th><td>{escape(e['name'])} &lt;{escape(e['email']) or '<i>chưa có</i>'}&gt;</td></tr>
<tr><th>Tiêu đề</th><td>{escape(e['subject'])}</td></tr>
<tr><th>Đính kèm</th><td>{escape(', '.join(e['gmail_attachments']) or 'không')}</td></tr></table></div>
<div class="body">{e['html']}</div></section>""")
    path.write_text(f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Xem trước email giao việc</title><style>
body{{margin:0;background:#EEE9DF;font:15px/1.5 'Segoe UI',Arial,sans-serif;color:#1D2329}}
.wrap{{max-width:820px;margin:0 auto;padding:24px 16px}} h1{{font-size:22px;margin:0 0 6px}}
.mail{{background:#fff;border-radius:16px;margin:22px 0;box-shadow:0 8px 24px rgba(0,0,0,.08);overflow:hidden}}
.head{{padding:16px 20px;background:#FAF6EE;border-bottom:1px solid #E4DDD0}} .head span{{font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;margin-left:8px}}
.head table{{margin-top:8px;font-size:14px}} .head th{{text-align:left;color:#5A636B;padding:2px 14px 2px 0;font-weight:600}}
.body{{padding:20px}}</style></head><body><div class="wrap"><h1>Xem trước {len(plan)} email giao việc</h1>
<p>Cuộc họp: <b>{escape(m.get('meeting', {}).get('title', ''))}</b>. Các email này <b>chưa được gửi</b>. Hãy kiểm tra rồi trả lời Claude
“Đồng ý gửi” (hoặc nêu chỗ cần sửa).</p>{''.join(cards)}</div></body></html>""", encoding="utf-8")


def mark_sent(out: Path, name: str, message_id: str, status: str = "đã gửi") -> None:
    f = out / "email" / "email_plan.json"
    plan = read_json(f)
    hit = False
    for e in plan["emails"]:
        if e["name"] == name:
            e["status"], e["message_id"], e["sent_at"] = status, message_id, time.strftime("%Y-%m-%d %H:%M:%S")
            hit = True
    if not hit:
        raise SystemExit(f"Không có email nào cho '{name}' trong kế hoạch gửi.")
    write_json(f, plan)
    with open(out / "email" / "nhat-ky-gui.txt", "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{name}\t{status}\t{message_id}\n")
