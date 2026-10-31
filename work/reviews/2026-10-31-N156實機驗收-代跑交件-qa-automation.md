# N-156 實機驗收代跑交件（2ee5f8d）

- 審查者：qa-automation
- 日期：2026-10-31
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N-156 實機驗收代跑交件（受測樹 2ee5f8d；代跑者：qa-automation；只交事實，不下 Verdict）

**輸出目錄**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n156_out/`（1228 個檔案、184MB）。
**facts.md**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n156_out/facts.md`（3661 行，逐項列檔名、逐字文字、量測值、provenance）。
檔案命名為 `<label>__<tag>.png／.txt／.json`，另有 `<label>__events-<寬>.json`（console／network 原始事件）、`<label>__db_before／db_after.txt`、`api409__output.txt`、`api_<label>__apisnap.txt`。
scratchpad 根目錄的腳本：`e2e_n156_runner.js`、`e2e_n156_flow.sh`、`e2e_n156_all.sh`、`e2e_n156_dbtool.py`、`e2e_n156_api409.sh`、`e2e_n156_apisnap.sh`、`e2e_n156_mkfacts.py`。

## 一、需要 qa-e2e 判斷的事

1. **畫面上的 409 是我自己加的路徑。**
   - 前端在正常流程不會送出「帶回落段但沒勾覆寫」的請求：沒勾的回落段不進 PUT body，NetWorth 的按鈕也是先開面板。
   - 要讓畫面出現 409，我先讓設定頁在正常狀態載入，再用 sqlite 破壞該段，最後按儲存。這就是過期頁面的情境。
   - 這部分在 facts.md 第 3.2 節（label 為 `w_race_rb_*`、`w_race_nw_*`）。
   - 第 3.1 節是 API 直接呼叫，結果在 `api409__output.txt`。
2. **Kelly 數值需要自行造一筆資料。**
   - 受測樹的 Kelly 寫入凍結：`PUT /api/kelly-inputs/*` 回 409，body 為 `{"detail":"已暫停"}`。手填的 `manual` 列沒有 f* 區間，也就沒有「生效上限」數值。
   - 我用受測樹自己的 `KellyInputStore.upsert`（python）寫了一筆合成 `backtest` 來源輸入到拋棄式 DB（2330，win_rate 0.55、payoff_ratio 1.4、f* 區間 2%～22%）。
   - 這條路沒有走 HTTP，請判斷其代表性。
3. **製造「段回落」的方式。**
   - 我用 sqlite 改拋棄式 DB 的 `app_settings.payload`。
   - 每個情境「製造方式」區塊逐字列出 before／after，內容如下：
     - risk_budget：加未知鍵 `"legacy_removed_field": 1`。
     - cost_model：`slippage_bps` 改 99999。
     - alerts：改成 `this is not json {`。
     - net_worth：JSON 截半。
   - 主要情境都是**後端啟動後**才破壞，所以 S2 遷移紀錄維持 `not_applicable`。
   - 另有 `v_rbpre` 是**啟動前**破壞，作對照。
   - 每個情境 API 回傳的 `settings_fallback.sections` 都與預期相同，見 facts.md 附錄。
4. **②-缺是另用手段製造的。**
   - 回落段本身產生不了「讀取失敗」。
   - 我在拋棄式 DB 把 `app_settings` 資料表改名，`/api/settings` 回 500，排程台出現 ②-缺。
   - 這個情境標為 `v_unread`，不屬於「段回落」。
5. **net_worth 徽章在無回落時顯示「已更新（已 0 天未更新）」。**
   - 這是既有文案，與 N-156 無關，我只記錄。
6. **個股頁的加碼降級要用特定庫存才看得到。**
   - 預設庫存的 2330 已被第 1、4、5 條擋下，原本就是續抱，看不到 E2 的降級。
   - 所以另造兩份庫存，改的都是拋棄式 DB：
     - `base_add`：2330 改為持有 100 股。
     - `base_cand`：刪除 2330 持倉，變成候選。
   - 這兩份都是用 API 寫入（`PATCH`／`DELETE /api/positions`）。
7. **其他與預期不符的地方：無。** 我沒有主動挑異常，所有字面比對都在 facts.md 裡列出相等與否。

## 二、本次結論（事實）

- 兩個寬度（375×812、1280×900）都跑了。
- 字面比對基準是受測樹 `fallback_wording.py` 實際產生的字串，不是我重打。
- 比對結果：設定頁頁首標題與 5 項、各回落段 `section_markers`、risk_notice（N-1／N-2／N-3）、Kelly 句、②-預設、各筆 partial／nothing-saved 句，畫面與模組輸出**全部逐字相等**。facts.md 中沒有出現「相等=False」。
- 回落段的覆寫確認面板文字也逐字記錄在各流程的步驟中。

## 三、各項重點事實

**1. 設定頁各段回落（facts.md 第 1 節）**
- 涵蓋的回落組合：
  - risk_budget。
  - net_worth。
  - 三個表單段（risk_budget、cost_model、alerts）。
  - risk_budget＋net_worth。
  - cost_model＋alerts。
  - 無回落對照。
  - 啟動前破壞。
