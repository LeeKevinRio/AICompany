# ADR-0032：stock-desk 設定段回落預設值的偵測、揭露與寫回保護

- 狀態：accepted（CEO #74，2026-10-29 核可）
- 日期：2026-10-29（tech-architect 草案日期 2026-10-28）
- 決策者：tech-architect（草案）；風控 2026-10-29 字面定稿（含檔末補記；VERDICT: CONDITIONAL APPROVE，required 條件須與本案同批完成）；CEO #72 已裁 E2、#73 已裁 A-1 照常評估（2026-10-29）；本 ADR 待 CEO 核可。
- 補充（風控 2026-10-29 K-15 正式核對，CONDITIONAL APPROVE，`work/reviews/2026-10-29-N156K15正式核對與裁示-風控.md`）：裁示二-2——Kelly 解除凍結前，cost_model 段回落期間 import-backtest 須 fail-closed 拒絕、拒絕句先送風控（追蹤 N-167），已寫入 `app/kelly/freeze.py` docstring 與守門測試；裁示二-4 (b)——request 未帶任何區段時，部分儲存句改用「全未寫入」變體 `NOTHING_SAVED_NOTICE`（`app/settings/fallback_wording.py`），前端以琥珀框逐字渲染；不修訂本檔條文；本檔原文不改。
- 來源簡稱（皆在 `work/` 下）：
  - [TA]：`reviews/2026-10-28-N156設定段回落揭露規格-tech-architect.md`（附錄為本 ADR 草案；K-1～K-15 與方案比較）
  - [風控]：`reviews/2026-10-29-N156字面定稿與表態-風控.md`（主文與檔末「補記」）
  - [補充二]：`reviews/2026-10-28-#68裁決補充二-N155已知限制-風控.md`
  - [決策包]：`dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`（#72、#73）
  - [追蹤]：`dispatch/2026-10-17-後續追蹤清單.md`（N-156、N-158）
- 與既有 ADR 的關係：
  - **補充 ADR-0031**（accepted）。ADR-0001 禁止原地改寫已生效 ADR，故所有延伸寫在本 ADR（[追蹤] N-158）。
  - **部分取代 ADR-0031 C-4 的簽章**：`get_cap1_weight() -> Decimal | None` 改為 `get_cap1_reading() -> Cap1Reading(weight, from_default)`；C-4 其餘條文、C-1、C-2、C-6、R4-1～R4-5 不變（[TA] 附錄；[風控] 第 5 項）。
  - 另立「ADR-0031 的延伸（N-158）」一節收錄風控裁示的延伸與解讀。
  - H5、R4-6 的範圍確認見 Decision 9。
- 適用範圍：僅 product/stock-desk；程式路徑相對於 `apps/stock-desk/backend/`。
- 標註約定：本檔為 [TA] 草案加 [風控] 定稿的轉錄，屬記錄決策脈絡。引用的檔案行號為上述來源撰寫時（2026-10-28／29）的快照，會隨 commit 漂移，tech-writer 落檔時未重新驗證。字面一律不抄入本檔，逐字以 [風控] 為準。本會話無 Bash，commit 由 coordinator 處理。

---

## Context（背景）

