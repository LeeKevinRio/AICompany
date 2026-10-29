# N-159 出清對話框實機複驗代跑交件

- 審查者：qa-automation
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# e2e-fallback 代跑交件：N-159 全部出清對話框（代跑者：qa-automation；只交事實，不下 Verdict）

**輸出目錄**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n159_out/`（44 個檔案、4.4MB）
**facts.md**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n159_out/facts.md`（330 行，分 0～10 節，每個量測值都有三種尺寸的原始數字）
**其他檔案**：`results.json`、`console-all.json`、`network-non2xx.json`、`runner-stdout.txt`、`backend.log`、`frontend.log`、`confirm_rules_response.txt`、各 png 與 innerText。補充批次在子目錄 `supp-3c/`、`supp-short/`。
**腳本**（scratchpad 根目錄）：`e2e_n159_runner.js`、`e2e_n159_run.sh`、`e2e_n159_start_be.sh`、`e2e_n159_start_fe.sh`、`e2e_n159_mkfacts.py`、`e2e_n159_probe.js`。

## 環境與紀律
- 受測樹 `e2e_n159`，HEAD `12216d4`。`git status --short` 全程為空，只有被 ignore 的 `__pycache__`、`.next`、`node_modules`；`package.json` 與 lockfile 與主 checkout 以 `cmp` 比對相同。
- **Provenance**：
  - playwright 為 `/opt/node-tools/node_modules/playwright/index.js`，1.63.0。
  - Chromium 為 `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`，153.0.8010.12。
  - trustedPrefix 為 `/opt/`，runner 的 fail-closed 斷言通過。
  - 後端 `app.__file__` 已確認指向受測樹。
- 沒有安裝任何東西；`node_modules` 是從主 checkout `cp -a` 複製。
- 資料是 `python -m app.demo.seed` 的**合成示範資料**，放在 `scratchpad/e2e_n159_db/`。排程台已用 `POST /api/playbook/confirm-rules` 進入 confirmed（capital=1000000，合成數字）。
- 前端是 `next dev --webpack`（dev 模式，畫面左下有 Next dev 指示圓鈕，非產品元素）。
- 沒讀 `.env`；主 checkout 的 `backend/data/` 底下沒有任何 `*.db`，我也沒碰。
- 「確認送出全部出清」**從未點擊**，聚焦後也沒按過 Enter 或 Space。我另外對 `**/emergency-exit` 掛了 route abort 防護，作為安全網；該請求事件為 0 筆，防護命中也是 0 筆。
- 我啟動的 next 與 uvicorn process group（7619、7620）已用 `kill -- -PGID` 殺掉，確認沒有殘留。

## facts.md 摘要（以下僅為數值，都是事實，沒有判斷）
對話框文字與核取方塊在三種尺寸下逐字相同（md5 一致），4 條事實，逐字在 facts.md 開頭。

**1. 頁面在頂端開啟（1280×900 ／ 375×812 ／ 1280×500）**
- 遮罩 `[role=dialog]` 是 `position:fixed`、z-index 50，父節點是 `<body>`。
  - rect 分別為 L0 T0 R1280 B900、L0 T0 R375 B812、L0 T0 R1280 B500。
  - left=0、top=0、right=innerWidth、bottom=innerHeight 四項在三種尺寸都是 true。
  - 四個角落的 `elementFromPoint` 命中的都是遮罩本身。
- 內層面板：
  - 1280×900：L384 T272 R896 B628。
  - 375×812：L16 T198 R359 B614。
  - 1280×500：L384 T72 R896 B428。
- Step 2 標題 rect：T293–B321、T219–B247、T93–B121。第一條事實 rect：T337–B397、T263–B343、T137–B197。標題與第一條事實都完整落在視窗內與面板內。
- 截圖為 `<viewport>-1-top-step2.png`。

**2. 捲到底部後開啟**
- 開啟前 scrollY 分別為 401、1119、801（都是該頁最大可捲）。
- 遮罩與面板 rect 與第 1 項完全相同，標題與第一條事實都在視窗內。
- 逐一勾選：
  - 每次勾選後 `checked` 依序變成 `[T,F,F,F]`、`[T,T,F,F]`、`[T,T,T,F]`、`[T,T,T,T]`。
  - 「我已閱讀，繼續」的 disabled 前三次維持 true，第 4 次勾完變 false。
  - 沒有 click 錯誤。

**3. 焦點**
- 開啟後 activeElement 是 `<h2>`，文字「全部出清 — 確認前請閱讀以下事實」，tabIndex=-1。
- 此時按 Space，核取方塊維持 `[F,F,F,F]`，焦點仍在 h2。
- 第一次按 Tab 落在 `exit-check-0`。
- Step 2 在 continue 為 disabled 時有 5 個可聚焦元素。Tab 與 Shift+Tab 各連按 9 次，每一步 `inDialog=true`：
  - Tab 順序：check-0 → 1 → 2 → 3 → 取消 → 回到 check-0。
  - Shift+Tab 順序：取消 → check-3 → 2 → 1 → 0 → 取消。
- 全部勾選後有 6 個可聚焦元素（多了「我已閱讀，繼續」）。Tab 與 Shift+Tab 各連按 10 次，全部 `inDialog=true`，順序循環。
- 按「我已閱讀，繼續」後 activeElement 是 `<h2>`「全部出清 — 二次確認」。滑鼠點擊與鍵盤 Enter 兩種都是這個結果。
- Step 3 有 2 個可聚焦元素，取消與確認送出互相循環。Tab 與 Shift+Tab 各 6 步全部 `inDialog=true`。

