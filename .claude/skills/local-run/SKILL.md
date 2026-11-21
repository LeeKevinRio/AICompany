---
name: local-run
description: CEO 要在本機啟動、重啟、跑起來或開起來測試產品時的轉介規則。觸發後先做兩件事：查產品分支 README 中給 CEO 的操作段，以及該產品有沒有常設限制（例如進行中的紀錄、不得自行重啟的規則），再依那些已定稿的字面回覆；本 skill 不提供任何指令，coordinator 不得臨場輸出。
---

# local-run — 本機啟動／重啟的轉介規則

> 本 skill 只屬 `product/stock-desk`，不 merge 回 main。
> 它只規定 coordinator 要去哪裡找、哪些事不能做；啟動與重啟的細節不寫在這裡。

## 適用時機

CEO 說「啟動」「重啟」「跑起來」「開起來測試」，或任何等同意思的話時。

## 轉介步驟

1. coordinator 不臨場輸出任何指令或操作步驟，也不憑記憶或舊會話內容回答。
2. 先到產品分支 README，找「給 CEO 的操作」那一段。只轉述該段（或追蹤清單）中已由 risk-compliance-officer 定稿的字面，不改寫、不補充、不摘要成自己的話。
3. 查有沒有常設限制，例如「不得自行重新啟動」的規則，或進行中的紀錄。有的話：
   - 要請 CEO 重新執行任何東西，一律走定稿請求 R1、R2、R3、R3-0、R3-0C、RC-447（只列代號，字面與送出條件以追蹤清單為準），照送出條件辦；
   - 不在送出條件內的時段或狀態，不回答啟動或重啟的方式；
   - 屬於重新啟動的要求，coordinator 照實記錄並轉 devops-sre，不輸出指令。
4. README 的 CEO 操作段尚未落地時，轉介目標暫為 `work/dispatch/2026-10-17-後續追蹤清單.md`，coordinator 依其中的常設規則辦；操作段落地後改指向該段。
5. 以 `work/dispatch/2026-10-17-後續追蹤清單.md` 為準；本檔和清單不一致時，以清單為準。
6. 找不到合適的定稿字面時，不自行拼湊，先送 risk-compliance-officer 定稿，並請 devops-sre 協助確認產品現況。

## 禁止事項（coordinator 對 CEO 一律不得）

逐條可檢查，任何一條成立即違規：

1. 輸出手動啟動指令，例如 `uv run`、`npm run`、`bash …sh`。
2. 輸出任何 `git` 指令。
3. 輸出 `taskkill`、`kill`、`lsof`、`pgrep`、`Stop-Process`。
4. 輸出備份或還原步驟。
5. 檢查或修改 `.env` 或環境變數，或請 CEO 去查、去改。
6. 請 CEO 判讀視窗或終端機訊息。

## 維護

- 啟動、重啟、備份、資料位置等工程內容，寫在產品的工程文件，不寫進本 skill。
- 本 skill 不寫任何給 CEO 看的字面；對 CEO 的字面只能來自已定稿的產品文件。
- 修改本 skill 須經 qa-reviewer 審查，並確認沒有帶入給 CEO 的句子。
