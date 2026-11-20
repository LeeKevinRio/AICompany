# 補充十一：D-4 檢查放在測試層的裁示

- 審查者：tech-architect
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**採 (d)，是 (c) 的變體：一鍵檔在執行期不重做 D-4 檢查，也不設替代的絆線。** D-4 的保證放在測試層，由兩件事一起構成：
- 腳本的輸出與 `report status` 逐字相同；
- 這份輸出已由既有的 `d4_violations` 檢查。

補充十一要換兩行，見下方對照。

## 裁示與理由

我讀了 `tests/test_forecast_report.py` 第 78～104 與 232～269 行，結論是 (a) 會失真，(b) 代價不成比例。

- **(a) 不採用：複製到腳本會失真。**
  - `unpassed_hashes` 要讀帳內每一筆紀錄的 `content_hash` 與 `valid_until_session_estimate`。腳本若要自己算這個參數，讀取範圍就會超出 `status`；而 `status` 的輸出本來就不印紀錄的雜湊與標籤，這條規則在執行期等於空轉。
  - 免除清單 `APPROVED_N_HAT_LINES` 來自 `tests.approved_copy`，也就是從風控報告抽出的字面。腳本不能讀 `work/`，只能把核可字面再抄一份到腳本裡，等於多一個會漂移的真相來源。
  - `BANNED_WORDS`、`FIXED_TEXTS` 同理，都得一起複製。
- **(b) 不採用。** 把測試用的檢查器搬進 `app/`，會讓正式程式帶著測試邏輯，`code_digest` 也會變，與補充十一「`app/` 零差異」衝突。為了一支顯示用的工具，不值得付這個代價。
- **(c) 的「簡單絆線」也不設。** 比對 ASCII 範圍或 traceback 樣式，抓不到 D-4 真正關心的東西，例如標籤、聚合用語、n̂。traceback 本來就由固定的 ERROR 句攔下。

**保證的來源**：
- 測試確認腳本不增刪、不改寫 `report` 的任何一行，輸出與 `python -m app.forecast.report status` 逐字相同；
- `report status` 的 D-4 合規，由既有的 `tests/test_forecast_report.py` 把關；
- 另加一支測試，對腳本輸出直接跑 `d4_violations`。測試環境可以合法取得帳內資料與核可字面。

## 補充十一的逐字對照

這兩句在我上一份補充十一全文中各只出現一次。

**第 2 點「輸出」第一款**
- 原：`     - 不另設白名單。每一行再套一次既有的 `d4_violations`；任一行不為空，就整批不印，只印固定 ERROR 句。`
- 新：`     - 不另設白名單，也不在執行期重做 D-4 檢查：輸出由 `report status` 原樣產生，D-4 合規由既有測試（`tests/test_forecast_report.py` 的 `d4_violations`）把關。腳本對 `report` 的輸出不增刪、不改寫任何一行，不 import `tests`，也不讀 `work/` 下的任何檔案。`

**S-21a 第四項**
- 原：`  - 注入任一行 `d4_violations` 不為空時，整批不印，只印固定 ERROR 句（測試）。`
- 新：`  - AST 確認腳本不 import `tests`、不讀 `work/` 下的任何檔案；以含最近一次執行、F-2 兩句與兩行缺日加註的合成 ledger 執行腳本，輸出經 `tests/test_forecast_report.py` 的 `d4_violations` 檢查為空（測試）。`

**S-21a 不變的項目**：「與 `python -m app.forecast.report status --db` 逐字相同」這一項維持原樣，它就是前面說的第一件事。

## 驗證

- 讀了 `tests/test_forecast_report.py` 第 27～104 行（import 與常數）及第 221～269 行（`_unpassed_hashes`、`d4_violations`）。
- 確認 `APPROVED_N_HAT_LINES` 取自 `tests.approved_copy.review_gap_line()`；`approved_copy` 的內容沒有讀。
- 唯讀：沒有改任何檔，沒有讀 `.env`，也沒有碰任何 `.db`。

## 下一步

- **coordinator**：把這兩行換進補充十一，再整份送風控。
- **devops-sre**：一鍵檔依新字面建置；不複製 `d4_violations`，也不設絆線。
