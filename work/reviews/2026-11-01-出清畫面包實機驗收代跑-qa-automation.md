# 出清回饋畫面修正包實機驗收代跑（受測樹 47f8ad9，只交事實）

- 審查者：qa-automation
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# 出清後回饋畫面修正包 實機驗收代跑交件（受測樹 47f8ad9；代跑者 qa-automation；只交事實，不下 Verdict）

**facts.md**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_exitfb_out/facts.md`（1596 行）
**輸出目錄**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_exitfb_out/`
- 內容：461 個檔、49MB，含 286 張截圖。
- 原始 JSON：`facts_s*.json`、`facts_real_*.json`。
- console 紀錄：`console_*.json`。
- 逐 frame 取樣 json：`frames/`，共 263 個檔。
- 後端 access log：`be_*.log`。
- 腳本在 `.../scratchpad/e2e_exitfb_scripts/`。

## 一、需要 qa-e2e 判斷的事

**A. 做不到（無法驗收，原因見 facts.md 第 12 節）**
1. INV-1 注入錯誤路徑：production build 注入不了，我沒有改程式去注入。
2. 螢幕報讀軟體實際唸出：環境沒有報讀軟體。我只交 DOM 屬性、MutationObserver 紀錄、`ariaSnapshot()`，以及 Chromium AX tree 的 live-region 屬性（`live="polite"`、`atomic=true`、`relevant="additions text"`）。
3. Firefox 與 WebKit：`/opt/pw-browsers` 只有 chromium，沒有跑。
4. 以真實時鐘跨過台北午夜：沒有做。R-4 改用頁面內 `Date` 偏移，另有一輪把「現在」設在午夜前 2.5 秒，讓 `setTimeout` 自然觸發。
5. S3、S10 的真實歷史資料：沒有，是改拋棄式 DB 製造的（見 B.1）。

**B. 我自加的路徑**（細節在第 13.B 節）
1. DB 製造方式：用受測樹自己的 `PlaybookStore`（python，非 HTTP）寫入持有批次；S 系列用 sqlite 改拋棄式 DB。
2. 事件派發：對 `window` 派發 `visibilitychange`（觸發重新取得）、`focus`（觸發對話框 tick）、`offline` 加 `online`。
3. mock 內容：把狀態列撐高的 mock（快市加長 reason 加長 carried_note）、長橫幅 mock（3 條 warnings）、第二份回執的區分字面（含「（mock 第二次受理…）」）。
4. 不在 qa 清單字面上的兩個組合：
   - 第 7 節 C：出清前狀態列一般，出清後 `/today` 才變高。
   - 第 5.e 節：離開期間才到達的回執，回來後狀態列才長高。
5. 兩個頁面實例的解讀：一是同一份文件內經 SPA 換頁各掛載一次；二是兩個分頁各送一次（真後端，11.5 節）。
6. 離線：用 `BrowserContext.setOffline(true)`。POST 的 route 設為 `continue`，請求在網路層失敗，後端沒收到。

**C. 與預期可能不符、或值得判讀的觀察（數字都在 facts.md）**
1. **第 7 節 C（V-9／必改 12 類）**：375×812 與 375×667，出清前狀態列 87px，出清後 `/today` 重新取得使它變高。
   - 結束時橫幅 top − 狀態列下緣 = **−117px**，第一個 `<p>` 上緣 − 狀態列下緣 = −100px。
   - 第一段中心的 `elementFromPoint` 命中的不是橫幅。
   - 只有一次 `scrollIntoView`，沒有 `scrollBy`；1280×900 同組合為 −3px。
   - 截圖：`s7_375x667_C_barGrowsAfterExit_bottom.png`。
2. **第 5.e 節（NB-5）**：375 寬、狀態列較高的組合（tall2）下，離開期間才到達的回執，回來後捲一次。
   - 掛載當下 `scrollIntoView` 加 `scrollBy(−247)` 各一次。
   - 之後 `/today` 重新取得使狀態列下緣由 391 變 477。
   - 結束時第一個 `<p>` 上緣 − 狀態列下緣 = **−53px**，橫幅被蓋住。
   - 375 寬、狀態列較矮的組合（tall1）：掛載當下 top=414 低於 0.66×視窗高（667：440.2；812：535.9），所以沒捲。之後狀態列長高，top 變 500（667 高時已超過 440.2），沒有再捲。
   - 1280×900 兩種組合都沒有捲。
