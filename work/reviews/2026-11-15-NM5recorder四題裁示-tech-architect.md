# NM-5 recorder 四題裁示與 ADR-0030 補充三

- 審查者：tech-architect
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
四題全部裁示完畢，不需要 CEO 裁決。第 1、2、4 題接受 dev-lead 的做法，並另加檢查條件。第 3 題我判定**違反 K-2**，要改程式：在本批再補 1 個 commit，qa 要一併審過，本批才能結案。四題都以 ADR-0030 補充三寫下來，全文在文末，可直接 append。

## 各部門回報（tech-architect）
**1. 跨 commit 觸發條件：接受，寫入補充三第 1 點。**
- 理由：照字面只比「前一次執行」，`gate_closed` 本身就會成為下一次的比對基準，等於靠失敗一次就能繞過核對。D-5 第 6 點要守的是「新紀錄的語意，經核對與既有紀錄相同」，所以該拿來比的是最後一次通過核對的執行環境。兩個條件取 OR 只會多重算，不會漏。三種 outcome 都在核對之後才會產生，列為「通過」是對的。
- qa 怎麼檢查：
  - 情境 A ok → B gate_closed → B 第三次，仍記 gate_closed。
  - A ok → B gate_closed → 改回 A，會重算而且通過。
  - 帳內還沒有任何通過的執行時，視為「不同」。
  - `error` 與沒有 end 列的執行，都不能當作比對基準。

**2. `LOADED` 在 import 時取一次：接受，寫入補充三第 2 點。**
- 理由：同一次執行裡，記下的 digest 必須描述實際在跑的程式。每次執行重讀磁碟，會讓舊程式掛上新 digest，D-5 第 3 點的前提就破了。
- 反方向的風險有兩個，都由補充三第 2 點處理：
  - (a) digest 涵蓋範圍內如果有函式內的延遲 import，`git pull` 之後才載入的模組，會是新程式配舊 digest。
  - (b) `code_commit` 如果每次執行才取，會與 digest 不一致。
- 殘留風險：import 讀檔到計算 digest 之間的極短窗口。知悉，不處理。另外，`git pull`、`uv sync` 之後必須重啟排程程序，要寫進 devops-sre 的 runbook。
- qa 怎麼檢查：
  - 用 AST 掃 `app/forecast`、`app/outlook`、`app/dirdef`、`session_calendar.py`：函式內沒有 `import`，沒有 `importlib`／`__import__`。
  - `code_commit` 與 `LOADED` 在同一時點取值。
  - 有測試證明：磁碟改了、程序沒重啟時，記下的仍是舊 digest。

**3. K-2 遞移可達：違反。**
- 理由：補充二已定 K-2 依可達性判定。ADR-0027 N113-1 寫「沒有條文禁止」是在 ADR-0030 之前，已被 K-2 收緊。這條路徑我已讀檔確認：`loader.py:44` → `context.py:29` → `limits.py:54` → `app.api.kelly_wording`。`app/api/__init__.py` 只有 docstring，所以實害很低，但規則不能因為無害就開例外。
- 修法：新增葉模組 `app/advice/banned_phrases.py`，不 import 任何模組，作為禁詞的唯一定義。`loader.py` 再匯出同一個物件，`definitions.py` 改從葉模組 import。
- 為什麼不用其他兩種做法：
  - 放進 `app.dirdef`：會讓 advice 反過來依賴凍結中的套件，否決。
  - 新開頂層 `app/compliance`：要改 K-2 字面，牽動太大，否決。
- 雜湊與字面的影響：
  - `rules_sha256`、`rules_logic_sha256`、`definition_sha256` 不變，h3／h5 四個釘住值也不變。禁詞的值與順序不變。
  - ADR-0004、ADR-0022、ADR-0025 所寫的 `loader.BANNED_PHRASES` 仍指同一個物件，字面不受影響。
  - 只有 `code_digest` 會變。目前帳內沒有任何紀錄，正式表也還沒建（CG-3），所以對帳無影響。
- qa 怎麼檢查：
  - 從 `app.forecast`、`app.outlook` 出發的可達集合，與 `app.api*` 沒有交集。
  - 可達的 advice 模組恰好是 `{app.advice, app.advice.banned_phrases}`。
  - `loader.BANNED_PHRASES is banned_phrases.BANNED_PHRASES`。
  - FL-78 (i) 的「無副本」檢查改指向新位置。
  - dev-lead 原本釘住「可經這條路徑到達」的測試要改成上面的禁止測試。
  - 全套測試要綠。任何已釘住的雜湊有變，就是停止點。

**4. 兩個小規格：接受，寫入補充三第 4、5 點，各加一條限制。**
- `candidate_t` 為 null：補充二第 2 點 (a) 的規則優先。有 (a) bar 時，`candidate_t` 填其中最大的 S；只有在沒有任何定案 bar、也沒有 (a) bar 時才填 null。這種情形會計入 F-2，資料中斷看得見。
- `source_status` 照實記錄：PIT 的保證來自逐根判定定案與 store 時鐘，不靠來源標記。大盤來源依 ADR-0005 恆為 backup，設拒收規則就永遠記不了。限制是它不得作為任何分支條件。
- qa 怎麼檢查：
  - 有「只有 (a) bar、沒有定案 bar」的測試，`candidate_t` 等於最大的 S。
  - 同一組 bars 分別配上 4 種 `DataStatus`，T、`label`、`band_def`、`baseline_predictions_json`、`missing_json` 都逐位相同。
  - 用 AST 確認 recorder 與 `app/outlook/**` 沒有以 `source_status` 作為分支條件。

