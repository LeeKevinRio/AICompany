<!-- tech-architect 唯讀回報原文（TA5）；coordinator 轉存，2026-10-12 -->

# tech-architect 回報：ADR-0024 最新版抽驗、F9W-31 (b) 記錄方式指定、F-9b 實作切分（TA5；R-57～R-69）

全程唯讀。讀碼基準是 product/stock-desk 工作樹現況。沒有讀 `.env` 和任何 `*.db`，沒有改檔，也沒有跑測試。

## 本次結論

1. **抽驗**：指定的段落都忠實套用了 R-47～R-56 和 F9W-30～F9W-34，沒有曲解原意的誤植。但有 4 處需要修字句，另外抽驗時發現 4 個設計缺口，共列 R-57～R-69。最重要的三項：
   - **R-57**：D-2 (5)(a) 第 5 步的「回覆 `rejection=None`，該列正常估值」範圍過寬。這是我在 R-47 原文就寫得不精確，不是 tech-writer 誤植。
   - **R-61**：F9W-31 (a) 的絆線測試只檢查 `INDEX_SYMBOL_METADATA` 這張表自己一致，但閘門是依「呼叫端傳入的 market」查預期幣別。所以「正式設定下不可達」這個前提少釘了一半。
   - **R-63**：快取裡若有壞列落在來源不回傳的日期，整段重抓也覆寫不到。之後每次點擊都會重跑梯子，美股每次耗一次 AV 額度，不受冷卻期限制。壞處 5 寫的「每個冷卻窗至多一輪」在這種情形下不成立。
2. **tech-writer 三問**：
   - (a) 設計上不衝突，但 C-30 的「只出現一次」照字面讀，會和 R-48 (iii) 的「0 次」衝突，要收窄範圍（R-58）。
   - (b) 要統一，改成「不讀也不寫 D-9 標記」，並定義「不寫」是什麼意思（R-59）。
   - (c) 第 5 步的整合字句符合我的原意，加上的「閘門檢查在 R-8 分支之前」也正確。只有末句的範圍要修（R-57）。
3. **F9W-31 (b) 指定**：沿用 F-9a 的 `CURRENCY_DIFFERS_LOG_PREFIX`，不另訂前綴。在 F-9a 欄位後面加 `verdict=`、`scope=` 兩欄；指數（`scope=index`）記 ERROR，股票（`scope=equity`）維持 WARNING。確切格式與測試要求見下方第二節（R-60）。
4. **F-9b 切分**：**不採「後端 F-9b-1／前端標籤 F-9b-2」**。後端先合併的話，庫存頁會直接顯示原始 token 字串；若沒有新 token，則會顯示「查無價格資料」，這正是 F9W-11 否決的語意。另外 F-9b-2 也會和既有的 F-9b2 撞名。
   - 改拆成 **F-9b0**（介面與建構參數，行為不變）和 **F-9b**（閘門本體加前端，仍是一個 PR）。
   - commit 順序也修正我先前的建議：改為「先消費端、後產生端」，deps 不放最後（R-68）。

## 各部門回報

### tech-architect

#### 一、抽驗結果

| 範圍 | 結果 | 說明 |
|---|---|---|
| D-2 (5)(a) 五步 | 忠實；有 2 處修正、1 處補註 | 第 1～4 步與 R-47、R-53、F9W-23、F9W-30 一致。第 5 步末句範圍過寬（R-57）。第 2 步的增量處置是新發現的缺口（R-64）。第 1～3 步屬 F-9b2、第 4～5 步屬 F-9b，ADR 沒有標明（R-67）。 |
| D-2 (5)(c) | 忠實 | 與 R-54 逐字一致。 |
| D-2 (5)(d)／C-30 | 字句要收窄 | 見下方 (a)（R-58）。 |
| D-4 指數段 | 忠實；4 處補強 | R-49、F9W-31、F9W-32 都已到位。要補的是：舊句和新句統一（R-59）、(b) 的記錄方式（R-60）、絆線涵蓋呼叫端（R-61）、(c)「一律 `bars=[]`」的解讀（R-62）。 |
| D-7 (2) | 忠實 | 不變式與 R-48 逐字一致。 |
| D-7 (7) | 忠實；漏列 1 項 | W-d 完整 reason 清單漏了 T-14（R-65）。F9W-33 段落正確。 |
| C-17 | 忠實；4 處補強 | 補強項見 R-59、R-60、R-61、R-67。其中「預置 D-9 標記」那一測只能在 F-9b2 做，因為 F-9b 還沒有標記欄。 |
| C-19 | 忠實 | 與 R-52 逐字一致，含我對 TA2 的自我更正。 |
| C-26 | 忠實 | R-47、F9W-30 (b)～(e) 都已納入。 |
| C-34 | 忠實；補 1 註 | F9W-33 (a) 的完全相等公式沒有考慮快取為多來源拼接的情形（R-66）。 |
| 失效條件 5 | 忠實 | 與 R-51 一致。 |
| 失效條件 13 | 忠實 | 與 F9W-32 (a) 一致。「記錄出現」要改指 R-60 的具體記錄。 |

