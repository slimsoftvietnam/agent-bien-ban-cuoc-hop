# Meeting Minutes Agent

Codex Agent Skill tạo biên bản có dẫn chứng từ transcript, audio hoặc video. Mỗi lần chạy tạo đồng thời trang web responsive dễ xem/chia sẻ và PDF A4 để lưu trữ/in, cùng bảng Action Items Excel và email nháp theo từng người. Skill không suy đoán dữ liệu thiếu, không tự công khai biên bản và không gửi email khi chưa được phê duyệt.

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

## Hai bản biên bản chính

- `bien-ban-share.html`: bản web responsive có mục lục, liên kết sâu, lọc theo người nói, sắp xếp Action Items và nút chia sẻ.
- `bien-ban.pdf`: bản A4 dọc có cùng dữ liệu, phù hợp gửi email, lưu trữ và in.

`sharing.json` luôn ghi trạng thái xuất bản. Mặc định là `local_only`; việc triển khai private/public chỉ được thực hiện khi người dùng xác nhận phạm vi chia sẻ.
