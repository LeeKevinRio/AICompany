# stock-desk 全公司產品審視（架構視角）

- 審查者：tech-architect
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論（評分）

| 面向 | 分數 | 依據 |
|---|---|---|
| 合理性 | **2／5** | 資料層的防呆方向正確，包括 PIT、fail-closed、幣別閘門、只綁 loopback 加寫入 header、還原價與原始價分流（`dividends/adjust.py:3-18`）。問題在比例：治理文件與尚未產生價值的功能規模失衡。ADR 共 16,116 行，其中 ADR-0025～0029 合計 8,613 行（53%），而這五份除 0025 外都還是 proposed，也都還沒上線。模組邊界有多處反向依賴，其中一處就是我自己的 ADR 造成的（見問題 5）。 |
| 好用性 | **2／5** | 六個頁面可以用，CEO 也能用 `dev-up` 啟動。但有三個問題：一是已通過審查的修正有 8 個分支卡在 #23 Codex 沒合併，最早從 10-16 起，已約 10 天；二是 CEO 10-15 說「我需要的就是投資建議」，到今天畫面仍寫「非投資建議」（`backend/app/advice/engine.py:60`、`frontend/app/layout.tsx:20`）；三是預測功能就算做好，也要多年後才可能顯示「優於基準」。 |
| 簡易清楚 | **1.5／5** | 一套系統有 3 顆 SQLite，README 卻說只有一顆。ADR 有 12 份 proposed，但都寫著「核可前以某份為準」。追蹤清單累積到 N-146。改一句字要讀一份 5,824 行、修訂優先序是「RC‴ > 增補 > r3″ > r3′ > r3」的 ADR（`docs/adr/0027-…:11`）。CEO 不可能自己讀懂，連員工也要靠計數核對才能確認落檔正確。 |

一句話：**防 look-ahead、防誤導的底線是對的。但我們把「保證不出錯」做成了「保證出不了貨」，而且預測帳的價值取決於累積天數，每延後一天上線，就少一天樣本。**

---

## 各部門回報（tech-architect）

### 最重要的 5 個問題

**1. ADR-0027 的治理量與它能產生的價值不相稱（含對我自己的批評）**
- 規模：5,824 行，佔全部 ADR 行數的 36%。FL 條目開頭 110 處、FL 引用 585 處；「對實作的約束」一節就有 795 行（`0027:2579-3374`）。
- 寫到程式碼形狀：FL-74 (b) 規定「同一函式恰好一個 `except Exception`……以不帶參數的 `raise` 結束」（`0027:2608`）。這是 code review 規則，不是架構決策。
- 實作進度：B1 純葉節點已 commit，但只有 `app/forecast/` 的 `band`、`definitions`、`claims`、`errors` 四個檔（約 1,035 行），recorder、store、scoring 都還不存在。
- 價值時程：quant 推估模型比最強基準高約 13 個百分點時，大盤 5 日約 10 年、3 日約 6 年才可能判定優於基準（`work/dispatch/2026-10-16-決策包二-Phase0與Phase1待CEO事項.md:55`）。ADR 自己也寫 n=150 約 3.1 年，全程掛「驗證中」或「未驗證」（`0027:87`）。
- 結論：IUT、α\*=0.05/48、四態驗證、claim 一次性轉值 trigger、25 張表這些「升級判定」機器，至少兩三年內不會被觸發，卻擋住了第一筆紀錄。
- 自我批評：我讓 ADR 同時兼任規格、測試計畫和審查紀錄，違背 ADR-0001「記錄決策」的本意。我自己也開了不少 suggested 級的 N 項，例如 N-122、N-124、N-127、N-129、N-130、N-143，每一項都會再引發一輪起草、確認、落檔、審查。

