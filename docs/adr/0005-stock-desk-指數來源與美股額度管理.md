# ADR-0005：stock-desk 指數日線來源、標的指數對應表、美股額度管理與 ticker 正規化

- 狀態：proposed
- 日期：2026-07-26
- 決策者：tech-architect（草案）；待 CEO 核可
- 適用範圍：僅 `product/stock-desk` 產品線（本 ADR 不存在於 main）
- 相依：
  - ADR-0002（`MarketDataProvider` 抽象、SQLite/WAL、compose 三 service）
  - ADR-0003（美股主來源 Alpha Vantage、備援 yfinance、四層降級鏈、`as_of`/`source` 約定、額度預算化要求、ticker 正規化待辦）
  - skill `data-source-integration`（adapter／契約測試／離線 fixture／紅線）
- 與既有 ADR 的關係：**不取代任何 ADR**。本則補齊 ADR-0003 完全未涵蓋的「指數日線」，並具體化 ADR-0003「對實作的約束」第 3 條（額度計數器）與「尚缺的事實」第 4 條（ticker 正規化）。
  唯一一處**修訂**：ADR-0003 約束 1 的降級鏈由四層改為五層（新增 layer 0「TTL 內快取先行」，僅對有額度上限的來源啟用），理由見決策四。ADR-0003 其餘內容維持 accepted。
  2026-08-03 修訂：I-3 與決策一第 3 點的措辭原寫為「恆為 `BACKUP`」，範圍過寬且與 `DataStatus.BACKUP` 的定義及本 ADR 決策四第 4 點／D-2 衝突，經 tech-architect 裁決收窄為「不得標為 `FRESH`、且不得將快取結果升級為 `BACKUP`」。本次僅修訂措辭，決策實質與實作均未改變。

---

## 評估摘要（結論先行）

1. **指數日線一律使用官方指數代號，不使用代理 ETF。** 架構上保留 `basis="proxy_etf"` 欄位，但 **Phase 7 不放行任何一筆代理條目**；要放行需 CEO 決策。理由：drag 拆解輸出的是 `fee_effect / reset_effect / residual` 三個看起來乾淨的歸因數字，代理 ETF 自身的經理費與追蹤誤差會整包掉進 `residual`，而 `reset_effect` 與 `naive` 也會同步偏移；在 metadata 已經 `verified=False` 的前提下再疊一層代理偏離，這個專章的資訊價值會低到不值得顯示。
2. **指數來源 = yfinance（`^` 前綴代號），Alpha Vantage 不參與指數路徑。** AV 免費層 25 req/day 的額度全部保留給使用者實際持倉的個股／ETF；且 AV 免費層是否提供指數序列在本環境無法查證，不憑猜測接線。指數序列因此**恆為非官方來源**，`status` 一律 `backup`，UI 必須標示。
3. **17 檔槓桿 ETF 中，Phase 7 只放行 12 筆指數對應；5 筆明確標為 `unmapped`**（00631L、00632R、00680L、SOXL、SOXS），並在專章回明確原因。其中 SOXL/SOXS 是「看起來合理但可能錯誤」的典型案例，寧可不給數字。
4. **對應表獨立成 `app/leverage/index_mapping.py`，不擴充 `detect.py` 的註冊表**；key 為 normalized ETF symbol（不是 `underlying_index` 敘述字串），並以 drift 測試綁住兩表一致性。
5. **額度計數器落在既有 SQLite 新增 `provider_quota_usage` 表**，以單一 `INSERT ... ON CONFLICT DO UPDATE ... WHERE used < limit` 語句做**先預留、後呼叫**的原子扣減，配合 `PRAGMA busy_timeout` 解決 API／scheduler 雙寫者競態。
6. **前置阻擋條件**：`compose.yaml` 原本沒有掛載任何 volume，backend 與 scheduler 各自持有一份 DB，跨進程計數器沒有共享對象。**此項已於 2026-07-26 修復（commit 81e050c）**，新增具名 volume `stock-desk-data` 掛到兩個 service 的 `/app/data`，並顯式設定 `STOCK_DESK_DB_PATH`。
7. **canonical ticker 採「點號形式」（`BRK.B`），快取鍵與 `PriceBar.symbol` 一律用 canonical**，各 provider 自行做 canonical → provider symbol 的轉換。
8. **需 CEO 或使用者裁決的事項**見文末，不硬猜。