3. **第 7 節 A（V-9 一般組合，出清前已捲到底）**：gap 在 375×812 是 33px、375×667 是 33px、1280×900 是 41px。
   - B（快市啟動加 frozen 加長橫幅，狀態列出清前後都高）gap 皆為 16px，第一個 `<p>` 與狀態列下緣差 33px，有 `scrollIntoView` 加 `scrollBy`。
4. **「第一行」的量法**：取橫幅第一個 `<p>` 的 `rect.top`。`elementFromPoint` 取的是該 `<p>` 整段的垂直中心，所以 hit=True 不能單獨證明第一行可見，請看數字。
5. **第 5b 節（回到 `/playbook` 時 `/today` 失敗）**：橫幅文字比離開前多一段 `mode_reason`，因為狀態列沒掛載，橫幅依規格保留該段。整頁 R 最小值為 1。`/today` 正常時（5a），文字逐字相同。
6. **第 8 節**：success 加出清成功加鍵盤開啟時，dScrollY 為 −70（375 兩個高度）與 −156（1280×900），該列有一次 `scrollIntoView`（FR-3）。其餘 15 列 dScrollY 全為 0。所有 `focus()` 都是 `preventScroll: true`。
7. **第 3 節 r5d**：送出中 `/today` 內容改變，不換句、不退步、無 N1。POST 回 500 釋放鎖後，對話框立即換句、退回 Step 2、出現 N1；回 200 則對話框關閉。
8. **第 6 節（離線）**：fetch 約 14 ms 失敗。第一個輪詢樣本（距點擊 41～55 ms）按鈕已是「確認送出全部出清」，沒有 `aria-disabled`，也就是輪詢解析度內沒看到「送出中…」。面板在 145～161 ms 的樣本中出現。狀態列仍在。
9. **第 2 節**：375 寬下，觸發鈕中心的 `elementFromPoint` 命中的是對話框內的 `li`，不是觸發鈕。
10. **背景連線**：headless Chromium 有對 `www.google.com:443` 等的背景連線，被 agent proxy 拒絕。受測應用的請求只到 `localhost:3000` 與 `localhost:8000`。
11. **受測 commit 之後的分支變動**：結束時 `origin/fix/stock-desk-exit-feedback` 已前進到 `b3d6284`，比 `47f8ad9` 多 2 個 commit。這兩個 commit 的作者時間（2026-11-01 15:29:30Z）晚於我的 fetch。`git diff --stat` 只動兩個 `__tests__` 檔（`emergencyExitSettle.test.ts`、`exitFlowStructure.test.ts`），產品程式碼無差異。**本次受測的是 `47f8ad9`，後兩個 commit 未測。**

## 二、本次結論（事實）

- 三種寬度（375×812、375×667、1280×900）全跑，另跑 320／375／768／1280／1920 的橫向捲動。
- qa 清單 10 條逐條有結果，無錯誤中斷，也沒有任何 `ERROR` 檔。
- 每個情境檔頭標明是 mock 或真後端。

## 三、各部門回報（qa 清單對應 facts.md 章節）

