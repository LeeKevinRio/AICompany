# stock-desk F-9b PR 說明：日線價格幣別閘門與代號准入（2026-10-13）

- 分支：`feat/stock-desk-f9b`（自 `origin/product/stock-desk` 839567f 長出；本地分支，未 push）
- 撰寫：dev-lead；狀態：qa-reviewer 第一段、第二段 PASS（BLOCKING_ISSUES=false；Codex 第二意見未執行，環境不可用）
- 風控 PR 層級逐字審：APPROVE WITH CONDITIONS（F9W-40～F9W-48，2026-10-13；無否決）
- 合併前提：ADR-0024 經 CEO 核可（T-10，現為 proposed）；qa-reviewer 勾核 F9W-40～F9W-45；qa-e2e（375／1280，F9W-46 (a)、F9W-47）
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
| 補 | 63a9b7d | test: 補 F-9b 風控 PR 層級條件測試（F9W-41、F9W-43～F9W-46） | alerts C-34 (b) 完全相等；讀回被擋後 backup 回 W-c／W-c′；`source_id` 絆線；taiex 同進同出與 ERROR log；T-11 改讀裁定原行；≤8 字改為「預設全部、例外明列」。未新增 `except`、未改任何字面 | F9W-41、F9W-42 (c)、F9W-43～F9W-46 |

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
| alerts snapshot | `app/alerts/snapshot.py` L111-151 | 無 bars 時 `SymbolSnapshot(reason=loaded.reason)` 原樣 | 無 bars：無。**有 bars（W-c′＋快取，C-34 (b)）時，前接既有核可的 layer note「資料來自 cached_stale 層（{source}）。」**，以 `_joined_reason` 的單一空格相接（風控 2026-09-15 R1-a／R4-a 既有機制，不是新橋接句）；風控 F9W-41 裁定可接受，並以 `test_f9b_risk_conditions.py::test_f9w41_…` 完全相等釘住。layer note 的組成或接法若有任何改動，須回風控 |
| alerts 觸發訊息（feed、Discord、Telegram） | `app/alerts/engine.py` L444-445 | 拒收時沒有收盤價，規則不觸發（見下列 skip outcome） | C-34 (b) 有 bars 時，訊息尾端接 `data_disclosure`（＝layer note＋單一空格＋`loaded.reason`）；W-c′ 句完整、不改寫（F9W-41） |
| `POST /api/alerts/evaluate` 的 skip outcome | `app/alerts/engine.py` L500-533 | 無 bars 時 snapshot 沒有收盤價：價格規則用 `snapshot.reason or "沒有可用的最新收盤價。"`，訊號規則用 `snapshot.reason or "沒有可用的訊號輸出。"`，即 W-a～T-15 原樣；風險上限規則用自己的固定句 | 無 |
| playbook | `app/playbook/service.py` L221-235、L279-289、L360-361、L758-763、L784 | **無 bars 時**，reason 不進 settle、rebalance、evaluate 的 warnings：三處只用 `DATA_GAP_NOTE`、`SETTLEMENT_NO_OPEN_PRICE`、`REBALANCE_BLOCKED`，帶 status 與 source。唯一例外是 `emergency_exit`，把 `series.reason` 原樣放進 `Directive.data_reason`（L784）。**有 bars 時**，`MarketSnapshot.data_reason` → `Directive.data_reason` → 前端 `DirectiveLedger.tsx` L71-76 的 `DataMetaStatusBadge` 原樣呈現。指數 reason 經 `INDEX_DATA_REASON_NOTE` 呈現，指數路徑不帶閘門字面（D-4） | 無包裝、無改寫（風控逐行追到最終字串）。無 bars 時，W-b 等成因不出現在 settle／evaluate 警示，屬少揭露、不是不實，列 CEO 知悉 |
| Kelly import | `app/api/kelly.py`、`app/kelly/sample_gate.py` L128-139 | 走自己的 `INSUFFICIENT_DATA_MESSAGE`，**不帶 `loaded.reason`** | 無 |
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

