# 警示每一輪紀錄與檢查未完成揭露 ADR-α、(B) 修訂 ADR-β、D-10 取代 ADR-γ 草案

- 審查者：tech-architect
- 日期：2026-11-22
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：(B) 修訂與警示一輪未完成揭露的新 ADR（RC-652～RC-654），以及 ADR-0029 D-10 的取代草案

全程唯讀，只用了 Read、Glob、Grep，搜尋都指定了明確路徑。沒有讀 `.env*`，沒有碰 `apps/stock-desk/backend/data/`，沒有看 `.claude/worktrees/`，也沒有寫任何檔。
本件所有 CEO 可見字面都標「字面待風控定稿」。ADR 編號都用代稱（α、β、γ），由 tech-writer 落檔時取號。

---

## 本次結論

1. **RC-652 第 1～11 點、RC-653 第 1～6 點、RC-654 第 3 點全部採用**，RC-654 第 3 點的 suggested 也採用。有三處是讀法問題，要請風控確認。它們列為待決，不算不採：
   - **(i) 優先序**：RC-652 第 3 點寫「D 照舊最優先」。但現行 R-A3 的順序是 C 先於 D（`AlertStatusStrip.tsx:28-30`）。我照現行順序（C → D → A → E → B）。
   - **(ii) 「每一輪」讀為排程輪**：手動檢查不寫入紀錄，也不推播。
   - **(iii) 狀態 E 分四種變體**：本輪未完成、本輪中止、紀錄過期、尚無紀錄。

   風控如果不接受 (i) 或 (ii)，才算觸發 RC-651 (c)。
2. **落點**：RC-652、RC-653、RC-654 不塞進 (B) 的 ADR，另立 **ADR-α**。理由有二：
   - RC-652 不分成因，而且要先於 (B) 落地；
   - (B) 的 ADR 性質是修改 ADR-0017 C4。

   (B) 的 ADR（**ADR-β**）修訂約束 4、8、9、11 和 Consequences，並引用 ADR-α。RC-653 第 6 點允許「另外附一段」，所以這樣放符合它的要求。
3. **PR 先後**（RC-652 拆成獨立 PR，先於 (B)）：
   - 順序：**α1（RC-653）→ α2（RC-652 主體加 RC-654 第 3 點）→ (B) → α3（RC-652 第 8 點，狀態 B 的附註）**。
   - (A) 和這幾支沒有技術相依，各自獨立 PR，不得和任何一支同 PR。(A) 可以排進序列裡任一個空檔，建議排在 α2 之後。
   - 全部 PR 的合併時點都受 RC-556 約束 8 (a)～(d) 限制，也都不碰 `code_digest` 範圍。
4. **門檻、紀錄與 API 位置**：
   - 推播「開始」：連續 2 次排程輪未完成時送出。
   - 推播「恢復」：已經送過開始通知之後，第一次完成的那一輪送出。
   - 常數放 `app/alerts/tick_status.py`。
   - 紀錄放在警示 DB 新增的單列表 `alert_tick_status`。
   - API 是在 `GET /api/alerts/events` 的回應加新欄位 `last_tick`。
5. **ADR-0029 D-10**：用 **ADR-γ** 只取代 D-10，不取代 ADR-0029 全檔。
   - 第 1 點改成三個條件，涵蓋四種憑證。
   - 第 2 點採 **(b)**，但確認的動作改成**產品內的「測試推送」操作**。風控推論的做法是讓 CEO 執行 selftest 指令，我不採，因為它和「不得請 CEO 執行指令」一類的裁定衝突。
6. **自我更正**：原 (B) 的 Consequences 寫「警示停止期間，CEO 只有在開啟畫面時才會知道」。RC-652 已判定這句不成立，本次刪除並改寫。

---

## 各部門回報（tech-architect）

### 一、逐條採或不採

| 條目 | 採／不採 | 落點與說明 |
|---|---|---|
| RC-652-1 觸發範圍（`load_failures > 0`，不分成因） | 採。我把判定收緊成**規則數**：「本輪有 ≥1 條規則因載入失敗而略過」 | ADR-α D-2。現行 `load_failures` 是按標的計數。一個標的如果只有 W-2 規則（永久略過，先判），它的載入失敗不會讓任何規則因此被略過 |
| RC-652-2 每一輪持久化 | 採。「每一輪」讀為排程輪（待決 ii） | D-2：單列表、固定欄位、不帶例外原文、數量、成本、備註、代號、規則 id |
| RC-652-3 狀態 E、優先序 | 採。優先序照現行 R-A3（待決 i），E 分四種變體（待決 iii） | D-3 |
| RC-652-4 E 不用中性樣式 | 採 | 交 art-lead，送風控核 |
| RC-652-5 推播開始與恢復各一則、門檻、`notify_webhooks` | 採。門檻 = 2 | D-4；殘留寫進 Consequences |
| RC-652-6 ADR-0029 通道 | 採（suggested，不實作） | D-8：devops-sre 決定，不得當成替代 |
| RC-652-7 手動檢查分類 | 採 | D-5 |
| RC-652-8 其他原因略過的計數 | 採。計數在 α2 落地，狀態 B 的附註另開 α3 | D-6 |
| RC-652-9 字面約束 | 採 | D-7 |
| RC-652-10 測試 | 採，另外加了幾支 | 約束 α2-T |
| RC-652-11 時點、和 (B)、(A) 的關係 | 採 | 第五節 |
| RC-653-1 快照分兩段 | 採 | D-1 |
| RC-653-2 用到持倉的價格或訊號規則歸到風險上限側 | 採。〔推論〕目前沒有這種規則：ADR-0021 K-1 的 `ALERT_RULE_FIELDS` 不含 `position.*`，`signal_context` 也不帶持倉。PR 要逐一列出並用測試釘住 | 約束 α1-4 |
| RC-653-3 降級時的推播內容 | 採。進一步要求：帳本失敗時，價格與訊號規則的 fired 訊息要和帳本正常時**逐字相同** | 約束 α1-6 |
| RC-653-4 新的略過理由（帳本失敗另一句） | 採。共兩個常數 | D-1，字面待風控定稿 |
| RC-653-5 測試 | 採 | 約束 α1-T |
| RC-653-6 寫進 ADR | 採。寫進 ADR-α | — |
| RC-654-3 狀態 B 改顯示最近一次檢查時間 | 採。**取代**「查詢時間」，不並列；尚無紀錄時不顯示 B | D-3 |
| RC-654-3 suggested：超過 2 倍間隔不顯示 B | 採 | D-3 的 E 變體「紀錄過期」 |
| (B) 約束 4、8、9、Consequences | 採，修訂全文見第三節 | ADR-β |

