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

(完成後回填)

## 風控快審(2026-08-09)

- 新句清單全數 APPROVE(SECTOR_US_DISABLED_HINT 不得改寫,改寫=漂移需重審)。
- VETO 兩處既有文案+一項控制缺口,核可句已給、三項齊備即自動 APPROVE 無須再送審:
  1. SettingsForm:55 換逐字核可句(產業上限完整四狀態描述,列風控核可文案改動需送審)
  2. AlertRulesSection:96「立即檢查一次」→「手動檢查一次」(禁用清單無例外原則)
  3. componentWordingScan SCANNED_FILES 補 EditPositionModal、AlertRulesSection(掃描覆蓋
     是文案核可前提,與本批同批上線)
