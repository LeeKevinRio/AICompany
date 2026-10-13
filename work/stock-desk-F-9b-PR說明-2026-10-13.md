# stock-desk F-9b PR 說明：日線價格幣別閘門與代號准入（2026-10-13）

- 分支：`feat/stock-desk-f9b`（自 `origin/product/stock-desk` 839567f 長出；本地分支，未 push）
- 撰寫：dev-lead；狀態：qa-reviewer 第一段、第二段 PASS（BLOCKING_ISSUES=false；Codex 第二意見未執行，環境不可用）
- 合併前提：ADR-0024 經 CEO 核可（T-10，現為 proposed）、風控逐字審、qa-e2e（375／1280）
- 依據：`docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md`；commit 切分與測試門檻依 TA5 第三節（`work/reviews/2026-10-12-tech-architect-ADR-0024第三次抽驗與F-9b切分R-57至R-69.md`）

## (a) commit 摘要與 TA5「對應」欄

切分依 TA5 R-68「先消費端、後產生端」：產生端（commit 5～7）開始寫 `rejection` 前，消費端（commit 1～4）都已能正確處理。

| # | hash | commit | 摘要 | TA5「對應」 |
|---|---|---|---|---|
| 1 | e8ff6cf | feat: load_bars 依 rejection 三分流（W-d） | 有 bars 走既有成功路徑；無 bars 且 `rejection` 不為 None 時，reason 原樣傳出（不接 `NO_BARS_REASON`、不加前綴）；其餘照舊 | D-7 (7)、C-13（管線）、C-18、F9W-6、F9W-22、F9W-33 (a)（傳遞） |
| 2 | 9071ea4 | feat: 估值器新增單位拒收缺漏 token 且不查匯率 | `symbol_or_unit_rejected`：只看 `rejection`；`missing` 只有該 token；`fx`／`fx_open` 為 None；匯率 provider 零呼叫 | C-19、C-11（估值）、C-34 (b)(c)(d)（估值）、F9W-18 |
| 3 | 838d8aa | feat: 整書成因組 T-11 與陳述順序 | 第四組成因：計數 X-3c ＞ 本組 ＞ not_queried ＞ asked；陳述 W4 → W5 → (b) → 本組；`UNVALUED_NOTE_TEMPLATE` 零 diff | C-20、C-21、C-29、F9W-17、F9W-25、壞處 10 |
| 4 | ff41f25 | feat: 庫存頁新增 T-12 缺漏標籤 | `MISSING_LABELS` 新增一鍵（10 字，依 coordinator 2026-10-13 裁決 (a) 為 ≤8 字目標的例外） | C-22、C-8、F9W-19 |
| 5 | 7a8c4a5 | feat: 日線 live 層幣別閘門（W-c／W-c′ fail-closed） | live 層整段拒收；同一次呼叫有 W-c 時不讀快取；W-c 之後的層要整段；C-35 建構期檢查與 live 檢查點 raise | C-1（live）、C-2、C-3、C-11、C-13 (3)(4)(5)(10)、C-14、C-33、C-34 (e)、F9W-4 (a) |
| 6 | 5eced07 | feat: 快取閘門與 T-15（layer 0 第 4、5 步、fallback、cache-only、合併讀回） | 四條快取路徑都過閘門；layer 0 在 R-8 之前檢查；T-15 恰一次；指數路徑無字面 | C-1、C-13 (7)(8)(9)、C-17、C-30、C-32、C-34、F9W-31 (b)(c)、F9W-33 (a)(b) |
| 7 | a9fb896 | feat: 日線兩入口代號准入與 AV 縱深檢查 | 兩入口准入（W-a／W-b）；deps 顯式接准入與字面組；AV 在扣額度前再檢查 | C-4、C-6、C-7、C-13 (1)(2)、C-15、C-16、C-17（grep）、C-19（准入） |
| +1 | fe91012 | fix: 指數路徑 W-c′ 後亦整段請求並補自行修復測試變體 | 依 D-4，指數 W-c′ 後的層也要整段；類別 docstring 去掉過時字句；補 TA6 R-75 suggested 兩項測試 | D-4、D-2 (2)、TA6 R-75 |

