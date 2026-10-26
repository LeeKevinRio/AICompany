# ADR-0027 B2 修正批與 ADR 補字複審

- 審查者：qa-reviewer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

BLOCKING_ISSUES=false

# ADR-0027 B2 修正批與 ADR 補字複審（qa-reviewer，2026-10-26）

審查範圍：HEAD 98c8b31，staged 23 檔（全在 `apps/stock-desk/backend/`），加上未 stage 的 ADR-0027 diff。我逐檔讀過 `app/dirdef/` 的 definition、guard、hashing、registry、rules、strings、`__init__`，以及 `forecast/definitions.py`、`outlook/basket.py`、`forecast/claims.py`、`outlook/volatility.py` 和兩個 `__init__` 的 diff。測試讀了 `test_forecast_boundaries.py`、`test_dirdef_definition.py`、`test_dirdef_rules.py`、`test_forecast_definitions.py`、`test_outlook_basket.py`、`dirdef_helpers.py`，以及 `test_dirdef_strings.py` 的絆線段。`test_forecast_claims.py`、`test_outlook_volatility.py` 這輪沒有變動，我沒有重讀。ADR 逐字對過三份來源。CI 我沒跑，也不能跑。

## Summary

沒有 critical 或 high。

- **程式面：**
  - TA 的 C-1～C-8、C-5′、C-7′、C-9、C-10，我的 M-1～M-4 與三項 low，風控的 R-1、R-2、S-c，全部落實。
  - 程式與 ADR 字面一致。閘門不變式成立。
- **ADR 補字：**
  - 逐字與 TA 兩份 C 節、風控 RQ-1／RQ-2 相符。
  - 修訂紀錄段在檔尾，沒有殘留佔位符。「CEO：否」與風控結論一致。
- **有 2 項 medium（測試的反例格不夠咬人）和數項 low。** 都不擋，列在下面。

## Codex 第二意見

Codex 第二意見未執行（環境不可用），依 CEO #53 合併前補跑。我跑 `codex --version` 得到 `command not found`（exit 127）。

## 發現

### F-1 [medium][測試／可維護性] `_dirdef_import_violations` 的相對 import 對非 dirdef 檔案用錯基準
- 位置：`tests/test_forecast_boundaries.py:495-508`（函式本體）；呼叫端 `:888`（claims）、`:899`（volatility）、`:906`（basket）。
- 依據：FL-78 (a) 的 B2D-4b 字面「相對 import 依所在套件換算成絕對名稱後判定」；我上一輪 M-3。
- 問題：
  - 函式的 `module` 預設值是 `"app.dirdef.probe"`。這三個呼叫端沒傳真正的模組名，所以 `claims.py`、`volatility.py`、`basket.py` 裡的 `from .X import …` 或 `from . import X`，會被當成 `app.dirdef.X` 而過關。
  - 後面 `app_imports == {…}` 的斷言用 `_imports_of_source`，只看 `node.module`，也看不到相對 import。
  - 目前這三個檔沒有相對 import，所以綠燈。但「basket／volatility 只 import 標準庫與 dirdef 型別」這條，被一個相對 import 就能繞過。
  - 一部分由 `test_basket_and_volatility_reach_none_of_the_forbidden_packages` 補位。它只擋 5 個禁止套件。可達 `app.outlook.*` 其他模組，再從那裡走出去，不一定擋得到。
  - dirdef 自己的檢查（`:532-535`）有傳 `_module_name(path)`，是對的。
- 建議：
  - 這三格改成 `_dirdef_import_violations(source, _module_name(path))`。
  - 在 `test_the_dirdef_import_rule_has_teeth` 加一格：以 `module="app.outlook.volatility"` 驗 `from .basket import x`，要判違規。

### F-2 [medium][測試] C-10 (a) 的反例格分辨不出「數值排序」與「字串排序」
- 位置：`tests/test_outlook_basket.py:312-321`（`test_the_basket_weight_regression_check_has_teeth`），實作 `:297-303`。
- 依據：FL-56 新字「依版本號（MAJOR、MINOR 以數值）排序」；交件報告自稱此格驗證數值排序。
- 問題：
  - 該格的版本組是 v1.10（0.92）、v1.0（0.95）、v1.2（0.95）、v2.0（1.0）。
  - 不論用數值或字串排序，第一個都是 v1.0，凍結值都是 0.95，結果都是 `["dirdef-v1.10"]`。
  - 把 `_version_key` 換成 `definition_version` 字串，這格仍然綠燈。
  - 排序只影響「哪個是第一個登記版本」，所以要用第一個版本因排序方式不同而改變的組合才咬得到。
