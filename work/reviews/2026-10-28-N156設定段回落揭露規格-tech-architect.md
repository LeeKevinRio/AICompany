# N-156 設定段回落預設值的偵測、揭露與寫回保護（含 ADR-0032 草案）

- 審查者：tech-architect
- 日期：2026-10-28
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 1. 本次結論

規格草案寫完了。有兩項要 CEO 裁定（E2、A-1），也需要一則新 ADR，草案在附錄，暫編 ADR-0032。

- **偵測**：設定層新增 `load_with_status()`，用同一次讀取同時回傳設定值與回落段。每次讀取都重新判定，結果不寫入資料庫，讀取路徑也不取寫入鎖。
- **揭露**：設定頁、個股頁、儀表與 kelly 回應各帶一份由後端組好的揭露字面。排程台的回應不加欄位，只把 ② 換成另一句。
- **寫回保護**：補上「一次無關的儲存就把 10% 寫死」這個缺口。
- **時序**：N-156 自成第三批，等 N-155 合併後再開分支，建議在 #62 第二批之前合併。

先更正一個前提：題目舉例的「段損毀時第 1 條改報 `not_evaluable`」並不是 fail-closed，反而比現況更寬。
- 引擎只有在上限為 `violated` 時才把加碼擋下（`advice/engine.py:369-372`）。
- 股數計算會直接排除 `not_evaluable` 的上限（`advice/limits.py:1597-1613`）。
- 所以第 1 條改報 `not_evaluable`，等於整條拿掉，不會在 10% 擋下。這個方案否決，真正 fail-closed 的做法是下面的 E2。

## 2. 各部門回報

- **tech-architect**：全程唯讀，只用 Read、Glob、Grep。
  - 讀過兩個 worktree 的設定層、各 API 呼叫點、engine 與 limits，以及 ADR-0031 和三份風控裁決。
  - 沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。
- **待接手**：
  - risk-compliance-officer：定字面、回審 ② 與 U3。
  - CEO：裁定 E2、A-1。
  - dev-lead：實作。
  - tech-writer：落檔 ADR。
- **其他部門**：本次未參與，這是純規格任務。

---

## 評估摘要

**採用**
- D1：`load_with_status()`，值與回落狀態出自同一次讀取。
- 回落狀態不持久化。
- 揭露字面由設定層組好，只存一份。
- 排程台 ② 走 P2（前提是風控同意換句）。
- 寫回保護 S2+S3。

**建議 CEO 核可**
- E2：risk_budget 段回落時，加碼改為觀望，也不給買進股數。

**否決**
- D2：另設查詢函式。
- D3：把狀態放進 `AppSettings` 或另開表。
- E1：改報 `not_evaluable`。
- E3：端點直接 503。
- 逐欄搶救損毀 payload。

**新發現的同源問題**（都由同一個靜默回落造成）
1. **儲存會把回落值寫死，原值永久遺失。**
   - `models.py:24-28` 承諾「沒帶的段不會被重設成預設值」。
   - 但 `api/settings.py:451-453` 先 `load()` 再 `apply_to`，`models.py:226-231` 會用回落後的預設值補上沒帶的段。
   - `store.save` 一律整份寫入（`store.py:127-144`）。所以使用者只是存一下費率，risk_budget 的 10% 就被寫死了。
   - 前端的放寬確認比的是畫面上那個 10%，所以這次寫入不會觸發確認。
2. **kelly 的條件 87 也被這個回落打破。** 條件 87 規定 kelly 的數值必須依使用者自己的 risk_budget 計算，不得用預設值（`api/kelly.py:449-454`）。段回落時，它算出來的正是預設預算的數值。
3. **`alerts` 段回落時，預設值是啟用評估、開啟推播**（`models.py:101-109`）。原本關掉推播的使用者會開始收到推播。
4. **net_worth 段回落時，第 3 條會顯示「尚未輸入帳戶總淨值」**（`api/settings.py:123`），但使用者其實輸入過，這句是不實陳述。
5. **最可能的觸發點是 schema 演進。** `RiskBudget` 設了 `extra="forbid"`（`limits.py:568`），刪一個欄位或收緊一個界限，全部已存的 risk_budget 就會一起回落。#62 第二批（5-K 停用第 5 條）如果移除 `kelly_*` 欄位，就會觸發這種全面回落。

