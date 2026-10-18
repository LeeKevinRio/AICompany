# R-1 小修複審（aa1b2bd、686c3bb）

- 審查者：qa-reviewer
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**Verdict：PASS。BLOCKING_ISSUES: false**

M-1、L-3、L-4 都處理得當，增量 `aa1b2bd`、`686c3bb` 沒有發現新的 critical 或 high。守門測試的 subprocess 環境夠用，也沒有帶入祕密。我只做靜態審查，沒有跑 pytest、ruff、mypy。

**Codex 第二意見未執行（環境不可用）**：`codex --version` 回報 `command not found`。這輪只有本地審查，沒有跨廠商意見。

- **M-1（接受 dev-lead 的取捨）**
  - 提前 return 沒有改成把 filter 掛到既有 handler，我同意。filter 會就地改寫 `record.msg`，並把 `args` 設成 `None`。pytest 的 caplog 和既有測試會讀 `record.args`，所以 dev-lead 回報 8 個測試變紅是合理的。
  - 我上輪的建議本來就允許「守門測試」作為替代方案，這次採用了。
  - `logging_setup.py:109-113` 的英文註解如實說明原因，並指向守門測試。程式行為不變。
- **L-3 已處理**
  - `_assert_no_secret` 現在擋整個 `api.telegram.org/bot` 子字串，與 D-1 一致，遮蔽後的 `bot***` 也不放行。
  - Discord 的 `/api/webhooks/[^/\s]+/(?!\*\*\*)` 是正確的：id 後面只准接 `***`。
  - 我推演過回溯：`/api/webhooks/111/***` 不會誤中，`/api/webhooks/111/FAKE…` 與 `/api/webhooks/9/` 會被擋下。
  - 實際執行結果以 dev-lead 為準，我沒有重跑。
- **L-4 已處理**
  - `_capture_raw_records` 的 docstring 與 `DATA_SOURCE_CASES` 上方的註解準確。
  - 註解限定在「使用該 helper 的測試」和 D-6。
  - D-1、D-3 的測試在 pytest 下 root 已有 caplog handler，`configure_logging()` 會提前 return，filter 沒裝。所以那組測試看到的是真正的原始 record，這個註解不會誤導它們。

## 各部門回報（qa-reviewer）

### 守門測試能否偵測失效
- **探針設計正確**
  - `python -I` 加上 `sys.path.insert(0, backend)`，匯入 `app.main` 與 `app.scheduler`。
  - 先取 `before`（`configure_logging()` 之前的 root handlers），再取 `after`。
  - 兩個測試都在乾淨直譯器中成立。這是我上輪缺的那一步，現在補上了。
- **失效偵測**
  - 任何在 import 階段加 root handler 的相依或程式碼（`basicConfig`、`addHandler`）都會讓 `before != []`。
  - 它同時涵蓋 transitive 相依，前提是 CI 的相依版本與正式環境一致。
  - `after` 的斷言也會抓到「configure 因為 root 已有 handler 而提前 return」。
  - dev-lead 的變異測試 (a)（在 `main.py` 尾端加 `logging.basicConfig()` 後兩測試皆紅）與我的靜態推演一致。
- **subprocess 環境足夠且乾淨**
  - 只傳 `PATH` 與 `STOCK_DESK_DB_PATH`、`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH`，指向 `tmp_path`。
  - 我對照 `app/` 內所有 `os.environ` 讀取點，這三個是全部 DB 路徑變數。
  - 其餘讀取點為 `DISCORD_WEBHOOK`／`TELEGRAM_*`、`FINMIND`／`ALPHA_VANTAGE` 的 key、scheduler 與 quota 的設定值。這些都不在 import 階段需要，且沒有被繼承。
  - 沒有祕密環境變數帶入，也沒有碰真實 DB。`-I` 另外忽略 `PYTHON*` 變數與 user site。
- **未設 `PYTHONPATH`、`HOME`**：目標是 Linux/Docker，且 venv 的 `sys.executable` 能找到自己的 site-packages，所以沒有問題。

