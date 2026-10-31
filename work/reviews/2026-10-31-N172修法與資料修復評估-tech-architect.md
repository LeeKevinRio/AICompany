# N-172 修法與資料修復評估（ADR-0035 草案）

- 審查者：tech-architect
- 日期：2026-10-31
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**建議修法是方案 (e)：「同一預定執行日的決策冪等」，修在 store/service 的單一 `BEGIN IMMEDIATE` 寫入 transaction 內。engine 一行不改。需要新立 ADR-0035，補充 0033、0034，不取代，草案見下文。** 四個指定方向都不能單獨當主修法：(b) 的無條件版、(c)、(d) 的兩個變體標 VETO；(a) 的「跨日在途單」部分拆成 N-172b，等 N-176（F7）定調後再做。

讀碼時另有三項重要發現（讀碼判定，未執行）。前兩項讓 N-172 的實害比重現報告寫的更大，第三項改變緩解方式：
1. **順延計數膨脹（V2）**：在追價日（R2）或指數缺漏日（M1）重複開頁，每次都會把 `defer_count` 加 1。開 3 次，該批當天就被 R3 永久跳過，沒有任何下單紀錄（`engine.py:874`、`:932-940`、`:739`、`:761-769`；`store.py:738-741`；`models.py:94` `r3_max_defers=3`）。
2. **重複 R1 遇上 MISSED（V5）、P1/P2/P3 減碼重複（V3）**：
   - V5：N 列 R1 全部 MISSED 時，`missed_count` 一次加 N（`store.py:915-920`），可能一天就達到 E-2 上限（`engine.py:806`）。
   - V3：S/P 賣出每個交易日都評估，不限排程日。同一天重複開頁，1/3 減碼會寫成 N 列，帳冊會被扣 N 次股數（`engine.py:448-535`、`store.py:942-957`）。
3. **危險窗口不只週二當天。** 未收盤的 K 線會被丟掉（`data/service.py:941-957`），所以在週三收盤資料進來之前，`data_date` 一直是週二。週三早上打開排程台準備下單，本身就會再寫一列（`engine.py:1099-1100`、`service.py:275-291`）。qa 的對照組在週三有 K 線，所以沒有覆蓋到這個情況。

**資料修復**：
- 建議先跑唯讀偵測，再由 CEO 決定：只揭露，或用「CEO 確認的離線修復工具」。
- **任務單建議用「settled_at 相同」偵測，這個方法不成立。** `claim_directive` 每一列各自取 `datetime.now`（`store.py:896`），同一次結算的重複列 settled_at 也不同。改用「決策身分鍵相同、`created_at` 不同」（`store.py:791`：同一次評估的所有列共用一個 `created_at`）。
- **自動遷移回補：VETO。**

**排序**：N-166 → N-172a → N-171 → N-168；N-164/N-165 的開發可以並行，但上線要排在 N-172a 之後。N-172a 若和 N-166 平行開發，`store.py` 一定會衝突。

**暫行緩解（給 CEO 的一句話）**：
> 「週二、週四收盤後，到隔天收盤資料出來前（保守起見到隔天傍晚），排程台只開一次：只開一個分頁，看完就截圖記下指令並關掉分頁，這段時間不要切回、不要重新整理，也不要隔天早上再打開。」

---

## 各部門回報

### tech-architect（本人，唯讀）

#### 一、修法方案比較

**先定義根因。** `GET /today` 是帶寫入副作用的 GET（`api/playbook.py:406-435`）。`evaluate_today` 每次都會依序呼叫 `apply_effects`、`save_fast_market`、`record_schedule`、`record_directives`，四者都是各自開 connection，而且無條件寫入（`service.py:682-685`）。docstring 還寫著「It is idempotent, so calling this endpoint repeatedly is safe」（`service.py:617-620`），這句與事實不符。

問題不只 R1。凡是「同一個預定執行日」重算一次，就會重寫一次。目前已知的變體：

