# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (trong `src/`, backend REPLAY: verdict của judge lưu sẵn trong CSV).
Lớp dương tính = `FAIL` (việc của judge là tìm lỗi).

| Tiêu chí | n | κ | Precision | Recall | Ma trận (tp/fp/fn/tn) | Tỉ lệ fail quan sát → Rogan-Gladen | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | 24 / 4 / 6 / 66 | 0.28 → 0.30 | **Đạt** (exit 0) | **dùng** — chỉ để theo dõi giọng văn, không chặn release về tiền |
| helpful | 100 | 0.375 | 1.000 | **0.300** | 9 / 0 / 21 / 70 | 0.09 → 0.30 | **Không đạt** (κ, R dưới sàn; exit 1) | **loại** — không được dùng làm gate |

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú → sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em", "nha" quá suồng sã với khách khiếu nại; judge coi là thân thiện. Rubric thêm: *xưng hô phải là "LogiX"/"anh/chị", không "em/bạn", không tiểu từ "nha/nhé"*. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…rồi nha." | PASS | FAIL | Người | Cùng lỗi xưng hô "bạn". Gộp vào quy tắc #1, kèm 2 ví dụ FAIL có "bạn ơi". |
| 3 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Judge bị "Dạ, vui lòng" đánh lừa, bỏ qua câu ra lệnh. Rubric: *đánh giá cả câu; câu cấm khách liên hệ ("không cần nhắn thêm") = FAIL dù mở đầu lịch sự*. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric: *xin lỗi không bắt buộc; ngắn, đủ ý, lễ phép = PASS*. Thêm ví dụ PASS này vào few-shot. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | CS LogiX cho phép từ "refund". Rubric: *danh sách từ tiếng Anh được phép: refund, ship, voucher*. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống — đây là lỗi **nội dung**, không phải giọng. Tách khỏi tiêu chí tone, đưa về grader code (reply chỉ được nói điều ledger ghi; xem FM-08). |
| 7 | H-070 "…đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Rubric: *emoji cười trong ngữ cảnh khiếu nại = FAIL*. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** (về tone thì reply ổn, nhưng nhãn người dựa trên việc đọc nhầm ticket) | Nhãn người sai: người chấm trộn đúng/sai nghiệp vụ vào tone. **Sửa nhãn** trong lần gán nhãn tới và nhắc người chấm: tone chỉ chấm giọng văn. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người (lỗi nhỏ) | Lặp "Dạ" do gõ; không nên FAIL cả reply. Rubric: *lỗi gõ nhỏ không đổi nghĩa = PASS*. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341…" | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy). Rubric: *tiếng Việt không dấu = FAIL*. |
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger ghi 40.000đ) | PASS | FAIL | Người | Judge không nhìn thấy ledger nên không thể biết số sai. 18/21 FN của helpful là kiểu này (3 FN còn lại là case 13). **Không sửa rubric được** — chuyển sang grader code `ReplyMatchesLedger` (bắt 18/18 dòng có ghi chú "ledger ghi"). |
| 12 | HL-016 / HL-090 (xin lỗi dài 3 câu + số tiền sai) | PASS | FAIL | Người | Thiên vị độ dài/lời xin lỗi che mất số sai. Rubric (nếu còn dùng judge): *chấm nội dung trước, lời xin lỗi không cộng điểm*. |
| 13 | HL-047 / HL-091 / HL-097 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả (hoàn bao nhiêu / từ chối vì sao). Rubric: *reply phải nêu trạng thái và số tiền (hoặc lý do từ chối)*. |

## Kết luận

- **tone_ok dùng được**: κ 0.757, P 0.857, R 0.80 đều trên sàn. 4 FP / 6 FN còn lại phần lớn là lỗi rubric về xưng hô và câu ra lệnh (case 1–3, 7, 10) — sửa rubric như bảng trên rồi calibrate lại trên nhãn mới. Rogan-Gladen: tỉ lệ fail quan sát 0.28 → hiệu chỉnh 0.30, chênh nhỏ. Vẫn chỉ dùng để theo dõi, không chặn release.
- **helpful bị loại**, không được làm gate. Ma trận nhầm lẫn: tp 9, fn 21 → **recall 0.30**: judge bỏ sót 21/30 reply mà người đánh FAIL; κ 0.375 < 0.6. Precision 1.0 không cứu được: một gate với recall 0.3 cho 70% lỗi đi qua. Rogan-Gladen kéo 0.09 lên 0.30 (gấp hơn 3 lần) — con số đó phụ thuộc hoàn toàn vào ước lượng sensitivity 0.3 trên 30 mẫu dương, quá bất định để ra quyết định. Nguyên nhân gốc: 18/21 FN là **reply nói sai số tiền so với ledger** — judge chỉ đọc chữ, không có ledger. Tiêu chí này là tiền nên phải chấm bằng code: `reply_amount_matches_ledger` (FM-08).
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí); cần nhãn người mới để có held-out thật, và cần 2 người gán nhãn độc lập (κ người–người) để biết trần chất lượng nhãn — case 8 cho thấy nhãn người cũng sai.
