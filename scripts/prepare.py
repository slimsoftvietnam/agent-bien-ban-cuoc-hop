"""Bước 1 – Chuẩn bị: đọc transcript/audio/video → transcript.json có người nói, mốc thời gian, mã đoạn."""
from __future__ import annotations

import json
import re
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

from mmlib import (AUDIO_EXT, MODELS, TEXT_EXT, UNKNOWN, VIDEO_EXT, AgentError, find_ffmpeg, load_config,
                   load_participants, log, norm_text, participant_lookup, read_docx_text, read_json, sec_to_ts,
                   ts_to_sec, write_json)

TS = r"\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?"


# ======================================================================= transcript văn bản
def _looks_like_name(s: str) -> bool:
    s = s.strip()
    return (0 < len(s) <= 40 and len(s.split()) <= 6 and not re.search(r"[.!?;\"“”]", s)
            and not re.fullmatch(r"[\d\s:]+", s))


def parse_text_transcript(text: str) -> list[dict[str, Any]]:
    segs: list[dict[str, Any]] = []
    cur_time: float | None = None
    pending_speaker: str | None = None
    patterns = [
        re.compile(rf"^\[?(?P<t>{TS})(?:\s*[-–>]+\s*(?P<t2>{TS}))?\]?\s*[-–]?\s*(?P<sp>[^:]{{1,40}}?)\s*:\s*(?P<tx>.+)$"),
        re.compile(rf"^(?P<sp>[^:\[\]()]{{1,40}}?)\s*[\[(](?P<t>{TS})[\])]\s*:?\s*(?P<tx>.+)$"),
        re.compile(r"^(?P<sp>[^:\[\]()]{1,40}?)\s*:\s+(?P<tx>.+)$"),
        re.compile(rf"^\[?(?P<t>{TS})\]?\s+(?P<tx>.+)$"),
    ]
    all_lines = text.splitlines()

    def next_is_timestamp(i: int) -> bool:
        for nxt in all_lines[i:]:
            if nxt.strip():
                return bool(re.fullmatch(rf"\[?({TS})\]?", nxt.strip()))
        return False

    for ln, raw in enumerate(all_lines, 1):
        line = raw.strip().lstrip("﻿")
        if not line:
            continue
        only_ts = re.fullmatch(rf"\[?({TS})\]?", line)
        if only_ts:
            cur_time = ts_to_sec(only_ts.group(1))
            continue
        m = None
        for pat in patterns:
            m = pat.match(line)
            if m and ("sp" not in m.groupdict() or m.group("sp") is None or _looks_like_name(m.group("sp"))):
                break
            m = None
        if m:
            gd = m.groupdict()
            t = ts_to_sec(gd.get("t")) if gd.get("t") else None
            if t is not None:
                cur_time = t
            sp = (gd.get("sp") or "").strip() or pending_speaker
            segs.append({"start": t if t is not None else cur_time, "end": ts_to_sec(gd.get("t2")),
                         "speaker": sp or UNKNOWN, "text": gd["tx"].strip(), "line": ln})
            pending_speaker = None
        elif _looks_like_name(line) and len(line.split()) <= 5 and next_is_timestamp(ln):
            pending_speaker = line  # dạng "Tên\nNội dung" (Google Meet/Docs)
        else:
            sp = pending_speaker or (segs[-1]["speaker"] if segs else UNKNOWN)
            if segs and pending_speaker is None and segs[-1]["speaker"] == sp and segs[-1]["start"] == cur_time:
                segs[-1]["text"] += " " + line
            else:
                segs.append({"start": cur_time, "end": None, "speaker": sp, "text": line, "line": ln})
            pending_speaker = None
    return segs