以下皆出自 [TA] 草案與 [補充二]「另開 CEO 事項」：
- `SettingsStore.load()` 對「有存但驗證失敗」的段靜默回到預設（`settings/store.py:152-165`），只記 log。risk_budget 回落時各條上限改用預設，原設較嚴者在不知情下被放寬，牴觸「放寬需 CEO 同意」（[補充二] 第 2 項）。
- 唯一的揭露是 S2 遷移紀錄的 `failed_sections`（`settings/migrations.py:320`），只在建構時寫入，是啟動時的快照。
- 任一次儲存都會把回落值整份寫死（`api/settings.py:451-453`、`settings/models.py:226-231`；`store.save` 整份寫入，`store.py:127-144`），與 `models.py:24-28` 的承諾不符；前端放寬確認比的是畫面上的預設值，不會觸發。
- `not_evaluable` 不擋加碼，也被排除在股數計算外（`advice/engine.py:369-372`、`advice/limits.py:1597-1613`），故「改報 `not_evaluable`」比現況更寬。
- 同源問題：kelly 條件 87（`api/kelly.py:449-454`）被打破；`alerts` 回落時預設為啟用評估、開啟推播（`models.py:101-109`）；`net_worth` 回落時第 3 條顯示「尚未輸入」（`api/settings.py:123`）屬不實陳述。
- `RiskBudget` 為 `extra="forbid"`（`limits.py:568`）：刪欄位或收緊界限會讓全部存檔一起回落；#62 第二批（5-K）若移除 `kelly_*` 欄位即觸發。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險／結論 |
|---|---|---|---|
| **D1 `load_with_status()` 一次讀取回傳值與回落段** | 同源；`load()` 薄包裝，約 10 個呼叫點不動 | 多一個回傳型別 | 低。**採用** |
| D2 另設 `fallback_sections()` 查詢 | 介面小 | 第二次讀取可能與值不一致 | 否決 |
| D3 狀態放進 `AppSettings` 或另表 | 可記「何時開始」 | 狀態會進 PUT body；另表使讀取變寫入、要取 `BEGIN IMMEDIATE` | 否決 |
| E0 只揭露 | 判定不變 | 放寬照樣發生 | 仍牴觸「放寬需 CEO 同意」，未採 |
| E1 第 1 條改報 `not_evaluable` | — | 不擋加碼、退出股數計算 | 比現況更寬。否決 |
| **E2 risk_budget 回落時加碼改觀望、不給買進股數；減碼停損照常並揭露** | 不可能被靜默放寬 | 回落期間沒有加碼參考；改 engine | **採用（CEO #72）** |
| E3 建議端回 503 | 最保守 | 連停損與減碼資訊一起藏起來 | 否決 |
| P1 ② 不變，照現行裁定顯示實際值 10% | 不必修訂 ADR-0031 | （[TA] 未列） | 未採 |
| **P2 `Cap1Reading.from_default` 改用「②-預設」句** | 風控本來就要求本案落地時回審 ②，邊際成本低 | 需部分取代 C-4 簽章 | **採用（[風控] 第 5 項）** |
| A-0 alerts 回落時以預設值照常評估，設定頁揭露 | 不漏停損警示 | 以預設值（啟用、推播）執行 | **採用（CEO #73）** |
| A-1 alerts 回落時跳過評估 | 不對已關推播者推播 | 會漏停損警示 | 未採 |

另否決：逐欄搶救損毀 payload（[TA]）。

## Decision（決策）

1. **偵測**：設定層提供 `load_with_status() -> LoadedSettings(settings, fallback_sections)`，`load()` 等於其 `.settings`。回落段只算「有存但驗證失敗」，缺列不算。每次讀取都重新判定（`absent`／`valid`／`invalid` 三態），不持久化，讀取路徑不寫入、不取鎖（[TA] 一）。
2. **揭露**：字面由設定層組好、只存一份，逐字以 [風控] 為準。
   - `GET`／`PUT /api/settings` 帶 `settings_fallback`（`sections`、`notice{title, items[]}`、`section_markers{section_id: str}`）；頁首區塊不在任何 `<details>` 內、不能關閉，各回落段 h2 下方另有標記。
   - `GET /api/advice/{symbol}`、`GET /api/portfolio/limits`、顯示第 5 條數值的 kelly 回應帶 `settings_fallback_notice: str | None`；觸發條件為 `risk_budget` 與 `net_worth` 的聯集，只回落 `cost_model` 或 `alerts` 時為 `None`，`insufficient_data` 時為 `None`（比照 `advice.py:241`）。字面有三種情況（只 risk_budget、只 net_worth、兩段同時；兩段同時用整句、不得串接前兩者）。
   - 渲染位置：`LimitsCheckList`、`RiskGauge` 清單層級放在各條之上；**個股頁主畫面（`<details>` 之外，held 與 candidate 兩種模式）再放一次**（[風控] 第 2 項，required）。
   - 前端只照字串渲染，不得從設定值自行推導回落狀態。
3. **排程台（P2）**：見下節「ADR-0031 的延伸」第 2 項。`/today`、`/rule-set`、`/confirm-rules` 不加欄位（ADR-0031 C-2 禁止旗標），只有 `lines[1]` 可能換句。
4. **寫回保護（W-1＋W-2；[TA] 草案原稱 S2／S3，為免與 CEO #63 的「S2 遷移」混淆改名，coordinator 定案）**：PUT 沒帶的回落段保留原始 payload、不寫入；PUT 帶了回落段就必須列在 `overwrite_fallback_sections`，否則回 409。判定與寫入在同一個 `BEGIN IMMEDIATE` 內、鎖內重讀（N-154 模式）。
5. **E2（CEO #72）**：risk_budget 回落時，規則結論為加碼者改為觀望、不給買進股數；減碼與停損照常。放置規則（[風控] 第 3 項，required）：
   - 理由句放進 `downgrade_notices`，不放 `blocked_notices`，`blocked_action` 維持 `None`。若設為 `"add"`，前端會顯示「被風險上限擋下」（`AdviceCardView.tsx:150`）並觸發股數成因的失效條件 Q-8，而實際上沒有任何上限擋下，屬不實陳述。
   - 順序在既有的防禦降級與上限擋下兩道閘門之後，只在動作仍是 `add` 時作用；既有兩道閘門的語意與字面一字不變。
   - 觸發條件只看 `"risk_budget" in fallback_sections`，`net_worth` 回落不觸發；此值取自同一次 `load_with_status()`（K-5），不得寫死成 `False`。
