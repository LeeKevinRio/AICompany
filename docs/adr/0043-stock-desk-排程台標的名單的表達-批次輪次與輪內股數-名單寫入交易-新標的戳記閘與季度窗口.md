# ADR-0043：stock-desk 排程台標的名單的表達、批次輪次與輪內股數、名單寫入交易、新標的戳記閘與季度窗口（補充 ADR-0035、ADR-0041、ADR-0042，不取代；判定 ADR-0034 C-B11 為 N-168 的範圍約束）

- 狀態：proposed
- 日期：2026-11-08（修訂一：2026-11-09，依風控審查第四節第 1 點）
- 2026-11-09 併入 TA 補遺-1（RC-2，風控確認）
- 2026-11-10 併入 TA 補遺 5c 與補遺二-1b、1c（RC-11，風控免回送）
- 2026-11-10 依風控 RC-21、RC-22、RC-24 併入 TA C-T05、C-T13 約束
- 決策者：
  - tech-architect：草案與修訂一；
  - risk-compliance-officer：2026-11-09 CONDITIONAL APPROVE（R-1～R-18）；修訂後的 D3 第 7 點與 ADR-0034 補充四風控 2026-11-09 確認（見 work/reviews/2026-11-09-ADR0043修訂一單項確認與N209Q2裁示-風控.md），其餘段落不必回送；
  - CEO：#119～#122（2026-11-08）裁定方向；#123（甲案）、#124（另開 N-209）、#125（E2）於 2026-11-09 裁定；本 ADR 的核可（須明示包含 ADR-0034 補充四，見 D3 第 7 點 J-9）與 Q-C11 待定。
- 來源簡稱（皆在 `work/` 下）：
  - [TA-207]：`reviews/2026-11-08-N207架構評估-tech-architect.md`
  - [PRD]：`stock-desk-排程台標的設定-PRD.md`（draft v2，以 v3 為準）
  - [N203]：`reviews/2026-11-08-N203排程台標的寫入路徑查證-dev-lead.md`
  - [TA-197]：`reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md`（3.8～3.9，N-197a 規格與 `TotalDeployStamp`）
  - [決策包]：`dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`（#119～#125 與「#123 知悉事項」列）
  - [風控-207]：`reviews/2026-11-09-N207與ADR0043審查-風控.md`（R-1～R-18）
- 適用範圍：僅 product/stock-desk。路徑相對於 `apps/stock-desk/backend/`。
- 標註：
  - 行號是 2026-11-08 主 checkout 的快照。N-177a、N-195、N-196、N-197a、N-177b、N-198、N-209 都還沒合入，行號會漂移，抽驗請以內容定位。
  - `TotalDeployStamp`、`set_total_deploy(expected=…)` 是 [TA-197] 的規格名稱，以 N-197a 實際合入為準；名稱不同時回 TA。
  - 新字面只寫識別名，逐字由風控定稿，只放在 `wording.py`。

## Context（背景）

1. **現況**：
   - 名單就是 `playbook_batches` 裡出現的 distinct symbol。
   - 唯一建立批次列的 `ensure_batches`（`INSERT OR IGNORE`）在 `app/` 內沒有呼叫點；也沒有任何入口可以設定、停止、換標的（[N203]）。
   - `high_volatility` 欄位存在，但沒有寫入也沒有讀取。P3 永遠以 BIAS25 大於 15% 判定（`engine.py:487`），屬於沒接上線的 bug（[TA-207] Q-T7）。
2. **CEO 裁示**：
   - #119：第一版就支援重開新輪；採單調遞增的 `batch_no` 加 `batch_round`，engine 的 `planned_batch_shares` 改為輪內計算，送風控。
   - #120：季度窗口由系統依日曆判定，以 Asia/Taipei 為準；窗口外只能停止新進場。
   - #121：新標的等 REBALANCE 重算 TOTAL_DEPLOY 後才生效，採戳記閘，相依於 N-197a。
   - #122：季中自己停止的標的，恢復也要等窗口。
   - #123（2026-11-09）：待生效閘採甲案，REBALANCE 或資金確認都算（D6）。
   - #124（2026-11-09）：REBALANCE 畫面入口另開 N-209，須在 N-207 上線前完成。
   - #125（2026-11-09）：窗口終點採 E2，也就是下季第一個交易日 13:30（D8）。
3. **既有不變式（本 ADR 不得破壞）**：
   - ADR-0035：批次永不重置。K1／K2 決策身分鍵含 `(symbol, batch_no)`。G1 的 SQL 零 diff（補充六）。
   - N172-C11：不 UPDATE、不 DELETE 既有指令列。
   - ADR-0041：結算以外的批次寫入者只能做欄位化寫入，不得寫股數；`app/` 內不再以 `INSERT OR REPLACE` 整列寫批次。
   - ADR-0042：唯一的結算進入點是 `claim_and_settle`。
   - N-197a：TOTAL_DEPLOY 三個鍵（TD、set_at、source）的原始字串戳記；寫入者只有 `set_capital`（confirm）與 `set_total_deploy`（REBALANCE）。
   - ADR-0034 Decision 6：CEO #80 永久紅線（B-2b）。
4. **engine 現況的阻礙**：
   - `planned_batch_shares` 以 `batch_no < batches_per_target` 判斷末批（`engine.py:208`）。新一輪的第 4 批會被誤判為末批，吸收整檔餘額。
   - 要支援新一輪，就得改 engine 這個函式，碰到 ADR-0034 C-B11「R、S、P 的引擎邏輯不改」。
5. **REBALANCE 的 docstring**寫「manual by design……engine has no calendar of quarters」（`service.py:1817-1819`）。季度窗口是新概念，但只用在名單操作；REBALANCE 本身不受窗口限制，維持零 diff。
6. **風控審查**（[風控-207]，2026-11-09）：CONDITIONAL APPROVE。required 項目 R-1～R-18 全部完成前，N-207 不得合併或上線。本修訂吸收 R-2～R-10、R-12～R-14、R-17、R-18 中屬於 ADR 的部分；字面類（R-11、R-15、R-16 與第二節 F 表）由 creative-lead 擬稿、風控逐字定稿。

## Options（選項比較）