**2. 流程產能幾乎全被預測帳文件吃掉**
- `work/reviews/` 共 623 份檔案、約 10 萬行。10-16～10-19 四天產出 283 份。
- 10-20 之後的 133 份裡，有 131 份檔名屬於 ADR-0027、事先宣告 v0.x、N 項或 B1／B2；其中 50 份是「落檔／逐字／輕量確認／計數落差／機械」這類純文件核對。
- 風控在做字串計數：「`N-114` 實測 40……TA 預期值人工加總少算」（`work/reviews/2026-10-25-ADR0027第二批計數落差確認-風控.md:11-37`）。但風險閘門的範圍本來只限「面向使用者的建議類產出」（`docs/handoff-protocol.md:49`），這已經超出範圍。
- 「同一關卡退件兩輪不收斂就升級」（`handoff-protocol.md:57`）被拆批規避了：r1→r3″→RC‴，事先宣告 v0.11→v0.31，追蹤項到 N-146（`work/dispatch/2026-10-17-後續追蹤清單.md:230`）。

**3. 已完成的價值送不到 CEO 手上**
- A-1、T1-12、B-16、B0、F-9b2、KT-1、T-9、R-1 祕密遮蔽，都已 qa PASS，大多也有 e2e，但都在等 #23（`後續追蹤清單.md:6-16,35`；`決策包二:11`）。
- CEO 10-24 對 #23 選了「維持現狀，合併前再補跑」（`決策包二補遺:24`），結果仍然沒有合併。
- R-1 是 security 判定 BLOCKING 的祕密洩漏修補，devops 確認還沒進 `product/stock-desk`（`work/reviews/2026-10-26-產品審視-devops-sre.md:38-42`）。
- 新定位已核可 11 天，使用者看到的定位字面仍是舊的（見評分表）。新定位的字面遷移清單就有 3,973 行（`work/stock-desk-新定位-字面遷移清單-2026-10-16.md`）。

**4. 維運可見度做反了：複雜的告警模型先做，簡單的心跳沒有**
- ADR-0029 寫了 587 行，`ops_alert/model.py` 也寫了 449 行，但沒有接上排程，自己也這樣註明（`backend/app/ops_alert/__init__.py:5-6`）。scheduler 死掉，CEO 看不到。
- 實際有 3 顆 DB：主 DB（`data/cache.py`）、市場 DB（`data/market_panel.py:95`）、研究 DB（`research/sector_biased/store.py:45`）。README 卻寫「這一顆 SQLite 檔案……全部使用者資料都在這裡」（`README.md:53-54`）。
- 備份方式是對執行中的 WAL DB 直接 `tar`，並宣稱「不需要停機」（`README.md:58-62`）。這不保證一致快照〔推論：沒有用 SQLite backup API，也沒有 `VACUUM INTO`〕。三顆 DB 也沒有同一時點的備份，而預測帳依賴市場 DB 的 PIT 視圖，兩邊還原時點錯開就會破壞 PIT 的前提〔推論〕。
- ADR-0026 的備份組仍是 proposed、未實作。原生啟動不讀 `.env`、會靜默失效，devops 已列為第 1 個問題，這裡不重複。

**5. 模組邊界侵蝕與過胖的層（含 ADR-0006 的責任）**
- domain 反向 import API 層：`advice/limits.py:54` import `app.api.kelly_wording`；`scheduler.py:98,110` import `app.api.deps`、`app.api.kelly`。
- 最底層的資料層反向依賴上層：`data/providers/twse_snapshot.py:87-93` 依賴 directory 和 dividends；`data/diagnose.py:43-46,601` 依賴 positions、services、api。
- 正式路徑依賴 demo：`playbook/engine.py:36` import `app.demo.series`。
- API 層過胖：`api/kelly.py` 1,591 行、`api/kelly_wording.py` 1,238 行。ADR-0006 自己寫「本 repo 路由一律薄」（`0006:61`），卻用 D-8 把 api 定成唯一組裝點，`kelly_inputs_for` 因此住在 `api/kelly.py:1047-1059`，scheduler 只好去 import API。**這是我的設計錯誤。**
- 整體規模：22 個套件、約 59k 行正式碼，對 105k 行測試（4,061 個 test 函式），只服務 6 個頁面。另有 998 處 ADR／LM／FL／N 編號寫在正式碼裡（126 個檔），程式和流程文件互相綁死。
- 前端 `lib/types.ts` 有 2,298 行手寫型別、手動對齊後端；未查證有沒有 codegen，有漂移風險。

### 哪些是必要的防呆，哪些是過度工程

