# F-9b2 程式審查（febd6a9..a2f8b2a）— qa-reviewer

> 轉存：coordinator，2026-10-14，子 agent 回報逐字轉存。Codex 第二意見未執行（環境不可用）；本審查 PASS 附條件：合併前補 Codex 或 CEO 明示放行。

---

## Summary
F-9b2（febd6a9..a2f8b2a，5 個 commit）的實作與 ADR-0024 D-9、D-2 (5)(a) 第 1～3 步、D-2 (5)(c) 相符，我沒有找到 critical 或 high 問題。第 4、5 步程式實質未動，T-14 兩句與 C′ 逐字等於裁定原文，app 內沒有 C 版。遷移照 kelly store 已驗證的做法，競態處理正確。測試有牙，每項都有無標記的 control 對照。有 3 項 non-blocking 觀察與 1 項文件跟進，列於後。

限制（請 tech-architect 與 CEO 知悉）：
- 我的 Bash 只准 `git diff` 與 `codex`，所以沒有跑 pytest、ruff、mypy。「6666 passed／21 mutation 全擋」我沒有重現，只能靠讀碼與讀測試判斷測試有牙。
- 第二意見（Codex）無法取得：`codex: command not found`，沒有 Codex 輸出可摘錄。依紅線，缺 Codex 時不能給無保留的 PASS。以下 PASS 附帶條件：合併前補一輪 Codex，或由 CEO 明示放行。
- 我另用了 `git log --format`、`git ls-files`，都是唯讀，但超出你指定的 `git diff`，在此揭露。

## 逐條勾核表

| 項目 | 結論 | 依據（worktree 內檔案與行號） |
|---|---|---|
| C-23 遷移 | 落實，測試有牙 | 實作在 `app/data/cache.py` 的 `_migrate_attempt_log_marker`（約 L118-150），`_init_schema` L301 呼叫。測試在 `test_f9b2_attempt_log_marker.py`：L87 新庫、L98 舊庫兩欄為 NULL 且不回填、L116 重複初始化不改值、L131 雙實例、L146 敗方強制讓未上鎖檢查過期（能抓到「鎖內不重檢」）、L177 四執行緒。 |
| C-24 有效性 | 落實 | `_valid_marker` 同時要求 `rejection_at == last_attempt_at` 與 `attempted > last_fetched_at`；`fetch_log` 主鍵為 (symbol, market)，LEFT JOIN 不會產生重複列。測試 L286 與 L299（逐字使用舊 upsert SQL）。服務層測試在 `test_f9b2_marker_guard.py` L617、L639。 |
| C-25 有效 W-c | 落實 | 實作為 `service.py` `_marker_step`（L787-852）。測試 L297 涵蓋 5 種快取狀態，每種都有無標記的 control；另有 L396（停用增量）、L667（cache-only，冷卻內外各一）。 |
| C-26 W-c′ | 落實 | 實作為 `_marker_step` 的 `elif cooling and not usable_cache`（L828）。測試 L476（無快取與被擋兩種，完全相等，斷言不含 T-15 與 RECENT，provider 零呼叫，`bars=[]`）、L521、L545、L562、L577、L597。 |
| C-27 清除與優先 | 落實 | `record_attempt` 三欄同時覆寫，沒有 COALESCE（`cache.py` 約 L472-480）。`_marker_to_write` 以 W-c 優先（`service.py` L529-546）。測試 L884（5 種梯子）、L916（成功、W-c′ 後成功、靜默失敗、有原因失敗，各乘兩種前次標記）。 |
| C-31 不寫快取類別 | 落實 | `record_attempt` 對 `AttemptRejection` 以外的值 raise ValueError。`_marker_to_write` 只看 live 的 `refusals`，不看快取類別。測試 `test_f9b2_attempt_log_marker.py` L238，`test_f9b2_marker_guard.py` L926、L936。F-9b 原式（不新增記錄點）未動。 |
| C-13 (6) | 落實 | 美、台兩句各一測，經 `load_bars` 完全相等（guard L297、L332、L1031）。`test_f9b_load_bars_wd.py` 的 C 案改為 T-14-US、T-14-TW 兩案。 |
| C-17 | 落實 | `deps.py` 指數 `rejection_marker=False`。建構時指數加 True 或 `wording=None` 加 True 會 raise（`service.py` L457-460）。測試 L746（2 標記乘 2 快取乘 2 冷卻，兩個入口與 provider 呼叫全等）、L773、L799（AST 逐站字面）、L819、L964。 |
| TA5 R-64（第 2 步） | 落實 | `(None, True)` 讓 `fetch_start = start`（`service.py` L334）。測試 L396 有 control 證明未標記時會縮成尾段。 |
| 第 4、5 步零改變 | 成立 | `_try_session_fresh_cache`（L760-785）只多一行 `marked = ...` 的早退。`not refused` 與原 `cached is None or not _cache_refuses(...)` 等價，`_cache_refuses` 的呼叫次數與時點不變。第 4 步以後的程式一字未動。 |

