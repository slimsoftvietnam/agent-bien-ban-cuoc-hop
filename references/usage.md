# Hướng dẫn sử dụng

## 1. Chuẩn bị danh sách người tham gia

Tạo file JSON UTF-8:

```json
{
  "participants": [
    {"name": "Nguyễn Lan", "email": "lan@example.com", "aliases": ["Lan", "chị Lan"]},
    {"name": "Trần Minh", "email": "minh@example.com", "aliases": ["Minh"]}
  ]
}
```

Email có thể để trống. Agent sẽ không tự đoán địa chỉ.

## 2. Chạy với transcript

```powershell
$python = "C:\Users\ADMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python .\meeting-minutes-agent\scripts\meeting_agent.py `
  --input .\transcript.txt `
  --participants .\participants.json `
  --video .\recording.mp4 `
  --output .\outputs\meeting-001 `
  --title "Họp triển khai"
```

Mỗi lượt nói nên có dạng `[HH:MM:SS] Người nói: Nội dung`. Dạng `MM:SS` cũng được chấp nhận. Nếu không có mốc, dẫn chứng sẽ dùng số dòng và Agent không tạo ảnh video cho mục đó.

## 3. Chạy với audio hoặc video

Nếu có transcript, truyền media ở `--input` và transcript ở `--transcript`.

```powershell
& $python .\meeting-minutes-agent\scripts\meeting_agent.py --input .\meeting.mp4 --transcript .\meeting.txt --participants .\participants.json --output .\outputs\meeting-001
```

Nếu chưa có transcript, cài `faster-whisper` vào Python bạn dùng rồi chạy lại. Đây là tùy chọn cục bộ và miễn phí; lần chạy đầu sẽ cần tải model. Backend Whisper không tự phân vai người nói, vì vậy segment chưa có nhãn sẽ mang tên `Chưa xác định`.

```powershell
python -m pip install faster-whisper
```

### Video mẫu đi kèm repository

Repository có file `sample/du-lieu-mau-cuoc-hop.mp4` để thử luồng video:

- Thời lượng: khoảng 14 phút 32 giây.
- Độ phân giải: 1280 × 720, H.264/AAC.
- Dung lượng: 34.307.429 byte.
- SHA-256: `106438e461836d42c746c33fdfff7285ee2b04a926afa3a30df7e0bb40c376e1`.

Chạy phiên âm và tạo bộ đầu ra từ video mẫu:

```powershell
python .\scripts\meeting_agent.py `
  --input .\sample\du-lieu-mau-cuoc-hop.mp4 `
  --participants .\sample\participants.json `
  --output .\outputs\video-mau `
  --title "Dữ liệu mẫu cuộc họp"
```

Lần đầu dùng `faster-whisper` có thể cần tải model. Không dùng `sample/transcript.txt` làm transcript cho video này vì đó là bộ dữ liệu kiểm thử riêng.

### Hình ảnh theo loại nguồn

- Với video, lấy screenshot tại các mốc quan trọng và giữ timestamp trong chú thích.
- Với audio không có video, tạo hình minh họa hoặc đồ họa dựa trên các ý đã xác nhận trong transcript. Trong PDF/HTML phải ghi `Hình minh họa được tạo từ nội dung audio`; hình này không phải bằng chứng nguồn.
- Không tạo khuôn mặt, danh tính, khung cảnh hay diễn biến như thể đã xuất hiện trong audio.

## 4. Cấu trúc bản tóm tắt

Mỗi lần chạy phải có hai bản chính sinh từ cùng `analysis/meeting_data.json`:

- `bien-ban-share.html`: bản web responsive để xem/chia sẻ.
- `bien-ban.pdf`: bản A4 dọc để lưu trữ/in.

Cả hai bản đều phải có các nội dung sau:

1. Diễn biến cuộc họp.
2. Ý chính.
3. Hình screenshot từ video hoặc hình/đồ họa minh họa được gắn nhãn cho audio.
4. Kế hoạch hành động gồm nội dung, người phụ trách, deadline, trạng thái xác nhận và dẫn chứng.

Bản web bổ sung mục lục, liên kết sâu từng phần, lọc diễn biến theo người nói và thao tác sao chép. Bản PDF bổ sung metadata, số trang và ghi chú kiểm chứng. Xem [chuẩn trình bày kép](output-design.md).

### Xuất bản bản web

Script chỉ tạo file cục bộ và ghi `sharing.json` với trạng thái `local_only`. Khi người dùng cần URL, có thể triển khai toàn bộ thư mục đầu ra lên Sites hoặc dịch vụ static hosting đã được kết nối. Phải xác nhận audience trước khi đưa nội dung cuộc họp lên mạng; Site mới nên để private trừ khi người dùng yêu cầu public rõ ràng.

## 5. Phê duyệt và gửi email

Các file `.eml` có header `X-Unsent: 1`. Việc gửi phải đi qua các bước sau:

1. Kiểm tra Gmail. Nếu chưa kết nối, yêu cầu người dùng kết nối và dừng tại bước gửi.
2. Soạn email riêng cho từng người tham gia có Action Items và đính kèm PDF tóm tắt.
3. Hỏi địa chỉ email của từng người nhận hoặc yêu cầu xác nhận ánh xạ tên - email đã có.
4. Trình nội dung email, người nhận và file đính kèm cho người dùng kiểm tra.
5. Chờ xác nhận gửi rõ ràng rồi mới gọi công cụ gửi Gmail.

Nếu nội dung hoặc người nhận thay đổi sau khi phê duyệt, phải xin xác nhận lại. Không tự gửi lại email thất bại.

## 6. Định dạng được hỗ trợ

- Transcript: TXT, DOCX, PDF có lớp chữ.
- Audio: MP3, WAV, M4A và các định dạng FFmpeg đọc được.
- Video: MP4, MOV, MKV và các định dạng FFmpeg đọc được.
- Danh sách người tham gia: JSON.

## 7. Cấu hình

File `config/default.json` chứa từ khóa nhận diện quyết định, công việc và các thiết lập xuất bản. Chỉ mở rộng từ khóa khi cách nói đó thực sự thể hiện cam kết; từ khóa quá rộng dễ tạo Action Item giả.

Đặc biệt, từ `sẽ` đứng riêng không được coi là tín hiệu giao việc vì thường xuất hiện trong câu mô tả hoặc giảng giải. Cấu hình mặc định chỉ nhận các mẫu cam kết rõ hơn như `tôi sẽ`, `em sẽ`, `phụ trách` hoặc `cần hoàn thành`; mọi kết quả vẫn phải được rà soát theo ngữ cảnh.