## 方案比較

### 一、偵測與傳遞

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **D1 `load_with_status() -> LoadedSettings(settings, fallback_sections)`（採用）** | 值與狀態同一次 SELECT；`load()` 改成薄包裝，約 10 個呼叫點不用動 | 多一個回傳型別 | 低 |
| D2 另設 `fallback_sections()` 查詢 | 介面小 | 第二次讀取可能和值不一致（中間夾一次 save 就會），等於第二種判定 | 違反「揭露與實際值同源」，否決 |
| D3 把狀態放進 `AppSettings`，或另開表持久化 | 能記下「何時開始」 | `AppSettings` 是 PUT／GET 的文件，狀態會跟著 PUT body 被帶出、被編輯（S2 記錄不放進 `RiskBudget` 也是這個理由，`migrations.py:30-32`）；另開表會讓讀取變成寫入、要取 `BEGIN IMMEDIATE` | 否決 |

**是否每次讀取都重新判定**：是。現在 `_parse_section` 每次都會驗證，只是把結果丟掉；改成回傳三種狀態（`absent` / `valid` / `invalid`）即可，不多任何 I/O。這也符合風控 R4-4 對「不得延遲」的解讀：只讀一次。

**是否持久化**：不持久化。理由有三：
- 真實狀態就是已存的 payload。從備份還原、手動修好、或回退 schema 之後，持久化的旗標會和實際內容脫節。
- store 每個程序只建構一次（`deps.py` 的 `lru_cache`），如果在建構時才記錄，執行中途發生的損毀要等重啟才看得到。
- 讀取路徑一旦寫入，就會和排程程序搶寫入鎖。

如果風控的字面需要「自何時起」，唯一可接受的做法是比照 S2：只在建構時記錄，先做一次不加鎖的 SELECT，有變化才 `BEGIN IMMEDIATE`，並在鎖內重讀（`migrations.py:463-492`）。我不建議這樣做。

**與 N-154 寫入鎖的互動**
- 讀取路徑：沒有互動。
- 唯一需要鎖的是下面的寫回保護 S3：`save` 必須改成明確的 `BEGIN IMMEDIATE`，在鎖內重讀原始列、判定、寫入，最後 COMMIT。現行 `save` 用的是 Python 隱式的 DEFERRED 交易（`store.py:134`），先讀後寫在 WAL 下會撞到 `SQLITE_BUSY_SNAPSHOT`。

### 二、揭露落點（只定結構）

| 端點 | 新增欄位 | 前端渲染位置 |
|---|---|---|
| `GET` / `PUT /api/settings` | `settings_fallback: SettingsFallbackView \| None`（`sections`、`notice{title, items[]}`、`section_markers{section_id: str}`） | 頁首一個區塊，加上每個回落段 h2 下方一行標記 |
| `GET /api/advice/{symbol}` | `settings_fallback_notice: str \| None`；`insufficient_data` 時為 None（比照 `advice.py:241`） | `LimitsCheckList` 清單層級，放在五條之上，不只第 1 條那一列 |
| `GET /api/portfolio/limits` | 同上 | `RiskGauge` 五列之上 |
| kelly 回應中顯示第 5 條數值者（`kelly.py:1185`） | 同上 | 該數值旁邊 |
| `/today`、`/rule-set`、`/confirm-rules` | **不加欄位**（ADR-0031 C-2 禁止旗標） | 只換 `lines[1]` 那一句 |

