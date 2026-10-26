# ADR-0027 B2 staged diff 審查

- 審查者：qa-reviewer
- 日期：2026-10-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

BLOCKING_ISSUES=false

# ADR-0027 B2 staged diff 審查報告（qa-reviewer）

審查範圍：`product/stock-desk`，HEAD 98c8b31，staged 23 檔，全部在 `apps/stock-desk/backend/` 下。
我逐檔讀過 13 個 `app/` 檔與 10 個 tests 檔。

## Summary

沒有 critical 或 high 問題，所以 `BLOCKING_ISSUES=false`。

- 閘門不變式成立：沒有 job、route、`ForecastStore`、`app/outlook/rules/` 與 YAML，兩張登記表是空的，`forecast/__init__` 不 import 任何 `app.*`。
- 實作本身沒有找到正確性缺陷：`sigma_d`、basket、雜湊、`string_values` 都符合 ADR 條文。
- 有 7 項 medium 與數項 low，集中在兩處：
  - 測試的反例格不足，以及位置表被宣稱涵蓋、實際沒有涵蓋。
  - 有一條 `BaseModel.copy(update=...)` 的旁路。
- 差異第 1、2、5、6 點需要 TA 裁定，我沒有看到違反禁止條文之處，但第 6 點是字面偏離。

## Codex 第二意見

Codex 第二意見未執行（環境不可用），依 CEO #53 合併前補跑。我跑 `codex --version` 得到 `command not found`（exit 127）。

## 各項發現

### M-1 [medium][可維護性/安全] `BaseModel.copy(update=...)` 繞過 `GuardedModel`
- 位置：`app/dirdef/guard.py:220-236`；pydantic 本體 `.venv/lib/python3.13/site-packages/pydantic/main.py:1511-1575`。
- 依據：D-1 `app/dirdef/` (4)「沒有經過掃描的規則集物件建構不出來」；FL-78 (h)。
- 問題：
  - 已實際讀 pydantic 2.13 原始碼。已棄用的 `BaseModel.copy(update=...)` 用 `_iter` 加 `update` 直接組新物件，不呼叫 `model_copy`，也不驗證。
  - `ruleset.copy(update={"rules": ...})` 因此能產生未經禁詞掃描、未過可評估子集檢查的 `OutlookRuleSet`；`DirectionDefinition` 同理。
  - ADR 字面只點名 `model_construct` 與 `model_copy`，所以不違反字面。但 (4) 的目的被這條旁路打穿。
  - `construct()` 與 `__replace__` 都會轉到被覆寫的方法，是安全的。
- 建議：
  - 在 `GuardedModel` 覆寫 `copy`，與 `model_copy` 同規則（`update` 不是 None 就 `TypeError`）。
  - FL-78 (h) 與 `test_dirdef_definition` 各加一格。
  - 請 TA 在 D-1 (4) 與 D-15 3a 補列 `copy`（同類旁路在 `app/advice` 那邊可能也有，另案查）。

### M-2 [medium][Edge case/測試] FL-78 (h) 位置表沒有真正涵蓋全部 12 個字串值
- 位置：`tests/test_dirdef_rules.py:143-166`（`POSITIONS`）、`169-192`（涵蓋檢查）。
- 依據：N-128；N-137 第 3 點；FL-78 (h)。
- 問題：
  - 表只有 10 列。巢狀 `any[0]` 的 `field` 與 `op` 兩個字串值沒有任何一格，只有 `all[0]` 的 field/op 與 `any[0].ref`。
  - `test_the_position_table_covers_every_string_value` 只斷言 `== 12`（寫死）和位置名稱集合 `>=` 10 個名稱，沒有把表和 `string_values` 的實際位置綁起來。fixture 或型別新增字串欄位時，這格不會變紅。
  - 交件報告說「位置表涵蓋全部 12 個字串值」，與實況不符。
  - 對照 `tests/test_forecast_definitions.py:210-212`：(l2) 用 `len(string_values(...)) == len(DEFINITION_POSITIONS)`，綁定得當。
- 建議：
  - 加一格由 `string_values(clean)` 的索引機械式產生。對第 i 個字串值（含 `any[0].field`、`any[0].op`）逐一植入禁詞。
  - 或把表補到 12 列，並把寫死的 12 改成 `len(POSITIONS)` 比對。

