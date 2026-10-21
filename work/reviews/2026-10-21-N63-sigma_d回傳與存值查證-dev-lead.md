# N-63 sigma_d 回傳值與證據不足時存值查證

- 審查者：dev-lead
- 日期：2026-10-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. **`volatility.py` 還沒有實作，所以「現行實作回傳什麼」沒有答案。** `apps/stock-desk/backend/app/outlook/` 與 `app/forecast/` 都不存在。`sigma_d`、`SIGMA_MIN_VALID`、`threshold_inputs`、`E-VOL-*` 在 `apps/` 與全部 worktree 的 `*.py` 中都是 0 筆，所有 refs 的歷史裡也沒有 outlook 路徑。它們目前只是 ADR-0027 L252 的規格。D-9 實作前，這個自由度完全由規格決定，現在釘死成本最低。
2. **4e-17 的殘差真的會出現，看用哪個估計式。**
   - 用 `np.std(ddof=1)`：60 個 0.1 算出 4.198e-17，隨機常數值約 60% 不為 0。
   - 用 `statistics.stdev`：一律剛好 0.0。
   - 全部報酬剛好是 0.0（平盤填值的實際情形）：兩種都是 0.0。
   - 殘差（≤ 5.6e-17）遠小於 `SIGMA_FLOOR` 0.1%。只要預測端以 σ_d < 0.001 判定，`E-VOL-DEGENERATE` 一定擋得住；有標籤列另有 `sigma_d_below_floor` 守衛。
   - 真正的風險不在殘差本身，而在所有 0 < σ_d < 0.001 的值（殘差或真實的近常數序列都算）。若把它存進 `band_def`，`threshold_inputs()` 會把該列判為「完整」，而不是「缺項」，後果見下。
3. **照 ADR L299 字面，`E-VOL-SHORT` 的列存不存 σ_d 取決於實作。** 字面只說「實際算得的值存，算不出的記 null」。`sigma_d()` 在有效數不足時回傳 None 就不存；算了也回傳值就會存。
4. **quant 說「不影響判定」只對大盤與個股成立，對族群不成立。**
   - 族群：存或不存，會改變 §4.3 (f) W 放回的筆數，也就是會改變 `fail_w`。
   - 退化列：如果把極小的 σ_d 存進去，該列可能整筆被拒寫。
5. **建議**：證據不足而輸出 `E-VOL-SHORT` 或 `E-VOL-DEGENERATE` 的列，`band_def.sigma_d` 一律記 null，並由 `sigma_d()` 的回傳契約與寫入驗證兩處同時釘死。條文由 TA 落字。

## 各部門回報

### dev-lead

**一、σ_d 計算（問題 1）**

【事實】
- `apps/stock-desk/backend/app/outlook/` 與 `app/forecast/` 都不存在（`ls` 回報 No such file）。
- `grep -rn "threshold_snapshot\|threshold_inputs\|E-VOL"` 在 backend `*.py` 中是 0 筆。
- `git log --all -- apps/stock-desk/backend/app/outlook` 是 0 筆。
- 對所有 refs 做 `ls-tree`，沒有 outlook 或 volatility.py。
- 目前 HEAD 是 `de62042`（product/stock-desk）。
- 後續追蹤清單 `work/dispatch/2026-10-17-後續追蹤清單.md:147` 也把 N-63 的時點列為「D-9 實作前」。

【事實：規格】
- ADR-0027 L252：`sigma_d(log_returns)` 是唯一的 σ 核心，常數 `SIGMA_MIN_VALID`、`SIGMA_FLOOR` 取自 dirdef，為純函式。規格沒有寫回傳型別，也沒有寫不足時回傳什麼。
- 事先宣告：
  - L834：ddof=1。
  - L850：`SIGMA_MIN_VALID` 是 60 個中至少 55 個。
  - L851：`SIGMA_FLOOR` 是 < 0.1%。
  - L1448：`E-VOL-SHORT` 的「現有」欄記 n。
  - L1449：`E-VOL-DEGENERATE` 的「現有」欄記 σ_d 值。
- 所以三種情形（有效數不足下限、0 筆、退化）都沒有既定回傳值，目前是規格空白。

【事實：同 repo 的類比實作，非 sigma_d】
- `app/signals/risk.py:126-138`：少於 2 筆回傳 None，否則用 `np.std(ddof=1)`。
- `app/playbook/indicators.py:83-99`：不足時回傳 None，用 two-pass 的純 Python 計算。
- 兩者的慣例都是「不足 → None，不拋例外、不回 NaN」。

