# 第十九輪：erosion 表（L-16）／D-1 fresh 標籤折字／RangeGauge（D-3）——實機驗收紀錄（e2e-fallback 代跑）

- 日期：2026-10-06（落檔日）。取證時間 2026-10-06T13:54:58Z～14:06:13Z（UTC，見 `start-time.txt`、`git-state-*.txt`）。
- 受測 commit：`product/stock-desk` 的 `1b1531b9ea340b97de7b8911e35cbd7aa6c6a0ae`。開跑前後 HEAD 相同。
- 代跑者：qa-automation。判定者：qa-e2e（唯讀，只用 Read／Glob／Grep；由主會話代為落檔）。art-lead 最終驗收見附錄。
- 證據位置（scratchpad，不在 repo 內）：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-19/`
  - 文字與原始輸出：`evidence-report.md`、`derived-summary.txt`（657 行，逐 run）、`aggregate-counts.txt`、`runner-stdout-{A,A2,B,B2,C}.json`、`process-env-proof.txt`、`probe-overflow-output.json`、`git-state-before.txt`／`-after.txt`、`git-diff-stat-app.txt`／`-app-after.txt`／`-control.txt`／`-control-after.txt`、`stat-data-before.txt`／`-after.txt`、`frontend-build.log`、`backend-*.log`。
  - 截圖：全部來自 `next build --webpack`＋`next start --port 3000`，沒有任何一張來自 dev。
- 資料與啟動方式：
  - 全部是合成示範資料（API `data.source`＝`demo_synthetic`，`data.status`＝`cached_stale`）。複本 DB 在 `scratchpad/db19/`（由 `db18/` 複製）。
  - 後端：`uvicorn app.main:app --port 8000`（無 reload），三個 `STOCK_DESK_*_DB_PATH` 指向複本。狀態切換 A（2330 hold）→ C（2330 stop_loss）→ B（00675L）→ B2（同 B 後端）→ A2（再回 A），以 `restart-backend.sh` 重啟後端，前端不重啟（next-server pid 5665 全程）。
  - 啟動前設死埠 proxy `http://127.0.0.1:9`，`NO_PROXY=127.0.0.1,localhost`；瀏覽器端以 `ctx.route` 攔截並 abort 所有非 loopback 請求。
  - 儀器：playwright 與 chromium 都在 `/opt/` 前綴下（runner 有 fail-closed 前綴斷言）；5 個 `runner-rc-*.txt` 皆 `rc=0`，`runner-stderr-*.txt` 皆空。
  - 共 44 個 run（A 22、A2 10、B 6、B2 3、C 3），寬度 1280／390／375。

## Verdict

**整體：PASS 附一項新增 required 缺陷（D-10，既有行為，非本輪回歸）。`BLOCKING_ISSUES=false`。**

- **第十八輪兩項 blocking 改判 false：**
  - L-16 erosion 表：真實資料 390／375／1280 全數達標，**L-16 的版面驗收條件達成**。
  - D-2（上一輪紀錄編號；本輪 art-lead 清單稱 D-1）fresh 折字：1280／390／375 標籤單行、375 reason 寬 275 ≥ 250，**達標；L-10i 版面條件隨之結案**。
- **PASS 的項目：** erosion 表（真實）、D-1／D-2 徽章列、RangeGauge 真實位階（hold 71%、stop_loss 38%）版面、PriceLadder 回歸、Gap 表回歸、全頁通用檢查。
- **新增缺陷：**
  - **D-10（required）**：RangeGauge 位階 100% 時游標標籤右緣超出視窗 3.02px，造成頁面層級水平溢出（docScrollWidth 393／378）。這是 44 個 run 中唯一的整頁水平溢出，A 與 A2 兩次重現。既有行為，非本輪改動引入。
  - 另有觀察項 O-1、O-2、O-3，交 art-lead／風控裁量（見列管表）。
