# N-172a 重審（PASS）

- 審查者：qa-reviewer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**PASS。BLOCKING_ISSUES=false。** 單家審查，Codex 待環境可用時補跑（`codex --version` 上次回 `command not found`，這次未重試，環境沒有變動的訊息）。

增量範圍是 `390565b..02bab9c`，兩個 commit：`bd57d7a`（feat）、`02bab9c`（test）。

- **上次 B-1：** 已補齊。T21 擴充、G1 SQL trace、T22 往返、T22 錨點缺席都有，而且斷言夠強。
- **TA 對 NB-1 的裁定：** 測試斷言 ENTRY_NOTE 在第一則。
- **風控必改 1～8：** 全部落實。
- **範圍：** 增量沒有動 `engine.py`、`store.py`、`settle()`、`scripts/`、`.claude/`，沒有碰 `READONLY_AGENTS`／`READONLY_ALLOWED_BASH`，祕密、`CREATE UNIQUE`、`DELETE FROM` 掃描無命中。
- **沒有跑測試。** CI 數字（pytest 9107 passed、ruff、mypy strict 全綠）是 dev-lead 自報，我沒有獨立重現。

## 二、各部門回報

### 風控必改 1～8 逐條核對（分支內容，見 `service.py` 與 `wording.py` 的增量 diff）

| 必改 | 結果 | 依據 |
|---|---|---|
| 1 A 句改字 | 滿足 | `wording.py`：「筆買賣指令」「稍早這檔資料可用時」兩處。用 `git diff -G` 抽查，命中 `wording.py` 和守門測試。逐字守門測試同步更新，並斷言舊字面不得回來。 |
| 2 A 句條件 | 滿足 | `orders = sum(1 for line in lines if line.action in ORDER_ACTIONS)`，`ORDER_ACTIONS` 是從 `store` 匯入的常數，沒有另寫一份清單，沒有讀 `rule_summary`。`orders==0` 時不渲染。 |
| 3 B 句 | 滿足 | `SAME_DAY_EARLIER_DECISIONS_DATA_GAP_NOTE` 只在 `wording.py`；store 沒有 import wording，這條由既有的 AST 守門測試涵蓋，片段清單已加入 B 句。順序是 DATA_GAP → A → B：`anchor` 在 A 渲染後改成 A 的字串，B 接在 A 之後。字面以 `-G` 抽查（結尾「這些紀錄未因此取消或修改。這幾筆不是買賣指令，帳冊不會依開盤價判定成交。」）命中。 |
| 4 Action 分類涵蓋測試 | 滿足 | `test_every_action_is_classified_once`：`set(_ACTION_CLASS) == set(get_args(Action))`，並斷言 A 類等於 `ORDER_ACTIONS`、B 類等於 `DECISION_RECORD_ACTIONS`、兩者互斥。我查了 `Action` 是 `buy/sell/defer/skip/none`；`none` 只在 `service.py` 的 REBALANCE 出現，歸「不進清單」，與註解一致。日後新增 action，這支會失敗。 |
| 5 (a)～(e) 測試 | 滿足 | `test_c_a_*`（只有 R2 順延，只出 B）、`test_c_b_*`（只有 R3 跳過，只出 B）、`test_c_c_*`（第一次指數缺漏產生 M1 順延，第二次該檔缺漏，只出 B）、`test_c_d_*`（P1 加 R2，A=1、B=1，順序 A 再 B，緊接 DATA_GAP 句）、`test_c_e_*`（只有 S1 賣出，只出 A）。FLIP 檔原有的 S1 測試保留。 |
| 6 (a) | 滿足 | `test_b_a_an_r3_skip_writing_day_and_its_refresh`：走 HTTP，兩檔都 `defer_count=2`，指數缺漏。斷言無 DEFER_NOTE、有 INDEX_DATA_GAP_NOTE、directives 都是 R3 skip，且第二次 `/today` 的 warnings 與第一次相同。 |
| 6 (b) | 滿足 | `test_b_b_*[r2-defer]、[r2-r3-skip]`：第一次 R2 順延或 R2 造成 R3 跳過，第二次指數缺漏，不出 DEFER_NOTE。 |
| 6 (c) | 滿足 | `test_b_c_*`：A 檔 M1 順延加 B 檔 R3 跳過，DEFER_NOTE 出現。 |
| (b) 條件只看 M1 加 defer | 滿足 | 本次 diff 沒動這個條件；程式仍是 `line.rule_id == "M1" and line.action == "defer"`，對 `logged` 判斷。 |
| 7 錨點退路 | 滿足 | `test_entry_note_comes_first_when_frozen_note_is_missing`（ENTRY 在第一則）、HOLDING 錨點缺席（A、B 在末尾）、DATA_GAP_NOTE 錨點缺席（A 在末尾）、只有 B 且錨點缺席（B 在末尾，且沒有 A）。每個錨點都有一支，而且斷言位置，不只斷言存在。 |
| 8 (a) 只用整句相等 | 滿足 | 程式用 `w not in stale`（set 整句成員）、`anchor in warnings`、`warnings.index(anchor)`，沒有 substring、startswith 或 regex。測試輔助函式裡有用 `startswith`，那是測試端挑句子，不是被審查的程式。 |
| 8 (b) 往返 | 滿足 | 見下方對 T22 的判斷。 |
| 8 (c) 用 engine 本次選的批次 | 滿足，程式與測試都對 | 程式：`stale` 的 SHRINK_TO_ZERO 是對「被擋下 symbol 的所有批次」逐批渲染，不依落檔列的批次，所以第 2 批的句子也在集合內。測試：`test_round_trip_shrink_to_zero_of_the_batch_the_engine_chose_now`（純 engine，批次 1 skipped，engine 產生「第 2 批」句，落檔列是批次 1 的 R3 skip，仍被移除）加上端到端版 `test_shrink_to_zero_of_the_chosen_batch_is_removed_end_to_end`。 |