觸發條件：注入的查表在建構後才對某市場回 None 或空白。正式設定下 `MARKET_CURRENCY` 是模組常數，C-35 (b) 的建構期檢查會在 CI 擋住，因此**不可達**。

本 PR **沒有為這個例外新增任何 `except`**，表中的攔截都是既有程式（風控 F9W-40）。

**前端 500 呈現（全表通用，不需實機驗）**
- `frontend/app/lib/api.ts` L172-184：FastAPI 預設 500 沒有 JSON body，這段會轉成「請求失敗（HTTP 500）」的 `ApiError`，不會出現任何資料語意字面。
- `missingSummary` 只在 `frontend/app/components/PositionsTable.tsx` L86、L100 對 **200 回應**的 `valuation.missing` 使用，500 路徑到不了。
- 以上狀態在正式設定下不可達，因此不需要 qa-e2e 實機驗（F9W-40 (c)）。

| 呼叫端 | 是否在傳播路徑上、處理方式 | 是否產生資料語意字面 | 前端 500 呈現證據 |
|---|---|---|---|
| `MarketDataService.get_daily_bars`／`get_cached_bars`（所有閘門檢查點） | 是（源頭）。先寫一筆 `expected=<none>` 記錄再 raise；不寫快取、不 `record_fetch` | 不產生資料語意字面 | 不適用 |
| `MarketDataService._try_provider` | 否。例外不在其 `try` 範圍內，不會被吞成「非預期錯誤」降級 | 不產生資料語意字面 | 不適用 |
| `app/services/market.py::load_bars` | 是。無 except，向外傳出 | 不產生資料語意字面 | `api.ts` L172-184；不可達、不需實機驗 |
| `app/portfolio/valuation.py::_resolve_price`／`value_position` | 是。無 except，向外傳出 | 不產生資料語意字面 | `api.ts` L172-184；`missingSummary` 只用於 200（`PositionsTable.tsx` L86、L100）；不可達、不需實機驗 |
| `app/services/index.py` 指數與基準兩個出口、`IndexSeriesService` | 是。無 except，向外傳出 | 不產生資料語意字面 | `api.ts` L172-184；不可達、不需實機驗 |
| `/api/*` 端點（bars、signals、advice、portfolio、leverage、backtest、event_study） | 是。無 except，FastAPI 預設 500 | 不產生資料語意字面 | `api.ts` L172-184；不可達、不需實機驗 |
| `app/alerts/snapshot.py::build_snapshot` | 是。本身無 except，例外拋給它的 loader 呼叫端，由下一列的 `_load_isolated` 攔截（**更正：先前寫的「500」不正確**） | 不產生資料語意字面 | 見下一列 |
| `app/alerts/engine.py::_load_isolated`（L470-490，既有） | 是，在此**攔截**。記 WARNING（市場、規則數、例外類別，附 `exc_info`），以空 snapshot 繼續該 tick。該 (symbol, market) 的價格規則與訊號規則以既有句「沒有可用的最新收盤價。」「沒有可用的訊號輸出。」略過，風險上限規則用自己的固定句。`POST /api/alerts/evaluate` 回 **200**、`status=skipped`；排程 tick 只留 log | **不產生新字面**：沿用既有 skip 句，狀態為 skipped 而不是 quiet（未改既有 skip 句） | 回 200，不適用 500 |
| `app/playbook/service.py` | 是。無 except，向外傳出 | 不產生資料語意字面 | `api.ts` L172-184；不可達、不需實機驗 |
| `app/portfolio/price_change.py` L193-197（`ChangeScreen` 的 `except Exception`） | **否**。它拿到的是已完成的估值（`PositionValuation` 列），不會呼叫資料服務；例外早在估值時就已拋出，到不了這裡 | 不產生資料語意字面 | 不適用 |
| `app/services/sector_board.py` L365、L371（`refresh_board`、`_maybe_evaluate` 的 `except Exception`） | **否**。sector board 只透過 `reference_taiex`（＝`scheduler.taiex_reference_return`）碰到資料服務，例外會先在那裡被攔下（見下列）；其餘讀的是市場面板 store，不經 `MarketDataService` | 不產生資料語意字面 | 不適用 |
| `app/scheduler.py` L344（`DataRefreshRun.__call__`） | 是。記 ERROR（`outcome=error`）後 re-raise | 不產生資料語意字面（只有 log） | 不上畫面 |
| `app/scheduler.py` L502（PIT capture 後 `refresh_sector_board()` 的 `except Exception`） | **否**。例外已在 `taiex_reference_return` 被攔下，傳不到這一層 | 不產生資料語意字面 | 不上畫面 |
| `app/scheduler.py` L610（`_guarded`） | 是，作為排程最外層。資料刷新 re-raise 上來的例外在此記 traceback，排程續存 | 不產生資料語意字面（只有 log） | 不上畫面 |
| `app/scheduler.py::taiex_reference_return`（既有，L443-453） | 是，在此**攔截**。`except Exception` → 記 ERROR log（`sector board: TAIEX reference unavailable`，附 traceback；**不降噪**），回 None | 不產生資料語意字面。**靜默省略參考數字與揭露句、記 ERROR log**。參考數字與 `TAIEX_REFERENCE` 揭露句**同進同出**：`api/sectors.py` L370 以 `has_taiex_reference=board.reference_taiex_return_L is not None` 傳入 `sectors_wording.py` L251 的 `standing_disclosures`；前端 `SectorMomentumCard.tsx` L336。以 `test_f9b_risk_conditions.py::test_f9w45_*` 兩則測試釘住（另有既有的 `test_api_sectors.py::test_standing_disclosures_when_the_card_is_ok`） | 不可達、不需實機驗 |
| `app/data/diagnose.py` | 是。無 except，CLI 中止 | 不產生資料語意字面 | 不上畫面 |

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