### 二、ADR-α 草案（交 tech-writer 在 `product/stock-desk` 落檔，狀態 proposed）

**標題建議**：「stock-desk 警示每一輪結果持久化、檢查未完成的揭露與快照分段載入」

- 適用範圍：只限 `product/stock-desk`。
- 關聯：
  - 和 ADR-β 互相引用；
  - ADR-0021 的 K-1、K-6、T-6 不變；
  - ADR-0014 的 I-9 不變；
  - ADR-0029 見 D-8。

#### Context
- **快照一失敗，整個標的的規則都停**：`snapshot.py:130` 的 `build_summary` 和價格、訊號規則共用同一份快照。`engine.py:501-511` 的 `_load_isolated` 接住所有 `Exception`，然後回傳空快照。結果是價格規則和訊號規則也一起被略過，而且理由寫錯：收盤價明明存在，理由卻寫「沒有可用的最新收盤價。」（dev-lead I-3、I-4）。
- **一輪的結果沒有留下來**：`scheduler.py:412-425` 只記 log，有事件時才推播，`outcomes` 被丟掉。警示 DB 只有 `alert_rules` 和 `alert_events` 兩張表（`alerts/store.py:28-56`）。
- **首頁會主動顯示放心訊息**：狀態 B 顯示「N 條規則已設定，目前沒有待處理警示」，再加上「查詢時間」。這個時間來自 `events.as_of`，也就是 API 回應當下的時間，不是檢查時間（`AlertStatusStrip.tsx:103-107`、`api/alerts.py:185-188`）。
- **重啟後第一輪要等一個間隔**：警示 job 沒有啟動補跑（`scheduler.py:651-659`，沒有 `next_run_time`），所以重啟後最多要等一個間隔才有第一輪。
- 風控的判定：RC-650 判為 high，RC-652、RC-653、RC-654 為 required。

#### Options

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **紀錄 p1：單列最新狀態表 `alert_tick_status`（採用）** | 固定大小；開始與恢復的判定只需要前一輪狀態；重啟後保留 | 沒有歷史 | 中：狀態壞掉時通知會錯。緩解：讀取時驗證封閉列舉，讀不出來就當作「尚無紀錄」（不顯示 B） |
| 紀錄 p2：每輪 append 的歷史表 | 可以回溯 | 無界成長，要另訂保存規則；需求沒有要求 | 不採 |
| 紀錄 p3：只放記憶體或 log | 零 schema | 違反 RC-652-2（重啟後要能回答） | 否決 |
| 紀錄 p4：寫檔 | 不動 DB | API 和排程是兩個行程，要另外處理檔案鎖與路徑；違反既有「狀態進 DB」的慣例 | 不採 |
| **API q1：在 `AlertEventListResponse` 加 `last_tick`（採用）** | 狀態列原本就查這個端點；事件和狀態在同一個回應，不會出現一個成功、一個失敗的組合；09-19 原本也建議放這裡 | 事件端點多帶了一個非事件欄位 | 低 |
| API q2：新端點 `GET /api/alerts/status` | 職責分離 | 狀態列要多一個 query，它失敗時又要另立一態（不得退回 B） | 不採 |
| API q3：放在規則列表 | — | 語意不合 | 否決 |
| **推播 n1：連續 2 次排程輪才送開始，恢復時送一則（採用）** | 單一輪的暫時性例外（例如 SQLite busy）不會推播；開始、恢復各一則 | 開始最多延後一個間隔（預設 60 分鐘） | 中：延後期間只有畫面揭露 |
| 推播 n2：門檻 1 | 最即時 | 暫時性失敗會造成開始加恢復兩則推播 | 不採 |
| 推播 n3：每輪重送 | — | RC-652-5 禁止 | 否決 |
| 推播 n4：改走 ADR-0029 維運通道 | — | RC-652-6 禁止當成替代 | 否決 |
| **分段 s1：在 `snapshot.py` 內隔離帳本段，`SymbolSnapshot` 帶失敗代號（採用）** | 不改 `SnapshotLoader` 介面，API 和排程兩個呼叫端不用改形狀；engine 維持不碰資料 | 隔離放在接線層 | 低 |
| 分段 s2：engine 分別呼叫行情 loader 和帳本 loader | 隔離放在 engine，邊界清楚 | 介面要改，兩個呼叫端和所有測試替身都要改 | 不採：改動面大，好處只在形式上 |

