"""Bước 3 – Kiểm chứng minutes.json: dẫn chứng có thật, người phụ trách đúng, deadline có nguồn, không bỏ sót."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from mmlib import (EMAIL_RE, UNKNOWN, AgentError, load_config, log, norm_text, partial_ratio, participant_lookup,
                   read_json, sec_to_ts, ts_to_sec, write_json)

SECTIONS = {"summary": "Tóm tắt", "timeline": "Diễn biến", "decisions": "Quyết định",
            "action_items": "Công việc", "open_issues": "Vấn đề còn mở", "key_moments": "Mốc quan trọng"}


class Index:
    def __init__(self, segs):
        self.segs = segs
        self.by_id = {s["id"]: i for i, s in enumerate(segs)}
        self.norm = [norm_text(s["text"]) for s in segs]
        self.words = [set(n.split()) for n in self.norm]

    def window(self, i: int, before: int = 1, after: int = 1) -> str:
        return " ".join(self.segs[j]["text"] for j in range(max(0, i - before), min(len(self.segs), i + after + 1)))

    def locate(self, quote: str, seg_hint: str | None) -> tuple[int | None, float]:
        q = norm_text(quote)
        if not q:
            return None, 0.0
        if seg_hint and seg_hint in self.by_id:
            i = self.by_id[seg_hint]
            if q in self.norm[i]:
                return i, 1.0
            r = partial_ratio(quote, self.window(i))
            if r >= 0.97:
                return i, r
        for i, n in enumerate(self.norm):
            if q in n:
                return i, 1.0
        for i in range(len(self.segs) - 1):
            if q in self.norm[i] + " " + self.norm[i + 1]:
                return i, 1.0
        qw = set(q.split())
        best_i, best = None, 0.0
        for i in range(len(self.segs)):
            pool = self.words[i] | (self.words[i + 1] if i + 1 < len(self.segs) else set())
            if len(qw & pool) < 0.5 * len(qw):
                continue
            r = partial_ratio(quote, self.window(i, 0, 1))
            if r > best:
                best_i, best = i, r
        return best_i, best


def validate(out: Path) -> dict[str, Any]:
    cfg = load_config()
    mpath = out / "minutes.json"
    if not mpath.exists():
        raise AgentError(f"Chưa có {mpath}", "Claude cần đọc transcript và lưu kết quả phân tích thành minutes.json trước.")
    m = read_json(mpath)
    tr = read_json(out / "work" / "transcript.json")
    participants = read_json(out / "work" / "participants.json")
    media = read_json(out / "work" / "media.json")
    idx = Index(tr["segments"])
    look = participant_lookup(participants)
    names = {p["name"] for p in participants}
    errors: list[str] = []
    warnings: list[str] = []
    ok_th, warn_th = cfg.get("evidence_exact", 0.97), cfg.get("evidence_near", 0.85)

    for key in ("meeting", *SECTIONS):
        if key not in m:
            errors.append(f"Thiếu mục '{key}' trong minutes.json")
    meeting = m.get("meeting", {})
    mdate = None
    if meeting.get("date"):
        try:
            mdate = date.fromisoformat(str(meeting["date"]))
        except ValueError:
            errors.append(f"Ngày họp '{meeting['date']}' không đúng dạng YYYY-MM-DD")

    smap = m.get("speaker_map", {})

    overrides = m.get("speaker_overrides") or {}
    for sid, ov in overrides.items():
        nm = ov.get("name") if isinstance(ov, dict) else ov
        if sid not in idx.by_id:
            errors.append(f"speaker_overrides: không có đoạn {sid}")
        elif not isinstance(ov, dict) or not ov.get("basis"):
            errors.append(f"speaker_overrides {sid}: phải ghi căn cứ (basis) khi sửa người nói")
        elif participants and nm not in names and nm != UNKNOWN:
            errors.append(f"speaker_overrides {sid}: '{nm}' không có trong danh sách người tham gia")

    def speaker_name(label: str, seg_id: str | None = None) -> str:
        if seg_id and seg_id in overrides:
            ov = overrides[seg_id]
            return (ov.get("name") if isinstance(ov, dict) else ov) or UNKNOWN
        v = smap.get(label)
        if isinstance(v, dict):
            return v.get("name") or UNKNOWN
        if isinstance(v, str):
            return v
        p = look.get(norm_text(label))
        return p["name"] if p else (label if label != UNKNOWN and not re.fullmatch(r"SPK\d+", label) else UNKNOWN)

    for lab, v in smap.items():
        nm = v.get("name") if isinstance(v, dict) else v
        if nm and nm != UNKNOWN and participants and nm not in names:
            warnings.append(f"Nhãn {lab} được gán tên '{nm}' nhưng tên này không có trong danh sách người tham gia")
        if isinstance(v, dict) and nm and nm != UNKNOWN and not v.get("basis"):
            errors.append(f"Nhãn {lab} → '{nm}' chưa ghi căn cứ nhận diện (basis)")

    cited: set[str] = set()
    stats = {"evidence_total": 0, "evidence_exact": 0, "evidence_near": 0, "evidence_failed": 0}

    def check_evidence(item: dict[str, Any], where: str) -> list[dict[str, Any]]:
        evs = item.get("evidence") or []
        if isinstance(evs, dict):
            evs = [evs]
        if not evs:
            errors.append(f"{where}: không có dẫn chứng (evidence) — không được đưa thông tin không có nguồn")
            return []
        resolved = []
        for ev in evs:
            if isinstance(ev, str):
                ev = {"quote": ev}
            stats["evidence_total"] += 1
            i, r = idx.locate(ev.get("quote", ""), ev.get("seg"))
            if i is None or r < warn_th:
                stats["evidence_failed"] += 1
                errors.append(f"{where}: dẫn chứng KHÔNG tìm thấy trong transcript (khớp {r:.0%}): \"{ev.get('quote', '')[:120]}\"")
                continue
            seg = idx.segs[i]
            cited.add(seg["id"])
            if r >= ok_th:
                stats["evidence_exact"] += 1
                status = "nguyên văn"
            else:
                stats["evidence_near"] += 1
                status = "gần khớp"
                warnings.append(f"{where}: dẫn chứng chỉ gần khớp ({r:.0%}) với {seg['id']} — nên chép nguyên văn")
            who = speaker_name(seg["speaker"], seg["id"])
            if ev.get("speaker"):  # sửa người nói cho riêng câu này (đoạn phiên âm gộp lời 2 người)
                if not ev.get("speaker_basis"):
                    errors.append(f"{where}: sửa người nói thành '{ev['speaker']}' nhưng thiếu speaker_basis")
                elif participants and ev["speaker"] not in names:
                    errors.append(f"{where}: '{ev['speaker']}' không có trong danh sách người tham gia")
                else:
                    who = ev["speaker"]
            resolved.append({"quote": ev.get("quote", ""), "seg": seg["id"], "time": sec_to_ts(seg["start"]),
                             "seconds": seg["start"], "line": seg.get("line"), "speaker_label": seg["speaker"],
                             "speaker": who, "match": round(r, 3), "status": status,
                             "speaker_basis": ev.get("speaker_basis", "")})
        return resolved

    ids_seen: set[str] = set()
    for sec, label in SECTIONS.items():
        items = m.get(sec) or []
        if not isinstance(items, list):
            errors.append(f"Mục '{sec}' phải là danh sách")
            continue
        for n, it in enumerate(items, 1):
            if isinstance(it, str):
                it = {"text": it}
                items[n - 1] = it
            iid = it.get("id") or f"{sec[:2].upper()}{n}"
            it["id"] = iid
            if iid in ids_seen:
                errors.append(f"Mã '{iid}' bị trùng")
            ids_seen.add(iid)
            where = f"{label} {iid}"
            it["evidence"] = check_evidence(it, where)

    # ---- công việc
    for it in m.get("action_items", []):
        where = f"Công việc {it['id']}"
        if not (it.get("task") or "").strip():
            errors.append(f"{where}: thiếu nội dung công việc (task)")
        owner = (it.get("owner") or "").strip() or UNKNOWN
        it["owner"] = owner
        quotes = " ".join(e["quote"] for e in it["evidence"])
        speakers = {e["speaker"] for e in it["evidence"]}
        for who in [owner, *(it.get("supporters") or [])]:
            if who == UNKNOWN:
                continue
            if participants and who not in names:
                errors.append(f"{where}: '{who}' không có trong danh sách người tham gia (dùng đúng họ tên trong danh sách, "
                              f"hoặc ghi '{UNKNOWN}')")
                continue
            p = next((p for p in participants if p["name"] == who), None)
            keys = [who, *(p.get("aliases", []) if p else []), who.split()[-1], who.split()[0]]
            mentioned = any(re.search(rf"\b{re.escape(norm_text(k))}\b", norm_text(quotes)) for k in keys if k)
            if not mentioned and who not in speakers:
                errors.append(f"{where}: dẫn chứng không cho thấy '{who}' được giao/nhận việc (không được nêu tên, "
                              f"cũng không phải người nói) — thêm câu dẫn chứng phù hợp hoặc ghi '{UNKNOWN}'")
        if owner == UNKNOWN:
            warnings.append(f"{where}: chưa xác định người phụ trách → cần hỏi người dùng")
        p = next((p for p in participants if p["name"] == owner), None)
        it["owner_email"] = p.get("email", "") if p else ""
        it["owner_role"] = p.get("role", "") if p else ""
        dl, dtext = it.get("deadline"), (it.get("deadline_text") or "").strip()
        if dl:
            try:
                d = date.fromisoformat(str(dl))
                if mdate and d < mdate:
                    warnings.append(f"{where}: deadline {dl} sớm hơn ngày họp")
            except ValueError:
                errors.append(f"{where}: deadline '{dl}' phải ở dạng YYYY-MM-DD (hoặc để null và ghi deadline_text)")
            if not dtext:
                errors.append(f"{where}: có deadline nhưng thiếu deadline_text (câu chữ gốc nói về thời hạn)")
            elif partial_ratio(dtext, quotes) < 0.8:
                errors.append(f"{where}: thời hạn '{dtext}' không xuất hiện trong dẫn chứng — có thể là suy đoán")
            if re.search(r"tuần|thứ|mai|cuối|đầu tháng|giữa tháng", dtext.lower()) and not mdate:
                errors.append(f"{where}: thời hạn tương đối '{dtext}' nhưng chưa biết ngày họp → để deadline=null")
        elif dtext and partial_ratio(dtext, quotes) < 0.8:
            errors.append(f"{where}: thời hạn '{dtext}' không xuất hiện trong dẫn chứng")
        if not dl and not dtext:
            warnings.append(f"{where}: cuộc họp chưa nêu thời hạn → ghi 'Chưa nêu'")
        it.setdefault("priority", "Trung bình")
        it.setdefault("status", "Chưa bắt đầu")

    # ---- mốc quan trọng
    dur = media.get("duration")
    for it in m.get("key_moments", []):
        t = ts_to_sec(it.get("time"))
        if t is None and it["evidence"] and it["evidence"][0]["seconds"] is not None:
            t = it["evidence"][0]["seconds"] + 1.0  # lệch 1 giây để khung hình đã chuyển cảnh
        if t is None:
            warnings.append(f"Mốc {it['id']}: không có thời điểm → không chụp được hình")
        elif dur and t > dur:
            errors.append(f"Mốc {it['id']}: thời điểm {it.get('time')} vượt quá thời lượng media {sec_to_ts(dur)}")
        elif it["evidence"] and it["evidence"][0]["seconds"] is not None and abs(t - it["evidence"][0]["seconds"]) > 90:
            warnings.append(f"Mốc {it['id']}: thời điểm {it.get('time')} lệch xa dẫn chứng ({it['evidence'][0]['time']})")
        it["seconds"] = t
        it["time"] = sec_to_ts(t) if t is not None else ""

    # ---- kiểm tra bỏ sót
    reviewed = set()
    for r in m.get("reviewed_not_actionable") or []:
        if isinstance(r, str) and r in idx.by_id:
            reviewed.add(r)
            continue
        q = r.get("quote", "") if isinstance(r, dict) else str(r)
        i, ratio = idx.locate(q, r.get("seg") if isinstance(r, dict) else None)
        if i is None or ratio < warn_th:
            errors.append(f"reviewed_not_actionable: không tìm thấy đoạn \"{q[:80]}\"")
        else:
            reviewed.add(idx.segs[i]["id"])
    triggers = [norm_text(k) for k in cfg.get("coverage_keywords", [])]
    action_cited = {e["seg"] for sec in ("decisions", "action_items", "open_issues") for it in m.get(sec, [])
                    for e in it["evidence"]}
    candidates = []
    for s, n in zip(idx.segs, idx.norm):
        hit = next((k for k in triggers if re.search(rf"\b{re.escape(k)}\b", n)), None)
        if hit and s["id"] not in action_cited and s["id"] not in reviewed:
            candidates.append({"seg": s["id"], "time": sec_to_ts(s["start"]), "speaker": speaker_name(s["speaker"], s["id"]),
                               "keyword": hit, "text": s["text"][:220]})
    if candidates:
        errors.append(f"Có {len(candidates)} đoạn chứa từ khoá quyết định/giao việc chưa được xử lý (xem review_candidates). "
                      "Với mỗi đoạn: hoặc bổ sung vào decisions/action_items/open_issues, hoặc thêm mã đoạn vào "
                      "reviewed_not_actionable nếu không phải quyết định/công việc.")

    # ---- email
    owners = sorted({a["owner"] for a in m.get("action_items", []) if a["owner"] != UNKNOWN})
    missing = [o for o in owners if not EMAIL_RE.fullmatch(next((p.get("email", "") for p in participants
                                                                  if p["name"] == o), "") or "")]
    unknown_speakers = sorted({e["speaker_label"] for sec in SECTIONS for it in m.get(sec, []) for e in it["evidence"]
                               if e["speaker"] == UNKNOWN and e["speaker_label"] != UNKNOWN})
    if unknown_speakers:
        warnings.append(f"Các nhãn người nói chưa được xác định tên: {', '.join(unknown_speakers)}")

    total = stats["evidence_total"] or 1
    report = {
        "ok": not errors, "errors": errors, "warnings": warnings, "review_candidates": candidates,
        "missing_emails": missing, "owners": owners,
        "stats": {**stats, "evidence_verified_rate": round((stats["evidence_exact"] + stats["evidence_near"]) / total, 3),
                  "decisions": len(m.get("decisions", [])), "action_items": len(m.get("action_items", [])),
                  "actions_with_owner": sum(1 for a in m.get("action_items", []) if a["owner"] != UNKNOWN),
                  "actions_with_deadline": sum(1 for a in m.get("action_items", []) if a.get("deadline") or a.get("deadline_text")),
                  "open_issues": len(m.get("open_issues", [])), "key_moments": len(m.get("key_moments", [])),
                  "segments": len(idx.segs), "segments_cited": len(cited),
                  "coverage_keywords_unhandled": len(candidates)},
    }
    write_json(out / "work" / "validation.json", report)
    resolved = out / "work" / "minutes.resolved.json"
    resolved.unlink(missing_ok=True)  # không để bản kiểm chứng cũ bị xuất bản khi bản mới có lỗi
    if not errors:
        m["_participants"] = participants
        m["_media"] = media
        m["_validation"] = report
        m["_transcript_source"] = tr.get("source", "")
        write_json(resolved, m)

    log("")
    log("✅ KIỂM CHỨNG ĐẠT" if not errors else f"❌ KIỂM CHỨNG CHƯA ĐẠT — {len(errors)} lỗi cần sửa trong minutes.json")
    st = report["stats"]
    log(f"   Dẫn chứng: {st['evidence_exact']} nguyên văn, {st['evidence_near']} gần khớp, {st['evidence_failed']} không tìm thấy")
    log(f"   Quyết định: {st['decisions']} | Công việc: {st['action_items']} (có người phụ trách: {st['actions_with_owner']}, "
        f"có thời hạn: {st['actions_with_deadline']}) | Mốc: {st['key_moments']}")
    for e in errors:
        log(f"   ✗ {e}")
    for c in candidates[:40]:
        log(f"      ? {c['seg']} [{c['time']}] {c['speaker']}: {c['text'][:140]}")
    for w in warnings:
        log(f"   ⚠ {w}")
    if missing:
        log(f"   ✉ Thiếu email của: {', '.join(missing)} → PHẢI hỏi người dùng trước khi gửi")
    return report
