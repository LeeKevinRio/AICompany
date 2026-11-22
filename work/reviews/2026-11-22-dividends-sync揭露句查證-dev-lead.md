# 2026-11-22 `app.dividends.sync` 揭露句查證（dev-lead）

- 查證分支：`product/stock-desk`
- 查證 HEAD：`5a66a4c8ee3ca77dbbe794d54e6fe8944c176262`（`git rev-parse HEAD`）
- 性質：只讀查證。沒有改任何產品檔、沒有 commit、沒有開分支、沒有跑測試，也沒有碰 `.env*`、`data/*.db`、`.bat` 或 `.claude/worktrees/`。
- 本文件只寫事實與推論，**不擬任何 CEO 可見字面**。字面由 risk-compliance-officer 定稿。

---

## 1. 本次結論

**做完了。** 三句都會進 API 回應，前端也都會逐字顯示在畫面上。三句的觸發條件都一樣：主 DB 的 `dividend_events` 表一筆都沒有（`is_synced()` 為 false）。其中兩句（回測、事件研究）現在仍然是在叫人手動跑一行開發者指令。但 scheduler 從 2026-10-04 起已經會在平日 17:50／19:50／21:50（台北時間）自動呼叫**同一個** `sync_dividends`。所以這兩句的「手動指令」部分對 CEO 來說已經過時，括號裡的歸因（「未執行」那支 CLI）也不精確。Kelly 那句是「帶入當時」的歷史紀錄，過時程度較輕，但歸因有同樣的問題。另外，Kelly 寫入自 2026-10-26 起凍結，不會再產生新的列。要改字的話，會牽動 3 支逐字測試和 5 份 golden JSON（共 9 處）。

---

## 2. 各部門回報

- **dev-lead**：依任務 1～6 讀碼查證，結果如下。每點都分成「事實／推論／未查證」。

### 問 1：三處完整字句與 API 出現條件

**事實**

- **(A) 回測**：`apps/stock-desk/backend/app/api/backtest.py:138-142` 的 `DIVIDEND_NOT_SYNCED_NOTE` 串接後，逐字如下：
  「本回測未還原除權息：本機尚未同步過任何除權息資料（未執行 uv run python -m app.dividends.sync）。台股高配息情況下，未還原的報酬率會低估。此低估（若發生）落在 Buy & Hold 與持有期間的報酬；策略欄因進出場時點不同，偏誤幅度不一定相同。」
  （後半句是 `DIVIDEND_BIAS_SCOPE_NOTE`，在 `backtest.py:135-137`。）
  - 端點：`POST /api/backtest`（router prefix 在 `backtest.py:78`，handler 在 `backtest.py:597`）。另外 `POST /api/kelly-inputs/{symbol}/import-backtest` 也會內部重跑同一段回測。
  - 欄位：這句**同時**出現在兩個地方：
    - 回應的 `notes[]`：`backtest.py:254-260` 放進 `notes=[DIVIDEND_NOT_SYNCED_NOTE]`，`backtest.py:540` 再合併進 `notes`。
    - `dividend_adjustment.note`：`_dividend_block` 在 `backtest.py:214`，以 `dividend_notes_by_code(market)` 取 `"never_synced"`，見 `backtest.py:180`。
  - 觸發條件：
    - `adjust_dividends` 為 true（預設值，見 `backtest.py:325` 附近 `BacktestRequest.adjust_dividends: bool = True`）；
    - `store.is_synced()` 為 false（`backtest.py:254`）；
    - 回測有產出報告。資料不足時走 `unavailable()`，`reason_code="not_run"`，不帶這句（`backtest.py:484-506`）。
  - `is_synced()` 的定義是 `count() > 0`，也就是 `SELECT COUNT(*) FROM dividend_events`（`app/dividends/store.py:351-360`）。它**不看** `dividend_sync_runs`，也不分市場：US 回測在 store 全空時同樣會拿到這句（`is_synced` 的判斷在 market 分支之前）。
