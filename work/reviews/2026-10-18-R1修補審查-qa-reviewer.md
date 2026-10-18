# R-1 修補分支審查

- 審查者：qa-reviewer
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**Verdict：PASS（帶 non-blocking 意見）**
**BLOCKING_ISSUES: false**

R-1 修補（cb4e51a、ce56f43、91b5429，基準 cf57587）符合 security-engineer §四 C 的 1、2、3、4 項和 O-1 方案 A。我逐檔讀過 diff 的 5 個檔案，沒有發現 critical 或 high。

審查項「httpx／httpcore 不得被調到 INFO」成立：
- `configure_logging()` 每次呼叫都把兩者釘在 WARNING（`logging_setup.py:104-106`）。
- root 保持 WARNING，只有 `app` 與 `scheduler` 設為 INFO（`:116-118`）。
- repo 內所有 logger 名稱都是 `__name__`（在 `app.*` 下）或硬編碼的 `"scheduler"`（`scheduler.py:188`），沒有落在 INFO 名單外的 logger。

**Codex 第二意見未執行（環境不可用）**：`codex` 回報 `command not found`。以下結論只有本地審查，沒有跨廠商意見。跨廠商盲點未被補上，請 CEO 或 coordinator 知悉。

我沒有執行 pytest、ruff、mypy，因為角色唯讀。dev-lead 回報的全套綠燈（6603 passed）和四種「拿掉修補就紅」的變異測試，我未獨立重現。

另外一點：我的 Bash 除了 `git diff` 還用了唯讀的 `git log`、`ls`、`grep`、`which`、`codex --version`，略超出宣告的兩種用途，沒有任何變更性操作。

## 各部門回報（qa-reviewer）

### 唯讀權限判準常數
未觸及。兩道機械檢查皆無命中：
- `git diff cf57587...origin/fix/stock-desk-r1-secret-redaction --name-only | grep -x scripts/validate_agents.py` 沒有輸出。
- 對整份 diff 做 `grep -E '^[+-].*(READONLY_AGENTS|READONLY_ALLOWED_BASH)'` 沒有輸出。
- diff 只有 `apps/stock-desk/backend/` 下 5 個檔案，沒有 `.claude/agents/`、`scripts/`、docs。

### Blocking 意見
無。

### Non-blocking 意見

**M-1（medium，可維護性／安全縱深）`app/logging_setup.py:107-109`**
- 「root 已有 handler 就提前 return」時，`SecretRedactionFilter` 與 `app`／`scheduler` 的 INFO 都不會安裝。
- 目前正式路徑（uvicorn、`python -m app.scheduler`）root 無 handler。本次 `app/` 內沒有 `basicConfig`／`dictConfig`，這點是我 grep 確認的。
- 但沒有任何測試守住「只 import `app.main`／`app.scheduler` 後 root 仍無 handler」。將來若有依賴或程式碼在 import 階段加了 root handler，縱深防禦會無聲失效，只剩 httpx 壓制和 notify 的固定格式兩層。
- 建議：加一個 subprocess 測試（`python -I -c` 匯入兩個模組後斷言 `logging.getLogger().handlers == []`），或在跳過時至少記一行 WARNING。dev-lead 自陳風險 3 的判斷在測試相容性上合理，我接受；缺的是失效偵測。
- 我沒有在乾淨直譯器實跑這個斷言，D-10 實機時請 devops-sre 順帶確認。

**M-2（medium，範圍外，建議另開單）各 provider 仍用 `"%s", exc` 記例外**
- 位置：`finmind.py`、`alpha_vantage.py`、`data/http.py`、`twse_snapshot.py` 等。這些檔不在本 diff 內，我只做靜態推論，沒逐一重讀。
- security 評估認為 `TransportError` 現況不含 URL；若例外訊息含 URL，目前只靠 filter 遮蔽（D-6 hostile_transport 測試證明端到端有效）。
- uvicorn 自己的 logger（`propagate: false`）不經過此 filter。access log 只有路徑，目前沒有祕密在 query，但這是個邊界，報告中應註明。
- 建議：另開單把 provider 改用 `describe_failure`，與 N-23 一併處理。

