# 首頁重排第一階段：風控裁示（2026-10-03）

- 審查者：risk-compliance-officer（唯讀），由主會話代為落檔。
- 結論：第 1 項（無標籤損益％）VETO → 採 (c) 本階段不渲染，待 creative-lead 起草標籤、風控逐字核後再上；第 2 項（展開鈕 aria-label）APPROVE。主會話已依 (c) 移除百分比渲染並更新測試。

---

## 審查結論
**VETO（只否決第 1 項，也就是無標籤的損益％；第 2 項 APPROVE）**
`BLOCKING_ISSUES: 1`（B-1）

---

## 第 1 項：損益％無標籤疊放，裁示 (c)，以 (b) 作為重新上線的路徑

**本階段**：先拿掉百分比，整行不渲染。
**下一階段**：走 (b)。字面要經 creative-lead 起草、我逐字核過之後，百分比才能回到畫面上。
(a) 無標籤疊放：**不接受**。

### 逐條意見
- [`apps/stock-desk/frontend/app/components/PositionsTable.tsx` L116–118，`PnlTwdCell` 的百分比行] 新的數字沒有標示口徑。外幣持倉的台幣口徑百分比含匯率效果，可能跟原幣漲幅差很多，甚至正負號相反。例如原幣 +5%、台幣同期升值約 4%，畫面只會出現「AAPL +0.80%」，讀者很自然會讀成這檔股票漲了 0.8%。這屬於「隱藏口徑、誤導讀法」。之後同一格旁邊還會加上「今日漲跌」，也是帶正負號的百分比，兩個無標籤的百分比並排會更難分辨。→ **required**
- [手機寬度] 手機版百分比上方有 `md:hidden` 的「台幣損益」小標，但那個小標描述的是金額，不足以讓讀者推斷下面的百分比是「台幣口徑、含匯率」。桌機版連這個小標都沒有。→ 同上，**required**
- [跟規範不一致] 規範 §9 第一階段明文「此階段沒有損益％與今日漲跌欄」，§8 L3 也要求「口徑（台幣／原幣）要寫清楚」。這次實作超出第一階段的範圍，又跳過了 L3 的字面流程。選 (c) 剛好回到規範原本的安排。
- [計算本身] 計算方式我核過，沒有問題，不需要修改。`backend/app/portfolio/valuation.py` L310 的 `cost_twd = quantity × price_open × fx_open` 只在 `status == "ok"` 時才有值；沒有建倉日期時 `fx_open` 不會拿別的匯率代替（L355–363）。前端 `pnlPercentTwd` 遇到 null、0 或無法解析都回 null，也不會捏造數字。
- [`app/lib/__tests__/homeReflow.test.ts` L106–133] 選 (c) 之後，「+12.34% 出現在預設列」那條斷言要改成斷言預設列**不含**百分比。`pnlPercentTwd`／`formatSignedPercent` 這兩個函式可以保留給下一階段用，只是不要渲染。→ required（隨 B-1 一起改）

### 給 creative-lead 的 (b) 字面方向（我只給條件，不代寫）
1. 一定要看得出是**台幣口徑**，或至少讀者能從字面知道外幣持倉的百分比**含匯率變動**。
2. 標籤要常駐在預設視圖：桌機在表頭，手機用小標，兩種寬度都要有。不能只放在 hover／`title`，也不能收進展開列。
3. 禁用會被讀成股價變動的字：「漲幅」「漲跌」（跟 L1「今日漲跌」撞名）。也避免「報酬率」「獲利率」「收益」這類可能被讀成已實現或績效保證的字。
4. 口徑說明要跟現有台幣損益的揭露一致，不能另外創一套說法。不過要知道，百分比會沿用台幣損益的同一個建倉日匯率（`fx_open` 以 `opened_at` 取價）。
5. 字數要配合 CEO「不要寫一堆字」的要求：表頭或小標只放短標籤；比較長的口徑說明如果需要，再評估放在哪裡，送審時一起送。
6. 字面定稿後，D2（後端統一計算損益％）建議同一批完成，避免前後端小數處理不一致。這點由 dev-lead／tech-architect 決定，不屬於我的閘門。

---

## 第 2 項：展開鈕無障礙名稱 `aria-label="{代號} 持倉明細"`，**APPROVE**

- [`PositionsTable.tsx` L240] 這是介面操作字，不是建議類，也沒有承諾或保證語氣，用的是既有詞「持倉明細」加代號，從風控角度沒有意見。螢幕閱讀器會一起讀出 `aria-expanded` 的展開／收合狀態，不需要在名稱裡再寫「展開／收合」。
- suggested（不擋）：依規範 §8 L5，命名仍由 creative-lead 確認，這是流程上還欠的一步，跟風控無關。另外表格本身的 `aria-label` 是「持倉明細表」，跟按鈕名稱很接近，creative-lead 確認時可以一併看會不會讓人混淆。

---

## 否決理由（VETO，第 1 項）
違反兩條原則：
- 「不隱藏不確定性或口徑」：沒有標籤的百分比，在外幣持倉上把匯率效果混進看起來像股價表現的數字裡。
- 「面向使用者的新字面或新數字須經 creative-lead 起草、風控逐字核」：§8 L3 的流程沒有走。

改成 (c) 之後，第 1 項我這邊就沒有阻擋，不需要回來重審。之後要走 (b)，再送字面來逐字核。

---

## 知悉事項（不裁示）
- 首頁的風險儀表改成灰／橘，個股頁 `LimitsCheckList` 還是紅綠：已知悉。兩頁的「已違反」都保留文字標籤，首頁還改成橘色實心，醒目程度沒有降低，所以過渡期不擋。建議 CEO 不要讓兩頁長期不同步。
- 跟規範 §5.2 有兩處出入，請 qa／art-lead 確認是否刻意，我這邊不擋：
  - `app/lib/riskGauge.ts` L101 的 violated chip 沒有規範要的 `font-semibold`。
  - `homeReflow.test.ts` L280 斷言**沒有**加 ✓ ✕ ？ 符號。所以現況只用顏色加實心兩種區分，規範要的是三重編碼。

相關檔案：
- /home/user/AICompany/apps/stock-desk/frontend/app/components/PositionsTable.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/positionsTableView.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/__tests__/homeReflow.test.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/riskGauge.ts
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/work/stock-desk-首頁重排-視覺規範-2026-10-03.md
