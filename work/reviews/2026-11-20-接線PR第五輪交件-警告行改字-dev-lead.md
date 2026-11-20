# 接線 PR 第五輪交件：警告行改字（RC-331）

- 審查者：dev-lead
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

第五輪（RC-331 改字）做完了，已推到 `origin/feat/nm5-wiring`。新的 head 是 `2a48af3e0890433531cd51e1a76af1baa69b4248`。

- `DISK_DIFFERS_WARNING` 已刪掉祈使分句。定稿字面由腳本自風控報告抽出，與常數的執行期值逐字相同。
- 新的接線版 `code_digest` 是 `731e09f425317a468dac98b099985766b451d5a987b03db45fbb1868bb610c2b`。
- 全套在兩個版本都是 13455 passed、1 failed、2 xfailed，coverage 97.83%。唯一失敗的仍是已知的 R-1 tree id 那一支。
- 第 5 題的結論：登記腳本執行時會把 `code_digest` 印進輸出，但沒有釘任何 digest 常數。這次改字不影響已登記或將登記的值，也不影響登記一鍵檔釘的 tree id `9c157d86…`。

## 各項回報

**改動的檔與行**

| commit | 內容 |
|---|---|
| `11a56726a8b26f2698e0003414bcf10b3f29d0a4` | merge `origin/product/stock-desk`，取得 RC-331 報告。另帶進 product 上的 `tests/test_r2_first_run.py` 修改，不是本輪改的。 |
| `fca3637d8387d04df2cd89e865e1439383cfdfd5` | `app/forecast/recorder.py` 第 231 行改為 `" this run keeps the loaded provenance"`（+1／−1）。`tests/approved_copy.py` 新增 `DISK_DIFFERS_APPROVAL`、`DISK_DIFFERS_ITEM` 與 `disk_differs_line()`。新增 `tests/test_forecast_record_log_wording.py`，含 `test_rc331_the_disk_differs_warning_is_the_approved_text`、`test_rc331_the_superseded_clause_is_gone_from_app`。 |
| `84b14052921b65c37554e4a4a24c42335b3a884d` | 第 4 項的祈使句掃描：`test_rc333_no_forecast_record_line_in_app_is_imperative`、`test_rc333_the_imperative_scan_has_teeth`、`test_rc333_the_literal_scan_finds_concatenated_and_f_string_lines` |
| `2a48af3e0890433531cd51e1a76af1baa69b4248` | 範圍清單：新增 W-19，「PR 說明用的材料」補上新的 `code_digest` 與計算方式 |

**第 1 項：字面比對**
- 腳本自報告「項目：RC-331 …」的「定稿全文」抽出的是：`'forecast_record: the sources or the runtime on disk differ from the loaded program; this run keeps the loaded provenance'`
- 與 `recorder.DISK_DIFFERS_WARNING` 的執行期值比對結果為 `equal: True`。這個比對已寫成測試。

**第 2 項：引用舊字面的地方**
- 全 repo grep `restart the scheduler`，唯一命中是 `recorder.py` 那一行，已改。
- 測試都以常數名稱 `DISK_DIFFERS_WARNING` 引用，不必改。
- `recorder.py` 第 62 行 docstring 的「until the scheduler process is restarted」是敘述句，不是祈使句；測試名 `test_s12a_a_disk_change_without_restart_…` 也是。這兩處我沒動，請 qa 看是否同意。

**第 3 項：新的 `code_digest`**
- 新值：`731e09f425317a468dac98b099985766b451d5a987b03db45fbb1868bb610c2b`，取代 `e8e0fb63…d340`。造成改變的只有 `recorder.py`。
- 計算方式：在 `apps/stock-desk/backend` 下執行 `uv run --frozen python -c "from app.forecast.canonical import code_digest; print(code_digest())"`，3.12 與 3.13 結果相同。
  - 涵蓋範圍：`app/forecast`、`app/outlook`、`app/dirdef` 的全部 `*.py`，加上 `app/data/session_calendar.py`。
  - 算法：各檔把 CRLF／CR 正規化成 LF 後取 sha256，再把 `[app/路徑, sha256]` 清單經 `canonical_sha256` 雜湊。
- **期望值清單：**
  - 程式與測試裡沒有任何地方釘這個值。測試都以執行期的 `code_digest()` 比對；`test_cg2_register_addendum3.py::test_p1_no_code_digest_constant_is_pinned_and_the_tree_id_constant_stays` 還釘住了「登記腳本不帶 digest 常數」。
  - 已更新：範圍清單 `work/reviews/2026-11-19-接線PR範圍清單-dev-lead.md` 的「PR 說明用的材料」寫入新值。
  - 沒有更新（屬存檔紀錄或 coordinator 的檔，請 coordinator 決定）：
    - `work/dispatch/2026-10-17-後續追蹤清單.md`（前置清單）
    - 第二、三、四輪的交件存檔
    - TA 裁示檔