#### Decision
- **D-1 快照分兩段（RC-653）**
  - **行情段**：`load_bars`、`compute_signals`、`atr_from_signals`。
  - **帳本段**：`build_summary`、`resolve_fx_quote`、`build_book_context`、Kelly 輸入的讀取、`evaluate_limits`。
  - 帳本段在 `snapshot.py` 內用 `except Exception` 隔離。失敗時：
    - 快照保留行情段的 `close`、`currency`、`signals`、`as_of`、`data_disclosure`；
    - `limits=()`，`fx_disclosure*` 和 `price_cap_cause` 為 `None`；
    - `reason` 只放行情段的部分；
    - 新欄位 `book_load_failure` 填 `positions_unreadable` 或 `book_other`。
  - 行情段或 loader 本身拋出的例外，照舊由 `_load_isolated` 接住。空快照改帶 `snapshot_load_failed=True`。
  - `_evaluate_one` 的判定順序：
    1. W-2（ADR-0021 K-6，永久略過，歸類為「其他」）；
    2. `snapshot_load_failed`：所有類型都回 `SNAPSHOT_LOAD_FAILED_REASON`；
    3. 風險上限規則遇到 `book_load_failure`：回 `BOOK_LOAD_FAILED_REASON`；
    4. 其餘照舊。
  - 兩個理由常數都是**字面待風控定稿**。
- **D-2 每一輪的紀錄（RC-652-1、RC-652-2、RC-652-8）**
  - 只有排程輪寫入；總開關關閉時跳過的那一輪不寫。
  - 欄位：
    - `completed_at`：UTC ISO8601；
    - `outcome ∈ {complete, incomplete, aborted}`；
    - `enabled_rules`；
    - `skipped_load_failure`；
    - `skipped_load_failure_risk_limit`；
    - `skipped_load_failure_price_signal`；
    - `skipped_other`；
    - `failure_kinds`：JSON 陣列，值只限 `positions_unreadable`、`book_other`、`snapshot_other`、`tick_aborted`；
    - `interval_minutes`：排程註冊時用的值；
    - 內部欄位 `failure_streak`、`failure_notice_sent`。
  - `outcome` 的定義：
    - `incomplete`：本輪有 ≥1 條規則因載入失敗而略過；
    - `aborted`：例外逃出 tick 主體（例如設定或規則讀取失敗）。這時先寫紀錄，再把例外往外拋給 `_guarded`。這一點是我依 RC-652 的原意擴大的範圍，方向是保守的。
  - `skipped_other` 只算 `status == "skipped"` 而且不是載入失敗的規則，W-2 也算在內。混合情形的 quiet（`UNEVALUATED_LIMITS_NOTE`）不算。
- **D-3 首頁狀態列（RC-652-3、RC-652-4；RC-654-3）**
  - 判定順序：
    1. 有事件 → C。E 的條件成立時，同一個容器裡加一行 E 的說明；
    2. 總開關關閉 → D；
    3. 規則 0 條 → A；
    4. E 的條件成立 → E；
    5. 其餘 → B。
  - E 的條件與變體，判定時依序看：
    1. `last_tick` 為 null：**尚無紀錄**；
    2. `stale`（`now - completed_at > STALE_AFTER_INTERVALS(=2) × interval_minutes`，由伺服器在回應當下計算）：**紀錄過期**；
    3. `incomplete`：**本輪未完成**，字面要帶出哪一類規則、幾條、這段期間不推播、最近一次檢查的時間；
    4. `aborted`：**本輪中止**。
  - 狀態 B 的時間改成 `last_tick.completed_at`，標成「最近一次檢查」一類的說法。字面待風控定稿。
  - E 的視覺交 art-lead。
- **D-4 推播（RC-652-5）**
  - 狀態轉移由純函式 `advance(previous, observed, notify_enabled)` 計算：
    - 失敗輪：`streak + 1`。當 `streak ≥ NOTICE_AFTER_CONSECUTIVE_FAILED_TICKS(=2)`、還沒送過、而且 `notify_enabled is True` 時，送開始通知，並標記已送。
    - 完成輪：如果已送過開始通知，而且 `notify_enabled is True`，送恢復通知。不論送不送，都把 `streak` 和已送標記歸零。
    - `aborted` 輪如果讀不到設定，`notify_enabled = None`，不送。
  - 順序：先寫入紀錄與狀態（同一筆 UPSERT），再推播。寫入失敗時不推播，記 ERROR。送出失敗照 `notify_all` 的現行規則處理，不重送。
  - 推播只經 `app/alerts/notify.py` 內既有的 `_deliver` 送出，日後 ADR-0029 抽出 `push_channels` 時會一併帶走。
