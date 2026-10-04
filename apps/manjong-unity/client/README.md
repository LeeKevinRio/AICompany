# manjong-unity 用戶端（Unity 6.3 LTS，WebGL 優先）

台灣 16 張麻將「可愛麻將」的 Unity 用戶端：1 位玩家對 3 個 AI。
規則、洗牌、AI、聽牌與台數計算、結算全部在後端（`apps/manjong-unity/server`），用戶端只負責畫面與送出「選了哪個合法動作」。

- **連線方式（契約 v0.3）**：登入、暱稱、救濟金、排行榜與牌局**全部走同一條 WebSocket**（`/ws`）；用戶端不呼叫任何 HTTP API（伺服器只剩 `/api/health` 與 WebGL 靜態檔）。

- 全部 UI 都由程式碼建立（uGUI legacy `Text` / `Image` / `Button`），**不需要手拉 scene 或 prefab**。
- 進入點：`Assets/Scripts/Core/Bootstrap.cs`（`RuntimeInitializeOnLoadMethod`，scene 載入後自動建立畫面）。
- 字型：`Assets/Resources/Fonts/huninn.ttf`（jf open 粉圓子集，授權見同資料夾 `LICENSE-jf-openhuninn.txt`）。
- 圖形：**牌面用傳統麻將牌的圖**（`Assets/Resources/Tiles/<牌碼>.png`，牌背 `back.png`，每張 150×200 px、圓角外透明）；
  找不到圖時自動退回程式畫的文字牌，並在 Console 警告一次。按鈕、面板、圓形頭像等可愛風 UI 仍在執行期用 `Texture2D` 產生。
- 牌圖匯入設定由 `Assets/Editor/ManjongTileImporter.cs`（AssetPostprocessor）自動套用：產生 mipmap（Kaiser 濾鏡，避免小牌走樣）、不壓縮、Trilinear、alpha 為透明、不縮放成 2 的次方。
  第一次開專案時 `Manjong/Setup Project` 會強制重新匯入牌圖，確保套到這組設定；若牌面仍偏糊，在 Project 視窗對 `Assets/Resources/Tiles` 按右鍵 → Reimport。
- API 契約：`work/manjong-unity/api-contract.md`（v0.3.1）；決策紀錄：`work/manjong-unity/adr/M002-牌局改用-WebSocket.md`。

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
3. 開啟後會自動連線：沒有 token 就送 `guest` 建立訪客帳號，token 存在 `PlayerPrefs`（key：`manjong.token`）；之後都用 `auth` 登入同一個帳號。
   想換一個新帳號：Play 停止後，在 Unity 選單 `Edit > Clear All PlayerPrefs`。

Editor 與桌面平台預設連 `http://127.0.0.1:7316`（集中在 `Assets/Scripts/Net/ApiConfig.cs`）。
若 7316 被佔用：後端用 `PORT=<新 port> npm run dev` 啟動，並在**啟動 Unity Hub / Editor 之前**設定環境變數 `MANJONG_API_URL=http://127.0.0.1:<新 port>`（環境變數要在 Editor 啟動前設定才會生效）。

## 3. 連線方式與除錯

### 位址

| 用途 | 位址 | 來源 |
| --- | --- | --- |
| 伺服器基底位址 | `ApiConfig.BaseUrl` | Editor / 桌面：`MANJONG_API_URL` 或預設 `http://127.0.0.1:7316`；WebGL：頁面 origin（loopback 頁面可用 `?api=`） |
| WebSocket（所有功能） | `ApiConfig.WebSocketUrl` | 由 BaseUrl 換算：`http→ws`、`https→wss`，再加 `/ws`。例：`ws://127.0.0.1:7316/ws` |

### WebSocket 流程（`Assets/Scripts/Net/GameConnection.cs`）