- 建議：加一格 `[v1.10（0.95）, v1.2（0.92）]`。
  - 數值排序：v1.2 先，凍結值 0.92，結果 `[]`。
  - 字串排序：v1.10 先，凍結值 0.95，v1.2 被判退步，結果 `["dirdef-v1.2"]`。

### F-3 [low][可維護性] ADR 沒有 `copy`，實作的 `copy` 守門（含 `include`、`exclude`）沒有 ADR 錨點
- 位置：`app/dirdef/guard.py:43-56`（docstring 引用「ADR-0027 D-1 app/dirdef/ (4)」）；ADR 對應處為 L235 第 (4) 點與 FL-78 (h)。
- 依據：我上一輪 M-1 建議請 TA 在 D-1 (4) 與 D-15 3a 補列 `copy`。
- 問題：
  - TA 這輪的 B2D-2 沒有處理 `copy`，ADR 現在仍只寫 `model_construct` 與 `model_copy`。
  - 程式有守門（`update`、`include`、`exclude` 任一給了就拋 `TypeError`），測試也有，但 ADR 沒寫。
  - 同類旁路在 `app/advice` 那邊是否存在，已在 N-142(c)。
- 建議：
  - 在追蹤清單另開一項（或併入 N-142 (c)）：請 TA 補 D-1 (4)／FL-78 (h) 的 `copy` 字面，並一併裁定 `include`、`exclude` 的收緊（見下面 (c) 的第 1 點）。
  - 不擋本批。

### F-4 [low][測試] C-3 的檢查順序測試沒有涵蓋「版本鍵先於 logic 雜湊」
- 位置：`tests/test_forecast_definitions.py:175-186`、`225-239`。
- 問題：
  - `test_the_checks_run_version_then_logic_then_full_then_scan` 從 logic 雜湊起測，沒有「版本鍵不符且雜湊也不符」的格。
  - 版本錯誤那格（`:175`）雜湊是正確的，所以分不出誰先誰後。
- 建議：加一格，以錯誤的鍵登記一個雜湊也錯的物件，斷言訊息是 `definition_version`。

### F-5 [low][測試] 規則集雜湊的「其餘欄位改值」沒有和欄位集合連動
- 位置：`tests/test_dirdef_rules.py:542-558`。
- 依據：B2D-1f 對規則集只寫「其餘欄位改值 → 改變」，沒有要求表格驅動；定義物件那側有要求。
- 問題：
  - 目前六格（weight、direction、invalidation、name、id、condition）剛好蓋住 `OutlookRule` 的全部非文字欄位。
  - 但沒有「欄位集合相等」的守門格，日後新增欄位時不會變紅。
  - `RULE_TEXT_FIELDS` 也不在 `test_b2_names_are_defined_once` 的清單內。D-10 第 1 點寫「排除欄位的集合在 `app/dirdef/` 定義一次」。
- 建議：比照 `test_every_field_has_exactly_one_changed_value_cell` 補一格，並把 `RULE_TEXT_FIELDS` 補進單一定義清單。

### F-6 [low][測試] `_resolve` 對 `__init__.py` 的預設是 `is_package=False`
- 位置：`tests/test_forecast_boundaries.py:533-535`，由 `_module_name(path)` 取到 `app.dirdef` 時。
- 問題：
  - `dirdef/__init__.py` 目前沒有 import，所以沒有影響。
  - 日後若加了相對 import，會算成 `app.xxx` 而誤報違規。
  - 方向是 fail-closed，不會漏掉。
- 建議：該測試用 `path.name == "__init__.py"` 帶 `is_package`。

### F-7 [low][可維護性] ADR D-1 `app/dirdef/` 列的唯一定義清單漏列 `definition_sha256`
- 位置：ADR L235，「`definition_logic_sha256`、`rules_logic_sha256` 與規則集載入函式…的唯一定義」。
- 問題：
  - B2D-1c 沒有補這一處。D-10 第 1 點與 FL-78 (g) 都已寫明單一定義，所以只是 D-1 列的列舉沒跟上。
  - 這不是補字漏抄，是 TA 的字面本來就沒有。
