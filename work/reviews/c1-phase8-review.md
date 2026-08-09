# 審查紀錄:C1 Phase 8 清償(FR-10/11、FR-12、FR-1)

- 審查者:qa-reviewer|日期:2026-08-09|範圍:a8c3aba/9f283ec/91dbb37
- Codex:不可用,降級人工(逐檔 diff+追查引擎/前端渲染鏈路)

## 結論:NEEDS_CHANGES

## BLOCKING(僅 FR-12)

- B1:`book.py:99-115`(SECTOR_UNCLASSIFIED/MIXED_NOTE)與 `limits.py:113-121`(NO_SECTOR_DETAIL)
  三句自標「TODO(risk-gate) 未核准不得出貨」的草稿文案,已無守門地流入 /api/advice 回應
  (context_notes、limits_check[].detail),前端 page.tsx:173-182 與 AdviceCardView:147-148
  原樣渲染對使用者可見——違反 AC-12.7 與 CLAUDE.md 風險閘門。
  處置:走快速路徑——三句直接送風控審(FR-9 批已審結,AC-12.7 前置已成立);
  核准即解除,退件才改守門。

## 升級必修(獨立高優任務,非本次迴歸)

- FX1:`book.py:239-266` _position_rollup 用原幣價填 position_market_value_twd,未乘 fx_to_twd
  (全檔唯一漏做處)。美股持倉第 1 條上限分子原幣/分母 TWD,比率系統性低估 ~30 倍,
  方向為「風險看起來更低」;並經 notional_caps/suggest_quantity_range 污染股數建議。
  修法:比照 _sector_rollup(285-303)用 SummaryPosition.market_value_twd;附美股迴歸測試。

## 通過

FR-10/11:_replay 無 look-ahead、無跨折污染;RSI 抽取純搬移有 golden test;
前移收盤價偵測為真洩漏模擬。FR-1:PATCH 原子性成立、params 無殘留。
非阻擋:O(n²) 效能(樣本量內無感)、book.py:12 過期註解、note+clear_note 矛盾組合無測試。

---

## 風控快審 FR-12 三句文案(2026-08-09)

結論:句 3(SECTOR_MIXED_NOTE)APPROVE 照准;句 1(NO_SECTOR_DETAIL)、句 2(SECTOR_UNCLASSIFIED_NOTE)VETO。

- 句 1 required:實際涵蓋四種狀態(候選無持倉/台股未填/非台股/混填)卻共用一句——對混填說
  「尚未填寫」是事實錯誤;對非台股承諾「填入即可啟用」但系統會 422 拒絕(§5 誠實邊界);
  「未實際檢查」偏軟須改「本次不計算,回報 not_evaluable」。核可修正句已給(四狀態分流,
  非台股句禁止出現「填入即可啟用」;混填狀態 detail 改用句 3 說法)。
- 句 2 required:須補「通過判定也可能建立在偏低的比率上」(比照 GROSS_EXPOSURE_INCOMPLETE
  同級句);「{count} 筆」須同時給市值與佔比(筆數掩蓋量級;_sector_rollup 已握有數字,成本零)。
  核可修正句已給。
- 另:§2.1 視覺弱化條款未驗(前端顯示方式),留待 qa-e2e 實機;三處 TODO(risk-gate) 註解
  定稿後須更新為審查結論。

---

## 風控複審句 1/2 實作(2026-08-09 二輪)

- 句 1 四狀態分流:全數 PASS(unsupported_market 無承諾字樣=原 VETO 核心解除;測試釘住四句互異)。
- fallback _inferred_sector_gap:可接受,成立條件=使用者可見路徑一律走 build_book_context
  (已查證為真;建議 qa 以測試釘此不變量)。
- 句 2:逐字落實(市值+佔比+「通過判定也可能建立在偏低的比率上」)。PASS。
- 標點全形化:追認;三處核准註解為憑證不得移除。
- **新 VETO:RiskGauge.tsx**——必修 A(:45「沒有產業別欄位」「與個股卡一致」皆已不實,
  核可替換句已給可照抄);必修 B(:38、:58-59、檔頭註解以「未提供明細」為由,但 API 每筆
  已帶 sector 與 market_value_twd——方向:改述「本頁不做此計算」,出稿後回審)。
  裁定:前端不必接 gap 訊號(總覽是帳本層;唯 FR-8 可改變此結論)。
- 列管:§2.1 對比度留 qa-e2e;format.ts「無法評估/本頁不評估」語意偏差 FR-8 一併。

結論:後端文案批 APPROVE 定稿;前端 RiskGauge 兩條必修另案。