| 代號 | 現象 | 證據 | 狀態 |
|---|---|---|---|
| V1 | R1 重複，現金扣 N 倍 | 重現報告 | qa 已重現 |
| V2 | R2/M1 順延計數一天加 N，最快 3 次就把該批 R3 跳過 | `engine.py:874-940`、`:739-779` | 讀碼 |
| V3 | P1/P2/P3 減碼重複，帳冊超賣、現金多入帳 | `engine.py:448-580`、`store.py:942-957` | 讀碼 |
| V4 | 跨日在途：前一次買單沒抓到開盤價而未結算，下一個排程日 R1 又挑同一批 | `engine.py:699-711`；我 N-168 評估的 Q4 | 讀碼 |
| V5 | 重複列一起 MISSED，`missed_count` 加 N | `store.py:915-920` | 讀碼 |
| V6 | `playbook_schedule` 重複列 | `store.py:759-782` | 讀碼 |
| N-174(c) | 同一 data_date 第二次評估翻成凍結或防守，第一次的 R1 照樣結算 | 追蹤清單:276 | 已併入 N-172 |

關於 V6：`_mark_schedule` 會把同鍵的所有重複列一起更新（`store.py:961-976`）。`list_schedule` 在 app 內沒有呼叫端，只有測試在用（grep 結果），所以 V6 只是外觀問題。

**方案比較表**

| 方案 | 正確性 | 併發安全 | 對 R3 重試、MISSED、defer | 與 N-166、N-168 的互動 | record_schedule | 規模 | 結論 |
|---|---|---|---|---|---|---|---|
| (a) 產生 R1 時，略過已有未結算 buy 的批次（鎖內判斷） | 修 V1、V4、V5。修不到 V2：defer 列寫入時就是 `settled=1`（`store.py:822`），不算在途。也修不到 V3。同日重開時，R1 會從頁面消失，需要新字面 | 判斷放鎖內可以做到 | 跨日版遇到 F7（`calendar` weekday fallback 讓執行日落在休市日，永遠結算不了，追蹤清單:279）時，該標的 R 系列會被永久封鎖。現況反而是重發一張可結算的新單，所以跨日版是退步 | 不衝突 N-166。N-168 的待成交清單會變乾淨 | 沒有處理 | 中 | 同日部分併入 (e)。**跨日部分拆成 N-172b，等 N-176 定調** |
| (b) UNIQUE 或 partial unique index | `settled=0` 的 partial 版涵蓋不到 defer，修不到 V2。INSERT OR IGNORE 會靜默丟列，資料一變，回應會顯示沒落檔的行，違反 R16 一致性。effects 照樣套用 | 資料層可以擋 | V2 沒修 | 舊 DB 已有重複列時，`CREATE UNIQUE INDEX` 會失敗，啟動時 `_init_schema`（`store.py:297-311`）會 raise，所有端點 500 | 沒有處理 | 小 | **VETO（無條件建 index 版，延續我先前的判定）**。可在盤點確認零未結算重複列之後，另議做成 fail-soft 的縱深防禦 |
| (c) 結算時做批次層級 claim，其餘列改判新狀態 | 只修 V1 的現金。V2 完全沒修；V3、V5 要逐規則特判。日誌仍留 N 列 | claim 與 settle 分屬兩個 transaction（`store.py:883-898`、`:900-959`），也就是 F2 窗口，要先修 N-169 | MISSED 要另外去重，否則照樣多加 | 要改 `settle()`，與 N-168 的 C-B6 正面衝突。新的 `DirectiveStatus`（`models.py:47`）要同步前端 union 與 label，並送風控 | 沒有處理 | 中到大 | **VETO（作為主修法）**：它把評估端的非冪等藏到結算端，V2 仍在，卻會讓 N-172 看起來已修好 |
| (d1) 當日首次評估整份快取、之後重播 | 修 V1 到 V6 | 要另加鎖 | 第一次若是資料缺漏（例如持股標的停損沒評估），補到資料後整天也不會再評估 S1，停損時效退步 | 必須儲存 `mode_reason` 快照，違反 ADR-0033 C-9 與覆審「mode_reason 禁存快照」（`0033:145`） | 有處理 | 中到大 | **VETO** |
| (d2) 當日已提交就整次不寫入，只重算顯示 | 資料一變，回應顯示的行沒有落檔（R16）。資料恢復後新觸發的 S1 也寫不進去 | 要另加鎖 | 有處理 | — | 有處理 | 小 | **VETO** |
| **(e) 建議：預定執行日 × 決策身分的冪等**（詳見 ADR 草案） | 修 V1、V2、V3、V5、V6、N-174(c)。資料恢復後的新決策照樣寫入 | 鎖內重讀身分鍵，比照 N-154／N-166 | defer 與 skip 的 effect 跟著它的指令列走，被擋下就不套用。MISSED 只會有一列 | 沿用 N-166 的 `_insert_directives(conn, …)` 與 C-11 錯誤處理。不改 `settle()`，不碰 N-168 的 C-B6。engine 不改，符合 0034 的 C-B11 | schedule 列只在指令列新寫入時才寫，同一個 transaction | 中 | **採用** |
| (f) 前端 `refetchOnWindowFocus:false`、`staleTime` | 只降低觸發頻率。多分頁、隔天早上重開、`retry:1`、網路重連都還會觸發 | — | — | 方向與 N-164/N-165 的 `onSettled` 失效（PRD:270）相反 | — | 小 | 可選的縱深防禦，交 PM/CEO 決定，**不可取代 (e)** |
| (g) 拆成 POST /evaluate 加純讀的 GET | 架構上最乾淨 | — | — | 整個前端流程與風控文案都要重審 | — | 大 | 長期方向，這次不採 |