- 建議：下次動 D-1 列時順手補。

## 逐條核對

### (a) 程式對條文

| 條文 | 結果 | 依據 |
|---|---|---|
| C-1 | 滿足 | `definition.py:68-71`、`177-186`；`DEFINITION_NON_LOGIC_FIELDS` 四個欄位；`definition_sha256` 與 logic 用同一個 `canonical_sha256`。 |
| C-2 | 滿足 | `registry.py:34-46`；三種錯各一格（`test_published_definition_entries_are_checked`）。 |
| C-3 | 滿足（附 F-4） | `definitions.py:97-120`，順序為鍵、logic、完整、掃描，失敗不快取，測試都在。 |
| C-4 | 滿足 | B2D-1f 的 description、c8-ref、c8-sha 各一格，且斷言 logic 雜湊不變。<br>`CHANGED_VALUES` 與 `NON_LOGIC_CHANGES` 由 `test_every_field_has_exactly_one_changed_value_cell` 連動。<br>FL-78 (g) 清單已補。 |
| C-5′、C-9 | 滿足 | `Field(ge=0.9, le=1)` 寫成字面值，沒有 import `app.sectors`。<br>拒絕格有 0.0、0.8999、1.1、nan；通過格有 0.9、0.95、1.0、1。 |
| C-6 | 滿足 | 簽章 `(members, series, window, *, coverage_unknown, definition)`。<br>只 import `app.dirdef.definition`。<br>`coverage_unknown` 含非成員拋 `ValueError`。 |
| C-7、C-7′ | 滿足 | `__init__.py`、`basket.py`、`definition.py:35-39` 的 docstring 都已改成「不 import 本套件以外的 `app.*`」「retained weight below」「只改物件不改登記雜湊的原地修改，執行期拒絕」。 |
| C-8 | 滿足 | `test_no_definition_or_rule_field_hides_strings_from_the_scan` 涵蓋 6 個 model，遞迴型別註記；`test_the_tripwire_has_teeth` 咬得到 frozenset、dict、Mapping。 |
| C-10 (a) | 部分，見 F-2 | 邏輯對；登記表為空照跑；反例格的排序辨識力不足。 |
| C-10 (b)、S-c | 滿足 | 掃整個 `app/`；`BASKET_MIN_MEMBER_WEIGHT` 屬性出現在減法任一運算元（含 `-=`）都判違規；反例格有左、右、巢狀、AugAssign、深層屬性，比較式與其他減法不誤殺。 |
| 我的 M-1 | 滿足 | `guard.py` 覆寫 `copy`；5 個 model × 3 種參數；`test_the_deprecated_copy_cannot_swap_in_unscanned_rules` 直接重現原本的旁路。 |
| 我的 M-2 | 滿足 | `POSITIONS` 由 clean fixture 的 JSON dump 機械式產生。<br>`_clean_dump` 斷言走訪順序與 `string_values` 逐一相等。<br>列出 12 個位置，含 `any[0].field`、`any[0].op`、`any[0].ref`。<br>未歸類的鍵直接失敗。 |
| 我的 M-3 | 大部分滿足，見 F-1 | `_callers` 與 `_imports_dirdef` 吃 sources，相對 import 已換算，也認屬性呼叫。<br>反例格都是真的呼叫被測函式。<br>`:` 前綴比對已改，`app.dirdefx` 與 `app.dirdef_x` 有格。 |
| 我的 M-4 | 滿足 | `_band_import_violations` 對齊 FL-72 (n)：`app.forecast.*` 恰一句且名稱正確、無別名；其他 `app.*` 只允許 `app.dirdef(.*)`。<br>原違規格改成合規格，並新增 non-dirdef、lookalike、plain、relative、second-forecast、plain-forecast 違規格。 |
| low：空禁詞 | 滿足 | `_scan_definition` 開頭 fail-closed；`test_an_empty_banned_phrase_list_is_refused`，也確認不快取。 |
| low：`tmp_path` | 滿足 | `tmp_path / "missing"`。 |
| low：look-ahead | 滿足 | `test_prices_after_the_window_change_nothing`，在窗口後放 1e9，結果與 `basket_hold_ratio` 都不變。 |
| 風控 R-1 | 滿足 | `[0.90, 1]` 字面值；`definition.py:111-115` 註解有「explicit risk-compliance and CEO approval」。 |
| 風控 R-2 | 滿足 | 用 `count / total < threshold` 與常數直接比；`basket.py` 沒有 `1 - x`，有全檔掃描格。<br>10 檔排除 1 檔不觸發，9 檔排除 1 檔（11%）與 10 檔排除 2 檔（20%）觸發。 |