6. **A-1（CEO #73）**：alerts 段回落時，排程以預設值照常評估，不漏停損警示，設定頁揭露該段已回落。
7. **Kelly 揭露（[風控] 第 4 項）**：只做最小揭露，放在 `KellyDisclosuresPanel` 的 `effective_cap` 數值旁，只在 risk_budget 回落時出現，`net_worth` 回落時為 `None`。數值不隱藏。**回落期間條件 87（kelly 數值依使用者自己的 risk_budget 計算）在已揭露的前提下不成立。**
8. **與 S2 遷移 `skipped` 告知的取捨（[風控] 第 7 項）**：
   - **R-1**：區段目前是否使用預設值、頁面與存檔的關係、怎麼恢復，一律只由即時的 `settings_fallback` 陳述；`skipped` 告知只陳述遷移事件本身（U0、U4、U5）。
   - **R-2**：U2 與 U2' 的分支改依同一次 `load_with_status()` 的 `"risk_budget" in fallback_sections`，不再依 `record.failed_sections`（啟動時快照）。
   - **R-3**：兩者並存時都顯示；衝突時以即時揭露為準，`skipped` 告知不得有任何一句依快照陳述區段現況。
   - 另：U3 整句刪除（W-1＋W-2 落地後「任何儲存按鈕都整份寫入」已非事實）；U2' 改寫；S1'（`text_if_risk_budget_failed`）退役，`skipped` 的 short 一律用 S1。
9. **H5、R4-6 範圍確認（[風控] 第 8 項）**：兩者只約束 #68／N-155 那個 PR，N-156 可改動 advice、settings、portfolio、kelly 的回應。**ADR-0031 D-2 (4) 仍然有效**（建議端判定不得因標的是排程台標的而被放寬、略過或降級）；E2 只收緊且只看回落狀態，符合。R4-1～R4-5、H1～H4、C-1～C-6 繼續約束 ② 的路徑。

## ADR-0031 的延伸（N-158）

[追蹤] N-158 為 coordinator 定案（CEO 可推翻）：下列各項屬 ADR-0031 C-3「字面以風控定稿為準」授權範圍內的延伸，或對既有條文的解讀，不與 accepted 條文衝突。

1. **①-缺b、①-缺nb 與四種情況表**（來源：[補充二] 第 1 項，2026-10-28）。字面逐字以 [補充二] 為準。① 位置只出現一句：

   | n_targets | batches_per_target | ① | ③ | per_target_pct | per_target_book_pct |
   |---|---|---|---|---|---|
   | > 0 | > 0 | 原句 | 原句 | 有值 | 有值 |
   | ≤ 0 | > 0 | ①-缺（現行） | ③-缺 | null | null |
   | > 0 | ≤ 0 | ①-缺b | 原句 | null | 有值 |
   | ≤ 0 | ≤ 0 | ①-缺nb | ③-缺 | null | null |

   - 任一種 ①-缺 時 `per_target_pct` 為 `null`（不得為 `0`，AV-16）；③ 只看 n_targets，與批數無關。
   - ② 的替換規則與此獨立，④ 永遠不變，`lines` 固定 4 句、順序固定；不得把批數原始值（0 或負數）插進句子。
2. **②-預設與三句優先序**（來源：[風控] 第 5 項，2026-10-29）。優先序 **②-缺 > ②-預設 > ②**，三句互斥：
   - (1) `weight is None` → ②-缺（讀取例外固定回 `Cap1Reading(None, False)`）；(2) `from_default` → ②-預設；(3) 其他 → ②。
   - `{cap1_pct}` 取 `Cap1Reading.weight`（實際載入的值），不得用常數頂替；和 ②-缺 一樣不寫補救指引；①、③ 的選句與 ② 獨立。
   - 至此 ADR-0031 的缺值句清單為 ①-缺、①-缺b、①-缺nb、②-缺、③-缺，另有 ②-預設（來源：[風控] tech-writer 待辦第 2 項；[補充二]）。
