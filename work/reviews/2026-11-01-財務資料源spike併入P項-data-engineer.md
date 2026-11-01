# 財務資料源 spike 併入 ADR-0038 P 項

- 審查者：data-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

ADR-0038 的 P-1～P-9 與 P-12 都併進 spike 腳本和 CEO 文件了，已 push 到 `origin feat/stock-desk-fundamentals-spike`，後端 CI 全綠。腳本仍然只讀、不碰 DB、不寫檔、請求總數有上限；沒有 merge product，工作樹已移除。

**請求數**
- 上限從 20 改為 30，仍由程式內強制。
- 沒填持股時正常 22 次。
- 最壞 26 次：填滿 3 檔持股，加上 SEC 對照檔第一個路徑失敗。
- P 項的判定不另外發請求，全部由 SEC 那幾次回應算出來。

**所有判定都來自假回應**
- 沒有任何真實的 SEC 回應，所以 P 項的結論要等 CEO 在本機跑完才有。
- 我手上能給的，只有「每一項輸出什麼就代表成立或不成立」的判讀規則。
- 沙盒的 Python 是 3.11，`uv` 實際用 3.13，CI 指定 3.12；我沒用 3.12 實跑，風險低。

**我自己加的判斷，請 tech-architect 確認**
- 「原始年報保留」門檻：已結束滿一年以上的年度中，最早一筆在期末後 130 天內申報的比率，90% 以上算成立，50%～90% 算部分成立，低於 50% 不成立。
- P-7 只給量測值，沒有成立與否，門檻留給 ADR 決定（ADR 沒給數字，我不自創）。
- 「已驗證標籤」的定義：標籤最近 400 天內還在用，且至少有 3 個會計年度的全年資料。

**另外兩件事**
- Alpha Vantage 在 2026-08-16 已實測通過的說明，我保留在 CEO 文件裡。
- 文件也註記設定頁「尚未實際發送過請求」的揭露字樣可能過時，已另案追蹤。前端我沒動。
- 主 repo 工作目錄有一個不是我改的檔：`work/prd/2026-10-29-出清後回饋畫面-N164N165.md`（modified）。我沒碰，請確認是誰的。

## 各部門回報（data-engineer）

**Commit 清單**（分支 `feat/stock-desk-fundamentals-spike`，從 `origin/product/stock-desk` 9c2d705 長出，共 6 個，後 3 個是這次新增）
1. `b1efdb9` feat: 新增財務資料源 spike 腳本與測試（CEO #92）
2. `382861b` chore: .env.example 新增 SEC_USER_AGENT
3. `bdc5dd7` docs: 新增財務資料源 spike 的 CEO 本機執行指令
4. `f125ea2` feat: spike 腳本併入 ADR-0038 的 P-1～P-9、P-12 判定
5. `369335a` chore: .env.example 新增 SPIKE_US_HOLDINGS（選填，僅假值）
6. `fbe49d1` docs: spike 執行指令併入 P 項對照表與持股選填變數

六個 commit 都帶指定的兩行 trailer。

**檔案**（相對路徑）
- `apps/stock-desk/backend/scripts/fundamentals_spike.py`
- `apps/stock-desk/backend/tests/test_fundamentals_spike.py`
- `apps/stock-desk/.env.example`
- `work/research/財務資料源spike-執行指令-2026-11-01.md`

**新增的 SEC 請求**
- AAPL 申報清單（submissions）1 次，再帶 ETag／If-Modified-Since 重發 1 次。若第一次回應沒有這兩個標頭，重發會省略。
- 外國發行人樣本 TSM 的 companyfacts 1 次。
- ETF 樣本 SPY 的申報清單 1 次、companyfacts 1 次。
- SEC 存取規範頁面 1 次。
- 可選環境變數 `SPIKE_US_HOLDINGS`：最多 3 檔持股，每檔 1 次 companyfacts。
- 白名單新增營收、淨利、稀釋後每股盈餘；移除每股股利標籤。

| 來源 | 正常請求數 |
| --- | --- |
| SEC | 10（最壞 14） |
| TWSE | 4 |
| TPEx | 3 |
| FinMind | 4 |
| Alpha Vantage | 1 |
| 合計 | 22（最壞 26，上限 30） |

**P 項對照表**（判定詞：HOLDS 成立／NOT_HOLD 不成立／PARTIAL 部分成立／MEASURED 只量測／INCONCLUSIVE 資料不足）

