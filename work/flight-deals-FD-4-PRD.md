# PRD：flight-deals FD-4 通知與維運體驗

- 版本：v0.1（spec）
- 發起人：CEO（總經理定調）
- 撰寫：product-manager
- 任務單：`work/tasks/FD-4.md`
- 相關文件：`work/flight-deals-PRD.md`（FD-1，FR-C、FR-E）、`work/flight-deals-FD-3-PRD.md`、`docs/adr/0002-flight-deals-技術棧與資料源.md`（D-4、D-5、C-17、第 350 行「不設登入自動啟動」）、`apps/flight-deals/README.md`
- 產品分支：`product/flight-deals`

## 背景與目標

FD-1 到 FD-3 完成後，系統只在「價格符合條件」時才推播。CEO 的痛點是：沒收到通知時，分不清是真的沒有低價、資料源壞了，還是電腦根本沒開服務。另外 Telegram 的 chat id 取得流程需要手動開瀏覽器查 JSON，服務也得每次自己啟動。FD-4 補齊四件事：

1. 每日摘要推播：每天固定時間推一則「現況」，讓「沒消息」可以被判讀。
2. Telegram 設定精靈：用 CLI 引導取得 chat id 並測試，降低首次設定門檻。
3. Windows 登入自動啟動：降低「機器開著但服務沒跑」的漏掃風險。
4. 列表頁趨勢：在監看列表直接看到最低價較前一輪的漲跌。

成功指標（可驗證行為）：
- 設定好 Telegram 的情況下，每天在設定時間收到恰好一則摘要，內容與網頁數據一致。
- 沒有 Telegram 設定的新使用者可以只靠 `flight-deals telegram-setup` 取得可貼上的設定行並完成測試發送。
- 執行 install-autostart 後登出再登入，服務自動在背景啟動，健康頁顯示「自動啟動：已安裝」。
- 列表頁每個有資料的監看都看得到漲跌箭頭與金額。

產品前提（沿用，須貫穿文案）：
- 價格是查到當下的參考值，實際以訂票網站為準。
- 文案只做事實陳述，不得出現建議語氣（沿用 `BANNED_PHRASES` 禁用字規則，C-17）。
- 服務仍只綁 127.0.0.1，無登入。

## 使用者與情境

- 使用者：CEO 本人，單一使用者，Windows 本機。
- 情境 A：每天早上 08:00 手機收到摘要，一眼看到各監看目前最低價與漲跌、資料源是否正常、昨天有沒有查價失敗。沒收到價格警示時，摘要告訴他「是沒低價，還是系統壞了」。
- 情境 B：第一次設定（或換 bot）時，執行 `flight-deals telegram-setup`，照提示對 bot 傳一則訊息，拿到 chat id 並貼進 `.env`。
- 情境 C：電腦重開機登入後，不必記得雙擊 dev-up.bat，服務自己在背景跑。
- 情境 D：打開監看列表，掃一眼就知道哪個監看變便宜、哪個變貴。

## 範圍內 / 範圍外

範圍內：
- 每日摘要的內容、排程時間設定、開關、去重、通知紀錄顯示。
- `flight-deals telegram-setup` CLI 子指令。
- `install-autostart.bat`、`uninstall-autostart.bat`、README 說明、健康頁自動啟動狀態。
- 監看列表頁漲跌趨勢顯示。

範圍外（non-goals）：
- Travelpayouts 備援、多使用者、LINE、價格預測、自動購票、行動版 app（總經理指定）。
- 自動把 token 或 chat id 寫入 `.env`。
- 詳情頁趨勢圖重做（已有，不動）。
- 摘要的「建議」「推薦」類內容（例如建議是否出手），一律不做。
- 每日摘要以外的定期報表（週報、月報）。
- 非 Windows 平台的自動啟動。
- 從網頁安裝或移除自動啟動（僅顯示狀態，安裝與移除走 .bat）。
- 對外暴露服務或遠端存取。

## 功能需求（逐條編號）

### 一、每日摘要（FR-DG）