- **為何 D-10 是 required 但本輪 `BLOCKING_ISSUES=false`：**
  - 為何是 required：(1) 整頁水平溢出，「頁面 `scrollWidth == innerWidth`」是每輪都驗的通用條件；(2) 標籤末字（%）有 3px 落在視窗外，`GHIGH100-2330-390-gauge-card-0-fullwidth.png` 可見被截；(3) 100% 位階在真實資料可達（收盤創 252 根區間新高，趨勢股常見；此為主會話陳述，未用真實資料驗證）；(4) 溢出量與視窗寬度無關（標籤右緣＝figure 右緣＋約 49px），360／375／390 都會超出約 3px。
  - 為何本輪不擋：(1) 核心資訊重複呈現且可讀（卡片右上「區間上緣 100%」完整在畫面內，aria-label 也有），被截的只是游標標籤末字；(2) 沒有元件被遮擋到點不到、沒有資料看不到；(3) 不在 art-lead 第十八輪對 RangeGauge 的驗收條件內，上一輪沒量過極端位階，不是「這次改壞」；(4) 與第十八輪 erosion 表「數值整欄看不到」性質不同。
  - 判準與可改判條件：若 CEO／art-lead 認為「頁面層級水平溢出」本身即屬紅線，改判 true 只影響 D-10，不推翻本輪其他 PASS。D-10 應在第四批整批 PASS 前修掉，修法很小。

## 逐項判定

| # | 項目 | 判定 | 依據 |
|---|---|---|---|
| 1 | erosion 表（L-16 required）真實資料 390／375／1280 | **PASS；L-16 版面條件達成** | 見 1 |
| 1b | erosion 壓力版 LEVSTRESS（合成） | **觀察 O-1，待 art-lead 裁量；不判缺陷** | 見 1 |
| 1c | 情境格第二行 12px | **觀察 O-2，交 art-lead／風控（qa N4）** | 見 1 |
| 2 | D-1 fresh 標籤折字（required） | **PASS；L-10i 版面條件隨此結案** | 見 2 |
| 3 | RangeGauge 真實位階（D-3） | **PASS** | 見 3 |
| 3b | RangeGauge 極端位階（合成） | **新缺陷 D-10（required），非回歸** | 見 3 |
| 4 | PriceLadder、Gap 表回歸 | **PASS** | 見 4 |
| 5 | 通用 | **PASS（404 第五度已知）** | 見 5 |
| 6 | 流程揭露 | 要件達成，附一項如實揭露 | 見「流程揭露」 |

### 1. erosion 表（00675L，state B）——PASS（L-16 達成）

容器 `div.mt-2.overflow-x-auto.rounded-md.border`；table class `w-full text-left text-sm sm:w-auto sm:min-w-[480px]`；四欄：情境／波動侵蝕／費用侵蝕／合計侵蝕；初始 scrollLeft＝0。

| run | 寬 | 容器 scrollW／clientW | 四欄表頭 right ≤ 容器 right | 8 個 td right ≤ 容器 right | 表頭單行 | 資料列最大行數 | 情境格第二行 | docScrollWidth |
|---|---|---|---|---|---|---|---|---|
| LEV（真實） | 390 | 314／314 | 是（138.72／209.8／280.88／352；容器 right 353） | 是 | 是 | 2 | 12px（`（21 交易日）`，letter-spacing −0.3px） | 390 |
| LEV（真實） | 375 | 299／299 | 是（133.91／201.59／269.28／337；容器 right 338） | 是 | 是 | 2 | 12px | 375 |
| LEV（真實） | 1280 | 948／948 | 是（table 寬 480） | 是 | 是 | 1 | 14px（inline） | 1280 |
| LEVSTRESS（合成，英文長情境名＋三值 −100.00%） | 390 | **623／314** | 否 | 否 | 是 | 2 | 12px | 390 |
| LEVSTRESS | 375 | **623／299** | 否 | 否 | 是 | 2 | 12px | 375 |
| LEVSTRESS | 1280 | 948／948 | 是（table 782） | 是 | 是 | 1 | 14px | 1280 |
| LEVSTRESSCJK（合成，中文長名＋−100.00%） | 390 | 314／314 | 是 | 是 | 是 | **5** | 12px | 390 |
| LEVSTRESSCJK | 375 | 299／299 | 是 | 是 | 是 | **5** | 12px | 375 |
| LEVSTRESSCJK | 1280 | 948／948 | 是 | 是 | 是 | 1 | 14px | 1280 |

