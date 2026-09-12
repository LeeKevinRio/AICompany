# ADR-0008：stock-desk 事件研究網頁版的 API 形狀與 SVG 內嵌

- 狀態：proposed
- 日期：2026-09-12
- 決策者：tech-architect（草案）、CEO（待核可）
- 適用範圍：僅 product/stock-desk 產品線

## Context（背景）

`work/stock-desk-事件研究網頁版-PRD.md` 要把 CLI `--html` 的五張圖搬進 `/backtest` 頁，
字面與視覺編碼須逐字／逐像素一致（AC-2／AC-3），且不得有第二套實作（FR-3）。
開放問題 Q1～Q3 要架構定案。現況：CLI 的 `render_html` 一次產出整頁 HTML；三個
`*_chart_svg(period, …)` 是純函式；CLI 只讀本機快取（`_load_cached_bars`），而
`/api/backtest` 走 `load_bars` 全階梯；TW `cache_first=False`、US `cache_first=True`
且快取 TTL 24 小時（ADR-0002／0005）。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| A 整頁 HTML 字串（innerHTML） | 零重構 | doctype／h1／全域 CSS 進頁；AC-8 無處放 | 樣式汙染、語境重複 |
| B iframe srcdoc + sandbox | 隔離最強 | 固定寬、高度需 script（企劃禁止）；頁首重複 | 圖被截斷、揭露被框住 |
| C sections JSON + 後端 SVG | 單一事實來源、版面可控 | 需新增 page model 模組 | 前端重排破 AC-6 |
| D 純數字 JSON、前端重畫 | 無 innerHTML | 字面與配色第二套實作 | 違反 FR-3，否決 |

Q2 替代方案：DOMPurify（新依賴、每次 render 執行、會改動已釘字的 SVG，對 XSS 零收益，否決）；
CSP（對 innerHTML 注入的 `<script>` 無效；全站 CSP 基線是 devops-sre 另案，不併入本功能）。
Q3 替代方案：把 TW 改 `cache_first=True`（違反 ADR-0005 D-1，否決）；在 `MarketDataService`
之上加 per-params run cache（第二個快取層、provenance 曖昧，違反 ADR-0002 單一入口，否決）；
合併進 `/api/backtest` 回應（違反 PRD 獨立按鈕，否決）。

## Decision（決策）

- **D-1（Q1 形狀）** 採方案 C。新增 `app/backtest/event_study_page.py`：`PageModel`／`SectionModel`／
  `HeaderItem` 與 `build_page_model(report, *, dividend_lines, generated_at, chart_width)`；
  `render_page(model)` 是唯一組 HTML 的地方，CLI 的 `render_html` 只是薄包裝。CLI 與 API 共用同一個 model。
- **D-2（Q1 順序）** `header` 是**有序** `[{role, text}]`（role ∈ `meta|notice|legend`），`sections` 是有序陣列，
  每項 `{key, title, note, extra_note|null, no_events_note|null, empty_statement|null, svg|null}`，
  `footnotes` 有序。頁首順序由後端測試保證，前端只能照序渲染、不得條件跳過。
- **D-3（字串層級）** page model 持有未轉義純文字；`html.escape` 只發生在 `render_page` 與 SVG 產生器內。
  所有字面常數留在原位（`event_study.py`／`event_study_charts.py`），既有逐字測試照舊有效。
- **D-4（端點）** `POST /api/event-study`，body 只含 `symbol/market/start/end`（無 `adjust_dividends`，固定嘗試還原）。
  `symbol` 以白名單 `^[A-Za-z0-9.-]+$` 在 pydantic 層驗證並拒絕，不做部分淨化。
  回應含與 `/api/backtest` 同構的 `status/reason/data/as_of` 與 `page`。
- **D-5（Q2 安全）** 不引入 DOMPurify、不改 CSP、不用 iframe。只有 `sections[].svg` 可進
  `dangerouslySetInnerHTML`，其餘欄位一律當純文字交給 React。依據：SVG 的文字節點只由
  `_fmt(float)`、`str(int)` 與模組級常數組成，`symbol`／`source`／日期只出現在 header 文字欄位；
  以**測試**維持邊界（後端：SVG 不含 `<script`、`on*=`、`<foreignObject`、`href`、`javascript:`；
  前端：新元件只有一處 `dangerouslySetInnerHTML`，引數即 `svg` 欄位）。
- **D-6（Q3 資料鏈）** 事件研究走與 `/api/backtest` 相同的 `load_bars` ＋ `resolve_dividend_adjustment`，
  不共用上一次回測的序列、不新增跨請求 run cache、不改 TW 的 `cache_first`。端點回報自己這次的
  `data.status/source/staleness_minutes`。
- **D-7（除權息文案）** 事件研究的除權息行採**事件研究自己已核可的句子**（`event_study.dividend_sentence`，
  依 resolver 的 reason_code **與 market** 選句：`no_events` 依台股／非台股分流，`unusable_events` 獨立成句），
  不用回測的「本回測未還原…」句；同一頁對同一事實不出現兩種說法是靠兩句各自指名對象達成
  （回測句自帶「本回測」，事件研究句自帶「已還原／未還原除權息：」，組裝端不再另加前綴）。
  此裁決已由 risk-compliance-officer 於 2026-09-12 實作複審（第二輪）無條件確認。
- **D-8（圖寬）** 圖寬為 `build_page_model` 參數：CLI 900px、網頁 800px（配合 `/backtest` 欄寬），
  字級不變；窄視窗以水平捲動容器呈現，**不得等比縮放**（風控 REQ-W6）。

## Consequences（後果）

- 好處：字面與配色只有一個產出點（FR-3）；CLI 回歸測試即網頁版的字面測試；前端零風控決策權；無新增依賴。
- 代價：多一個模組；`sections[].svg` 是唯一的 innerHTML sink，這條邊界要靠測試長期維持。
- 代價（Q3 誠實版）：台股 `cache_first=False`，按一次「顯示事件研究」就是多一次 TWSE primary 請求，
  快取不吸收；美股 TTL 內由快取回答但 `status=cached_stale`，與同頁回測區塊的狀態可能合法地不一致，
  UI 必須分別誠實呈現兩個區塊的資料狀態。
- 代價（AC-3 範圍修正）：CLI 只讀快取、Web 走全階梯，兩者可能拿到不同 bars；本決策保證的是
  「同一批 bars → 同樣像素」，不是「CLI 與 Web 永遠相同」。
- 已知限制：SVG 根帶 `role="img"` 而無可及名稱；不改已釘字的 SVG，記錄待無障礙工作處理。
- 約束：與 ADR-0002、ADR-0005 D-1 一致；要改 TW 的 `cache_first` 或引入前端淨化／CSP，開新 ADR。