- **D-5 手動檢查（RC-652-7）**
  - `EvaluationResponse` 加 `skipped_load_failure`、`skipped_other`，每一列 outcome 加 `skip_cause`。
  - 結果句要分開寫出「因資料讀取失敗而略過 N 條」。字面待風控定稿。
  - 手動檢查不寫紀錄、不推播（待決 ii）。理由：狀態列回答的是「排程有沒有在檢查」。手動檢查成功，不代表排程會成功；手動檢查也不推播（`api/alerts.py:15-16`）。如果讓它寫進紀錄，開始與恢復的判定會被打亂。
- **D-6 其他原因的略過（RC-652-8）**：計數在 α2 落地。狀態 B 的附註（「其中 M 條這一輪無法判定」，字面待風控定稿）在 α3 落地，條件是 `skipped_other > 0`。
- **D-7 字面（RC-652-9）**：creative-lead 起草，風控逐字審。不得：
  - 叫 CEO 改 DB 或檔案、執行工具、看 log；
  - 承諾什麼時候恢復；
  - 在恢復通知寫「恢復正常」「沒有問題」；
  - 把「略過」寫成「沒有觸發」。
- **D-8 和 ADR-0029 的界線**：
  - ADR-0029 Options F 和 D-8 禁止跨執行狀態與「已恢復」通知，範圍只限 `app.ops_alert`。本 ADR 在 `app.alerts` 新增跨執行狀態與恢復通知，不受那兩條約束，也不修訂 ADR-0029。
  - `app.ops_alert.*` 本來就不得 import `app.alerts.*`（ADR-0029 D-1），所以不得讀取本紀錄。
  - 要不要另外經 ADR-0029 通道送出，由 devops-sre 決定，不得當成對使用者揭露的替代。

#### Consequences
- **好處**：
  - 帳本失敗時，價格與訊號規則照常評估與推播；
  - 檢查沒有完成時，首頁不再顯示狀態 B；
  - 設定過推播的使用者，在開始與恢復時各收到一則；
  - 「最近一次檢查」有了事實來源；
  - 排程停止或重啟後還沒跑時，經過 2 倍間隔，畫面不再顯示 B。
- **壞處與殘留**（照實寫）：
  - 沒有設定推播通道，或 `notify_webhooks` 關閉時，只能靠畫面。
  - 推播「開始」至少要第 2 個連續失敗輪才送出；預設間隔下最多延後約 60 分鐘。
  - 排程沒有在跑時不會有任何推播（沒有 dead-man's switch），畫面要等 2 倍間隔才轉成 E。
  - 寫入紀錄之後、推播之前如果行程中止，那一則通知就遺失，不會重送。
  - 警示 DB 寫入失敗時沒有紀錄，畫面要等到過期才轉成 E。
  - 手動檢查成功不會更新狀態列；資料修好之後，E 最多再停留一個間隔。
  - 失敗期間關閉 `notify_webhooks` 的話，不會收到恢復通知。
  - `aborted` 輪如果讀不到設定，不推播。
  - 紀錄只保留最近一輪，沒有歷史。
  - 混合情形的 quiet 不算進 `skipped_other`。
  - 新增一張表、一組 API 欄位、四種 E 變體、兩則推播字面、兩個略過理由。
  - 推播量會增加。
  - (B) 合併之前，帳本讀取失敗一律記為 `book_other`。
  - 前端多久重抓一次，我沒有查證；畫面上的過期判定取的是該次回應當下的時間。
- **回滾**：程式移除使用處即可。表留著沒有害處。ADR 要退回時，開新 ADR 取代。

#### 對實作的約束（qa-reviewer 可以逐條檢查）

**α1（RC-653）**
1. 帳本段涵蓋的讀取：持倉、估值、`resolve_fx_quote`、Kelly store、`evaluate_limits`。Kelly 的讀取要移進帳本段，現在它在兩個 loader 的閉包裡（`scheduler.py:409`、`api/alerts.py:249`）。簽章由 dev-lead 決定。
2. 帳本段失敗時，記一行固定開頭的 WARNING，只帶市場、失敗代號、例外類別名，**不帶 `exc_info`**。〔推論，未實測〕pydantic 的 `ValidationError` 字串會帶輸入值，可能把持倉欄位寫進 log。
3. `_load_isolated` 的現行 log 不改；本 PR 之後，帳本例外已經不會到達那裡。
4. PR 說明逐一列出價格與訊號規則用到的輸入，證明都沒有用到持倉。加一支測試斷言 `signal_context` 不含 `position.*`。
5. 兩個新理由常數只在載入失敗時使用。理由已有測試的既有常數（例如 W-2、`UNEVALUATED_LIMITS_NOTE`）零 diff。
6. 帳本失敗時，價格與訊號規則的 fired 訊息和帳本正常時逐字相同，`BAR_AS_OF_NOTE` 和 `data_disclosure` 照舊附上。資料新鮮度規則不得放寬。
7. ADR-0021 T-6：index resolver 呼叫 0 次。ADR-0014 I-9：在「被呼叫就 raise」的假報價服務下照樣通過。
8. `RuleOutcome` 加 `skip_cause`（status 為 skipped 時必填）。`EvaluationResult` 提供分類計數。
9. **T（測試）**：
   - 帳本失敗時，價格規則 fired 或 quiet 照常；
   - 風險上限規則 skipped，理由是新常數；
   - 反向：帳本正常時零行為差異；
   - 行情段失敗時，所有類型都用新理由；
   - W-2 規則在載入失敗時仍回 W-2，歸類為「其他」。