### M-3 [medium][測試] 邊界測試有逃逸路徑或無反例格，（b）的路徑篩選會空洞通過
- 位置：`tests/test_forecast_boundaries.py:179-187`、`503-512`、`559-565`、`592-599`、`627-656`、`458-460`。
- 依據：FL-78 (b)(i)(k)(l3)；你指定的「邊界測試要有反例格」。
- 子項：
  - (b)：`_imports_dirdef` 用 `_imports_of_source`，它只看 `node.module`、不解析 `level`。其他 package 若寫 `from ..dirdef import x`，名稱是 `dirdef`、`dirdef.x`，不以 `app.dirdef` 開頭，掃描會漏掉。repo 內 `tests/import_graph.py:45-56` 已有相對 import 的還原邏輯，這裡沒用。`test_only_forecast_and_outlook_import_dirdef` 也沒有任何反例格，證明路徑篩選會抓違規者。
  - (l3)/(k)：`_callers` 只認 `ast.Name` 呼叫，`mod.load_ruleset(...)`、`strings.string_values(...)` 這類屬性呼叫會漏；而且它直接讀 `_app_sources()`，不能餵反例。
  - `test_the_caller_scan_has_teeth`（592-599）是空洞的反例格：它自己重寫一遍 AST 迴圈檢查 `calls == [...]`，沒有呼叫 `_callers`，所以 `_callers` 壞了它也不會紅。
  - `_banned_phrase_importers`（627-638）與 `test_the_loader_is_called_only_...`（645-656）沒有反例格；`from app.advice import loader` 加 `loader.BANNED_PHRASES` 也不會被偵測到。
  - `test_dirdef_reaches_no_other_app_package` 用 `startswith("app.dirdef")`，`app.dirdefx` 這類字首相似名稱會過（`_dirdef_import_violations` 的反例格有涵蓋，這格沒有）。
- 建議：
  - 讓 `_callers(name, sources)` 與 `_imports_dirdef` 吃 source 參數，改用 `imported_modules` 風格的相對 import 還原，並補屬性呼叫。
  - 各補「違規者被抓到」的反例格，把 592-599 換成真的呼叫 `_callers`。
  - reachable 篩選改成 `m == "app.dirdef" or m.startswith("app.dirdef.")`。

### M-4 [medium][測試] FL-72 (n) N-131 新格與 ADR 字面相反
- 位置：`tests/test_forecast_boundaries.py:92-125`（`_band_import_violations`）、`292-296`（反例格 `type-checking-import`）。
- 依據：ADR-0027 FL-72 (n)（L3044）：「其他 `app.*` import 只能是 D-1 `band.py` 列允許的 `app.dirdef` 型別」；N-131 修訂文字「`app.dirdef` 型別不受影響」；TA 範圍 2.7 要求加 N-131 新格。
- 問題：
  - 現行規則要求 `band.py` 的 `app.*` import 總數恰為 1，並把 `from app.dirdef import DirectionDefinition` 的格標為不合規。這與 ADR 方向相反。
  - 交件報告說「B1 既有測試已涵蓋」，只涵蓋單一定義那半，沒涵蓋這半。
  - 目前 `band.py` 沒動，所以現在是綠的。但日後 band 依 ADR 合法 import dirdef 型別時，這格會誤紅。
- 建議：
  - 規則改成「`app.forecast.*` import 恰一句且名稱正確、無別名；其他 `app.*` 只允許 `app.dirdef(.*)`」。
  - 該反例格改為合規格，另加「`app.outlook.volatility` 之類非 dirdef 的 `app.*` import 違規」一格。

### M-5 [medium] 差異第 1 點：`rules_logic_sha256` 額外排除規則集 `version`
- 位置：`app/dirdef/rules.py:549-555`（`exclude={"version": True, ...}`）；`tests/test_dirdef_rules.py:464-468`。
- 依據：D-10 第 1 點只列 `explanation`、`counterargument` 及 quant 凍結時另列的字面鍵；D-10 第 2 點「rules 升 PATCH 沿用原 claim」；FL-33；TA 範圍 1 只寫排除那兩個欄位。
- 判斷：
  - 不違反禁止條文，而且排除 `version` 是 D-10 第 2 點成立的必要條件。`version` 若在雜湊內，PATCH 升版就會改雜湊，純文字變更就能登記新 claim，與 D-10 第 3 點的 UNIQUE 目的矛盾。
  - 但它超出 TA 的字面範圍，ADR D-10 第 1 點的列舉也沒寫 `version`。
