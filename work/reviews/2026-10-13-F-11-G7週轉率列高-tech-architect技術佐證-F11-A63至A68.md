# F-11 G7「週轉率」列高技術佐證（F11-A-63～A-68）— tech-architect

> 轉存：coordinator，2026-10-13，子 agent 回報逐字轉存。
> 裁示權在 risk-compliance-officer（W-29(a) 風控門檻）。

---

# F-11 G7「週轉率」36.5 → 37 技術佐證（tech-architect，F11-A-63～A-68）

## 一、本次結論

- **(1) 差異可以完全解釋，而且沒有殘差。**
  - 原因是 border-collapse 下，邊框以格線為中心、上下各分一半。基準時週轉率是 tbody 最後一列，下方沒有邊框可分，所以是 36.5；F-11 後它成為中間列，所以是 37。
  - 換算成內容高，兩次都是 **36**（`py-2` 8＋8，加 1 行 20），內容高完全相同。
  - 除了 qa-e2e 的推論之外，我在 raw JSON 找到兩項**幾何上的直接證據**：
    - 定義列 `td` 的內距是 0，裡面的區塊跟 `tr` 上下各差 0.5，最後一列則上差 0.5、下差 0。
    - 表頭 `th` 高 36.5，跟最後一列對稱。
- **(2) 其他可能原因都可以排除，證據足夠。** 我檢查了折行、文字、字型與行高、`table-layout` 改動、次像素或縮放、harness、外層容器邊框，逐項說明在後面。
- **(3) 建議風控把 G7 改成「去除邊框分攤後的內容高 ≤ 基準內容高，容差 0」。**
  - 依現有資料，週轉率的換算結果等於「中間列上限 37」。
  - 這樣不放寬任何實質保護：多 1 行是 +20，一定會被擋下；內容高的容差仍是 0。
- **(4) 不需要補量測就能裁示。** 如果風控要求直接讀到 `borderCollapse`，確切量測方式列在後面，量完只記錄，不改判定。
- **我的疏漏要說清楚。** F11-A-58 是我把基準的 36.5 原樣抄成上限，沒有辨識出這是最後一列的邊框效應。W-12(b) 規定在週轉率之後插入新增列，所以這個上限在結構上**不可能被滿足**。這是規格缺陷，不是實作缺陷，不退 frontend-engineer。

## 二、各部門回報

### tech-architect

#### 評估摘要
- 我同意 qa-e2e 的判讀：這是量測定義的假象，不是排版回歸。
- 建議 G7 改用「邊框正規化內容高」的定義（方案 B）。
- 否決兩條路：
  - 改 code 去湊 36.5，例如加 `border-b`、`last:border-b-0` 或改 `tr` class。
  - 改以「行數」作為唯一判據（方案 C）。

#### 讀碼與設定事實
- **後測版**：worktree `/home/user/AICompany/.claude/worktrees/agent-aec2877a4d3acb611/apps/stock-desk/frontend/app/backtest/BacktestReportView.tsx`
  - L281：外層 `div` 是 `overflow-x-auto @container rounded-md border border-neutral-800`。邊框在 `div` 上，不在 table 上。
  - L282：`<table className="w-full table-fixed min-w-[520px] text-left text-sm">`，table 本身沒有 border class。
  - L289：thead 的 `<tr>` 沒有 border class。
  - L304（定義列）、L319（資料列）：都是 `className="border-t border-neutral-800"`，沒有 `border-b`。
  - L320、L323、L324：`td` 為 `px-3 py-2`。L305：定義列 `td` 為 `p-0`，內層 `div` 為 `py-2`。
- **基準版**：主工作樹 `/home/user/AICompany/apps/stock-desk/frontend/app/backtest/BacktestReportView.tsx`
  - L115：外層容器同上。L116：`<table className="min-w-[520px] text-left text-sm">`。
  - L132：`tr` 為 `border-t border-neutral-800`。L133～135：`td` 為 `px-3 py-2`。
  - L96：週轉率是 `metricRows` 的最後一項，也就是 tbody 最後一列。