| 議題 | 方案 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| 停止新進場 | 新增批次狀態 `stopped` | 狀態一眼可見 | 停止前已產生的 R1 會被 G1 擋下，違反 FR-10；恢復時要改回 planned，等於重置 | 高 | VETO |
| | 共用 `paused` | 零 schema 變更 | S1 站回 25MA 的自動恢復會把它清掉（`engine.py:1239-1255`） | 高 | VETO |
| | **`playbook_symbols.entry_stopped`，service 從 engine 輸入剔除該檔 planned 批次** | 批次列與指令列零變動 | engine 輸入與帳冊清單不同，要守住單一定義 | 低 | **採用（D2）** |
| 新一輪的身分 | 主鍵改為 `(symbol, round, batch_no)` | 語意直觀 | 要重建表；K1、G1、claim 的 `WHERE symbol=? AND batch_no=?` 會有歧義 | 高 | VETO |
| | 舊批次改回 planned | 零 schema 變更 | 就是重置；舊的 pending R1 會被 G1 放行 | 高 | VETO |
| | `INSERT OR IGNORE`／`INSERT OR REPLACE` | 現成 | 靜默無效，或刪掉舊列 | 高 | VETO |
| | service 重新編號後交給 engine | engine 零 diff | directive 與 effect 都要反向對映；「第 N 批」會和帳冊不一致 | 中高 | 否決 |
| | **單調 `batch_no` 加 `batch_round`，engine 改為輪內計算** | 主鍵、G1、K1、指令列全部不變；`batch_no` 永不重用 | 改 engine 一個函式，屬規則語意變更 | 中 | **採用（D3，CEO #119）** |
| 互斥 | **單一 `BEGIN IMMEDIATE` 加鎖內重驗加預覽摘要** | 跨執行緒、跨行程有效；SQL trace 可以檢查 | 確認型操作可能要使用者重新預覽 | 低 | **採用（D4、D5）** |
| | 執行中標記、`threading.Lock`、大交易、檔案鎖 | — | 見 [TA-207] Q-T4 | 中～高 | 否決 |
| 生效閘 | **戳記閘（新批次列記錄 TOTAL_DEPLOY 戳記）** | REBALANCE 與 confirm 零 diff；同一次讀取就能自洽 | 有 ABA 殘留（同 N-197a） | 低 | **採用（D6，CEO #121）** |
| | 名單提交與 REBALANCE 合成一個交易 | 沒有中間狀態 | 鎖內會有網路 I/O；推翻 N-196、N-197a | 高 | 否決 |
| 閘的解開條件 | **甲：任何一次 TD 寫入使戳記改變就解開** | 只開不關；REBALANCE、confirm、N-197a 零 diff | 屬放寬 #121（風控 R-9） | 低 | **採用（D6，CEO #123）** |
| | 乙、丙、丁 | 見 D6 第 6 點 | 見 D6 第 6 點 | 中 | 不採（CEO #123） |
| 季度窗口 | **日曆窗口純函式，API 層與鎖內都強制** | 符合 #120 | 日曆退回週一到週五判定的已知限制（雙向，D8 第 4 點） | 低 | **採用（D8，CEO #120）** |
| | 使用者宣告換季 | 比照 REBALANCE | 不符合 #120 | — | 否決 |
| 窗口終點 | **E2：F 的 13:30** | F 當天盤中仍可提交；等於「下季第一個評估日之前」的最晚時刻 | 窗口較 E1 長半天 | 低 | **採用（D8，CEO #125）** |
| | E1：F 的 00:00 | 較保守 | F 盤中不能改名單 | 低 | 不採（CEO #125） |
| `/today` 排除揭露（R-7） | **service 以同一份 `engine_batches` 結果分類排除批次，API 層組句** | `_snapshot_rows`、`BatchSnapshot` 零 diff；類別與 engine 輸入同源 | `PlaybookEvaluation` 多一個加法欄位；golden 要登錄新鍵 | 低 | **採用（D3 第 6 點）** |
| | 改 `_snapshot_rows` 一併列出被排除的批次 | 一處呈現 | 破壞 N207-C3；engine diff 超出 `planned_batch_shares` | 高 | 否決 |
| 「規則已全數評估」範圍（R-8） | **(a) service 層把旗標判為 false** | 與 S1、S2 先例（`engine.py:1277-1281`）相同；零新字面；API `no_directive_note` 與前端 `noDirectiveNote` 零 diff | 有排除的日子不再顯示「無命中」句，由 R-7 揭露行說明 | 低 | **採用（D3 第 6 點）** |
| | (b) 改用加註範圍的變體句 | 資訊較多 | 新字面；前端 `noDirectiveNote` 只在旗標為 true 時顯示，要改；內容與 R-7 揭露行重疊 | 低 | 不採，風控 2026-11-09 確認（見 work/reviews/2026-11-09-ADR0043修訂一單項確認與N209Q2裁示-風控.md） |
| | 在 engine 內處理 | — | 違反 N207-C7 與 D3 第 7 點 J-6 | 高 | VETO |

## Decision（決策）

### D1：名單與「啟用」的單一定義
1. 名單 = `playbook_batches` 中的 distinct symbol，是唯一的真實來源，不另立名單表。名單列一律不刪。
2. 「啟用」= 在名單內，而且 `entry_stopped = 0`（`playbook_symbols` 沒有該列，視同 0）。
   - S1 暫停、S2 黑名單、待生效中的標的仍算啟用，占名額，名額不補。
3. **啟用檔數** = 名單中啟用的 symbol 數。這是唯一的計數定義，名單入口、FR-24 的 confirm-rules 檢查、cap-1 揭露（FR-28）都引用同一個函式。
4. **今日可進場檔數** = 啟用中、沒有 S1 暫停、不在 S2 黑名單，而且在 D3 第 6 點的 engine 輸入裡至少有一筆 planned 批次的 symbol 數。直接沿用 engine 輸入函式，不另寫第二份條件。
   - **名單頁 S2 的用途與判定日期（風控 2026-11-10 RC-21；來源：TA 2026-11-09 T-13「ADR 漏洞」，風控同意）**：
     - 名單頁的 S2 只用於顯示，不得作為任何寫入或閘的判斷。
     - 名單頁的 S2 以台北今日判定，取值與 D8 第 6 點的 `today_tpe` 必須是同一個來源。
     - 已知代價（方向不保守）：資料落後的那幾天，名單頁的 W 可能比 `/today` 實際評估時大（來源：TA T-13；風控 RC-21）。
   - **多標記計數（TA 2026-11-09 C-T13-1、C-T13-2；風控 2026-11-10 RC-21 採方案 (B)）**：
     - C-T13-1：後端回傳 X、W 與各類計數。差額由後端另外給（X−W），前端不得以加總代替。
     - C-T13-2：每類的謂詞定義如下，全部限啟用標的，直接沿用 `engine_batches` 與 `entry_gate_open`：
       - S1 = `paused`；
       - S2 = 黑名單在效期內；
       - 待生效 = 最大輪有 planned 而且閘未開；
       - 無待進場 = 最大輪沒有 planned。
     - 四類不互斥：「待生效」與「無待進場」彼此互斥，S1、S2 可與其他類同時成立；各類各自計數，加總可能大於差額（來源：TA T-13 事實段）。
5. 不提供「單獨新增一檔新代號」的操作。新代號只能經首次設定或季度提交進入名單。

### D2：停止新進場
1. `playbook_symbols` 新增加法欄位 `entry_stopped INTEGER NOT NULL DEFAULT 0`、`entry_stopped_on TEXT`（停止當下的 Asia/Taipei 日期）。
2. 只有名單寫入方法會寫這兩欄，寫法是 upsert，`ON CONFLICT(symbol) DO UPDATE` 只更新自己的欄位。`set_paused`、`blacklist`、`apply_effects` 不寫這兩欄；名單路徑也不寫 `paused`、`paused_since`、`playbook_blacklist`。
3. 停止只影響 engine 輸入（D3 第 6 點）：
   - 該檔 planned 批次不交給 engine，所以不出 R1，也不累計 M1 順延與 R3 跳過；
   - open 批次照常交給 engine，S、P 與 EMERGENCY 照常評估。
4. 已產生、尚待結算的指令照常結算，不取消、不改寫（FR-10，N172-C11）。停止若在某次評估讀取之後才 commit，那次評估仍可能寫出 R1，視同「先評估、後停止」，並揭露。
5. 對已停止的標的再停止一次：冪等，零寫入，也不寫稽核列。

### D3：批次身分、輪次與 engine 輪內計算
1. **身分**：主鍵維持 `(symbol, batch_no)`，`batch_no` 永不重用。
   - `playbook_batches` 新增加法欄位 `batch_round INTEGER NOT NULL DEFAULT 1`。既有列一律是第 1 輪，不回填其他欄位。
