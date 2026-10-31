# ADR-0035：stock-desk 排程台同一預定執行日重複評估的決策冪等（補充 ADR-0033、ADR-0034，不取代）

- 狀態：accepted（CEO #83、#86、#88，2026-10-31 裁定；落檔前提：新字面經風控逐字定稿後才可合併、N-174(c) 揭露句為 N-172a 的合併門檻、`GET /today` 上線排序見 Decision 12，詳見 Decision 5、Decision 11 與 Consequences）
- 日期：2026-10-31（tech-architect 草案與追加評估日期 2026-10-31）
- 決策者：tech-architect（草案與技術評估）；CEO #83（採方案 (e)／S-α）、#86（N-174(c) 揭露句列為合併門檻）、#88（G1 併入 N-172a）於 2026-10-31 裁定；#84（授權偵測腳本）、#85（資料修復方式）同日裁定，見 Decision 9。風控（risk-compliance-officer）對新字面的審查**進行中**，尚無逐字定稿，見 Decision 11 與待決。
- 與 ADR-0033、ADR-0034 的關係：
  - **補充 ADR-0033 與 ADR-0034，不取代**。兩份皆維持 accepted，**原文不改**（ADR-0001 決策生效後不得原地改寫；也不在 0033、0034 加指向本 ADR 的註記）。
  - 0033 C-10 第二句（「`record_directives` 與 `apply_effects` 對 `evaluate_today` 的行為不變」）：依 [TA1] 判定，那是 N-166 的**範圍約束**，不是持久決策；本 ADR 是後續決策，二者**不衝突**。見 Decision 10。
  - 0034 Decision 9（F5（N-172）定調前 N-168 不開工實作）：依 [TA1]，本 ADR accepted 時視為滿足，N-168 可開工。排序見 Decision 12。
  - 0033 的 C-3、C-9、C-11 與 0034 的 C-B11 是本 ADR 的限制條件，本 ADR 沿用、不修改（見 Context「限制」）。
  - CEO #87（2026-10-31）修正了 #82 的範圍，該項與 N-166 有關，內容見 [決策包] 第 107 行。**本 ADR 不展開、不依賴該項。**
- 來源簡稱（皆在 `work/` 下，除非另註明）：
  - [TA1]：`reviews/2026-10-31-N172修法與資料修復評估-tech-architect.md`（方案比較表、V1～V6、N172-C1～C11、N172-T1～T16、D-A～D-F、R-1～R-4、VETO 彙整、「ADR-0035 草案」一節）
  - [TA2]：`reviews/2026-10-31-N172評估追加N174N176-tech-architect.md`（S-α～S-δ 表、G1 規格、K3 與 ADR-0036 的關係、「四、ADR-0035 草案的修訂點」、N172-T17～T21、N172-C8 修訂）
  - [決策包]：`dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`（第 101 行 #83、第 102 行 #84、第 103 行 #85、第 104 行 #86、第 107 行 #87、第 108 行 #88；第 106 行 coordinator 定案）
  - [qa-N172]：`reviews/2026-10-31-N172重複R1買單重現-qa-automation.md`；[qa-N174N176]：`reviews/2026-10-31-N174N176重現-qa-automation.md`（本檔未讀其全文，僅引用 [TA1]、[TA2] 對它們的轉述）
  - [ADR-0033]：`docs/adr/0033-stock-desk-EMERGENCY_EXIT重複呼叫的覆蓋判定式冪等.md`
  - [ADR-0034]：`docs/adr/0034-stock-desk-出清時待結算R買單的處置.md`
- 適用範圍：僅 product/stock-desk；程式路徑相對於 `apps/stock-desk/backend/`（前端路徑相對於 `apps/stock-desk/frontend/`）。
- 標註約定：
  - 本檔為 [TA1]、[TA2] 加 CEO #83～#88 與 coordinator 定案的轉錄，屬記錄決策脈絡（B 類）。tech-writer 落檔時**沒有讀 code、沒有執行程式**，也沒有替草案補任何技術細節。[TA1]、[TA2] 自己也標明「全部是讀碼判定、未執行」；其中 V2、V3、V5、週三早上窗口、F8、G1 原子性、F7 與 N-166 擋住出口，待 qa-automation 重現（見待決）。
  - 文內 `檔案:行號` 一律是 [TA1]、[TA2] 撰寫時（2026-10-31，工作樹 `product/stock-desk`）的快照，會隨 commit 漂移，**tech-writer 未逐條重驗**，抽驗請以內容定位。
  - 引用 ADR-0033、ADR-0034 時，本檔改引**條號**（C-10、Decision 9 等），不沿用 [TA1] 的 `0033:行號`、`0034:行號`。
  - **字面規則**：`SAME_DAY_EARLIER_ENTRY_NOTE`、`SETTLEMENT_BATCH_ALREADY_FILLED_NOTE` 的實際文字**一律不寫進本檔**，本檔只寫識別名；逐字由風控定稿，僅放 `wording.py`，風控核可前不得合併。
  - 偵測 SQL 不全文收錄，見 [TA1] 第二節「既有資料修復」。

---

## Context（背景）

以下出自 [TA1]「本次結論」與「一、修法方案比較」、[TA2]「本次結論」。

