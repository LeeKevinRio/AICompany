# N-207 規格 v2 補遺 修訂一（RC-59～RC-69）

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：N-207 規格 v2 補遺 修訂一

## 一、本次結論

**做完了。** 修改清單的 6 大項（RC-59、62、63、65、66、67、68、69）都已寫成可以直接貼上的條文，見第二段「N-207 規格 v2 補遺 修訂一（TA 2026-11-10）」。dev-lead 可以把它疊在補遺上出 v3。全程唯讀：沒有執行指令，沒有改檔，沒有讀 `.env`，也沒有碰 `data/*.db`。

**評估摘要（結論先行）**
- **P-9 的 SQL 採 `substr(symbol, -1) = 'K' COLLATE BINARY`，前面加 `typeof(symbol) = 'text'` 守門**。不採 `unicode(substr(...)) = 75`。
  - 對 text 值來說，兩種寫法結果相同。
  - 但依 SQLite 文件，`unicode()` 的引數不是字串時，結果「undefined」。
  - 非 text 的值（BLOB）兩種寫法都判不準，所以另外增列 P-9b 計數非 text 的列，大於 0 就 STOP。
- **suggested 1（既有代號形狀不符也計數）可行，採用為 P-9c**。做法是 9 條 `GLOB`：SQLite 的 GLOB 區分大小寫、整串比對，不需要 REGEXP。另外用參數化測試加性質測試，在 tmp DB 上釘住它與 `symbol_shape_ok` 等價。
- **RC-63**：新增 N207-C21，`high_volatility` 的解析只有一個函式，`type(raw) is int and raw == 1` 才判為已標記。標籤、W-27 旗標與 engine 都只吃這個函式的結果。新增 T30，以直接 SQL 種入 0、1、2、-1、'x'、0.5。`high_volatility_prev` 的部分標「依 D7 修訂」。
- **RC-62、RC-66**：STOP-4 改為回報 TA 與風控，書面裁決記入紀錄之前不得部署。P-4c 大於 0 時，部署通知定稿檔 RC-52 第二段不送出。新增 STOP-5（P-9）。
- **RC-69 (c)**：N207-M3 增列第 (5) 項，ADR-0043 D7 第 1～3 點的修訂經風控確認，列為合併閘。整項標「依 CEO 裁示改寫（若拆單）」。
- **ADR**：不需要新 ADR，也不取代任何 ADR。本修訂沒有改 `READONLY_ALLOWED_BASH`。

**方案比較**

| 議題 | 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|---|
| P-9 判定式 | (a) `substr(symbol,-1) = 'K' COLLATE BINARY`，加 `typeof = 'text'` | 照文件定義，逐位元比較；COLLATE 明寫，qa 可檢查 | BLOB 值要另外處理 | 低 | **採用**，加 P-9b |
| | (b) `unicode(substr(symbol,-1)) = 75` | 整數比較，不涉及 collation | 依 SQLite 文件，非字串引數「結果 undefined」 | 中 | 否決 |
| | (c) `LIKE '%K'` | 簡單 | 對 ASCII 不分大小寫，`2330k` 會被算進去 | 高 | 禁止（補遺確認檔 RC-66） |
| suggested 1 形狀計數 | (a) SQL `GLOB` 9 條，加上與 `symbol_shape_ok` 的等價測試 | 純 SQL，不需要 extension，CEO 本機能跑；GLOB 區分大小寫、整串比對 | 形狀規則有兩份定義，要靠測試釘住 | 低 | **採用** |
| | (b) Python 腳本 import `symbol_shape_ok` | 只有一份定義 | 部署前 CEO 本機還沒有 N-207 的程式；產品線「拉 product 即部署」，先 checkout 就形同部署 | 高 | 否決 |
| | (c) sqlite3 CLI 內建的 `regexp` | 寫法接近 regex | 依版本而定，語法也和 Python `re` 不同，我無法查證 CEO 本機的版本 | 中 | 否決 |
| RC-63 讀取 | (a) 只有 integer 1 判為已標記 | 方向保守（門檻 15%）；符合 ADR 確認檔 RC-56「取較嚴者」 | 外部寫入的異常值會靜默變成未標記，只有盤點的 P-4c 抓得到 | 低 | **採用**（補遺確認檔 RC-63） |
| | (b) 讀到非 0／1 時 raise | 異常會被看見 | 會讓 `/today` 整頁失敗，S 系列停損賣出也跟著出不來 | 高 | 否決，不送風控 |

## 二、各部門回報

### tech-architect（本人，唯讀）

---

# N-207 規格 v2 補遺 修訂一（TA 2026-11-10）