- **Tailwind preflight**：`/home/user/AICompany/apps/stock-desk/frontend/node_modules/tailwindcss/preflight.css`，版本 4.3.3（同目錄 `package.json` L3）。
  - L7～16：`*, ::after, ::before, ::backdrop, ::file-selector-button { … border: 0 solid; }`，所有元素的邊框歸 0。
  - L168～172：`table { text-indent: 0; border-color: inherit; border-collapse: collapse; }`。
  - 同一規則也在 `node_modules/tailwindcss/index.css` L718（`@import "tailwindcss"` 實際載入的檔案）。
- **`app/globals.css`**：`/home/user/AICompany/apps/stock-desk/frontend/app/globals.css` L1 為 `@import "tailwindcss";`。全檔沒有任何 table、`border-collapse` 或 `border-spacing` 的覆寫。
- **限制**：受測 worktree 的 `node_modules/` 與 `.next/` 跑完已清除。`git-ignored-mid.txt` L27、L29 證實執行時存在，但我現在讀不到該次建置實際產出的 CSS，只能引用主工作樹同一份 lockfile 下的套件。這一點由下方幾何證據補強。

#### F11-A-63（技術佐證：36.5／37 完全由「最後一列沒有下鄰邊框」解釋）

**規則（CSS 2.1 §17.6.2，轉述）**
- collapse 模型中，邊框以格線為中心，相鄰兩列各分一半。
- 同一條格線上有衝突時，依 §17.6.2.1，較寬的邊框勝出。
- 表格外緣的邊框由 table、row group、row、cell 的對應邊框競合決定。

**本表各格線的邊框寬**
- tbody 列與列之間：下方列的 `border-t` 1px 對上方列的下緣 0（preflight 歸 0），結果是 1px。
- thead 與第一列 tbody 之間：第一列的 `border-t`，1px。
- 表頂：thead 的 `tr`、table 皆為 0，結果是 0。
- 表底：最後一列沒有 `border-b`，tbody 與 table 皆為 0，結果是 **0**。
- 外層容器的 1px 邊框屬於 `div`，不參與 collapse。
  - 實測基準 container 2708～3341、table 2709～3340，table 上下各內縮 1px。
  - 後測 container 3254～5088、table 3255～5087，同樣上下各內縮 1px。

**單元高度**
- 內容高 c＝`padding-top` 8 ＋ 行數 × `line-height` 20 ＋ `padding-bottom` 8。
- 單行為 36，兩行為 56。
- 實測 computed 值：`fontSize` 14px、`lineHeight` 20px。

**列高公式：列高＝上半邊框＋c＋下半邊框**

| 列 | 計算 | 預測 | 實測 |
|---|---|---|---|
| thead（表頂 0、下鄰 1px） | 0 ＋ 36 ＋ 0.5 | 36.5 | 36.5（基準與後測的 `th` rect 皆是） |
| 單行中間列 | 0.5 ＋ 36 ＋ 0.5 | 37 | 37 |
| 兩行中間列 | 0.5 ＋ 56 ＋ 0.5 | 57 | 57（最大回撤、勝率、375 寬的三個新增列） |
| 基準週轉率（最後一列） | 0.5 ＋ 36 ＋ **0** | 36.5 | 36.5（top 3303.5、bottom 3340＝tableRect.bottom 3340） |
| 後測週轉率（中間列） | 0.5 ＋ 36 ＋ 0.5 | 37 | 37（4308.5～4345.5，下一列從 4345.5 起，兩列貼合） |
| 後測最後定義列 | 0.5 ＋ c ＋ 0 | 整數＋0.5 | 276.5（ma_cross 表 0，375 寬）；agg 中為 236.5、96.5 |

**換算回內容高**
- 基準週轉率：36.5 − 0.5 − 0 ＝ **36**。
- 後測週轉率：37 − 0.5 − 0.5 ＝ **36**。
- 兩者相同，殘差 0。

**全表加總驗算（ma_cross run1，375 寬，表 0）**
- 基準：
  - 列高加總：36.5 ＋ 12×37 ＋ 2×57 ＋ 36.5 ＝ **631**，等於 `tableRect.height` 631。
  - 內容加總：36 ＋ 12×36 ＋ 2×56 ＋ 36 ＝ 616，加 15 條內部 1px 邊框也是 631。
- 後測：
  - 列高加總：36.5 ＋ 資料列 840 ＋ 定義列（157＋265＋257＋276.5）＝ **1832**，等於 `tableRect.height` 1832。
  - 內容 1812 ＋ 20 條內部邊框 ＝ 1832。
  - 「交易次數」的 top 也可推得：3255 ＋ 36.5 ＋ 980 ＝ 4271.5，與實測相同。
