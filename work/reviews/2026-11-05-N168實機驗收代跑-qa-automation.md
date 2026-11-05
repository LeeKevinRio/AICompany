# N-168 實機驗收代跑（d1ff816）

- 審查者：qa-automation
- 日期：2026-11-05
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
我只交事實，沒有下 Verdict，Verdict 由 qa-e2e 下。

受測 commit 是 `d1ff816`（`git -C <wt> log -1` 已確認，分支 `feat/stock-desk-exit-pending-r-buys`）。VP-168-1～20 與 VP-21 在 320、375、768、1280 四個視窗都量了。

- **機械比對**：量測值對規範值的比對，共 0 條落在容差外。
- **WebKit**：環境沒有，列為「未驗證殘留」，沒有安裝。
- **R-3 最關鍵的一項（VP-168-8）**：375 寬（scroller 可視寬 341，`maxScroll` 299）與 320 寬（可視寬 286，`maxScroll` 354）各量 5 個 `scrollLeft` 位置（0、25%、50%、75%、max）。每個 pin 的每個文字矩形，左內縮 13px、右內縮 14.4～22.9px，`outOfBounds` 都是 0。
- **768 與 1280 寬**：`maxScroll` 為 0，只量 `scrollLeft` = 0，同樣沒有越界。

證據的完整表格在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n168_out/facts.md`（約 410 列，同檔內容也在 `facts_table.md`）。欄位是「VP｜視窗｜項目｜實測｜規範｜是否在容差內（機械比對）」。

## 各部門回報（代跑事實）

### VP 實測值對規範值（摘要，逐視窗逐列見 facts.md）
- 帳冊 note 用 N1～N3。N1 是 W-B2L，N2 是 W-B2LS 加 W-B2LSr，N3 是 W-B2LSf。N1～N3 的 note 字串由 worktree 後端 `service.entry_before_exit_note` 實際產生，沒有自己撰寫。

| VP | 規範值 | 實測值 |
|---|---|---|
| 1 | DOM 順序為 [div.flex, p, div.grid, row-notes, p(limit), p(狀態)]；note 不在 grid 或標題內；標題與 grid 文字和 baseline 逐字相同 | 全部相同，4 個視窗一致 |
| 2 | 14px／20px／400／normal／none／none／rgb(212)±2／block | 全部相同 |
| 3 | 上緣 8／下緣 8／左 20／與 chip 左緣差 ≤1 | 8／8／20／0 |
| 4 | 無 overflow、max-height、line-clamp、hidden；無 title、aria、details；`textContent` 與 API 值逐字相等 | 違規 0 項，全部逐字相等 |
| 5 | `row-notes` 寬 307／700／956；`white-space` normal；`overflow-wrap` break-word；`word-break` normal；高度為 20 的倍數 | 307／700／956，其餘全部相同；320 寬為 252（規範無值，等於 `li` 內容寬） |
| 6 | 橫幅子樹無 `row-notes`、無 note 文字；class 與 rect 差 ≤1 | 375／768／1280 三個視窗，`outerHTML` 與 baseline 建置逐字相同，rect 差 0，`row-notes` 0 個 |
| 7 | 子列後接批次；`td` 的 `colSpan` 為 6；pin 內順序為 [label p, row-notes]；B 批無子列；無空 `tr` | 相符；批次列 6 個 `td` 文字與 baseline 逐字相同 |
| 8 | 見上；三條判準 a、b、c 都量過 | 頁面 `scrollWidth` 等於 `innerWidth`（320／375 皆是）；pin 子孫的 clip 屬性違規 0 項；pin 的 `scrollWidth` 等於 `clientWidth`（375 寬為 317、320 寬為 262） |
| 9 | 六欄 `th` 與 `table` 寬差 ≤1；`min-width` 640px；`td` 為 nowrap | 對 nulls 版與 baseline 建置，th 寬差都在 1px 內；A、B、C 三批各欄寬一致；640px；nowrap |
| 10 | label 14／20／600／neutral-100（245），note 14／20／400／212；不是徽章 | 相符；label 背景 alpha 0、圓角 0px、邊框 0px |
| 11 | 子列與批次列的間距 0；label 上緣到批次列內容底緣 4；label 到 note 4；最後一句到子列底 12；無 `border-top` | 0／4／4／**12.5**／0px。12.5 是 4 個視窗都一樣的小數（border-collapse），在 ±1 內 |
| 12 | label 寬等於 pin 寬 ±1 | 375 寬為 317 對 317；320 寬為 262 對 262 |
| 13 | `p` 高度為 20 的倍數；`li` 與子列高度公式 ±2 | 全部相符（`li` 實測 388 對公式 388，子列實測 176.5 對公式 176，其餘同樣吻合） |
| 14 | 每個 ISO 日期被單一 nowrap span 包住；Range 與 span 矩形數都是 1；容器 `white-space` 為 normal | 4 個視窗各 9 個 token，違規 0 項；span 實測 76.234、76.344、76.734px（規範字面寫約 85；N-171A 實測 70.25～78.89）；容器全為 normal；320 寬 `scrollWidth` 320 |
| 15 | 結算區零差異 | 4 個視窗，`outerHTML` 與 baseline 建置逐字相同，相對 rect 差 ≤1，`row-notes` 0 個，無 note 文字 |
| 16 | 4 句堆疊間距 4；上下緣 8／8；無邊框、縮排、`hr`／`ol`／`ul`／`svg`／`img`；樣式與 VP-2 相同 | 帳冊與批次列都相符。**這是 DOM 注入**，真實資料路徑目前只出得了一句 |
| 17 | 缺鍵／null／空字串不渲染；`li` 高度與 baseline 差 ≤1；B 批無子列 | 三種情況 `row-notes` 都是 0 個，`li` 高度與 baseline 相同（375 寬 220 對 220）；整頁空 div 與 baseline 同為 1 個（既有，非新增）；完全無新鍵的舊後端 fixture 渲染成功（6 列帳冊、4 列快照、0 個 `row-notes`） |
| 18 | 對比 ≥7:1；channel ≥210；字級與亮度不低於 `page_summary` | note 對比 13.35，label 對比約 18.2，兩者都達規範值；channel ≥210；字級不小於 `page_summary` |
| 19 | 無彩色（channel 差 ≤3）；背景 alpha 0；無彩色 class 與任意色值；只用 neutral 100／300 | 全部相符；帳冊 note 只用 neutral-300，批次子列用 neutral-100 與 300 |
| 20 | 無互動元素、transition 0s、animation none、transform none；hover 不變；Tab 順序不變 | 相符；Tab 40 次的順序和 baseline 一致（見「與預期不符的觀察」） |
| 21 | 扣除 pin 後 sticky 恰 1 個，pin 只有 `left` | 4 個視窗都是扣除後只剩狀態列 `div.sticky.top-0.z-10`；2 個 pin 都是 top／right／bottom 為 auto，left 為 12px |

### 各寬度行數（VP-168-13 記錄；規範估算不是 pass／fail 條件）
- **帳冊的 N1、N2、N3 行數**

| 視窗 | N1 | N2 | N3 |
|---|---|---|---|
| 320 | 9 | 15 | 17 |
| 375 | 8 | 13 | 14 |
| 768 | 4 | 6 | 6 |
| 1280 | 3 | 4 | 5 |

- **批次列子列行數**：N1 對應的 A 批在 375 寬為 7 行，C 批（W-B2LSf）在 375 寬為 14 行、768 寬為 6 行、1280 寬為 5 行。
- **通報門檻**：375 寬最大 14 行，沒超過 24 行門檻，不需通報。

### 與預期不符的觀察（交 qa-e2e 判讀）
1. **Tab 順序的 class 簽名不同**：375 寬時，Tab 順序按「標籤加文字」比對相同，但 class 簽名多了 `@container`。多出的 class 在部位快照捲動容器上，是 N-168 新增的。同一個元素在 baseline 與新版都是第 10 個 Tab 停點，順序沒變。1280 寬時簽名也相同。
2. **日期 span 寬度**：實測 76 左右，規範寫約 85。N-171A 也有同樣的差異，只是規範字面問題。
3. **子列高度的小數**：子列最後一句到子列底是 12.5px（規範 12），子列整體高度也多 0.5px。4 個視窗一致，在容差內。
4. **VP-168-16 的限制**：目前實作只有 `entry_before_exit_note` 一個來源，N6 的 4 句堆疊只能用 DOM 注入量。注入內容是 `[N6-TEST-1…4 (test fixture)]`，只驗證 CSS 結構（`space-y-1` 在多子元素下成立），不驗證 N-188、N-189 的真實資料路徑。
5. **Chromium 的 Tab 行為**：Tab 會停在 `overflow-x-auto` 的捲動容器上（新舊建置都是）。這是 Chromium 對可捲動容器的預設行為，不是 N-168 新增。

### 截圖路徑
截圖都是 deviceScaleFactor 2，目錄 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n168_out/shots/`。

