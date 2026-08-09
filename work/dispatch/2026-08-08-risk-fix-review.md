# 派工單:RISK-FIX-REVIEW 六條必修的審查與風控複審

- 狀態:done(qa PASS;風控 VETO 出 V1–V3,轉派 risk-fix3)
- 日期:2026-08-08
- 派工者:coordinator(主 session)
- 承辦:qa-reviewer(先)→ risk-compliance-officer(後,僅複審 R1–R6 涉及檔案)
- 分支:product/stock-desk(審 702c422..c02cb28 的六條修復)
- 預算:qa-reviewer 約 40k;風控複審約 40k(僅六檔,非全量)

## 範圍

- qa-reviewer:審 8b348c6..b0f14f4 六個 fix commit 的 diff(正確性、R4 交易日邏輯、
  測試品質、是否引入回歸)
- 風控官:確認 R1–R6 修法符合其審查紀錄 `work/reviews/risk-final-review.md` 的要求,
  其餘部分沿用前次結論(他已明示)

## 恢復指引

- `work/reviews/risk-fix-review.md` 存在且末行結論為 PASS → qa 關已過
- `work/reviews/risk-final-review.md` 若已補記 re-review APPROVE → 風控關已過
- 缺哪關補派哪關

## 結果

- qa-reviewer:**NEEDS_CHANGES**(2026-08-08),紀錄見 `work/reviews/risk-fix-review.md`
- B1:tradingCalendar 未建模休市日反向膨脹計數,長假後誤報「資料過舊」;R1/R2/R3/R5/R6 全過
- 退修派工:2026-08-08-risk-fix2.md(frontend-engineer);修畢 qa 只複審 R4 範圍,再過風控關
- 用量:qa 67k(預算 40k,超因逐檔通讀+交叉核對元件現檔)
