# ADR-0027 B2 自決事項裁定與 N-137 補字字面

- 審查者：tech-architect
- 日期：2026-10-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

8 點都裁定完了。多數接受，有兩處要退件小修，合併前必須改掉：

1. **第 2 點的子項：`c8_decision_ref`、`c8_decision_sha256` 算進 `definition_logic_sha256`，退件。**
   - 這兩欄只是 C-8 決策紀錄的出處，不影響任何標籤或判定。
   - 算進 logic 雜湊會和 D-10 第 2 點衝突。只改文字的 MINOR 升版若動到出處，logic 雜湊就會變，結果是新版的紀錄被「logic 雜湊須等於所屬 claim」擋下；不然就是讓純字面變更登記出新 claim，越過 FL-33 和 D-12 (iv) 的結構檢查。
   - 修法：兩欄移出 logic 雜湊；另外新增完整雜湊 `definition_sha256`，和第 4 點一起做。
2. **第 5 點的子項：`min_member_weight` 用 float 參數傳入，退件。**
   - 事先宣告 §1.2 L880 把覆蓋規則釘在 `SectorMomentumDefinition` v1。這個 90% 會影響標籤，卻不在 logic 雜湊範圍內；族群方法日後改版時，它會在 claim 進行中途跟著變動。
   - 修法：改成 dirdef 常數 `BASKET_MIN_MEMBER_WEIGHT`（名稱暫定），`basket_log_returns` 改用沒有預設值的關鍵字參數 `definition` 讀取。這也是我上一份範圍說明 D 第 6 點原本的約束。

第 6 點的處理是修訂 ADR 字面，不合併模組。N-137 第 1、3 點的補字字面已經寫好，見下文 C 節。另外審查時發現 4 個新問題，列進文末的追蹤清單；其中第 3 項會擋規則集的登記。

## 各部門回報

### tech-architect

#### A. 逐點裁定

| # | 事項 | 裁定 |
|---|---|---|
| 1 | `rules_logic_sha256` 排除規則集的 `version`；`name`、`invalidation` 算入雜湊 | **接受，但需 ADR 補字**（B2D-1a）。排除 `version` 是必要的：算入的話，PATCH 升版就會改變 logic 雜湊，和 D-10 第 2 點、第 3 點 UNIQUE 的用意相反。`invalidation` 依 ADR-0025 D-2 第 3 點是「機器可檢查的運算式」，屬於邏輯，**不得**列為字面鍵（這點要寫進 ADR）。`name` 暫留在雜湊內，凍結時由 quant 決定。 |
| 2a | 新增 `description` 文字欄，排除於雜湊 | **接受**（字面併入 B2D-1b）。 |
| 2b | `c8_decision_ref`／`sha256` 算入雜湊 | **退件**。理由見本次結論第 1 點；修法見 D 節 C-1～C-4，ADR 字面見 B2D-1。 |
| 2c | FL-31、36、37 的欄位名稱暫定 | **接受，登記追蹤**（T-2）。附帶發現：事先宣告 §4.1 的 N_eff 區塊長度是 h，§4.2、§4.3 用的是 4（另列 2、8）。單一個 `BOOTSTRAP_BLOCK_LEN` 表達不了兩種，凍結時要拆欄。 |
| 3 | `DirectionDefinition` 套用 construct／copy 守門，加型別層級的形狀檢查 | **接受，但需 ADR 補字**（B2D-2）。這是收緊。形狀檢查都對照過：退出期限 150／250 確實都是檢查點（D-12 (i) 與主方案條件二）；區塊長度主值 4、另列 (2, 8) 也能通過。寫進 ADR，是為了防止日後有人以「ADR 沒要求」為由拿掉。 |
| 4 | 登記表 entry 同時登記定義物件與 logic 雜湊，由 `definitions.py` 重算比對 | **接受，但需 ADR 補字，並追加一項實作**（B2D-1c、1d、1f）。只登記 logic 雜湊的話，已登記版本的文字欄位可以原地修改而沒人發現；規則集那一側有 `rules_sha256` 做完整位元組比對，定義物件這側沒有，兩邊不對稱。所以要追加完整雜湊 `definition_sha256`，登記並比對。另外，D-1 原句「每版只登記 horizon 與雜湊」字面上也涵蓋定義登記表，要分開寫。 |
| 5a | `coverage_unknown` 關鍵字參數，沒有預設值 | **接受，但需 ADR 補字**（B2D-3b、3c）。少了它，函式無法做事先宣告 §2.1 第 2 點的成員層排除。 |
| 5b | `min_member_weight` float 參數 | **退件**。修法見 D 節 C-5～C-6，ADR 字面見 B2D-3。 |
| 6 | FL-78 (a)「不 import 任何 `app.*`」解讀為允許套件內 import | **接受你的解讀，修訂 ADR 字面**（B2D-4），**不合併模組**。原字面是我在範圍說明 D 第 1 點照抄 D-1 列的，本意是不依賴套件外的 `app.*`；把六個模組併成一個檔沒有任何架構收益。 |
| 7a | 交集格延到 D-15 的 B13 | **接受，但需 ADR 補字**（B2D-5），把先後順序寫成閘門：`OUTLOOK_RULE_FIELDS` 必須維持空集合，直到 `POLICY_FORBIDDEN_FIELDS` 落地；登記非空集合的批次不得早於 B13。現有測試（`test_dirdef_rules.py:318`）已經斷言集合為空，等於已有一道絆線。 |
| 7b | `basket_hold_ratio` 不套用 90% 門檻 | **接受，登記追蹤**（T-1）。B1 分子與 B4 在成員缺 bar 時怎麼處理，屬於規則選擇，事先宣告沒寫。要由 quant 具名登記、送風控，期限是 G-3 凍結之前、baselines 批之前。這一格不能由實作自己決定。 |
| 7c | set、frozenset、dict 鍵靜默跳過 | **接受**（照 ADR 現行揭露；N-136 已在追蹤）。建議（不阻擋合併）加一格絆線：遞迴檢查 `DirectionDefinition` 與規則集 model 的欄位型別註記，出現 set、frozenset、dict 或 Mapping 就失敗，訊息指向 N-136。這樣 N-136「出現這類欄位前」的期限就能機械化檢查。 |
| 8 | N-137 第 1、3 點補字 | 字面見 C 節的 N137-1～N137-4；N137-5（例外具名）建議同批補上。 |