- **疊加對象**：`work/reviews/2026-11-10-N207規格v2補遺-tech-architect.md`（下稱「補遺」）。本修訂覆蓋補遺中與下列各條對應的文字；沒有提到的部分維持原文。
- **依據**：補遺確認檔 RC-59～RC-69。凡是與 ADR-0043 D7 修訂、D7 拆不拆單、ADR-0044 定稿有關的地方，由另一位 TA 處理，本文只標「依 D7 修訂」「依 CEO 裁示改寫」「依 ADR-0044 定稿」。
- **標記**：「〔TA 追加，送風控知悉〕」表示加嚴，風控可以刪。

## 修一-0：引用規則（補遺確認檔 RC-67、RC-69 (e)；v3 全文適用）

1. **檔名簡稱**，v3 來源表與正文一律照下表：

| 簡稱 | 檔案 | RC 範圍 |
|---|---|---|
| 交付 B 風控檔 | `work/reviews/2026-11-10-交付B裁示ADR0044審查與字面定稿-風控.md` | RC-36～RC-47 |
| 補擬四句風控檔 | `work/reviews/2026-11-10-補擬四句裁定-風控.md` | RC-48～RC-51 |
| **部署通知定稿檔** | `work/reviews/2026-11-10-N207部署通知定稿-風控.md` | **RC-52～RC-55** |
| **ADR 確認檔** | `work/reviews/2026-11-10-ADR0044修訂一確認與O1O2裁示-風控.md` | **RC-52～RC-58** |
| 補遺確認檔 | `work/reviews/2026-11-10-規格v2補遺確認與PRD新AC-風控.md` | RC-59～RC-74 |

2. **規則**：
   - RC-52～RC-55 在兩檔重號，一律寫成「部署通知定稿檔 RC-5x」或「ADR 確認檔 RC-5x」，不得只寫「RC-5x」。
   - 其他 RC 也一律附上簡稱。
   - qa-reviewer 以 grep 檢查 v3：`RC-5[2-8]` 的每一筆命中，同一行都要有「部署通知定稿檔」或「ADR 確認檔」，否則判 BLOCKING。
3. **補遺內既有的引用一律改寫**：
   - 補遺寫的「RC-52～55」「RC-52 第二段」「RC-54」「RC-55 必含的五點」，都是指部署通知定稿檔。
   - 待辦編號 TA-TODO-RC55 保留，第一次出現時加註「（部署通知定稿檔 RC-55）」。

## 修一-1：補遺-1 第 5 點改寫（補遺確認檔 RC-59）

> 5. **回退偵測，比照 R2、R3**〔TA 追加 → 補遺確認檔 RC-59 保留，附 required〕
>    - **範圍**：N-209b 一律適用；情況 A 時，N-210a、N-210b（及 N-210c）也適用。
>    - **做法**：每個 `<M_x>`（完整 40 碼）依序執行以下指令。執行者依補遺-3，每條後面接 ` 2>&1; echo "exit=$?"`。
>      - (i) `git rev-parse --verify <M_x>^2^{commit}`：確認 `<M_x>` 是有第二個 parent 的 merge commit。
>      - (ii) `git rev-list <M_x>^1..<M_x>^2`：令 S_x = 輸出 ∪ {`<M_x>`}。
>      - (iii) 對 S_x 的每一個 s 執行 `git log -F --grep=<s> --format=%H <M_x>..<base>`。
>    - **判定**：以下任一成立，判 **BLOCKING**。
>      - (i) 不是 `exit=0`，也就是 `<M_x>` 不是 merge commit；
>      - (ii) 不是 `exit=0`，或沒有輸出；
>      - (iii) 任一條不是 `exit=0`，或有輸出；
>      - 補遺-4 的控制組不符預期。這時 (iii) 的零命中無法判讀。
>    - **(i)、(ii) 不成立時**：回 TA 定 S_x。不得當成「沒有輸出」，執行者與 qa-reviewer 都不得自行補 S_x。
>    - **殘留（記入交件紀錄）**：
>      - 本檢查只偵測得到 commit message 含 S_x 中 SHA 的回退，例如 `git revert` 的預設訊息。
>      - 以一般 commit 手動改回，或 revert 訊息不含 SHA 的回退，偵測不到。
>      - coordinator 把這兩句逐字記入交件紀錄的「殘留」欄；qa-reviewer 檢查紀錄存在，缺少時判 BLOCKING。

**補遺-4 的連動修改**
- 表中 R3d 一列的指令欄改為「補遺-1 第 5 點 (i)～(iii)」。
- 第 3 點的 BLOCKING 清單增列：「**R3d**：依補遺-1 第 5 點的判定」。

## 修一-2：補遺-2 第 1 點改寫（補遺確認檔 RC-68）

