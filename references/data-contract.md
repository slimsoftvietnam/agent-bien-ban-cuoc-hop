# Hợp đồng dữ liệu

`analysis/meeting_data.json` là nguồn sự thật cho các đầu ra xuất bản.

- `source`: đường dẫn, loại tệp và SHA-256 của đầu vào.
- `speakers`: nhãn nguồn, danh tính đã khớp và trạng thái xác nhận.
- `segments`: từng lượt nói với `timestamp`, `speaker`, `text` và `evidence_ref`.
- `decisions`: nội dung quyết định, mốc, người nói, trích dẫn và trạng thái rà soát.
- `action_items`: `id`, `task`, `owner`, `owner_email`, `deadline_text`, `deadline_iso`, `evidence_quote`, `evidence_ref`, `review_status`.
- `screenshots`: ảnh lấy trực tiếp từ video, mốc giây và mục quyết định/công việc liên quan. Không lưu ảnh sinh từ audio vào trường này.
- `illustrations`: hình/đồ họa được tạo từ nội dung audio, ý nguồn liên quan, prompt/mô tả tạo ảnh và nhãn bắt buộc `Hình minh họa được tạo từ nội dung audio`. Minh họa không được dùng làm evidence.
- `review_queue`: vấn đề cần người dùng xác nhận.

Email chỉ được gửi khi đã có đủ ba trạng thái kiểm soát: Gmail đã kết nối, địa chỉ người nhận đã được người dùng cung cấp/xác nhận, và người dùng đã xác nhận bản nháp cuối cùng cùng file đính kèm. Nếu hệ thống ghi lịch sử gửi, lưu trạng thái và mã thư theo từng người nhận; không suy ra thành công chỉ từ việc tạo draft.

Không xóa dữ liệu thiếu bằng chuỗi rỗng. Dùng `Chưa xác định`, `Chưa nêu` hoặc `null` theo đúng trường, đồng thời thêm lý do vào `review_queue`.