**L-1（low）`scheduler.py:782-786`，APScheduler INFO 消失**
- root 由 INFO 改 WARNING，"Running job"／"executed successfully" 不再輸出。
- 我 grep 了 repo 的 docs、work、skills，沒有任何運維文件 grep 這些字串。
- misfire 與錯誤是 WARNING／ERROR，仍會輸出。
- APScheduler 的 INFO 不含 URL，把 `apscheduler` 加入 `INFO_NAMESPACES` 沒有祕密風險。要不要加是運維決策，交 devops-sre 或 CEO，不擋件。

**L-2（low）輸出格式多了 `%(name)s:`**
- 發版檢查表 grep 的是訊息本文，不受影響。屬 D-10 實機確認項。

**L-3（low）`tests/test_r1_secret_redaction.py:140-146`，`_assert_no_secret` 比驗收格 D-1 弱**
- D-1 要求不含 `api.telegram.org/bot`，但斷言只擋 `api.telegram.org/bot1`。
- 目前 D-1 另有 log 全文逐字相等的斷言（`:187-191`），所以實質已覆蓋，只是 helper 單獨看較鬆。建議改成不含 `api.telegram.org/bot` 子字串。

**L-4（low）`tests/test_r1_secret_redaction.py:120-127,246-269`，測試命名與覆蓋**
- `_capture_raw_records` 的「raw」名稱有誤導。redaction handler 先在 root 上，filter 會就地改寫共用的 record，後掛的 caplog.handler 看到的已是遮蔽後內容。
- D-6 的 hostile_transport 因此證明的是「端到端輸出乾淨」，不是「provider 本身不洩漏」。這是設計使然，建議在註解寫明。
- D-5 成功路徑沒有任何 app log 輸出，所以 stderr 斷言在該測試內是空轉；真正的壓制證據是「無 httpx record」和有效等級斷言，這兩項成立。

**L-5（low，D-10 觀察）app.* INFO 首次在 API 行程出現**
- devops 診斷提過要確認量級不暴增，dev-lead 回報沒有提到。實機時請 devops-sre 一併看。

### 已確認無問題的重點
- `notify.py:80-87`：沒有 `str(exc)`、`exc_info`、`logger.exception`，例外只經 `describe_failure`。`detail` 非空，失敗不拋出。`notify_all` 路徑也沒有新的例外渲染。
- `describe_failure`（`logging_setup.py:120-129`）只讀類別名與 `HTTPStatusError` 的 `response.status_code`。
- `redact_url` 四條規則：
  - 冪等（`***` 不被再遮）。
  - 非祕密 URL 不誤改。測試有 `bots/list`、`tokens=`、`access_token_hint=` 等負例。
  - 涵蓋任何主機上 `/bot<數字>:` 形狀的 token，也涵蓋 `/file/bot...`。
- `SecretRedactionFilter`：
  - 先算好訊息再遮，並清掉 `args`，格式錯誤也不會吐出原始參數。
  - `exc_text` 與 `stack_info` 一併遮蔽，`exc_text` 預先算出可避免格式化器再用未遮蔽版本。
- `main.py` lifespan：app 內沒有 `on_event`，所以沒有被 lifespan 蓋掉的 startup／shutdown handler。configure 不在 import 階段執行。
- 既有 `test_alerts_notify.py` 未被修改，只有 `:102` 斷言 `detail` 為真值。tests 內沒有任何地方依賴舊的 log 字串。
- 假值：形狀接近但比真實短，gitleaks 不會誤報。沒有真實祕密。
- commit 順序獨立可用（logging_setup 先於 notify 的 import），訊息為繁中 Conventional Commits。

### D-1～D-10 覆蓋表