- **(B) Kelly**：`apps/stock-desk/backend/app/api/kelly_wording.py:537-540` 的 `KELLY_DIVIDEND_NEVER_SYNCED_FACT`，逐字如下：
  「這筆 Kelly 輸入所依據的回測，回測帶入當時本機尚未同步過任何除權息資料（尚未執行 uv run python -m app.dividends.sync）。」
  - 它不會單獨出現，而是由 `kelly_dividend_note("never_synced", ...)` 依序組成一整塊（`kelly_wording.py:582-621`）：fact ＋ E1 ＋ E2 ＋ `KELLY_DIVIDEND_STATE_AS_RECORDED_NEVER_SYNCED`（「此為回測帶入當下記錄的狀態，顯示時本系統依當時記錄呈現（含是否已完成同步）。」，`kelly_wording.py:512-514`）＋ E4。
  - 端點：`GET /api/kelly-inputs/{symbol}/disclosures`（`app/api/kelly.py:1142`，prefix 在 `kelly.py:190`）。
  - 欄位：`disclosures.sample_detail.rows[]` 中 label 為 `KELLY_DETAIL_DIVIDEND_LABEL` 那一列的 `note`（`kelly.py:786-788`）。
  - 觸發條件：
    - 該 Kelly 列 `source == "backtest"`（`kelly.py:997` `imported = row.source == "backtest"`，`kelly.py:1002` 只對 imported 產生 `sample_detail`）；
    - 該列儲存的 `dividend_reason_code == "never_synced"`（`kelly.py:690-704`）。這個值在 import 當下由回測回應的 `dividend_adjustment.reason_code` 寫入（`kelly.py:1604`），之後不會再更新。
  - Kelly 寫入自 2026-10-26 起凍結：`app/kelly/freeze.py:33` 有 `KELLY_INPUT_WRITES_FROZEN: Final = True`；import 路由在 `kelly.py:1431-1432` 拒絕寫入。
- **(C) 事件研究**：`apps/stock-desk/backend/app/backtest/event_study.py:582-585`，`dividend_sentence("never_synced", ...)` 回傳的句子逐字如下：
  「未還原除權息：本機尚未同步過任何除權息資料（未執行 uv run python -m app.dividends.sync）；報酬若實際有配息會低估。」
  - 端點：`POST /api/event-study`（`app/api/event_study.py:38`、`:147`）。
  - 欄位：`page.header[]` 裡 `role == "notice"` 的那一項的 `text`。路徑是 `event_study.py:172-187` → `app/backtest/event_study_page.py:161` 的 `header.extend(HeaderItem("notice", line) ...)`。
  - 觸發條件：這個端點固定以 `requested=True` 呼叫同一個 `resolve_dividend_adjustment`（`api/event_study.py:172-174`），所以條件同樣是 `dividend_events` 為空，且日線數量達到 `MIN_BARS`（不足時走 `insufficient_data`，不帶這句，見 `api/event_study.py:154-166`）。
  - 同一句也會出現在 CLI `python -m app.backtest.event_study` 的輸出，路徑是 `event_study.py:627-628` → `event_study_page.py:256`。但那是終端機輸出，不是 API。

**推論**

- 三句共用同一個觸發來源：`dividend_events` 表全空。只要成功同步過一次（CLI 或 scheduler 都算），A、C 兩句在這台機器上就不會再出現，因為 `dividend_events` 沒有刪除路徑（store 內只有 append-only trigger 的 SQL，沒有 app 端的 DELETE）。B 則不同：B 是已儲存列的歷史值，與目前 DB 狀態無關，只要那筆 Kelly 列還在就會持續顯示。

**未查證**

- CEO 本機目前 `dividend_events` 是否為空，以及有沒有 `dividend_reason_code='never_synced'` 的 Kelly 列。這兩件依規定不碰真實 DB，所以沒查。

### 問 2：前端是否顯示

**事實**