#### B. 方案比較

**c8 出處欄位的雜湊範圍（第 2、4 點）**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 甲：照 dev-lead，算入 logic 雜湊，不加完整雜湊 | 改得最少 | 和 D-10 第 2 點衝突；純出處變更能通過 FL-33 結構檢查；已登記版本的文字可原地修改 | 高（底線 5） |
| **乙：移出 logic 雜湊，加完整雜湊 `definition_sha256` 並登記比對（採用）** | 和 D-10、§2.4 MINOR 語意一致；任何欄位都不能原地修改；和規則集的 `rules_sha256` 對稱 | 多一個雜湊函式、entry 多一欄 | 低 |
| 丙：移出 logic 雜湊，不加完整雜湊 | 改得少 | 出處欄位可原地修改，執行期查不到 | 中 |

**籃子 90% 的來源（第 5 點）**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 甲：float 參數，呼叫端取 `CoverageRules`（dev-lead） | 純函式、和 sectors 解耦 | 值不在 logic 雜湊範圍；族群方法改版會在 claim 中途改變判定；呼叫端可能傳字面值 | 中高 |
| **乙：dirdef 常數，經 `definition` 傳入（採用）** | 值隨 `definition_version` 固定；和 `sigma_d` 同型，AST 可檢查 | 同一個值存兩處，靠登記批的一致性測試把關 | 低 |
| 丙：basket import `app.sectors` | 單一來源 | 違反 D-1 basket 列與 FL-56 | 否決 |

**FL-78 (a) 字面（第 6 點）**：修訂字面（採用），或把六個模組併成一檔。後者沒有收益，也破壞模組職責，否決。

#### C. 決策（ADR 草案，交 tech-writer）

ADR-0027 狀態是 proposed，依 ADR-0001 可以原地修訂，檔尾要加修訂紀錄段。下列每個 old 字串或錨點，我都用 Grep `-o` 確認過在現行檔中恰好出現 1 次。標記「接字」的，是接在錨點原句之後。

**B2D-1a　L1618（D-10 第 1 點，`rules_logic_sha256`）**　方向：補定義。CEO：否。風控：輕量確認（與 B2D-1 同批）
- 錨點：`以及 quant 凍結時列出的其他字面鍵）後，做正規化的 sha256。`
- 接字：
```text
（B2D-1；tech-architect 2026-10-25）規則集層級的 `version` 也不在範圍內：PATCH 升版必改 `version`，算入就會讓只改文字的升版產生不同的 logic 雜湊，與第 2 點「沿用原 claim」及第 3 點 UNIQUE 的用意相反。規則的 `invalidation` 依 ADR-0025 D-2 第 3 點是機器可檢查的運算式，屬於邏輯，不得列為字面鍵；`name` 在凍結前暫列範圍內，是否列為字面鍵由 quant 凍結時依前句決定。
```