**tech-writer 三問：**

- **(a) 不衝突，但字句要改。** 讀碼結果（`service.py` L202-273）：`reasons` 是梯子迴圈內的累積清單，成功路徑在 L265-273 只帶 `mixed_sources_reason(bars)`，累積原因整份丟掉。所以 T-15 只會在「其後各層都失敗」時出現，而且恰好一次；他層整段成功時出現 0 次。兩者不衝突。
  - 問題在字句：(d) 的「reason 加 T-15」容易被讀成「最終回覆一定帶 T-15」。C-30 的「只出現一次」照字面讀，也會要求成功情境也要有一次，和 C-34 (c) 衝突。修法見 R-58。
- **(b) 要統一。** 新句「不讀也不寫 D-9 標記」包含舊句「不寫 W-c 標記」，語意上不矛盾。但兩句並存，會讓人以為讀標記是允許的。修法見 R-59。
- **(c) 符合原意。** 第 5 步加上「快取閘門檢查必須在 R-8 分支之前，以測試釘住」和「照 D-7 的 F9W-18 條件」，都正確。
  - 唯一的問題是末句「回覆 `rejection=None`，該列正常估值」，這是我在 R-47 原文就寫得太寬。第 5 步也涵蓋「無快取而落在 ADR-0009 D-8 冷卻分支」（`COOLDOWN_NO_CACHE_REASON`、`bars=[]`），這時該列並不是「正常估值」，而是走既有的 `price` token；另外「回 None 走梯子」根本不算一個回覆。修法見 R-57。

#### 二、F9W-31 (b) 指定：指數快取閘門被擋時的記錄方式

**方案比較：**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A：沿用 `CURRENCY_DIFFERS_LOG_PREFIX`，加 `verdict`、`scope` 欄；指數記 ERROR（採用）** | 只要 grep 一個字串；F-9a 測試結構（`_layer()`、caplog 篩前綴）直接延用；「單位與市場不符」是同一類事件，不會因路徑不同而被拆開 | 要改 F-9a 定字測試（L251-261），F-9b 本來就得改 | 低 |
| B：另訂前綴（例如 `index price bars cache rejected:`） | 指數事件一眼可辨 | 同一類事件要 grep 兩個字串，容易漏看其中一個；要另寫一套測試基礎 | 中：操作端可能只監看其中一個 |
| C：只沿用前綴，不加欄，靠 `^` 代號辨識指數 | 改動最小 | 「`^` 開頭就是指數」是隱性約定；層級無法區分 | 中 |

**指定格式（R-60）：** F-9a 欄位順序不變，句尾附加兩欄，欄位之間以單一空白分隔。

```
price bars currency differs from market: symbol=<symbol> market=<market> expected=<expected> observed=<observed> mismatched=<n>/<total> layer=<layer> source=<source> verdict=<mismatch|missing> scope=<equity|index>
```

各欄規則：
- `observed`：各根宣告值去重、依原值排序後以 `,` 連接，不轉大小寫。空字串或只有空白的值寫成 `<blank>`。F-9a 現行寫法會產生 `,USD` 這種難讀的字串。
- `verdict`：取 `classify_currency` 的判定。整批同時有不符和空白時記 `mismatch`，與 D-2 (1) 的優先序一致。
- `layer`：沿用 F-9a 的五個值：`provider`、`layer0_cache`、`incremental_readback`、`fallback_cache`、`cache_only`。
- `scope`：由建構點顯式注入（R-56 的「三個建構點各自顯式傳入」），TW、US 傳 `equity`，指數傳 `index`。不給預設值，也不得以代號是否以 `^` 開頭推斷。

