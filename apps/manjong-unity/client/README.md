# manjong-unity 用戶端（Unity 6.3 LTS，WebGL 優先）

台灣 16 張麻將「可愛麻將」的 Unity 用戶端：1 位玩家對 3 個 AI。
規則、洗牌、AI 與結算全部在後端（`apps/manjong-unity/server`），用戶端只負責畫面與送出「選了哪個合法動作」。

- 全部 UI 都由程式碼建立（uGUI legacy `Text` / `Image` / `Button`），**不需要手拉 scene 或 prefab**。
- 進入點：`Assets/Scripts/Core/Bootstrap.cs`（`RuntimeInitializeOnLoadMethod`，scene 載入後自動建立畫面）。
- 字型：`Assets/Resources/Fonts/huninn.ttf`（jf open 粉圓子集，授權見同資料夾 `LICENSE-jf-openhuninn.txt`）。
- 圖形：圓角牌、按鈕、面板、圓形頭像都在執行期用 `Texture2D` 產生，專案裡沒有任何圖檔。
- API 契約：`work/manjong-unity/api-contract.md`。

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
   預設監聽 `http://127.0.0.1:3000`。
2. 回到 Unity，開啟 `Assets/Scenes/Main.unity`，按 **Play**。
3. 第一次會自動建立訪客帳號（token 存在 `PlayerPrefs`，key：`manjong.token`）。
   想換一個新帳號：Play 停止後，在 Unity 選單 `Edit > Clear All PlayerPrefs`。

Editor 與桌面平台一律連 `http://127.0.0.1:3000`（集中在 `Assets/Scripts/Net/ApiConfig.cs`）。

## 3. Build WebGL 並由後端同源提供

1. Unity 選單 **`Manjong/Build WebGL`**，輸出到 `apps/manjong-unity/client/Build/WebGL`（已被 `.gitignore`）。
   - 也可以用命令列：
     ```bash
     <Unity 執行檔> -batchmode -quit -projectPath apps/manjong-unity/client -executeMethod ManjongBuild.BuildWebGL
     ```
2. 啟動後端；後端會讀環境變數 `WEBGL_DIR`（預設 `../client/Build/WebGL`）當作靜態檔目錄。
3. 瀏覽器開 `http://127.0.0.1:3000/`。WebGL 版本會自動用**頁面的 origin** 當 API 位置（同源，不需要 CORS）。
   - 本機開發時可用網址參數指定 API：`http://localhost:8080/index.html?api=http://127.0.0.1:3000`。基於安全考量，`?api=` **只在頁面本身來自 localhost / 127.0.0.1 時生效**（避免惡意連結把 token 送到別的伺服器）；正式部署請同源提供。
     （此時後端需允許該來源的 CORS）。

壓縮格式設為 `Disabled` 是為了讓後端不必設定 `Content-Encoding` 標頭；正式部署若要 gzip / brotli，需同步調整後端。

## 4. 程式結構

```
Assets/
  Editor/
    ManjongProjectSetup.cs   首次開啟建立 Main.unity、Build Settings、Player Settings；選單 Manjong/Setup Project
    ManjongBuild.cs          選單 Manjong/Build WebGL
  Plugins/WebGL/
    ManjongPrompt.jslib      WebGL 專用：用瀏覽器 prompt 輸入中文暱稱（見常見問題）
  Resources/Fonts/huninn.ttf
  Scripts/
    Core/  Bootstrap（進入點）、AppController（畫面切換、登入流程、統一的 API 呼叫與錯誤處理）
    Net/   ApiConfig（API 位置）、ApiClient（UnityWebRequest + coroutine）、Dto（契約 DTO）
    UI/    Palette（配色）、RoundedSprite（執行期圓角圖）、UiFactory（建 UI 的 helper）、
           TileFace（牌碼→字/顏色/中文名）、TileView（牌面/牌背）、Format、WebPrompt
    Screens/ LobbyScreen（大廳）、TableScreen（牌桌）、ResultPanel（結算）
```

技術限制（刻意的選擇）：不用 TextMeshPro、不用 Input System 套件、不用 async/await（WebGL 單執行緒，全部用 coroutine）、
不用第三方套件、JSON 只用 `JsonUtility`、C# 語法不超過 9.0。

## 5. 常見問題

| 狀況 | 原因與處理 |
| --- | --- |
| 開啟後出現「連不上伺服器」 | 後端沒啟動或不在 `127.0.0.1:3000`。先 `npm run dev`，再按「重試」。 |
| 按鈕都點不到 | Active Input Handling 設成只用新版 Input System，改為 Old 或 Both（見上方）。 |
| 字變成方塊 / 缺字 | 粉圓字型是子集，只含常用字；若後端訊息出現子集外的字會顯示成方塊。找不到字型檔時會改用 Unity 內建字型並在 Console 警告。 |
| WebGL 版打不了中文暱稱 | 瀏覽器中 uGUI 舊版 `InputField` 收不到輸入法（IME）組字。WebGL 版暱稱旁有「中文輸入」按鈕，會跳出瀏覽器輸入框。 |
| WebGL 開啟後一片空白 / 載入失敗 | 確認是透過後端（`http://127.0.0.1:3000/`）開啟，而不是直接雙擊 `index.html`（`file://` 無法載入）。 |
| 想重開一個新帳號 | Editor：`Edit > Clear All PlayerPrefs`。WebGL：清除該網站的瀏覽器資料（PlayerPrefs 存在 IndexedDB）。 |
| 打到一半按「離開」 | 牌局保留在伺服器（伺服器重啟才會消失）；回大廳再按「開始遊戲」會接續同一場。 |
