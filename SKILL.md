---
name: bien-ban-hop
description: Agent lập biên bản cuộc họp từ transcript, file ghi âm (MP3/WAV/M4A) hoặc video (MP4) — nhận diện người nói, tóm tắt diễn biến và quyết định có dẫn chứng nguyên văn, chụp ảnh từ video tại các mốc quan trọng (hoặc tạo hình minh hoạ khi chỉ có audio), xuất biên bản HTML + PDF gọn, dễ đọc (tối đa 4 trang, ảnh dẫn chứng nằm ngay trong phần diễn biến), bảng Action Items Excel, và soạn email giao việc riêng cho từng người — chỉ gửi qua Gmail sau khi người dùng phê duyệt. Dùng skill này bất cứ khi nào người dùng nhắc tới biên bản họp, tóm tắt cuộc họp, meeting minutes, ghi chép họp, file ghi âm/ghi hình cuộc họp, transcript Google Meet/Zoom/Teams, action items, giao việc sau họp, gửi email phân công sau cuộc họp — kể cả khi họ chỉ thả một file .mp3/.mp4/.txt và nói "tóm tắt giúp", "làm biên bản", "ai làm gì sau buổi họp này".
---

# Agent Biên bản họp (PEAS)

| PEAS | Nội dung |
|---|---|
| **P – Kết quả** | Tóm tắt chính xác, không bỏ sót quyết định/công việc, đúng người phụ trách, mọi ý có dẫn chứng nguyên văn, không bịa. Biên bản HTML/PDF gọn, dễ đọc, tối đa 4 trang (`max_pages`). |
| **E – Môi trường** | Thư mục trên máy, Google Drive và Gmail (qua connector có sẵn của Claude). |
| **A – Hành động** | Đọc nguồn → nhận diện người nói → tóm tắt & quyết định → ảnh chụp video / hình minh hoạ → xuất & mở biên bản → Action Items Excel → email riêng từng người → gửi sau khi được duyệt. |
| **S – Đầu vào** | Transcript (.txt .docx .vtt .srt .json), audio (.mp3 .wav .m4a), video (.mp4 .mov .mkv), danh sách người tham gia + email (.csv .xlsx .json .txt hoặc gõ trong chat). |

Phân vai: **script** làm phần máy móc (phiên âm, tách giọng, kiểm chứng, chụp ảnh, dàn trang, Excel, email). **Claude (bạn)** đọc hiểu transcript và viết `minutes.json`. Script kiểm chứng sẽ chặn mọi thông tin không có trong nguồn, nên đừng cố "làm đẹp" bằng suy đoán.

`SKILL` dưới đây là thư mục chứa file này. Mọi lệnh chạy bằng `python "<SKILL>/scripts/mm.py" …` (dùng Bash hoặc PowerShell, nhớ đặt đường dẫn trong ngoặc kép vì có dấu cách/tiếng Việt).

## Nguyên tắc không được vi phạm

1. **Không suy đoán**: người phụ trách, thời hạn, email, ngày họp, danh tính người nói. Thiếu thì ghi `Chưa xác định` / để `null` và hỏi người dùng.
2. **Mọi mục đều có dẫn chứng chép nguyên văn** từ `work/transcript.md` (không sửa chính tả, không ghép câu của người khác).
3. **Không gửi email khi chưa được phê duyệt rõ ràng** trong chat cho đúng danh sách người nhận và nội dung đó. Thiếu email → hỏi, không đoán từ tên/tên miền.
4. Ảnh chụp từ video là bằng chứng; hình tạo cho audio chỉ là minh hoạ và luôn được gắn nhãn như vậy (script tự làm).
5. Không đưa dữ liệu cuộc họp lên dịch vụ nào khác ngoài Gmail/Drive của người dùng khi họ đã đồng ý.

## Quy trình

### Bước 0 — Kiểm tra máy (lần đầu hoặc khi lỗi)
```bash
python "<SKILL>/scripts/mm.py" doctor
```
Thiếu thư viện → bảo người dùng nhấp đúp `<SKILL>/CAI-DAT.bat` (hoặc bạn chạy `powershell -ExecutionPolicy Bypass -File "<SKILL>/setup.ps1"` sau khi hỏi). Thiếu Python/FFmpeg: hướng dẫn theo `HUONG-DAN-SU-DUNG.md`.