- **整頁**：`new_full_{320x640,375x812,768x1024,1280x900}_full.png`
- **baseline 對照**：`base_full_*_full.png`
- **nulls 版**：`new_nulls_*_full.png`
- **舊後端版**：`new_old_*_full.png`
- **帳冊列**：`new_full_*_ledger_N1.png`、`_N2.png`、`_N3.png`
- **N6 DOM 注入**：`new_full_*_ledger_N6_injected.png`
- **批次列 scrollLeft 為 0**：`new_full_*_snapshot_scroll0.png`
- **批次列 scrollLeft 為 max**：`new_full_320x640_snapshot_scrollMax.png`、`new_full_375x812_snapshot_scrollMax.png`（768 與 1280 寬 `maxScroll` 為 0，沒有此圖）
- **出清後橫幅**：`{new,base}_banner_{375x812,768x1024,1280x900}_full.png`

## 驗證

### 環境與儀器來源（`provenance`）
- Playwright 1.63.0：`/opt/node-tools/node_modules/playwright/index.js`
- Chromium 153.0.8010.12：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`
- `trustedPrefix` 為 `/opt/`，runner 的前綴斷言沒有觸發，沒有 `e2e-fallback: ABORT`。
- 沒安裝任何東西，也沒改任何產品檔。
- 受測前端：`d1ff816` 的既有 `.next` 建置，`BUILD_ID` 時間晚於原始碼，用 `next start --port 3000`。
- baseline：用 `git archive 2e7c157 apps/stock-desk/frontend` 解到 scratchpad，`node_modules` 用 `cp -al` 建立後 `next build`，`next start --port 3001`。沒有動 `.git` worktree。
- 後端：沒起後端，也沒碰任何 `.db` 與 `.env`。`/today` 與 `POST /emergency-exit` 用 Playwright route 攔截，其他 API 回 404（有記錄）。
- 資料：本次畫面是合成示範資料，底稿是 `e2e_n171_out2/c_with/probe_today.json`，再覆寫 `directives`、`snapshot`、`settlement.settled`。`pending_exit_block` 設為 null，因為不在 N-168 範圍。
- **fixture 說明**：N1～N3 的 note 字串由 worktree 後端 `service.entry_before_exit_note` 實際產生。N4 的 note 是缺鍵／null／空字串各一列。N5 的 A 批是 label 加 W-B2L，B 批是兩者皆 null，C 批是 label 加 W-B2LSf（note 字串取自 N3）。
- **網路與 console**：全部 run 的 console error／warning 與 request failure 都是 0 筆。API 請求只有 `GET /api/playbook/today` 與 `POST /api/playbook/emergency-exit`。
- **repo 狀態**：結束後 `git -C wt_n168fe status --short` 與主工作區 `git status --short` 都是空。
- **清理**：`next start`（:3000、:3001）已停；Chromium 隨 runner 結束；:3000、:3001、:8000 都無回應；無殘留程序。

### 可重跑的指令
scratchpad 前綴為 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad`，下面以 `$S` 代表。

