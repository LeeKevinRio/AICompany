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

## qa 審查接線四 commit(2026-08-09):NEEDS_CHANGES

- 策略下拉/產業下拉/bcddaea 補漏:PASS(市場切換原子性、雙重防呆、逐字比對皆確認)。
- **BLOCKING**:alertRuleForm.ts buildAlertParams 與 EditAlertRuleModal paramsToForm 不認識
  signal_condition 的 ref 型條件——編輯 ref 規則(後端合法、有測試)時 value 預填 ""、
  Number("")===0,靜默把「MA5>MA20」改寫成「MA5>0」且後端 200 過。違反 AC-1.2/1.6。
  退修:補 ref 讀取/保留與正確差異比對(僅切啟用時 params 不得進 body),附 ref 規則編輯
  單元測試(該兩檔目前零測試)。
- 建議:SCANNED_FILES 再補 EditAlertRuleModal、AlertParamFields(前批已補另兩檔)。
- 流程澄清:qa 審查中察覺檔案內容變動並警戒「注入」——經查為協調層 86373a6 真實 commit
  (風控快審結論落檔),非注入;qa 拒絕採信未驗證訊息的行為正確,特此記錄。

## BLOCKING 退修完成(2026-08-09,frontend-engineer,commit 32188bd)

- 根修(要求1):`alertRuleForm.ts` 新增 `parseRequiredNumber`(杜絕
  `Number("")===0` 陷阱,所有數值欄位共用)與 `paramsEqual`(以原始 params
  物件為基準、順序無關的深比對,取代 `JSON.stringify` 直接比對);
  `buildAlertParams` 對 signal_condition 同時帶出 value/ref 兩鍵(其一
  為 null),形狀對齊後端 `Comparison` 序列化,確保差異比對正確 ——
  僅切 enabled 時 PATCH body 不含 params。
- ref 型條件編輯(要求2):選**方案 b**(唯讀顯示現值 + 提示語,理由:
  成本低、無資料毀損風險,與 dispatch 建議一致)。新句(供風控快審):
  「此規則的比較條件為欄位對欄位，目前不支援在此表單修改。」
  ——功能性/UI 限制說明,非投資/健康/法律建議性質文案,但依 dispatch
  指示列出供快審。enabled/note/symbol/market 等其餘欄位仍可編輯。
- Number("") 陷阱(要求3):`parseRequiredNumber` 統一套用於 threshold 與
  signal_condition value 欄位,空字串一律回傳 null(表單視為未完成),不再
  被 `Number()` 轉成 0。
- 測試(要求4):新增 `app/lib/__tests__/alertRuleForm.test.ts`、
  `app/settings/__tests__/EditAlertRuleModal.test.ts` 共 28 項,含
  「編輯 ref 規則僅切 enabled → PATCH body 無 params」與「ref 規則現值
  正確預填顯示」兩項指定案例。本專案無 RTL/jsdom,依既有慣例
  (`operationSummary.test.ts`)測純函式,`buildPatch` 已抽成模組層級純函式
  `buildAlertRulePatch` 供測試呼叫。
- 順手(要求5):`componentWordingScan.test.ts` `SCANNED_FILES` 補上
  `EditAlertRuleModal.tsx`、`AlertParamFields.tsx`;新覆蓋掃描全綠,
  **未掃出既有違規**。
- 驗證:`npm run typecheck`(tsc --noEmit,無輸出)與 `npm run test`
  (vitest,7 個測試檔、166 項全綠,含新增 28 項)皆綠燈。
- commit 32188bd,已 push origin/product/stock-desk。

## 複審收官(2026-08-09)

- qa 複審 32188bd:PASS(parseRequiredNumber 雙重防呆含 Infinity 邊界;buildAlertParams 形狀
  與後端 Comparison 一致;enabled-only PATCH 斷言驗到 body 內容;28 項測試無空殼)。
- 風控單句快審:APPROVE(誠實邊界過、視覺未弱化、有 role=note;suggested:補「其他欄位仍可
  修改」句,列管)。
- 下一關:qa-e2e 實機驗收(三新功能+ref 唯讀顯示+兩項列管視覺條款)。

## qa-e2e 環境缺口(2026-08-09)

- 本雲端環境未配 preview 工具與 Bash 給 qa-e2e agent,無法實機驗收;其拒絕以 code 推測
  冒充實測,行為正確。
- Deviation(協調層決定):改派通用執行代理按 qa-e2e 人設+驗收清單,以預裝 Chromium+
  Playwright 實跑(工具限制下的等效實機驗收);qa-e2e 本尊環境問題另列基礎設施待辦。
- 附帶發現:README「離線示範模式規劃中」已落後實作(app/demo/seed.py CLI 存在),
  文件更新列管交 tech-writer。

## 等效實機驗收(2026-08-09,Playwright)

- 4 PASS:回測三策略(數字互異、envelope 齊)、持倉產業別(37 選項與 API 一致、切美股停用、
  第 2 條文案隨狀態變:35.79% 已違反 ↔ 未填 not_evaluable)、ref 規則唯讀+enabled-only PATCH
  (攔截 body 證實)、375px 三表單無溢出。
- NEEDS_CHANGES(單點,不 BLOCKING):警示編輯填壞值(-5/abc)按儲存→前端守門靜默 no-op,
  無請求無錯誤字;fieldErrors 顯示機制存在但不可達。後端 422 以 curl 證實存在。
- §2.1 實測:reason 文字對比 4.18:1(<AA 4.5:1,建議 neutral-500→400 約 7.5:1);
  not_evaluable 進度條實測 0px 寬,誤讀風險中偏高(建議不畫條或斜紋佔位)→交風控裁量。
- 附帶觀察列管:ref 規則列表描述漏顯示 ref 目標(「close 大於 —」);後端 PATCH symbol 無格式
  驗證("!!!"回 200);summary 在 provider 全掛時 49 秒才降級(重試預算交 data-engineer);
  favicon 404。
- 截圖與腳本:scratchpad/e2e/(沙盒暫存,重要證據已述於本紀錄)。
