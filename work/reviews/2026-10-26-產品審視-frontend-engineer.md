# stock-desk 全公司產品審視（實機操作視角）

- 審查者：frontend-engineer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## stock-desk 離線示範資料實跑評估（frontend-engineer，唯讀審視）

證據前提：畫面資料全為合成示範資料（source=demo_synthetic），非真實行情。
- 以 e2e-fallback 路徑執行：playwright 為 /opt/node-tools/node_modules/playwright，chromium 為 /opt/pw-browsers/chromium-1243。兩者都在 /opt/ 前綴內。
- 未改 repo 任何檔案，未做 git 寫入。`npm install --no-save` 會在 frontend 產生 node_modules，`uv run` 會在 backend 產生 .venv；兩者都被 .gitignore 忽略，我沒有檢查。
- 啟動的後端與前端程序都已停掉，8000、3000 兩個 port 都已確認無回應。
- 截圖、log 與 DB 都在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/ux/`（下稱 `$S`，實際路徑如截圖清單）。
- 操作流程中對 demo.db 做過寫入：新增再刪除 2454、改過風險上限（最後設回 0.15）、標記 1 條警示為已處理、在排程台確認規則集並設資本額 1,000,000。
- 目前 demo.db 已 `--reset`（示範持倉清空，警示事件依設計保留）。

---

## 一、評分（1～5 分）

| 項目 | 分數 | 依據 |
|---|---|---|
| 合理性 | 3.5 | 資料誠實度、降級標示、免責與「非建議」的紀律很強：缺資料標「資料不足」或「—」，不假造數字，每張卡都標資料日與快取狀態。扣分在於系統整體過度工程化，且有幾處內部不一致（見問題 3、4、5）。 |
| 好用性 | 2.5 | 「我持有的股票現在該怎麼辦」要點進每檔個股頁才看得到結論，總覽沒有各檔建議。新增持倉要選 6 個欄位。設定頁的儲存回饋離輸入欄約 1500px。排程台與庫存互不相通。 |
| 簡易清楚 | 2.0 | 一檔個股頁展開後高達 8356px，排程台 32 個 snake_case 參數直接攤出。警示訊息夾帶 `cached_stale`、`violated_limit_ids`、`lt -0.2`、`verified_on 為 null` 等開發字眼。第一次使用者 3 秒內看不懂要做什麼。 |

---

## 二、逐頁觀察

### 1. 首頁 `/`（投資組合總覽）
桌面：`$S/01-home-desktop.png`；手機：`$S/01-home-mobile.png`（整頁縮圖）、`$S/40-home-mobile-firstscreen.png`（首屏）。
- 上方有 4 張數字卡：總資產 NT$2,566,530、未實現損益、標的貢獻、匯率貢獻。其中「標的貢獻」與「匯率貢獻」對一般人是術語，且與未實現損益數值重複。
- 持倉明細表只有代號、現價、損益%、損益、漲跌，沒有建議（續抱／減碼）、持股數、佔比。點列首的三角形展開才看到數量與成本（`$S/60-home-row-expanded-top.png`）。
- 風險儀表顯示「第 1 條 單一標的佔比上限 已違反 40.92%／15.00%」，「觀測值最高：0050」要細看才知道是哪一檔。
- 待處理警示卡顯示原始欄位，例如 `violated_limit_ids: single_position_weight violated_count: 1`、`field: drawdown.max_drawdown value: -0.46032763532763543 op: lt`。內文也有 `資料來自 cached_stale 層（demo_synthetic）`，見 `$S/01-home-desktop.png`。
- 紅漲綠跌（台股慣例）在 `frontend/app/lib/format.ts:5-6` 的註解有說明，但畫面沒有圖例。「NT$-130,930」的負號位置也不自然。
- 手機：欄位改為卡片，沒有水平捲動。但首屏全是 4 張大數字卡，持倉表要捲過一屏才出現（`$S/40-home-mobile-firstscreen.png`）。
- 警示「標記已處理」按下後該筆就消失，沒有看到已處理歷史的入口。

### 2. 庫存 `/positions`
桌面：`$S/02-positions-desktop.png`；手機：`$S/02-positions-mobile.png`；表單展開：`$S/20-positions-add-and-csv-open.png`。
- 手機版改為卡片，清楚、可用。
- 新增表單必填 6 欄：代號、市場、類型、幣別、數量、成本，其中市場、類型、幣別都是「請選擇」下拉。代號輸入 2330 時沒有自動帶出市場與幣別。
- 空必填欄只會跳瀏覽器內建的英文訊息 “Please fill out this field.”，見 `$S/21-add-empty-submit.png`。
- CSV 匯入除「下載 CSV 範本」連結外，沒有欄位說明。
- 頁首「新增」按鈕與下方「新增持倉」手風琴並存，讓人不確定兩者差別。

### 3. 個股頁 `/position/2330?market=TW`
桌面：`$S/03-position-2330-desktop.png`；手機：`$S/03-position-2330-mobile.png`；手機首屏：`$S/41-position-mobile-firstscreen.png`；全展開：`$S/11-position-2330-expanded.png`（8356px 高）；建議卡：`$S/15-advice-card.png`；槓桿 ETF（00631L）：`$S/16-position-00631L-top.png`、`$S/12-position-00631L-expanded.png`（9438px 高）。
- 首屏有大字「續抱參考」，加上停損參考 859.89、停利參考 966.54 與 K 線，這是全站最好的畫面，直接回答「該怎麼辦」。
- 但同一頁的建議卡寫「加碼建議被風險上限擋下」，命中規則的動作是「加碼參考」權重 0.50。結論「續抱參考」與規則方向「加碼參考」需要讀完整張卡才對得起來。
- 「股數參考：未提供股數」：2330 我持有 1,000 股，卻顯示未提供。00631L 反而顯示「1,256 ~ 3,000 股」。兩檔行為不一致。
- 「基準價（持倉平均成本）」這行標籤後面沒有數值（要到下方價位階梯才看到 895.44）。
- 「六項觀察條件」只有 6 個圓點圖示，沒有標籤，要展開才知道每個點代表什麼。
- 同一頁重複出現「頁尾『…』涵蓋本區資料來源…」的指路句，內容沒有資訊量，卻佔版面。
- 價位階梯、MA20 ±3% 標籤、「大字所示」等術語沒有說明。
- 不存在的代號（`$S/13-position-unknown-9999.png`）與無資料的情況（`$S/82-empty-position-2330-desktop.png`）：誠實顯示「資料不足」與「—」，這是好的。
- 手機沒有水平捲動，K 線可用（`$S/42-position-mobile-chart-area.png`）。

### 4. 排程台 `/playbook`
桌面：`$S/04-playbook-desktop.png`；手機：`$S/04-playbook-mobile.png`；確認規則集後：`$S/70-playbook-after-confirm.png`。
- 首次進入是一整面規則條文（R1…R4、S1…S3、P1…P3、M1、鐵律、EMERGENCY_EXIT、REBALANCE），後面接 32 個 snake_case 參數（`r2_bias_limit`、`s3_unrealized_pct`…），沒有分組、沒有白話摘要。
- 同一段「系統預設規則集，尚無你本人的設定」的文字在頁首與頁內各出現一次。
- 確認規則集後，「今日指令帳冊：無。」與「部位快照：無。」，而我在庫存有 3 檔持倉。排程台自成一套帳，與庫存不通，使用者看不出為什麼。
- 顯示 `加權指數資料狀態為 unavailable（來源 none）`、`^TWII` 之類英文狀態。
- 「全部出清」按鈕常駐在頁首，但有 3 步確認流程（`playbook/EmergencyExitControl.tsx:15`），這點設計得好。
- 手機沒有水平捲動。

### 5. 回測 `/backtest`
桌面表單：`$S/05-backtest-desktop.png`；結果：`$S/35-backtest-2330-result.png`（5488px 高）；手機：`$S/05-backtest-mobile.png`、`$S/36-backtest-result-mobile.png`。
- 表單乾淨。但開始與結束日期是空白必填，沒有預設值，不填按執行只會跳英文瀏覽器提示。我自己第一次就漏填，見 `$S/35-backtest-2330-result.png` 的前一版執行失敗。
- 結果頁極度詳盡：樣本內外分列、對照 Buy & Hold、獲利因子與盈虧比的說明。
- 但對第一次使用者過量，且內文有 `verified_on 為 null`、`uv run python -m app.dividends.sync` 這類開發者語言。
- 數據誠實度高：報告頂端用警告框標明「本次使用的是離線示範資料（demo_synthetic）」。

### 6. 設定 `/settings`
桌面（整頁 3299px 高）：`$S/06-settings-desktop.png`；手機（5049px 高）：`$S/06-settings-mobile.png`；風險上限放寬警告：`$S/30-settings-invalid-0.9-at-save-button.png`、`$S/31-settings-widen-warning-at-button.png`；儲存成功：`$S/32-settings-saved-at-button.png`。
- 這一頁塞了：帳戶總淨值、風險預算、費率、警示排程、Kelly 輸入、資料來源、證券目錄、警示規則，8 個區塊。
- 風險預算以小數輸入（0.15 代表 15%），說明文字寫「與後端 `app/advice/limits.py` 的 RiskBudget 欄位一一對應」，這是開發者視角。
- 輸入 0.9 超過硬上限後，「你正在放寬風控上限」的警告與「儲存設定」按鈕在整個表單最底（離輸入欄約 1500px），輸入欄旁沒有任何即時回饋。使用者按下儲存、什麼都沒看到，要自己往下捲才知道。
- 「證券目錄尚未同步」顯示正確，指令 `uv run python -m app.directory.sync` 也貼在頁面上，但這是給開發者的操作。
- 警示規則表單的空欄位也是英文原生提示。

---

## 三、最重要的 5 個問題（依嚴重度）

1. **總覽頁不回答核心問題，答案藏在各檔個股頁內。**
   - 證據：`$S/01-home-desktop.png` 的持倉表沒有建議欄。要看「續抱參考／減碼參考」得逐檔點進去（`$S/03-position-2330-desktop.png`）。持 3 檔就要 3 次導航。
   - 影響：核心任務變成「首頁 → 點 2330 → 讀首屏 → 返回 → 點 0050 …」。

2. **畫面混用內部開發字眼，一般使用者看不懂。**
   - 證據：首頁警示卡的 `violated_limit_ids: single_position_weight`、`cached_stale 層`、`lt -0.2`（`$S/01-home-desktop.png`）。排程台的 32 個 snake_case 參數與 `unavailable（來源 none）`（`$S/04-playbook-desktop.png`）。回測的 `verified_on 為 null`（`$S/35-backtest-2330-result.png`）。設定頁的 `app/advice/limits.py`（`$S/06-settings-desktop.png`）。
   - 影響：這些不是文案，是 debug 字串直接洩漏到使用者介面。

3. **「股數參考」在持倉股顯示「未提供股數」，與庫存資料矛盾。**
   - 證據：`$S/03-position-2330-desktop.png` 與 `$S/41-position-mobile-firstscreen.png`：2330 顯示「未提供股數」，庫存卻有 1,000 股（`$S/02-positions-desktop.png`）。00631L 卻顯示「1,256 ~ 3,000 股」（`$S/16-position-00631L-top.png`）。
   - 影響：使用者會質疑系統有沒有讀到他的持倉。原因我沒有追原始碼確認，只能說現象存在。

4. **首次載入個股頁時結果與重新整理後不同。**
   - 證據：第一次載入 2330（`$S/03-position-2330-desktop.png`）顯示「均線資料不足，未繪製 MA5/20/60 疊圖」與「6 條中成立 3 條，其中 2 條無法判定」。同一頁再次載入（`$S/14-position-2330-load1-top.png`）已有三條均線，條件變成「6 條中成立 5 條」。
   - 我用腳本重複載入兩次，兩次都是 5 條，沒有再重現第一次的狀態。
   - 可能與首次呼叫時的快取暖機有關，但我沒有查證根因。
   - 影響：同一天同一檔標的，第一次與第二次看到的結論不同，會傷害信任。

5. **排程台與庫存是兩套互不相通的帳，使用者看不出為什麼。**
   - 證據：`$S/70-playbook-after-confirm.png`：確認規則集後「部位快照：無。」，但庫存有 3 檔（`$S/02-positions-desktop.png`）。
   - 影響：使用者有持倉，排程台卻說沒有部位。頁面上沒有任何一句話說明這是獨立帳冊。排程台首屏也不說「這頁是用來做什麼」。

---

## 四、5 個具體改善建議

| # | 建議 | 投入 | 效益 |
|---|---|---|---|
| 1 | 首頁持倉表加一欄「建議」（續抱／減碼／加碼參考徽章）與「佔比」，點一下直接進個股頁。 | 中 | 高：核心任務從 3 次導航降到 0 次，3 秒內看到「我該怎麼辦」。 |
| 2 | 做一輪「使用者字串清理」：警示訊息用白話模板取代 `field/value/op` 原始欄位；`cached_stale`、`unavailable`、`verified_on` 全部改成人話；設定頁拿掉 `app/advice/limits.py` 這類路徑；排程台參數表預設摺疊。 | 中 | 高：直接解決簡易清楚的最大扣分項。這些屬於面向使用者的文案，需走 risk-compliance-officer 審查。 |
| 3 | 設定頁的放寬警告與儲存回饋搬到輸入欄旁（或做 sticky 儲存列）；風險上限改用「%」輸入。 | 小～中 | 中高：避免「按了沒反應」。 |
| 4 | 新增持倉表單：輸入代號後自動帶出市場與幣別，或給預設值（台股／TWD／股票）；必填欄位用繁中提示取代瀏覽器英文訊息；回測日期給預設值（例如近一年）。 | 小 | 中高：新增持倉步驟與出錯率明顯下降。 |
| 5 | 排程台首屏加一句白話「這頁在做什麼、與庫存的關係」，把規則條文與參數收進摺疊區；同時查「未提供股數」與首次載入結果不一致（問題 3、4）。 | 中 | 中：降低首次進入的恐懼感，也修掉影響信任的前後不一致。 |

---

## 五、ui-delivery-checklist 逐項核對（只列有證據的）

通過項：
- 3.1 全區間無橫向捲動：1280、390、320 寬下，6 個頁面的 `scrollWidth == clientWidth`，全部通過。
- 5.1 / 5.2 禁止捏造數據：缺資料處皆為「—」或「資料不足」，示範資料明確標 demo_synthetic。

違反或存疑：
- **2.1 / 2.5 input 狀態完整性**：必填驗證使用瀏覽器原生英文提示（`$S/21-add-empty-submit.png`、`$S/30-settings-invalid-0.9-at-save-button.png`），不是自訂的繁中 error 狀態。
- **2.4 同表單同高**：回測表單日期欄比其他欄略高，我只做目測，沒有量測。
- **6.2 token／spacing**：我沒有逐項量測，未驗證。
- **第 0 節 風控地板**：每頁底部都有常駐的「本工具為研究與教育用途，非投資建議」，字級小、對比偏低，這符合已定稿。我沒有查視覺規範有無白名單，不下結論。
- 1.1 對比：未做逐元素量測。肉眼看，灰色說明文字在深色背景上偏淡，例如設定頁欄位下方的說明、回測表單 label。需 qa 量測確認，我不下結論。

---

## 六、啟動難度紀錄

| 步驟 | 內容 | 耗時 |
|---|---|---|
| 1 | 讀 README 與 e2e-fallback | 約 2 分鐘 |
| 2 | `uv run python -m app.demo.seed`（STOCK_DESK_DB_PATH 指向 scratchpad） | 0.6 秒（uv 環境已就緒） |
| 3 | 後端 `uv run uvicorn app.main:app --port 8000` | 約 5 秒內 `/health` 回 200 |
| 4 | `npm install --no-save` | 25 秒 |
| 5 | `npm run dev` | 約 6～9 秒，首次 `/` 編譯 749ms |
| 6 | `POST /api/alerts/evaluate`（需 `X-Stock-Desk-Client` header），才會有警示事件 | 即時 |

- 從零到看到畫面：5 個指令、約 1 分鐘（不含讀文件）。
- 環境與路徑障礙：
  - README 的 Docker 路徑我沒有用。
  - 「離線示範」要先讀 README 後段才找到，快速啟動區沒有提。
  - 警示事件需另外 POST（README 有寫）。
  - 證券目錄尚未同步導致公司名稱搜尋不能用（`$S/18-search-company-name.png`），只能輸入代號。
- 沒有卡住的地方，但以第一次使用者來說，README 沒有「5 分鐘上手」的單一路徑，要在 Docker、本機開發、離線示範之間自己拼。
- 版本落差：`frontend/package.json` 寫 next 16.3.3，README 版本表寫 next 16.2.11，兩者不一致；不影響啟動。

---

## 七、截圖清單（全部位於 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/ux/`）

