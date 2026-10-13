"""Tạo dữ liệu mẫu để tự kiểm thử: transcript.txt, cuoc-hop-mau.mp3 (4 giọng đọc), cuoc-hop-mau.mp4 (slide + tiếng),
nguoi-tham-gia.csv và ground_truth.json. Giọng đọc dùng Microsoft Edge TTS miễn phí (cần Internet lần đầu)."""
from __future__ import annotations

import asyncio
import subprocess
import wave
from pathlib import Path

from mmlib import SKILL_DIR, AgentError, find_ffmpeg, log, sec_to_ts, write_json

SAMPLES = SKILL_DIR / "samples"
PEOPLE = {
    "Nguyễn Minh Anh": (["vi-VN-HoaiMyNeural", "en-US-AvaMultilingualNeural"], "Giám đốc dự án", "minhanh@example.com"),
    "Trần Quốc Bảo": (["en-US-BrianMultilingualNeural", "vi-VN-NamMinhNeural"], "Trưởng nhóm kỹ thuật", "bao.tran@example.com"),
    "Lê Thu Hà": (["en-US-EmmaMultilingualNeural", "en-US-AvaMultilingualNeural"], "Trưởng nhóm marketing", "ha.le@example.com"),
    "Phạm Đức Long": (["en-US-AndrewMultilingualNeural", "en-AU-WilliamMultilingualNeural"], "Phụ trách kinh doanh", ""),  # cố ý thiếu email
}
SLIDES = {
    "agenda": ("Họp kế hoạch ra mắt khoá học AI Agent", ["1. Học phí", "2. Nội dung khoá học", "3. Kế hoạch truyền thông"]),
    "tech": ("Tiến độ nền tảng học", ["Hệ thống sẵn sàng: 80%", "Còn thiếu: thanh toán tự động", "Hạn: thứ Sáu 16/10"]),
    "price": ("Phương án học phí", ["Đề xuất A: 1.990.000đ (như khoá trước)", "Khảo sát: đa số chọn < 1.500.000đ"]),
    "price_ok": ("QUYẾT ĐỊNH: Học phí ưu đãi", ["1.490.000đ", "Áp dụng cho 100 học viên đầu tiên"]),
    "course": ("Cấu trúc khoá học", ["8 buổi", "2 buổi thực hành xây agent với dữ liệu thật", "Đề xuất: +1 buổi bảo mật dữ liệu (chưa chốt)"]),
    "mkt": ("Kế hoạch truyền thông", ["Quảng cáo Facebook + TikTok", "Bắt đầu: 25/10", "Duyệt kế hoạch & ngân sách: thứ Tư 21/10"]),
    "risk": ("Việc còn treo", ["Kiểm tra điều khoản bảo mật hợp đồng", "đối tác phòng học trực tuyến", "Người phụ trách: chưa phân công"]),
    "wrap": ("Tổng kết", ["Học phí ưu đãi 1.490.000đ", "Khoá học 8 buổi", "Quảng cáo từ 25/10", "Họp tiếp: sáng thứ Hai tuần tới"]),
}
SCRIPT = [
    ("Nguyễn Minh Anh", "agenda", "Chào mọi người, tôi là Minh Anh. Hôm nay chúng ta họp để chốt kế hoạch ra mắt khóa học AI Agent vào tháng mười một. Có ba nội dung: học phí, nội dung khóa học, và kế hoạch truyền thông."),
    ("Trần Quốc Bảo", "tech", "Chào chị, em là Bảo bên kỹ thuật. Về nền tảng học, hệ thống đã sẵn sàng khoảng tám mươi phần trăm, còn thiếu phần thanh toán tự động."),
    ("Nguyễn Minh Anh", "tech", "Vậy Bảo hoàn thiện phần thanh toán tự động trước thứ Sáu ngày 16 tháng 10 được không?"),
    ("Trần Quốc Bảo", "tech", "Dạ được chị, em nhận việc này và sẽ hoàn thành trước thứ Sáu ngày 16 tháng 10."),
    ("Phạm Đức Long", "price", "Mình là Long bên kinh doanh. Về học phí, mình đề xuất một triệu chín trăm chín mươi nghìn đồng như khóa trước."),
    ("Lê Thu Hà", "price", "Em là Thu Hà phụ trách marketing. Em nghĩ mức đó hơi cao với học viên mới, khảo sát cho thấy đa số chọn mức dưới một triệu rưỡi."),
    ("Nguyễn Minh Anh", "price_ok", "Sau khi cân nhắc, chúng ta chốt học phí ưu đãi một triệu bốn trăm chín mươi nghìn đồng cho một trăm học viên đầu tiên."),
    ("Phạm Đức Long", "price_ok", "Đồng ý với chị. Mình sẽ cập nhật bảng giá và kịch bản tư vấn cho đội bán hàng trước ngày 20 tháng 10."),
    ("Nguyễn Minh Anh", "course", "Tiếp theo là nội dung khóa học. Chúng ta thống nhất khóa học gồm tám buổi, trong đó có hai buổi thực hành xây dựng agent với dữ liệu thật."),
    ("Trần Quốc Bảo", "course", "Em đề xuất thêm một buổi về bảo mật dữ liệu khi dùng agent, vì học viên doanh nghiệp rất quan tâm."),
    ("Nguyễn Minh Anh", "course", "Ý hay, nhưng việc thêm buổi thứ chín thì để tuần sau bàn tiếp khi có phản hồi từ giảng viên."),
    ("Lê Thu Hà", "mkt", "Về truyền thông, em sẽ chạy chiến dịch quảng cáo trên Facebook và TikTok, bắt đầu từ ngày 25 tháng 10."),
    ("Nguyễn Minh Anh", "mkt", "Thu Hà gửi kế hoạch truyền thông chi tiết và ngân sách cho tôi duyệt trước thứ Tư ngày 21 tháng 10 nhé."),
    ("Lê Thu Hà", "mkt", "Dạ vâng, em sẽ gửi trước thứ Tư ngày 21 tháng 10."),
    ("Phạm Đức Long", "risk", "Còn hợp đồng với đối tác cung cấp phòng học trực tuyến thì cần ai đó kiểm tra lại điều khoản bảo mật."),
    ("Nguyễn Minh Anh", "risk", "Đúng rồi, việc kiểm tra hợp đồng này cần làm trong tháng này, tôi sẽ sắp xếp người sau."),
    ("Trần Quốc Bảo", "mkt", "Ngoài ra em cần quyền truy cập tài khoản quảng cáo để gắn mã theo dõi chuyển đổi lên trang đăng ký."),
    ("Lê Thu Hà", "mkt", "Em sẽ cấp quyền cho anh Bảo ngay trong chiều nay."),
    ("Nguyễn Minh Anh", "wrap", "Tóm lại, chúng ta đã chốt học phí ưu đãi, cấu trúc tám buổi và ngày bắt đầu quảng cáo là 25 tháng 10. Cuộc họp sau vào sáng thứ Hai tuần tới. Cảm ơn mọi người."),
]
GAP = 0.6


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    for f in (["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{f}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def slide(key: str, speaker: str, path: Path) -> None:
    from PIL import Image, ImageDraw
    title, bullets = SLIDES[key]
    im = Image.new("RGB", (1280, 720), "#FBF8F2")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1280, 110], fill="#1F5C6B")
    d.text((60, 30), title, font=_font(44, True), fill="#FBF8F2")
    color = "#D9693A" if key == "price_ok" else "#1D2329"
    for i, b in enumerate(bullets):
        y = 170 + i * 82
        d.ellipse([62, y + 18, 80, y + 36], fill="#D9693A")
        d.text((100, y), b, font=_font(46 if key == "price_ok" and i == 0 else 38, key == "price_ok" and i == 0), fill=color)
    d.rectangle([0, 640, 1280, 720], fill="#1D2329")
    d.ellipse([40, 660, 80, 700], fill="#3C7A4F")
    d.text((96, 658), f"Đang nói: {speaker}", font=_font(30, True), fill="#FFFFFF")
    d.text((930, 664), "Google Meet · Ghi hình", font=_font(24), fill="#B8C0C8")
    im.save(path)