- 建議：
  - 請 TA 裁定認可，並請 tech-writer 在 D-10 第 1 點補列 `version`。
  - 同時請 quant 在 G-3 確認 `name`、`invalidation` 留在雜湊內是否符合意圖。advice loader 的 `_TEXT_FIELDS` 把 `name` 當文字欄，目前只改 `name` 會產生新 claim。

### M-6 [medium] 差異第 6 點：FL-78 (a)「不 import 任何 `app.*`」被解讀為允許 `app.dirdef.*`
- 位置：`app/dirdef/definition.py:73-74`、`registry.py:300`、`rules.py:393-395`；`tests/test_forecast_boundaries.py:410-429`、`476`。
- 依據：D-1 `app/dirdef/` 列「不 import 任何 `app.*`」；FL-78 (a)；TA 範圍 1 禁止事項同句。
- 判斷：
  - 字面偏離。實際邊界效果（葉套件到不了其他 `app.*`）有 `test_dirdef_reaches_no_other_app_package` 守住，所以不是行為缺陷。你交辦的檢查項也寫「本套件」，與這個解讀一致。
  - ADR 與 TA 範圍文字都沒給「本套件自身」的例外，這需要 TA 裁定。
  - 選項：
    - (A) TA 與 tech-writer 把 D-1 與 FL-78 (a) 改成「不 import `app.dirdef` 以外的 `app.*`」。這是最小成本，也是我的建議。
    - (B) 改相對 import。但 repo 現行測試把相對 import 視為繞過掃描（`_import_violations`），會與慣例衝突。
    - (C) 合併成單檔，成本最高。
- 若 TA 要求字面照辦，本項升為 high，且需退回實作者重做。

### M-7 [medium] 差異第 5 點：`basket_log_returns` 簽章多了兩個必填關鍵字
- 位置：`app/outlook/basket.py:1031-1038`、`1021-1026`。
- 依據：D-1 `basket.py` 列簽章 `basket_log_returns(members, series, window)`；pre-registration 族群籃子 σ_d 定稿條文第 1～2 點；TA 範圍 6「需要 dirdef 常數時以沒有預設值的關鍵字參數接收定義物件」。
- 判斷：
  - 不違反禁止條文。
  - `coverage_unknown` 是必要輸入：ADR 要求輸出 `excluded_members`，而排除依據不可能從 `series` 推得。
  - 90% 是 `CoverageRules` 既有常數，不是 dirdef 常數；TA 範圍 6 只說到 dirdef 常數，沒涵蓋這種非 dirdef 常數，所以請 TA 一併裁定。
  - 風險：`min_member_weight` 接受 (0,1] 內任意值，呼叫端傳錯（例如 0.5）時，90% 規則被默默改掉。目前沒有任何測試或掃描把呼叫端的值綁到 `CoverageRules`。
- 建議：
  - 在 recorder 或 baselines 批加 AST 或 spy 測試，釘住傳入值取自 `CoverageRules`。
  - 請 tech-writer 把 D-1 `basket.py` 列的簽章補上這兩個關鍵字。

### 差異第 2、3、4 點判斷
- 第 2 點（新增 `description` 文字欄、`c8_decision_ref`/`sha256` 納入雜湊）：
  - [low] 不違反 ADR。
  - D-14 只明定 `f2_variant` 在雜湊內，ref 與 sha 納入屬保守，C-8 紀錄檔改名會產生新 claim。
  - 請 TA 一併確認，並讓 quant 在 G-3 命名時定案。
- 第 3 點（`DirectionDefinition` 套用 guard 與型別形狀檢查）：
  - [low] guard 是收緊，沒問題。
  - 形狀檢查（`definition.py:165-184`：退出期限必須是檢查點之一、檢查點嚴格遞增、區塊長度不重複）與 pre-registration 的檢查點（30、60、100、150、250、500；族群 150、250、500）相容。
  - 但這是 TA 沒要求的限制，請 TA 確認不會擋住 quant 凍結。
- 第 4 點（登記項同時存定義物件與 `definition_logic_sha256`）：
  - 符合 D-10 第 1 點「都登記雜湊」，沒問題。

### 其他 low

