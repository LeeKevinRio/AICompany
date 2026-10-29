# 整合實機驗收代跑交件（產品線＋第一批＋N-155，e2e_combo b56ff37）

- 審查者：qa-automation
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# e2e-fallback 代跑交件：受測樹 e2e_combo（代跑者：qa-automation；只交事實，不下 Verdict）

**輸出目錄**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_combo_out/`（約 214 個檔案、20MB；png、innerText、results-*.json、console／network JSON、後端 log）
**facts.md**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_combo_out/facts.md`（721 行，逐項列檔名、URL、viewport、逐字文字、量測值與 provenance）
**腳本**（都在 scratchpad 根目錄）：`e2e_combo_runner.js`、`e2e_combo_run.sh`、`e2e_combo_start_be.sh`、`e2e_combo_start_old.sh`、`e2e_combo_put.sh`、`e2e_combo_mkfacts.py`

## 先講需要你判斷的事

1. **A2「先存 0.15、重啟、觸發遷移」在受測樹上做不到。**
   - 我照做了：後端啟動後第一次讀設定，`SettingsStore` 就寫入終態紀錄 `not_applicable`。
   - 之後 `PUT` 存 0.15 回 200，重啟後 `cap1_migration` 仍是 `not_applicable`、`notice` 為 null、設定值仍 0.15。`migrations.py` 文件也寫明 `migrated`／`not_applicable` 是終態。
   - 原始輸出在 `s2_attempt1_put015.txt`。第一次不帶 header 的 PUT 被 403 擋下，原文是「寫入型請求必須帶 X-Stock-Desk-Client header」，所以後續寫入都帶了該 header。
   - 為了仍能拍到 S2 告知，我走了一條沒有直接改 DB 的路：
     - 用 `git archive 43e376b`（= `e6de882^`，預設仍是 0.15、尚無 S2）解出舊版後端，放在 scratchpad `e2e_combo_oldbe/`。
     - 由舊版後端經 `PUT /api/settings` 寫入 0.15。
     - 再用受測樹啟動同一個 DB，由受測樹自己遷移，變成 `migrated`（0.15 → 0.1，`changed_by_user=false`）。
   - **這條路是我自己加的，請判斷它是否有代表性。** 這個狀態用的 DB 是 `mig.db`。
   - `demo.db` 因為存了 0.15 且 `not_applicable`，只當對照樣本（標 `demo015`）：設定頁沒有告知區塊，首頁與個股頁也沒有 S2 句。
2. **第 5 條註記**（`計算方式有誤，算出的數字不可靠。`）只在第 5 條是 `passed`／`violated` 時出現。
   - `mig.db` 的 2330 沒有 Kelly 輸入，第 5 條是「無法評估」，註記不出現。
   - 受測樹 `PUT /api/kelly-inputs/2330` 回 409，body 為 `{"detail":"已暫停"}`。
   - 我把 `mig.db` 複製成 `migk.db`，用舊版後端 API 寫入 `win_rate 0.5／payoff_ratio 1.5`，再以受測樹啟動，取得有註記的畫面。
3. **EXIT 流程只走到 Step 2、Step 3 並取消，未點「確認送出全部出清」**（會寫入凍結狀態、無法還原）。期間 non-GET 請求為 0。
4. 排程台確認用 `POST /api/playbook/confirm-rules`（capital=`1000000`，合成數字），回應在 `B_confirm_rules_response.txt`。

## 重點事實

