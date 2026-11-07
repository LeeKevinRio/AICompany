# 偵測回溯工具修正複審

- 審查者：qa-reviewer
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**PASS（單家審查，Codex 待環境可用時補跑）。BLOCKING_ISSUES=false。**
- 審查範圍：`git diff cd7fd91 51bb945`，2 個檔（腳本、測試），逐段讀完。
- R-1、S-1～S-5、D-9 都到位。
- 唯讀不變式沒有被破壞。
- 交件「與 D-9 的出入」第 1～3 點，我都判可以接受，但各有一項建議，見下。
- 有 4 項 suggested（皆 low），無 required。
- Codex：依指示記為「單家審查，Codex 待環境可用時補跑」。我沒有執行 `codex --version`，也沒有重跑 pytest、ruff、mypy。9660 passed、覆蓋率 97.59% 是 data-engineer 的自述，我未獨立驗證。

## 各部門回報（qa-reviewer）

### 逐項核對
| 項目 | 結果 | 依據 |
|---|---|---|
| R-1 | 到位 | 抽成 `_assert_s2_constants_align`，兩邊 `" ".join(split())` 後比對，並對 `S2_UNAUDITED_SQL` 與 `S2_UNAUDITED_NO_TABLE_SQL` 都斷言。我目視確認：規格 4.2 的單行字串，正規化後是探針 SQL 的子字串（腳本 `:118-119`、`:129-130`）。假常數測試同時驗證「對得上會過、改掉 `S2_ELIGIBLE_BATCH_SQL` 會失敗」。腳本 `:93` 的合格批次常數與假常數一致。真實對齊測試仍 skip，N-177a 合併後自動啟用。 |
| S-1 | 到位 | `ENUM_VALUES` 白名單加 `（非預期值）` 和計數，寫進 `meta.unexpected_enum_values`，報告標頭多一行。白名單比對 app 實際值：engine 與 service 的 rule_id（R1、R2、R3、S1、S2、P1～P3、M1、EMERGENCY、REBALANCE）都在內，沒有漏。方向偏保守：漏列只會多標，不會少標。測試：英文句子、`ZZ9` 都不進報告；乾淨帳冊計數為 0。 |
| S-2 | 到位 | `INDEX_BARS_SQL` 加 `source <> ?` 並傳入 `DEMO_SOURCE`。測試：demo bar 不進日曆，也不影響 `trading_day_difference`。 |
| S-3 | 到位 | docstring 與 L8 都補了 `-shm`、`-wal` 與「DB 雜湊只涵蓋主檔」。測試鎖住字串。 |
| S-4 | 到位 | `costed` 改成 `(cost or 0) > 0`，與 S1 迴圈一致。 |
| S-5 | 到位 | `build_result`、渲染放進 try，錯誤回 exit 2，不寫檔。讀 DB 階段加 `ValueError`、`TypeError`。渲染在寫檔前完成，所以失敗時 out-dir 是空的（測試有斷言）。 |
| D-9 | 到位 | 新增 `D-9` 理由，進入 `guards`，列為「需人工判讀」、不給試算。範圍：G-a 列的 `rule_id`／`action`、在途賣單的 `rule_id`、該檔 S2 列的 `status`。測試涵蓋 g_a、在途、S2 status 三路與「已知值不觸發」。 |

### 交件「與 D-9 的出入」判斷
1. **只判定「用到」的列：可接受。**
   - G-a 的 SQL 是規格逐字版，只撈 buy 或 sell，所以 `action` 非預期值的列不會進判定。
   - 風控 D-9 的字面是「判定或試算用到的列」，與此一致。
   - 保留一項 suggested（見 S-6）。
2. **計數只算有輸出的欄位：可接受。**
   - 規格 S8 的原文是「輸出（非預期值）並計數」，計數對象就是有輸出的值。
   - D-9 的列已用 id 呈現，資訊沒有消失。
   - 標頭文字寫的是「枚舉欄位的非預期值個數」，容易被讀成全部列的總數（見 S-7）。
3. **`source` 白名單為空集合：可接受。**
   - 目前沒有任何類別輸出 `source`，我 grep 確認過。
   - 空白名單偏保守：以後若有輸出，全部會先標非預期，不會洩漏供應商字串。

### suggested（皆 low，不阻擋）
- **S-6【可維護性，low】** `_classify_affected` 內對 G-a 列檢查 `action` 不在白名單，是死程式碼。SQL 只撈 buy 與 sell，永遠不會命中。
  - 建議在註解寫明，並在 PR 說明記一句：「同檔若有 `action` 不明、但實際已成交的列，G-a 不會撈到，也就不會觸發 D-9」。
  - 此限制來自規格的 G-a 逐字 SQL，需要改要 TA 裁示。
