# 派工單:RISK-FIX-REVIEW 六條必修的審查與風控複審

- 狀態:running
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

(完成後回填)
