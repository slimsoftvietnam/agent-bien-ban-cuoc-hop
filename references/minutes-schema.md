# Cấu trúc `minutes.json` (Claude viết)

Mỗi mục `evidence` là danh sách `{"quote": "...", "seg": "S0012"}`. Chỉ `quote` là bắt buộc. Trường `seg` giúp tìm nhanh hơn.
`quote` phải là đoạn **chép nguyên văn**, liền mạch, nằm trong 1 đoạn (hoặc 2 đoạn liên tiếp) của `work/transcript.md`. Nên dài 6–25 từ, đủ để người đọc hiểu.
Script tự bổ sung thời điểm, người nói và mức khớp. Đừng tự ghi các trường này.

```jsonc
{
  "meeting": {
    "title": "Tên cuộc họp",               // từ người dùng/nguồn
    "date": "2026-10-12",                  // YYYY-MM-DD, "" nếu không biết — KHÔNG đoán
    "start_time": "",                      // "09:00" nếu nguồn có
    "location": "",                        // "" → hiển thị "Chưa nêu"
    "chair": "Nguyễn Minh Anh",            // chỉ khi rõ ràng từ nguồn
    "purpose": "1–2 câu mục đích cuộc họp"
  },
  "speaker_map": {                         // nhãn trong transcript → người thật
    "SPK1": {"name": "Nguyễn Minh Anh", "basis": "S0001 tự giới thiệu 'tôi là Minh Anh'", "confidence": "cao"},
    "SPK4": {"name": "Chưa xác định", "basis": "", "confidence": "thấp"}
  },
  "speaker_overrides": {                   // tuỳ chọn: sửa người nói cho TỪNG đoạn khi tách giọng sai
    "S0016": {"name": "Lê Thu Hà", "basis": "Trả lời 'Dạ vâng, em sẽ gửi' ngay sau khi chủ trì gọi tên Thu Hà (S0015)"}
  },
  "summary": [                             // 4–6 ý, mỗi ý 1 câu ≤ 25 từ, có số liệu cụ thể
    {"text": "...", "evidence": [{"quote": "..."}]}
  ],
  "timeline": [                            // 5–10 mục theo chủ đề, đúng thứ tự thời gian; summary 1–2 câu ≤ 40 từ
    {"topic": "Học phí", "summary": "Ai đề xuất gì, ai phản biện, kết quả.", "evidence": [{"quote": "..."}]}
    // có thể thêm "start"/"end" dạng "00:12:30"; bỏ trống thì lấy theo dẫn chứng
  ],
  "decisions": [                           // CHỈ những gì đã chốt/thống nhất/phê duyệt
    {"id": "QĐ1", "text": "Quyết định, viết rõ con số", "rationale": "lý do nếu được nêu",
     "evidence": [{"quote": "câu chốt"}, {"quote": "câu nêu lý do"}]}
  ],
  "action_items": [
    {"id": "CV1", "task": "Động từ + việc cụ thể", "owner": "Họ tên ĐÚNG như danh sách | Chưa xác định",
     "supporters": ["Họ tên"],              // tuỳ chọn
     "deadline": "2026-10-16",              // YYYY-MM-DD hoặc null
     "deadline_text": "thứ Sáu ngày 16 tháng 10", // cụm từ GỐC trong dẫn chứng; null nếu không nêu
     "priority": "Cao | Trung bình | Thấp",  // "Cao" khi có hạn gần/được nhấn mạnh; mặc định "Trung bình"
     "deliverable": "kết quả bàn giao, nếu được nêu",
     "notes": "ví dụ: Quy đổi “chiều nay” theo ngày họp 12/10/2026",
     "evidence": [{"quote": "câu giao việc"}, {"quote": "câu nhận việc"}]}
  ],
  "open_issues": [                         // đề xuất chưa chốt, câu hỏi bỏ ngỏ, việc chưa có người làm
    {"id": "VĐ1", "text": "...", "evidence": [{"quote": "..."}]}
  ],
  "key_moments": [                         // 4–8 mốc; ảnh/minh hoạ được đặt vào mục diễn biến chứa mốc đó
    {"title": "≤ 6 từ", "caption": "1 câu", "icon": "money",
     "time": "00:00:49",                   // tuỳ chọn; bỏ trống = thời điểm dẫn chứng + 1 giây
     "evidence": [{"quote": "..."}]}
  ],
  "reviewed_not_actionable": [             // đoạn có từ khoá "chốt/giao/sẽ…" nhưng KHÔNG phải quyết định/việc
    {"quote": "Hôm nay chúng ta họp để chốt kế hoạch", "reason": "Giới thiệu chương trình"}
  ],
  "notes_for_reviewer": ["Điều người đọc cần biết: phần ghi âm bị nhiễu ở 00:31–00:33, ..."]
}
```

