# manjong-unity 用戶端（Unity 6.3 LTS，WebGL 優先）

台灣 16 張麻將「可愛麻將」的 Unity 用戶端：1 位玩家對 3 個 AI。
規則、洗牌、AI、聽牌與台數計算、結算全部在後端（`apps/manjong-unity/server`），用戶端只負責畫面與送出「選了哪個合法動作」。

- **連線方式（契約 v0.2）**：帳號與排行榜走 HTTP；**牌局全部走 WebSocket**（`/ws`），沒有任何 `/api/games` 呼叫。

- 全部 UI 都由程式碼建立（uGUI legacy `Text` / `Image` / `Button`），**不需要手拉 scene 或 prefab**。
- 進入點：`Assets/Scripts/Core/Bootstrap.cs`（`RuntimeInitializeOnLoadMethod`，scene 載入後自動建立畫面）。
- 字型：`Assets/Resources/Fonts/huninn.ttf`（jf open 粉圓子集，授權見同資料夾 `LICENSE-jf-openhuninn.txt`）。
- 圖形：圓角牌、按鈕、面板、圓形頭像都在執行期用 `Texture2D` 產生，專案裡沒有任何圖檔。
- API 契約：`work/manjong-unity/api-contract.md`（v0.2）；決策紀錄：`work/manjong-unity/adr/M002-牌局改用-WebSocket.md`。

## 1. 開啟專案

1. 安裝 Unity Hub 與 **Unity 6.3 LTS**，安裝時勾選 **WebGL Build Support** 模組。
2. Unity Hub →「Add」→「Add project from disk」→ 選這個資料夾 `apps/manjong-unity/client`。
3. 版本選 6.3 LTS 開啟。第一次開啟會產生 `Library/`、`ProjectSettings/` 與各檔案的 `.meta`（請把 `ProjectSettings/` 與 `.meta` 一併 commit）。
4. 開啟完成後，`Manjong/Setup Project` 會自動跑一次（只在 `Assets/Scenes/Main.unity` 不存在時）：
   - 建立 `Assets/Scenes/Main.unity`（預設 Camera + Light，UI 全由程式碼產生）並加入 Build Settings；
   - 設定產品名稱 `manjong-unity`、`Run In Background = true`、WebGL 壓縮格式 `Disabled`。
   - 若當下有未存檔的 scene，會先詢問是否存檔；按取消則不建立，之後可從選單 `Manjong/Setup Project` 手動執行。

### Active Input Handling（必設）

UI 使用 `StandaloneInputModule`（舊版 Input Manager）。請確認：
`Edit > Project Settings > Player > Other Settings > Active Input Handling` 設為 **Input Manager (Old)** 或 **Both**。
若設成只用 Input System Package (New)，按鈕會點不到，Console 會出現 `[Manjong] StandaloneInputModule needs the legacy Input Manager` 錯誤。
改完 Unity 會要求重啟 Editor。

## 2. 在 Editor 裡玩

1. **先啟動後端**（另開終端機）：
   ```bash
   cd apps/manjong-unity/server
   npm install
   npm run dev
   ```
   預設監聽 `http://127.0.0.1:7316`。
2. 回到 Unity，開啟 `Assets/Scenes/Main.unity`，按 **Play**。
3. 第一次會自動建立訪客帳號（token 存在 `PlayerPrefs`，key：`manjong.token`）。
   想換一個新帳號：Play 停止後，在 Unity 選單 `Edit > Clear All PlayerPrefs`。

Editor 與桌面平台預設連 `http://127.0.0.1:7316`（集中在 `Assets/Scripts/Net/ApiConfig.cs`）。
若 7316 被佔用：後端用 `PORT=<新 port> npm run dev` 啟動，並在**啟動 Unity Hub / Editor 之前**設定環境變數 `MANJONG_API_URL=http://127.0.0.1:<新 port>`（環境變數要在 Editor 啟動前設定才會生效）。

## 3. 連線方式與除錯

### 位址

| 用途 | 位址 | 來源 |
| --- | --- | --- |
| HTTP（帳號、排行榜） | `ApiConfig.BaseUrl` | Editor / 桌面：`MANJONG_API_URL` 或預設 `http://127.0.0.1:7316`；WebGL：頁面 origin（loopback 頁面可用 `?api=`） |
| WebSocket（牌局） | `ApiConfig.WebSocketUrl` | 由 BaseUrl 換算：`http→ws`、`https→wss`，再加 `/ws`。例：`ws://127.0.0.1:7316/ws` |