- **根因（[TA1]，讀碼判定）**：
  - `GET /today` 是帶寫入副作用的 GET（`api/playbook.py:406-435`）。
  - `evaluate_today` 每次都依序呼叫 `apply_effects`、`save_fast_market`、`record_schedule`、`record_directives`，四者各自開 connection，且無條件寫入（`service.py:682-685`）。
  - `service.py:617-620` 的 docstring 寫「It is idempotent, so calling this endpoint repeatedly is safe」，[TA1] 判定與事實不符。
  - 沒有 UNIQUE；`claim_directive` 只防列層級的重放。
  - 未收盤的 K 線會被丟掉（`data/service.py:941-957`），所以在隔天收盤資料進來之前，`data_date` 一直是前一個交易日；危險窗口**延伸到 T+1 收盤**，不只排程日當天。[TA1] 的例子：週三早上打開排程台，本身就會再寫一列（`engine.py:1099-1100`、`service.py:275-291`）。qa 的對照組在週三有 K 線，所以沒有覆蓋到這個情況。此為讀碼判定，待 qa 補測。
  - 前端 react-query 使用預設值。
- **問題不只 R1**：凡是「同一個預定執行日」重算一次，就會重寫一次。已知變體：

  | 代號 | 現象 | 證據（[TA1] 快照） | 狀態 |
  |---|---|---|---|
  | V1 | R1 重複，現金扣 N 倍 | 重現報告 | qa 已重現 |
  | V2 | R2／M1 順延計數一天加 N，最快 3 次就把該批 R3 跳過（`models.py:94` `r3_max_defers=3`，沒有任何下單紀錄） | `engine.py:874-940`、`:739-779`、`:874`、`:932-940`；`store.py:738-741` | 讀碼 |
  | V3 | P1／P2／P3 減碼重複，帳冊超賣、現金多入帳；S/P 賣出每個交易日都評估、不限排程日 | `engine.py:448-580`、`store.py:942-957` | 讀碼 |
  | V4 | 跨日在途：前一次買單沒抓到開盤價而未結算，下一個排程日 R1 又挑同一批 | `engine.py:699-711`；[TA1] 的 N-168 評估 Q4 | 讀碼 |
  | V5 | 重複列一起 MISSED，`missed_count` 一次加 N，可能一天就達 E-2 上限 | `store.py:915-920`、`engine.py:806` | 讀碼 |
  | V6 | `playbook_schedule` 重複列。`_mark_schedule` 會把同鍵的所有重複列一起更新（`store.py:961-976`）；`list_schedule` 在 app 內沒有呼叫端、只有測試使用（[TA1] grep 結果），所以 V6 只是外觀問題 | `store.py:759-782` | 讀碼 |
  | N-174(c) | 同一 data_date 第二次評估翻成凍結或防守，第一次的 R1 照樣結算 | 追蹤清單:276 | 已併入 N-172（qa-N174N176 重現） |

- **「後補 bar 重複扣款」機制（[TA2]，讀碼判定加 qa 實測）**：`settle_pending` 依 id 順序逐列 claim（`service.py:272-298`）；`settle()` 遇到 buy 時不檢查批次狀態，直接覆寫 shares 並扣現金（`store.py:930-941`）。批次一生只會被買一次（`ensure_batches` 用 `INSERT OR IGNORE`，批次從不重置，`store.py:315-325`），但結算端從來沒有執行這條不變式。
- **N-172 範圍擴充**：[TA2] 判定，K1＋K2（Decision 1、2）只能封住「同一執行日的多列」；「跨日的多列（V4）」要靠 G1（Decision 6′，CEO #88 併入 N-172a）或 K3（N-172b，見 Decision 8）。
- **限制**：
  - R10（系統無從得知使用者是否已在券商下單）、R16（回應顯示的列必須是已落檔的列）。
  - 0033 的 C-3（持鎖期間零 I/O）、C-9（`mode_reason` 即時計算、不得儲存）、C-11（錯誤處理）；0034 的 C-B11（engine 邏輯不改）。
  - 覆審結論「mode_reason 禁存快照」（[TA1] 引為 `0033:145`）。
  - CEO #79 選 B-2a 的精神：保留並揭露、不撤回（理由是 R10，使用者可能已經下單）。

## Options（選項比較）

### 一、修法方案（取自 [TA1]）

