# N113-1 修訂稿（風控否決後重擬）

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N113-1 修訂稿（風控否決後重擬）

## 1. 本次結論

N113-1 改好了，可以送風控重審。這次沒有寫檔，也沒有跑任何指令。

**否決理由 (a)：禁詞掃描**
- 掃描放在葉套件 `app/dirdef/` 的規則集 model 驗證器裡，每次載入規則集都會跑。
- 禁詞清單不另存副本，唯一來源是 `app/advice/loader.py::BANNED_PHRASES`。由 `app/forecast/definitions.py` import 這份清單，以沒有預設值的關鍵字參數傳給 `app/dirdef/` 的載入函式。
- 為什麼要繞這一層：葉套件規定不 import 任何 `app.*`；`app.outlook.*` 依 ADR-0027 D-15 第 5 點不能可達 `app.advice.context`，而 `loader.py:44` 一載入就會 import 它。兩邊都拿不到禁詞，`app.forecast.*` 則沒有這項限制。
- fail-closed 做法：
  - 沒傳禁詞，或傳了空清單，驗證器一律拒絕，所以沒掃過的規則集物件建不出來。
  - `model_construct` 和帶 `update` 的 `model_copy` 一律拋 `TypeError`，比照 D-15 第 3 點 3a。
  - claim 登記只能從 `definitions.py` 取得規則集。所以沒通過掃描的規則集不能載入、不能登記，也就不能凍結。
  - CI 另外要求 `PUBLISHED_RULESETS` 的每一版都能載入（新 FL-78 (k)）。
- 沒有副本，所以不需要比照 `tests/test_advice_wording.py` 做集合相等測試，改用 FL-78 (i) 檢查副本有沒有出現。這點已寫進照實並陳。

**否決理由 (b)：規則檔路徑**
- 照 coordinator 的意思，沿用 ADR-0025 D-2 第 3 點：`app/outlook/rules/h3.yaml`、`h5.yaml`。
- 改成葉套件不做檔案 IO：由 `definitions.py` 讀檔，再把位元組傳進去。這樣就不需要把規則檔搬進葉套件，ADR-0025 不用修訂。

**風控轉交的同結構問題（可評估子集）**
- 在 `app/dirdef/` 新增 `OUTLOOK_RULE_FIELDS`（名稱暫定），當作展望規則可用欄位的唯一來源，由同一個驗證器檢查。
- 不沿用 `ADVICE_RULE_FIELDS`：它是建議卡的欄位，而且 outlook 依 D-15 第 5 點碰不到它所在的 `app.advice.context`。
- 這就是 ADR-0021 K-3 的同一條不變式，ADR-0025 L81 也寫了「outlook 規則套用同一個不變式」。
- 另加一個測試：`OUTLOOK_RULE_FIELDS` 和 `POLICY_FORBIDDEN_FIELDS` 不能有交集。

**方向與 CEO 層級**
- N113-1 是補定義。不變的部分：常數的值、雜湊範圍、規則檔路徑。收緊的部分：掃描與子集寫明放在哪裡、禁詞只有一個來源、fail-closed。
- 沒有修訂 ADR-0025，CEO 層級為「否」。
- N113-2～N113-4 不用改。N113-5 的 FL-78 要整段換成新版（見下文）。

**我自己草稿裡的一處衝突，要先處理**
FL-42（ADR-0027 L3072）規定 `app.api.*` 在 `app.forecast` 底下只能碰到 `views` 和型別模組。但我起草、風控判為「不涉風控」的 N115-5，寫了 `app/api/outlook.py` 會呼叫 `app/forecast/on_demand.py`，兩者衝突。這個矛盾其實原本就隱含在 on-demand 寫入裡（L259），N115-5 只是把它寫明了。如果走方案乙先落 N-115，建議先處理這一點，或改由 qa 判定。

---

## 2. 各部門回報

### tech-architect

#### 一、方案比較