## T-14 與 C′ 逐字（F9W-21）
- 我用同一條嚴格 regex 比對，裁定檔 L32、L35、L37 各命中，`gate_wording.py` L102-104、L113-115、L126-128 的 9 個片段各命中同一模式。片段順序與拼接結果等於裁定原文，標點為全形。
- 測試 L217-229 讀裁定原行比對。
- 我以 Grep 搜尋整個 `apps/`，C 版特有子句「標示的價格單位與市場所用的單位不同」只剩 T-15（`gate_wording.py` L87）與 `advice/book.py` L232 的各自不同句，C 版本身不存在。T-14 取 `market` 是呼叫的序列鍵，C′ 不分市場。
- 三個常數都帶「風控核可文案，修改須重新送審」註記與出處；C′ 引用了 F9W-20、F9W-23、F9W-30 三者。

## 遷移
- 做法：`PRAGMA table_info` 無鎖檢查，`BEGIN IMMEDIATE` 後重檢，再 `ADD COLUMN`，兩欄在同一交易內。`except BaseException` 先 ROLLBACK 再 raise。結構與 `kelly/store.py` L168-184 已驗證的做法相同。
- 前置 `enable_wal` 與 busy_timeout 已處理 WAL 切換的 BUSY。沒有回填，也沒有 DEFAULT。
- 舊程序 upsert 只動 `last_attempt_at`，使 `rejection_at != last_attempt_at`，標記失效（C-24）。若舊程序的 `last_attempt_at` 恰好等於 `rejection_at`，只有同一時間戳碰撞才會誤判，實務不可達；即使碰撞，舊程序成功路徑也會讓 `last_fetched_at` 追上，標記仍失效。

## 實作者疑點的判斷（項目 6）
1. `rejection_marker` 必填參數：同意保留。D-4、TA5 R-59 要求「由建構點顯式設定」，獨立布林比綁 `wording is not None` 更貼字面。建構期互斥檢查封住「指數加 True」。唯一代價是「equity 有 wording 卻 False」是合法組合，會靜默關掉持久化。但 deps 三站有 AST 測試釘字面，風險已受控。請 tech-architect 順手確認；ADR C-6 的建構點清單沒有列第五個必填參數，建議補一句（文件跟進）。
2. 「讀回被擋視為有層取得資料，不寫標記」：與 D-9「沒有任何一層取得可用資料」字面一致，可接受。但 PR 說明 (i)3 寫「只在另一程序寫入壞列時出現」不夠精確。`service.py` L384-394 的 `merged is None` 分支也會讓 `obtained=True` 而不寫標記，那條不是競態。見下方 non-blocking 1。
3. W-c′＋通過快取仍寫 `unit_missing`：正確。快取不是梯子的「層」，D-9 與 T-17（F9W-24）要求這個標記存在，冷卻內下一次才會走 R-8 回 RECENT。測試 L893 釘住。
4. 有效 W-c＋被擋快取每次留 WARNING：這是 D-2 (5)(a)「讀出整段快取後、所有分支之前檢查一次」的直接後果。F9W-35 (c) 的不降噪是針對指數路徑，股票路徑多一筆操作端記錄無使用者面影響。可接受，不建議為此打破 ADR 的順序。

## F11-W-38 交互（項目 5）
- 我核對程式後，PR 說明 (g) 的三個前提都成立：
  - 寫入 `unit_mismatch` 時 `"unit_mismatch" in refusals`，必定走 L453 的 `_refused_answer`，到不了 `_fall_back_to_cache`。
  - 最終 `record_attempt` 在讀任何快取之前執行（L447-452）。
  - `_fall_back_to_cache` 本身不讀標記，所以它回覆時只可能有本次剛寫的 `unit_missing`，而它對標記無感。
- 2e（有效 W-c 且冷卻外，梯子全靜默，快取通過）回 RECENT＋快取價格：這是 ADR D-2 (5)(a) 第 2 步與壞處 9 明寫的結果。RECENT 句屬實，是 W-38 已核可字面，與無標記序列在 REFETCH 的回覆完全相同，沒有新字串。
- 我另外推演了這些組合，都沒有新的使用者面字串，皆為既有核可句的獨立整句：
  - 2d。
  - 2c（C-34 (b)）。
  - 缺 `source_id` 的 W-c′（PR 說明第 7 列）。
  - 指數路徑。
  - 第 2 步＋被擋快取＋靜默梯子，回 T-15 單獨，與無標記相同。