**逐字比對測試的實際寫法**（風控 F9W-42 (c) 更正，原句「每個常數都讀裁定檔原行」不完全屬實）

| 常數 | 比對方式 |
|---|---|
| W-a、W-b | `test_f9b_admission_gate.py` 讀裁定一 L20、L23 原行 |
| W-c、W-c′ | `test_f9b_live_currency_gate.py` 讀裁定一 L26、L29、L32、L35 原行 |
| T-15 | `test_f9b_cache_currency_gate.py` 讀裁定二 L40 原行 |
| T-11 | 原為寫死字串；63a9b7d 起改讀裁定二 L26 原行（F9W-42 (c) suggested） |
| T-12 | 前端 `valuationWording.test.ts` **仍是寫死字串**，與裁定二 L29 逐字相同（已人工核對，風控 F9W-42 亦確認相同）。前端測試不讀 repo 外的 `work/` 檔 |

改任何字、分流或先後順序，都要回風控重審（F9W-16、F9W-29）。

- 風控 PR 層級逐字審：`/home/user/AICompany/work/reviews/2026-10-13-F-9b-PR層級逐字審-F9W-40至F9W-48-風控.md`。F9W-40～F9W-45 已於 63a9b7d（測試）與本檔落實；F9W-46 (b) suggested 一併做了；F9W-46 (a)、F9W-47 屬 qa-e2e；F9W-48 屬合併後。

## (f) 殘留與知悉

風控 F9W-40～F9W-48 裁定（2026-10-13）：以下五項殘留全部接受，其中三項附條件，條件均已落實。

