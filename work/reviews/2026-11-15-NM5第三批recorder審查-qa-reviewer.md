# NM-5 第三批 recorder 程式碼審查

- 審查者：qa-reviewer
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**程式碼審查結論：PASS，BLOCKING_ISSUES=false。** 九項 BLOCKING 判準都成立，沒有 critical 或 high。
- 單家審查：`codex --version` 回 `command not found`，沒有 Codex 第二意見。
- 我不能執行測試。`11279 passed`、覆蓋率 97.76% 未經重現。
- 判準 8 的兩份 YAML sha256 與兩個 `rules_logic_sha256` 不變，只靠「diff 沒動 YAML」加「測試釘了四個值」推得，標為建議實證。
- 以下 f1～f9 是依行號與 diff 判斷的，主要在 `.claude/worktrees/agent-a26c48e22e94b6a29/apps/stock-desk/backend/`（下稱 backend/）。

## 各部門回報（qa-reviewer，逐條判準）

1. 不接線：成立。
   - `git diff --name-only` 對 `app/main.py`、`app/scheduler.py`、`app/dirdef/registry.py` 無輸出，三者零 diff。
   - 在 `app/` 搜 `record_forecasts` 與 `forecast.recorder`，只有 recorder 自己的定義與 docstring，沒有呼叫者。
   - 登記表未動。
2. recorder 不能選 T：成立。
   - 進入點是 `record_forecasts(store, *, load_benchmark, resolver)`（`recorder.py:250`），沒有 T、`as_of`、`clock` 參數。
   - 時鐘只有 `store.now()`（`recorder.py:~283`）。
   - `app/forecast/**`、`app/outlook/**` 沒有 import `app.services`；搜到的字樣只在 docstring。
   - `LOADED` 時序見 f5 的低風險說明。
3. 執行順序：成立。
   - `begin_run` 在 `_run` 之前，是第一個寫入（`recorder.py:253`）。
   - `except Exception` 記 `error`；`KeyboardInterrupt`、`SystemExit` 不是 `Exception`，會穿過而不寫 end 列。
   - `error_class` 只經 `exception_class_name`。
   - outcome 限 ok、no_new_session、inputs_not_ready、gate_closed、error 五種。
4. CG-2：成立（`recorder.py:~357-395`）。
   - `set(recording)` 須等於 `{(SCOPE_KIND,3),(SCOPE_KIND,5)}`，所以恰好兩個。
   - 五項雜湊與 horizon 逐一比對。
   - 取代關係有核對（見 f1）。
   - 任一不成立即 `WriteGateClosedError(("CG-2",))`。這發生在 `_fetch` 之前，所以不呼叫取數函式，也不寫紀錄。
5. 跨 commit 核對：成立（`recorder.py:~397-470`）。
   - 逐位比對 `data_as_of` 加五個欄位。
   - 不同時回傳 `SemanticsChanged`，由 `_run` 轉成 `gate_closed`，不寫紀錄。
   - 取 snapshot 的 `store.snapshot` 讀取失敗會走 `error`，不會誤放行。
6. 未定案 bar 分流：成立。
   - (a) 判定用 `is_final(SNAPSHOT_MARKET, S, now)`（`recorder.py:~503`），沒有第二份比較式。
   - (a) 重抓恰好一次後記 `inputs_not_ready`，`candidate_t=max(S)`。
   - (b) 進 `dropped_rows_json`，T 不變。
   - `compute_outlook` 的路徑沒有讀 `snapshot.dropped`。這支撐了「`content_hash` 與取數端不回傳該 bar 時相同」，且重算用 `dropped=()` 不會誤判。
7. 同一份快照：成立。
   - 先對所有 pending claim 算完 `compute_outlook`，再 `put_input_series`，之後逐一 `write_record`。
   - `late = created >= late_cutoff_at(T)`，截止點是 T 次日 00:00 台北時間（`inputs.py:73`、`store.py:594`）。臨界點的實際測試值我無法重跑，標為建議實證。
   - 「同一交易」見 f2。
