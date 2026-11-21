# P2 五份一次性指令文件標註套用交件（docs/p2-oneoff-ceo-notice）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
五份一次性指令文件已逐字套用風控定稿，分成五個獨立 commit，已 push 到 `docs/p2-oneoff-ceo-notice`。沒有開 PR，沒有合併。驗證 1～9 點全數通過，未發現歧義。

- base：`origin/product/stock-desk` = `f662aff9b8c71620305ea4a0238469084423c8a8`（分支建立前才 fetch）。
- head：`8bc03809882fa5e4925ad7bf718c7a71a1534b33`
- worktree：`/home/user/AICompany/.claude/worktrees/agent-a942b73e8a642c93d`，停在 head。
- 五個 commit，由舊到新：
  1. `72857773d622085f4431f5d3c948767cd6861e49` docs: N-152 檢測指令加註給 CEO 的一次性標註與警示
  2. `20d2983d98b6b4d08e5a10768146732aee8ef278` docs: N-172 偵測指令加註給 CEO 的一次性標註與警示
  3. `952741bb345d20d9b43fdda33aefda84c46c7931` docs: 財務資料源 spike 執行指令加註給 CEO 的一次性標註與警示
  4. `cee3b0b3abe89dcfbaf352569ccdbdee46d50cf3` docs: Phase 1 資料源探測指令加註給 CEO 的一次性標註與警示
  5. `8bc03809882fa5e4925ad7bf718c7a71a1534b33` docs: 數據核實操作說明加註給 CEO 的一次性標註與警示
- 每個 commit 都帶指定的兩行 trailer。沒有 amend、rebase、force。repo 內容沒有寫 model ID。

## 各部門回報（devops-sre）
- 五份都已用 `git ls-files --error-unmatch` 確認在 base 上被追蹤，沒有搬檔。
- 套用方式：腳本放在 scratchpad，沒有 commit。
  - 腳本從風控檔擷取四反引號區塊。
  - 先 assert 再寫入：第 1 行原文等於檔案第 1 行；每個插入點標題在 code fence 之外恰好出現一次；標題原行號與風控註明相符；標題下一行是空行；風控註明的「之前」那一行確實緊接在空行之後。
  - 插入點由後往前處理，最後換第 1 行、插檔頭。
- 只動了五個檔，沒有碰 `apps/`、`.env*`、`backend/data/`，也沒有執行任何 `.bat` 或文件中的指令。
- 腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/apply.py`（套用）、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/verify.py`（驗證）。

## 驗證（實際輸出摘要）
1. 行數（`wc -l`，base → 新）：
   - N-152：161 → 169（+8）
   - N-172：247 → 253（+6）
   - spike：309 → 315（+6）
   - Phase 1：3041 → 3053（+12）
   - 數據核實：79 → 83（+4）
   - 全部與 RC-526 表一致。`git diff --stat` 為 5 files、41 insertions、5 deletions，即每檔 1 行替換。
2. 逐字 `==`：
   - 第 1 行：五份都與定稿「新」一致。每檔只移除原本那一行，已逐檔列出原文。
   - 檔頭：N152-H（4 行）、N172-H、SPK-H、VRF-H（各 2 行）、PH1-H（4 行）都一致。
   - 就地警示：N152-1、N152-2、N172-1、N172-2、SPK-1、SPK-2、PH1-1、PH1-2、PH1-3、PH1-4、VRF-1 共 11 處都一致。
   - 比對用腳本 `==`，另以 `difflib` 確認每檔新增行以外沒有其他變動。
3. 插入形式：
   - 11 處都是「標題、空行、警示、空行、原內容」，原內容的前綴與風控註明相符。
   - 檔頭在第 1 行標題、第 2 行空行之後，區塊最後一行是空行。
4. `> **給 CEO：` 開頭的行：N-152 3、N-172 3、spike 3、Phase 1 5、數據核實 2。`> 也不要在 Windows 環境變數` 開頭的行：N-152 與 Phase 1 各 1，其餘 0。
5. `給 CEO 本機執行`、`CEO 本機代跑）`、`CEO 本機一鍵操作說明` 在五份都是 0 命中。新增行不含「已結束」「已執行」「不要再照」。
6. 標題唯一性：11 個插入點標題，在各檔 code fence 之外都恰好出現一次（Phase 1 的 4 個也包含在內）。
7. 五份 base 與新檔都沒有 CR、都是 UTF-8、檔尾換行狀態與 base 一致；新增行無行尾空白。
8. `git diff f662aff HEAD --stat` 只有這五份，沒有夾帶 RC-529 的 6 份或其他檔。
9. base 是 `product/stock-desk`，分支追蹤時由它建立。

## 你做了判斷的地方
- 風控檔本身的檔頭區塊（`N152-H` 等）最後一行是空字串，我照字面當作區塊的最後一行空行插入，與「4 行或 2 行」的描述一致。
- 風控註明「之前」是 code fence 的那幾處（N152-2、N172-2、SPK-1、SPK-2），我以「下一行以 ``` 開頭」做 assert，沒有再限定反引號數量。
- 沒有其他需要自行決定的歧義。

## 沒有查證的事
- 沒有跑 qa-reviewer 或 Codex 第二意見；這是下一關。
- 沒有開 PR，沒有看 CI。
- 沒有驗證 RC-529 那 6 份是否被追蹤（不在本任務範圍）。
- RC-530 的 PSReadLine 與 bash 歷史檔推論（suggested，轉 devops-sre）本次沒有查證。查證之前不得對 CEO 提這件事。

## 下一步
1. 交 qa-reviewer 依 RC-526 的 1～9 點審查，含 Codex `/review`。可用 `git diff f662aff9b8c71620305ea4a0238469084423c8a8 8bc03809882fa5e4925ad7bf718c7a71a1534b33`。
2. qa 通過後回報風控做單項確認。需附 head SHA 與工作樹路徑（上方已列），以及「五份在 `product/stock-desk` 上被追蹤」這項確認（本次已確認）。
3. 開 PR 與合併由 coordinator 決定，須遵守 RC-527 的限制：不得在預檢到登記完成之間 push 或合併（#156）。注意這次我已經 push 了分支，但還沒開 PR 或合併。
4. 風控另有建議（RC-530，suggested）：查證 PSReadLine 預設行為與敏感字過濾規則。我可以另接這項。