---

## Context（背景）

Phase 7 要補三個資料層缺口（美股日線、標的指數日線、FX 風控接線）。ADR-0003 只處理「美股個股日線」的主／備援選擇，對「指數」隻字未提；`app/leverage/detect.py` 的 `underlying_index` 是給人讀的敘述字串（如 `"NASDAQ-100 Index (3x single-day)"`），不是可查詢代號；ADR-0003 雖要求「本地持久化當日已用次數、跨進程可見」與 ticker 正規化，但沒有具體方案。

三項硬限制決定了本 ADR 的形狀：

- **本環境無外網**。任何選定的端點都無法對真實回應查證。既有台股／FX adapter 的作法是「依公開文件手工構造離線 fixture ＋ 契約測試 ＋ 檔頭與 fixture README 的未查證聲明」，本則沿用，且把「未查證」從開發者內部文件提升為**使用者可見的常駐揭露**。
- **drag 拆解對輸入序列的語意極敏感**。`app/leverage/drag.py` 的 `naive = beta * R_idx`、`reset_effect = ideal_daily_reset_path(index_returns) - naive`、`residual = gap - fee_effect - reset_effect`。換掉 index 序列不會讓計算失敗，只會讓三個歸因項**安靜地變成別的東西**。這是本 ADR 最需要防的失效模式：不是「算不出來」，而是「算得出來但意義不對，且使用者看不出差別」。
- **AV 25 req/day 是硬天花板**，而現行 `MarketDataService.get_daily_bars` 是**每次請求都先打主來源**（`PriceBarCache.get` 算出的 `is_within_ttl` 從未被 service 讀取）。台股沒有明訂額度，這只是浪費；美股接上 AV 之後，**單一次頁面重整就可能燒掉一天的配額**。

---

## 決策一：指數日線來源

### 選項比較

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **A. 官方指數代號（`^NDX`／`^GSPC`／`^TWII`），走 yfinance** | drag 的 `naive`／`reset_effect` 語意與 `drag.py` docstring 完全一致；不消耗 AV 額度 | 來源非官方、無 SLA、無授權保障；代號可得性未查證；台股僅涵蓋加權指數 | yfinance 端點漂移或 IP 封鎖 → 指數區塊回 `insufficient_data`（可接受，fail-safe） |
| **B. 代理 ETF（QQQ／SPY／0050）當指數序列** | 代號一定拿得到；可與美股個股走同一 adapter | 代理自身的經理費、追蹤誤差、折溢價會混進 `residual`，`reset_effect` 與 `naive` 同步偏移；使用者看到的三項歸因數字失真而無從察覺 | **最高**：產生「有數字、看似乾淨、實際錯誤」的輸出，與產品「可解釋、可反駁」的定位正面衝突 |
| **C. Alpha Vantage 取指數** | 官方 key、條款明確 | 免費層是否提供指數序列在本環境無法查證；即使支援，也會與持倉個股搶 25 req/day | 憑猜測接線 → 上線即失效，且吃掉個股額度 |
| **D. Phase 7 完全不做指數** | 零風險 | 槓桿專章最有價值的兩區永久停在 `insufficient_data` | 產品缺口不收斂 |

### 決策

