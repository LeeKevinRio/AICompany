# 證據交件第二輪（e2e-fallback 補跑）— qa-automation

以 e2e-fallback 代跑，代跑者：qa-automation。只列事實，不下 PASS / FAIL，判讀交 qa-e2e。

## 0. 環境與跑法（與第一輪相同，只改 fixture）
- 受測版本 `49c2ca3259d0ddaa334a55419f40aa9624af70b0`；沿用第一輪仍在跑的 `next dev --webpack --port 3100`（我沒有停它，也沒有再嘗試 kill）。
- runner：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/runner2.js`（由 `runner.js` 複製，儀器載入與前綴斷言不變；差異只有 fixture、案例清單、展開 `<details>` 的點擊步驟）。
- 指令：`cd <scratchpad>/e2e-t3 && PW_CHROME=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome OUT_DIR=$PWD BASE_URL=http://localhost:3100 NODE_PATH=/opt/node22/lib/node_modules:/opt/node-tools/node_modules node runner2.js > stdout-r2.txt 2> stderr-r2.txt`
- 原始輸出：`stdout-r2.txt`、`raw-output-r2.json`（含 provenance：playwright `/opt/node-tools/node_modules/playwright/index.js`、chrome `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`、trustedPrefix `/opt/`）；`stderr-r2.txt` 為空。
- 不用真實 DB、不讀 `.env*`、不改產品碼、不 commit。截圖 deviceScaleFactor 1、viewport 高 900。

## 1. Fixture（全為合成資料）
日線 80 根，日期 2026-09-01 起逐日，open 100 / high 105 / low 95 / volume 1000 / TWD / `synthetic-fixture`，close = `100 + (i % 7)`。
- `9999`：index 40 的 `low:"0"`，且最後一根（2026-11-19）`close:"-1"`（兩者皆有，同第一輪）。
- `7771`：只有 index 40 的 `low:"0"`，所有 close 為正。
- `7772`：只有最後一根 `close:"-1"`，其餘 low/high/close 皆正。
- 組 A（持有）：`/api/positions` 回一筆 `{id:1, symbol:"9999", market:"TW", quantity:"1000", avg_cost:"120", currency:"TWD", opened_at:"2026-09-01", instrument_type:"stock"}`（合成，非真實持倉）；advice 回 `held:true, position_ids:[1]`，卡片 action 仍為 `add`、quantity 500~1000。
- 組 B、C（未持有）：positions 空，advice `held:false`。
- signals 一律 `insufficient_data`；directory resolve `{found:false}`。
- 持有組多出一個請求 `GET /api/leverage/9999?market=TW`（持有才會觸發），我沒有為它做 fixture，runner 回 404 `{"detail":"no fixture"}`，因此該組 console 有一筆 `[error] Failed to load resource: the server responded with a status of 404 (Not Found)`，network 有一筆 `404 GET http://localhost:8000/api/leverage/9999?market=TW`。其餘組無 error。

## 2. 結果
所有截圖都在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/shots-r2/`，每個目標有 `-element.png`（區塊）與 `-fullpage.png`（整頁）。檔名規則：`<組>-<寬度>-<目標>-{element,fullpage}.png`。
每組都量了：innerText 是否含「距最新收盤」「距現價」「%」「價格單位」（腳本旗標，原文見 `raw-output-r2.json` 的 `shots[].flags`）。375 與 1280 每個目標的 innerText 逐字相同（我逐段比對輸出，內容一致）；`document.scrollWidth == clientWidth`（375/375、1280/1280）。含「價格單位」字串的最內層 section 在所有組都只有 `技術分析`。

### 組 A：持有錨點、異常標的 9999（375 與 1280）
檔名：`A-held-both-375-card-element.png`、`A-held-both-375-card-expanded-element.png`、`A-held-both-375-panel-element.png`；`A-held-both-1280-…` 同三種；另各有 `-fullpage.png`。
- 決策卡 innerText（收合狀態，逐字）：
```
資料截至 11-19
加碼參考
依規則
▸
未經歷史驗證

最新收盤

—

 

停損參考

—

 

股數參考

500 ~ 1,000 股

 

依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。
```
- 展開「未經歷史驗證」後（以 click `summary` 觸發），innerText 與上相比只多一段：
```
這個結論所依據的規則、門檻與權重，都還沒用歷史資料驗證過。
```
（位於「▸ 未經歷史驗證」之後、「最新收盤」之前。）
- 距離句：「距最新收盤」＝無；「距現價」＝無；`%`＝無；「價格單位」＝無（收合與展開兩狀態皆同）。收盤、停損兩格皆「—」；股數格「500 ~ 1,000 股」。
- 同頁面板 innerText：「關鍵價位參考」＋「目前沒有可用的日線資料，本面板無法計算任何關鍵價位。」（兩寬度相同）。
- 版面數值（取自 `raw-output-r2.json` 的 `styles`，欄位含 fontSize / color / display）：請以該檔 `results[A-held-both-*].shots[*].styles` 為準；本輪未另行摘錄。

### 組 B：只有 low=0（7771），未持有（375 與 1280）
檔名：`B-lowzero-375-panel-element.png`、`B-lowzero-375-card-element.png`、`B-lowzero-1280-…`；另各有 `-fullpage.png`。
- 面板 innerText：
```
關鍵價位參考

目前沒有可用的日線資料，本面板無法計算任何關鍵價位。
```
- 決策卡 innerText：
```
資料截至 11-19
未持有

未持有此標的，以最新收盤 — 試算；此數字不是任何進場暗示。

進場評估
規則評估未命中防禦型規則，建設性規則命中 1 條。 這不構成進場理由。
▸
未經歷史驗證

最新收盤

—

 

停損參考

—

 

股數參考

500 ~ 1,000 股

 

依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。
```
- 距最新收盤 / 距現價 / % / 價格單位：皆無。console 無 error（僅 React DevTools info、HMR log）；network 5 筆 200。

### 組 C：只有最後一根 close=-1（7772），未持有（375 與 1280）
檔名：`C-closeneg-375-panel-element.png`、`C-closeneg-375-card-element.png`、`C-closeneg-1280-…`；另各有 `-fullpage.png`。
- 面板 innerText 與決策卡 innerText：與組 B 逐字相同（面板同為兩行無資料句；決策卡同為「未持有」＋「—」「—」＋「500 ~ 1,000 股」）。
- 距最新收盤 / 距現價 / % / 價格單位：皆無。console 無 error；network 5 筆 200。

## 3. 限制（如實）
- 組 A 的 leverage 404 是我沒做該端點 fixture 造成，不是受測碼行為；產品碼對 404 有既有 fallback，本輪頁面沒有看到槓桿專章區塊的畫面證據（我沒有截該區）。
- 持有組的 `-fullpage.png` 展開狀態只存在於 `card-expanded` 那組截圖。
- 計算樣式只存在 `raw-output-r2.json`，本文件沒有逐項摘錄。
- 異常標的的「技術分析」區是否仍顯示 -1.00，本輪沒有取該區 innerText（第一輪也沒有取）；如需要請 qa-e2e 指定，我再補截。