### 上次 B-1 逐項

- **T21 擴充：** `test_a_missing_batch_row_is_not_refused` 參數化為 `batch_no=9`（無此批次列）與 `None`。測試先把同 symbol 的三個批次全設為 open，這樣寬鬆的條件會誤擋，才有鑑別力。斷言 (i) 被結算、log 為已結算並已 claim、`batch_blocking_claim` 為 None；(ii) `list_batches()` 與現金不變；(iii) `unsettled == []` 且 warnings 沒有「不是待買進狀態」。
- **SQL trace：** `test_the_g1_refusal_is_part_of_the_claim_update` 斷言整個 claim 過程只有一條碰 `playbook_directives`／`playbook_batches` 的語句，是 UPDATE，含 `settled = 0`、`NOT EXISTS`、`b.status <> 'planned'`，沒有先 SELECT。我認為這比我要求的更嚴格。
- **S-1 第 4 點：** `test_only_the_update_decides_whether_the_book_moves`：結算中 claim 的 UPDATE 先於挑理由的 SELECT，而且全程唯一的寫入就是那條 UPDATE（沒有現金、批次、schedule 寫入）。
- **C-12 (b)：** `test_the_reconciliation_reads_the_snapshot_handed_to_the_engine` 用 `is` 證明 `batches`、`portfolio`、`markets`、`params` 是同一份物件，commit 之後沒有重讀。

### 對 T22 黑箱往返是否足夠的判斷：足夠，不需要抽出公開函式

理由：
- 移除與定位在程式裡都是整句相等比對。
- 縮量句往返測試的結構是：先呼叫真的 `evaluate()`，斷言 engine 當次確實輸出那一句；再呼叫 `same_day_warnings`，斷言結果 `==` 「engine 的 warnings 少了那一句」。
- 如果 service 重新渲染出的字串與 engine 的不逐字相等，那句就不會被移除，等式就不成立。所以「重算字串 == engine 輸出」是這個等式的必要條件，黑箱證明和直接比對字串在邏輯上等價。
- 錨點也一樣：`test_round_trip_data_gap_anchors` 要求 A、B 緊接在各自的 DATA_GAP 句之後，且下一個 symbol 的 DATA_GAP 句還在其後。若 service 找不到錨點，只會附加在末尾，位置會不對，等式失敗。FROZEN 錨點同理（`reconciled[:2] == [frozen, entry]`，而後備位置會把 ENTRY 放在 FROZEN 之前）。
- 抽出公開函式等於改 code，只為了測試，沒有必要。
- 變異檢查（dev-lead 自報注入 6 種錯誤，每種都有測試失敗）我沒有重做，但從測試結構看是可信的。

### 範圍與章程

- **範圍：** `git diff --name-only` 查增量，`engine.py`、`store.py`、`scripts/`、`.claude/` 都沒有異動。`settle()` 無異動。
- **唯讀權限常數：** 見下方判準節，未觸及。
- **註解與 docstring：** 英文，符合章程。
- **trailer：** 我的 Bash 只能用 `git diff`，看不到 commit 訊息；請 coordinator 合併前確認 `bd57d7a`、`02bab9c` 的訊息格式（Conventional Commits、繁中、trailer）。

