# Chuẩn trình bày kép cho biên bản

## 1. Bản web xem và chia sẻ

Tạo `bien-ban-share.html` dưới dạng trang responsive, tự chứa CSS/JavaScript và chỉ phụ thuộc vào ảnh nằm trong cùng thư mục đầu ra. Nội dung chính theo thứ tự:

1. Tiêu đề, ngày, thời lượng, nguồn và người tham gia.
2. Thẻ số liệu: số quyết định, Action Items, mục cần rà soát và ảnh có mốc.
3. Mục lục có liên kết sâu.
4. Ý chính 30 giây.
5. Kế hoạch hành động, có sắp xếp theo thời hạn/người và nút sao chép.
6. Quyết định đã chốt.
7. Slide, screenshot hoặc hình minh họa được gắn nhãn đúng loại nguồn.
8. Diễn biến có timestamp và bộ lọc theo người nói.
9. Câu hỏi còn mở, rủi ro và mục cần rà soát.
10. Thông tin kiểm chứng nguồn.

Trang phải có nút chia sẻ trang, sao chép liên kết từng phần và in. Các thao tác chia sẻ chỉ dùng URL hiện tại; không tự gửi nội dung sang dịch vụ khác.

## 2. Bản PDF

Tạo `bien-ban.pdf` khổ A4 dọc. Giữ phong cách tối giản, khoảng trắng rộng, màu nhấn nhất quán và cỡ chữ đọc được khi in. Nội dung gồm:

- Metadata và các chỉ số tóm tắt ở đầu tài liệu.
- Tóm tắt ngắn bằng gạch đầu dòng.
- Diễn biến/mốc quan trọng cùng dẫn chứng.
- Screenshot hoặc hình minh họa với caption.
- Bảng quyết định.
- Bảng kế hoạch hành động có owner, deadline và căn cứ.
- Vấn đề còn mở và ghi chú kiểm chứng.
- Footer có tên cuộc họp và số trang.

PDF và bản web phải được sinh từ cùng `analysis/meeting_data.json`.

## 3. Xuất bản trang chia sẻ

- Tạo file web cục bộ trước và kiểm tra xong mới cân nhắc xuất bản.
- Nội dung cuộc họp có thể nhạy cảm. Trình bày rõ URL dự kiến, audience và dữ liệu sẽ được tải lên; chờ người dùng xác nhận khi phạm vi chia sẻ chưa được nêu rõ.
- Khi dùng Sites, Site mới mặc định private. Chỉ public khi người dùng yêu cầu rõ.
- Sau khi triển khai thành công, ghi `sharing.json` với `status`, `url`, `audience`, `published_at` và `provider`.
- Nếu chưa triển khai, ghi `status: local_only` và không tạo URL giả.
