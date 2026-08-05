# groupbuy 後端即時同步 — 安全設計：最低限度存取控制與濫用防護

- 撰寫：security-engineer
- 對應：PRD `groupbuy-後端同步-需求.md` 開放問題 7（賣家後台存取控制最低方案）、
  開放問題 11（防灌單/濫用填單連結的節流機制），以及「安全與隱私」章節第 1～5 點
- 狀態：draft，供 tech-architect 選定平台後對接落地；平台未定之處已標註
  「依 ADR 選定平台調整」
- 前提（CEO 裁示，本文件據此設計，不重複論證）：
  1. 部署用**免費層**，防護方案不得依賴付費 WAF / 付費防護服務
  2. 賣家身分採**輕量方案**（裝置 token 或簡單密碼），不做完整帳號系統
  3. 買家**免帳號**，憑連結即可填單，不得因本設計增加買家操作摩擦

---

## 1. 賣家後台存取控制

### 1.1 威脅

現行 `/groups/:id` 後台網址本身不含任何驗證。純前端時代資料只在賣家自己裝置沒有風險，
後端化後任何拿到或猜到這個 URL 的人都能讀訂單明細、切換收款狀態、刪單（對應 FR-6、
PRD 開放問題 7）。

### 1.2 方案比較

**方案 A：裝置 token（建議案）**

- **生成時機**：賣家成功開團（`POST /groups`）當下，由伺服器產生，回應中明文回傳一次。
- **熵**：至少 128 bit 的密碼學安全隨機值（例如 `crypto.randomUUID()` 或
  `crypto.getRandomValues` 產生 16 bytes 後 base64url 編碼），**不得**用 `Math.random()`
  或時間戳等可預測來源。熵足夠時不需要額外的失敗次數鎖定機制，因為暴力枚舉在合理時間內
  不可行。
- **儲存**：
  - 伺服器只存 token 的雜湊值（如 SHA-256 即可，token 本身已是高熵隨機值，不是人選密碼，
    不需要 bcrypt 級的慢雜湊），不存明文，比照密碼儲存的最小衛生原則。
  - 瀏覽器端存 `localStorage`，key 建議 `groupbuy:seller_token:<groupId>`（每團一把，
    互相獨立，降低單一 token 外洩的影響範圍）。
  - 呼叫賣家 API 時，token 放 `Authorization: Bearer <token>` header，**不放 URL
    query**（理由見第 5 節傳輸與儲存）。
- **遺失後果**：換裝置、清 `localStorage`、換瀏覽器＝永久失去該團管理權（無帳號系統，
  沒有「忘記密碼」路徑可找回）。
- **復原：管理連結備援**（建議做）：
  - 開團成功當下，後台頁面**額外**顯示一組「管理連結」（形如
    `.../groups/:id?token=<token>`），並附明確警語：「這個連結等於這個團的管理密碼，
    請自行截圖或存到 LINE Keep，勿分享給買家；換裝置時用這個連結重新登入。」
  - 該連結**只在開團當下的頁面顯示一次**；後台頁面之後仍可有「顯示管理連結」的入口，但
    需要已經是通過 token 驗證的狀態才能看（此時已是已驗證身分，沒有雞生蛋問題）。
  - Token 入 URL 有 referrer 洩漏風險，僅限管理連結這個「刻意的可攜帶版本」使用，一般
    日常操作走 header，不落地到 URL（緩解措施見第 5 節）。
  - 補一個「重新產生管理連結（舊連結與舊 token 一併失效）」的操作，作為疑似外洩後的手動
    補救；本輪不做強制輪替，理由見第 6 節「不做清單」。

**方案 B：簡單密碼（比較用，不建議）**

- 開團時要求賣家自訂或系統產生一組團密碼，之後開啟後台網址跳出輸入框，驗證通過後可用
  cookie/sessionStorage 記住。