**(e) 的核心規則（詳見 ADR 草案 Decision 1 到 4）**

1. **決策身分鍵 K1** = `(symbol, batch_no, rule_id, action, execution_date)`。`batch_no` 用 `IS` 比對，因為 S2 的 `batch_no` 是 NULL。
   - 用 `execution_date`，不用 `data_date`。原因：`directive.data_date` 是該標的自己的 K 線日（`engine.py:102-103`）。同一次評估中，若某標的的 K 線較晚才到，用 data_date 當鍵會被當成不同決策。`execution_date` 由這次評估的 data_date 決定（`engine.py:1099`），全部標的一致。
2. **R 系列鍵 K2**：每個 `(symbol, execution_date)` 的 R 系列（R1、R2、R3、M1）只決策一次。
   - 必須以標的為單位，不能以批次為單位。否則第一次評估把第 1 批 R3 跳過之後，第二次評估會改挑第 2 批進場，違反「每標的每排程日只處理一批」（`engine.py:704-706`）。
3. **同一個 transaction**：鎖內重讀 K1 與 K2 → 只 INSERT 新的指令列 → 只為新列寫 schedule 列 → 只為新列套用綁定的 effects（`defer_increment`、`batch_skipped`）→ COMMIT。
   - 其餘 effects 照現況套用，可以留在 transaction 外。這些 effects 在同一個 data_date 下是冪等的：freeze 與 blacklist 都由 `calendar.shift(data_date)` 算出相同值；`defense_on` 的 since 等於 data_date；S3 有 `already_frozen` 防護（`engine.py:1112`）；FILL_DEPENDENT 本來就被略過（`store.py:224-226`、`:716-717`）。
   - 如果 transaction 之後才失敗，下一次呼叫會自行補齊。
4. **回應的 `directives` 等於日誌中這個 execution_date 的 R/S/P/M1 列**（存檔版本，以 K1 去重、取最小 id）。
   - 同一天怎麼刷新，看到的都是同一張表，與 R16 一致。
   - 翻成凍結或防守時，第一次寫入的 R1 仍會列出，再附一句揭露（N-174(c)，字面交風控）。
   - 這和 CEO #79 選 B-2a 的精神一致：保留並揭露，不撤回。理由是 R10，使用者可能已經下單。

**`record_schedule` 要一起處理**：放進同一個 transaction，同生同滅。既有的 schedule 重複列不修。

**對 N-166、N-168 的互動**

- **N-166**
  - 身分鍵排除 `EMERGENCY`、`REBALANCE`，與 C-4 的覆蓋集合互斥。
  - 0033 C-10 的「`record_directives`、`apply_effects` 對 `evaluate_today` 的行為不變」（`0033:146`）是 N-166 的範圍約束，不是持久決策。ADR-0035 要明寫：這是後續決策、補充不取代，不構成衝突。
  - F4（S/P 替已有 EMERGENCY 在途單的批次再出賣單，`0033:223`）和 F2 不在 N-172a 範圍內，仍歸 N-169。
- **N-168**
  - 0034 的 Decision 9（`0034:120`）在 ADR-0035 accepted 時就算滿足，N-168 可以開工。
  - N-172a 之後，同一 execution_date 的重複待成交買單只會是舊資料。跨日的重複（V4）要到 N-172b 才消失。
  - 所以 W-B1 清單**以 (symbol, batch_no) 去重計批數，股數逐列顯示、不得加總**（比照 N171-C4）。
  - L4 戳記會把所有重複列都打上，這沒有問題。
  - N-172a 不改 `settle()`，C-B6 不受影響。

