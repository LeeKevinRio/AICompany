# 風控整改 R-1～R-5 增量核對

- 審查者：qa-reviewer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

BLOCKING_ISSUES=false

# 增量核對：`git diff 48c5209 4c9e1fe`（fix/stock-desk-risk-remediation，3 個 commit）

## Summary
R-1、R-2、R-3、R-5 都符合風控裁定，沒有 critical 或 high 問題。C-9 前置條件已解除，但有一項記錄義務要留意（見第 5 點）。Codex 第二意見無法取得，原因見後文。

diff 範圍共 5 個檔案，+75/-9：
- `README.md`
- `limitNotices.ts`
- `limitNotices.test.ts`
- `riskRemediationItem4.test.ts`
- `OperationSummaryPanel.tsx`

我只做靜態比對，沒有跑測試。交件宣稱的 CI 全綠（vitest 2413 通過）我無法獨立驗證。

## 核對結果

### 1. R-1（2-R 只在 hold 顯示）：通過
- `limitNotices.ts:31`：`NOTICE_ACTIONS = ["hold"]`。
  - 註解已改為「風控 2026-10-26 裁定修訂 C-6；失效條件 T1、T9」，並附英文原因說明。
  - 使用處 `:92` 的條件（`kind === "held"`、違反數大於 0、`NOTICE_ACTIONS.includes`）沒變。
  - `buildLimitsDoNotChangeActionNotice`（`riskRemediationWording.ts:75-77`）不在 diff 內，字面未動。
- `limitNotices.test.ts:240-249`：矩陣中 reduce、take_profit、stop_loss 改為 `shown: false`。
  - 上方註解標了「行為變更（風控修訂 C-6，2026-10-26 裁定）」。
  - add 與 insufficient_data 維持 false。hold 維持 true，第 253 行的斷言邏輯沒刪。
- 00631L 型 fixture 的斷言有兩條：
  - 單元層（`:259-273`）：reduce 加第 1、4 條違反。
    - `actionNotice` 為 null。
    - 2-M 標題「已違反 2 條上限：」，兩行。
    - 2-O「另有 1 條上限無法評估…」，這裡的 1 條是因為 fixture 的第 5 條被 kelly 排除，算法正確。
  - 渲染層（`:365-377`）：沒有「不代表你的部位在上限內」，2-M、2-O 與 3-S 都在。
- `test_advice_engine.py` 不在 diff 內，沒動。後端零變更。
- 原有 2330 hold 的順序測試（`:311`、`:349`）沒動。
- 實機結果（`runner2_out.txt`）：
  - 00631L 決策卡沒有 2-R。
  - 它有 2-M，兩行逐字等於交件所述。
  - 2-O 與 3-S 都在。
  - 2330 的順序是被擋句、2-R、2-O、3-S。

### 2. R-2（README）：通過
- `README.md` 的 diff 只有第 32、33 行。
  - 第 32 行句末「；」改成「。」。
  - 原第 33 行（常駐免責句）整行刪除。
- 第 34 行維持原樣。與風控給的刪字後字面完全一致，沒有新增文字。
- 我另做了一次 Grep：整個 worktree 在 `.md/.ts/.tsx` 中，「研究與教育用途」與「非投資建議」的出貨面殘留只有以下幾類，都不渲染：
  - 兩個測試檔的「不得含此詞」負向斷言（`limitNotices.test.ts:168`、`riskRemediationItem4.test.ts:89`）。
  - `docs/adr/` 與 `work/` 內的歷史文件。
  - 交件所說的 `KeyLevelsPanel.tsx` 兩行註解。
- 這個 Grep 的 head_limit 是 40，輸出被截斷，所以我沒完整複核 `KeyLevelsPanel.tsx`，只能採信交件對那兩行註解的描述。
- 後端 `engine.py` 的 `DISCLAIMER` 與 `notify.py` 屬於 3-F／3-N 範圍，不在本輪增量，我沒有複核。

