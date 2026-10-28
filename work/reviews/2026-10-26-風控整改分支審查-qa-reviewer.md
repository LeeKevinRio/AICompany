# 風控整改分支審查

- 審查者：qa-reviewer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

BLOCKING_ISSUES=false

# qa-reviewer 審查報告：origin/fix/stock-desk-risk-remediation（HEAD 48c5209）

## Summary
沒有 critical 或 high 問題，字面逐字等於定稿，C-1、C-2 與 5-K／Kelly 邊界都守住了。但有 3 個合併前置條件還沒滿足：C-9 的 dev-lead 書面確認、風控對 Kelly 守門測試單句例外的知悉、2-R 在 reduce 時讀起來矛盾的處置。

## 審查範圍與限制
- 讀了 34 個檔案的 diff，包含全部既有測試的修改處。
- 4 個新增測試檔（limitNotices、riskRemediationItem4、riskRemediationWording 後半、backtestAssumptionsDisclosure）只抽讀 parity 與守門段落，沒有逐行審。
- 只看了 2 張截圖（00631L-desktop-expanded.png 整頁縮圖解析度低、2330-mobile-375.png）。其餘靠 runner_out.txt 的逐字畫面。
- CI 結果（vitest 2409、pytest 8089、typecheck、build、ruff、mypy）是採信交件原文，我沒有重跑，也不能重跑。

## 各檔問題

### apps/stock-desk/frontend/app/lib/__tests__/kellyBannedLiteralsFrontend.test.ts（交件請我特別看）
- [可維護性][medium] 新增的單句例外判定：
  - 它只放行 lib/riskRemediationWording.ts 裡「不反映最近一次收盤之後的價格變動」這一整句（ALLOWED_CONTEXTS，約 :73-82）。
  - 以等長 \u0000 遮罩該句，其餘檔案的「最近一次」照舊紅燈，「帶入回測結果」完全不受影響。
  - 有過期檢查：條目必須含被禁字面，且該句必須真的存在於該檔，否則轉紅。
  - 3-F 字面是逐字定稿不能改，所以例外有必要，範圍也夠窄。
  - 它沒有動 C-1 列舉的五處守門（FRONTEND_FORBIDDEN_TERMS、shared/forbidden-terms.json、BANNED_PHRASES、allowedContexts、findBareRealtimeClaims）。
  - 但它確實改了 Kelly 條件 77／89／104 的守門測試，該檔不在 C-1 列表內，字面上不違反 C-1。定稿也沒有預先授權這個例外，因為風控沒注意到 3-F 與 Kelly 禁字相撞。
  - 建議：合併前請風控書面知悉並認可，不要求改程式。

### apps/stock-desk/frontend/app/lib/limitNotices.ts:87-90 與 DecisionCard.tsx 的 2-R
- [Edge case][medium] 在 reduce、take_profit、stop_loss、hold 都顯示 2-R。
  - 照 C-6 和定稿字面實作，沒有偏離。
  - 但 00631L 畫面（runner_out.txt）實際出現「「減碼參考」不代表你的部位在上限內；……不會改成減碼參考。」，自我矛盾。交件已揭露此事。
  - 建議：不由實作者改字。請風控裁示 reduce／stop_loss／take_profit 是否仍顯示，或交 creative-lead 改字。程式只需調整 NOTICE_ACTIONS（limitNotices.ts:27）。

### apps/stock-desk/backend/app/alerts/notify.py:64-67（3-N，C-9）
- [可維護性][medium] C-9 要求落地前由 dev-lead 書面確認警示只用日線收盤價，目前沒有這份確認。
  - 我自己核對的證據：snapshot.py:111-122 以 load_bars 取 latest.close；app/alerts 內沒有 intraday／quote 的 import。FX 的 resolve_fx_quote 是另有揭露的路徑。
  - test_alerts_notify.py 新增的 AST 守門測試也護著這一點。
  - 這是前置條件，不是程式缺陷。建議：合併前補上 dev-lead 確認。

### apps/stock-desk/frontend/app/position/[symbol]/KeyLevelsPanel.tsx:139
- [可維護性][low] 決策卡基準價句寫「停損參考與停利參考以最新收盤 918.66（…）為基準計算」，但決策卡已沒有停利格。畫面上看得到這句（2330-mobile-375.png、runner_out.txt）。句子本身仍然為真（價位階梯詳細內還有停利），只是跟主視圖不一致。字面不是定稿範圍，建議列後續處理，需風控或 creative-lead 決定。

### 根目錄 README.md:33
- [可維護性][low] 仍寫「所有建議畫面常駐「本工具為研究與教育用途，非投資建議」」。它是倉庫文件不是應用畫面，定稿也只指名 apps/stock-desk/README.md:6。這行已與實際畫面不符，建議由 creative-lead 或風控裁示新字或刪句，可併入下一批。

