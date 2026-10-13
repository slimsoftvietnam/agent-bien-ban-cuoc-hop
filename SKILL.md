---
name: meeting-minutes-agent
description: Tạo biên bản cuộc họp có dẫn chứng từ transcript, audio hoặc video; xuất đồng thời trang web dễ xem/chia sẻ và PDF A4, kèm Action Items, hình ảnh và email nháp sau khi xác nhận. Dùng khi cần tóm tắt họp mà không được suy đoán thông tin thiếu, tự công khai dữ liệu hoặc tự gửi email.
---

# Meeting Minutes Agent

Tạo một bộ hồ sơ cuộc họp có thể kiểm chứng. Ưu tiên bằng chứng trong nguồn hơn câu chữ trôi chảy.

## Nguyên tắc bắt buộc

- Không suy đoán người phụ trách, deadline, email, quyết định hoặc danh tính người nói.
- Mọi quyết định và Action Item phải giữ mốc thời gian, người nói và câu dẫn chứng. Nếu nguồn không có mốc, dùng số dòng hoặc số trang.
- Ghi `Chưa xác định`, `Chưa nêu` hoặc `Cần rà soát` khi dữ liệu thiếu hay mâu thuẫn.
- Không gọi công cụ gửi email cho đến khi đã soạn xong, cho người dùng xem nội dung/đính kèm, hỏi địa chỉ người nhận và nhận xác nhận gửi rõ ràng.
- Luôn tạo hai bản biên bản chính từ cùng một dữ liệu đã kiểm chứng: `bien-ban-share.html` để xem/chia sẻ và `bien-ban.pdf` để lưu trữ/in. Không để nội dung giữa hai bản mâu thuẫn.
- Tạo trang web cục bộ không đồng nghĩa với công khai. Trước khi xuất bản trang cho người khác truy cập, phải trình bày rõ phạm vi chia sẻ (private/public hoặc danh sách người có quyền) và chỉ xuất bản sau khi người dùng xác nhận.
- Ảnh chụp từ video là bằng chứng nguồn. Ảnh/đồ họa tạo cho audio chỉ là minh họa, phải ghi rõ `Hình minh họa được tạo từ nội dung audio` và không được dùng làm dẫn chứng.
- Không đưa dữ liệu cuộc họp lên dịch vụ ngoài nếu người dùng chưa cho phép.

## Quy trình

1. Xác nhận đầu vào và danh sách người tham gia. Khi nguồn ở Google Drive hoặc Gmail, chỉ đọc các tệp nằm trong phạm vi người dùng chỉ định.
2. Chạy bộ tiền xử lý:

   ```powershell
   python scripts/meeting_agent.py --input <transcript-or-media> --participants <participants.json> --output <output-dir> --title "<tên cuộc họp>" --video <video.mp4>
   ```

   Với audio/video chưa có transcript, script thử backend `faster-whisper` cục bộ. Nếu backend chưa cài, dừng và yêu cầu transcript hoặc đọc hướng dẫn cài đặt trong [hướng dẫn sử dụng](references/usage.md). Không tự tạo transcript giả.
3. Tạo phần hình ảnh theo loại nguồn:
   - **Có video:** chụp các mốc quan trọng, giữ timestamp và chú thích nội dung liên quan. Ưu tiên mốc có quyết định, thay đổi chủ đề, số liệu hoặc kế hoạch hành động.
   - **Chỉ có audio:** tạo hình minh họa hoặc đồ họa tóm lược các ý đã được xác nhận trong transcript. Có thể dùng công cụ tạo ảnh hoặc sơ đồ cục bộ; không dựng khuôn mặt, danh tính, phòng họp hay sự kiện như thể chúng xuất hiện trong nguồn. Gắn nhãn minh họa rõ ràng trong PDF/HTML.
   - **Chỉ có transcript/tài liệu:** dùng trích đoạn hoặc ảnh trang tài liệu khi hữu ích; không gọi đó là screenshot cuộc họp nếu nguồn không có hình ảnh.
4. Đọc `analysis/meeting_data.json` và `analysis/review_queue.json`. Kiểm tra các mục `Cần rà soát` trước khi trình bày như thông tin đã xác nhận.
5. Soạn phần tóm tắt theo đúng thứ tự sau:
   1. **Diễn biến cuộc họp:** dòng thời gian theo các chủ đề và mốc nguồn.
   2. **Ý chính:** kết luận, quyết định, vấn đề còn mở và dẫn chứng tương ứng.
   3. **Hình ảnh:** screenshot có timestamp từ video, hoặc hình/đồ họa được gắn nhãn minh họa khi nguồn chỉ có audio.
   4. **Kế hoạch hành động:** công việc, người phụ trách, deadline, trạng thái xác nhận và dẫn chứng. Không có dữ liệu thì ghi `Chưa nêu`.