1. **採方案 A**：指數序列一律使用**官方指數代號**，由 **yfinance adapter** 供給。Alpha Vantage **不接入指數路徑**。
2. **代理 ETF 路徑在架構上保留、在資料上封鎖**：`IndexRef.basis` 定義三值 `official_index | proxy_etf | unmapped`，但 Phase 7 的 `INDEX_MAPPING` 中**不得存在任何 `basis="proxy_etf"` 的列**，並以測試強制（約束 I-2）。日後要放行須 CEO 核可並另立 ADR。
3. **指數序列不得標為 `FRESH`**：即使 yfinance 呼叫成功也一律揭露為 `BACKUP`。它是非官方來源，用 `fresh` 會讓使用者以為這是官方紀錄來源。反向亦然：結果來自本機快取時**維持 `CACHED_STALE`**，不得改標為 `BACKUP`——揭露只能往悲觀方向調整，不得為了統一標籤而抹去「這是快取／過期資料」的事實。
4. **台股指數**：Phase 7 僅涵蓋臺灣加權股價指數（對應 00675L／00676R），走 `^TWII`。**臺灣50指數列為 `unmapped`**：沒有已查證的免費日線代號，且**明確禁止以 0050 代理**（0050 有經理費與折溢價）。FinMind 指數 dataset 列為未來備援，dataset 名稱必須由 devops-sre 在有網路環境查證後才可寫進程式碼。
5. **不對指數序列做含息口徑臆測**：`IndexRef.return_basis ∈ {price, total_return, unknown}`，未查證者一律 `unknown`，並在專章 `assumptions` 追加「指數的含息口徑未查證，配息差異會落在 residual」。
6. **殘差跳閘**：`|residual|` 超過 `RESIDUAL_ALERT_ABS`（預設 0.10，**明示為人工設定的提醒門檻、非統計檢定**）時，專章 `notes` 必須追加「殘差異常大，標的指數對應可能有誤或含息口徑不一致，請勿將本次歸因視為定論」。

### 明確不該做的事（紅線，違反即否決）

- 不得以 QQQ／SPY／0050／TLT 等 ETF 冒充指數序列傳入 `decompose_drag` 或 `estimate_erosion`。
- 不得在 `IndexRef` 缺列時猜一個看起來對的代號（SOXL → `^SOX` 即為被明確擋下的案例）。
- 不得把指數序列標為 `fresh`。
- 不得把來自本機快取的指數結果標為 `backup`；`backup` 專指「即時取自備援來源」。
- 不得為了讓 FR-2「有東西可看」而放寬第 2、3、6 點。

---

## 決策二：`underlying_index` → 可查詢代號的對應表

### 選項比較

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **A. 擴充 `detect.py` 的 `KNOWN_LEVERAGED_ETF`** | 一張表、不會漏同步 | 兩種查證對象完全不同的事實（發行商公開說明書 vs 資料源代號可得性）共用同一個 `verified` 旗標，揭露精度下降 | 一個旗標翻真時，另一半事實被誤認為也已查證 |
| **B. 獨立模組 `app/leverage/index_mapping.py`** | 兩張表各自的 `verified`／`verified_on` 獨立；維護者不同；模組邊界乾淨 | 兩表可能漂移 | 以 drift 測試消除 |
| **C. 放進 YAML／DB 讓使用者維護** | 使用者可自行擴充 | 需要 schema 驗證、審核層與沙箱；填錯代號會產生錯誤歸因數字且無人審查 | 與 ADR-0004「規則進 git、經 review」的治理精神相反 |

### 決策

**採方案 B。** 新增 `app/leverage/index_mapping.py`，純資料表與純查詢函式，**不做任何 I/O、不 import `app/data/providers/*`**。

```python
IndexBasis = Literal["official_index", "proxy_etf", "unmapped"]
ReturnBasis = Literal["price", "total_return", "unknown"]

@dataclass(frozen=True)
class IndexRef:
    etf_symbol: str                 # normalized；必須存在於 KNOWN_LEVERAGED_ETF
    underlying_index_text: str      # detect.py 該列文字的快照，供 drift 測試比對
    basis: IndexBasis
    series_symbol: str | None       # e.g. "^NDX"；basis="unmapped" 時為 None
    series_market: Market
    return_basis: ReturnBasis
    verified: bool = False          # 代號可得性是否經真實回應查證
    verified_on: str | None = None
    note: str = ""                  # unmapped 時必須寫明「為什麼拿不到 / 為什麼不代理」

MAPPING_VERIFIED_ON: Final[str | None] = None   # 比照 detect.REGISTRY_VERIFIED_ON
```

**關鍵設計理由：**

- **key 用 normalized ETF symbol，不用 `underlying_index` 敘述字串**。敘述字串是給人看的文案，改一個全形括號就會讓對應靜默失效。
- **`series_source_hint` 刻意不放進 mapping**。「誰去抓 `^NDX`」是資料層知識，屬 `app/services/index.py`；mapping 只回答「這檔 ETF 的標的指數是哪一個可查詢代號、什麼口徑」。
- **`unmapped` 必須以「存在的列」表示，不得以「缺席」表示**。「沒查過」與「查過、確定拿不到」是兩件事，文案必須能分辨；`note` 就是那句文案的來源。