- 兩個 .5（表頭與最後一列）剛好互相抵銷，所以表高是整數。

**直接幾何證據（與文字內容無關）**
- 定義列 `td` 為 `p-0`，內層區塊的 rect 就是 `td` 內容盒的位置。
  - 中間定義列（idx 13）：`tr` 3812.5～3969.5，區塊 3813～3969，**上下各內縮 0.5**。
  - 最後定義列：`tr` 4810.5～5087，區塊 4811～5087，**上內縮 0.5、下內縮 0**；`tr` 底等於 tableRect.bottom 5087。
- 這就是半邊框落在 cell border-box 內的實測值，也直接證明表底的邊框為 0。

**separated 模型的反證**
- 依 CSS 2.1 §17.6.1，separated 模型下 row 不能有邊框。所有量（內距 8、行高 20、`border-spacing` 整數）都是整數，不可能出現 .5。
- 所以 .5 本身就是 collapse 模型生效的正面證據。

#### F11-A-64（其他可能原因的排除）

| 候選原因 | 排除依據 | 結論 |
|---|---|---|
| 內容折行 | 多 1 行是 +20（37→57，或最後列 36.5→56.5）；`line-height` 固定 20px，0.5 不可能是行的一部分；內容高前後皆 36 | 排除 |
| 文字改變 | 週轉率 `strategyText` 為「192.58%」、`bhText` 為「0.00%」，前後相同；qa-e2e W-28／W-30 逐字比對 15 列 × 3 run 無差異 | 排除 |
| 字型或 fallback 造成行框變高 | env-probe 字型與基準相同（wqy-zenhei、DejaVu Sans）；`fontSize`、`lineHeight`、`fontFamily`、`fontWeight` 逐字相同；若是 fallback 度量造成，應跟著內容走、且不會恰好 0.5、也不會隨位置移動；相鄰同樣單行的「交易次數」前後皆 37 | 排除 |
| `table-layout` 由 auto 改 fixed | 只影響欄寬，對列高的影響只能經由折行，已在第一項排除；基準在 auto layout 下就已是最後一列 36.5 | 排除 |
| 次像素、DPR、縮放 | 所有 .5 都精確落在有半邊框的位置（表頭、最後列），其餘列與表高、容器高都是整數，且等於逐列加總 | 排除（DPR 未記錄，屬小缺口，不影響結論） |
| harness 量測函式改變 | 後測 `measure.js` L110 為 `rowHeight: tr.getBoundingClientRect().height`；qa-e2e 逐段讀過 `harness.diff`，`rowHeight` 未改；我沒有自行比對 `measure.base.js` | 排除（依 qa-e2e 審 diff 的結果） |
| 外層容器邊框或 sticky 定義區塊 | 容器邊框在 `div`，不參與 collapse；sticky 只有 `left-0`，不影響垂直方向 | 排除 |

- **證據是否足以排除：足夠。**
- **殘留缺口只有一項**：沒有直接讀到 `getComputedStyle(table).borderCollapse`，受測建置的 CSS 也已清除。但 A-63 的區塊內縮 0.5、表頭 36.5 對稱、全表加總三項彼此獨立又相互印證，這個缺口不影響結論。

#### 方案比較（G7 對「基準時為最後一列」的比較方式）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A：只把週轉率上限改為 37 | 最簡單；不用重量，現有 raw JSON 直接可判 | 只針對單一標籤，沒有寫出原理；將來列序再變，同樣問題會換一列重演 | 低；就這次數值而言與 B 等價 |
| **B（建議）：邊框正規化內容高** h_norm ＝ rowHeight − 上半 − 下半；有上鄰 `tr`（tbody 列一律有）上半為 0.5，有下鄰 `tr` 下半為 0.5，否則為 0；判定 h_norm(post) ≤ h_norm(base)，容差 0 | 不受位置影響，全部 15 列一體適用；可由現有 rowRect ＋ `nextTrLabel`（或 tableRect.bottom）計算，不需重量；正好對應 A-58 的本意 | 依賴「1px 邊框、Chromium 以小數分攤」這個前提；換儀器（例如 Firefox 可能以裝置像素取整）就要重新建立基準 | 低；harness 已鎖定 `/opt/pw-browsers/chromium-1194` |
| C：以行數 ≤ 基準行數判定 | 語意最直接 | 需要新的量測法（Range `getClientRects` 數行，CJK 加 inline 片段有歧義），必須重跑；而且會漏掉「不折行、但內距或行高被改」這類回歸，G7 原本能擋 | 中；檢驗力反而下降 |