- **真實資料判定 PASS。**art-lead 第十八輪驗收清單逐條：容器 `scrollWidth == clientWidth`（皆是）、四欄表頭與數值 right ≤ 容器 right（皆是）、表頭單行（皆是）、資料列 ≤ 2 行（390／375 為 2、1280 為 1）、頁面 `scrollWidth == innerWidth`（皆是）。375 無任何數值欄被擠破、表頭無逐字折行，「B 轉置後備」條件未觸發。真實逐字：情境 `1_month`／`（21 交易日）`、`1_year`／`（252 交易日）`；數值 `-0.28%`／`-0.10%`／`-0.38%`、`-3.30%`／`-1.19%`／`-4.45%`，單行靠右。
- 目視 `LEV-00675L-390-erosion-table-initial.png`、`-375-`：四欄表頭與 8 個數值完整在畫面內，無橫向捲動。與第十八輪同圖相比，「費用侵蝕」「合計侵蝕」由完全看不到變為完整可見。
- **LEVSTRESS：觀察 O-1，不列缺陷。**後端情境名是寫死常數（`leverage/erosion.py` L47–L48 只有 `("1_month", 21)`、`("1_year", TRADING_DAYS_PER_YEAR)`，`test_leverage_erosion.py` L80 斷言 labels），壓力版 62 字元無斷行點字串非後端真值；壓力版溢出為容器內橫向捲動非整頁；CJK 版不捲動但 4～5 行；1280 皆不溢出。可選防呆：情境名 span 加 `break-words`。art-lead 裁示：不算缺陷（見附錄）。
- **O-2 情境格第二行 12px**：`（21 交易日）` 12px、`letter-spacing −0.3px`、display block（1280 為 14px inline）。art-lead 裁定可（見附錄）；風控 qa N4 待確認。

### 2. D-1 fresh＋reason 標籤折字（required）——PASS；L-10i 版面條件結案

| run | 寬 | 日線標籤 lines | 指標標籤 lines | 日線／指標 reason 寬／行數 | 決策列 reason 寬／行數 | 徽章列元素兩兩重疊（技術列／細項／決策列） | docScrollWidth |
|---|---|---|---|---|---|---|---|
| BFRESH | 1280 | 1（span 24×16） | 1 | 858.67／1 | 858.67／1 | 0／0／0 | 1280 |
| BFRESH | 390 | **1** | **1** | **290**／4 | 318／3 | 0／0／0 | 390 |
| BFRESH | 375 | **1** | **1** | **275**／4 | 303／4 | 0／0／0 | 375 |
| BREAL（真實 `cached_stale`） | 390 | 1 | 1 | 無 reason | 無 | 0／0／0 | 390 |
| BBACKUP（合成） | 390 | 1 | 1 | 無（compact 只畫 chip） | 無 | 0／0／0 | 390 |
| BUNAV（合成） | 390 | 1 | 1 | 無 | 無 | 0／0／0 | 390 |