**範圍外新發現：F8（讀碼判定，建議 medium，請 qa-automation 重現，另開追蹤，不併入 N-172）**
- S2 指令的 `batch_no=None`（`engine.py:656`）。`settle()` 遇到 `batch_no is None` 就直接 return（`store.py:921-923`），而 `batch_closed` 屬於 FILL_DEPENDENT、會被略過（`store.py:224-226`）。
- 結果：S2 成交後帳冊既不減股、也不入帳。
- S/P 在黑名單下照常評估（`engine.py:1211-1236`），所以價格沒回升前，S2 會每天再發一次。
- 我在 tests 裡沒有找到 S2 結算動帳的測試（grep `test_playbook_store.py` 只有 blacklist effect）。

#### 二、既有資料修復

**能否可靠偵測：分類別看。**

不變式：批次永遠不會重置。`ensure_batches` 用的是 `INSERT OR IGNORE`（`store.py:315-325`），批次只會從 planned 走向 open、closed 或 skipped。所以**任何 (symbol, batch_no) 一生最多只有一列 executed 的 R1 buy**。

| 類別 | 判準 | 可信度 | 帳冊影響 | 可否精算 |
|---|---|---|---|---|
| D-A 同鍵 R1 重複成交 | 同一 K1、`COUNT(DISTINCT created_at)>1`、全部 executed、shares 與 `settled_open_price` 都只有一種值 | 高。每次回應都只顯示 1 行（qa 實測 [1,1,1]），使用者看到的是同一張單 | 現金多扣 | 多扣金額 = (k−1) × shares × settled_open_price。成立前提：結算價就是開盤價（`service.py:293-298`） |
| D-A′ 同鍵 R1 重複 MISSED | 同上，但狀態是 missed | 高 | `missed_count` 多加 k−1，可能已經被 R3 跳過 | 計數可以算。但「該批是否因此被跳過」會改變之後的指令，不宜回溯 |
| D-B 跨日重複買同一批（V4） | 同一 (symbol, batch_no) 有大於 1 列 executed R1，`execution_date` 不同 | **模糊**。使用者在兩天各看到一張不同的單（R10） | 現金扣兩次 | 只揭露 |
| D-C defer/skip 重複 | 同一 K1，action 是 defer 或 skip | 高 | `defer_count` 膨脹，可能已經被 R3 跳過 | 只揭露 |
| D-D P1/P2/P3 賣出重複成交 | 同一 K1，action 是 sell，rule 是 P1、P2 或 P3 | 高 | 帳冊超賣、現金多入帳（帳冊內部一致，但與券商不符） | 只揭露，個案處理 |
| D-E S1、P2 移動停利、S2、EMERGENCY 重複 | 同一 K1 | 高 | 有 `min` 保護，現金與股數不翻倍（我 4xx 評估:68-82） | 只列計數。EMERGENCY 併入 N-166 的 CEO-2 |
| D-F 未結算的重複列 | 同鍵、`settled=0` | 高 | **下次開頁會被逐列結算，照樣多扣** | 列出警告 |

**誤判防護：遇到以下情況，該組不給回補金額，只列「需人工判讀」：**
- 同一個 `created_at` 卻出現重複鍵。單次評估不可能發生，原因不明。
- shares 或價格不只一種值。
- 批次 `shares` 不等於單列 shares。
- `total_deploy_set_at` 晚於該組第一列的結算時間，也就是使用者之後重新輸入過資金。`confirm_rules` 每次都會把現金覆寫成輸入值（`service.py:534-539`、`store.py:494-516`）。這時回補會變成重複更正。
- 現金是單一 KV，沒有異動歷史（`store.py:557-558`）。所以只能從指令列反推，而且只看得到最後一次的 set_at。

**修復選項**

| 選項 | 風險 | R16 留存 | 稽核軌跡 | 誤判 | 結論 |
|---|---|---|---|---|---|
| R-1 啟動時自動遷移、回補現金 | 未經 CEO 確認就改帳；backend 與 scheduler 兩個 process 都會跑；冪等標記一旦遺失就會重複回補 | 不動列 | 現金 KV 沒有歷史，改了就無痕 | D-B、set_at 的情境會誤補 | **VETO** |
| R-2 只偵測、只揭露 | 帳冊維持錯誤：鐵律①讀到偏低的現金（`engine.py:998-1004`），之後的買單可能被錯誤縮量或取消 | 不動 | 不動 | 無 | 可接受，但不建議長期停在這裡 |
| **R-3 CEO 確認的離線修復工具（建議，只用在 D-A）** | 要停服務、先備份。先 dry-run，再用 `--apply --confirm <dry-run 印出的 token>` 執行；鎖內比對現金未變（compare-and-set）才寫入 | **不 DELETE、不 UPDATE 任何指令列**（延續 VETO） | 新增加法表 `playbook_adjustments`（id、created_at、kind、directive_ids、cash_before、cash_after、delta、tool_version）。同一組 directive_ids 已校正過就拒絕 | 只處理通過全部判準的 D-A 組 | **建議** |
| R-4 不修 | 帳冊永久對不上 | — | — | — | 不建議 |