**α2（RC-652 主體，加 RC-654 第 3 點）**
1. 表結構依 D-2，用 `CREATE TABLE IF NOT EXISTS` 新增，不 ALTER 既有表。值只能是封閉列舉，讀取時驗證，不合法就當作 null。
2. 不寫例外原文、代號、規則 id、數量、成本、備註（grep 加測試）。
3. `evaluate_alerts_tick` 接收 `interval_minutes`，在註冊處傳入 `alert_minutes`。總開關關閉時不寫紀錄。
4. 推播文字只由固定常數、計數與時間組成。標題要和 `[stock-desk 警示]` 區分。要不要附 `ALERT_DISCLAIMER_LINE`，交風控決定（待決）。
5. `notify_webhooks` 為假，或通道沒有設定時，不送。
6. 手動檢查不寫紀錄、不推播。
7. 前端的狀態判定抽成純函式，照 D-3 的順序。狀態 B 不再使用 `buildAlertsQueriedAt`。
8. **T（測試）**：
   - 帳本失敗的一輪：有寫入紀錄、事件 0 筆、狀態列不是 B；
   - C 和 E 同時出現；
   - 開始與恢復各送一次，連續失敗時不重送；門檻前一輪不送；
   - `notify_webhooks` 關閉時不送；
   - 行程重啟後讀回紀錄，狀態一致；
   - 尚無紀錄、紀錄過期都不是 B；
   - `aborted` 輪有寫入紀錄，例外照樣拋給 `_guarded`；
   - 手動檢查的結果句分開兩種略過數，而且不寫紀錄；
   - 反向：正常的一輪，畫面與推播零行為差異（只有 B 的時間來源改變）。
9. 走 qa-reviewer 加 Codex。qa-e2e 看 375 與 1280 兩種寬度，包括 C+E。字面與視覺送風控。

**α3（RC-652 第 8 點，medium）**：只改前端與字面。條件是 `skipped_other > 0`。測試要包含 0 條時不出現附註。

### 三、ADR-β（(B) 無法讀取列）修訂版：只列有改的部分，其餘照原規格

- **Context 加一條**：警示的分段載入、每一輪紀錄與狀態 E 由 ADR-α 承接。本 ADR 只補 `positions_unreadable` 的分類。
- **約束 4（修訂）**：
  - 409 錯誤處理器，以及 `GET /api/positions` 的 200 加 `unreadable`，照原規格。
  - 明確失敗的端點清單裡，「警示快照」改成「**只有警示快照的帳本段**走明確失敗（ADR-α D-1）」：
    - `UnreadablePositionsError` 在帳本段被接住，記為 `positions_unreadable`；
    - 風險上限規則略過，理由用 `BOOK_LOAD_FAILED_REASON`；
    - 價格與訊號規則照常評估。
  - `POST /api/alerts/evaluate` 不回 409，回 200 並帶分類略過數。
  - 排程那一輪寫 `outcome=incomplete`、`failure_kinds ∋ positions_unreadable`，不得拋出未分類的例外。
- **約束 8（修訂）**：
  - 原因句要說三件事，字面待風控定稿：
    - 有 N 筆持倉紀錄無法讀取，修正之前不計算任何數字；
    - **風險上限類的警示規則停止檢查與推播**；
    - **價格與訊號規則照常**。
  - 這句要和 (B) 合併當時的實際行為相符，並用測試釘住：同一個 fixture 下，價格規則 fired，風險上限規則 skipped。
  - 不得引導 CEO 改 DB 或執行指令。
  - 如果 (B) 比 α1 先合併（不建議），原因句要改成「這些標的的所有警示規則都停止」，並重送風控審。
- **約束 9（修訂）**：
  - 使用者揭露（紀錄、狀態 E、開始與恢復推播）由 ADR-α 承接。
  - (B) 只補兩件事：
    - 帳本段的分類器辨識 `UnreadablePositionsError`，記為 `positions_unreadable`，其他例外照舊記為 `book_other`；
    - 記一行固定開頭的 WARNING，含筆數與 id，不帶欄位原始值，也不帶 traceback。
  - ADR-0029 通道照舊交 devops-sre 決定（suggested），不得當成替代。
- **約束 11（修訂）**：
  - 前提是 α1、α2 已經合併；
  - 獨立 PR；
  - 合併時點受 RC-556 約束 8 (a)～(d) 限制；
  - 不碰 `code_digest` 範圍，附 diff 為空的證明；
  - 走 qa-reviewer 加 Codex、qa-e2e、風控。
- **新增約束 12**：PR 說明與 ADR 都不得寫成「警示問題已解決」（RC-652-11）。
- **新增約束 13（測試）**：有無法讀取列時：
  - 排程那一輪的紀錄帶 `positions_unreadable`；
  - 狀態列是 E；
  - 價格規則照常；
  - 風險上限規則用新的理由常數。