- **PASS。**標籤單行、reason 無橫向溢出、徽章列不重疊、頁面無水平溢出、**375 reason 寬 275 ≥ 250**。BREAL／BBACKUP／BUNAV 390 回歸正常。
- **L-10i 版面條件結案**：375／390 重拍、44 run dev overlay 0、兩顆標籤可目視不折字。
- 目視 `BFRESH-2330-{375,390}-badge-row-tech-title.png`：「日線」「指標」各自單行位於 reason 左側；reason 在右側多行折行每行完整。與第十八輪逐字直排比，缺陷消失。
- **校正**：`evidence-report.md` §3 寫「label 在 reason 之上、上下兩列」；核對 `derived-summary.txt` L249–L251（label span left 33／right 57，所在列 top 774 height 80，label top 806＝列中央，reason 寬 290）加截圖，實際是**左右並排**、label 與 reason 區塊垂直置中。art-lead 目視亦同（見附錄）。附帶觀察：reason 4 行時標籤垂直置中可能偏離第一行，是否改頂端對齊由 art-lead 決定（art-lead：nit，改 `items-start`，已交 frontend）。
- **三種 chip computed 色與對比（如實記錄）**：

| chip | computed color | 疊合後背景（sRGB） | 前景 sRGB | 對比（WCAG） |
|---|---|---|---|---|
| `備援源`（`bg-amber-900/40 text-amber-300`） | `oklch(0.879 0.169 91.605)` | `rgb(55, 26, 8)` | `rgb(255, 210, 48)` | 11.05 |
| `資料不足`（`bg-neutral-800 text-neutral-400`） | `oklch(0.708 0 none)` | `rgb(38, 38, 38)` | `rgb(161, 161, 161)` | 5.86 |
| `快取資料`（同上） | `oklch(0.708 0 none)` | `rgb(38, 38, 38)` | `rgb(161, 161, 161)` | 5.86 |

  12px 小字，三者皆高於 4.5:1。視覺權重倒掛（灰色資料不足比琥珀備援源更不顯眼）為第十八輪 D-8 延續，art-lead 給色值建議（見附錄），語意歸屬待風控。

### 3. RangeGauge（D-3）——真實位階 PASS；極端位階新缺陷 D-10（required）

**3a 真實位階——PASS**

| run | 寬 | 行數 range／低／高／游標 | range↔低 | range↔高 | 低↔高 | 左右 span 高度 | 對稱 | figure／figcaption scrollW／clientW | 重疊 |
|---|---|---|---|---|---|---|---|---|---|
| LAD（hold 71%） | 390 | 1／1／1／1 | 8 | 8 | 60.58 | 21／21 | 是 | 298／298 | 0 |
| LAD | 375 | 1／1／1／1 | 8 | 8 | 45.58 | 21／21 | 是 | 283／283 | 0 |
| LAD | 1280 | 1／1／1／1 | 303.72 | 303.72 | 694.58 | 21／21 | 是 | 932／932 | 0 |
| STOP（stop_loss 38%） | 390 | 1／1／1／1 | 8 | 8 | 77.38 | 21／21 | 是 | 298／298 | 0 |
| STOP | 375 | 1／1／1／1 | 8 | 8 | 62.38 | 21／21 | 是 | 283／283 | 0 |
| STOP | 1280 | 1／1／1／1 | 312.11 | 312.11 | 711.36 | 21／21 | 是 | 932／932 | 0 |

- **PASS。**兩側對稱、相鄰間距 ≥ 8px（range 列與低／高列垂直 8px；低↔高水平 45.58～77.38）、無折行、hold 與 stop_loss 都驗、游標標籤不重疊、figcaption 無裁切。結構（390／375）：figcaption `mt-1 flex flex-wrap justify-between gap-x-3 gap-y-1 text-sm text-neutral-400`；「近 252 根區間」在 `order-first basis-full text-center sm:order-none sm:basis-auto` div（span 寬 87.14）；其下「區間最低 705.36」（110.31）與「區間最高 1,004.44」（127.11）。1280 三者同列。與第十八輪「0px 黏連、區間最低折兩行」比，缺陷消失。

**3b 極端位階（合成：改寫 `/api/bars/2330` 最後一根收盤）——新缺陷 D-10（required）**