建議端那則揭露要放在清單層級，因為 risk_budget 回落會影響五條上限，不只第 1 條。觸發段是 `risk_budget` 與 `net_worth` 的聯集，`net_worth` 決定第 3 條的分母。

**排程台 ② 的兩個做法**
- **P1**：② 不變，照風控現行裁定顯示實際值 10%。不必修訂 ADR-0031。
- **P2**（建議）：`get_cap1_reading()` 帶出 `from_default`，`compose` 改用另一句「② 預設值句」。

由誰決定：風控定字面，不需要 CEO。風控本來就要求本案落地時回審 ②，所以 P2 的邊際成本很低。

**建議端判定**

| 方案 | 優點 | 缺點 | 風險 | 誰裁定 |
|---|---|---|---|---|
| E0 只揭露 | 判定不變、範圍小 | 放寬照樣發生，只是看得見 | 仍牴觸「放寬需 CEO 同意」 | CEO 須明文接受 |
| E1 第 1 條改報 `not_evaluable` | — | 不擋加碼，也退出股數計算 | 比現況更寬 | 否決 |
| **E2 risk_budget 回落時加碼改觀望、不給買進股數；減碼與停損照常，並揭露** | 不可能被靜默放寬 | 回落期間沒有任何加碼參考；改動 engine | 中 | **CEO** |
| E3 建議端回 503 | 最保守 | 連停損與減碼資訊一起藏起來 | 否決 | — |

**建議 E0 加 E2。**
- E2 的閘門放在 `advice/engine.py`，和既有的保守閘門同一處，因為現有閘門都在 engine 裡、並寫在卡片上（`engine.py:16-22`）。
- 參數用 keyword-only 而且不給預設值，強迫每個呼叫端（advice、alerts、scheduler）明確決定。
- 回落的出口是使用者在設定頁明確確認並覆寫該段，靠下面的 S3 保證。

**A-1：alerts 段回落時，排程要不要跳過評估（CEO 裁定）**
- 跳過：可以避免對已關閉推播的使用者推播，但會漏掉停損警示。
- 照常：用預設值執行，並在設定頁揭露。
- 我建議照常（A-0）。

### 三、與 ADR-0031 C-4、C-6、H1 的關係

這裡只講 P2 的情況：

- `get_cap1_reading()` 只呼叫一次 `_default_settings_store().load_with_status()`，再取 `from_default = "risk_budget" in fallback_sections`。它讀的是設定層唯一一次判定，不讀原始 payload，也不呼叫 `_parse_section`，符合風控「不得另外判定段損毀」的條件。
- `Cap1Reading` 定義在 `api/playbook_cap1_wording.py`。這個模組維持零 `app.*` 依賴（C-1、T-3）。router 只從 `app.api.deps` 和這個模組 import，已在白名單內（C-6、T-2），也不碰 `app.advice`（H1）。
- router 只把 `Cap1Reading` 原樣傳給 `compose`，不在任何 `if`、比較、運算或 log 裡使用（把 R4-1 的範圍擴及這個旗標）。旗標不流進 engine 或 service（H3）。
- 讀取例外與非有限值時回 `Cap1Reading(None, False)`，② 的缺值句語意不變（風控補充二條件）。
- 要修訂的地方：
  - C-4 的回傳型別。ADR-0001 不准原地改寫已生效的 ADR，所以由 ADR-0032 部分取代 C-4 的簽章。
  - C-1 本來就允許增列參數。
  - T-4 的識別字禁令要加上 `get_cap1_reading`、`cap1_reading`、`Cap1Reading`。
  - B-1 不變性矩陣要加上 `from_default` 為 True 和 False 兩種情況。

**H5、R4-6**：這兩條約束的是 #68 與 N-155 那個 PR（補充二:67「本 PR」）。N-156 會改動建議端回應，需要風控明文確認不受這兩條約束；ADR-0031 D-2 (4) 出自 CEO #70，所以也要 CEO 知悉。

## 決策（ADR 草案）