- **Consequences（修訂）**：
  - **壞處**：
    - 只要有一列無法讀取，所有數字畫面都不可用，直到修好為止；
    - 風險上限類警示也停止；α1 之後，價格與訊號規則照常；
    - 對使用者的阻斷程度和現在相同，差別是說得出原因；
    - 新增一組字面與一個 API 錯誤契約。
  - **殘留**：
    - 修好之前沒有任何數字；
    - 風險上限類警示停止期間，首頁顯示狀態 E；設定過推播、而且 `notify_webhooks` 開著的話，開始與恢復時各收到一則；
    - 沒有設定推播時，只能靠畫面；
    - 開始通知至少延後到第 2 個失敗輪；
    - **(B) 本身不改善警示的可見性，可見性由 ADR-α 提供**。
  - **刪除**原句「警示停止期間，CEO 只有在開啟畫面時才會知道」，理由是 RC-652 判定它不成立。
- ADR-0017 待決點 2 的處理照原規格，不變。

### 四、ADR-γ 草案：取代 ADR-0029 D-10（交 tech-writer 在 `product/stock-desk` 落檔，狀態 proposed）

**標題建議**：「stock-desk 維運告警 D_v 閘門改寫：憑證輪換條件與送達確認的處理方式」

#### Context
- RC-616 第 5 點：D-10 第 1 點不得保留「CEO 已完成主機 log 清查」。原因是清查要 CEO 讀 log，違反 RC-580 第 4 點和 RC-608 第 1 點，也和 security-engineer 選的 (c) 不一致。
- RC-621 第 1 點：範圍擴大到四種憑證。
- RC-617 第 3 點：第 2 點只有在新程式執行之後才觀測得到，不得寫成合併前閘門。
- ADR-0029 目前在 `app/ops_alert/` 只有 `__init__.py`、`model.py`（security-engineer 11-22）。

#### Options（取代的方式）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 原地修訂（ADR-0029 仍是 proposed，技術上允許） | 一處就改完 | RC-616 第 5 點要求開新 ADR；閘門的改寫歷史不好追 | 不採 |
| **新 ADR 只取代 D-10（採用）** | 範圍最小，其他條文不必重審 | ADR-0029 全檔仍是 proposed，D-10 和 D-9 要加註指向 | 低 |
| 新 ADR 取代 ADR-0029 全檔 | 一份完整 | 要重審全部 OA 和風控知悉，和本題無關的條文也被捲進來 | 不採 |

#### Options（第 2 點的處理方式，依 handoff-protocol〈閘門的時點表述〉第 3 點；本節在 main 的落檔狀態沒有查證，出處先用 tech-architect 11-22 定稿檔）

| 方案 | 判斷 |
|---|---|
| (a) 先合併唯讀工具，由使用者執行並回貼結果 | **不採**：selftest 會對外送出訊息，不是唯讀；要 CEO 執行 `python -m`，和草案三 Decision 3、RC-580 第 4 點、RC-622 第 3 點「不得出現指令」衝突 |
| (b-i) (b) 加上 CEO 執行 selftest 指令（風控的推論） | **不採**：確認的動作不是「產品內的操作」，又是執行指令，理由同上 |
| (b-ii) (b) 加上產品內的按鈕，觸發維運 sink 的 `deliver()` | 不採：要改寫 ADR-0029 D-9 和 OA-21（API 不得 import selftest），維運告警也會變成使用者可以觸發 |
| **(b-iii) (b) 加上產品內的「測試推送」操作，走 `app.push_channels`（採用）** | 和維運告警用同一組環境變數、同一條傳輸，所以設定是否有效可以由 CEO 在產品內完成確認；不動 D-9 |
| (c) 無法事前攔截，改成事後揭露 | 不採：設定錯了的話，fail-closed 事件只會進 log，而 CEO 不得被要求讀 log，這正是 ADR-0029 否決方案 E 的理由。如果 product-manager 或風控不接受 (b-iii) 的按鈕，(c) 才作為後備，要由風控判定 |

#### Decision（新 D-10，取代 ADR-0029 D-10；D_v 指結算程式接線 PR 合併進 `product/stock-desk` 之前）

1. **憑證與 log（三個條件全部成立）**：
   - 1-i. R-1 修補已經合併進 `product/stock-desk`，而且有測試（已成立：合併 commit `3903df1`，依 security-engineer 11-22）。
   - 1-ii. CEO 對**四種憑證（Telegram 推送、Discord 推送、FinMind、Alpha Vantage）整體**回覆「已輪換」或「沒有設定過」，並依 handoff-protocol 第 3 點 (c) 記錄殘留：
     - 殘留包括 RC-616 第 2 點三項、(v)，以及 RC-621 第 2 點三項；
     - 出處是追蹤清單裡 CEO 回答的紀錄，寫法照 RC-615、RC-619，註明「團隊未查證」；
     - 只換了部分、「不確定」「暫不輪換」「先不回答」、貼出任何值，都算**未成立**；
     - 範圍的出處：devops-sre 資料源盤點，以及 RC-618、RC-621。
   - 1-iii. devops-sre 的資料源盤點，包括補掃 `scripts/`、`tests/`、`backend/scripts/`，已經結案，結論已併入。補掃如果查到其他會寫出憑證的路徑，另外送風控判定（RC-621 第 4 點）。
   - 不要求 CEO 清查、打開或刪除任何 log。