**F-9b2 範圍（本 PR 不做）**：D-2 (5)(a) 第 1～3 步、D-9 標記、C-23～C-27、C-31 原式、C-17「預置 D-9 標記」。

## (b) 改寫的既有測試（逐一列名）

只列「本 PR 之前就存在」的測試。標「延伸」者，原有斷言全數保留、只加不減。

**第一段（commit 1～4）**
1. `tests/test_x3c_currency_market_mismatch.py::_cause_counts`（helper）：由三組延伸為四組。（commit 3，延伸）
2. `tests/test_x3c_currency_market_mismatch.py::test_kxa9_three_groups_are_disjoint_ordered_and_add_up`：更名為 `test_kxa9_four_groups_are_disjoint_ordered_and_add_up`，加一列被拒列，總數 4 → 5。（commit 3，延伸）
3. `tests/test_x3c_currency_market_mismatch.py::test_kxa10_a_mismatched_row_is_never_counted_as_missing_a_price_or_rate`：計數 dict 補上 `"rejected": 0`。（commit 3，延伸）
4. `frontend/app/lib/__tests__/valuationWording.test.ts` 的 `labels every token the backend can emit, each within eight characters`：更名為 `…, the five pre-F-9 ones each within eight characters`；鍵集合加入新 token；≤8 字斷言改為明列既有五鍵、強度不變。（commit 4，**依 coordinator 2026-10-13 裁決 (a)**）

**第二段（commit 5～7）**
5. `tests/test_f9b0_rejection.py::test_nothing_produces_a_rejection_before_the_gate_lands`：更名為 `test_only_the_service_produces_a_rejection_and_only_through_the_constructor`。（commit 5）
6. `tests/test_f9a_service_currency_warning.py::test_off_market_currency_warns_on_each_path_and_changes_nothing`：commit 5 改為只跑快取檢查點；commit 6 更名為 `test_off_market_currency_on_each_cache_path_is_refused_with_its_record`。
7. `tests/test_f9a_service_currency_warning.py::test_index_scope_logs_error_on_each_path_and_changes_nothing`：同上兩步；更名為 `test_index_scope_logs_error_on_each_cache_path_and_refuses_without_wording`。
8. `tests/test_f9a_service_currency_warning.py::test_a_market_without_a_currency_counts_as_mismatch_and_changes_nothing`：commit 5 改為查表在建構後才落空（C-35 (d)），並拆出 `…raises_at_the_live_checkpoint`；commit 6 兩者合併為 `test_a_market_without_a_currency_raises_at_every_checkpoint`。
9. `tests/test_f9a_service_currency_warning.py::test_a_blank_currency_logs_verdict_missing_and_changes_nothing`：更名為 `…_and_is_refused`。（commit 5）
10. `tests/test_f9a_service_currency_warning.py::test_warning_text_is_fixed`：incremental 情境的期望記錄。（commit 5、6）
11. `tests/test_f9a_service_currency_warning.py::test_index_ladder_is_checked_per_market_and_logs_error`：由「仍回 bars」改為斷言拒收。（commit 5）
12. `tests/test_f9a_service_currency_warning.py` 的 incremental 情境資料與檢查點數；移除不再使用的 `_assert_unchanged`。（commit 5、6）
13. `tests/test_f9a_service_currency_warning.py::test_equity_ladders_are_told_their_market_currency`：US 改用 `AAPL`。（commit 7）
14. `tests/test_f9a_admission.py::test_admission_is_not_wired_into_any_path_yet`：更名為 `test_admission_is_wired_only_where_adr_0024_puts_it`，列出四個使用處。（commit 7）
15. `tests/test_f9b0_service_scope.py::test_the_gate_arguments_are_keyword_only_and_have_no_default`、`test_omitting_either_gate_argument_fails_to_construct`：參數由 2 個擴為 4 個。（commit 7，延伸）
16. `tests/test_f9b0_service_scope.py::test_an_unknown_scope_is_refused`：補傳 `admission`、`wording`。（commit 7）
17. `tests/test_service.py`：`_us_bar` 與 TestCacheFirst 美股情境的代號由 `2330` 改為 `AAPL`（TA1 M-12），斷言未改。（commit 7）