需要新 ADR，見附錄 ADR-0032。理由：
- 這是新的跨模組契約，牽涉設定層的回傳型別、四個端點的回應形狀，以及寫回語意。
- 需要部分取代已生效的 ADR-0031 C-4。

## 對實作的約束（逐條可由 qa-reviewer 檢查）

- **K-1** `SettingsStore.load_with_status() -> LoadedSettings`，型別為 frozen，含 `settings` 與 `fallback_sections: tuple[str, ...]`（依 `_SECTIONS` 順序）。`load()` 必須等於 `load_with_status().settings`。測試要涵蓋缺列、合法、不合法 JSON、schema 不符四種情況。
- **K-2** `fallback_sections` 只收「有存但驗證失敗」的段，缺列不算（例如 FR-9 之前的舊存檔沒有 net_worth 列，這是合法的）。
- **K-3** 讀取路徑不寫入：用 trace callback 斷言沒有任何 BEGIN、INSERT、UPDATE、DELETE（比照 N-154 的測試）。
- **K-4** `app/settings/` 之外不得出現 `app_settings` 表名或 `_parse_section`，用 grep 或 AST 測試把關。
- **K-5** 同一個 handler 只能呼叫一次 `load()` 或 `load_with_status()`，值和揭露都從這一次來，用 spy store 計次。
- **K-6** 揭露字面放在 `app/settings` 下單一模組，只存一份，由風控逐字定稿。router 原樣轉傳。前端不得從設定值自行推導回落狀態，要有哨兵測試（比照 ADR-0031 F-1）。
- **K-7** 四個端點的欄位依上表；沒有回落時一律為 `None`，不得給空字串。
- **K-8** playbook 回應不增欄位，只有 `lines[1]` 可以不同；B-1 不變性矩陣加 `from_default` 為 True 和 False 兩種。
- **K-9** `get_cap1_reading()` 的規格如第三節；router 不得對它做分支（AST 檢查）。
- **K-10** 寫回保護：
  - **S2**：PUT 沒帶的回落段保留原始 payload，不寫入。
  - **S3**：PUT 帶了回落段，就必須在 `overwrite_fallback_sections` 列出該段，否則回 409。
  - 判定與寫入在同一個 `BEGIN IMMEDIATE` 內，鎖內重讀。
  - risk_budget 沒有寫入時不得呼叫 `note_cap1_write`，否則會用預設值誤設 `changed_by_user`（`store.py:149`）。
- **K-11** 前端儲存時，未經使用者確認的回落段不得放進 PUT body。確認面板只定結構，字面由風控定。
- **K-12** 修正 `store.py:9-14` 的 docstring：拿掉「conservative default」的說法，改成「回落段由 `load_with_status` 帶出並揭露」。
- **K-13**（CEO 核可 E2 才做）`build_advice` 新增 keyword-only、無預設值的 `budget_from_default: bool`。為 True 時加碼改為觀望並附 engine 的說明文字，`quantity_range` 不給買進方向；減碼與停損照常。
- **K-14**（第二批前置約束）修改 `RiskBudget` 欄位集合或收緊界限時，必須附 raw-payload 遷移（比照 S2），以及「上一版存檔仍能驗證」的測試。
- **K-15** 本案落地時，風控必須回審 ② 與 S2 遷移的 U3 項目（`migrations.py:221-226`）。採用 S2+S3 之後，「任何儲存按鈕都會把所有區段整份寫入」這句就不再是事實。

## 與現有分支的時序

- **不放進第一批**（`fix/stock-desk-cap1-10pct`）：這批已審完、快要合併，加進去會重開審查。
- **不放進 N-155**：R4-6 和 H5 明確禁止那個 PR 改動 advice、settings、portfolio 的回應。
- **建議第三批**：等 N-155 合併後，從 `product/stock-desk` 另開 `fix/stock-desk-settings-fallback`。K-9 依賴 N-155 的 `deps.get_cap1_weight`，所以一定要排在 N-155 之後。
- **commit 拆法**：
  1. K-1～K-5、K-12，設定層，不改 API。
  2. K-6、K-7、K-11 的設定頁、建議端與前端。
  3. K-9 排程台 ②。
  4. K-10 寫回保護。
  5. K-13 或 A-1，視 CEO 裁定。