6. Tạo hai bản biên bản theo [chuẩn trình bày kép](references/output-design.md):
   - **Bản web:** responsive, có mục lục, liên kết sâu từng phần, nút chia sẻ/sao chép, lọc diễn biến theo người nói, sắp xếp Action Items và ảnh có chú thích.
   - **Bản PDF:** khổ A4 dọc, ưu tiên đọc/in, có metadata, số liệu tóm tắt, diễn biến kèm dẫn chứng, ảnh, quyết định, Action Items và mục cần rà soát.
7. Kiểm tra trực quan cả trang web và toàn bộ trang PDF; xác nhận font tiếng Việt, ảnh, bảng, liên kết và dữ liệu khớp nhau. Nếu sửa dữ liệu phân tích, chạy lại script để mọi đầu ra đồng bộ.
8. Nếu người dùng cần URL chia sẻ và Sites đang khả dụng, triển khai thư mục đầu ra như một static Site. Mặc định tạo Site private; chỉ đổi sang public hoặc mở quyền cho người khác sau xác nhận rõ ràng. Ghi URL và audience vào `sharing.json`. Nếu không có hosting, bàn giao `bien-ban-share.html` và nêu rõ đây mới là bản cục bộ.
9. Chuẩn bị email riêng cho từng người tham gia có công việc; đính kèm PDF tóm tắt và nêu đúng Action Items của người đó. Sau khi soạn xong, thực hiện cổng gửi email bên dưới.
10. Khi Google Drive được kết nối, chỉ tải đầu ra lên vị trí người dùng chỉ định.

## Cổng gửi email bắt buộc

1. Kiểm tra Gmail trước khi tạo/gửi trên Gmail. Nếu chưa kết nối, yêu cầu người dùng kết nối Gmail; vẫn có thể hoàn tất các file cục bộ nhưng không được báo rằng email đã được tạo hoặc gửi trên Gmail.
2. Soạn xong tiêu đề, nội dung, danh sách file đính kèm và email riêng cho từng người trước khi hỏi gửi.
3. Hỏi người dùng địa chỉ email của từng người cần nhận, hoặc trình bày ánh xạ tên - email đã có để người dùng xác nhận. Không suy đoán địa chỉ từ tên hay tên miền.
4. Cho người dùng xem bản nháp hoặc tóm lược chính xác của từng email, người nhận và file đính kèm; sau đó dừng và chờ xác nhận gửi rõ ràng.
5. Chỉ gửi sau xác nhận cuối cùng. Nếu danh sách người nhận hoặc nội dung thay đổi, trình lại phần thay đổi và chờ xác nhận mới.
6. Báo kết quả theo từng người nhận với trạng thái gửi và mã thư nếu có. Không tự gửi lại khi lỗi; nêu lỗi và xin hướng xử lý.

## Đầu ra chuẩn

- `bien-ban-share.html`: bản web responsive để người dùng xem, tìm, lọc, sao chép và chia sẻ từng phần. Video dùng screenshot; audio dùng hình/đồ họa được gắn nhãn minh họa.
- `bien-ban.pdf`: bản A4 dọc để lưu trữ/in, có cùng dữ liệu đã kiểm chứng với bản web.
- `bien-ban.html`: bản tương thích có cùng nội dung với `bien-ban-share.html`.
- `sharing.json`: trạng thái cục bộ hoặc URL/audience đã triển khai; không được ghi `published` nếu chưa có kết quả xác nhận từ dịch vụ hosting.
- `action-items.xlsx`: một bảng thao tác được, có owner, email, deadline, trạng thái và dẫn chứng.
- `email-drafts/*.eml`: một nháp riêng cho từng người có công việc; chỉ điền người nhận sau khi địa chỉ đã được người dùng cung cấp hoặc xác nhận.
- `analysis/meeting_data.json`: dữ liệu chuẩn để kiểm toán hoặc chỉnh sửa.
- `analysis/peas-report.json`: kết quả theo PEAS, giới hạn và hàng đợi rà soát.
- `manifest.json`: danh sách file cùng SHA-256.

## Xử lý ngoại lệ

- Speaker không khớp danh sách: giữ nguyên nhãn nguồn, đánh dấu `Chưa xác định`.
- Một việc có nhiều owner nhưng câu nguồn không phân vai: giữ nguyên danh sách owner và đánh dấu rà soát.
- Deadline tương đối như “thứ Sáu” nhưng không có ngày họp: không quy đổi thành ngày cụ thể.
- Video không có mốc tương ứng: bỏ ảnh và nêu lý do trong báo cáo PEAS.
- Audio không có hình: tạo minh họa từ các ý đã có bằng chứng; nếu không thể tạo ảnh, dùng đồ họa chữ/sơ đồ và ghi rõ giới hạn thay vì giả lập screenshot.
- Gmail chưa kết nối: yêu cầu kết nối và dừng tại bước gửi; không chuyển sang cách gửi khác nếu người dùng chưa yêu cầu.
- PDF scan không có lớp chữ: dừng với hướng dẫn OCR; không kết luận từ trang trắng.

Định dạng người tham gia và các lệnh đầy đủ nằm trong [hướng dẫn sử dụng](references/usage.md). Schema dữ liệu nằm trong [hợp đồng dữ liệu](references/data-contract.md).