### (b) 程式對已落檔 ADR 字面

- **L260：**
  - 簽章、`[0.90, 1]`、「保留權重直接比較」、「`coverage_unknown` 必須是 `members` 子集」、「只取這個常數、不讀 `CoverageRules`」，程式和測試都一致。
  - `_weight_below(len(valid), total, min_member_weight)` 對每日有效權重，`_weight_below(total - len(excluded), total, …)` 對保留權重。
- **L1619：**
  - `DEFINITION_NON_LOGIC_FIELDS` 與字面的四個欄位一致。
  - `definition_sha256` 涵蓋全部欄位。
  - 回傳前重算比對。
  - 兩個雜湊函式與排除集合各在 `app/dirdef/` 定義一次（FL-78 (g) 測試）。
- **FL-56（L3306）各格：**
  - 關鍵字參數、呼叫點以關鍵字傳入且 `definition` 非字面值（`test_every_basket_call_site_passes_its_keywords` 與反例格）。
  - 10%／11%／20% 的格由 `BASKET_MIN_MEMBER_WEIGHT = 0.9` 的 fixture 驅動。
  - 減法絆線。
  - `coverage_unknown` 含非成員拋 `ValueError`。
  - 0.8999、0.90、1.0 的型別格。
  - 已登記各版不小於凍結值（附 F-2）。
  - 「第一次登記批另釘 `SectorMomentumDefinition` v1」未來才做，目前不需要。
- **FL-78：**
  - (a)：`_in_dirdef` 用 `==` 加 `startswith("app.dirdef.")`，與「前兩段判定、不用字首字串」等價；相對 import 換算。
  - (g)：清單內的名稱（含 `string_values`、`definition_sha256`、`load_ruleset`）各恰一個定義，函式只計 `def`。
  - (h)：位置表與 `string_values` 逐一綁定，例外可辨識為 `BannedPhraseRuleSetError`，type 位置斷言「載入失敗而且不是禁詞命中」，`field`、`ref` 用替身 `OUTLOOK_RULE_FIELDS`。
  - (l2)：`BannedPhraseInDefinitionError` 是 `PublishedVersionRejectedError` 的子類；位置表格數與 `string_values` 綁定。

### (c) 實作者擴大的兩處

1. **M-1 的 `copy` 一併擋 `include`、`exclude`：接受。**
   - 理由是 `include`、`exclude` 同樣會產生缺欄位、未驗證的物件，與 ADR (4)「沒有經過掃描的規則集物件建構不出來」同一目的。
   - 不帶參數的 `copy()` 等於 `model_copy()`，行為不變，有測試。
   - 這是收緊。需要 TA 在 ADR 補字（F-3）。
2. **B2D-4b 允許套件內相對 import：接受。**
   - 我上一輪的疑慮是「ADR 沒給本套件例外」和「repo 慣例把相對 import 視為繞過」。
   - 現在 ADR 的 B2D-4a／4b 已明文寫「絕對或相對寫法皆可」，並規定換算成絕對名稱後判定，字面與程式一致。
   - 慣例面：`errors.py`、`missing.py`、`model.py` 仍走 `_import_violations`，相對 import 照舊判違規。
   - 但實作有一個漏洞，見 F-1：對 dirdef 以外的檔案用錯基準。

### (d) 閘門不變式：成立

