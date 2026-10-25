# N-118 腳本依登記門檻改寫與 CEO 執行說明改字

- 審查者：data-engineer
- 日期：2026-10-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

1. 已在現有 working tree 上一次改齊。coordinator 的兩則要求都做了：先是 qa 小修，後是風控 2026-10-25 登記的判讀規則（依該檔第二節第 2～4 點）。**沒有 commit，沒有跑 git 寫入指令**（只讀了 `git status --short`）。
2. CI 全綠，原文在第三節。全套 pytest 7194 passed、2 xfailed、覆蓋率 96.94%；新測試 42 個，上一輪是 21 個。
3. 關於 coordinator 中途補充的「TAIL 3、60／60、改量提前消失」那則，先前說「門檻常數先不動」。風控登記檔隨後到達，明確要求改，所以我照風控檔把常數改為登記值，兩則不衝突。
4. 這份工作在風控定案之前不在 commit 內，需 qa-reviewer 重審。
5. **有一處我讀字句後選了較嚴的讀法，請風控或 coordinator 確認，這算「定義偏離」的候選：**
   - 風控輸入完整性第 6 項「同一個 session 有多個 ok run」。
   - 我改成數**所有**有 `session_date` 的 ok run（含不可用者）。原本只數可用 run。
   - 理由：字句是「同一個 session 有多個 ok run」，沒有限定可用；不可用的 ok run 可能正好是有缺口的那批。
   - 影響：只會讓步驟 1「輸入完整性」更容易命中，方向較嚴。
6. 其餘定義（未到期 key、提前消失、可檢驗對、整批掉出對、尾段間隔、M、未解釋消失）都逐字照風控第 3 點實作，沒有偏離。

## 二、各部門回報

### 變動清單（腳本 `/home/user/AICompany/apps/stock-desk/backend/scripts/n118_dividend_persistence_probe.py`）

**qa 小修**
- `open_read_only` 在 `PRAGMA query_only=ON` 失敗時關閉連線再重拋。
- 標籤改為「share of the largest-by-rows drop」，並新增「同時滿足兩條件的對數」，事件層級與 `row_count` 層級各一個。
- Conclusion-format fields 補印 `events_closed`。

**風控登記（required）**
- 常數逐字照第 2 點，註解標 `REGISTERED 2026-10-25, risk control`：
  - `TAIL_GAP_DAYS=3`
  - `MIN_DISTINCT_SESSIONS=60`
  - `MIN_TESTABLE_CLOSED_TAIL_COMPLETE=60`
  - `MIN_INFORMATIVE_PENDING=30`
  - `MIN_INFORMATIVE_PAIRS=60`
  - `MIN_BATCH_DROP=3`
  - `MIN_DROP_SHARE=0.10`
  - `RUN_GAP_DAYS=4`（註明 descriptive only）
- 比率比較用精確整數運算：`share_at_least` 由 `Fraction("0.1")` 推導，等價於 `10 * lost >= pending`，無浮點邊界。
- 尾段間隔擴及三個可檢驗類別（`persistent`、`vanished_gone`、`vanished_returned`）。新增輸出：
  - M（closed、尾段間隔 ≤ 3）
  - 可檢驗 closed 中尾段間隔 > 3 的事件數
  - 相鄰對總數
  - N_pair（前一個 run 未到期 key ≥ 30）
- 「Suggested reading thresholds」整段移除，換成「Registered reading rule (risk control 2026-10-25)」：
  - 五步依序列出，每步印數字與 met / not met。
  - 第 5 步只寫「decided by risk control from the numbers above」。
  - 步驟 2 的整批掉出指向「同時滿足 ≥ 3 與 ≥ 0.10 × 未到期的對數」，不是最大掉出那一對。
  - 反例為 `vanished_returned` 的 closed 加 open 合計。
  - 腳本**不印最終結論字樣**，不印 `holds`／`does not hold`／`PROPOSED`。固定句與英文對照句保留。
- Conclusion-format fields 補印：
  - S、`session_date` 期間、N_pair、相鄰對總數、M
  - `events_closed`
  - `vanished_returned`（closed 加 open）
  - 整批掉出對數、未解釋消失數、`reschedule_candidate`（closed）
  - 3/N_pair、3/M，標「zero counter-examples only」
