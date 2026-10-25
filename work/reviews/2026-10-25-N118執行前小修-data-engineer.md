# N-118 CEO 執行前最後小修

- 審查者：data-engineer
- 日期：2026-10-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

最後三處小修已完成，只改了兩個檔，沒有 commit，沒有跑 git 寫入指令。常數、定義、判讀邏輯都沒動。CI 全綠，新測試 42 passed（與上一輪個數相同，因為都是改既有斷言）。

## 二、各部門回報（變動清單）

腳本：`/home/user/AICompany/apps/stock-desk/backend/scripts/n118_dividend_persistence_probe.py`
1. 步驟 3 的輸出標籤由「3 sample size」改為 `3 sample insufficient`。
   - met 表示樣本不足。
   - 括號末尾由「met when any is below」改為「met = insufficient, i.e. any is below」。
2. module docstring 第 6～9 行：
   - 原「at most 30 events」與「--detail 30」已拿掉。
   - 現在寫成「`--detail` 的值不小於 vanished 事件總數（closed 加 open），才能全部列出供 TWSE 公告對照」。範例指令改為 `--detail 200`。
   - 與 CEO 執行說明同義。
3. 原始 row_count 段標題由 `(incomplete-batch estimate)` 改為 `(descriptive)`。

測試：`/home/user/AICompany/apps/stock-desk/backend/tests/test_n118_dividend_persistence_probe.py`
- rule of three 那個測試改斷言 `3 sample insufficient: met`，並確認不是 `not met`。
- 同一測試新增兩項斷言：輸出含 `(descriptive) --`，且不再含 `incomplete-batch`。

沒碰：執行說明檔、B1、ADR、事先宣告。沒有讀真實 `*.db`、`.env`，沒有打網路。

## 三、驗證（`apps/stock-desk/backend`，原文）

```
$ ruff check .
All checks passed!
$ ruff format --check .
416 files already formatted
$ mypy app tests
Success: no issues found in 411 source files
$ pytest new
42 passed, 1 warning in 6.49s
$ git diff --stat
 .../scripts/n118_dividend_persistence_probe.py     | 260 +++++++++++++++++----
 .../tests/test_n118_dividend_persistence_probe.py  | 245 ++++++++++++++++++-
 2 files changed, 452 insertions(+), 53 deletions(-)
```
- `git diff --stat` 只限這兩檔。
- 數字是相對上次 commit（`d4d9265`）累積的全部改動，不只這三處。
- 全套 pytest 這次沒重跑，因為改動只是字樣與 docstring。上一輪全套是 7194 passed、2 xfailed、覆蓋率 96.94%。

## 四、下一步

1. **coordinator**：把這兩檔的最後改動 commit，並確認 `git rev-parse HEAD` 是 CEO 要用的版本。
2. **CEO**：用已登記版本執行，回貼 stdout 與 `git rev-parse HEAD`。步驟 3 若顯示 `met`，表示樣本不足，屬預期的 fail-closed。