- 優點：換裝置只要記得密碼即可復原，不像 token 完全綁死單一瀏覽器儲存。
- 缺點：
  - 多一個「設密碼」「輸入密碼」的操作步驟，直接違反 PRD 開放問題 7 明確點名的取捨——
    「賣家操作要夠輕量、不能變成要記帳密」。
  - 若密碼強度低（例如 4～6 位數字，符合「輕量」直覺），沒有節流會很容易被暴力猜測，需要
    額外做失敗鎖定/節流機制，複雜度反而高於 token 方案。
  - 一樣沒有「忘記密碼」復原路徑（不做完整帳號系統），遺失後果與 token 方案相同，但體驗
    多了「要記憶一組密碼」的負擔，沒有換來更好的復原能力。

### 1.3 建議案

**採方案 A（裝置 token）＋ 管理連結備援**。理由：與現行「賣家單裝置操作」的心智模型一致、
零額外操作摩擦（開團當下自動產生，賣家無感）、安全性只要熵足夠即可擋猜測攻擊且不需要
額外的鎖定機制，遺失後果不比密碼方案差，體驗更好。

### 1.4 賣家 API 授權檢查點清單

| Endpoint（範例，命名依 tech-architect 契約設計調整） | 需要 token | 額外檢查 |
| --- | --- | --- |
| `POST /groups`（開團） | 否（新建） | 伺服器建立時產生 token，僅在此次回應中明文回傳一次 |
| `GET /groups/:id/admin`（後台明細） | 是 | token 雜湊比對且對應該 groupId |
| `PATCH /groups/:id/closed`（截止切換） | 是 | 同上 |
| `PATCH /orders/:orderId/paid`（收款切換，FR-12） | 是 | 同上，且 order 需屬於該 token 對應的 group |
| `DELETE /orders/:orderId`（刪單） | 是 | 同上 |
| `POST /groups/:id/orders/manual`（現場代填，OrderPage） | 是 | 同上，且仍需通過 FR-4 截止檢查 |
| `POST /receipts/import`（回單碼匯入，FR-11） | 是 | 同上，且 receipt payload 內的 groupId 需與 URL 的 groupId 一致 |
| `POST /groups/:id/products/:productId/image`（圖片上傳） | 是 | 同上 |
| `GET /groups/:id/public`（買家用，JoinPage） | 否 | 只回傳白名單欄位，見第 3 節 |
| `POST /groups/:id/orders`（買家送單） | 否 | FR-4 截止檢查、FR-13 併發、第 4 節輸入驗證 |

實作細節：

- token 驗證應使用 constant-time 比對（多數框架的雜湊比對函式已內建，或用
  `crypto.timingSafeEqual`），避免 timing attack 側漏 token 是否部分正確。
- token 以「每團一把」而非「每賣家跨團共用一把」設計，符合現行單團管理心智模型，也降低
  單一 token 外洩時的影響範圍（只波及一個團）。
- 後台 API 本身也要有基本節流（見第 2 節），雖然 token 熵已夠高，但仍建議對同一 IP 對
  賣家 API 的失敗驗證次數做寬鬆節流（防禦性寫法，成本低）。

---

## 2. 買家填單連結的濫用

### 2.1 威脅

分享連結是公開的、會被層層轉傳（LINE 群組間常見），陌生人亂填或用腳本灌單皆有可能
（PRD 開放問題 11）。威脅模型定位：這是一個**熟人團購工具**，攻擊者輪廓是「意外過度轉傳
導致的誤填」或「單純惡意者/競爭對手手動或用簡單腳本灌爆某團」，而非有動機投入運算資源
的高階攻擊者。防護強度應對應此威脅模型，避免過度設計。

### 2.2 對策（皆為免費層可行手段）

**Rate limit（必做）**

- per-IP + per-group 節流：同一 IP 對同一團的送單 endpoint（`POST /groups/:id/orders`）
  限制在合理時間窗內的請求次數（例如 10 分鐘內 10 次），超過回應 `429 Too Many
  Requests`。
- 免費層平台的實作位置——**依 ADR 選定平台調整**，此處列出常見選項供 tech-architect
  參考：
  - 若選 Cloudflare Workers/Pages Functions：可用 KV 或 Durable Object 做簡易計數器
    （免費額度內可行），或視方案是否含內建 Rate Limiting rules。
  - 若選 Vercel/Netlify Functions + 免費層資料庫（如 Supabase/PlanetScale）：在 API
    handler 內查詢「近期同 IP + groupId 的請求時間戳筆數」做節流判斷，不另外引入快取層，
    降低依賴的服務數。
  - **前提風險**：部分免費 serverless 平台不易取得可靠的真實來源 IP，需依賴平台注入的
    header（如 `x-forwarded-for`、`cf-connecting-ip`）。tech-architect 需在 ADR 中確認
    選定平台下「哪個 header 可信」，否則 rate limit 會形同虛設（可被偽造 header 繞過）。

