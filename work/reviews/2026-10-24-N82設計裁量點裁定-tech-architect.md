# N-82 方案 A 設計裁量點裁定（含 qa M-1、M-2、L-3）

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

五個裁量點我都裁定了，coordinator 補交的 qa M-1、M-2、L-3 也一併處理。總結是要改程式，但所有改動都在 ADR-0005 I-3 註記的範圍內，不構成「超出本註記的情形」，不必修訂 I-3。其中有兩處要另案補 ADR-0027 D-3 修訂（我起草，送風控），才能實作 `replay_checks.py`。閘門 (b) 本來就被 N-82 與 #49 擋著，這次沒有放寬。

| 點 | 裁定 | 一句話 |
|---|---|---|
| 1 多視窗（含 qa M-2） | **修改**：改成永遠單請求，請求區間前後各多請求一天 | 多視窗沒有違反 (5a)～(5e)。改掉的原因是 1096 沒有依據，[S, E] 很可能遠長於 1096 天，而且視窗邊界會在 N-82 改用台北日期後靜默掉列 |
| 2 null 列（含 qa M-1） | **修改**：「null 缺口」和「畸形列」分開處理。缺口照常排除，但要逐列交回；畸形列讓整次失敗 | 這次就要做 adapter 與 service 端；快照要怎麼存，須先修 ADR-0027，一律在閘門 (b) 之前完成 |
| 3 非整數時間戳記 | **不採用**在 adapter 拒絕；維持保留原樣，另附下游約束 | ADR-0027 D-3 明文「不是整數時照原樣存」，交給 (5a) 判定。在 adapter 拒絕等於先看內容再決定存不存，ADR-0027 禁止這樣做 |
| 4 service 不吞例外 | **採用**，附 `replay_checks.py` 約束 | ADR-0027 snapshot 列「`detail_json` 帶例外類別」本來就預設例外會傳到 `replay_checks` |
| 5 單一 `as_of` | **採用**它當快照的 `as_of`；**修改**：每份回應另帶 `received_at`，對應到 `fetched_at` | PIT 證明靠閘門順序，單一 `as_of` 夠用；但把呼叫開始的時刻寫成「取得時間」名不副實 |
| L-3 `source="none"` | **修改**：改為 `None` | 這個字串容易被當成來源名稱寫進 `fetch_failed` 列 |

## 各部門回報（tech-architect）

### 第 1 點：多視窗（併 qa M-2）

**先回答前提：多視窗沒有違反單一快照，也沒有違反 (5a)～(5e)。**
- 單一快照指存成一份快照、一個 sha256。ADR-0027 D-3 規定 `response_seq` 在同一份快照內自 1 起算，ADR-0005 註記寫「多份回應中任一份失敗」，兩者本來就容許一份快照有多份回應。
- (5a) 要求「每一列」的台北時刻全部相同，(5e) 的 B 是「快照全部列」的日期集合。兩款都跨回應判定。
- (5c) 逐份回應檢查 meta。
- 所以多份回應若慣例不一致，(5) 會擋下，結果仍是往安全的方向。

**方案比較**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A 保留 1096 天均分（現況） | 萬一 Yahoo 對長區間截斷或降頻，有防護 | 1096 沒有任何 Yahoo 端依據；請求數、`response_seq`、`content_sha256` 都跟著常數變，要登記 | ① S 是 TWSE 官方來源的 `coverage_start`（事先宣告「重放期的起訖日」），[S, E] 很可能多年，多視窗會是常態，不像實作者說的「大多 ≤ 1096」。② 視窗的請求邊界用 UTC 午夜，列又依推導日期過濾，兩者只在 UTC 推導下才一致。N-82 清單本身就排了「以 `exchangeTimezoneName`／`gmtoffset` 取台北當地日期」，一旦落地，台北 00:00 的列（UTC 前一日 16:00）會由前一窗傳回、卻被前一窗的過濾排除，下一窗又不會傳回它，就在快照中間靜默消失，(5e) 與 X2 都看不到。③ 任一窗回錯，整次失敗，一份快照又只能取一次 |
| **B 永遠單請求，請求區間前後各多一天（採用）** | 一次回應、一份 meta，沒有內部邊界；請求區間和日期推導方式脫鉤，N-82 改日期慣例也不掉列；不需要登記常數 | 如果 Yahoo 真的會截斷長區間，這個方案擋不住 | 截斷的風險交給 #49 實測：補一題「以接近 [S, E] 長度的單一請求取 `^TWII`，確認是日線密度、沒有截斷」。如果不成立，在閘門 (b) 前重開：改回多視窗，視窗也前後各多請求一天，常數與切分規則登記進 ADR-0027 D-3 |
| C 保留多視窗並前後多請求一天 | 同時防截斷與邊界掉列 | 複雜度最高，而它防的截斷問題目前沒有證據 | 等 #49 證實需要再說 |

