"""Đồ hoạ minh hoạ (SVG, tạo hoàn toàn trên máy): bìa, thẻ minh hoạ cho file âm thanh, dạng sóng, biểu đồ."""
from __future__ import annotations

import hashlib
import math
import random
import subprocess
from html import escape
from typing import Any

from mmlib import find_ffmpeg, sec_to_ts

PALETTE = ["#1F5C6B", "#D9693A", "#6B4E8C", "#3C7A4F", "#B8862B", "#2F6FA8"]
INK = "#1D2329"
PAPER = "#FBF8F2"
FONT = "'Be Vietnam Pro','Segoe UI',Arial,sans-serif"
SERIF = "'Lora','Cambria','Times New Roman',serif"

ICON_KEYWORDS = {
    "money": ["giá", "chi phí", "ngân sách", "doanh thu", "tiền", "đồng", "học phí", "lợi nhuận", "budget", "thanh toán"],
    "calendar": ["lịch", "ngày", "deadline", "thời hạn", "tuần", "tháng", "khai giảng", "ra mắt"],
    "team": ["nhân sự", "đội", "nhóm", "tuyển", "phân công", "người"],
    "chart": ["số liệu", "báo cáo", "kpi", "tăng trưởng", "chỉ số", "kết quả", "tỷ lệ", "chuyển đổi"],
    "rocket": ["ra mắt", "launch", "triển khai", "khởi động", "phát hành"],
    "megaphone": ["marketing", "quảng cáo", "truyền thông", "nội dung", "chiến dịch", "facebook", "tiktok", "email"],
    "code": ["kỹ thuật", "hệ thống", "code", "website", "landing", "phần mềm", "tích hợp", "lỗi"],
    "cart": ["bán hàng", "khách hàng", "đơn hàng", "sale", "kinh doanh", "chốt đơn"],
    "document": ["hợp đồng", "tài liệu", "giáo trình", "văn bản", "biên bản", "quy trình"],
    "warning": ["rủi ro", "vấn đề", "chậm", "khó khăn", "cảnh báo", "chưa rõ"],
    "check": ["chốt", "thống nhất", "quyết định", "đồng ý", "phê duyệt"],
    "idea": ["ý tưởng", "đề xuất", "gợi ý", "sáng kiến"],
    "target": ["mục tiêu", "chỉ tiêu", "target"],
    "handshake": ["đối tác", "hợp tác", "ký kết"],
}


def pick_icon(text: str, given: str | None = None) -> str:
    if given and given in ICON_PATHS:
        return given
    t = (text or "").lower()
    best, score = "idea", 0
    for name, kws in ICON_KEYWORDS.items():
        s = sum(1 for k in kws if k in t)
        if s > score:
            best, score = name, s
    return best


# Biểu tượng nét mảnh trong khung 24x24
ICON_PATHS = {
    "money": '<rect x="2.5" y="6" width="19" height="12" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M6 9v.01M18 15v.01"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/><path d="M8 14l2.5 2.5L16 12"/>',
    "team": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14.2c3 .2 5 2.4 5 5.3"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 6-7"/><path d="M16 7h4v4"/>',
    "rocket": '<path d="M12 3c4 2 6 6 5 11l-3 3h-4l-3-3c-1-5 1-9 5-11z"/><circle cx="12" cy="9.5" r="1.8"/><path d="M9 17l-2 4M15 17l2 4M7 13l-3 2 1 3M17 13l3 2-1 3"/>',
    "megaphone": '<path d="M3 10v4h3l7 4V6l-7 4H3z"/><path d="M16 9a4 4 0 010 6M18.5 6.5a7.5 7.5 0 010 11"/><path d="M6 14l1.5 5h2.5l-1-5"/>',
    "code": '<rect x="2.5" y="4" width="19" height="15" rx="2"/><path d="M2.5 8h19"/><path d="M9.5 11.5L7 14l2.5 2.5M14.5 11.5L17 14l-2.5 2.5"/>',
    "cart": '<path d="M3 4h2.5l2.2 10.5h10.6L20.5 7H6.5"/><circle cx="9.5" cy="19" r="1.5"/><circle cx="17" cy="19" r="1.5"/>',
    "document": '<path d="M6 2.5h8l4.5 4.5V21a.5.5 0 01-.5.5H6a.5.5 0 01-.5-.5V3A.5.5 0 016 2.5z"/><path d="M14 2.5V7h4.5M8.5 12h7M8.5 15.5h7M8.5 19h4"/>',
    "warning": '<path d="M12 3l9.5 17h-19L12 3z"/><path d="M12 10v4.5M12 17.5v.01"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M7.5 12.5l3 3 6-6.5"/>',
    "idea": '<path d="M9 17h6M10 20.5h4"/><path d="M12 3a6 6 0 00-3.5 10.9c.4.3.5.7.5 1.1v2h6v-2c0-.4.1-.8.5-1.1A6 6 0 0012 3z"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5.5"/><circle cx="12" cy="12" r="2"/><path d="M12 12l7-7M16 5h3v3"/>',
    "handshake": '<path d="M2.5 9l4-3 4 2 3-2 3 1 5 3"/><path d="M2.5 9v5l5 5 2-1 2 2 2-1 2 1 2-2 4-4V9"/><path d="M10.5 8l-3 4 1.5 1.5 3-2.5 4 4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "mic": '<rect x="9" y="2.5" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5v4M8.5 21.5h7"/>',
}


