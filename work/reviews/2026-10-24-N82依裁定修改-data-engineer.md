# N-82 依 TA 裁定修改

- 審查者：data-engineer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

照 tech-architect 裁定檔（`/home/user/AICompany/work/reviews/2026-10-24-N82設計裁量點裁定-tech-architect.md`）逐點改完，並一併處理 qa 的 M-1、L-2、L-3、L-4。
- 全套 pytest 為 6716 passed、2 xfailed、0 failed，覆蓋率 97.22%。
- ruff check、ruff format --check、mypy strict 都通過。
- 沒有 commit、沒有 push，沒有改 ADR 或 `work/`，沒有讀 `.env`，沒有碰 `data/*.db`，全部離線。
- 三個檔仍是 staged 的狀態，這次的修改在工作樹，尚未重新 `git add`。

## 各部門回報（data-engineer）

改動檔案（皆在 `apps/stock-desk/backend/` 下）：
- `app/data/providers/yfinance.py`
- `app/services/index.py`
- `tests/test_replay_index_snapshot.py`

**第 1 點：永遠單請求**
- 刪除 `RAW_CHART_MAX_WINDOW_DAYS` 與 `_split_windows`。`get_index_raw_responses` 現在只發一次請求，`response_seq = 1`。
- 請求區間為 `start − 1 日` 到 `end + 1 日`，即 `period1` 是 `start − 1` 的 UTC 午夜，`period2` 是 `end + 2` 日的 UTC 午夜。仍以推導出的 `session_date ∈ [start, end]` 過濾。
- 回傳仍是 `responses` tuple。service 對序號 1..n 與「每份有 bar」的驗證保留。
- `get_index_daily_bars` 與 `_fetch` 的請求區間不動，有測試釘住。
- 檔頭 docstring 已改寫 role 3，沒有任何多視窗說明。

**第 2 點與 qa M-1：三分類**
- 新增 `_derive_session_date(ts)`，是全檔唯一的 `fromtimestamp`。呼叫端只有 `_parse_chart_row` 與新的 `_classify_raw_rows`。
- 新增 `_classify_raw_rows`，取代 `_raw_bars`。逐列分三類：
  - **畸形列**整次失敗，不論是否在範圍內，同一句 reason「yfinance 回應含無法解析的列，暫不可用。」。涵蓋：
    - 陣列長度不一致，含 `or []` 造成的空陣列與非 list。
    - 時間戳記是 `None` 或 `bool`。
    - `int(ts)` 失敗，或推導日期時拋 `ValueError`／`OverflowError`／`OSError`／`TypeError`。
    - 非 null 值轉換失敗。有 null 欄位的列，其餘非 null 值也要驗證。
  - **null 缺口**：日期可推導、在範圍內、OHLCV 任一為 null，不進 bars，放進 `RawChartResponse.null_gap_rows`。新型別 `RawNullGapRow` 帶 `raw_timestamp`、`session_date`、`null_fields`（依 open、high、low、close、volume 順序）。缺口列日期在範圍外則不列入。
  - **正常列**：照舊經 `_parse_chart_row`。
- 只有缺口、沒有 bar 的回應仍整次失敗（「查無」）。
- `_parse_row`、`_parse_result` 與 `_parse_chart_row` 的行為不動。只把 `Decimal(str(...))` 與 `int(Decimal(str(...)))` 抽成 `_to_price` 與 `_to_volume`。
- service 端：新增 `ReplayNullGapRowLike`（Protocol）與 `ReplayIndexNullGapRow`。`ReplayChartResponseLike` 與 `ReplayIndexResponse` 加上 `null_gap_rows`，原樣轉交。

**第 3、4 點：程式不改，只加 docstring**
- `RawChartBar` 的 docstring 註明非整數時間戳記保留原樣，下游約束指向裁定檔第 3 點。
- `fetch_replay_index_snapshot` 的 docstring 註明不吞例外，下游約束 (4-a)(4-b) 指向裁定檔。

**第 5 點：`received_at`**
- `RawChartResponse.received_at` 在 `_request_chart_result` 成功返回後立即取 `datetime.now(UTC)`。實作上是請求返回後、檢查 `error_reason` 之前取。
- `ReplayIndexResponse.received_at` 原樣轉交。

**L-3 與 L-4**
- `ReplayIndexSnapshot.source` 改為 `str | None`。不支援代號分支為 `None`，docstring 寫明「`None` 不是來源名稱，`replay_checks` 不得當來源名寫入」。
- (b) 的 import 測試加 `node.level == 0` 斷言，不允許相對 import。

## 驗證

指令都在 `/home/user/AICompany/apps/stock-desk/backend` 下執行：
- `.venv/bin/ruff check .`：All checks passed。
- `.venv/bin/ruff format --check .`：全部已格式化。
- `.venv/bin/mypy app tests`：no issues found in 395 source files。
- `.venv/bin/python -m pytest --cov=app --cov-report=term-missing:skip-covered --cov-fail-under=90 -q`：**6716 passed、2 xfailed、0 failed**，覆蓋率 97.22%，約 13 分鐘。
- 新測試檔單獨跑：165 passed。其餘 6551 個既有測試沒有改動。