- 原始 `row_count` 段改標 `(descriptive)`，並加一行「不構成判讀門檻」。
- 事件層級的「Run-to-run drops」段改名為「Early disappearance between adjacent usable ok runs (registered measure)」。

### 測試（`/home/user/AICompany/apps/stock-desk/backend/tests/test_n118_dividend_persistence_probe.py`）

風控要求的四組邊界與 qa 補件：
- 尾段間隔 3 天計入 M、4 天不計；三類事件（`persistent`、`vanished_gone`、`vanished_returned`）各一。
- 未到期 key 29 不算可檢驗對，30 算（含 31）。
- 提前消失 3 筆占 0.10 算整批掉出對，2 筆不算；另含 (31,3) 不算、(29,3)／(20,3) 算，並確認所有相鄰對都計入，不限可檢驗對。
- open 的 `vanished_returned` 被計數，且步驟 2 顯示 met。
- 輸入完整性六項與未解釋消失的回報。
- 常數與風控第 2 點逐字相符，輸出不含 `holds`／`does not hold`。
- rule of three 的 3/N_pair 與 3/M 數值。
- qa 補件：`unparsed_keys`、`distant_run_pairs` 數值、`events_censored`、`+N more`、收緊 reappearance 斷言（`drop_episodes == 1`、`largest_drop_share == 1.0`）、`open_read_only` 在 PRAGMA 失敗時關閉連線。
- 舊的 7／8 天尾段測試已被 3／4 天取代。

### CEO 執行說明改字（old → new，交回文字，我沒有改該檔）

檔案：`/home/user/AICompany/work/research/N118-除權息預告表持續列出與row_count查證-查證指令-2026-10-24.md`

**改字 1，第一節第 2) 點**

old：
```
# 2) 選用：只在第 (c) 段 vanished_gone 或 vanished_returned 大於 0 時再跑，
#    最多列 30 筆消失的事件（代號、除息日、run id；不含名稱、價格、原始列）
uv run python scripts/n118_dividend_persistence_probe.py --db-path "$STOCK_DESK_MARKET_DB_PATH" --detail 30
```
new：
```
# 2) 選用：只在第 (c) 段 vanished_gone 或 vanished_returned 大於 0 時再跑。
#    --detail 的值要不小於 vanished 事件總數（第 1) 步輸出中 vanished_gone 與 vanished_returned
#    的 closed 加 open 合計），才能全部列出供 TWSE 公告對照
#    （代號、除息日、run id；不含名稱、價格、原始列）。下例以 200 為例，請依實際總數調整
uv run python scripts/n118_dividend_persistence_probe.py --db-path "$STOCK_DESK_MARKET_DB_PATH" --detail 200
```

**改字 2，第二節表格，Sample 列**

old：`同一 session 多個 ok run 的數量`
new：`同一 session 多個 ok run 的數量（含不可用的 ok run，屬輸入完整性條件）`

**改字 3，第二節表格，「(c) Run-to-run drops」列整列**

new：
```
| (c) Early disappearance | 相鄰兩個可用 ok run 之間：相鄰對總數、可檢驗對數 N_pair（前一個 run 未到期 key ≥ 30）、提前消失總數（前一個 run 有、後一個沒有、而且除息日晚於後一個 run 的 `session_date` 的 key）、單批最大提前消失數、整批掉出對數（提前消失 ≥ 3 且 ≥ 0.10 × 未到期 key 數，所有相鄰對都計入）。另有 M 與其補數：已結束、屬可檢驗類別（`persistent`、`vanished_gone`、`vanished_returned`）、而且**尾段間隔** ≤ 3 天的事件數，以及尾段間隔 > 3 天而不計入 M 的事件數。尾段間隔 = 除息日減去除息日前最後一個可用 ok run 的 `session_date`，以日曆天計；腳本沒有交易日曆，遇連假的事件會被排除在 M 之外（寧可少算） |
```

**改字 4，第二節表格，「(c) row_count change」列句末加**

new 句末加：`標為 descriptive，不構成判讀門檻。`

**改字 5，第二節表格，「Suggested reading thresholds」列整列**