| 必要（保留） | 過度（凍結或刪減） |
|---|---|
| 預測輸入在 cutoff 前寫入、只增不改（FL-1 的 trigger 本身簡單也有效） | 規定 try/except 結構、import 數量的 AST 格（FL-74 (b) 一類） |
| 禁止讀 `price_bars_cache`、`_hindsight_view`、`dividend_events` 當預測輸入（FL-5） | 兩三年內不會觸發的升級判定機器：IUT、四態驗證、F-2 B 型細節 |
| 定義凍結並登記雜湊；顯示時並列基準；未驗證就標「未驗證」 | 25 張表、claim registry 的一次性轉值、作廢判定的四值順序 |
| 資料缺漏或幣別不明時 fail-closed，寧可顯示無值也不猜 | 族群方向（要累積 150 樣本，約 3 年）的全套規格；`research/sector_biased`（1,338 行） |
| 面向使用者的建議文案要經風控 | 對 ADR 內部字串的計數確認、逐字確認 |

---

## 建議

### 簡化方案比較

| 方案 | 內容 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| **A. 預測帳拆成「最小記錄器」和「凍結的驗證層」（建議）** | 新開一份精簡 ADR（目標 ≤500 行），只定記錄、PIT 輸入、基準並列、「未驗證」固定標示。D-11 升級判定、D-12 F-2、claim 細則改為附錄並凍結，第一個檢查點接近時再啟用。原始輸入多記，以後可以重算 | 盡早開始累積樣本，而時間正是這個功能的瓶頸；系統沒有升級路徑，就不可能誤宣稱「有效」，本身就是 fail-closed | 要重開部分已核可的風控條件；之後補驗證層時可能要遷移 | 少記了日後驗證要用的欄位。緩解方式：只增不改地保存原始輸入快照 |
| B. 暫停整條預測／展望線，回到既有六頁 | 凍結 ADR-0027／0028，人力轉去合併積壓分支、做維運心跳、修文件 | 降幅最大，馬上改善好用性 | 違背 CEO 10-15「我需要的就是投資建議」的需求 | 已投入的成本歸零；之後重啟時脈絡已散失 |
| C. 維持路線，只砍流程 | ADR-0027 不動，只套用下面的流程刪減 | 不必重工 | 5,824 行的維護負擔還在，速度只會小幅提升 | 文件繼續漂移，N 項繼續增加 |

### 可凍結的項目
1. ADR-0027 除了會擋住最小記錄器的缺陷以外，一律不再修訂；不再開 suggested 級的 N 項。
2. 事先宣告固定在 v0.31。之後的變更集中到「第一個檢查點」那一批處理。
3. 族群方向、`research/sector_biased`、ADR-0012 的延伸功能。
4. ADR-0029 的完整推播 sink。先改做 devops 建議 2 的 heartbeat 和首頁狀態帶。
5. Kelly 字面的後續迭代。
6. ADR-0028 的 8 態估值狀態，只實作畫面現在真的用得到的幾態。

### 流程可以減的步驟
1. **風控只審使用者看得到的字串和建議門檻**，回到 `handoff-protocol.md:49` 原本的範圍。ADR 內文、測試格編號、計數一律不送風控。
2. **計數落差和機械核對改用腳本**，在 CI 或由 coordinator 執行 Grep，不再開 agent 回合。
3. **ADR 落檔由作者直接提交 diff，qa 審一次**，省掉「tech-writer 落檔 → qa 落檔審查」這一輪。純文件變更不跑 e2e。
4. **小改字走輕量路徑**：起草 → 風控一次 → frontend → qa 審一次 diff → 合併。只刪字不重審，T-2 已有先例。版面有變才跑 e2e。
5. 取消「ADR 與事先宣告必須同一 commit」的綁定，改成用版本雜湊互相引用。
6. 「兩輪不收斂就升級」改成跨批次累計，拆批不再重新計數。

### 絕不可減的安全底線
- PIT 與防 look-ahead：預測輸入在 cutoff 前寫入、只增不改，禁用 hindsight 來源，還原價與原始價分流。
- 資料不完整或幣別不明時 fail-closed。
- 沒有事先宣告的評估，就不得宣稱有效；一律並列基準，標示「未驗證」。
- 面向使用者的建議類文案經風控審查（章程 §0.5）。
- 祕密不進檔、不進 log。R-1 必須盡快合併。
- 只綁 loopback 加寫入 header；不自動下單；不用黑箱 ML 產生方向。
- 程式合併前要有 qa-reviewer PASS 加 CI 綠燈；遷移前先備份；唯讀角色的權限邊界不放寬。