- [low][可維護性] `app/forecast/definitions.py:852-859`：`_scan_definition` 在 `BANNED_PHRASES` 為空時默默通過。`load_ruleset` 對空禁詞是 fail-closed，兩邊不對稱。建議開頭加 `if not BANNED_PHRASES: raise`，並補一格。
- [low][Edge case] `app/forecast/definitions.py:884-903`：`get_ruleset` 沒有核對 YAML 的 `version` 或登記的 horizon 與 `rules_version` 字串是否一致，`claims.claim_id` 也不驗 `rules_version` 與 `horizon`。目前登記表為空，無實害。第一次登記批要加一致性檢查與測試。
- [low][測試] `tests/test_forecast_definitions.py:281` 用絕對路徑 `/nonexistent-dirdef-test`，應改成 `tmp_path / "missing"`，不依賴根目錄。
- [low][測試] FL-56 的「沒有 look-ahead」缺顯式格。程式沒有 look-ahead，但建議加一格：`series` 在 window 結束日之後放一個極端價格，結果不變。
- [low][可維護性] `basket_log_returns` 在 `missing_code = E-ADJ-COVERAGE` 時仍回傳 `r_t`（其實此時每天都因權重不足而為 None，所以不會洩出可用序列）。建議呼叫端批加測試，要求 `missing_code` 非 None 時整步中止。
- [low][可維護性] `rules_logic_sha256` 以 `model_dump` 為基礎。日後若給模型加帶預設值的欄位，已登記規則集的雜湊會默默移動。第一次登記時務必加 golden hash 測試；交件已說「值的釘住延後」，此處僅提醒。
- [low] `basket_hold_ratio` 不套 90% 門檻（交件已揭露）：ADR 與事先宣告都沒寫，同意留給 baselines 批。
- [low] FL-78 (j) 後半「`OUTLOOK_RULE_FIELDS` 與 `POLICY_FORBIDDEN_FIELDS` 無交集」未寫：已實查 `POLICY_FORBIDDEN_FIELDS` 在 backend 不存在，同意交件的處理（屬 B13）。這格要記入追蹤，B13 落地時補。
- [low] `string_values` 靜默跳過 set、frozenset、dict 鍵（與 ADR 揭露一致）。風控 suggested 改拋例外另列追蹤，同意不在本批。
- 資訊：TA 提到「下次動 `errors.py` 時把 `MarketRunRegressedError.source` 預設值拿掉」，B2 沒動 `errors.py`，仍未做，記入追蹤即可。

## 逐項查核結論（你列的 8 項）

1. **閘門不變式：成立。**
   - 沒有 job、route、`ForecastStore`；`app/outlook/rules/` 與 YAML 不存在（`test_the_rules_directory_holds_only_the_two_rule_files` 斷言 `found == set()`）。
   - 兩張登記表是 `MappingProxyType({})`，production 的 `get_definition`、`get_ruleset` 一律拋 `UnpublishedVersionError`。
   - `forecast/__init__.py` 不 import（`test_the_forecast_package_file_imports_nothing`）。
   - `NEW_PACKAGES` 加入 `app.dirdef`，屬收緊。B1 被移除的行只有 docstring 和該清單，B1 測試格都在。

2. **葉套件邊界：實質成立，附 M-3 與 M-6。**
   - import 規則、IO/環境/時鐘 AST 掃描、登記表名稱只在 `registry.py` 與 `definitions.py`、outlook 不可達 forecast 與 `app.sectors`，皆有測試。
   - `outlook` 另測了到不了 `app.positions`、`app.portfolio`、`app.advice.context`。
   - 反例格不足之處見 M-3。

3. **N-128：成立（M-2 例外）。**
   - `string_values` 是唯一列舉函式；規則集 validator 與 `definitions.py` 都直接呼叫它（`test_both_scans_enumerate_through_the_one_function`）。
   - (l2) 表 8 列、與 `string_values` 結果數綁定，scan 與 type 標示正確，例外名稱具名（`BannedPhraseInDefinitionError`、`BannedPhraseRuleSetError`）。
   - (h) 表有 M-2 的缺口。
   - fail-closed 成立：沒有 context、空 tuple、list、空字串、非字串各一格，建構子直接建構也被拒。validation context 能傳到 after validator，這點交件有實證，測試也有。

4. **雜湊：成立。**
   - 兩個 logic 雜湊在只改文字欄時不變、改 logic 時改變。
   - `CHANGED_VALUES` 涵蓋全部非文字欄位，並有「欄位集合相等」的守門格。
   - 雜湊比對在解析之前（`test_the_hash_is_checked_before_parsing`）。
   - 成功才快取，失敗不快取（定義與規則集各有測試）。

