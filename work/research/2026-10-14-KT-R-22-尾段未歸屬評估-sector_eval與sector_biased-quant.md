# KT-R-22 尾段未歸屬評估（sector_eval、research/sector_biased）— quant-researcher

> 轉存：coordinator，2026-10-14，子 agent 回報逐字轉存。只讀碼與 scratchpad 純計算重現，未改 repo。

---

## 本次結論

KT-R-22 評估完成。我只讀了程式碼，並在 scratchpad 跑了純計算重現。沒有改任何 repo 檔案、沒有 commit，也沒有碰 `*.db`、`.env`，沒有連網。

- **`sector_eval`：沒有尾段問題，不需處理。** `segment_bounds` 會把不滿一窗的尾段明確補成最後一段。主統計（p、q、Wilson、bootstrap、permutation、兩半、相位、近 12 個月）用的是全部有效週，本來就不經過折切分。
- **`research/sector_biased`：有同構的尾段未歸屬。** 最後 r = (n − 504) mod 126 根 session 裡做決策的週，不屬於 `in_sample`，也不屬於 `out_of_sample`，只計入 `full`。最多 24 個主相位週。
  - 這批輸出只寫進研究 DB，沒有任何 API 或前端使用者（Grep 確認），定位是「含已知偏誤，不得上畫面」。
  - 沒有任何字面宣稱涵蓋到最後一根，也沒有回合被錯放到別的計數。
  - **建議只做內部揭露**，不走使用者字面流程，不需要 ADR。
- 沒有 look-ahead 或樣本外污染的連帶風險，因為兩處都沒有用分段資料做任何擬合或選擇。附帶發現兩點偏離「樣本內／樣本外不混報」的地方，都在研究 DB 內，見 §3。

---

## 1. `walk_forward_splits` 所有呼叫點（Grep，排除 *.md）

折在 `splits.py:84-85` 遇到 `test_stop > n` 就停止，所以凡是直接拿 `folds[-1].test_stop` 當樣本外右界的呼叫點，都會有 r 根尾段。

| 呼叫點 | 用途 | 尾段處理〔讀碼〕 |
| --- | --- | --- |
| `app/api/backtest.py:551` | F-11 回測頁 | 有尾段，已由 KT-R-9／L-18 系列處理（原案） |
| `app/backtest/sector_eval.py:892`（`segment_bounds`） | 判定資料每 126 日分段報告 | 前面放一段虛擬訓練窗，再把結果平移回來；`:894-896` 若 `covered < n_sessions`，**補上尾段當最後一段**。沒有未歸屬 |
| `app/research/sector_biased/study.py:344` | 偏誤研究，切樣本內／外 | **有尾段未歸屬**（§2） |
| `scripts/c8_regression_comparison.py:124` | 內部腳本 | `oos=(folds[0].test_start, folds[-1].test_stop)` = (120, 3960)，r = 40〔實跑〕。產出檔 `work/C8-修復回歸對照.md:9` 寫的是「`oos`=拼接樣本外區段」，沒有宣稱涵蓋到最後一根。屬內部文件，不需處理 |
| `tests/`：`test_backtest_splits.py`、`test_backtest_report.py`、`test_backtest_wording.py`、`test_backtest_round_trip_detail.py` | 測試 | 不適用 |

`research/sector_biased/sensitivity.py:356-365` 沒有直接呼叫 `walk_forward_splits`，而是透過 `study_on_hindsight` 間接使用，所以繼承 study 的尾段行為。

## 2. 兩處逐一判斷

### 2.1 `sector_eval`（`/home/user/AICompany/apps/stock-desk/backend/app/backtest/sector_eval.py`）

**讀碼事實**
- `:32-38` 與 ADR-0012 `:1084`：判定資料整段視為樣本外，126 日分段只用來報告。
- `:1011-1019`：分段範圍是從第一個有效決策日到最後一個有效決策日；每週依決策日歸到 `[lo, hi]`。
- `:997-1009`、`:1070`：主統計直接用 `valid`，不經過分段。
- `:922-923`、`:1070`：`segments` 只存在 `SectorStatistics` 裡。全 repo（含 `app/api`、`app/sectors`、`app/services`、`frontend`）**沒有任何使用者**。依 ADR-0012 `:457`，它不進 G5，`to_stats_record`（`:1993-2027`）也沒有寫入。
- 既有測試 `tests/test_sector_eval.py:600-603` 已斷言 `segment_bounds(300) == [(0,126),(126,252),(252,300)]`。