**對 data-engineer 的具體要求**
- 刪除 `RAW_CHART_MAX_WINDOW_DAYS` 與 `_split_windows`。`get_index_raw_responses` 永遠只發一次請求，`response_seq = 1`。
- 呼叫 `_request_chart_result(index_symbol, start - 1 日, end + 1 日)`；`_raw_bars` 照舊以推導出的 `session_date ∈ [start, end]` 過濾。
- 既有的 `_fetch` 與 `get_index_daily_bars` 的請求區間不動。
- 回傳型別仍是「多份回應的 tuple」，不要改。service 對 1..n 序號與「任一份失敗」的驗證保留，改用假 provider 測試。這是 ADR-0027 D-3 規定的形狀，ADR-0005 註記「多份回應中任一份失敗」由 service 層承擔。
- 新增測試格：
  - (1-a) 20 年的區間，transport 恰好收到 1 個請求；`period1` 是 `start − 1` 日的 UTC 午夜，`period2` 是 `end + 2` 日的 UTC 午夜。
  - (1-b) 推導日期為 `start − 1` 與 `end + 1` 的列不在 bars 內。
  - (1-c) 原本的「第二份失敗」各格移到 service 層，用假 provider 構造。
  - (1-d) 檔頭 docstring 刪掉多視窗的說明。

**是否超出 ADR-0005 註記**：否。仍是 yfinance、同一個代號、只走即時、不讀快取。M-2「記入 ADR」的需求因常數刪除而消失。

### 第 2 點與 qa M-1：null 缺口和畸形列分開處理

**現況的影響**
- 被略過的列不在快照列集合內，(5a)、(5b) 看不到它們的時間戳記，B 也少了這些日期。
- (5e) 只比較平移前後的計數，少數缺列通常不會翻轉結果，所以閘門 (c) 多半照樣會過。結果就是快照靜默缺列、閘門照過。
- 只缺 volume 的列，連 close 也一起丟掉。
- 依 CPython 行為推論（未實跑，跟 qa 的推斷相同）：毫秒級時間戳記觸發 `ValueError`，會被略過；`10**30` 觸發 `OverflowError`，卻整次失敗。同一類錯誤處理不一致。
- ADR-0005 註記的 fail-closed 條列有「回應無法解析」，畸形列依字面屬於這一條。

**裁定**

raw 路徑把每一列分成三類，判定在 `_raw_bars`（或新增一個 raw 專用的分類函式）：

1. **畸形 → 整次失敗**。只要有任一列符合以下情形，整次失敗（不限是否在範圍內，因為畸形列的日期本來就不可信）：
   - `timestamp` 與五個 OHLCV 陣列長度不一致。`or []` 造成的空陣列也算在內。
   - 時間戳記是 `None` 或 `bool`。
   - `int(ts)` 失敗。
   - 推導日期時拋出 `ValueError`／`OverflowError`／`OSError`。
   - 非 null 的值轉 `Decimal` 或 `int` 失敗。

   這些情形一律回同一句 reason，例如「yfinance 回應含無法解析的列，暫不可用。」
2. **null 缺口 → 排除但逐列交回**。條件是時間戳記可推導出日期、日期落在 [start, end]，而且五個 OHLCV 中至少一個是 null。這類列不進 bars，改放進 `RawChartResponse.null_gap_rows`。每項帶 `raw_timestamp`（原值）、`session_date`、`null_fields`（依 open、high、low、close、volume 的順序，列出是 null 的欄位名稱）。
3. **正常列**：照舊。

日期推導仍只能有一處：
- 把 `fromtimestamp` 抽成 `_derive_session_date(ts)`。呼叫它的只能是 `_parse_chart_row` 與 raw 分類函式。
- `_parse_chart_row` 內「先檢查 None、再推導」的順序不變，所以既有路徑不會因此在 null 列上拋出 `OverflowError`。
- AST 測試改為釘「`fromtimestamp` 恰一處、位於 `_derive_session_date`、呼叫端恰為上述兩者」。

service 一側：
- `ReplayChartResponseLike`、`ReplayIndexResponse` 加 `null_gap_rows`，原樣轉交。新的型別名稱要納入 (a) 呼叫點封閉的掃描。
- 「每份回應至少有一根 bar」的規則不變：只有缺口、沒有 bar，照樣失敗。
- 既有路徑（`_parse_row`／`_parse_result`）完全不動。