**單團訂單數上限（必做）**

- 同一團的訂單數（不同買家名）超過上限（建議預設 300，可視需要調整為可設定值）時，後續
  送單一律拒絕並提示「本團已達上限，請聯繫主揪」。目的：避免無限灌單耗盡免費層資料庫
  額度、拖垮效能，也間接抑制「狂刷不同名字灌爆團」的濫用。

**蜜罐欄位（建議做，成本極低）**

- 填單表單加一個對真人不可見的欄位（避免用容易被爬蟲識破的 `display:none`，改用
  `position:absolute; left:-9999px` 或等效手法 + `aria-hidden`、`tabindex="-1"`，避免
  螢幕閱讀器誤讀）。後端若偵測該欄位有值，直接靜默拒絕（對呼叫端裝作成功，但不寫入
  資料庫），擋掉最低端的通用垃圾表單機器人。成本僅一個 hidden input + 一行後端判斷，
  值得做。

**輕量 PoW（proof-of-work）——評估後不建議本輪做**

- 理由：這是熟人團購工具，攻擊者不太可能投入運算資源做 PoW 攻擊；PoW 需要前端額外運算
  邏輯與後端驗證，增加開發與維護成本，與「免費層、最小可行」的精神衝突。Rate limit ＋
  單團上限 ＋ 蜜罐已能覆蓋主要威脅（腳本大量灌單、通用垃圾機器人）。屬於過度設計，先不
  做；若上線後真的觀察到針對性灌單攻擊，屆時評估改用 Cloudflare Turnstile 之類的免費
  驗證碼服務，會比自建 PoW 更划算。

**CAPTCHA / Turnstile——本輪不做，列為觀察後可選項**

- 會增加買家填單摩擦，與「低摩擦填單」的產品目標衝突，不應預先防禦一個尚未觀察到的問題。
  若上線後濫用嚴重，Cloudflare Turnstile 有免費額度可考慮加裝。

### 2.3 建議案

**本輪必做**：per-IP + per-group rate limit、單團訂單數上限、蜜罐欄位。
**可選、視上線後觀察再加**：PoW、CAPTCHA/Turnstile。

---

## 3. 資料邊界

### 3.1 買家 API 能讀到什麼

- `GET /groups/:id/public`（JoinPage 用）：只回傳
  `{ groupId, name, note, deadlineAt, closed, products: [{ id, name, price, image? }] }`，
  **絕不**包含 `orders` 陣列或任何其他買家的訂單資料——對應 FR-7，現行純前端版本本來就
  看不到，後端化**不得倒退**。
- `POST /groups/:id/orders`（買家送單）：回應只回傳「自己這筆」是否成功、以及（可選）
  自己剛送出的訂單內容供收據頁顯示；**不得**在回應中夾帶該團的訂單總覽或統計數字（例如
  目前有幾人下單、總金額——這些屬於賣家後台資訊）。即使目前 UI 沒有顯示這些欄位，
  API 層也不該回傳，避免有人透過瀏覽器開發者工具或 `curl` 繞過 UI 拿到其他買家資料。
- 買家 API 完全不需要 token；靠 `groupId` 做定位。`groupId` 建議延續現行 `genId` 的
  高熵隨機字串精神（**不可**用簡單遞增 ID），避免被枚舉出其他團的 id 進而窺探。

### 3.2 賣家 API 授權檢查點清單

見第 1.4 節表格（已彙整賣家端全部 endpoint 的授權要求，供 tech-architect 對接 API 契約
設計時直接核對）。

---

## 4. 輸入驗證（後端＝唯一可信層）