1. 程式一啟動就連線。第一則是 `auth`（有已存的 token，token 放在訊息裡、不放 URL）或 `guest`（沒有 token），收到 `auth_ok` 才算連上；`auth_ok` 帶回新 token 時會存進 PlayerPrefs。
   大廳右上角會顯示連線狀態，未連上時大廳按鈕都會停用。
2. 每則請求（`me`、`nickname`、`relief`、`leaderboard`、`start`、`action`）都帶遞增的 `requestId`；伺服器的回應與錯誤用 `replyTo` 帶回，
   用戶端據此把錯誤顯示在對的地方：改暱稱的錯誤在暱稱提示欄、救濟金用 toast、開始遊戲的錯誤在開始按鈕下方、牌局動作照牌桌流程處理。
   沒有回應的請求 15 秒後視為逾時；斷線時進行中的請求全部視為失敗並提示。「重新整理」會送 `me` 與 `leaderboard`。
3. 伺服器即時推送 `step`（摸牌、打牌、吃碰槓…）與 `state`（輪到你時的權威快照）。用戶端把它們排進同一個佇列依序播放：
   每步約 0.35 秒（開局 0.8 秒、胡牌 1.2 秒），佇列超過 6 步或點畫面任意處會快轉到每步約 0.08 秒；
   `state` 排到時才套用，此時若有 options 才解鎖操作。送出 `action` 後會鎖住，直到收到下一個 `state`。
4. 連上後每 25 秒送 `ping`；超過 60 秒沒收到任何伺服器訊息（含 `pong`）就視為斷線。連線階段與登入階段各有約 10–12 秒的逾時。
5. 斷線時自動重連（0.5、1、2、4、8 秒，上限 10 秒；連線穩定 30 秒後才把退避次數歸零），牌桌上方會出現「連線中斷，正在重新連線…」。
   重連成功後若在牌桌上會再送 `start` 取得最新 `state`；但若最後畫面已是整場結束（`game_end`），**不會**送 `start`（避免悄悄開新局），只保留「回大廳」。
   重連後若收到的 `gameId` 和原本不同（例如伺服器重啟），會先提示「牌局已重新開始」並清空事件列。
6. 關閉代碼與錯誤碼：

   | close / error | 意義 | 用戶端處理 |
   | --- | --- | --- |
   | `4401` + `INVALID_TOKEN` | 已存的 token 無效 | **唯一會清掉 token 的情況**，立刻改送 `guest` 建立新訪客帳號 |
   | `4408` + `AUTH_TIMEOUT` | 10 秒內沒完成登入 | 保留 token，照退避重連 |
   | `4401` + `UNAUTHORIZED` | 未登入就送了需要登入的訊息（用戶端程式錯誤） | 保留 token，Console 記 error，照退避重連 |
   | `4000` | 同帳號在別的視窗登入 | 停止重連，大廳顯示「已在其他視窗登入」與「重新連線」按鈕 |
   | `4403` | 網頁來源不被伺服器允許 | 停止重連並說明原因 |
   | `1008` | 超過防洗版限制 | 照一般斷線重連 |

實作：WebGL 用 `Assets/Plugins/WebGL/ManjongSocket.jslib` 包瀏覽器 `WebSocket`，C# 每個 frame 輪詢取訊息（不用 SendMessage）；
Editor / 桌面用 `System.Net.WebSockets.ClientWebSocket`（`NativeSocketTransport.cs`），背景接收迴圈把完整訊息（分段 frame 會組回）放進 `ConcurrentQueue`，
主執行緒在 `Update` 取出；離開 Play mode / 物件銷毀時會取消並關閉，不會留下執行緒。

### 除錯