**本 PR 內新增、後又調整的測試**（不屬「既有」，列出供核對）：`test_f9b_cache_currency_gate.py::test_layer0_refused_outside_the_cooldown_self_repairs_from_the_live_rung` 在 fe91012 加了 `ladder` 參數化與「不含 T-15」斷言；`test_f9b_load_bars_wd.py` 的 W-c′＋T-15 案例在 5eced07 補註，類別未改。

## (c) C-28／F9W-10 消費端字串表

**傳遞方式**
- W-a、W-b、W-c、W-c′、T-15 都只經 `ProviderResult.reason` → `load_bars` 的 W-d 分流，原樣傳出，不接 `NO_BARS_REASON`、不加「來源回報：」。
- 估值器與整書另用 token：T-11（整書成因）、T-12（庫存頁標籤）。

**後端消費端**（依 `load_bars` 呼叫點逐一讀碼）

| 消費端 | 位置 | 拒收時（無 bars）如何呈現 reason | 有無框架句包裝 |
|---|---|---|---|
| K 線 `/api/bars` | `app/api/bars.py` L90-104 | `reason=loaded.reason`，並放在 `data.reason` | 無 |
| 訊號 `/api/signals` | `app/api/signals.py` L96-105 | 同上 | 無 |
| 操作建議 `/api/advice` | `app/api/advice.py` L157-227 | 無最新 bar 時 `reason=loaded.reason`；`data.reason` | 無 |
| 首頁風險上限 sources `/api/portfolio/limits` | `app/api/portfolio.py` L159-166 | `SymbolDataMeta.data.reason`（meta 原樣） | 無 |
| 槓桿 `/api/leverage` | `app/api/leverage.py` L97-126 | chapter 無自有原因時 `loaded.reason` | 無；指數原因另走 `index.py` |
| 回測 | `app/api/backtest.py` L449-488 | `unavailable(loaded.reason)` | 無 |
| 事件研究 | `app/api/event_study.py` L154-163 | `loaded.reason`，空才用自有「區間內只有…」句 | 無 |
| alerts snapshot | `app/alerts/snapshot.py` L111-151 | 無 bars 時 `SymbolSnapshot(reason=loaded.reason)` 原樣 | 無 bars：無。**有 bars（W-c′＋快取，C-34 (b)）時，前接既有核可的 layer note「資料來自 cached_stale 層（{source}）。」**（`_joined_reason`；風控 2026-09-15 R1-a 既有機制，不是新橋接句）→ 請風控依 F9W-33 (d) 知悉 |
| playbook | `app/playbook/service.py` L221-235 | `result.reason` 帶入 snapshot／warnings | 未逐行追到最終字串，待 qa 核對 |
| scheduler 資料刷新 | `app/scheduler.py` L295-299 | 只寫 INFO log | 不上畫面 |
| diagnose CLI | `app/data/diagnose.py` L154-161 | 原樣印出（操作端） | 不上畫面 |
| 指數路徑 | `app/services/index.py` L255-266、L377-388 | **不會出現上列任何句子**：指數無字面（D-4），沿用既有指數版 `NO_BARS_REASON`（風控 F9W-31、F9W-32 已接受的殘留） | 既有 |

**前端**：本 PR 沒有逐元件實機核對，屬 qa-e2e 範圍。讀碼所見如下：
- `InsufficientPanel` 原樣顯示 `reason`，只有 null 時才用自有預設句。
- `DataMetaStatusBadge` 在狀態標示旁顯示 `DataMeta.reason`，compact 時移入 `<details>`。
- `RiskGauge` 的 `excluded` 清單以「{symbol}（{市場}）：{reason}」呈現；這裡的 reason 是 book limits 自己的原因，不是 `loaded.reason`。
- 未見把 `loaded.reason` 包進「已改以快取」「單位為美元」這類句子的框架。