層級與觸發規則：
- **層級**：`scope=equity` 記 WARNING，延續 F-9a。`scope=index` 記 **ERROR**。理由是 D-4 認定此事件在正式設定下不可達，一出現就適用失效條件 13；這也和 `_try_provider` 對契約外事件提高 log 層級的既有慣例一致。
- **觸發**：F-9b 起，每個幣別閘門檢查點判定拒收時各記一筆，通過時不記。只要那個檢查點拒收了就要記，不看最終結果，包括：
  - 最終回覆帶 bars（冷卻期外整段重抓、自行修復）；
  - 回覆 reason 為 None（指數 layer 0 冷卻期內）。
- **不記此前綴**：准入拒絕不記，因為它不是幣別事件。
- **內容限制**：訊息不得含任何使用者面字面（W-a～T-15、C、C′），也不得含回應內容。logger 維持 `app.data.service`。

**測試要求**（放在 F-9b0 commit 3 和 F-9b commit 6，見第三節）：

1. **定字**：至少三筆完全相等的斷言：
   - 一筆 `scope=equity`（WARNING）；
   - 一筆 `scope=index`（ERROR）；
   - 一筆 `verdict=missing`，且 `observed` 含 `<blank>`。
2. **指數，梯子失敗**：假快取放入 `^GSPC`／US、`currency="TWD"` 的壞列，來源失敗。斷言：
   - ERROR 記錄的 `layer` 依序恰為 `["layer0_cache", "fallback_cache"]`；
   - 回覆 `bars=[]`、`rejection=cache_unit_rejected`；
   - reason 不含 T-15，也不含任何股票路徑常數。
3. **指數，自行修復**：同樣的壞列，冷卻期外 live 成功。斷言回覆帶新抓的列，而且仍恰好有一筆 `layer=layer0_cache` 的 ERROR。
4. **指數，冷卻期內**：回覆 reason 為 None，provider 呼叫 0 次，恰好一筆 ERROR。
5. **正式設定的負面測試**：取代 `test_f9a_service_currency_warning.py::test_index_ladder_is_explicitly_not_checked`。用 deps 組出的指數服務，stub 照 `INDEX_SYMBOL_METADATA` 回幣別，對 R-61 列出的每一組 (symbol, market) 斷言：沒有任何帶此前綴的記錄。
6. **股票**：沿用 F-9a 的情境矩陣，每個拒收檢查點恰好一筆 WARNING。
7. **准入拒絕**：不產生帶此前綴的記錄。
8. **字面隔離**：所有使用者面字面常數都不是任一筆記錄訊息的子字串。

**補充（拉取式偵測，不取代上述記錄）：** F-9a 盤點的 (a) 部分（`diagnose.py` L404-417）沒有排除 `^` 開頭的序列，所以手動改庫留下的指數壞列，跑 `currency-inventory` 也看得到。是否接告警屬 devops-sre 的範圍，F9W-31 沒有要求。

#### 三、F-9b 實作準備

**PR 拆分比較：**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 後端 F-9b-1 先合、前端 F-9b-2 後合 | 前端審查面分開 | 前端改動本來就只有 `MISSING_LABELS` 一鍵加測試，省不到多少審查量；名稱和 F-9b2 撞名 | 兩次合併之間會出現未經審查的使用者面狀態：`missingLabel()` 對未知 token 會原樣顯示；若產生端先落地而沒有新 token，會顯示「查無價格資料」，這是 F9W-11 否決的語意。**否決** |
| 資料層閘門先合，估值與 UI 後合 | 閘門可以先上線 | 同上：中間狀態違反 F9W-11、F9W-18 | **否決** |
| **F-9b0（介面＋建構參數，行為不變）→ F-9b（其餘，一個 PR）（採用）** | 把 45 處測試建構點的機械性改動和語意改動切開，F-9b 的 diff 只剩語意；F-9b0 不需風控和 qa-e2e；F9W-31 (a) 絆線提早落地 | 多一輪 qa-reviewer 加 Codex | 低：F-9b0 合併後行為與 F-9a 相同 |
| F-9b 再拆成消費端 α、產生端 β | 審查面更小 | 風控和 qa-e2e 要跑兩輪；α 合併後是一段沒有產生端的程式 | 不建議。若人力不足非拆不可，**只能 α 先合**，不可顛倒 |