- FR-DG1 摘要排程：每天在設定的時間（預設 08:00，時區 Asia/Taipei）推送一則 Telegram 摘要。
- FR-DG2 設定項：設定頁新增「每日摘要」開關（預設開啟）與推送時間（HH:MM，24 小時制，預設 08:00）。修改後下一次排程起生效；不合法的時間被拒絕並顯示錯誤。
- FR-DG3 摘要內容（每個啟用中監看一行）：路線（中文短名＋代碼）｜目前已查到最低價（含出發／回程日期組合）｜較前一日的漲跌（金額與百分比）。無前一日資料或目前無價格時，漲跌顯示「—」。
- FR-DG4 漲跌定義：以該監看「目前最低價」對「前一個 Asia/Taipei 日曆日結束時點的最低價」比較；金額為差額（TWD），百分比相對前一日最低價，取至小數 1 位；漲用「+」、跌用「-」，持平顯示「持平」。只比較目前設定版本（revision）與同一 `price_kind` 的資料，不跨即時價與快取價。
- FR-DG5 整體狀態區塊（每則摘要一次）：資料源狀態（正常／異常／斷路器開啟）、上次掃描時間（Asia/Taipei）、過去 24 小時查價失敗次數。
- FR-DG6 失敗次數定義：過去 24 小時內，判為 `error` 或 `blocked` 的查價次數；`no_data` 不算失敗（與 FD-3 一致）。
- FR-DG7 固定結尾：每則摘要結尾須有兩句固定文字：價格免責句（「價格為查到當下的參考值，實際以航空公司或訂票網站為準」）與「沒有收到價格通知不代表沒有低價」。
- FR-DG8 無啟用中監看：仍推送短訊「目前沒有啟用中的監看」，並帶資料源狀態與結尾固定句（上次掃描時間無資料則顯示「—」）。已停用、已過期的監看不列入。
- FR-DG9 單日去重：同一個 Asia/Taipei 日曆日最多推送一則摘要，不論重啟服務幾次或修改設定幾次。
- FR-DG10 Telegram 未設定：不推送、不產生 `failed` 紀錄，沿用既有 `suppressed` 行為（未設定期間的摘要日後不補發）。
- FR-DG11 開關關閉：關閉後不產生任何摘要（含 `suppressed` 紀錄也不產生）。
- FR-DG12 推送失敗：沿用既有通知重試機制（有限次數、不標記為已通知）；失敗須記錄原因（已遮蔽）。
- FR-DG13 錯過時間的補發：服務在摘要時間當下沒在執行，當天稍後啟動時，若當天尚未推送且已過設定時間，補發一次（仍受單日去重）。預設值，見開放問題 1。
- FR-DG14 通知紀錄：通知紀錄頁須顯示類型「每日摘要」，並可看到時間、成功／失敗／未送出與摘要全文。
- FR-DG15 文案與長度：只做事實陳述，不含禁用字；啟用中監看很多時，單則訊息長度不得超過 Telegram 上限（超出的處理由架構決定，須在訊息中標明「另有 N 個監看未列出」，不得靜默截斷）。
- FR-DG16 文案審查：摘要文案模板定稿後交 risk-compliance-officer 看一次（C-17），預期判定「不適用」。

### 二、Telegram 設定精靈（FR-SW）

- FR-SW1 指令：新增 CLI 子指令 `flight-deals telegram-setup`；不帶參數時不影響既有 `flight-deals` 啟動行為。
- FR-SW2 讀取 token：從環境變數或 `.env`（與服務同一套讀取規則）讀取 bot token。若無，印出 BotFather 建立步驟（@BotFather、`/newbot`、取得 token、寫入 `FLIGHT_DEALS_TELEGRAM_BOT_TOKEN`）後以非零代碼結束。
- FR-SW3 引導：有 token 時，提示使用者先對該 bot 傳一則任意訊息，然後開始輪詢 `getUpdates`，最長 60 秒。
- FR-SW4 取得 chat id：輪詢期間收到訊息即取得 chat id，印出並提示可直接貼上的一行：`FLIGHT_DEALS_TELEGRAM_CHAT_ID=<id>`。偵測到多個不同 chat 時，須列出供選擇（預設選最新一筆），群組負數 id 須能正確處理。
- FR-SW5 逾時：60 秒內未取得任何訊息，印出明確說明（未收到訊息、請確認已對正確的 bot 傳訊）並以非零代碼結束，不卡住、不無限等待。
- FR-SW6 測試發送：取得 chat id 後詢問是否發送測試訊息（預設否，需明確確認）；選擇發送時以該 chat id 發一則測試訊息，並回報成功或失敗原因。
- FR-SW7 不寫入：精靈不自動寫入或修改 `.env` 或任何檔案；印出的設定行由使用者自行貼上。
- FR-SW8 祕密保護：bot token 不得出現在任何輸出（stdout、stderr、錯誤訊息、例外追蹤、log）；API 錯誤須先遮蔽（沿用 D-5 的 `redact()`）。
- FR-SW9 錯誤處理：token 無效、網路不通、bot 設有 webhook 導致無法 `getUpdates` 等情況，須以人話說明原因與處理方式，不印出含 token 的 URL。
- FR-SW10 獨立性：精靈不啟動網頁服務與排程，也不取排程鎖，因此服務執行中也能使用。