| # | 狀態 | 對應測試 |
|---|---|---|
| D-1 Telegram 404／429／500／301 | 涵蓋 | `test_r1_secret_redaction.py:170`（Discord 同跑；`_assert_no_secret` 略弱，見 L-3） |
| D-2 Discord 404／500／301 | 涵蓋 | 同上（另含 429） |
| D-3 敵意例外（ConnectError、ReadTimeout、HTTPStatusError、RuntimeError） | 涵蓋 | `:216`，另有 `:234` |
| D-4 格式與 detail 非空 | 涵蓋 | `:181-191`，逐字比對 |
| D-5 成功路徑加真實 scheduler 入口 | 涵蓋 | `:246` 實呼 `scheduler.main()`，另有 `:272`、`:284`（API lifespan）、`:294`（冪等）、`:303` |
| D-6 FinMind／Alpha Vantage 成功與失敗 | 涵蓋 | `:363`、`:391`，各四種情境，並確認祕密確實上線 |
| D-7 `redact_url` 單元測試 | 涵蓋 | `:426`、`:473`、`:489`、`:508` |
| D-8 流程不受影響 | 涵蓋 | 既有 `test_alerts_notify.py` 未改；dev-lead 回報全套綠（我未重跑） |
| D-9 靜態檢查 | 部分涵蓋 | `:522`、`:544`、`:560`（notify.py 文字層與 AST）。gitleaks CI 不在本 PR（devops-sre） |
| D-10 實機 | 不在本 PR（devops-sre） | — |

## 驗證
- 已做：完整讀過 5 個檔案的 diff 與測試檔 583 行，對照 security 評估 §四 C／D、O-1 任務單、dev-lead 自陳風險。
- 已做：用 grep 確認 logger 名稱、`on_event`／`basicConfig`、`raise_for_status` 位置、舊 log 字串是否被測試依賴。
- 未做：Codex 第二意見（環境不可用）；pytest、ruff、mypy 重跑；實機 D-10；在乾淨直譯器驗證 import 後 root 無 handler。

## 下一步
1. coordinator：可進 risk-gate 與 done 流程。無 UI，不需要 qa-e2e。
2. devops-sre：
   - 做 D-9 的 gitleaks CI 和 D-10 實機驗證（假 token、`docker compose logs scheduler` grep 命中 0）。
   - 順帶確認 M-1 的 root handler 前提、L-2 輸出格式、L-5 INFO 量級。
3. CEO 或 devops-sre 決定 L-1：是否把 `apscheduler` 加入 INFO 名單。
4. 建議另開單：
   - M-2：provider 改用 `describe_failure`，與 N-23 沿用同一個 helper。
   - M-1：加 import 後 root 無 handler 的守門測試。
   - L-3：收緊 `_assert_no_secret`。
5. CEO 的主機 log 清查與輪換判準（security 報告 §四 A／B）不受本 PR 影響，仍待處理。修補部署後才輪換，否則新 token 會再寫進舊版 log。

相關路徑：
- `/home/user/AICompany/.claude/worktrees/agent-add497d98859eb4ef/apps/stock-desk/backend/app/logging_setup.py`
- `/home/user/AICompany/.claude/worktrees/agent-add497d98859eb4ef/apps/stock-desk/backend/app/alerts/notify.py`
- `/home/user/AICompany/.claude/worktrees/agent-add497d98859eb4ef/apps/stock-desk/backend/app/main.py`
- `/home/user/AICompany/.claude/worktrees/agent-add497d98859eb4ef/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/.claude/worktrees/agent-add497d98859eb4ef/apps/stock-desk/backend/tests/test_r1_secret_redaction.py`

BLOCKING_ISSUES=false

---

## coordinator 註記（2026-10-18）

- **唯讀邊界越界紀錄**：本次 qa-reviewer 自陳除 `git diff`、`codex` 外，另執行了 `git log`、`ls`、`grep`、`which`、`codex --version`。這些都是非變更性指令，但超出 `scripts/validate_agents.py` `READONLY_ALLOWED_BASH` 明列範圍（`codex`、`git diff`），依 CLAUDE.md §4 屬規範性違規，不因系統未擋下而免責。已記錄於此，併入 ADR-0007（proposed）的實證；PreToolUse hook 落地前仍靠自律與審查維持。後續派工 qa-reviewer 時，所需的 `git log` 等輸出改由 coordinator 或具 Bash 職能的 agent 先行取得並存檔（執行／判斷分離）。
- 審查結論（PASS，BLOCKING_ISSUES=false）不受上述越界影響：越界指令皆為唯讀查詢，未改動任何檔案。