- **(A) 回測頁 `/backtest`**：
  - `apps/stock-desk/frontend/app/backtest/BacktestReportView.tsx:659-680` 在 `report.notes.length > 0` 時把 `report.notes` 全部逐條渲染成 `<li>`。旁邊另有「除權息資料最近同步時間：…／尚未同步過」一行（`:673-677`）。
  - 前端**沒有**讀 `dividend_adjustment.note`（全前端只讀 `dividend_adjustment.last_synced_at`，見 `:675-676`）。所以實際上畫面上看到的是 `notes[]` 那份。
  - 掛載點是 `app/backtest/page.tsx`。
- **(C) 事件研究**：
  - `apps/stock-desk/frontend/app/backtest/EventStudySection.tsx:145-149` 對 `result.page.header` 逐項渲染；`role === "notice"` 會畫成有框的 `<p>`。
  - 顯示條件：使用者在 `/backtest` 已有報告、表單沒有變動、按下事件研究按鈕，且 `result.page` 不為 null（`:100-143`）。
- **(B) Kelly**：
  - `apps/stock-desk/frontend/app/settings/KellyDisclosuresPanel.tsx:230-243` 在 `disclosures.sample_detail !== null` 時逐列渲染 `DetailRow`；`row.note` 不為 null 時以 `<span>` 原樣顯示（`:120-126`）。
  - 掛載點是 `app/settings/page.tsx` → `KellyInputsSection.tsx:128`。
- 前端原始碼裡沒有任何地方另外寫死 `app.dividends.sync` 字樣（`git grep` 在 frontend 只找到 `roundTripFixtures.ts:295` 的 `reason_code: "never_synced"`，而且那裡 `note: null`、`notes: ["note-one"]`，不含該字面）。
- 既有實機紀錄（他人文件，不是我這次重現的）：
  - `work/reviews/2026-10-26-產品審視-frontend-engineer.md:76` 記錄 `/backtest` 結果頁內文出現 `uv run python -m app.dividends.sync`；
  - `work/reviews/2026-10-13-KT-1-實機驗收代跑-qa-automation.md:335` 記錄 Kelly 明細列的 DOM 有「…（尚未執行 uv run…」。

**推論**

- 三句一旦進入 API 回應，在畫面上都是可見的，沒有被前端過濾。

**未查證**

- 我這次沒有實機開畫面重現。

### 問 3：scheduler 是否定時跑除權息同步

**事實**

- Job id 是 `dividend_sync`（`apps/stock-desk/backend/app/scheduler.py:184`）。
- 註冊位置在 `build_scheduler`（`scheduler.py:618`）內的 `scheduler.py:690-703`：
  - `CronTrigger(day_of_week="mon-fri", hour="17,19,21", minute=50, timezone="Asia/Taipei")`；
  - `max_instances=1`、`coalesce=True`；
  - **沒有** `next_run_time`，也就是啟動時不跑（`:702` 註解，以及模組 docstring `:48-58`）。
- 呼叫鏈是 `_guarded("dividend_sync", run_dividend_sync)` → `run_dividend_sync`（`scheduler.py:542-601`）→ `sync_dividends(store=target, adapter=adapter, trigger="scheduled")`（`:584`）。
- CLI `main()` 呼叫的是同一個 `sync_dividends(store=store, adapter=adapter, trigger="cli")`（`app/dividends/sync.py` 的 `main()`）。兩者的差別只有三點：
  - `trigger` 值不同；
  - scheduler 在「該台北日期已有 `ok` run」時跳過（`scheduler.py:566-573`，查的是 `dividend_sync_runs`）；
  - CLI 每次都會抓。
  兩邊的請求間隔都是 0.5 秒（`scheduler.py:186-187`；CLI 在 `sync.py` 的 `main()`）。
- 實作 commit：`4b47940`（2026-10-04，「feat: 排程新增 dividend_sync（平日 17:50／19:50／21:50 台北）…」）。三句字面的落地時間都比它早：
  - `8d81825` 2026-08-10（A）；
  - `6d564cc` 2026-08-22（B）；
  - `3fe176b` 2026-09-09（C）。