### 三、Windows 登入自動啟動（FR-AS）

- FR-AS1 安裝：`apps/flight-deals/install-autostart.bat` 以 Windows 登入自動啟動機制建立「使用者登入時」觸發的工作，以目前使用者身分執行，視窗隱藏，啟動 flight-deals 服務（固定 port 8795，與 dev-up.bat 一致）。
- FR-AS2 重複安裝：已存在同名工作時，重新執行 install 須覆寫或明確告知已存在，不得產生重複工作。
- FR-AS3 移除：`apps/flight-deals/uninstall-autostart.bat` 移除該工作；工作不存在時給出友善說明且不視為錯誤。
- FR-AS4 前置檢查：安裝時檢查 uv 是否存在；缺少時說明並結束。安裝與移除結果須明確印出成功或失敗與原因。
- FR-AS5 不提權原則：預設不要求系統管理員權限、不使用 SYSTEM 帳號；若環境限制必須提權，須印出清楚說明。
- FR-AS6 安全：服務仍只綁 127.0.0.1；工作定義不得內含任何祕密（token、chat id 仍只來自 `.env`）。
- FR-AS7 與其他啟動方式共存：自動啟動的服務與 dev-up.bat 或手動啟動同時存在時，依 FD-3 單一排程鎖，後啟動者拒絕執行並說明原因，不產生雙重排程。
- FR-AS8 健康頁顯示：健康頁新增「自動啟動：已安裝／未安裝」；能偵測就顯示，無法偵測（權限或環境限制）時整列不顯示，不得顯示成「未安裝」誤導。
- FR-AS9 README：說明安裝／移除步驟、運作方式、如何確認、如何停止目前跑著的服務，以及「機器沒開仍不會掃描」的限制。

### 四、列表頁趨勢（FR-TR）

- FR-TR1 顯示位置：監看列表在「已查到最低價」欄旁顯示較前一輪掃描的漲跌。
- FR-TR2 顯示格式：下跌「↓ 金額」、上漲「↑ 金額」、持平「＝」（或等效），金額為 TWD 差額；不依賴顏色單獨傳達（須有箭頭與文字）。
- FR-TR3 比較基準：目前最低價對「前一輪成功掃描結束時的最低價」；只比較目前 revision 與同一 `price_kind`。
- FR-TR4 無基準：無前一輪、前一輪無價格、或目前無價格時顯示「—」。
- FR-TR5 語氣：只做事實陳述，不使用「划算」「快買」之類字眼。
- FR-TR6 範圍：只改列表頁，詳情頁既有趨勢圖不動。

## 驗收條件（每條需求至少一組 Given/When/Then）

### 一、每日摘要