| run | 寬 | 位階 | 游標標籤寬 | 距 figure 左／右 | 距視窗 左／右 | figure scrollW／clientW | docScrollWidth |
|---|---|---|---|---|---|---|---|
| GLOW | 390／375／1280 | 2% | 81.22 | −34.66／251.44；−34.95／236.73；−21.98／872.77 | 11.34／297.44；11.05／282.73；152.02／1046.77 | 298／298；283／283；932／932 | 390／375／1280 |
| GLOW0 | 390／375／1280 | 0% | 81.22 | −40.61／257.39；−40.61／242.39；−40.61／891.39 | 5.39／303.39；5.39／288.39；133.39／1065.39 | 298／298；283／283；932／932 | 390／375／1280 |
| GHIGH | 390／375／1280 | 98% | 89.63 | 247.22／−38.84；232.52／−39.14；868.55／−26.17 | 293.22／7.16；278.52／6.86；1042.55／147.83 | **337**／298；**322**／283；**958**／932 | 390／375／1280 |
| GHIGH100 | 390 | 100% | 98.03 | 248.98／**−49.02** | 294.98／**−3.02** | **347**／298 | **393** |
| GHIGH100 | 375 | 100% | 98.03 | 233.98／**−49.02** | 279.98／**−3.02** | **332**／283 | **378** |
| GHIGH100 | 1280 | 100% | 98.03 | 882.98／−49.02 | 1056.98／124.98 | **981**／932 | 1280 |

- 游標標籤為 `absolute -translate-x-1/2 whitespace-nowrap`，`left` 以 0～100% 夾在軌道內；標籤寬約 81～98px，兩端會超出 figure；figure 與祖先 `overflow` 皆 visible。`RangeGauge.tsx` L61 註解「clamped by translate so it never overflows」與實際不符，修正時一併更正。
- **100%（390／375）：標籤右緣超出視窗 3.02px，造成頁面水平溢出**（`probe-overflow-output.json` 唯一 `rect.right > innerWidth` 元素即此標籤 right＝393.02）；A 與 A2 重現；1280 無溢出。**0%**：標籤左緣距視窗 5.39px，但跨出位階卡左框約 27.6px（`GLOW0-2330-390-gauge-card-0-fullwidth.png`）。**98%**：figure scrollWidth > clientWidth。溢出量與視窗寬無關；99% 不超出，只有顯示 100% 才會。
- 目視 `GHIGH100-2330-390-gauge-card-0-fullwidth.png`：「收盤位於 100%」右緣貼齊視窗、「%」被截；卡片右上「區間上緣 100%」完整。
- **D-10 required**；修法（art-lead 規範，見附錄）：`left: clamp(46px, <pct>%, calc(100% - 46px))` 加 `-translate-x-1/2`，thumb 照真實 pct，只夾文字標籤；驗收 0／2／98／100% × 390／375／1280 標籤全在 figure 內、docScrollWidth == innerWidth。0% 跨框與 98% figure 溢出同根因，一併驗。

### 4. PriceLadder、Gap 表回歸——PASS

- PriceLadder（390）：`LAD` hold 容器 298／298、無橫向捲動、chip 重疊 0、無截斷；9 列 label／chip／行數／rowRect／td 文字與 rect **與第十八輪逐列完全相同**（腳本比對 True）；1280 亦同（932／932）。`BANDT2R`（合成 avg_cost 852.5）298／298、`2R` 列 label＋3 chip（5 行、列高 111），與第十八輪相同。D-7（label 窄欄折多行、chip 孤字）本輪未改，仍為觀察。
- Gap 表：390 容器 316／316、8 列單行靠右 `tabular-nums nowrap`、right 353；1280 容器 950／950、table 480、td right 645。與第十八輪逐格相同（390 僅整體 y 下移 24px，因上方 erosion 版面改變）。375 另有一份。

### 5. 通用——PASS

