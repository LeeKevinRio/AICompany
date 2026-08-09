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