**Provenance**
- playwright：`/opt/node-tools/node_modules/playwright/index.js`，1.63.0。
- Chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`，153.0.8010.12。
- trustedPrefix：`/opt/`，斷言通過。
- 後端 `app.__file__` 已確認指向受測樹。
- 受測樹與主 checkout 的 `package.json`、`package-lock.json`、`uv.lock` 以 `cmp` 比對相同。
- 受測樹與主 checkout 的 `git status` 全程為空。
- 資料是合成示範資料，環境離線，外部資料源一律回 `403 Forbidden`。
- 我啟動的 uvicorn 與 next 已全部殺掉，確認沒有殘留 process。

**A1 個股頁 2330，展開建議卡（375／390）**
- 展開方式是真的點「建議卡 命中 2 條」的 summary。
- 第 1 條「已違反」chip 與 S1 句在同一個 `<li>`（`closest('li')` 相同，S1 的 parent 就是該 `<li>`）。
- S1 句與 API `cap1_migration_notice` 逐字相等，全頁只出現 1 次。
- 量測值：

| 項目 | 375 | 390 |
| --- | --- | --- |
| S1 寬×高 | 233×112 | 248×96 |
| S1 行數 | 7 | 6 |
| font-size／line-height | 12px／16px | 12px／16px |
| color | `lab(86.4156 6.13147 78.3961)` | 同左 |

- 截斷與巢狀檢查：
  - overflow `visible`、text-overflow `clip`、line-clamp `none`、max-height `none`。
  - scrollHeight 等於 clientHeight，往上的祖先沒有任何 clamp 或 overflow。
  - S1 與 `<li>` 之間沒有多出的 `<details>`，`<li>` 內 `<details>` 為 0。

**A2 設定頁（375／1280）**
- 告知區塊標題與 5 項逐字都在 facts.md。字級 12px，無 `<details>`、無可聚焦元素、無 role／aria-live。
- 位置：
  - 375：單欄，告知 top 966，在第 1 條欄容器 bottom 之下 16px，後面接單一產業欄。
  - 1280：欄位格是 `grid-flow-row-dense`。第 1 條欄在 (left 229, top 606)，單一產業欄在同一列右側 (left 648, top 606)，告知區塊在兩欄下方、全寬 822 (top 784)。
  - DOM 順序是第 1 條 → 告知 → 單一產業。
- Tab 走一遍：
  - 順序為第 1 條欄 → 單一產業 → 總曝險 → 單筆虧損 → ATR → 分數 Kelly → Kelly 硬上限。
  - 告知區塊沒有可聚焦元素，Tab 不停在它上面。
  - 與 1280 畫面由左到右、由上到下的順序相同；375 的 DOM、畫面與 Tab 順序三者相同。

**A3 首頁第 1 條列**
- 列文字：`40.92%／10.00%`、`觀測值最高：0050`、彙總句 `3 檔持股已達或超過第 1 條上限（10.00%）。`、S2 句。
- 順序：S2 句在彙總句之後，兩者都是 12px。
- 行數：S2 句在 1440 是 2 行，在 375 是 5 行。
- 沒有 `<details>`、沒有 clamp。

**A4 Kelly**
- 日落導語全文已逐字記錄，12px，color `lab(48.496 0 0)`。1280 為 3 行（height 48），375 為 8 行（height 128）。
- 兩顆「已暫停」按鈕：
  - `disabled=true`，opacity 0.5，cursor `not-allowed`。
  - hover 時 `:hover` 有命中，但 bg、color、opacity、border 都沒變。
  - 對它們 `click({force})` 沒有任何非 GET 請求。
  - 把日期欄填滿後仍是 disabled，所以不是因為日期空白才停用。
- `migk` 狀態有「刪除」鈕，是啟用的。
- 第 5 條註記在 `migk` 的 2330 頁出現，是獨立 `<p>`，14px，位於第 5 條說明文字之後、「觀察值」行之前。

**B 排程台（unconfirmed、confirmed 各 375／1280）**
- 兩種狀態區塊數量都是 1。
- unconfirmed：
  - 區塊在 `RuleSetConfirmPanel` 內，順序為規則參數（h3＋dl）→ **本區塊（h3）** → ⑥ 同意句（`確認即表示這份規則集為你本人設定。…`）→ 資本額欄。
  - 今日頁沒有第二份。
- confirmed：
  - 順序為歸屬語 → page_summary 3 句 → warnings 4 個 `<div>` → **本區塊（h2）** → 今日指令帳冊 → 部位快照 → 結算。
  - 確認面板不渲染。
- 標題與 4 句逐字都在 facts.md。
- 共通：
  - 標題 14px、font-weight 500、`lab(90.952 0 -0.0000119209)`；4 句 14px、`lab(84.92 0 -0.0000119209)`。
  - `<details>`、`<summary>`、button、a、svg、img、tooltip 屬性都是 0。
  - 4 句在 1280 的行數是 2、2、2、1，在 375 是 6、5、5、4（confirmed 狀態；unconfirmed 的 375 為 7、5、5、4）。
- EXIT 流程 Step 2 與 Step 3：對話框內**沒有**區塊標題與 4 句。我的粗略正則曾命中對話框既有的「單一標的」一詞，那是對話框原有句子，不是揭露區塊。
- **另一個現象**：EXIT 對話框的 `position:fixed` 遮罩被 `sticky top-0 z-10 … backdrop-blur` 的祖先 div 當成 containing block。
  - 遮罩高度只有 86px；面板上緣在視窗之外（1280 寬時 y=-70，375 寬時 y=-22）。
  - 其餘頁面沒被遮罩蓋住。
  - 我只量測，不判斷是否為缺陷。

**C6 全新空 DB 首頁首次載入**
- 做法：每次用事先確認不存在的 DB 路徑啟動，啟動後不先打任何 API，直接由瀏覽器開首頁。共 5 次。
- 結果：console 0 筆、非 2xx 0 筆、requestfailed 0 筆，後端 log 無 Traceback、無 500。
- 上次的 CORS／`net::ERR_FAILED` 與 `duplicate column name: bar_as_of` 本次都沒再出現。5 次不足以證明競態已消失。

**C7 無價持倉橫幅**
- 做法：經 API 新增 `9999`（`POST /api/positions` 回 201）。
- 「部分」版本：另有種子 3 檔有價，`totals.status=partial`。
- 「所有」版本：再 `DELETE` 種子 3 檔（皆 204），只剩 9999，`totals.status=no_data`。
- 橫幅逐字：
  - 所有版：`所有部位皆無法估值，總計無法計算。`
  - 部分版：`部分部位無法估值，總計僅含可估值部位。`
- 三個寬度（1440、375、390）各一張，1 行，14px，color `lab(86.4156 6.13147 78.3961)`，寬度分別為 992、343、358。
- **「位位」**：6 個畫面（所有／部分 × 3 寬度）的 body innerText 都不含「位位」；受測樹原始碼的 `SUMMARY_BANNER_NO_DATA` 也沒有。

**全程 console 與 network**
- 12 批 console 的 error、warning、pageerror 全是 0；非 2xx 全是 0。
- 唯一的 requestfailed 是離開首頁時被中止的 Next.js `_rsc` prefetch（`net::ERR_ABORTED`，共 29 筆：mig 9、demo015 12、partial 8），原文逐條在 facts.md 第 4 節。
- 後端 log 的 WARNING／ERROR 都是離線造成的外部資料源失敗與環境變數未設：
  - `403 Forbidden`（TWSE、TPEx、yfinance）。
  - `FINMIND_API_TOKEN` 未設。
  - `ALPHA_VANTAGE_DAILY_LIMIT` 未設。
  - `no provider and no cache entry available for ^TWII`、`…for 9999`。

## 無法完成或有限制的項目

1. A2 照派工單做法無法觸發遷移（見上，原始輸出在 `s2_attempt1_put015.txt`）；改用舊版後端寫入的路徑。
2. 第 5 條註記在 `mig.db` 不出現，原因是第 5 條無法評估；改用 `migk.db`。
3. EXIT 送出後的橫幅與狀態沒驗（不可逆）。
4. 派工單沒要求的組合沒拍：首頁第 1 條列在 390 寬、設定頁在 390 寬。C6 只取 1440 寬，且只有 5 次樣本。
5. `results-B_conf.json` 中 375 寬那次 EXIT 流程的 `viewport` 欄位，是 runner 寫死的 1280×900，記錄有誤；實際 viewport 以同項的 `dialogGeom.viewport`（375×812）為準，facts.md 已註明。
6. 行數是用逐字元 Range 的 top 分組算出，單一字級元素可信。
7. 我沒跑 pytest 或 vitest。除上面明列的 PUT、POST、DELETE 外，沒有其他寫入型 API 操作。
8. 我刪除了 `demo015` 與 `mig` 的 A2「風險預算區塊」兩組截圖，因為截到了錯的元素（警示規則區）。`mig` 的兩張已用正確元素重拍並覆蓋；`demo015` 的兩張未重拍。