| 方案 | 內容 | [TA1] 技術判定 | 結論 |
|---|---|---|---|
| (a) 產生 R1 時略過已有未結算 buy 的批次（鎖內判斷） | 修 V1、V4、V5；修不到 V2（defer 列寫入時就是 `settled=1`，`store.py:822`，不算在途）與 V3。同日重開時 R1 會從頁面消失，需要新字面。跨日版遇到 F7（`calendar` weekday fallback 讓執行日落在休市日、永遠結算不了，追蹤清單:279）時，該標的 R 系列會被永久封鎖，比現況退步 | 同日部分併入 (e)；**跨日部分拆成 N-172b，等 N-176 定調**（見 Decision 8） |
| (b) UNIQUE 或 partial unique index | `settled=0` 的 partial 版涵蓋不到 defer，修不到 V2；`INSERT OR IGNORE` 會靜默丟列，資料一變，回應會顯示沒落檔的行，違反 R16；effects 照樣套用；舊 DB 已有重複列時 `CREATE UNIQUE INDEX` 會失敗，啟動時 `_init_schema`（`store.py:297-311`）會 raise，所有端點 500 | **VETO（無條件建 index 版）**。可在盤點確認零未結算重複列之後，另議做成 fail-soft 的縱深防禦（見 Decision 7） |
| (c) 結算時做批次層級 claim，其餘列改判新狀態 | 只修 V1 的現金；V2 完全沒修；V3、V5 要逐規則特判；日誌仍留 N 列；claim 與 settle 分屬兩個 transaction（F2 窗口，需先修 N-169）；要改 `settle()`，與 N-168 的 C-B6 正面衝突；新 `DirectiveStatus`（`models.py:47`）要同步前端 union 與 label 並送風控 | **VETO（作為主修法）**：把評估端的非冪等藏到結算端，V2 仍在卻讓 N-172 看起來已修好 |
| (d1) 當日首次評估整份快取、之後重播 | 修 V1～V6；第一次若資料缺漏（例如持股標的停損沒評估），補到資料後整天也不會再評估 S1，停損時效退步；必須儲存 `mode_reason` 快照，違反 0033 C-9 與覆審「mode_reason 禁存快照」 | **VETO** |
| (d2) 當日已提交就整次不寫入，只重算顯示 | 資料一變，回應顯示的行沒有落檔（R16）；資料恢復後新觸發的 S1 也寫不進去 | **VETO** |
| **(e) 預定執行日 × 決策身分的冪等** | 修 V1、V2、V3、V5、V6、N-174(c)；資料恢復後的新決策照樣寫入；鎖內重讀身分鍵，比照 N-154／N-166；defer 與 skip 的 effect 跟著它的指令列走，被擋下就不套用；MISSED 只會有一列；沿用 N-166 的 `_insert_directives(conn, …)` 與 C-11；不改 `settle()`、不碰 N-168 的 C-B6；engine 不改（符合 0034 C-B11）；schedule 列只在指令列新寫入時才寫、同一個 transaction | **採用（CEO #83）** |
| (f) 前端 `refetchOnWindowFocus:false`、`staleTime` | 只降低觸發頻率；多分頁、隔天早上重開、`retry:1`、網路重連都還會觸發；方向與 N-164／N-165 的 `onSettled` 失效（PRD:270）相反 | 可選的縱深防禦，不可取代 (e)；**coordinator 定案：暫不做**（[決策包] 第 106 行，CEO 可推翻） |
| (g) 拆成 POST /evaluate 加純讀的 GET | 架構上最乾淨；整個前端流程與風控文案都要重審；規模大 | 長期方向，這次不採 |

### 二、同一 data_date 重評估語意（取自 [TA2]，N-174(c)）

| 語意 | 內容 | [TA2] 判定 | 結論 |
|---|---|---|---|
| **S-α 首次決策為準、回應以日誌為準、翻轉時附揭露** | 第二次評估翻成凍結或防守時，不撤回第一次的 R1；`/today` 的 `directives` 照列日誌中該執行日的列，再附一句揭露。帳冊與畫面一致，保留使用者可能已依指令下單的事實（R10）；與 CEO #79 選 B-2a「保留並揭露、不撤回」同一精神；凍結效果照常寫入（freeze 由 `calendar.shift(data_date)` 決定、冪等，`store.py:730-731`） | qa 的兩支 expected 測試會轉綠 | **採用（CEO #83）** |
| S-β 後次覆蓋：撤回前次未成交買單 | 新增撤回狀態；使用者若在第一次回應後已下單（U-A），持倉會對系統隱形；要和結算的 claim 競爭（F2）；等於 0034 方案 A 的翻版，CEO #79 已因同一理由不採 A；要新增 `DirectiveStatus`（`models.py:47`），前端與風控都要改 | 不建議 | **未採** |
| S-γ 延後凍結：同一 data_date 第二次評估不寫凍結，延到下一個 data_date 才生效 | 改變 S3／防守的生效時點，保護動作延遲；等於改規則語意，要 CEO 與風控重裁 | 否決 | **否決** |
| S-δ 現況：不列 R1、照樣成交 | qa 已實測矛盾（[qa-N174N176] :91-93，經 [TA2] 轉述） | **VETO** | **VETO** |

### 三、「後補 bar 重複扣款」的封堵分析（取自 [TA2]）

| 情境 | N-172a（K1、K2） | 加 G1 | 加 K3（N-172b） |
|---|---|---|---|
| 休市日當天重評估，兩列同為 08-12 | 封住，只剩一列 | — | — |
| 08-12 那列卡住，週四又開 08-14 那列，之後 08-12 的 bar 被補上 | **封不住** | 封住：08-12 那列遇到批次已 open，不動帳，列入 unsettled | 封住：週四根本不會開單 |
| 真休市，bar 永遠不會來 | 卡一列（比現況少一列） | 卡一列 | **永久封鎖 R 系列**，除非 N-176 給終點 |
| R10：資料缺漏日使用者其實已在券商成交，週四又成交一次 | 帳冊：現金扣 2 次、股數記 1 次，**自相矛盾** | 帳冊記 1 次並揭露，內部一致，但可能少記 | 不會產生第二張單，根治 |

### 四、既有資料修復（取自 [TA1] 第二節）

不變式：批次永遠不會重置，`ensure_batches` 用 `INSERT OR IGNORE`（`store.py:315-325`），所以任何 (symbol, batch_no) 一生最多只有一列 executed 的 R1 buy。

