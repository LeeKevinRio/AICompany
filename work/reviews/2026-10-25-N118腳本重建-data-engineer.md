# N-118 唯讀查證腳本重建（容器替換後）

- 審查者：data-engineer
- 日期：2026-10-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

1. 已重建兩個檔，都是 untracked，**沒有 commit、沒有跑任何 git 寫入指令**（只用了 `git status --short`）。
   - `/home/user/AICompany/apps/stock-desk/backend/scripts/n118_dividend_persistence_probe.py`
   - `/home/user/AICompany/apps/stock-desk/backend/tests/test_n118_dividend_persistence_probe.py`
2. 這兩個檔是依你給的兩份交件和 CEO 執行說明重寫的，不是還原，所以**不是逐字相同**。
   - 設計、輸出段落、結論格式欄位、固定句、PROPOSED 門檻，都照交件。
   - 兩條 SELECT、`mode=ro` 加 `PRAGMA query_only=ON`、`--db-path` 與環境變數備援、`--detail`、exit 0/2，都與 CEO 說明一致。
3. 全綠：ruff check、ruff format --check、mypy app tests、新測試 21 個、全套 pytest（7173 passed，2 xfailed，覆蓋率 97.29%）。B1 沒有造成失敗，所以沒有另跑 `--ignore` 版本。
4. 絕對沒碰：真實 `*.db`（連 stat 都沒做）、`.env`、網路。沒動 B1（`app/forecast/`、`app/outlook/`、`app/ops_alert/`、`tests/test_forecast_*` 等）和 ADR-0027。

## 二、各部門回報（與上次的差異）

**腳本行為（與 CEO 執行說明一致）**
- 只用標準函式庫，不 import `app.*`。
- 檔案不存在就拒絕（exit 2），不會新建。
- 只選 `pit_snapshot_runs` 與 `pit_dividend_announce_rows` 的 `(content_hash, key, symbol, ex_date)`，不選 `raw_json`，不選名稱。
- 預設只輸出彙總計數。`--detail N` 才列最多 N 筆 vanished 事件（代號、除息日、run id）。
- 腳本只印數字，不做成立／不成立判定。
- 輸出段落：Sample、(c) Persistence classes（closed/open）、(c) Run-to-run drops、(c) row_count change、(e) row_count vs rows stored、Suggested reading thresholds（標 PROPOSED，門檻 30／20／3／0.10）、Conclusion-format fields。
- 最後印固定句「樣本不足或未完成一律視為不成立；成立與否須送風控確認。」，後面接一行英文對照。
- 事件分類：`persistent`、`vanished_gone`（含 `reschedule_candidate`、`symbol_relisted_existing`、`symbol_gone`）、`vanished_returned`、`single_observation`、`first_seen_on_or_after_ex`。
- 事件比較用 `session_date`，不比較 `recorded_at`。

**與上次不同或需你確認的地方**
1. **`TAIL_GAP_DAYS`（持續列出但最後一個 ok run 離除息日多遠才算尾段沒觀察到）取 7 天。**
   - 交件自相矛盾：設計段寫 3 天，示範輸出的註記寫 7 天。我取後者，因為它描述的是實際輸出。
   - 此值是腳本頂端的具名常數，改一個數字即可。請 coordinator 或 quant 確認。
2. **測試 21 個，上次是 19 個。**
   - 多的是「只有兩條 SELECT、不含 `raw_json`」和「只用標準函式庫」兩個守則測試。
   - 其餘涵蓋交件列的情形：消失、再出現、改期、key 重複、open、單次觀察、failed run、stored>row_count 與其他異常、分位數與最大跌幅、少於 2 個 run、結論欄位與固定句、byte 不變且寫入被拒、不存在的檔、無 run 的 DB、環境變數備援。
3. **新增的異常分類。** stored>row_count、有 hash 但 stored==0、ok 但 hash 為 NULL、ok 但 row_count<=0，各自獨立計數並列 run id，不併入撞號。
4. **未重現的部分。**
   - 交件只提過示範輸出的節錄，沒有逐字格式規格。
   - 欄位標籤的對齊寬度和部分標籤字面，是我依示範節錄重寫的，可能與你上次看到的輸出有些微差異。
5. **端到端測試**用真正的 `_fetch_dividend_announce`（`httpx.MockTransport`）、`capture_once`、`MarketPanelStore`，DB 在 `tmp_path`。
   - 5 列 payload 中 1 列無 Code，3 列 strip 後同 key。結果是解析 4 列、寫入 2 列，差額 2，與上次一致。
   - 該測試要求 `monkeypatch.setenv("FINMIND_API_TOKEN", "test-token-not-a-secret")`，屬假值。

**自建假 DB 示範**
- 在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118fake/demo.db` 跑過 `--detail 5`，exit=0，輸出符合上述段落。這個假 DB 是用 `MarketPanelStore` 自建的，不是真實資料。

## 三、驗證（皆在 `apps/stock-desk/backend`，指令與結果原文）

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
416 files already formatted

$ .venv/bin/mypy app tests
Success: no issues found in 411 source files

$ PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_n118_dividend_persistence_probe.py -q -p no:cacheprovider
21 passed, 1 warning in 6.51s
```
（1 個 warning 是 `fastapi/testclient.py` 的 Starlette 對 `httpx` 的棄用警告，與本案無關。）

全套（CI 指令，加 `-p no:cacheprovider`、`PYTHONDONTWRITEBYTECODE=1`）：
```
$ PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
TOTAL                                       18550    502    97%
Required test coverage of 90% reached. Total coverage: 97.29%
7173 passed, 2 xfailed, 18 warnings in 883.56s (0:14:43)
exit=0
```
輸出存在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118fake/full_run2.txt`。

**過程中的兩個狀況**
- 第一次 mypy 報一個錯：`tests/test_n118_dividend_persistence_probe.py:355: Need type annotation for "contents"`。已補型別標註，上面的 mypy 是修好後的結果。
- 第一次全套（6803 passed，覆蓋率 94.26%）跑的時候，B1 的 `app/` 檔已在，但 B1 的測試還沒進來，所以覆蓋率偏低。dev-lead 之後把 6 個 `tests/test_forecast_*` 等測試放進來（git 顯示為 `A`，已暫存，不是我暫存的），我在 B1 測試到齊後重跑了一次，就是上面的結果，全部通過。B1 仍在變動，數字會隨之變。

**沒做**
- 沒有讀、開、查詢任何真實 DB，沒有取 sha256。
- 沒有量測真實的持續性或撞號發生率。
- 沒有送 qa-reviewer 審查。

## 四、下一步

1. **coordinator**
   - 兩個新檔送 qa-reviewer（含 Codex）審查，通過後再 commit。我沒有 commit。
   - 若 `TAIL_GAP_DAYS` 要改回 3，或有其他欄位標籤要與上次輸出完全一致，告訴我，我改。
2. **quant／風控**：確認 30／20／3／0.10 這四個建議值；確認前腳本只印數字。
3. **CEO**：照 `work/research/N118-除權息預告表持續列出與row_count查證-查證指令-2026-10-24.md` 在本機執行並貼回 stdout。若 `vanished_*` 大於 0，再跑 `--detail 30`。
4. **tech-architect**：CEO 輸出回來之前，限制 c 維持未驗證，樣本不足視為不成立。