**commit 順序修正：** 我先前建議「介面 → 閘門 → 准入 → W-d → 估值器 → 成因組 → 前端 → deps」，「deps 放最後」是錯的。建構參數一改為必填，deps 就必須在同一個 commit 一起改，否則中間的 commit 組不起來。改採「先消費端、後產生端」：產生端開始寫出 `rejection` 時，所有消費端都已經能正確處理，每個 commit 的狀態在語意上都一致，也方便 bisect。

**所有 commit 共同的門檻：**
- 後端 pytest 全綠，repo CI 既有的 lint、型別檢查全綠；有改前端的 commit，另加 vitest 和型別檢查。
- 除了下表明列要改寫的 F-9a「行為不變」測試，不得放寬任何既有測試的斷言。PR 說明要列出每一個被改寫的測試名稱。
- 新字面一律寫成逐字常數，並標註風控核可出處（C-9、C-29）。

**F-9b0（qa-reviewer＋Codex；不需風控、不需 qa-e2e）**

| # | commit | 測試門檻 | 對應 |
|---|---|---|---|
| 0-1 | `refactor: ProviderResult 新增內部 rejection 欄位與不變式` | 四種違反不變式的組合都 raise，兩種合法組合可建構；`LoadedBars.meta()` 鍵集合不變；OpenAPI schema 全文不含 `rejection`；這一步沒有任何產生端寫非 None 值 | C-34 (a)、C-18、D-7 (2) |
| 0-2 | `feat: 新增 classify_currency 三分類判準` | `check_currency` 判定的不符 ＝ mismatch ∪ missing；與 `currency_matches_market` 等價；`usd` 判為 mismatch，`""` 和 `"  "` 判為 missing，兩者並存時 mismatch 優先；KX-A1 續綠 | D-2 (1)、D-5、C-5 |
| 0-3 | `refactor: 日線服務幣別判準改為必填市場查表並注入 scope` | 共用測試 helper 收斂 45 處建構點；deps 三個建構點都改；F-9a 情境矩陣的回覆、資料表、來源呼叫次數與改前逐一相等；第二節的測試 1、5、6 先落地（觀察模式）；C-6 的幣別與 scope 部分；C-12；F9W-31 (a)＋R-61 絆線；grep 確認 production 沒有 `expected_currency=None`，也沒有預設值 | C-6（部分）、C-12、F9W-31 (a)(b)、R-56、R-61、壞處 4 |

**F-9b（qa-reviewer＋Codex＋風控＋qa-e2e）**

| # | commit | 測試門檻 | 對應 |
|---|---|---|---|
| 1 | `feat: load_bars 依 rejection 三分流（W-d）` | 用假服務注入 `rejection`，三個分流各至少一測；W-a～T-15 原樣傳出，不接 `NO_BARS_REASON`、不加 `PROVIDER_REASON_PREFIX`；有 bars 時 reason 原樣傳出 | D-7 (7)、C-13（管線）、C-18、F9W-6、F9W-22、F9W-33 (a)（傳遞部分） |
| 2 | `feat: 估值器新增單位拒收缺漏 token 且不查匯率` | 每種 `rejection` 各一測，斷言 `missing == [token]`、`fx` 和 `fx_open` 為 None、匯率 provider 零呼叫；`rejection` 為 None 而 bars 為空時走既有 token；有 bars 時正常估值；更新 `fx_open` docstring | C-19、C-11（估值部分）、C-34 (b)(c)(d)（估值部分）、F9W-18 |
| 3 | `feat: 整書成因組 T-11 與陳述順序` | 方向子句測試 1～6；X-3c 計數從三組延伸為四組（只能延伸）；T-11 完全相等加出處；不重用 `CURRENCY_MARKET_MISMATCH_CAUSE`；`UNVALUED_NOTE_TEMPLATE` 零 diff | C-20、C-21、C-29、F9W-17、F9W-25、壞處 10 |
| 4 | `feat: 庫存頁新增 T-12 缺漏標籤` | `MISSING_LABELS` 鍵集合測試；新標籤不以「查無」「本次未查」開頭；禁詞掃描通過；`price_guard.py` 零 diff，F-7 前端閘門測試未改且綠；後端 token 字串由後端測試釘住，前端鍵集合斷言含同一字串 | C-22、C-8、F9W-19 |
| 5 | `feat: 日線 live 層幣別閘門（W-c／W-c′ fail-closed）` | C-1 的 live 出口；W-c 層之後有層成功時改要整段（D-2 (2)）；改寫 F-9a live 層的「行為不變」測試 | C-1（live）、C-2、C-3、C-11、C-13 (3)(4)(5)(10)、C-14、C-33、C-34 (e)、F9W-4 (a) |
| 6 | `feat: 快取閘門與 T-15（layer 0 第 4、5 步、fallback、cache-only、合併讀回）` | C-1 六個出口；C-30（依 R-58 改版）；C-32（依 R-63 限定 fixture）；R-8 先後測試；第 4 步 `fetch_start == start`；C-34 (b)(c)(d) 端到端，含 F9W-33 (a) 單層與兩層各一測、F9W-33 (b) 的 `cached_stale`、R-66 的拼接一測；第二節測試 2、3、4、7、8；C-17 指數快取閘門部分 | C-1、C-13 (7)(8)(9)、C-17、C-30、C-32、C-34、F9W-31 (b)(c)、F9W-33 (a)(b) |
| 7 | `feat: 日線兩入口代號准入與 AV 縱深檢查` | deps 同步接上准入規則和字面組；指數只檢查幣別、沒有字面 | C-4、C-6（准入與字面組）、C-7、C-13 (1)(2)、C-15、C-16、C-17（grep 部分）、C-19（准入 live 與 cache_only 各一，端到端） |
| PR 層級 | — | C-28 消費端字串表；PR 說明引用 F9W-30～F9W-34 與 F7-R10；F9W-34 和 PR 表所列的 375／1280 qa-e2e；風控逐字審 | C-28、C-29、F9W-34 |