**實跑**
- n = 1..3000：分段沒有缺口、沒有重疊，最後一段的終點恆等於 n。
- 400 組隨機日曆，照 `:1011-1019` 的歸段邏輯重現：每個有效週都恰好落在一段，違反數 0。

**推論**
- 沒有尾段未歸屬，也沒有面向使用者的影響。
- 最後 H = 5 根 session 本來就無法做決策（`:1581` 是 `range(first, len(calendar) - holding)`）。這是標籤需要 t+H 的結果，不是折切分造成的尾段；`stats_as_of = valid[-1].window.exit_date`（`:2018`）是如實的。
- 小瑕疵（選做）：`:922` 的欄位註解寫「summary over that 126-session window」，但最後一段可能短到只有 1 根 session（實跑 n = 127、253 時最後一段長度為 1）。這只是內部註解。日後如果要把分段放上畫面，必須同時顯示每段的長度與樣本數，不能統稱為「126 日段」。

### 2.2 `research/sector_biased`（`/home/user/AICompany/apps/stock-desk/backend/app/research/sector_biased/study.py`）

**讀碼事實**
- `:343-346`：`sessions` 是起始日之後的全部日曆日，用 `walk_forward_splits(len(sessions), 504, 126, step=126)` 切分。
- `:358-361`：`in_sample` 只取第一折訓練窗 `[0, 504)` 內決策的週；`out_of_sample` 取 `[504, folds[-1].test_stop)` 內決策的週。
- `:364`：連一折都切不出來（n < 630）時，全部標為 `in_sample`，`out_of_sample` 為空。
- `:389-393`：`full` 用的是全部 `main`，**包含尾段**。
- 寫入位置：`save_study` `:418-446` 寫 `research_study_runs`，`sensitivity.py:404-433` 寫 `research_sensitivity_runs`。兩張表的 segment 都限定在 `('in_sample','out_of_sample','full')`（`store.py:79`、`:103`）。
- 每列會帶 `folds`（日期）。報告層另存 `data_end`（`:397`），但它取的是 panel 內最大的 `session_date`，不保證等於 `run.calendar[-1]`（傳入 `calendar` 時兩者可能不同）。也就是說，尾段大致可以事後推算，但沒有明列。
- 可見性：`hindsight.py:20` 定義 `BIAS_LABEL = "含已知偏誤，不得上畫面"`，`tests/test_research_isolation.py:513` 有斷言這個標籤。Grep `app/api`、`app/services`、`app/sectors`、`frontend`、`scripts`，都沒有 import `app.research` 或 `ResearchStore`，**不面向使用者**。

**實跑**（H = 5，只算主相位週；輸出節錄見文末）
- 全部 n = 630..3999 都滿足 r = (n − 504) mod 126。
- 尾段週數最多 24 週（例如 n = 751、755、2645）。
- 依方法論 §5.3「2016 起約 10 年」換算 n ≈ 2450：r = 56，尾段 10 週，樣本外 378 週。

**影響**
- 受影響的輸出：只有 `out_of_sample` 列的 `sample_count`、`beat_count_*`、`base_rate_*`、metrics、`sample_end`。這些數值排除了最近 r 根的決策週。
  - `in_sample` 不受尾段影響。
  - `full` 有含尾段，所以 in_sample + out_of_sample ≠ full。
- 偏誤方向：無法判斷。被略過的是時間上最近的一段，結果取決於那段的行情，程式沒有系統性方向。
- 最大幅度：若把尾段週納入，樣本外命中率最多偏移 t / (N + t)。這是極端上界，前提是尾段每一週結果都相同。
  - n ≈ 2450：≤ 2.6 個百分點。
  - n = 1000：≤ 22.4 個百分點。
  - n = 751（只有一折）：≤ 49.0 個百分點。
  - 樣本外越短，影響越大。期望偏移遠小於上界。
- 錯放或漏算：沒有像 Kelly 那樣「錯放到另一個計數」的情形，因為這裡沒有排除計數。尾段週沒有被算進任何樣本內或樣本外計數，但有算進 `full`，也沒有任何地方宣稱 `out_of_sample` 涵蓋到最後一根。
  - `study.py:11-14` 只寫「in-sample and out-of-sample reported apart」。
  - 方法論 `work/stock-desk-族群動能-方法論.md:303` 只寫用 504/126 分開列出。