- staged 23 檔中，沒有 `band.py`、`errors.py`，也沒有 `sectors` 下的檔案。`basket_hold_ratio` 的程式碼與簽章維持原樣。
- 兩張登記表仍是 `MappingProxyType({})`，production 的 `get_definition`、`get_ruleset` 一律拋 `UnpublishedVersionError`（有測試）。
- 沒有 job、route、`ForecastStore`、`recorder`；`test_forecast_gate_closed.py` 的 `NEW_PACKAGES` 只加了 `app.dirdef`（收緊）。
- `app/outlook/rules/` 不存在，`test_the_rules_directory_holds_only_the_two_rule_files` 斷言 `found == set()`。
- `forecast/__init__.py` 不 import 任何東西，有測試。
- `apps/` 下沒有未 stage 的變更；未 stage 的只有 ADR 與 `work/dispatch/2026-10-17-後續追蹤清單.md`。

### (e) ADR 補字

我取 ADR 的 diff，與下面三份來源逐項對字。

**TA 自決事項裁定 C 節（`B2自決事項裁定-tech-architect.md`）：**
- B2D-1a、1b、1c、1d、1e、1f 逐字相符。
- B2D-2a、2b 相符。
- B2D-3a、3b、3c、3d 相符。
- B2D-4a、4b 相符。
- B2D-5 相符。
- N137-1～5 相符。
- 修訂紀錄段的原文與格式相符，「接在 L5787 之後、前置空行、`---`、空行」。

**TA 風控條件確認 C 節 1～17（`B2D風控條件確認-tech-architect.md`）：**
- 第 1～8 項（正文）相符。
- 第 9～17 項（修訂紀錄）逐字相符。

**風控單項確認 RQ-1、RQ-2（`B2D風控條件單項確認-風控.md`）：**
- L2451 的 R-3 接字已整段換成 RQ-1 的 new 字面，並保留前半「下一點的 CI 檢查同樣適用」。
- 修訂紀錄 L5795 已接上 RQ-2 字面，三個檔名佔位符都已填入真實存在的檔案。

**其他：**
- 修訂紀錄段是檔尾最後一段。
- 殘留佔位符：Grep `〔轉存檔名〕|〔風控檔名〕|TODO|TBD|FIXME|XXX` 在 ADR 中 0 筆。`〔事實：…〕` 是有出處的合法標記。
- 「CEO：否」與風控結論一致：
  - 風控輕量確認：R-1 補上後沒有放寬風控上限，不需要 CEO 同意。
  - 風控單項確認：「CEO：否」成立。
- 修訂紀錄的閘門句仍是未來式（「R-1～R-7 補入…回送風控」），而風控單項確認已經做完。這是歷史紀錄，不影響結論。
- 追蹤清單（`work/dispatch/2026-10-17-後續追蹤清單.md`）的 N-136 到 N-145 已登記，與 TA 的 T-1～T-5、風控 S-1、S-2、S-a、S-b，以及我上一輪延後的 low 對得上。
- `docs/` 範圍外沒有其他變動。

### (f) 測試品質

- 反例格大致咬得到違規。
  - 例外是 F-1 的 base 錯用與 F-2 的排序辨識力。
  - 其餘的邊界掃描（band、dirdef import、importer、caller、banned phrase、loader call site、减法、一減、basket call、sigma call）都用違規字串餵進被測函式，不是自己重寫一遍 AST 迴圈。
- 沒有只驗 mock 的空洞測試。`test_every_published_ruleset_loads` 在登記表為空時空轉，這是 FL-78 (k) 的設計，可接受。
- 沒有祕密：我 Grep 的祕密樣式在 `app/` 與相關測試中 0 筆（`test_forecast_errors.py` 有 1 筆是既有檔，不在本批 diff）。
- 程式碼與註解皆為英文。

## 唯讀權限判準常數

未觸及。

- 判準一：staged 的 23 檔（`git diff --cached --stat`）全在 `apps/stock-desk/backend/` 下，沒有 `scripts/validate_agents.py`。未 stage 的兩個檔是 ADR 與 `work/dispatch/` 追蹤清單，也不是它。
- 判準二：我把 ADR 的 `git diff` 輸出存檔（工具結果檔），用 Grep 搜 `READONLY_AGENTS|READONLY_ALLOWED_BASH|validate_agents`，0 筆。追蹤清單的 diff 我讀過全文，沒有。
- 補充：另對整個 `apps/stock-desk` 做同樣搜尋，0 筆，沒有 shadow 定義。staged 檔與工作樹一致，所以這步等效於搜 staged diff。
- 因為我的 Bash 權限不含 `grep`，所以用 Grep 工具做等效檢查。

