# B0 測試補強 M3、L1～L5（frontend-engineer 回報）

- 審查者：frontend-engineer；commit 8d6d1f3（父 0aef9f0），只改測試檔，未 push、未合併
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
M3、L1–L5 已補完並 commit，新 commit 為 `8d6d1f3`（分支 `fix/stock-desk-b0-hold-stop-anchor`，接在 0aef9f0 之後）。只改兩個測試檔，未動任何產品程式或字面。M1、M2、L6 未處理。未 push、未 merge、未啟動 server，也沒讀 `.env` 或 `*.db`。

## 各項修改
測試檔位於 `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/lib/__tests__/`。

- **M3**（`keyLevelsHoldingUnknown.test.ts`）：持倉未確定的案例加了 `not.toContain(KEY_LEVELS_TARGET_ANCHOR_CROSS_REF)`。
  - 我另外加了一條正向對照：確定持有但成本不可用的 (c) 案例斷言這句有渲染。這是你沒要求的小增項。
- **L1**（同檔）：(a)(b) 合併成一個案例（分 ATR 有、無兩個），輸入為 `undefined`。
  - 註解說明：載入中與失敗在頁面上都是 `positions.data === undefined`，這個測試分不出兩者。
  - 註解也說明：refetch 失敗但保留舊 data 的情形不在範圍內，且沒有新增 hook 層測試。
- **L2**（`componentWordingScan.test.ts`）：改為完整比對 `{holdingKnown ? fmt(levels.stopSuggested) : "—"}` 與 `{holdingKnown ? fmt(levels.target2R) : "—"}`。
- **L3**（`keyLevelsHoldingUnknown.test.ts`）：
  - 停損、停利兩個大字各自緊接在自己的卡片標題後面，且都是「—」。
  - 大字「—」的 `<p>` 在整段 HTML 中剛好出現 2 次。
  - 詳細區 2R 與 +20% 固定停利兩列的值都是「—」。
- **L4**（同檔）：決策卡 `holding-unknown`（positions 為 undefined）與 `close-unknown`（avg_cost 為 0）的整段 HTML 做 `toBe` 相等斷言。
- **L5**（同檔）：確定未持有分支加相鄰斷言，「大字為…」那行緊接 not-held 基準句，兩個 `<p class="mt-1">` 之間沒有其他元素。

## M3 反向驗證
把 `KeyLevelsPanel.tsx:564` 的 `{holdingKnown && <p …>}` 暫時改成 `{<p …>}` 後，持倉未確定的兩個案例（ATR 有、無）紅燈：`Tests 2 failed | 7 passed`，其餘案例仍綠。紅燈後已用 `git checkout` 還原，產品檔無差異。

## 驗證
- vitest 全套：80 個檔案、2255 個測試全過。
- `tsc --noEmit`：exit 0。
- `node_modules` 用 `cp -a` 複製過來，commit 前已刪除。commit 只含兩個測試檔，工作樹乾淨。