【事實：浮點實驗】
- 腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/const_std.py`。
- 常數序列的 `np.std(ddof=1)`：
  - n=60、值 0.1 → 4.198e-17；
  - n=55、值 0.1 → 5.60e-17；
  - n=55、值 ln(1.01) → 1.75e-18；
  - 值 0.0 → 0.0。
- 隨機 20000 組常數序列（n 為 55～60，值在 ±0.1 之間）：
  - `np.std`：11911 組不為 0，最大 5.6e-17；
  - `statistics.stdev`：0 組不為 0。
- 若 σ=4e-17，`exp(K·σ·√h) − 1` 與 `1 − exp(−K·σ·√h)` 在 h=3 和 h=5 都等於 0.0；`expm1` 約為 3e-17。

【推論】
- 擋得住：`E-VOL-DEGENERATE` 擋得住殘差，前提是預測端用 `sigma < SIGMA_FLOOR` 判定。
- 擋不住：`threshold_inputs()` 的「正的有限值」檢查（ADR L295）擋不住殘差。
- 若把這種 σ_d 存進證據不足列：
  - 該列會被判為「完整」，ADR L298 的五項驗證就要適用。
  - 照事先宣告 L858-859 的 `exp()−1` 實作，`up_pct` 算出 0.0，違反「`up_pct` > 0」，整筆被拒寫。這違反 §5.1 第 4 點「證據不足的預測也寫入紀錄帳」（L1435）。
  - 若改用 expm1，可以寫入，但結算時 z 會爆大（L851 正是要防這個），並產生 `realized_label`。
- 同一個風險對任何 0 < σ_d < 0.001 的真實近常數序列都成立，不限於殘差。

**二、σ_d 不足時 `threshold_snapshot` 怎麼寫（問題 2）**

【事實：只有規格，沒有程式】
- ADR L299（證據不足而缺項的列）：
  - `missing_json` 必須非空；
  - `up_pct`、`down_pct` 必須同為 null；
  - 其餘鍵照實際算得的值存，算不出的記 null。
- ADR L297：`band_def` 另有 `valid_returns` 鍵。
- 下游判定證據不足，有兩條獨立的路：
  - label 與 `missing_json`：事先宣告 §5.1 第 2 點，L1434。
  - 門檻缺項只看 `threshold_inputs()`（ADR L295）：缺鍵、null、0、負值、NaN、inf 都算缺項。
- 缺項時，八個門檻相關欄位記 null（ADR L1284、L1291；事先宣告 L1551 V22-07）。
- 完整的證據不足列，照常算 `realized_z`、`realized_label`，`hit` 記 null（ADR L1286）。

【推論】
- 「省略鍵」與「寫 null」在下游等價，兩者都是缺項。
- 「寫入算出的值」則會走「完整」路徑。

**三、`E-VOL-SHORT` 的列會不會存 σ_d（問題 3）**

【事實】
- 照 ADR L299 字面，兩種做法都合規：
  - `sigma_d()` 在有效數少於 55 時仍用現有的 n 筆算出值並回傳 → 這是「實際算得」，會存，該列為完整；
  - `sigma_d()` 回傳 None → 記 null，該列為缺項。
- 同一份事先宣告中，quant 在 `work/reviews/2026-10-19-N53重放null規則提案-quant.md:109` 已經寫明「證據不足時照樣用不到 55 個日報酬算 σ_d：這是 §5.1 第 3 點禁止的替代估法」（§5.1 第 3 點即 L1436）。

【查證 quant 的說法（quant 檔 L215：「只影響證據不足列的診斷欄位，不影響任何判定」）】

- 大盤與個股：【推論】成立。
  - 證據不足列的 `hit` 恆為 null（ADR L1286、L1292；事先宣告 L1553），不計入 n（L1011）。
  - 作廢率依鏈尾 `status`，不讀 label，也不讀門檻欄位（L1073）。
  - 所以存不存只改變 `realized_z`、`realized_label` 與診斷欄位。
- 族群：【事實】不成立。
  - 事先宣告 L1073（V23-02）規定：E 內 `label = insufficient` 而 `resolved`、而且 `basket_excluded_members_json` 非空的列，任一籃子標籤為 null 就「算不一致」，在 W 中放回。LG-34 (f)（L2357）也這樣測。
  - ADR L1287 也寫明，V23-02 是這些欄位唯一作為判定輸入的例外。
  - 【推論】因此，同一筆族群 `E-VOL-SHORT` 列（排除成員非空）：
    - σ_d 記 null → 兩個標籤都是 null → 算不一致 → W 放回；
    - σ_d 存值 → 兩個標籤照算 → 可能一致 → 不放回。
  - W 放回的筆數會改變 §4.3 (f) 的 `fail_w`，只在作廢率 > 5% 時生效。
- 退化列：【推論】另一個影響。
  - 若把 0 < σ_d < 0.001 存進去，可能如第一點所述整筆被拒寫。
  - 該列就沒有 outcome，作廢率的分母跟著變，間接影響 W 是否套用。

**四、提案（交 TA 落字，不是定案）**

提案內容：
- (a) `sigma_d()` 的回傳契約：
  - 有效日報酬少於 `SIGMA_MIN_VALID`（含 0 筆）時，回傳 None，不回 NaN、不拋例外，也不用現有的 n 筆計算；
  - 估計值小於 `SIGMA_FLOOR` 時，同樣不把這個值當作 σ_d 輸出；
  - 建議回傳型別化結果，例如 `{value: float | None, valid_returns: int, raw_std: float | None}`；
  - 原始估計值只放進 `E-VOL-DEGENERATE` 的 `missing_json.available`（§5.2 L1449「σ_d 值」）。
- (b) `forecast_record` 的寫入驗證加一條：`label = insufficient`，而且 `missing_json` 含 `E-VOL-SHORT` 或 `E-VOL-DEGENERATE` ⇒ `band_def.sigma_d` 必須為 null，`valid_returns` 照實記 n（0 也照記）。
- (c) 附錄 C 與 FL 加格：
  - 有效數 54、0、55 各一格；
  - 常數序列 0.0 與 0.1 各一格（期望 `E-VOL-DEGENERATE`、σ_d 為 null）；
  - σ_d = 5e-4 一格；
  - 族群 `E-VOL-SHORT` 而且排除成員非空 → 依 V23-02 在 W 中放回。
- (d) 選配：σ_d 的估計式指定一種在常數序列上剛好得 0 的算法（例如 `statistics.stdev` 這種精確累加），避免 4e-17 這類依實作而變的殘差，也有利於 ADR L293「重算逐位相等」。這只影響 `missing_json` 裡記下的退化值，不影響判定。

理由：
- 1）不存 σ_d 符合 §5.1 第 3 點：用不到 55 筆算出的 σ 是被禁止的替代估法。照字面存下來，結算端就會拿被禁止的估計值算 `realized_z`。
- 2）缺項筆數與 W 放回筆數會由規格決定，不再取決於實作怎麼選（族群有判定影響，見第三點）。
- 3）可以消除退化列被拒寫的路徑，不必依賴 `exp()−1` 和 `expm1` 之間的選擇。
- 4）不損失診斷資訊：n 留在 `valid_returns` 與 `missing_json`，退化值留在 `missing_json`。
- 5）與 repo 既有的「不足 → None」慣例一致（risk.py、indicators.py）。

也要照實並陳另一面（推論）：
- 族群 `E-VOL-SHORT` 而且排除成員非空的列，會一律在 W 中放回，比存值時嚴，是收緊面。這需要 quant 確認方向，並送風控。
- 證據不足列可做的「實際走勢」診斷會變少。事先宣告 L113（V22-07）已揭露這一面，目前不登記這類診斷。

## 驗證

所有指令都是唯讀。沒有 Edit、Write 或 commit；沒有讀 `.env`；沒有碰任何 `*.db`。執行後 `git status --short` 輸出為空。

- 定位：
  - `ls` outlook 與 forecast 目錄；
  - `grep -rn` 搜 `sigma_d`、`SIGMA_MIN`、`E-VOL`、`threshold_inputs`（apps 與全部 worktree）；
  - 對所有 refs 做 `git ls-tree`，並跑 `git log --all -- app/outlook`。
- 文件：
  - ADR-0027：`sed -n` L270-302、L1280-1296，並 grep `volatility`、`valid_returns`；
  - 事先宣告：L828-920、L1429-1476，並 grep `籃子標籤不一致`；
  - quant 檔：L45-60、L100-118、L208-220；
  - TA 檔（N41-G2）：L217。
- 浮點實驗：`.venv/bin/python -I /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/const_std.py`，結果如上。
- 既有測試：`pytest test_playbook_indicators.py test_leverage_drag.py test_leverage_erosion.py test_signals_risk.py` → **78 passed，1 warning（Starlette deprecation）**。
  - conftest 的 autouse fixture 把預設 DB 路徑指向哨兵目錄，store 一律用 `tmp_path`。
  - 這些測試測的是類比函式，不是 sigma_d。sigma_d 沒有任何測試可跑。

## 下一步

1. **TA**：依第四點的提案 (a)～(c) 落字，修訂 ADR-0027 L252 的 `volatility.py` 列與 D-3「適用範圍與缺項」（L299），並決定是否採 (d)。
2. **quant-researcher**：
   - 更正 quant 檔 L215：大盤與個股不影響判定；族群經 V23-02 會影響 W，退化列可能被拒寫。
   - 確認提案的方向（族群 W 是收緊面），並決定事先宣告是否要同步加註（§2.1 常數表、§5.2）。
3. **風控**：落字後逐字確認（涉及 W 的口徑）。
4. **dev-lead**：D-9 實作時依定案條文實作 `sigma_d()` 與寫入驗證，FL 格與 LG 格一起交付，送 qa-reviewer 審查。