- `apps/stock-desk/backend/README.md:196-201` 已有說明，指出 scheduler「呼叫與 CLI（`python -m app.dividends.sync`）相同的 `sync_dividends`」。
- scheduler 的啟動方式：
  - `compose.yaml:46` 有 `scheduler` service；
  - `dev-up.sh:102-103` 會起 scheduler；
  - `dev-up.bat:166` 的內容是 `start "stock-desk scheduler" ... uv run python -m app.scheduler`（只讀了這一行，沒有執行）。
- 失敗語意：
  - 來源失敗，或回 ok 但沒有事件，都記成 `failed` run，不會寫入 `dividend_events`（`scheduler.py:589-591` 註解；`sync.py` 的 `sync_dividends` docstring）；
  - 下一個時點會重試；
  - 沒有任何環境變數可以關閉這個 job（README `:199`；測試 `test_no_environment_switch_names_the_job`）。

**推論**

- 就「把 TWT48U 寫進 `dividend_events`」這件事來說，scheduler 的 `dividend_sync` 和 `python -m app.dividends.sync` 是**同一件事**：同一個函式、同一個來源、同一張表、同一個 upsert。

**未查證**

- CEO 本機 scheduler 是否長時間在跑，以及是否跨過平日 17:50 的時點（要看 `logs/scheduler.log` 或 `dividend_sync_runs`，這次沒讀）。

### 問 4：這句話對 CEO 現在是否過時（只寫事實與推論，不擬字面）

**事實**

- A、C 兩句的括號把「未還原」的原因寫成「未執行 uv run python -m app.dividends.sync」。
- 測試 `tests/test_api_backtest_dividends.py:269-271` 的 docstring 明講這是一個「suggested fix」，而且要求「the pasted command works verbatim」。也就是說，A 句被設計成叫使用者貼上執行的指令。
- B 句的設計理由寫在 `kelly_wording.py:533-536`：「the actor is the user, so naming the step they have not taken is a fact about this machine」。這段理由寫於 2026-08-22，當時 scheduler 還沒有 dividend_sync。

**推論**

1. **「叫人手動跑」這層意思已經過時（A、C）。** 自 `4b47940` 起，只要 scheduler 在跑，而且跨過一次平日 17:50／19:50／21:50 並成功抓到資料，`dividend_events` 就會自己長出資料，CEO 不需要手動跑指令。
2. **括號裡的歸因本身不精確（A、B、C 都有這個問題，而且 scheduler 上線前就存在）。** 觸發條件是「`dividend_events` 為 0 筆」，不是「CLI 沒跑過」。下面這些情境都會出現同一句，但「未執行」那一段是錯的：
   - CLI 跑過，但連線失敗或回空；
   - scheduler 已經跑過但都記成 failed；
   - 這台機器只靠 scheduler，從未用過 CLI。
3. **現在仍會出現「未還原」的真實情境**（也就是句子前半「本機尚未同步過任何除權息資料」仍然成立的情況）。從讀碼可以推出：
   - 新安裝後還沒跨過第一個平日 17:50；
   - 週末或只在白天開機（job 沒有啟動時補跑）；
   - scheduler 沒有起來（例如只手動起了 API）；
   - TWSE 來源連續失敗；
   - 預告表當下沒有任何事件。
   在這些情境下，「手動跑 CLI」仍然是一條有效的補救路徑，只是不再是唯一的路徑。
4. **指令本身對 CEO 也有可用性問題（推論，未實測）**：
   - 句子沒有說明要在 `apps/stock-desk/backend` 目錄下執行（`-m app...` 依賴 cwd）；
   - 沒有帶 `--env-file ../.env`。依 `apps/stock-desk/README.md:145-149、272-278`，手動 `uv run` 不帶 `--env-file` 就讀不到 `.env`。如果 `.env` 有設定 `STOCK_DESK_DB_PATH`，裸跑 CLI 可能會寫到與 API 不同的 DB；
   - 在 compose 部署下，主機上裸跑也會寫到 volume 之外的 DB（`compose.yaml:43-45`）。
   這幾點與 frontend-engineer 10-26 指出的「開發者語言」是同一類問題。
