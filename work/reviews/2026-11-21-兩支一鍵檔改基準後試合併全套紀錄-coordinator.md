# 兩支新一鍵檔改凍結基準後的試合併全套紀錄（風控 RC-399 (d)、RC-352 (d)；補充十二 S-21 第 5 點）

- 記錄者：coordinator
- 日期：2026-11-21
- 性質：試合併只在本機、位於 repo 目錄之外、沒有推送。正式合併時仍須依合併程序修訂八在合併點上重跑。任一分支 head 再變動，本紀錄即失效、須重跑。

## 1. 版本（40 碼）

| 項目 | 狀態報告一鍵檔 | 帳外缺日比對一鍵檔 |
|---|---|---|
| 分支 | `feat/forecast-status-oneclick` | `feat/gap-check-oneclick` |
| 分支 head | `11ce56d21c80b023806ab8cfe67499aa794aeeb1` | `f6aff2ce61bb15dd4d1e5d52b54e6668801eaf3e` |
| 試合併用的 product commit | `5e6a56d800a6cde2ccc988a5a145ce4bd9c1123c` | `5e6a56d800a6cde2ccc988a5a145ce4bd9c1123c` |
| 試合併 commit（`--no-ff`，parents 為上兩列） | `41b822c7455725d86c8861f9998f4b6c16bccb37` | `e67e801baef510d23cf9e05091634c17f2411b73` |
| 試合併的 `apps/stock-desk/backend/app` tree | `07b5e1fd95fa933d969ba4f5adecb3c982be0a62` | `07b5e1fd95fa933d969ba4f5adecb3c982be0a62` |

- 兩個合併都沒有衝突；合併後工作樹乾淨。
- product 在 `5e6a56d` 之後到本紀錄撰寫時（tip `740f9db`）的 commit 都只動 `work/`：`git log 5e6a56d..origin/product/stock-desk -- apps .github` 為 0 筆。

## 2. 測試要讀的風控報告確實在場

這些報告 commit 在 `product/stock-desk` 的 `work/reviews/`（不是 main），試合併工作樹因為含 product 而有這些檔。逐檔以 `test -f` 確認存在：

| 測試檔引用的報告 | 狀態報告試合併 | 缺日比對試合併 |
|---|---|---|
| `2026-11-20-補充十一與退役通知判定RC284至RC297-風控.md` | 在 | 在 |
| `2026-11-20-補充十一增修確認與三句固定行RC298至RC302-風控.md` | 在 | 在 |
| `2026-11-20-補充十一E1確認與缺少uv提示定稿RC305至RC312-風控.md` | 在 | 在 |
| `2026-11-20-兩份CEO文件判定RC313至RC324-風控.md` | 在 | 在 |
| `2026-11-20-補充十修訂版與三句STOP判定RC265至RC274-風控.md`（缺日比對用） | — | 在 |

試合併工作樹位於 scratchpad，不在 `/home/user/AICompany` 底下，所以測試往上層找 `work/reviews/` 時找到的是試合併自己的檔，不是主工作目錄的檔。

## 3. 指令（與 CI 相同；Python 3.12）

在 `apps/stock-desk/backend` 下，`UV_PROJECT_ENVIRONMENT` 指向專屬 venv，先 `uv sync --frozen --python /usr/bin/python3.12`，再依序：

```
uv run --frozen --python /usr/bin/python3.12 ruff check .
uv run --frozen --python /usr/bin/python3.12 ruff format --check .
uv run --frozen --python /usr/bin/python3.12 mypy app tests
uv run --frozen --python /usr/bin/python3.12 pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

## 4. 結果

| 項目 | 狀態報告一鍵檔 | 帳外缺日比對一鍵檔 |
|---|---|---|
| `ruff check .` | All checks passed!（exit 0） | All checks passed!（exit 0） |
| `ruff format --check .` | 549 files already formatted（exit 0） | 550 files already formatted（exit 0） |
| `mypy app tests` | no issues found in 536 source files（exit 0） | no issues found in 537 source files（exit 0） |
| 一鍵檔自己的測試檔 | `test_forecast_status_flow.py`：105 passed | `test_gap_check_flow.py`＋`test_gap_check_logic.py`：203 passed |
| 全套 | **12172 passed、2 xfailed、0 failed、0 error、0 skipped**，1 warning，32 分 37 秒，exit 0 | **12270 passed、2 xfailed、0 failed、0 error、0 skipped**，1 warning，31 分 42 秒，exit 0 |
| 覆蓋率 | 97.81%（門檻 90%，達標） | 97.81%（門檻 90%，達標） |

- 全套輸出的最後一行各為 `12172 passed, 2 xfailed, 1 warning in 1957.95s` 與 `12270 passed, 2 xfailed, 1 warning in 1902.72s`；輸出中沒有 skipped 字樣。
- xfail：2 個，與 product 本身相同（先前在 product 基底上的各次全套也都是 2 xfailed；這兩支分支沒有新增或移除 xfail 標記）。
- **先前在沒有風控報告的位置失敗的測試，這次都通過、沒有被跳過。** 另外以 `-k` 單獨重跑確認：
  - 狀態報告：`test_rc310_the_missing_uv_line_is_the_risk_control_sentence_verbatim`、`test_the_bat_differs_from_the_precedent_only_in_the_listed_lines`、`test_rc318_the_backend_error_line_is_followed_by_the_risk_control_sentence`、`test_the_bat_has_no_non_cmd_redirect_and_only_r2_lines_besides_its_own`，加上新增的兩個凍結基準測試 → 6 passed、0 skipped。
  - 缺日比對：`test_the_three_stops_are_the_risk_control_sentences_verbatim`（三個參數）、`test_the_bat_adds_the_risk_control_sentence_below_the_unchanged_backend_error_line`、`test_the_bat_prints_the_risk_control_uv_sentence_verbatim_and_no_install_hint`、`test_the_bat_matches_the_pipeline_acceptance_launcher_except_its_own_lines`，加上新增的兩個凍結基準測試 → 8 passed、0 skipped。
- 沒有為了通過而改任何測試、加任何 skip 或 xfail；試合併工作樹在跑完後 `git status` 乾淨。

## 5. 沒有涵蓋的事

- 沒有跑 Python 3.13（CI 會跑兩個版本）。
- 兩支一鍵檔同時合併、以及與退役分支一起合併後的組合，沒有跑全套。
- 沒有在 Windows 實機執行任何 `.bat`。
- 與 G_acc 的 blob 核對（補充十二 F10）要等 CEO 的驗收貼回，另行記錄。

## 6. qa 確認

（待 qa-reviewer 讀過本紀錄後，於其複審報告中確認；確認的報告路徑補記在後續追蹤清單。）