**禁詞掃描放哪裡**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A：`definitions.py` import 禁詞，以參數傳給葉套件的驗證器（採用）** | 只有一個來源、沒有副本；葉套件仍然不依賴任何 `app.*`；沒傳禁詞就建不出規則集 | `app.forecast.definitions` 因此可達 `app.advice.context`、`app.advice.limits`、`app.api.kelly_wording`；靠 pydantic 的 validation context，我沒實測 | 呼叫端傳錯清單：由 FL-78 (h) 的表格測試和 (i) 的 AST 檢查擋 |
| B：葉套件另存一份禁詞，加集合相等測試 | 掃描完全在型別內部 | 兩份清單；AV-14 守門範圍變大 | 測試沒跑時兩份會漂移 |
| C：載入和掃描放在 `app.outlook` | 離規則檔近 | D-15 第 5 點讓它碰不到 `app.advice.context`，要開例外 | 成本欄位的邊界被侵蝕 |
| D：把禁詞搬到新的葉模組，`loader.py` 改成轉出 | 結構最乾淨 | 要改既有的合規紅線程式和 ADR-0004 L99 指定的位置，會碰到 AV-14 | 需要風控裁示編號，不在本次範圍 |

**規則檔路徑**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **沿用 ADR-0025 D-2 第 3 點（採用）** | 不修訂已核可的 ADR，CEO 層級為「否」 | forecast 要去讀 outlook 套件底下的資料檔 | 無 |
| 改放 `app/dirdef/rules/` | 葉套件自己帶著規則檔 | 要修訂 ADR-0025：照該檔第 11 行的慣例，由 ADR-0027 增列一項 M-12 提案，須 CEO 核可，核可前以 ADR-0025 為準 | 要 CEO 介入，卻沒有實際好處 |

#### 二、N113-1 修訂稿（D-1 L235，整行換成兩行）

