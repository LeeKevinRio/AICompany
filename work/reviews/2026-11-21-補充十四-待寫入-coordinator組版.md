# ADR-0030 補充十四：待寫入（coordinator 組版）

- 組版者：coordinator
- 日期：2026-11-21
- 來源：`work/reviews/2026-11-21-退役鏈同步衝突與claims註解裁示及補充十四-tech-architect.md`（tech-architect 裁示第 2 題「補充十四（可逐字寫入）」）；字面逐字取自該檔，只把檔頭行中的代稱「本裁示的轉存檔」換成實際檔名。
- 狀態：風控已審（RC-512～RC-518，`work/reviews/2026-11-21-補充十四審查RC512至RC518-風控.md`），APPROVE_WITH_CONDITIONS；required 的 RC-513（檔頭行補審查紀錄）已由 coordinator 套用；suggested 的 RC-514、RC-515 待 tech-architect 決定是否採用（採用須書面確認技術意旨不變，逐字套用即可、不必回送風控）。
- 寫入時點：append 順序 8、9、10、11、12、13、14；最晚在 CG-2 一鍵檔退役 PR 合併之前。
- 寫入位置：檔頭行接在補充十三的檔頭行之後；正文接在補充十三正文之後。

## 檔頭行

<<<檔頭行開始>>>
- 補充紀錄：2026-11-21 append 補充十四（CG-2 一鍵檔退役 PR 對 `app/forecast/claims.py` 一句過時註解的處理；tech-architect 裁示；窄幅寬於補充九第 1 點「不改 `app/`」與 S-19a 第 1 點「`app/` 零差異」的字面，已標明；不改本文、補充八～十三的字面、事先宣告 v0.32、規則檔、定義物件與已登記雜湊；不改任何 CEO 可見字面；經風控審查（RC-512～RC-518，`work/reviews/2026-11-21-補充十四審查RC512至RC518-風控.md`），接受；CEO 可推翻；來源 `work/reviews/2026-11-21-下游分支同步CG2新head交件-dev-lead.md`、`work/reviews/2026-11-21-退役鏈同步衝突與claims註解裁示及補充十四-tech-architect.md`）
<<<檔頭行結束>>>

## 正文

<<<正文開始>>>
## 補充十四：CG-2 一鍵檔退役 PR 與 `claims.py` 的過時註解（2026-11-21）

- 決策者：tech-architect。來源：`work/reviews/2026-11-21-下游分支同步CG2新head交件-dev-lead.md`、`work/reviews/2026-11-21-export寫法漏網與警示手冊維護與QuickEdit裁示-tech-architect.md`。
- 性質：第 1 點窄幅寬於補充九第 1 點「不改 `app/`」與 S-19a 第 1 點「`app/` 零差異」的字面，已標明。第 2 點為釐清。不改 CEO 可見字面。
- 背景：CG-2 登記分支依 2026-11-21 (甲) 裁示，在 `_ENV_FILE_KEY` 的 `#:` 註解中點名 `scripts/cg2_register.py`，以及一個相等斷言測試。兩者都由退役 PR 刪除。這句註解若保留，S-19a 第 1 點的 grep 必然命中，內容也不再屬實；所以補充九第 1 點的「不改 `app/`」與 S-19a 的 grep 條件不能同時成立。

1. **退役 PR 對 `app/` 的唯一允許差異**
   - 只限 `app/forecast/claims.py` 中 `_ENV_FILE_KEY` 上方的 `#:` 註解：刪去指向退役檔及其測試的那一句，包括該句在前一行的開頭片段。不新增任何字，其餘行不動。
   - `claims.py` 全模組的 AST 與退役 PR 的 merge-base 相同。補充九第 2 點「claims.py 的程式行為不變」，以此為證。
   - 這處變動會使 `code_digest` 與 `app/` 的 tree id 改變。
     - 退役 PR 在登記紀錄 commit 之後、接線 PR 之前合併，也就是在第一筆 `forecast_run` 之前，所以 D-5 第 6 點沒有可重算的既有紀錄。
     - 登記表不存 `code_digest` 與 tree id，已登記的值與雜湊不受影響。
     - 補充七附記三的 R-1 只在登記時生效，它的測試隨同一個 PR 刪除。
   - 新的 `code_digest` 與 tree id 記在 PR 說明。接線 PR 依補充九第 1 點 merge 退役之後，重算接線版的 `code_digest`。
2. **S-19a 第 1 點的 grep 條件不變**
   - 除守門測試本身以外，不另設例外。

- **S-22（逐條可檢查）**
  - 退役 PR 相對 merge-base，`app/` 的差異只有 `app/forecast/claims.py` 一個檔。該檔的新增行只有一行，內容等於原來那一行刪去行尾 ` The pattern and`；刪除行只有兩行，就是原來那一行和下一行。
  - `claims.py` 的 `ast.dump` 與 merge-base 相同（附輸出）。
  - 守門測試對 merge-base 零差異，而且通過。
  - `tests/test_forecast_claims_bootstrap.py` 零差異，而且通過。
  - PR 說明附上新舊 `code_digest` 與 tree id。
  - 本補充 append 進本 ADR 的 commit，早於退役 PR 的合併 commit。
<<<正文結束>>>