> 1. **共同條件（兩種情況都要成立）**
>    - **AC-84 的「風控審過」**：修訂一已經風控確認（ADR 確認檔）；附條件併入後，由 qa-reviewer 核對。
>    - **證據鏈由以下兩份組成，缺一不可**：
>      - (a) ADR 確認檔 RC-52～RC-54；
>      - (b) qa-reviewer 的逐條核對紀錄。它要核對 TA 的 ADR-0044 併入版確實含有兩樣東西：
>        - ADR 確認檔 RC-52 的三項條件：時間相等改判 unknown、交錯測試在現行程式上失敗、寫入者封閉涵蓋原生 SQL；
>        - ADR 確認檔 RC-53 條件 2：`settle` 與 claim 的 SQL 不引用 `td_basis`。
>    - 缺 (b) 時，證據鏈不完整，N-207 不得上線。
>    - 併入版改到審過範圍以外的實質內容（Decision、R-a～R-g、Consequences）時，改動的部分不算審過，要回送風控（補遺確認檔 RC-68 條件 2）。併入版本身依 ADR-0044 定稿。
>    - **CEO 的書面裁示**必須寫明三件事：(a) 修正或接受殘留；(b) (iii-c) 採不採；(c) N-210a、N-210b 與 N-207 部署的先後。
>    - 裁示沒有涵蓋這三件事時，視為未裁示（補遺-1 第 3 點）。

（原句「風控 11-10 的 CONDITIONAL APPROVE 審的是草案；修訂一回送風控確認完成之前，AC-84 不成立」刪除。）

## 修一-3：補遺-11 改寫（補遺確認檔 RC-62、RC-63、RC-65）

### 第 1 點「執行」一句改為

> - **執行**：§9 全部對 CEO DB 的盤點，一律由 CEO 在本機執行，以唯讀模式開啟連線（T-20 第 1 步）。範圍是 **P-1～P-8、P-4a～P-4c、1d、1d-2、P-9（P-9a～P-9c）**（補遺確認檔 RC-65 第 1 點）。

### 第 3 點「輸出形狀的要求」改為

> 3. **輸出形狀的要求**：下列各項在盤點前都要是計數或布林值的形狀，不得有「每檔一列」的輸出。
>    - P-1：批數不等於 bpt 的檔數。
>    - P-2：最大值大於 bpt 的檔數、最小值不等於 1 的檔數、最小值小於 1 的檔數、有斷號的檔數。
>    - P-3：distinct symbol 的檔數，以及 `n_targets` 的值。
>    - P-5：例外的列數。
>    - **1d、1d-2**：各回一個列數，SQL 依 §9 原文（`SELECT COUNT(*)`）。1d-2 照用的前提依 N207-M5（補遺確認檔 RC-65 第 2 點）。
>    - **P-4a、P-4c、P-9a～P-9c**：各回一個計數。
>    - P-6～P-8：各回 0 或 1。

### 第 4 點「判定」與「N-207 的讀取要一致」改為

> - **判定**：
>   - **P-4c 大於 0 → STOP-4**。
>     - 部署暫停，回報 TA **與風控**；書面裁決記入交件紀錄之前不得部署。
>     - 處理方式不以手動修改 DB 進行。
>     - 部署通知定稿檔 RC-52 第二段**不送出**。
>     - STOP-4 處理完之後，CEO 在本機重跑 P-4a～P-4c，依重跑結果組成通知（補遺確認檔 RC-62）。
>   - **P-4c 為 0、P-4a 大於 0 → STOP-3**，處置依第 5 點。
>   - P-4c 為 0 時，`<> 0` 與 `= 1` 等價。依據是 `store.py:124`：INTEGER NOT NULL DEFAULT 0，symbol 是主鍵，所以列數就是檔數。
>   - 依 SQLite 的 affinity 與比較規則推論，P-4c 計到的列一定也在 P-4a 內，所以 P-4c 大於 0 時 P-4a 一定大於 0。T30 會以實測釘住這一點。
> - **盤點與執行期的判定方向不同**：
>   - 盤點用 `<> 0`，多算就多停，方向保守；
>   - 執行期依 N207-C21，只有 integer 1 判為已標記（補遺確認檔 RC-63）。
>   - 兩者在 P-4c = 0 時等價。
> - **第一段不受 P-4c 影響**：部署通知定稿檔 RC-52 第一段照 P-6 的規則送出。如果因此要把第一段、第二段分兩次送，coordinator 送出前要先向風控確認，分送是否在部署通知定稿檔 RC-52 的授權範圍內。

（原句「讀 `high_volatility` 時，非 0 一律判為 True，與 P-4a 一致」刪除。）

### 第 4 點「交件紀錄可以記的內容」改為

> - **交件紀錄與 release note 的記錄範圍**（補遺確認檔 RC-65 第 3 點）：
>   - (1) **與部署通知有關的項目**（部署通知定稿檔 RC-54）：盤點時間、P-6 的布林值、P-4a 的檔數、CEO 確認收到的時間與選項、P-4b 交叉核對的結果（只記「一致」或「不一致」與檔數）。
>   - (2) **§9 其他的布林值與計數**（P-1～P-3、P-4c、P-5、P-7、P-8、1d、1d-2、P-9a～P-9c）：依 AC-90（P-7）、AC-93（P-8）與 release note 記錄。
>   - (3) **共同限制只有兩條**：不含代號、不含金額。

