# N-171 群組 A 整包審查（5e7c31c，PASS）

- 審查者：qa-reviewer
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-171 群組 A 整包（後端＋前端）我判 PASS，沒有 critical 或 high 問題，BLOCKING_ISSUES=false。

- **單家審查**：Codex 不可用（`codex --version` 回 exit 127，command not found），Codex 待環境可用時補跑。
- **三個變異測試**：我沒有親自重做，原因是我的 Bash 只准 `git diff` 與 `codex --version`，不能改檔或跑測試。
  - 我改為讀守門測試原始碼，逐一推演三個變異會不會讓測試轉紅，三個都會，推演見下。
  - 同時核對 dev-lead 的紀錄（M1、M2 已確認有記載；M3 的紀錄我沒讀到）。
  - 這是「推演加紀錄」，不是實跑，請 coordinator 知悉。
- **其他做不到的事**：我沒有重跑 CI，也沒有重跑 E-13(e) 的逐 commit SEAM 測試。
  - CI 結果沿用 coordinator 的 `5e7c31c` 全綠。
  - E-13(e) 只核對了紀錄與 diff。
- **後續關卡**：涉及 UI，仍須 qa-e2e 實機驗收（qa-automation 已同步代跑），以及風控依 S-A～S-D 做最終字面終核。
- **越界紀錄**：Bash 只用了 `git diff` 與 `codex --version`，無越界。沒有讀 `.env`、沒有碰 `data/*.db`。

## 各部門回報（逐項核對）

### ADR-0039 附錄 A 與補充一
- **C1～C24**：逐項核對。
  - C2″：`classify_exit_batches` 是唯一把 `exit_line_still_covers` 用在批次上的地方。有 AST 測試鎖定，呼叫者只能是它和 `_with_stale_exit_notes`。
  - C7：區塊掛在 `today.isSuccess` fragment 的第一個子節點。
  - C9／C14：`_read_pending_exits` 只透過 `_read_exit_state` 做 SELECT。區塊為空時回傳 `None`，頁面零渲染。
  - C10：未簽署路徑 `loaded=None`，不分類，每批一列 unclassified，加 A-13 與 A-14。
  - C15／C22：W-B2L 只從 `_lines` 複製；前端不讀 `pending_exit_directives`。
  - C17′：`settle_on_request` 第一步就讀 authorship，未簽署時回傳只含 `SETTLEMENT_UNAUTHORED_NOTE` 的空結算。`/today` 不會呼叫它。
  - C19：`{read_at}` 由前端只替換一次，值為同一回應的 `formatDateTime(as_of)`。
  - C21～C23：A-6／A-15 各為單一純函式，有 T17 (a)～(d) 與 T25 測試。
  - 群組 B 的 C12、C16、C20、C24 未實作，符合範圍。
- **S-8**：C17′、C21～C23 皆有測試。

### 補充四
- **QB-6／QB-7**
  - `app/` 內 `pending_directives(` 仍只有兩處，在 `_settle_pending` 與 `_with_stale_exit_notes`，與釐清三白名單一致。這兩處在 diff 中沒有被動到，是我對照工作樹行號 747、915 確認的。
  - `settle_on_request` 不直接呼叫它，`app/api/` 也不呼叫 `settle_pending`，都有 AST 測試。
- **QB-12**
  - `git diff 5c2d3e1 5e7c31c` 對 `pre_seam_responses.json` 為空，golden 零 diff。
  - `GOLDEN_SHA256` 已釘選，並由 T2 比對。
  - `n171a.json` 的 `deltas` 為空，`added_keys` 只登記最外層的 `pending_exit_block`。
  - 兩筆 `filled` 都指向存在的精確值測試。
  - 機制另有負向測試：before 不符、空差異、撞名、message 非附加、兩個 owner 共用同一 list。
- **QB-13／E-11**
  - `_read_exit_state` 本體在 diff 中未動。
  - `_read_pending_exits` 不讀買單。
  - `classify_exit_batches` 不碰買單。
  - 列的 `entry_before_exit_note` 只從 `_lines` 產生的 `DirectiveLine` 複製，不讀 `labeled_batches`。