| P 項 | 輸出怎麼判 | 成立 | 不成立或其他 |
| --- | --- | --- | --- |
| P-1 | 8 欄位占比、flow fact 的 `start` 占比、一份申報是否對應多組 `fy`／`fp` | 8 欄每筆都有且 `fy`／`fp` 是申報層級 | `PARTIAL`：只有 `frame` 不是每筆都有。`NOT_HOLD`：缺 `accn` 或 `filed`，或同一份申報有多組 `fy`／`fp` |
| P-2 | 同一期間被幾份申報報過、原始 10-K 保留比率、重編例子 | 保留 90% 以上 | `PARTIAL` 50%～90%。`NOT_HOLD`：無重複期間或低於 50% |
| P-3 | 每個項目 `n/N` 家有已驗證標籤、是否用替代標籤 | 全部項目、全部公司都有 | `PARTIAL`：有缺口，缺的項目會列出。`NOT_HOLD`：某項所有公司都沒有 |
| P-4 | AAPL、BRK.B、GOOG、GOOGL、SPY、TQQQ 的 CIK 查詢與寫法、共用 CIK 數、SPY companyfacts 狀態 | BRK.B 照原樣查得 | `PARTIAL`：只有 BRK-B 查得到，要做代號正規化。`NOT_HOLD`：AAPL 或類股都查不到 |
| P-5 | 官方頁面寫的上限、狀態碼分布、限流標頭 | 讀到上限且 ≤4 次／秒沒被 403／429 | `NOT_HOLD`：被擋。`INCONCLUSIVE`：讀不到上限 |
| P-6 | 申報清單欄位、帶 ETag 重發是否回 304、companyfacts 落後申報清單幾天（單次快照） | 欄位齊且 304 | `PARTIAL`：欄位齊但重發回 200。`NOT_HOLD`：缺欄位 |
| P-7 | 各 issuer 解壓縮後與壓縮傳輸大小 | 只給 `MEASURED` 和數字 | 門檻由 ADR 決定 |
| P-8 | AAPL 與 SPY 的 `sic`、`entityType`、`category` | 公司有且與 ETF 不同 | `PARTIAL`：都有但相同。`NOT_HOLD`：公司缺 |
| P-9 | `fiscalYearEnd` 與 companyfacts 最新全年期間的月份 | 有且月份一致 | `PARTIAL`：月份不一致或無資料可對照。`NOT_HOLD`：沒有 |
| P-12 | 每家公司的 IFRS 與非美元單位 | 注意方向：`HOLDS`＝有這類公司，要走 `source_unavailable` | `NOT_HOLD`：填的持股沒有。`INCONCLUSIVE`：沒填持股，只能看 TSM 樣本 |

P-12 的限制：腳本不能讀 DB，所以「持股」改成 CEO 用環境變數 `SPIKE_US_HOLDINGS` 自己填。

**我在寫的過程中修掉的兩個判定 bug**
- P-9 原本把 dei 流通股數的封面日期當成年度結束日，已限定只看全年期間資料。
- 測試夾具原本讓重編資料落在不會同時出現在兩份申報的期間，已修。

**CEO 文件更新**
- 請求數表與上限。
- `SPIKE_US_HOLDINGS` 的用法和清除指令。
- 新增「P 項對照表」與 SEC 新行的白話說明。
- 版本核對值更新為腳本最後修改 commit `f125ea2b29cee5fdf2c7101c8fd74f5107d3a339`，腳本 `script_sha256_lf` 為 `5fd195028a1ee1c404c31b36ae8d705e7deed161a1b6ad3e124b10af9ebc3daf`。
- 文件不含真實 email：只有 `Your Name your@email.com` 這類範例，且用 `git check-ignore` 確認不被忽略（exit 1）。

## 驗證

CI 原文摘錄（工作樹，以 `Popen(start_new_session=True)` 啟動的 runner 跑，有 `__main__` guard）：
```
##### ruff check: exit 0   All checks passed!
##### ruff format: exit 0  465 files already formatted
##### mypy strict: exit 0  Success: no issues found in 457 source files
##### pytest: exit 0
TOTAL 19716 503 97%
Required test coverage of 90% reached. Total coverage: 97.45%
8972 passed, 2 xfailed, 34 warnings in 871.43s (0:14:31)
```

- 新測試檔 93 項（上次 54 項）。
- 加 `--cov=scripts` 另量，腳本本身約 99%；CI 的覆蓋率只算 `app`。
- 每個 P 項的成立、部分成立、不成立、資料不足分支都有測試。
- 另有以下測試：
  - 重發請求確實帶了第一次回應的 ETag。
  - 304 在真實傳輸層下的行為。
  - 回應標頭只保留驗證器、大小與限流欄位，不留 cookie 與授權標頭。
  - 持股清單解析（上限 3、去重、拒絕不合法代號）。
  - 持股代號不在對照檔時會明確回報。
  - 未設 SEC 時 P 項標為跳過，不憑空判定。
  - 429 時 P-5 判不成立。
- 原始碼斷言仍成立：無 `sqlite3`、不 import `app`、只 import 標準函式庫、無檔案寫入、唯一的檔案讀取是讀自己、只有 GET、無 email 與金鑰字面值。
- 輸出遮蔽測試仍成立：完整跑一遍（含持股）後，輸出不含任何假金鑰或假 email，同時確認它們確實被拿去發請求。

## 下一步

1. coordinator 送 **qa-reviewer** 審查（含 Codex 第二意見），通過才交 CEO。
2. 請 qa-reviewer 特別看三處：
   - P-1／P-2／P-9 的判定邏輯，包括上述「我自己加的判斷」的門檻。
   - 腳本由 20 提高到 30 的請求上限。
   - 這份文件請求 CEO 把自己的持股代號放進環境變數，是否需要風控或隱私把關。
3. CEO 照 `work/research/財務資料源spike-執行指令-2026-11-01.md` 在有網路的 Windows 機器跑一次，把 `== 5. ADR-0038 P items` 與 `== Summary ==` 兩段貼回（最好完整輸出）。建議同時填 `SPIKE_US_HOLDINGS`，否則 P-12 只能是 `INCONCLUSIVE`。
4. 輸出回來後，由我整理 P 項實測結果交 **tech-architect** 修訂 ADR-0038，再送 CEO 核可。
5. 風險提示：若 P-1 出現 `NOT_HOLD`（缺 `accn` 或 `filed`），是結構性問題，ADR 要先修訂才能開工 F1。