### 第 6 點 TA-TODO-RC55 的驗證句改為〔TA 追加，送風控知悉；對應補遺確認檔 RC-70 對 AC-95 的 suggested〕

> 移除後如何驗證：CEO 在本機重跑 P-4a 得 0，**而且 P-4c 得 0**。

## 修一-4：新增 N207-C21 與 N207-T30（補遺確認檔 RC-63）

**N207-C21 `high_volatility` 的執行期解析（BLOCKING）**

> - **單一解析函式**：`app/playbook/store.py` 定義 `def high_volatility_marked(raw: object) -> bool`，本體恰好是 `return type(raw) is int and raw == 1`。
>   - 只有 integer 1 判為已標記；0、其他整數、TEXT、REAL、BLOB 一律判為未標記，生效值 0，門檻 15%。
>   - 本體不得出現 `bool(`、`int(`、`!= 0`、`> 0`，也不得以真值判斷 raw。以 AST 檢查。
> - **解析時點**：`playbook_symbols.high_volatility` 的原始值，在 store 組 `SymbolState` 之前、而且只經由這個函式轉成 bool。`SymbolState`（pydantic）不得收到原始值。
>   - 理由：pydantic 的 bool 遇到 2、'x'、0.5 會 raise，會讓整頁 500。
> - **共用**：
>   - 交給 engine 的 `high_volatility=`（N207-C15 的 `effective_high_volatility` 輸入）、W-25d～f 標籤、W-27 顯示旗標，三者都只讀 store 回傳的 bool，不得各自另讀原始欄位。
>   - AST／grep 檢查：`app/` 中讀 `high_volatility` 欄位的 SQL 只在 `store.py`；這個函式只定義一次，store 外沒有任何呼叫點。
> - **`high_volatility_prev`**：照同一條規則，以同一個函式解析。欄位存不存在、語意為何，依 D7 修訂。
> - **不採 raise**：讀到異常值不 raise。異常值由盤點 P-4c 與 STOP-4 處理。

**N207-T30（BLOCKING）**

> - 以直接 SQL 種入 `playbook_symbols.high_volatility` = 0、1、2、-1、'x'、0.5，做參數化測試。
> - **前提斷言**：`typeof` 依序為 integer、integer、integer、integer、text、real，確認種入的值沒有被 affinity 轉掉，測試才不會白跑。
> - **斷言**：
>   - 只有 1 判為已標記。
>   - BIAS25 = 18% 時，只有種入 1 的那一檔不觸發 P3，其餘五檔都觸發。
>   - 同一列的 W-25d～f 標籤、W-27 旗標與 engine 的輸入一致。
>   - 全程不 raise。
> - **與盤點交叉**：在同一個 tmp DB 上，執行打包腳本裡的 P-4a、P-4c SQL 原檔（測試直接讀同一個檔案，不是複本），斷言 P-4a = 5、P-4c = 4。
> - 涉及 `high_volatility_prev` 的情境，依 D7 修訂後補上。

## 修一-5：新增 §9 P-9 與 STOP-5（補遺確認檔 RC-66）

**SQL**（唯讀；data-engineer 打包、devops-sre 覆核 SQL 文字；只回計數）：

```sql
-- P-9a: distinct symbols whose last character is ASCII uppercase 'K' (U+004B), case-sensitive
SELECT COUNT(*) FROM (
  SELECT symbol FROM playbook_batches
  UNION
  SELECT symbol FROM playbook_symbols
) AS u
WHERE typeof(u.symbol) = 'text'
  AND substr(u.symbol, -1) = 'K' COLLATE BINARY;

-- P-9b: distinct symbols not stored as TEXT (the P-9a predicate cannot judge them)
SELECT COUNT(*) FROM (
  SELECT symbol FROM playbook_batches
  UNION
  SELECT symbol FROM playbook_symbols
) AS u
WHERE typeof(u.symbol) <> 'text';

-- P-9c: distinct TEXT symbols that are not K-suffixed and fail the shape rule
SELECT COUNT(*) FROM (
  SELECT symbol FROM playbook_batches
  UNION
  SELECT symbol FROM playbook_symbols
) AS u
WHERE typeof(u.symbol) = 'text'
  AND NOT (substr(u.symbol, -1) = 'K' COLLATE BINARY)
  AND NOT (
       u.symbol GLOB '[1-9][0-9][0-9][0-9]'
    OR u.symbol GLOB '[1-9][0-9][0-9][0-9][A-JL-Z]'
    OR u.symbol GLOB '00[0-9][0-9]'
    OR u.symbol GLOB '00[0-9][0-9][A-JL-Z]'
    OR u.symbol GLOB '00[0-9][0-9][0-9]'
    OR u.symbol GLOB '00[0-9][0-9][0-9][A-JL-Z]'
    OR u.symbol GLOB '00[0-9][0-9][0-9][0-9]'
    OR u.symbol GLOB '00[0-9][0-9][0-9][0-9][A-JL-Z]'
    OR u.symbol GLOB '91[0-9][0-9][0-9][0-9]'
  );
```