def icon_svg(name: str, x: float, y: float, size: float, color: str, stroke: float = 1.6) -> str:
    s = size / 24
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.3f})" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{ICON_PATHS.get(name, ICON_PATHS["idea"])}</g>')


def wrap(text: str, max_chars: int, max_lines: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;: ") + "…"
    return lines


def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16))


# ------------------------------------------------------------------ bìa
def cover_art(title: str, w: int = 1240, h: int = 900) -> str:
    r = _rng(title)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice">',
             '<defs><linearGradient id="cg" x1="0" y1="0" x2="1" y2="1">'
             '<stop offset="0" stop-color="#123B47"/><stop offset=".55" stop-color="#1F5C6B"/>'
             '<stop offset="1" stop-color="#2E7A72"/></linearGradient>'
             '<radialGradient id="sun" cx=".78" cy=".28" r=".45"><stop offset="0" stop-color="#F2B66D" stop-opacity=".9"/>'
             '<stop offset="1" stop-color="#F2B66D" stop-opacity="0"/></radialGradient></defs>',
             f'<rect width="{w}" height="{h}" fill="url(#cg)"/><rect width="{w}" height="{h}" fill="url(#sun)"/>']
    cx, cy = w * 0.78, h * 0.3
    for i in range(9):
        rad = 60 + i * 46
        parts.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{rad}" fill="none" stroke="#FBF8F2" '
                     f'stroke-opacity="{0.22 - i * 0.02:.2f}" stroke-width="{1.4 if i % 2 else 0.8}"/>')
    # sóng âm cách điệu
    base = h * 0.78
    n = 90
    for i in range(n):
        x = 40 + i * (w - 80) / n
        amp = (math.sin(i / 6.0) * 0.5 + 0.5) * (0.4 + r.random() * 0.6) * 110
        parts.append(f'<rect x="{x:.1f}" y="{base - amp / 2:.1f}" width="{(w - 80) / n * 0.55:.1f}" height="{max(4, amp):.1f}" '
                     f'rx="2" fill="#FBF8F2" fill-opacity="{0.18 + 0.25 * (amp / 110):.2f}"/>')
    for _ in range(26):
        parts.append(f'<circle cx="{r.uniform(0, w):.0f}" cy="{r.uniform(0, h * 0.6):.0f}" r="{r.uniform(1.2, 3.2):.1f}" '
                     f'fill="#F2B66D" fill-opacity="{r.uniform(.3, .8):.2f}"/>')
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------ thẻ minh hoạ (khi chỉ có audio)
def moment_card(m: dict[str, Any], n: int, w: int = 1200, h: int = 675) -> str:
    color = PALETTE[(n - 1) % len(PALETTE)]
    r = _rng(m.get("title", "") + str(n))
    icon = pick_icon((m.get("title", "") + " " + m.get("caption", "")), m.get("icon"))
    sp = m["evidence"][0]["speaker"] if m.get("evidence") else ""
    title_lines = wrap(m.get("title", ""), 26, 3)
    cap_lines = wrap(m.get("caption", ""), 44, 3)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="{FONT}">',
         f'<defs><linearGradient id="bg{n}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{PAPER}"/>'
         f'<stop offset="1" stop-color="#F1EADF"/></linearGradient></defs>',
         f'<rect width="{w}" height="{h}" rx="28" fill="url(#bg{n})"/>']
    for _ in range(7):
        p.append(f'<circle cx="{r.uniform(w * .55, w):.0f}" cy="{r.uniform(0, h):.0f}" r="{r.uniform(20, 120):.0f}" '
                 f'fill="{color}" fill-opacity="{r.uniform(.04, .10):.2f}"/>')
    # dải sóng âm ở chân thẻ
    for i in range(70):
        x = 60 + i * 15.5
        a = (math.sin(i / 4 + n) * .5 + .5) * r.uniform(.3, 1) * 70
        p.append(f'<rect x="{x:.0f}" y="{h - 70 - a / 2:.0f}" width="7" height="{max(4, a):.0f}" rx="3.5" fill="{color}" fill-opacity=".22"/>')
    p.append(f'<circle cx="250" cy="300" r="160" fill="{color}"/>'
             f'<circle cx="250" cy="300" r="182" fill="none" stroke="{color}" stroke-opacity=".35" stroke-width="3" stroke-dasharray="6 10"/>')
    p.append(icon_svg(icon, 160, 210, 180, "#FFFFFF", 1.5))
    p.append(f'<rect x="470" y="96" rx="18" width="{150 + len(m.get("time", "")) * 2}" height="40" fill="{color}"/>'
             f'<text x="492" y="123" font-size="22" font-weight="700" fill="#fff">⏱ {escape(m.get("time", ""))}</text>')
    y = 200
    for line in title_lines:
        p.append(f'<text x="470" y="{y}" font-size="46" font-weight="800" fill="{INK}" font-family="{SERIF}">{escape(line)}</text>')
        y += 58
    y += 10
    for line in cap_lines:
        p.append(f'<text x="470" y="{y}" font-size="26" fill="#4A535C">{escape(line)}</text>')
        y += 36
    if sp:
        p.append(f'<text x="470" y="{y + 18}" font-size="22" fill="{color}" font-weight="600">🎙 {escape(sp)}</text>')
    p.append(f'<text x="{w - 40}" y="{h - 22}" text-anchor="end" font-size="17" fill="#7A828A" font-style="italic">'
             f'Hình minh hoạ tạo từ nội dung ghi âm — không phải ảnh chụp cuộc họp</text>')
    p.append("</svg>")
    return "".join(p)