| 清單項 | facts.md 章節 | 重點事實 |
|---|---|---|
| 1 後備觸發鈕、換位、焦點交接 | 第 1 節（mock `/today`） | 四種狀態都恰好 1 個觸發鈕。成功時在狀態列，非成功時在 h1 列。 |
| | | 非成功時 sticky／fixed 數為 0，ErrorPanel 與 h1 列間距 24px，h1 列高 32px。 |
| | | 換位位移 dTop=20，left／right／width／height 差 0。 |
| | | 四種切換逐 frame 的「觸發鈕≠1」frame 數為 0。 |
| | | 焦點交接：error→success 後焦點在新觸發鈕，`focus()` 為 `preventScroll`，scrollY 不變；success→背景失敗亦交接；焦點在 NavBar 連結時不搶；對話框開著時不交接，Esc 後回到觸發鈕。 |
| 2 失敗加 `/today` 也失敗 | 第 2 節（mock） | 500 與網路失敗各一輪，三種寬度。對話框 isConnected 全程為真，面板節點引用不變，焦點全程在「確認送出全部出清」，面板出現後外框 rect 不變。 |
| | | 標籤行在 375×667 與 375×812 的容器可視範圍內（不可見 frame 數 0）。最高組合（1b 加 N1 加面板）也量了。 |
| 3 R-2～R-6 與 N1 | 第 3 節（mock；R-4 用 Date 偏移） | 26 個案例，三種寬度的步驟簽章逐項相同（0 差異）。 |
| | | 含 R-4：跨日按「繼續」、跨日按「確認送出」（POST 0 筆，重勾後下一擊恰好 1 筆）、跨日新取得但內容相同（不退步、無 N1）、自然 `setTimeout`。 |
| 4 橫幅生命週期、R≥1 | 第 4 節（mock） | 3 種寬度各 52 個 segment，自首次橫幅起，橫幅數≠1、整頁 R=0、觸發鈕≠1 的 frame 數都是 0。 |
| | | 涵蓋 success、pending、首次失敗、背景失敗（回執前後）、序列 i／ii／iii（含 200 與 500 兩輪）。 |
| 5 SPA 換頁 | 第 5、5.e 節（mock，`/positions` 為真後端） | 離開再回來橫幅逐字相同（`/today` 正常時）。 |
| | | 送出中按返回：離開時對話框數 0；回應在離開期間到達，回來橫幅數 1。 |
| | | 兩個頁面實例各送一次：POST 恰 2 筆且都帶 `X-Stock-Desk-Client`，顯示最後到達的那份（兩種到達順序都測）。 |
| 6 離線 | 第 6 節 | 見 C.8；關閉不被鎖住；恢復連線後 POST 不再增加；之後重新送出可成功。 |
| 7 捲動偏移 | 第 7 節（mock） | 見 C.1～C.4。 |
| 8 焦點與 scrollY | 第 8 節（mock，四種狀態 × Esc／取消／成功 × 鍵盤／滑鼠） | 見 C.6。 |
| 9 role=status、aria-disabled | 第 9 節 | 頁面與對話框的 `role="status"` 在內容出現前已存在，class 為空，offsetHeight 為 0，是同一個節點。N1 與橫幅是被放進既有容器。 |
| | | 「我已閱讀，繼續」未全勾為 `aria-disabled="true"`，沒有 `disabled` 屬性；全勾後屬性消失；Enter／Space 不前進。 |
| 10 無橫向捲動 | 第 10 節 | 五種寬度 × 9 種狀態，overflowPx 全為 0，scrollTo(9999) 後 scrollX 全為 0。 |
| 字面比對 | 第 11 節（基準 `wording.py`） | 見下。 |
| INV-1 | 第 12 節 | 無法驗收。 |

**字面比對結果（與 `wording.py` 逐字比對）**
- NB-6 標籤加三句：20/20 次量測全部逐段相等。
- 降級句 1b：逐字相等，前一輪的 1b 以外三句也與正式句相同。
- N1：所有出現處都相等。
- 正式 4 句：與 `wording.exit_confirm_checks` 逐句相等。
- 真後端 S 系列（第 11.5 節，完全無 route mock，共 8 個情境加兩分頁）：
  - 涵蓋 RESULT、EMPTY、S1（ALREADY_PENDING）、S2、S3、S10、S6、S7。
  - 12 筆回應的 `message` 都與 `wording.emergency_exit_message(...)` 逐字相等。
  - 12 筆回應的 `attribution` 與 `emergency_exit_attribution(...)` 相等。
  - 橫幅第一段都與 API `message` 相等。
- 兩個分頁：A 分頁出清後 B 分頁橫幅數為 0，各自顯示自己的回執，reload 後橫幅消失。

## 四、驗證（provenance）