**第 4 項：祈使句掃描的設計**
- 收集範圍：以 AST 收集 `app/` 內所有以 `forecast_record:` 開頭的字串字面。隱式串接會合成一個常數；f-string 把字面部分接起來讀，子節點不重複計。
- 判定規則：出現 `please`，或某個子句（前綴之後，或 `; . : , (` 之後）以指示動詞開頭，就算祈使句。動詞清單：restart、rerun、run、retry、install、delete、remove、close、open、start、stop、tell、contact、ask、check、fix、set、update、try、wait、use、load、reload 等。
- 為什麼不會恆真：
  1. 測試先要求掃描找到現有全部 10 行（`recorder` 3 行、`scheduler` 3 行 WARNING 加 4 行 refusal，以各常數的執行期值比對）。掃描是空的或壞了就會失敗。
  2. teeth 測試餵入舊的 RC-331 字面，以及 `run the bootstrap`、`please close`、`delete it`、`Retry later`、`(install it)`、`Tell the coordinator` 這幾種，都必須被抓到；名詞用法如 `the run is skipped`、`this run keeps …` 則必須不被抓到。
  3. 我做了變異測試：把常數改回舊字面，RC-331 的兩支與 RC-333 主測試共 3 支都會失敗。
- 限制：這是關鍵字規則，不是語法分析；清單外的祈使動詞抓不到。

**第 5 項：登記腳本與 `code_digest`、tree id（只查證，沒改任何登記相關檔）**
- **`code_digest`**：`scripts/cg2_register.py` 的 `prechecks` 在執行時以 `canonical.code_digest(backend_dir / "app")` 現算，並印成 `code_digest=<hex>` 輸出行（白名單 regex 只檢查是 64 位十六進位）。
  - 它記下的是「執行登記時那個 checkout」的值，不是常數；`Pins` 沒有任何 digest 欄位。
  - 登記在登記分支（product）上執行，這支分支的改字影響不到它。
- **已登記的值**：登記的是定義雜湊與規則雜湊。`app/dirdef`、`app/outlook/rules` 相對 `9d5bbf48` 零差異，不受影響。
- **tree id**：`REAL_PINS.app_tree_id = 9c157d8640fb97d7e90dc7edc3f5ff0252aa00d7`，經 `git rev-parse 9d5bbf48:apps/stock-desk/backend/app` 核對，正是登記 PR head 的 `app/` tree。
  - 這支分支的 `app/` tree 是 `db8c60f4…`，接線以來本來就不等於 pin，所以 R-1 測試在這支分支上預期失敗。這次改字不會動到 pin，也不會影響登記一鍵檔在 product 上的判斷。
- **順帶看到**：`origin/product/stock-desk` 目前的 `app/` tree 是 `07b5e1fd…`，也不等於 `9c157d86…`（最近一個碰 `app/` 的 commit 是 `10fbdf9`，docstring 修改）。這與本輪無關，但登記一鍵檔若在 product 現況上執行，R-1 會 STOP。請 coordinator 或 devops-sre 留意。

## 驗證

- **全套**（head `2a48af3`，含 `--cov=app --cov-fail-under=90`）：

  | 版本 | 結果 | coverage | 耗時 |
  |---|---|---|---|
  | 3.12 | 13455 passed、1 failed（R-1）、2 xfailed | 97.83% | 56:55 |
  | 3.13 | 13455 passed、1 failed（R-1）、2 xfailed | 97.83% | 54:39 |

- 全套輸出：
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round5-full-312.log`
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round5-full-313.log`
- **ruff 與 mypy**：兩個版本都全過（`ruff check`、`ruff format --check` 568 檔、`mypy app tests` 554 檔）。輸出：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round5-lint.log`
- **零刪除**：`git diff --numstat df536340 HEAD -- service.py index.py` 仍是 `154 0`、`138 0`。
- **`app/` 的差異**：相對上一輪 head `59b23e29`，只有 `app/forecast/recorder.py`（+1／−1）。其餘風控定稿字句沒有動。
- **鐵則**：沒有讀 `.env`、沒有碰 `data/*.db`、沒有執行 `.bat`，也沒有 force push、rebase 或 amend；只推到 `feat/nm5-wiring`。

## 偏離與沒驗證到的

- **commit trailer**：你指定的是「Claude Fable 5.2」，我照我自己環境的歸屬設定寫 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`，`Claude-Session` 那行相同。依規定，agent 訊息不能覆寫歸屬設定；若要改，請由使用者指示。
- **merge**：派工沒要求 merge，但我先 merge 了 `origin/product/stock-desk`，因為測試要讀 RC-331 報告。merge 帶進 product 上的 `test_r2_first_run.py` 修改（89+／5−）。
- **沒驗證到**：
  - 沒有在真的 scheduler 行程裡觸發這行 WARNING；只以常數與測試比對。
  - qa 的 RC-333 (a) grep 是另一份獨立核對，我沒有代做。

## 下一步

1. 請 qa 複審 RC-331：核對新的 `code_digest` `731e09f4…0c2b`，並辦 RC-333 (a) 的 grep。
2. coordinator：
   - 把前置清單與 PR 說明裡的 `e8e0fb63…` 換成新值，並記下「RC-331 改字已併入接線 PR」。
   - 留意 product 的 `app/` tree 已不是 `9c157d86`。