**測試對照**（皆在 `tests/test_replay_index_snapshot.py`）：

| 裁定項 | 測試 |
|---|---|
| (1-a) 20 年區間只有 1 個請求，`period1`／`period2` 正確 | `TestSingleRequest::test_twenty_year_range_is_one_request_with_padded_period` |
| (1-b) 推導日期為 `start−1` 與 `end+1` 的列不在 bars | `TestSingleRequest::test_rows_dated_just_outside_the_range_are_not_bars` |
| (1-c) 「第二份失敗」移到 service 層用假 provider | `TestAcceptanceEFailClosed::test_service_rejects_malformed_provider_answers`（10 格，含 `second_response_without_bars`、`seq_gap`、`duplicate_seq`、`reason_set_but_responses_present`、`first_response_without_bars` 等）、`test_two_good_responses_are_handed_over_in_order`、`test_a_failing_second_response_costs_the_good_first_one_too` |
| (1-d) 多視窗痕跡已刪 | `TestSingleRequest::test_multi_window_machinery_is_gone`；另有 `test_the_get_index_daily_bars_request_window_is_unchanged` |
| (2-a)～(2-i) 畸形列整次失敗，reason 用關鍵字「無法解析的列」斷言 | `TestMalformedRowsFailTheWholeFetch`：14 格，分別對 adapter 與 service 各跑一遍；另有「所有格子 reason 字面相同」與「好列夾畸形列不外洩」。格子對應如下：<br>- 毫秒時間戳記 (2-a)<br>- `10**30` (2-b)<br>- close 短 1 (2-c)<br>- 缺 volume 鍵 (2-d)<br>- close 值 `"abc"` (2-e)<br>- 時間戳記 null (2-f)<br>- 時間戳記 `true` (2-g)<br>- 範圍外畸形列 (2-h)<br>- 全 null 加毫秒時間戳記 (2-i)<br>- 另加 close 空陣列、close 非 list、volume 值 `"x"`、null 旁邊的壞值、時間戳記非數字 |
| (2-j) 範圍內全 null 列不是 bar，`null_gap_rows` 恰一項 | `TestNullGapRows::test_all_null_in_range_row_is_reported_not_a_bar` |
| (2-k) 只缺 volume，`null_fields == ("volume",)` | `TestNullGapRows::test_only_volume_null_lists_only_volume` |
| (2-l) 缺口日期為 `start−1` 時不列入 | `TestNullGapRows::test_gap_dated_outside_the_range_is_not_reported`（含 `end+1`）|
| (2-m) service 原樣轉交 `null_gap_rows` | `TestNullGapRows::test_service_hands_gaps_over_as_reported`、`test_service_hands_gaps_over_end_to_end` |
| (2-n) 回歸：`get_index_daily_bars` 對 (2-a)、(2-c)、(2-e)、(2-j) 的 payload 行為與改動前相同（仍靜默略過列） | `TestMalformedRowsFailTheWholeFetch::test_get_index_daily_bars_is_unchanged_for_the_same_payloads` |
| (5-b) `as_of ≤ 請求返回 ≤ received_at ≤ 呼叫結束`；service 原樣轉交 | `TestReceivedAt`（3 個測試）|
| L-3 | `TestSourceIsNoneWhenNothingWasContacted`（4 個測試）|
| L-2 | `TestAcceptanceEFailClosed::test_single_response_failure` 與 `test_adapter_reason_matches_for_the_same_cell`：17 格各加關鍵字斷言 |
| L-4 | `TestAcceptanceBNoCacheServiceQuota::test_module_imports_no_cache_quota_or_provider_module` |
| AST 封閉清單 | `TestAcceptanceACallSiteClosure` 已納入 `ReplayIndexNullGapRow`、`ReplayNullGapRowLike`、`RawNullGapRow` |
| `fromtimestamp` 位置 | `TestSingleDateDerivation` 四個測試：<br>- 全檔恰 1 處。<br>- 位於 `_derive_session_date`。<br>- `_derive_session_date` 的呼叫端恰為 `_parse_chart_row` 與 `_classify_raw_rows`。<br>- `_parse_chart_row` 的呼叫端恰為 `_parse_row` 與 `_classify_raw_rows`。 |

## 下一步

1. **qa-reviewer**：複審這三個檔。上次 PASS 之後有新增的畸形列與缺口列邏輯，建議特別看 `_classify_raw_rows`；Codex 第二意見仍待在有 `codex` 的環境補跑。
2. **tech-architect**：依裁定檔「下一步」第 2 點，ADR-0027 D-3 修訂（`null_gap_rows`、`received_at` 納入快照與 `content_sha256`）要先落檔，`replay_checks.py` 才能實作快照寫入。
3. **coordinator**：決策包 #49 補兩題（接近 [S, E] 長度的單一請求是否被截斷；歷史上是否有只缺 volume 的列）。如果截斷成立，要回 TA 重開多視窗方案。
4. **dev-lead**：實作 `replay_checks.py` 時遵守裁定檔 (3-a)、(3-b)、(4-a)、(4-b)、(5-c)。