#### F11-A-65（建議風控採用的 G7 定義；裁示權在 risk-compliance-officer）

**定義**
- 對既有 15 列，計算 h_norm ＝ rowHeight − 0.5 ×〔有上鄰 `tr`〕− 0.5 ×〔同一 tbody 內有下鄰 `tr`〕。
- 判定：h_norm(post) ≤ h_norm(base)，逐列、逐格（兩夾具 × 兩段），容差 0。

**換算後的上限**
- 基準 h_norm：最大回撤、勝率皆為 56；其餘 13 列（含週轉率）皆為 36。
- 換回後測列高：
  - 中間列：上限 37，最大回撤與勝率為 57。
  - 若某既有列在後測是最後一列：上限 36.5，兩行列為 56.5。
- 以這次後測資料而言，週轉率為中間列，上限 **37**，實測 37，判 PASS；其餘 14 列的判定與現行數值完全相同。

**適用範圍**
- 1280 寬「既有列 ≤ 基準（37，週轉率 36.5）」的守則，以同一定義改寫。
- G7 的其他部分不動：375、`scrollLeft=0`、`getBoundingClientRect().height` 量法、W-29(a)「風控門檻、不符即 BLOCKING」的屬性。

**為什麼不放寬實質保護**
- A-58 設下 G7 的本意，是擋既有列多折行。最小的實質回歸是 +1 行＝+20px。改定義後，週轉率作為中間列，多 1 行就是 57，遠大於 37，一定會被擋。
- 內容高的界線一字未鬆，仍是 36，也就是剛好 1 行，容差 0。
- 不折行的回歸（例如內距、行高、字級被改）只要讓內容高增加 ≥ 0.5，B 一樣擋得下，嚴格度與原意相同。
- 原上限 36.5 等於要求週轉率的內容高 ≤ 35.5，也就是比基準還矮 0.5。這在 W-12(b) 之下不可能成立，已經不是「不放寬」，而是錯誤的收緊。
- 改定義只是修正量測定義的錯置，不是讓步。

#### F11-A-66（補實測：選做，不是解除 BLOCKING 的前提）

- 只在風控要求直接讀值時才做。由代跑者 qa-automation 在現行 harness 的正式量測**全部完成之後**，於同一頁面加跑以下唯讀查詢，375 與 1280 各一次，兩表都量，結果只記錄。

```js
const out = [...document.querySelectorAll('table')].filter(t => t.tBodies.length && t.tHead).map((t) => {
  const tcs = getComputedStyle(t);
  const rows = [...t.tBodies[0].rows];
  const last = rows[rows.length - 1];
  const turn = rows.find((r) => r.cells.length === 3 && r.cells[0].textContent === '週轉率');
  const td = turn.cells[0];
  const r = document.createRange(); r.selectNodeContents(td);
  const lineTops = [...new Set([...r.getClientRects()].map((q) => q.top))];
  const tdr = td.getBoundingClientRect();
  return {
    borderCollapse: tcs.borderCollapse,            // expect "collapse"
    borderSpacing: tcs.borderSpacing,
    tableBorderTopWidth: tcs.borderTopWidth, tableBorderBottomWidth: tcs.borderBottomWidth, // expect "0px"
    tbodyBorderBottomWidth: getComputedStyle(t.tBodies[0]).borderBottomWidth,               // expect "0px"
    turnTrBorderTop: getComputedStyle(turn).borderTopWidth + ' ' + getComputedStyle(turn).borderTopStyle, // expect "1px solid"
    lastTrBorderBottom: getComputedStyle(last).borderBottomWidth,                           // expect "0px"
    turnIsLast: turn === last,
    turnTrRect: turn.getBoundingClientRect().toJSON(),
    turnTdRect: tdr.toJSON(),
    turnTdPadding: [getComputedStyle(td).paddingTop, getComputedStyle(td).paddingBottom],    // expect 8px / 8px
    turnLabelLineCount: lineTops.length,                                                    // expect 1
    turnLabelRangeRect: r.getBoundingClientRect().toJSON(),
  };
});
```