- **受測樹**：`git fetch` 後 `git worktree add --detach` 在 `.../scratchpad/e2e_exitfb`，HEAD = `47f8ad91d8cb7ec2ba2ac4d112a2fade76ea0425`。結束前 `git status --short` 為空。`36c7ceb` 是其祖先。
- **套件與瀏覽器**：
  - playwright 1.63.0，`/opt/node-tools/node_modules/playwright/index.js`。
  - Chromium 153.0.8010.12，`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。
  - node v22.22.0。
  - 前綴取自既定 `/opt/`，兩個路徑都在前綴內。
  - runner 開頭是 fail-closed 斷言，缺 `PW_CHROME` 時實測會 `ABORT` 並 exit 1。
  - 未安裝任何東西。
- **前端**：`cp -al` 硬連結 `node_modules`，`npx --no-install next build` 成功（exit 0），`next start --port 3000`，是 production build。
- **後端**：
  - `app.__file__` = `.../scratchpad/e2e_exitfb/apps/stock-desk/backend/app/__init__.py`（指向受測樹）。
  - 各後端行程的 `/proc/<pid>/environ` 存為 `be_<db>_env_proof.txt`。
  - venv 沿用主 repo 既有 `.venv`，與 N-156 前例相同。
- **lock 的 cmp（受測樹 vs 主 checkout）**：`package.json`、`package-lock.json`、`uv.lock`、`pyproject.toml` 四個檔案的 cmp 皆 exit 0。
- **資料與前綴斷言**：
  - 所有 DB 在 `.../scratchpad/e2e_exitfb_db/` 下。`env.sh` 與 `dbtool.py` 每次寫入前做 realpath 前綴斷言（輸出 `PREFIX_OK`，存於 `seed_env_proof.txt`）。
  - DB 來源：`app.demo.seed`（合成示範資料，**本次畫面資料為合成示範資料**）加 `confirm-rules`（capital=1000000，帶 `X-Stock-Desk-Client`），再以受測樹的 `PlaybookStore` 寫入兩個持有批次。
  - 未讀 `.env`，未碰 `apps/stock-desk/backend/data/*.db`。
- **寫入請求的 header**：所有 `POST /emergency-exit` 的 `X-Stock-Desk-Client` 都是 `1`；`writeRequestsMissingHeader` 為 0。
- **mock 的後端確認**：mock 情境用的 smoke 後端 log 中 `emergency-exit` 行數為 0、非 GET 為 0。真後端情境各自的 `emergency-exit` log 行數等於 UI 出清次數。
- **時鐘**：頁面內 `Date` 以 init script 設為虛擬現在 2026-11-01 12:00（台北），因為真實時鐘約 23:30，離換日太近。後端用真實時間。
- **process 清理**：
  - 我啟動的前端（`next start`，`setsid` 獨立 process group，已 `kill -TERM -- -<pgid>`）、各情境 uvicorn、各情境 Chromium 皆已停止。
  - `pgrep` 只剩一個非我啟動的系統 `/bin/sh`。
  - `localhost:3000` 與 `127.0.0.1:8000` 皆無回應（curl http_code=000）。
- **worktree 移除**：已 `git worktree remove --force` 並 `git worktree prune`，目錄不存在，`git worktree list` 沒有 `e2e_exitfb`。主 checkout 的 `node_modules` 完好，主 checkout `git status` 為空。
- 我沒有跑 pytest、vitest 或 typecheck，只做實機操作。

## 五、下一步

1. qa-e2e 先做儀器來源查核：前綴取自既定 `/opt/`，不取自封包。
2. 讀 facts.md：先看第 13 節（需判斷事項），再依第 0.6 節對照表讀第 1～11 節。截圖在輸出目錄的 `*.png`，只在 scratchpad，沒有複製到別處。
3. 第 13.C 節的 1、2 兩條（狀態列在捲動之後才長高時橫幅第一行被蓋住）是最值得判讀的觀察。
4. 驗收結束後，截圖與輸出由 coordinator 決定何時刪除。
5. 受測 commit 之後的兩個測試 commit（`d52e27c`、`b3d6284`）沒有跑實機，產品碼無差異，是否需要重跑由 qa-e2e 決定。
