# F-2 短期範圍「成立」是否延續到完整視窗：合成帳本實測

- 審查者：qa-automation
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**推論成立。** 實測行為是：視窗未滿時「成立」的訊號，在第一個完整視窗形成後會讓該完整視窗成立，之後「曾否成立：是」一直留著。這與 2026-11-20 裁示第 4 題 (d)「晚看會消失」相反，補充十三第 9 點 (d) 才對。但有一個細節要寫進給 CEO 的文件：第一句開頭的「F-2 成立」字樣，只在視窗未滿時出現。完整視窗之後，開頭改看「此視窗」，訊號改由句尾的「曾否成立」承載。

測試帳本：起點 2026-10-05（週一），前 7 個平日有定案 session 但沒有 `late = 0` 紀錄，之後每個平日都正常記錄。claim 是 `market|h3|r1|dirdef-v1.0|forward`，輸出整行原文如下。

- (a) 第一個完整視窗期間（看第 19、20、21 個平日時）
  - 第 19 個平日，視窗未滿：`…視窗未滿（自起點以來 19 個平日：2026-10-05～2026-10-29），沒有 late = 0 紀錄的定案 session 數 7，inputs_not_ready 日數 0，F-2 成立（兩項合計已超過 6，成立後不撤銷）`
  - 第 20 個平日，第一個完整視窗：`…最近一個完整視窗 2026-10-05～2026-10-30，沒有 late = 0 紀錄的定案 session 數 7，inputs_not_ready 日數 0，分母 20，此視窗 F-2 成立；自起點以來 F-2 曾否成立：是（成立後不撤銷）`
  - 第 21 個平日，窗口滾動一天，最早的漏記日掉出，剩 6 筆：`…最近一個完整視窗 2026-10-06～2026-11-02，沒有 late = 0 紀錄的定案 session 數 6，inputs_not_ready 日數 0，分母 20，此視窗 F-2 未成立；自起點以來 F-2 曾否成立：是（成立後不撤銷）`
  - 所以第 21 個平日起，「此視窗」已變成未成立，只剩「曾否成立：是」。只看第一句開頭的人會以為訊號消失，其實沒有。
- (b) 漏記日滑出視窗之後（第 27 個平日起，視窗內漏記為 0）：`…最近一個完整視窗 2026-10-14～2026-11-10，沒有 late = 0 紀錄的定案 session 數 0，inputs_not_ready 日數 0，分母 20，此視窗 F-2 未成立；自起點以來 F-2 曾否成立：是（成立後不撤銷）`
- (c) 更久之後（第 300 個平日，約一年多；漏記日已滑出約 280 個平日）：`…最近一個完整視窗 2027-11-01～2027-11-26，沒有 late = 0 紀錄的定案 session 數 0，inputs_not_ready 日數 0，分母 20，此視窗 F-2 未成立；自起點以來 F-2 曾否成立：是（成立後不撤銷）`
  - 程式碼裡沒有任何上限，也沒有儲存旗標。「曾否成立」是每次從帳本重算：`ever_held=any(item.holds for item in windows)`，視窗涵蓋自起點 S_c 以來每個滾動完整視窗。所以「很久以後才看」仍然看得到。
  - 若 ledger 資料被改動或遺失，這個答案會跟著變，因為它是重算而不是存的。

邊界對照（實測）：7 筆漏記是最小的成立數。6 筆在短期範圍顯示「尚未判定（兩項合計未超過 6）」，第一個完整視窗顯示「此視窗 F-2 未成立；…曾否成立：否」，之後 300 個平日都是「否」。

## 各部門回報

- qa-automation：新增一個測試檔，共 8 個測試，沿用既有 `Ledger`、`file_ledger`、`approved_copy`、`f2_lines` 等 helper，帳本都建在 `tmp_path`。沒有動 `app/`、`scripts/`、`.bat`、既有測試檔。
- 門檻出處（`apps/stock-desk/backend/app/forecast/store.py`）：
  - 短期門檻：第 495 行 `F2_SHORT_WINDOW_LIMIT = 6`，第 1594 行 `holds = numerator > 6`，即至少 7 筆才成立。
  - 完整視窗門檻：第 493 行視窗長 20、第 497～498 行比例 3/10。判斷在第 1589～1592 行，`numerator*10 > limit*3`，`limit = min(20, 範圍內定案 session 數)`。分母 20 時至少 7 筆，分母 12 時 4 筆，分母 0 一律成立。至多為 7 筆的門檻是 6 筆「剛好不成立」，所以 7 筆必成立。
  - 「曾否成立」：第 1611～1625 行，`windows` 取全部滾動完整視窗，`ever_held=any(...)`。
  - 視窗未滿的 `ever_held`：第 1604～1612 行，等於短期範圍當下是否成立。