2. **送達確認：採 handoff-protocol 第 3 點 (b)**：
   - **PR-1**：帶進 `push_channels`、`ops_alert` 的 sink、render、selftest，以及產品內的「測試推送」操作。
     - **不接 `forecast_record`**。
     - 要證明這時功能不可達：用 AST 或 grep 確認 `scheduler.py` 沒有註冊 `forecast_record`，也沒有建構 `OpsAlertSink`。
     - PR-1 受第 1、3、7、8 點閘門約束，包括 RC-617 的 BLOCKING。
   - **確認動作**：第 1 點的輪換完成之後，CEO 在產品內按一次「測試推送」，然後憑記憶回覆有沒有在聊天室看到訊息，不需要貼任何內容。紀錄出處是追蹤清單。
   - **PR-2（接線）**：合併前閘門是「CEO 回覆看到了，而且回覆日期晚於最近一次輪換」。通道憑證變更之後，要重做一次。
   - `python -m app.ops_alert.selftest` 保留為維運工具，但不是本點的證據，也不得請 CEO 執行。
   - 「測試推送」的規格：
     - 回應只帶通道名稱、`sent`／`skipped`／`failed`、`error_class`、`status`；
     - 不顯示環境變數名稱或任何設定值；
     - 伺服器端設冷卻常數；
     - 字面待風控定稿，不得提示 CEO 去查看設定；
     - 這個功能要 product-manager 同意。
3. 照 ADR-0029 原第 3 點（上限查證），屬 PR-1 的閘門。
4. 照原第 4 點（啟動時的通道檢查），屬 PR-2 的閘門。
5. 照原第 5 點（部署手冊 §5），屬 PR-2 的閘門。
6. 照原第 6 點：每支 PR 各自通過；PR-2 要全套通過。
7. 照原第 7 點（CEO 核可 ADR-0029，連同本 ADR），屬 PR-1 的閘門。
8. 照原第 8 點（render 送風控知悉級確認），屬 PR-1 的閘門。

- dead-man's switch 照舊不是本閘門的項目。
- 加註（交 tech-writer，原文不改）：
  - ADR-0029 第 19 行：「〔加註〕本行的『清查』由 ADR-γ D-10 第 1 點取代：不要求 CEO 清查 log，改為四種憑證的輪換回覆與殘留紀錄。」
  - D-10 標題旁：「〔由 ADR-γ 取代，原文保留〕」。
  - D-9 末句「CEO 在聊天室看到」旁：「〔D_v 的證據改依 ADR-γ 第 2 點〕」。

#### Consequences
- **好處**：
  - 第 1 點不再要求 CEO 讀 log；
  - 第 2 點有一個 qa 擋得住的檢查點，就是 PR-2 合併之前；
  - 四種憑證不會因為只換一半而被記成完成。
- **壞處**：
  - 多一個產品內功能（測試推送），要 product-manager 同意，字面與視覺要送審，還多一個會對外送出訊息的 API；
  - 測試推送走的是使用者警示那條路，維運 render 和 sink 在真實網路上的路徑，要等第一則真的維運告警才會驗證到（單元測試以 MockTransport 涵蓋）；
  - 接線 PR 的路徑變長：要等 CEO 輪換、按測試推送、回覆；
  - CEO 回覆都是憑記憶，團隊沒有查證；
  - CEO 如果四種都「沒有設定過」，第 2 點要等 CEO 自己決定設定通道才可能成立，接線 PR 會一直卡在這裡。這要照實寫進 ADR-0029 送 CEO 核可的決策包（RC-615 的中性語氣規則）。
  - PR-2（接線）會碰到 `app/forecast`，也就是 `code_digest` 範圍，由既有的接線 PR 規則處理，不在本件。

### 五、PR 先後與時點（RC-652-11、任務第 3 點）
- 序列：α1 → α2 → (B) → α3。(A) 排進任一個空檔，建議在 α2 之後。
- 不同支不得放在同一個 PR，也不得和 RC-556、接線、退役、README、RC-554 的 PR 放在一起。
- 每一支的合併時點都要以下條件全部成立（RC-556 約束 8）：
  - (a) 登記紀錄 commit 已經在 `work/`；
  - (b) 退役 PR 已經合併；
  - (c) 不在 #156 期間；
  - (d) 不落在其他 PR「最終 head 已送驗證」到「合併」之間。
- α1、α2、α3、(A)、(B) 都不碰 `app/forecast`、`app/outlook`、`app/dirdef`、`app/data/session_calendar.py`，各自附 diff 為空的證明。ADR-γ 的 PR-1 也不碰；PR-2 例外，見上。
- 照實寫：(a)、(b) 這兩個條件會讓 high 等級的 RC-650 修正延到登記之後才能合併。這是 RC-652-11 自己指定的限制，我照辦。要不要放寬，由風控或 CEO 決定。
- RC-655 第 9 點：(A) 如果比新知悉包先合併，第三項要整項重審。這是排程 (A) 時要考慮的一點。

---

## 驗證