**條文**

> 1. **P-9a**（補遺確認檔 RC-66 required-1）：批次表與 `playbook_symbols` 中，最後一個字元是 ASCII 大寫 `K` 的 distinct symbol 檔數。
>    - 區分大小寫，**不得使用 `LIKE`**。
>    - `COLLATE BINARY` 必須明寫，不得省略。依 SQLite 規則，這裡本來就是 BINARY；明寫是為了讓 qa 可以檢查。
>    - 依 SQLite 文件推論的行為：`substr(X, -1)` 對 text 以字元計，所以全形 `Ｋ`、小寫 `k`、結尾空白或換行都不會被算進去，開頭有空白的 ` 00625K` 會被算進去。這與補遺-7 的 `symbol_k_suffix`（`str.endswith("K")`）一致。
> 2. **P-9b**〔TA 追加，送風控知悉〕：symbol 不是 TEXT 儲存類別的檔數。
>    - 兩張表的 symbol 欄宣告為 TEXT，整數寫入時會被轉成 text，但 BLOB 會保留原樣，P-9a 判不準這種列。
>    - 這類列只可能來自 app/ 以外的寫入。
> 3. **P-9c**（補遺確認檔 RC-66 suggested 1；TA 評估可行，採用，送風控裁示）：不是 K 結尾、而且不符形狀規則的 TEXT 代號檔數。
>    - 與 P-9a、P-9b 不重疊，判定順序與補遺-7 相同：先判 K，再判形狀。
>    - 9 條 GLOB 是 `[1-9][0-9]{3}[A-JL-Z]?|00[0-9]{2,4}[A-JL-Z]?|91[0-9]{4}`（fullmatch）的逐一展開。GLOB 區分大小寫，而且整串比對，所以結尾換行不會被放行。
>    - 實際合入的 `symbol_shape_ok` 規則若有變動，P-9c 要同一個 PR 一起改，並由 N207-T31 釘住。
>    - 已知代價：形狀規則目前是 `verified=False`。CEO DB 若有合法、但規則沒涵蓋的代號，會誤停。方向保守。
> 4. **判定**：P-9a、P-9b、P-9c 任一大於 0 → **STOP-5**。
> 5. **理由**：補遺-7 只檢查新代號；重新加入與開新輪沿用批次表中既有的代號，不經過 K 與形狀檢查。既有的不合格代號會繞過 RC-43（交付 B 風控檔）與 FR-5。

**N207-T31 P-9 SQL 的等價測試（BLOCKING）**

> - 在 tmp DB 上執行打包腳本裡的 P-9a～P-9c SQL 原檔（測試直接讀同一個檔案，不是複本）。
> - **P-9a 種入**：
>   - 要算進去：`00625K`、`2330K`、`ABCK`、` 00625K`；
>   - 不算：`2330k`、`00625Ｋ`、`00625K `、`00625K\n`、`2330`。
>   - 同一個代號同時在兩張表時只算一次；只出現在批次表的也要算進去。
> - **P-9b 種入**：以 BLOB `x'30303632354B'` 種入一列，斷言 P-9b = 1，而且 P-9a 不把它算進去。
> - **P-9c**：
>   - data-engineer 形狀規則檔第 4 節的 P01～P20、N01～N27，逐一斷言「SQL 判為不符形狀」等價於「`not symbol_k_suffix(s) and not symbol_shape_ok(s)`」；
>   - 再跑性質測試至少 300 組 seed。字元集為 `0-9`、`A-Z`、`a-z`、`Ｋ`、`０`、空白、`\n`、`.`，長度 0～8；斷言同一個等價關係。
> - **P-9a 的性質測試**：至少 300 組 seed，斷言 SQL 判定與 `symbol_k_suffix` 一致。

**STOP 表增列**

| STOP | 觸發 | 處置 | 依據 |
|---|---|---|---|
| STOP-5 | P-9a、P-9b、P-9c 任一大於 0 | 部署暫停，回報 TA 與風控；書面裁決記入交件紀錄之前不得部署。處理方式不以手動修改 DB 進行。只回計數，不回代號。處理完之後，CEO 在本機重跑 P-9a～P-9c | 補遺確認檔 RC-66；P-9b、P-9c 為 TA 追加或評估 |

## 修一-6：§9.3 在 v3 的替換條文（補遺確認檔 RC-62、RC-65、RC-67）