### WebSocket 流程（`Assets/Scripts/Net/GameConnection.cs`）

1. 按「開始遊戲」才建立連線；連上後第一則一定送 `auth`（token 放訊息裡，不放 URL），收到 `auth_ok` 才算連上，接著送 `start`。
2. 伺服器即時推送 `step`（摸牌、打牌、吃碰槓…）與 `state`（輪到你時的權威快照）。用戶端把它們排進同一個佇列依序播放：
   每步約 0.35 秒（開局 0.8 秒、胡牌 1.2 秒），佇列超過 6 步或點畫面任意處會快轉到每步約 0.08 秒；
   `state` 排到時才套用，此時若有 options 才解鎖操作。送出 `action` 後會鎖住，直到收到下一個 `state`。
3. 連上後每 25 秒送 `ping`。
4. 斷線時自動重連（0.5、1、2、4、8 秒，上限 10 秒），牌桌上方會出現「連線中斷，正在重新連線…」；重連成功會再送 `start` 取得最新 `state`。
5. close code `4401`（token 無效）：清掉 token、重新建立訪客帳號；`4000`（同帳號在別的視窗開了牌局）：回大廳並提示，**不會自動重連**，在這個視窗再按「開始遊戲」就會把連線搶回來。

實作：WebGL 用 `Assets/Plugins/WebGL/ManjongSocket.jslib` 包瀏覽器 `WebSocket`，C# 每個 frame 輪詢取訊息（不用 SendMessage）；
Editor / 桌面用 `System.Net.WebSockets.ClientWebSocket`（`NativeSocketTransport.cs`），背景接收迴圈把完整訊息（分段 frame 會組回）放進 `ConcurrentQueue`，
主執行緒在 `Update` 取出；離開 Play mode / 物件銷毀時會取消並關閉，不會留下執行緒。

### 除錯

- Console 搜尋 `[Manjong]`：會記錄 WebSocket 錯誤、關閉代碼與下一次重連的秒數（例：`WebSocket closed (1006), retrying in 2.0 s`）。
- 用瀏覽器開發者工具 → Network → WS，可以看到 WebGL 版每一則收送的訊息。
- 不開 Unity 也能測後端：`server/test/socket.test.ts` 有完整的 WebSocket 測試用戶端。
- 想讓 AI 出牌節奏變快：後端用 `AI_DELAY_MS=0` 啟動（預設 600ms）。
- 後端有防洗版限制（每條連線 10 秒內最多 100 則訊息，超過以 close `1008` 關閉）；用戶端會照一般斷線處理並自動重連。

## 4. Build WebGL 並由後端同源提供

1. Unity 選單 **`Manjong/Build WebGL`**，輸出到 `apps/manjong-unity/client/Build/WebGL`（已被 `.gitignore`）。
   - 也可以用命令列：
     ```bash
     <Unity 執行檔> -batchmode -quit -projectPath apps/manjong-unity/client -executeMethod ManjongBuild.BuildWebGL
     ```
2. 啟動後端；後端會讀環境變數 `WEBGL_DIR`（預設 `../client/Build/WebGL`）當作靜態檔目錄。
3. 瀏覽器開 `http://127.0.0.1:7316/`。WebGL 版本會自動用**頁面的 origin** 當 API 位置（同源，不需要 CORS）。
   - 本機開發時可用網址參數指定 API：`http://localhost:8080/index.html?api=http://127.0.0.1:7316`。基於安全考量，`?api=` **只在頁面本身來自 localhost / 127.0.0.1 時生效**（避免惡意連結把 token 送到別的伺服器）；正式部署請同源提供。
     （此時後端需允許該來源的 CORS）。

壓縮格式設為 `Disabled` 是為了讓後端不必設定 `Content-Encoding` 標頭；正式部署若要 gzip / brotli，需同步調整後端。
WebGL 頁面若是 `https://`，WebSocket 會自動改用 `wss://`，反向代理需要支援 WebSocket upgrade。

## 5. 程式結構

