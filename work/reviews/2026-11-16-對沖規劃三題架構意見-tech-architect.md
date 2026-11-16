# 對沖規劃三題架構意見

- 審查者：tech-architect
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
- **Q-T1**：建議走 ADR-0030 D-1.2 的修訂，用 append 補充的方式，不另立 ADR。紙上對沖做成「事先宣告的事後導出項」：不新增 claim 列，不改表，核心期間 `app/` 一行都不動。若硬要登記成 registry 的一列，或在寫入時多記「對沖／不對沖」兩欄，就一定要改 schema，會直接撞上 CG-3、K-5、K-12，必須另立 ADR，而且要等 ADR-0026 D-6 核可並實作。
- **Q-T2**：不擴充 `CardAction`。沿用 `hold`，由後端在卡上新增一個機器可讀的原因欄位。
- **Q-T3**：第一段先放在既有建議卡，可以接受，前提是狀態由後端算好。日後搬到行動計畫卡時，代價主要是前端搬位置，以及 policy 表的對映。
- **另題**：有現成計算，就是第 3 條上限「總曝險」的 `observed`。沒填淨值時，回 `not_evaluable`，`observed` 為 null。

## 各部門回報（tech-architect，唯讀）

**Q-T1：紙上對沖要修訂 ADR-0030 還是另立 ADR**
- 修訂的依據是 ADR-0030:108。核心期間新增前瞻 claim，必須先修訂本 ADR，經風控審語意，並計入 m。
- 「沿用 scope 欄位」不可行，原因有三：
  - DDL 把欄位值釘死了：`scope_kind='market'`、`scope_key='TAIEX'`、`horizon IN (3,5)`、`kind='forward'`，`claim_id` 也由這些欄位組成（`schema.py:175-178,198-199`）。
  - 啟動時會逐字比對 `sqlite_master`（`schema.py:348-367`），表定義有任何不同都會被擋。
  - 最危險的一點：CG-2 的執行期檢查會把「同一個 (scope, horizon) 中最後登記的那列」當成記錄中 claim，其餘前瞻 claim 若沒有被取代，整個 recorder 會 `gate_closed`（`recorder.py:421-432`）。也就是說，多登記一列，輕則整條記錄停擺，重則取代掉正式的大盤 claim，n 歸零。
- `forecast_record.label` 只有四個值（`schema.py:217`），沒有地方放「對沖」欄。
- 可行做法：
  - 對沖結果以事先宣告的公式，由兩項既有資料逐位導出：既有 h3／h5 紀錄的 label，以及之後快照中已含的 T+h bar（ADR-0030:176 D-5.4）。
  - 宣告文件 commit 的時間就是起算點，只計入 `created_at` 晚於該 commit 的紀錄。
  - 公式要等驗證層解凍（D-8.5）時才實作。核心期間只落宣告文件與 ADR 補充，所以 `code_digest`、K-1 都不受影響。
  - 也不建議在 `report.py` 輸出暫定的對沖對照，以免碰到 D-4.5 的不彙總限制（ADR-0030:165）。
- 給 quant 的架構事實：快照只有 `series_kind='index_bars'`（`schema.py:155`）。指數假想空單可以導出；反向 ETF 沒有輸入序列，要用就得新增序列或表，屬於另立 ADR 的範圍。

**Q-T2：「暫停加碼」要擴充 `CardAction` 還是用 `hold` 加原因**
- 擴充 `CardAction` 與兩份 ADR 衝突：
  - ADR-0025 D-4.1 明訂「engine 不動：`CardAction` 仍為 6 值」（`0025:260`）。
  - ADR-0004 的卡片契約（`0004:194`）。
- 擴充的影響面也大：`engine.py:61,85`、前端 `types.ts:508-514`、`ACTION_DIRECTION`、股數區間、playbook 等消費端都要改。
- 用 `hold` 加原因的做法：
  - 這個狀態現在已經可以判定：`aggregated_action=="add"` 且 `action=="hold"`。
  - 三個原因各有既有分支：防禦型規則命中、上限擋下、預算採預設值（`engine.py:376-406`）。
  - 新增一個列舉欄位，例如 `add_paused_reasons`，值只來自這三個分支。
  - 不得重用 `blocked_action`，因為前端把 `blocked_action=="add"` 讀成「被風險上限擋下」（`engine.py:103-105`）。
  - 判斷必須在後端做，前端不得自行推導（AV-13，`0025:554`）。
- 對 ADR-0004 的影響：只在檔頭加一行，指向新的補充，不需要新 ADR。
- 對 ADR-0025 的影響：`0025:27` 寫「`build_advice` 輸出欄位不動」，新增欄位要在修訂中明確說明。
- 對測試的影響：
  - 卡片欄位測試用子集斷言（`test_advice_engine.py:80`），新增欄位不會使它失敗。
  - `tests/golden` 底下沒有建議卡的快照（grep `downgrade_notices` 為 0），golden 測試不受影響。

**Q-T3：第一段先放既有建議卡，日後搬到行動計畫卡**
- 先放建議卡，可以接受。理由是 `app/plan` 本來就設計成讀 engine 輸出（`0025:137`），而 AV-3 禁止 advice 反向 import plan（`0025:544`）。
- 日後搬移的代價有三項：
  - (a) 前端換位置。
  - (b) policy 第 6 列 `wait/pending_add_conditions` 與暫停加碼的語意重疊，需要一張對映表（`0025:274`）。
  - (c) 第 7 列用「5 日展望 = bearish」當觸發（`0025:275`）。在預測通過驗證之前，這一列不得混進第一段的原因清單。
- 前提條件：若狀態改由前端計算，以上前提就不成立，而且違反 AV-13。

**另題：持股占自填淨值的比例**
- 現成計算在 `limits.py:1333`：`gross_exposure_twd ÷ net_worth.amount_twd`。分子是已估值部位的市值合計（`book.py:1202,1409`）。
- 這個值會出現在兩處，各自的 `limits_check[*].observed` 欄位：
  - 每張建議卡（`engine.py:433`，欄位定義在 `limits.py:915`）。
  - 總覽 `/api/portfolio/limits`。
- 以下情況都回 `not_evaluable`，`observed` 為 null：
  - 沒填淨值（`limits.py:1302-1303`）。
  - 淨值超過 30 天未更新（`limits.py:194,1304`）。
  - 帳本沒有任何持倉（`limits.py:1315`）。
  - 有部位無法估值（`limits.py:1326`）。
- 沒填淨值時，分子本身也不會給（`book.py:1202`）。
- 產品沒有現金資料，見 `book.py:14-26` 與 `127-136`。
- 第一段只能沿用這個 `observed`，不得另算一份。

## 驗證
- 以上判斷都來自 Read／Grep 靜態查證，沒有執行任何程式或測試。沒有讀 `.env`，也沒有碰 `*.db`。

## 下一步
- 給風控：無淨值時的字面寫「缺少組合總市值」（`limits.py:426`），實際原因卻是缺少淨值，請風控確認這段字面能否沿用到第一段。
- 給 PM：Q-T1 若採導出法，PRD 第二段驗收 1「每筆紀錄同時含兩欄」要改成「可由每筆紀錄逐位導出」。
- 給 quant：Q-Q1 若選反向 ETF，就落到另立 ADR 的路線，接不上本案「不改表」的做法。
- 給 CEO：Q-T1 的 ADR-0030 補充新增了計入 m 的項目，屬實質修訂，需要 CEO 核可。排程依 #144，等接線完成後再起草，不插隊。