1. **v2 :355「執行方式」整句移除**，改為：
   > - **執行方式**：§9 全部對 CEO DB 的盤點（P-1～P-8、P-4a～P-4c、1d、1d-2、P-9a～P-9c），一律由 CEO 在本機執行，以唯讀模式開啟連線（T-20 第 1 步）。
   >   - 只回傳布林值或計數，不回代號、不回金額，沒有例外。P-4b 的輸出只留在 CEO 本機的畫面。
   >   - 任何 agent 都不得對 CEO DB 執行查詢（R12）。
   >   - 判定 SQL 由 data-engineer 打包成腳本、devops-sre 覆核。覆核只看 SQL 文字，不接觸 DB。
   >   - P-4a～P-4c、P-6～P-8、1d、1d-2、P-9a～P-9c 的 SQL 由 TA 給出。
   >   - 記錄範圍依補遺-11 第 4 點（修一-3）。
2. **P-4 列**由 P-4a、P-4b、P-4c 三列取代，SQL 與判定依補遺-11 第 4 點（修一-3）。
3. **v2 :369 P-6 列的舊句「首次設定後，只能經 REBALANCE 解開待生效」移除**，處置欄改為：
   > 不是 STOP。結果記入交件紀錄。為真時，發出部署通知定稿檔 RC-52 第一段（FR-53、AC-92）；CEO 第一次使用「設定標的名單」之前，必須送達並有書面確認收到。
4. **增列 P-9a、P-9b、P-9c 三列**，依修一-5。
5. **STOP-3 列的處置欄改為**：
   > 部署暫停。通知改用部署通知定稿檔 RC-52 第二段：不列代號，以 `{P4_COUNT}` 交叉核對。P-4c 大於 0 時先處理 STOP-4，第二段不送出。CEO 書面確認收到並裁示之前不得部署，紀錄記入交件紀錄。
   > - 保留標記：名單頁常駐 W-27（後端旗標驅動）。
   > - 取消標記：照部署通知定稿檔 RC-55 必含的五點，移除方式依 TA-TODO-RC55（部署通知定稿檔 RC-55），不以手動修改 DB 進行。
   > - 甲案只在 app 單一使用者時成立。
6. **STOP-4 列改為**：
   - 觸發：「P-5 有例外，或 P-4c 大於 0」。
   - 處置依補遺-11 第 4 點（修一-3）：回報 TA 與風控，書面裁決記入交件紀錄之前不得部署。
   - P-5 觸發時也回報風控。〔TA 追加，送風控知悉：補遺確認檔 RC-62 是對 STOP-4 整體寫的，這裡照字面一體適用〕
7. **v2 :434 改為**：
   > - **STOP-1～STOP-5 全數未觸發，且 P-7、P-8 已依上表處理**：release note 記錄 P-1～P-8、P-4a、P-4c、1d、1d-2、P-9a～P-9c 的計數或布林值，不含代號、不含金額。

## 修一-7：補遺-8 的更正（補遺確認檔 RC-67、RC-69）

- **第 1 點 來源表**改為：
  - PRD v3.4（3c1de93）；
  - 交付 B 風控檔 RC-36～RC-47；
  - 補擬四句風控檔 RC-48～RC-51；
  - **部署通知定稿檔 RC-52～RC-55**；
  - **ADR 確認檔 RC-52～RC-58**；
  - 補遺確認檔 RC-59～RC-74；
  - ADR-0044 修訂一（依 ADR-0044 定稿）；
  - 補遺及本修訂一；
  - 附錄 C 全部吸收後刪除。
  - 兩套 RC-52 各列一列，不得合併（補遺確認檔 RC-69 (e)）。
- **第 7 點**：「RC-52 定稿」改為「部署通知定稿檔 RC-52」。
- **第 10 點**：「（RC-52～55）」改為「（部署通知定稿檔 RC-52～RC-55）」；「RC-52 第二段」改為「部署通知定稿檔 RC-52 第二段」。
- **第 13 點 W-25f**改為：
  > 定稿（TA 2026-11-10 確認、ADR 確認檔 RC-58 確認）。§6 加後端顯示條件 W25f-1～3（判定式、參考日 `today_tpe`、{M}/{D} = `next_trading_day(changed_on)`）。O-1 已由 ADR 確認檔 RC-55 裁示，O-2 已由 ADR 確認檔 RC-56 裁示。D7 修訂之後，TA 要重新核對 W25f-1～3 與 W-25d、W-25e 的顯示條件（依 D7 修訂）。