8. lax float 收緊：diff 範圍內 YAML 未動。
   - `rules.py` 的 `weight`、`value` 改用 `AggregationNumber`（strict float、不接受 inf/nan）。
   - `tests/test_outlook_rule_files.py:41-49` 釘了兩份 YAML 的 sha256 與兩個 logic hash，數值與派工單相符。
   - 拒收反例測試存在（`test_dirdef_rules_aggregation_invalidation.py` 新增 87 行）。
9. 測試合成資料：成立。`test_forecast_recorder.py` 搜不到 `.db`、`.env`、網路字樣，`^TWII` 只作符號常數比對。

### Findings（行號為 recorder.py 的檔內行號，約值）

- **f1 [可維護性/edge][low，凍結後待辦] CG-2 取代關係核對偏鬆**（`recorder.py:~365-372`）。
  - 非記錄中 claim，只要被「任一個較晚登記的列」的 `replaces_claim_id` 指到就過，沒有要求同 `(scope_kind, horizon)`，也沒有要求鏈最後落在記錄中 claim。
  - 讀碼無法確定登記端是否已限制 `replaces_claim_id` 同 horizon。建議實證：加一個 h3 舊 claim 被 h5 新 claim 取代的反例。
  - 不涉及改寫紀錄、PIT 或 T，列凍結後待辦。
- **f2 [edge][low，凍結後待辦] 兩個 claim 的紀錄不是同一交易**（`recorder.py:~343`）。
  - 每筆 `write_record` 各自一個交易。D-4 第 1 點「同一交易」讀成「基準與主預測同列」是成立的（`baseline_predictions_json` 在同一個 row）。
  - 若第二筆失敗，會留下 `error` 與 `records_written=1`。下次執行只補缺的 claim，可能用較新的快照，兩個 horizon 的快照因此不同。
  - 之後補寫的紀錄，`late` 仍由 store 時鐘如實標記，不會被改寫。
  - 若 TA 要求兩個 claim 原子寫入，要在 store 加批次寫入 API。
- **f3 [可維護性][low] `_reproduces` 的 `except (ValueError, ArithmeticError)`**（`recorder.py:~421-433`）。
  - `ForecastStoreError` 是 `ValueError` 子類（`store.py:132`），所以 `expected_record_columns` 的 store 驗證失敗，會被記成「不重現」，變成 `SemanticsChanged`。
  - 方向是 fail-closed，但會把帳本問題標成語意改變。
  - 建議把「程式拒收」與「帳本不一致」分開記。
- **f4 [可維護性][low] `stored_records` 用 `closing(self._connect())`，不是 `_read()`**（`store.py` 新增處）。
  - 無法確定這個連線是否唯讀，建議實證：確認 `_connect` 是否設 `query_only`，或改走 `_read()`。
- **f5 [PIT 低風險] `LOADED` 的取得時序**：見下方判定 2。

## 驗證

- 已做：逐檔讀 `recorder.py` 全文、`store.py`、`errors.py`、`definitions.py`、`rules.py`、`inputs.py`、`engine.py` 的 diff，並用 grep 核對 import 與呼叫者。
  - `test_forecast_recorder.py`、`test_forecast_store.py` 等測試檔只用 grep 抽查，沒有逐行讀。