```
Assets/
  Editor/
    ManjongProjectSetup.cs   首次開啟建立 Main.unity、Build Settings、Player Settings；選單 Manjong/Setup Project
    ManjongBuild.cs          選單 Manjong/Build WebGL
  Plugins/WebGL/
    ManjongPrompt.jslib      WebGL 專用：用瀏覽器 prompt 輸入中文暱稱（見常見問題）
    ManjongSocket.jslib      WebGL 專用：瀏覽器 WebSocket 橋接（輪詢式）
  Resources/Fonts/huninn.ttf
  Scripts/
    Core/  Bootstrap（進入點）、AppController（畫面切換、登入流程、HTTP 呼叫、牌局訊息路由與錯誤處理）、
           Economy（底 / 每台 / 門檻 / 救濟金，必須與 server/src/engine/rules.ts 的 ECONOMY 同步）
    Net/   ApiConfig（HTTP 與 WebSocket 位址）、ApiClient（UnityWebRequest + coroutine）、Dto（契約 v0.2 DTO）、
           GameConnection（auth / ping / 重連）、SocketTransport（介面）、WebGLSocketTransport、NativeSocketTransport
    UI/    Palette（配色）、RoundedSprite（執行期圓角圖）、UiFactory（建 UI 的 helper）、
           TileFace（牌碼→字/顏色/中文名）、TileView（牌面/牌背）、Format、WebPrompt
    Screens/ LobbyScreen（大廳）、TableScreen（牌桌）、ResultPanel（結算）
```

技術限制（刻意的選擇）：不用 TextMeshPro、不用 Input System 套件、不用第三方套件、JSON 只用 `JsonUtility`、C# 語法不超過 9.0。
async/await 只出現在 `NativeSocketTransport.cs`（Editor / 桌面專用，WebGL build 不會編入）；其他程式一律用 coroutine。

## 6. 畫面上的聽牌與台數資訊（全部由後端提供）

- 輪到你打牌時，打出後會聽牌的牌，牌面上方有珊瑚色的「聽」標記。
- 點一下牌（浮起）時，畫面左下（手牌左側、花牌上方）的提示列會顯示「打出後聽：三筒（剩 2）、六筒（剩 3）」，不會聽牌則顯示「打出後未聽牌」。剩餘張數是後端只用你看得到的牌推算的。
- 不是你的回合但已聽牌時，提示列常駐顯示「聽牌中：…」。
- 自摸 / 胡的按鈕文字直接用後端的 label（已含台數，例如「自摸（5 台）」）；暗槓、加槓各自一顆按鈕。
- 自己摸牌時，事件列會顯示「你 摸到 五萬」。

## 7. 常見問題

| 狀況 | 原因與處理 |
| --- | --- |
| 開啟後出現「連不上伺服器」 | 後端沒啟動或不在 `127.0.0.1:7316`。先 `npm run dev`，再按「重試」。 |
| 按「開始遊戲」後跳出「連不上伺服器」 | HTTP 通但 WebSocket 連不上：確認後端版本含 `/ws`（契約 v0.2）、反向代理有轉 WebSocket upgrade。 |
| 牌桌上方一直顯示「連線中斷，正在重新連線…」 | 後端停了或網路斷了；會持續以最多 10 秒的間隔重試。可以按「離開」回大廳，牌局保留在伺服器。 |
| 跳出「已在其他視窗登入」 | 同一個帳號在別的視窗或分頁開了牌局（close 4000）。在這個視窗按「開始遊戲」即可接回來。 |
| 按鈕都點不到 | Active Input Handling 設成只用新版 Input System，改為 Old 或 Both（見上方）。 |
| 字變成方塊 / 缺字 | 粉圓字型是子集，只含常用字；若後端訊息出現子集外的字會顯示成方塊。找不到字型檔時會改用 Unity 內建字型並在 Console 警告。 |
| WebGL 版打不了中文暱稱 | 瀏覽器中 uGUI 舊版 `InputField` 收不到輸入法（IME）組字。WebGL 版暱稱旁有「中文輸入」按鈕，會跳出瀏覽器輸入框；若被瀏覽器擋下（例如放在 iframe 裡），會提示改用欄位輸入。 |
| WebGL 開啟後一片空白 / 載入失敗 | 確認是透過後端（`http://127.0.0.1:7316/`）開啟，而不是直接雙擊 `index.html`（`file://` 無法載入）。 |
| 想重開一個新帳號 | Editor：`Edit > Clear All PlayerPrefs`。WebGL：清除該網站的瀏覽器資料（PlayerPrefs 存在 IndexedDB）。 |
| 打到一半按「離開」 | 牌局保留在伺服器（伺服器重啟才會消失）；回大廳再按「開始遊戲」會接續同一場。 |