- **第 14 點**改為（字面以程式從風控原檔逐字比對，N207-C16 適用；以下引文只供對照，比對來源以原檔為準）：
  > **W-27**：改用 ADR 確認檔 RC-55 的預核全文，顯示條件不變：
  > 「P3 過熱減碼的門檻：已適用高波動者為 BIAS25（收盤對 25MA 的乖離）大於 20%，其餘為大於 15%。本頁以各列的高波動標籤表示是否已適用，依台北日期判定；今日頁的評估依資料日判定，資料日早於台北今日時，今日頁使用的門檻可能與標籤所示不同。」
  >
  > **W-22 第一行**：改用補遺確認檔 RC-72 的預核全文：
  > 「組合凍結時，名單變更入口依台北日期判定，今日頁依資料日判定；資料日早於台北今日時，名單變更入口的凍結判定可能已結束，而今日頁仍處於凍結。名單變更不會讓凍結提早解除。」
  >
  > **W-22 第二行**：改用 ADR 確認檔 RC-55 的預核全文，常駐，不依 W-27 旗標顯示：
  > 「本頁的黑名單效期與高波動標籤依台北日期判定；今日頁的評估依資料日判定，資料日早於台北今日時，兩者可能不同。」
  >
  > 以上三句都是 N-207 前端合併前必須完成的事。D7 修訂之後，TA 要核對 W-27 預核全文與部署通知定稿檔 RC-52 第二段的「自部署起適用，沒有緩衝期」「由大於 15% 改為大於 20%」，有變動就回風控（補遺確認檔 RC-69 (d)；依 D7 修訂）。

- **第 16 點 N207-M3 狀態行**改為：
  - W-24：預核定稿（補擬四句風控檔 RC-48）；
  - W-05m：定稿（補擬四句風控檔 RC-50）；
  - W-10：B 版定稿（補擬四句風控檔 RC-51）；
  - W-25f：定稿（ADR 確認檔 RC-58）；
  - W-27：預核全文（ADR 確認檔 RC-55）；
  - W-22：第一行預核（補遺確認檔 RC-72），第二行預核（ADR 確認檔 RC-55）；
  - W-19：仍待 `round_spans` 落地；
  - N9-07 第二階段：由 N-207 PR 接上。
- **增列第 20 點**：N207-M3 加第 (5) 項，依修一-8。
- **增列第 21 點**：下列依附 ADR-0043 D7 的條文，在 v3 中逐處標「依 D7 修訂」：
  - `high_volatility_prev`、`high_volatility_changed_on` 兩個欄位；
  - `effective_high_volatility` 的簽名；
  - N207-C15；
  - N207-T14；
  - W-25d～f 與 W-27 的顯示旗標；
  - N207-C21 的 prev 句；
  - P-4 與部署通知第二段的事實。
- **增列第 22 點**：補遺-11、§9.3 依修一-3、修一-5、修一-6 改寫；新增 N207-C21、N207-T30、N207-T31，併入 §7、§8。

## 修一-8：N207-M3 增列第 (5) 項（補遺確認檔 RC-69 (c)）〔若 CEO 決定拆單：依 CEO 裁示改寫〕

> (5) **ADR-0043 D7 第 1～3 點的修訂經風控確認的書面紀錄**（ADR 確認檔 RC-56；補遺確認檔 RC-69 (c)）。
> - 修訂本體依 D7 修訂。
> - CEO 若先核可 ADR-0043 的其餘段落，第 (1) 項的核可紀錄必須明示排除 D7 第 1～3 點，並標「待修訂（O-2）」（ADR 確認檔 RC-56）。
> - (1) 與 (5) 都具備，M3 才成立。產品線合併即部署，所以這也是部署閘。
> - 若 CEO 決定把 D7 從 N-207 拆出，本項與修一-7 第 21 點所列的條文依 CEO 裁示改寫。FR-46、W-25d～f、W-27、P-4 與通知第二段的事實要重新核對，再回風控。

## 修一-9：補遺-7 第 5 點增列〔附帶，補遺確認檔 RC-66 接受的殘留〕

> 5. **接受的殘留**（補擬四句風控檔 RC-50；補遺確認檔 RC-66）：
>    - `ABCK` 一類的輸入，以及開頭有空白的 ` 00625K`，都只會收到 W-05m，不會被告知有空白。整批拒絕、零寫入。
>    - 兩者一併記入交件紀錄的「殘留」欄。

---

### 其他部門
- 本次沒有參與：product-manager、dev-lead、frontend-engineer、data-engineer、devops-sre、qa-reviewer、qa-e2e、risk-compliance-officer、tech-writer、creative-lead 等。
- 這是 TA 的條文修訂，不是使用者面向的文案。引用的字面全部是風控已經預核的原文，本修訂沒有新擬任何字面，所以不另送風控審字面。〔TA 追加〕各點要送風控知悉，見第四段。

## 三、驗證

- **讀過的文件**：
  - 全文：補遺；補遺確認檔；ADR 確認檔；部署通知定稿檔；data-engineer 形狀規則檔。
  - 部分：v2 規格 :56-75、:276-435，以及 grep D7、W-27、`high_volatility_prev`。
- **讀過的程式**（唯讀）：
  - `store.py:68-150`：`playbook_batches.symbol TEXT NOT NULL`、`playbook_symbols.symbol TEXT PRIMARY KEY`，兩者都沒有宣告 COLLATE；`high_volatility INTEGER NOT NULL DEFAULT 0`。
  - grep `backend/`：現行 store 沒有讀取 `high_volatility`；`SymbolState`、`MarketSnapshot` 的欄位是 `bool`；engine 在 `engine.py:487` 依 bool 選門檻。