- **預期結果**
  - `borderCollapse === "collapse"`。
  - 表與 tbody 的下邊框、最後一列的 `borderBottomWidth` 皆為 `0px`。
  - 週轉率 `tr` 的上邊框為 `1px solid`，`turnIsLast` 為 false。
  - 標籤行數為 1。
  - `turnTdRect` 與 `turnTrRect` 的高度相同，皆為 37。
- **注意**：collapse 模型下 `getComputedStyle(td).borderTopWidth` 回傳的是宣告值，不是分攤後的半寬，所以不列入，也不作判據。半寬以 A-63 的 rect 內縮為證。
- **另一個選做的對照實驗**（更強，但會改動執行期 DOM，需風控同意才做）：
  - 在所有正式量測與截圖完成後，對受測頁執行 `t.style.borderCollapse = 'separate'`，再量週轉率與最後一列的 rowHeight。
  - 預期 .5 全部消失：單行列不論位置都變成同一個整數，row 的 `border-t` 不再繪製。
  - 這項只作佐證，不得混入正式量測或截圖，harness diff 必須顯示它排在最後。

#### F11-A-67（對實作的約束，可由 qa-reviewer 逐條檢查）

1. F-11 不得因 G7 改動任何 code。`BacktestReportView.tsx` L304、L319 的 `tr` className 必須維持 `border-t border-neutral-800`。
2. 不得加 `border-b`、`last:border-b-0`、`last:border-b`、`border-separate`、`border-spacing-*`，也不得在 table 或 tbody 加邊框，來湊 36.5 或 37。這與 W-29(b)、A-57(c) 一致。
3. 不得調整既有列的 `py-2`、`text-sm`、`leading-*`，也不得調整新增列或定義列的插入位置（W-12(b) 不變）。
4. 不得在 `app/globals.css` 新增 table 相關覆寫，例如改 `border-collapse` 或 `border-spacing`。

#### F11-A-68（A-58 的修正範圍）

- A-58 (G7) 中「週轉率 ≤ 36.5」與 1280「週轉率 36.5」兩處，待風控書面裁示後，由 A-65 的定義取代。
- A-58 其餘內容（G6、G7 的其餘 14 列、容差 0、硬性門檻屬性）一字不動。
- 不需要新 ADR。約束範圍擴為 F11-A-14～A-68。

## 三、驗證

- **讀過的檔案**
  - qa-e2e 判讀全文。
  - 基準紀錄（G7 段 L277～300、W-29 段 L433）。
  - 我自己的 A-57～A-62 原文。
  - worktree 與主工作樹的 `BacktestReportView.tsx`。
  - `globals.css`、`preflight.css`、`index.css`。
- **證據**
  - 後測：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-f11-post/agg-out.txt`（G7 與定義列高各段）、`raw/ma_cross-run1.json`（表頭 rect L184～228、週轉率 L968～1007、定義列 L1202～1444、tableRect L174～181）。
  - 基準：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-f11-base/raw/ma_cross-run1.json`（container 與 tableRect L45～66、表頭 L78～114、週轉率 L730～770）。
- **只抽驗了 ma_cross run1 的逐列 rect**。five_conditions、run2／run3 與 1280 只依 agg 輸出，那裡的數值型態一致。
- **未讀**：任何 `*.db`、`.env`。
- **未改任何檔案、未執行任何指令。**

## 四、下一步

1. **coordinator**：把本文轉給 risk-compliance-officer，並知會 CEO。
2. **risk-compliance-officer**：對 G7 出書面裁示，建議採 A-65；選 A 或 C 亦可，由風控決定。另請裁示是否要求 A-66 的補量測，我的建議是不需要。
3. **qa-e2e**：取得裁示後依 A-65 重判 G7，不需重量。依其判讀，屆時 AC-28 可判 PASS。
4. **tech-writer**：在基準紀錄 G7 表的週轉率列加註「36.5 為基準時最後一列的半邊框效應，見 F11-A-63」，並把 A-63～A-68 併入 F-11 約束清單。
5. **qa-reviewer**：審查時依 A-67 四條確認 F-11 未為 G7 改動 code。
