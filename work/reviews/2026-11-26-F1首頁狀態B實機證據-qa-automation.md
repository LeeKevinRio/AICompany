# F1 首頁警示狀態列（狀態 B 等六情形）實機證據——qa-automation 代跑

> 以 e2e-fallback 代跑，代跑者：qa-automation。本文件只交事實，不含 Verdict / BLOCKING_ISSUES，判讀交 qa-e2e。
> 畫面資料全部為合成示範資料（`page.route` 攔截 `http://localhost:8000/**`，未起後端、未用真實 DB）。截圖只在 scratchpad，不入 repo。

## 受測版本
- worktree `/home/user/AICompany/.claude/worktrees/agent-ae6916d8ea93b35d9`，分支 `fix/alert-strip-state-b-f1`
- HEAD `e054055f7ce83eeffe1461a40c6b4ca49ce20dea`；跑前與跑後 `git status --short` 皆為空（產品碼未動）
- 前端 `npx next dev --webpack --port 3103`（PID 12708 為 `npm exec`，子程序 12720 / 12721 / 12732）

## 儀器 provenance（stdout 原樣）
- playwrightModule：`/opt/node-tools/node_modules/playwright/index.js`（版本 1.63.0，`require('playwright/package.json')` 於 `NODE_PATH=/opt/node22/lib/node_modules` 下取得）
- chromiumExecutable：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`
- trustedPrefix：`/opt/`（預設值，未覆寫）；runner 開頭 fail-closed 斷言通過，exit=0
- 與 skill 附錄不同：附錄寫 chromium-1194 / playwright 1.56.1 / `chrome-linux/chrome`，本環境實際為 chromium-1243 / 1.63.0 / `chrome-linux64/chrome`。skill 第 2 節的 `ls .../chrome-linux/chrome` 在本環境落空，改以 `find` 找到上述路徑（沿用前例 runner 的同一路徑）。

## Fixture（依 AlertStatusStrip.tsx 優先序構造；見 scratchpad `fixtures.json`）
| 情形 | alerts | events | settings.alerts.enabled |
| --- | --- | --- | --- |
| A | 0 條 | 無 | true |
| B | 4 條（enabled=true） | 無 | true |
| B-allDisabled | 4 條（enabled=false） | 無 | true |
| C | 4 條 | 3 筆未處理 | true |
| D | 4 條 | 無 | false |
| error | `GET /api/alerts` 回 500 `{"detail":"synthetic alerts query failure"}` | 無 | true |

## 選取器與 matchCount（每情形 375 / 1280 相同）
- 文字：`p:has-text("<該態特徵字>")`，特徵字依序為 `尚未設定警示規則`／`4 條規則已設定`／`待處理警示`／`排程目前未啟用`／`無法載入警示狀態`
- 容器：文字元素 `.first` 的 `xpath=ancestor-or-self::*[parent::div[contains(@class,'mt-6')]][1]`（即 `page.tsx` 中 `<div className="mt-6"><AlertStatusStrip/></div>` 的直接子元素）
- matchCount：text=1、container=1 全部情形皆是；descendants（`p, a, button`）A=2、B=1、B-allDisabled=1、C=11、D=2、error=0
- 「查詢時間」：`text=查詢時間` matchCount 與 `document.body.innerText.includes('查詢時間')`、容器 innerText 皆為 0 / false，12 個情形全部相同

## 容器 innerText（逐字，375 與 1280 一致）
- A：`尚未設定警示規則\n\n去設定`
- B：`4 條規則已設定。這裡沒有列出待處理警示，不代表警示檢查已完成。`
- B-allDisabled：`4 條規則已設定。這裡沒有列出待處理警示，不代表警示檢查已完成。`
- C：`3 條待處理警示\n\n管理警示規則\n2330（TW）・價格高於門檻\n2026/11/25 09:30（台北時間）\n\nsynthetic price threshold event\n\n資料日收盤價: 605　設定的門檻: 600　幣別: TWD　資料日期（日線收盤，非即時）: 2026-11-24\n\n標記已處理\n2330（TW）・訊號條件\n2026/11/25 09:30（台北時間）\n\nsynthetic signal condition event\n\n判斷欄位: 14 日 RSI 最新值　該欄位數值: 28.4　比較方式: 小於（<）　比較對象數值: 30　資料日期（日線收盤，非即時）: 2026-11-24\n\n標記已處理\n2330（TW）・風險上限被觸發\n2026/11/25 09:30（台北時間）\n\nsynthetic risk limit event\n\n觸發的上限: 單一標的佔比上限、總曝險上限　觸發的上限數量: 2\n\n標記已處理`
- D：`排程目前未啟用，警示評估暫不會更新\n\n管理警示規則`
- error：`無法載入警示狀態：synthetic alerts query failure`

## 狀態列主文字 computed style 與截斷量測（原值）
欄位：color／fontSize／fontWeight／class／文字元素 scrollWidth÷clientWidth／overflow／textOverflow／whiteSpace。所有情形文字元素 overflow=`visible`、textOverflow=`clip`、whiteSpace=`normal`。

| 情形 | 寬 | 主文字 color | fontSize | fontWeight | 文字元素 sw/cw | 文字元素高 | 容器 sw/cw（寬×高） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 375 | oklch(0.87 0 none) | 14px | 400 | 112/112 | 20 | 341/341（343×46） |
| A | 1280 | oklch(0.87 0 none) | 14px | 400 | 112/112 | 20 | 990/990（992×46） |
| B | 375 | oklch(0.87 0 none) | 14px | 400 | 309/309 | 40 | 341/341（343×66） |
| B | 1280 | oklch(0.87 0 none) | 14px | 400 | 433/433 | 20 | 990/990（992×46） |
| B-allDisabled | 375 | oklch(0.87 0 none) | 14px | 400 | 309/309 | 40 | 341/341（343×66） |
| B-allDisabled | 1280 | oklch(0.87 0 none) | 14px | 400 | 433/433 | 20 | 990/990（992×46） |
| C | 375 | oklch(0.879 0.169 91.605) | 14px | 500 | 97/97 | 20 | 341/341（343×584） |
| C | 1280 | oklch(0.879 0.169 91.605) | 14px | 500 | 97/97 | 20 | 990/990（992×448） |
| D | 375 | oklch(0.87 0 none) | 14px | 400 | 238/238 | 20 | 341/341（343×70） |
| D | 1280 | oklch(0.87 0 none) | 14px | 400 | 238/238 | 20 | 990/990（992×46） |
| error | 375 | oklch(0.808 0.114 19.571) | 14px | 400 | 341/341 | 66 | 341/341（343×66） |
| error | 1280 | oklch(0.808 0.114 19.571) | 14px | 400 | 990/990 | 46 | 990/990（992×46） |

class（原字串）：
- A / B / B-allDisabled / D 主文字 `<p>`：`text-sm text-neutral-300`
- C 主文字：`text-sm font-medium text-amber-300`；C 事件內文 `mt-1 text-neutral-300`（oklch(0.87 0 none) 14px）、事件細節 `mt-1 text-xs text-neutral-500`（oklch(0.556 0 none) 12px）
- error（`<p>` 即容器）：`rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300`
- 連結 `<a>`：`text-xs text-sky-400 underline hover:text-sky-300`，oklch(0.746 0.16 232.661)、12px（A 的「去設定」36/36、C 與 D 的「管理警示規則」72/72）
- 容器 class：A/B/B-allDisabled/D `flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-4 py-3`；C `rounded-lg border border-amber-800/60 bg-amber-950/10 p-4`
- 容器 overflow／overflowX 皆 `visible`；C 的各 `<p>`／`<button>` sw=cw（375：283/283、84/84；1280：932/932、84/84）
- 完整 style（含 borderTopColor、padding、rect）見 scratchpad `raw-output.json`

## 橫向捲動（documentElement／body scrollWidth vs clientWidth）
12 個情形全部：375 寬時 doc 375/375、body 375；1280 寬時 doc 1280/1280、body 1280；innerWidth 與之相同。無橫向捲動。

## Console / requestfailed / network 原始輸出
- requestfailed：12 個情形全為 `[]`。
- console（A、B、B-allDisabled、C、D，兩種寬度皆同）：
  - `[info] %cDownload the React DevTools for a better development experience: https://react.dev/link/react-devtools font-weight:bold`
  - `[log] [HMR] connected`
  - `[error] Failed to load resource: the server responded with a status of 404 (Not Found)`