## 三、驗證

### 唯讀權限判準常數

未觸及。
- 增量 `--name-only` 路徑查詢（`scripts`、`.claude`）無輸出。
- `git diff 390565b 02bab9c -G'READONLY_AGENTS|READONLY_ALLOWED_BASH'` 無命中。
- 因此沒有 agent 名單、常數值或 shadow 定義的異動。

### Bash 使用紀錄

這次只用了 `git diff`（不接 pipe、不 `cd`）。沒有新的越界。上次審查中的三次越界（`cd`、`git log`／`git status | head`、`wc -l`）已在上次報告記錄，這次沒有再犯。

### 非阻擋項（NB）

行號為分支 diff 的約略位置，分支未簽出。

- **NB-1 縮量句往返測試只涵蓋第 1 批。**
  - 位置：`tests/test_playbook_same_day_anchors.py::test_round_trip_shrink_note`。
  - 現況：只測批次 1 的情況（`planned=666`、`actual=350`）。`planned_batch_shares` 對「最後一批」有走另一條算式（`already` 累加），這條沒有往返測試。
  - 風險：低，因為 service 和 engine 呼叫的是同一個純函式，輸入也經 C-12(b) 測試守住是同一份；但最後一批的輸入若出現差異，會讓縮量句留在頁面上。
  - 建議：之後有機會時補一組批次 3 的縮量往返。
- **NB-2 `DECISION_RECORD_ACTIONS` 是 `service.py` 裡的區域常數**（約 :404），而 `ORDER_ACTIONS` 在 store。
  - 風控必改 2 只要求 A 句引用 `ORDER_ACTIONS`，這點滿足；B 的清單沒有現成常數，也有分類涵蓋測試守住。可接受，僅記錄。
- **NB-3 風控已知殘留不擋合併：**
  - S2 賣出列有 F8 問題，歸 N-177。
  - G1 擋下的列與 ENTRY_NOTE、A、B 的「仍會照常…判定」會失準，ADR-0036 落地時要一起回審。
- **NB-4 上次的 NB-2（DEFER_NOTE 在 R3 skip 日消失）已由風控 (b) 裁示 APPROVE；NB-3（`{line_count}`）已由風控 (c) 處理並在程式落實。** 這兩項都關閉。

## 四、下一步

1. **coordinator：**
   - 確認 `bd57d7a`、`02bab9c` 的 commit 訊息與 trailer。
   - 合併時處理 product 已前進的部分，不由 dev-lead merge。
   - Codex 環境可用時補跑 `/review`；補跑前本結論標註為單家審查。
2. **風控：** 確認最終字面。我已用 `-G` 抽查 A 句、B 句的片段，與你說的程式逐字比對一致。
3. **tech-writer：** 依風控與 TA 要求，在 ADR-0035 補記：Decision 4 第 3 點維持只看 M1 順延列、B 句、A 句計數口徑。
4. **qa-automation（非阻擋，建議）：** 在舊 code 上重跑 FLIP 檔，確認 21 失敗／12 通過；上次我數到 22／12，差 1 未能唯讀證實。
5. 本任務涉及面向使用者的字面，最終字面由風控簽核；PASS 後無 UI 變更（前端型別沒動），不需要 qa-e2e，純後端與文案，回報 CEO。

相關檔案（絕對路徑）：
- /home/user/AICompany/work/reviews/2026-11-01-N172a修正交件-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-01-N172a解讀點bcd裁示-風控.md
- /home/user/AICompany/work/reviews/2026-11-01-ADR0035補充一-tech-architect.md
- 被審查檔案（分支 `origin/fix/stock-desk-same-day-idempotency`，工作樹未簽出）：`apps/stock-desk/backend/app/playbook/service.py`、`apps/stock-desk/backend/app/playbook/wording.py`、`apps/stock-desk/backend/tests/test_playbook_same_day_anchors.py`、`apps/stock-desk/backend/tests/test_playbook_settlement_g1.py`、`apps/stock-desk/backend/tests/test_playbook_wording.py`、`apps/stock-desk/backend/tests/test_playbook_same_day_flip.py`、`apps/stock-desk/backend/tests/same_day_helpers.py`

## Verdict
PASS
BLOCKING_ISSUES=false