- **不得拿 `confirm-rules` 重新輸入資金充當修復。** 它會連帶把 TOTAL_DEPLOY 重算成 capital × ratio（`service.py:535-539`），把持股價值排除在外。
- 若 D-A 發生後 CEO 跑過 REBALANCE，TOTAL_DEPLOY 是用偏低的現金算出來的（`service.py:375-376`）。回補現金不會自動修正它，要由 CEO 決定是否再跑一次 REBALANCE。
- 過去因現金偏低而被縮量的買單，是已經發出的指令，不回溯。

**本機執行方式（比照 N-152 文件:36-130）**
- 腳本放 `apps/stock-desk/backend/scripts/n172_duplicate_probe.py`，獨立分支，只用標準函式庫，不 import `app.*`，不連網。
- DB 以 `file:…?mode=ro` 開啟，並下 `PRAGMA query_only=ON`；只送 SELECT；輸出只印事實。
- PowerShell 步驟：
  1. 停 backend 與 scheduler 兩個視窗。
  2. 把 `stock-desk.db`、`-wal`、`-shm` 三個檔一起 `Copy-Item` 到帶時間戳的資料夾，並記錄 `Get-FileHash -Algorithm SHA256`。
  3. 開**新的** PowerShell 視窗，`echo $env:UV_ENV_FILE` 應為空白。
  4. 用 `git worktree add` 取出腳本。
  5. 對**複本**執行 `uv run --frozen python scripts\n172_duplicate_probe.py --db-path <複本>`。
  6. 核對腳本的 commit hash。
  7. 直接從主控台複製貼回輸出，不要用 `>` 導向（cp950 編碼問題）。
- 修復工具（若採用）是另一支腳本：先 dry-run，CEO 看過後才 apply；還原方式是覆蓋回備份的三個檔。
- 偵測查詢的核心如下。DB 由 CEO 或 devops-sre 執行，我不碰。

```sql
SELECT symbol, batch_no, rule_id, action, execution_date, COUNT(*) n,
       COUNT(DISTINCT created_at) calls, SUM(settled=0) unsettled,
       SUM(status='executed') executed, SUM(status='missed') missed,
       COUNT(DISTINCT shares) share_variants, COUNT(DISTINCT settled_open_price) price_variants,
       GROUP_CONCAT(id) ids
FROM playbook_directives WHERE rule_id NOT IN ('EMERGENCY','REBALANCE')
GROUP BY symbol, batch_no, rule_id, action, execution_date HAVING COUNT(*) > 1;

SELECT symbol, batch_no, COUNT(*) n, GROUP_CONCAT(id), GROUP_CONCAT(execution_date)
FROM playbook_directives WHERE rule_id='R1' AND action='buy' AND status='executed'
GROUP BY symbol, batch_no HAVING COUNT(*) > 1;

SELECT key, value FROM playbook_state
WHERE key IN ('cash','total_deploy','total_deploy_set_at','total_deploy_source');
```
- EMERGENCY 的盤點查詢沿用我 4xx 評估:104-108，同一支腳本一起輸出。

#### 三、排序與分支衝突

1. **N-166 先合併**（已實作，審查中）。N-172a 要沿用它新增的 `_insert_directives(conn, …)`、`_write_state` 與 C-11 錯誤處理（N-166 交件:40-43）。
   - 若 N-172a 從現在的 product 線平行開發，`store.py` 的 `record_directives` 區段幾乎一定會衝突，`service.py` 也會。
   - 若 N-166 審查拖太久，替代做法是從 N-166 分支疊一個 PR，合併時排在 N-166 之後。要不要這樣做，由 dev-lead 與 CEO 決定。