2. **新一輪的寫入**：
   - 新輪的 `batch_no` 從該檔目前最大值加 1 起，連續編 `batches_per_target` 個號，`batches_per_target` 取鎖內讀到的現行參數；
   - `batch_round` = 該檔目前最大輪次加 1；全新代號是第 1 輪，`batch_no` 1～bpt；
   - 一律用一般 `INSERT`，主鍵衝突就 raise、整個交易回滾；
   - INSERT 只寫 `symbol, batch_no, status='planned', batch_round, entry_gate, updated_at`，股數類欄位走 DEFAULT，所以不構成 ADR-0041 所稱的「寫股數」。
3. **開新輪的前置條件**（鎖內判定）：
   - 該檔所有既有批次都已是 `closed` 或 `skipped`。這兩者都是終態，所以舊輪之後永遠不會再變動。
   - 舊輪殘留的在途買單，會因批次已非 planned 被 G1 擋下，不會成交到新輪（AC-50）。
4. **重新加入的案例矩陣**依 [PRD]（i）～（v）：
   - (i) 解除停止，續用原 planned 批次，不加閘；
   - (ii) 解除停止，不新增任何列；
   - (iii)、(iv) 開新輪，新批次加閘（D6）；
   - (v) 拒絕。
   - 季度提交：
     - 「保留」組中舊輪已全部終結的標的，要使用者逐項確認後才開新輪（Q-C10 預設）；
     - 保留組中有 planned 或 open 的標的，是 no-op（續用），不適用 (v) 的拒絕；
     - 保留組中已停止的標的，依 (i)～(iii) 處理。
5. **engine 輪內計算（CEO #119，規則語意變更；風控 2026-11-09 核可方向）**：
   - 只改 `planned_batch_shares` 的函式本體，簽名與呼叫點（`engine.py:982-988`）都不變。
   - 規格（英文程式，load-bearing）：
```python
def planned_batch_shares(*, batch_no, close, symbol_batches, total_deploy, params) -> int:
    symbol_amount = total_deploy / Decimal(params.n_targets)
    per_batch = symbol_amount / Decimal(params.batches_per_target)
    if close <= 0:
        return 0
    # Round of the batch being sized; a batch_no not in symbol_batches keeps
    # the pre-N-207 behaviour (round 1).
    this_round = next((b.batch_round for b in symbol_batches if b.batch_no == batch_no), 1)
    round_batches = [b for b in symbol_batches if b.batch_round == this_round]
    # Round 1 keeps its legacy numbering verbatim (offset 0). A later round is
    # numbered contiguously from the previous maximum + 1 (D3 第 2 點), so its
    # offset is that previous maximum.
    offset = 0 if this_round == 1 else min(b.batch_no for b in round_batches) - 1
    if batch_no - offset < params.batches_per_target:
        return max(1, int(per_batch // close))
    already = 0
    for batch in round_batches:
        if batch.batch_no >= batch_no:
            continue
        already += batch.shares if batch.status != "planned" else max(1, int(per_batch // close))
    return max(1, int(symbol_amount // close) - already)
```
   - **等價性**：所有批次都是第 1 輪時，`round_batches == symbol_batches`、`offset == 0`，整個函式與修改前逐式相同。斷號、批數多於 bpt 的舊資料也一樣。由 N207-T1、T2 的差分測試（各至少 300 組 seed）釘住；seed 空間只含 `batch_no ≥ 1`，因為 `BatchState` 不允許更小的值。
   - **舊資料異常（風控 R-1）**：等價不代表正確。
     - 有斷號的資料，可能沒有末批補足；
     - 批數多於 bpt 的資料，從第 bpt 批起每一批都走末批分支，有可能只買 1 股；
     - 這兩種是使用者事前不會知道的靜默沿用；
     - `batch_no` 小於 1 的列到不了 engine：讀取時就 raise。`/today`（含未確認路徑）、`/rebalance`、全部出清、未確認時的資金確認都回 500；排程台頁無法載入，全部出清無法使用。已確認的 `/today` 在失敗之前可能已經 commit 結算。這是現況就有的行為，完整範圍見 N-207 規格 §9「說明」。
     - 部署前唯讀盤點發現第 1 輪批數不等於 bpt、`batch_no` 最大值大於 bpt、最小值不等於 1，或有斷號時，停止部署，回報 TA 與風控（N-207 §9 STOP-1）。
   - **語意變更只發生在第 2 輪以後**：
     - 輪內序位小於 bpt 的批次，依每批金額計算；
     - 輪內末批吸收「整檔配額減去同一輪已占用」；
     - 舊輪批次不計入。
   - **不變的部分**：
     - 每批金額仍是 TD ÷ n_targets ÷ bpt，取「評估當下」的 TD，不是開輪當時的 TD；
     - 每檔配額仍是 TD ÷ n_targets，名額不補，不因啟用檔數減少而提高；
     - R1、R2、R3、M1 的條件與順序不變；
     - S、P 系列一行都不改；
     - **鐵律①的現金底線只看 open 批次，不受 engine 輸入過濾影響（風控 R-2）**：`_apply_cash_floor`（`engine.py:1037-1043`）的總資產只加總輸入中 status 為 open 的批次。open 批次由 `engine_batches` 恆納入（D3 第 6 點），所以總資產與預算不因名單狀態、戳記閘或輪次改變；
     - skipped 批次在末批計算中以 `shares` 計入，末批補足被跳過批次的金額，這是第 1 輪現況照搬；
     - rule_summary 的「第 {batch_no} 批」仍由 `batch_no` 呈現，新輪自然顯示為第 4～6 批（FR-43）。`/today` 的輪次說明由 API 層補（D3 第 6 點）。
   - **輪次完整性的測試（風控 suggested，採納為 N207-T23，BLOCKING）**：
     - 斷言 `planned_batch_shares` 只會對「整輪都在輸入裡」的批次被呼叫：被計算批次所屬的輪，在 `symbol_batches` 中的 `batch_no` 集合，要等於帳冊中該檔同一輪的 `batch_no` 集合。
     - 理由：輪次不完整時 offset 會算錯。目前只靠 D3 第 6 點的結構間接保證（同一輪各批的閘相同；已停止標的只剩 open，不會有 planned 被計算），要用測試直接釘住。
6. **engine 輸入的單一定義**：在 service 內新增一個純函式 `engine_batches(book, *, roster, stamp)`，`evaluate` 與 `evaluation_marks` 收同一個回傳物件。批次 b 被納入，當且僅當：
   - `b.status == "open"`（任何一輪；賣出類評估永不被名單狀態壓住），**或**
   - 標的未停止、`b.batch_round` 等於該檔最大輪次，而且（`b.status != "planned"`，或 `entry_gate_open(b.entry_gate, stamp)`）。
   - 推論：
     - 舊資料（未停止、全是第 1 輪、`entry_gate` 為 NULL）時，輸入與修改前逐列相同，順序不變；
     - 已停止的標的只剩 open 批次；
     - 待生效的新輪整輪不在輸入內。
   - **被排除批次的分類（風控 R-7）**：
     - 在 service 內新增純函式 `classify_exclusions(book, inputs, *, roster, stamp)`。「是否被排除」只由 `inputs`（即交給 engine 的同一個物件）決定；分類只負責說明原因，不得自行判定是否排除。
     - 每一個被排除的批次恰好屬於下列一類，依序判定：
       - (1) 已停止新進場標的的待進場批次（標的已停止，而且 status 為 planned）；
       - (2) 已停止標的的已終結批次（標的已停止，而且 status 為 closed 或 skipped）；
       - (3) 舊輪批次（標的未停止，而且輪次小於該檔最大輪次）；
       - (4) 待生效批次（標的未停止、最大輪次、planned、閘未開）。
     - 結果掛在 `PlaybookEvaluation` 的加法欄位上，只在 `evaluate_today` 設定；engine 不讀寫此欄位。
     - `/today` 的常駐揭露行由 API 層組出，`_snapshot_rows` 與 `BatchSnapshot` 零 diff（N207-C3、C17）。
   - **「規則已全數評估」的範圍（風控 R-8，採 (a)）**：
     - 只要有任何被排除的批次是 planned（不論屬第 (1) 類或第 (4) 類），`evaluate_today` 就把 `rules_fully_evaluated` 判為 false。
     - 這只能在 engine 之外做，方向只能由 true 改為 false。這與 S1 暫停、S2 黑名單的先例相同（`engine.py:1277-1281`）：R 系列沒有評估，就不得說成「已全數評估」。
     - API 層 `no_directive_note` 與前端 `noDirectiveNote` 的判斷零 diff，原句因此不會單獨出現（N207-C18）。
   - **`/today` 輪次說明（風控第二節 F 第 11 句）**：只要 `/today` 有第 2 輪以後的批次，或任何指令指向第 2 輪以後的批次，就由 API 層加一行常駐輪次說明。engine 的「第 {batch_no} 批」零 diff。