3. **F-4「mode 只決定位置，不決定是否顯示」**（來源：[風控] 補記第 1 項）。五種 mode 都恰好渲染一份，`Cap1DisclosureBlock` 不接收 mode；unconfirmed 時今日頁不得再放 `/today` 那一份，否則畫面出現兩份。此解讀與風控 #68 裁決補充第 3 節一致。
4. **C-4 解讀一：load fallback 不算頂替**（來源：[補充二] 第 2 項）。「不得以 10% 頂替」禁止揭露層自行補數字（常數、前端常數、讀取失敗時自填預設值）；`load()` 回傳的值是全系統當下實際生效的值，如實陳述不算頂替。
   - 條件：②-缺 只在 weight 為 `None`（例外或非有限值）時使用；router 與取值函式不得另外判定段損毀（不得自讀 `app_settings` 原始 payload 或呼叫 `_parse_section`）。
   - 此條件在 P2 後仍適用（[風控] 第 5 項）：回落與否的判定只來自設定層唯一一次 `load_with_status()`。
5. **C-4 解讀二：R4-4「不得延遲」**（來源：[補充二] 第 3 項）。第 1 條的讀取不得帶來超過端點自身 DB 存取上限的等待：只讀一次、不重試、不 sleep、不走網路，上限為同一個 `BUSY_TIMEOUT_MS`（`data/cache.py:36` 為 5000；`playbook/store.py:294` 同值）。不另設較短的 timeout。
6. **不加負向快取**（來源：[風控] 補記第 2 項，採 qa-reviewer 2026-10-29 報告結論）。`lru_cache` 不快取例外：store 建構持續失敗時每次請求重新建構（含重跑 S2 遷移的寫入交易）。判定可接受，因負向快取會讓設定能讀到後揭露仍寫「讀取失敗」，與設定頁互相矛盾。
   - 最壞情況是依賴與端點兩邊的等待相加（各 5 秒），不是只多 5 秒，且只在 DB 被鎖時發生；仍符合解讀二。
   - **適用範圍：本機單人桌面應用。** 產品若改為多人或對外服務須重新評估，屆時由 TA 評估短 TTL 負向快取再送風控。
7. **讀取失敗不得當作回落**（來源：[風控] 補記第 2 項）。`get_cap1_reading()` 讀取或建構失敗時一律回 `Cap1Reading(None, False)` 並使用 ②-缺，不得改用 ②-預設。
8. **unconfirmed 時兩個 `rules_version` 語意不同**（來源：[補充二] 第 4 項，coordinator 定案收錄）。unconfirmed 時 `cap1_disclosure.rules_version` 是 in-force 版本（數字取自哪一版參數，B-3），與 `/today` 頂層 `rules_version = 0`（今天沒有評估任何使用者規則）語意不同；兩者都不得在前端顯示（C-2、F-3），任何人不得拿兩者互相對帳。

## 對實作的約束