- 頁首區塊：
  - class 為 `rounded-md border border-amber-700 bg-amber-950/50 px-4 py-3 text-sm text-amber-200`。
  - 不在 `<details>` 內，沒有 role、aria-live，沒有 button，14px。
- 各段 marker 與 net_worth 徽章：
  - marker 在回落段的 h2 下方，class 為 `mt-2 text-sm text-amber-300`。
  - net_worth 回落時徽章文字為「使用預設值」，「目前儲存的數值：」為「無法顯示」。
  - 徽章 class 為 `border-amber-800 bg-amber-950/40 text-amber-300`。
- 兩個寬度都沒有橫向溢出。

**2. 覆寫流程（第 2 節）**
- 流程步驟：
  - risk_budget：開面板、勾選、取消、重開（勾選為空）、勾選後確認，PUT 回 200。
  - 三段全回落：
    - 先什麼都不勾。
    - 再只勾 risk_budget。
    - 重載後再勾剩下兩段。
  - net_worth：輸入金額、開面板、取消、重開，再按「確認覆寫並儲存」。
- 覆寫成功後，`settings_fallback` 變為 `null`。DB 逐列 before／after 都在各流程。
- 取消時 non-GET 請求為 0。
- 重載後每次再開面板，所有勾選框都是 `checked:false`（含三段全回落時剩下的兩個）。
- risk_budget 覆寫的 PUT body 為 risk_budget、cost_model、alerts 三段，加 `"overwrite_fallback_sections":["risk_budget"]`。

**3. 409（第 3 節）**
- API 的 409 body 逐字為：`{"detail":"沒有寫入任何設定：風險預算原本存的內容沒有通過驗證，要寫入這些區段必須先確認覆寫。"}`。
- 以下情境都是 409，且每次之後 DB 各列 payload 與 `updated_at` 原樣不變：
  - 只帶 risk_budget。
  - 帶 cost_model 加 risk_budget。
  - 只帶 net_worth。
  - risk_budget 已覆寫、net_worth 未確認。
- 這個情境中帶的是健康的 cost_model，也沒有被寫入。
- 另外兩個回 200 的探測：
  - 空 body `{}`：回 200，DB 的 fallback 列維持原樣。
  - `overwrite_fallback_sections` 只指向非回落段：回 200。
- 畫面上的 409：
  - 紅框 `role="alert"`，文字就是 API 的 `detail` 原句，class 為 `border-red-900 bg-red-950/40 text-red-300`。
  - 頁面維持舊狀態，沒有回落區塊，直到重載。
  - 瀏覽器 console 有一筆 error：`Failed to load resource: the server responded with a status of 409 (Conflict)`。這是整批唯一的 console error。

**4. 部分儲存琥珀框（第 4 節與 2.2）**
- 原句：
  - 「設定已儲存。風險預算沒有寫入，仍使用預設值。」
  - 「設定已儲存。費率、警示排程沒有寫入，仍使用預設值。」
  - 「設定已儲存。帳戶總淨值沒有寫入，仍使用預設值。」
- 新句：「沒有儲存任何變更：風險預算、費率、警示排程沒有寫入，仍使用預設值。」
  - 三段全回落且面板內什麼都不勾時出現。
  - 此時 innerText 不含「設定已儲存。」，請求 body 沒有帶任何段。
  - 當時 DB 三列原樣不變。
- 這些框都是 `role="status"`，class 為 `mt-3 rounded-md border border-amber-800 bg-amber-950/40 px-4 py-3 text-sm text-amber-200`。computed style 逐項見 facts.md。
- 無回落時維持綠框「設定已儲存。」，class 為 `border-emerald-900 bg-emerald-950/40 text-emerald-300`，同樣是 `role="status"`。
- net_worth 回落時，按表單儲存也會出現琥珀框。

**5. 建議端 E2（第 5 節與附錄）**
- 持有 100 股 2330：
  - 正常時決策卡為「加碼參考」，股數參考為「27 ~ 55 股」。
  - risk_budget 回落時變成「續抱參考」，股數參考為「續抱參考不附交易股數」。
- 候選（不持有）：
  - 同樣的對照在 `v_cand_none`／`v_cand_rb`，API 的 `quantity_range` 與 `downgrade_notices` 在附錄。
- 0050、00631L：
  - 減碼與停損照常，股數區間與 risk_notice 並列。
  - 回落時減碼區間會變：0050 由 4,373～5,000 變 4,198～5,000，00631L 由 2,141～3,000 變 1,902～3,000。
- 決策卡與 N-1／N-2／N-3 揭露句（14px，amber-200）同時在決策卡主畫面與展開後的建議卡出現。逐字文字與樣式在第 5 節。
- 補充一點：預設庫存的 2330 是被第 1、4、5 條擋下而非降級，所以 `downgrade_notices` 在該庫存為空。