- 這個模組沒有面向使用者的字面，§5 無需交風控。

## 3. look-ahead／樣本外污染連帶風險

**讀碼加推論**
- `sector_eval`：分段只用於報告，沒有使用者，也沒有用任何分段做參數選擇。判定路徑讀的是 `panel.as_of(t)`，分段幾何不影響 point-in-time。**無風險。**
- `sector_biased`：hindsight 的已知偏誤（存活者、分類）本來就有標籤揭露，不是本議題範圍。程式沒有擬合任何東西（`study.py:13`），切分只是報告紀律，所以尾段不會造成樣本外被用於選擇。方法論 §5.4 另外規定，看過結果後才提出的版本要計入 m。
- **附帶發現（不屬尾段問題，研究 DB 內部）**
  - (a) **全樣本數字標在分段列上**。`study.py:439-445` 與 `sensitivity.py:425-433` 在 `in_sample`、`out_of_sample` 列的 `report_json` 都寫入 `report.statistics.delta_real` 和 `delta_shuffle`。這兩個值是用全部 main（樣本內 + 樣本外 + 尾段）算出來的，卻放在標為 `in_sample` 或 `out_of_sample` 的列裡。這偏離 backtest-protocol「樣本內／外不得混在一起報」的呈現要求。
  - (b) **邊界週跨段**。實跑顯示，恆有 1 個樣本內週的持有窗落進樣本外的 session；r ≥ H 時另有 1 個樣本外週的出場日落進尾段。既有測試（`test_research_isolation.py:519-523`）只要求 `in_sample.sample_end <= out_of_sample.sample_start`，這是成立的，因為出場收盤日就是下一次決策日。由於沒有擬合，這不構成污染，屬已知邊界。

## 4. 建議處置與影響範圍

| 對象 | 建議 | 理由 |
| --- | --- | --- |
| `sector_eval` | **不需處理**（可選：修正 `:922` 註解） | 沒有尾段；已有測試鎖住 |
| `sector_biased` 尾段 | **只需內部揭露**，不走 creative 或風控字面流程，**不需 ADR** | 不上畫面，也沒有宣稱涵蓋到最後一根 |
| 附帶發現 (a) | 建議與尾段揭露同批處理 | 違反「樣本內／外不混報」 |
| 改折幾何（讓最後一折吸收尾段） | **不建議** | 會改動方法論 §5.3 寫定的 504/126/126，需要方法論修訂、ADR-0012 註記與 qa 審查，成本高於效益 |
| c8 腳本 | 不需處理 | 內部腳本，文件寫法正確 |

**最小改法**（交 dev-lead 排程，不急）
1. 在 `BiasedStudyReport` 加兩個欄位，兩者都直接取自 `sessions`，不推測：
   - `oos_end`：`sessions[folds[-1].test_stop - 1]`，沒有折時為 `None`；
   - `unassigned_tail`：尾段的起訖日與 session 數。
2. 在 `save_study` 與 `save_sensitivity` 的 `report_json` 加上 `"unassigned_tail"`。**不要**新增 segment 值，否則要動 `store.py` 的 CHECK 約束並做 migration。
3. 附帶發現 (a)：把 `delta_real`、`delta_shuffle` 改放到 `report_json["full_sample"]` 底下，或只寫在 `full` 列。這會改變研究 DB 的 `report_json` 結構；這批資料沒有使用者，但要確認有沒有離線分析依賴這個 key。
4. 把 `study.py:11-14` 的模組說明補成：最後 (n − 504) mod 126 根 session 的決策週只計入 `full`。

**必要測試**
- r > 0 的 fixture，例如 `train_sessions=60, test_sessions=20`，並刻意讓 n − 60 不被 20 整除。斷言：
  - 尾段週數等於 `full` 減去樣本內與樣本外的週數；
  - `unassigned_tail` 的起訖日正確；
  - 樣本外的 `sample_start` 早於 `oos_end`。
- r = 0 的 fixture：斷言尾段為空，或依設計回傳 `None`。
- 斷言 `in_sample` 與 `out_of_sample` 列的 `report_json` 不含全樣本 delta 的頂層 key。

影響範圍只在研究 package，不碰判定路徑、`sector_rank_stats`、閘門、API 或前端。

## 5. 使用者面字面

**無。** 兩處模組都沒有面向使用者的字串。`sector_biased` 的 `BIAS_LABEL` 明示「不得上畫面」。F-11 與 Kelly 的尾段字面已由 KT-R-9、KT-R-13～R-15 處理，不在本案範圍。