| 類別 | 判準 | 可信度 | 帳冊影響 | 可否精算 |
|---|---|---|---|---|
| D-A 同鍵 R1 重複成交 | 同一 K1、`COUNT(DISTINCT created_at)>1`、全部 executed、shares 與 `settled_open_price` 都只有一種值 | 高 | 現金多扣 | 多扣金額 = (k−1) × shares × settled_open_price；成立前提：結算價就是開盤價（`service.py:293-298`） |
| D-A′ 同鍵 R1 重複 MISSED | 同上，但狀態是 missed | 高 | `missed_count` 多加 k−1，可能已被 R3 跳過 | 計數可算；「該批是否因此被跳過」會改變之後的指令，不宜回溯 |
| D-B 跨日重複買同一批（V4） | 同一 (symbol, batch_no) 有大於 1 列 executed R1，`execution_date` 不同 | **模糊**（使用者在兩天各看到一張不同的單，R10） | 現金扣兩次 | 只揭露 |
| D-C defer／skip 重複 | 同一 K1，action 是 defer 或 skip | 高 | `defer_count` 膨脹，可能已被 R3 跳過 | 只揭露 |
| D-D P1／P2／P3 賣出重複成交 | 同一 K1，action 是 sell，rule 是 P1、P2 或 P3 | 高 | 帳冊超賣、現金多入帳（帳冊內部一致，但與券商不符） | 只揭露，個案處理 |
| D-E S1、P2 移動停利、S2、EMERGENCY 重複 | 同一 K1 | 高 | 有 `min` 保護，現金與股數不翻倍（[TA1] 引其 4xx 評估:68-82） | 只列計數；EMERGENCY 併入 N-166 的 CEO-2 |
| D-F 未結算的重複列 | 同鍵、`settled=0` | 高 | **下次開頁會被逐列結算，照樣多扣** | 列出警告 |
| D-G（[TA2] 新增）已過執行日仍 pending 的列 | 可用同一 DB 的 `price_bars_cache` 判斷該 symbol 在 `execution_date` 沒有 bar、之後的日期有 bar | — | 代表「疑似休市或資料缺漏」；腳本只列事實，不判斷是休市還是缺漏 | — |

| 修復選項 | 風險 | R16 留存 | 稽核軌跡 | 結論 |
|---|---|---|---|---|
| R-1 啟動時自動遷移、回補現金 | 未經 CEO 確認就改帳；backend 與 scheduler 兩個 process 都會跑；冪等標記一旦遺失就會重複回補；D-B、`set_at` 的情境會誤補 | 不動列 | 現金 KV 沒有歷史，改了就無痕 | **VETO** |
| R-2 只偵測、只揭露 | 帳冊維持錯誤：鐵律①讀到偏低的現金（`engine.py:998-1004`），之後的買單可能被錯誤縮量或取消 | 不動 | 不動 | 可接受，但 [TA1] 不建議長期停在這裡 |
| **R-3 CEO 確認的離線修復工具（只用在 D-A）** | 要停服務、先備份；先 dry-run，再用 `--apply --confirm <dry-run 印出的 token>` 執行；鎖內比對現金未變（compare-and-set）才寫入 | **不 DELETE、不 UPDATE 任何指令列** | 新增加法表 `playbook_adjustments`（id、created_at、kind、directive_ids、cash_before、cash_after、delta、tool_version）；同一組 directive_ids 已校正過就拒絕 | **採用（CEO #85）** |
| R-4 不修 | 帳冊永久對不上 | — | — | 不建議 |

## Decision（決策）

1. **K1 決策身分鍵**（CEO #83）：`(symbol, batch_no, rule_id, action, execution_date)`。
   - `batch_no` 用 `IS` 比對（S2 的 `batch_no` 是 NULL）。
   - 用 `execution_date`、不用 `data_date`：`directive.data_date` 是該標的自己的 K 線日（`engine.py:102-103`），同一次評估中某標的 K 線較晚才到時，用 data_date 當鍵會被當成不同決策；`execution_date` 由這次評估的 data_date 決定（`engine.py:1099`），全部標的一致。（[TA1] 快照）
2. **K2**：R 系列（R1、R2、R3、M1）以 `(symbol, execution_date)` 為單位只決策一次。
   - 必須以標的為單位、不能以批次為單位；否則第一次評估把第 1 批 R3 跳過之後，第二次評估會改挑第 2 批進場，違反「每標的每排程日只處理一批」（`engine.py:704-706`）。（[TA1] 快照）
   - K1、K2 皆**不含** `EMERGENCY`、`REBALANCE`，與 0033 C-4 的覆蓋集合互斥。
3. **單一 `BEGIN IMMEDIATE`**：engine 在鎖外跑，**不改 engine**；持鎖期間零 I/O。在單一 `BEGIN IMMEDIATE` 內：重讀 K1、K2 → 只 INSERT 新的指令列 → 只為新列寫 schedule 列 → 只為新列套用綁定的 effects（`defer_increment`、`batch_skipped`）→ COMMIT。
   - 其餘 effects 維持照現況套用，可留在 transaction 外。[TA1] 判定這些 effects 在同一個 data_date 下是冪等的：freeze 與 blacklist 都由 `calendar.shift(data_date)` 算出相同值；`defense_on` 的 since 等於 data_date；S3 有 `already_frozen` 防護（`engine.py:1112`）；FILL_DEPENDENT 本來就被略過（`store.py:224-226`、`:716-717`）。
   - 若 transaction 之後才失敗，下一次呼叫會自行補齊。
   - `record_schedule` 放進同一個 transaction，同生同滅；既有的 schedule 重複列不修。