**各句出現處**

| 句子 | 出現處 |
|---|---|
| W-a（美）、W-b（台） | 上表所有股票消費端；只在服務層准入時產生（F9W-7）。AV 縱深路徑不出句 |
| W-c 美／台 | 股票消費端，live 層拒收時；可能與其他層原因以 `_combine_reasons` 合併 |
| W-c′ 美／台 | 同上；另在 C-34 (b) 情境與快取價格、F-7 單位標籤並存（F9W-33、F9W-34） |
| T-15 | 股票消費端，四條快取路徑被擋時；可能與各層原因合併；同一 reason 至多一次 |
| T-11 | 整書成因：`/api/advice` 卡片與 `/api/portfolio/limits` 總覽的 notes（`book_notes`）；以 `UNVALUED_NOTE_TEMPLATE` 接方向子句 |
| T-12 | 庫存頁 `PositionsTable` 價格欄小字（`missingSummary`），位於「資料不足」badge 下方 |

## (d) C-35／F9W-39 呼叫端處理表（`CurrencyLookupError`）

觸發條件：注入的查表在建構後才對某市場回 None 或空白。正式設定下 `MARKET_CURRENCY` 是模組常數，屬推論上不可達。

| 呼叫端 | 處理 | 是否產生資料語意字面 | 前端 500 呈現證據 |
|---|---|---|---|
| `MarketDataService.get_daily_bars`／`get_cached_bars`（所有閘門檢查點） | 先寫一筆 `expected=<none>` 記錄，再 raise；不寫快取、不 `record_fetch` | 不產生資料語意字面 | — |
| `MarketDataService._try_provider` | 例外不在其 `try` 範圍內，不會被吞成「非預期錯誤」降級 | 不產生資料語意字面 | — |
| `app/services/market.py::load_bars` | 無 except，向外傳出 | 不產生資料語意字面 | 待 qa-e2e |
| `app/portfolio/valuation.py::_resolve_price`／`value_position` | 無 except，向外傳出 | 不產生資料語意字面 | 待 qa-e2e |
| `app/services/index.py` 指數與基準兩個出口、`IndexSeriesService` | 無 except，向外傳出 | 不產生資料語意字面 | 待 qa-e2e |
| `/api/*` 端點（bars、signals、advice、portfolio、leverage、backtest、event_study） | 無 except，FastAPI 預設 500 | 不產生資料語意字面 | 待 qa-e2e |
| `app/alerts/snapshot.py`、`app/playbook/service.py` | 無 except，向外傳出 | 不產生資料語意字面 | 待 qa-e2e |
| `app/scheduler.py` 資料刷新（`DataRefreshRun.__call__`） | 記 ERROR（`outcome=error`）後 re-raise；`_guarded` 記 traceback，排程續存 | 不產生資料語意字面（只有 log） | 不上畫面 |
| `app/scheduler.py::taiex_reference_return`（既有，L443-453） | `except Exception` → 記 ERROR log（`sector board: TAIEX reference unavailable`），回 None | 不產生資料語意字面；**靜默省略參考數字與揭露句、記 ERROR log**（`reference_taiex_return_L=None`，API `has_taiex_reference=false`） | 待 qa-e2e |
| `app/data/diagnose.py` | 無 except，CLI 中止 | 不產生資料語意字面 | 不上畫面 |

## (e) 引用

- 風控裁定：F9W-1～F9W-16、F9W-17～F9W-29、**F9W-30～F9W-34**、**F9W-35～F9W-37**、**F9W-38**、**F9W-39**（`work/reviews/2026-10-12-F-9-*-風控.md`）。
- F7-R10（F-7 系列，延伸引用，依 F9W-16）。
- C-29：每個新常數都依 C-9 註明風控核可出處。

**新常數出處**