**設定層與 API（[TA] K-1～K-15，一行一條；括號為補充）**
- **K-1** `load_with_status() -> LoadedSettings`（frozen；`settings`、`fallback_sections: tuple[str, ...]` 依 `_SECTIONS` 順序）；`load()` 等於其 `.settings`；測試涵蓋缺列、合法、不合法 JSON、schema 不符。
- **K-2** `fallback_sections` 只收「有存但驗證失敗」的段；缺列不算（FR-9 之前的舊存檔沒有 net_worth 列是合法的）。
- **K-3** 讀取路徑不寫入：用 trace callback 斷言沒有 BEGIN、INSERT、UPDATE、DELETE（比照 N-154 測試）。
- **K-4** `app/settings/` 之外不得出現 `app_settings` 表名或 `_parse_section`（grep 或 AST 測試）。
- **K-5** 同一個 handler 只呼叫一次 `load()` 或 `load_with_status()`，值與揭露同源；用 spy store 計次。
- **K-6** 揭露字面放 `app/settings` 下單一模組、只存一份、逐字以 [風控] 為準；router 原樣轉傳；前端不得自行推導回落狀態，要有哨兵測試（比照 ADR-0031 F-1）。
- **K-7** 四個端點欄位如 Decision 2；沒有回落時一律為 `None`，不得給空字串。
- **K-8** playbook 回應不增欄位，只有 `lines[1]` 可不同；B-1 不變性矩陣加 `from_default` 為 True 與 False 兩種。
- **K-9** `get_cap1_reading()` 只呼叫一次 `_default_settings_store().load_with_status()`，取 `from_default = "risk_budget" in fallback_sections`；`Cap1Reading` 定義在 `api/playbook_cap1_wording.py`（維持零 `app.*` 依賴）；router 只原樣傳給 `compose`，不得在 `if`、比較、運算、log 中使用（AST 檢查；R4-1 擴及此旗標），旗標不流進 engine 或 service；例外與非有限值回 `Cap1Reading(None, False)`。
- **K-10** 寫回保護：W-1 與 W-2 如 Decision 4；risk_budget 沒有寫入時不得呼叫 `note_cap1_write`（否則以預設值誤設 `changed_by_user`，`store.py:149`）；`save` 改明確 `BEGIN IMMEDIATE`（現行為隱式 DEFERRED，`store.py:134`）。
- **K-11** 前端儲存時，未經使用者確認的回落段不得放進 PUT body；確認面板只定結構，字面以 [風控] 第 6 項為準。
- **K-12** 修正 `store.py:9-14` docstring：拿掉「conservative default」說法，改為「回落段由 `load_with_status` 帶出並揭露」。
- **K-13** `build_advice` 新增 keyword-only、無預設值的 `budget_from_default: bool`；為 True 時加碼改觀望並附 engine 說明文字，`quantity_range` 不給買進方向；減碼與停損照常（CEO #72 已核可；放置規則見 Decision 5）。
- **K-14** 修改 `RiskBudget` 欄位集合或收緊界限時，必須附 raw-payload 遷移（比照 S2 遷移）與「上一版存檔仍能驗證」的測試。
- **K-15** 本案落地時風控必須回審 ② 與 S2 遷移的 U3（`migrations.py:221-226`）。[風控] 第 5、7 項已給出結論（② 採 P2、U3 刪除）。〔coordinator 定案：規格層回審已於風控 2026-10-29 完成；落地時風控仍須核對實作 diff 與字面逐字〕
- ADR-0031 T-4 識別字禁令加上 `get_cap1_reading`、`cap1_reading`、`Cap1Reading`（[TA] 三）。

**風控 dev-lead 待辦中屬架構約束者（[風控]「下一步」，編號為該節項次）**
- **DL-1（第 1 項）** 第 1～6 項字面放進單一模組逐字照抄；測試檔重打每一句並納入禁用詞掃描（後端下發或前端單一常數檔皆可，均需逐字守門與禁用詞掃描）。
- **DL-2（第 2、3 項）** 設定頁組合測試：四段回落的 16 種組合，涵蓋三條條件式 item 與四個段標記；net_worth 回落時設定頁三處改動（徽章、「目前儲存的數值」、`net_worth.notes` 拿掉 `NET_WORTH_ABSENT_NOTE`），判定依後端 `settings_fallback.sections`。
- **DL-3（第 4、5 項）** 短句三情況各有測試；個股頁主畫面再放一份交 qa-e2e 在 375 與 1280 兩種寬度實機驗收。
- **DL-4（第 6 項）** E2 測試：add 改 hold 且附理由句、`blocked_action is None`、`quantity_range is None`；減碼停損照常；兩道既有閘門優先時不附 E2 句；net_worth 回落不觸發；`budget_from_default` keyword-only 無預設值；advice 端取自同一次 `load_with_status()`。
- **DL-5（第 8 項）** B-1 矩陣含 `from_default` True／False，並斷言 `weight is None` 時 `from_default` 必為 False。
- **DL-6（第 9 項）** 409 時一個區段都不寫入（並有測試，409 的 detail 句才成立）；W-2 覆寫面板每段勾選框預設不勾選；先出覆寫面板，再對已勾選的段跑既有放寬確認；部分儲存成功時顯示專用成功句。
- **DL-7（第 10 項）** S2 告知：刪 U3、改 U2'、U2／U2' 依即時回落狀態、S1' 退役；更新 `migrations.py` 模組 docstring 與 `ShortNoticeCopy` 註解；重打 S2 相關測試字面。
- **DL-8（第 11 項）** 守門測試釘住 `AlertSettings` 預設 `enabled=True`、`notify_webhooks=True`；任一改變須回送風控（F-4 與 alerts 標記依此成立）。
- **DL-9（第 12 項）** 查清 `cost_model` 除 backtest 外的所有使用端（如 `services/sector_board.py:482` 的來源）；若另有讀取已存 `cost_model` 者，`cost_model` 標記須回送風控補寫。
- 第 7 項（Kelly 揭露只在 risk_budget 回落時出現）見 Decision 7；第 13 項即 K-12。

