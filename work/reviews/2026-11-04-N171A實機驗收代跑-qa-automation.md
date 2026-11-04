# N-171 群組 A 實機驗收代跑（5e7c31c，只交事實）

- 審查者：qa-automation
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

N-171 群組 A 的清單 1～5 已在受測樹 `5e7c31c` 的 production build 加真後端上跑完。以 e2e-fallback 代跑，代跑者 qa-automation，只交事實、不下 Verdict。

- 所有證據在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n171_out/`。
- 摘要與逐條表格在該目錄的 `facts.md`，共 584 行，開頭有四段式摘要。
- 腳本在 `.../scratchpad/e2e_n171_scripts/`。
- 產品碼差異（`git diff --stat origin/product/stock-desk 5e7c31c -- apps`）存在 `.../scratchpad/n171_diffstat.txt`，共 20 檔。

## 各部門回報

只有 qa-automation 動作：改了測試腳本與拋棄式 DB。

沒有改產品碼、依賴宣告或 lockfile。沒有安裝東西，沒有讀 `.env`，沒有碰 `apps/stock-desk/backend/data/*.db`。

## 驗證

**環境**
- worktree 用 `git worktree add --detach` 開在 scratchpad，HEAD `5e7c31cf750cbb6661d83ea1c66c0006f176228f`。
- `node_modules` 用 `cp -al`，`next build` 成功，`next start :3000`，uvicorn `:8000`。
- 每個情境和視窗都用全新重建的 DB。DB 路徑每次寫入前做 realpath 前綴斷言（`env.sh`、`mkdb.py` 的 `guard`、`dbtool.py` 的 `guard`）。
- 寫入請求缺 `X-Stock-Desk-Client` 的次數：全部情境皆為 0。
- 結束時已停掉 uvicorn 與 next，並移除 worktree。repo 的 git status 乾淨。

**provenance**
- playwright 1.63.0，路徑 `/opt/node-tools/node_modules/playwright/index.js`。
- Chromium 153.0.8010.12，路徑 `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。
- runner 開頭的 `/opt/` 前綴 fail-closed 斷言沒有觸發。

**清單 1：風控 Q13 的 S-A～S-D**
- 四個情境都有 375×812 與 1280×900 的截圖和 DOM 擷取。
- S-A 的 DOM 擷取包含 A-2 修訂版全文與 NB-6 第 2 段第二版全文。
- S-A 實測：
  - NB-6 標籤與三段都與 `wording.py` 常數逐字相同，第 2 段含 3 個「。」，且含區塊標題。
  - 區塊不在對話框內。
  - 回執橫幅數為 0。
  - 徽章顯示「緊急出清後凍結 … 暫停中」。
  - DB 有 2 列（0050 第 1 批 200 股、2330 第 1 批 300 股），與區塊的兩行一致，股數不翻倍。
- S-B：第二次送出前後，區塊 `innerText` 與 `outerHTML` 都全等。
- S-C：狀態列不在、區塊數 0、標題 0 次、無空殼、有「無法載入排程台資料」、sticky 與 fixed 為 0。禁用字面都未出現。
- S-D：區塊數 0。頁面中含「無／沒有／尚無」的行已原文列在 `facts.md`，供判讀 F-4。

**清單 2：VP 條款**
- VP-1 到 VP-24 在 F1～F5 與 F5u、三種尺寸逐條量測，表格在 `facts.md` 第三節。
- 色值都經 canvas 轉成 sRGB。
- VP-2 的間距在所有 fixture 與視窗下為單一值：24、24、8、16 或 24、4、8、13、4、25、16，stale 的 h3 離小節上緣 18。

**清單 3：風控版面條件**
- R-3 (c)：f2、f5 三視窗，covering 與 stale 的行本文與附註 computed style 簽章相同，li padding 相同。
- stale 的 `border-top` 為 2px solid，色 (115,115,115)。
- stale 粗線實際效果截圖：`f2_*_stale_line.png`、`f3_*_stale_line.png`、`f5_*_stale_line.png`。
- R-4：最長的是 f5 在 375×812，區塊總高 2054px，整頁高 5959px，約佔 34.5%。截圖是 `f5_375x812_full.png`。

**清單 4：fixture 整頁截圖**
- F2、F4、F5（authored 版與 unauthored 版 f5u）、F6（真橫幅 f6、mock 長橫幅 f6m）都在 375×812 與 1280×900 各有 `*_full.png`。
- 涵蓋 covering、stale、unclassified 三類小節，以及 A-6、A-11、A-12、A-15 的行。對照表在 `facts.md` 第五節。

**清單 5：回歸**
- C 組在 375×667：T1 狀態列 0 至 277，scrollY 207，橫幅減狀態列下緣 16，第一個 `<p>` 減狀態列下緣 33。
- 無區塊（沿用上一輪 `probe_today.json`）與有區塊（F2 狀態的真 `pending_exit_block`）兩種 `/today` 本體都是 16／33。有區塊時，區塊上緣減橫幅下緣為 24。
- VP-18：f6（有區塊）與 f6nb（把 `/today` 的區塊改成 null）相比，橫幅、狀態列高度、觸發鈕 rect 前後差都是 0。
- `role=status` 在掛載與卸載期間每個 frame 都是同一個 DOM 節點。
- 無橫向捲動：`scrollWidth > innerWidth` 的組合數為 0。
- 掛載與卸載逐 frame 取樣，opacity 恆為 1。
- 無區塊時 Tab 順序相同。

## 需要 qa-e2e 判斷的事

1. **VP-14 日期拆行**：375 寬的 F5 與 F5u，`2026-11-11` 在第二個連字號後換行，Range 有 2 個矩形。規範預期 1 個。320 寬時 `2026-11-05` 與 `2026-11-02` 也被拆。1280 寬沒有拆。逐字元位置在 `probe_date_*`。
2. **VP-4 像素取樣與底色**：空白帶取樣 (10,10,10)，規範寫 (0,0,0)±1。頁面 `body` 與 `html` 的底色是 `rgb(10,10,10)`。區塊所有子孫背景 alpha 皆為 0。文字對比以黑底算為 14.17:1，以 (10,10,10) 底色算為 13.31:1。
3. **VP-18 掛載時 scrollY**：
   - scrollY=0 時前後差 0。
   - 375 寬 scrollY=700（落在橫幅內）時差 0。
   - 1280 寬 scrollY=700，以及兩種寬度捲到底時，scrollY 會變，差等於文件高度增量：375 為 1778，1280 為 958。
   - 對 `documentElement` 設 `overflow-anchor:none` 後差為 0。掛載期間沒有任何頁面程式的捲動呼叫。
   - 是否算違反該條，請判斷。
4. **風控終核項**：R-3 的粗線讀感與 R-4 的帳冊被推多遠，我只附實際截圖和數值。f5 的帳冊文件座標 top 為 3926px。
5. **F5 拆成兩個情境**：真後端上 A-9（authored）與 A-13（unauthored）互斥，所以拆成 `f5` 與 `f5u`，兩者各含 8 日期列與 20 字元 symbol 列。

## 我自己加的路徑

- **情境製造**：`mkdb.py` 用受測樹的 `PlaybookStore`（`ensure_batches`、`save_batch`、`record_directives`）寫持有批次與出清列。
  - stale 列的執行日取 2026-10-24（週六）。
  - covering 且已過期的列取 2026-11-02。
  - 未過期的列取 2026-11-05 起。
  - unauthored 情境刪除 `playbook_rule_params` 與 `rule_set_confirmed_*` 狀態。
- **行情資料**：拋棄式 DB 內預載的 `demo_synthetic` 日線（2330、0050、00631L，到 2026-10-30）。供應商在沙盒回 403，服務以快取回應。**本次畫面為合成示範資料。**
- **mock 的地方**（`facts.md` 各情境 `kind` 欄已標明）：
  - S-A、S-C：POST 先轉送後端 commit，再改寫成 500。S-C 另外 abort 其後的 `/today`。
  - S-B、S-D：POST 在進後端前被 route 直接回 500。
  - `f6m`：POST 回應換成長橫幅。
  - `f6nb`：`/today` 的區塊改成 null。
  - F8（缺鍵）、F9（rows 皆空）、F10（pending）、F11（error）、F12（背景重取失敗）：route 改寫或阻斷 `/today`。
  - 掛載與卸載測試、Tab 順序對照：同樣用 route 改寫區塊。
  - F7 是真後端，有持有批次但沒有出清列。
- **觸發重取**：用 `window` 的 `visibilitychange` 事件。
- **VP-4 像素取樣**：整頁截圖在第二個分頁的 canvas 解碼後取樣。
- **C 組回歸**：沿用上一輪 `e2e_n183_scripts` 的 `lib.js` 與 `sc_comp.js`（未改，複製在 `e2e_n171_scripts/c_old/`），新增兩個 wrapper。

## 與預期不符的觀察

- 日期在連字號處拆行（上述第 1 項）。
- 像素取樣 (10,10,10)（上述第 2 項）。
- scrollY 在下方捲動位置掛載時會變（上述第 3 項）。
- F6 真回執只有短訊息（「已產生 1 批、共 100 股」），拿不到 attribution 與 warnings 皆非空的長橫幅，所以用 `f6m` 補。
- Playwright 的元素截圖 `*_block.png` 頂部會疊上 sticky 狀態列，判讀請看 `*_full.png` 與 `*_view.png`。
- S-A 沒有回執橫幅時，A-14 末尾說明仍顯示「本頁若同時顯示…」，這是 A-14「一律出現」的規定。
- li 高度與規範公式的差在 −1 到 +1，在容差內。

## 缺口

- VP-20 的「移除功能前 baseline 逐像素對照」未做，只量了 `role=status` 的下一個兄弟與 16px 間距。
- V-9、V-10、V-11、V-12、V-47 只重跑了 C 組。A、B、D、E、F、G 組沒有重跑。
- 沒有任何真實行情的畫面。

## 下一步

交 qa-e2e 判讀，風控終核 S-A～S-D、R-3、R-4 的畫面。

主要檔案（皆在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/` 下）：
- `e2e_n171_out/facts.md`
- `e2e_n171_out/facts_*.json`
- `e2e_n171_out/*.png`
- `e2e_n171_out/c_with/`
- `e2e_n171_out/c_without/`
- `e2e_n171_scripts/`