def parse_subtitles(text: str) -> list[dict[str, Any]]:
    segs = []
    blocks = re.split(r"\n\s*\n", text.replace("\r", ""))
    for b in blocks:
        lines = [l for l in b.strip().split("\n") if l.strip()]
        tl = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if tl is None:
            continue
        a, _, c = lines[tl].partition("-->")
        start, end = ts_to_sec(a.strip().split(" ")[0]), ts_to_sec(c.strip().split(" ")[0])
        body = " ".join(lines[tl + 1:])
        sp = UNKNOWN
        mv = re.match(r"<v(?:\.[^ >]+)?\s+([^>]+)>", body)
        if mv:
            sp = mv.group(1).strip()
        body = re.sub(r"<[^>]+>", "", body).strip()
        mc = re.match(r"^([^:]{1,40}?)\s*:\s+(.+)$", body)
        if sp == UNKNOWN and mc and _looks_like_name(mc.group(1)):
            sp, body = mc.group(1).strip(), mc.group(2)
        if body:
            if segs and segs[-1]["speaker"] == sp and start is not None and segs[-1]["end"] is not None \
                    and start - segs[-1]["end"] < 1.0 and len(segs[-1]["text"]) < 300:
                segs[-1]["text"] += " " + body
                segs[-1]["end"] = end
            else:
                segs.append({"start": start, "end": end, "speaker": sp, "text": body, "line": None})
    return segs


def parse_json_transcript(data: Any) -> list[dict[str, Any]]:
    items = data.get("segments", data) if isinstance(data, dict) else data
    segs = []
    for it in items:
        segs.append({"start": ts_to_sec(it.get("start")), "end": ts_to_sec(it.get("end")),
                     "speaker": it.get("speaker") or UNKNOWN, "text": str(it.get("text", "")).strip(), "line": None})
    return [s for s in segs if s["text"]]


def load_transcript(path: Path) -> list[dict[str, Any]]:
    ext = path.suffix.lower()
    if ext == ".docx":
        text = read_docx_text(path)
    elif ext == ".json":
        return parse_json_transcript(read_json(path))
    else:
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "utf-16", "cp1258", "cp1252"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise AgentError(f"Không đọc được bảng mã của file {path.name}", "Lưu lại file ở dạng UTF-8 rồi chạy lại.")
    if ext in {".vtt", ".srt"} or "-->" in text[:2000]:
        return parse_subtitles(text)
    return parse_text_transcript(text)