- 附帶效果：同一序列在冷卻期內是 T-14（空白），冷卻期外靜默失敗後變成快取價格＋RECENT，畫面會交替。PR 說明已列「請風控知悉」，我同意。

## 各檔問題

### 阻擋（blocking）
無。

### 非阻擋（non-blocking）
1. `app/data/service.py` L384-394＋L447-452［Edge case］［low］：早一層通過閘門但合併讀回為 `None` 時 `obtained=True`，之後即使遇到 W-c 層也不寫標記，且最終回覆仍是 `_refused_answer`（帶 `unit_mismatch`）。下一次點擊沒有標記，快取（含該層新尾段）可能在冷卻期內回價格。與 D-9 字面一致，不改程式。建議把 PR 說明 (i)3 改成「讀回為 None 或被擋兩種」，並把這個殘留一併列給風控知悉。
2. `service.py` L819 與 L776/L882/L915/L963［可維護性、效能］［low］：layer 0 現在每次多一次 `last_attempt()`（含新連線），與後續 `last_attempt_at()` 分屬不同快照。功能上無害（R-8 判定本來就分開讀）。可選的後續：把兩次讀取合併，但這會動到第 4、5 步，F-9b2 不建議做。
3. `test_f9b2_marker_guard.py` L244-249［可維護性］［low］：測試直接 import 其他測試檔的私有函式 `_shared_forbidden_terms`，耦合；F-9b 同款做法，非新增問題。
4. 文件跟進［可維護性］［low］：ADR C-6 的建構點清單補 `rejection_marker`（見疑點 1）。

## 第 2 項：F-9b 既有測試未被放寬
PR 說明 (e) 的 5 項與 diff 逐項核對，都成立，沒有任何斷言被放寬或刪除：
1. `test_f9b_cache_currency_gate.py::_Cache.record_attempt`：只同步簽章並轉傳 `rejection`。
2. `test_f9b0_service_scope.py`：`GATE_ARGUMENTS` 多一項，只增加參數化案例；`test_an_unknown_scope_is_refused` 補必填參數。
3. `market_service_helpers.py`：`build_service` 顯式傳 `rejection_marker`。
4. `f9b_helpers.py`：刪 `C_COOLDOWN`，改指向 app 常數。全 `apps/` 已無 `C_COOLDOWN` 引用。逐字驗證已移到 `test_f9b2_marker_guard.py` L226。
5. `test_f9b_load_bars_wd.py::REFUSALS`：C 案改為 T-14-US、T-14-TW 兩案，分流斷言未動，`cooldown_hours` 用真實值（US 24、TW 1）。
- 沒有其他 F-9b 測試檔被改。

## 第 7 項：commit 1 歷史
- 線性鏈 a2f8b2a→2102506→91a1f4a→dcaaab0→926e143→febd6a9，無 merge。
- 926e143 自成一體：`cache.py`、新測試檔、F-9b 測試 stub 簽章同步，內容與「amend 併入 stub 修正」的說法一致。
- 我沒有用 `git show` 讀 commit message 本文，所以「訊息已註明 amend」只靠 PR 說明，未驗證。

## 第二意見（Codex）
無法執行：`codex: command not found`。沒有其他廠商的審查意見可摘錄。

## 唯讀權限判準常數
未觸及。
- `--name-only` 的 12 個檔案中沒有 `scripts/validate_agents.py`。
- 以 `git diff febd6a9..a2f8b2a --name-only -G"READONLY_AGENTS|READONLY_ALLOWED_BASH"` 取代兩道檢查中的 pipe 版本，結果為空。
- 因此沒有 agent 名單異動、常數的值未改，也沒有 shadow 定義。
- 本 PR 只動 `apps/stock-desk/` 與 `work/`，完全不涉及 `.claude/` 與 `scripts/`。

## 自我揭露
- 沒有跑 pytest、ruff、mypy（權限所限）。對「6666 passed」與「21 mutation 全擋」，我只做讀碼層面的有牙性判斷：每項關鍵行為都有 control 對照、完全相等斷言與強制競態注入。
- Codex 缺席，如上。
- 用了超出指令範圍的 `git log`、`git ls-files`（唯讀）。
- 未讀 `git show` 的 commit message 本文。
- 未讀前端與 `services/index.py` 本體，只用 Grep 確認其不引用 T-14/C′ 常數。

## Verdict
PASS（附帶條件：合併前補 Codex 第二意見，或由 CEO 明示放行；tech-architect 另行確認第 2、3 項後即可進風控字面把關與合併）。後端純邏輯，無 UI，不需 qa-e2e。

BLOCKING_ISSUES=false