5. **B 句（Kelly）過時程度較輕。** B 句明確是「回測帶入當時」的歷史紀錄，旁邊還有 E3 的「依當時記錄呈現（含是否已完成同步）」。它不是行動指示，所以 scheduler 上線不會讓「當時未同步」變成錯的事實。不過推論 2 的歸因問題同樣適用。另外，寫入凍結後已不會產生新的 B 列；但 `kelly.py:997-1002` 產生 `sample_detail` 只看 `source == "backtest"`，我沒有看到以過期（`KELLY_STALE_AFTER_DAYS = 30`，`app/kelly/models.py:66`）為條件的閘門。所以舊列只要沒被刪除，就會持續顯示這句。
6. **程式內部的過時敘述（不是 CEO 可見文字，順帶記錄）**：
   - `app/dividends/sync.py:8-10` 檔頭寫「同步動作由 CEO（或任何有網路的機器）手動觸發」；
   - `app/api/deps.py:267` 寫「empty until the CEO runs `python -m app.dividends.sync`」；
   - `tests/conftest.py:70` 的註解。
   這三處都早於 scheduler，沒有提到自動同步。

**未查證**

- A 句（`DIVIDEND_NOT_SYNCED_NOTE`）有沒有獨立的風控逐字核可紀錄：
  - `backtest.py:113-118` 列出的已核可清單裡沒有它；
  - `work/reviews/波次1文案裁決.md` 用 grep 搜「未同步／never_synced／dividends.sync」都沒有命中；
  - `work/reviews/2026-09-12-事件研究網頁版-審查全文.md:228` 對 C 句寫的是「`never_synced` … 維持既有核可字面」。
  - B 句的核可紀錄在 `work/reviews/2026-08-19-C5-Kelly-文案批審.md:443`（第八輪）。
  - A 句的核可出處請風控自行確認。

### 問 5：釘住字面的測試，以及改字會牽動什麼

**事實（後端測試）**

- `tests/test_api_backtest_dividends.py:269-271` 的 `test_the_sync_command_is_quoted_the_way_it_is_actually_run`：斷言 `"uv run python -m app.dividends.sync" in DIVIDEND_NOT_SYNCED_NOTE`（子字串）。同檔 `:250-266` 另外斷言每一句降級文案都含 `DIVIDEND_BIAS_SCOPE_NOTE`，而且不含「系統性低估」「確定」。
- `tests/test_api_event_study.py:291-296` 的 `DIVIDEND_SENTENCES_PINNED[("never_synced","TW")]`：C 句**逐字**比對。
- `tests/test_kelly_wording.py:217-220` 的 `CONFIRMED_VERBATIM["div-never-synced"]`：B 句**逐字**比對，由 `test_each_approved_sentence_ships_character_for_character`（`:441-447`）執行。此外還有兩個連帶守門：
  - `test_the_batch_is_every_sentence_the_review_has_closed_on`（`:391-438`）斷言清冊數量是 84，而且 key 集合要與 `kelly_wording.py:1166-1169` 附近的 `SHIPPED` registry 相等；
  - `test_the_never_synced_state_sentence_keeps_its_parenthesis`（`:853-870`）釘住 E3 括號版。
  - 另外 `REJECTED_LITERALS`／`test_an_approved_opening_is_never_followed_by_an_unapproved_remainder`（`:938`）等反向守門，對新字面也會生效。
- Golden 測試（`tests/test_golden_backtest_outputs.py`，比對 `_assert_matches_golden`，用 `STOCK_DESK_UPDATE_GOLDEN=1` 重產）：
  - A 句在 `tests/golden/backtest/` 的 4 個檔各出現 2 次（`dividend_adjustment.note` 與 `notes[]`），共 8 處：
    - `breakout.json:2453、2464`
    - `five_conditions.json:2413、2425`
    - `ma_cross.json:2343、2354`
    - `rsi_reversal.json:2323、2334`
  - C 句在 `tests/golden/event_study/walk.json:48`，共 1 處（比對位置在 `test_golden_backtest_outputs.py:492`）。