- AC-DG1 Given Telegram 已設定、摘要開啟、時間 08:00、有 2 個啟用中監看；When Asia/Taipei 時間到 08:00；Then Telegram 收到恰好 1 則摘要，且通知紀錄新增 1 筆類型「每日摘要」狀態成功。
- AC-DG2 Given 當天 08:00 已推過摘要；When 同一天內再次經過排程時間、或重啟服務、或修改摘要時間為更晚；Then 當天不再推第二則。When 隔天 08:00；Then 再推 1 則。
- AC-DG3 Given 設定頁；When 將時間改為 09:30 並儲存；Then 之後在 09:30（而非 08:00）推送；When 輸入「25:00」「9:3x」或空白；Then 被拒絕並顯示錯誤，原設定不變。
- AC-DG4 Given 摘要開關關閉；When 到達設定時間；Then 不推送、通知紀錄無新增任何摘要（含 `suppressed`）。When 重新開啟且當天尚未推過且已過時間；Then 依 FR-DG13 補發一次。
- AC-DG5 Given Telegram 未設定、摘要開啟；When 到達設定時間；Then 不對外發送，通知紀錄為「未送出（未設定）」的 `suppressed`，沒有 `failed` 紀錄，也不產生重試。
- AC-DG6 Given 沒有任何啟用中監看（全部停用、過期，或根本沒有）；When 到達設定時間；Then 推送短訊含「目前沒有啟用中的監看」、資料源狀態、兩句固定結尾，且不列任何路線行。
- AC-DG7 Given 監看 A 前一日（Asia/Taipei）結束時最低價 10,000、目前最低價 9,400；When 產生摘要；Then A 的漲跌顯示「-600（-6.0%）」，並含最低價日期組合。
- AC-DG8 Given 監看 B 前一日結束時最低價 9,000、目前 9,450；When 產生摘要；Then 顯示「+450（+5.0%）」。Given 價格相同；Then 顯示「持平」。
- AC-DG9 Given 監看 C 是今天才建立（前一日無資料）或目前尚未查到價格；When 產生摘要；Then 漲跌欄顯示「—」，目前無價格時最低價欄顯示「尚未查到價格」，不得出現 0 元。
- AC-DG10 Given 資料源狀態分別為正常、異常、斷路器開啟；When 產生摘要；Then 摘要的資料源狀態與健康頁一致，並顯示上次掃描時間（Asia/Taipei）。
- AC-DG11 Given 過去 24 小時有 3 次 `error`、2 次 `blocked`、4 次 `no_data`；When 產生摘要；Then 查價失敗次數顯示 5。
- AC-DG12 Given 任一摘要；When 檢視全文；Then 結尾含價格免責句與「沒有收到價格通知不代表沒有低價」，且全文不含 `BANNED_PHRASES` 任一禁用字（有測試）。
- AC-DG13 Given Telegram 暫時無法連線；When 到達設定時間；Then 失敗被記錄（原因已遮蔽）、當日未標記為已送出，並依重試機制補送，超過重試上限後停止；補送成功後當天不再重複。
- AC-DG14 Given 服務在 08:00 沒執行、當天 10:00 啟動、當天尚未推過；When 啟動完成；Then 補發 1 則；Given 當天已推過；Then 不補發。
- AC-DG15 Given 開啟通知紀錄頁；When 檢視；Then 每日摘要類型顯示為「每日摘要」，可看到時間、狀態與全文，且與價格通知、告警、測試類型可區分。
- AC-DG16 Given 30 個啟用中監看；When 產生摘要；Then 訊息不超過 Telegram 長度上限，且若有未列出者，訊息載明「另有 N 個監看未列出」。
- AC-DG17 Given 摘要文案模板定稿；When 交 risk-compliance-officer；Then 取得判定結果並記錄於任務單。

### 二、設定精靈

- AC-SW1 Given 未設定 bot token；When 執行 `flight-deals telegram-setup`；Then 印出 BotFather 建立步驟與要寫入的變數名稱，以非零代碼結束，不發出任何網路請求。
- AC-SW2 Given 已設定有效 token；When 執行指令並在 60 秒內對 bot 傳一則訊息；Then 印出 chat id 與一行 `FLIGHT_DEALS_TELEGRAM_CHAT_ID=<id>`，並詢問是否發送測試訊息。
- AC-SW3 Given 已找到 chat id；When 回答確認發送；Then 該 chat 收到測試訊息，終端顯示成功；When 回答否或直接 Enter；Then 不發送並正常結束。
- AC-SW4 Given 測試發送失敗（例如 chat id 不可用）；Then 終端顯示失敗原因，不含 token，並以非零代碼結束。
- AC-SW5 Given 已設定 token 但 60 秒內沒有任何新訊息；When 逾時；Then 印出明確的逾時說明與排查建議，以非零代碼結束，總等待時間不超過約 60 秒。
- AC-SW6 Given 輪詢期間來自兩個不同 chat 的訊息；Then 列出兩者供選擇，預設最新一筆；Given 群組 chat（負數 id）；Then 正確印出負數 id。
- AC-SW7 Given 以假 token（例如 `123456:FAKE-TOKEN`）執行，並觸發無效 token、網路失敗、webhook 衝突三種情境；When 檢查 stdout、stderr、例外追蹤與 log；Then 皆不含 token 原文，也不含 `bot<digits>:` 型態的 URL（有自動化測試）。
- AC-SW8 Given 執行精靈前後；When 比對 `.env` 與專案檔案；Then 內容不變。
- AC-SW9 Given 服務正在執行；When 同時執行精靈；Then 精靈正常運作，不因排程鎖而失敗，也不影響服務。
- AC-SW10 Given 全部測試；Then 不連外網（以假的 Telegram 回應測試），真實連線只在 opt-in 的手動驗收進行。