- **QB-14**
  - E-13 (a)：`git diff 0f02cf3^ 909899b` 對 `test_playbook_today_seam.py`、`seam_helpers.py`、`golden/` 為空。
  - E-13 (b)：`git diff --stat 909899b 01e99cb` 只列 `approved/.gitkeep`、`seam_helpers.py`、`test_playbook_today_seam.py` 三個路徑，`app/` 與 golden 零 diff。
  - E-13 (c)：`n171a.json` 首次出現在 `460413d`；`01e99cb` 沒有。
  - E-13 (d)：`909899b` 只新增 `test_playbook_settle_on_request.py`，既有 `POST /settle` 測試零改動。
  - E-13 (e)：只核對紀錄與 diff，未重跑。
  - E-14 (a)：`508a976` 含 `wording.py` 常數、`playbookView.ts` 的 `body[1]`、後端守門測試（`test_playbook_wording.py`）、`exitWordingMirror.test.ts`、字面絆線測試。
  - E-14 (b)：`0f02cf3^..460413d` 對 `EXIT_RESULT_UNCONFIRMED_BADGE`、`playbookView.ts`、兩個守門測試檔都沒有改動，只加區塊常數。
  - E-14 (c)(d)：區塊元件在同一分支；PR 須用 merge commit，不得 squash。這是合併流程要求，請 coordinator 照辦。
  - E-15：`models.py` 與 `types.ts` 的 `pending_exit_directives` 擁有者行只改註解，措辭與建議文字一致。
    - `InFlightRead`／`read_in_flight` 在 `5c2d3e1..5e7c31c` 的 diff 中沒有任何變動。
    - `PendingExitRead` 新增必填欄位 `state`，這是 ADR-0039 Decision 2 授權的 owner 填入，由 `filled.in_flight` 登記，T4 對未登記部分仍斷言預設值。
  - E-16：`origin/product` 到 `5e7c31c` 的淨差異中，沒有任何 N-182 內容被刪除或改動（`refused_by_g1`、`BATCH_LEFT_PLANNED_SQL`、`blocked` 都在 product 側，未出現在淨差異）。

### 風控條款
- **11-03 給 dev-lead 第 1～7 點、給 frontend-engineer 第 1～5 點**：後端字面有 `SIGNED_OFF` 逐字比對、佔位符檢查、禁用詞掃描（建議只准出現在 A-2 的歸屬否定句）；前端用 sentinel 字串，證明前端不自寫任何字。
- **A 閘門四項**：A-2 修訂版已替換，舊版列入 `RETIRED_A2` 比對。`SETTLEMENT_UNAUTHORED_NOTE`、A-15、NB-6 第二版皆有逐字測試。
- **測試 (k)(l)(m)**：測試涵蓋 C17′、C21、T25。
- **補充一確認 (d)**：A-13 與 A-14 的順序固定為 A-13 後接 A-14。
- **解讀點 3 (a)**：守門比對的是「接起來之後的值」。
  - 後端：用 AST，相鄰字串在 AST 已合併。
  - 前端：先把 `"…" + "…"` 接起來，再做 regex 抽取。
  - 前端測試檢查 `wording.py` 時，也先合併相鄰字串。
- **解讀點 3 (b)**：三個 11-03 專有子句為「會列出」＋「目前尚未結算」、「該區塊沒有出現」＋「，」、「指令結算後」＋「也不再列於該區塊」，與風控列的三處一致。
- **三個變異測試（推演結果）**
  - M1（`wording.py` 新增拆行、值等於第一版的常數）：AST 合併成第一版整句，`_NB6_P2_FIRST not in literals` 失敗。
  - M2（前端 `body[1]` 改回第一版並拆行）：先接起來後 `first_count` 大於 `second_count`，`first_count == second_count >= 2` 失敗。前端對應測試也失敗。
  - M3（把 11-03 專有子句拆行塞回任一常數）：`fragment in literal` 檢查會失敗。
- **解讀點 3 (d)**：`PendingExitBlock.test.ts` 最後一個 describe 渲染 `ExitFailurePanel`，斷言第 2 段是單一 `<p>`、textContent 完整等於第二版、無截斷或摺疊 class。
- **解讀點 5**：豁免詞為「本回應的」，在句中恰好 1 次，剔除後「應」為 0。A-2、A-15、NB-6 第二版不給任何豁免。
- **NB6_P1 用途**：我在 diff 範圍內沒有找到任何測試拿 `wording.json` 的 `NB6_P1` 當第 1 段基準，第 1 段由後端與前端各自逐字斷言。
- **R-1／R-2**：`li` 子元素依序為 `text`、`notes`、`entry_before_exit_note`，中間無元素；附註 class 固定為 `mt-1 break-words text-sm text-neutral-300`。
- **R-3 (a)～(c)**：只有 stale 小節是 `mt-6 border-t-2 border-neutral-500 pt-4` 實線，覆蓋與 stale 的 `ul`、`li`、文字、附註 class 完全相同，並禁 `opacity`、`line-through`。
- **R-6 (a)(b)**：根 `section` 有 `aria-labelledby` 指向 `h2`，區塊內沒有 `aria-live` 與 `role`。