- 前端測試沒有釘住這幾個字面（見問 2）。

**事實（文件，含字面或指令的地方）**

- 程式內註解與 docstring：
  - `backtest.py:111-118`（文案狀態說明）
  - `kelly_wording.py:533-536`（B 句的設計理由）
  - `event_study.py:568-569`（docstring 提到 2026-09-11 R5 的風控審查）
  - `deps.py:267`、`sync.py:1-10`、`tests/conftest.py:70`
- 過程文件（歷史紀錄，是否回改屬於流程決定）：
  - `work/stock-desk-C5-Kelly-揭露文案起草.md:996、1044、1298、1301、1307`
  - `work/reviews/2026-08-19-C5-Kelly-文案批審.md:443`
  - `work/stock-desk-五條件回測-方法論.md:314`
  - `work/事件研究-除權息句-起草.md:92`
  - `work/reviews/2026-10-26-產品審視-frontend-engineer.md:76`
  - `work/reviews/2026-11-22-RC529補普查與再掃-tech-architect.md:35、81、117、123、144`
  - `work/dispatch/2026-10-17-後續追蹤清單.md:756`

**推論**

- 改 A 句：至少要改 `test_api_backtest_dividends.py:271`（這條斷言的本意就是「指令必須在句中」，改字時要一起重新決定這條測試還要不要存在），並重產 4 份 backtest golden。
- 改 C 句：要改 `test_api_event_study.py:293-296`，並重產 `event_study/walk.json`。
- 改 B 句：要改 `test_kelly_wording.py:217-220`。如果還要調整 `kelly_wording.py:533-536` 的理由註解，要一起改。依該檔慣例，改字一律視為漂移，須重送風控。
- A、C 兩句的字面不同（A 有「本回測」並串接 BIAS_SCOPE，C 沒有），屬於不同常數，要各自定稿。

### 問 6：查證基準

**事實**

- 查證時在 `product/stock-desk`，HEAD 為 `5a66a4c8ee3ca77dbbe794d54e6fe8944c176262`。`git status --short` 沒有輸出，工作樹是乾淨的。

---

- **risk-compliance-officer**：本次未參與。字面是否要改、要怎麼改由風控定稿；本文件只提供事實。
- **其他部門**（product-manager、tech-architect、frontend-engineer、qa-reviewer、qa-e2e、qa-automation、devops-sre 等）：本次未參與（純只讀查證）。

---

## 3. 驗證

- 用了哪些方法：
  - `git rev-parse`、`git status`、`git log -S`（追字面與 job 的落地 commit）、`git grep`；
  - Read／Grep 讀碼。
  - 沒有跑 pytest 或 Python，因為所有問題讀碼都能回答。
  - 也沒有實機開畫面；畫面上可見這件事，是依前端渲染碼，加上兩份既有實機紀錄（frontend-engineer 10-26、qa-automation 10-13）得出的。
- 想複核的人可以這樣做：
  - 在上述 HEAD 執行 `git grep -n "dividends.sync" -- apps/stock-desk`，應該會對到本文列出的所有位置；
  - 執行 `git show 4b47940 --stat`，確認 scheduler job 的落地日期。
- CEO 不需要親自驗證任何東西。

## 4. 下一步

1. 把本文的事實交給 risk-compliance-officer，由他判斷 A、B、C 三句是否改字、怎麼改，並補上 A 句核可出處的確認。
2. 風控定稿後，由 dev-lead 依定稿改常數，並連動問 5 列出的 3 支測試與 5 份 golden（要另開任務單，不併入現有文件 PR），再交 qa-reviewer（含 Codex）審查。
3. 程式內註解的過時敘述（`sync.py:8-10`、`deps.py:267`、`conftest.py:70`）不涉及 CEO 可見字面，可以在同一支 PR 順手修正，或另外處理，由 coordinator 決定。