現行純前端有多層防呆（HTML input `maxLength`/`min`/`max`、React state clamp、資料層
`applySubmitOrder`/`createGroup` 清洗），QA 已回報這幾層之間存在不一致之處。後端上線後，
**後端驗證是第四層、也是唯一可信層**——前三層都只是體驗優化，後端不得假設前端已經做過
任何檢查，必須把下列驗證**在伺服器端重做一次**。

**買家送單（`POST /groups/:id/orders`）**

- `buyerName`：trim 後非空字串，長度 `<= MAX_BUYER_NAME_LENGTH`（20，沿用 `types.ts`
  的常數，前後端共用同一份常數來源，避免未來改動時一邊漏改）；做基本控制字元清洗，
  但不過度過濾（中文/emoji 屬正常輸入）。
- `items`：陣列，每個 item 的 `productId` 必須存在於該團當下的 `products` 清單中（防止
  偽造不存在的 `productId` 汙染統計）；`qty` 為非負整數且 `<= MAX_ITEM_QTY`（999）；
  `qty <= 0` 的項目伺服器端一併過濾（沿用現行 clean 邏輯精神）。
- `note`：可選字串，需補一個合理長度上限（現行前端未見明訂上限，建議 200 字）。
- **價格絕不可信任前端傳來的值**：買家送單 payload 不應攜帶 `price`，後端一律以 group
  當下存的 `products.price` 重新計算金額。現行前端送單 payload 本來就沒帶 price，但
  後端化擴充 API 時要特別留意，避免未來不慎讓 client 端可覆寫金額，形成價格竄改漏洞。
- 截止檢查（FR-4）：以**伺服器當下時間**比對
  `group.closed || (deadlineAt && now >= deadlineAt)`，不信任 client 送來的任何時間欄位
  （對應現行 `deadline.ts` 註解承認的「無後端架構已知限制」，後端上線後必須修正）。

**賣家開團（`POST /groups`）**

- `name`：非空，trim 後長度 `<= MAX_GROUP_NAME_LENGTH`（40）。
- `note`：可選，補長度上限（同上建議）。
- `products`：陣列，至少一項名稱非空；每項 `name` 長度 `<= MAX_PRODUCT_NAME_LENGTH`
  （30）；`price` 為非負整數（伺服器端 `Math.floor` + `>=0` 校正，沿用現行 `createGroup`
  邏輯精神，搬到後端）。
- `deadlineAt`：若提供，須是型別合法的數值時間戳（`Number.isFinite`）；伺服器不需要因
  「已是過去」就拒絕（現行是前端 confirm 提示、允許使用者堅持），但要驗證型別避免注入
  異常值。

**賣家操作（`togglePaid`／`toggleClosed`／`removeOrder`）**

- 一律先驗證 token，再確認 `orderId`/`groupId` 存在且屬於該團；找不到回 `404` 而非
  `500`（避免用錯誤碼差異洩漏額外資訊）。

**通用**

- 所有字串欄位都要有伺服器端長度上限（防止超大 payload 塞爆資料庫欄位或造成 DoS）；
  整個 request body 建議設一個上限（例如 32KB，圖片上傳走獨立 endpoint、沿用 FR-8 現行
  `IMAGE_MAX_BYTES` 200KB 另外限制）。
- SQL/NoSQL injection：一律用參數化查詢/ORM，禁止字串拼接組查詢語句（依 tech-architect
  選定的資料庫技術於 ADR 落實）。
- 路徑穿越：`groupId`/`orderId`/`productId` 一律當不透明字串比對，不得用來組檔案路徑；
  圖片上傳的實體檔名由伺服器產生（不使用使用者提供的檔名），避免路徑穿越或覆寫任意檔案。

---

## 5. 傳輸與儲存

- **HTTPS**：全站強制 HTTPS。多數免費層 PaaS/CDN 平台預設提供 TLS，此為前提；若
  tech-architect 選定的平台不含，需在 ADR 中明確處理（例如加 Cloudflare 前置）。
- **Token 不入一般網址的 URL query**：日常後台操作一律用 `Authorization` header 帶
  token，避免出現在瀏覽器歷史紀錄、被轉貼截圖，或透過 `Referer` header 洩漏給頁面載入
  的第三方資源（若後台頁面載入任何外部資源如字型/CDN，URL 上的 token 可能隨 Referer
  外流）。
  - 例外：第 1.2 節的「管理連結」備援機制，其設計目的就是要讓 token 可攜帶分享，屬刻意
    取捨（換取「換裝置復原」能力）。緩解措施：該頁面加
    `<meta name="referrer" content="no-referrer">`，且不在該頁面載入任何第三方資源。