**F-9b2 範圍**（附帶整理，避免被誤放進 F-9b）：C-23～C-27、C-31、C-17 的「預置 D-9 標記」、C-19 的 cache_only W-c 標記、D-2 (5)(a) 第 1～3 步、R-64。

#### 四、ADR 修改清單（R-57 起；交 tech-writer）

〔TA5〕指本回覆。

**R-57〔D-2 (5)(a) 第 5 步末句〕**

「回覆 `rejection=None`，該列照 D-7 的 F9W-18 條件正常估值。〔TA4 R-47〕」改為：

> 以快取回覆時 `rejection=None`，該列照 D-7 的 F9W-18 條件正常估值；無快取而落在 ADR-0009 D-8 冷卻分支時，照現行回 `COOLDOWN_NO_CACHE_REASON`、`bars=[]`、`rejection=None`，估值照既有規則，不給新 token；回 None 時依梯子結果決定。〔TA4 R-47；TA5 R-57〕

**R-58〔D-2 (5)(d)、C-30〕**

(d)「reason 加 T-15，不用 `MERGE_READBACK_FAILED_REASON`；之後各層整段請求；`_fall_back_to_cache` 不再讀快取；T-15 至多出現一次。」改為：

> T-15 併入本次梯子的累積原因（取代 `MERGE_READBACK_FAILED_REASON`）；之後各層整段請求；`_fall_back_to_cache` 不再讀快取。其後各層皆失敗時，回覆 reason 含 T-15 恰一次、`rejection=cache_unit_rejected`；其後有層整段成功時，依 D-7 (7) 只帶 `mixed_sources_reason`，不含 T-15、`rejection=None`（C-34 (c)）。〔TA3 R-39；TA5 R-58〕

C-30 改為：

> 合併讀回被擋且其後各層皆失敗時，T-15 恰出現一次，且不出現 `MERGE_READBACK_FAILED_REASON`；其後有層整段成功時 T-15 出現 0 次（C-34 (c)）。〔TA3 R-43；TA5 R-58〕

**R-59〔D-4 第二點、C-17 句首〕**

- D-4 的「指數閘門不帶任何使用者面字面、不寫 W-c 標記」改為「指數閘門不帶任何使用者面字面、不讀也不寫 D-9 標記（見下〔TA4 R-49〕）」。
- 在「指數路徑〔TA4 R-49〕」那一點之後加：

> 「不寫」指指數服務寫入 attempt log 時 `rejection` 一律為 NULL（與 D-9「其他提問一律寫 NULL」一致）；「不讀」指指數服務的 layer 0 與 `get_cached_bars` 不做 D-9 守門。讀寫與否由建構點顯式設定，不得以代號是否以 `^` 開頭推斷。〔TA5 R-59〕

- C-17 句首「指數服務不寫標記、不帶 W-c 字面；」改為「指數服務不讀也不寫 D-9 標記、不帶任何使用者面字面；」。

**R-60〔D-4 (b)、C-17、失效條件 13、實作進度補記、佐證末段〕**