- 44 run：`pageerror` 0、`requestfailed` 0、`externalRequests` 0、dev overlay 0；禁字合計 0。console error 44 筆＝每 run 一筆 `404 /api/directory/resolve/<sym>`，**第五度**已知（D-6）。`documentElement.scrollWidth <= innerWidth` 44 run 中只有 `GHIGH100` 390／375 違規（A 與 A2 共 8 筆，即 D-10），其餘 42 run 含所有真實資料 run 無違規。後端日誌皆 `Connection refused`，`403|Forbidden|CONNECT` 0。

## 缺陷與列管（D-n）

| 編號 | 等級 | 內容 | 交辦對象 |
|---|---|---|---|
| D-1（第十八輪 erosion 表 required） | **已結案** | 390／375／1280 真實資料達標。**L-16 版面條件達成**，風控 L-16 可據此結案。 | 風控 L-16 結案確認 |
| D-2（第十八輪 fresh 折字 required） | **已結案** | 1280／390／375 標籤單行、375 reason 275 ≥ 250、重疊 0、無溢出。**L-10i 版面條件隨此結案**。 | — |
| D-3（RangeGauge 黏連） | **已結案（真實位階）** | 單行、對稱、間距 8px、無裁切。極端位階另立 D-10。 | — |
| **D-10（新增）** | **required**（既有行為，非回歸；本輪不擋；art-lead 判 P1 major） | 位階 100% 游標標籤右緣超出視窗 3.02px 致整頁水平溢出、末字被截；0% 跨出卡左框、98% figure 溢出同根因。`RangeGauge.tsx` L61 註解與行為不符一併更正。修法：`left: clamp(46px, <pct>%, calc(100% - 46px))`。驗收：0／2／98／100% × 390／375／1280 標籤全在 figure 內、docScrollWidth == innerWidth；art-lead 只需複看 `GHIGH100`、`GLOW0` 全寬圖。 | frontend-engineer（已派）；art-lead 把關；release 前須完成 |
| O-1 | 觀察（不擋；art-lead：不算缺陷） | erosion 壓力版英文長情境名容器內橫向捲動；CJK 長名 4～5 行。真實情境名為寫死常數。日後情境名動態化時才加 `break-words`。 | art-lead |
| O-2 | 觀察 → **art-lead 裁定可**（12px 為下限、不得再低、字距維持 −0.3px）；風控 qa N4 待確認 | 390／375 情境格第二行 12px −0.3px。 | 風控 |
| O-3（承 D-8） | suggested | chip 對比：備援源 11.05、資料不足 5.86、快取資料 5.86；視覺權重倒掛。art-lead 建議「資料不足」改 `text-neutral-200`＋`border-neutral-500`，不用紅色（台股紅漲）；語意歸屬待風控。 | 風控、art-lead |
| D-4 | suggested（流程） | e2e-fallback 補通則。**本輪 44 run 全程依此執行。** | coordinator → tech-architect／devops-sre |
| D-5 | 既知 | 「未選取圖表 tab」待旗標開啟補驗。 | art-lead、qa-e2e |
| D-6 | 既知，不擋 | `/api/directory/resolve` 404 **第五度**；dev-lead 已派改 200＋`found:false`。 | dev-lead |
| D-7 | 觀察 | 390 PriceLadder label 窄欄折多行、chip 孤字（art-lead 建議 chip `whitespace-nowrap`，選修）。 | art-lead／frontend |
| D-9 | suggested（內容層） | 「日線」「指標」reason 逐字相同可合併一行（標籤改「日線／指標」），可省約 100px。 | creative-lead、frontend |
| D-11（新，art-lead nit） | suggested | D-1 標籤相對 reason 垂直置中改頂端／基線對齊（`items-start`）。已派 frontend 順手。 | frontend-engineer |

## 流程揭露

