# FL-42 與 N115-5 衝突改字（N115-9）

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# FL-42 與 N115-5 衝突的改字（N115-9），併 N113-1 送風控重審

## 1. 本次結論

改字擬好了，編為 **N115-9**：在 FL-42 第二項句末接字，不動 N115-5 本文。這次沒有寫檔、沒有跑指令。

**衝突出在哪裡**
- FL-42 第二項（現行 ADR L3072）規定 `app.api.*` 在 `app.forecast` 底下只能碰到 `views` 與型別模組。
- 但 D-7 第 8 點與 D-14 G-7 要求 POST 必須寫入。所以 ADR 內本來就互相矛盾，N115-5 只是把它寫明了。
- 這一項其實照字面根本做不到：`views` 本身要讀 `store.py`，任何碰到 `views` 的模組都會連帶碰到 `store.py`。

**改字做了五件事**
1. 改成「第一跳」判準：只看外部套件直接 import 了哪個 `app.forecast` 模組。
2. 型別模組明列為只有 `errors.py`，並寫明改寫後的 `definitions.py` 不是型別模組。這同時處理了你問的「`definitions.py` 不再是型別模組」那件事。
3. 開一個唯一例外：`app/api/outlook.py` 可以 import `app.forecast.on_demand` 的進入函式。
4. 這個例外的補償條件：回傳值只有 `forecast_id`；展望計算的結果不外流；回應只經 `views` 產生。
5. D-14 的閘門函式不得放在 `recorder.py`；`on_demand` 不可達排程作業的各個模組。

**方向與 CEO 層級**
- 方向是補定義（兩面）：放寬面是第 3 點的例外，收緊面是第 2、4、5 點。
- 第 3 點放寬的是 A-6 的守門測試，所以要送風控，和 N113-1 一起重審。
- CEO 層級：建議為「否」，最後以風控判定為準。理由是這只是調和 ADR 內既有的矛盾，沒有新增任何讓 label 對外的路徑。

**你要我確認的 `views.py`**
- 現行程式裡沒有 `views.py`。`app/forecast/` 底下只有 `__init__.py`、`errors.py`、`band.py`（Glob 確認），所以 `views.py` 也不可能 import `definitions.py`。
- ADR 也沒有任何一句要求 `views` import `definitions.py`。
- 不過照 D-1，`views` 要讀 `store.py`，而 `store.py` 的寫入驗證會經 `definitions.py` 取得定義〔推論〕。所以會有遞移可達，但在第一跳判準下不違規。

---

## 2. 各部門回報

### tech-architect

#### 一、方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A：FL-42 改為第一跳判準，加上單一例外與補償條件（採用）** | 改動最小；保留 A-74 的靜態 route 列舉；把照字面無法成立的遞移讀法改成可以檢查的讀法 | 放寬一條 A-6 的守門測試 | label 經 on-demand 外流：由第 4 點的 AST 與 FL-42 第一項的讀取點 AST 擋住 |
| B：由組裝端注入寫入函式，`api/outlook.py` 不 import `on_demand` | FL-42 字面可以成立 | 組裝端照樣碰得到同一批模組，保護並沒有變強；A-74「每個 on-demand route 都呼叫同一個閘門函式」無法再靜態檢查 | 只是形式上合規 |
| C：讓 `views` 兼做寫入 | 不必開例外 | 破壞「`views` 是唯一對外讀取點」的語意 | 讀取點開始累積寫入邏輯，日後被侵蝕 |

#### 二、改字

old 取自**現行 ADR**（L3072 的句尾）。「型別模組」在全檔只有這一處，所以 `str.count==1`。改法是句末接字，原句保留。