- 測試清單，全部通過：
  1. `test_supplement_13_point_9_d_short_range_holds_carries_into_first_full_window`：主情境逐階段，釘住第 9 點 (d)，包含第 19、20、21、26、27、60 個平日的整行原文。
  2. `test_the_short_range_wording_exists_only_before_the_window_fills`：第一句開頭「F-2 成立（兩項合計已超過 6」只出現在視窗未滿，之後只剩「曾否成立：是」。
  3. `test_the_two_thresholds_in_the_constants`：門檻常數。
  4. `test_the_smallest_holding_miss_count_carries_over_and_one_fewer_never_holds`：7 筆對 6 筆的對照組。
  5. `test_the_short_range_is_a_prefix_of_the_first_full_window`：短期範圍是第一個完整視窗的前綴，分子不超過它。
  6. `test_ever_held_is_recomputed_from_every_window_since_the_start_with_no_cap`：第 300 個平日仍是「是」。
  7. `test_ever_held_is_derived_from_all_windows_not_a_stored_flag`：用 `inspect.getsource` 斷言重算的原始碼字面。
  8. `test_a_spread_miss_pattern_stays_at_no_for_the_whole_history`：漏記分散（每 4 個平日 1 筆，任何 20 個平日至多 5 筆）則整段歷史都是「否」。
- 既有測試 `tests/test_forecast_f2_window.py` 的 `test_n11_*` 已經在不同角度驗證「短期成立 → 第一個完整視窗成立 → ever 不撤銷」。本次新增的是接 `report status` 整行輸出、逐階段（含滑出之後與很久之後）的釘住，以及「曾否成立」的歷史範圍。

## 驗證

- 環境：Python 3.12，`UV_PROJECT_ENVIRONMENT=/tmp/claude-0/venv-f2c`，`uv sync --frozen --python /usr/bin/python3.12`。
- 遠端 `feat/nm5-wiring` head 為 `2a48af3e0890433531cd51e1a76af1baa69b4248`，與指定相符。
- 新測試檔：8 passed。
- 新測試檔加既有 `test_forecast_f2_window.py`、`test_forecast_report.py`、`test_forecast_gap_disclosure.py`：756 passed。
- `ruff check .`：All checks passed。
- `ruff format --check .`：569 files already formatted（新檔經 `ruff format` 整理過一次再提交）。
- `mypy app tests`：Success, no issues found in 555 source files。
- 新分支 head（40 碼）：`7f2f8cd30e442e6299b4ce93f8ce0ebdd3c6d9ff`，已 push 到 `origin/test/f2-short-window-carryover`，沒有 merge。只有一個 `test` commit。
- 測試檔路徑：`/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/tests/test_forecast_f2_short_window_carryover.py`。

## 下一步

- 給 CEO 的文件字面，建議採補充十三第 9 點 (d)，並加註：完整視窗之後第一句開頭會顯示「此視窗 F-2 未成立」，訊號只在「曾否成立：是」。若文件寫成「晚看會消失」，與現行程式不符。
- 2026-11-20 裁示第 4 題 (d) 需要由 tech-architect 更正。
- 請 qa-reviewer 審查測試。

## 我沒有查證的事

- 沒有逐日寫入的情境。測試是一次建好整本帳本，只移動 `now`。依程式讀法，`f2_status` 只讀到最後一個可計入平日為止，帳本內未來日期的資料不影響結果。
- 沒有測 `inputs_not_ready` 日數造成的短期成立，只測了漏記 session。這條路徑在既有 `test_n11_*` 的參數表有覆蓋（分母 0、混合項）。
- 沒有測假日造成分母小於 20，且漏記少於 7 筆的情況下的 carryover，這部分靠既有 `test_n11_*` 與 `test_a_holiday_heavy_window_uses_min_20_s_as_its_denominator`。
- 沒有查證上游 ledger 資料遺失或被改動時的行為。
- 全套測試沒跑，已知的 `test_cg2_register_values.py` 既有失敗沒有碰。
- 沒有做 Codex 第二意見，也沒有 qa-reviewer 審查。
