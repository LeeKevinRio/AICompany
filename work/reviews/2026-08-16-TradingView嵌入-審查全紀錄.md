# TradingView 圖表嵌入:審查全紀錄(2026-08-16)

- 功能:標的詳情頁嵌入 TradingView Advanced Chart 官方 widget(頁籤與本地圖表並列,
  TradingView 預設);CEO 裁示。
- 交付鏈:實作 4938eb5 → qa NEEDS_CHANGES(critical XSS)→ 修補 644a80c →
  風控文案二輪(揭露句 CONFIRMED/失敗句刪尾三輪 CONFIRMED)→ 定稿落地 c9e35d9 →
  qa 複審 **PASS**。

## qa 一輪(NEEDS_CHANGES,BLOCKING)

- **critical reflected XSS**:route 參數 symbol 未驗證 → toTradingViewSymbol 僅
  trim/upper → JSON.stringify 進 dangerouslySetInnerHTML;`</script>` 注入實測可行
  (JSON.stringify 不逃逸 <>/)。修法要求:白名單+script-safe 逃逸雙層+注入測資。
- medium:同頁換代號僅重掛內層 script,舊 iframe 可能殘留 → key 提升呼叫端。
- low:script 無 onerror,失敗要等滿 12 秒。

## 修補(644a80c)

- 白名單 `^[A-Za-z0-9.-]+$` 回傳 string|null,不符不靜默替換;null → 中性
  TRADINGVIEW_CHART_INVALID_SYMBOL_MESSAGE 早退不進 sink。
- scriptSafeJson.ts:<>& → \uXXXX(JSON 內合法,round-trip 語意不變)。
- key 提升 page.tsx 呼叫端(`market:symbol`);onError 立即 fallback(settledRef 防雙觸發)。
- 注入 regression 測資:`</script>`/`"`/%3C%2Fscript%3E decode/白名單拒絕。

## 風控文案(VETO → 定稿)

- 一輪 VETO 兩句(R1-R6):「已驗證」全稱背書對上櫃/美股為假、缺第三方非背書聲明、
  預設頁籤揭露密度低於既有面板、與全產品否定式揭露體系互斥、失敗句導流+品質宣稱。
- 二輪:揭露句 CONFIRMED(定稿字面見 TradingViewChartPanel.tsx 常數;落地條件
  ≥text-sm/≥neutral-400);失敗句尾句再退兩點(無條件未來式承諾+「其」同屏指代矛盾),
  風控預核刪除案。
- 三輪:刪尾版單句 CONFIRMED。兩句定稿已落地(c9e35d9,樣式 text-sm/neutral-300,
  componentWordingScan 逐字釘住同 commit 更新)。

## qa 複審(PASS,BLOCKING_ISSUES=false)

- 兩層防禦驗證完整(白名單空字串正確拒絕;\uXXXX 在 script 解析層安全;null 早退在
  config 與 sink 之前);key 提升確認;定稿字面與留痕逐字一致含標點;兩處揭露句渲染
  分支樣式皆升級無遺漏。
- low 觀察:全點號/連字號輸入會放行(交 TradingView 自身錯誤畫面,安全無虞,設計內);
  TRADINGVIEW_CHART_INVALID_SYMBOL_MESSAGE 屬技術性錯誤提示非建議類,不落風險閘門,
  註解已標記獨立性。
- 建議 qa-e2e/CEO 實機驗收畫面呈現(字級對比實際渲染、無效代號路徑)。

## 列管(風控/qa 各一)

- 揭露句可補「圖表價量可能與本頁其他數值不一致」(版位餘裕時另審)。
- DataSourcesSection US 主欄字面於 AV 三輪 PASS 後可能已過時(保守方向不擋,更新須另審);
  TW 列 backups 含 TPEx 而該 legacy 路徑已死,是否標注屬另案。