### ADR 草案要點（方案 A；落檔交 tech-writer）
- Context：ADR-0027 規模失衡；樣本價值取決於累積天數；升級判定機器多年內不會觸發。
- Decision：另立「預測紀錄帳核心」ADR，部分取代 ADR-0027 的 D-1～D-8、D-14；D-9～D-13 改為凍結附錄，「第一個檢查點前 90 天」或「n 達門檻的 50%」先到者觸發重審；核心期間驗證狀態固定為「未驗證」，沒有任何升級路徑。
- Consequences：好處是可以提早開始累積樣本、文件可讀、流程輪數下降。壞處是驗證層之後要重審，可能要做 schema 遷移，也要重開風控已核可的部分條件。

### 對實作的約束（可逐條檢查）
1. `app/` 下除了 `main.py` 以外，不得 import `app.api.*`。方法：import graph 測試。
2. `app/data/**` 不得 import positions、directory、dividends、services、api。方法：grep。
3. 正式路徑不得 import `app.demo`。方法：grep。
4. `kelly_inputs_for` 移出 api 層，改放在 domain 或 service 層（修正 ADR-0006 D-8，要另出 ADR）。
5. 三顆 DB 的備份必須同一時點、用 SQLite backup API 取得；README 改為說明有三顆 DB。

---

## 驗證

- 方法：只用 Read、Glob、Grep，沒有執行任何指令，沒有改任何檔案。
- ADR：狀態逐份 grep 出來，15 份 accepted、1 份 superseded（0018）、12 份 proposed，共 28 份（沒有 0013）。行數與 `^## ` 數量用 count 模式取得。
- 程式規模：後端 182 個 .py、59,192 行；前端非測試 118 個檔、24,781 行；後端測試 280 個檔、105,378 行。
- **未查證**：
  - 那 8 個分支到今天是否已經合併。我沒有跑 git，本機只看到 `main`、`product/stock-desk` 和一個 claude 分支，判斷依據是 10-17、10-18 的派工檔，加上 devops 10-26 的 R-1 確認。
  - pytest 6,605、vitest 2,274 這些數字取自文件，我沒有重跑。
  - tar 備份不一致、雙 DB 還原錯位，都屬於推論。
- 依指示沒有處理 N-140、N-141、N-146。

## 下一步：需要 CEO 決策的事項

1. **選簡化路線**：A、B 或 C。我建議 A，配合流程刪減。
2. **#23 Codex 現在就定案**：實際跑一次，或書面接受同廠商審查，讓 8 個分支馬上合併。R-1（security BLOCKING）最優先。
3. **ADR-0027 拆分**：是否同意拆成「核心」和「凍結附錄」？ADR-0025～0029 是要逐份核可，還是駁回後重寫？
4. **你是否接受預測功能多年內都顯示「未驗證」**。不接受的話，B 才是誠實的選擇。
5. **風控審查範圍限縮回「使用者可見字串」**：這會動到風控的否決範圍，必須由你明確裁定。
6. **新定位字面何時上線**：目前畫面的「非投資建議」和已核可的定位互相矛盾。
7. 維運方式與備份頻率：與 devops 報告第五節第 1、5 點相同，請一併裁定。

### 相關檔案
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/docs/adr/0006-stock-desk-kelly-輸入來源與模組邊界.md
- /home/user/AICompany/docs/handoff-protocol.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/work/dispatch/2026-10-16-決策包二-Phase0與Phase1待CEO事項.md
- /home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md
- /home/user/AICompany/work/reviews/2026-10-25-ADR0027第二批計數落差確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-26-產品審視-devops-sre.md
- /home/user/AICompany/apps/stock-desk/README.md
- /home/user/AICompany/apps/stock-desk/backend/app/advice/limits.py
- /home/user/AICompany/apps/stock-desk/backend/app/scheduler.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/kelly.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/twse_snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/diagnose.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/ops_alert/__init__.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/market_panel.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/engine.py
- /home/user/AICompany/apps/stock-desk/frontend/app/layout.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/types.ts