async def _tts1(text: str, voice: str, out: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="+8%").save(str(out))


def _tts(text: str, voices: list[str], out: Path) -> None:
    for v in voices:  # giọng đọc đôi khi tạm ngừng phục vụ → thử giọng dự phòng
        try:
            asyncio.run(_tts1(text, v, out))
            if out.exists() and out.stat().st_size > 1000:
                return
        except Exception:
            pass
    raise AgentError(f"Không tạo được giọng đọc mẫu ({', '.join(voices)}).", "Kiểm tra kết nối Internet rồi chạy lại.")


def make_samples(force: bool = False) -> dict:
    SAMPLES.mkdir(exist_ok=True)
    mp3, mp4 = SAMPLES / "cuoc-hop-mau.mp3", SAMPLES / "cuoc-hop-mau.mp4"
    txt, gt = SAMPLES / "transcript-mau.txt", SAMPLES / "ground_truth.json"
    csvp = SAMPLES / "nguoi-tham-gia.csv"
    csvp.write_text("Họ tên,Email,Vai trò,Tên gọi khác\n" + "\n".join(
        f"{n},{e},{r},{n.split()[-1]}" + (";Thu Hà" if n == "Lê Thu Hà" else ";Minh Anh" if n == "Nguyễn Minh Anh" else "")
        for n, (_, r, e) in PEOPLE.items()) + "\n", encoding="utf-8-sig")
    if mp3.exists() and mp4.exists() and txt.exists() and gt.exists() and not force:
        return {"mp3": mp3, "mp4": mp4, "transcript": txt, "participants": csvp, "ground_truth": gt}
    ff = find_ffmpeg()
    if not ff:
        raise AgentError("Cần FFmpeg để tạo dữ liệu mẫu.")
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        raise AgentError("Cần edge-tts để tạo giọng đọc mẫu.", "python -m pip install edge-tts")
    tmp = SAMPLES / "_tmp"
    tmp.mkdir(exist_ok=True)
    log("Đang tạo giọng đọc mẫu (Edge TTS)…")
    rate = 24000
    frames = bytearray()
    t = 0.0
    lines, truth, concat = [], [], []
    for i, (who, key, text) in enumerate(SCRIPT):
        a = tmp / f"{i:02d}.mp3"
        w = tmp / f"{i:02d}.wav"
        if not a.exists():
            _tts(text, PEOPLE[who][0], a)
        subprocess.run([ff, "-y", "-v", "error", "-i", str(a), "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(w)], check=True)
        with wave.open(str(w)) as wf:
            data = wf.readframes(wf.getnframes())
        dur = len(data) / 2 / rate
        lines.append(f"[{sec_to_ts(t)}] {who}: {text}")
        truth.append({"start": round(t, 2), "end": round(t + dur, 2), "speaker": who, "text": text})
        png = tmp / f"s{i:02d}.png"
        slide(key, who, png)
        concat += [f"file '{png.as_posix()}'", f"duration {dur + GAP:.3f}"]
        frames += data + b"\x00\x00" * int(GAP * rate)
        t += dur + GAP
    concat.append(f"file '{(tmp / f's{len(SCRIPT) - 1:02d}.png').as_posix()}'")
    wav_all = tmp / "all.wav"
    with wave.open(str(wav_all), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))
    subprocess.run([ff, "-y", "-v", "error", "-i", str(wav_all), "-c:a", "libmp3lame", "-b:a", "64k", str(mp3)], check=True)
    (tmp / "list.txt").write_text("\n".join(concat), encoding="utf-8")
    log("Đang dựng video mẫu…")
    subprocess.run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"), "-i", str(mp3),
                    "-vf", "fps=5,format=yuv420p", "-c:v", "libx264", "-tune", "stillimage", "-crf", "28",
                    "-c:a", "aac", "-b:a", "64k", "-shortest", str(mp4)], check=True)
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(gt, {"meeting_date": "2026-10-12", "segments": truth})
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    log(f"✅ Dữ liệu mẫu: {mp3.name} ({t:.0f}s), {mp4.name}, {txt.name}")
    return {"mp3": mp3, "mp4": mp4, "transcript": txt, "participants": csvp, "ground_truth": gt}


if __name__ == "__main__":
    make_samples(force=True)
