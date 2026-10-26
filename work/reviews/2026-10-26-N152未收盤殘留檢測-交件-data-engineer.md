# N-152 舊 DB 未收盤殘留唯讀檢測腳本交件

- 審查者：data-engineer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 接入摘要
N-152 唯讀檢測腳本、測試和 CEO 執行說明都完成了。分支 `feat/stock-desk-unfinished-bar-probe` 已 push 到 origin（第一次就成功，沒用到重試）。完整後端 CI 全綠。

- 分支從當時的 `product/stock-desk`（1d7bffd）開出，沒有 merge 或 push 到 `product/stock-desk`。
- 已 push 的 HEAD：`767c5249b7069479495f0bd7b8046c6c1bcad19f`，本地與 `origin/feat/stock-desk-unfinished-bar-probe` 一致。
- 我做到一半時，本地 `product/stock-desk` 被別的 session 推進到 f66fc9d，不是我動的。本分支的 base 仍是 1d7bffd，之後需要時再 merge。
- 3 個 commit，都帶指定 trailer：
  - 1d7bffd 之後的 `d3e1fbb`：`feat:` 腳本和測試
  - `767c524`：`docs:` CEO 執行說明

檔案（都在 `/home/user/AICompany/.claude/worktrees/agent-a07313e613f8d1d41/` 下）：
- `apps/stock-desk/backend/scripts/unfinished_bar_probe.py`
- `apps/stock-desk/backend/tests/test_unfinished_bar_probe.py`
- `work/research/N152-未收盤殘留檢測-執行指令-2026-10-26.md`

## Schema / 介面

**判定邏輯**
- 一列被列出，當且僅當 `fetched_at` 早於該列 `trade_date` 在該市場收盤時刻（換算成 UTC）。
- 收盤時刻：TW 13:30 `Asia/Taipei`，US 16:00 `America/New_York`。
- `fetched_at` 剛好等於收盤時刻時不列出。依據是 `freshness.py` 以 `local.time() >= session_close` 視為已收盤。
- 規則沒有交易日曆，只依日期判定。

**最新一根標記**
- `is_latest_bar` 為 yes，表示該列 `trade_date` 等於同一 `(symbol, market)` 在整張表裡最大的 `trade_date`，不只是被列出的那幾列。
- 另外印出該 symbol 的最新 `trade_date`，方便對照。

**輸出內容（只印事實）**
- 檔頭：DB 路徑、執行時間（UTC）。
- 規則本身。
- 計數：掃描總列數；TW、US 各自的總列數、`fetched_before_close`、`is_latest_bar` / `not_latest_bar` 各幾筆。
- 逐列：market、symbol、trade_date、`fetched_at`（DB 原值）、收盤時刻（UTC）、`is_latest_bar`、該 symbol 最新 trade_date、source。
- 我多加了 `source` 欄（取自表上的欄位），因為風控提到 US 備援 yfinance 是最可能來源。
- 不印結論或建議。

**無法判定的列**
- 另列一個區塊，原值照印，不略過也不猜。
- 原因分四種：`unknown_market`、`unparseable_trade_date`、`unparseable_fetched_at`、`timezone_naive_fetched_at`。

**執行方式**
- DB 路徑：`--db-path`，其次環境變數 `STOCK_DESK_DB_PATH`，最後預設 `./data/stock-desk.db`。
- 退出碼：0 成功（含 0 筆）；2 表示讀不到 DB 或沒有 `price_bars_cache` 表。
- 只用標準函式庫，不 import `app.*`。

## 品質檢查
**時區處理**
- 用 `zoneinfo`，每列依自己的 `trade_date` 呼叫 `datetime.combine(date, close, tzinfo=ZoneInfo(...)).astimezone(UTC)`，沒有寫死任何 UTC 偏移。
- US 結果隨 DST 變動：夏令 20:00Z、冬令 21:00Z。
- `fetched_at` 帶非 UTC 偏移（例如 `+08:00`）時，用瞬間比較。
- 時區 naive 的 `fetched_at` 不比較，歸入無法判定。
- 時間規則常數（時區、收盤時刻）有測試對照 `app/data/freshness.py` 的 `policy_for`，兩邊不一致測試會失敗。