1. **HEAD 鎖定：達成。**前後皆 `1b1531b…`（13:54:58Z／14:06:13Z），`git status --short` 前後皆空；app 目錄 diff 0 位元組（兩檔確為空）；對照組 `9aa969a..1b1531b` 非空（3 files, 19+/16−）前後相同；`next build --webpack`（rc=0）＋`next start`。
2. **正式 DB 只 `stat`：達成。**兩檔大小與 mtime 前後逐字相同；未讀取、未開啟、未讀 `.env`。
3. **不對外網路：達成。**`process-env-proof.txt` 5 段 backend 與 next-server 皆死埠變數＋NO_PROXY（backend pid 5664／6724／7005／7005／8863，next-server 5665）；44 run `externalRequests` 0；收尾無殘留。
4. **如實揭露（日誌被覆寫）**：第一次 A 的 `backend-A.log` 在 A2 重啟時被同名覆寫，僅留最後一段；第一次 A 的環境證明仍在（pid 5664）。影響限於該段 Connection refused 次數無法複核。
5. **合成情境一覽**：`GLOW`／`GHIGH`／`GLOW0`／`GHIGH100`（改寫 `/api/bars` 最後收盤）、`LEVSTRESS`／`LEVSTRESSCJK`（改寫 `/api/leverage`）、`BANDT2R`（改寫 `/api/positions`）、`BFRESH`／`BBACKUP`／`BUNAV`（改寫 `data.status`／`reason`；BBACKUP／BUNAV reason 為示意句）。真實後端僅 `cached_stale`。
6. runner 相對第十八輪改動：三個量測器重寫、新增兩種改寫、`CARD_SHOT=1` 多存全寬圖；皆在 scratchpad。

## 自我揭露（qa-e2e）

- 只用 Read／Glob／Grep，未啟動 app、未執行 git／vitest／Bash、未改任何檔案。讀過 `evidence-report.md` 全文、`aggregate-counts.txt`、`process-env-proof.txt` 全文、`git-state-*`、`git-diff-stat-*`、`stat-data-*`、`probe-overflow-output.json`、`runner-rc-*`；`derived-summary.txt` L1–157、L164–175、L241–252，其餘 grep；第十八輪紀錄全文；`erosion.py` 情境常數與測試、`RangeGauge.tsx` L40–115（說明 D-10 根因）。未讀 `runner-stdout-*.json` 原始檔、`backend-*.log`、`frontend-*.log`。chip 對比值為 runner 計算未獨立重算；「100% 真實可達」為主會話陳述未驗證。
- 目視 11 張：`GHIGH100-2330-390-gauge-card-0-fullwidth.png`、`GLOW0-2330-390-gauge-card-0-fullwidth.png`、`LEV-00675L-{390,375}-erosion-table-initial.png`、`LEVSTRESS-00675L-390-erosion-table-initial.png`、`BFRESH-2330-{390,375}-badge-row-tech-title.png`、`BBACKUP-`／`BUNAV-2330-390-badge-row-tech-title.png`、`STOP-2330-375-gauge-0.png`、`LEV-00675L-390-gap-table.png`。未目視所有 1280、`LAD`／`GLOW`／`GHIGH` gauge、`BREAL`、ladder、`LEVSTRESSCJK`、全頁圖。

BLOCKING_ISSUES=false（範圔：L-16 與 D-2 改判 false；新增 D-10 為 required、非回歸、第四批整批 PASS 前修；若 CEO／art-lead 將頁面層級水平溢出視為紅線，D-10 可改判 true，僅影響 D-10）

---

## 附錄：art-lead 第十九輪最終驗收（2026-10-06，coordinator 轉錄）

**總結論：第四批整批 PASS。**第十八輪退件三項（RangeGauge 排版、erosion 表、D-1）全部修正通過。既有問題 RangeGauge 游標標籤極端位階跨框致頁面水平溢出列 **P1 follow-up（major）**，不重開第四批，但上線前須修。**L-16 三表（Gap、erosion、PriceLadder）美術面結案。**