### Non-blocking 意見（皆 low）
- **L-6（可維護性，low）`tests/test_r1_secret_redaction.py:377`**
  - `completed.stdout.splitlines()[-1]`：若 stdout 為空會丟 `IndexError`，而不是清楚的斷言訊息。
  - 兩個測試各起一次直譯器，匯入 `app.main` 有成本。
  - 建議在 `assert returncode` 後加 `assert completed.stdout.strip(), completed.stderr`，探針結果也可改用 module-scoped fixture 共用。不擋件。
- **L-7（殘餘風險，low，已被 dev-lead 揭露）**
  - 守門測試只涵蓋 import 階段。
  - 它管不到下列情況：
    - lifespan 或 `main()` 內、早於 `configure_logging()` 的 handler。
    - 部署層外部注入的設定，例如 `uvicorn --log-config` 指定的 root handler、容器 entrypoint 的包裝。
  - 提前 return 這一支在正式環境仍然是靜默的，沒有 WARNING。
  - 這已經由 `test_api_lifespan_configures_logging`、`test_scheduler_entry_installs_the_redacting_handler` 與 D-10 實機（假 token、`docker compose logs` grep 為 0）補強。
  - 請 devops-sre 在 D-10 繼續保留這一項。
- **L-8（極低）`_UNREDACTED_WEBHOOK` 只認 `/api/webhooks/`**
  - 若祕密出現在非 `/api/webhooks/` 的路徑，這個 regex 抓不到。
  - 該情況由 `app/logging_setup.py` 的 `/webhooks/` 遮蔽規則與祕密字串本身的檢查兜底。不擋件。
- 上輪其餘 non-blocking 意見狀態不變：M-2（provider 的 `"%s", exc` 另開單）、L-1、L-2、L-5（交 CEO／devops-sre）。

### 唯讀權限判準常數
未觸及。兩道機械檢查（在 `r1_delta.diff` 上以 Grep 代跑）皆無命中。
- 增量 diff 只有兩個檔：`apps/stock-desk/backend/app/logging_setup.py`（僅新增註解）與 `apps/stock-desk/backend/tests/test_r1_secret_redaction.py`。沒有 `scripts/validate_agents.py`。
- `READONLY_AGENTS`、`READONLY_ALLOWED_BASH`、`validate_agents` 在 diff 中出現 0 次，所以也沒有 shadow 定義或常數值被改動。
- 沒有 `.claude/agents/` 異動，不需要 ADR。

## 驗證
**本次實際執行的 Bash 指令只有一個：`codex --version`**（結果 `command not found`，Exit 127）。我沒有執行 `git log`、`ls`、`grep`、`which`，也沒有任何其他 Bash。其餘全用 Read／Grep：
- Read 了：commit 清單、增量 diff、dev-lead 小修報告、我上輪的審查報告、完整的 `logging_setup.py`、測試檔第 1–498 行。
- Grep 了：`app/` 內的 `basicConfig`／`dictConfig`／`fileConfig`／`addHandler`／`StreamHandler`，結果只有 `logging_setup.py` 自己；`os.environ`／`getenv` 讀取點；增量 diff 內的 `READONLY_*`／`validate_agents`（0 命中）與 `diff --git` 檔案清單（2 個檔）。

未做：
- Codex 第二意見。
- pytest、ruff、mypy 重跑。dev-lead 回報的 6605 passed、ruff、mypy 與三組變異測試，我未獨立重現。
- 測試檔第 498 行之後。
- 實機 D-10。

## 下一步
1. coordinator：R-1 分支可維持 PASS，進 risk-gate 與 done。無 UI，不需要 qa-e2e。Codex 缺席請 CEO 知悉。
2. devops-sre：D-10 實機時保留 L-7 的檢查（確認正式啟動方式沒有注入 root handler），並一併處理 L-1、L-2、L-5。
3. dev-lead：L-6 可順手做，不急。M-2 另開單。

BLOCKING_ISSUES: false