### Phase 7 放行清單（12 筆 mapped / 5 筆 unmapped，全部 `verified=False`）

| ETF | basis | series_symbol | return_basis | 備註 |
| --- | --- | --- | --- | --- |
| 00670L | official_index | `^NDX` | unknown | |
| TQQQ / SQQQ / QLD | official_index | `^NDX` | unknown | |
| SSO / SDS / SH / UPRO / SPXL / SPXS | official_index | `^GSPC` | price | 含息差異落在 residual |
| 00675L / 00676R | official_index | `^TWII` | unknown | 註冊表寫「臺灣加權股價指數」，但該類基金常以期貨複製、且可能對應報酬指數；口徑未查證 |
| 00631L / 00632R | **unmapped** | — | — | 臺灣50指數無已查證的免費日線代號；**不以 0050 代理**（經理費＋折溢價） |
| 00680L | **unmapped** | — | — | ICE 美國政府20+年期債券指數無免費日線來源；**不以 TLT 代理** |
| SOXL / SOXS | **unmapped** | — | — | 註冊表記為「ICE Semiconductor Index」，公開常見的 `^SOX` 是另一支半導體指數；查證前對應會產出「看似合理但錯誤」的歸因 |

### 維護流程

1. 新增／修改對應：由 **data-engineer** 開 PR，必須同時附上該列的依據（發行商公開說明書中的標的指數名稱）與 `note`。
2. `verified` 只有 **devops-sre** 在有網路環境實際打過該代號、確認回得到日線後才能翻為 `True`，並同時寫 `verified_on` 與 `MAPPING_VERIFIED_ON`。
3. **tech-writer 不得修改本檔**；文案調整只能改前端顯示層。
4. `detect.py` 的 `underlying_index` 文字若變更，drift 測試會 fail，PR 必須同步更新 `underlying_index_text`（強制人看過一次）。

---

## 決策三：額度計數器與美股 ticker 正規化

### 選項比較（額度計數器）

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **A. 記憶體計數器（進程內）** | 零 I/O、最簡單 | API 與 scheduler 是兩個進程，各記各的 → 實際可打到 2×額度 | 直接違反 ADR-0003 約束 3 |
| **B. 獨立 JSON／檔案 + flock** | 不動既有 DB | 需自行處理原子性、殘留鎖；多一個持久化機制要備份 | 檔案鎖在 container 重啟後殘留 |
| **C. 既有 SQLite 新增一張表** | 沿用既有 WAL 資料庫與備份路徑；單一 SQL 語句即可原子扣減 | 依賴兩個 container 共享同一個 db 檔（已於 81e050c 修復） | 若 volume 未修，計數器等同方案 A |
| **D. 引入 Redis 之類的外部計數服務** | 標準解 | 需要新 service、違反 ADR-0002「本機零維運」 | 過度設計 |

### 決策（額度計數器）

1. **採方案 C**，新增 `app/data/quota.py` 的 `QuotaLedger`：

```sql
CREATE TABLE IF NOT EXISTS provider_quota_usage (
    provider    TEXT NOT NULL,
    quota_date  TEXT NOT NULL,
    used        INTEGER NOT NULL,
    limit_value INTEGER NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (provider, quota_date)
);
```

2. **先預留、後呼叫**：額度在「決定要發出請求」的當下就扣，**不是**在「請求成功」之後才扣——逾時、429、格式錯誤都已經消耗了對方的配額。扣減以單一語句完成，天然原子：

```sql
INSERT INTO provider_quota_usage (provider, quota_date, used, limit_value, updated_at)
VALUES (?, ?, 1, ?, ?)
ON CONFLICT(provider, quota_date) DO UPDATE SET
    used = used + 1,
    updated_at = excluded.updated_at
WHERE used < limit_value;
```

`cursor.rowcount == 0` 即代表額度已滿：**不發請求**，adapter 直接回 `DataStatus.UNAVAILABLE` 並附中文原因，由 `MarketDataService` 降級到 yfinance。