### 三、自動啟動

- AC-AS1 Given 未安裝；When 執行 `install-autostart.bat`；Then 登入自動啟動機制出現「登入時」觸發、目前使用者身分、不顯示視窗的工作，並印出成功訊息。
- AC-AS2 Given 已安裝；When 再次執行 install；Then 不產生第二個工作，並說明已存在或已覆寫。
- AC-AS3 Given 已安裝並登出再登入；When 登入完成；Then 服務在背景啟動（無可見主控台視窗），`http://127.0.0.1:8795` 可連線，且仍只綁 127.0.0.1。
- AC-AS4 Given 自動啟動的服務已在執行；When 再雙擊 dev-up.bat 或手動啟動第二份；Then 第二份依 FD-3 鎖機制拒絕並說明原因，不雙重排程。
- AC-AS5 Given 已安裝；When 開啟健康頁；Then 顯示「自動啟動：已安裝」。When 執行 `uninstall-autostart.bat` 後重新整理健康頁；Then 顯示「自動啟動：未安裝」，且登入自動啟動機制中已無該工作。
- AC-AS6 Given 工作不存在；When 執行 uninstall；Then 印出「尚未安裝」類說明，且不視為失敗。
- AC-AS7 Given 無法偵測自動啟動狀態（例如查詢指令失敗或被權限擋）；When 開啟健康頁；Then 不顯示該列，其餘頁面正常，不出現錯誤或誤導的「未安裝」。
- AC-AS8 Given 系統找不到 uv；When 執行 install；Then 印出缺少 uv 的說明並結束，不建立半成品工作。
- AC-AS9 Given 檢視工作定義與 .bat 內容；Then 不含 token、chat id 或其他祕密。
- AC-AS10 Given README；Then 載明安裝、移除、確認、停止服務步驟與「機器沒開不掃描」限制。

### 四、列表趨勢

- AC-TR1 Given 監看前一輪掃描結束時最低價 10,000、目前最低價 9,400；When 開啟列表；Then 該列在最低價旁顯示「↓ 600」。
- AC-TR2 Given 前一輪 9,000、目前 9,450；Then 顯示「↑ 450」。Given 兩者相同；Then 顯示「＝」或等效持平標示。
- AC-TR3 Given 只有一輪掃描、前一輪沒有價格、或目前尚無價格；Then 顯示「—」，目前無價格者仍顯示「尚未查價」，列表無錯誤。
- AC-TR4 Given 監看修改路線或日期（revision 變動）後第一輪；Then 不拿舊 revision 的價格當基準，顯示「—」。
- AC-TR5 Given 任一列的趨勢文字；Then 以箭頭與文字呈現（不只靠顏色），且不含建議語氣禁用字。
- AC-TR6 Given 詳情頁；When 開啟；Then 既有趨勢圖行為不變。

## 風險與依賴

