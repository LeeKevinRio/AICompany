# ADR-0027 第一批（N-113、N-115、N-117）落檔

- 審查者：tech-writer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 1. 本次結論

ADR-0027 第一批（N-113、N-115、N-117，含 N115-9）已落檔到 working tree，沒有 commit，也沒有跑任何 git 指令。第二批 N114 沒有落。47 個套用步驟的 old 在套用當下都恰為 1 處，沒有觸發停下。`-o` 實測計數 17 項裡 16 項與來源預期一致，只有 `FL-42` 不一致，原因見第 2 節。

有兩件事沒有照你的交付清單做到：
- **我沒有 Bash 工具**，只有 Read、Write、Edit、Glob、Grep。因此沒有產生 `adr_before.md`，也沒有跑真正的逐行 diff。
- `adr_removed.txt`、`adr_added.txt` 改為依我每一次 Edit 的 old／new 片段手工切段，是片段級，不是整行級。兩檔都是「開頭說明」加 23 段，以 `=====` 分隔，段標頭相同，一一對齊。最後一段（修訂紀錄，檔尾追加）在 added 檔只寫了指向 ADR 檔 L5529-5586 的指引，沒有重複抄錄全文。
- 要拿到真正的整行 diff：請 coordinator 先執行 `git show HEAD:docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md > adr_before.md`，再跑 `batch1/make_line_diff.py`。這支腳本我沒有執行過，未驗證。
- 我假設落檔前 working tree 就是 HEAD（TA 草稿的行號與基準檔 5506 行都吻合），但沒有用 git 比對確認。

## 2. 各部門回報

### 動到的 ADR 段落（行號是落檔後；括號內是落檔前）
- D-1 模組表：
  - L234 `store.py` 列（原 L234），N115-5。
  - L235-236 `app/dirdef/` 與 `definitions.py` 兩列（原 L235），N113-1。
  - L239 `errors.py` 列（原 L238），N115-4。
  - L240 `band.py` 列（原 L239），N113-2。
  - L252-257 插入六列（原 L250 之後），N115-5。
  - L259 `volatility.py` 列（原 L252），N113-3。
  - L261 `baselines.py` 列（原 L254），N113-4。
- D-3：
  - L338 `scope_reason` 子點（原 L331），N117-4、N117-5。
  - L350（原 L343），N115-6。
  - L871（原 L864），N115-7。
- D-7：L1073（原 L1066）N117-1；L1087（原 L1080）N115-1。
- D-10 第 3 點之後：L1576-1581 插入（原 L1568 之後），N115-3。
- FL 區：
  - L2560 FL-74 (h)（原 L2547），N117-2。
  - L2580 FL-76 (p)（原 L2567），N117-3。
  - L2592 FL-77 (h)（原 L2579），N115-2。
  - L2599 FL-77 (o)（原 L2586），N117-6、N117-7、N117-8。
  - L3085 FL-42 第二項（原 L3072），N115-9。
  - L3214-3222 插入 FL-78、FL-79（原 L3200 之後），N113-5、N115-8。
- 檔尾：L5529-5586 為修訂紀錄（原 L5506 之後），前置空行、`---`、空行。

### 來源衝突的處理
- N113-1 取 TA 修訂稿，取代原稿與被風控否決的版本。
- FL-78 取 TA 修訂稿版，再套風控重審 required 1、3b。
- N115-9 的 TA 逐項新增項被風控 required 8 取代。
- 風控「那一行」用重審檔第四部分的最終定稿，取代 TA 原稿 L231 的 bullet。

### 計數不一致
- **`FL-42`：預期 4（落檔前 3 處加風控表的 +1），實測 12。**
  - 新增的 9 處：標題 1、N115-9 來源行 1、風控那一行 2、N115-9 逐項 2、照實並陳 N113-1 改句 1、照實並陳 N115-9 新項 2。
  - 這些字句都是來源明文給的，沒有多寫；風控表只數了風控那一行的一部分。判定是預期值低估，不是落檔錯誤。
- 其餘 16 項與來源預期一致：
  - `N-113`＝9
  - `N-115`＝24（TA 修訂稿是 23，N115-9 第五節更新為 24）
  - `N-117`＝12
  - `app/dirdef`＝9
  - `app\.dirdef`＝7
  - `BANNED_PHRASES`＝10
  - `OUTLOOK_RULE_FIELDS`＝6
  - `app/outlook/rules`＝3
  - `FL-78`＝10
  - `FL-79`＝4
  - `BEGIN IMMEDIATE`＝10（落檔前 4）
  - `exception_class_name`＝4
  - `ENDPOINT_SURFACES`＝6（落檔前 5，預期 +1）
  - `ADR-0025`：落檔前 25，落檔後 34，增加 9，與 TA 預估一致