3. **並行策略**：每個連線 `PRAGMA busy_timeout=5000`；扣減走 `BEGIN IMMEDIATE`。兩個寫者在 WAL 下靠 SQLite 寫鎖序列化即可。**不得**用「先 SELECT 再 UPDATE」兩段式（TOCTOU 競態）。
4. **重置邊界**：`quota_date` 由 `QUOTA_RESET_TZ`（預設 `UTC`）換算，並標記「重置時區未查證」。額度數字從 `ALPHA_VANTAGE_DAILY_LIMIT` 環境變數讀入，預設值採 ADR-0003 於 2026-07-23 記載的 25 並註明查證日期；**不得寫死在公式裡**。另設 `ALPHA_VANTAGE_SAFETY_MARGIN`（預設 2），實際可用額度 = `limit - margin`。
5. **每分鐘節流**：AV 的每分鐘上限未查證，因此不宣稱對方的數字，改設我方自訂的保守節流 `ALPHA_VANTAGE_MIN_INTERVAL_SECONDS`（預設 12.0，即 ≤5 req/min），沿用既有 `RateLimitedClient`。
6. **可觀測**：`GET /api/settings` 的資料來源區塊必須能讀到當日 `used / limit_value / quota_date`。

### 決策（ticker 正規化）

1. **canonical 形式 = 點號形式**（`BRK.B`、`BF.B`）：與使用者手輸／CSV 匯入習慣一致，也與既有 `detect.normalize_symbol` 相容。
2. 新增 `app/data/providers/us_symbols.py`：
   - `canonical_us_symbol(raw) -> str`：strip → upper → 去 `.US` 後綴 → 只允許 `[A-Z0-9.\-]`（**不允許 `^`**）→ 空字串或非法字元回明確錯誤。
   - 每個 US provider 實作 `to_provider_symbol(canonical) -> str`，以宣告式規則 + 例外對照表表達（Yahoo 家族預設 `"." -> "-"`）；例外走 `US_SYMBOL_OVERRIDES`，整張表 `verified=False` 直到有網路查證。
3. **快取鍵與 `PriceBar.symbol` 一律用 canonical**。若 AV 寫 `BRK.B`、yfinance 寫 `BRK-B`，`price_bars_cache` 會長出兩組 key，降級到快取時靜默 miss，`find_foreign_bars` 的跨來源保護也會失效。
4. **反向轉換不存在**：只做 canonical → provider，避免回程規則不可逆造成錯配。
5. **`^` 前綴專屬指數路徑**：`PositionInput.symbol` 新增 validator 拒絕 `^` 開頭；指數序列走獨立的 `IndexSeriesService`，其 symbol 不經 `canonical_us_symbol`。

---

## 決策四：TTL 內快取先行（layer 0）

這不是加分項，是前三項成立的前提：沒有它，AV 的 25 req/day 會被單一次頁面重整燒光，額度計數器只會忠實記錄「今天又爆了」。

### 選項

| 方案 | 優點 | 缺點 |
| --- | --- | --- |
| **A. 新增 `DataStatus.CACHED_FRESH` 第五個狀態** | 語意最誠實 | API schema、前端徽章對照表全部要動 |
| **B. 沿用四狀態，`ProviderResult` 新增 `is_within_ttl: bool \| None`** | 血緣影響最小 | `cached_stale` 字面在 TTL 內時語意偏負面，需前端文案配合 |

### 決策

**採方案 B。**

1. `ProviderResult` 新增 `is_within_ttl: bool | None`（live 來源為 `None`）。
2. `MarketDataService` 新增 `cache_first: bool = False`；**US 與 index 服務開啟，TW 服務維持關閉**（把 Phase 7 的變更半徑鎖在美股與指數）。開啟時順序為：
   `layer 0 TTL 內快取 → Alpha Vantage → yfinance → 任何快取（含過期）→ unavailable`。
3. **TTL 一律 24h**。**明確否決「指數 TTL 拉長以節省額度」**：drag 是端點對端點的報酬比較，末端一天用到過期序列會直接讓 `actual`／`naive` 的比較基準錯位；而且指數走 yfinance，本來就不吃 AV 額度，拉長 TTL 換不到額度收益，只換來失真。
4. 前端對 `cached_stale` 的文案必須依 `is_within_ttl` 分岔：`true` → 「本機快取（今日已更新，N 分鐘前）」；`false` → 「快取資料，已延遲 N 分鐘」。兩者都不得顯示為即時。

---

## 決策五：FX 風控接線的模組邊界

