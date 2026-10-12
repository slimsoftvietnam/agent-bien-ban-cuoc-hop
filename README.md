# Meeting Minutes Agent

Codex Agent Skill tạo biên bản có dẫn chứng từ transcript, audio hoặc video. Skill xuất HTML/PDF, bảng Action Items Excel và email nháp theo từng người; không suy đoán dữ liệu thiếu và không gửi email khi chưa được người dùng phê duyệt.

## Cài đặt

Sao chép toàn bộ thư mục này vào thư mục skills của Codex, giữ nguyên tên `meeting-minutes-agent`, rồi khởi động lại hoặc tải lại danh sách skill.

Đọc [SKILL.md](SKILL.md) để xem quy tắc vận hành và [references/usage.md](references/usage.md) để chạy bằng dòng lệnh.

## Dữ liệu mẫu

- `sample/transcript.txt` và `sample/participants.json`: bộ dữ liệu nhỏ cho smoke test.
- `sample/du-lieu-mau-cuoc-hop.mp4`: video mẫu 1280×720, dài khoảng 14 phút 32 giây, dung lượng 34,3 MB.

Video mẫu được commit trực tiếp vì nhỏ hơn giới hạn 100 MB mỗi file của GitHub. Khi thay video bằng dữ liệu thật, cần xác nhận quyền chia sẻ và loại bỏ thông tin nhạy cảm trước khi push.

## Kiểm thử

```powershell
python .\tests\test_smoke.py
```

Smoke test chạy hoàn toàn cục bộ, tạo video tổng hợp tạm thời và xác nhận PDF, Excel, ảnh chụp, dữ liệu phân tích cùng email nháp chưa gửi.