- console（error 情形，兩種寬度皆同）：上述 info、log 兩行之後依序為 `[error] ...status of 500 (Internal Server Error)`、`[error] ...status of 404 (Not Found)`、`[error] ...status of 500 (Internal Server Error)`、`[error] ...status of 404 (Not Found)`
- 那筆 404 是 `GET http://localhost:8000/api/sectors/momentum?market=TW`（首頁其他元件的請求，我沒有為它做 fixture，攔截器回 `{"detail":"no fixture"}` 404）；與警示狀態列無關，但這筆 console error 是我 fixture 缺漏造成，不是產品行為。
- network（情形 B、375 全文，其餘情形結構相同、僅 `/api/alerts` 回應碼與 error 情形的重試不同）：
  ```
  200 GET http://localhost:3103/
  200 GET http://localhost:3103/_next/static/css/app/layout.css?v=1795703540345
  200 GET http://localhost:3103/_next/static/chunks/webpack.js?v=1795703540345
  200 GET http://localhost:3103/_next/static/chunks/app-pages-internals.js
  200 GET http://localhost:3103/_next/static/chunks/app/layout.js
  200 GET http://localhost:3103/_next/static/chunks/app/page.js
  200 GET http://localhost:3103/_next/static/chunks/main-app.js?v=1795703540345
  200 GET http://localhost:3103/icon.svg?154b911ed2489a14
  200 GET http://localhost:8000/health
  200 GET http://localhost:8000/api/portfolio/limits
  200 GET http://localhost:8000/api/alerts
  200 GET http://localhost:8000/api/alerts/events?unacknowledged=true
  200 GET http://localhost:8000/api/settings
  404 GET http://localhost:8000/api/sectors/momentum?market=TW
  200 GET http://localhost:8000/api/portfolio/summary
  ```
  error 情形：`GET /api/alerts` 回 500 兩次（有一次重試），`/api/sectors/momentum` 404 兩次，共 17 筆。各情形完整清單在 `raw-output.json`。

