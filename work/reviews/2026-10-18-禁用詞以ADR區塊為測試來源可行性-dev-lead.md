# 禁用詞清單以 ADR 區塊為測試來源可行性

- 審查者：dev-lead
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**可行，但要補一條錨點定位約定。** 用 ADR-0027 FL-71 (f) 的文字當測試的單一來源，在 CI 讀得到，也解析得出來。不過照 M-9 現在的寫法（「以起訖錨點截取」），按子字串去找錨點會截錯，原因在下面第 2 點的歧義 1。清單內容本身不用改格式，只要在 ADR-0029 D-4「單一來源」一點（或 FL-71 (f) 標頭）補上下面「最小格式要求」的第 1 條。其餘各條都是把現況寫成明文的約束，免得之後改字時被打破。不需要退回 tech-architect，也不需要另建清單。

這次是唯讀確認：沒有改任何 repo 檔、沒有 commit、沒有讀 `.env` 或 `*.db`。只在 scratch 寫了一支解析腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/parse_fl71f.py`。

## 各部門回報（dev-lead）

**1. 後端測試能不能穩定讀到 `docs/adr/`**
- **CI 讀得到**：`.github/workflows/stock-desk.yml` 的 backend job 先做完整的 `actions/checkout@v4`，再在 `apps/stock-desk/backend` 跑 pytest，`docs/adr/` 在 checkout 裡。
- **Docker 不受影響**：測試不在 Docker 裡跑。`apps/stock-desk/backend/Dockerfile` 只 COPY `pyproject.toml`、`uv.lock`、`app/`，`.dockerignore` 也排除了 `tests/`；compose 的 build context 是 `./backend`，本來就看不到 `docs/`。
- **路徑定位有前例**：用 `Path(__file__).resolve().parents[4]` 取 repo 根目錄，`test_f9b_book_cause_group.py`、`test_f9b_admission_gate.py`、`test_api_sectors_wording.py` 已經這樣讀 `work/` 下的檔案。路徑不依賴工作目錄。
- **B 類可直接重用**：`load_frontend_forbidden_terms()` 已經被別的測試檔 import 過（`test_f9b_book_cause_group.py` L51 `from tests.test_rules_invalidation_wording import ...`），`tests/__init__.py` 也存在。
- **缺口（devops-sre 範圍）**：stock-desk.yml 的 `paths` 篩選只有 `apps/stock-desk/**` 和 workflow 自己。**只改 ADR-0027 清單的 commit 不會觸發後端測試**，清單改壞了要等下次動到 app 才會被發現。建議把 `docs/adr/0027-*.md` 加進 push／pull_request 的 paths。
- **其他**：檔名是中文，要用 `read_text(encoding="utf-8")` 讀。CRLF 不影響解析（`.gitattributes` 只對 `.bat`／`.sh` 設了換行），解析時對每個詞做 strip 即可。

**2. 用現行文字試解析（ADR-0027 工作樹，2026-10-18 當下版本）**

取出的筆數：

| 類別 | 取出內容 | 筆數 |
|---|---|---|
| A | 「」詞 | 15 |
| A | regex `\b(LM\|PV\|TG\|FT\|PA\|BM)-\d+`（可編譯） | 1 |
| C | 中文「」詞 | 47 |
| C | 英文詞界清單（全為 ASCII 字母） | 16 |
| D | 「」詞 | 12 |
| F | 反引號字串，例如 `api.telegram.org/bot`、`File "` | 11 |

- 類別標題 `- **X. …**：` 能穩定切出 A～F 六段。
- F 類的非字面項（假 token、假 webhook URL、DB 路徑哨兵、例外哨兵）沒有加反引號，不會被誤取，照 M-9 交給 fixture 提供。

解析時發現的歧義：
1. **錨點自我引用（必須處理）**：tech-writer 套用 M-9 之後，L2410 的標頭本身就用反引號寫了 `` `**推播禁用詞清單**` ``、`` `**白名單例外**` ``。兩個錨點在全檔都各出現 2 次。照子字串找第一個 `**白名單例外**`，會落在標頭那一行，截出來的區塊幾乎是空的。改成「行首縮排 + `- ` + 錨點」比對之後，各恰好 1 次，切得正確。
2. **前言不能一起掃**：起錨點到 A 類標題之間有「單一來源」「詞界」這兩個「」，還有 `ops alert:`、`\b` 兩個反引號，必須排除，只解析各類標題之下的內容。
3. **B 類的「」是舉例，不要取**：「立即」「馬上」「將會」「即將」「命中率」「勝率」「盤中」「實時」「及時」共 9 個，都已在 `FRONTEND_FORBIDDEN_TERMS` 裡（逐一 grep 確認過）。B 類只走既有函式；這 9 個詞可以拿來做「是否為子集」的交叉檢查。B 類內文的 `L374～L486` 行號會漂移，但不被解析，沒有影響。
4. **`\b` 遇到中文的語意（建議寫進「比對規則」）**：Python 的 `re` 預設把中日韓文字視為 `\w`，所以「建議buy今天」用 `\bbuy\b` 抓不到，「片段LM-12」用 A 類 regex 也抓不到。加上 `re.ASCII` 就都抓得到（scratch 實測：False/True 各一組）。建議「比對規則」明寫 `\b` 以 ASCII 字元判定詞界。
5. **「英文不分大小寫」範圍不明**：沒寫清楚是否也適用 F 類（`ALERT_`、`STOCK_DESK_`、`.env`）。我檢查了白名單的事件名稱（ADR-0029 的 `forecast.*`、`ops_alert.selftest`），不分大小寫也不會誤中。建議明寫「適用全部英文項，含 F 類」。
6. A、C、D 類的「」裡目前沒有說明文字，說明都放在全形括號或標題裡；「[stock-desk 警示]」含空格，屬於合法字面。

**3. 產品分支的 merge 會不會讓 docs 路徑不一致**
- 不會。依 CLAUDE.md §1，產品分支不 merge 回 main。main 的 `docs/adr/` 只有 0001、0007，ADR-0027 只存在於 `product/stock-desk` 和從它長出來的 `feat/stock-desk-*`，這些都是完整 checkout，相對 repo 根目錄的路徑一致。
- ADR-0027 的 git 歷史沒有改名紀錄。
- 剩下的小風險：main 日後如果另有編號 0027 的 ADR，`0027-*` glob 會撞到。所以測試應該寫死完整檔名常數，不要用 glob。
- 在清單落檔之前就開出的 feature 分支，跑這支測試會失敗（錨點找不到），rebase 到 product 之後就正常。這是預期行為，合乎 fail-closed。

**最小格式要求（建議寫進 ADR-0029 D-4「單一來源」或 FL-71 (f) 標頭）**
1. 錨點是「行首（縮排後）`- ` 緊接 `**推播禁用詞清單**`／`**白名單例外**`」的清單項，全檔各恰好一個，起錨點在前。其他地方引用錨點字串，不算錨點。
2. 類別標題固定為 `- **X. 名稱**：`，A～F 各恰好一個。標題之前的前言不在取詞範圍內。
3. A、C、D 類的「」只放禁用詞本身，說明一律用全形括號或寫在標題裡。B 類的「」只是舉例，不取詞。
4. A 類 regex 寫成 `` regex `…` ``。C 類英文寫成單行，以「英文，詞界：」開頭，用「、」分隔，每個詞只含 ASCII 字母。
5. F 類反引號只放字面禁用字串，非字面項不加反引號。
6. 「比對規則」補兩點：`\b` 以 ASCII 詞界判定；「英文不分大小寫」適用全部英文項（含 F 類）。

## 驗證

- 解析腳本：`python3 -I /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/parse_fl71f.py "<ADR-0027 路徑>"`
  - 子字串計數為 2／2，改成行首錨點後為 1／1。
  - 取出 A 15 + 1 regex、C 47 + 16、D 12、F 11；regex 可編譯。
- `\b` 語意實測：`re.I` 為 False、`re.I|re.A` 為 True；A 類 regex 不加 `re.A` 為 False、加了為 True。
- B 類 9 個舉例詞，在 `apps/stock-desk/frontend/app/lib/adviceWording.ts` 各 grep 到至少 1 次。
- **ADR-0027 在我確認期間被同時修改**：L2410 的標頭在我兩次讀取之間變了，應是 tech-writer 在套用 M-9。上面的筆數以腳本執行當下的版本為準，行號會漂移。
- 沒有跑 pytest：這次唯讀，還沒有測試程式碼。

## 下一步

1. tech-architect：把上述最小格式要求的第 1 條（必要）和第 6 條（建議）寫進 ADR-0029 D-4「單一來源」，並確認第 3 條（B 類的「」只是舉例）。
2. 風控（知悉級）：「比對規則」補 `\b` 用 ASCII 判定、不分大小寫範圍含 F 類，屬於比對語意的明文化，請確認。
3. devops-sre：把 `docs/adr/0027-*.md` 加進 `.github/workflows/stock-desk.yml` 的 paths 觸發條件（建議和測試同批）。
4. dev-lead（ADR-0029 核可後實作時）：
   - 讀檔用完整檔名常數加 `parents[4]`，錨點用行首比對。
   - 錨點找不到、或 A～D、F 任一類取出 0 筆，測試就失敗。
   - B 類 import 既有的 `load_frontend_forbidden_terms` 和 shared JSON 讀取。
   - 英文比對用 `re.I|re.A`。

相關檔案：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md（FL-71 (f)，約 L2410～L2445）
- /home/user/AICompany/docs/adr/0029-stock-desk-維運告警通道.md
- /home/user/AICompany/work/reviews/2026-10-18-ADR0029審查-tech-architect.md（M-9）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_rules_invalidation_wording.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_f9b_book_cause_group.py
- /home/user/AICompany/.github/workflows/stock-desk.yml
- /home/user/AICompany/apps/stock-desk/backend/Dockerfile
- /home/user/AICompany/apps/stock-desk/backend/.dockerignore