### Bước 1 — Thu thập đầu vào
- **File trên máy**: dùng đường dẫn người dùng đưa (kéo-thả vào chat). Nếu họ chỉ nói "file họp hôm qua", tìm bằng Glob trong thư mục làm việc / Downloads rồi xác nhận lại.
- **Google Drive** (connector Google Drive): `search_files` → transcript dạng Docs/txt thì `read_file_content` và lưu thành `.txt` trong thư mục đầu ra. File audio/video lớn: nhờ người dùng tải về máy (connector trả về base64, không phù hợp file lớn). Xem [references/gmail-drive.md](references/gmail-drive.md).
- **Gmail**: `search_threads` (vd. `subject:(transcript OR "ghi chú cuộc họp" OR "Notes by Gemini")`) → `get_thread`; lưu nội dung transcript thành `.txt`. Danh sách người nhận lời mời họp có thể dùng làm gợi ý danh sách người tham gia — phải để người dùng xác nhận.
- **Danh sách người tham gia**: nếu người dùng gõ trong chat, ghi thành `nguoi-tham-gia.csv` (cột `Họ tên,Email,Vai trò,Tên gọi khác`). Không có danh sách vẫn chạy được, nhưng phải hỏi trước bước email.
- Tên cuộc họp, ngày họp: chỉ điền khi nguồn hoặc người dùng cung cấp. Không có ngày họp thì không quy đổi được "thứ Sáu tuần sau" thành ngày cụ thể.

### Bước 2 — Chuẩn bị (phiên âm + nhận diện giọng)
```bash
python "<SKILL>/scripts/mm.py" prepare --input "<file>" [--input "<file thứ 2>"] --participants "<ds.csv>" --out "<thư mục>" --title "<tên>" --date YYYY-MM-DD [--speakers N]
```
- Thư mục đầu ra mặc định nên là `<thư mục làm việc>/bien-ban/<ngày>-<tên-ngắn>`.
- Video + transcript cùng lúc: chữ lấy từ transcript, ảnh lấy từ video.
- Audio/video không có transcript: Whisper `large-v3-turbo` chạy trên máy (~0,5× thời lượng ghi âm trên CPU; một cuộc họp 1 giờ mất khoảng 30 phút). Báo trước cho người dùng và chạy nền (`run_in_background`) nếu dài hơn 10 phút. Cần nhanh hơn thì dùng `--model small` (kém chính xác hơn).
- Biết chắc số người phát biểu → thêm `--speakers N` để tách giọng chính xác hơn.

### Bước 3 — Claude phân tích và viết `minutes.json`
1. Đọc **toàn bộ** `<out>/work/transcript.md` (dài thì đọc từng phần bằng offset/limit, không bỏ đoạn nào) và `<out>/work/speakers.json`.
2. **Nhận diện người nói**: gán nhãn `SPK1…` cho tên thật chỉ khi có căn cứ: tự giới thiệu ("em là Bảo"), được gọi tên ngay trước lượt nói rồi trả lời, vai trò được nhắc. Ghi `basis` cụ thể kèm mã đoạn. Không chắc → `Chưa xác định`, rồi hỏi người dùng bằng cách trích 1–2 câu mẫu của nhãn đó. Tách giọng có thể nhầm từng đoạn (độ chính xác thường 80–90%). Khi ngữ cảnh cho thấy rõ một đoạn là của người khác, sửa bằng `speaker_overrides` cho đoạn đó, kèm căn cứ.
3. Copy `<out>/minutes.template.json` → `<out>/minutes.json` và điền theo [references/minutes-schema.md](references/minutes-schema.md). Đọc file schema trước khi viết.
4. **Viết ngắn, dễ đọc**: tóm tắt 4–6 ý, mỗi ý ≤ 25 từ; diễn biến 5–10 mục, mỗi mục 1–2 câu (≤ 40 từ) và ghi `start`; câu trích dẫn đầu tiên của mỗi mục là câu rõ nghĩa nhất (đó là câu được in ra).
5. Lỗi phiên âm rõ ràng ("than toán" → thanh toán): diễn giải đúng trong `text`/`task`, nhưng `quote` vẫn chép nguyên văn transcript.