**#62 第二批（5-K）前置約束（[風控] 第 9 項；否則風控否決第二批）**
- (a) 依 K-14 附 raw-payload 遷移與「上一版存檔仍能驗證」測試；fixture 用本版 `RiskBudget().model_dump()` 加一組非預設值的真實形狀，含 `kelly_*` 欄位。
- (b) 收緊界限時，已存值若落到界外不得夾值；等於改寫使用者的值，須比照 S2 遷移另附告知並送風控審查。
- (c) N-156 的 commit 1（偵測）、2（揭露）、4（寫回保護）、5（E2）必須先合併；commit 3（② P2）建議先合，不擋第二批。
- (d) 5-K 落地後，設定頁 F-3 與 Kelly 揭露須回審。

**時序與拆法（[TA]）**：不放第一批（`fix/stock-desk-cap1-10pct`）、不放 N-155（R4-6、H5 禁止）；N-155 合併後從 `product/stock-desk` 另開 `fix/stock-desk-settings-fallback`（K-9 依賴 N-155 的 `deps.get_cap1_weight`）。commit 順序：1 = K-1～K-5、K-12；2 = K-6、K-7、K-11（設定頁、建議端、前端）；3 = K-9；4 = K-10；5 = K-13（[TA] 寫「K-13 或 A-1，視 CEO 裁定」；CEO 已裁 E2 核可、A-1 照常）。〔coordinator 定案：A-1 照常不需排程端程式改動，只有設定頁 F-4 與 alerts 標記揭露（屬第 2 個 commit）；第 5 個 commit 僅含 K-13〕

## Consequences（後果）

- 好處：回落狀態即時、同源、各處可見；不會被一次無關的儲存寫死；排程台不必自行判定段損毀；risk_budget 回落期間不可能被靜默放寬。
- 壞處：設定、建議、portfolio、kelly 的回應形狀改變；前端儲存流程要能略過回落段並確認覆寫；ADR-0031 T-4、B-1 要改；E2 通過，回落期間沒有任何加碼參考。
- 風控指出的殘留：F-3 之下，減碼股數區間與第 4 條依預算計算，原設得比預設嚴者可能看不到已違反、減碼區間也可能變小（已於字面揭露）。
- 未涵蓋：已觸發的警示文字仍依回落值；列被刪除不被偵測；alerts 回落時以預設值（啟用、推播）執行（CEO #73）。
- 被約束：日後修改 `RiskBudget` 欄位集合或收緊界限須符合 K-14 與 5-K 前置 (a)～(d)；`AlertSettings` 預設值變更須回送風控（DL-8）。

## CEO 知悉（不必裁示；來源 [風控]「各部門回報」）

1. **net_worth 回落時第 3 條的狀態**：會變成 `not_evaluable`，與 FR-9「淨值過期」已核可的狀態相同，故照揭露處理，E2 不擴及 net_worth。若 CEO 希望 net_worth 回落時也把加碼改為觀望，需另外裁示。
2. **risk_budget 回落時的上限警示**：這段期間依預設值觸發，原設較嚴的使用者可能收不到警示。設定頁與儀表有揭露，**推播本文沒有**。
3. **D-2 (4) 仍然有效**：N-156 不受 H5、R4-6 約束（見 Decision 9）。D-2 (4) 出自 CEO #70，故請 CEO 知悉。

## 待決

- CEO 核可本 ADR：**已核可**（CEO #74，2026-10-29）。
- [風控] dev-lead 待辦第 14 項（suggested，交 TA 與 qa-reviewer）：狀態為 `skipped` 時，使用者以 W-2 覆寫把風險預算覆寫成 0.15，下次啟動 S2 遷移會改成 0.10。風控認為是收緊、不算紅線，請 TA 確認是否接受。
- 決策包新增 CEO 知悉事項（[風控] tech-writer 待辦第 3 項）：由 coordinator 處理；本任務未修改決策包。
- coordinator 定案：揭露字面（含 W-2 覆寫面板）首選隨後端回應下發，與 K-6 一致；實作若改放前端單一常數檔亦可（[風控] 第 6 項允許），但須單一來源、逐字守門測試與禁用詞掃描。
- 本檔的檔案行號轉自 [TA] 與 [風控] 的 2026-10-28／29 快照，未對照原始碼重驗；實作時以內容定位。