4. **`/today` 的 `directives` 等於日誌中該 execution_date 的 R／S／P／M1 列**（存檔版本，以 K1 去重、取最小 id）。由 directives 推導的「無」類敘述，以這份清單為準。
   - 同一天怎麼刷新，看到的都是同一張表，與 R16 一致。
   - 翻成凍結或防守時，第一次寫入的 R1 仍會列出，再附一句揭露（Decision 5）。這和 CEO #79 選 B-2a 的精神一致：保留並揭露，不撤回。
5. **採 S-α（CEO #83）；N-174(c) 揭露句為合併門檻（CEO #86）**：首次決策為準、回應以日誌為準、翻轉時附揭露。
   - **揭露觸發條件**（[TA2]）：清單含 R 系列 buy，**且本次 `mode != "normal"`**。這同時涵蓋 S3、防守、EMERGENCY 凍結。
   - **不得**改用比對 `FROZEN_NOTE` 字串來判斷（比照題 12 的 allowlist 精神，`engine.py:1164-1168`，[TA2] 快照）。
   - 揭露句識別名：`SAME_DAY_EARLIER_ENTRY_NOTE`。**逐字由風控定稿，僅放 `wording.py`，風控核可前不得合併**（目前風控審查中）。
   - 該揭露句列為 N-172a 的**合併門檻**（CEO #86）：揭露句未經風控逐字核可，N-172a 不得合併。
   - qa 的 control「翻轉只出現在 T+1 資料」不受影響：那一列屬於前一個執行日，只出現在 `settlement`，不會出現在當日的 `directives`（[TA2]）。
6. **結算端不改（G1 除外，見 6′）**：不新增 `DirectiveStatus` 狀態值、不做批次層級 claim、`settle()` 零 diff（避開 0034 的 C-B6）。
   - 依 [TA2] 對 N172-C8 的修訂，原草案「結算端不改」改為「除 6′ 的 G1 外不改」；`claim_directive` 與 `settle_pending` 只允許 G1 這一處改動。
6′. **G1 結算端不變式守門（CEO #88，併入 N-172a）**：buy 只能讓 `planned` 批次成交。批次已不是 `planned` 時，該列**不 claim、不動帳**，以專屬理由列進 `settlement.unsettled`。
   - **帳冊假設（CEO #88）**：接受 R10 下「帳冊只記一次並揭露」。
   - **原子化**（[TA2] 規格）：判斷要和 claim 原子化，把條件加進 `claim_directive` 的 UPDATE（`store.py:893-897`），buy 列加上 `AND EXISTS (SELECT 1 FROM playbook_batches WHERE symbol=? AND batch_no=? AND status='planned')`。
   - **區分兩種 rowcount 0**：被擋下時**不得**沿用現行「rowcount 0 就默默 `continue`」的分支（`service.py:293-297`），必須區分「已被別人結算」與「批次已成交」（T21）。後者以新的理由句列入 `unsettled`。
   - 理由句識別名：`SETTLEMENT_BATCH_ALREADY_FILLED_NOTE`。**逐字由風控定稿，僅放 `wording.py`，風控核可前不得合併**（目前風控審查中）。
   - **不得**：新增 `DirectiveStatus`、claim、寫 `missed`、改 `settle()`。
   - 殘留風險：claim 與 settle 分屬兩個 transaction（F2／N-169）。同一次結算循序處理時，G1 有效（第一列 settle 完批次已是 open）；兩個結算請求並發時仍有窗口。
7. **本 ADR 不建 unique index**（`_init_schema` 不得新增 UNIQUE index，N172-C9）。無條件版 VETO；日後若要建，前提是盤點確認零未結算重複列，而且建立失敗要 fail-soft。
8. **跨日在途單（V4）不在本 ADR**：K3（標的有在途 R1 buy 時，R 系列不再開單）屬 N-172b；**K3 與 N-176 的處置合併，另立 ADR-0036「在途單生命週期」，K3 不得早於 N-176 落地**（coordinator 定案，[決策包] 第 106 行，CEO 可推翻）。
   - 理由（[TA2]）：K3 的條件是「同一標的有 `rule_id='R1' AND action='buy' AND settled=0 AND status='pending'` 的列，不限執行日」。N-176 若只揭露，在途單沒有終點，K3 會讓真休市的標的永久停買（qa 實測休市日那列卡了 7 週以上）；N-176 若選順延或作廢，K3 才安全。
   - 順延與作廢都會改動已經發給使用者的指令語意，要送風控。
   - N-176 本體可以另案，但 K3 不能早於它；`work/repro/test_n176_repro.py` 的 expected 測試屬 ADR-0036 的驗收標準，N-172a 落地後**仍應保持紅燈**，不得為了 N-172a 而弱化斷言。