`icon` dùng một trong các giá trị: `money, calendar, team, chart, rocket, megaphone, code, cart, document, warning, check, idea, target, handshake, clock, mic`. Bỏ trống thì script tự chọn theo nội dung.

## Quy tắc viết

- **Biên bản tối đa 4 trang, phải dễ đọc**: câu ngắn, mỗi ý một dòng, không lặp lại giữa Tóm tắt và Diễn biến. Mục diễn biến nên có `"start": "00:12:30"` (giờ bắt đầu chủ đề). Câu trích dẫn **đầu tiên** của mỗi mục được in ra, nên đặt câu rõ nghĩa nhất lên đầu.

- **Một đoạn phiên âm gộp lời 2 người** (vd. câu trả lời ngắn dính vào câu của người kế tiếp): ghi người nói cho riêng câu trích dẫn: `{"quote": "Em sẽ cấp quyền…", "speaker": "Lê Thu Hà", "speaker_basis": "Trả lời ngay sau khi được giao việc ở S0013"}`.
- **Tách giọng có thể sai** (nhất là giọng gần giống nhau hoặc nói chen). Khi ngữ cảnh cho thấy rõ một đoạn là của người khác (đáp lời ngay sau khi được gọi tên, tự xưng tên, nói đúng phần việc mình vừa nhận), sửa bằng `speaker_overrides` và ghi căn cứ. Không chắc thì hỏi người dùng.
- **Quyết định và công việc là hai thứ khác nhau.** "Chốt học phí 1.490.000đ" là quyết định. "Long cập nhật bảng giá trước 20/10" là công việc. Một câu nói có thể sinh ra cả hai.
- **Một việc chỉ có một `owner`.** Chỉ nhận người khi dẫn chứng cho thấy họ được giao hoặc tự nhận: được gọi tên trong câu giao việc, hoặc chính họ nói "em sẽ…/em nhận…". Script sẽ chặn nếu không thấy căn cứ.
- **Thời hạn**: `deadline_text` là cụm từ gốc trong dẫn chứng. Chỉ quy đổi sang `deadline` (ngày cụ thể) khi đã biết ngày họp, và phải ghi cách quy đổi vào `notes`. "Cuối tuần", "sớm", "khi nào xong" → `deadline: null`.
- **Đề xuất bị bác hoặc thay thế** nêu trong `rationale` hoặc `timeline`, không đưa vào `decisions`.
- **Số liệu** giữ đúng như nguồn. Phiên âm ghi "1,490.000" thì `text` ghi "1.490.000đ", còn `quote` giữ nguyên "1,490.000".
- **Văn phong** tiếng Việt chuẩn mực, khách quan, câu ngắn, không thêm nhận xét cá nhân.
- **Không bỏ sót**: rà lại toàn bộ transcript tìm các câu "chốt, thống nhất, đồng ý, giao, phụ trách, sẽ, nhận, trước ngày, hạn…". Script `validate` cũng liệt kê những đoạn này trong `review_candidates`.