- D-4 (b) 的「（可沿用 F-9a 的 `CURRENCY_DIFFERS_LOG_PREFIX` WARNING，或由 tech-architect 指定同等方式；採哪一種**待 tech-architect 指定**）」改為：

> 已指定（TA5 R-60）：沿用 `CURRENCY_DIFFERS_LOG_PREFIX`，F-9a 欄位後附 `verdict=<mismatch|missing> scope=<equity|index>`；`scope=index` 記 ERROR、`scope=equity` 記 WARNING；每個拒收的閘門檢查點各記一筆，不論最終回覆是否帶 bars、reason 是否為 None；`observed` 中的空白值寫為 `<blank>`；准入拒絕不記；訊息不含使用者面字面。完整格式與測試見 TA5 第二節。

- C-17 的「指數快取閘門被擋須留下操作端看得到的記錄並以測試釘住（F9W-31 (b)）」句尾加「，方式見 D-4 (b)〔TA5 R-60〕」。
- 失效條件 13 的「F9W-31 (b) 的記錄出現」改為「F9W-31 (b) 的記錄（`scope=index` 的 `CURRENCY_DIFFERS_LOG_PREFIX` ERROR）出現」。
- 實作進度補記（F-9a）加一點：「F-9b 起此 WARNING 附加 `verdict`、`scope` 兩欄，指數改記 ERROR（TA5 R-60）。」
- 佐證末段「仍待指定：…」改為「已指定（TA5 R-60）」。

**R-61〔D-4 (a)、C-17 絆線〕**

在「`INDEX_SYMBOL_METADATA` 幣別一致（測試）」之後加：

> 另以測試釘住：`INDEX_MAPPING` 中 `basis == "official_index"` 的每一列、`MARKET_BENCHMARK` 的每一項，其 `(series_symbol, market)` 皆滿足 `INDEX_SYMBOL_METADATA[series_symbol] == (market, MARKET_CURRENCY[market])`。理由：閘門依呼叫端傳入的 market 查預期幣別，不依 metadata；若某列把 `^NDX` 標為 TW，正式設定下 live 指數閘門即會觸發。〔TA5 R-61；強化 F9W-31 (a)，送風控知悉〕

讀碼依據：
- `index.py` L255、L377 以 `ref.series_market` 或 `market` 呼叫服務；
- `index_mapping.py` L168-295 目前全部一致；
- `index.py` L302-305 的 `MARKET_BENCHMARK` 也一致。

**R-62〔D-4 (c)〕**

句尾加：

> 「一律 `bars=[]`」指由快取閘門拒收決定的回覆（layer 0 冷卻期內、`_fall_back_to_cache`、`get_cached_bars`、合併讀回被擋且其後無層成功）。layer 0 被擋而冷卻期外整段重抓、live 層通過閘門時，回覆帶新抓的列，被拒的舊列不上畫面（與股票路徑壞處 5 的自行修復相同），D-4 (b) 的記錄照記。〔TA5 R-62；此解讀待風控確認〕

**R-63〔壞處 5 句尾、C-32 加註〕**

壞處 5 句尾加：

> 例外（孤兒壞列）：請求區間內若有壞列落在來源不回傳的日期（只在手動改庫或 `MARKET_CURRENCY` 變動後可能出現），整段重抓成功也覆寫不到（`cache.put` 為逐列 upsert）。之後每次點擊 layer 0 都會被擋，且因最後一次提問是成功、不符 R-8 冷卻條件，會每次重跑梯子（美股每次耗一次 AV 額度），直到 F-9e 清理。D-2 (5) 不刪資料，故不在服務層修補；每次都會留下 D-4 (b) 的記錄；指數路徑適用失效條件 13，股票路徑應儘速執行 F-9e。〔TA5 R-63；送風控知悉〕

C-32 加註：

> 「來源成功後，同一請求下一次由 layer 0 服務」以壞列皆落在來源回傳日期的 fixture 測試。〔TA5 R-63〕

不採的替代方案：把第 4 步的冷卻條件改成「最後一次提問在冷卻期內」，不論那次是否成功。這會改變 T-15 的分流，依 C-29 要回風控；而且使用者剛看到新資料，下一次點擊就變成 T-15，畫面會來回跳。

**R-64〔D-2 (5)(a) 第 2 步；F-9b2〕**

「快取被擋時，本次停用增量。」改為：

