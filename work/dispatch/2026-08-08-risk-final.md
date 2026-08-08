# 派工單:RISK-FINAL 股票措辭定稿風控複審

- 狀態:done
- 日期:2026-08-08
- 派工者:coordinator(主 session)
- 承辦:risk-compliance-officer(背景 agent,唯讀)
- 分支:product/stock-desk(審 58b204f 的現況)
- 預算:輸出上限約 30k token
- 前情:2026-08-06 首次派出的複審 agent 因 session 用量上限夭折,本單為補派

## 範圍

依 `work/stock-desk-phase8-風控定調.md` 的定案,複審下列檔案中所有面向使用者的
建議類措辭、揭露與免責聲明,產出 APPROVE 或 VETO(逐條附理由):

- `apps/stock-desk/frontend/app/lib/adviceWording.ts`(措辭唯一來源)
- `apps/stock-desk/frontend/app/position/[symbol]/AdviceCardView.tsx`
- `apps/stock-desk/frontend/app/position/[symbol]/OperationSummaryPanel.tsx`
- `apps/stock-desk/frontend/app/position/[symbol]/page.tsx`(揭露三條)
- `apps/stock-desk/frontend/app/components/RiskGauge.tsx`
- `apps/stock-desk/frontend/app/settings/SettingsForm.tsx`、`NetWorthSection.tsx`

## 恢復指引(若環境回滾、agent 無聲死亡)

- 檢查 `work/reviews/risk-final-review.md` 是否存在且有最終結論行
- 不存在即以同樣範圍與預算重派;本單狀態改回 pending

## 結果

- 結論:**VETO**(2026-08-08),審查紀錄見 `work/reviews/risk-final-review.md`
- required 六條(R1–R6);suggested 七條(S1–S7)列管
- 用量:約 90k token(超出 30k 預算,實際逐句對照 10 檔;同類全量複審後續應編 80–100k)
- 後續:退回 build,派工單 RISK-FIX(frontend-engineer 主修)