**唯讀保證**
- `mode=ro` 加 `PRAGMA query_only=ON`；檔案不存在就拒絕，不會新建。
- 整個執行只送一條 SELECT，不讀價格欄位。測試用 trace 驗證。
- 在 SQLite 本身的限制上：讀 WAL 模式 DB 時，旁邊可能出現空的 `-wal` / `-shm` 輔助檔。我實測確實出現了。DB 檔的 SHA-256 不變，`-wal` 大小為 0。說明文件已寫明，並建議對複本執行。

## 降級策略
- 讀不到 DB 或表不存在：stderr 印原因，exit 2。
- 部分列無法判定：計數與逐列都印出，不影響其他列。

## 驗證結果

**測試名稱**（`tests/test_unfinished_bar_probe.py`，共 29 個）
- 殘留判定
  - `test_tw_and_us_each_have_one_listed_row_and_one_normal_row`（TW、US 各一列殘留與一列正常）
- 臨界
  - `test_fetched_exactly_at_the_close_is_not_listed`（TW、US 兩個參數）
  - `test_one_second_either_side_of_the_close`（TW、US 兩個參數）
- DST
  - `test_us_close_follows_daylight_saving_time`：參數是 2026-03-06（春季轉換前，EST）、03-09（轉換後，EDT）、10-30（秋季轉換前，EDT）、11-02（轉換後，EST）
  - `test_a_fixed_offset_would_misjudge_the_hour_between_the_two_us_closes`
  - `test_tw_close_does_not_move_across_the_year`
- 時區與規則對照
  - `test_fetched_at_with_a_non_utc_offset_is_compared_as_an_instant`
  - `test_probe_rule_constants_match_the_data_service_session_policy`
- 最新一根標記
  - `test_latest_bar_flag_separates_the_newest_bar_from_a_historical_one`
  - `test_counts_split_latest_and_not_latest_per_market`
- 無法判定的列與輸出
  - `test_unjudgeable_rows_are_reported_with_their_stored_values`
  - `test_output_lists_every_requested_field_and_states_no_conclusion`
  - `test_only_the_selected_columns_are_read_and_no_price_value_is_printed`
- 空表與路徑錯誤
  - `test_empty_table_prints_zero_counts_and_exits_zero`
  - `test_db_path_comes_from_the_environment_variable_and_the_argument_wins`
  - `test_missing_db_is_refused_and_not_created`
  - `test_db_without_the_table_exits_two`
- 唯讀保證
  - `test_writing_through_the_probe_connection_fails`：INSERT、UPDATE、DELETE、CREATE、DROP 五個參數。每個都在 `query_only` 開啟時失敗；把 `query_only` 關掉後，因為 `mode=ro` 仍然失敗。
  - `test_a_run_leaves_the_database_file_and_its_directory_unchanged`
  - `test_the_only_sql_issued_is_one_select_and_the_query_only_pragma`

測試只用 `tmp_path` 內經真正的 `PriceBarCache` 建立的合成 DB；沒有碰真實 `*.db`，沒有讀 `.env`。

**CI 原文（`apps/stock-desk/backend`，在 767c524 上）**
```
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
441 files already formatted
$ uv run mypy app tests
Success: no issues found in 435 source files
$ uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q
TOTAL                                       19140    500    97%
Required test coverage of 90% reached. Total coverage: 97.39%
8115 passed, 2 xfailed, 18 warnings in 1574.64s (0:26:14)
```
我另外在合成 DB 上手動跑過一次 CLI，輸出格式符合上述描述。

**CEO 執行說明重點**
- 腳本唯讀、不會改資料；也寫明不做清理。
- 停哪些程序：建議（非必要）停後端 API（`uvicorn app.main:app`）和排程（`python -m app.scheduler`），讓輸出是靜止快照。
- 指令：用 `git worktree add` 取得分支，再 `uv run python scripts/unfinished_bar_probe.py`。
- 請 CEO 回傳：輸出全文、`git rev-parse HEAD`，以及執行前後是否動過 DB。
- 文件裡有寫「這份輸出不能做什麼」，例如看不出 close 值是否與最終收盤價不同。

## 備註
- 本機 `.venv` 是 Python 3.13，CI 用 3.12。腳本沒用 3.13 專屬語法，CI 設定檔也沒改。
- 沒有任何東西寫進真實 DB。實際檢測要由 CEO 在存有 `stock-desk.db` 的機器上跑。
- 後續交給 qa-reviewer 審查。