### 3. R-3（4-附全形括號）：通過
- `OperationSummaryPanel.tsx:305`：`<span className="text-neutral-400">{`（${DRAWDOWN_UNADJUSTED_NOTICE}）`}</span>`。
  - 全形括號與文字在同一個模板字串，因此在同一個文字節點、同一個 span。
  - 規則名稱後面直接接 span，`ml-2` 已移除，風控允許。
- `DRAWDOWN_UNADJUSTED_NOTICE` 常數所在的 `riskRemediationWording.ts` 不在 diff 內，常數沒改。
- `riskRemediationItem4.test.ts:343-368` 用 `it.each` 對 `drawdown_protection`（兩成）與 `deep_drawdown_stop`（三成）各一條逐字斷言：
  - 去標籤後的 innerText 逐字等於「依據：目前回撤深於{兩|三}成（以未還原價計算，回撤可能含除權息缺口）」。
  - 另有 DOM 結構斷言：規則名稱後緊接 `<span class="text-neutral-400">（…）</span>`。
- 實機：00631L 操作摘要的「依據」行逐字為「依據：目前回撤深於兩成（以未還原價計算，回撤可能含除權息缺口）」，與風控指定的 innerText 一致。
- 小缺口，不擋：三成的 deep_drawdown_stop 只有單元測試，沒有實機佐證（示範資料只有兩成）。風控也只要求兩條斷言，所以不算違規。

### 4. R-5：通過
- diff 只有上述 5 個檔案。
  - 風控字面檔 `riskRemediationWording.ts` 不在 diff 內。
  - 守門檔（`componentWordingScan.test.ts` 等）不在 diff 內。
  - 所以 C-1 守門清單沒動，其他字面也沒動。
- 本輪新增的字面只有測試註解與測試名稱，加上 R-3 的兩個全形括號。

### 5. C-9 前置條件：已解除
- `work/reviews/2026-10-26-信任缺陷結案確認-風控.md` 第 3 點明文「C-9 可以結案」，並寫「風控整改分支（3-N）的 C-9 前置條件：已解除」。
- dev-lead 的書面確認存在：`work/reviews/2026-10-26-信任缺陷R1R3與股數成因交件-dev-lead.md` 第 160 行起「C-9 書面確認：成立」。
- 所以 frontend 交件那句「仍缺 dev-lead 確認」已過期，可以視為不存在。
- 但風控附了兩項尚未落地的後續義務，由 coordinator 或 CEO 追蹤，不是本輪程式碼問題：
  - 3-N 分支的紀錄要同時引用兩份證據，並註明分支與行號。
    - 一份是 `test_alerts_notify.py:68-101`（ae548 分支，警示層不碰盤中報價）。
    - 另一份是 `test_service.py:985`、`:1020`（資料層剔除未收盤 bar）。
  - 舊 DB 殘留未收盤 bar 的唯讀檢測，由 data-engineer 出查詢、CEO 執行。風控明說不擋合併，是 required 的後續追蹤項。

## 各檔問題
本輪增量沒有 critical、high 或 medium 問題。僅以下 low 與觀察：
- `limitNotices.ts`：[可維護性][low] `NOTICE_ACTIONS` 現在只有一個元素，`includes` 可簡化成 `action === "hold"`。風控已明定實作形式，且 T1 要求顯示動作集合再變動就要重送風控，維持陣列有利於日後被絆線抓到，不建議改。
- `riskRemediationItem4.test.ts`：[可維護性][low] 用 `html.match(/<p class="text-sm text-neutral-300">…/)` 抓第一個符合的 `<p>`。目前該 class 在 SummaryBody 內只有依據行使用，通過。日後若在它之前出現同 class 的 `<p>`，會抓錯而讓測試失敗，屬於會響的失敗，不是靜默通過。

## 第二意見（Codex）
無法取得：`codex --version` 回 exit 127（`command not found`），環境沒有安裝 Codex CLI。
- 依前例的降級規則，此缺席必須在紀錄中揭露。
- 本輪全是靜態比對加風控逐字裁定，風險集中在字面與顯示條件，兩者都有風控逐字審把關，缺席的實質影響低。
- 我沒有因為缺席放寬任何判定。

