# N-171-A 重驗代跑（VP-14 於 346d5cb、S-A／S-D 結算句於 73f369e，只交事實）

- 審查者：qa-automation
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
我只交事實，沒有下 Verdict。證據檔是 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n171_out2/facts.md`，開頭有四段式摘要，後面是詳細表格。

**受測 HEAD 有兩個**
- VP-14、不退步檢查、V 系列、其餘情境：全部在 `346d5cb` 上量的。增量 `git diff --stat 5e7c31c 346d5cb` 只有 2 個前端檔（`PendingExitBlock.tsx`、`PendingExitBlock.test.ts`）。
- 追加的 S-A、S-D 結算句：在 `73f369e` 上量的。`git diff --stat 346d5cb 73f369e` 只有 `wording.py`、`n171a.json`、`test_playbook_wording.py`，前端沒有變動。
- 因為 VP-14 已在 `346d5cb` 上做完，我沒有在 `73f369e` 上重跑。

**VP-14（f5、f5u；375×812、375×667、1280×900、320×640）**
- 日期 token：f5 有 16 個、f5u 有 18 個。每個 token 的 Range 矩形數都是 1，`span.getClientRects()` 也是 1。
- 沒有未被 span 包住的 token。
- `probe_date` 在 4 個視窗的 `splits` 都是空。上一輪在 375 寬列出 `2026-11-11`，在 320 寬列出 2 個被拆的日期。
- span 的 `white-space` 是 nowrap，`display` 是 inline。190 個 span 全部是 `<p>` 的直接子元素，class 只有 `whitespace-nowrap`，屬性只有 `class`。
- `<p>` 的 `white-space` 是 normal。區塊內 `p` 以外沒有元素是 nowrap 或 pre*。
- 320 寬：`scrollWidth` 是 320，`innerWidth` 是 320。
- 其他 VP-14 條款（p 寬、行高整數倍、導言行數、20 字元 symbol、`overflow-wrap`）與上一輪一致，沒有出現新值。
- 導言行數：375 寬 12 行、320 寬 15 行、1280 寬 5 行。

**不退步檢查**
- VP-10：f1～f5u 全部組合，`textContent` 與 `innerText` 和 API 值都是 0 段不等。
- VP-6、VP-12、VP-16：量測值無異常。VP-16 的 span 是唯一 inline，且都是 `p` 的直接子元素。
- VP-4：取樣 (10,10,10)，等於 body computed 背景 (10,10,10)，各通道差 0。
- VP-18：`mnt` 的 `bottom` 情境，`scrollY` 差都等於文件高度增量（375 寬 1778、1280 寬 958），錨定元素視窗座標差 0。`scrollY=0` 與 375 寬 `scrollY=700` 的差是 0。
- V 系列：A、B、C、D、E、F、G，另加 C2、C3。有區塊和無區塊的 T0、T1、after500 欄位逐欄位相同，程式捲動呼叫也相同。C 組與上一輪逐值相同。

**追加：`73f369e` 的 S-A、S-D（375 與 1280 各一份）**
- 結算區 `innerText` 逐字是：「結算\n\nT+1 結算：本次結算沒有判定任何指令；預定執行日在本次結算範圍之外的指令，維持待結算。」
- S-A 四份（375、1280）：區塊標題「全部出清產生、尚未結算的賣出指令」出現 1 次，區塊有 0050 與 2330 兩列；新句出現 1 次；舊句「T+1 結算：目前沒有待結算指令。」出現 0 次；沒有任何行含「沒有待結算指令」或「目前沒有」。
- S-D：區塊數 0，新句 1 次，舊句 0 次。
- 全部情境的 NB-6 標籤與常數比對都是 True。

## 各部門回報
- 我跑了這些情境：fx_f1～fx_f5u（含 f5u 的 320）、probe_date、f6／f6m／f6nb、sa～sd、f7～f12、mnt、tab，以及 V 系列的 c_with、c_without、c_withnb（各 3 視窗）。
- 0 個 ERROR 檔，沒有腳本跑不動的情境。
- 沒改任何產品碼，也沒動 `package.json` 或 lockfile。

## 驗證：需要 qa-e2e 判斷的事項
1. **日期 span 寬度與規範不符**：實測 70.25～78.890625px，規範與 frontend 都寫「約 85px」。320 寬沒有溢出，所以只是規範字面的問題，是否要改交你判斷。
2. **V 系列的對照基準**：`c_with` 和 `c_without` 兩份 mock 本體除了 `pending_exit_block`，另有 8 個欄位不同，包括 `warnings`、`settlement`、`snapshot`。
   - 所以 `docH` 差（375 寬 2818、1280 寬 1402）不全是區塊造成。
   - 我另加 `c_withnb`：`c_with` 本體只把區塊設為 null。T0、T1 欄位在兩種對照下都無差異。純區塊的 `docH` 增量是 375 寬 1733、1280 寬 913。
   - 區塊高度請以 3.2 節為準。
3. **VP-18 判準**：`bottom_noanchor` 對照列內容被推開 1778／958px，只是對照，不是過關條件。請你對照條文判讀。
4. **覆蓋缺口**：日期只出現在「行本文」和「附註」兩類 `<p>`。
   - 區塊導言、小節導言、`closing_notes` 在 fixture 裡沒有 ISO 日期，導言的 `{read_at}` 戳記是 `2026/11/05 00:30（台北時間）` 斜線格式。
   - 所以這三處的 span 包裝沒有實機量到，只有 frontend 的單元測試。後端字面我不能自行捏造，要補驗請你指定來源。
5. 只用了 Chromium 153.0.8010.12 一個引擎，斷行行為仍可能因引擎而異。

## 下一步
- qa-e2e 請讀 `facts.md` 的第一節（VP-14 全表與逐 token）、第二節、第三節與第七節（`73f369e` 結算句），再看截圖後判讀。
- 截圖都在 scratchpad：
  - f5 與 f5u 在 375 與 320 寬的整頁截圖：`f5_375x812_full.png`、`f5_320x640_full.png`、`f5u_375x812_full.png`、`f5u_320x640_full.png`，目錄是 `e2e_n171_out2/`。
  - 日期所在區域的局部截圖：`*_dates_li.png`（8 日期那一列）、`*_lead.png`。
  - `73f369e` 的結算區截圖：`e2e_n171_out2/at_73f369e/{sa,sd}_{375x812,1280x900}_settlement.png`。S-A 另有整頁 `sa_*_closed_full.png`。
- 腳本在 `e2e_n171_scripts2/`（346d5cb 那輪）和 `e2e_n171_scripts3/`（73f369e 追加）。

## 我自行加的路徑
- 逐 token 與逐元素的 `white-space`、`display`、父元素量測（`inpage.js` 的 `dateSpans()`），以及 `innerText` 比對。
- 日期區域局部截圖。
- f5u 的 320×640。
- `mnt` 加錄錨定元素視窗座標。
- `c_withnb` 乾淨對照。
- 順跑 S-A～S-D、f6 系列、f7～f12、tab。
- `probe_date` 在 f5 DB 重跑。
- `73f369e` 上的 `settleFacts()`：擷取結算區文字、區塊列、新舊句出現次數與截圖。

## 與預期不符的觀察
- span 寬度與「約 85px」不符（見上）。
- c_with／c_without 兩份 mock 本體差異大於區塊（見上）。
- 你指名的 `e2e_exitfb_scripts2/sc_comp.js` 與 `c_old/sc_comp.js` 逐行相同，只差最後一行 `module.exports`（多匯出 `__h`）。所以我沿用 `c_old`。
- 重驗期間主工作區 `/home/user/AICompany` 的 HEAD 從 `7977a8d` 變成 `916d627`（`product/stock-desk`）。這不是我操作的。我只對 `origin/feat/stock-desk-pending-exit-block` 開 detached worktree，沒碰主工作區。
- V 系列的 mock 本體是沿用上一輪 `c_with/probe_today.json` 與 `c_without/probe_today.json`，沒有重新抓取。後端在 `5e7c31c` 到 `346d5cb` 沒有改動。
- `wording_consts.json` 沿用上一輪。`73f369e` 只改了結算句常數，NB-6 與區塊字面常數未變，結算句我直接用畫面逐字比對。
- 其餘量測沒有看到與條文不一致的值。

## provenance
- Playwright 1.63.0：`/opt/node-tools/node_modules/playwright/index.js`。
- Chromium 153.0.8010.12：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。
- `trustedPrefix` 是 `/opt/`，runner 的前綴斷言沒有觸發，沒有 `e2e-fallback: ABORT`。
- 沒安裝任何東西；`node_modules` 以 `cp -al` 建立；前端是 `next build`＋`next start`（production）；後端是真 uvicorn。
- 沒讀 `.env`，沒碰 `apps/stock-desk/backend/data/*.db`。拋棄式 DB 在 `e2e_n171_db2/`（346d5cb）與 `e2e_n171_db3/`（73f369e），寫入前都做 realpath 前綴斷言。
- 寫入請求缺 `X-Stock-Desk-Client` 為 0 次。
- 結束後：uvicorn、`next start`、Chromium 都已停（`ps` 無殘留，:3000 與 :8000 無回應）；`wt_n171b`、`wt_n171c` 都已 `git worktree remove --force` 並 prune；主工作區 `git status --short` 為空。
- 證據檔：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n171_out2/facts.md`，以及同目錄下的 `facts_*.json`、`c_with/`、`c_without/`、`c_withnb/`、`at_73f369e/`。
