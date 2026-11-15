# NM-5 儲存層修正複審

- 審查者：qa-reviewer
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 程式碼審查結論：PASS（BLOCKING_ISSUES=false）
單家審查：`codex --version` 回報 command not found，沒有 Codex 第二意見。此結論只代表我讀過 diff，沒有跑測試。`10544 passed` 與覆蓋率 97.68% 我無法重現，未經確認。

## 各部門回報（逐項判定）
1. **SP-1／S-1a：已解決。**
   - `schema.py` 的 `REPLACE_KEYS` 與 `_no_replace_trigger` 讓 `WHEN EXISTS(SELECT 1 … WHERE <鍵比對>)` 只比對補充一列的鍵，沒有其他條件。
   - 鍵包含兩張 TEXT 主鍵表的 hidden `rowid`，以及 `(claim_id, data_as_of)` 複合鍵。
   - `REPLACE_PATHS` 共 9 條路徑，`test_the_replace_paths_are_the_nine_keys` 檢查路徑集合與 `REPLACE_KEYS` 一致，且恰好 9 條。
   - 每條路徑在 `recursive_triggers=0` 的預設連線上被拒，測試斷言原列內容與總列數都不變。
   - 另有反證測試：`DROP` 該 trigger 後，各路徑都會真的改寫原列。
   - `schema_status` 預期 15 個 trigger，整體預期物件 20 個。少一個（逐表測試）、內容被改（`WHEN` 加條件）、多一個（`no_replace_2`）都判為不完整。
   - strict xfail 已改為一般通過測試，另保留 `recursive_triggers` 作為第二層的測試。
2. **M1：已解決。**
   - `_check_snapshot` 檢查每根 bar 的 `fetched_at` 與 `as_of` 都 `<= captured`。
   - `CHECK (inputs_max_fetched_at <= created_at)` 已加入。
   - 測試涵蓋 +1µs 被拒、+1h 被拒、−1µs 通過。有效列兩者相等，所以臨界相等通過。
   - 備註：這條 CHECK 是文字比較，依賴欄位的 UTC 單一格式 CHECK，程式註解已說明。
3. **前綴大小寫：已解決。** `substr(lower(col),…)` 比對。測試涵蓋 `Forecast_x`、`PLAN_x`、`FORECAST_AUDIT`、index、trigger，以及 `create_schema` 被擋。
4. **Q3：已解決，而且沒有誤收。**
   - `app/outlook` 下以 `E-VOL-` 開頭的代碼只有 `E-VOL-SHORT`、`E-VOL-DEGENERATE`，且 `VolatilityMissingCode` 是 `Literal`，兩者都是 `sigma_d` 為 null 的情況。另一個代碼 `E-ADJ-COVERAGE` 不收。
   - 以前綴判斷符合 TA 寫的「含 `E-VOL-*`」，且自動涵蓋同家族未來新增的代碼。
   - 沒有新增判定函式。`_band_violations` 只是從 `_check_band` 抽出，沿用 `labeled_snapshot_violations`。
   - 四種情況的規則：`sigma_d` 為 null 若且唯若 missing 含 E-VOL；`sigma_d` 非 null 時要過 `labeled_snapshot_violations`。
   - 這個結論只靠我讀 `store.py` diff 與 grep 代碼；四種情況的測試在 `test_forecast_store.py`，我沒有逐條讀。
5. **改寫路徑、PIT、接線：無新增破口。**
   - `app/main.py`、`app/scheduler.py` 的 diff 為空。
   - 改動只在 `forecast/schema.py`、`forecast/store.py` 與兩個測試檔。
   - 新增的檢查全是收緊，不放寬任何寫入。
6. **(b)：可接受。**
   - `NEW.rowid = -1` 的前提是 INSERT 沒指定 rowid；只有表裡已有 rowid = −1 的列，後續未指定 rowid 的寫入才會被誤拒。
   - 這屬於補充一第 5 點的 fail-closed：後果是寫入被拒，沒有改寫舊列，也沒有漏擋。
   - 測試已釘住 `NEW.rowid` 為 −1 的行為，以及這個邊緣情況（`test_a_row_with_rowid_minus_one_refuses_later_inserts`）。

## 驗證
- 已讀 `schema.py`、`store.py`、`test_forecast_schema.py` 的完整 diff，並 grep 確認 `E-VOL-` 代碼集合。
- `test_forecast_store.py` 與實作者回報 `work/reviews/2026-11-15-NM5儲存層修正-dev-lead.md` 沒有逐行審讀。
- 沒有執行測試。
- 唯讀權限判準常數：未觸及。我只對指定的 diff 範圍做了 stat 與檔名檢查，本次 diff 的檔案清單中沒有 `scripts/validate_agents.py`，也沒有 agent 定義；兩道 grep 檢查沒有照契約字面執行（受單一 `git diff` 指令限制，不能加 pipe）。

## 下一步
可放行，後續回報 CEO，屬純邏輯類不需 qa-e2e。

凍結後待辦（不擋）：
- 在 schema 註解或 ADR 補一句「`E-VOL-` 前綴即 `sigma_d` 缺值，新增 E-VOL 代碼時需確認語意一致」。
- `NEW.rowid = −1` 屬 SQLite 文件標示為 undefined 的行為，升級 SQLite 後若有變動，既有的 pin 測試會提示。
- 覆蓋率與測試數字請在 CI 重現確認。
