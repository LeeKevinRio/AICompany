# e2e 代跑交件

- 審查者：qa-automation
- 日期：2026-10-26（container 重啟後於 2026-10-28 轉存）
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# e2e-fallback 代跑交件（代跑者：qa-automation；只交事實，不下 Verdict）

**輸出目錄**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_c9401c2_out/`（112 個檔案：png、innerText.txt、results-*.json、console-all-*.json、network-non2xx-*.json、後端與前端 log）
**facts.md**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_c9401c2_out/facts.md`
**腳本**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_c9401c2_runner.js`、`e2e_c9401c2_start_be.sh`

## 先講需要你判斷的幾件事

1. **`make_demo.py` 不是 `demo_synthetic` 產生器。** 它只寫 2 根 `AAPL`／`yfinance` 日線，畫面不會有 2330。我改用 repo 內建種子器 `python -m app.demo.seed`，產出 `source=demo_synthetic`，共 1560 根日線和 3 筆持倉（2330、0050、00631L）。
2. **新 worktree 沒有 `.venv` 與 `node_modules`，安裝一律禁止。**
   - 後端：用主 checkout 既有的 `.venv/bin/python` 加 `PYTHONPATH` 指向 worktree，`app.__file__` 已確認載入受測 commit 的程式碼。
   - 前端：symlink `node_modules` 被 Turbopack 拒絕（`Symlink [project]/node_modules is invalid, it points out of the filesystem root`），改成 `cp -a` 複製主 checkout 既有的 `node_modules`。
   - 兩邊的 `package.json`、`package-lock.json`、`uv.lock` 都與受測 commit 比對相同。
   - 沒有任何安裝動作，worktree 的 `git status` 為空。
3. **主 checkout 目前 HEAD 是 `52c31a2`，不是 `c9401c2`。** 我沒用主 checkout 的程式碼，只借它的依賴。
4. **回測頁第一次嘗試作廢。** 我的 runner 點到導覽列的「查詢」鈕，畫面出現「請輸入股票代號」。那批檔案已移到 `superseded_failed_backtest_attempt/`，不作為證據。有效資料在 `3-backtest-{default,slip0,slip5}-*` 和 `results-bt.json`。
5. **收尾**：已 kill 我啟動的 uvicorn 與 next，並 `git worktree remove --force` 移除 `e2e_c9401c2`。其他 `.claude/worktrees/*` 未動。

## 重點事實（細節與逐字文字都在 facts.md）

**Provenance**
- playwright：`/opt/node-tools/node_modules/playwright/index.js`，1.63.0。
- Chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`，153.0.8010.12。
- 受測 commit：`c9401c2f7d2338d9ab52b839baea78fefdd4f2b9`。
- runner 的 `trustedPrefix` 為 `/opt/`，fail-closed 斷言通過。
- 資料為合成示範資料，環境離線，畫面顯示「快取資料」。

**1. 首頁**
- 在 `main` 內搜尋「未經歷史驗證」、3-S 句子、「過渡」，三個寬度、demo DB 與空 DB 都是 **0 筆**。
- 首頁只有頁尾 3-F 一處免責：1440 top 1427、3 行；375 與 390 top 2213、5 行。它在首屏之外。
- 因此「兩條提示帶」在本版首頁不存在，我無法量它們的位置與換行。
- 空 DB：顯示「尚無持倉」2 處和「—」；風險儀表五列為「—／15.00%」等。
- 頁高：demo DB 1440＝1499、375＝2325、390＝2325；空 DB 1440＝1348、375＝1866、390＝1866。
- 三個寬度都沒有橫向溢位。

**2. 個股頁 2330**
- 2330 是 hold，第 1 條與第 4 條上限違反，加碼被擋，與預期相符。
- 股數參考格的值 `<p>`：`font-size 20px`、`line-height 28px`，高 56，都是 **2 行**。

| viewport | 格寬×高 | 換行位置 |
| --- | --- | --- |
| 1440 | 208.875×110 | `加碼參考被風險上限擋` / `下`（「下」孤立一行） |
| 375 | 146.5×98 | `加碼參考被風險` / `上限擋下` |
| 390 | 154×98 | `加碼參考被風險` / `上限擋下` |

- 只展開 4-Q／4-E 時，1440 的格寬變 250.562，值變單行。

- 紅框「已違反 2 條上限：」的 top 距成因字 bottom：1440＝42，375 與 390＝30。
- 被擋加碼句 #1 距成因字 bottom：1440＝144，375 與 390＝172。
- 被擋加碼句 #2 距成因字 bottom：1440＝172，375＝220，390＝200。
- 4-Q 在收合時在 1440、375、390 都是 2 行，展開成 1 行寬 238.031。
- 1-L 與動作大字同一排：1440 top 282，375 與 390 top 302。
- 4-附（全形括號句）在 2330 **不渲染**。補探測 00631L 有，位置在「操作摘要」面板，不在決策卡內；0050 沒有。
- 停利：決策卡三格已沒有停利格。但決策卡內仍有一句可見的「停損參考與停利參考以最新收盤 918.66（2026-10-26）為基準計算…」。決策卡之外，「關鍵價位參考」階梯在收合時仍可見「+20% 固定停利」和「停利參考（固定算式，非分析結果）」。
- 頁高（收合／全展開／只展開 4-Q 與 4-E）：1440＝2498／8929／2704；375＝3660／13753／3830；390＝3620／13471／3790。

**3. 回測頁**
- 5-BT 方塊在送出回測後才出現。預設滑價 0 bps 的文字：「先看以下假設：前兩項可能讓結果偏樂觀」，下接兩條假設。
- 位置：1440 top 857、高 86；375 top 1441、高 146；390 top 1413、高 126。
- 另跑 slip0 與 slip5 兩個變體，文案依滑價切換，逐字見 facts.md。
- 起訖日 2025-05-05～2026-10-26 是我選的，因為表單預設為空且 `required`。

**4. Console 與 network**
- 主批次、回測、extra 批次：console error／warning 為 0，非 2xx 為 0。
- 唯一的 `requestfailed` 是首頁離開時被中止的 Next.js prefetch（`net::ERR_ABORTED`，共 12 筆，原文在 facts.md 4.1）。
- **空 DB 第一次載入有 2 筆 console error，是已重現的事實：**
  - 瀏覽器原文：`Access to fetch at 'http://localhost:8000/api/alerts/events?unacknowledged=true' from origin 'http://localhost:3000' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.` 和 `Failed to load resource: net::ERR_FAILED`。
  - 後端同一請求回 500：`sqlite3.OperationalError: duplicate column name: bar_as_of`，出自 `app/alerts/store.py` 的 `_migrate_add_bar_as_of_column`。
  - 現象是全新 DB、多個請求同時建立 `AlertStore`，ALTER 互撞。後續請求都是 200，demo DB 沒有發生。
  - 是否為缺陷由你和實作者判斷。

**5. 競態回歸**
- 同一頁連載 5 次（要求是 2 次），每次輪詢 20 次，約 5 秒。
- 最終都是「6 條中成立 5 條」，過程中只有空白和這一個值，**沒有出現 3 條**。
- 這句位於「六項觀察條件」區塊，不在決策卡內。

## 無法完成或有限制的項目
- 「兩條提示帶」在首頁不存在，無法量測。
- 4-附在 2330 不渲染，改以 00631L 補探。
- `lines` 輔助函式遇到同一元素內混字級（如 `▸` 12px 加文字）會誤報行數。這類項目我已以元素 `height` 為準，facts.md 已註明。單一字級文字（股數值、被擋加碼句、免責句）的行數可信。
- 我沒有跑 pytest，也沒有測試寫入型 API。

## facts.md 全文
上面的重點事實是節錄。facts.md 全文共 376 行，含逐字文字、所有量測表、console 與 network 原文、後端 traceback，請直接讀 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_c9401c2_out/facts.md`。章節如下。
- 第 0 節：provenance 與環境，0.1 為與派工單不一致的處理。
- 第 1 節：首頁，含空持倉。
- 第 2 節：個股頁，含決策卡逐字、股數格、紅框距離表、4-Q／4-E／1-L／4-附、停利位置、頁高。
- 第 3 節：回測 5-BT。
- 第 4 節：console 與 network。
- 第 5 節：競態回歸。
- 第 6 節：無法完成或需說明的項目。
