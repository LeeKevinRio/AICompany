# ADR-0006：groupbuy 後端即時同步的技術選型

- 狀態：accepted（CEO 2026-08-05 核可免費層前提；本 ADR 依其約束定案）
- 日期：2026-08-05
- 決策者：tech-architect（草案）、CEO（核可）
- 適用範圍：僅 groupbuy 產品線（本 ADR 不存在於 main）
- 相依：`work/groupbuy-後端同步-需求.md`（PRD）、`work/groupbuy-安全設計-後端同步.md`、ADR-0001
- 與 ADR-0002 的關係：不取代、不牴觸。ADR-0002 選 FastAPI 的理由是量化生態，僅適用 stock-desk；groupbuy 無量化需求，該理由不遷移。公司自此並存兩種後端棧，為明知代價。

## 評估摘要（結論先行）

- **Hosting：Cloudflare Workers（API）+ Cloudflare Pages（SPA）+ D1（資料庫，apac location hint）**。唯一同時滿足「免費且超額停機不自動收費、不綁卡」「幾乎無冷啟動」「台灣有 PoP」「SQLite 語意」的組合。
- 否決：Render（閒置 15 分鐘冷啟動數十秒、免費 DB 有回收政策）、Railway（無常態免費層）、Fly.io（須綁卡且超額自動計費）、Vercel Hobby（條款限非商業用途且需外接 DB）、Supabase 作主後端（免費專案閒置 7 天暫停——團購是間歇流量，分享連結會在賣家不知情下死掉，產品級致命傷）。
- **後端：TypeScript + Hono on Workers**。非偏好而是硬限制：FastAPI 跑不上 Workers；且本案最大架構價值是前後端共用 types/calc/deadline/codec 的編譯期契約，換語言等於把契約降級成人工同步文件。
- **「即時」：輪詢**。後台分頁可見時每 5 秒 GET 帶 If-None-Match，version 未變回 304；分頁隱藏停止、10 分鐘無互動暫停、失敗指數退避（5→10→30→60s）。PRD 的 10 秒門檻不需下修。SSE/WebSocket 在無 Durable Object 前提下不省只脆，列 Phase 2 升級路徑（屆時另開 ADR）。
- **圖片：第一期做，買家端也顯示**（CEO「傾向做」成立）。存 D1 BLOB + sha256 內容雜湊 id + `GET /api/images/:hash` 帶 immutable 快取。不用 R2：R2 超額是「繼續服務並計費」且啟用需綁卡，觸「不花錢」紅線；D1 超額是「停止寫入報錯」。代價：約 2,500 張 200KB 圖的硬天花板，撞頂告警後由 CEO 決定是否升級 R2。後端強制閘門：單張 ≤200KB、每團 ≤8 張、magic bytes 驗證。
- **賣家身分：裝置 token**。後端 CSPRNG 256-bit、只在建團回應回傳一次、存 localStorage、走 Authorization header、絕不進 URL、DB 只存 SHA-256 雜湊、常數時間比對。否決簡單密碼（摩擦高、熵低、無實質增益）。細節依 `work/groupbuy-安全設計-後端同步.md`。
- **Monorepo：`apps/groupbuy/` 升為 npm workspace**，三包：`web/`（現行 SPA 搬入）、`api/`（Hono + wrangler + D1 migrations）、`shared/`（純 TS：types、calc、deadline、codec、api-contract、共用常數）。爆炸半徑鎖在 groupbuy 內。`image.ts` 留 web（依賴 canvas），其常數抽到 shared。
- **回單碼備援的唯一合法位置：買家送單失敗的錯誤分支**；成功路徑不再產生回單碼。賣家貼碼匯入改呼叫後端 API。寫入失敗絕不降級為本機寫入後宣稱成功；localStorage 鏡像僅供離線唯讀渲染（帶過期橫幅、寫入按鈕 disabled）。

## 資料模型（D1 正規化 schema）

groups(id 後端 128-bit 隨機、name、note、deadline_at、closed、created_at、version、seller_token_hash、expires_at)
products(id、group_id、name、price、image_id、sort_order)
orders(id、group_id、buyer_name、note、created_at、updated_at、paid，UNIQUE(group_id, buyer_name))
order_items(order_id、product_id、qty)
images(id = sha256(bytes)、bytes BLOB、mime、size、created_at)

- 送單一律單語句 upsert：`INSERT ... ON CONFLICT(group_id, buyer_name) DO UPDATE`（覆蓋時 paid 重置 0，沿用現行 applySubmitOrder 財務語意）；併發正確性由 SQL 保證。
- 買家名比對沿用現行語意：trim 後精確比對（改比對規則屬 PM 決策，本 ADR 不代為變更）。
- `Order` 新增 `note?: string`——順手修掉現行「回單碼備註被匯入端靜默丟棄」的既有缺陷。
- 每次寫入 bump `groups.version`，供輪詢 ETag 短路。

## API 契約草案

