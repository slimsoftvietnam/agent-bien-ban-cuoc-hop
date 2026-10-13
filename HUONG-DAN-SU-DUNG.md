# Hướng dẫn sử dụng — Agent Biên bản họp

Agent nhận **transcript, file ghi âm hoặc video cuộc họp** và trả về:

- 📘 **Biên bản gọn, tối đa 4 trang** (`bien-ban.html` + `bien-ban.pdf`): tóm tắt, diễn biến cuộc họp (ảnh chụp từ video / hình minh hoạ nằm ngay cạnh từng mục), quyết định, kế hoạch hành động, vấn đề còn mở. Mỗi mục kèm thời điểm và câu nói gốc để đối chiếu. Muốn bản dài kiểu ebook có bìa, nói với Claude "xuất bản ebook".
- 📊 **Bảng Action Items Excel** (`action-items.xlsx`): có danh sách chọn trạng thái, tô đỏ việc quá hạn, tổng hợp theo người.
- ✉️ **Email giao việc riêng cho từng người**, kèm phiếu giao việc Excel và lịch nhắc hạn. Agent **chỉ gửi khi bạn đồng ý**.

Mọi công cụ đều **miễn phí và chạy trên máy bạn**: Whisper chuyển giọng nói thành chữ, sherpa-onnx tách người nói, Edge/Chrome xuất PDF. Dữ liệu cuộc họp không bị gửi lên dịch vụ lạ.

---

## 1. Cài đặt (một lần, khoảng 10–20 phút)

1. Mở thư mục `.claude\skills\bien-ban-hop` (thư mục `.claude` bị ẩn: trong File Explorer chọn **View → Show → Hidden items**).
2. **Nhấp đúp `CAI-DAT.bat`**. Script tự cài những gì còn thiếu: Python, FFmpeg, thư viện, model nhận giọng (~1,7 GB, tải một lần).
3. Cuối cùng màn hình hiện danh sách ✅. Có dòng ❌ thì chụp màn hình gửi cho Claude.
4. **Kết nối Gmail** (để gửi email): vào **claude.ai → Settings → Connectors → Gmail → Connect**, chọn tài khoản Google và bấm **Allow**. Muốn Agent đọc file trên Drive thì kết nối thêm **Google Drive**.