- Console 搜尋 `[Manjong]`：會記錄 WebSocket 錯誤、關閉代碼與下一次重連的秒數（例：`WebSocket closed (1006), retrying in 2.0 s`）。
- 用瀏覽器開發者工具 → Network → WS，可以看到 WebGL 版每一則收送的訊息。
- 不開 Unity 也能測後端：`server/test/socket.test.ts` 有完整的 WebSocket 測試用戶端。
- 想讓 AI 出牌節奏變快：後端用 `AI_DELAY_MS=0` 啟動（預設 600ms）。
- `curl http://127.0.0.1:7316/api/health` 回 `{"ok":true}` 代表伺服器活著；若 health 正常但大廳一直「連不上伺服器」，問題在 WebSocket（例如反向代理沒轉 upgrade）。
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
    ManjongTileImporter.cs   Resources/Tiles 牌圖的匯入設定（AssetPostprocessor）
  Plugins/WebGL/
    ManjongPrompt.jslib      WebGL 專用：用瀏覽器 prompt 輸入中文暱稱（見常見問題）
    ManjongSocket.jslib      WebGL 專用：瀏覽器 WebSocket 橋接（輪詢式）
  Resources/Fonts/huninn.ttf
  Resources/Tiles/*.png      牌面圖（1m…9m、1p…9p、1s…9s、E S W N、RD GD WD、F1…F8、back）
  Scripts/
    Core/  Bootstrap（進入點）、AppController（畫面切換、requestId / replyTo 路由、牌局訊息與錯誤處理）、
           Economy（底 / 每台 / 門檻 / 救濟金，必須與 server/src/engine/rules.ts 的 ECONOMY 同步）
    Net/   ApiConfig（伺服器與 WebSocket 位址）、TokenStore（PlayerPrefs token）、Dto（契約 v0.3 DTO）、
           GameConnection（auth / ping / 重連）、SocketTransport（介面）、WebGLSocketTransport、NativeSocketTransport
    UI/    Palette（配色）、RoundedSprite（執行期圓角圖）、UiFactory（建 UI 的 helper）、
           TileFace（牌碼→字/顏色/中文名）、TileView（牌圖載入與快取、文字牌 fallback、副露組）、Format、WebPrompt
    Screens/ LobbyScreen（大廳）、TableScreen（牌桌）、ActionPanel（吃碰槓聽胡過面板）、ResultPanel（結算）
```

技術限制（刻意的選擇）：不用 TextMeshPro、不用 Input System 套件、不用第三方套件、JSON 只用 `JsonUtility`、C# 語法不超過 9.0。
async/await 只出現在 `NativeSocketTransport.cs`（Editor / 桌面專用，WebGL build 不會編入）；其他程式一律用 coroutine。

## 6. 牌桌版面與操作

**版面固定、不會跳動**（參考解析度 1920×1080；1280×720 等 16:9 視窗是同一份版面等比縮小）：

- 我的手牌從固定的左邊界排起，最多 17 格，右邊隔一段距離是固定的「摸牌格」。摸牌只出現在摸牌格，其他牌完全不動；
  打出後剩下的牌重新排序並靠左。吃碰後手牌變少，也是從左邊排起。
- 對手的手牌、副露、花牌、牌河、資訊卡都在固定位置、固定格線；副露從固定起點往右延伸（側邊玩家排滿一列才換行）。
- 副露照 `tiles` 順序顯示，從別家拿來的那張（`claimedIndex`）**橫放**；吃牌時被吃的那張在中間。暗槓外側兩張蓋牌。

**操作面板**（我的手牌上方偏右，位置固定）：只要有吃、碰、槓、胡、過任一個選項，或打出某張就會聽牌，面板就會彈出，
固定六顆按鈕依序是 **吃、碰、槓、聽、胡、過**。可以用的按鈕會亮起並有脈動光暈，不能用的變灰、按不了；沒有任何操作時面板收起。

| 按鈕 | 對應 | 說明 |
| --- | --- | --- |
| 吃 | `chi:*` | 只有一種吃法就直接送出；多種時跳出小選單，用三張牌圖顯示順子（被吃的那張有外框） |
| 碰 | `pon` | |
| 槓 | `kan`、`ankan:*`、`kakan:*` | 只有一個就直接送出；多個時跳出小選單，標示「明槓／暗槓／加槓」並附牌圖 |
| 聽 | （不送伺服器） | 切換提示：所有打出就會聽的牌加上外框，提示列列出「打 五萬：聽 三筒（剩 2）…」 |
| 胡 | `ron` / `tsumo` | 按鈕文字是「胡」或「自摸」，下面小字是台數（option 的 `tai`） |
| 過 | `pass` | 只有別人打牌或加槓、等你決定時才亮；輪到你打牌時是灰的 |

## 7. 畫面上的聽牌與台數資訊（全部由後端提供）

- 輪到你打牌時，打出後會聽牌的牌，牌面上方有珊瑚色的「聽」標記。
- 點一下牌（浮起）時，畫面左下（手牌左側、花牌上方）的提示列會顯示「打出後聽：三筒（剩 2）、六筒（剩 3）」，不會聽牌則顯示「打出後未聽牌」。剩餘張數是後端只用你看得到的牌推算的。
- 不是你的回合但已聽牌時，提示列常駐顯示「聽牌中：…」。
- 操作面板的「胡」按鈕會顯示「胡」或「自摸」，下面一行小字是這手的台數（後端的 `tai`）；槓有多種時（明槓／暗槓／加槓）會跳出選單。
- 自己摸牌時，事件列會顯示「你 摸到 五萬」。

## 8. 常見問題

| 狀況 | 原因與處理 |
| --- | --- |
| 開啟後出現「連不上伺服器」 | 後端沒啟動或不在 `127.0.0.1:7316`。先 `npm run dev`，再按「重試」。 |
| 大廳右上角一直顯示「連不上伺服器，正在重試…」 | 後端沒啟動、port 不對，或 WebSocket 被擋：確認 `/api/health` 正常、後端版本為契約 v0.3、反向代理有轉 WebSocket upgrade。 |
| 結算畫面顯示「金幣歸零，牌局結束」 | 金幣下限是 0，輸到 0 時整場立即結束。回大廳領救濟金（補到 10,000）即可再開局。結算的金幣增減是實際收付（可能因金幣不足而少於台數算出的金額）。 |
| 牌桌上方一直顯示「連線中斷，正在重新連線…」 | 後端停了或網路斷了；會持續以最多 10 秒的間隔重試。可以按「離開」回大廳，牌局保留在伺服器。 |
| 跳出「已在其他視窗登入」 | 同一個帳號在別的視窗或分頁登入（close 4000）。按大廳右上角的「重新連線」即可把連線搶回這個視窗。 |
| 按鈕都點不到 | Active Input Handling 設成只用新版 Input System，改為 Old 或 Both（見上方）。 |
| 牌面是白底文字而不是牌圖 | `Assets/Resources/Tiles/` 下缺少對應的 png（Console 會有 `Tile image ... not found` 警告）。補上圖檔即可，檔名就是牌碼。 |
| 字變成方塊 / 缺字 | 粉圓字型是子集，只含常用字；若後端訊息出現子集外的字會顯示成方塊。找不到字型檔時會改用 Unity 內建字型並在 Console 警告。 |
| WebGL 版打不了中文暱稱 | 瀏覽器中 uGUI 舊版 `InputField` 收不到輸入法（IME）組字。WebGL 版暱稱旁有「中文輸入」按鈕，會跳出瀏覽器輸入框；若被瀏覽器擋下（例如放在 iframe 裡），會提示改用欄位輸入。 |
| WebGL 開啟後一片空白 / 載入失敗 | 確認是透過後端（`http://127.0.0.1:7316/`）開啟，而不是直接雙擊 `index.html`（`file://` 無法載入）。 |
| 想重開一個新帳號 | Editor：`Edit > Clear All PlayerPrefs`。WebGL：清除該網站的瀏覽器資料（PlayerPrefs 存在 IndexedDB）。 |
| 打到一半按「離開」 | 牌局保留在伺服器（伺服器重啟才會消失）；回大廳再按「開始遊戲」會接續同一場。 |