7. **ADR-0034 C-B11 的範圍判定**（比照 ADR-0035 補充六；依風控 R-3～R-6 修訂）：
   - 本點的條款與 ADR-0034 補充四**逐字同列**，以條款編號 J-1～J-10、I-1～I-5 對照。本點與補充四合稱「本判定」。兩處若有不一致，qa-reviewer 依 C-B11 字面判 BLOCKING，並回 TA 修正。
   - **J-1 判定**：ADR-0034 附錄 C 的 C-B11「R、S、P 的引擎邏輯不改」，以及 Consequences「被約束」中「R、S、P 的引擎邏輯不改（C-B11）」一句，判定為 N-168 的範圍約束，不是 engine 永久不得修改的架構決策。
   - **J-2 理由**：C-B11 列在「B-2a 約束清單（交 dev-lead）」，目的是防止 N-168 在實作 B-2a 時順手改動 R、S、P，讓「照常結算、停損停利照常評估」的語意可以驗證；N-168 已於 9253032 合併。先例：ADR-0035 補充六對 `settle()` 零 diff 的判定；ADR-0040 補充一 E-2 對 C-B8 與 C-B11 關係的判定。
   - **J-3 延伸適用**：同一判定適用於 ADR-0035 附錄 B 的 N172-C3（N-172a 的範圍）、ADR-0041「限制」與「與其他 ADR 的關係」中的「engine 零 diff（C-B11）」（N-177a 的範圍）、ADR-0042 N198-C1 的 engine.py 零 diff（N-198 的範圍）。ADR-0040 Decision 12 的限定範圍豁免在本判定之前成立，不需要撤回。
   - **J-4 不放寬所屬單**：J-3 所列約束，對其所屬單自身的 diff 仍然完全有效。N-177a 與 N-198 在本判定起草時（2026-11-08）都尚未合入：ADR-0041「engine 零 diff」對 N-177a 的 diff、N198-C1 對 N-198 的 diff，qa-reviewer 照原字面判定。N172-C3 對 N-172a 亦同。本判定的意思只是「這些約束不約束 N-207」，不是放寬它們自己。
   - **J-5 仍然有效的不變式**（日後改動 engine，以及依 J-6 視同改動 engine 的變更，都必須遵守）：
     - **I-1 B-2a 語意（CEO #79）**：出清當時未結算的 R 買單照常結算並標示（L4 落檔戳記）；停損停利照常評估。
     - **I-2 C-B8**：engine 只照抄標示，不做判斷。
     - **I-3 C-B10**：不得自動替帶標示的批次產生 EMERGENCY 賣單。C-B10 是 CEO #80 永久紅線（ADR-0034 Decision 6）的實作約束，不是範圍約束。本判定不影響 #80，#80 亦不得以範圍判定的方式解除；重開的唯一途徑仍依 ADR-0034 Decision 6（CEO 修改豁免框架，並經新一輪風控審查）。
     - **I-4**：engine 不讀寫 TOTAL_DEPLOY 戳記、名單狀態或任何 I/O。可檢查的形式：`engine.py` 的 import 清單零 diff；`engine.py` 不出現 `TotalDeployStamp`、`entry_gate`、`entry_stopped`、`entry_stopped_on`、`high_volatility_prev`、`high_volatility_changed_on`、`engine_exclusions` 這些名稱。`batch_round` 是批次身分，不屬名單狀態。
     - **I-5**：open 批次在任何名單狀態、戳記閘、輪次之下，都交給 engine 評估 S、P 與 EMERGENCY。
   - **J-6 防繞道**：日後任何改動 R、S、P 判斷邏輯或股數計算的變更，須有自己的 ADR、經風控審查並經 CEO 核可。在 engine 之外以過濾或改寫 engine 輸入、或後處理 engine 輸出，而改變 R、S、P 判斷結果或股數者，視同改動引擎邏輯，適用同一要求。不得把本判定讀成「engine 從此開放修改」。
   - **J-7 不構成先例**：本判定不構成日後豁免的先例。日後對 engine 或任何 accepted ADR 護欄條文所做的範圍判定，不得以本判定作為成立依據，須各自陳明理由、經風控審查並經 CEO 核可。
   - **J-8 N-207 的承載**：以下三項都由 ADR-0043 承載，已經風控審查，隨 CEO 核可 ADR-0043 生效：
     - N-207 對 `planned_batch_shares` 的改動（ADR-0043 D3 第 5 點）；
     - 以 `engine_batches` 過濾 engine 輸入（D3 第 6 點）；
     - 「規則已全數評估」旗標的範圍處理（D3 第 6 點）。

     其中 engine 輸入過濾正屬 J-6 所稱「在 engine 之外以過濾輸入而改變 R 系列結果」，是經由 J-6 的程序成立，不是 J-6 的例外。
   - **J-9 生效**：本判定自 CEO 核可 ADR-0043（含 ADR-0034 補充四）之日起生效；核可須明示包含補充四。核可前以 proposed 狀態落檔，qa-reviewer 依 C-B11 字面對 N-207 的 engine diff 判 BLOCKING；N-207 的合併以本判定生效為前提。
   - **J-10 原檔與註記**：ADR-0034 原文不改（比照補充一～三先例，CEO 可推翻改為另立取代 ADR）。本判定生效後，由 tech-writer 在 ADR-0035、0041、0042 檔頭各加一行指向 ADR-0043 D3 第 7 點的註記；生效前不加。
   - 補充四全文見 ADR-0034 檔頭（由 tech-writer 落檔，狀態 proposed，依 J-9 生效）。

### D4：名單寫入交易
1. 操作種類：首次設定、停止新進場、重新加入（含開新輪）、季度提交、高波動標記。每種都是兩步，先「預覽」再「確認」，確認時必須帶回預覽摘要。
2. **鎖外**（可以有網路）：
   - 新代號的驗證（[TA-207] Q-T8）；
   - 以 `evaluate_today` 同一個指數載入器建立 `TradingCalendar`（D8）；
   - API 層的窗口判定與凍結判定（快速拒絕用，不作為最終依據）。
3. **鎖內**：一個連線、一個 `BEGIN IMMEDIATE`，依序：
   - (a) 讀取：批次（symbol、batch_no、batch_round、status）、`playbook_symbols` 的相關欄位、`playbook_state` 的 TOTAL_DEPLOY 三鍵與 `emergency_until`、`freeze_until`、現行參數（接收 conn 的 helper，與 `active_params` 共用同一份定義）；
   - (b) 讀一次注入的時鐘；
   - (c) 呼叫純函式：窗口、凍結、案例矩陣、檔數與名額、摘要比對；
   - (d) 寫入只限三處：`playbook_symbols` 的自有欄位 upsert、`playbook_batches` 的新輪 INSERT、`playbook_roster_log` 的 INSERT；
   - (e) `COMMIT`。
   - 鎖內零網路，不呼叫會另開連線的 `self.*`。
   - 錯誤處理照 C-11：先 ROLLBACK 再原樣 raise。