**4. Esc**
- Step 2 先勾兩個核取方塊再按 Esc：
  - dialog 數量 0，`POST /emergency-exit` 0 筆。
  - activeElement 是「全部出清」按鈕。
  - 重開後核取方塊為 `[F,F,F,F]`，continue 為 disabled。
- Step 3 按 Esc：結果同上，重開後回到 Step 2，核取方塊全為 false。
- 三種尺寸結果相同。

**5. 取消**
- Step 2 與 Step 3 按取消後，dialog 數量 0，activeElement 都是「全部出清」按鈕。
- Step 3 取消後重開，核取方塊全為 false。

**6. 矮視窗 1280×500**
- 面板在視窗內，max-height 468px，overflow-y auto。
- **面板 scrollHeight=354、clientHeight=354，`scrollHeight > clientHeight` 為 false**，所以沒有可捲動量；設 `scrollTop=scrollHeight` 後仍為 0。
- 4 個核取方塊都能勾到，每個都在視窗內，`elementFromPoint` 命中該核取方塊。
- 勾完後「我已閱讀，繼續」啟用，且在視窗內。
- 面板在 1280×500 沒有溢出，所以我**補充**了更矮視窗（派工單未要求，見 6c）：
  - 1280×300：面板 scrollHeight 354、clientHeight 266，可捲到底（scrollTop 88）。
  - 375×400：scrollHeight 414、clientHeight 366，可捲到底（scrollTop 48）。
  - 375×300：scrollHeight 414、clientHeight 266，可捲到底（scrollTop 148）。
  - 三者的標題與第一條事實都在視窗內，4 個核取方塊都能勾到，勾完後「我已閱讀，繼續」啟用且在視窗內，遮罩都覆蓋整個視窗。
- **另一個現象**：滑鼠滾輪在面板上滾動時，面板不可捲（1280×900、375×812、1280×500）的情況下，背景頁面 `scrollY` 從 0 變成 401、1119、801，也就是對話框開啟時背景頁面仍被捲動。在可捲的短視窗，滾輪是捲面板，頁面 scrollY 維持 0。

**7. 焦點外框（標題被聚焦時）**
- 滑鼠點開：`:focus-visible`=false，computed `outline` 為 `oklch(0.97 0 none) none 3px`（outline-style none），box-shadow none。
- 鍵盤開啟（從頁首 Tab 9 次到「全部出清」再按 Enter）：`:focus-visible`=true，computed `outline` 為 `rgb(16, 16, 16) auto 1px`，box-shadow none。
- 三種尺寸數值相同。
- 我看了 1280×900 面板截圖：鍵盤開啟時標題外圍可見一圈淺色圓角矩形框，滑鼠開啟時沒有框。
- 截圖為 `<viewport>-7-outline-{mouse,keyboard}[-panel].png`。

**8. Console 與 network**
- error、warning、pageerror 共 0 筆，非 2xx 0 筆，requestfailed 0 筆，非 GET 請求 0 筆。
- console 只有每個頁面各一對 info 與 log，原文是 `%cDownload the React DevTools for a better development experience: https://react.dev/link/react-devtools font-…` 與 `[HMR] connected`。
- 後端 log 的 WARNING／ERROR 共 3 行，都是離線造成的，原文：
  - `WARNING app.data.http: transport error on attempt 1/2 for /v8/finance/chart/%5ETWII: 403 Forbidden`
  - `WARNING app.data.providers.yfinance: yfinance request failed for ^TWII: 403 Forbidden`
  - `ERROR app.data.service: no provider and no cache entry available for ^TWII`

## 無法完成或有限制的項目
1. **未驗：送出成功路徑與送出失敗路徑。** 送出不可逆，無法安全模擬，我從未點擊「確認送出全部出清」。Step 3 內的「送出中…」與 ErrorPanel「全部出清送出失敗」都沒看到。
2. 前端是 dev 模式，不是 production build。
3. 只用滑鼠 click 與鍵盤 Enter 開啟；觸控、真實裝置、其他瀏覽器都沒做。
4. 此資料集的 Step 2 恆為 4 條事實；3 條的降級分支沒觸發，未驗。
5. 焦點循環一律從標題起算；沒測從對話框外的元素起算，因為開啟後焦點必在標題。
6. 第一次跑 runner 時，第 7 節的 `ring` 函式寫死使用已關閉的 `page`，出現 `Target page, context or browser has been closed`（腳本 bug，不是受測應用的問題）。我修正後重跑全部，`e2e_n159_out/` 內的檔案都是修正後那次的產物。原始錯誤如下：
   `ERR 1280x900 7-outline page.evaluate: Target page, context or browser has been closed at ring (…/e2e_n159_runner.js:348:31)`
7. 我原本想用 `rm -f $O/*.png ...` 清舊輸出，被權限檢查擋下，沒有執行。舊檔案已被新一輪產出覆蓋，不影響結果；這個檢查擋下的刪除我沒有繞過。
8. 沒跑 pytest 或 vitest。除 `confirm-rules` 的 POST 以外沒有其他寫入型 API 操作。