2. **偵測腳本現在就可以開工**：只動 `scripts/` 與 tests，和任何分支都不衝突。
3. **N-172a 的測試現在就可以寫**：qa 草稿的 3 支 expected 測試轉正、3 支 observe 測試刪除、3 支 control 測試保留，再加上本文的 T 系列。正式程式等 N-166 合併後再寫。
4. **N-172a 排在 N-171 之前。** N-171 也要在 `evaluate_today` 的結算之後讀新欄位，碰同一個函式；而 N-172a 是 P1。修正原定的「N-166 → N-171 → N-168」。
5. **N-168** 在 ADR-0035 accepted 後即可開工（0034 Decision 9），合併排在 N-172a、N-171 之後。它改的是 `settle()` 與出清路徑，與 N-172a 衝突很低。
6. **N-164/N-165（含 N-170）**：只改前端，可以並行開發。但它把 `invalidateQueries` 改成 `onSettled`（PRD:270），會增加 `/today` 的重打次數，**上線要排在 N-172a 之後**。若另採方案 (f)，兩者都改 `queries.ts:415-466`，需要協調。
7. **N-172b**（跨日在途單排除）排在 N-176（F7）定調之後。

#### 四、暫行緩解

給 CEO 的一句話見「本次結論」。補充三點：
- 切到券商 App 再切回瀏覽器，也算重新聚焦，會觸發重打。按「確認規則」也會觸發（`queries.ts:449`）。
- 「全部出清」仍可隨時使用（EX-2，不得勸阻），可能多出來的列由偵測腳本收尾。
- 這個做法只能降低觸發，不能歸零：網路重連、`retry:1` 仍可能重打。若從週四以後就沒再開過頁，DB 可能已有未結算的重複列，下次開頁就會結算。這不影響之後的修復，修法相同；想先知道的話，可以先跑偵測腳本。
- 這是內部操作建議，不是面向使用者的產品文案，不需要經風控閘門。

### 應經手但尚未經手
- **risk-compliance-officer**：N-174(c) 的揭露句（識別名暫定 `SAME_DAY_EARLIER_ENTRY_NOTE`）。若帳冊校正之後要在 UI 揭露，也要送審。
- **qa-automation**：重現 V2、V3、V5、週三早上窗口、F8。
- **dev-lead**：N-172a、偵測腳本，以及 R-3 修復工具（若採用）。
- **tech-writer**：ADR-0035 落檔。
- **devops-sre**：上線前檢查「零未結算重複列」。

### ADR-0035 草案（proposed，交 tech-writer）

- **標題**：stock-desk 排程台同一預定執行日重複評估的決策冪等（補充 ADR-0033、ADR-0034，不取代）
- **Context**：
  - 重現報告的 V1 實測值。
  - V2 到 V6、N-174(c)。
  - `GET /today` 帶寫入副作用；四個寫入各自開 connection、無條件 INSERT；沒有 UNIQUE；`claim_directive` 只防列層級重放。
  - 未收盤 K 線被丟掉，所以窗口延伸到 T+1 收盤（`data/service.py:941-957`）。
  - 前端 react-query 使用預設值。
  - 限制：R10、R16、0033 的 C-3／C-9／C-11、0034 的 C-B11、覆審「mode_reason 禁存快照」。
- **Options**：上述 (a) 到 (g)。
- **Decision**：
  1. K1 決策身分鍵：`(symbol, batch_no, rule_id, action, execution_date)`。
  2. K2：R 系列（R1、R2、R3、M1）以 `(symbol, execution_date)` 為單位只決策一次。
  3. engine 在鎖外跑，不改 engine。持鎖期間零 I/O。在單一 `BEGIN IMMEDIATE` 內重讀 K1、K2，只寫新列、新列的 schedule 列、新列綁定的 `defer_increment`／`batch_skipped`。其餘 effects 維持冪等套用。
  4. `/today` 的 `directives` 等於日誌中該 execution_date 的 R/S/P/M1 列（存檔版本，以 K1 去重、取最小 id）。由 directives 推導的「無」類敘述，以這份清單為準。
  5. 清單含 R 列、但本次 mode 不是 normal 時，附加揭露句（風控定稿，只放 `wording.py`）。
  6. 結算端不改：不新增狀態、不做批次層級 claim。
  7. 本 ADR 不建 unique index。無條件版 VETO；日後若要建，前提是盤點確認零未結算重複列，而且建立失敗要 fail-soft。
  8. 跨日在途單（V4）不在本 ADR，交 N-172b，以 N-176 定調為前提。
  9. 既有資料：先唯讀偵測。修復只能用 CEO 確認的離線工具；不刪、不改指令列；校正寫進加法表 `playbook_adjustments`。
  10. 0033 C-10 第二句視為 N-166 的範圍約束，本 ADR 是後續決策，不構成衝突。0033、0034 原文不改。