4. **零寫入**：任何拒絕或失敗，三張表都逐列不變（FR-39）。資料層的日線快取不在此限。
5. 名單路徑在任何情況下都不寫：`playbook_state` 的任何鍵、`playbook_directives`、`playbook_schedule`、`playbook_blacklist`、`playbook_fill_moves`、`playbook_evaluation_marks`。
6. **各操作的閘門矩陣**：

| 操作 | 窗口（D8） | 組合凍結（D8） | 預覽摘要 | 代號驗證 | 新批次 | 戳記閘（D6） |
|---|---|---|---|---|---|---|
| 首次設定（批次表為空） | 不受限（Q-C6 PM 預設，coordinator 定案，CEO 可推翻） | 拒絕 | 是 | 是 | 每檔第 1 輪，bpt 批 | 有 |
| 停止新進場 | 不受限 | 允許 | 是 | 否 | 無 | — |
| 重新加入 (i)(ii) | 受限 | 拒絕 | 是 | 否 | 無 | — |
| 開新輪 (iii)(iv) | 受限 | 拒絕 | 是 | 否 | bpt 批 | 有 |
| 季度提交 | 受限 | 拒絕 | 是 | 新增組 | 新增組第 1 輪；保留組中逐項確認的開新輪 | 有 |
| 高波動標記 | 不受限（Q-C8 PM 預設，coordinator 定案，CEO 可推翻） | 允許（FR-40 未列） | 是 | 否 | 無 | — |

### D5：並發語意
- 每次名單寫入都在寫鎖內重驗，再加上預覽摘要比對，所以任何並發組合的結果都等於某一個循序執行。確認前內容已改變時拒絕、零寫入（FR-22）。
- 不設「執行中」標記，也不用行程內鎖（F-c、F-d、ADR-0042 P6 的先例）。
- 交錯分析（讀碼推論）：

| 並發的兩方 | 兩方寫入的資料 | 結果 |
|---|---|---|
| 名單 × REBALANCE | REBALANCE 只讀 open 批次與現金，寫 TD 三鍵；名單不建 open，不寫 state | 交換律成立。名單先 commit：新批次記舊戳記，REBALANCE 之後解開。REBALANCE 先 commit：新批次記新戳記，仍待生效（AC-56） |
| 名單 × confirm-rules | confirm 寫 params、資金、TD 三鍵；名單只讀 n_targets 與戳記 | 等於某一個循序。FR-24 的檢查若在名單改變之前讀到，等於「先 confirm、後改名單」 |
| 名單 × `claim_and_settle` | 結算寫批次狀態、股數、現金、指令列、schedule；名單寫 `playbook_symbols`、新 `batch_no` 列、稽核表 | 寫入不相交；開新輪的前置條件由寫鎖序列化。結算剛把最後一批關閉時，名單交易若排在後面就看到終態並允許開新輪，排在前面就拒絕 (v) |
| 名單 × `evaluate_today` | 評估在鎖外讀取 | 等於「先評估、後寫名單」或相反。閘與輪次放在批次列上，與 `book` 同一次讀取；戳記與 `portfolio` 同一次 state 讀取 |
| 名單 × 名單 | — | 寫鎖序列化，加上鎖內重驗與摘要比對 |
| 名單 × 參數變更（另案） | 參數依鐵律④次日生效 | 鎖內讀現行參數，結果等於某一個循序 |

- ADR-0041 R-4′ 的判定維持：評估新增的是讀取（戳記），不是寫入，budget 公式不變。

### D6：新標的戳記閘（CEO #121；解開條件採甲案，CEO #123 定案）
1. `playbook_batches` 新增加法欄位 `entry_gate TEXT`：
   - NULL 表示無閘（既有列，以及續用的 planned）；
   - 非 NULL 是新批次 INSERT 當下、鎖內讀到的 `TotalDeployStamp` 的標準編碼：`json.dumps([td, set_at, source], ensure_ascii=False, separators=(",", ":"))`，鍵不存在時為 null。
   - 只在 INSERT 時寫一次，之後任何路徑都不更新。同一輪的各批戳記相同。
2. **判定**：`entry_gate_open(recorded, current)`，與 `TotalDeployStamp` 放在 store.py 同一處，只有一份定義：
   - recorded 為 NULL：開；
   - 否則把 recorded 解碼為 `TotalDeployStamp`，與 current 比較 NamedTuple 是否相等；**不相等就開**（甲案，CEO #123）。
   - 只比對原始字串，不比時間先後，比照 ADR-0035 補充五。
3. **current 的來源**：與交給 engine 的 `portfolio` 取自同一次 `_state_map()` 讀取。這樣閘一打開，engine 用的 TD 必然是解開閘的那個新 TD。
4. REBALANCE 失敗、`REBALANCE_BLOCKED` 或 `REBALANCE_SUPERSEDED` 時，戳記不變，名單保留待生效，不作廢（AC-57）。
5. 首次設定也套用閘。理由：
   - 只有一條規則；
   - `evaluate_today` 在 `:2158` 與 `:2199` 兩次讀批次之間若插入首次設定，沒有閘的話，新 symbol 會進 engine 輸入但日線沒有載入，出現假的資料缺漏警示。
   - CEO #123 對此點未另行指示，隨本 ADR 核可。
6. **甲案定案與 CEO 同意紀錄（風控 R-9）**：
   - **CEO #123（2026-11-09）**：「REBALANCE 或資金確認都算，即甲案。任何一次 TD 寫入使戳記改變就解開閘，解開後不再關上。是否屬於放寬 #121，由風控判定。」
   - **風控判定（2026-11-09，R-9）：屬放寬 #121，字面與實質都是。**
     - 字面：#121 是「等 REBALANCE」，甲案多了資金確認這條解開路徑。
     - 實質：`confirm_rules` 的 TD 是 capital × deploy_ratio，只依提交的數字計算、不看持股（`service.py:2013-2016`）；REBALANCE 則依當日資產重算。
   - **同意紀錄**：CEO 選定 #123 時，已知悉「與 #121 字面有差異、是否屬放寬由風控判定」。風控既已判定屬放寬，#123 即為 CEO 對此項放寬的明示同意。另外，R-10(c) 要求的補充知悉事項已於 2026-11-09 告知 CEO，記在 [決策包]「#123 知悉事項」列。內容是：首次確認後畫面不再出現確認入口；以 API 重送資金確認會以提交數字覆寫現金，TD 不看持股，不能用來取代 REBALANCE。
   - **未採方案（紀錄）**：

| 方案 | 內容 | 不採理由 |
|---|---|---|
| 乙 | 戳記改變，而且目前 source 等於 `REBALANCE_SOURCE` 才開 | 會倒退：REBALANCE 之後若再有一次 confirm，閘會重新關上；首次上線要多跑一次 REBALANCE |
| 丙 | 只認 REBALANCE，只開不關，在 `set_total_deploy` 同一交易內另寫 REBALANCE 紀錄 | 推翻 N197a-C1、C2，要重送風控；首次上線同樣要 REBALANCE |
| 丁 | 丙，加上首次設定不套用閘 | 丙的全部代價，加上第 5 點的讀取偏斜殘留 |

