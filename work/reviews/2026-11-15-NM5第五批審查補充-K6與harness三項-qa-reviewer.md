# NM-5 第五批審查補充（K-6 與 harness 三項）

- 審查者：qa-reviewer
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 補充報告（併入第五批審查；先前報告的結論不變）

**總結論不變：** NEEDS_CHANGES，`BLOCKING_ISSUES=true`，唯一的阻擋項是 `compare` 的 `unavailable` 沒附原因（`scoring.py:105`、`report.py:234-240`）。
本次補查兩項只靠讀碼與 grep。沒有跑測試，Codex 仍不可用，所以仍是單家審查。

### 1. K-6：scoring 是否重用 `log_return` 與門檻比較函式，sigma_d 是否用紀錄自己的值

**成立，沒有另寫一份。**

- **`log_return`：** `scoring.py:57` 從 `app.outlook.volatility` import，這是凍結包 §2.2 唯一的定義（`volatility.py:116`）。`scoring.py:173` 呼叫它。engine 的 `engine.py:89`、`242`、`253` 與 `baselines.py:70`、`116` 都用同一個函式。
- **門檻比較：** `scoring.py:55` 從 `app.outlook.baselines` import `threshold_label`（`baselines.py:51`，§2.1 的唯一定義）。`scoring.py:177` 呼叫它。
- **sigma_d 與門檻參數：**
  - `scoring.py:149` 的 `threshold_inputs(record.band_def)` 取出紀錄自己存的 `K_h`、`EPS`、`sigma_d`（`app.forecast.band`，該函式標明為「缺門檻輸入」的唯一判斷）。
  - `scoring.py` 內沒有 `sigma_at`、`window_log_returns` 或 `usable` 的 import，也沒有重算 sigma 的路徑，符合 v0.32 V32-03。
- **一個小重複：** `scoring.py:176` 內聯寫了 `z = ret / (sigma_d * sqrt(h))`。`baselines.py:70-74` 也是同樣的內聯寫法，兩者算式相同，但不是同一個函式。我列為「凍結後待辦」（低）。建議由 baselines 匯出一個 z 計算函式讓兩邊共用，避免日後兩邊算式分歧。

### 2. quant 三項 harness 新規格，現況涵蓋與否

都不列 BLOCKING，全部列「真實資料一鍵檔之前必補」。我用 grep 在 `forecast_pipeline_harness.py` 找 `vacuous`、`missing_code`，都沒有命中，下列判斷基於讀 `_check`（438-483 行）。

- **(a) `vacuous_equality`：未涵蓋。**
  - `_check` 只累計 `labels_checked`（461 行），完全沒有「某個 P × horizon 組合的非 insufficient 紀錄數為零就判失敗」的檢查。
  - 目前只靠測試斷言 `labels_checked == 42`（`test_forecast_pipeline_harness.py:129`），那是測試端，不是 harness 本身的失敗種類。
  - 若真實資料上所有紀錄都 insufficient，harness 會判通過，這就是 quant 擔心的空洞等式。
  - 要補的是：`_check` 依 (規則, horizon) 分別計數，零筆就加 `vacuous_equality`。`render_summary` 與失敗訊息不得印筆數。
- **(b) 模型非 insufficient 但對應基準為 `unavailable`：部分涵蓋，失敗種類不對。**
  - 462 行 `row["label"] != baseline["label"]` 會因 `"unavailable"` 不等於模型標籤而判失敗，所以結果仍是失敗。
  - 但訊息是 `model and B6 differ`，把「基準不可用」與「標籤不同」混在一起，而且沒有專屬測試。
  - 要補的是：先判基準是否 `unavailable`，用獨立的失敗種類，並加反例測試。
- **(c) 「missing 非空 ⇔ insufficient」，且 missing code 只能是 §2.5 表內四類：只涵蓋一半。**
  - 現況只檢查 456-459 行「insufficient 必須有 missing」，也就是單向。
  - 缺的有兩件：第一，非 insufficient 的紀錄 missing 必須為空，這個方向沒查；第二，完全沒有檢查 missing code 屬於 §2.5 的四類。
  - 要補的是：反向斷言，加上 code 集合白名單的比對。白名單應從凍結包 §2.5 的定義取，不要在 harness 內另抄一份常數。若 `app/outlook/missing.py` 已有該列舉，應直接引用。

### 驗證與下一步

- 本次補查動作：Grep 兩次，沒有新的 `git diff`。
- 唯讀權限判準常數：未觸及。結論同先前報告，本批 diff 不含 `scripts/validate_agents.py`，也沒有 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的異動。
- 下一步：dev-lead 在修 `compare` 的 BLOCKING 時，一併補 (a)(b)(c) 與 z 計算共用，並在真實資料一鍵檔之前完成。

Verdict: NEEDS_CHANGES
BLOCKING_ISSUES=true