1. **「T-15。 W-c。」跨層組合**
   - 情境：合併讀回被擋（T-15 已併入累積原因）之後，後續 live 層又判定 W-c 或 W-c′，回覆 reason 依 `_combine_reasons` 依序含 T-15 與該句。
   - 只在「另一個程序於兩次讀取之間寫入壞列」的競態下才會發生，因為 layer 0 已先擋下快取壞列。
   - 風控接受：兩句各自屬實，與 C-13 (9) 同類；讀回被擋後 fallback 不再讀快取，F9W-4 仍成立。
   - **F9W-43 已以 `test_f9b_cache_currency_gate.py::test_f9w43_a_refused_read_back_then_a_refused_backup`（W-c、W-c′ 兩變體）完全相等釘住。**
   - 這兩種以外的跨層新組合若出現，須回風控。
2. **AV 縱深 reason=None**
   - `AlphaVantageAdapter` 在扣額度前判定准入不通過時，回 `UNAVAILABLE`、`reason=None`。
   - 依 F9W-7 不得出 W-a／W-b；adapter 內既有的「不是合法的美股個股代號格式…」句查無風控核可紀錄，所以不採用。
   - 正常路徑不可達，因為服務層准入會先擋。風控接受。
3. **指數路徑 reason 可為 None**
   - 依 ADR-0024 D-4，指數拒收時不帶任何字面，reason 只含其他 live 層的既有原因；layer 0 冷卻期內被擋時為 None。
   - 經 `index.py` 呈現既有指數版 `NO_BARS_REASON`（F9W-31、F9W-32 殘留）。風控接受。
   - qa non-blocking (1)「reason 非空白」只套用股票路徑。
   - **C-14 股票路徑 reason=None**：沒有 `source_id` 的 provider 判定 W-c 時依 C-14 不出句，此時消費端用各自的既有預設句。風控接受。
   - **F9W-44 絆線**：`test_f9b_risk_conditions.py::test_f9w44_every_equity_rung_deps_builds_has_a_source_id`。轉紅時須連同此殘留回風控，不得只改期望值。
4. **taiex 參考值殘留**
   - `scheduler.py::taiex_reference_return`（既有程式）以 catch-all 吞掉例外。查表落空時會靜默省略 TAIEX 參考數字與揭露句，兩者同進同出，並記 ERROR log。
   - 風控接受，附 F9W-45：不降噪；以 `test_f9b_risk_conditions.py::test_f9w45_*` 兩則測試釘住。
5. **已以測試實證的原推論**
   - TA5 第二節測試 2 的 layer 序列；
   - R-63「孤兒壞列使每次點擊重跑梯子」；
   - F9W-38 的跨呼叫後果（冷卻期內第二次呼叫回 `RECENT_ATTEMPT_FAILED_REASON` 與快取列）。
   - 合併後由 tech-writer 依 F9W-48 更新 ADR 的知悉句。
6. **CEO 知悉**（風控 2026-10-13「需 CEO 知悉事項」）
   - W-c′ 句在 C-34 (b) 情境會連同 layer note 出現在警示推播（F9W-41）。
   - 組態錯誤時，該市場的警示規則每個 tick 都被略過、只留 WARNING log；正式設定下由 C-35 在 CI 擋住，不可達。
   - playbook 在無 bars 時少揭露成因：屬少揭露、不是不實。
   - F9W-14 殘留不變。
7. **仍待 PR 層級完成**
   - qa-reviewer 勾核 F9W-40～F9W-45；
   - qa-e2e 執行 F9W-46 (a)、F9W-47 必驗清單（375／1280）；
   - CEO 核可 ADR-0024（T-10）；
   - Codex 第二意見未執行（環境不可用），由 CEO 決定。

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
| 63a9b7d | 6170 |

（各列皆另有 2 xfailed。）

**前端**（commit 4、6 與 63a9b7d）：vitest 75 檔／2089 passed，`tsc --noEmit` 通過。

**mutation**：每個 commit 至少一種，總計 50 種，全部被擋。
- commit 1～7 依序 3／5／5／6／7／8／7 種；
- fe91012 2 種；
- 63a9b7d 7 種：後端 6、前端 1。