9. **既有資料**（CEO #84、#85）：
   - **先唯讀偵測**（CEO #84 授權、越快越好）：dev-lead 撰寫，比照 N-152（停服務、備份、對複本執行、唯讀、不 import app、不連網），目標 11-03（週二）前。偵測 SQL 見 [TA1] 第二節；偵測類別含 D-A～D-G（見 Options 四）。
   - **D-A：採 R-3 離線修復工具**（CEO #85）：dry-run → CEO 確認 → apply；只回補現金，校正寫入加法表 `playbook_adjustments`；**不刪、不改指令列**。
   - **誤判防護**（[TA1]）：遇到以下情況，該組不給回補金額，只列「需人工判讀」：同一個 `created_at` 卻出現重複鍵；shares 或價格不只一種值；批次 `shares` 不等於單列 shares；`total_deploy_set_at` 晚於該組第一列的結算時間（使用者之後重新輸入過資金，回補會變成重複更正）。現金是單一 KV、沒有異動歷史（`store.py:557-558`），只能從指令列反推。
   - **D-A′、D-B、D-C、D-D：只揭露、逐案裁示**（CEO #85）。後補 bar 造成的重複扣款歸 D-B（[TA2]），依 R10 維持只揭露，不納入 R-3 自動精算。
   - **EMERGENCY 舊重複列：不清、讀取側去重**（CEO #85，N-166 CEO-2）。
   - **上線前提**（[TA1]）：先確認零未結算重複列（D-F）；由 devops-sre 檢查。
   - **VETO**：R-1 啟動自動遷移回補現金；刪除指令列；改寫已結算列的 status；以 `confirm-rules` 重新輸入資金充當修復（它會連帶把 TOTAL_DEPLOY 重算成 capital × ratio，把持股價值排除在外，`service.py:535-539`）。
   - 若 D-A 發生後 CEO 跑過 REBALANCE，TOTAL_DEPLOY 是用偏低的現金算出來的（`service.py:375-376`），回補現金不會自動修正它，由 CEO 決定是否再跑一次 REBALANCE；過去因現金偏低而被縮量的買單是已發出的指令，不回溯。
10. **與 0033 C-10 的關係**：0033 C-10 第二句視為 N-166 的範圍約束；本 ADR 是後續決策，不構成衝突。0033、0034 原文不改。
11. **字面規則與合併門檻（風控閘門）**：
    - `SAME_DAY_EARLIER_ENTRY_NOTE`、`SETTLEMENT_BATCH_ALREADY_FILLED_NOTE` 逐字由風控定稿，僅放 `wording.py`，風控核可前不得合併；`wording.py` 之外不得出現這兩句的實際文字；store 不 import wording（N172-C7）。
    - 這兩句都是面向使用者的文案，屬 CLAUDE.md 最高原則 5 的風險閘門範圍，風控有否決權。
    - 帳冊校正之後若要在 UI 揭露，也要送風控審（[TA1]）。
12. **排序與拆分**（coordinator 定案，[決策包] 第 106 行，CEO 可推翻）：
    - N-172 拆為 **N-172a**（P1；含 K1、K2、G1、Decision 5 的揭露句）與 **N-172b**（K3，併入 ADR-0036）。
    - 排序 **N-166 → N-172a → N-171 → N-168**；N-164／N-165 的開發可並行，上線排在 N-172a 之後。
    - 理由（[TA1]）：N-172a 要沿用 N-166 新增的 `_insert_directives(conn, …)`、`_write_state` 與 C-11 錯誤處理；若與 N-166 平行開發，`store.py` 的 `record_directives` 區段與 `service.py` 幾乎一定衝突。N-172a 排在 N-171 之前，因為 N-171 也要在 `evaluate_today` 的結算之後讀新欄位、碰同一個函式，而 N-172a 是 P1。
    - 偵測腳本只動 `scripts/` 與 tests，現在就可開工；N-172a 的測試現在就可寫，正式程式等 N-166 合併後再寫。
    - 前端方案 (f) 暫不做（見 Options 一）。
13. **實作與測試約束**：以附錄 B（N172-C1～C11）、附錄 C（N172-T1～T21）、附錄 D（VETO 彙整）為準。

## Consequences（後果）

- **好處**（[TA1]）：
  - 不論觸發來源（分頁、隔天早上重開、多分頁、重試），同一個決策只落檔一次，effects 只套一次。
  - 資料恢復後的新決策照樣寫入，停損時效不退步。
  - 頁面在同一天刷新多少次都穩定，而且等於日誌內容。
  - engine 零 diff、`settle()` 零 diff。
- **代價與壞處**：
  - **首次決策為準**（[TA1]）：同一天資料修正後，R 決策不會改。例如第一次判 R2 順延，就要等下一個排程日。
  - 同一批同一天可能先後出現不同規則的賣單（例如 P1 之後又出 S1）。帳冊有 `min` 保護，但使用者會收到兩張單，屬殘留風險（[TA1]）。
  - 回應中的參考價可能早於畫面上的快照價（[TA1]）。
  - store 要新增幾個接收 conn 參數的方法（[TA1]）。
  - 既有重複列留在日誌裡，所有讀取端都要去重（[TA1]）。
  - **G1 會留下永久 pending 列**，直到 ADR-0036 落地：被擋下的列會永遠維持 pending、每天出現在 unsettled（[TA2]）。
  - **G1 在 R10 下採「只記一次」的帳冊假設**（CEO #88）：若使用者其實兩張單都在券商成交，帳冊會少記（[TA2]）。
  - **F2 並發窗口仍在**：F2 與結算時現金的讀改寫競態（`store.py:941`、`:944`）仍在，歸 N-169（[TA1]）；G1 的並發窗口同此（[TA2]）。
  - **對 N-168 的影響**（[TA1]、[TA2]）：
    - N-172a 之後，同一 execution_date 的重複待成交買單只會是舊資料；跨日重複（V4）要到 N-172b 才消失。
    - N-168 的 W-B1「待成交 R 買單」清單（`action='buy' AND settled=0 AND status='pending'`，0034 的 Decision 1）**以 (symbol, batch_no) 去重計批數、股數逐列顯示、不得加總**（比照 N171-C4）。
    - G1 擋下的列會被該清單納入，所以 **N-168 落地時，W-B1 要排除或另行標示「批次已非 planned」的列，交風控定**。
    - L4 戳記會把所有重複列都打上，沒有問題；N-172a 不改 `settle()`，C-B6 不受影響。
  - **F4 與 F2 不在 N-172a 範圍**：F4（S/P 替已有 EMERGENCY 在途單的批次再出賣單，[ADR-0033] 附錄 D）與 F2 仍歸 N-169（[TA1]）。