# ======================================================================= media
def run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def probe_media(path: Path) -> dict[str, Any]:
    ffprobe = find_ffmpeg("ffprobe")
    if not ffprobe:
        raise AgentError("Chưa cài FFmpeg nên không đọc được audio/video.",
                         "Mở PowerShell và chạy: winget install Gyan.FFmpeg  (sau đó mở lại Claude).")
    r = run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
             "-of", "json", str(path)], timeout=120)
    if r.returncode != 0:
        raise AgentError(f"File media bị hỏng hoặc không đúng định dạng: {path.name}",
                         f"Thử mở file bằng trình phát nhạc/video. Chi tiết FFmpeg: {r.stderr.strip()[:300]}")
    info = json.loads(r.stdout or "{}")
    streams = info.get("streams", [])
    has_video = any(s.get("codec_type") == "video" and (s.get("width") or 0) > 16 for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    dur = float(info.get("format", {}).get("duration") or 0)
    if dur <= 0:
        raise AgentError(f"Không xác định được thời lượng của {path.name} — file có thể bị hỏng.")
    return {"duration": dur, "has_video": has_video, "has_audio": has_audio}


def extract_wav(src: Path, dst: Path) -> None:
    r = run([find_ffmpeg(), "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(dst)])
    if r.returncode != 0 or not dst.exists():
        raise AgentError(f"Không tách được âm thanh từ {src.name}", r.stderr.strip()[:300])


def read_wav(path: Path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype("float32") / 32768.0


def _filter_words(segments, pats, max_cr: float, offset: float = 0.0, tag: str = ""):
    """Bỏ các từ thuộc câu ảo giác; trả về (từ giữ lại, mô tả phần bị loại, vùng thời gian bị loại trọn)."""
    words, dropped, gaps = [], [], []
    for s in segments:
        ws = list(s.words or []) or [type("W", (), {"start": s.start, "end": s.end, "word": " " + s.text.strip()})()]
        if s.compression_ratio > max_cr:  # câu lặp vô nghĩa
            dropped.append(f"[{sec_to_ts(s.start + offset)}] {s.text.strip()[:80]}")
            gaps.append((s.start + offset, s.end + offset))
            continue
        text, spans = "", []
        for w in ws:
            spans.append((len(text), len(text) + len(w.word)))
            text += w.word
        bad = [m.span() for p in pats for m in p.finditer(text)]
        kept = 0
        for w, (x0, x1) in zip(ws, spans):
            if any(x0 < y and x1 > x for x, y in bad):
                continue
            words.append({"start": w.start + offset, "end": w.end + offset, "word": w.word, "seg": f"{tag}{s.id}"})
            kept += 1
        if bad:
            dropped.append(f"[{sec_to_ts(s.start + offset)}] " + " | ".join(text[x:y].strip() for x, y in bad)[:120])
            if kept == 0:
                gaps.append((s.start + offset, s.end + offset))
    return words, dropped, gaps


def transcribe(wav: Path, cfg: dict[str, Any], names: list[str] | None = None) -> list[dict[str, Any]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise AgentError("Chưa cài bộ chuyển giọng nói thành chữ (faster-whisper).",
                         "Chạy file setup.ps1 trong thư mục skill, hoặc cung cấp transcript có sẵn.")
    model_name = cfg.get("whisper_model", "small")
    log(f"   • Đang chuyển giọng nói thành chữ bằng Whisper ({model_name}, chạy trên máy, miễn phí)…")
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=cfg.get("cpu_threads", 0))
    lang = cfg.get("language", "vi")
    common = dict(language=lang, vad_filter=True, word_timestamps=True, beam_size=cfg.get("whisper_beam_size", 1),
                  condition_on_previous_text=False)  # tránh lặp một câu ảo giác suốt nhiều phút
    prompt = ((cfg.get("whisper_prompt") or "") + (" Người tham gia: " + ", ".join(names) + "." if names else "")) or None
    segments, info = model.transcribe(str(wav), initial_prompt=prompt, **common)
    pats = [re.compile(p, re.IGNORECASE) for p in cfg.get("hallucination_patterns", [])]
    max_cr = cfg.get("max_compression_ratio", 2.4)
    words, dropped, gaps = _filter_words(segments, pats, max_cr)
    # Phiên âm lại các vùng bị loại trọn (lời nói thật có thể bị che bởi câu ảo giác)
    if gaps:
        audio = read_wav(wav)
        total = len(audio) / 16000
        recovered = 0
        for g0, g1 in gaps:
            mid = (g0 + g1) / 2
            lo = max([w["end"] for w in words if w["end"] <= mid] or [0.0])
            hi = min([w["start"] for w in words if w["start"] >= mid] or [total])
            if hi - lo < 1.5:
                continue
            clip = audio[int(lo * 16000):int(hi * 16000)]
            segs2, _ = model.transcribe(clip, initial_prompt=None, temperature=[0.0, 0.2, 0.4], **common)
            w2, d2, _ = _filter_words(segs2, pats, max_cr, offset=lo, tag="r")
            words += w2
            dropped += d2
            recovered += len(w2)
        words.sort(key=lambda w: w["start"])
        if recovered:
            log(f"   • Đã phiên âm lại {len(gaps)} vùng bị che bởi câu ảo giác → khôi phục {recovered} từ")
    if dropped:
        log(f"   ⚠ Đã loại {len(dropped)} đoạn phiên âm ảo giác (câu quảng cáo/lặp không có trong lời nói)")
    cfg["_dropped_hallucinations"] = dropped
    log(f"     → {len(words)} từ, ngôn ngữ nhận diện: {info.language} ({info.language_probability:.0%})")
    return words


def diarize(wav: Path, cfg: dict[str, Any], num_speakers: int | None) -> list[tuple[float, float, int]] | None:
    seg_model = MODELS / "sherpa-onnx-pyannote-segmentation-3-0" / "model.int8.onnx"
    emb_model = MODELS / "speaker-embedding.onnx"
    try:
        import sherpa_onnx
    except ImportError:
        log("   ⚠ Chưa cài sherpa-onnx → bỏ qua nhận diện giọng nói, Claude sẽ nhận diện người nói theo nội dung.")
        return None
    if not (seg_model.exists() and emb_model.exists()):
        log("   ⚠ Thiếu model nhận diện giọng nói (thư mục models/) → chạy setup.ps1 để tải.")
        return None
    if num_speakers == 1:  # đã biết chỉ 1 người nói → không cần tách giọng
        log("   • Chỉ có 1 người nói → gán toàn bộ cho SPK1")
        return [(0.0, len(read_wav(wav)) / 16000 + 1, 0)]
    log("   • Đang nhận diện người nói theo giọng (sherpa-onnx, chạy trên máy)…")
    import os
    threads = cfg.get("cpu_threads") or max(1, (os.cpu_count() or 2) - 1)
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg_model)),
            num_threads=threads),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb_model), num_threads=threads),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=num_speakers or -1,
                                                    threshold=cfg.get("diarization_threshold", 0.5)),
        min_duration_on=0.3, min_duration_off=0.5)
    if not config.validate():
        log("   ⚠ Cấu hình nhận diện giọng nói không hợp lệ → bỏ qua.")
        return None
    sd = sherpa_onnx.OfflineSpeakerDiarization(config)
    samples = read_wav(wav)
    result = sd.process(samples).sort_by_start_time()
    turns = [(r.start, r.end, r.speaker) for r in result]
    max_spk = cfg.get("_max_speakers")
    if not num_speakers and max_spk and len({t[2] for t in turns}) > max_spk:
        # không thể nhiều giọng hơn số người tham gia → phân cụm lại với số cụm cố định
        config.clustering.num_clusters = max_spk
        result = sherpa_onnx.OfflineSpeakerDiarization(config).process(samples).sort_by_start_time()
        turns = [(r.start, r.end, r.speaker) for r in result]
    log(f"     → phát hiện {len({t[2] for t in turns})} giọng nói khác nhau")
    return turns