## 唯讀權限判準常數
未觸及。

- 第一道檢查：`scripts/validate_agents.py` 不在 `git diff 48c5209 4c9e1fe --stat` 的 5 個檔案內。
- 第二道檢查：diff 內容只涉及前端與 README，沒有出現 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`。
- 這是靠 `--stat` 檔案清單與 diff 內容的人工比對，不是對 diff 輸出做機械 grep。我的 Bash 權限不准接管線，所以兩道檢查沒有用指令原樣跑，這點如實揭露。
- shadow 定義與常數值被改動兩種情境的答案：
  - 我用 Grep 搜整個 worktree（排除 `work/`、`docs/`、`.git`、`node_modules`），這兩個常數名稱只出現在 `scripts/validate_agents.py`、`.claude/skills/code-review-checklist/SKILL.md`、`.claude/agents/qa-reviewer.md`、`CLAUDE.md`。
  - 其中沒有任何檔案在本輪 diff 內，所以沒有 shadow 定義，常數的值也沒被改。
  - 改了什麼：無。為何改：不適用。有無對應 ADR：不適用。

## Verdict
PASS

BLOCKING_ISSUES=false

## 合併建議
- 程式碼可進 risk-gate。風控 2-R 裁定的三項 required（R-1、R-2、R-3）加 R-5 都已落地並經我複核。
- 本輪涉及 UI 字面，R-4 實機已由 frontend 用 `r2-` 本批截圖做過逐字確認。
  - 我只讀了逐字輸出檔，沒有看 `r2-*.png` 截圖。
  - qa-e2e 若要另行驗收，以 `r2-` 前綴的圖為準。
- 合併前請 coordinator 確認：
  - 風控對本輪 R-1～R-3 的最終「進 done」確認（裁定寫的是「qa 複核通過以後，第 1～4 項與 5-BT 可以進 risk-gate done」，現在複核已通過）。
  - 5-K 仍等 CEO 裁定，不屬於本批。
  - C-9：3-N 分支的紀錄要同時引用兩份證據，並註明分支。舊 DB 殘留的唯讀檢測列為後續追蹤，不擋合併。
  - Codex 缺席的事實要寫進 PR 紀錄。

## 自我揭露：執行過的 Bash 指令
共 5 條，其餘都是 Read、Grep、Glob 工具：
1. `git diff 48c5209 4c9e1fe --stat`
2. `git diff 48c5209 4c9e1fe -- README.md`
3. `git diff 48c5209 4c9e1fe -- apps/stock-desk/frontend/app/lib/limitNotices.ts apps/stock-desk/frontend/app/lib/__tests__/limitNotices.test.ts`
4. `git diff 48c5209 4c9e1fe -- apps/stock-desk/frontend/app/lib/__tests__/riskRemediationItem4.test.ts "apps/stock-desk/frontend/app/position/[symbol]/OperationSummaryPanel.tsx"`
5. `codex --version`（exit 127，找不到指令）

沒有使用 `cd`、管線、`git show`、`git log`、`sed`、`grep`、`cat`、`python`、`npm`、`uv` 或任何寫入。沒有讀 `.env`，沒有碰 `*.db`，沒有看 PNG。

## 相關檔案
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/apps/stock-desk/frontend/app/lib/limitNotices.ts
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/apps/stock-desk/frontend/app/lib/__tests__/limitNotices.test.ts
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/apps/stock-desk/frontend/app/lib/__tests__/riskRemediationItem4.test.ts
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/apps/stock-desk/frontend/app/position/[symbol]/OperationSummaryPanel.tsx
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/README.md
- /home/user/AICompany/work/reviews/2026-10-26-信任缺陷結案確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-26-信任缺陷R1R3與股數成因交件-dev-lead.md
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/runner2_out.txt