- **已知風險與外部互動**：
  - **N-166 × F7（[TA2]，讀碼推論，待 qa 實證）**：N-166 加上 CEO #82 後，遇到 F7，休市日那列 EMERGENCY 賣單永遠算「已覆蓋」，再次出清只回 ALREADY_PENDING、不寫新列，批次永遠 open，與 EX-3 衝突。這是 N-166 與 N-176 的互動，不是 N-172 的問題；CEO 已以 #87 修正 #82 的範圍（[決策包] 第 107 行），本 ADR 不展開。
  - **F8（[TA1]，讀碼判定，建議 medium，待 qa 重現）**：S2 指令的 `batch_no=None`（`engine.py:656`），`settle()` 遇到 `batch_no is None` 就直接 return（`store.py:921-923`），結果 S2 成交後帳冊既不減股、也不入帳；不併入 N-172，coordinator 已另開追蹤 N-177（[決策包] 第 106 行）。
  - **R10 無法觀測**：系統無從得知使用者是否已在券商下單；這是 S-α 與 G1 的前提，由揭露字面承擔。
- **被約束**：
  - 禁止在遷移或 `_init_schema` 無條件建 unique index（N172-C9）。
  - 禁止以結算端的批次層級 claim 或新狀態吸收重複列當主修法；G1 不得新增狀態、不得寫 `missed`、不得改 `settle()`。
  - 禁止儲存 `mode_reason` 快照（0033 C-9）。
  - 禁止 DELETE 或 UPDATE 既有指令列（N172-C11）。
  - 在 N-176 給在途單終點之前，禁止單獨上線 K3（Decision 8）。
  - engine 不改（N172-C3）。

## 待決

- **風控**：`SAME_DAY_EARLIER_ENTRY_NOTE`、`SETTLEMENT_BATCH_ALREADY_FILLED_NOTE` 的逐字定稿**審查中**；兩者皆為合併門檻（CEO #86 含前者；後者隨 G1 併入 N-172a，CEO #88）。N-176 順延或作廢的語意、N-168 W-B1 對「批次已非 planned」列的呈現方式，也待風控（[TA2]「應經手但尚未經手」）。
- **qa-automation**：重現 V2、V3、V5、週三早上窗口、F8；N-166 合併後用 `test_n176_repro.py` 重跑 EMERGENCY 的 F7 情境（[TA1]、[TA2]）。在重現前，這些項目在本檔皆為讀碼判定。
- **dev-lead**：N-172a（N-166 合併後，含 G1 與 T1～T21）、偵測腳本（CEO #84，目標 11-03 前）、R-3 修復工具（CEO #85，確認後才寫）。
- **devops-sre**：上線前檢查「零未結算重複列」（[TA1]）。
- **product-manager**：N-176 的處置選項（ADR-0036 的輸入）（[TA2]）。
- **ADR-0036**：「在途單生命週期」（N-172b／K3 與 N-176）尚未起草。
- **暫行緩解**：[TA1] 建議的操作建議（內部操作建議、非面向使用者文案）列於 [TA1] 第一節，屬內部操作建議、非產品決策，不經 CEO 裁示；coordinator 已於 2026-10-31 以 [TA1] 的一句話轉告 CEO（見 [決策包] #88 之後 coordinator 定案）。
- 落檔後待 coordinator 處理：commit、ADR 索引同步。ADR-0033、ADR-0034 不改。本任務只新增本檔，未改其他檔案。

---

## 附錄 A：[TA1]、[TA2] 列出的相關檔案

路徑前綴 `/home/user/AICompany/`：

- `work/reviews/2026-10-31-N172重複R1買單重現-qa-automation.md`
- `work/reviews/2026-10-31-N174N176重現-qa-automation.md`
- `work/reviews/2026-10-31-N168技術評估-tech-architect.md`
- `work/reviews/2026-10-31-4xx重複列N171N174評估-tech-architect.md`
- `work/reviews/2026-10-31-N166實作交件-dev-lead.md`
- `work/research/N152-未收盤殘留檢測-執行指令-2026-10-26.md`
- `work/dispatch/2026-10-17-後續追蹤清單.md`
- `work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`
- `work/prd/2026-10-29-出清後回饋畫面-N164N165.md`
- `work/repro/test_n172_repro.py`、`work/repro/test_n174_repro.py`、`work/repro/test_n176_repro.py`
- `docs/adr/0033-stock-desk-EMERGENCY_EXIT重複呼叫的覆蓋判定式冪等.md`
- `docs/adr/0034-stock-desk-出清時待結算R買單的處置.md`
- `apps/stock-desk/backend/app/playbook/{store,service,engine,models}.py`
- `apps/stock-desk/backend/app/api/playbook.py`
- `apps/stock-desk/backend/app/data/{service,calendar}.py`
- `apps/stock-desk/frontend/app/lib/queries.ts`

