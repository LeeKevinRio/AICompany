# N-118 唯讀查證腳本進 repo 工作樹

- 審查者：data-engineer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N-118 腳本進 repo 工作樹與驗證（data-engineer，2026-10-24）

## 一、本次結論

1. 腳本與測試已放進 repo 工作樹，**沒有 commit、沒有跑 git 寫入指令**（只讀 `git status`、`check-ignore`）。
2. 風控補充的兩項已做進腳本：輸出末段有「結論格式欄位」和那句固定文字，也有相鄰 ok run 的 `row_count` 變化分布。
3. 建議值 30／20／3／0.10 在 docstring 和輸出裡都標為「PROPOSED, pending quant and risk-control confirmation」。腳本只印數字，不做成立／不成立判定。
4. 檢查全綠：`ruff check`、`ruff format --check`、`mypy app tests`、新測試 19 個、全套 pytest（7139 passed，2 xfailed，覆蓋率 97.30%）。
5. B1（dev-lead 進行中）的測試在全套裡**全部通過**，所以沒有失敗項，也不需要 `--ignore` 再跑一次。
6. 沒有動 B1 的任何檔，沒有讀真實 DB，沒有讀 `.env`，沒有打網路。

## 二、各部門回報

### 新增檔案清單（共 2 個，皆為 untracked）
- `/home/user/AICompany/apps/stock-desk/backend/scripts/n118_dividend_persistence_probe.py`
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_n118_dividend_persistence_probe.py`

`git status` 還顯示 B1 的檔案和 ADR-0027 為已暫存或已修改，那些不是我動的。

### 與先前草稿的差異
- 草稿「尚未進 repo」的說明改為正式 docstring，執行指令改成 `scripts/` 路徑，格式比照 `v1_announce_lead_probe.py`。
- 新增輸出段落：
  - 「row_count change between consecutive usable ok runs」：相鄰 usable ok run 的 `row_count` 差值，印最小值、p25、中位數、p75、最大值（nearest-rank 分位數），最大跌幅（列數與占前一個 `row_count` 的比例），以及跌幅比例不低於 0.10 的組數。段尾註明 `row_count` 會因合法原因變動（事件過除息日、新事件出現）。
  - 「Suggested reading thresholds」：四個建議值，明寫「This script does not judge」。
  - 「Conclusion-format fields」：依據的 usable ok run 數、其中不同 `session_date` 數、closed testable 事件數、執行日期（`date.today()`，印的是執行機器的日期）。最後固定印「樣本不足或未完成一律視為不成立；成立與否須送風控確認。」加一段英文對照。
- 新增 3 個測試：分位數與最大跌幅、少於 2 個 run 時為空、結論格式欄位與那句固定文字。
- 原有的一個測試原本禁止輸出出現 "does not hold"，與風控要求的英文對照句衝突，已改成只禁止 "verdict" 與 "refuted"。

### 在示範假 DB（自建，scratchpad）上的新段落輸出
```
-- (c) row_count change between consecutive usable ok runs (incomplete-batch estimate) --
consecutive pairs                          : 5
delta min / p25 / median / p75 / max       : -3 / -1 / -1 / -1 / 1
largest drop (rows)                        : 3
largest drop share of previous row_count   : 0.750
pairs with drop share >= 0.10 (PROPOSED)    : 4
-- Suggested reading thresholds (PROPOSED, pending quant and risk-control confirmation) --
This script does not judge. Suggested values, not approved rules:
  sample adequacy   : testable closed events >= 30
                      and usable ok runs >= 20
  counter-example   : any vanished_returned closed event
  whole-batch drop  : largest drop in one pair >= 3 and share >= 0.10
-- Conclusion-format fields (for the risk-control confirmation) --
usable ok runs the reading rests on        : 6
distinct session_date among them           : 6
closed testable events (>=2 runs)          : 6
run date (date.today() on the executing machine): 2026-10-24
樣本不足或未完成一律視為不成立；成立與否須送風控確認。
```

### CEO 執行說明檔內容（請放 `work/research/`，建議檔名 `N118-除權息預告表持續列出與row_count查證-查證指令-2026-10-24.md`）

```markdown
# N-118 查證指令：除權息預告表是否在除息日前持續列出事件，以及擷取紀錄 row_count 是否與實際寫入列數一致（給 CEO 本機執行）