- **沒有查證的部分**：我沒有 Bash，以下 SQLite 行為都是依文件推論，沒有實跑，交 T30、T31 在 tmp DB 上實證：
  - `substr(X,-1)` 對 text 以字元計；
  - UNION 去重與 `=` 預設使用 BINARY；
  - GLOB 區分大小寫、整串比對、支援 `[A-JL-Z]`；
  - `unicode()` 遇到非字串引數時結果 undefined；
  - INTEGER affinity 會把 '1'、1.0 轉成 integer 1，把 0.5、'x' 保留原樣；
  - P-4c 計到的列一定也在 P-4a 內。

  T31 的 BLOB 字面值是我手算的 hex，dev-lead 實作時要以 `typeof` 斷言確認。CEO 本機 DB 的狀態不明。
- **給 qa-reviewer 的可檢查項**：
  - 修一-0 第 2 點的 grep 規則；
  - N207-C21 的 AST；
  - T30、T31 讀的是盤點腳本的原檔，不是複本；
  - v3 中沒有 v2 :355、:369 的舊句。
- 沒有讀 `.env`，沒有碰 `data/*.db`，沒有執行任何指令，沒有改任何檔案。

## 四、下一步

1. **dev-lead**：依本修訂加補遺出 v3，移除 v2 的 :355、:369；附錄 B 增列覆蓋紀錄。
2. **risk-compliance-officer（知悉並可刪除）**：
   - P-9b、P-9c，以及 P-9c 是否觸發 STOP-5；
   - STOP-4 在 P-5 觸發時也回報風控；
   - 補遺-1 第 5 點的 (i) `rev-parse` 檢查；
   - TA-TODO-RC55 的驗證加上 P-4c = 0；
   - P-4c 為真時第一、二段分送的授權問題。

   另外兩項 suggested 本修訂沒有吸收，交 PM 與 creative-lead 決定：補遺確認檔 RC-66 suggested 2（bidi `unicode-bidi: isolate`）與 suggested 3（AC-91 的 Given）。
3. **data-engineer、devops-sre**：把 P-4a～P-4c、P-9a～P-9c、1d、1d-2 打包成計數形狀的 SQL 檔，讓 T30、T31 直接讀同一個檔案。
4. **另一位 TA、CEO**：
   - D7 修訂與拆單裁示完成後，回頭改寫修一-8 與修一-7 第 21 點的「依 D7 修訂」「依 CEO 裁示改寫」各處；
   - ADR 確認檔 RC-57 條件 3（同一讀取交易）不在本修訂範圍，仍待 TA 回覆。

相關檔案：
- /home/user/AICompany/work/reviews/2026-11-10-N207規格v2補遺-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-10-規格v2補遺確認與PRD新AC-風控.md
- /home/user/AICompany/work/reviews/2026-11-10-ADR0044修訂一確認與O1O2裁示-風控.md
- /home/user/AICompany/work/reviews/2026-11-10-N207部署通知定稿-風控.md
- /home/user/AICompany/work/reviews/2026-11-10-N207實作規格v2彙整-dev-lead.md（:355、:369、:411-434）
- /home/user/AICompany/work/reviews/2026-11-10-N207台股代號形狀規則-data-engineer.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py（:68-150）

---

## coordinator 實測（2026-11-10，Python sqlite3 3.45.1，`:memory:` 暫存 DB，不碰任何產品 DB）

- **P-9a**：種入 `00625K`、`2330K`、`ABCK`、` 00625K`、`2330k`、`00625Ｋ`、`00625K `、`00625K\n`、`2330`，批次表另有 `9999K`、`00625K`。
  - 結果：5，預期 5。其中 `00625K` 同時出現在兩張表，只算 1 次。
- **P-9b**：種入 BLOB `x'30303632354B'`。
  - 結果：P-9b = 1，P-9a 沒有把它算進去。
- **`LIKE '%K'`**：對 `2330k` 回 1。證實 LIKE 不分大小寫，不能用（補遺確認檔 RC-66）。
- **GLOB**：
  - `'2330k' GLOB '[1-9][0-9][0-9][0-9][A-JL-Z]'` 回 0；
  - `'2330B'` 回 1；
  - `'2330\n' GLOB '[1-9][0-9][0-9][0-9]'` 回 0。
  - 證實 GLOB 區分大小寫，而且整串比對。
- **INTEGER affinity**：種入 0、1、2、-1、'x'、0.5、'1'、1.0。
  - typeof 依序為 integer×4、text、real、integer、integer，也就是 '1' 與 1.0 都轉成 integer 1。
  - P-4a = 7，P-4c = 4，與 TA 的推論一致。
  - T30 只種前六個值時，預期 P-4a = 5、P-4c = 4，成立。
- 本實測只是佐證，不取代 T30、T31。