- ADR 衝突（需 tech-architect 處理）：ADR-0002 第 350 行載明「不設登入自動啟動」，此為預設而非禁令，CEO 現已要求，須由 tech-architect 於 ADR 增補（FD-4 小節）並說明鎖機制共存。另 `notification.kind` 現有 CHECK 只含 `price_alert`、`ops_source_failure`、`test`，新增「每日摘要」類型可能需要 migration；ADR 第 346 行 FD-2 之約束「不新增 migration」僅限 FD-2，FD-4 不受限，但仍須評估。
- 摘要日期邊界：「前一日結束時點最低價」需能由既有觀測紀錄重建；若資料模型無法重建，須退回 product-manager 重議基準定義。
- 取樣偏差：彈性窗監看每輪輪換取樣日期，「目前最低價」的漲跌可能反映取樣範圍不同而非真實價格變動。摘要與列表須維持事實陳述，必要時加一句「依已取樣日期計算」（文案由架構與 UX 決定）。列表趨勢同理。
- 祕密外洩風險：`getUpdates` 的 URL 含 bot token；精靈的所有錯誤路徑都是外洩高風險點（stock-desk 前例）。須有自動化測試。另 FD-1 待辦提到「`chat_id` 是否仍登記為遮蔽祕密」，精靈會印出 chat id，須由 tech-architect 確認遮蔽規則不會誤傷精靈輸出（chat id 是使用者要貼上的值）。
- 排程可靠度：自動啟動只解決「登入後沒啟動服務」；睡眠、關機、未登入期間仍不掃描也不推摘要。摘要補發（FR-DG13）只補當天。
- 登入自動啟動機制環境差異：不同 Windows 設定可能要求提權、或登入時網路尚未就緒；架構與 devops-sre 需評估延遲啟動或重試。
- 摘要與重複告警的關係：摘要中的資料源狀態與既有「異常告警」並存，不互相取代、不互相去重。
- 風控閘門判定：摘要與列表趨勢為事實陳述，原則上不適用 §0-5；仍依 C-17 交 risk-compliance-officer 確認摘要模板（AC-DG17）。
- UI 驗收：涉及網頁介面（列表趨勢、設定頁、健康頁），完成前須 qa-e2e 實機驗收；無人值守環境起不了 dev server 時依 e2e-fallback。自動啟動的登出再登入屬需人工實機驗證，列為 CEO 或總經理手動驗收項。
- 真實 Telegram 送達驗收（AC-DG1、AC-SW3）需 CEO 已設定 bot，沿用 FD-1 待辦。

## 開放問題（待 CEO 或其他部門回答）

預設值已標示；未覆議則照預設進行。

1. 【總經理，預設：補發】摘要時間當下服務沒在跑，當天稍後啟動是否補發？預設：補發一次（FR-DG13）。若不要補發，需改 AC-DG14。
2. 【tech-architect】「前一日結束時點最低價」與「前一輪掃描結束時最低價」如何由現有觀測資料重建（FR-DG4、FR-TR3）；是否需要新增欄位或 migration；彈性窗輪換取樣造成的偏差是否在文案加註。
3. 【tech-architect】新增通知類型「每日摘要」的資料模型（`notification.kind` 擴充、dedupe key 以 Asia/Taipei 日期、是否需要 migration），以及摘要時間與開關存於 `app_setting`。
4. 【tech-architect】摘要排程的實作方式（與既有單一 worker 排程共存、時間修改後生效時機、補發判定）。
5. 【tech-architect】訊息超過 Telegram 長度上限時的處理（預設：依價格或路線排序，列出前 N 個並標明「另有 N 個監看未列出」）。
6. 【tech-architect】`chat_id` 是否登記為遮蔽祕密，及對精靈輸出的影響（FR-SW8、風險段）。
7. 【tech-architect】ADR-0002 第 350 行「不設登入自動啟動」須補 FD-4 增補說明；是否需要 ADR（預設：增補小節即可，不另開）。
8. 【devops-sre】自動啟動的實作與環境限制：是否必須提權、隱藏視窗做法、登入時網路未就緒的處理、健康頁偵測方式（FR-AS5、AS8）。預設：不提權，能偵測才顯示。
9. 【devops-sre】工作名稱與重複安裝處理（預設：固定工作名，重複安裝時覆寫並告知）。
10. 【總經理，預設：選最新】精靈偵測到多個 chat 時預設選最新一筆（FR-SW4）。
11. 【總經理，預設：不寫 DB】精靈的測試訊息不寫入通知紀錄（CLI 不開資料庫、不取鎖），與網頁「測試發送」不同。
12. 【總經理，預設：只列目前最低價一組】摘要每個監看只列一組最低價日期組合，不列前 N 筆。
13. 【risk-compliance-officer】摘要文案模板審查（預期「不適用」）。
14. 【qa-e2e】登出再登入的自動啟動實機驗收，以及設定頁、健康頁、列表的 UI 驗收，無人值守環境降級路徑見 e2e-fallback。

## 變更紀錄

- 2026-10-26 v0.1 初稿，由 product-manager 依總經理定調建立。

- 2026-10-26 v0.2 總經理依 tech-architect 裁決修訂：自動啟動不綁定 schtasks，改為「登入自動啟動（不需系統管理員權限）」；列表最低價與漲跌改以排除已出發日期的快照計算（行為變更）。