old 已用 Grep 確認，在現行 ADR 恰好 1 處：
```text
old: | `app/forecast/definitions.py` | frozen 的 `DirectionDefinition`、`PUBLISHED_DIRECTION_DEFINITIONS`、`PUBLISHED_RULESETS` |
new:
| `app/dirdef/`（N-113；葉套件，不在 `app/forecast/`、`app/outlook/` 底下） | frozen 的 `DirectionDefinition`（該版 dirdef 的全部常數，例如各 h 的 K、`EPS`、`SIGMA_MIN_VALID`、`SIGMA_FLOOR`、`BASKET_EXCLUSION_REASON_ORDER`、`SPLIT_SUSPECT_ABS_RETURN` 與 D-14 的三個欄位）、展望規則集的 frozen 型別、展望規則可用欄位的集合 `OUTLOOK_RULE_FIELDS`（名稱暫定）、`PUBLISHED_DIRECTION_DEFINITIONS`、`PUBLISHED_RULESETS`（每版只登記 horizon 與雜湊，不含規則內容），以及 `definition_logic_sha256`、`rules_logic_sha256` 與規則集載入函式（含 D-10 第 1 點的雜湊檢查）的唯一定義。只 import 標準庫、`pydantic` 與 `yaml`（都是既有依賴），不 import 任何 `app.*`；不讀 DB、時鐘與環境變數，也不做檔案 IO，規則檔由 `app/forecast/definitions.py` 讀取後以位元組傳入載入函式（AST）。`app.forecast.*` 與 `app.outlook.*` 可以 import 本套件，其他 `app.*` 不得 import（增列須修訂本列）。兩個登記表在 `app/` 內只由 `app/forecast/definitions.py` 讀取；`app.outlook.*` 只 import 型別與純函式，所需的定義物件與規則集由呼叫端依該紀錄的 `definition_version`、`rules_version` 取得後，以沒有預設值的關鍵字參數傳入（AST）。本 ADR 他處所稱「dirdef 常數」「該列 `definition_version` 所登記 dirdef 的常數」，都指本套件中該版定義物件的屬性。**規則集的載入守門**（ADR-0025 D-2 第 3 點「schema 比照 `app/advice/loader.py`」各項的落點；規則集物件只能經載入函式建構）：(1) 規則集、規則與條件的 model 都是 `extra="forbid"`，`version` 為 semver；以 `yaml.safe_load` 解析。(2) 可評估子集（ADR-0021 K-3 的同一個不變式）：條件樹（含巢狀）的每個 `field`、`ref` 都必須在 `OUTLOOK_RULE_FIELDS` 內。這個集合是展望規則可用欄位的唯一來源；不沿用 `app.advice.context` 的 `ADVICE_RULE_FIELDS`，因為那是建議卡的欄位，而且 `app.outlook.*` 依 D-15 第 5 點不可達 `app.advice.context`。(3) 禁詞掃描：禁詞的唯一來源是 `app/advice/loader.py::BANNED_PHRASES`，本套件不另存副本。載入函式以沒有預設值的關鍵字參數 `banned_phrases` 接收禁詞，經 validation context 交給規則集 model 的 after validator；validator 掃描規則集與每條規則的全部字串欄位，命中即拒絕。欄位依 model 的欄位定義列舉、不手列名稱，所以涵蓋 D-10 第 1 點去掉的全部文字欄位。(4) fail-closed：validation context 沒有禁詞，或禁詞為空，validator 一律拒絕，所以沒有經過掃描的規則集物件建構不出來；`model_construct` 一律拋 `TypeError`，`model_copy` 在 `update` 不是 None 時拋 `TypeError`（比照 D-15 第 3 點 3a）。載入函式依序做位元組的雜湊比對、YAML 解析與 model 驗證，任一步失敗就拋例外，不回傳部分結果 |
| `app/forecast/definitions.py`（N-113 改寫） | `app/` 內唯一讀取 `PUBLISHED_DIRECTION_DEFINITIONS`、`PUBLISHED_RULESETS` 的模組：依 `definition_version`、`rules_version` 回傳已登記的定義物件與規則集，查無時拋例外，不回預設值。`claims.py`、`recorder.py`、`on_demand.py`、D-14 的閘門函式、重放執行函式與 `store.py` 的寫入驗證都經這裡取得（AST）。型別與登記表本身定義在 `app/dirdef/`。**規則檔與禁詞掃描**：規則檔的位置照 ADR-0025 D-2 第 3 點，為 `app/outlook/rules/h3.yaml` 與 `app/outlook/rules/h5.yaml`，依該版登記的 horizon 取檔；路徑以 `app/outlook/` 套件目錄為基準解析，取規則集的函式沒有路徑參數，本模組不讀環境變數。本模組讀取規則檔的位元組，以該版登記的 `rules_sha256` 與自 `app.advice.loader` import 的 `BANNED_PHRASES`，呼叫 `app/dirdef/` 的規則集載入函式；`app/` 內只有本模組呼叫該載入函式，`app/forecast/**` 與 `app/outlook/**` 之中也只有本模組 import `BANNED_PHRASES`（AST）。回傳定義物件之前，本模組以同一份 `BANNED_PHRASES` 掃描它的全部字串欄位，命中就拋例外。掃描與雜湊比對在每次回傳規則集或定義之前完成（成功的結果可以在行程內快取，失敗不快取）；沒有通過時不回傳該版，拋例外。`PUBLISHED_RULESETS` 的每一版都必須能經本模組載入（FL-78 (k)），D-10 第 3 點的 claim 登記也只經本模組取得規則集與定義，所以沒有通過掃描的規則集不能登記 claim，也就不能凍結（D-14 G-3） |
```

#### 三、連動改字

- **N113-2、N113-3、N113-4**：不用改。old 分別在 L239、L252、L254，Grep `-o` 各 1 處。
- **N113-5（L3200 之後插入）**：錨點 FL-55 那一行不變，恰好 1 處。FL-78 換成下面整段；FL-79 照舊。
```text
- **FL-78**（N-113；D-1 `app/dirdef/` 與 `app/forecast/definitions.py` 兩列）：import graph 與 AST，沿用 `tests/import_graph.py`。(a) `app.dirdef` 不 import 任何 `app.*`，只 import 標準庫、`pydantic`、`yaml`，也不做檔案 IO（AST：不出現 `open`、`read_text`、`read_bytes` 與 `importlib.resources`）；(b) import `app.dirdef` 的模組只在 `app/forecast/**`、`app/outlook/**` 內；(c) `PUBLISHED_DIRECTION_DEFINITIONS`、`PUBLISHED_RULESETS` 在 `app/` 內，除了定義處之外只出現在 `app/forecast/definitions.py`；(d) `app.outlook.*` 仍不可達 `app.forecast.*`；(e) `sigma_d` 的 `definition` 是沒有預設值的關鍵字參數，`app/` 內每一個呼叫點都以關鍵字傳入，值不是字面值；(f) 兩個 `definition_version` 的 `SIGMA_FLOOR` 不同的 fixture，`sigma_d()` 各依傳入的定義判定退化；(g) `app/` 內 `DirectionDefinition`、`OUTLOOK_RULE_FIELDS` 與兩個登記表各恰一個定義，都在 `app/dirdef/`（grep）；(h) 禁詞掃描（表格驅動，禁詞逐一取自 `app.advice.loader.BANNED_PHRASES`，測試內不另列）：每個禁詞 × 規則集與規則的每一個字串欄位各一格，以 fixture 規則檔的位元組與相符的雜湊經載入函式載入 → 拒絕；同一格直接呼叫規則集 model 的 `model_validate`（不帶 validation context）→ 拒絕；禁詞傳入空 tuple → 拒絕；規則集、規則與條件 model 的 `model_construct` 與帶 `update` 的 `model_copy` → `TypeError`，`model_copy()` 可以正常使用；(i) 單一來源：`app/forecast/**`、`app/outlook/**` 之中，import `BANNED_PHRASES` 的只有 `app/forecast/definitions.py`，而且來自 `app.advice.loader`；它呼叫載入函式時，禁詞以關鍵字 `banned_phrases` 傳入，值就是這個 import 的名稱；`app/dirdef/**`、`app/outlook/**` 的 Python 原始碼不出現含任一禁詞的字串常數（AST，防副本）；(j) 可評估子集：條件樹（含巢狀的 all、any）中有一個 `field` 或 `ref` 不在 `OUTLOOK_RULE_FIELDS` → 拒絕；`OUTLOOK_RULE_FIELDS` 與 `app.advice.context.POLICY_FORBIDDEN_FIELDS` 沒有交集（測試內 import 兩者）；(k) 載入路徑：`PUBLISHED_RULESETS` 的每一版都能經 `app/forecast/definitions.py` 載入；fixture 規則檔改動一個位元組、雜湊照舊 → 拒絕；`app/` 內規則集載入函式的呼叫點只有 `app/forecast/definitions.py`；`app/outlook/rules/` 之下的 YAML 只有 `h3.yaml`、`h5.yaml`（尚未建立時為空）；(l) fixture 定義物件的任一字串欄位含禁詞 → `app/forecast/definitions.py` 拋例外、不回傳；(m) 以含禁詞的 fixture 規則集執行 D-10 第 3 點的登記 CLI → 非零結束碼，`forecast_claim_registry` 沒有新列（替換讀檔位元組的接縫由 dev-lead 定，名稱寫入測試）。
```
- N-115、N-117 各項不受影響，不用改字。

#### 四、修訂紀錄裡 N-113 相關字句（只列差異）

以草稿 L226-276 為底稿，風控改字照該檔另外套用。

1. **「來源與套用範圍」**：在「tech-architect 2026-10-24 起草：…第一批（缺日稽核冪等為第二批，另段）。」之後插入一行：
```text
  - N113-1 修訂稿（風控否決後重擬）：tech-architect 2026-10-24，coordinator 轉存〔轉存檔名〕。
```
2. **「風控」那一行**：照風控給的方案甲定稿取代，〔重審檔名〕〔重審結論〕由 coordinator 填。我不改。
3. **「逐項」N113-1**：
```text
old:   - N113-1 D-1 `app/dirdef/` 新列與 `app/forecast/definitions.py` 列改寫：方向：補定義（不變：常數的值與雜湊範圍不變，只改所在模組與讀取點；收緊：登記表的讀取點只剩一處、`app.dirdef` 不 import 任何 `app.*`）。CEO：否。被取代的原文——
new:   - N113-1 D-1 `app/dirdef/` 新列與 `app/forecast/definitions.py` 列改寫：方向：補定義（不變：常數的值與雜湊範圍不變，只改所在模組與讀取點；規則檔路徑沿用 ADR-0025 D-2 第 3 點，不修訂 ADR-0025；收緊：登記表的讀取點只剩一處，`app.dirdef` 不 import 任何 `app.*`、不做檔案 IO；ADR-0025 D-2 第 3 點的 `BANNED_PHRASES` 掃描與可評估子集寫明落點，禁詞單一來源，沒有經過掃描的規則集不能載入、不能凍結；定義物件的字串欄位另加掃描）。CEO：否。被取代的原文——
```
   引文（L235 原文）照舊。N113-2～N113-5 這幾項不改。
4. **「照實並陳」N113-1**：原句保留，在句末「本批把這件事明寫成參數。」之後接上：
```text
（N113-1 修訂，風控 2026-10-24 退回後補）禁詞以參數注入、不另存副本：葉套件不 import 任何 `app.*`；`app.outlook.*` 依 D-15 第 5 點不可達 `app.advice.context`，而 `app/advice/loader.py` 在模組層級 import 它〔事實：`app/advice/loader.py:44`〕，所以兩處都引用不到禁詞來源，改由 `app/forecast/definitions.py` import `BANNED_PHRASES` 後傳入。沒有副本，所以不需要比照 `tests/test_advice_wording.py` 的集合相等測試，改由 FL-78 (i) 擋住副本出現。代價：`app.forecast.definitions` 因此可達 `app.advice.context`、`app.advice.limits` 與 `app.api.kelly_wording`〔事實：`app/advice/context.py:29`、`app/advice/limits.py:54`〕；本 ADR 沒有條文禁止 `app.forecast.*` 可達這些模組〔推論〕。改寫後的 `app/forecast/definitions.py` 不再是 FL-42 所稱的型別模組〔推論〕。validation context 能否把禁詞傳到規則集 model 的 after validator，實作時以 FL-78 (h) 實測〔未查證〕；改用其他機制時，「沒有提供禁詞就建構不出規則集物件」這一點不變。規則檔路徑沿用 ADR-0025 D-2 第 3 點，本批不修訂 ADR-0025。每個 horizon 只有一份規則檔：檔案改版之後，舊版 `rules_version` 的雜湊比對不會通過，舊版規則集無法再載入（fail-closed；FLT-6 的純文字改版也一樣）；舊版的保存與重新載入方式，本批不定義〔推論〕。`OUTLOOK_RULE_FIELDS` 由 quant 依 G-3 凍結規則集時一併登記；`app/outlook/features.py` 正式實作的那一批，要以測試釘住特徵鍵的集合等於它。在那之前，集合裡的名稱只是宣告，但 `app/` 內沒有 `OutlookComputer` 的實作（D-1 `app/outlook/computer.py` 列），不會產生紀錄。定義物件字串欄位的掃描是額外的收緊，ADR-0025 只要求掃描規則文字。
```
5. **「待決事項與同批規則」第一個子項**：在「全批可以只用一個 commit。」之後接上：
```text
N113-1～N113-5 不得早於 N115-3 落檔（FL-78 (m) 引用 N115-3 的登記 CLI）。
```

#### 五、第一批落檔後預期計數

基準是「現行 ADR＋第一批全部改字（含風控改字，方案甲）」。數法：ADR-0027 單檔，用 Grep `-o` 數出現次數，區分大小寫。小寫的 `banned_phrases` 不算進 `BANNED_PHRASES`。

| 字串 | 落檔前（實測） | 第一批後 | 前一版預期 | 怎麼分布 |
|---|---|---|---|---|
| `N-113` | 0 | 9 | 9 | 本文 6（兩個新列各 1、N113-2～4 各 1、FL-78 1）；紀錄 3 |
| `app/dirdef` | 0 | **7** | 5 | 新 dirdef 列 1、新 definitions 列 2、FL-78 3、紀錄 N113-1 項 1 |
| `app\.dirdef` | 0 | 6 | 6 | N113-2～4 各 1、FL-78 (a)(b) 2、紀錄 1 |
| `BANNED_PHRASES` | 0 | **9** | — | 新 dirdef 列 1、新 definitions 列 3、FL-78 2、紀錄 N113-1 項 1、照實並陳 1、風控那一行 1 |
| `OUTLOOK_RULE_FIELDS` | 0 | **6** | — | 新 dirdef 列 2、FL-78 3、照實並陳 1 |
| `app/outlook/rules` | 0 | **3** | — | 新 definitions 列 2、FL-78 (k) 1 |
| `FL-78` | 0 | **7** | 3 | FL-78 本條 1、新 definitions 列 1、紀錄標題 1、紀錄 N113-5 項 1、照實並陳 2、待決 1 |
| `N-115` | 0 | 23 | 23 | 不變 |
| `N-117` | 0 | 12 | 12 | 不變 |
| `BEGIN IMMEDIATE` | 4 | 10 | 10 | 不變 |
| `FL-79` | 0 | 4 | 4 | 不變 |
| `exception_class_name` | 0 | 4 | 4 | 不變 |

- `ADR-0025`：這次新增的字樣共 +9（新 dirdef 列 1、新 definitions 列 1、紀錄 N113-1 項 3、照實並陳 3、風控那一行 1）。總數請 tech-writer 在落檔前後各用 `-o` 實測再比對，我這次只用 count 模式看過，那個數字可能是行數。
- 被取代的原文（L235）落檔後只剩 1 處，在紀錄的引文裡。FL-55 錨點仍是 1 處。

#### 六、對實作的約束（qa 可以逐條檢查）

1. `app/dirdef/**` 不 import 任何 `app.*`，不做檔案 IO，不出現任何禁詞字面。
2. 規則集物件只能經 `app/dirdef/` 的載入函式建構。驗證器拿不到禁詞，或禁詞為空時，一律拒絕；`model_construct` 和帶 `update` 的 `model_copy` 一律拋 `TypeError`。
3. 載入函式在 `app/` 內只有 `app/forecast/definitions.py` 一個呼叫點。傳入的禁詞就是從 `app.advice.loader` import 的 `BANNED_PHRASES`，以關鍵字傳入。
4. 規則檔只有 `app/outlook/rules/h3.yaml`、`h5.yaml`。取規則集的函式沒有路徑參數，也不讀環境變數。
5. 可評估子集只看 `OUTLOOK_RULE_FIELDS`，而且它和 `POLICY_FORBIDDEN_FIELDS` 不能有交集。
6. `PUBLISHED_RULESETS` 的每一版在 CI 都能載入。含禁詞的規則集，登記 CLI 必須失敗、不留任何列。
7. 不准為了方便讓 `app.outlook.*` 去 import `app.advice.loader`：會違反 D-15 第 5 點，我否決這種做法。

### risk-compliance-officer（待重審）

- 只看本段第二到第四節：N113-1 兩列、FL-78 新版、紀錄差異。
- 重點：禁詞注入加上「沒提供就建構失敗」，是否符合 (a) 的「唯一來源、fail-closed」；不留副本、改用 FL-78 (i) 代替集合相等測試，是否可以接受。

### CEO

- 知會即可。沒有修訂 ADR-0025，N113-1 不需要 CEO 明示同意。

### qa-reviewer、coordinator（附帶發現）

- **FL-42（L3072）和 N115-5 衝突**：N115-5 的 `on_demand.py` 列寫「只由 `app/api/outlook.py` 呼叫」，這會讓 `app.api.outlook` 可達 `views` 和型別模組以外的模組。這不在 N-113 範圍內，但方案乙一旦先落 N-115 就會碰到。建議在 N-115 落檔前定案，可以由我另擬一項改字。FL-42 來自 A-6，涉及標籤不變性，要不要送風控請 coordinator 判斷。
- **建議新增追蹤項目**：
  1. 舊版 `rules_version` 規則集的保存與重新載入（照實並陳已列出）。
  2. 風控交代的「前瞻 claim 登記齊全的機器檢查」。

---

## 3. 驗證

- **讀過的檔案**：
  - 起草稿全文
  - 風控確認檔全文
  - ADR-0025 L1-488：重點是 D-2 第 3 點（L201）、L81、AV-2、AV-3
  - ADR-0004 的 `BANNED_PHRASES` 相關行（L52、L99、L100、L153）
  - `apps/stock-desk/backend/app/advice/loader.py` 全文：禁詞在 L50，掃描在 L161，L44 import `app.advice.context`
  - `context.py:29` import `limits`；`limits.py:54` import `app.api.kelly_wording`；`app/api/__init__.py` 沒有 import
  - `tests/test_advice_wording.py`：L67 有集合相等測試
  - `tests/import_graph.py`
  - ADR-0027 L222-260、L1540-1571、L2418-2452、L3058-3073
- **用 Grep 實測**：
  - N113-1 的 old（L235）恰好 1 處。N113-2～4 的 old（L239、L252、L254）和 FL-55 錨點（L3200）各 1 處。
  - `N-113`、`app/dirdef`、`app\.dirdef`、`BANNED_PHRASES`、`OUTLOOK_RULE_FIELDS`、`app/outlook/rules`、`FL-78`、`FL-79`、`N-115`、`N-117` 在現行 ADR 都是 0。
  - D-15 第 5 點（L2448）、FL-41c（L3067）、FL-42（L3072）、FLT-6（L3293）的原文都確認過。
- **沒有做的事**：
  - pydantic 的 validation context 能不能傳到 after validator，沒實測（標了〔未查證〕）。
  - 沒有確認 `views.py` 是否 import `definitions.py`。
  - 「第一批後」的數字是照落字稿逐項加總，不是實測。
  - 沒有讀 `.env`，沒有碰 `*.db`，沒有寫檔，沒有跑指令。
- CEO 不需要親自驗證任何事項。

## 4. 下一步

1. coordinator 轉存本回報，並把檔名填進紀錄的〔轉存檔名〕。然後只把第二到第四節送風控重審。
2. 風控重審通過後，照方案甲由 tech-writer 整批落檔：第一批原稿，加上風控改字，加上本修訂稿。落檔後用 `-o` 照第五節的表重算，再送 qa-reviewer，並補跑 Codex。
3. 如果改走方案乙，請告訴我，我再把紀錄裡的 N-113 部分拆出來（標題、來源、逐項、照實並陳、待決)。
4. FL-42 和 N115-5 的衝突，請 coordinator 決定要我擬改字，還是交 qa 判定。最晚在 N-115 落檔前處理。
5. 追蹤清單新增兩項：舊版規則集的保存與重新載入；前瞻 claim 登記齊全的機器檢查。