**我讀過的**
- 風控 RC-650～RC-656 全文。
- 我的 (A)(B) 規格全文。
- RC-612～RC-617 全文。
- RC-618～RC-622 全文。
- dev-lead 交件全文。
- ADR-0029 全文（588 行）。
- ADR-0001。
- 草案一定稿（`2026-11-22-規則草案定稿與PR2PR3脫離閘門評估-tech-architect.md` 第 30～164 行）。
- R0-2 檔第 300～359 行。
- RC-556 裁示的約束 8（Grep 命中段）。
- RC-553 的 P1 段。
- `alerts/engine.py` 第 100～557 行。
- `alerts/snapshot.py` 全檔。
- `scheduler.py` 第 270～669 行。
- `api/alerts.py` 全檔。
- `alerts/store.py` 第 1～140 行。
- `alerts/notify.py` 第 1～153 行。
- `AlertStatusStrip.tsx` 全檔。
- `oneLinerWording.ts` 第 55～104 行。

**我 Grep 過的**
- `docs/adr` 的 `load_failures|evaluate_alerts_tick|AlertStatusStrip|查詢時間`：只命中 ADR-0014 I-9。
- ADR-0021 的 K-6、W-2、T-6。
- `docs/adr` 的無法讀取列相關字樣：0 筆，表示 (B) 的 ADR 還沒落檔。
- `settings/` 的 `notify_webhooks` 等欄位。
- security-engineer 的 selftest 段。

**沒有查證**
- `AlertRulesSection.tsx`：採 dev-lead 的行號，我沒有讀。
- 前端 QueryClient 的重抓間隔。
- `api/kelly.py` 的 `kelly_inputs_for` 內部。
- pydantic `ValidationError` 字串是否帶輸入值（推論）。
- 草案一是否已經落檔進 main。
- 其他分支的 ADR 最大號。
- CEO 本機的實際狀況。

**沒有執行任何測試、git 或指令。**

---

## 下一步

- **risk-compliance-officer**：
  - 確認三處讀法：(i) 優先序 C 先於 D、(ii) 手動檢查不寫紀錄、(iii) E 分四種變體。這三處如果不接受，才算 RC-651 (c)。
  - 決定開始與恢復推播要不要附 `ALERT_DISCLAIMER_LINE`。
  - 判定 ADR-γ 第 2 點採 (b-iii)、不採 (b-i) 這件事。
  - 依 RC-617，核對 PR-1 和 PR-2 的閘門分配。
- **creative-lead**：起草以下字面，都是字面待風控定稿，不和新知悉包混在同一批：
  - E 的四種變體；
  - C+E 的那一行；
  - 狀態 B 的「最近一次檢查」；
  - 開始與恢復兩則推播；
  - 兩個略過理由；
  - 手動檢查的分類句；
  - α3 的附註；
  - (B) 原因句裡和警示有關的部分；
  - 測試推送的按鈕與結果句。
- **art-lead**：狀態 E 和 C+E 的視覺，送風控核。
- **product-manager**：同意或否決產品內的「測試推送」功能。否決的話，ADR-γ 第 2 點退回 (c)，送風控判定。
- **dev-lead、frontend-engineer**：字面定稿之後，照 α1 → α2 → (B) → α3 開任務單，照第五節排合併。
- **devops-sre**：
  - ADR-0029 通道要不要另外送（suggested）；
  - ADR-γ PR-1 的測試推送實作，要等 `push_channels` 抽出之後。
- **security-engineer**：
  - `_load_isolated` 的 `exc_info=True` 可能把持倉輸入值寫進 log（推論），請判定；
  - 審測試推送回應的欄位。
- **tech-writer**：在 `product/stock-desk` 落檔 ADR-α、ADR-β（修訂後）、ADR-γ，狀態都是 proposed；依第四節在 ADR-0029 第 19 行、D-9、D-10 加註；ADR-0017 的 C4 和第 105 行照原規格加註。
- **coordinator**：追蹤清單更新以下各列：
  - α1、α2、α3、(B) 的相依與時點；
  - ADR-γ PR-1 和 PR-2 的閘門分配；
  - RC-650 的失效條件改成「α1、α2 都合併之後重判」。
- **CEO**：本件沒有需要決定或操作的事。

**相關路徑**
- /home/user/AICompany/work/reviews/2026-11-22-警示失敗升高與狀態列與查詢時間RC650至RC656-風控.md
- /home/user/AICompany/work/reviews/2026-11-22-F1b壞值匯率揭露與無法讀取列規格-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-22-推播憑證輪換告知逐字定稿RC612至RC617-風控.md
- /home/user/AICompany/work/reviews/2026-11-22-憑證輪換告知範圍擴大定稿RC618至RC622-風控.md
- /home/user/AICompany/work/reviews/2026-11-22-警示失敗痕跡查證與X3b串接測試交件-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-22-規則草案定稿與PR2PR3脫離閘門評估-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-22-RC556改字時點裁示與R0-2盤點-tech-architect.md
- /home/user/AICompany/docs/adr/0029-stock-desk-維運告警通道.md
- /home/user/AICompany/docs/adr/0021-stock-desk-規則與警示欄位的可評估性不變式.md
- /home/user/AICompany/docs/adr/0014-stock-desk-盤中報價資料邊界顯示範圍與節流.md
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/notify.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/alerts.py
- /home/user/AICompany/apps/stock-desk/backend/app/scheduler.py
- /home/user/AICompany/apps/stock-desk/frontend/app/components/AlertStatusStrip.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/oneLinerWording.ts