# ------------------------------------------------------------------ dạng sóng thật của file âm thanh
def audio_envelope(path: str, bins: int = 480) -> list[float] | None:
    ff = find_ffmpeg()
    if not ff:
        return None
    try:
        raw = subprocess.run([ff, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "4000", "-f", "s16le", "-"],
                             capture_output=True, timeout=900).stdout
    except Exception:
        return None
    import numpy as np
    a = np.frombuffer(raw, dtype=np.int16).astype("float32")
    if a.size < bins:
        return None
    chunks = np.array_split(np.abs(a), bins)
    env = np.array([float(np.sqrt(np.mean(c ** 2))) if c.size else 0 for c in chunks])
    peak = float(np.percentile(env, 98)) or 1.0
    return [min(1.0, v / peak) for v in env]


def waveform_svg(env: list[float], duration: float, moments: list[dict[str, Any]], timeline: list[dict[str, Any]],
                 w: int = 1200, h: int = 300) -> str:
    left, right, top, mid = 30, 30, 70, 175
    span = w - left - right
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="{FONT}">',
         f'<rect width="{w}" height="{h}" rx="18" fill="{PAPER}"/>']
    for i, t in enumerate(timeline):
        a, b = t.get("_start"), t.get("_end")
        if a is None or b is None or not duration:
            continue
        x0, x1 = left + span * a / duration, left + span * min(b, duration) / duration
        col = PALETTE[i % len(PALETTE)]
        p.append(f'<rect x="{x0:.1f}" y="{top - 40}" width="{max(2, x1 - x0 - 2):.1f}" height="8" rx="4" fill="{col}"/>')
        label = wrap(t.get("topic", ""), max(4, int((x1 - x0) / 9)), 1)
        if label and x1 - x0 > 60:
            p.append(f'<text x="{x0 + 2:.1f}" y="{top - 46}" font-size="13" fill="{col}" font-weight="600">{escape(label[0])}</text>')
    bw = span / len(env)
    for i, v in enumerate(env):
        hh = max(1.5, v * 90)
        p.append(f'<rect x="{left + i * bw:.1f}" y="{mid - hh / 2:.1f}" width="{max(.8, bw * .7):.1f}" height="{hh:.1f}" fill="#1F5C6B" fill-opacity=".55"/>')
    for n, m in enumerate(moments, 1):
        if m.get("seconds") is None or not duration:
            continue
        x = left + span * m["seconds"] / duration
        p.append(f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{h - 50}" stroke="#D9693A" stroke-width="2" stroke-dasharray="4 4"/>'
                 f'<circle cx="{x:.1f}" cy="{h - 38}" r="14" fill="#D9693A"/>'
                 f'<text x="{x:.1f}" y="{h - 33}" text-anchor="middle" font-size="14" font-weight="700" fill="#fff">{n}</text>')
    for k in range(0, 5):
        t = duration * k / 4
        p.append(f'<text x="{left + span * k / 4:.1f}" y="{h - 8}" text-anchor="{"start" if k == 0 else "end" if k == 4 else "middle"}" '
                 f'font-size="12" fill="#7A828A">{sec_to_ts(t)}</text>')
    p.append("</svg>")
    return "".join(p)