## 驗證
- 我沒有執行程式。f52bff6 不在本機，我讀的是本機工作樹的 `app/advice/{__init__,loader,context,limits}.py`、`app/api/{__init__,kelly_wording}.py`、`app/forecast/definitions.py`。
- 另外讀了 ADR-0030 全文的相關段落，以及 ADR-0027 N113-1。
- 沒有讀 `.env`，也沒有碰任何 `.db`。

## 下一步
1. tech-writer：把下面的補充三 append 到 `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`，並在檔頭加一行：「- 補充紀錄：2026-11-15 append 補充三（跨 commit 比對基準、執行環境取值時點、K-2 禁詞來源、無定案 bar 與 source_status；tech-architect 裁示，收緊與釐清，不改使用者面字面與已登記雜湊，CEO 可推翻；來源 `work/reviews/2026-11-15-NM5第三批recorder交件-dev-lead.md`）。」
2. dev-lead：在 `feat/nm5-forecast-storage` 補一個 `refactor: 禁詞移至無依賴葉模組（K-2）` commit，並補齊第 1、2、4 題的測試缺口。
3. qa-reviewer：把這次的增量併入第三批審查，依上面各題的「qa 怎麼檢查」逐條勾選。
4. devops-sre：runbook 加上「`git pull`／`uv sync` 後重啟排程程序」。

---
## 補充三：跨 commit 比對基準、執行環境取值時點、K-2 禁詞來源、無定案 bar 與 source_status（2026-11-15）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-NM5第三批recorder交件-dev-lead.md` 下一步第 1～4 點（已實證：`app/advice/loader.py:44` → `app/advice/context.py:29` → `app/advice/limits.py:54` → `app.api.kelly_wording`）。
- 性質：收緊 D-5 第 6 點與 K-2；釐清 D-2 第 1～2 點與補充二第 2 點。補充本文，不改本文；不改任何產品行為、使用者面字面、規則檔與定義物件的雜湊。取代 ADR-0027 N113-1「代價」段所述的可達狀態。CEO 可推翻。

1. **比對基準**：D-5 第 6 點的「前一次執行」，讀為以下兩者：(i) run_id 小於本次的最近一次執行；(ii) 最後一次通過執行，即 outcome ∈ {`ok`, `no_new_session`, `inputs_not_ready`} 的執行。本次的 `code_digest` 或 `runtime_json` 與 (i)、(ii) 任一不同，就執行 D-5 第 6 點。沒有通過執行時，視為不同。`gate_closed`、`error` 與沒有 end 列的執行，都不是通過執行。
2. **取值時點**：`code_digest`、`runtime_json`、`code_commit` 在 recorder 模組 import 時取值一次，同一程序內的各次執行都沿用這組值。D-2 第 1 點 `code_digest` 涵蓋範圍內的原始檔，不得在函式內 import，也不得使用 `importlib` 或 `__import__`。更換程式或依賴之後，須重啟排程程序才會生效；重啟前寫入的紀錄出自舊程式，記錄的也是舊值，出處一致。殘留風險（知悉，不處理）：import 讀檔與取值之間的極短窗口。
3. **K-2 禁詞來源**：K-2 依可達性判定，`app.forecast.*`、`app.outlook.*` 不得可達 `app.api` 及其子模組。`BANNED_PHRASES` 的唯一定義移到 `app/advice/banned_phrases.py`，該模組不 import 任何模組。`app/advice/loader.py` 以 `from app.advice.banned_phrases import BANNED_PHRASES as BANNED_PHRASES` 再匯出，所以 ADR-0004、ADR-0022、ADR-0025 所稱的 `loader.BANNED_PHRASES` 仍指同一個物件。`app/forecast/definitions.py` 改由 `app.advice.banned_phrases` import。禁詞的值與順序不變；`app/advice/__init__.py` 不含 import。從 `app.forecast`、`app.outlook` 可達的 `app.advice` 模組，恰好是 `app.advice` 與 `app.advice.banned_phrases`。
4. **沒有定案 bar**：補充二第 2 點 (a) 先適用。處理之後，沒有任何定案 bar，也沒有屬 (a) 的 bar 時（含取數端沒有回傳任何 bar），記 `inputs_not_ready`，`candidate_t` 為 null，不寫紀錄，並計入 F-2 的 `inputs_not_ready` 日數。
5. **`source_status`**：照實記錄於 `forecast_input_series`，不設拒收規則。PIT 與定案的保證來自 D-3 第 2 點的逐根判定與 store 時鐘。`source_status` 不得作為 recorder 或 `app/outlook/**` 的分支條件，也不影響 T、`label`、`band_def`、`baseline_predictions_json`、`missing_json`。ADR-0005 下大盤來源恆為 backup，所以不得以「非 backup」或「非 fresh」作為拒收條件；要設拒收規則，須另修本 ADR。

- **S-12a（逐條可檢查）**：
  - 依序執行 A ok → B gate_closed → B，第三次仍記 `gate_closed`；之後改回 A，會重算並通過；沒有通過執行時會重算（測試）。
  - 第 2 點所列範圍內，函式內沒有 import，也沒有 `importlib`／`__import__`（AST）；程序未重啟時，磁碟變更不改變記錄的 `code_digest`（測試）。
  - 可達集合與 `app.api*` 沒有交集，可達的 advice 模組恰好如第 3 點（import graph）；`loader.BANNED_PHRASES is banned_phrases.BANNED_PHRASES`；h3、h5 的 `rules_sha256`、`rules_logic_sha256` 與 `definition_sha256` 不變（測試）。
  - 只有 (a) bar 時，`candidate_t` 等於最大的 S；沒有任何 bar 時，`candidate_t` 為 null（測試）。
  - 同一組 bars 分別配上 4 種 `DataStatus`，第 5 點所列欄位都逐位相同（測試）。
