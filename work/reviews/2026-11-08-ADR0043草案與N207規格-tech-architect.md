# ADR-0043 草案、N-207 實作規格、風控審查清單

- 審查者：tech-architect
- 日期：2026-11-08
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**完成。** ADR-0043 草案（proposed，含 D1～D9）、N-207 實作規格（N207-C1～C16、N207-T1～T22，全部 BLOCKING）、給風控的審查清單都已產出，全文在下方三個區塊。我只讀了文件與程式，沒有修改或新增任何檔案。

- **Q-T11（戳記閘與 confirm-rules）**：建議採甲，也就是任何一次 TOTAL_DEPLOY 寫入（REBALANCE 或資金確認）都解開閘，和 PM 的 Q-C12 預設相同。理由有三：
  - 閘只會從關變成開，不會倒退；
  - REBALANCE 與 confirm 都不用改；
  - 只認 REBALANCE（乙或丙）的話，以目前沒有 REBALANCE 畫面入口的狀況，首次上線只用 UI 會永遠解不開閘。
  
  甲和 #121「等 REBALANCE」的字面有差異，所以要 CEO 明確選擇。乙、丙、丁三案的利弊列在 ADR D6。
- **Q-T12(a) 窗口切點**：建議窗口為 [季末最後交易日 L 的 13:30，下季第一個交易日 F 的 13:30)，以 Asia/Taipei 時間判定，含起點、不含終點。13:30 沿用 `TW_POLICY.session_close`，不另立常數。我證明了交易日曆退回「只看週一到週五」時，系統算出的窗口只會比真實窗口窄，不會變寬；唯一例外是某個真實交易日在已觀測範圍內整天缺 bar。替代方案是終點改在 F 當天 00:00，交給 CEO 選。
- **Q-T12(b) 凍結期間能否在鎖內判定**：可以。`emergency_until` 與 `freeze_until` 都存放在 `playbook_state`，鎖內一句 SELECT 就能讀到。判定依據是台北日期 ≤ until。性質是：名單入口拒絕時，engine 一定也處於凍結；殘留只有一種，資料落後的那幾天名單入口已放行、`/today` 仍顯示凍結。這不會造成買進，因為 engine 照樣壓住 R 系列，新批次也還在閘後。
- **engine 輪內計算**：只改 `planned_batch_shares` 的函式本體，簽名與呼叫點都不變。第 1 輪的位移量固定是 0，所以只要輸入全是第 1 輪，新舊兩版逐式相同，斷號或從 0 起編的舊資料也一樣。差分測試兩層，都至少 300 組 seed：函式層，以及完整 `evaluate()` 層。
- **ADR-0034 C-B11**：判定為 N-168 的範圍約束，比照 ADR-0035 補充六。同樣判定 N172-C3、ADR-0041「限制」、N198-C1 中的 engine 零 diff 各屬該單的範圍。ADR-0034 補充四全文附在 D3。生效前 qa 依字面仍判 BLOCKING。

讀碼時另外發現四件事，都已寫進規格：

1. **整列寫入會洗掉新欄位**：`save_batch` 目前是整列 `INSERT OR REPLACE`（`store.py:916-947`）。若 base 仍有這種寫法，新加的 `batch_round` 與 `entry_gate` 會被洗回預設值。所以 N-207 要求 base 必須已含 ADR-0041 的欄位化寫入；做不到就停下回 TA（N207-C6）。
2. **兩處語意改變要送風控**：engine 輸入改為只收生效中的批次後，
   - `/today` 的批次表不再列出已停止標的的 planned 批次、待生效批次與舊輪批次；
   - 「規則已全數評估」的範圍縮為生效中的標的。
3. **PRD FR-28 前提有誤**：cap-1 揭露句不是寫死「5 檔」，而是 `{n_targets}` 參數（`app/api/playbook_cap1_wording.py:58`、`:109`）。改法要依 ADR-0031 C-1 增列參數。
4. **兩個「待生效」會混淆**：高波動標記的「待生效」與戳記閘的「待生效」用同一個詞，請風控分開定字面。

## 二、各部門回報

- **tech-architect**：
  - 讀過 TA 評估、PRD v2、決策包 #119～#122、ADR-0001、0034、0035、0040、0041、0042、0031（grep），以及 N-197a 規格段；
  - 讀碼範圍：engine、store、service、calendar、freshness、cap1 wording；
  - 產出下方三份文件並回答 Q-T11、Q-T12。唯讀，沒有改任何檔案。
- **其他部門**（product-manager、risk-compliance-officer、dev-lead、qa-reviewer、tech-writer、devops-sre、data-engineer 等）：本次沒有參與。
  - 風控尚未審：FR-42 規則語意變更、C-B11 範圍判定、14 句字面都在清單三，合併前必經風控。
  - qa 尚未審。

## 三、驗證

- **讀過的依據**：
  - `/home/user/AICompany/work/reviews/2026-11-08-N207架構評估-tech-architect.md`
  - `/home/user/AICompany/work/stock-desk-排程台標的設定-PRD.md`
  - `/home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`（#119～#122）
  - `/home/user/AICompany/work/reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md`（3.8～3.9）
  - ADR-0001、0034、0035、0040、0041、0042 的相關段落
- **讀過的程式**（只讀，未執行；主 checkout，N-177a 以後的單都還沒合入，行號會漂移）：
  - `engine.py`：`:186-215`、`:385-412`、`:738-750`、`:982-1017`、`:1093-1121`、`:1124-1309`
  - `store.py`：`:68-241`、`:858-1055`
  - `service.py`：`:536-566`、`:1809-1933`、`:1987-2035`、`:2123-2240`
  - `app/data/calendar.py` 全文；`app/data/freshness.py`：`:61-145`
  - `app/api/playbook_cap1_wording.py`（grep）
- **沒有查證的部分**：
  - N-197a、N-177a、N-198 合入後的實際名稱與行號；
  - 交錯分析都是讀碼推論；
  - 窗口「只會變窄」的性質是推導，要由 N207-T12 實證；
  - 台股代號形狀空間。
- **需要 CEO 親自確認**：下方「需要 CEO 決定」各項，Q-C12 優先。
- 沒有讀 `.env`，沒有碰 `data/*.db`，沒有執行任何指令。

## 四、下一步

1. **CEO**：回覆下方決定清單，第 1 項 Q-C12 影響 D6 與 N207-T6 定稿。
2. **risk-compliance-officer**：依清單三審查，含 14 句字面、FR-42 規則語意變更、C-B11 範圍判定、待生效揭露、兩處非字面的語意改變、甲案是否屬放寬。**product-manager** 依 ADR 修 PRD v3：
   - Q-T12 的精確切點；
   - FR-28 前提更正；
   - `/today` 批次表的變化；
   - 「規則已全數評估」的範圍。
3. **tech-writer**：風控通過後落檔 ADR-0043（proposed）與 ADR-0034 補充四。**data-engineer**：查證代號形狀規則，並與 devops-sre 一起準備部署前唯讀盤點（規格 §9 列項）。**coordinator**：登錄先後順序 R2 → N-196 → N-197a → N-177b → N-198 → N-207。

## 需要 CEO 決定

1. **Q-C12／Q-T11：待生效閘由誰解開**（必答）
   - **甲（TA 建議，即 PM 預設）**：任何一次 TOTAL_DEPLOY 寫入都解開，REBALANCE 或資金確認都算。首次流程「設定標的 → 確認資金」一步到位。與 #121 字面有差異。
   - **乙**：只認 REBALANCE，以戳記比對加 source 判斷。之後若有一次資金確認，已解開的閘會再關上。不建議。
   - **丙**：只認 REBALANCE，而且只開不關。要改 N-197a 的 REBALANCE 寫入交易，並重送風控。首次上線也必須跑 REBALANCE，但目前沒有畫面入口。
   - **丁**：丙，加上首次設定不套用閘。
   - 附帶：首次設定的標的是否也套用閘？**TA 建議一律套用**，單一規則，也可避免 `evaluate_today` 兩次讀批次之間的讀取偏斜。
2. **Q-T12(a)：窗口終點**
   - **E2（建議）**：下季第一個交易日 13:30。
   - **E1**：下季第一個交易日 00:00。
