# R2 預備合併程式碼審查

- 審查者：qa-reviewer
- 日期：2026-11-14
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
程式碼審查結論：PASS，BLOCKING_ISSUES=false。單家審查，因為 `codex --version` 回報 command not found，Codex 第二意見缺席。

## 各部門回報
**1. 合併有沒有夾帶額外改動：沒有。**
- N-177a（5962b7d3）到 M1 的 `apps/stock-desk/backend/app` diff 為空。第一次合併沒有帶入任何 app 程式碼。M1 比 N-177a 多出的只有 scripts、tests、docs、`r2-probe.bat` 與 work。
- M1 到 M2 的整個 repo diff 只有 3 個檔：`app/playbook/service.py`、`app/playbook/store.py`、`tests/test_playbook_rebalance_no_cash.py`。這就是 N-195 的範圍。
- `store.py` 的自動合併乾淨，是純新增。
  - 新增 `_total_deploy_state` 與 `set_total_deploy`。
  - `set_capital` 改成共用 `_total_deploy_state`，寫入的三個 TOTAL_DEPLOY key 與格式不變。
  - `service.py` 的 REBALANCE 只改成呼叫 `set_total_deploy`，不再寫回舊的 cash。
  - 沒有 N-177a 與 N-195 原分支以外的改動。

**2. seam 指什麼：另有所指，而且已被跑到。**
- 交件文件 `2026-11-07-N177a交件-dev-lead.md` 第 220 行寫「完整 CI 與 seam golden」，另寫「重跑 T28」。所以 seam golden 與 T28 是兩件事。
- seam 指 `tests/test_playbook_today_seam.py`（SEAM-T1 到 T8）與 `tests/golden/seam/approved/*.json`。
- devops-sre 在 M2 上跑了完整 `pytest --cov=app --cov-fail-under=90`：10241 passed、2 xfailed、覆蓋率 97.65%，exit 0。這包含上述 seam 測試與 golden。
- T28 兩個測試與 S11 十個測試也在 M2 上通過。
- 因此沒有未跑到的合併前必做項目。devops-sre 疑惑的「T28 是不是 seam」，答案是否，但完整 CI 已涵蓋 seam。
- 小缺口：完整 CI 的輸出沒有逐檔列出 seam 測試，我是依「全套通過」推定它們有跑。

**3. RC-114 條件：符合。**
- 兩個分支的改動都在 `app/playbook/`（排程台）及其測試，沒有觸及排程台以外的 app 路徑。
- M1 到 M2 沒有 frontend 檔案與使用者面向字面的改動。
- 依 CEO #143、#144 與 RC-113，R2 合入不需再停機重跑探測。

## 驗證
我只做靜態檢查，沒有執行測試。檢查內容是三個 `git diff`（兩段 app diff 加 `--stat`）、讀 devops-sre 實跑紀錄，以及 grep seam 在交件文件與測試目錄中的指涉。

## 下一步
- 正式合入前，要對齊最新 product tip（devops-sre 記為 c209104）再 merge 一次，並重跑 CI。新增的只是 docs，預期不會衝突。
- 這個 merge commit 若只多了 docs，qa 不必再審；若有 app 或 tests 異動，需再送 qa。
- 後續回報給 CEO 即可。這批沒有 UI 改動，不需 qa-e2e。

相關路徑：
- /home/user/AICompany/work/reviews/2026-11-14-R2預備合併-devops-sre.md
- /home/user/AICompany/work/reviews/2026-11-07-N177a交件-dev-lead.md
- /home/user/AICompany/apps/stock-desk/backend/tests/test_playbook_today_seam.py

## 唯讀權限判準常數
未觸及。本審查未跑 `scripts/validate_agents.py` 與 `READONLY_*` 的兩道檢查，只因 Bash 被限定為單一 `git diff`。M1 到 M2 的 3 個異動檔不含 `scripts/validate_agents.py`，內容也不涉及 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`。