| 常數 | 核可出處 |
|---|---|
| `SYMBOL_NOT_ADMITTED_REASON_US`／`_TW`（W-a、W-b） | F9W-1、F9W-2 |
| `UNIT_MISMATCH_REASON_US`／`_TW`、`UNIT_MISSING_REASON_US`／`_TW`（W-c、W-c′） | F9W-3 |
| `CACHE_UNIT_REJECTED_REASON`（T-15） | F9W-22 |
| `SYMBOL_OR_UNIT_REJECTED_CAUSE`（T-11） | F9W-17 |
| 前端 `MISSING_LABELS.symbol_or_unit_rejected`（T-12） | F9W-19 |

- 每個常數都有測試，直接讀裁定檔原行做逐字比對。
- 改任何字、分流或先後順序，都要回風控重審（F9W-16、F9W-29）。

## (f) 殘留與知悉

1. **「T-15。 W-c。」跨層組合（未審）**：合併讀回被擋（T-15 已併入累積原因）之後，若後續 live 層又判定 W-c，回覆 reason 會依 `_combine_reasons` 依序含 T-15 與 W-c。只有在「另一個程序於兩次讀取之間寫入壞列」的競態下才可能發生（layer 0 已先擋下快取壞列）。沒有另做處理，送風控知悉。
2. **AV 縱深 reason=None**：`AlphaVantageAdapter` 在扣額度前判定准入不通過時，回 `UNAVAILABLE`、`reason=None`。依 F9W-7 不得出 W-a／W-b；adapter 內既有的「不是合法的美股個股代號格式…」句查無風控核可紀錄，所以不採用。正常路徑不可達，因為服務層准入會先擋。
3. **指數路徑 reason 可為 None**：依 ADR-0024 D-4，指數拒收時不帶任何字面，reason 只含其他 live 層的既有原因；layer 0 冷卻期內被擋時為 None。經 `index.py` 呈現既有指數版 `NO_BARS_REASON`（F9W-31、F9W-32 殘留）。qa non-blocking (1)「reason 非空白」只套用股票路徑。另外，沒有 `source_id` 的 provider 判定 W-c 時依 C-14 不出句，股票路徑的 reason 也可能為 None（正式 adapter 都有 `source_id`）。
4. **taiex 參考值殘留**：`scheduler.py::taiex_reference_return`（既有程式）以 catch-all 吞掉例外，查表落空時會靜默省略 TAIEX 參考數字與揭露句，只記 ERROR log。qa-reviewer 已接受，列 PR 層級條件。
5. **已以測試實證的原推論**
   - TA5 第二節測試 2 的 layer 序列；
   - R-63「孤兒壞列使每次點擊重跑梯子」；
   - F9W-38 的跨呼叫後果（冷卻期內第二次呼叫回 `RECENT_ATTEMPT_FAILED_REASON` 與快取列）。
6. **仍待 PR 層級完成**
   - 風控逐字審；
   - qa-e2e 在 375／1280 驗庫存頁 T-12、整書四組並列、K 線區／操作摘要／首頁風險上限「詳細」三處的 T-15 與合併 reason、C-34 (b) 情境（F9W-34）；
   - 前端 500 呈現證據；
   - CEO 核可 ADR-0024。

## 驗證摘要

**後端**：每個 commit 都在快照上依序跑 `ruff check`、`ruff format --check`、`mypy app tests`（strict，含 `warn_unused_ignores`）、`pytest -q`，全綠。pytest 數字：

| commit | pytest |
|---|---|
| 基準 | 5998 passed／2 xfailed |
| 1 | 6020 |
| 2 | 6043 |
| 3 | 6060 |
| 4 | 6060 |
| 5 | 6097 |
| 6 | 6121 |
| 7 | 6161 |
| fe91012 | 6164 |

（各列皆另有 2 xfailed。）

**前端**（commit 4、6）：vitest 75 檔／2089 passed，`tsc --noEmit` 通過。

**mutation**：每個 commit 至少一種，總計 43 種（commit 1～7 依序 3／5／5／6／7／8／7 種，fe91012 2 種），全部被擋。