- **Log 不記個資**：伺服器 access log / error log **不得**記錄買家姓名、備註等個資內容，
  也不得記錄 token 明文。需要除錯追蹤時，記錄 `groupId` + `orderId` + 時間戳即可定位問題；
  若必須記錄 token 用於除錯，僅記前幾碼或雜湊值。
- **買家個資保留期限與刪團連動刪除**：
  - 買家姓名、品項、備註屬於個資/準個資，資料庫需設計「刪團即刪除所有關聯訂單」
    （cascade delete）：賣家主動刪團時，該團底下所有訂單資料必須一併刪除，不得留下
    孤兒 `orders` 記錄。
  - 建議另設「團自動封存/清除」機制：團的 `deadlineAt` 或最後活動時間超過一定天數
    （建議預設 90 天，可調整）後，由背景排程自動刪除該團與其訂單，避免無限期保留買家
    個資。此機制**依 ADR 選定平台調整**——需要 tech-architect 確認免費層是否有可用的
    排程能力（cron job）；若沒有，本點降級為「僅靠賣家手動刪團」為主要刪除手段，自動
    清除列為 nice-to-have，非本輪硬性要求。

---

## 6. 不做清單（本階段刻意不做，避免 scope creep）

| 項目 | 不做理由 |
| --- | --- |
| 完整帳號系統（註冊/登入/忘記密碼） | CEO 已裁示賣家採輕量 token 方案，不做完整帳號系統 |
| Email / 簡訊驗證 | 賣家、買家皆免帳號，沒有 email/手機號可驗證，不適用 |
| GDPR 級或個資法完整合規機制（資料可攜權匯出、正式蒐集同意流程、DPO 指派等） | 本工具屬小型熟人團購用途，本輪只做「刪團連動刪除」與「保留期限」的基本衛生機制；若日後規模擴大需要正式合規，應另立專案評估，不在本輪範圍 |
| 付費 WAF / 進階防護服務（Cloudflare Pro、AWS WAF 等） | CEO 裁示免費層起步，本輪防護全部基於免費層可行手段（應用層 rate limit、輸入驗證、蜜罐），不依賴付費服務 |
| PoW / CAPTCHA | 第 2 節已評估，威脅模型不需要，先不做，留待上線後依實際濫用情況再加裝（可選 Cloudflare Turnstile 免費額度） |
| 多裝置賣家身分共享機制 | PRD 已裁示列入 Phase 2，本輪 token 方案僅支援單裝置（＋管理連結手動備援到第二裝置），不做正式的多裝置身分系統 |
| Token 定期強制輪替 | 本輪 token 長期有效，賣家沒有「登出」情境，強制輪替會增加複雜度且與「輕量」原則衝突；改以「賣家可手動重置 token（舊連結失效）」作為疑似外洩時的最小可行補救（見 1.2 節），非預設防線 |
| IP 層級封鎖名單 / 地理限制 | 屬過度設計，且免費層平台通常不易做到穩定的 IP 封鎖 |

---

## 7. 待 tech-architect 對接事項清單（平台選定後補完）

- Rate limit 的實作載體（KV / DB counter / 平台內建 rate limiting）——依 ADR 選定平台
  調整。
- 排程刪除（個資保留期限自動清除）是否有免費層可用的 cron——依 ADR 確認，若無則降級為
  手動刪團為主。
- 來源 IP 取得方式（哪個 header 在選定平台下可信）——依 ADR 選定平台調整，若無法可靠
  取得真實 IP，第 2 節的 per-IP rate limit 需要替代方案（例如退化為 per-group 全域節流）
  並在 ADR 中說明取捨。
- HTTPS 是否由選定平台原生提供——依 ADR 確認，若否需額外規劃。

---

（文件結束。若後續設計有調整，請於本檔案追加修訂記錄，不覆寫既有段落，保留決策脈絡。）