1. **`app/advice/book.py` 維持純函式，不得 import 任何 adapter**。`build_book_context` 改為接收 `fx: FxQuote | None`（`rate / as_of / source / status`），由呼叫端（`app/api/advice.py`、`app/alerts/snapshot.py`）透過共用 resolver 取得。理由：讓 book.py 自己抓匯率會把 I/O 塞進目前唯一一個純運算的風控組裝層，測試必須開始 mock 網路。
2. `_resolve_fx` 的紅線**原封不動保留**：拿不到匯率就回 `None`，價格類上限維持 `not_evaluable`，**不得以 1.0 或任何預設值代入**。
3. 原因文字必須可分辨「無法取得價格」與「無法取得匯率換算」。
4. `FxQuote` 的 `status`／`as_of` 必須流進 `notes`，且 `fx.py` 檔頭既有的「即期買賣中點模型值、非官方收盤匯率、端點未查證」聲明必須**常駐**呈現在使用者可見處。
5. **換算時點與小數精度本 ADR 不決定**，但架構上先固定 `FxQuote` 必須攜帶 `as_of`，讓時點決策日後只需改 resolver、不需改 book.py 與上限引擎。

---

## Consequences（後果）

### 好處

- drag／erosion 的歸因語意與 `drag.py` docstring 完全一致，沒有代理標的污染。
- 指數與個股的額度互不排擠：AV 額度 100% 服務持倉標的。
- 12/17 檔槓桿 ETF 的專章可真正運作；剩下 5 檔給出的是「為什麼不行」而不是含糊的技術故障暗示。
- 額度計數器與快取先行合併後，正常使用下每個美股標的每天最多消耗 1 次 AV 額度，25 req/day 從「單次操作就可能爆掉」變成「持倉 ≤ 23 檔即穩態」。
- ticker canonical 化封住了「同一標的兩組快取鍵」這個會讓降級鏈靜默失效的坑。

### 代價（照實列）

- **指數資料的可用性完全押在 yfinance 上**。它被封鎖或端點漂移時，槓桿專章的兩區會一起退回 `insufficient_data`；本 ADR 接受這個殘餘風險，因為替代方案（代理 ETF）用可用性換的是正確性。
- **臺灣50指數缺席**：00631L／00632R 是台灣最常見的槓桿 ETF，Phase 7 之後它們的專章仍然只有持有期間統計。這是本 ADR 最痛的取捨，應由 CEO 明確接受。
- **`cached_stale` 語意被 `is_within_ttl` 二次限定**，讀 API 的人必須看兩個欄位才知道新鮮度；換來的是不動 `DataStatus` 列舉值。
- **`decompose_drag` 與 `MarketDataService`／`ProviderResult` 的簽名都要動**，回測與訊號層的既有測試會被牽動。
- **本 ADR 的所有代號、口徑、額度數字都 `verified=False`**。功能上線不代表事實已查證；揭露必須常駐，不得因為「畫面太吵」而移除。

---

## 對實作的約束（逐條、可被 qa-reviewer 檢查）

**前置**

- P-1　`compose.yaml` 共享具名 volume 與顯式 `STOCK_DESK_DB_PATH`。**已完成（81e050c）**。
- P-2　devops-sre 在有網路環境查證並記錄日期：AV 免費層日／分鐘額度、`outputsize=full` 是否仍免費、`TIME_SERIES_DAILY_ADJUSTED` 是否仍在免費層、`^GSPC`／`^NDX`／`^TWII` 於 yfinance 的可得性。

**指數（I-\*）**