- **S-7【可維護性，low】** 報告標頭「非預期值個數」建議改成「報告輸出欄位中的非預期值個數（D-9 用到的列另見理由句）」，避免 CEO 把 0 讀成「完全沒有非預期值」。
- **S-8【可維護性，low】** 測試寫法有雜訊：
  - `test_d9_a_row_with_an_unexpected_enum_value_withholds_the_trial` 的 `assert ... or ...` 是弱斷言，`cases` 字典只有一筆。
  - `test_d9_in_flight_row_and_s2_status_with_unknown_values` 有 `... if False else _report_in(...)` 的死分支。
  - 建議改成嚴格斷言並刪掉死分支。
- **S-9【安全，low】** 讀 DB 階段的 `ValueError`、`TypeError` 訊息會被 `_ascii` 轉成 ASCII 後印到 stderr，可能帶出某個儲存格的值，例如 `int('...')` 的錯誤。
  - 這只印在 CEO 本機終端，不進報告檔，與報告外洩無關。
  - 建議只印例外類別名稱，與 build 階段一致。

## 重點檢查結果
1. **逐項到位**：見上表。
2. **唯讀不變式**：
   - 連線：`mode=ro`（腳本 `:389`）加 `PRAGMA query_only=ON`（`:391`），這次 diff 沒有動這一段。
   - 只用 stdlib：import 清單未增加。
   - 前後 SHA-256 比對（`:1885`、`:1888`）與 exit 3 未動。
   - exit codes 2、3、4：新增的錯誤分支只用 exit 2，沒有新增寫入路徑。
   - 輸出目錄在 repo 外：檢查未動。
   - 寫檔仍用 `open(..., "x")`，且是在渲染完成後才開檔。
3. **報告洩漏**：
   - 枚舉欄位改成「只輸出已知值」，比之前更嚴；其餘字串仍走 token 正規式。
   - 新增的 D-9 理由句只含 id 與固定措辭。
   - `meta.unexpected_enum_values` 只是整數。
   - 報告不含持股與現金以外的祕密。
4. **測試在舊碼上失敗**（以讀碼推論，未實跑）：
   - S-1 的測試引用 `probe.ENUM_UNEXPECTED`、`counter`，舊碼沒有，會失敗。
   - S-2：舊碼的 demo bar 會進日曆，天數差會不同。
   - S-4：舊碼的 `cost != 0` 讓 -50 與 50 加權成 0，會除以零。
   - S-5：舊碼是 KeyError traceback，或 sqlite 以外的錯誤沒有被攔，exit code 不是 2。
   - D-9：舊碼沒有 `D-9` 守衛。
   - R-1：R-1 屬測試端修正。新增的「假常數」測試驗證新寫法，不是在舊腳本上失敗；舊的原始子字串寫法在 N-177a 合併後才會失敗。這可以接受。
   - S-3：docstring 與 L8 的字串斷言，舊碼不含 `-shm`，會失敗。

## 驗證
- 讀過：`git diff cd7fd91 51bb945` 全文、腳本 `:90-160`（SQL 常數）與 `:720-795`（`_classify_affected`）、我上一輪審查檔、風控 D-9 原文（`work/reviews/2026-11-07-N177修訂一再審與N177b定稿-風控.md` 第 164、210 行）、交件檔、規格第 1528 行的 D-9 附註。
- 用 Grep 查：app 內實際的 rule_id 值、枚舉欄位在腳本中的輸出位置、import 清單。
- 未做：沒有重跑任何測試。上面「在舊碼上失敗」是推論。

## 唯讀權限判準常數
未觸及。
- 第一道檢查：diff 只涉及 `apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py` 與 `apps/stock-desk/backend/tests/test_n177_n190_backtrack_probe.py`，沒有 `scripts/validate_agents.py`。
- 第二道檢查：Bash 不得接 pipe，所以改用 Grep 在整個 backend 目錄搜尋 `READONLY_AGENTS` 與 `READONLY_ALLOWED_BASH`，0 筆。
- 三問：改了什麼，沒有；為何改，不適用；有無對應 ADR，不適用。沒有 shadow 定義，也沒有常數值被改動。

## 越界自我檢查
- Bash 只用過一次 `git diff cd7fd91 51bb945`（在 worktree 以 `-C` 指定，單一指令，不接 pipe，不 `cd`，不 `&&`）。沒有執行 `codex`。
- 其餘全用 Read、Grep、Glob。
- 沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔，沒有 staging 或 commit。
- 沒有寫報告檔，內容只在這份回報。

## 下一步
1. 本工具屬純邏輯、不涉及 UI，不需要 qa-e2e，可回報 CEO。
2. 交件的第 1、3 點請 TA 確認；S-6 的限制是否要改 G-a 規格，也請 TA 裁示。
3. S-7、S-8、S-9 交 data-engineer 順手處理，不擋 CEO 本機執行與合併。
4. 把交件的 D-9 三點寫進 PR 說明（風控要求的流程）。
5. N-177a 合併後確認 S11 的 skip 測試轉為通過。
6. Codex 環境可用時補跑 `/review`。

檔案：
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_probe/apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_probe/apps/stock-desk/backend/tests/test_n177_n190_backtrack_probe.py`

## Verdict
PASS
BLOCKING_ISSUES=false