## Verdict

PASS，附條件：

- 合併前依 CEO #53 補跑 Codex。
- F-1、F-2 是實作者一次小改就能處理的測試補強，建議在 commit 前補；若先 commit，須列入追蹤。
- F-3 請 TA 補 ADR 字面或另開追蹤項；F-4～F-7 為 low，可併入 N-142。

BLOCKING_ISSUES=false

## Commit 建議

- **ADR 與程式碼要不要同一個 commit：**
  - ADR 的修訂紀錄段寫「本段與正文各項同一個 commit；修訂紀錄最後落檔」，管的是 ADR 內部，沒有要求與程式同 commit。
  - 但同一段的閘門寫「B2 staged diff 依本段改完並經 qa 審查之前不 commit」。
  - 建議拆兩個 commit，同一次 push：
    1. `docs: ADR-0027 B2D 自決裁定與 N-137、風控條件補字`。內容為 ADR 正文加修訂紀錄，同一個 commit。
    2. `feat: ADR-0027 B2 dirdef、定義讀取、σ_d 與族群籃子（閘門仍關閉）`。內容為 staged 的 23 個程式與測試檔。
  - 先落 ADR，再落程式，符合「程式依 ADR 字面實作」的順序。
  - 若 coordinator 偏好單一 commit 也可接受。一個語意是「B2 落檔與實作」，但 diff 會很大。
- **審查檔一起提交：**
  - ADR commit 帶：
    - `work/reviews/2026-10-25-B2自決事項裁定-tech-architect.md`
    - `work/reviews/2026-10-25-B2D風控條件確認-tech-architect.md`
    - `work/reviews/2026-10-25-B2D批輕量確認-風控.md`
    - `work/reviews/2026-10-25-B2D風控條件單項確認-風控.md`
    - `work/reviews/2026-10-25-B2D批落檔-tech-writer.md`、`…B2D風控條件落檔-tech-writer.md`、`…B2D-RQ落檔-tech-writer.md`
    - 追蹤清單 `work/dispatch/2026-10-17-後續追蹤清單.md`
  - 程式 commit 帶：
    - `work/reviews/2026-10-25-B2實作交件-dev-lead.md`
    - `work/reviews/2026-10-25-B2審查-qa-reviewer.md`
    - `work/reviews/2026-10-25-B2修正批交件-dev-lead.md`
    - 本複審（建議檔名 `work/reviews/2026-10-26-B2修正批與ADR補字複審-qa-reviewer.md`）
  - ADR 修訂紀錄引用的 `N128N131N132` 四份檔與 `…補字與B2範圍-tech-architect.md` 都已存在（Glob 確認）。若它們尚未 commit，要先進 ADR 的 commit，避免引用落空。
- **commit 前還要做：**
  - 補跑 Codex（#53）。
  - 建議先處理 F-1、F-2。
  - CI 由 coordinator 獨立跑綠燈。

## 我實際執行過的 Bash 指令（全數自我揭露）

沒有帶 `cd`。

1. `codex --version`：exit 127，`command not found`。
2. `git diff --cached --stat`
3. `git diff -- docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`：輸出過大，由系統存到工具結果檔，我用 Read 與 Grep 讀它。
4. `git diff --cached -- apps/stock-desk/backend/tests/test_forecast_gate_closed.py apps/stock-desk/backend/app/forecast/__init__.py apps/stock-desk/backend/app/outlook/__init__.py`
5. `git diff --stat`
6. `git diff --cached -- apps/stock-desk/backend/app/outlook/volatility.py apps/stock-desk/backend/app/forecast/claims.py`
7. `git diff -- work/dispatch`

沒有用到 `git show`、`git log`、`sed`、`grep`、`cat`、`python`、`pytest`、`uv`，沒有任何寫入。其餘都用 Read、Grep、Glob。沒有讀 `.env`，沒有碰 `*.db`。CI 沒有跑。

## 相關檔案（絕對路徑）

- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_boundaries.py（F-1、F-6）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_outlook_basket.py（F-2）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_definitions.py（F-4）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_dirdef_rules.py（F-5）
- /home/user/AICompany/apps/stock-desk/backend/app/dirdef/guard.py（F-3）