7. **ABA**：三個鍵恰好回到原值時（時鐘倒退，而且 TD、source、set_at 微秒都相同），會有兩種情形，殘留同 N-197a：
   - 尚未解開的閘不會開；
   - 已解開的閘會重新關上。這是 #123「解開後不再關上」的唯一理論例外。

   兩者方向都是不開，不會造成買進。只在 ADR 記錄，不對使用者揭露（風控同意「不開」面向；「重新關上」面向：風控 2026-11-09 確認（見 work/reviews/2026-11-09-ADR0043修訂一單項確認與N209Q2裁示-風控.md））。
8. **以 API 重送資金確認（風控 R-10）**：
   - 首次確認後，畫面上的確認入口不再出現（`RuleSetConfirmPanel` 只在 `mode === "unconfirmed"` 時顯示）。甲案多出的實質解開路徑，只剩以 API 重送資金確認。
   - 重送會以提交數字覆寫現金，TD 也不看持股；若誤把總資產當成現金填入，鐵律①的現金底線預算會被灌大。
   - 字面約束（逐字由風控定稿）：
     - (a) 待生效說明句只把資金確認寫成「首次設定時」的解開方式，不得寫成通用的解開方法；
     - (b) 手動操作說明（#118）與 N-209 的 REBALANCE 入口說明，都要寫明重送資金確認會覆寫現金、TD 不看持股，不能用來代替 REBALANCE；
     - (c) 知悉事項見第 6 點。
   - 「已有 open 批次時重送資金確認」要不要拒絕或警示，由 TA 另案評估（風控 suggested），不在 N-207 範圍。在另案定案前，`confirm_rules` 除了 FR-24 的前置檢查之外不改。
9. **REBALANCE 入口（CEO #124；風控 R-17）**：
   - N-209（REBALANCE 畫面入口）必須先於 N-207 合入（N-207 規格 N207-M4）；
   - 待生效相關字面只有在 N-209 已合入時，才可以提到「REBALANCE 入口」。

### D7：高波動標記的接線與生效（併入 N-204）
1. `playbook_symbols` 新增加法欄位 `high_volatility_prev INTEGER NOT NULL DEFAULT 0`、`high_volatility_changed_on TEXT`（變更當下的 Asia/Taipei 日期）。`high_volatility` 是目標值。
2. 生效值（單一純函式）：`effective = high_volatility if changed_on is None or data_date > changed_on else high_volatility_prev`。
   - data_date 都是交易日，所以「data_date 晚於變更日」等價於「下一個交易日起生效」；變更當日的評估仍用舊值（FR-30、AC-65）。
   - 不需要日曆，也不受週一到週五退回判定影響。
3. 寫入時：
   - `prev` = 寫入當下的生效值，以台北今日為 data_date 計算；
   - `high_volatility` = 新值；
   - `changed_on` = 台北今日。
   - 同日來回切換時，生效值不變。
4. **接線**：`evaluate_today` 在算出 `data_date` 之後、建 snapshot 之前，讀一次 `symbol_states(data_date)`，同一份結果同時交給 `build_market_snapshot(high_volatility=effective)` 與 engine。`:417`（出清）與 `:1840`（REBALANCE）不傳，因為它們不評估 P3。
5. 畫面上的生效日期以 `calendar.next_trading_day(changed_on)` 呈現，有日曆退回判定的已知限制。判定只看第 2 點，不看這個日期。字面用「M 月 D 日起適用」或「尚未適用」，不得用「待生效」（風控 R-18；「待生效」只留給 D6 的戳記閘）。
6. **既有標記（風控 R-13）**：
   - 既有列中 `high_volatility=1` 而 `changed_on` 為 NULL 的，部署當下立即生效：這些標的的 P3 過熱減碼門檻由 BIAS25 大於 15% 提高為大於 20%，減碼變少，屬放寬賣出規則。
   - 部署前唯讀盤點列數大於 0 時，停止部署（N-207 §9 STOP-3）。CEO 要明示保留或取消：
     - 保留：需要一次性的部署通知，在本機畫面列出受影響代號、門檻變化與「自部署起適用」；
     - 取消：取消路徑由 TA 另行設計並送風控，不得以手動改 DB 處理。
   - 列數為 0 時，不需要通知，在 release note 記錄即可。

### D8：季度窗口與組合凍結的判定（CEO #120；終點採 E2，CEO #125 定案）
1. **窗口純函式**（唯一定義，放在新模組 `app/playbook/roster.py`）：`quarter_window(*, now: datetime, calendar: TradingCalendar) -> QuarterWindow`。
   - `now` 必須帶時區，naive 就 raise。先轉為 Asia/Taipei 時間 t。
   - L(q) = 季度 q 內依 `calendar.is_trading_day` 判定的最後交易日；F(q) = 季度 q 內第一個交易日。
   - **窗口 W(q) = [L(q) 13:30, F(q+1) 13:30)**，以 Asia/Taipei 判定，含起點、不含終點（E2，CEO #125）。13:30 取自 `app/data/freshness.py` 的 `TW_POLICY.session_close`，不另立常數。
   - 等價說法：「最近一個已收盤的交易日，是它所屬季度的最後交易日」。
   - 回傳開窗與否、起訖時刻、L 與 F（供訊息使用）。
2. **切點的理由**：
   - 起點：季末最後交易日的收盤時刻，就是 #120「收盤後」的字面。
   - 終點：data_date = F 的評估，只能在 F 收盤之後開始，所以「下季第一個評估日之前」的最晚時刻是 F 的 13:30。
   - E1（終點為 F 的 00:00），CEO #125 未採。
   - 不採「下季第一個排程日（週二或週四）」：評估每個交易日都在跑（S、P 每天評估），排程日不等於評估日，而且會把窗口拉長。
3. **日曆來源**：在鎖外以 `evaluate_today` 同一個指數載入器建立 `TradingCalendar`，以值傳入鎖內，鎖內只呼叫純函式。載入失敗時，日曆為空，全部走週一到週五判定。
4. **日曆退回判定的雙向影響**（推導，由 N207-T12 實證；揭露依風控 R-11，必須雙向陳述，不得寫「只會變窄」）：
   - **已觀測範圍外**，以週一到週五判定：國定假日可能被當成交易日。算出的 L 不早於真實 L、F 不晚於真實 F，所以窗口可能提早結束或延後開始。
     - 已知的系統性情形（保守方向，風控可接受）：Q4 換 Q1 時，1 月 1 日落在週一到週五而且在已觀測範圍外的話，會被當成交易日，窗口在 1/1 13:30 結束，而不是 1/2 13:30。
   - **已觀測範圍內**，某個真實交易日整天缺 bar（指數與全部標的都缺）：該日被當成非交易日，窗口可能提早開始或延後結束。
   - 拒絕訊息中「下一個窗口」的起訖都是未來日期，一定是以週一到週五推算的。字面要註明「依系統日曆推算，遇休市可能不同」；拒絕原因寫成「依系統日曆判定」，不得寫成「已過窗口」這種絕對說法。
5. **強制點**：
   - API 層（預覽與確認）；
   - 寫鎖內：以鎖內讀到的時鐘重算。預覽到確認之間跨過切點，就拒絕、零寫入。