3. **Q-C11／FR-40：組合凍結的判定方式**。是否同意以台北日期 ≤ `emergency_until` 或 `freeze_until` 判定，並接受「資料落後的那幾天會放行」的殘留？**建議同意。** 另外，防守模式不在 FR-40 範圍；高波動標記依 FR-40 字面不受凍結限制。
4. **C-B11 範圍判定**：隨 ADR-0043 核可，同時核可 ADR-0034 補充四。
5. **REBALANCE 的觸發方式**（PRD 風險 6）：閘要靠 REBALANCE 解開，但目前沒有畫面入口。
   - (a) 由 CEO 直接呼叫 API，另附操作說明；
   - (b) 在 N-207 上線前另開單做 REBALANCE 入口。
   - 選甲時首次上線不受影響，但季度換標的仍需要 REBALANCE。
6. **FR-28 cap-1 揭露改法**：同單但獨立 commit（建議），或另案。兩者都要依 ADR-0031 C-1 增列參數，並由風控定字面。
7. **Q-C4～Q-C10 的 PM 預設**：TA 對技術面沒有異議（Q-C10 已納入 D4），請 CEO 一次確認或推翻。

相關檔案：
- `/home/user/AICompany/work/reviews/2026-11-08-N207架構評估-tech-architect.md`
- `/home/user/AICompany/work/stock-desk-排程台標的設定-PRD.md`
- `/home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`
- `/home/user/AICompany/docs/adr/0034-stock-desk-出清時待結算R買單的處置.md`
- `/home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md`
- `/home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md`
- `/home/user/AICompany/docs/adr/0042-stock-desk-排程台結算的claim與動帳併入同一寫鎖交易.md`
- `/home/user/AICompany/docs/adr/0031-stock-desk-排程台與第1條並存揭露的組合點與邊界.md`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/calendar.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/freshness.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/api/playbook_cap1_wording.py`

---

### 交付 1：ADR-0043 草案全文

````markdown
# ADR-0043：stock-desk 排程台標的名單的表達、批次輪次與輪內股數、名單寫入交易、新標的戳記閘與季度窗口（補充 ADR-0035、ADR-0041、ADR-0042，不取代；判定 ADR-0034 C-B11 為 N-168 的範圍約束）

- 狀態：proposed
- 日期：2026-11-08
- 決策者：
  - tech-architect：草案；
  - risk-compliance-officer：審查（FR-42 規則語意變更、C-B11 範圍判定、全部新字面），待審；
  - CEO：#119～#122（2026-11-08）已裁方向；本 ADR 核可待定；Q-C12（D6）待選。
- 來源簡稱（皆在 `work/` 下）：
  - [TA-207]：`reviews/2026-11-08-N207架構評估-tech-architect.md`
  - [PRD]：`stock-desk-排程台標的設定-PRD.md`（draft v2）
  - [N203]：`reviews/2026-11-08-N203排程台標的寫入路徑查證-dev-lead.md`
  - [TA-197]：`reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md`（3.8～3.9，N-197a 規格與 `TotalDeployStamp`）
  - [決策包]：`dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`（#119～#122）
- 適用範圍：僅 product/stock-desk。路徑相對於 `apps/stock-desk/backend/`。
- 標註：
  - 行號是 2026-11-08 主 checkout 的快照。N-177a、N-195、N-196、N-197a、N-177b、N-198 都還沒合入，行號會漂移，抽驗請以內容定位。
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
3. **既有不變式（本 ADR 不得破壞）**：
   - ADR-0035：批次永不重置。K1／K2 決策身分鍵含 `(symbol, batch_no)`。G1 的 SQL 零 diff（補充六）。
   - N172-C11：不 UPDATE、不 DELETE 既有指令列。
   - ADR-0041：結算以外的批次寫入者只能做欄位化寫入，不得寫股數；`app/` 內不再以 `INSERT OR REPLACE` 整列寫批次。
   - ADR-0042：唯一的結算進入點是 `claim_and_settle`。
   - N-197a：TOTAL_DEPLOY 三個鍵（TD、set_at、source）的原始字串戳記；寫入者只有 `set_capital`（confirm）與 `set_total_deploy`（REBALANCE）。
4. **engine 現況的阻礙**：
   - `planned_batch_shares` 以 `batch_no < batches_per_target` 判斷末批（`engine.py:208`）。新一輪的第 4 批會被誤判為末批，吸收整檔餘額。
   - 要支援新一輪，就得改 engine 這個函式，碰到 ADR-0034 C-B11「R、S、P 的引擎邏輯不改」。
5. **REBALANCE 的 docstring**寫「manual by design……engine has no calendar of quarters」（`service.py:1817-1819`）。季度窗口是新概念，但只用在名單操作；REBALANCE 本身不受窗口限制，維持零 diff。

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
| 季度窗口 | **日曆窗口純函式，API 層與鎖內都強制** | 符合 #120 | 日曆退回週一到週五判定的已知限制 | 低 | **採用（D8，CEO #120）** |
| | 使用者宣告換季 | 比照 REBALANCE | 不符合 #120 | — | 否決 |

## Decision（決策）

### D1：名單與「啟用」的單一定義
1. 名單 = `playbook_batches` 中的 distinct symbol，是唯一的真實來源，不另立名單表。名單列一律不刪。
2. 「啟用」= 在名單內，而且 `entry_stopped = 0`（`playbook_symbols` 沒有該列，視同 0）。
   - S1 暫停、S2 黑名單、待生效中的標的仍算啟用，占名額，名額不補。
3. **啟用檔數** = 名單中啟用的 symbol 數。這是唯一的計數定義，名單入口、FR-24 的 confirm-rules 檢查、cap-1 揭露（FR-28）都引用同一個函式。
4. **今日可進場檔數** = 啟用中、沒有 S1 暫停、不在 S2 黑名單，而且在 D3 第 6 點的 engine 輸入裡至少有一筆 planned 批次的 symbol 數。直接沿用 engine 輸入函式，不另寫第二份條件。
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
5. **engine 輪內計算（CEO #119，規則語意變更，送風控）**：
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
   - **等價性**：所有批次都是第 1 輪時，`round_batches == symbol_batches`、`offset == 0`，整個函式與修改前逐式相同。斷號、從 0 起編、批數多於 bpt 的舊資料也一樣。由 N207-T1、T2 的差分測試（各至少 300 組 seed）釘住。
   - **語意變更只發生在第 2 輪以後**：
     - 輪內序位小於 bpt 的批次，依每批金額計算；
     - 輪內末批吸收「整檔配額減去同一輪已占用」；
     - 舊輪批次不計入。
   - **不變的部分**：
     - 每批金額仍是 TD ÷ n_targets ÷ bpt，取「評估當下」的 TD，不是開輪當時的 TD；
     - R1、R2、R3、M1 的條件與順序不變；
     - S、P 系列一行都不改；
     - rule_summary 的「第 {batch_no} 批」仍由 `batch_no` 呈現，新輪自然顯示為第 4～6 批（FR-43）。
6. **engine 輸入的單一定義**：在 service 內新增一個純函式 `engine_batches(book, *, roster, stamp)`，`evaluate` 與 `evaluation_marks` 收同一個回傳物件。批次 b 被納入，當且僅當：
   - `b.status == "open"`（任何一輪；賣出類評估永不被名單狀態壓住），**或**
   - 標的未停止、`b.batch_round` 等於該檔最大輪次，而且（`b.status != "planned"`，或 `entry_gate_open(b.entry_gate, stamp)`）。
   - 推論：
     - 舊資料（未停止、全是第 1 輪、`entry_gate` 為 NULL）時，輸入與修改前逐列相同，順序不變；
     - 已停止的標的只剩 open 批次；
     - 待生效的新輪整輪不在輸入內。
7. **ADR-0034 C-B11 的範圍判定**（比照 ADR-0035 補充六）：
   - **判定**：ADR-0034 附錄 C 的 C-B11「R、S、P 的引擎邏輯不改」，以及「被約束」中的同一句，判定為 **N-168 的範圍約束**，不是 engine 永久不得修改的架構決策。
   - **理由**：
     - C-B11 列在「B-2a 約束清單（交 dev-lead）」，目的是防止 N-168 在實作 B-2a 時順手改動 R、S、P，讓「照常結算、停損停利照常評估」的語意可以驗證；
     - N-168 已於 9253032 合併；
     - 先例：ADR-0035 補充六對 `settle()` 零 diff的判定，以及 ADR-0040 補充一 E-2 對 C-B8 與 C-B11 關係的判定。
   - **同一判定適用於**：
     - ADR-0035 附錄 B 的 N172-C3（N-172a 的範圍）；
     - ADR-0041「限制」與「與其他 ADR 的關係」中的「engine 零 diff（C-B11）」（N-177a 的範圍）；
     - ADR-0042 N198-C1 的 engine.py 零 diff（N-198 的 diff 範圍）。
     - ADR-0040 Decision 12 的限定範圍豁免在本判定之前成立，不需要撤回。
   - **仍然有效、日後改 engine 必須遵守的不變式**：
     - ADR-0034 B-2a 的語意：出清當時未結算的買單照常結算並標示；停損停利照常評估；C-B8 engine 只照抄標示、不做判斷；C-B10 不自動產生 EMERGENCY；
     - engine 不讀寫 TOTAL_DEPLOY 戳記、名單狀態或任何 I/O；
     - S、P 系列不因名單狀態而被壓住。
   - **日後任何改動 R、S、P 判斷邏輯或股數計算的變更，仍然要有自己的 ADR 並經風控審查；不得把本判定讀成「engine 從此開放修改」。**
   - 本判定自 ADR-0034 補充四落檔起生效。生效以前，qa-reviewer 依 C-B11 字面對 N-207 的 engine diff 仍應判 BLOCKING，所以 N-207 合併以本判定生效為前提。
   - **建議的 ADR-0034 檔頭補充四全文**（由 tech-writer 落檔，風控逐字確認）：
     > 補充四（tech-architect 2026-11-08，回應 N-207 與 CEO #119）：附錄 C 的 C-B11 與「被約束」中「R、S、P 的引擎邏輯不改（C-B11）」一句，判定為 N-168 的範圍約束，不是 engine 永久不得修改的架構決策（理由：該條是為 N-168 實作 B-2a 時的範圍而設，N-168 已於 9253032 合併；先例是 ADR-0035 補充六）。仍然有效的不變式：B-2a 的結算與標示語意、C-B8、C-B10，以及 S、P 系列不因名單狀態被壓住。日後任何改動 R、S、P 判斷邏輯或股數計算的變更，仍然要有自己的 ADR 並經風控審查；不得把本判定讀成「engine 從此開放修改」。N-207 對 `planned_batch_shares` 的改動由 ADR-0043 D3 承載並經風控審查。本判定自本補充落檔起生效；生效以前，qa-reviewer 依本 ADR 字面仍應判 BLOCKING。本檔原文不改（比照補充一～三先例，CEO 可推翻改為另立取代 ADR）。

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
| 首次設定（批次表為空） | 不受限（Q-C6 預設，CEO 可推翻） | 拒絕 | 是 | 是 | 每檔第 1 輪，bpt 批 | 有 |
| 停止新進場 | 不受限 | 允許 | 是 | 否 | 無 | — |
| 重新加入 (i)(ii) | 受限 | 拒絕 | 是 | 否 | 無 | — |
| 開新輪 (iii)(iv) | 受限 | 拒絕 | 是 | 否 | bpt 批 | 有 |
| 季度提交 | 受限 | 拒絕 | 是 | 新增組 | 新增組第 1 輪；保留組中逐項確認的開新輪 | 有 |
| 高波動標記 | 不受限（Q-C8 預設） | 允許（FR-40 未列） | 是 | 否 | 無 | — |

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

### D6：新標的戳記閘（CEO #121；Q-C12 待 CEO 選）
1. `playbook_batches` 新增加法欄位 `entry_gate TEXT`：
   - NULL 表示無閘（既有列，以及續用的 planned）；
   - 非 NULL 是新批次 INSERT 當下、鎖內讀到的 `TotalDeployStamp` 的標準編碼：`json.dumps([td, set_at, source], ensure_ascii=False, separators=(",", ":"))`，鍵不存在時為 null。
   - 只在 INSERT 時寫一次，之後任何路徑都不更新。同一輪的各批戳記相同。
2. **判定**：`entry_gate_open(recorded, current)`，與 `TotalDeployStamp` 放在 store.py 同一處，只有一份定義：
   - recorded 為 NULL：開；
   - 否則把 recorded 解碼為 `TotalDeployStamp`，與 current 比較 NamedTuple 是否相等；**不相等就開**（預設採甲）。
   - 只比對原始字串，不比時間先後，比照 ADR-0035 補充五。
3. **current 的來源**：與交給 engine 的 `portfolio` 取自同一次 `_state_map()` 讀取。這樣閘一打開，engine 用的 TD 必然是解開閘的那個新 TD。
4. REBALANCE 失敗、`REBALANCE_BLOCKED` 或 `REBALANCE_SUPERSEDED` 時，戳記不變，名單保留待生效，不作廢（AC-57）。
5. 首次設定也套用閘（TA 建議）。理由：
   - 只有一條規則；
   - `evaluate_today` 在 `:2158` 與 `:2199` 兩次讀批次之間若插入首次設定，沒有閘的話，新 symbol 會進 engine 輸入但日線沒有載入，出現假的資料缺漏警示。
6. **Q-T11／Q-C12 的選項**（CEO 選定後本條定稿）：

| 方案 | 內容 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| **甲（TA 建議，即 PM 預設）** | 任何一次 TD 寫入（REBALANCE 或 confirm）造成戳記改變就解開 | 只開不關；REBALANCE、confirm、N-197a 零 diff；首次流程「設定標的 → 確認資金」一步到位；兩種寫入都產生新宣告的 TD，符合「以新 TD 起算」的意旨 | 與 #121 字面有差異（要 CEO 明示）；以 API 重送資金確認也會解開閘，而且同時覆寫現金 | 低 |
| 乙 | 戳記改變，而且目前 source 等於 `REBALANCE_SOURCE` 才開 | 符合字面；零新寫入者 | 會倒退：REBALANCE 之後若再有一次 confirm，閘會重新關上，同一輪中途可能又變回待生效；首次上線要多跑一次 REBALANCE，但目前沒有 UI 入口 | 中 |
| 丙 | 只認 REBALANCE，而且只開不關：在 N-197a 的 `set_total_deploy` 同一交易內，另寫只增不改的 REBALANCE 寫入紀錄，閘依「INSERT 之後是否有 REBALANCE 紀錄」判定 | 符合字面且只開不關 | 推翻 N197a-C1、C2（diff 範圍與語句序列），要重送風控；首次上線同樣要 REBALANCE | 中 |
| 丁 | 丙，加上首次設定不套用閘 | 首次流程不受影響 | 丙的全部代價，加上第 5 點的讀取偏斜殘留 | 中 |

7. **ABA**：三個鍵恰好回到原值（時鐘倒退，而且 TD、source、set_at 微秒都相同）時，閘不會開。方向是不開（保守），殘留同 N-197a。

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
5. 畫面上「N 月 N 日起」的日期以 `calendar.next_trading_day(changed_on)` 呈現（有日曆退回判定的已知限制）。判定只看第 2 點，不看這個日期。
6. 既有列中 `high_volatility=1` 而 `changed_on` 為 NULL 的，部署當下立即生效，屬行為變更，要靠部署前唯讀盤點與揭露處理。

### D8：季度窗口與組合凍結的判定（CEO #120；回答 Q-T12）
1. **窗口純函式**（唯一定義，放在新模組 `app/playbook/roster.py`）：`quarter_window(*, now: datetime, calendar: TradingCalendar) -> QuarterWindow`。
   - `now` 必須帶時區，naive 就 raise。先轉為 Asia/Taipei 時間 t。
   - L(q) = 季度 q 內依 `calendar.is_trading_day` 判定的最後交易日；F(q) = 季度 q 內第一個交易日。
   - **窗口 W(q) = [L(q) 13:30, F(q+1) 13:30)**，以 Asia/Taipei 判定，含起點、不含終點。13:30 取自 `app/data/freshness.py` 的 `TW_POLICY.session_close`，不另立常數。
   - 等價說法：「最近一個已收盤的交易日，是它所屬季度的最後交易日」。
   - 回傳開窗與否、起訖時刻、L 與 F（供訊息使用）。
2. **切點的理由**：
   - 起點：季末最後交易日的收盤時刻，就是 #120「收盤後」的字面。
   - 終點：data_date = F 的評估，只能在 F 收盤之後開始，所以「下季第一個評估日之前」的最晚時刻是 F 的 13:30。
   - 替代方案 E1 把終點改為 F 的 00:00，F 當天盤中就不能再改名單，交 CEO 選。
   - 不採「下季第一個排程日（週二或週四）」：評估每個交易日都在跑（S、P 每天評估），排程日不等於評估日，而且會把窗口拉長。
3. **日曆來源**：在鎖外以 `evaluate_today` 同一個指數載入器建立 `TradingCalendar`，以值傳入鎖內，鎖內只呼叫純函式。載入失敗時，日曆為空，全部走週一到週五判定。
4. **只會變窄的性質**（推導，由 N207-T12 實證）：
   - 已觀測範圍內的判定是精確的；範圍外以週一到週五判定，只會多算交易日。所以算出的 L 不會早於真實的 L，算出的 F 不會晚於真實的 F，算出的窗口必然包含在真實窗口之內，也就是只會比真實窗口窄、不會變寬。
   - 唯一例外：某個真實交易日在已觀測範圍內整天缺 bar（指數與全部標的都缺）。這種情況要揭露。
5. **強制點**：
   - API 層（預覽與確認）；
   - 寫鎖內：以鎖內讀到的時鐘重算。預覽到確認之間跨過切點，就拒絕、零寫入。
6. **組合凍結（Q-T12(b)：可以在鎖內判定）**：
   - 鎖內同一句 SELECT 讀 `emergency_until` 與 `freeze_until`；
   - 純函式 `portfolio_frozen(*, emergency_until, freeze_until, today_tpe)`：任一者不為 None 且 `today_tpe <= until`，就判為凍結。
   - **性質**：engine 以 `data_date <= until` 判定凍結，而 data_date ≤ 台北今日。所以名單入口拒絕時，engine 一定也處於凍結，不會多擋。
   - **殘留**：資料落後的那幾天（until < 台北今日，但 data_date ≤ until），名單入口已放行、`/today` 仍顯示凍結。這期間 engine 照樣壓住 R 系列，新批次也在閘後，不會造成買進。
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
| ADR-0034 C-B11（及「被約束」同句） | **範圍判定** | 屬 N-168 的範圍約束，見 D3 第 7 點；以 ADR-0034 補充四落檔。B-2a、C-B8、C-B10 不受影響 |
| ADR-0035 不變式 | 補充（加強） | 「永不重置」加強為「新批次只用從未用過的 `batch_no`，以一般 INSERT 寫入」。K1／K2 因 `batch_no` 不重用，新輪不會與舊決策撞鍵。G1 的 SQL 零 diff |
| ADR-0035 N172-C3 | 範圍判定 | 同 D3 第 7 點，屬 N-172a 的範圍 |
| ADR-0035 補充五 | 沿用 | 只比對原始字串、不比時間先後 |
| ADR-0040 Decision 9 | 沿用 | `evaluation_marks` 收「engine 實際收到的輸入」，也就是過濾後的 `engine_batches` |
| ADR-0040 Decision 12 | 不變 | 既有的限定範圍豁免不需要撤回 |
| ADR-0041 | 補充 | 新增一種允許的批次寫入者：新輪 INSERT（planned、股數走 DEFAULT），不屬於動帳；不得有整列寫回（新欄位會被洗回預設值）。R-4′ 維持。「engine 零 diff」屬 N-177a 的範圍 |
| ADR-0042 | 補充 | 名單路徑不新增任何 claim 或動帳呼叫點；`claim_and_settle` 仍是唯一的結算進入點。N198-C1 的 engine 零 diff 屬 N-198 的範圍 |
| N-197a（[TA-197]） | 相依 | 沿用 `TotalDeployStamp` 的單一定義，不重新定義。N197a-C5「`confirm_rules` 零 diff」屬 N-197a 的範圍；N-207 在 N-197a 合入後，為 FR-24 修改 `confirm_rules`，`set_capital` 仍零 diff。N197a-C6 不受影響（名單不寫現金） |
| ADR-0033 | 不衝突 | 只讀 `emergency_until`；C-9 不儲存 |
| ADR-0031 | 補充（待風控） | FR-28 依 C-1「可依此增列」，在 `compose` 增列 keyword-only 的 `enabled_targets` 參數；字面由風控定稿；C-5 同一份回應的來源要求，擴及啟用檔數 |
| ADR-0024 | 不變 | 代號的形狀規則放在名單模組，不放進資料層准入 |
| REBALANCE docstring | 不衝突 | 季度窗口只用在名單操作；REBALANCE 維持手動、不受窗口限制、零 diff |

## Consequences（後果）

- **好處**：
  - N203 §1.4 的 8 點風險都有結構性的對應；
  - REBALANCE、confirm 的寫入、結算、`commit_evaluation`、G1 零 diff；
  - `batch_no` 永不重用，「每個 (symbol, batch_no) 一生最多一筆 executed R1」比現在更強；
  - 舊資料上 engine 與 `/today` 逐值不變（T1、T2、T21）。
- **壞處與代價**：
  - **規則語意變更**：第 2 輪以後的股數計算改變，須經風控通過才可合併。每批金額取評估當下的 TD，新輪開始之後若 REBALANCE 改變了 TD，同一輪各批的金額基準會不同（與第 1 輪現況一致）。
  - engine 輸入與帳冊清單分開，以單一函式守住。
  - **`/today` 批次表的呈現改變**：已停止標的的 planned 批次、待生效批次、舊輪批次不再出現在 `/today` 的批次快照（`_snapshot_rows` 只看 engine 輸入），改在名單入口呈現。要送風控與 PM。
  - **「規則已全數評估」範圍縮小**：`every_symbol_evaluated` 的範圍變成「交給 engine 的標的」。已停止而且沒有 open 的標的、整檔待生效的標的不計入。要送風控。
  - 並發評估仍可能為剛停止的標的出一張 R1（FR-10，揭露）。
  - 戳記閘有 ABA 殘留（同 N-197a，方向是不開）。
  - 日曆窗口有缺 bar 的例外，見 D8 第 4 點。
  - 凍結判定在資料落後的那幾天會放行（D8 第 6 點）。
  - 確認型操作遇到並發變動時，使用者要重新預覽。
  - store.py 共用的批次讀取 helper（`_BATCH_SELECT`、`_row_to_batch`）加欄位，會碰到 N198-T5 與 ADR-0041 T27 的差分基準，只做加法。
  - 部署回滾到舊版時，如果舊版仍有整列寫回，新欄位會被洗掉。所以 N-207 與 ADR-0041 的欄位化寫入綁在一起。
  - 第 D6 點甲案下，以 API 重送資金確認會同時解開閘與覆寫現金，要揭露。
- **被約束**：
  - 名單路徑只能寫 `playbook_symbols` 的自有欄位、`playbook_batches` 的新輪 INSERT、`playbook_roster_log` 的 INSERT；
  - engine 只准改 `planned_batch_shares`，而且以 C-B11 範圍判定生效為前提；
  - 日後要「改 `batches_per_target`」時處理既有輪次，或把防守模式納入凍結，各自另立 ADR。

## 待決

- **CEO**：
  - 本 ADR 核可；
  - Q-C12（D6 甲乙丙丁）；
  - 窗口終點 E2 或 E1；
  - FR-40 的凍結判定依據；
  - C-B11 範圍判定（ADR-0034 補充四）；
  - REBALANCE 的觸發方式（PRD 風險 6）；
  - FR-28 同單或另案。
- **風控**：FR-42 規則語意變更、C-B11 判定、全部新字面、`/today` 批次表與「規則已全數評估」兩處語意變更、甲案是否屬放寬。
- **data-engineer**：台股代號的形狀規則（N207-C12）。
- **devops-sre／data-engineer**：部署前唯讀盤點（N-207 規格 §9）。
- **tech-writer**：風控通過後落檔本 ADR（proposed）與 ADR-0034 補充四。
````

---

### 交付 2：N-207 實作規格

````markdown
# N-207 實作規格（排程台標的設定、季度換標的、新一輪、戳記閘、高波動接線）

- 依據：ADR-0043（proposed）；PRD v2（以 v3 為準）；CEO #119～#122。
- 負責：dev-lead（backend）、frontend-engineer（名單入口畫面）；qa-reviewer、qa-automation、qa-e2e 驗收；risk-compliance-officer 審 FR-42 與字面。
- 路徑相對於 `apps/stock-desk/backend/`。

## 0. diff 範圍（qa 以 `git diff <base> <head>` 逐檔核對）
- **允許**：
  - `app/playbook/store.py`：`_SCHEMA`（新稽核表與 trigger）；`_MIGRATIONS`（D2、D3、D6、D7 的加法欄位）；`_BATCH_COLUMNS`、`_row_to_batch`（加法）；`symbol_states`（加讀欄位）；新的名單讀寫方法；`entry_gate` 的編碼、解碼與判定（緊鄰 `TotalDeployStamp`）；接收 conn 的參數 helper（`active_params` 委派給它）；`portfolio_and_stamp()`（`portfolio_state()` 委派到同一個 parse helper）。
  - `app/playbook/models.py`：加法欄位與名單相關的新型別。
  - `app/playbook/engine.py`：**只有 `planned_batch_shares` 的函式本體**。
  - `app/playbook/service.py`：`evaluate_today`（engine 輸入、戳記、高波動接線）；`confirm_rules`（FR-24 前置檢查）；新的名單 service 方法；`engine_batches`。
  - `app/playbook/roster.py`（新檔，純函式）。
  - `app/playbook/wording.py`：新常數。
  - `app/api/playbook.py`：新端點；confirm-rules 的拒絕對映。
  - `app/api/playbook_cap1_wording.py`：只限 FR-28，而且依 CEO 決定。
  - frontend 名單入口、`types.ts`。
  - `tests/**`。
- **零 diff**：見 N207-C3。

## 1. Schema 與型別
- `playbook_batches`：`batch_round INTEGER NOT NULL DEFAULT 1`、`entry_gate TEXT`。
- `playbook_symbols`：`entry_stopped INTEGER NOT NULL DEFAULT 0`、`entry_stopped_on TEXT`、`high_volatility_prev INTEGER NOT NULL DEFAULT 0`、`high_volatility_changed_on TEXT`。
- `playbook_roster_log`：欄位依 ADR-0043 D9，另加 `playbook_roster_log_no_update`、`playbook_roster_log_no_delete` 兩個 trigger。
- `BatchState`：`batch_round: int = 1`、`entry_gate: str | None = None`。`SymbolState`：`entry_stopped: bool = False`、`entry_stopped_on: date | None = None`、`high_volatility: bool = False`、`high_volatility_prev: bool = False`、`high_volatility_changed_on: date | None = None`。
- `BatchSnapshot` 零 diff。

## 2. `app/playbook/roster.py`（純函式，只 import 標準函式庫、`app.data.calendar`、`app.data.freshness`、`app.playbook.models`；不 import store）
```python
def quarter_window(*, now: datetime, calendar: TradingCalendar) -> QuarterWindow: ...
def portfolio_frozen(*, emergency_until: date | None, freeze_until: date | None,
                     today_tpe: date) -> Literal["emergency", "s3"] | None: ...
def effective_high_volatility(*, value: bool, prev: bool, changed_on: date | None,
                              data_date: date) -> bool: ...
def symbol_shape_ok(symbol: str) -> bool: ...          # rule supplied by data-engineer
def roster_digest(*, op: RosterOp, facts: RosterFacts) -> str: ...   # sha256 of canonical JSON
def plan_change(*, op: RosterOp, facts: RosterFacts, params: RuleParams,
                window: QuarterWindow, frozen: str | None) -> RosterPlan | RosterRefusal: ...
def enabled_count(facts_or_book, roster) -> int: ...   # the one definition (ADR-0043 D1)
```
- `RosterFacts` 只含不隨時間變動的事實：範圍內各檔的 `entry_stopped`、高波動三欄、`(batch_no, batch_round, status)` 的有序清單；`n_targets`、`batches_per_target`；啟用檔數。
- 範圍：首次設定與季度提交是整份名單；其他操作是該檔加上全域計數。

## 3. store
- `roster_facts() -> RosterFacts`：唯讀，一個連線，供預覽與名單檢視使用。
- `apply_roster_change(op, *, expected_digest, calendar, clock) -> RosterWriteResult`：依 ADR-0043 D4 第 3 點執行。在鎖內呼叫 `plan_change`；摘要不一致就回 `RosterRefusal("preview_stale")`。
- `_INSERT_ROUND_SQL`（唯一定義）：`INSERT INTO playbook_batches (symbol, batch_no, status, batch_round, entry_gate, updated_at) VALUES (?, ?, 'planned', ?, ?, ?)`。
- `encode_entry_gate`、`decode_entry_gate`、`entry_gate_open`：緊鄰 `TotalDeployStamp`，各只有一份定義。
- `portfolio_and_stamp() -> tuple[PortfolioState, TotalDeployStamp]`：只呼叫一次 `_state_map()`。

## 4. service
- `engine_batches(book, *, roster, stamp) -> list[BatchState]`：依 ADR-0043 D3 第 6 點，純函式，不呼叫 store。
- `evaluate_today`：
  - `book = list_batches()`；
  - `portfolio, stamp = portfolio_and_stamp()`；
  - 在建 snapshot 之前，`states = symbol_states(data_date)`；
  - `inputs = engine_batches(book, roster=states, stamp=stamp)`；
  - `evaluate(batches=inputs, symbols=states, portfolio=portfolio, …)`；
  - `evaluation_marks(…, batches=inputs, …)`；
  - `build_market_snapshot(…, high_volatility=effective_high_volatility(…))`。
  - `:2158` 的日線載入範圍維持不變（所有批次的 symbol）。
- 名單方法：`roster_view()`、`roster_preview(op)`、`roster_commit(op, digest)`。
  - 預覽與確認都要在鎖外做代號驗證，並在 API 層判定窗口與凍結；
  - 日曆以 `evaluate_today` 同一個指數載入器建立；
  - 時鐘以建構子注入，預設 `datetime.now(UTC)`。
- `confirm_rules`：在任何寫入之前，若啟用檔數大於 n_targets，或批次表為空，就拒絕（FR-24）。`set_capital` 零 diff。

## 5. engine
- 依 ADR-0043 D3 第 5 點的程式改 `planned_batch_shares` 的本體；其他一行都不改。

## 6. API 與前端
- 每種操作都是預覽、確認兩步；確認必帶 `digest`。端點命名由 dev-lead 定。
- 拒絕原因以 `Literal` 回傳，每個原因對應一個 `wording.py` 識別名。
- 名單依代號升冪排序。
- 前端只呈現後端給的事實，不自行計算檔數、窗口或閘的狀態。

## 7. 約束（qa-reviewer 逐條檢查，全部 BLOCKING）
- **N207-C1 批次表不變式**：
  - `app/` 內沒有 `DELETE FROM playbook_batches`；
  - 沒有 `INSERT OR IGNORE`、`INSERT OR REPLACE`、`REPLACE INTO` 寫 `playbook_batches` 或 `playbook_symbols`；
  - `ensure_batches` 在 `app/` 內零呼叫點；
  - 名單模組與名單 store 方法對 `playbook_batches` 零 UPDATE；
  - 新批次只經 `_INSERT_ROUND_SQL`，`app/` 內恰好一個使用點。
  - 判定方式：AST 加 SQL trace。
- **N207-C2 寫入白名單與稽核**：
  - 名單路徑只寫三處：`playbook_symbols` 的自有欄位 upsert、`_INSERT_ROUND_SQL`、`playbook_roster_log` INSERT；
  - 不寫 `playbook_state` 的任何鍵、`playbook_directives`、`playbook_schedule`、`playbook_blacklist`、`playbook_fill_moves`、`playbook_evaluation_marks`；
  - 稽核表在 `app/` 內只有 INSERT；每次成功的寫入恰好一列；拒絕、失敗、no-op 零列。
- **N207-C3 零 diff，名單路徑也不呼叫**：
  - `claim_and_settle`、`_settle_on` 及其 helper、`_add_cash`、`settle`、`claim_directive`；
  - `commit_evaluation`、`commit_emergency_exit`、`apply_effects`、`set_paused`、`blacklist`、`roll_peak_closes`；
  - `set_capital`、`set_total_deploy`、`read_rebalance_inputs`、`rebalance()`；
  - `BATCH_LEFT_PLANNED_SQL`、`_CLAIM_SQL`、`_BLOCKING_CLAIM_SQL`、`_insert_directives`；
  - `BatchSnapshot`、`_snapshot_rows`；
  - `app/data/**`、`app/services/**`。
  - `confirm_rules` 只准在寫入之前加 FR-24 的前置檢查，檢查使用 `enabled_count` 的唯一定義。
- **N207-C4 交易形狀**：
  - `apply_roster_change` 是一個連線、一個 `BEGIN IMMEDIATE`；
  - SQL trace 的序列是：SELECT（批次、symbols、state 的指定鍵、現行參數）→ 0 或多句白名單寫入 → `COMMIT`；
  - 期間 connection factory 計數為 1；
  - 鎖內沒有 resolver、沒有網路、沒有呼叫另開連線的 `self.*`；
  - 時鐘在鎖內讀一次；
  - 錯誤處理照 C-11。
- **N207-C5 欄位歸屬**：
  - `entry_stopped*`、`high_volatility*` 只由名單 store 方法寫入；
  - upsert 的 `DO UPDATE SET` 只列自有欄位；
  - `set_paused` 的 ON CONFLICT 子句零 diff；
  - 名單路徑不寫 `paused`、`paused_since`。
- **N207-C6 批次欄位貫穿**：
  - `batch_round`、`entry_gate` 經 `_MIGRATIONS` 加入，不回填；
  - `BatchState`、`_BATCH_COLUMNS`、`_row_to_batch` 都要有這兩欄；
  - base 上 `app/` 內不得存在整列寫回 `playbook_batches` 的語句（ADR-0041 Decision 5）。若 base 仍有，**停下回 TA**，不得以「把新欄位也加進整列寫回」自行處理。
  - 結算以外的寫入者與結算本身都不寫這兩欄。
- **N207-C7 engine**：
  - `engine.py` 對 base 的 diff 只在 `planned_batch_shares` 的函式本體內，簽名與 `:982-988` 呼叫點零 diff，而且與 ADR-0043 D3 第 5 點的程式語意相同；
  - ADR-0034 補充四落檔之前判 BLOCKING；
  - 沒有風控通過的審查紀錄，不得合併（AC-49）。
- **N207-C8 engine 輸入單一定義**：
  - `engine_batches` 是 `app/` 內唯一產生 engine 輸入批次的地方；
  - `evaluate(batches=…)` 與 `evaluation_marks(batches=…)` 收同一個物件（AST 判定同名變數）；
  - 「今日可進場檔數」也由它衍生；
  - open 批次永遠會被納入。
- **N207-C9 戳記閘**：
  - `entry_gate` 只在 `_INSERT_ROUND_SQL` 寫入；同一輪各批的值相同；
  - 判定只經 `entry_gate_open`，比較的 current 戳記與交給 engine 的 `portfolio` 取自同一次 `_state_map()`；
  - 沿用 N-197a 的 `TotalDeployStamp`，不得重新定義；
  - 解開條件依 CEO 對 Q-C12 的選擇（預設甲：不相等就開）；
  - 續用的 planned（矩陣 (i)）不加閘。
- **N207-C10 輪次規則**：
  - 新輪的 `batch_no` 從該檔目前最大值加 1 起，連續 bpt 個；`batch_round` = 目前最大輪次加 1；全新代號是第 1 輪、1～bpt；
  - 開新輪的前置條件「該檔所有批次都是 closed 或 skipped」在鎖內判定；
  - bpt 取鎖內讀到的現行參數；
  - 矩陣 (i)～(v) 與季度提交的分組規則依 ADR-0043 D3 第 4 點。
- **N207-C11 預覽摘要**：
  - 所有名單寫入都要先預覽、再確認；
  - 摘要只由 `roster_digest` 產生，鎖內以鎖內讀到的事實重算；
  - 不一致就拒絕（`preview_stale`）、零寫入；
  - 摘要不含時間戳記與窗口狀態。
- **N207-C12 代號驗證**：
  - 在鎖外，走 `load_bars(…, market=PLAYBOOK_MARKET)`（含 ADR-0024 的 `admit_symbol`），加上 `symbol_shape_ok`（規則由 data-engineer 查證，保留 `00631L` 這類字尾）；
  - 確定性失敗與暫時性失敗分成兩種拒絕原因；
  - 不做正規化；
  - 只對新代號驗證。
- **N207-C13 季度窗口**：
  - 只有一份定義 `quarter_window`，切點依 ADR-0043 D8 第 1 點（CEO 若選 E1，終點改為 F 的 00:00）；
  - Asia/Taipei；13:30 取自 `TW_POLICY.session_close`；
  - 在 API 層與鎖內都強制；
  - `now` 為 naive 時 raise；
  - 測試一律用注入時鐘。
- **N207-C14 組合凍結**：
  - 鎖內讀 `emergency_until`、`freeze_until`，以 `portfolio_frozen` 判定，不儲存；
  - 只有停止新進場與高波動標記在凍結期間允許。
- **N207-C15 高波動**：
  - `high_volatility=` 只在 `evaluate_today` 傳入，值來自 `effective_high_volatility`，而且取自同一次、在建 snapshot 之前的 `symbol_states(data_date)`；
  - `:417` 與 `:1840` 不傳；
  - 寫入依 ADR-0043 D7 第 3 點。
- **N207-C16 字面與紅線**：
  - 新字面只放在 `wording.py`，風控逐字定稿前不得合併，PR 以程式從風控原檔逐字比對；
  - 回應、schema、畫面不含 recommend、score、rank、candidate、suggest，也不含波動率數字；
  - 名單依代號升冪；
  - placeholder 不放範例代號；
  - 沒有任何自動停止或自動補位的路徑。

## 8. 測試（全部 BLOCKING；用真實 `PlaybookStore`、檔案型 DB；時鐘一律注入）
- **N207-T1 函式層差分**：
  - 至少 300 組 seed，隨機產生全第 1 輪的輸入：`batch_no` 集合含斷號、從 0 起編、多於 bpt；status 與 shares 隨機；close 含 ≤0；TD、n_targets、bpt 隨機。
  - 測試檔內放修改前 `planned_batch_shares` 的逐字複本作為參考實作，斷言兩者的回傳逐值相等。
  - **效力證明**：PR 說明附本機輸出，顯示把第 1 輪的 offset 改成 `min-1` 時，本測試失敗。這份對照不 commit。
- **N207-T2 完整 `evaluate()` 差分**：
  - 至少 300 組 seed，隨機產生第 1 輪的帳冊、markets、symbols、portfolio、index；
  - 以 monkeypatch 換成參考實作跑一次，再用新版跑一次，斷言 `PlaybookEvaluation.model_dump()` 相等。
- **N207-T3 輪內計算（AC-47）**：
  - 第 2 輪（4～6）與第 3 輪（7～9）：第 4、5 批與首輪第 1、2 批相同；第 6 批吸收餘額；同一 close 下三批合計等於 `floor(symbol_amount/close)`；第 4 批不被當作末批。
  - 第 1 輪斷號（1、2、4）之後開新輪（5～7）。
  - 新輪中有 skipped 時的吸收方式。
- **N207-T4 案例矩陣**（AC-16、17、51、52、69）：
  - (i)～(v) 加季度提交的保留組，分別斷言列數；舊列逐欄不變；新列的 `batch_no`、`batch_round`、`entry_gate`；啟用檔數；稽核列。
- **N207-T5 舊輪殘留（AC-50）**：舊輪已 closed 的批次 k 有一張 pending buy，開新輪後跑結算，斷言 `claim_and_settle` 被 G1 以 closed 拒絕、新輪各批不變、現金不變。
- **N207-T6 戳記閘**（AC-25、56、57、58、68）：
  - 新輪與新代號在戳記不變時不在 engine 輸入；
  - REBALANCE ok 之後納入；
  - BLOCKED 與 SUPERSEDED 時不納入；
  - 「REBALANCE 先、名單後」仍待生效；
  - 矩陣 (i) 不加閘；
  - 首次設定加閘，第一次 confirm 之後解開；
  - 依 CEO 選擇參數化甲乙丙丁。
- **N207-T7 戳記同源**：
  - AST：`evaluate_today` 內只有一次 `portfolio_and_stamp()`，沒有 `portfolio_state()`；
  - 注入：`list_batches` 與 state 讀取之間 commit 一次 REBALANCE，斷言不會出現「閘已開而 TD 是舊值」。
- **N207-T8 停止新進場**（AC-08、09、10、13、14、67）：
  - 停止後不出 R1，賣出照常；
  - S1 自動恢復與 S2 到期不會清掉停止，停止也不改 S1、S2 的狀態；
  - 停止期間 `defer_count` 與 `missed_count` 不增加；
  - 冪等（零寫入、零稽核列）。
- **N207-T9 決定性交錯**（AC-26～29、44、62）：
  - 以 connection factory 的 hook，在名單交易的 `BEGIN IMMEDIATE` 之前或 COMMIT 之前，以另一個 store 實例分別完成 REBALANCE、confirm、`claim_and_settle`（含把最後一批關閉）、`evaluate_today`、另一筆名單寫入；
  - 斷言結果等於兩種循序之一，而且摘要不一致時零寫入。
  - **效力證明**：拿掉鎖內重驗時失敗（PR 說明附輸出）。
- **N207-T10 SQL trace**：依 N207-C4 的語句序列；connection factory 計數為 1；resolver 被 patch 成一呼叫就 raise。
- **N207-T11 零寫入**（AC-61、42）：
  - 逐一跑每一種拒絕原因（形狀、重複、檔數、窗口、凍結、名額已滿、(v)、`preview_stale`、確定性、暫時性），以及在 INSERT 或稽核 INSERT 注入例外；
  - 前後比對三張表逐列相同；
  - 成功路徑上 TD 三鍵、現金、指令列、`paused`、黑名單逐值不變。
- **N207-T12 窗口邊界**（AC-53、54、55）：
  - L 13:29:59 拒絕、L 13:30:00 放行；
  - 季末後的週末與元旦放行；
  - F 13:29:59 放行、F 13:30:00 拒絕（選 E1 時改為 F 00:00）；
  - 下季第二個交易日拒絕；L 前一個交易日拒絕；
  - 台北 00:00～08:00 與 UTC 不同日的情況；
  - 空日曆的情況：斷言算出的窗口包含在真實窗口內；
  - 預覽在窗口內、確認時已跨過切點：拒絕；
  - 不經畫面直接呼叫 API：同樣拒絕；
  - 窗口外停止新進場：成功。
- **N207-T13 組合凍結**（AC-59、60）：
  - `emergency_until` 或 `freeze_until` ≥ 台北今日時，首次設定、重新加入、開新輪、季度提交都拒絕，停止新進場成功；
  - until < 台北今日時放行；
  - 性質測試：拒絕時，engine 對任何 data_date ≤ 台北今日都判為凍結。
- **N207-T14 高波動**（AC-34～38、65）：
  - BIAS25 16%、21%、恰好 15%、恰好 20% 的邊界；
  - 當日變更不生效，下一個交易日生效；同日來回切換；
  - `changed_on` 為 NULL 的既有 1 立即生效；
  - AST 確認 `:417` 與 `:1840` 沒有傳入。
- **N207-T15 靜態檢查**：N207-C1、C2、C3（白名單函式的 AST 加 diff 錨點）、C5、C8、C16 的禁用詞掃描（AC-40）；改變價格資料不改變名單順序。
- **N207-T16 性質測試（AC-31、41）**：隨機產生操作序列（首次設定、停止、重新加入、開新輪、季度提交、結算成交、評估），斷言：
  - 啟用檔數 ≤ n_targets，而且小於 n_targets 只來自停止；
  - `batch_no` 不重用；
  - 每檔最多一個未終結的輪次；
  - 每輪的列數等於當時的 bpt；
  - 批次列不消失；
  - 除了明確的操作，沒有其他方式會建立批次列。
- **N207-T17 代號驗證**（AC-03、04、05、45）：用 data-engineer 提供的形狀表；`2330.TW` 拒絕；以 stub 重現確定性與暫時性失敗，兩者訊息不同；零寫入。
- **N207-T18 稽核**（AC-23、42）：每次成功恰好一列，欄位內容正確；trigger 讓 UPDATE 與 DELETE 都 raise。
- **N207-T19 confirm-rules（AC-30）**：啟用檔數大於 n_targets，或批次表為空時拒絕；`set_capital` 沒有被呼叫；params 不變。
- **N207-T20 遷移**：
  - 舊版 DB 檔加上新欄位後，既有列的 `batch_round=1`、`entry_gate` 為 NULL，其他欄位逐位元相同；
  - 雙行程同時 `add_missing_columns`（N-154）；
  - schema 釘住測試（`tests/test_playbook_exit_idempotency.py:738` 附近）的修改逐條列在 PR 說明，交 qa 判定。
- **N207-T21 舊資料端到端不變**：
  - `tests/golden/seam/approved/` 零 diff；
  - N198-T5、ADR-0041 T27、N197a、N196 各測試原樣綠燈。
  - 因 `BatchState` 新增預設欄位而需要修改的斷言，逐條列出交 qa 判定。
- **N207-T22 語意變更釘住（送風控）**：
  - 標的已停止而且沒有 open、或整檔待生效時，`every_symbol_evaluated` 與 `/today` 批次快照的行為；
  - 斷言結果與風控核可的規格一致。

## 9. 先後順序與合入
- **順序**：R2（N-177a、N-195）→ N-196 → N-197a → N-177b → N-198 → N-207。ADR、spec、風控字面可以現在並行。
- **N207-M1 base 驗證**：比照 N196-C8 與 N198-C7 的方法。對 N-177a、N-195、N-196、N-197a、N-177b、N-198 六個 merge commit（完整 40 碼）逐一執行 `git merge-base --is-ancestor <M_x> <base>; echo "exit=$?"`，六條都要是 `exit=0`。指令原文與完整輸出記入交件紀錄。
- **N207-M2**：以 merge commit 合入；合入前 merge 最新 product（不得 rebase），之後重跑完整 CI 與 seam。
- **N207-M3**：ADR-0034 補充四落檔，加上風控對 FR-42 與字面的通過紀錄，兩者都要早於合併。
- **部署前唯讀盤點**（CEO 本機執行，只回傳數字，比照 N-199）：
  - 實際檔數對 n_targets；
  - 每檔批數對 bpt；
  - `high_volatility=1` 的列數；
  - 每檔 `batch_no` 的最小值、最大值、斷號數、從 0 起編的檔數；
  - 是否存在非終態舊列以外的異常狀態。

## 10. commit 切分（一個 commit 一個語意）
1. `feat`：schema 與 store 加法欄位、遷移（不改行為）。
2. `feat`：engine 輪內計算加 T1～T3（單獨一個 commit，方便風控核對 diff）。
3. `feat`：service 的 engine 輸入、戳記閘、高波動接線。
4. `feat`：roster 純函式、名單寫入交易、API。
5. `feat`：前端名單入口。
6. `feat`：字面（風控定稿之後）。
7. FR-28 若同單，以獨立 commit 處理。
````

---

### 交付 3：給風控的審查清單

````markdown
# N-207 送風控審查清單（risk-compliance-officer，有否決權）

依據：ADR-0043（proposed）、N-207 實作規格、PRD v2 附錄。識別名是 TA 的建議，最終由風控與 creative-lead 定稿；所有字面只放在 `wording.py`。

## 一、PRD 附錄的 14 句字面

| # | 字面 | 建議識別名 | 請風控確認的重點 | 對應 |
|---|---|---|---|---|
| 1 | 停止新進場的確認句 | `ROSTER_STOP_CONFIRM_NOTE` | 列出 planned 與 open 批數；明講已持有部位照常走停損、停利、EMERGENCY；不暗示停止是「降低風險的建議」 | FR-7、AC-12 |
| 2 | 已產生未結算指令的揭露句 | `ROSTER_STOP_INFLIGHT_NOTE` | 含「停止若在評估之後才完成，該次評估仍可能出 R1」這一情況；不得寫成「已取消」 | FR-10、AC-10 |
| 3 | 名額空缺常駐揭露 | `ROSTER_VACANCY_NOTE` | 「系統不會補位」「實際投入低於計畫」都要出現；不用安撫性用語 | FR-11、AC-11 |
| 4 | 季度提交差異確認畫面 | `ROSTER_QUARTERLY_GROUP_*`、`ROSTER_QUARTERLY_NEW_ROUND_ITEM` | 三組標題與說明；「保留」組逐項標示「將新增 N 批」，未勾選就不開新輪；不得出現候選或排序意味 | FR-18、AC-20、AC-69 |
| 5 | 各條拒絕訊息 | `ROSTER_REFUSED_{WINDOW, QUOTA_FULL, COUNT_MISMATCH, FROZEN, ROUND_NOT_TERMINAL, PREVIEW_STALE, NOT_IN_ROSTER, SHAPE, DUPLICATE, NO_BARS, TRANSIENT, ROSTER_NOT_EMPTY}` | 只陳述事實與下一步，不推測原因；窗口訊息要能附上下一個窗口的起訖（取自 `quarter_window`）；凍結訊息不重述 `mode_reason`（C-9） | FR-5、14、17、22、40 |
| 6 | cap-1 揭露句改為依實際檔數 | ADR-0031 `compose` 增列 `enabled_targets` | **PRD 前提有誤**：現行句子不是寫死「5 檔」，而是 `{n_targets}`（`app/api/playbook_cap1_wording.py:58`、`:109`）。要決定的是：啟用檔數與 n_targets 不同時如何並陳；是否屬 ADR-0031 已核可字面的修訂 | FR-28、AC-33 |
| 7 | 高波動標記的效果揭露句 | `HIGH_VOL_EFFECT_NOTE` | BIAS25 門檻 15% 與 20% 的變化與生效日；生效日句中的日期可能因日曆退回週一到週五判定而落在假日，是否需要附註；不含波動率數字 | FR-32、AC-37 |
| 8 | 重新加入的結果句 | `ROSTER_RESULT_{NEW_ROUND, CONTINUE_PLANNED, NO_PLANNED}` | (ii)「無待進場批次」要說清楚「之後不會再買，等 open 全部出場後，可再於窗口內重新加入開新輪」 | FR-16、矩陣、AC-51 |
| 9 | 首次設定的欄位說明與空狀態 | `ROSTER_FIRST_SETUP_*` | 不得出現「請選擇適合的標的」之類引導；說明批數由參數決定、使用者不輸入 | FR-3 |
| 10 | placeholder | （前端常數，同樣經風控） | 不放任何範例代號（2330、0050、00631L 都不行） | FR-35 |
| 11 | 「第 4～6 批」的輪次呈現 | `ROUND_LABEL`（名單入口）；R1 rule_summary 的「第 {batch_no} 批」在 engine.py，**零 diff** | 新輪顯示第 4～6 批是否需要附「第 2 輪」說明；engine 的指令摘要只會寫「第 4 批」 | FR-43、AC-46 |
| 12 | 「待生效」的狀態字面與揭露 | `PENDING_GATE_LABEL`、`PENDING_GATE_NOTE` | 見本清單第三節 | FR-21 |
| 13 | 啟用檔數與今日可進場檔數的差額原因 | `ENTRY_COUNT_GAP_{S1, S2, PENDING_GATE, NO_PLANNED}` | 只列原因類別，不含行情條件；不暗示要使用者補位 | FR-26、AC-66 |
| 14 | engine 輪內計算的規則語意變更本身 | — | 見本清單第二節 | FR-42、AC-49 |

## 二、engine 輪內計算的規則語意變更（FR-42；ADR-0043 D3 第 5 點）
1. **改了什麼**：
   - 只在第 2 輪以後：輪內序位小於 bpt 的批次，依每批金額計算；輪內末批吸收「整檔配額減去同一輪已占用」；舊輪批次不計入。
   - 修改前的程式會把第 4 批誤判為末批，第 4 批會吸收整檔配額，大約是每批金額的 3 倍。
2. **沒改什麼**（請逐項確認可接受）：
   - 第 1 輪逐式相同，包括斷號或從 0 起編的舊資料（N207-T1、T2，各至少 300 組 seed）；
   - 每批金額仍是「評估當下的 TD」÷ n_targets ÷ bpt，不是開輪當時的 TD。新輪進行中若 REBALANCE 改了 TD，同一輪各批的基準會不同，與第 1 輪現況一致；
   - skipped 批次在末批計算中以 `shares`（通常是 0）計入，所以末批會補足被跳過批次的金額。這是第 1 輪的現況，新輪照搬；
   - R1、R2、R3、M1 的條件不變；S、P 系列零改動；鐵律①的現金底線不變。
3. **C-B11 範圍判定**：依 CEO #60，「ADR 中拆除護欄的條文」屬風控的審查範圍。請審 ADR-0043 D3 第 7 點與 ADR-0034 補充四全文，特別是「仍然有效的不變式」與「不得讀成 engine 從此開放修改」兩句。
4. **兩處非字面的語意改變**（ADR-0043 Consequences；N207-T22）：
   - (a) `/today` 的批次快照只列生效中的批次。已停止標的的 planned 批次、待生效批次、舊輪批次改在名單入口呈現。
   - (b) 「規則已全數評估」的範圍縮為「交給 engine 的標的」。已停止而且沒有 open、或整檔待生效的標的不計入。
   - 這兩處是否需要揭露句、怎麼寫，請風控裁示。
5. **已知未涵蓋**：參數 `batches_per_target` 在兩輪之間被修改時的處理，屬另案（FR-27）。

## 三、待生效的揭露（FR-21；ADR-0043 D6）
1. 新加入的標的與新一輪的批次「占用名額、但還不會出 R1」，要同時出現在名單入口與今日可進場的差額原因。
2. **解開條件的說法取決於 CEO 對 Q-C12 的選擇**：
   - 甲：「REBALANCE 或資金確認重算 TOTAL_DEPLOY 之後」；
   - 乙、丙、丁：「REBALANCE 成功之後」。
   - **請風控判定甲相對於 #121 字面是否屬放寬**（閘較容易解開）。若屬放寬，需要 CEO 明示同意。
3. 順序揭露：建議「先提交名單、再 REBALANCE」；反過來做的話，新標的仍是待生效，要再跑一次 REBALANCE。
4. REBALANCE 失敗、被 `REBALANCE_BLOCKED` 或 `REBALANCE_SUPERSEDED` 擋下時，名單保留，維持待生效，不作廢。
5. 目前前端沒有 REBALANCE 入口（PRD 風險 6）。揭露句不得暗示畫面上有入口；觸發方式待 CEO 決定。
6. 甲案下，以 API 重送資金確認會同時解開閘並覆寫現金，是否需要揭露。
7. 高波動的「待生效，N 月 N 日起」與戳記閘的「待生效」是兩個不同機制，**請定兩組可以區分的字面**。
8. ABA 殘留（時鐘倒退導致閘不開，方向保守）是否需要對使用者揭露。TA 判斷不需要，只在 ADR 記錄。

## 四、其他需要風控判定的事項
1. **季度窗口**：切點 [L 13:30, F 13:30)，以 Asia/Taipei 判定。已知限制：日曆退回週一到週五判定時，窗口只會變窄；真實交易日在已觀測範圍內整天缺 bar 時，窗口可能變寬。是否需要揭露句（FR-38 已要求揭露）。
2. **組合凍結的判定殘留**：資料落後的那幾天，名單入口放行、`/today` 仍顯示凍結。TA 判斷不會造成買進，請確認是否需要揭露。
3. **高波動接線**：既有列中 `high_volatility=1` 的，部署當下立即生效，是行為變更。是否以部署通知揭露（數字由盤點取得）。
````