- 日期：2026-10-24
- 對應：後續追蹤清單 N-118（ADR-0027 D-3「晚到資料的觸發」第 10 點 (10) (c)、(e)）；風控單項確認 `work/reviews/2026-10-24-N17因子修訂觸發單項確認-風控.md`
- 腳本：`apps/stock-desk/backend/scripts/n118_dividend_persistence_probe.py`
- 性質：唯讀離線查證，不屬持倉資料鏈（ADR-0012 C-7）。本雲端環境沒有市場 DB 的真實資料，**必須在存有市場 DB 的機器上跑**。不需網路、不涉祕密、不需付費。

## 一、怎麼跑

```bash
# 路徑用變數，請依您的機器調整
REPO=<您的 AICompany checkout 路徑>
export STOCK_DESK_MARKET_DB_PATH="$REPO/apps/stock-desk/backend/data/stock-desk-market.db"   # 或您實際使用的市場 DB

cd "$REPO/apps/stock-desk/backend"

# 1) 只輸出彙總計數（請把完整 stdout 貼回）
uv run python scripts/n118_dividend_persistence_probe.py --db-path "$STOCK_DESK_MARKET_DB_PATH"

# 2) 選用：只在第 (c) 段 vanished_gone 或 vanished_returned 大於 0 時再跑，
#    最多列 30 筆消失的事件（代號、除息日、run id；不含名稱、價格、原始列）
uv run python scripts/n118_dividend_persistence_probe.py --db-path "$STOCK_DESK_MARKET_DB_PATH" --detail 30
```

- `--db-path` 省略時依序用環境變數 `STOCK_DESK_MARKET_DB_PATH`，再退回 `./data/stock-desk-market.db`。
- 檔案以 SQLite `mode=ro` 開啟並下 `PRAGMA query_only=ON`；檔案不存在就拒絕（exit 2），不會新建。只印 stdout，不寫任何檔、不改任何 DB。
- 只選 run 編號、`session_date`、`content_hash`、`row_count`、key、代號、除息日；**不選 `raw_json`、不選名稱、不讀價格**。
- 唯一副作用來自 SQLite 本身：讀 WAL 模式資料庫時，旁邊可能出現 `-wal`／`-shm` 輔助檔，資料庫檔本身位元組不變。想更保守，可先把 `.db`、`.db-wal`、`.db-shm` 三個檔一起複製到別處再跑。
- 後端服務可以照常運行，腳本只讀、不取寫鎖。
- 只用標準函式庫，不 import `app.*`。
- 退出碼：0 成功；2 表示讀不到 DB、表不存在或沒有任何 `dividend_announce` run。

## 二、輸出各段的意思

| 段落 | 內容 |
| --- | --- |
| Sample | 可用 ok run 數、不同內容數、`session_date` 範圍、同一 session 多個 ok run 的數量、相鄰 ok run 相隔超過 4 天的次數、事件數（closed／open／已在第一個 run 就列出的） |
| (c) Persistence classes | 事件分類：`persistent`（除息日前每個 run 都列出）、`vanished_gone`（消失後沒再出現）、`vanished_returned`（消失後又出現）、`single_observation`（只有一個 run，無法檢驗）、`first_seen_on_or_after_ex`（首見時已不早於除息日）。`vanished_gone` 再分改期候選、同代號還有其他既有事件、同代號完全消失。每項都分 closed／open |
| (c) Run-to-run drops | 相鄰兩個 run 之間，仍在未來的事件被丟掉的次數、單批最大掉出數與占比（暗示單批回應不完整的特徵） |
| (c) row_count change | 相鄰 ok run 的 `row_count` 差值分布（最小值、p25、中位數、p75、最大值）、最大跌幅與占比。`row_count` 也會因合法原因變動，這是估計單批不完整頻率的參考，不是結論 |
| (e) row_count vs rows stored | 各 ok run 的 `row_count` 與實際寫入列數是否一致；`stored < row_count` 代表該批有 key 撞號（同代號同日期被覆蓋）；`stored > row_count`、`stored == 0`、ok 但無 hash、ok 但 `row_count <= 0` 都屬異常 |
| Suggested reading thresholds | 建議值，**待 quant、風控確認**：樣本充足性（可檢驗且已結束的事件 ≥ 30、可用 ok run ≥ 20）、反例（任何已結束的 `vanished_returned`）、整批掉出特徵（單批掉出 ≥ 3 筆且占比 ≥ 0.10）。腳本只印這些數字，**不做成立／不成立判定** |
| Conclusion-format fields | 依據的 usable ok run 數、不同 session 數、已結束且可檢驗的事件數、執行日期（取自執行機器的 `date.today()`）；並固定印「樣本不足或未完成一律視為不成立；成立與否須送風控確認。」 |