### Bước 4 — Kiểm chứng (lặp đến khi đạt)
```bash
python "<SKILL>/scripts/mm.py" validate --out "<thư mục>"
```
- Dẫn chứng không tìm thấy → chép lại đúng câu trong transcript, hoặc bỏ ý đó.
- Người phụ trách không có trong dẫn chứng → thêm câu cho thấy việc được giao/nhận, hoặc đổi thành `Chưa xác định`.
- **`review_candidates`** (đoạn có từ khoá chốt/giao việc chưa được xử lý): đọc lại từng đoạn. Nếu là quyết định/công việc/vấn đề mở thì bổ sung; nếu không thì thêm vào `reviewed_not_actionable` kèm `reason`. Đây là chốt chặn chống bỏ sót: **không được** đưa đoạn vào danh sách bỏ qua chỉ để vượt kiểm tra.
- Cảnh báo (⚠) không chặn xuất bản nhưng phải được nêu trong báo cáo cho người dùng.

### Bước 5 — Xuất bản và mở biên bản
```bash
python "<SKILL>/scripts/mm.py" render --out "<thư mục>"
```
Lệnh này tạo và **tự mở** `bien-ban.html` và `bien-ban.pdf`, kèm `action-items.xlsx`, thư mục `email/`, `hinh-anh/`, `bao-cao-PEAS.md` và `manifest.json`. Mẫu mặc định `compact`: một khối tiêu đề + chỉ số, Tóm tắt, Diễn biến (mỗi mục: giờ, tiêu đề, 1–2 câu, 1 câu trích dẫn, **ảnh dẫn chứng ngay bên cạnh**), Quyết định, Kế hoạch hành động, Vấn đề còn mở, ghi chú kiểm chứng. Video → ảnh chụp thật tại mốc trong mục (tự bỏ ảnh trùng slide). Audio → hình minh hoạ có nhãn. Vượt `max_pages` (mặc định 4) → script tự thu gọn ảnh/chữ; vẫn vượt thì báo ⚠ và Claude phải rút gọn `minutes.json` rồi xuất lại. Bản dài kiểu ebook có bìa: `render --layout ebook` (chỉ khi người dùng yêu cầu). Không tạo được PDF → báo người dùng mở HTML và bấm "In / Lưu PDF".

**Trình đọc web** (`bien-ban-doc.html`, tạo cùng lúc): trang đọc một cột kiểu máy đọc sách, gồm Tóm tắt nhanh, Kế hoạch hành động (khung QUAN TRỌNG, sắp theo hạn/người, sao chép việc từng người), Quyết định, Sơ đồ, Diễn biến (ảnh dẫn chứng trong từng chủ đề), Vấn đề còn mở, Kiểm chứng; thanh đáy Mục lục · Tìm không dấu · Chia sẻ · Hiển thị (cỡ chữ, giãn dòng, nền Giấy/Sepia/Tối). Khi người dùng muốn link chia sẻ: đăng `<out>/artifact/bien-ban-doc.html` bằng công cụ Artifact (publish, icon `document`, kèm description một câu) và đưa link claude.ai — trang ở chế độ riêng tư cho tới khi họ bấm Share. Muốn khoá: `render --out … --password "<mật khẩu>"` (nội dung mã hoá AES-GCM; không ghi mật khẩu vào file nào khác, nhắc người dùng gửi mật khẩu riêng với link).

Báo cáo cho người dùng (ngắn gọn, theo PEAS): số quyết định, số công việc (có/chưa có người phụ trách, có/chưa có thời hạn), tỉ lệ dẫn chứng đã kiểm chứng, các cảnh báo, kèm link tới các file.

### Bước 6 — Cổng gửi email (bắt buộc theo thứ tự)
1. Đọc `<out>/email/email_plan.json`. Trình bày bảng: người nhận, email, số việc, tiêu đề, file đính kèm, trạng thái.
2. **Thiếu email** (`thiếu email`) → hỏi người dùng địa chỉ của từng người. Sau khi họ trả lời, chạy cho từng người:
   `python "<SKILL>/scripts/mm.py" set-email --out "<thư mục>" --name "<Họ tên>" --email <địa chỉ>`
   Người dùng không cung cấp → không gửi cho người đó, và ghi rõ trong báo cáo.