- **Consequences**：
  - 好處：
    - 不論觸發來源（分頁、隔天早上重開、多分頁、重試），同一個決策只落檔一次，effects 只套一次。
    - 資料恢復後的新決策照樣寫入，停損時效不退步。
    - 頁面在同一天刷新多少次都穩定，而且等於日誌內容。
  - 壞處：
    - **首次決策為準**：同一天資料修正後，R 決策不會改。例如第一次判 R2 順延，就要等下一個排程日。
    - 同一批同一天可能先後出現不同規則的賣單（例如 P1 之後又出 S1）。帳冊有 `min` 保護，但使用者會收到兩張單，屬殘留風險。
    - 回應中的參考價可能早於畫面上的快照價。
    - store 要新增幾個接收 conn 參數的方法。
    - 既有重複列留在日誌裡，所有讀取端都要去重。
    - F2 與結算時現金的讀改寫競態（`store.py:941`、`:944`）仍在，歸 N-169。
- **待決**：見下方 CEO 裁示。

**對實作的約束（qa-reviewer 可逐條檢查）**
- N172-C1：K1、K2 的查詢與所有新列 INSERT、schedule INSERT、綁定 effects，都在同一個 conn 的單一 `BEGIN IMMEDIATE` 內完成。錯誤處理照 C-11：`in_transaction` 時 ROLLBACK，然後原樣 raise。
- N172-C2：持鎖期間零 resolver、零網路呼叫（比照 C-3）。
- N172-C3：`engine.py` 零 diff（C-B11）。
- N172-C4：K1、K2 不含 `EMERGENCY`、`REBALANCE`。另加守門測試，釘住「M1 列只由進場段落產生」。
- N172-C5：被擋下的指令，它的 `defer_increment`、`batch_skipped` 不得套用；其他 effect 種類要有逐種冪等的表格測試。
- N172-C6：`/today` 的 `directives` 等於日誌中該 execution_date 的允許規則列；鎖內讀取，以 K1 去重。
- N172-C7：store 不 import wording（C-10）。新字面只放 `wording.py`，風控核可前不得合併。
- N172-C8：`settle()`、`settle_pending`、`claim_directive` 零 diff。
- N172-C9：`_init_schema` 不得新增 UNIQUE index。
- N172-C10：修正 `service.py:617-620` 那句不實的 docstring。
- N172-C11：不 DELETE、不 UPDATE 既有指令列。

**測試清單**
- N172-T1：qa 草稿 3 支 expected 測試轉綠。
- N172-T2：週三 as_of、K 線只到週二 → 零新列。
- N172-T3：R2 追價日連續評估 3 次 → `defer_count==1`、批次仍是 planned。
- N172-T4：M1 指數缺漏日，同 T3。
- N172-T5：P1 日評估兩次 → 一列；結算後 remaining 只減一次。
- N172-T6：R1 兩次評估後 MISSED → `missed_count==1`。
- N172-T7：第一次正常、第二次翻成防守或 S3 → 零新列，回應仍列出 R1，並帶揭露句。
- N172-T8：第一次某標的資料缺漏、第二次補齊 → S1 照寫。
- N172-T9：第一次 R3 跳過第 1 批、第二次 → 不得替第 2 批進場。
- N172-T10：thread 與 process 並發，用 Barrier → 恰好一列（比照 T-1、T-2）。
- N172-T11：鎖外讀到過時資料 → 鎖內重讀後零 INSERT（比照 T-3）。
- N172-T12：鎖被占用 → raise（比照 T-4）。
- N172-T13：中途失敗 → 零列、零 defer 變動（比照 T-5）。
- N172-T14：持鎖期間零 I/O（比照 T-6）。
- N172-T15：預先 seed 舊的同鍵重複列 → 回應只列一行。
- N172-T16：連打 3 次 HTTP `GET /today`，回應 body 完全相同。

---

## 驗證