### apps/stock-desk/frontend/app/position/[symbol]/OperationSummaryPanel.tsx:303-305（4-附）
- [可維護性][low] 4-附與規則名只用 ml-2 分隔，畫面讀起來是「依據：目前回撤深於兩成以未還原價計算……」，像同一句。字面是定稿的，不算違規。若要加分隔，由 art-lead 決定。

## 逐項核對

### 1. 字面逐字等於定稿
逐字對照 riskRemediationWording.ts、engine.py:66、notify.py:64、layout.tsx、apps/stock-desk/README.md:6、KeyLevelsPanel.tsx:50,305、backtestCurveWording.ts:60、entryObservationWording.ts:63、sectionTaglines.ts:35：
- 1-L／1-X、2-V／2-M／2-R／2-O、3-S／3-F／3-N、4-Q、4-E 兩版、4-T 兩處、4-附、5-BT 標題與第 1／2 點（兩版）、5-BT 圖說，全部一字不差。
- K-1、K-2 對照 work/copy/2026-10-26-風控五項整改-字面起草.md:203,207 的原字面，一致。
- 兩條 xref 與 confidenceMeaning 不渲染（API 欄位保留）也符合。
- 沒有看到定稿以外的新字面；5-BT 第 3 點確實未採用。定稿之外新增的使用者可見字串只有 ▸ 符號，屬 UI 裝飾。

### 2. C-1
- git diff --stat 的檔案清單中沒有 forbidden-terms.json、loader.py、wordingScanHelpers、intradayWording.ts。
- adviceWording.ts 只新增註解（CONFIDENCE_PREFIX 標孤兒）。
- 新字面模組已加入 SCANNED_FILES，被禁用詞與 realtime 掃描涵蓋。
- Kelly 單句例外的評估見上方。

### 3. C-2（逐檔）
decisionCard、operationSummary、ruleInvalidationDisclosure、componentWordingScan、keyLevels*、backtestCurveWording、test_advice_wording、test_alerts_notify 逐檔看完，沒有刪斷言不補的情形。
- 字面更新：fixture 的 disclaimer、K-1、K-2、xref、頁尾 3-F、圖說，都是換字面。
- 等價或更嚴的替換：「整卡無 <details>」改成逐 block 檢查該句不在任何 <details> 內；「停利格」斷言改為 not.toContain／格數 4→3；「信心行」測試改為標示恆顯示，並保留「信心不渲染」。
- 較弱處：decisionCard.test.ts 的信心 chip 原本斷言「緊接 chip、中間只隔一個閉合與開啟標籤」，現在只剩「標示在 RULE_SOURCE_CHIP 之後」。原斷言綁定的 chip 已下架，可接受，但相鄰性斷言確實弱了一級（low）。
- 屬 5-K 範圍而未動：test_advice_limits.py、Kelly API 測試、RiskGauge、SettingsForm、KellyImportDialog，符合 C-16。
- 舊字面 grep：使用者可見面只剩根 README.md:33（已列上方）。其餘為註解、否定式測試與延後處理的 event_study.py:423。
- CONFIDENCE_PREFIX：已無元件使用，測試有反向斷言。

### 4. C-4～C-13 對照實作
- C-4：held 與 candidate 恆顯示，no_action 與 no_price 不顯示；用 <details>，text-sm text-neutral-400；兩處 chip 都移除。
- C-5：排除 kelly_fraction；1 條用 2-V、2 條以上用 2-M；null 時不印「—」；2-O 不論有無違反都顯示；放主畫面，text-sm。
- C-6：只限 held、至少 1 條 violated（排除 kelly）、action 屬四種之一；add 與 insufficient_data 不顯示；被擋句在 2-R 之前。邏輯與定稿一致，問題只在字面（見上）。
- C-7：四種 kind 都顯示 3-S；位置在上限區塊後、失效條件行前；text-sm text-neutral-300；不在 <details>。R3 指引句已移除，InlineDisclaimer 保留。
- C-8：頁尾字級與色階不弱於 text-sm text-neutral-400；apps/stock-desk/README.md:6 同步。
- C-9：見上方 notify.py 項目。
- C-10：只在停損非「—」時顯示 4-Q；text-xs text-neutral-400；依 atr14 === null 二選一；<details>。
- C-11：決策卡停利格與 targetDistance 已移除（四格變三格）；KeyLevelsPanel 主視圖停利大字已移除；階梯組標題改 4-T，target-2r 的 isHeadline 為 false；詳細內停利卡標題下加 4-T。
- C-12：以 topMatchedRuleId 比對 drawdown_protection／deep_drawdown_stop，與依據同一行。
- C-13：5-BT 在 data_warning 之後、EquityCurveChart 之前，常駐、text-sm；標題與第 2 點依 slippage_bps === 0 選句；實測 14px。
- C-15：新常數都有「風控 2026-10-26 定稿；失效條件 T#」；limitNotices.ts 兩個常數已補註解。
- C-3：test_advice_engine.py 新增三條（非 add 動作不變、add 才變 hold、not_evaluable 不擋加碼）；test_backtest_engine.py 新增三條（同根收盤成交、滑價預設 0）。4-E 的 riskRemediationItem4.test.ts:99-146 我沒有逐行讀，採信交件說明。