**時程**
- adapter 與 service 的改動，在本輪就做。
- 快照怎麼存要先修 ADR-0027。D-3 的 `response_meta_json` 寫的是「每一項恰為三個鍵」，加缺口列必須修訂，修訂範圍見「下一步」。
- 兩者都必須在閘門 (b) 之前完成。快照只能取一次，取了之後被略過的列就無法補回，所以不能拖到閘門 (b) 之後。
- 後續追蹤清單上 N-82 其餘各項（台北日期、去重、擋盤中半成品 bar）的擋點仍是閘門 (b) 之前，我不建議放寬。

**新增測試格（MockTransport）**
- 整次失敗，reason 用關鍵字斷言，順帶解決 qa L-2：
  - (2-a) 一列毫秒時間戳記，其餘正常。
  - (2-b) `10**30`，reason 與 (2-a) 相同。
  - (2-c) close 陣列比 timestamp 短 1。
  - (2-d) 缺 volume 鍵。
  - (2-e) close 值是 `"abc"`。
  - (2-f) 中間一列時間戳記是 null。
  - (2-g) 時間戳記是 `true`。
  - (2-h) 畸形列落在請求多出的那一天，也就是範圍外。
  - (2-i) 全 null 的缺口列，但時間戳記是毫秒級。
- 成功（BACKUP）：
  - (2-j) 範圍內一列全 null，該列不在 bars 內；`null_gap_rows` 恰一項，`null_fields` 為五個欄位名稱，`raw_timestamp` 是原值。
  - (2-k) 只缺 volume，`null_fields == ("volume",)`。
  - (2-l) 缺口列推導日期為 `start − 1`，不列入 `null_gap_rows`。
- (2-m) service 原樣轉交 `null_gap_rows`。
- (2-n) 回歸：`get_index_daily_bars` 對 (2-a)、(2-c)、(2-e)、(2-j) 的 payload 行為與改動前相同。

**是否超出 ADR-0005 註記**：否。畸形列整次失敗正好落實註記的「回應無法解析」；多交回一個欄位，沒有讓註記任何一個條件失效。

### 第 3 點：非整數時間戳記，不在 adapter 拒絕

**不採用 fail-closed 的理由**
- ADR-0027 D-3 寫「整數照存；不是整數時照原樣存」，事先宣告 §4.7 v0.26 註也寫「照回應原值」「由第 (5) 項判定」。
- 如果 adapter 拒絕，結果會變成 `fetch_failed`，而 `fetch_failed` 之後可以再取。這等於依內容挑選要不要存（違反 ADR-0027「不得先檢視內容再決定是否寫入」），也會讓 (5a) 該記下的證據消失。
- 只有無法推導日期的時間戳記（`int()` 失敗、None、bool），才依第 2 點算畸形、整次失敗。這不衝突：這種列根本產生不了 `session_date`。ADR-0027「缺漏為 null」在這條路徑上實際不會出現，我會在下述 ADR-0027 修訂中註明。

**給 dev-lead 實作 `replay_checks.py` 與閘門的約束**
- (3-a) 序列化要保留型別：
  - 整數存成 JSON 整數；`Decimal` 存成原字面的 JSON 數字（例如 `1704182400.0`，用 `str(Decimal)`）；字串存成 JSON 字串。
  - 讀回時用 `parse_float=Decimal`，`1704182400.0` 才不會變回整數。
  - `content_sha256` 對三者必須不同。
- (3-b) (5a) 的「是整數」判定為 `type(x) is int`：排除 `bool`，任何 `Decimal`（包括 `1704182400.0` 這種整數值）都不成立。這和 (5c)「字串或其他型別視同不成立」一致，是嚴格讀法，不是改條件。
- 每一條都要有測試格。

### 第 4 點：service 不吞例外，採用

- 例外往上拋時不回傳任何 bar，本身就是 fail-closed；ADR-0027 的「`detail_json` 帶例外類別」也預設 `replay_checks` 看得到例外。
- 如果在 service 用 `except Exception` 全部吞掉，程式錯誤會和來源失敗混成同一種 `UNAVAILABLE`，例外類別也就無從記錄。

**給 `replay_checks.py` 的約束**
- (4-a) 以 `except Exception` 接住 `fetch_replay_index_snapshot` 拋出的例外，寫一列 `fetch_failed`：`detail_json` 帶例外類別，並附中文原因（ADR-0005 註記要求「附中文原因」）。不寫任何 `forecast_input_series` 列。
- (4-b) 同一個呼叫內不自動重試。每次嘗試，包括拋例外的那次，都各留一列（取數嘗試次數列入 §4.7 揭露）。

第 2 點把日期推導的 `ValueError` 也收進整次失敗之後，程式錯誤（例如 `AttributeError`）仍會照常往上拋。

### 第 5 點：`as_of` 與 `fetched_at`