```bash
S=/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad
# 1) 產 fixture（-B 避免在 repo 寫 .pyc）
cd $S/e2e_n168_scripts && PYTHONDONTWRITEBYTECODE=1 /home/user/AICompany/apps/stock-desk/backend/.venv/bin/python -B mkfacts.py
# 2) 起前端（new=:3000 為 d1ff816，base=:3001 為 2e7c157）
$S/e2e_n168_scripts/start_fe.sh new; $S/e2e_n168_scripts/start_fe.sh base
# 3) 量測
V="320x640 375x812 768x1024 1280x900"
cd $S/e2e_n168_scripts
for a in "measure new full" "measure base full" "measure new nulls" "measure new old"; do ./go.sh $a $V; done
for b in new base; do ./go.sh banner $b full 375x812 768x1024 1280x900; ./go.sh tab $b full 375x812 1280x900; done
# 4) 機械比對表（stdout 與 $S/e2e_n168_out/facts_table.md）
node analyze.js
# 5) 收尾
kill -TERM -- -$(cat $S/e2e_n168_scripts/fe_new.pid) -$(cat $S/e2e_n168_scripts/fe_base.pid)
```

腳本在 `$S/e2e_n168_scripts/`：`run.js`、`inpage.js`、`mkfacts.py`、`analyze.js`、`go.sh`、`start_fe.sh`。原始 JSON 在 `$S/e2e_n168_out/facts_*.json`，run 的 stdout 在 `run_all.log` 與 `run_base.log`。run 的 stdout 沒有重排，每份 JSON 的 `provenance` 欄位可驗證前綴。

## 下一步（交 qa-e2e）

### 環境限制與未驗證殘留
1. **WebKit：未驗證殘留。**
   - 風控 A 節要求 375 寬另跑一輪 WebKit，本環境沒有。
   - `/opt/pw-browsers` 只有 chromium、chromium_headless_shell、ffmpeg。
   - Playwright 預期的 `/opt/pw-browsers/webkit-2359` 不存在，全機找不到 WebKit 或 MiniBrowser。
   - 依規則沒有安裝。
   - **這一項由風控判斷是否擋上線**：pin 的寬度依賴 `100cqw` 與 `@container`，WebKit 若不支援，pin 會退回表格寬 640px。這個風險在 Chromium 驗不到。
2. **只有 Chromium 153 一個引擎**，斷行行為可能因引擎而異。
3. **VP-168-16 的 4 句堆疊是 DOM 注入**（見上）。N-188、N-189 欄位上線後需用真實資料重驗。
4. **VP-168-6 與 VP-168-15 的 baseline 是 `2e7c157` 的建置**，不是 N-168 前的另一份獨立紀錄。
5. **未重跑 vitest**（含 SEAM-T8）。VP-168-17 寫的「既有測試維持綠燈」我沒有重驗，只引用前端交件與 qa-reviewer 審查的結果。
6. **N-171 區塊在本次 fixture 為 null**，沒有量它與新版面的交互。
7. **風控 A 節的「容不下」判定、C-3 對 VP-21 口徑修訂的接受與否**，都是 qa-e2e 與風控的事，我沒有判斷。