> 本次停用增量（不論快取是否被擋），使來源成功時以整段新列覆寫可疑舊列，而不是讀回快取頭段與新尾段合併回覆；同一次呼叫中梯子全部失敗時，`_fall_back_to_cache` 依現行規則處理（標記已被本次一般失敗覆寫，屬壞處 9）。〔TA5 R-64〕

理由：D-2 (3) 規定「任何讀取路徑都不以快取回該序列價格」，而合併讀回就是一條會回出快取列的路徑。這項只會讓系統更保守，不改任何字面，送風控知悉即可。

**R-65〔D-7 (7) 首句〕**

「W-a、W-b、W-c、W-c′、C、C′、T-15 即完整 reason」改為「W-a、W-b、W-c、W-c′、C（或採用時的 T-14）、C′、T-15 即完整 reason」。

**R-66〔C-34 (b) 加註〕**

> F9W-33 (a) 的完全相等以單一來源的快取 fixture 測。快取為多來源拼接時，`_cached_result`（`service.py` L553）依 ADR-0005 D-5 於句尾再接拼接揭露句，期望值為 `_combine_reasons([各層原因..., W-c′ 句, mixed_sources_reason(bars)])`，另一測釘住（W-c′ 句完整、拼接句在最後）。不得為了符合 F9W-33 (a) 而移除拼接揭露。〔TA5 R-66；送風控知悉〕

**R-67〔分期標註〕**

- D-2 (5)(a) 開頭加：「第 1～3 步（讀 D-9 標記）屬 F-9b2；F-9b 只實作第 4、5 步。F-9b2 在第 4 步之前插入第 1～3 步，不得改變第 4、5 步的行為，並重跑其測試。〔TA5 R-67〕」
- C-31 標「（F-9b2）」；在 F-9b 改測「快取被擋不新增 `record_attempt` 呼叫點」。
- C-17 的「預置任何 D-9 標記不改變指數回覆」標「（F-9b2）」。
- C-13 (7) 加「（無有效標記時；有標記見 D-2 (5)(a) 第 1、3 步）」。

**R-68〔PR 拆分表〕**

- 新增 F-9b0 列：
  - 內容：`ProviderResult.rejection` 與不變式；`classify_currency` 與等價測試；`MarketDataService` 幣別判準改為 keyword-only 必填的市場查表函式並注入 `scope`；共用測試 helper；deps 三個建構點；F9W-31 (b) 記錄格式（觀察模式）；C-12；F9W-31 (a)＋R-61 絆線。**行為不變**：除了記錄以外，回覆、快取、log 表與來源呼叫都與合併前相同。
  - 審查：qa-reviewer＋Codex；不需風控、不需 qa-e2e。F-9b0 是 F-9b 的前提。
- F-9b 列的「建議分 commit：…」改為：

> 先消費端、後產生端：W-d → 估值器 → 成因組 → 前端 T-12 → live 閘門 → 快取閘門 → 准入與 AV 縱深（含 deps 准入／字面組接線）；介面與建構參數已於 F-9b0 完成〔TA5 R-68〕

- 硬性順序句改為「F-9b0 → F-9b → F-9b2 → F-9c」。

**R-69〔檔頭優先序〕**

「TA4 在下述衝突優先序中的位置，來源未載…」改為：

> tech-architect 各次之間以後者為準（TA5 ＞ TA4 ＞ TA3 ＞ TA2 ＞ TA1）；風控裁定優先於全部 tech-architect 項。

來源清單加上本回覆（檔名由 coordinator 定）。

### 給其他部門（經 coordinator 轉達）

- **tech-writer**：套用 R-57～R-69。R-62 在風控確認前，以「待風控確認」標註。
- **risk-compliance-officer**：
  - **需確認**：R-62，即 F9W-31 (c)「一律 `bars=[]`」不涵蓋整段重抓成功的自行修復。
  - **知悉即可**：
    - R-60，採用風控建議的第一個方式（沿用前綴），指數另升為 ERROR；
    - R-61，絆線補強；
    - R-63，孤兒壞列殘留；
    - R-64，W-c 標記冷卻期外停用增量，比原設計更保守；
    - R-66，W-c′ 句後接既有的拼接揭露句。
- **dev-lead／data-engineer**：
  - F-9b0 可以先開工，它是行為不變的重構，不依賴 T-10。
  - F-9b 照第三節的 commit 表實作，並遵守 R-57、R-58、R-60、R-61、R-66。