- `N113-`＝18、`N115-`＝32、`N117-`＝20，來源沒有給預期值，僅供對照。
- 逐項分布在 `counts.tsv`。

### 被取代的 old 落檔後
- 剩 0 處：N113-3、N113-4、N115-4，以及所有風控改字的 old。
- 只剩修訂紀錄引文 1 處：N113-1（L5543）、N113-2（L5545）、N115-1（L5550）、N115-2（L5552）、N115-5 的 `store.py` 原列（L5556）、N117-3～N117-7（L5564、5566、5568、5570、5572）。
- 本文仍有 1 處，這是 new 以原句開頭所致，不是殘留：FL-42 old（符合 TA 預期）、風控 required 4 與 required 7a 的 old。
- 無殘留的〔轉存檔名〕〔重審檔名〕〔重審結論〕。

### 需要你知道的判斷點（來源沒有明講，我照字面處理）
1. 〔轉存檔名〕填成「coordinator 轉存 `work/reviews/2026-10-24-N113-1修訂稿-tech-architect.md`」，原文「轉存〔…〕」之間我加了一個空格。
2. 修訂紀錄前置為「空行、`---`、空行」，比照 N-109/N-110 段的做法。TA 原文只寫「前面先加一行 `---` 與空行」，我多補了 `---` 之前的空行，免得上一行變成 Markdown 標題。
3. N115-9 新增的照實並陳項，我放在 N115-6 項之後、N117-4 項之前（依編號順序）。來源只說「新增一項」。
4. 待決第一子項的最終順序：「全批可以只用一個 commit。」→「N113-1～N113-5 不得早於 N115-3 落檔（FL-78 (m) 引用 N115-3 的登記 CLI）。」→「修訂紀錄（本段）最後落檔。」→「N115-9 與 N115-5、N113-1 必須同一個 commit。」N115-9 那句是照「第一個子項句末」字面接在最後，讀起來在「最後落檔」之後略不順，需要的話請 TA 確認位置。
5. 沒有套用的：
   - 風控 suggested 項：RC2 三條、RC1 的 N115-1 與 N115-6 兩條。
   - TA1 在 N115-5 後的「注意」說明。
   - 風控與 TA 要求列入後續追蹤清單的四項。來源沒有給落檔字句，我沒有自行撰寫。四項是：舊版規則集的保存與重新載入、前瞻 claim 登記齊全的機器檢查、禁詞比對正規化、FL-78 (k) 升版阻擋的解除條件。
6. 風控重審檔要求 TA 把第六節第 1 點的「直接 import」同步改為「進入點」。這是 TA 的 work/reviews 檔，不在 ADR 內，不是我的範圍，請 coordinator 確認 TA 有改。

### 佐證清單
B 類（記錄決策脈絡）：所有字句來源是上述五份 work/reviews 檔，逐項對照見 `apply_log.txt`，快照基準是 TA 草稿所稱 HEAD f5a6ae8，未用 git 驗證。我沒有補寫任何來源沒給的技術細節。唯一做過的 A 類交叉核對是風控字句引用的 D-14 G-3：ADR 新 L2406 寫「registry 中 `frozen_commit`、`rules_sha256`、`prereg_doc_blob` 都非 NULL」，與風控字句相符。行號會漂移，抽驗請以原文定位。

## 3. 驗證

- 每個 old 套用前用 Grep `-o` 實測恰 1 處（獨立的 old）。依賴前一步結果的 old 以 Edit 工具成功為證，Edit 要求 old 唯一。
- 落檔後逐項重測：所有 new 的獨有片段各恰 1 處，superseded old 如上。
- 抽讀檔尾 L5526-5535、L5574-5587，確認修訂紀錄結構與標題。
- 沒有讀 `.env`，沒有碰 `*.db`，沒有執行任何程式碼或 git 指令。
- 沒有經 qa-reviewer 審查，也沒有補跑 Codex。

## 4. 下一步

1. coordinator 產生 `adr_before.md`，執行 `make_line_diff.py`，取得整行級 diff。
2. 送 qa-reviewer 審查並補跑 Codex。風控要求 required 5～7 列為 qa 實作檢查項：進入點的走法、`app/forecast/__init__.py` 不 import 任何 `app.*`、kind 為 `on_demand` 的 route 列舉、5xx 回應本體為固定字面。
3. TA 同步 N115-9 第六節 1 的「直接 import」措辭，並確認上述第 4 點的待決句位置。
4. 後續追蹤清單的四項新增，請 TA 或 coordinator 提供落檔字句。

## 交付檔案（皆在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/batch1/`）
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/batch1/apply_log.txt`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/batch1/adr_removed.txt`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/batch1/adr_added.txt`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/batch1/counts.tsv`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/batch1/make_line_diff.py`
- `adr_before.md` 沒有產生。

已修改的 ADR：`/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`（5506 行變 5586 行）。