## 附錄 B：對實作的約束（N172-C1～C11，交 dev-lead，qa-reviewer 可逐條檢查）

逐條轉錄自 [TA1]；C8 採 [TA2] 修訂版。

- **N172-C1**：K1、K2 的查詢與所有新列 INSERT、schedule INSERT、綁定 effects，都在同一個 conn 的單一 `BEGIN IMMEDIATE` 內完成。錯誤處理照 C-11：`in_transaction` 時 ROLLBACK，然後原樣 raise。
- **N172-C2**：持鎖期間零 resolver、零網路呼叫（比照 C-3）。
- **N172-C3**：`engine.py` 零 diff（C-B11）。
- **N172-C4**：K1、K2 不含 `EMERGENCY`、`REBALANCE`。另加守門測試，釘住「M1 列只由進場段落產生」。
- **N172-C5**：被擋下的指令，它的 `defer_increment`、`batch_skipped` 不得套用；其他 effect 種類要有逐種冪等的表格測試。
- **N172-C6**：`/today` 的 `directives` 等於日誌中該 execution_date 的允許規則列；鎖內讀取，以 K1 去重。
- **N172-C7**：store 不 import wording（C-10）。新字面只放 `wording.py`，風控核可前不得合併。
- **N172-C8（[TA2] 修訂版）**：`settle()` 維持零 diff；`claim_directive` 與 `settle_pending` 只允許 G1 這一處改動。（原版為「`settle()`、`settle_pending`、`claim_directive` 零 diff」，已由 [TA2] 修訂取代。）
- **N172-C9**：`_init_schema` 不得新增 UNIQUE index。
- **N172-C10**：修正 `service.py:617-620` 那句不實的 docstring。
- **N172-C11**：不 DELETE、不 UPDATE 既有指令列。

## 附錄 C：測試清單（N172-T1～T21，交 dev-lead）

T1～T16 逐條轉錄自 [TA1]；T17～T21 轉錄自 [TA2]。

- **N172-T1**：qa 草稿 3 支 expected 測試轉綠（`work/repro/test_n172_repro.py`：3 支 expected 轉正、3 支 observe 刪除、3 支 control 保留，見 [TA1] 第三節）。
- **N172-T2**：週三 as_of、K 線只到週二 → 零新列。
- **N172-T3**：R2 追價日連續評估 3 次 → `defer_count==1`、批次仍是 planned。
- **N172-T4**：M1 指數缺漏日，同 T3。
- **N172-T5**：P1 日評估兩次 → 一列；結算後 remaining 只減一次。
- **N172-T6**：R1 兩次評估後 MISSED → `missed_count==1`。
- **N172-T7**：第一次正常、第二次翻成防守或 S3 → 零新列，回應仍列出 R1，並帶揭露句。
- **N172-T8**：第一次某標的資料缺漏、第二次補齊 → S1 照寫。
- **N172-T9**：第一次 R3 跳過第 1 批、第二次 → 不得替第 2 批進場。
- **N172-T10**：thread 與 process 並發，用 Barrier → 恰好一列（比照 T-1、T-2）。
- **N172-T11**：鎖外讀到過時資料 → 鎖內重讀後零 INSERT（比照 T-3）。
- **N172-T12**：鎖被占用 → raise（比照 T-4）。
- **N172-T13**：中途失敗 → 零列、零 defer 變動（比照 T-5）。
- **N172-T14**：持鎖期間零 I/O（比照 T-6）。
- **N172-T15**：預先 seed 舊的同鍵重複列 → 回應只列一行。
- **N172-T16**：連打 3 次 HTTP `GET /today`，回應 body 完全相同。
- **N172-T17**：週二開 R1、週三缺 bar、週四開 R1、週五成交，之後補上週三的 bar。斷言現金只扣一次，舊列以 G1 理由列入 unsettled。
- **N172-T18**：休市日當天重評估，執行日 08-12 的列只有一列。
- **N172-T19**：qa `work/repro/test_n174_repro.py` 的 8 個 expected 轉綠，observe 刪除，control 保留。
- **N172-T20**：G1 不影響正常的單次成交，也不影響 planned 批次的 MISSED（`missed_count` 照樣加 1）。
- **N172-T21**：G1 與「已被別人 claim」兩種 rowcount 0 的情況分得開。

（T-1～T-6 為 [ADR-0033] 附錄 B 的測試編號。）

## 附錄 D：VETO 彙整

轉錄自 [TA1]「VETO 彙整」與 [TA2]「VETO 追加」。

[TA1]：

- (b) 在遷移或 `_init_schema` 中無條件建 unique index。
- (c) 以結算端的批次層級 claim 或新狀態吸收重複列，當作 N-172 的主修法。
- (d1) 整份評估快取重播，需要儲存 `mode_reason`，違反 0033 C-9。
- (d2) 當日已提交就整次不寫入。
- 修復採 R-1 啟動自動遷移回補現金；刪除指令列；改寫已結算列的 status。
- 以 `confirm-rules` 重新輸入資金充當修復。

[TA2] 追加：

- S-δ：維持現況，翻轉後不列、照樣成交。
- 在 N-176 給在途單終點之前，就單獨上線 K3。
- G1 沿用 `missed` 狀態、新增 `DirectiveStatus`，或改動 `settle()`。