# ------------------------------------------------------------------ biểu đồ
def donut_svg(data: list[tuple[str, float]], title: str, unit: str = "phút", size: int = 520) -> str:
    total = sum(v for _, v in data) or 1
    cx, cy, R, r0 = 150, 160, 120, 72
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} 320" font-family="{FONT}">',
         f'<text x="0" y="18" font-size="15" font-weight="700" fill="{INK}">{escape(title)}</text>']
    ang = -math.pi / 2
    for i, (name, v) in enumerate(data):
        frac = v / total
        a2 = ang + frac * 2 * math.pi
        large = 1 if frac > .5 else 0
        col = PALETTE[i % len(PALETTE)]
        if frac >= .999:
            p.append(f'<circle cx="{cx}" cy="{cy}" r="{(R + r0) / 2}" fill="none" stroke="{col}" stroke-width="{R - r0}"/>')
        else:
            x1, y1, x2, y2 = cx + R * math.cos(ang), cy + R * math.sin(ang), cx + R * math.cos(a2), cy + R * math.sin(a2)
            x3, y3, x4, y4 = cx + r0 * math.cos(a2), cy + r0 * math.sin(a2), cx + r0 * math.cos(ang), cy + r0 * math.sin(ang)
            p.append(f'<path d="M{x1:.1f},{y1:.1f} A{R},{R} 0 {large} 1 {x2:.1f},{y2:.1f} L{x3:.1f},{y3:.1f} '
                     f'A{r0},{r0} 0 {large} 0 {x4:.1f},{y4:.1f}Z" fill="{col}" stroke="{PAPER}" stroke-width="2"/>')
        ly = 60 + i * 34
        p.append(f'<rect x="300" y="{ly}" width="16" height="16" rx="4" fill="{col}"/>'
                 f'<text x="324" y="{ly + 13}" font-size="14" fill="{INK}">{escape(name[:22])}</text>'
                 f'<text x="{size - 4}" y="{ly + 13}" text-anchor="end" font-size="14" fill="#5A636B">{frac:.0%}</text>')
        ang = a2
    tot = total / 60 if unit == "phút" else total
    p.append(f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="26" font-weight="800" fill="{INK}">{tot:.0f}</text>'
             f'<text x="{cx}" y="{cy + 20}" text-anchor="middle" font-size="13" fill="#7A828A">{unit}</text></svg>')
    return "".join(p)


def bars_svg(data: list[tuple[str, int]], title: str, w: int = 520) -> str:
    mx = max([v for _, v in data] or [1]) or 1
    h = 50 + 38 * len(data)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="{FONT}">',
         f'<text x="0" y="18" font-size="15" font-weight="700" fill="{INK}">{escape(title)}</text>']
    for i, (name, v) in enumerate(data):
        y = 40 + i * 38
        bw = (w - 200) * v / mx
        col = PALETTE[i % len(PALETTE)]
        p.append(f'<text x="0" y="{y + 18}" font-size="14" fill="{INK}">{escape(name[:20])}</text>'
                 f'<rect x="160" y="{y + 4}" width="{max(6, bw):.0f}" height="20" rx="6" fill="{col}"/>'
                 f'<text x="{168 + bw:.0f}" y="{y + 19}" font-size="14" font-weight="700" fill="{INK}">{v}</text>')
    p.append("</svg>")
    return "".join(p)