## 三、請 CEO 回傳

1. 腳本完整 stdout（請直接貼上，不必存檔）。
2. 市場 DB 開始每日抓取的日期（若與輸出的 `session_date` 範圍起點不同，請說明）。
3. 若有 `vanished_*` 事件，是否知道原因（例如該日 TWSE 預告表改版、更正、公告撤銷）。

## 四、這份輸出不能做什麼

- 消失是被計數，不是被解釋：真撤銷與來源單批回應不完整，在 DB 內看起來一樣。要區分需要對照 TWSE 公告，由有網路的人做。
- 沒有 ok run 的交易日看不到；腳本沒有交易日曆。
- 每個 session 只保留第一筆 ok run，同一 session 內的修訂看不到。
- 沒有 `Code` 的列在擷取時就被略過，`row_count` 與寫入列數都不含它們。
- 成立與否由風控確認；樣本不足或未完成一律視為不成立。建議值未經確認，不得當作已核可的門檻。

## 五、單元測試

腳本的測試在 `apps/stock-desk/backend/tests/test_n118_dividend_persistence_probe.py`，只用 `tmp_path` 內自建的假市場 DB（經真正的 `MarketPanelStore` 寫入），不碰真實 DB、不打網路。
```

## 三、驗證（指令與結果原文，皆在 `apps/stock-desk/backend`）

**`ruff check .`**
```
All checks passed!
```

**`ruff format --check .`**
```
414 files already formatted
```

**`mypy app tests`**（CI `stock-desk.yml` 的範圍；`scripts/` 不在 mypy 範圍，只受 ruff 檢查）
```
Success: no issues found in 409 source files
```

**只跑新測試 `.venv/bin/python -m pytest tests/test_n118_dividend_persistence_probe.py -q -p no:cacheprovider`**
```
...................                                                      [100%]
19 passed, 1 warning in 5.29s
```
（1 個 warning 是 `fastapi/testclient.py` 的 Starlette 對 `httpx` 的棄用警告，與本案無關。）

**全套 `.venv/bin/python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q -p no:randomly`**（CI 的指令；我加了 `-p no:randomly`，環境未必安裝該外掛，無影響）。這是在最終版腳本與測試上跑的，輸出存在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118/full_run3.txt`：
```
TOTAL                                       18450    498    97%
Required test coverage of 90% reached. Total coverage: 97.30%
7139 passed, 2 xfailed, 1 warning in 1053.30s (0:17:33)
exit=0
```
- 覆蓋率門檻 90%，實際 97.30%。
- `app/forecast/`、`app/outlook/`、`app/ops_alert/` 的 B1 測試全部通過，所以沒有需要回報的失敗，也沒有另跑 `--ignore` 版本。覆蓋率數字含 B1 目前的程式狀態，B1 變動後會變。
- 先前還有兩次全套執行：第一次（`full_run.txt`）在最後一次修改之前，7121 passed、2 xfailed、覆蓋率 96.50%，全過；第二次被背景時間限制中止，沒有結果，已用上面第三次取代。

## 四、下一步

1. **coordinator**：
   - 把上面的 CEO 執行說明放進 `work/research/`。
   - 兩個新檔送 qa-reviewer（含 Codex）審查，審查通過後再 commit（我沒有 commit）。
   - 決策包條目的編號由您指派；條目措辭與我先前報告的草稿相同，指令改用 `scripts/` 路徑。
2. **quant、風控**：確認 30／20／3／0.10 這四個建議值，或指定其他數字；確認前腳本只印數字。
3. **CEO**：照說明檔在本機跑一次並貼回 stdout。
4. **tech-architect**：CEO 輸出回來之前，限制 c 維持未驗證，樣本不足視為不成立。