- **與 #62 第二批的關係**：建議至少 1 和 2 在第二批之前合併；K-14 不論如何都要先成為第二批的約束。

## 3. 驗證

- 要確認這份規格是對的，請 qa-reviewer 對照以下檔案與行號核對前提：
  - `store.py:115-165`
  - `api/settings.py:451-453`
  - `models.py:24-28` 對照 `models.py:226-231`
  - `engine.py:369-372`
  - `limits.py:1612-1613`
  - `kelly.py:449-454`
  - `deps.py:386-412`（N-155 worktree）
- 實作後的自動化驗證就是 K-1～K-15 各自的測試。本次沒有執行任何測試（唯讀職能）。
- **CEO 要親自決定的事**：
  1. 是否核可 E2（回落期間加碼改為觀望）。若不核可，要明文接受「已揭露的回落放寬」。
  2. A-1：alerts 段回落時，排程要不要跳過評估（建議照常）。

## 4. 下一步

1. 風控：
   - 定稿設定頁區塊與段標記、建議端短句、② 的預設值句（決定 P1 或 P2）、S3 確認面板的字面。
   - 定 S2 遷移 `skipped` 告知與新揭露重疊時的取捨規則。
   - 確認 N-156 不受 H5、R4-6 約束。
2. CEO：裁定 E2 與 A-1。
3. tech-writer：附錄落檔為 `docs/adr/0032-…`（proposed）。dev-lead：等 N-155 合併後開第三批分支。

---

## 附錄：ADR-0032 草案