**B2D-1b　L1619（D-10 第 1 點，`definition_logic_sha256`）**　方向：補定義；新增完整雜湊屬收緊。CEO：否。風控：輕量確認（涉及 D-14 G-2、底線 5、底線 7）
- 錨點：`同理定 `definition_logic_sha256`：只含常數，不含說明文字。`
- 接字：
```text
（B2D-1）範圍是定義物件的全部欄位，扣除版本標籤 `definition_version`、說明文字欄位（v1 只有 `description`；凍結時 quant 另列的文字欄位，例如事先宣告「經風控 R-1 裁定的已知偏離」一點要求的載明欄位，同此），以及 D-14 的 `c8_decision_ref`、`c8_decision_sha256`。後兩者是 C-8 決策紀錄的出處，不影響任何標籤、基準或判定；C-8 的選擇本身由 `f2_variant` 承載，在範圍內（D-14、FL-37）。所以只改上述欄位屬於 MINOR 升版，沿用原 claim（第 2 點），也不能據以登記新 claim（第 3 點 UNIQUE、D-12 共同部分 (iv)）。另定定義物件的完整雜湊 `definition_sha256`：與 logic 雜湊同一套正規化，涵蓋全部欄位。`PUBLISHED_DIRECTION_DEFINITIONS` 每版登記定義物件與這兩個雜湊，`app/forecast/definitions.py` 回傳前逐一重算比對，所以已登記版本的任何欄位（含文字與出處欄位）都不能原地修改，只改文字也要升 MINOR、另登一版（事先宣告 §2.4）。兩個雜湊函式與排除欄位的集合，在 `app/` 內都只在 `app/dirdef/` 定義一次。
```

**B2D-1c　L235（D-1 `app/dirdef/` 列）**　方向：補定義（消除歧義）
- old：`` `PUBLISHED_DIRECTION_DEFINITIONS`、`PUBLISHED_RULESETS`（每版只登記 horizon 與雜湊，不含規則內容） ``
- new：
```text
`PUBLISHED_DIRECTION_DEFINITIONS`（B2D-1：每版登記該版的定義物件與 `definition_logic_sha256`、`definition_sha256`，D-10 第 1 點）、`PUBLISHED_RULESETS`（每版只登記 horizon 與雜湊，不含規則內容）
```

**B2D-1d　L236（D-1 `app/forecast/definitions.py` 列）**　方向：收緊
- 錨點：`依 `definition_version`、`rules_version` 回傳已登記的定義物件與規則集，查無時拋例外，不回預設值。`
- 接字：
```text
（B2D-1）定義物件回傳之前，先核對它的 `definition_version` 等於查表的鍵，並重算 `definition_logic_sha256` 與 `definition_sha256`，與登記值比對，任一不符就拋例外、不回傳。
```

**B2D-1e　L2448（D-14 G-2 的機器部分）**　方向：補定義
- 錨點：`` `c8_decision_ref` 是 repo 相對路徑；`c8_decision_sha256`； ``
- 接字：
```text
（B2D-1）這兩欄在 `definition_sha256` 的範圍內，不在 `definition_logic_sha256` 的範圍內（D-10 第 1 點）；
```

**B2D-1f　L3081（FL-26 句末）**　方向：收緊（測試）
- 錨點：`loader 遇到 `rules_sha256` 不在 `PUBLISHED_RULESETS` 就拒絕載入。`
- 接字：
```text
（B2D-1）定義物件：已登記版本原地改 `description` 或 `c8_decision_ref`、登記的兩個雜湊照舊 → `app/forecast/definitions.py` 拒絕，而且這兩種修改都不改變 `definition_logic_sha256`；`definition_version` 與查表的鍵不同 → 拒絕；排除欄位以外的每一個欄位改值 → `definition_logic_sha256` 改變（表格驅動，表涵蓋排除欄位以外的全部欄位）；規則集的 `version` 與 `explanation`、`counterargument` 改值 → `rules_logic_sha256` 不變，其餘欄位改值 → 改變。
```

**B2D-2a　L235（D-1 `app/dirdef/` 列第 (4) 點）**　方向：收緊
- 錨點：`` `model_copy` 在 `update` 不是 None 時拋 `TypeError`（比照 D-15 第 3 點 3a）； ``
- 接字：
```text
（B2D-2）`DirectionDefinition` 同樣套用這兩項，定義物件只能經型別驗證建構；它的型別驗證只拒絕任何一版定義都不可能採用的值（非有限、越界、重複、未嚴格遞增，以及退出期限不是同一 scope 的檢查點之一，依 D-12 主方案條件二「在 n＝150（族群 n＝250）的檢查點」），不釘數值；
```