### 5. 前後端 DISCLAIMER parity
- 後端 test_advice_wording.py 從 riskRemediationWording.ts 解析常數，與 DISCLAIMER 比對。
- 前端 riskRemediationWording.test.ts:124-130 反向從 engine.py 解析。兩側互讀，且我逐字核對兩邊常數一致。

### 6. 5-K 與 Kelly
- 本批沒有動 limits.py、RiskGauge、SettingsForm、KellyInputsSection、KellyImportDialog、KellyDisclosuresPanel、kelly_wording.py，字面與行為都沒變。
- 5-K 另開 PR，需等 CEO 對「停用會拿掉 10% 封頂」裁定，符合 C-16。

## 第二意見（Codex）
無法取得：codex --version 回傳 exit 127（codex: command not found）。依 CEO #58 只在報告中註明，沒有試圖安裝或繞過。因此這份審查沒有跨廠商第二意見。

## 唯讀權限判準常數
未觸及。
- 我用 git diff product/stock-desk...origin/fix/stock-desk-risk-remediation --stat 取代指定的 --name-only | grep。34 個檔案全在 apps/stock-desk/ 下，沒有 scripts/validate_agents.py，也沒有 .claude/ 或 docs/ 的異動。
- 指定的第二道檢查（git diff -- . | grep -E 'READONLY_AGENTS|READONLY_ALLOWED_BASH'）沒有照字面跑：Bash 權限只准 git diff，管線與 grep 不在範圍內。改用已讀取的各檔 diff 作代替，三問回答：改了什麼＝沒有任何檔案出現這兩個常數；為何改＝不適用；有無 ADR＝不適用。shadow 定義與常數值被改動這兩種情境，在這批 diff 中均無出現。
- 這是有限度的核對，不等價於該 grep 的全量掃描。

## 合併建議
可合併，但需先滿足以下 3 項，皆不要求改程式：
1. dev-lead 補 C-9 書面確認。
2. 風控書面知悉並認可 Kelly 守門測試的單句例外。
3. 風控裁示 2-R 在 reduce、stop_loss、take_profit 時是否顯示，或改字。若判定須改，退回實作者只動 NOTICE_ACTIONS 與字面。

另外：
- 根 README.md:33 與 KeyLevelsPanel.tsx:139 的決策卡「停利參考」基準句列為後續待辦。
- 5-K 另開 PR，等 CEO 裁示後才能 merge。
- 本批屬 UI 變更，審查通過後仍須 qa-e2e 實機驗收，不得以交件自己代跑的截圖取代。

## Verdict
PASS
BLOCKING_ISSUES=false

## 我執行過的 Bash 指令（全部）
1. codex --version：失敗，exit 127，命令不存在。
2. git diff product/stock-desk...origin/fix/stock-desk-risk-remediation --stat
3. git diff product/stock-desk...origin/fix/stock-desk-risk-remediation -- apps/stock-desk/frontend/app/lib/__tests__/kellyBannedLiteralsFrontend.test.ts
4. git diff product/stock-desk...origin/fix/stock-desk-risk-remediation -- apps/stock-desk/backend/app apps/stock-desk/README.md …layout.tsx …adviceWording.ts …backtestCurveWording.ts …entryObservationWording.ts …keyLevelsVisuals.ts …sectionTaglines.ts …operationSummary.ts
5. git diff …-- "apps/stock-desk/frontend/app/position" apps/stock-desk/frontend/app/backtest/BacktestReportView.tsx
6. git diff …-- decisionCard.test.ts operationSummary.test.ts ruleInvalidationDisclosure.test.ts（輸出過大被存到工具結果檔，用 Read 讀完）
7. git diff …-- componentWordingScan.test.ts keyLevelsHoldingUnknown.test.ts keyLevelsVisuals.test.ts backtestCurveWording.test.ts test_advice_wording.py test_alerts_notify.py
8. git diff …-- test_advice_engine.py test_backtest_engine.py

沒有寫入任何檔案，沒有讀 .env，沒有碰 *.db，也沒有 cd、git show、git log、grep、cat、npm、uv 或 python。其餘讀取都是用 Read、Grep、Glob。

相關檔案（絕對路徑）：
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/apps/stock-desk/frontend/app/lib/riskRemediationWording.ts
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/apps/stock-desk/frontend/app/lib/limitNotices.ts
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/apps/stock-desk/frontend/app/lib/__tests__/kellyBannedLiteralsFrontend.test.ts
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/apps/stock-desk/backend/app/alerts/notify.py
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/apps/stock-desk/frontend/app/position/[symbol]/KeyLevelsPanel.tsx
- /home/user/AICompany/.claude/worktrees/agent-ae548e877df28e7ce/README.md