- 全部是讀碼判定。我沒有執行程式或測試，沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。工作樹在 `product/stock-desk`（`.git/HEAD`），N-166 分支的內容只透過交件文件得知。
- 讀過的程式（前綴 `apps/stock-desk/backend/app/`）：
  - `playbook/store.py`：55-314、315-414、461-560、700-983
  - `playbook/service.py`：150-710
  - `playbook/engine.py`：386-695、695-1034、1082-1319
  - `playbook/models.py`：30-69，並 grep 了 94 行
  - `api/playbook.py`：395-449
  - `data/service.py`：936-975
  - `data/calendar.py`：grep 87-93
- 前端：`lib/queries.ts:405-424`，以及 grep 449、465、`page.tsx:38`。
- 文件：
  - 重現報告全文、我的 N-168 評估、我的 4xx 與 N-171、N-174 評估
  - ADR-0034 全文；ADR-0033 的 24-223 行
  - N-166 交件、N-152 執行指令
  - 追蹤清單 254-280、PRD N164N165:270
- 與重現報告的差異：
  - 「重複只在週二當天」更正為「延伸到 T+1 收盤資料進來前」，讀碼判定，待 qa 補測。
  - `queries.ts` 的行號在目前工作樹是 415-422（報告寫 411-418），內容相同。
- 未驗證、需要 qa 重現的項目：V2、V3、V5、週三早上窗口、F8。

---

## 下一步

### 需要 CEO 裁示
1. **N-172 的語意**：是否採 (e)「同一預定執行日首次決策為準、之後只補新決策、回應以日誌為準」？替代方案是「後次覆蓋並撤回前次」，那需要新狀態，而且與 B-2a 不撤回的精神相反，我不建議。
2. **拆分**：N-172a 先做（P1）；N-172b（跨日在途單）等 N-176（F7）定調後再做。
3. **N-174(c) 的揭露句**：列為 N-172a 的合併閘門（建議）；或者若風控無法及時定稿，允許先合併、揭露句後補。
4. **偵測**：是否授權 dev-lead 立即寫唯讀偵測腳本，由您在本機對複本執行？建議是，而且越早越好，最好在 11-03（週二）前。
5. **修復**：
   - D-A：採 R-3 離線工具（建議）或 R-2 只揭露。
   - D-A′、D-B、D-C、D-D：只揭露，逐案裁示。
   - 上線前提：先確認零未結算重複列。
   - R-1 自動遷移、刪列、改寫已結算列，一律 **VETO**。
   - 與 N-166 的 CEO-2（EMERGENCY 重複列）一併裁示，沿用「不清加讀取側去重」。
6. **排序**：N-166 → N-172a → N-171 → N-168；N-164/N-165 排在 N-172a 之後上線。
7. **前端 (f)**：要不要另外調整 `refetchOnWindowFocus`，交 PM 與您決定，非必要。
8. **F8**（S2 不動帳）：是否另開追蹤（建議 medium）。
9. **暫行緩解**：確認採用上面那一句。

### VETO 彙整
- (b) 在遷移或 `_init_schema` 中無條件建 unique index。
- (c) 以結算端的批次層級 claim 或新狀態吸收重複列，當作 N-172 的主修法。
- (d1) 整份評估快取重播，需要儲存 mode_reason，違反 0033 C-9。
- (d2) 當日已提交就整次不寫入。
- 修復採 R-1 啟動自動遷移回補現金；刪除指令列；改寫已結算列的 status。
- 以 `confirm-rules` 重新輸入資金充當修復。

### 交接
- tech-writer：ADR-0035 落檔。
- dev-lead：偵測腳本（現在就做）；N-172a（N-166 合併後）；R-3 修復工具（CEO 核可後）。
- qa-automation：V2、V3、V5、週三早上窗口、F8 重現；N-172 測試轉正。
- risk-compliance-officer：N-174(c) 揭露句。
- devops-sre：上線前檢查零未結算重複列。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-10-31-N172重複R1買單重現-qa-automation.md
- /home/user/AICompany/work/reviews/2026-10-31-N168技術評估-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-31-4xx重複列N171N174評估-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-31-N166實作交件-dev-lead.md
- /home/user/AICompany/work/research/N152-未收盤殘留檢測-執行指令-2026-10-26.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/work/prd/2026-10-29-出清後回饋畫面-N164N165.md
- /home/user/AICompany/docs/adr/0033-stock-desk-EMERGENCY_EXIT重複呼叫的覆蓋判定式冪等.md
- /home/user/AICompany/docs/adr/0034-stock-desk-出清時待結算R買單的處置.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/calendar.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/queries.ts
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/test_n172_repro.py（qa 草稿測試，未 commit）