- I-1　`app/leverage/*` **不得** import `app/data/providers/*`，也不得執行任何 I/O；接合點只有 `app/services/index.py` 一處。
- I-2　`INDEX_MAPPING` 中不得存在 `basis="proxy_etf"` 的列（測試強制）。
- I-3　指數序列（含槓桿 ETF 的標的指數與市場比較基準）**不得**以 `DataStatus.FRESH` 呈現。任何下層回報 `FRESH` 的指數結果，在離開 `app/services/index.py` 之前必須降級為 `BACKUP`。降級**只能往悲觀方向**進行：`CACHED_STALE` 與 `UNAVAILABLE` 一律原樣保留，**不得**為了讓狀態字面統一為 `BACKUP` 而把快取結果「升級」掉。理由：`BACKUP` 的定義是「即時取自備援來源」，把一筆未呼叫任何來源、從本機快取取得的資料標為 `BACKUP` 是不實陳述，並會使 `is_within_ttl`（決策四第 4 點、D-2）在指數路徑上永久失去意義。「本序列取自非官方來源」這個事實由常駐的來源揭露 `notes`（每一條成功與失敗路徑皆須掛入）承擔，不由 `status` 單一欄位承擔。本約束適用於讀取指數序列的**每一層**：`MarketDataService` 會把主來源成功一律標為 `FRESH`，因此呼叫端必須經由 `IndexSeriesService` 取得結果，不得直接持有底層 service。
- I-4　`decompose_drag` 新增 `index_basis` 與 `index_return_basis` 參數，於輸出回顯，並在 `basis != official_index` 或 `return_basis == "unknown"` 時追加對應的 `assumptions` 句子。
- I-5　`basis="unmapped"` 時，drag 與 erosion 皆回 `insufficient_data`，`reason` 使用該列的 `note`；文案不得暗示暫時性技術故障。
- I-6　殘差跳閘（`RESIDUAL_ALERT_ABS`，預設 0.10）觸發時必須追加 `notes`；常數 docstring 必須寫明「人工設定的提醒門檻，非統計檢定」。
- I-7　指數序列不得寫入與個股相同的 symbol key。

**對應表（C-\*）**

- C-1　`index_mapping.py` 只有資料與純函式，無 I/O、無 import provider。
- C-2　key 為 normalized ETF symbol；每個 key 必須存在於 `KNOWN_LEVERAGED_ETF`（測試強制）。
- C-3　`KNOWN_LEVERAGED_ETF` 的每一列都必須在 `INDEX_MAPPING` 有對應列（含 `unmapped`）；缺席即測試失敗。
- C-4　drift 測試：`IndexRef.underlying_index_text` 必須逐字等於 `detect.py` 該列的 `underlying_index`。
- C-5　`basis="unmapped"` 的列，`note` 不得為空且必須說明「為什麼拿不到」與「為什麼不代理」。
- C-6　`verified=True` 的列必須同時有 `verified_on`；`MAPPING_VERIFIED_ON is None` 時不得有任何列 `verified=True`。
- C-7　專章輸出必須帶 `index_mapping_verified` 布林欄位，且前端在其為 `false` 時必須顯示「指數對應未查證」標示；此標示不得因版面而隱藏。

**額度與 ticker（Q-\*）**

- Q-1　額度扣減必須是單一 `INSERT ... ON CONFLICT DO UPDATE ... WHERE used < limit_value` 語句；不得出現「先 SELECT 再 UPDATE」。
- Q-2　扣減發生在**發出請求之前**；請求失敗不回補額度（測試：模擬逾時後 `used` 仍為 1）。
- Q-3　`rowcount == 0` 時 adapter **不得**發出 HTTP 請求，回 `UNAVAILABLE` 並附中文原因（測試：以 transport spy 斷言零次呼叫）。
- Q-4　所有 `QuotaLedger` 連線設定 `PRAGMA busy_timeout`；額度上限、時區、安全邊際、節流間隔全部從環境變數讀入，程式碼中不得出現字面量 `25`。
- Q-5　快取鍵與 `PriceBar.symbol` 一律為 canonical 形式；契約測試須包含 `BRK.B` 經兩路徑後快取中只存在一組 key。
- Q-6　`canonical_us_symbol` 拒絕 `^` 開頭；`PositionInput.symbol` 同步拒絕。
- Q-7　AV API key 只從環境變數讀取，不得出現在 code、設定檔、fixture。

**降級鏈與揭露（D-\*）**

- D-1　`cache_first` 僅對 US 與 index 服務開啟；TW 服務行為不得改變（既有台股測試須全數不改而通過）。
- D-2　`ProviderResult.is_within_ttl` 必須一路流到 API 回應與前端徽章文案。
- D-3　新增的每個 adapter 檔頭必須有未查證聲明，`tests/fixtures/README.md` 必須新增對應列；此聲明不得因功能上線而移除。
- D-4　來源若無法區分「代號不存在」與「暫時無資料」，文案必須誠實寫「無法區分」，不得臆測。
- D-5　跨來源不得靜默拼接：同一回應中的 bars 必須同源；混源時每列保留自身 `source`，並在 `notes` 明示。

