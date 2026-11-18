# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Case của tôi: `seeded_regression C-014@11` — trừ kép tiền đã hoàn (FM-05)

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11
python -m lab9.trace_case --shape fixed --claim C-014 --seed 11              # đối chứng
python -m pytest -q -m student -o addopts= -k trace_case                     # regression test
```

```
== seeded_regression C-014@11  lab8 grader: FAIL (proposal_mismatch)
   1 handoff            {"request_id": "REQ-C-014", "task": "check_applicable_policy", ...}
   2 investigator       {"lookup_order": {"visible": true, "order": {"order_id": "O-515", "delay_days": 5, "damage_verified": true, ...
   3 quote              {"amount_vnd": 150000, "clause_ids": ["SHIP-LATE-03", "DMG-04"], "parts": {"SHIP-LATE-03": 30000, "DMG-04": 150000}}
   4 refund_history     {"refund_count": 1, "refunded_vnd": 30000}
   5 proposal           {"amount_vnd": 120000}
   6 reply              {"text": "Dạ, LogiX đã hoàn 120.000đ cho đơn O-515."}
  refund_vnd     ledger=90000    label=120000   <-- differs
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11` (item E-014), report `reports/eval_seeded_regression.json`, run ID `E-seeded_regression-20261118-cb77` |
| Triệu chứng | `pass_rate` FAIL (`proposal_mismatch`: đề xuất 120.000, nhãn 150.000), `refund_amount_correct` FAIL (ledger **90.000**, nhãn 120.000), `quote_forwarded` FAIL, `reply_amount_matches_ledger` FAIL. Reply nói "đã hoàn **120.000đ**" — trùng đúng số nhãn — trong khi ledger chỉ ghi 90.000. Ai chỉ đọc reply (hoặc một judge so reply với nhãn) sẽ cho PASS. |
| Bước sai đầu tiên | **Event 5 `proposal` {"amount_vnd": 120000}**: agent tự trừ 30.000 đã hoàn trước đó khỏi quote 150.000 rồi mới đưa cho host. |
| Vì sao là bước *đầu tiên* | Event 1 handoff không mang fact nào; event 2 đọc đúng dòng order O-515 (trễ 5 ngày, hỏng đã xác minh); event 3 `quote` 150.000 = max(30.000 ship, 150.000 damage), đúng luật "lấy số lớn hơn, không cộng" và khớp nhãn `proposal_amount`; event 4 `refund_history` chỉ là phép đọc hợp lệ (shape `honest_refactor` cũng gọi nó và vẫn đúng). Sai bắt đầu khi số đọc được ở event 4 bị dùng để sửa quote ở event 5. Host sau đó trừ 30.000 thêm lần nữa theo trần theo đơn → 90.000. |
| Failure mode | **FM-05** (pre_deducted). Triệu chứng phụ ở event 6 là FM-08 (reply nói số agent tự tính, không phải số host ghi). |
| Đối chứng | `fixed C-014@11`: event 3 `quote` 150.000 rồi đi thẳng tới host (không có `refund_history`, không có `proposal`); host tự trừ 30.000 → ledger 120.000; reply "đã hoàn 120.000đ" khớp ledger; Lab 8 PASS. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_lab9_trace_case_pre_deduct_is_caught` (ledger 90.000; event 3–5 là `quote`, `refund_history`, `proposal`; `quote_forwarded`, `refund_amount_correct`, `reply_amount_matches_ledger` đều False) và `test_lab9_trace_case_fixed_stays_green` (cùng claim@seed trên `fixed`: ledger 120.000, cả 3 grader True). Đã chạy: fail đúng trên variant lỗi, pass trên `fixed`; test chạy trong CI (`-k "lab9 and not advanced"`). Ở mức eval set, `quote_forwarded` (min 1.0, chặn) bắt lỗi này trên mọi item có tiền hoàn trước (E-013, E-014, C-105, C-106, C-111). |
| Chưa chắc chắn | Trace không cho biết agent "định" làm gì: event 5 chỉ có con số, không có lý do. Không chứng minh được agent luôn trừ đúng bằng `refunded_vnd` hay chỉ trùng hợp ở đơn này (E-013 cũng trừ đúng 35.000 → 0, củng cố giả thuyết). Trace cũng không ghi lời gọi `issue_refund` của host, nên số 90.000 chỉ suy ra từ ledger chứ không thấy trực tiếp trong trace. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