標準頁面（桌面 1280、手機 390）：
- `01-home-desktop.png`、`01-home-mobile.png`
- `02-positions-desktop.png`、`02-positions-mobile.png`
- `03-position-2330-desktop.png`、`03-position-2330-mobile.png`
- `04-playbook-desktop.png`、`04-playbook-mobile.png`
- `05-backtest-desktop.png`、`05-backtest-mobile.png`
- `06-settings-desktop.png`、`06-settings-mobile.png`

操作流程：
- `10-home-expanded.png`、`60-home-row-expanded-top.png`、`61-home-row-expanded-2.png`（首頁展開）
- `11-position-2330-expanded.png`、`12-position-00631L-expanded.png`、`13-position-unknown-9999.png`
- `14-position-2330-load0-top.png`、`14-position-2330-load1-top.png`（重複載入比對）
- `15-advice-card.png`、`15b-advice-card-2.png`（建議卡）
- `16-position-00631L-top.png`
- `18-search-company-name.png`（公司名搜尋，目錄未同步）
- `20-positions-add-and-csv-open.png`、`21-add-empty-submit.png`、`22-add-2454-submitted.png`、`23-home-after-add-2454.png`、`24-edit-modal.png`（新增與匯入持倉）
- `30-settings-invalid-0.9-at-save-button.png`、`31-settings-widen-warning-at-button.png`、`32-settings-saved-at-button.png`（改風險設定）
- `34-home-after-ack-one.png`（警示處理）
- `35-backtest-2330-result.png`、`36-backtest-result-mobile.png`（回測結果）
- `40-home-mobile-firstscreen.png`、`41-position-mobile-firstscreen.png`、`42-position-mobile-chart-area.png`、`43-playbook-mobile-firstscreen.png`、`44-settings-mobile-firstscreen.png`
- `50-home-backend-unreachable.png`、`51-position-backend-unreachable.png`（後端未連線狀態）
- `70-playbook-after-confirm.png`

