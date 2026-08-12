# 派工單:BACKLOG-SPRINT 列管池清償

- 狀態:done(2026-08-10 全池收官)|日期:2026-08-10|CEO 授權全池實作
- 波次 1:A2 除權息還原(quant)、D1/D2+設定頁區塊(frontend)、README(tech-writer)、M1 麻將盤點(worktree)
- 波次 2(波次 1 落地後):TWSE 產業清單覆核工具(data-eng)、neutral-500 全站裁決(風控→frontend)
- 全部照常走 qa/風控關;新文案一律列清單送審

## 結果

- A2 除權息:資料層+同步 CLI+回測 back-adjustment(look-ahead 四道證明),六句揭露文案
  經風控兩輪退修後定稿(4930f7a);守門測試鎖 valuation/limits 不得 import dividends。
- D1/D2 清償:台北時間標註、context_notes 常駐、放寬確認擴雙上限(順修已同意紀錄遺失 bug)、
  限定語補「不含現金」五處、命中方向區塊(真對立條件)、回測常駐警語升層級+同步時間上畫面、
  設定頁目錄區塊(核可句)。
- 文件:README+已知限制 7 項過時清償(ac3867a)。
- M1 麻將盤點:cb685cc(mahjongapp 分支);反向缺口發現(做了沒記 8+ 批次)。
- 波次 2:產業覆核工具 3c06ef2(--verify-sectors)。
- 審查:qa 總審 PASS(1134+262 測試)、風控三輪後 APPROVE 收官。
- 列管遺留:放寬閘覆蓋雙欄評估、directory synced_at API、SummaryCards 總資產標籤統一、
  「分散化已無實質意義」文案待議、BacktestReportView 掃描欄位級例外。

## playbook MVP qa 審查(2026-08-12):NEEDS_CHANGES

- BLOCKING:settle()/settle_directive()/settle_open_price() 無任何生產呼叫點——T+1 結算
  未接線,帳本永不前進,同批部位每日重複出指令;settle 非冪等(重放會重複扣減)。
- 合規加固待辦 11 條:R19 價位 allowlist 雙軌(高)、D-1 REBALANCE 未實作(高)、FM-1 快市
  前態未持久化(中高)、S-1 矩陣、D-2 時間戳+limits 測試、M1-1 順延語意、E-1 停損失效
  條件句、R17 字樣、S-3 黑名單測試、E-2 MISSED 上限、R2/B1-add-5。
- 合規已過:EX-2/3/4、S-2、R18、H-1、FM-2。核心算術手算全對,T1-T9 非空殼。