```text
old: 只可達 `views` 與型別模組（import graph）。
new: 只可達 `views` 與型別模組（import graph）。（N-115；N113-1 連動）判準與例外：(1) 以「第一跳」判定：上列套件直接 import 的 `app.forecast.*` 模組只能是 `views` 與型別模組；經 `views` 再往下的遞移可達（例如 `views` 讀 `store.py`）不在本項範圍，`label` 的讀取由本條第一項的 AST 與 D-11.4 第 5 點的單一閘門管住。(2) 型別模組只有 `app/forecast/errors.py`，增列須修訂本項。`app/forecast/definitions.py` 經 N113-1 改寫後是登記表的讀取點，不是型別模組；葉套件 `app.dirdef` 不在 `app.forecast` 底下，上列套件依 D-1 該列本來就不得 import。(3) 唯一例外：`app/api/outlook.py` 另可 import `app.forecast.on_demand` 的進入函式（D-1 `app/forecast/on_demand.py` 列）；`app/api/**` 的其他模組，以及 `app.plan.*`、`app.advice.*`、`app.alerts.*`，都不得 import 它。(4) 例外的補償條件（AST）：進入函式的回傳值只有 `forecast_id`，閘門不成立時拋 `WriteGateClosedError`，不回傳任何計算結果；`on_demand.py` 中，展望計算器的輸出只作為 `store.py` on-demand 寫入函式的引數出現，不取屬性、不寫入 log、不回傳；POST 的回應（含 `OnDemandGateClosedView`）只經 `views` 的函式產生，`app/api/outlook.py` 不 import `display.py`。(5) D-14 的閘門函式不放在 `recorder.py`（所在模組由 dev-lead 定，名稱寫入測試）；`app.forecast.on_demand` 不可達 `recorder.py`、`settlement.py`、`audit.py`、`correction.py`、`validation.py` 與 `scoring.py`（import graph）。
```

#### 三、`app.api.outlook` 經 `on_demand.py` 碰得到哪些模組、會不會碰到 A-6

程式還沒寫，下面的清單依 D-1 各列、N115-5、N113-1 推得〔推論〕。

**直接 import（第一跳）**
- `on_demand.py`
- `views`
- `errors.py`

**經 `on_demand.py` 遞移可達**
- `store.py`
- D-14 閘門函式所在的模組
- `app.outlook.computer`（只有 Protocol 與型別）
- 經 `store.py` 寫入驗證：`band.py`、`canonical.py`、`definitions.py`、`errors.py`
- 經 `definitions.py`：葉套件 `app.dirdef`、`app.advice.loader`、`app.advice.context`、`app.advice.limits`、`app.api.kelly_wording`
  - 後面四個有程式碼為證：`loader.py:44` import `context`，`context.py:29` import `limits`，`limits.py:54` import `kelly_wording`。
- **未列全**：G-4 要讀的 `verified_on` 從哪個模組來，我沒查到〔未查證〕，所以閘門函式所在模組能碰到哪些模組，沒辦法列完整。

**和 label 不變性（A-6，FL-43／LG-22）的關係：結構上不受影響，但前提是第 4 點成立**
- 進入函式只回傳 `forecast_id`，讀不到 label。
- 計算出來的 label 只在記憶體裡傳給 store 寫入，不會用來分支、不寫 log、不回傳。
- 回應一律經 `views` 產生，所以 D-11.4 的閘門、`display_state`、遮蔽照常套用。
- FL-42 第一項（`forecast_record.label` 只有 `views`、`display`、`scoring`、`validation` 四個模組能讀）不變。`on_demand`、`store`、閘門模組都不在這四個裡面。
- 「on-demand 紀錄存不存在都不影響當日展望」（A-25，L1712）也不受影響。

**要不要送風控：要**
第 3 點放寬的是 A-6 的守門測試，而 A-6 ② 先前經過風控核對（L1712）。重審請集中看兩件事：第 3 點的例外範圍，以及第 4 點的補償條件夠不夠。

#### 四、修訂紀錄的連動字句（以第一批草稿的紀錄段為底稿）

1. **段首標題**：在「FL-74、」前面插入「FL-42、」，其餘不變。
2. **「逐項」**：在 N115-8 那一項之後新增：
```text
  - N115-9 FL-42 的判準、型別模組與 on-demand 例外：方向：補定義（兩面）。不變：「第一跳」判準只把無法照字面成立的遞移讀法（`views` 本來就讀 `store.py`）改成可檢查的讀法；收緊：型別模組明列為 `errors.py`、`app/forecast/definitions.py` 排除在外，例外附補償條件（回傳只有 `forecast_id`、計算輸出不外流、回應只經 `views`、閘門函式不在 `recorder.py`）；放寬：`app/api/outlook.py` 可以 import `app.forecast.on_demand`，調和 D-7 第 8 點、D-14 G-7（POST 必須寫入）與 FL-42 字面的既有矛盾。CEO：否（建議；放寬面依風控判定）。句末接字，無被取代原文。
```
3. **「照實並陳」**：
   - N113-1 那一項的句子要改：
```text
old: 改寫後的 `app/forecast/definitions.py` 不再是 FL-42 所稱的型別模組〔推論〕。
new: 改寫後的 `app/forecast/definitions.py` 不是 FL-42 所稱的型別模組（N115-9 明列）。
```
   - 新增一項：
```text
  - N115-9：不採「由組裝端注入 on-demand 寫入函式，讓 `app/api/outlook.py` 不 import `app.forecast.on_demand`」：FL-42 字面可以成立，但組裝端照樣可達同一批模組，保護不變，A-74 的 route 列舉也變得無法靜態檢查。不採「由 `views` 兼做寫入」：會破壞 `views` 是唯一對外讀取點的語意。代價：`app.api.outlook` 經 `on_demand.py` 遞移可達 `store.py`、`definitions.py`、`band.py`、`canonical.py`、`errors.py`、閘門函式所在模組、葉套件、`app.outlook.computer`，以及經 `definitions.py` 的 `app.advice.loader`、`app.advice.context`、`app.advice.limits`、`app.api.kelly_wording`〔推論，依 D-1 各列與 N115-5，程式尚未存在〕；label 不外流靠 FL-42 第一項的讀取點 AST 與第二項 (4)，不是靠 import graph。G-4 的 `verified_on` 讀自何處未查證，閘門函式所在模組的可達範圍因此未列全。`app.advice.loader`、`context`、`limits` 目前不 import `app.forecast.*`，所以沒有循環；日後若有 `app.advice.*` 模組 import `views`，要先確認不會形成循環〔推論〕。
```
4. **「待決事項與同批規則」**：在第一個子項句末接上：
```text
N115-9 與 N115-5、N113-1 必須同一個 commit。
```
5. **「來源」那一行的〔轉存檔名〕**：填 `work/reviews/2026-10-24-N113-1修訂稿-tech-architect.md`。

#### 五、預期計數（更新前次第五節的表）

只有兩列有變動，其他列照前次的表：

| 字串 | 第一批後（前次） | 第一批後（含 N115-9） | 增加的來源 |
|---|---|---|---|
| `N-115` | 23 | **24** | FL-42 新句裡的「（N-115；」 |
| `app\.dirdef` | 6 | **7** | FL-42 新句裡的「葉套件 `app.dirdef`」 |

- `N-113` 仍是 9。新字句裡只寫「N113-1」，沒有出現「N-113」。
- `app/dirdef`、`BANNED_PHRASES`、`FL-78`、`OUTLOOK_RULE_FIELDS` 都不變。
- FL-42 的 old（`只可達 `views` 與型別模組（import graph）。`）落檔後仍只有 1 處，因為它是新句的開頭。

#### 六、對實作的約束（qa 可以逐條檢查）

1. `app/api/outlook.py` 對 `app.forecast` 的直接 import，只能是 `views`、`errors` 與 `on_demand` 的進入函式，而且不 import `display.py`。
2. `on_demand` 進入函式的回傳型別只有 `forecast_id`。
3. 展望計算器的輸出只作為 store 寫入函式的引數出現。
4. 閘門函式不在 `recorder.py`。`on_demand` 不可達 `recorder`、`settlement`、`audit`、`correction`、`validation`、`scoring`。
5. `app.plan.*`、`app.advice.*`、`app.alerts.*`、`app.api.*` 不直接 import `definitions.py`。

### risk-compliance-officer（和 N113-1 一起重審）

- 重審範圍：本段第二節（FL-42 新句），加上第四節的紀錄字句。
- 重點：第 (3) 點的放寬，以及第 (4) 點的補償條件，是否足以維持 A-6 ②。
- 另外請判定 CEO 是否需要明示同意。

### CEO

- 建議只知會，最後以風控判定為準。

---

## 3. 驗證

- **讀過的地方**：
  - ADR-0027：L1074-1085（D-7 第 8 點）、L1690-1719（D-11.4 第 4～6 點、A-25）、L2384-2409（D-14 G-7）、L3058-3073（FL-41～FL-42）
  - Grep 查過：`views` 相關各句、`型別模組`（全檔只有 L3072）、`A-6`、`閘門函式`、`app/api/outlook.py`
- **程式碼**：
  - `apps/stock-desk/backend/app/forecast/` 只有 `__init__.py`、`errors.py`、`band.py`（Glob），沒有 `views.py` 和 `definitions.py`。
  - 已讀過的 `band.py`、`errors.py` 都只 import 標準庫。
- **沒有查到的**：
  - D-14 閘門函式所在的模組，ADR 沒有指定（照抄進 (5) 交給 dev-lead）。
  - G-4 的 `verified_on` 從哪個模組讀，未查證。
- **沒有做的事**：沒有讀 `.env`，沒有碰 `*.db`，沒有寫檔，沒有跑指令。
- CEO 不需要親自驗證任何事項。

## 4. 下一步

1. coordinator 轉存本回報，把 N115-9 併進第一批的送審包，和 N113-1 修訂稿一起送風控重審。
2. 風控通過後，照方案甲由 tech-writer 整批落檔。落檔後用 `-o` 照第五節（含本次更新的兩列）重算，再送 qa-reviewer，並補跑 Codex。
3. 交給 dev-lead：決定 D-14 閘門函式放哪個模組（不得是 `recorder.py`），並查證 G-4 的 `verified_on` 從哪裡讀，以補全可達清單。