def speaker_at(turns, start: float, end: float) -> int | None:
    best, best_ov = None, 0.0
    for a, b, spk in turns:
        ov = min(b, end) - max(a, start)
        if ov > best_ov:
            best, best_ov = spk, ov
    if best is None:  # không giao nhau → lấy lượt gần nhất
        mid = (start + end) / 2
        near = min(turns, key=lambda t: min(abs(t[0] - mid), abs(t[1] - mid)), default=None)
        best = near[2] if near else None
    return best


def words_to_segments(words, turns) -> list[dict[str, Any]]:
    segs: list[dict[str, Any]] = []
    for w in words:
        spk = speaker_at(turns, w["start"], w["end"]) if turns else None
        label = f"SPK{spk + 1}" if spk is not None else UNKNOWN
        text = w["word"]
        cur = segs[-1] if segs else None
        new = (cur is None or cur["speaker"] != label or cur["_seg"] != w["seg"] and cur["text"].rstrip()[-1:] in ".?!"
               or w["start"] - cur["end"] > 2.0 or len(cur["text"]) > 400)
        if new:
            segs.append({"start": w["start"], "end": w["end"], "speaker": label, "text": text.strip(),
                         "line": None, "_seg": w["seg"]})
        else:
            cur["text"] += text
            cur["end"] = w["end"]
            cur["_seg"] = w["seg"]
    for s in segs:
        s.pop("_seg", None)
        s["text"] = re.sub(r"\s+", " ", s["text"]).strip()
    return [s for s in segs if s["text"]]


# ======================================================================= nhận diện người nói
INTRO_RE = re.compile(r"\b(?:tôi|em|mình|anh|chị|tớ)\s+(?:là|tên là)\s+([A-ZĐÀ-Ỹ][\wÀ-ỹ]*(?:\s+[A-ZĐÀ-Ỹ][\wÀ-ỹ]*){0,3})")


def speaker_report(segs, participants) -> dict[str, Any]:
    look = participant_lookup(participants)
    labels: dict[str, dict[str, Any]] = {}
    for i, s in enumerate(segs):
        d = labels.setdefault(s["speaker"], {"label": s["speaker"], "talk_seconds": 0.0, "segments": 0,
                                             "first_time": sec_to_ts(s["start"]), "samples": [], "self_intro": [],
                                             "addressed_as_before_first_turn": [], "auto_match": None})
        d["segments"] += 1
        if s["start"] is not None and s["end"] is not None:
            d["talk_seconds"] += max(0.0, s["end"] - s["start"])
        if len(d["samples"]) < 5:
            d["samples"].append(f'{s["id"]} [{sec_to_ts(s["start"])}] {s["text"][:160]}')
        for m in INTRO_RE.finditer(s["text"]):
            d["self_intro"].append(f'{s["id"]}: "{m.group(0)}"')
        if d["segments"] == 1 and i > 0:
            prev = norm_text(segs[i - 1]["text"])
            for p in participants:
                for k in [p["name"], *p.get("aliases", []), p["name"].split()[-1]]:
                    if k and re.search(rf"\b{re.escape(norm_text(k))}\b", prev):
                        d["addressed_as_before_first_turn"].append(p["name"])
                        break
    for lab, d in labels.items():
        p = look.get(norm_text(lab))
        if p:
            d["auto_match"] = {"name": p["name"], "basis": "Nhãn người nói trong transcript trùng danh sách"}
        d["talk_seconds"] = round(d["talk_seconds"], 1)
    return {"speakers": sorted(labels.values(), key=lambda d: -d["segments"]),
            "note": "Claude phải xác định tên thật cho từng nhãn dựa trên bằng chứng (tự giới thiệu, được gọi tên, "
                    "vai trò). Không chắc chắn → ghi 'Chưa xác định' và hỏi người dùng."}