**FX（F-\*）**

- F-1　`app/advice/book.py` 不得 import `app/data/providers/*`。
- F-2　匯率不可得時價格類上限維持 `not_evaluable`，原因文字必須與「無價格」可分辨；任何位置不得出現預設匯率 `1.0` 代入非 TWD 幣別。
- F-3　`FxQuote` 的 `status` 與 `as_of` 必須出現在 `notes`。
- F-4　`fx.py` 的未查證聲明必須常駐於使用者可見處。

---

## 替代方案與棄卻理由（彙整）

- **代理 ETF 當指數**：棄卻。用可用性換正確性，且錯誤不可見。保留欄位、封鎖資料，日後可由 CEO 決策放行。
- **Alpha Vantage 供指數**：棄卻。可得性未查證，且與持倉個股搶額度。
- **FinMind 台股指數 dataset**：**暫緩，非棄卻**。dataset 名稱無法在本環境查證；查證後可作為台股指數主來源，屆時 `^TWII` 降為備援，00631L／00632R 有機會脫離 `unmapped`。
- **擴充 `detect.py` 註冊表**：棄卻。兩種查證對象共用一個 `verified` 旗標會降低揭露精度。
- **記憶體／檔案鎖額度計數器**：棄卻。前者違反 ADR-0003 約束 3，後者自製原子性不划算。
- **Redis 等外部計數服務**：棄卻。違反 ADR-0002「本機零維運」。
- **新增第五個 `DataStatus`**：棄卻（近似平手）。改以 `is_within_ttl` 表達，換取最小血緣影響。
- **Phase 7 不做指數**：棄卻。12/17 檔可放行，缺口不必全留。

---

## 需要 CEO 或使用者決定（本 ADR 不代決）

1. **是否放行代理 ETF 指數序列？**
   - 選項 A（本 ADR 建議）：不放行。00631L／00632R／00680L／SOXL／SOXS 的 drag/erosion 維持 `insufficient_data`。取捨：正確性優先，功能缺口留著。
   - 選項 B：放行，並以 `basis="proxy_etf"` + 顯著揭露 + 殘差跳閘呈現。取捨：多數槓桿 ETF 有數字可看，但三項歸因的意義被稀釋，且使用者多半不會讀懂揭露。
   - tech-architect 立場：**選項 A**；若選 B，要求至少限定在「代理標的與指數的年追蹤誤差已查證」的條目，且 UI 不得使用「指數」二字稱呼該序列。
2. **臺灣50指數要不要投入查證成本？** 關係到 00631L／00632R 能否有專章。選項：(a) 請 devops-sre 查 FinMind／TWSE 指數端點；(b) Phase 7 接受缺席，列入 Phase 8。
3. **FX 換算的時點與小數精度**：需 risk-compliance-officer 與 tech-architect 共同定案，屬另一則 ADR 的範圍。
4. **是否擴充離線示範模式涵蓋美股與 FX**：這是本沙盒能否做端到端人工驗收的唯一途徑。技術意見：若不擴充，Phase 7 的驗收上限就是單元＋契約測試。

---

## 尚缺的事實（不阻擋定案，實作前必須補齊，全部需記錄查證日期）

1. AV 免費層的日／分鐘額度、`outputsize=full` 與 `TIME_SERIES_DAILY_ADJUSTED` 的免費層狀態（devops-sre）。
2. AV 額度的重置時區與邊界（devops-sre）；查證前以 `QUOTA_RESET_TZ=UTC` + 安全邊際保守處理。
3. `^GSPC`／`^NDX`／`^TWII` 在 yfinance 的可得性與欄位格式（devops-sre）。
4. 各槓桿 ETF 標的指數的含息口徑與 SOXL/SOXS 的實際 benchmark（data-engineer，對照發行商公開說明書）。
5. 實際持倉美股標的數量，決定 25 req/day 是否為穩態瓶頸。
6. AV 與 yfinance 對 `BRK.B` 類符號的實際接受格式（devops-sre）。
7. adjusted vs unadjusted 對回測序列的影響（ADR-0003 尚缺事實 3）：本 ADR 只保證資料層欄位為此留餘地，回測層的決策另案。
