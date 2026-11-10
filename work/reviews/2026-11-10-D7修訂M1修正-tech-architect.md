# D7 修訂 M-1 修正（_read_roster_max_date）

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：M-1 修正（單一性檢查第 5 項與第 3 點 (a) 互相矛盾）

## 一、本次結論

M-1 採**修法 (1)**：新增專用 helper `_read_roster_max_date`，把它列入第 5 項允許呼叫 `parse_high_volatility_changed_on` 的地方。替換條文共三處，都可以直接貼上：第 2 點單一性檢查第 1 項、第 5 項，以及第 3 點 (a)。其他內容都沒有動。

不採修法 (2)，理由有兩點：
- `_read_high_volatility` 也是 `symbol_states` 的讀取路徑。把 R 併進去，評估與名單頁每次讀取都會多一句 roster 查詢，但這兩條路徑都用不到 R。
- R 不是單一標的的資料，和「每檔一份 `HighVolRead`」的回傳型別對不上。

## 二、各部門回報

### tech-architect（本人，唯讀）

**替換 1：D7 第 2 點「單一性檢查」第 1 項**

- 舊句：
  > 1. app/ 內名為 `parse_high_volatility_flag`、`parse_high_volatility_changed_on`、`_read_high_volatility` 的函式定義各恰 1 個，都在 `app/playbook/store.py`。
- 新句：
  > 1. app/ 內名為 `parse_high_volatility_flag`、`parse_high_volatility_changed_on`、`_read_high_volatility`、`_read_roster_max_date` 的函式定義各恰 1 個，都在 `app/playbook/store.py`。

**替換 2：D7 第 2 點「單一性檢查」第 5 項**

- 舊句：
  > 5. **呼叫點封閉**：兩個解析函式的呼叫，以及 `HighVolChange(...)` 的建構，只出現在 `_read_high_volatility` 本體內。該本體的 `Compare` 節點只能是 `… is None` 或 `… is not None`。
- 新句：
  > 5. **呼叫點封閉**：
  >    - `parse_high_volatility_flag` 的呼叫與 `HighVolChange(...)` 的建構，只出現在 `_read_high_volatility` 本體內。
  >    - `parse_high_volatility_changed_on` 的呼叫只出現在 `_read_high_volatility` 與 `_read_roster_max_date` 兩個本體內。
  >    - `_read_roster_max_date(conn) -> date | None` 本體恰好執行一句 SQL，就是第 3 點 (a) 的 `SELECT MAX(taipei_date) FROM playbook_roster_log WHERE date(taipei_date) IS taipei_date`，結果只交給 `parse_high_volatility_changed_on`。它的呼叫者只能是第 3 點的寫入函式（預覽與確認）。
  >    - 兩個 helper 本體內的 `Compare` 節點，只能是 `… is None` 或 `… is not None`。

**替換 3：D7 第 3 點 (a)**

- 舊句：
  > - (a) **鎖內讀取**：經 `_read_high_volatility` 讀該檔的 `HighVolRead`；另以 `SELECT MAX(taipei_date) FROM playbook_roster_log WHERE date(taipei_date) IS taipei_date` 讀 R，結果再經 `parse_high_volatility_changed_on` 解析。沒有列或解析為 None 時，R 不存在。
- 新句：
  > - (a) **鎖內讀取**：經 `_read_high_volatility` 讀該檔的 `HighVolRead`；另經 `_read_roster_max_date(conn)` 讀 R（SQL 與解析依第 2 點單一性檢查第 5 項）。回傳 None 時，R 不存在。

### 其他部門
本次沒有參與。

## 三、驗證

- **一致性**：
  - `_read_roster_max_date` 執行的 SQL 只含 `playbook_roster_log`，不含子字串 `high_volatility`，所以不碰第 6 項的字串封閉。
  - 第 3 項只計 `type(N) is int and N == 1` 的 BoolOp，這個 helper 不會出現這個樣式。
  - 附錄 W9、W10、W12、P1 的期望值都不變。C-D7-4 照舊適用：SQL 仍然帶 WHERE，只是改放在新 helper 內。
- **核對紀錄**：`work/reviews/2026-11-10-D7與ADR0044併入核對-qa-reviewer.md` 我這次沒有讀，M-1 的內容依 coordinator 的轉述處理。
- 沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改任何檔案。

## 四、下一步

1. **tech-writer**：落檔前，把上述三處舊句換成新句，其餘照原定稿併入 ADR-0043。
2. **qa-reviewer**：確認 M-1 已關閉。只需核對這三處替換，以及單一性檢查第 1、5 項和第 3 點 (a) 不再互相矛盾。
3. **dev-lead**：v3 依新的第 5 項實作 `_read_roster_max_date`，並把它納入 P3 的 AST 測試；負例要加一條：在這兩個 helper 之外呼叫 `parse_high_volatility_changed_on`，必須判為違規。

相關檔案：
- /home/user/AICompany/work/reviews/2026-11-10-D7與ADR0044併入核對-qa-reviewer.md
- /home/user/AICompany/docs/adr/0043-stock-desk-排程台標的名單的表達-批次輪次與輪內股數-名單寫入交易-新標的戳記閘與季度窗口.md（D7 :314-331）