```markdown
# ADR-0032：stock-desk 設定段回落預設值的偵測、揭露與寫回保護

- 狀態：proposed
- 日期：2026-10-28
- 決策者：tech-architect（草案）；字面待風控定稿；E2 待 CEO 裁定
- 與既有 ADR 的關係：補充 ADR-0031；部分取代 ADR-0031 C-4 的函式簽章（`get_cap1_weight` 改為 `get_cap1_reading`），C-4 其餘條文、C-1、C-2、C-6、R4-1～R4-5 不變。R4-6／H5 只約束 N-155 那個 PR，本 ADR 對建議端回應的變更另經風控確認、CEO 知悉。
- 適用範圍：僅 product/stock-desk；路徑相對於 `apps/stock-desk/backend/`。

## Context（背景）
- `SettingsStore.load()` 對「有存但驗證失敗」的段靜默回到預設（`settings/store.py:152-165`），只記 log。risk_budget 回落時五條上限都改用預設，原值較嚴的使用者會在不知情下被放寬，違反「放寬需 CEO 同意」。
- 唯一的揭露是 S2 遷移紀錄的 `failed_sections`（`settings/migrations.py:320`），只在建構時寫入。
- 任一次儲存都會把回落值整份寫死（`api/settings.py:451-453`、`settings/models.py:226-231`），與 `models.py:24-28` 的承諾不符。
- `not_evaluable` 不擋加碼，也會被排除在股數計算外（`advice/engine.py:369-372`、`advice/limits.py:1612-1613`）。
- `RiskBudget` 是 `extra="forbid"`：刪欄位或收緊界限會讓全部存檔一起回落。

## Options（選項比較）
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| D1 `load_with_status()` 一次讀取回傳值與回落段（採用） | 同源；`load()` 呼叫端不動 | 多一個型別 | 低 |
| D2 另設查詢函式 | 介面小 | 兩次讀取可能不一致 | 否決 |
| D3 狀態寫入 `AppSettings` 或另表 | 可記時間 | 會進 PUT body；讀取變寫入、要取寫入鎖 | 否決 |
| E0 只揭露 | 判定不變 | 放寬照樣發生 | 需 CEO 明文接受 |
| E1 第 1 條改報 not_evaluable | 看似保守 | 不擋加碼、退出股數計算 | 更寬，否決 |
| E2 risk_budget 回落時加碼改觀望、不給買進股數 | 不會被靜默放寬 | 回落期間沒有加碼參考 | 需 CEO 裁定 |

## Decision（決策）
1. 設定層提供 `load_with_status() -> LoadedSettings(settings, fallback_sections)`；`load()` 等於其 `.settings`。回落段只算「有存但驗證失敗」。每次讀取都重新判定，不持久化；讀取路徑不寫入、不取鎖。
2. 揭露字面由設定層組好、只存一份，風控逐字定稿：`SettingsResponse.settings_fallback`（頁首區塊加各段標記）；`AdviceResponse`、`PortfolioLimitsResponse` 與顯示第 5 條數值的 kelly 回應帶 `settings_fallback_notice: str | None`，在上限清單層級渲染。前端只照字串渲染。
3. 排程台：`deps.get_cap1_reading() -> Cap1Reading(weight, from_default)`，取自同一次 `load_with_status()`，型別定義在 `api/playbook_cap1_wording.py`；router 原樣傳給 `compose`，不分支；回應不增欄位，只換 ② 的字面。
4. 寫回保護：PUT 沒帶的回落段保留原始 payload；帶了回落段就必須列在 `overwrite_fallback_sections`，否則回 409。判定與寫入在同一個 `BEGIN IMMEDIATE` 內、鎖內重讀（N-154 模式）；risk_budget 沒有寫入時不呼叫 `note_cap1_write`。
5. E2 由 CEO 裁定；若否決，CEO 須在本 ADR 記載接受「已揭露的回落放寬」。

## Consequences（後果）
- 好處：回落狀態即時、同源、各處都看得到；不會被一次無關的儲存寫死；排程台不必自行判定段損毀。
- 壞處：設定、建議、portfolio、kelly 的回應形狀改變；前端儲存流程要能略過回落段並確認覆寫；S2 遷移告知 U3 的字面失效，要風控回審；E2 通過時，回落期間沒有任何加碼參考。
- 未涵蓋：已觸發的警示文字仍依回落值；`alerts` 段回落時排程以預設值（啟用、推播）執行（A-1 待 CEO）；列被刪除不被偵測。
- 被約束：日後修改 `RiskBudget` 欄位集合或收緊界限，必須附 raw-payload 遷移，以及「上一版存檔仍能驗證」的測試。
```

## 相關檔案

- /home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b/apps/stock-desk/backend/app/settings/store.py
- /home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b/apps/stock-desk/backend/app/settings/migrations.py
- /home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b/apps/stock-desk/backend/app/settings/models.py
- /home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b/apps/stock-desk/backend/app/api/settings.py
- /home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b/apps/stock-desk/backend/app/api/advice.py
- /home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b/apps/stock-desk/backend/app/api/portfolio.py
- /home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b/apps/stock-desk/backend/app/api/kelly.py
- /home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b/apps/stock-desk/backend/app/advice/engine.py
- /home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b/apps/stock-desk/backend/app/advice/limits.py
- /home/user/AICompany/.claude/worktrees/agent-ab78ec67351c74920/apps/stock-desk/backend/app/api/deps.py
- /home/user/AICompany/.claude/worktrees/agent-ab78ec67351c74920/apps/stock-desk/backend/app/api/playbook_cap1_wording.py
- /home/user/AICompany/docs/adr/0031-stock-desk-排程台與第1條並存揭露的組合點與邊界.md
- /home/user/AICompany/work/reviews/2026-10-28-#68裁決補充二-N155已知限制-風控.md
- /home/user/AICompany/work/reviews/2026-10-28-#68裁決D2修訂與N155揭露規格-風控.md