### 前端視覺規範與 skill 自檢
- 能用 vitest 驗的 VP 條款已有測試，涵蓋位置、順序、禁用 class 與屬性、空資料不渲染、header id 唯一、元件不匯入收據 store。
- 計算樣式、幾何與 375 寬等項目測試誠實標為交 qa-automation，沒有造假。
- 這部分用 `ui-delivery-checklist`、`code-review-checklist` 的口徑自檢，沒有 blocking。

### NB-6 第 2 段原子替換
- 後端常數、前端鏡射與兩個守門測試在同一 commit（`508a976`）。
- 前後端第二版逐字一致，三句，點名區塊標題與 `PENDING_EXIT_BLOCK_TITLE` 相同。

## 各檔問題
- `apps/stock-desk/frontend/app/lib/__tests__/exitWordingMirror.test.ts`、`apps/stock-desk/backend/tests/test_playbook_wording.py`
  - [可維護性][low] 前端字面掃描的 regex 只抽雙引號字串。單引號、template literal、JSX 純文字裡的舊版第 2 段抓不到。
    - 風控 3(c) 建議的「掃描測試、`node_modules`、`.next` 以外全部原始碼」也只做到 `app/`。
    - 目前可出貨的原始碼只在 `app/`，也沒有舊版殘留，不阻擋。
    - 建議後續補掃單引號與 template literal，並在新增可出貨目錄時一起擴大範圍。
- `apps/stock-desk/backend/app/playbook/store.py`
  - [可維護性][low] `PendingExitRead` 新增必填欄位 `state`（無預設）。
    - 目前所有呼叫都經 `_read_pending_exits`，沒有問題。
    - 日後有人直接 `PendingExitRead()` 會得到 `TypeError`。T4 已避開此路徑。這是 ADR 授權，僅供知悉。
- 其餘檔案沒有發現 critical、high 或 medium 問題。

## 第二意見（Codex）
Codex 不可用，單家審查，待環境可用時補跑。

## 驗證
- 唯讀 `git diff` 逐檔檢視：
  - `origin/product/stock-desk..5e7c31c` 的 `apps/` 淨差異（20 檔）。
  - 各 commit 的 `--stat` 與路徑限定 diff：`0f02cf3^..909899b`、`909899b..01e99cb`、`460413d^..460413d`、`508a976^..508a976`、`909899b^..909899b`。
  - `5c2d3e1..5e7c31c` 的 golden、`store.py`、`models.py`。
- 唯讀 Read／Grep：交件說明、風控兩份裁示、補充四釐清一～四、守門測試原始碼。
- 沒有實跑任何測試；CI 結果沿用 coordinator。

## 唯讀權限判準常數
未觸及。
- `git diff origin/product/stock-desk 5e7c31c --name-only -- scripts .claude` 為空，沒有動 `scripts/validate_agents.py` 或 `.claude/`。
- `apps/` 下 Grep `READONLY_AGENTS|READONLY_ALLOWED_BASH` 為 0 筆；我讀過的所有 `apps/` diff 也沒有新增或刪除這兩個符號。
- 因此沒有 agent 名單異動、沒有常數值異動、沒有別處的 shadow 定義，也沒有對應 ADR 需求。

## 下一步
1. qa-e2e 實機驗收 S-A～S-D，另附最長 fixture 在 375×812 的整頁截圖與區塊總高（風控 R-4 回審觸發）。
2. 風控依 S-A～S-D 的畫面與 DOM 擷取做最終字面終核，包含 R-3 與 R-4 的實際效果。
3. PR 以 merge commit 合併，不 squash、不 cherry-pick（E-14 (d)）。在 qa-e2e 與風控終核完成前，分支不得合進 product 或部署（E-14 (c)）。
4. Codex 在環境可用時補跑。

## Verdict
PASS
BLOCKING_ISSUES=false