- 未做：沒有跑 pytest、ruff、mypy，也沒有重算 sha256。
- 唯讀權限判準常數：未觸及。
  - `git diff --name-only` 範圍內沒有 `scripts/validate_agents.py`（`--stat` 全是 `apps/stock-desk/backend/...`）。
  - 在 `apps/` 搜 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH`，0 處命中，所以沒有 shadow 定義。
  - 本批沒有改常數的值，也沒有動成員名單。

### 請 TA 裁示的四題（我的意見）

1. **跨 commit 觸發條件比 D-5 第 6 點字面嚴：同意，且漏洞如實作者所述。**
   - 字面做法下，程式 B 第一次執行記 `gate_closed` 之後，第二次執行的「前一次」也是 B，會跳過重算，用新語意寫進舊 claim。
   - 「與前一次不同，或與最後一次通過核對的執行（ok、no_new_session、inputs_not_ready）不同」是字面條件的超集，只會多重算，不會漏。
   - 我另外推演了三種序列：B 先 `error`、B 先被中斷、回復到 A。都不會漏，也不會永久卡死（回復到 A 時重算會通過）。
   - 建議 ADR 補一句落地，並保留測試 `test_a_label_changing_byte_closes_the_gate`。這條不影響 PASS。
2. **`LOADED` 在 import 時取一次：方向正確。**
   - 載入的程式與蓋的 digest 一致。程序沒重啟、磁碟已更新時，執行的仍是舊程式，用舊 digest 寫入才是真實的。
   - 反方向風險我只找到兩處，都是 fail-closed 或低風險。
     - 規則與定義 YAML 是延遲讀取（`get_ruleset` 有快取），若磁碟被改而程序沒重啟，CG-2 會因為登記表（舊）雜湊不符而關閘，不會寫紀錄。
     - 若 recorder 在其他 `app.forecast` 模組載入很久之後才被 import，且期間磁碟有變，digest 可能新於已載入的程式。這是低風險的時序問題。
   - 建議實證：確認 scheduler 在啟動時 import recorder，或另加「`LOADED` 之後重算 digest 不同就拒跑」的警示。
3. **`app.forecast` 遞移可達 `app.api.kelly_wording`：依字面算違反 K-2，但屬 ADR 內部不一致，不是實作者違規。**
   - K-2 列 `app.api` 為禁區，補充二又說「K-2 依可達性（含遞移 import）判定」。
   - 同一條 K-2 卻明文允許 `definitions.py` import `app.advice.loader.BANNED_PHRASES`，而這條 import 必然遞移到 `app.api`。
   - 第一批起就存在，且實作者已用測試釘住可達集合。不涉及改寫紀錄、PIT、選 T 或雜湊，所以不列 BLOCKING。
   - 請 TA 裁示：(a) 修訂 K-2 的「可達性」為「除 `BANNED_PHRASES` 這條已知路徑外」；或 (b) 把 `BANNED_PHRASES` 抽到不經 `app.api` 的模組，這個重構歸 `app.advice` 那邊。
4. **沒有任何定案 bar 時記 `inputs_not_ready`、`candidate_t` 為 null；`source_status` 照實記錄：同意。**
   - 前者與補充二第 2 點 (a) 不衝突，也不會誤記 T。
   - 後者不拒收符合「照實記錄」。若要「非 backup 就拒收」需要 TA 另訂規格，目前不是缺陷。

## 下一步

1. TA 裁示上述四題；f1、f2 看 TA 是否要在接線前收進凍結後待辦。
2. 實測補證，我無法做：
   - 在 CI 重跑 `uv run pytest --cov=app` 重現 `11279 passed` 與 97.76%。
   - 確認兩份 YAML 與兩個 `rules_logic_sha256` 的測試通過。
   - 以真實 `git rev-parse HEAD` 跑一次 `load_provenance`，確認 `code_commit` 為 40 位。
3. 接線 PR 才能開，且必須：
   - 在 `scheduler.py` 傳入 `load_market_benchmark` 本身，並以 AST 加 `is` 斷言（補充二 S-4a）；
   - 把 `WIRED_REFERRERS` 改為 `{"scheduler.py"}`；
   - 用已寫好的 `_job_wiring_violations` 檢查。
4. 本批已交 qa-reviewer，純邏輯無 UI，PASS 後回報 CEO；不需 qa-e2e。

Verdict: PASS
BLOCKING_ISSUES=false