> Skill nằm trong thư mục dự án, nên Claude Code tự nhận khi bạn mở **đúng thư mục `Khóa học AI Agent`**. Muốn dùng ở mọi thư mục, chép cả thư mục `bien-ban-hop` vào `C:\Users\<tên bạn>\.claude\skills\`.

## 2. Sử dụng — chỉ cần nói chuyện với Claude

Kéo-thả file vào khung chat của Claude Code rồi gõ, ví dụ:

- `Làm biên bản cuộc họp từ file này. Người tham gia: Lan (lan@example.com), Minh (minh@example.com), Hùng.`
- `/bien-ban-hop tóm tắt file ghi âm họp-sáng-thứ-2.mp3, họp ngày 12/10/2026`
- `Tìm transcript cuộc họp "Kế hoạch Q4" trên Google Drive và làm biên bản, gửi việc cho từng người`
- `Lấy transcript trong email Google Meet gửi hôm qua và làm biên bản`

Claude sẽ lần lượt:
1. Hỏi thêm những gì còn thiếu: tên cuộc họp, ngày họp, danh sách người tham gia. **Agent không tự đoán.**
2. Phiên âm và nhận diện ai nói câu nào. Một cuộc họp 1 giờ mất khoảng 30 phút trên máy thường.
3. Viết biên bản, tự kiểm tra lại từng dẫn chứng, rồi **mở biên bản HTML và PDF** cho bạn xem.
4. Đưa ra danh sách email giao việc. **Thiếu email của ai thì hỏi bạn.**
5. Hỏi **"Gửi N email này?"** — bạn chọn *Gửi ngay*, *Chỉ tạo nháp trong Gmail*, *Sửa* hoặc *Chưa gửi*.

### Danh sách người tham gia (khuyến nghị)
Có thể gõ thẳng vào chat, hoặc tạo file Excel/CSV gồm các cột:

| Họ tên | Email | Vai trò | Tên gọi khác |
|---|---|---|---|
| Nguyễn Minh Anh | minhanh@example.com | Giám đốc dự án | Minh Anh |
| Trần Quốc Bảo | bao@example.com | Kỹ thuật | Bảo |

Cột "Tên gọi khác" giúp Agent nhận ra khi trong họp mọi người gọi nhau bằng tên ngắn ("anh Bảo", "chị Minh Anh").

## 3. Định dạng file được hỗ trợ

| Loại | Đuôi file | Ghi chú |
|---|---|---|
| Transcript | `.txt .docx .vtt .srt .json .md` | Google Meet, Zoom, Microsoft Teams, hoặc tự gõ dạng `[00:01:02] Tên: nội dung` |
| Ghi âm | `.mp3 .wav .m4a .aac .ogg .flac` | Chỉ có âm thanh → Agent vẽ hình minh hoạ và biểu đồ dạng sóng |
| Video | `.mp4 .mov .mkv .webm .avi` | Agent chụp ảnh màn hình tại các mốc quan trọng |

Có cả video và transcript thì đưa cả hai: chữ lấy từ transcript (chính xác hơn), ảnh lấy từ video.

## 4. Kết quả nằm ở đâu?

`bien-ban\<ngày>-<tên-cuộc-họp>\` trong thư mục làm việc:

```
bien-ban.html            ← mở bằng trình duyệt (đẹp nhất), có nút "In / Lưu PDF"
bien-ban.pdf             ← bản in A4
action-items.xlsx        ← bảng theo dõi công việc
email\xem-truoc-email.html   ← xem trước toàn bộ email trước khi duyệt
email\*.eml              ← mở bằng Outlook nếu muốn tự gửi (đã đính kèm PDF)
email\phieu-giao-viec\   ← phiếu giao việc Excel riêng từng người
hinh-anh\                ← ảnh chụp từ video / hình minh hoạ
bao-cao-PEAS.md          ← báo cáo chất lượng (dẫn chứng, độ đầy đủ, cảnh báo)
minutes.json             ← dữ liệu biên bản (sửa ở đây rồi nhờ Claude xuất lại)
```

## 5. Câu hỏi thường gặp

**Biên bản có bịa thông tin không?** Mọi quyết định và công việc phải kèm câu nói gốc. Chương trình kiểm chứng sẽ chặn xuất bản nếu có câu dẫn chứng không tìm thấy trong bản ghi, nếu gán người phụ trách mà không có căn cứ, hoặc nếu thời hạn không được nói trong họp. Những gì cuộc họp không nêu sẽ ghi "Chưa nêu" hoặc "Chưa xác định".

**Có bỏ sót việc không?** Agent quét mọi câu có từ như "chốt, thống nhất, giao, phụ trách, em sẽ, trước ngày…". Câu nào chưa được xử lý thì không cho xuất bản cho tới khi được xem xét. Bạn có thể thêm từ khoá trong `config.json` → `coverage_keywords`.

**Nhận sai người nói?** Nhận diện theo giọng không hoàn hảo, nhất là khi nhiều người nói chen nhau. Mục *Phụ lục → Nhận diện người nói* ghi rõ căn cứ của từng người. Sai thì nói với Claude, ví dụ: "SPK2 là chị Lan", Claude sẽ sửa và xuất lại.

**Muốn nhanh hơn?** Nói "dùng chế độ nhanh" (model `small`, nhanh gấp 3 lần nhưng kém chính xác hơn), hoặc đổi `whisper_model` trong `config.json`.

**Đổi tên người ký email?** Ghi tên vào `"sender_name"` trong `config.json`.

**Email có đính kèm PDF biên bản không?** Email gửi qua Gmail có kèm phiếu giao việc Excel và lịch nhắc hạn. PDF thường quá nặng để gửi qua connector, nên bạn tải PDF lên Google Drive và đưa link cho Claude, Claude sẽ chèn link vào email. File `.eml` trong máy thì đã kèm sẵn PDF.

**Lỗi thì sao?** Agent báo lỗi bằng tiếng Việt kèm cách xử lý. Lỗi lạ được ghi vào `bien-ban-loi.log`; gửi file này cho Claude để được hỗ trợ.

## 6. Tự kiểm tra Agent

Nói với Claude: `chạy tự kiểm thử skill biên bản họp`. Agent sẽ tự tạo một cuộc họp mẫu (transcript, MP3 có 4 giọng đọc, MP4 có slide), chạy cả 3 kịch bản cùng 13 tình huống lỗi, rồi ghi báo cáo theo PEAS vào `bien-ban-tu-kiem-thu\bao-cao-tu-kiem-thu.md`.