## 截圖（僅 scratchpad，24 張）
目錄 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-f1/shots/`，檔名 `<寬>-<情形>-strip.png`（狀態列區塊）與 `<寬>-<情形>-fullpage.png`；情形名為 A、B、B-allDisabled、C、D、error，寬為 375、1280。

## 腳本相對前例 runner 的改動（誠實列出）
複製自 `scratchpad/e2e-alertlabels/runner.js`（原目錄未動），改動如下：
1. 刪除 `runCase1`（設定頁）與 `runCase2`（首頁事件列），改為單一 `runCase(page, name, C, tag)`，只量首頁警示狀態列。
2. `installRoutes` 改為依 `fixtures.json` 的每情形 `alerts` / `events` / `settings` 回應；`alerts===null` 時 `/api/alerts` 回 500；新增 `/api/portfolio/summary`、`/limits` 用共用 fixture。fixture 由我用一次性 python 腳本從舊 `fixtures.json` 衍生（settings 的 `alerts.enabled` 改值，rules 為合成 `price_above` 規則）。
3. `STYLE_KEYS` 改為 color、fontSize、fontWeight、lineHeight、display、overflow、overflowX、textOverflow、whiteSpace、backgroundColor、borderTopColor、paddingTop、paddingLeft；`styleOf` 另回傳 class、tag、scrollWidth/clientWidth、scrollHeight/clientHeight、bounding rect。
4. `hscroll` 欄位改名（docScrollWidth 等）並加 innerWidth。
5. 新增「查詢時間」檢查（`text=查詢時間` count、body innerText includes、容器 includes）。
6. 沿用：fail-closed 斷言、每寬度獨立 context、deviceScaleFactor 1、collector（console 全型別、requestfailed、全部 response）。
7. 輸出目錄改為 `.../scratchpad/e2e-f1/`。
- 腳本原文：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-f1/runner.js`；未改寫 stdout：同目錄 `stdout.txt`（與 `raw-output.json` 相同內容）；`stderr.txt` 為空。
- 指令：`cd <e2e-f1> && PW_CHROME=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome OUT_DIR=<e2e-f1> BASE_URL=http://localhost:3103 NODE_PATH=$(npm root -g) node <e2e-f1>/runner.js`

## dev server 收尾
- 以 `kill 12732 12721 12720 12708`（皆為我自己啟動之 PID 與其子程序，先用 `pgrep -P` / `ps` 確認 PID 歸屬）停止，未用 `pkill`，未被拒。
- 之後 `ps` 無殘留 next 程序，`curl http://localhost:3103/` 連線失敗（code 000）。已確認 server 停掉。

## 偏離與未查證事項
- 偏離：skill 第 2 節的 `ls .../chrome-linux/chrome` 找不到（本環境目錄為 `chrome-linux64`），改用 `find`；附錄版本與實際不符（見上）。
- 偏離：dev server 啟動後，worktree 內被 gitignore 的 `apps/stock-desk/frontend/.next` 已存在且會被 `next dev` 寫入；`git status --short` 前後皆空，但 `.next` 內容有變動（被忽略目錄，非產品碼）。
- 偏離：fixture 的 `GET /api/sectors/momentum` 未提供，造成每個情形多一筆 404 console error，與受測元件無關。
- 狀態 C 的 3 筆事件沿用前例的合成事件（含 `risk_limit_breach` 等），不是依狀態列規格另行挑選。
- 未查證：未驗證 `hover` 態；未驗證 375 與 1280 以外的寬度；未驗證真實後端回應；未做 `ackMutation`（標記已處理）互動；未查證 skill 所稱「既定前綴」是否仍是 `/opt/`（devops-sre 的環境定義，我未讀）；error 情形只模擬 `/api/alerts` 失敗，未模擬 `/api/alerts/events` 或 settings 失敗。
- 未在 error 情形於 `networkidle` 之外額外等待重試時序；text 出現後才量測。
