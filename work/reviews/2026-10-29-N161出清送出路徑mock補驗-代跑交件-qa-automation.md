# N-161 出清送出路徑 mock 補驗代跑交件

- 審查者：qa-automation
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## N-161 e2e-fallback 代跑交件（代跑者：qa-automation，只交事實，不下 Verdict）

**輸出目錄**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n161_out/`
- 事實摘要在 `facts.md`；原始資料在 `facts.json`、`console.json`、`network-api.json`、`requestfailed.json`、`backend.log`、`next_build.log`。
- 截圖在同目錄的 `*.png`。
- 補跑資料（section 1 與 3，時序更緊）在 `supp-rerun-1-3/`。
- 腳本在同目錄：`e2e_n161_runner.js`、`e2e_n161_run.sh`、`e2e_n161_run_supp.sh`、`e2e_n161_start_be.sh`、`e2e_n161_start_fe.sh`。

### 環境
- **受測樹 commit**：worktree 取自 `origin/product/stock-desk` 現行 tip，是 `72babd6`，不是 833c6d7。`git diff 833c6d7 HEAD -- apps` 為空，apps 內容與 833c6d7 相同，72babd6 只多文件 commit。`git status` 全程為空，已用 `worktree remove --force` 移除。
- **前端**：production（`next build` exit=0，加 `next start`）。`node_modules` 以 `cp -a` 從主 repo 複製，沒有任何安裝。
- **後端與資料**：uvicorn 加合成示範資料（`app.demo.seed`，source=demo_synthetic）。DB 在 scratchpad，沒碰 `backend/data/*.db`，沒讀 `.env`。排程台用 `confirm-rules` 進入 confirmed。
- **儀器**：playwright 1.63.0 在 `/opt/node-tools/`，chromium 153.0.8010.12 在 `/opt/pw-browsers/`，兩者皆在 `/opt/` 前綴內，runner 斷言通過。
- **清理**：前後端只殺自己的 process group，已確認無殘留。

### 真實 emergency-exit 從未送達後端
1. 攔截在 context 層，只用 `route.fulfill`，從未 `continue` 或 `fallback`。
2. 每個情境結束與全程結束時，runner 比對「request 事件數 = route 命中數」且後端 log 的 emergency-exit 行數 = 0。7 筆 safetyChecks 全部一致（POST 6 筆，命中 6，後端 0），不一致會 exit 2。
3. `grep -c emergency backend.log` = 0。後端 access log 只有 15 次 `GET /today`、1 次 `GET /health`、1 次 `POST /confirm-rules`。補跑那次也是 0。
4. 全程結束後直接 `GET /api/playbook/today` 回 `mode=normal`，後端狀態未被改動。
5. 瀏覽器端 network 看到 6 筆 emergency-exit POST：回 200 兩筆，回 500 四筆，皆為 mock。

### Mock 說明
- **`POST /emergency-exit` 的 200**：形狀依 `EmergencyExitResponse` 造，含一筆 EMERGENCY 賣出 directive（2330、3000 股，合成值）。message 等字串依 `wording.py` 模板手動代入，非後端真實輸出。
- **`GET /today`**：以後端真實回應為底，只在 mock 的 exit 回 200 之後改 `mode`、`mode_label`、`mode_reason` 三欄為 emergency_frozen。`directives`、`snapshot` 等欄位未模擬凍結後的實際內容，所以不是完整的凍結後形狀。
- **500 失敗**：兩種 body，`{"detail":"Internal Server Error"}`（FastAPI HTTPException 形狀）與純文字 `Internal Server Error`。
- **preflight**：Playwright 未把 OPTIONS 暴露給 route handler（0 筆），POST 仍被 mock 成功回應。

### 事實摘要（1280x900 與 375x812 結果相同，除非另註）

**1. 送出成功（mock 200，延遲 1.5s）**
- **送出中（約 350ms）**：「取消」disabled，按鈕文字變「送出中…」且 disabled。
- **activeElement**：`<body>`，不在對話框內。
- **按 Esc**：對話框仍在，狀態不變。
- **對 disabled「取消」click**：無效果。
- **送出中按 Tab**（補跑，844-897ms，對話框仍在）：activeElement 變成頁首 `<a>`「stock-desk」，已離開對話框。主跑的 Tab 因時序與完成撞在一起，以補跑為準。
- **完成**：約 1.5-1.7s 後對話框關閉，activeElement 回到「全部出清」觸發鈕，鈕仍在畫面內且 hit-test 命中它。
  - 1280x900：L1054 T77。
  - 375x812：L277 T201。
- **狀態列徽章**：變「緊急出清後凍結」。
- **sticky**：捲到底後觸發鈕仍在畫面內。
- **完成後橫幅**：逐字全文在 `facts.md`。橫幅第二段的 mode_reason 與狀態列下方的 mode_reason 是同一句，畫面上出現兩次。
- **完成後再按 Tab**（主跑）：activeElement 變 `<body>`。

**2. 送出失敗（mock 500）**
- **ErrorPanel**（`role=alert`）：
  - `err-json` 全文：`全部出清送出失敗：Internal Server Error`。
  - `err-text` 全文：`全部出清送出失敗：請求失敗（HTTP 500）`。
  - 位置：對話框面板內，DOM 上在事實清單 `<ul>` 與按鈕列之間，在 viewport 內，面板無內部捲動。
  - 座標：1280x900 為 L405 T530（470x46）；375x812 為 L37 T506（301x46）。
- **錯誤後**：對話框維持開啟，「取消」與「確認送出全部出清」皆 enabled，activeElement 是「確認送出全部出清」。handler 只看到 1 筆 POST，無自動重試。
- **Tab 與 Shift+Tab 各連按 8 次**：全程在「取消」與「確認送出全部出清」之間交替，inDialog 全為 true，沒有跑到對話框外。從 `focus()` 到「取消」起算的 Tab×4 與 Shift+Tab×4 結果相同。
- **Esc**：對話框關閉，activeElement = 「全部出清」觸發鈕，鈕在畫面內。
- **console**：4 筆 error（每個失敗情境 1 筆），原文 `Failed to load resource: the server responded with a status of 500 (Internal Server Error)`，url 為 `http://localhost:8000/api/playbook/emergency-exit`。無 pageerror，`requestfailed` 為空。

**3. 捲動連動（375x300，Step 2，不送出）**
- **起點**：背景 scrollY 先設 100，面板可捲距 148（scrollHeight 414，clientHeight 266）。
- **計算樣式**：html、body 的 overflow 為 visible，overscroll-behavior 為 auto；面板 overflow-y 為 auto，overscroll-behavior 為 auto。
- **滑鼠在面板中央，每次滾輪 +150**：面板第 1 次滾到底（scrollTop=148），第 2 次起背景 scrollY 跟著變，100 → 250 → … → 1600 → 1631（頁面最大可捲距）。
- **背景到底後再滾**：scrollY 維持 1631。
- **滑鼠在 overlay 邊緣（x=4，面板外 16px padding 區，補跑）**：背景先設 scrollY=300，滾 +300×4 後 scrollY 為 600 → 900 → 1200 → 1500，面板 scrollTop 不變。
- **往上滾 -200**：面板先回 0，之後背景 scrollY 1431 → … → 0。
- 全程對話框仍開啟。

### 無法完成的項目與原始錯誤
- 沒有無法完成的項目。
- 主跑中對 disabled「取消」做一般 click，Playwright 因 actionability 逾時：`locator.click: Timeout 700ms exceeded.`。補跑改 `force:true`，click 無效果。
- activeElement 為 body 是在 headless Chromium 153 觀測到的，其他瀏覽器未驗證。
- 截圖只留在 scratchpad，未搬動。