「沒有資料」狀態（`--reset` 後）：
- `80-empty-home-desktop.png`、`80-empty-home-mobile.png`
- `81-empty-positions-desktop.png`、`81-empty-positions-mobile.png`
- `82-empty-position-2330-desktop.png`、`82-empty-position-2330-mobile.png`
- `83-empty-playbook-desktop.png`、`83-empty-playbook-mobile.png`
- `84-empty-settings-desktop.png`、`84-empty-settings-mobile.png`
- 空狀態觀察：首頁與庫存各有「尚無持倉」加「新增持倉」引導，這是好的。但總覽的「所有部位皆無法估值，總計無法計算。」在根本沒有部位時是誤導。數字卡顯示「NT$0」而非「—」，也容易被誤讀為真實的零。
- 後端未連線時只寫「請確認服務是否已啟動」，沒有告訴使用者怎麼啟動，且畫面為空白版面。

文字擷取（逐字原文，供查證）：
- `01-home-desktop.txt`、`11-position-expanded.txt`、`12-position-00631L.txt`、`13-unknown.txt`、`35-backtest.txt`、`70-playbook.txt`、`80-empty-home.txt`

腳本與 log：
- `shoot.js`、`flow1.js` 到 `flow10.js`
- `backend.log`、`frontend.log`、`npm-install.log`
- `demo.db`（已 reset）

---

## 八、我看不懂或沒查證的地方

- 「六項觀察條件」每個圓點的語意，必須展開才知道，我沒有完整讀懂各門檻的設計用意。
- 排程台 R／S／P／M 規則的業務邏輯：我只從使用者角度評論它沒有白話摘要，沒有評斷規則本身合不合理。
- 風險儀表第 1 條「40.92%／15.00%」與警示卡「2330 佔總資產 35.79%」數字不同，我推測是前者取全持倉最大值（0050）、後者針對 2330，但沒有逐行核對原始碼。
- 問題 4 的根因我沒有查證。
- 對比（1.1）與 token 使用（6.1）沒有做自動化量測，需 qa-reviewer 或 qa-e2e 補。
