# 派工單:FE-WIRING 前端三處功能接線

- 狀態:running
- 日期:2026-08-09
- 承辦:frontend-engineer → qa-reviewer → qa-e2e 實機(含 §2.1 對比度、w-0 空條兩項列管驗收)
- 分支:product/stock-desk
- 預算:工程約 60k;qa 約 30k;e2e 約 40k

## 範圍(後端能力已就緒,C1 批交付)

1. BacktestForm 策略下拉:ma_cross 之外接 rsi_reversal、breakout(types.ts::BacktestStrategy 同步)
2. 持倉表單產業別下拉:接 GET /api/positions/sectors(台股限定;非台股停用並沿用後端 422 訊息)
3. 警示規則編輯表單:接 PUT/PATCH /api/alerts/{rule_id}(AC-1.6;clear_note 語意)

## 恢復指引

- 逐項檢查 origin 前端檔案是否已接;缺哪項補哪項;e2e 驗收結果看本單回填

## 結果

風控快審三項機械修正已完成（2026-08-09，frontend-engineer）：

1. `SettingsForm.tsx:55` `max_sector_weight` description 已整串替換為風控逐字核可句（以 Python 逐字元比對確認一字不改、標點照原文），旁註 `// 風控核可文案 2026-08-09，修改需重新送審（比照 limits.py 慣例）。`
2. `AlertRulesSection.tsx:96` 按鈕文字「立即檢查一次」→「手動檢查一次」（`立即` 屬 `FRONTEND_FORBIDDEN_TERMS` 禁用清單，無例外）。
3. `componentWordingScan.test.ts` 的 `SCANNED_FILES` 補上 `../../components/EditPositionModal.tsx` 與 `../../settings/AlertRulesSection.tsx`；新增覆蓋掃描結果全綠，**未掃出其他既有違規**。

驗證：`npm run typecheck`（tsc --noEmit，無輸出即通過）與 `npm run test`（vitest，5 個測試檔、134 項全綠，含 componentWordingScan 24 項）皆綠燈。三項齊備，依風控快審規則自動 APPROVE。

## 風控快審(2026-08-09)

- 新句清單全數 APPROVE(SECTOR_US_DISABLED_HINT 不得改寫,改寫=漂移需重審)。
- VETO 兩處既有文案+一項控制缺口,核可句已給、三項齊備即自動 APPROVE 無須再送審:
  1. SettingsForm:55 換逐字核可句(產業上限完整四狀態描述,列風控核可文案改動需送審)
  2. AlertRulesSection:96「立即檢查一次」→「手動檢查一次」(禁用清單無例外原則)
  3. componentWordingScan SCANNED_FILES 補 EditPositionModal、AlertRulesSection(掃描覆蓋
     是文案核可前提,與本批同批上線)