| Method | Path | 身分 | 說明 |
| --- | --- | --- | --- |
| POST | /api/groups | 無 | 建團；回 groupId + sellerToken（只此一次）+ joinPath |
| GET | /api/groups/:id/public | 無 | 團定義含 imageUrl；型別層即不含 orders 欄位 |
| POST | /api/groups/:id/orders | 無 | 買家送單；伺服器時鐘判截止 |
| GET | /api/groups/:id | 賣家 token | 全量含 orders；ETag/304 |
| PUT | /api/orders/:orderId/paid | 賣家 token | 冪等 set（非 toggle） |
| DELETE | /api/orders/:orderId | 賣家 token | 刪單 |
| PUT | /api/groups/:id/closed | 賣家 token | 冪等 set |
| POST | /api/groups/:id/orders/import | 賣家 token | 回單碼匯入（備援） |
| POST | /api/groups/:id/images | 賣家 token | 上傳圖；後端 magic bytes 驗證 |
| GET | /api/images/:hash | 無 | 圖片位元組，immutable 快取 |
| POST | /api/groups/import | 無 | 舊 localStorage 團一鍵上雲（建議案，優先序待 CEO） |

## 對實作的約束（qa-reviewer 據此檢查）

1. 禁止把 StorageRepository 整包讀寫語意當後端介面；賣家資料一律 per-entity RemoteGroupRepository。
2. 團 id 後端 CSPRNG ≥128-bit；不得沿用前端 genId 時間戳格式。
3. 賣家 token 不進 URL/query/log/錯誤訊息；DB 只存雜湊；常數時間比對。
4. paid 與 closed 的 API 必須冪等 set（PUT + boolean body），不得 toggle。
5. 同名覆蓋必須單一 SQL upsert；不得先 SELECT 再寫（競態）。
6. 截止判定一律伺服器時間，後端呼叫 shared/deadline 的 isGroupClosed(group, serverNow)；前端判定僅供 UI 提示。
7. 買家端回應不得含其他買家資料；/public 回應型別不存在 orders 欄位（型別層禁止）。
8. 圖片位元組永不內嵌團 JSON；回應出現 data:image/ 即違反。
9. 後端獨立驗證圖片：≤200KB、每團 ≤8 張、magic bytes。
10. 共用常數只有一份，全部住 shared/，前後端 import 同一份。
11. 寫入失敗絕不降級為本機寫入後宣稱成功；鏡像僅離線唯讀渲染＋過期橫幅＋寫入 disabled。
12. 回單碼只出現在買家送單失敗分支；成功路徑不產生回單碼。
13. 賣家回單碼匯入必須寫入後端。
14. 輪詢必帶 If-None-Match、分頁隱藏即停止。
15. shared/ 不得出現 DOM/window/Workers 專屬 API。
16. 每次寫入 bump groups.version。
17. 依賴版本由 devops-sre 查證當日 stable 版寫入 lockfile，不憑記憶指定。
18. 祕密只走 Workers secrets/環境變數,不進 git。
19. 檔案搬移（src/ → web/src/）必須獨立純搬移 commit。
20. Order.note 全鏈路（買家送單、回單碼匯入、後台顯示）必須帶到。

## 後果

好處：痛點直接解決（送單 5 秒內進後台）、結構性不可能自動產生費用、伺服器時鐘關掉裝置時鐘限制、併發正確性由資料庫保證、金額計算與 codec 單一實作、買家看得到商品圖。

代價（CEO 已知悉）：免費額度當日用爆＝全服務停到 UTC 隔日（不是降速）；D1 約 2,500 張圖硬天花板（撞頂停止上傳，不自動收費）；賣家清 localStorage/換裝置＝失去該團控制權（多裝置第二期）；公司並存 Python 與 TypeScript 兩套後端棧；一次大檔案搬移 commit；買家個資自此落地伺服器（保留期限 expires_at + 排程清理，天數由 security-engineer 提案、CEO 核可）。

## 尚缺的事實（實作前必補，本環境無外網，數字憑既有知識，須查證當日條款）

1. Workers Free 每日請求上限/CPU 上限/超額確切行為（不計費、不綁卡）→ devops-sre，**第一個確認**。
2. D1 免費層單庫容量/總儲存/row reads/writes 上限/超額行為 → devops-sre（直接決定圖片方案成立與否）。
3. D1 BLOB 與單次回應大小限制（200KB 可否單筆讀出）→ devops-sre；不可行則圖片方案回本 ADR 重評。
4. R2 是否強制綁卡、超額是否自動計費 → devops-sre（Phase 2 升級路徑）。
5. Durable Objects 於 Free plan 可用性 → devops-sre（Phase 2 WebSocket 路徑）。
6. D1 location hint 清單與台灣實測 RTT → devops-sre（驗證 5 秒輪詢 p95 < 10 秒）。
7. Free plan rate limiting rule 額度 → devops-sre + security-engineer。
8. Workers Cron Triggers 免費層可用性 → devops-sre（expires_at 自動清理）。
9. groupbuy 現行部署位置/網域/CI（worktree 查無任何部署設定）→ CEO 或 devops-sre。
10. Hono/wrangler/D1 套件當日 stable 版 → devops-sre。
11. Supabase 閒置暫停政策現況（備案用）→ devops-sre。
12. 個資保留天數 → security-engineer 提案、CEO 核可。