6. **組合凍結（Q-T12(b)：可以在鎖內判定）**：
   - 鎖內同一句 SELECT 讀 `emergency_until` 與 `freeze_until`；
   - 純函式 `portfolio_frozen(*, emergency_until, freeze_until, today_tpe)`：任一者不為 None 且 `today_tpe <= until`，就判為凍結。
   - **截止日的取值與回傳（TA 2026-11-09 C-T05-1～C-T05-3；風控 2026-11-10 RC-24 採附日期的 B 版字面）**：
     - 兩個截止日鍵都是含當日的截止日（來源：TA T-05，引 `models.py:269-273` 註解 `end date, inclusive`）。
     - C-T05-1：`portfolio_frozen` 改為回傳 `(frozen: bool, until: date | None)`。`until` 取兩個非 None 值中**較晚者**，只在 `frozen` 為真時有值。名單入口的字面所用的截止日只能取這個回傳值；API 預檢與鎖內共用同一個函式。
     - C-T05-2：截止日含當日，名單入口從截止日的下一個台北日曆日起放行。字面寫到截止日時，一律附「（含當日）」（風控 RC-24）。
     - C-T05-3：依 ADR-0033 C-9，這個判定不落檔。
     - `today_tpe` 與 D1 第 4 點名單頁 S2 的判定日期為同一個來源。
   - **性質**：engine 以 `data_date <= until` 判定凍結，而 data_date ≤ 台北今日。所以名單入口拒絕時，engine 一定也處於凍結，不會多擋。
   - **殘留（風控 R-12）**：
     - 資料落後的那幾天（until < 台北今日，但 data_date ≤ until），名單入口已放行，engine 仍處於凍結。
     - 這比 FR-40 的字面寬，但不會增加買進：engine 照樣壓住 R 系列，新批次也還在閘後。
     - CEO 要在本 ADR 改為 accepted 之前，明示回答 Q-C11；這不擋 proposed 落檔。
     - 名單頁的事實說明句：常駐，條件式規則陳述（風控 2026-11-10 RC-31；字面由 creative-lead 擬、風控逐字定稿）。
   - 判定不儲存（ADR-0033 C-9）。這不是 ADR-0034 VETO-1 所禁止的「以讀取時比較 `emergency_until` 推導標示」，因為本處是寫入前置條件，不是批次標示。
   - 本次評估剛觸發、尚未寫入的 S3 讀不到，視同「名單先、評估後」的循序結果。
7. **防守模式**不屬於 FR-40 所稱的組合凍結，本 ADR 不納入；要納入另裁。

### D9：稽核表
1. 在 `_SCHEMA` 新增 `playbook_roster_log`，欄位如下：
   - `id INTEGER PRIMARY KEY AUTOINCREMENT`
   - `created_at TEXT NOT NULL`（UTC ISO）
   - `taipei_date TEXT NOT NULL`
   - `action TEXT NOT NULL`
   - `symbol TEXT`（整份名單的操作為 NULL）
   - `before_json TEXT NOT NULL`
   - `after_json TEXT NOT NULL`
   - `detail_json TEXT NOT NULL`（季度提交的三組差異、新輪的 batch_no 範圍與 entry_gate）
   - `digest TEXT NOT NULL`
2. 每次成功的名單寫入，恰好寫一列，與業務寫入在同一個交易內；拒絕、失敗、冪等的 no-op 都不寫。FR-20 的書面紀錄就是 `action='quarterly_submit'` 的列。
3. `app/` 內只有 INSERT。另以 `CREATE TRIGGER IF NOT EXISTS` 擋 UPDATE 與 DELETE（`RAISE(ABORT, …)`）。`INSERT OR REPLACE` 本來就由 N207-C1 禁止（ADR-0038 的先例：REPLACE 不會觸發 DELETE trigger）。

## 與其他 ADR 的關係

| ADR／條文 | 性質 | 內容 |
|---|---|---|
| ADR-0034 C-B11（及「被約束」同句） | **範圍判定** | 屬 N-168 的範圍約束，見 D3 第 7 點 J-1～J-10；以 ADR-0034 補充四記錄（proposed，依 J-9 自 CEO 核可起生效） |
| ADR-0034 B-2a、C-B8、C-B10、Decision 6（CEO #80） | 不變 | 列為不變式 I-1～I-3；#80 不得以範圍判定解除 |
| ADR-0035 不變式 | 補充（加強） | 「永不重置」加強為「新批次只用從未用過的 `batch_no`，以一般 INSERT 寫入」。K1／K2 因 `batch_no` 不重用，新輪不會與舊決策撞鍵。G1 的 SQL 零 diff |
| ADR-0035 N172-C3 | 範圍判定 | 同 D3 第 7 點 J-3；依 J-4 對 N-172a 自身仍有效 |
| ADR-0035 補充五 | 沿用 | 只比對原始字串、不比時間先後 |
| ADR-0040 Decision 9 | 沿用 | `evaluation_marks` 收「engine 實際收到的輸入」，也就是過濾後的 `engine_batches` |
| ADR-0040 Decision 12 | 不變 | 既有的限定範圍豁免不需要撤回 |
| ADR-0041 | 補充 | 新增一種允許的批次寫入者：新輪 INSERT（planned、股數走 DEFAULT），不屬於動帳；不得有整列寫回（新欄位會被洗回預設值）。R-4′ 維持。「engine 零 diff」屬 N-177a 的範圍，依 J-4 對 N-177a 自身的 diff 仍完全有效 |
| ADR-0042 | 補充 | 名單路徑不新增任何 claim 或動帳呼叫點；`claim_and_settle` 仍是唯一的結算進入點。N198-C1 的 engine 零 diff 屬 N-198 的範圍，依 J-4 對 N-198 自身的 diff 仍完全有效 |
| N-197a（[TA-197]） | 相依 | 沿用 `TotalDeployStamp` 的單一定義，不重新定義。N197a-C5「`confirm_rules` 零 diff」屬 N-197a 的範圍，比照 J-4，對 N-197a 自身的 diff 仍完全有效；N-207 在 N-197a 合入後，為 FR-24 修改 `confirm_rules`，`set_capital` 仍零 diff。N197a-C6 不受影響（名單不寫現金） |
| N-209（CEO #124） | 相依（先行） | N-209 先於 N-207 合入（R-17，N207-M4）；REBALANCE 入口說明要依 D6 第 8 點 (b) |
| ADR-0033 | 不衝突 | 只讀 `emergency_until`；C-9 不儲存 |
| ADR-0031 | 補充（字面待風控） | FR-28 依 C-1「可依此增列」，在 `compose` 增列 keyword-only 的 `enabled_targets` 參數；同單、獨立 commit（coordinator 定案，CEO 可推翻）。風控 R-15 已定方向：① 的分母維持 n_targets，加註名額空缺不補；③ 有空缺時改用 1 ÷ 啟用檔數或並陳；啟用檔數為 0 時用 `_UNAVAILABLE` 變體；逐字由風控定稿。C-5 同一份回應的來源要求，擴及啟用檔數 |
| ADR-0024 | 不變 | 代號的形狀規則放在名單模組，不放進資料層准入 |
| REBALANCE docstring | 不衝突 | 季度窗口只用在名單操作；REBALANCE 維持手動、不受窗口限制、零 diff |

## Consequences（後果）

- **好處**：
  - N203 §1.4 的 8 點風險都有結構性的對應；
  - REBALANCE、confirm 的寫入、結算、`commit_evaluation`、G1 零 diff；
  - `batch_no` 永不重用，「每個 (symbol, batch_no) 一生最多一筆 executed R1」比現在更強；
  - 舊資料上 engine 與 `/today` 逐值不變（T1、T2、T21；新增欄位只以登錄的 added_keys 出現）；
  - 修正前新一輪的第 4 批會被當成末批，吸收約 3 倍的每批金額；修正後不會，這是收緊。
