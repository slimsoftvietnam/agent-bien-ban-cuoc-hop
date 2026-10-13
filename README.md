# Agent Biên bản họp — skill `bien-ban-hop` cho Claude Code

Agent lập biên bản cuộc họp từ **transcript, file ghi âm hoặc video**. Agent nhận diện người nói, tóm tắt diễn biến, quyết định và công việc. Mọi ý đều kèm **câu trích dẫn nguyên văn** từ bản ghi. Đầu ra gồm: biên bản PDF tối đa 4 trang, trang đọc trên web, bảng Action Items Excel và email giao việc riêng cho từng người. Email **chỉ được gửi qua Gmail khi bạn duyệt**.

Phiên âm, tách giọng, chụp ảnh và dàn trang đều chạy **trên máy, bằng công cụ miễn phí**. Claude đọc hiểu nội dung; một bước kiểm chứng tự động sẽ chặn mọi thông tin không có trong bản ghi.

## Agent làm được gì (PEAS)

| | |
|---|---|
| **P – Kết quả** | Tóm tắt chính xác, không bỏ sót quyết định và công việc, đúng người phụ trách, có dẫn chứng, không bịa. Biên bản gọn, dễ đọc. |
| **E – Môi trường** | Thư mục trên máy, Google Drive, Gmail (qua connector có sẵn của Claude). |
| **A – Hành động** | Đọc nguồn → nhận diện người nói → tóm tắt và chốt quyết định → ảnh chụp video / hình minh hoạ → xuất biên bản → Action Items → email giao việc → gửi sau khi duyệt. |
| **S – Đầu vào** | Transcript (`.txt .docx .vtt .srt .json`), ghi âm (`.mp3 .wav .m4a`), video (`.mp4 .mov .mkv`), danh sách người tham gia và email. |

**Đầu ra mỗi cuộc họp** (thư mục `bien-ban/<ngày>-<tên>/`):

- `bien-ban.pdf` / `bien-ban.html`: biên bản A4, tối đa 4 trang. Ảnh chụp từ video nằm ngay trong phần Diễn biến; nếu chỉ có ghi âm thì dùng hình minh hoạ có ghi chú rõ.
- `bien-ban-doc.html`: trang đọc trên web kiểu máy đọc sách. Có mục lục, tìm kiếm không dấu, chia sẻ, chỉnh cỡ chữ và nền Giấy/Sepia/Tối, có thể khoá bằng mật khẩu (AES-GCM). Đăng được thành link claude.ai.
- `action-items.xlsx`: bảng theo dõi công việc, có danh sách chọn trạng thái và tô màu việc quá hạn.
- `email/`: email riêng cho từng người, kèm phiếu giao việc Excel và lịch nhắc hạn `.ics`.
- `bao-cao-PEAS.md`: báo cáo chất lượng (tỉ lệ dẫn chứng khớp, cảnh báo, việc cần bổ sung).

## Cài đặt

**Yêu cầu:** Windows 10/11, [Claude Code](https://claude.com/claude-code), khoảng 2 GB trống cho model.

1. Tải skill vào thư mục skills của Claude Code:
   ```powershell
   git clone https://github.com/slimsoftvietnam/agent-bien-ban-cuoc-hop "$env:USERPROFILE\.claude\skills\bien-ban-hop"
   ```
   Chỉ muốn dùng trong một dự án thì clone vào `<dự án>\.claude\skills\bien-ban-hop`.
2. Nhấp đúp **`CAI-DAT.bat`** trong thư mục vừa tải. Script tự cài Python, FFmpeg và các thư viện còn thiếu, rồi tải model nhận giọng (khoảng 1,7 GB, chỉ tải một lần).
3. Muốn gửi email: vào **claude.ai → Settings → Connectors → Gmail → Connect**.

## Sử dụng

Kéo file vào khung chat của Claude Code rồi gõ, ví dụ:

- `Làm biên bản cuộc họp từ file này. Người tham gia: Lan (lan@example.com), Minh (minh@example.com).`
- `/bien-ban-hop tóm tắt file ghi âm hop-sang-thu-2.mp3, họp ngày 12/10/2026`
- `Tìm transcript cuộc họp "Kế hoạch Q4" trên Google Drive và làm biên bản`

Agent sẽ hỏi lại những gì còn thiếu (ngày họp, email…) thay vì tự đoán. Agent mở biên bản cho bạn xem, rồi hỏi **"Gửi N email này?"** trước khi gửi.

Hướng dẫn chi tiết cho người không biết lập trình: [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md). Quy trình Claude làm theo: [SKILL.md](SKILL.md).

## Cách đảm bảo không bịa và không bỏ sót

- Mỗi quyết định và công việc phải có câu nói gốc. Bước `validate` dò câu đó trong transcript và **chặn xuất bản** nếu không tìm thấy.
- Người phụ trách phải xuất hiện trong dẫn chứng (được gọi tên hoặc chính người đó nhận việc). Thời hạn phải được nói trong cuộc họp. Thiếu thì ghi "Chưa xác định" / "Chưa nêu".
- Mọi câu có từ khoá như "chốt", "giao", "em sẽ", "trước ngày"… đều phải được xử lý: đưa vào biên bản, hoặc ghi lý do bỏ qua.
- Bộ phiên âm tự lọc các câu "ảo giác" quen thuộc của Whisper ("Hãy subscribe cho kênh…") và phiên âm lại đoạn bị che.

## Cấu trúc

```
SKILL.md                 quy trình cho Claude
HUONG-DAN-SU-DUNG.md     hướng dẫn người dùng
CAI-DAT.bat, setup.ps1   cài đặt 1 lần
config.json              model Whisper, số trang tối đa, từ khoá chống bỏ sót, mẫu lọc ảo giác
scripts/                 mm.py (lệnh chính), prepare, validate, render, compact, reader, emails, excel…
assets/                  giao diện biên bản và trang đọc web
references/              cấu trúc minutes.json, hướng dẫn Gmail/Drive
samples/                 cuộc họp mẫu (transcript, MP3, MP4) để tự kiểm thử
models/                  model nhận giọng (tải bằng setup.ps1, không lưu trên GitHub)
```

Lệnh chính (Claude tự chạy, bạn không cần gõ):

```bash
python scripts/mm.py doctor      # kiểm tra máy
python scripts/mm.py prepare --input <file> --out <thư mục>
python scripts/mm.py validate --out <thư mục>
python scripts/mm.py render   --out <thư mục> [--password <mật khẩu>]
python scripts/mm.py selftest    # tự kiểm thử với dữ liệu mẫu
```

## Công cụ sử dụng (đều miễn phí)

[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (phiên âm) · [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (tách giọng) · [FFmpeg](https://ffmpeg.org) · Microsoft Edge / Chrome (xuất PDF) · openpyxl (Excel) · Edge TTS (chỉ dùng để tạo dữ liệu mẫu).

---

Sản phẩm của SlimSoft · Khoá học AI Agent SlimAI.