3. **Kiểm tra Gmail đã kết nối chưa**: tìm công cụ Gmail `send_message` / `create_draft` (dùng ToolSearch nếu đang bị hoãn tải). Nếu không có, hoặc gọi bị lỗi xác thực → **yêu cầu người dùng kết nối Gmail qua connector có sẵn**: claude.ai → Settings → Connectors → Gmail → Connect (trong Claude Code: gõ `/mcp` để đăng nhập lại). Trong lúc chờ, các file `.eml` trong `email/` vẫn mở được bằng Outlook/Thunderbird để gửi tay.
4. Mở `<out>/email/xem-truoc-email.html` cho người dùng xem. Hỏi rõ: **"Gửi N email cho [danh sách tên + email]?"** — các lựa chọn: Gửi ngay / Chỉ tạo bản nháp trong Gmail / Sửa nội dung / Chưa gửi.
5. Chỉ khi người dùng đồng ý rõ ràng: với từng email, đọc `<out>/<payload>` (JSON có sẵn `to, subject, body, htmlBody, attachments`) rồi gọi Gmail `send_message` (hoặc `create_draft` nếu họ chọn nháp) với **đúng** các trường đó. Không thêm người nhận, không đổi nội dung đã được duyệt.
6. Sau mỗi email: `python "<SKILL>/scripts/mm.py" mark-sent --out "<thư mục>" --name "<Họ tên>" --message-id <id> [--status "đã tạo nháp"]`. Gửi lỗi → báo lỗi, **không tự gửi lại**, hỏi hướng xử lý.
7. Nội dung hoặc danh sách người nhận thay đổi sau khi duyệt → trình lại phần thay đổi và xin duyệt lại.

Email gửi qua connector có đính kèm phiếu giao việc Excel riêng và lịch nhắc hạn `.ics`. PDF biên bản thường quá nặng để gửi qua connector. Nếu người dùng muốn kèm biên bản: họ tải PDF lên Drive và đưa link, sau đó chạy `render --out … --only-emails --minutes-link "<link>"` rồi xin duyệt lại. Bản `.eml` cục bộ đã có sẵn PDF đính kèm.

### Bước 7 (tuỳ chọn) — Lưu lên Google Drive
Khi người dùng yêu cầu: tải `action-items.xlsx` lên bằng `create_file` (base64, file nhỏ). Có thể chia sẻ cho người phụ trách bằng `share_file` **sau khi hỏi**. PDF/HTML lớn: hướng dẫn kéo-thả vào drive.google.com.

## Xử lý tình huống
| Tình huống | Cách làm |
|---|---|
| Transcript không có nhãn người nói, có video/audio đi kèm | `prepare` tự gán nhãn theo giọng; Claude xác định tên như Bước 3.2 |
| Hai người cùng nhận một việc | `owner` = người chính, còn lại ghi vào `supporters`. Không rõ ai chính → `Chưa xác định` + ghi chú |
| "Thứ Sáu tuần sau" mà không có ngày họp | `deadline: null`, `deadline_text: "thứ Sáu tuần sau"`; hỏi ngày họp nếu người dùng muốn quy đổi |
| Ý kiến đề xuất nhưng chưa chốt | Đưa vào `open_issues`, không đưa vào `decisions` |
| Phiên âm có câu lạ lặp lại ("Hãy subscribe cho kênh…") | Whisper ảo giác khi có nhạc nền. `prepare` đã tắt cơ chế dựa vào câu trước và tự lọc theo `hallucination_patterns` (ghi lại trong `transcript.json → filtered_hallucinations`). Còn sót thì thêm mẫu vào `config.json` rồi chạy lại `prepare`; không dùng câu đó làm dẫn chứng |
| File hỏng / định dạng lạ / file rỗng | Script báo lỗi tiếng Việt kèm cách xử lý; chuyển nguyên văn lỗi cho người dùng |
| PDF scan (ảnh) | Không hỗ trợ trực tiếp; nhờ người dùng xuất transcript dạng chữ |
| Lỗi không mong muốn | Xem `bien-ban-loi.log` trong thư mục làm việc |

## Tự kiểm thử
```bash
python "<SKILL>/scripts/mm.py" selftest            # đầy đủ: transcript + video + audio + 13 ca lỗi (~6 phút)
python "<SKILL>/scripts/mm.py" selftest --quick    # chỉ transcript + ca lỗi (~30 giây)
```
Báo cáo được ghi vào `bien-ban-tu-kiem-thu/bao-cao-tu-kiem-thu.md`, trình bày theo PEAS.

Cấu hình (model Whisper, ngưỡng kiểm chứng, từ khoá chống bỏ sót, tên người gửi): `config.json`. Muốn ghi đè riêng cho máy này thì tạo `config.local.json`. Hướng dẫn cho người dùng cuối: `HUONG-DAN-SU-DUNG.md`.