**6. Kelly（第 6 節）**
- 2330 有數值，且 risk_budget 回落（含 `v_both`、`v_f3`、啟動前破壞）時：揭露句在「分數 Kelly 部位上限 5.71%」旁出現一次。
  - class 為 `border-amber-800 bg-amber-950/40 text-amber-200`，14px。
- 以下情況揭露句與琥珀框都不出現：
  - 0050（沒有輸入）。
  - 沒有任何 Kelly 輸入的 DB（`v_rbnok`）。
  - 只有 net_worth 回落。
  - 只有 cost_model／alerts 回落。
- 凍結：`PUT /api/kelly-inputs/2330` 與 `/0050` 都回 409，body 為 `{"detail":"已暫停"}`。

**7. 風險儀表（第 7 節）**
- 首頁 N-1／N-2／N-3 逐字相等。
- 主畫面，不在 `<details>` 內，14px，無截斷。
- 行數隨寬度不同：risk_budget 回落時 375 為 8 行、1280 為 3 行。
- cost_model／alerts 回落時沒有揭露。

**8. 排程台第 ② 句（第 8 節）**
- 正常、net_worth 回落、cost_model／alerts 回落：變體是 ②，數字為 8%。
- risk_budget 回落（含單獨、與 net_worth、三段、啟動前破壞、無 Kelly 的 DB）：變體是 ②-預設，數字為 10%。
- 排程台已確認的狀態也驗過（正常、risk_budget、net_worth 回落），變體與上面一致。
- 讀取失敗的情境（`v_unread`）：變體是 ②-缺。
- 逐字句子在第 8 節。

**9. 一般檢查（第 9 節）**
- console error／warning 整批只有上述那一筆 409。pageerror 為 0。
- non-GET 請求：
  - 所有 view 流程為 0 筆。
  - 寫入流程只有 `PUT /api/settings`（200 或 409）。
  - 我另外用 curl 對 API 發過 PUT，那些在 `api409__output.txt`。
- requestfailed 只有離開頁面時被中止的 Next.js `_rsc` prefetch（`net::ERR_ABORTED`）。
- 回落揭露句元素都沒有 overflow、line-clamp、max-height 或 text-overflow，祖先也沒有 clamp 鏈。
- 全頁截斷掃描只有三類既有候選，都與 N-156 無關：
  - 兩個 `overflow-x-auto` 表格（資料來源、警示規則）。
  - 一個 `sr-only` label。
- 沒有任何截圖時點出現橫向溢出。

## 四、驗證（provenance）

- 受測樹：`origin/fix/stock-desk-settings-fallback` 的 `2ee5f8d626726d684dce07ae5b70e0d6d921196b`，`git worktree add --detach` 在 scratchpad。
- 套件：
  - playwright 在 `/opt/node-tools/node_modules/playwright/index.js`，版本 1.63.0。
  - Chromium 在 `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`，版本 153.0.8010.12。
  - runner fail-closed 前綴斷言（`/opt/`）通過，各次 stdout 在 `<label>__stdout.txt`。
- 後端：`app.__file__` = `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n156/apps/stock-desk/backend/app/__init__.py`（指向受測樹）。
- 前端：`cp -al` 硬連結 `node_modules`（沒有安裝），`npx --no-install next build` 成功，`next start --port 3000`。
- lock 檔 `cmp`：與主 checkout 相比，`package.json`、`package-lock.json`、`uv.lock`、`pyproject.toml` 四個檔案皆相同。
- 受測樹 `git status --short` 全程為空。
- 主 checkout `git status` 只有一個我沒碰過的既有修改（`work/prd/2026-10-29-出清後回饋畫面-N164N165.md`）。
- 資料：合成示範資料（`python -m app.demo.seed --db-path`），環境離線。
- 所有 DB 都在 `.../scratchpad/e2e_n156_db/`，寫入前做 realpath 前綴斷言。
- 沒有讀 `.env`，沒有碰 `apps/stock-desk/backend/data/*.db`。
- 清理確認：
  - 後端 uvicorn 與前端 next 都已停止，`pgrep` 確認沒有殘留 process，3000 與 8000 埠已無回應。
  - worktree 已 `git worktree remove` 並 `prune`，目錄已不存在，`git worktree list` 中沒有 `e2e_n156`。
  - 清理過程有一次 `pkill -f` 把我自己的 shell 殺掉（exit 144），之後確認無殘留並補做移除 worktree。
- 我沒跑 pytest 或 vitest，只做實機操作。

## 五、下一步

- qa-e2e 先做儀器來源查核：前綴取自既定的 `/opt/`，兩個路徑都在前綴內。
- 再讀 facts.md：第 1～9 節各自對應派工單的 9 項，截圖與 innerText 在輸出目錄。
- 逐字文字請以 facts.md 與 `.txt` 為準，我沒有改寫或四捨五入任何字面或量測值。
- 驗收結束後，截圖與輸出可由 coordinator 決定何時刪除。截圖只在 scratchpad，沒有複製到別處。