1. **RangeGauge 真實位階 PASS**（逐張看 LAD、STOP 390／375／1280 gauge 與卡片全寬圖；range 標籤 390／375 自成一列置中、1280 同列；垂直 8px；兩側 21／21 對稱；低↔高 45.58～77.38px；2%／98% 在視窗內）。**極端位階：要求 clamp，P1 major 非 blocker。**100%（創 252 日新高）為真實常見情境，不接受「既有行為」永久豁免；造成頁面水平溢出違反 L-16「無頁面水平溢出」原則；不重開本批因非本輪引入。clamp 規範：標籤保持 `absolute`，`left: clamp(46px, <pct>%, calc(100% - 46px))` 加 `-translate-x-1/2`（46px＝最寬約 90px 之半加 1px）；thumb 仍照真實 pct；驗收 0%／100% 在 390／375 標籤完整在 figure 內、`docScrollWidth == innerWidth`；98% figure 溢出同一 clamp 消除。
2. **erosion 表真實資料 PASS**（390／375 四欄全在容器內、表頭單行、資料列 2 行、無橫向捲動、數值靠右；1280 右對齊等寬數字與 Gap 表一致）。**12px 前提型文字（qa N4）：裁定可**——`（21 交易日）` 屬輔助註記非獨立決策數字，12px 為下限；`text-xs tracking-tight` 390 清晰不糊；限制：不得再低於 12px、負字距維持 −0.3px；同意 text-sm 會折 3 行的取捨。**壓力版不算缺陷**：LEVSTRESS 為容器內捲動（`overflow-x-auto` 設計預期退路）、頁面不溢出；CJK 版折 4～5 行無疊字；真實情境名只有 `1_month`／`1_year`；日後情境名動態化才加 `break-words`。
3. **D-1 徽章列 PASS**。目視 `BFRESH-*-badge-row-tech-title.png`：390／375 下標籤與 reason 為**同一水平列**（標籤左、reason 右），非報告所述上下兩列（標籤 left 33 與 reason left 67 之差即標籤寬加間距）；符合「標籤 shrink-0 nowrap＋reason 吃剩餘寬」預期；未加 `min-w-0 flex-1` 可接受。nit：標籤相對 reason 垂直置中改頂端／基線對齊（`items-start`／`items-baseline`），下輪順手修。
4. **chip 對比**：備援源 11.05（AAA）；資料不足／快取資料 5.86（12px 通過 AA）。問題在辨識度：兩者外觀完全相同而語意輕重不同。色值建議（語意歸屬由風控定）：「資料不足」改 `text-neutral-200`（#e5e5e5）、底色維持 neutral-800（對比約 12.0），加 1px `border-neutral-500`（#737373）作形狀線索；「快取資料」維持；**不建議紅色**（台股紅漲會與漲跌語意衝突）。辨識度優化，不阻擋。
5. PriceLadder、Gap 表回歸與第十八輪逐項一致，PASS。
6. **第二十輪不必須。**併入下個 chore 小單：(1) RangeGauge 游標標籤 clamp（P1，release 前）——驗收 0%／2%／98%／100% × 390／375 標籤完整在 figure 內、無頁面水平溢出，複拍 `GHIGH100`、`GLOW0` 全寬圖；(2)「資料不足」chip 加重（待風控認可語意）、D-1 標籤改頂端對齊（nit）。修完後 art-lead 只看兩張全寬圖。

coordinator 處置（2026-10-06）：(1) clamp 與 D-1 對齊 nit 已派 frontend-engineer（D-10、D-11）；(2)「資料不足」chip 語意與色值交風控與 art-lead 共同確認（O-3）；(3) 第四批整批 PASS、L-16 美術面結案；風控 L-16 與 L-10i 結案轉錄見 `2026-10-04-規則集-1.2.0-前置-風控預審.md`、`2026-10-04-個股頁-資料時間標籤-風控審查.md`。