- **qa-reviewer**：
  - F-9b0 審「行為不變」：F-9a 情境矩陣要逐一相等。
  - F-9b 逐 commit 依「對應」欄勾核，另加勾第二節測試 1～8。
- **devops-sre**（可選）：要不要對 `scope=index` 的 ERROR 接告警，由你們評估；F9W-31 沒有要求。

## 驗證

**讀過的文件：**
- ADR-0024 全文（524 行）
- TA4（R-47～R-56）
- 風控 F9W-30～F9W-34
- TA2 L70-89 與 PR 表
- TA3 中「增量」「冷卻期外」相關段落
- 任務單「更新後 PR 拆分」（L77-85）

**讀碼核對**（工作樹現況）：
- `/home/user/AICompany/apps/stock-desk/backend/app/data/service.py`：
  - `CURRENCY_DIFFERS_LOG_PREFIX` 在 L28；建構子 L168-183（`expected_currency: str | None = None`）。
  - 累積原因只在失敗時合併，成功路徑在 L265-273 只帶 `mixed_sources_reason`。
  - 合併讀回失敗在 L221-231；WARNING 格式在 L352-363；layer 0 在 L392-523；`_cached_result` 合併拼接句在 L553；`_fall_back_to_cache` 在 L601-651。
- `/home/user/AICompany/apps/stock-desk/backend/app/data/cache.py`：`put` 為 `ON CONFLICT(symbol, market, trade_date) DO UPDATE`（L215-219），逐列 upsert，這是 R-63 的依據。
- `/home/user/AICompany/apps/stock-desk/backend/app/api/deps.py`：L101-115、L144-151（指數服務傳 `expected_currency=None`，共用同一個 cache）。
- `/home/user/AICompany/apps/stock-desk/backend/app/services/index.py`：
  - `NO_BARS_REASON` 在 L74；L245-269 以 `ref.series_market` 呼叫服務；
  - `MARKET_BENCHMARK` 在 L302-305；L377-389。
- `/home/user/AICompany/apps/stock-desk/backend/app/leverage/index_mapping.py`：L168-295，`series_market` 與 metadata 現況一致。
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py`：L122-126。
- `/home/user/AICompany/apps/stock-desk/backend/app/data/diagnose.py`：L225-228、L404-420，盤點 (a) 部分沒有排除 `^` 序列。
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_f9a_service_currency_warning.py`：L200-344（定字測試，以及 F-9b 須翻轉的指數「不檢查」測試）。
- `/home/user/AICompany/apps/stock-desk/frontend/app/lib/valuationWording.ts`：L17-48（未知 token 原樣顯示，這是否決前後端拆 PR 的依據）。

**屬推論、尚未實證：**
- R-63 的「每次點擊重跑梯子」：依 upsert 語意和第 4 步的 R-8 條件推得。
- R-61：依呼叫端的 market 推得。
- 第二節測試 2 的 `layer` 序列 `["layer0_cache", "fallback_cache"]`：依 D-2 (5)(a)(b) 推得。

以上都須由對應測試實證。

**未做的事：** 沒有執行測試，沒有 git 操作，沒有連網，沒有改檔，沒有讀 `.env` 和 `*.db`。

## 下一步

1. **coordinator**：把本回覆存到 `work/reviews/`，再把 R-57～R-69 交給 tech-writer 套用到 `/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md`。同時把 R-62（需確認）和 R-60、R-61、R-63、R-64、R-66（知悉）轉給 risk-compliance-officer。
2. **risk-compliance-officer**：裁示 R-62。
3. **dev-lead**：開 F-9b0（3 個 commit）。F-9b 等 F-9b0 合併後開工；建議等 T-10 核可後再合併。
4. **tech-writer**：套用後回報，我再抽驗 R-57、R-58、R-60、R-68 這四處的落字。
5. **CEO**：T-10 核可時，除了既有的知悉事項，再一併知悉 R-63 的孤兒壞列殘留（只在異常資料狀態下出現）。

相關檔案（絕對路徑）：
- /home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md
- /home/user/AICompany/work/reviews/2026-10-12-tech-architect-ADR-0024抽驗與待確認項裁決R-47至R-56.md
- /home/user/AICompany/work/reviews/2026-10-12-F-9-R47至R49送審裁示-F9W-30至F9W-34-風控.md
- /home/user/AICompany/work/dispatch/2026-10-08-任務單-F-9-日線上游幣別未核對.md