---

## 驗證

**重現程式**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/kt_r22_tail.py`
- 直接 import repo 裡真實的 `walk_forward_splits` 與 `segment_bounds`。只有 `study.py:356-364` 與 `sector_eval.py:1011-1019`、`:1581` 的歸屬過濾，是依原碼改寫成索引形式。
- 以 `.venv/bin/python -B` 加 `PYTHONDONTWRITEBYTECODE=1` 執行，沒有寫入 pycache；執行後 `git status --short` 為空。

輸出節錄：
```
[1] segment_bounds n=1..3000: gaps/overlaps/uncovered tail -> none
    trailing segment length examples: {126: 126, 127: 1, 252: 126, 253: 1, 300: 48, 377: 125}
[1b] compute_statistics segment membership (400 random calendars): weeks not in exactly one segment -> 0
    {'n': 1000, 'folds': 3, 'r': 118, 'IS': 101, 'OOS': 76, 'tail': 22, 'full': 199, 'IS_exit_in_OOS': 1, 'OOS_exit_in_tail': 1}
    {'n': 2450, 'folds': 15, 'r': 56, 'IS': 101, 'OOS': 378, 'tail': 10, 'full': 489, ...}
    max tail weeks over n=630..3999: {'n': 751, 'folds': 1, 'r': 121, 'IS': 101, 'OOS': 25, 'tail': 24, 'full': 150, ...}
    r == (n-504) mod 126 for all n=630..3999: True
    n=2450: ... max |p_OOS(with tail) - p_OOS| <= 0.0258
    n=751: ... <= 0.4898
[3] c8 script 4000/120/60: oos=(120,3960) r=40
```

**事實與推論分開**
- 〔讀碼〕：所有行號引用。
- 〔實跑〕：上面的輸出。
- 〔推論〕：偏誤方向無法判斷、不面向使用者的結論（依 Grep 找不到使用者推得）、建議處置。

**自我揭露**
- 沒有用真實資料或真實 panel 跑 `study_on_hindsight` 或 `evaluate_views`；週數是用 H = 5 的主相位索引推算的。
  - 實際的有效週會因 `invalid_reason` 減少，所以尾段週數是上界。
  - n ≈ 2450 是依方法論的年限換算，不是實際的回補長度。
- 敏感度變體沿用 base 的 holding（`sensitivity.py:23`），所以 H = 5 的假設在變體上也成立；這點沒有實跑驗證。
- 沒有跑 pytest。
- 附帶發現 (a) 是讀碼得出的，沒有實際查研究 DB 內容。依指示，我沒有讀 `*.db`。

## 下一步

1. **coordinator**：轉給風控結案 KT-R-22。sector_eval 不需處理；sector_biased 不面向使用者，只需內部揭露，不需要字面送審。
2. **dev-lead**：如 CEO 排程，依 §4 最小改法與測試實作，交 qa-reviewer（含 Codex）審查。不急，也不綁任何出貨。
3. **若日後要把 sector_eval 分段或 biased study 結果放上任何畫面**：須另案送 creative-lead 與風控，且必須同時揭露最後一段的長度與尾段範圍。

## 相關檔案
- `/home/user/AICompany/apps/stock-desk/backend/app/backtest/splits.py`（第 79-85 行）
- `/home/user/AICompany/apps/stock-desk/backend/app/backtest/sector_eval.py`（第 32-38、884-896、922-923、1011-1019、1070、1581、1993-2027 行）
- `/home/user/AICompany/apps/stock-desk/backend/app/research/sector_biased/study.py`（第 11-14、68-70、343-393、418-446 行）
- `/home/user/AICompany/apps/stock-desk/backend/app/research/sector_biased/sensitivity.py`（第 340-365、404-433 行）
- `/home/user/AICompany/apps/stock-desk/backend/app/research/sector_biased/store.py`（第 79、103 行）
- `/home/user/AICompany/apps/stock-desk/backend/app/research/sector_biased/hindsight.py`（第 20 行）
- `/home/user/AICompany/apps/stock-desk/backend/scripts/c8_regression_comparison.py`（第 124-128 行）
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_sector_eval.py`（第 600-603 行）
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_research_isolation.py`（第 497-527 行）
- `/home/user/AICompany/work/stock-desk-族群動能-方法論.md`（第 288、298-303、457 行）
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/kt_r22_tail.py`
