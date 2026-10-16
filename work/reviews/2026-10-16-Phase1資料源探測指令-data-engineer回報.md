# Phase 1 資料源探測指令包回報 — data-engineer

> 轉存：coordinator，2026-10-16，子 agent 回報逐字轉存。指令本文：`work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`（未執行）。

---

## 1. 本次結論

做完了。探測指令包已寫好，全部指令尚未執行，因為本環境不能連外網。檔案在 `/home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`。

文件裡除了 repo 已驗證過的端點，其餘端點、資料集名稱和欄位都標成「候選／印象」。404 或回 HTML 都算預期結果，要求 CEO 照實回報，不要自己改路徑硬試。

一個要 CEO、PM 或 tech-architect 裁示的範圍風險：`CostModel.verified_on` 是單一欄位，同時管台股費稅和美股經紀費、美股規費（`app/backtest/costs.py` L47-55）。T1-10 只要求查台股手續費與證交稅。只查台股就填日期，會讓美股兩個費率被誤認為已查證。文件 §4.5 列了三個處理選項：同步查美股、拆欄位、或美股維持「費率未查證」。

## 2. 各部門回報

- **data-engineer（我）**：
  - 新寫上述文件，沒改任何程式。
  - 沒讀 `.env`，沒碰 `*.db`。
  - 對外請求是 0 次：沒有 curl、wget、pip、npm，也沒有 python 對外請求。
  - 指令全是唯讀 GET，並加了限速、停手和防洩密設計：
    - 每次請求間隔 6 秒，helper 不跟隨轉址。
    - 遇到 403、429 或 503 會自動建立 `.STOP`，之後所有 probe 拒絕執行。
    - FinMind token 一律讀 `$FINMIND_API_TOKEN`，走 `Authorization` 標頭，不進 URL 和索引檔，也不寫進任何檔案。
    - 文件警告不要用 `set -x`、`curl -v`。
    - 附祕密殘留檢查，token 不會被印出。
- **各項候選來源摘要**（官方優先）：
  - **T1-07 休市日與公布時段**：
    - 休市日：TWSE OpenAPI `holidaySchedule`；TWSE 官網 `holidaySchedule`，查 2024 到 2027 四年，先舊路徑再新路徑；FMTQIK（每日市場成交資訊）單月成交日，用來交叉比對颱風假；備援為 FinMind `TaiwanStockTradingDate`。
    - 公布時段：同一交易日在 13:35、14:15、15:30、17:30 和隔天 08:30 各跑一輪，每輪 3 次請求，看當日那一列何時出現。
    - 另外確認兩個全市場日資料集有沒有交易日欄位。
  - **T1-08 指數**：
    - 價格指數：TWSE `MI_5MINS_HIST` 和 OpenAPI 指數路徑，取樣 1990、2000、2010、2020、2026 五個月份來探歷史長度。
    - 報酬指數：TWSE `MFI94U`。
    - 備援：FinMind `TaiwanStockTotalReturnIndex`（名稱為印象），先用 datalist 確認 id。
    - 對照基準：Yahoo `^TWII` 一次請求，附時區欄位解析。
  - **T1-09 公司行動**：
    - 上市：`TWT48U_ALL` 已驗證且只列未來，本次不重打；另有 `t187ap45_L` 股利分派、www 網域的 `TWT49U` 除權息結果、`TWTAUU` 減資參考價（路徑皆為印象）。
    - 上櫃：TPEx OpenAPI 先看 swagger 篩選，另試兩個猜測路徑。
    - 備援：FinMind 六個資料集（含 `TaiwanStockDividend`、`TaiwanStockPriceAdj`，名稱皆為印象），其中 `TaiwanStockDividend` 同時測 2330 與上櫃 6147。
    - 用 0050 約 2025-06 的分割（日期為印象，須以交易所公告核對）比對 TWSE 與 FinMind 收盤，判斷是原始價還是已還原。
    - 回貼範本有「類型 × 上市／上櫃 × 來源」矩陣，沒有來源的格子明寫「來源未涵蓋」。
  - **T1-10 費率**：
    - 全國法規資料庫（`law.moj.gov.tw`）的證券交易稅條例和證券商管理規則，先用站內搜尋找 pcode，不憑記憶。
    - 指令撈出標題、修正日期和費率句。
    - 瀏覽器人工補查五項。
- **tech-architect、PM**：本次未參與。§4.5 的 `verified_on` 範圍需要他們裁示。
- **其他部門**：本次未參與。這是純文件任務，不含面向使用者文案，所以沒送 risk-compliance-officer。

## 3. 驗證

- **做過的驗證**（都是本機離線）：
  - 文件內 22 個 bash 區塊全部通過 `bash -n`。
  - 文件內嵌的 helper 與我先獨立測過的檔案逐字相同。
  - 內嵌的 python heredoc 都能編譯。
  - helper 用 `file://` 離線實測過 `probe`、`probe_try`（第一個 URL 失敗時自動換第二個）、`jsonshape`、`hdrs`。swagger 路徑列表（jq 版與 python 備援版）、法規頁解析、授權字串 grep 也都用假資料實測過，輸出符合預期。
  - 文件內沒有任何類似 token 的字面值。
- **沒做的驗證**：任何端點是否存在、回應內容、額度、授權，因為不能連網。這些全由 CEO 本機實跑決定。
- **CEO 要做的**：
  1. 先輸入 `bash`，再自行設定 `FINMIND_API_TOKEN`（文件 §0.1 有靜默輸入的寫法，不要貼回對話）。
  2. 照 §0.2、§0.3 建資料夾和 helper，依序跑 T1-07 到 T1-10。T1-07 的 timing 要挑一個交易日分時段跑。
  3. 照每節的「回貼範本」貼回；不要貼 token、`fm_user_info_*.body` 全檔、Set-Cookie 行、超過 40 行的輸出。
- **跑完仍需人工判讀的項目**（文件 §5.2 有總表）：
  - 所有來源的授權條款全文，包括快取、衍生顯示、再散布是否允許。
  - 指數授權和是否需付費。付費時依章程升級 CEO，不自行採購。
  - 報酬指數口徑是否對應 00675L／00676R。
  - 公布時段的規律性。單日實測不能直接寫成參數。
  - 臨時休市是否一定進官方表。
  - 公司行動各類型是否真被涵蓋。「沒出現」不等於「沒發生」。
  - 配股因子可否還原。
  - point-in-time。無版本戳者只能靠長期自存快照。
  - 稅率時效（當沖減稅是否仍有效）和手續費「法定上限」對「實收」的口徑。
  - FinMind 資料集是否限付費。

## 4. 下一步

1. CEO 本機代跑並回貼；請求量約 70 次、間隔 ≥ 6 秒，timing 部分要橫跨一個交易日。
2. 我收到回貼後：
   - 填 ADR-0025 D-9 比較表和查證日期，交 tech-architect 拍板主來源與備援。
   - 指名要入 repo 的 fixture，先做祕密掃描。
   - 定義 adapter 介面（含 `as_of`、`source`）與降級路徑，再交 dev-lead 做 T1-13 到 T1-16。
3. 等 PM 或 tech-architect 對 `verified_on` 範圍（文件 §4.5）給裁示，T1-10 才能收斂。

檔案：`/home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`（尚未 commit，也沒有 push）。