new：
```
| Registered reading rule | 風控 2026-10-25 登記（`work/reviews/2026-10-25-N118判讀門檻確認-風控.md`），執行前定案，執行後不得更動。依序四步，每步印出數字與 met / not met：(1) 輸入完整性：`stored > row_count`、有 hash 但 `stored == 0`、ok 但 hash 為 NULL、ok 但 `row_count <= 0`、ok 但不可用、同一 session 多個 ok run，任一大於 0；(2) 反例：`vanished_returned`（closed 加 open）≥ 1，或整批掉出對 ≥ 1；(3) 樣本：S < 60、N_pair < 60 或 M < 60；(4) 未解釋消失：已結束的 `symbol_gone` 加 `symbol_relisted_existing` ≥ 1。第 5 步（以上皆未命中）與最終結論由風控依數字判讀，**腳本不印最終結論** |
```

**改字 6，第二節表格，「Conclusion-format fields」列整列**

new：
```
| Conclusion-format fields | 供風控確認用：依據的可用 ok run 數、S（不同 `session_date` 數）與期間、N_pair 與相鄰對總數、M、已結束且可檢驗的事件數、`events_closed`、`vanished_returned`（closed 加 open）、整批掉出對數、未解釋消失數、`reschedule_candidate`（closed）、3/N_pair 與 3/M（零反例時單次回應不完整機率的 95% 上界，**僅零反例時有意義**）、執行日期（取自執行機器的 `date.today()`）；並固定印「樣本不足或未完成一律視為不成立；成立與否須送風控確認。」 |
```

**改字 7，第三節「請 CEO 回傳」**

old：`3. 若有 `vanished_*` 事件，是否知道原因（例如該日 TWSE 預告表改版、更正、公告撤銷）。`
new：同一行，其後新增一點：
`4. 執行時 repo 的 commit：在 repo 目錄執行 `git rev-parse HEAD`，把輸出貼回，用來核對跑的是已登記常數的版本。`

**改字 8，第四節末點**

old：`- 成立與否由風控確認；樣本不足或未完成一律視為不成立。建議值未經確認，不得當作已核可的門檻。`
new：`- 成立與否由風控確認；樣本不足或未完成一律視為不成立。門檻已於 2026-10-25 由風控登記（`work/reviews/2026-10-25-N118判讀門檻確認-風控.md`），執行後不得更動。`

## 三、驗證（皆在 `apps/stock-desk/backend`，指令與結果原文）

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
416 files already formatted

$ .venv/bin/mypy app tests
Success: no issues found in 411 source files

$ PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_n118_dividend_persistence_probe.py -q -p no:cacheprovider
42 passed, 1 warning in 1.23s
```

全套，執行一次：
```
$ PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
TOTAL                                       18550    567    97%
Required test coverage of 90% reached. Total coverage: 96.94%
7194 passed, 2 xfailed, 18 warnings in 898.33s (0:14:58)
exit=0
```
輸出存在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118fake/full_run4.txt`。

- 全套覆蓋率 96.94%，上一輪是 97.29%。降幅來自 B1 與其他人新增程式，不是這次的檔案。
- B1 在本次執行時測試已到齊且全過，所以沒有另跑 `--ignore` 版本。
- 中途曾 `pkill` 掉一次舊版全套，因為腳本隨後大改，該次結果作廢。

**沒做**
- 沒有讀真實 `*.db`，沒有讀 `.env`，沒有打網路。
- 沒有動 B1、ADR、事先宣告。`git status` 中 ADR-0027 的 ` M` 是 tech-writer 的改動，與我無關。
- 沒有改 CEO 執行說明檔，只交回上述改字。
- Codex 第二意見仍依 CEO #53 在合併前補跑，不是我能做的。

## 四、下一步

1. **coordinator**
   - 把兩個檔送 qa-reviewer 重審。對照三件事：常數與風控第 2 點逐字相符、規則段與第 3 點一致、四組邊界測試存在。審過後 commit。
   - 套用上面八處 CEO 執行說明改字。
2. **風控／coordinator**：確認第一節第 5 點。「同一 session 多個 ok run」我數所有 ok run，若要只數可用 run，改一行即可。
3. **CEO**：待上述完成後，用已登記版本執行，回貼 stdout 與 `git rev-parse HEAD`。
4. **tech-architect**：CEO 輸出回來、風控確認之前，(c) 維持未驗證。