- 重放的 PIT 證明，靠的是閘門順序：先 (a) 以 commit 登記，F 之後才進行 (b)，「快照中的 bar 都晚於 E 的 `final_after`」【推論，依閘門順序】。不靠每列的時間。
- 單一 `as_of` 取在呼叫開始，一定不晚於實際收到回應的時刻。拿它證明「晚於某個門檻」，方向是保守的。所以 `as_of` 本身夠用。
- 但 ADR-0027 的 `fetched_at` 語意是「取得時間」，直接寫成呼叫開始的時刻名不副實。

**要求**
- (5-a) adapter：`RawChartResponse.received_at` 在 `_request_chart_result` 成功返回後立即取 `datetime.now(UTC)`。service 原樣轉交。
- (5-b) 測試：`as_of ≤ received_at ≤ 呼叫結束後讀到的時鐘`；service 原樣轉交。
- (5-c) `replay_checks` 的對應：每一列的 `as_of` 取快照的 `as_of`，`fetched_at` 取該列所屬回應的 `received_at`。寫入時斷言 `as_of ≤ fetched_at ≤ 寫入時的 store 時鐘`。這個對應記入下述 ADR-0027 修訂。

### L-3：`source="none"`，修改

- `ReplayIndexSnapshot.source` 改為 `str | None`。不支援的代號分支不會發出請求，所以為 `None`。其他分支取 provider 回報的值。
- docstring 寫明：`None` 代表沒有聯絡任何來源，`replay_checks` 不得把它當成來源名稱寫入。
- 測試：不支援的代號時 `source is None`；成功與失敗時都等於 provider 回報的值。

### 是否構成「超出本註記的情形」

以上全部都不構成。沒有讀寫快取，沒有標 `FRESH`，輸出去向不變，沒有退回快取或改換來源、代號，仍是 yfinance，也仍只有一個呼叫端、一個代號。

需要另案修訂的是 **ADR-0027 D-3**（不是 ADR-0005），見「下一步」第 2 點。

## 驗證

- 讀過的檔案：
  - 實作者回報
  - qa 審查報告 `/home/user/AICompany/work/reviews/2026-10-24-N82方案A程式審查-qa-reviewer.md`
  - `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py` 全檔
  - `/home/user/AICompany/apps/stock-desk/backend/app/services/index.py` 第 410～645 行
  - `/home/user/AICompany/docs/adr/0005-stock-desk-指數來源與美股額度管理.md` I-3 與註記全段
  - `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md` 第 294～307 行與第 655～698 行
  - `/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md` 第 1436、1455～1463 行
  - `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md` N-82、N-88、N-93
- 第 1 點的邊界掉列，是我依程式推論的：請求邊界是 UTC 午夜，過濾用推導日期。我沒有實跑。
- 毫秒時間戳記觸發 `ValueError`、`10**30` 觸發 `OverflowError`，同樣是依 CPython 行為推論，沒有實跑。
- 「Yahoo 對長區間不截斷」【未查證】，所以列入 #49。
- 唯讀：沒有讀 `.env`，沒有碰 `*.db`，沒有寫任何檔，也沒有執行指令。

## 下一步

1. **data-engineer**：依第 1、2、5 點與 L-3 改 `yfinance.py`、`index.py` 與測試。測試格是 (1-a)～(1-d)、(2-a)～(2-n)、(5-b)、L-3，另把 AST 封閉清單與 `fromtimestamp` 的位置改釘到新結構。改完重跑 ruff、mypy、全套 pytest。
2. **tech-architect（我）**：起草 ADR-0027 D-3 修訂，內容如下，送風控（CEO 層級由風控裁定），落檔前不得實作 `replay_checks.py` 的快照寫入：
   - 快照另存每份回應的 `null_gap_rows` 與 `received_at`，納入 `content_sha256`；
   - 列的 `as_of`／`fetched_at` 依第 5 點對應；
   - 第 3 點的型別保留序列化，以及 (5a) 的 `type(x) is int`；
   - 註明「`raw_timestamp` 缺漏」在這條路徑上不會出現；
   - §4.7 要揭露缺口列數，逐字交 creative-lead 起草、送風控。
   - 另請風控判斷：(5a) 是否要把缺口列的時間戳記也納入檢查。這屬於收緊，但仍須在快照之前登記。
3. **coordinator**：在決策包 #49 加兩題。
   - 以接近 [S, E] 長度的單一請求，確認 `^TWII` 是日線密度、沒有截斷。
   - 歷史上有沒有只缺 volume 或部分欄位 null 的列。

   如果第一題不成立，回 TA 重開多視窗方案（方案 C），須在閘門 (b) 之前。
4. **qa-reviewer**：改完之後複審，並依章程在有 `codex` 的環境補跑 `/review` 第二意見，才可以合併。
5. **dev-lead**：之後實作 `replay_checks.py` 時，遵守 (3-a)、(3-b)、(4-a)、(4-b)、(5-c)。