# ======================================================================= chính
def classify_inputs(paths: list[str]) -> dict[str, Path | None]:
    found: dict[str, Path | None] = {"transcript": None, "video": None, "audio": None}
    for p in paths:
        path = Path(p).expanduser()
        if not path.exists():
            raise AgentError(f"Không tìm thấy file: {path}", "Kiểm tra lại đường dẫn (có thể kéo-thả file vào khung chat).")
        if path.stat().st_size == 0:
            raise AgentError(f"File rỗng (0 byte): {path.name}")
        ext = path.suffix.lower()
        kind = "transcript" if ext in TEXT_EXT else "video" if ext in VIDEO_EXT else "audio" if ext in AUDIO_EXT else None
        if kind is None:
            raise AgentError(f"Định dạng chưa hỗ trợ: {path.name}",
                             "Hỗ trợ: transcript (.txt .docx .vtt .srt .json .md), audio (.mp3 .wav .m4a…), video (.mp4 .mov .mkv…).")
        found[kind] = path
    if not any(found.values()):
        raise AgentError("Chưa có file đầu vào nào.")
    return found


def prepare(inputs: list[str], out: Path, participants_path: str | None, title: str, date: str,
            num_speakers: int | None, model: str | None, keep_audio: bool = False) -> dict[str, Any]:
    cfg = load_config()
    if model:
        cfg["whisper_model"] = model
    t0 = time.time()
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    steps = []

    def step(name, status, detail="", t=None):
        steps.append({"step": name, "status": status, "detail": detail, "seconds": round(time.time() - (t or t0), 1)})

    found = classify_inputs(inputs)
    participants = load_participants(Path(participants_path)) if participants_path else []
    if participants_path:
        step("Đọc danh sách người tham gia", "ok", f"{len(participants)} người")
    write_json(work / "participants.json", participants)
    if participants:
        cfg["_max_speakers"] = len(participants)

    media_path = found["video"] or found["audio"]
    media: dict[str, Any] = {"kind": "transcript", "path": None}
    if media_path:
        t1 = time.time()
        info = probe_media(media_path)
        kind = "video" if info["has_video"] else "audio"
        if found["video"] and not info["has_video"]:
            log(f"   ⚠ {media_path.name} không có hình ảnh → xử lý như file âm thanh.")
        media = {"kind": kind, "path": str(media_path.resolve()), "duration": info["duration"],
                 "duration_ts": sec_to_ts(info["duration"]), "has_audio": info["has_audio"]}
        step("Đọc thông tin media", "ok", f"{kind}, {sec_to_ts(info['duration'])}", t1)

    segs: list[dict[str, Any]]
    source = ""
    if found["transcript"]:
        t1 = time.time()
        segs = load_transcript(found["transcript"])
        source = f"transcript: {found['transcript'].name}"
        if not segs:
            raise AgentError(f"Không đọc được nội dung nào trong {found['transcript'].name}",
                             "File có thể là bản scan/ảnh. Hãy xuất transcript dạng chữ (.txt/.docx/.vtt).")
        step("Đọc transcript", "ok", f"{len(segs)} đoạn", t1)
        no_spk = all(s["speaker"] == UNKNOWN for s in segs)
        if media_path and media.get("has_audio") and no_spk and all(s["start"] is not None for s in segs):
            wav = work / "audio16k.wav"
            extract_wav(media_path, wav)
            turns = diarize(wav, cfg, num_speakers)
            if turns:
                for s in segs:
                    end = s["end"] or s["start"] + 3
                    spk = speaker_at(turns, s["start"], end)
                    s["speaker"] = f"SPK{spk + 1}" if spk is not None else UNKNOWN
                step("Nhận diện người nói theo giọng", "ok", f"{len({t[2] for t in turns})} giọng")
            if not keep_audio:
                wav.unlink(missing_ok=True)
    elif media_path:
        if not media.get("has_audio"):
            raise AgentError(f"{media_path.name} không có âm thanh nên không thể lập biên bản.",
                             "Cung cấp thêm transcript hoặc file ghi âm.")
        wav = work / "audio16k.wav"
        t1 = time.time()
        extract_wav(media_path, wav)
        words = transcribe(wav, cfg, [p["name"] for p in participants])
        if not words:
            raise AgentError("Không nhận được lời nói nào trong file (có thể im lặng hoặc quá nhiễu).")
        step("Chuyển giọng nói thành chữ (Whisper)", "ok", f"{len(words)} từ, model {cfg.get('whisper_model')}", t1)
        t2 = time.time()
        turns = diarize(wav, cfg, num_speakers)
        step("Nhận diện người nói theo giọng", "ok" if turns else "bỏ qua",
             f"{len({t[2] for t in turns})} giọng" if turns else "thiếu thư viện/model", t2)
        segs = words_to_segments(words, turns or [])
        source = f"phiên âm tự động từ {media_path.name}"
        if not keep_audio:
            wav.unlink(missing_ok=True)

    # gán mã đoạn
    for i, s in enumerate(segs, 1):
        s["id"] = f"S{i:04d}"
        if s["end"] is None and s["start"] is not None:
            nxt = segs[i]["start"] if i < len(segs) else None
            s["end"] = nxt if nxt is not None else s["start"] + 5
    has_times = any(s["start"] is not None for s in segs)

    if media["kind"] == "transcript" and has_times:
        last = max((s["end"] or s["start"] or 0) for s in segs)
        media["duration_ts"] = "≈ " + sec_to_ts(last)
    transcript = {"source": source, "has_timestamps": has_times, "segments": segs,
                  "filtered_hallucinations": cfg.get("_dropped_hallucinations", [])}
    write_json(work / "transcript.json", transcript)
    md = [f"# Transcript đã chuẩn hoá ({source})", "",
          "Mỗi dòng: MÃ_ĐOẠN [thời điểm] NHÃN_NGƯỜI_NÓI: nội dung. Dẫn chứng trong minutes.json phải chép NGUYÊN VĂN từ đây.", ""]
    for s in segs:
        when = f"[{sec_to_ts(s['start'])}]" if s["start"] is not None else f"[dòng {s['line']}]"
        md.append(f"{s['id']} {when} {s['speaker']}: {s['text']}")
    (work / "transcript.md").write_text("\n".join(md), encoding="utf-8")

    spk = speaker_report(segs, participants)
    write_json(work / "speakers.json", spk)
    write_json(work / "media.json", media)

    meeting = {"title": title or "", "date": date or "", "start_time": "", "location": "", "chair": "",
               "purpose": "", "source": source}
    template = {
        "meeting": meeting,
        "speaker_map": {d["label"]: ({"name": d["auto_match"]["name"], "basis": d["auto_match"]["basis"],
                                      "confidence": "cao"} if d["auto_match"] else
                                     {"name": UNKNOWN, "basis": "", "confidence": "thấp"}) for d in spk["speakers"]},
        "speaker_overrides": {},
        "summary": [], "timeline": [], "decisions": [], "action_items": [], "open_issues": [], "key_moments": [],
        "reviewed_not_actionable": [], "notes_for_reviewer": []}
    if not (out / "minutes.json").exists():
        write_json(out / "minutes.template.json", template)
    step("Chuẩn hoá transcript", "ok", f"{len(segs)} đoạn, {len(spk['speakers'])} nhãn người nói")
    run_log = {"prepared_at": time.strftime("%Y-%m-%d %H:%M:%S"), "inputs": [str(Path(p).resolve()) for p in inputs],
               "participants_file": participants_path, "steps": steps}
    write_json(work / "run_log.json", run_log)

    log("")
    log(f"✅ Đã chuẩn bị xong trong {time.time() - t0:.0f} giây")
    log(f"   Nguồn: {source} | Loại media: {media['kind']} | {len(segs)} đoạn | {len(spk['speakers'])} nhãn người nói")
    log(f"   → Đọc: {work / 'transcript.md'}")
    log(f"   → Người nói: {work / 'speakers.json'}")
    log(f"   → Mẫu cần điền: {out / 'minutes.template.json'}  (lưu thành minutes.json)")
    return {"segments": len(segs), "media": media, "speakers": spk}