- **壞處與代價**：
  - **規則語意變更**：第 2 輪以後的股數計算改變。每批金額取評估當下的 TD，新輪開始之後若 REBALANCE 改變了 TD，同一輪各批的金額基準會不同（與第 1 輪現況一致）。風控 2026-11-09 核可方向；required 項目未完成前不得合併。
  - **舊資料異常（R-1）**：
    - 斷號、批數多於 bpt 的舊資料原樣沿用舊算法，可能沒有末批補足，或每批只買 1 股。
    - `batch_no` 小於 1 的列在讀取時就 raise：`/today`（含未確認路徑）、`/rebalance`、全部出清、未確認時的資金確認都回 500，也就是排程台頁無法載入、全部出清無法使用；已確認的 `/today` 在失敗前可能已經 commit 結算。這是現況就有的行為，不是 N-207 引入的。
    - 部署前盤點發現就停止部署，不以揭露代替（N-207 §9 STOP-1；回報內容依 RC-12）。
  - engine 輸入與帳冊清單分開，以單一函式守住。
  - **`/today` 批次表的呈現改變（R-7）**：
    - 被排除的四類批次（D3 第 6 點）不再出現在 `/today` 的批次快照（`_snapshot_rows` 只看 engine 輸入），改在名單入口呈現。
    - 只要有被排除的批次，`/today` 就有一行由 API 層組出的常駐揭露，依類別列出數量，指向名單頁，不得收合。
    - 第 (1)、(4) 類要明列；第 (2)、(3) 類只列數量（第 (2) 類的處理：風控 2026-11-09 確認（見 work/reviews/2026-11-09-ADR0043修訂一單項確認與N209Q2裁示-風控.md））。
    - 若沒有揭露，使用者可能誤以為待生效標的不在名單內，或以為不需要 REBALANCE。
  - **「規則已全數評估」的範圍（R-8，範圍描述已更正）**：
    - 下列標的的 planned 批次被排除在輸入外，R 系列對它們沒有評估：
      - 已停止而且沒有 open 的標的：整檔不在輸入內；
      - **已停止但同時有 open 與 planned 的標的**：open 仍在輸入，engine 照常對該檔跑 S、P，`every_symbol_evaluated` 不會因此變 false，但 planned 沒有經過 R 系列評估；
      - 待生效的標的：整檔新代號，或已終結舊輪之後的新輪。
    - 已停止、有 open 但沒有 planned 的標的沒有 planned 被排除，不受影響。
    - 上述情況下，engine 的旗標可能為 true；`evaluate_today` 一律把它判為 false，所以原句「今日規則已全數評估，無任何規則命中，未產生指令。」不會單獨出現。
    - 代價：這些日子不顯示「無命中」句，由 R-7 的揭露行說明。
  - **已停止、沒有 open 的標的，S1 不會被評估（風控 2026-11-09 RC-2）**：
    - 已停止、沒有 open 的標的整檔不在 engine 輸入內。S1「站回 25MA 恢復」與資料缺漏警示都不會對它評估，暫停狀態維持到重新納入輸入為止（engine 只對輸入中有批次的標的逐檔評估：`engine.py:1201-1203`、`:1215`；資料缺漏 `:1218-1233`；S1 恢復 `:1236-1255`）。
    - 方向保守：該檔的 R 系列本來就不評估。
    - 名單頁不得把這種標的的 S1 狀態呈現成當日評估的結果。
    - 這一點屬 J-8「以 `engine_batches` 過濾」的承載範圍。
  - **甲案屬放寬 #121（R-9）**：資金確認也能解開閘，而 confirm 的 TD 只依提交數字、不看持股。CEO 以 #123 明示同意（D6 第 6 點）。
  - **以 API 重送資金確認（R-10）**：會同時解開閘並以提交數字覆寫現金，TD 不看持股；誤把總資產當成現金填入時，鐵律①的現金底線預算會被灌大。首次確認後畫面上沒有確認入口，所以這條路徑只剩 API。以 D6 第 8 點的字面約束揭露；是否拒絕或警示，由 TA 另案評估。
  - **組合凍結的殘留（R-12）**：資料落後的那幾天，名單入口已放行而 engine 仍凍結，比 FR-40 的字面寬，但不增加買進。Q-C11 須由 CEO 在 accepted 之前明示。
  - **啟用檔數大於 n_targets 的既有資料（R-14）**：
    - 每檔仍以 TD ÷ n_targets 計算，全部進場時投入會超過 TOTAL_DEPLOY（只受現金底線限制），屬突破風險上限。
    - N-207 的名額檢查只擋新寫入，擋不到既有資料。
    - 部署前盤點發現即停止部署，回報 CEO 與 TA，不得只靠揭露上線（N-207 §9 STOP-2）。FR-41 的揭露句要寫明這項後果。
  - **既有高波動標記（R-13）**：部署當下即放寬 P3 減碼門檻；列數大於 0 時停止部署，由 CEO 明示（D7 第 6 點）。
  - **上線相依**：N-207 依 R-17 要等 N-209 合入，排程因此多一個前置。
  - 並發評估仍可能為剛停止的標的出一張 R1（FR-10，揭露）。
  - 戳記閘有 ABA 殘留，含已解開的閘重新關上（D6 第 7 點，方向是不開）。
  - 日曆窗口在資料不足或缺 bar 時，會雙向偏離真實窗口（D8 第 4 點）。
  - 確認型操作遇到並發變動時，使用者要重新預覽。
  - store.py 共用的批次讀取 helper（`_BATCH_SELECT`、`_row_to_batch`）加欄位，會碰到 N198-T5 與 ADR-0041 T27 的差分基準，只做加法。
  - 部署回滾到舊版時，如果舊版仍有整列寫回，新欄位會被洗掉。所以 N-207 與 ADR-0041 的欄位化寫入綁在一起。
- **被約束**：
  - 名單路徑只能寫 `playbook_symbols` 的自有欄位、`playbook_batches` 的新輪 INSERT、`playbook_roster_log` 的 INSERT；
  - engine 只准改 `planned_batch_shares`，而且以 C-B11 範圍判定生效（J-9：CEO 核可）為前提；
  - engine 之外改變 R、S、P 結果或股數的過濾或後處理，依 J-6 視同改 engine；
  - 日後要「改 `batches_per_target`」時處理既有輪次，或把防守模式納入凍結，各自另立 ADR。

## 待決

- **CEO**：
  - 本 ADR 核可，**須明示包含 ADR-0034 補充四**（J-9）；
  - **Q-C11（FR-40 凍結判定依據與資料落後殘留）：必須在本 ADR 改為 accepted 之前由 CEO 明示（風控 R-12）**。coordinator 已暫定採 TA 建議，但暫定不能作為 accepted 的前提；這一項不擋 proposed 落檔；
  - 部署前盤點若觸發 STOP-1～4，由 CEO 裁決（N-207 §9）。
- **風控**：
  - D3 第 7 點與 ADR-0034 補充四的單項確認：風控 2026-11-09 確認（見 work/reviews/2026-11-09-ADR0043修訂一單項確認與N209Q2裁示-風控.md）；
  - 全部新字面的逐字定稿（第二節 F 表與 R-16）；
  - 確認 D3 第 6 點第 (2) 類的處理、D6 第 7 點的「重新關上」面向，以及 R-8 採 (a)：風控 2026-11-09 確認（見 work/reviews/2026-11-09-ADR0043修訂一單項確認與N209Q2裁示-風控.md）。
- **data-engineer**：台股代號的形狀規則（N207-C12）。
- **devops-sre／data-engineer**：部署前唯讀盤點（N-207 規格 §9）。
- **tech-architect**：另案評估「已有 open 批次時重送資金確認」是否拒絕或警示（R-10 suggested）。
- **tech-writer**：風控單項確認後，落檔本 ADR（proposed）與 ADR-0034 補充四（proposed）；CEO 核可後，依 J-10 加檔頭註記。