**B2D-2b　L3282（FL-78 (h)）**　方向：收緊（測試）
- old：`` 規則集、規則與條件 model 的 `model_construct` 與帶 `update` 的 `model_copy` → `TypeError` ``
- new：
```text
規則集、規則與條件 model 以及 `DirectionDefinition`（B2D-2）的 `model_construct` 與帶 `update` 的 `model_copy` → `TypeError`
```

**B2D-3a　L235（D-1 `app/dirdef/` 列）**　方向：補定義（值不變：沿用 90%）；收緊（門檻隨 `definition_version` 固定）。風控：知悉。quant：知悉（新欄位）
- old：`` `SPLIT_SUSPECT_ABS_RETURN` 與 D-14 的三個欄位） ``
- new：
```text
`SPLIT_SUSPECT_ABS_RETURN`、族群籃子成員層的覆蓋門檻 `BASKET_MIN_MEMBER_WEIGHT`（B2D-3；名稱暫定）與 D-14 的三個欄位）
```

**B2D-3b　L260（D-1 `basket.py` 列）**
- old：`` `basket_log_returns(members, series, window)` ``
- new：`` `basket_log_returns(members, series, window, *, coverage_unknown, definition)` ``

**B2D-3c　L260（同列）**
- 錨點（檔內原文是跳脫過的管線符號，要逐字照抄）：`90% 的分母用 \|S_T\|，被排除的權重 > 10% 時輸出 `E-ADJ-COVERAGE`；`
- 接字：
```text
（B2D-3）`coverage_unknown` 是 60 日窗內除權息覆蓋不明的成員（事先宣告 §2.1「族群籃子 σ_d」第 2 點、§5.2 `E-ADJ-COVERAGE` 的成員層判定），由呼叫端判定後傳入，必須是 `members` 的子集；90% 取自 `definition.BASKET_MIN_MEMBER_WEIGHT`，10% 是 1 減該值；兩者都是沒有預設值的關鍵字參數。`BASKET_MIN_MEMBER_WEIGHT` 的值沿用 `SectorMomentumDefinition` v1 的 `coverage.sector_coverage_threshold`（事先宣告 §1.2「母體與覆蓋率規則沿用 `SectorMomentumDefinition` v1」、§2.1 第 2 點「不是新值」）；以 dirdef 常數存放，是為了讓這個會影響標籤的門檻落在 `definition_logic_sha256` 的範圍、隨該紀錄的 `definition_version` 固定，族群方法日後改版不改變已登記 dirdef 的判定。`app/forecast/**`、`app/outlook/**` 判定族群籃子成員層 90%／10% 之處（本函式，以及事先宣告 §1.2 籃子結算的 10% 排除上限）都只取這個常數，不讀 `app.sectors` 的 `CoverageRules`（AST）；
```

**B2D-3d　L3306（FL-56 末條）**　方向：收緊（測試）
- 錨點：`` `app.outlook.basket`、`app.outlook.volatility` 不可達 `app.sectors.*`。 ``
- 接字：
```text
（B2D-3）`basket_log_returns` 的 `coverage_unknown`、`definition` 是沒有預設值的關鍵字參數，`app/` 內每一個呼叫點都以關鍵字傳入、`definition` 的值不是字面值（AST，比照 FL-78 (e)）；10%／11%／20% 的格以 `BASKET_MIN_MEMBER_WEIGHT = 0.9` 的 fixture 定義物件驅動；`coverage_unknown` 含非成員 → `ValueError`；第一次登記的那一批，另以測試釘住已登記版本的 `BASKET_MIN_MEMBER_WEIGHT` 等於 `SectorMomentumDefinition` v1 的 `coverage.sector_coverage_threshold`。
```

**B2D-4a　L235（D-1 `app/dirdef/` 列）**　方向：補定義（消除歧義，不變）
- old：`` （都是既有依賴），不 import 任何 `app.*`； ``
- new：
```text
（都是既有依賴），不 import 本套件以外的任何 `app.*`（B2D-4：套件內模組之間的 import 不受限，絕對或相對寫法皆可）；
```

**B2D-4b　L3282（FL-78 (a)）**
- old：`` (a) `app.dirdef` 不 import 任何 `app.*`， ``
- new：
```text
(a) `app.dirdef` 不 import 本套件以外的任何 `app.*`（B2D-4：以模組名稱的前兩段判定，`app.dirdef` 及其子模組允許，其餘 `app.*` 一律違規；相對 import 依所在套件換算成絕對名稱後判定；不以字首字串比對，所以 `app.dirdef_x` 這類名稱不算本套件），
```

**B2D-5　L3282（FL-78 (j) 後半）**　方向：收緊（閘門順序）
- 錨點：`` `OUTLOOK_RULE_FIELDS` 與 `app.advice.context.POLICY_FORBIDDEN_FIELDS` 沒有交集（測試內 import 兩者）； ``
- 接字：
```text
（B2D-5）這一格與 D-15 第 2 點 `POLICY_FORBIDDEN_FIELDS` 的落地同一批啟用；在那之前 `OUTLOOK_RULE_FIELDS` 必須為空集合（測試斷言），登記非空 `OUTLOOK_RULE_FIELDS` 的批次不得早於該批；
```

**N137-1　L235（D-1 `app/dirdef/` 列第 (3) 點句末）**　方向：補定義
- 錨點：`所以涵蓋 D-10 第 1 點去掉的全部文字欄位。`
- 接字：
```text
（N-137）這個列舉函式是 `app/dirdef/strings.py::string_values`，與 `app/forecast/definitions.py` 列 N-128 句所用的是同一個函式，`app/` 內恰有一個定義（FL-78 (g)、(l3)）。
```

**N137-2　L236（D-1 `app/forecast/definitions.py` 列）**
- old：`位於 `app/dirdef/`（名稱由 dev-lead 定）`（L1581 另有一處「（名稱由 dev-lead 定）」，所以 old 要帶前綴）
- new：
```text
位於 `app/dirdef/`（N-137：`app/dirdef/strings.py::string_values`）
```

**N137-3　L3282（FL-78 (g)）**　方向：收緊（測試）。單一定義清單一併補上 D-1 列已定為唯一定義的兩個雜湊函式與載入函式
- old：`` (g) `app/` 內 `DirectionDefinition`、`OUTLOOK_RULE_FIELDS` 與兩個登記表各恰一個定義，都在 `app/dirdef/`（grep）； ``
- new：
```text
(g) `app/` 內 `DirectionDefinition`、`OUTLOOK_RULE_FIELDS`、兩個登記表、`definition_logic_sha256`、`definition_sha256`（B2D-1）、`rules_logic_sha256`、規則集載入函式與字串值列舉函式 `string_values`（N-137）各恰一個定義，都在 `app/dirdef/`，其中 `string_values` 在 `app/dirdef/strings.py`（grep）；
```

**N137-4　L3282（FL-78 (h)，「字串欄位」與 (l) 對齊）**　方向：收緊（測試）
- old：`` 每個禁詞 × 規則集與規則的每一個字串欄位各一格，以 fixture 規則檔的位元組與相符的雜湊經載入函式載入 → 拒絕； ``
- new：
```text
每個禁詞 × fixture 規則集的每一個字串值位置各一格（N-137：位置依 `app/dirdef/` 列第 (3) 點遞迴列舉，與 (l) 同一套，含條件樹各層的 `field`、`ref`、`op`；位置表的格數等於 `string_values` 對不含禁詞的 fixture 的結果數），以 fixture 規則檔的位元組與相符的雜湊經載入函式載入 → 拒絕，由掃描擋下的位置，拋出的例外可辨識為禁詞命中（`BannedPhraseRuleSetError`）；位置若因 model 本身的型別驗證無法放入禁詞，該格改為斷言載入失敗、而且不是禁詞命中；`field`、`ref` 位置以替身 `OUTLOOK_RULE_FIELDS` 納入含禁詞的名稱，使擋下它的是掃描而不是 (j) 的可評估子集；
```

**N137-5（建議同批）　L3282（FL-78 (l2)）**
- old：`而且拋出的例外可辨識為禁詞命中；`
- new：
```text
而且拋出的例外可辨識為禁詞命中（N-137：`app.forecast.definitions.BannedPhraseInDefinitionError`，是同模組 `PublishedVersionRejectedError` 的子類）；
```

**修訂紀錄段**：接在 L5787 之後，前置「空行、`---`、空行」，和 L5758 的前例相同。
```text
**B2 自決事項裁定與 N-137 補字批（後續追蹤清單 N-137；D-1 `app/dirdef/`、`app/forecast/definitions.py`、`basket.py` 三列、D-10 第 1 點、D-14 G-2、FL-26、FL-56、FL-78；方向：逐項標示，見各項）**
- 來源與套用範圍：
  - dev-lead 2026-10-25 `work/reviews/2026-10-25-B2實作交件-dev-lead.md`「與 TA 範圍說明的差異和我自己決定的事項」第 1～6 點、「已知限制」、「qa N-137 四點的處理」；qa-reviewer 2026-10-25 `work/reviews/2026-10-25-N128N131N132落檔審查-qa-reviewer.md`（N-137）。
  - tech-architect 2026-10-25 裁定：coordinator 轉存 `〔轉存檔名〕`。
  - CEO：否。風控：B2D-1 輕量確認，其餘知悉 `〔風控檔名〕`。quant：B2D-1（文字欄位規則、`name`）、B2D-3（新欄位）知悉。
  - 事先宣告不改字。
- 逐項（被取代的原文：判準同 v0.25 同步批段）：
  - B2D-1 兩個 logic 雜湊的範圍與定義物件的完整雜湊：方向：補定義（版本標籤、說明文字與 C-8 出處欄位不在 logic 範圍；`invalidation` 屬邏輯）；收緊（新增 `definition_sha256`，已登記版本的任何欄位不得原地修改）。CEO：否。被取代的原文（D-1 `app/dirdef/` 列）——
    > `PUBLISHED_DIRECTION_DEFINITIONS`、`PUBLISHED_RULESETS`（每版只登記 horizon 與雜湊，不含規則內容）
    其餘（D-10 第 1 點兩句、`definitions.py` 列、D-14 G-2、FL-26）都是句末接字，無被取代原文。
  - B2D-2 `DirectionDefinition` 的 construct／copy 守門與型別層檢查：方向：收緊。CEO：否。D-1 列句中接字，無被取代原文；FL-78 (h) 被取代的原文——
    > 規則集、規則與條件 model 的 `model_construct` 與帶 `update` 的 `model_copy` → `TypeError`
  - B2D-3 族群籃子成員層覆蓋門檻改為 dirdef 常數、`basket_log_returns` 簽章：方向：補定義（值不變：沿用 `SectorMomentumDefinition` v1 的 90%）；收緊（門檻隨 `definition_version` 固定、入 logic 雜湊）。CEO：否。被取代的原文——
    > `SPLIT_SUSPECT_ABS_RETURN` 與 D-14 的三個欄位）
    > `basket_log_returns(members, series, window)`
  - B2D-4 `app.dirdef` 的 import 範圍：方向：補定義（消除歧義，不變：允許套件內 import）。CEO：否。被取代的原文——
    > （都是既有依賴），不 import 任何 `app.*`；
    > (a) `app.dirdef` 不 import 任何 `app.*`，
  - B2D-5 FL-78 (j) 交集格的啟用時點：方向：收緊（閘門順序）。CEO：否。句末接字，無被取代原文。
  - N-137 字串值列舉函式具名、FL-78 (g) 單一定義清單、(h) 用語與 (l) 對齊、(l2) 例外具名：方向：補定義；收緊（測試）。CEO：否。被取代的原文——
    > 位於 `app/dirdef/`（名稱由 dev-lead 定）
    > (g) `app/` 內 `DirectionDefinition`、`OUTLOOK_RULE_FIELDS` 與兩個登記表各恰一個定義，都在 `app/dirdef/`（grep）；
    > 每個禁詞 × 規則集與規則的每一個字串欄位各一格，以 fixture 規則檔的位元組與相符的雜湊經載入函式載入 → 拒絕；
    > 而且拋出的例外可辨識為禁詞命中；
  - 本段。
- 照實並陳：
  - B2D-1：C-8 決策紀錄換檔或改字、而 `f2_variant` 不變時，不產生新 claim、驗證計數不重置，這正是 D-12 共同部分 (iv) 的用意；決策紀錄中無法以 dirdef 常數表達的條件，系統不會執行〔推論〕，要生效就必須另以常數表達。
  - B2D-3：同一個值存在兩處（`CoverageRules` 與 dirdef），一致性只在第一次登記那一批以測試釘住；族群方法日後改版時，已登記的 dirdef 不跟著改，要改就另發 dirdef 版本。
  - B2D-5：`OUTLOOK_RULE_FIELDS` 目前是空集合，所以交集必然為空；本段只把啟用時點寫成閘門。
- 待決事項與同批規則：
  - 本段與正文各項同一個 commit；修訂紀錄（本段）最後落檔。
  - 落檔後的閘門：B2 staged diff 依本段改完並經 qa 審查之前不 commit；B2D-1 風控確認不成立時，回 tech-architect 重議（完整雜湊 `definition_sha256` 保留）。
```

#### D. 對實作的約束（給 dev-lead；C-1～C-7 合併前必做，每條 qa 都能逐條檢查）

- **C-1** `definition.py`：`c8_decision_ref`、`c8_decision_sha256` 移出 logic 雜湊。排除集合建議改名，例如 `DEFINITION_NON_LOGIC_FIELDS`，因為已不全是文字欄。新增 `definition_sha256(definition)`，用同一個 `canonical_sha256` 對完整的 `model_dump(mode="json")` 計算，`app/` 內只定義一次。
- **C-2** `registry.py`：`PublishedDefinition` 新增 `definition_sha256` 欄，用同一個十六進位檢查。
- **C-3** `definitions.py::get_definition`：比對版本鍵、logic 雜湊、完整雜湊，最後掃描禁詞；任一步失敗都不寫入快取。
- **C-4** 測試：
  - 新增 B2D-1f 的各格。
  - 「改值會改雜湊」表改成：c8 兩欄 → logic 雜湊不變、完整雜湊改變；這張表要和排除集合連動。
  - FL-78 (g) 的單一定義清單照 N137-3 補齊。
- **C-5** `DirectionDefinition` 新增 `BASKET_MIN_MEMBER_WEIGHT`，範圍取 `(0, 1]`，和 `basket._check_threshold` 一致。名稱暫定。
- **C-6** `basket_log_returns` 簽章改為 `(members, series, window, *, coverage_unknown, definition)`，讀 `definition.BASKET_MIN_MEMBER_WEIGHT`，只 import `app.dirdef` 的型別。FL-56 照 B2D-3d 改寫。`basket_hold_ratio` 不動。
- **C-7** docstring 對齊：`app/dirdef/__init__.py` 的「no `app.*` import」改成「不 import 本套件以外的 `app.*`」；`basket.py` 中「90% 不是 dirdef 常數」的段落改寫。
- **C-8（建議，不阻擋）** 加第 7c 點的欄位型別絆線格。
- **不得動**：`band.py`；兩張登記表維持空的；`app/outlook/rules/` 不建立；不加 job、不掛 route。

## 驗證

- 讀過：
  - 交件報告全文、我的範圍說明全文；
  - ADR-0027：L1～12、L229～268（D-1）、L1615～1635（D-10）、L2331～2412（D-12）、L2443～2519（D-14、D-15）、L3100～3111（FL-30～37）、L3153、L3282～3311（FL-78、FL-79、FL-75、FL-56）、L5755～5787（檔尾）；
  - ADR-0025 L196～203；
  - 事先宣告 §1.2（L858～889）、§2.1 族群籃子（L1028～1041）、§2.4（L1089～1099），並 Grep 了 §4.1～§4.3 的區塊長度、§4.3 (d)(e)、§12 claim 表；
  - 程式：`app/dirdef/` 全部 7 個檔、`app/forecast/{definitions,claims}.py`、`app/outlook/{basket,volatility}.py` 全文，`app/sectors/definition.py` 的 `CoverageRules`（L86～103：`sector_coverage_threshold = 0.90`）；
  - 測試：`test_dirdef_rules.py` L100～259，並 Grep 了 `test_dirdef_definition.py`。
  - 追蹤清單 N-133～N-137。
- C 節所有 old 字串與錨點，都用 Grep `-o` 確認在現行 ADR-0027 中恰好出現 1 次。「（名稱由 dev-lead 定）」單獨出現 2 次，所以 N137-2 帶了前綴。新字中的 `string_values`、`definition_sha256`、`BASKET_MIN_MEMBER_WEIGHT`、`coverage_unknown`、`BannedPhraseRuleSetError`、`BannedPhraseInDefinitionError`、`B2D-` 目前在 ADR 內都是 0 次。落檔後的計數請 tech-writer 以 Grep `-o` 回報，qa 對照本稿逐字核對；我沒有逐一預算計數。
- 沒有執行測試或 Bash，沒有寫入任何檔案，沒有讀 `.env` 或 `*.db`。

## 下一步

1. **coordinator**：轉存本回報，填入修訂紀錄段的〔轉存檔名〕；把下方追蹤清單登記編號。
2. **風控**：B2D-1 做輕量確認（涉及 D-14 G-2、底線 5、底線 7）；B2D-3 和其餘各項知悉。
3. **quant**：B2D-1（文字欄位規則、`name`）、B2D-3（新欄位）知悉；承接 T-1、T-2。
4. **tech-writer**：照 C 節落檔。正文各項與修訂紀錄放同一個 commit，修訂紀錄最後落檔。
5. **dev-lead**：在 staged diff 上做 C-1～C-7，C-8 可選；然後交 qa。
6. **qa-reviewer**：依 D 節逐條審查，並補跑 Codex（#53）。合併條件是 ADR 已落檔，且 B2D-1 風控確認成立。

**全部需要 ADR 補字的事項（可直接交辦）**

| 編號 | 位置 | 對應裁定 | 方向 | 風控 |
|---|---|---|---|---|
| B2D-1a | D-10 第 1 點 L1618 | 第 1 點 | 補定義 | 輕量確認 |
| B2D-1b | D-10 第 1 點 L1619 | 第 2 點 | 補定義＋收緊 | 輕量確認 |
| B2D-1c | D-1 `app/dirdef/` 列 L235 | 第 4 點 | 補定義 | 同上 |
| B2D-1d | D-1 `definitions.py` 列 L236 | 第 4 點 | 收緊 | 同上 |
| B2D-1e | D-14 G-2 L2448 | 第 2 點 | 補定義 | 同上 |
| B2D-1f | FL-26 L3081 | 第 2、4 點 | 收緊（測試） | 同上 |
| B2D-2a | D-1 `app/dirdef/` 列 (4) L235 | 第 3 點 | 收緊 | 知悉 |
| B2D-2b | FL-78 (h) L3282 | 第 3 點 | 收緊（測試） | 知悉 |
| B2D-3a | D-1 `app/dirdef/` 列 L235 | 第 5 點 | 補定義／收緊 | 知悉 |
| B2D-3b、3c | D-1 `basket.py` 列 L260 | 第 5 點 | 補定義／收緊 | 知悉 |
| B2D-3d | FL-56 L3306 | 第 5 點 | 收緊（測試） | 知悉 |
| B2D-4a | D-1 `app/dirdef/` 列 L235 | 第 6 點 | 補定義（不變） | 知悉 |
| B2D-4b | FL-78 (a) L3282 | 第 6 點 | 補定義（不變） | 知悉 |
| B2D-5 | FL-78 (j) L3282 | 第 7a 點 | 收緊（閘門順序） | 知悉 |
| N137-1 | D-1 `app/dirdef/` 列 (3) L235 | 第 8 點 | 補定義 | 知悉 |
| N137-2 | D-1 `definitions.py` 列 L236 | 第 8 點 | 補定義 | 知悉 |
| N137-3 | FL-78 (g) L3282 | 第 8 點 | 收緊（測試） | 知悉 |
| N137-4 | FL-78 (h) L3282 | 第 8 點 | 收緊（測試） | 知悉 |
| N137-5 | FL-78 (l2) L3282 | N-137 第 2 點（建議同批） | 補定義 | 知悉 |
| 修訂紀錄段 | 檔尾 L5787 之後 | 全批 | — | — |

**新增後續追蹤（請 coordinator 編號）**
- **T-1**（第 7b 點）：B1 分子與 B4 籃子在成員缺 bar、或除權息覆蓋不明時的處理規則，由 quant 具名登記進事先宣告、送風控。期限是 G-3 凍結之前，且在 baselines 批實作 B1、B4 之前。`basket_hold_ratio` 的介面可能因此調整。
- **T-2**（第 2c 點）：凍結時確認 dirdef 的欄位名稱與完整欄位集合。包括：§4.1 N_eff 區塊長度 = h，和 §4.2、§4.3 的區塊 4 要拆成不同欄；`MIN_COMPLETENESS`、θ_h、N_MIN 等其餘常數；事先宣告 L864 要求的風控 R-1 偏離載明欄位（依 B2D-1b 歸為文字欄）；規則 `name` 是否列為字面鍵。負責：quant；期限：G-3 凍結前。
- **T-3**（審查中另外發現，tech-architect 負責，期限是規則集登記批之前）：
  - ADR-0025 D-2 第 3 點規定每個 horizon 只有一份規則檔（`h3.yaml`、`h5.yaml`），但事先宣告 §12 每個 h 有三個 `rules_version`（market、sector_main、symbol）。
  - FL-78 (k) 又要求「每一版都能載入」。同一個 horizon 一旦登記第二個 rules 版本（包括 PATCH），舊版就載入不了。
  - YAML 的 `version` 和登記鍵 `rules_version` 之間的對應關係也沒有任何檢查；定義物件那邊有版本鍵核對，規則集沒有。
- **T-4**（第 7c 點）：沿用 N-136，建議加 C-8 的絆線格，讓「出現這類欄位前」的期限可以機械化檢查。
- **T-5**（recorder／baselines 批前，需要查證）：事先宣告 §1.2 把族群母體與覆蓋規則釘在 `SectorMomentumDefinition` v1。S_T、S_{T−h} 的成員判定不得取「現行版」族群定義；要確認 ADR 目前有沒有對應字面，沒有就補。

相關檔案：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md
- /home/user/AICompany/work/reviews/2026-10-25-B2實作交件-dev-lead.md
- /home/user/AICompany/work/reviews/2026-10-25-N128N131N132補字與B2範圍-tech-architect.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
- /home/user/AICompany/apps/stock-desk/backend/app/dirdef/definition.py
- /home/user/AICompany/apps/stock-desk/backend/app/dirdef/registry.py
- /home/user/AICompany/apps/stock-desk/backend/app/dirdef/rules.py
- /home/user/AICompany/apps/stock-desk/backend/app/dirdef/__init__.py
- /home/user/AICompany/apps/stock-desk/backend/app/forecast/definitions.py
- /home/user/AICompany/apps/stock-desk/backend/app/outlook/basket.py
- /home/user/AICompany/apps/stock-desk/backend/app/sectors/definition.py
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