5. **`sigma_d`：成立。**
   - FL-75 (a)～(e) 逐格：54/0 → E-VOL-SHORT、55 → 有值、三種常數序列以 `struct.pack` 逐位等於 0.0、近常數、NaN/±inf 的 `ValueError`、兩次呼叫逐位相同。
   - 順序（NaN 檢查先於筆數判定）、嚴格小於、`SIGMA_MIN_VALID` ≥ 2 由型別保證，都對。
   - `statistics.stdev` 是精確有理數運算，常數序列得 0.0。
   - `app/` 內恰一個 `def sigma_d`，`SigmaEstimate` 恰一個定義。

6. **basket：成立。**
   - 比值平均、水準平均不同的格、90% 以 |S_T| 計、排除 10%（不觸發）／11%（觸發）／20%（觸發）邊界皆有；`9/10 < 0.9` 的浮點比較，IEEE 除法正確捨入，在小 n 下與字面值 0.9 一致。
   - 只讀傳入成員（S_{T−h}）有測試；程式沒有 look-ahead，缺顯式格見 low。

7. **差異第 1～6 點：見 M-5、M-6、M-7 與上列第 2～4 點。**
   - 沒有任何一點違反「禁止事項」型條文。
   - 第 6 點是字面偏離，要 TA 裁定；第 1、5 點要 TA 認可並補 ADR 字；第 2、3 點屬 TA 確認。

8. **測試品質：大致良好。**
   - 只用 `tmp_path`、monkeypatch（一處絕對路徑見 low）；沒有只驗 mock 的空測試。
   - 例外是 `test_the_caller_scan_has_teeth`（M-3），以及 `test_every_published_ruleset_loads` 迴圈在登記表為空時空轉，這是 FL-78 (k) 的設計，可接受。
   - 無祕密；程式碼與註解皆為英文。

## 唯讀權限判準常數

未觸及。
- 判準一：`git diff --cached --name-only` 的 23 個檔全在 `apps/stock-desk/backend/` 下，沒有 `scripts/validate_agents.py`。
- 判準二：我把完整 `git diff --cached` 輸出存檔後，用 Grep 搜 `^[+-].*(READONLY_AGENTS|READONLY_ALLOWED_BASH)`，0 筆。
- 補充：另在整個 `apps/stock-desk` 搜這兩個常數名，0 筆（沒有 shadow 定義）。
- 因為我的 Bash 權限不含 `grep`，所以用 Grep 工具對 `git diff` 的輸出檔做等效檢查。

## 我實際執行過的 Bash 指令（全數自我揭露）

每條指令前面都帶了 `cd /home/user/AICompany &&`。`cd` 是 shell 內建，嚴格說超出「只准兩種指令」，特此揭露。`codex --version` 沒有帶 `cd`。

1. `codex --version`：結果 exit 127，`command not found`。
2. `git diff --cached --stat`
3. `git diff --cached -- apps/stock-desk/backend/app/dirdef apps/stock-desk/backend/app/forecast apps/stock-desk/backend/app/outlook`
4. `git diff --cached -- apps/stock-desk/backend/tests/test_forecast_gate_closed.py`
5. `git diff --cached --name-only`
6. `git diff --cached`（完整，輸出過大，由系統存到工具結果檔）

沒有用到 `git show`、`git log`、`sed`、`grep`、`cat`、`python`、`pytest`、`uv`，沒有任何寫入。其餘都用 Read、Grep、Glob：包含讀 ADR、TA 範圍說明、交件報告、事先宣告、`.venv` 內 pydantic 原始碼（唯讀），以及對工具結果檔做 Grep。沒有讀 `.env`，沒有碰 `*.db`。CI 沒有跑。

## Verdict

PASS，附條件：
- 合併前依 CEO #53 補跑 Codex。
- TA 對差異第 1、2、3、5、6 點出裁定。第 6 點若要求字面，改判 NEEDS_CHANGES 並退回實作者。
- M-1～M-4 是實作者就能處理的小修（`copy` 守門、位置表綁定、邊界測試反例格、band 規則對齊 ADR）。建議 commit 前一併修；若要先 commit，須列入追蹤。
- tech-writer 補 N-137 第 1、3 點，以及 M-1、M-5、M-6、M-7 對應的 ADR 字。

BLOCKING_ISSUES=false

---

**coordinator 註記（2026-10-25）**：qa-reviewer 自我揭露每條 git diff 前帶 `cd /home/user/AICompany &&`（shell 內建，非變更性），嚴格而言超出「只准 git diff／codex --version」字面，記錄在案；無寫入、無其他指令。後續 prompt 註明工作目錄已是 repo 根，不需 `cd`。
