# ADR-0012：stock-desk 族群動能板與全市場日線

- 狀態：proposed
- 日期：2026-09-24
- 決策者：tech-architect（草案）；待 CEO 核可
- 適用範圍：僅 `product/stock-desk` 產品線（本 ADR 不存在於 main）
- 相依：
  - ADR-0002：SQLite WAL、單機；「所有市場資料存取走抽象介面」。本 ADR D-3 對後者做了擴充解讀，見 §7。
  - ADR-0005：指數路徑 yfinance 恆為 `backup`。
  - ADR-0009：交易日新鮮度、D-3 正向證據、D-8 冷卻。
  - ADR-0010：單一請求 IO 預算、cache-only 讀取。
  - skill `backtest-protocol`、skill `data-source-integration`。
- 輸入狀態：`work/stock-desk-族群動能-PRD.md`、`-資料評估.md`、`-方法論.md` 撰寫本 ADR 時**尚未產出**。凡標「條件式」的決策，要等 §8 的開放問題回答後修訂本 ADR 才能定案。**在那之前本 ADR 不得轉為 accepted。**
- **待修訂（dev-lead 註記，2026-09-24）**：本草案完稿早於風控預審（`work/stock-desk-族群動能-派工單.md` §4）。以下與風控條件衝突，下一輪修訂必須處理：
  - D-7、C-16 與 API `ConstituentItem.score`／`score_components`：風控 VETO 成分股「技術面分數」。第一階段成分股只依族群排名所用的同一已發生變數（例：近 5 日漲跌幅）排序，不產生分數。
  - D-10 `SectorHistoryStats.hit_rate`：風控 QR-6 要求欄位改 `beat_count`／`sample_count`／`base_rate`，另需基準率 q、成本狀態、分名次區間統計。
  - D-8 門檻：以風控 §4.3 顯示門檻 a–f 為下限（樣本外、不重疊 N ≥ 60、CI 下界 > 基準率、扣成本判定、12 個月滾動失效、定義鎖版）。
  - D-10 回應須帶覆蓋率（應有／缺漏檔數）、「僅上市／僅上櫃」標記、統計截至日與樣本外期間（風控 §4.5）。
- 修訂：（無，本次為新增）

## Context（背景）

CEO 2026-09-24 裁定開第一階段：首頁新增「族群動能排行＋歷史機率」卡。第一階段只用日線，不接基本面，也不接消息面。

要做到這件事，系統得具備三種現在沒有的能力：

1. **全市場日線**。既有資料鏈只抓「持倉」：`scheduler.refresh_market_data` 只對 `PositionStore.list_all()` 的標的逐檔走 `load_bars`，程式註解寫明 “not to crawl a universe”。provider 介面 `MarketDataProvider.get_daily_bars(symbol, start, end)` 是「單一序列、時間區間」的形狀。`TwseAdapter` 每個日曆月一次 HTTP。拿這個介面去抓約兩千檔、每檔 N 個月，請求數是「檔數 × 月數」，不可行。
2. **跨標的的橫斷面計算**：族群等權指數、排名、成分股評分。既有 `app/signals` 是單一標的量測，而且 `signals/service.py` 明文寫「刻意不出 score／rating／buy-sell 欄位」。既有 `app/backtest/engine.py` 是單一資產回測。
3. **歷史命中率**：每天的排名都要附「歷史上第 1 名的族群，下 5 個交易日跑贏大盤的比例（N、期間）」。這需要 walk-forward 的橫斷面回測，而且線上排名和回測排名必須是同一段計算碼，否則顯示的機率不屬於畫面上那個排名。

另有四個既有事實限制了方案形狀：

- `PriceBarCache.put()` 以 `(symbol, market, trade_date)` 做 upsert，**不看既有列的 `source`**，最後寫入者勝出。`mixed_sources_reason()` 只要回傳的 bars 來源超過一個，就附上風控定稿句（ADR-0009 D-7）。
- `PriceBarCache.market_trading_days()` 在**每一次** `/api/advice` 都會被呼叫；`market_has_session()` 是 ADR-0009 D-3 的正向證據。兩者都掃 `price_bars_cache` 的整個市場。
- `security_directory.sector` 只涵蓋上市。上櫃和 ETF 是 NULL（`directory/models.py`）。而且它是**同步當下的快照**，沒有歷史分類。
- 本雲端開發環境打不到 TWSE／TPEx（`directory/sync.py`、`tpex.py` 檔頭都有記錄）。所有真實抓取只能在 CEO 本機跑。

## Options（選項比較）

### A. 模組邊界

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **A1 新 package `app/sectors/`（純計算＋自有 store），評估碼放 `app/backtest/sector_eval.py`，編排放 `app/services/sector_board.py`（採用）** | 排名／評分有獨立的家，不污染 `signals` 的「純量測」定位。評估碼（會讀未來資料）和線上碼分屬不同 package，可以用 import-graph 硬性隔離 | 多一個 package、多一組邊界測試 | 低 |
| A2 併入 `app/signals` | 少一個 package | `signals` 明文不出 score；它被 advice、alerts、playbook 廣泛依賴，族群排名一進來，建議卡就能隨手取用 | 動能排名悄悄流進建議卡或風險上限，構成未經風控的推薦 → 否決 |
| A3 併入 `app/advice` | 可沿用規則引擎 | advice 是單一標的＋整書風險上限，會把 ADR-0010 的 IO 預算（`build_summary`）帶進首頁；候選股和建議動作混在一起就是推薦 | 否決 |
| A4 全放 `app/backtest` | 回測與線上天然共碼 | 線上服務要依賴回測套件；計算 forward return 的碼和線上路徑同一個 package，look-ahead 守門只能靠自律 | 否決 |

### B. 全市場日線的儲存

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| B1 共用 `price_bars_cache` | 只有一張價格表；觀測到的市場日曆更完整 | `put()` 最後寫入者勝出：bulk 來源會覆寫持倉序列的列，持倉頁因此常駐 `MIXED_SOURCES_REASON`。bulk 列若不寫 fetch log，layer 0 用不上；若寫，會扭曲 ADR-0009「單一連續 coverage」的語意。`market_trading_days`／`market_has_session` 的掃描面放大約兩個數量級。每列多存兩個 ISO 時間戳，浪費空間 | 持倉資料鏈的行為和揭露句被非持倉的工作改變 → 否決 |
| **B2 獨立表 `market_daily_bars`＋`market_ingest_log`，同一個 SQLite 檔（採用）** | 持倉資料鏈零改動；以「交易日×交易所」為單位記錄抓取；schema 可以精簡 | 同一檔股票會有兩份價格（持倉鏈一份、bulk 一份），來源不同時數值可能不同 | 見 Consequences |
| B3 另開 SQLite 檔，或改用 DuckDB／Parquet | 隔離最好；列式分析快 | 偏離 ADR-0002（DuckDB 已被否決）；要新增依賴；備份點變成兩處 | 否決。DB 量體到 GB 級再另立 ADR |

### C. 計算時點

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **C1 收盤後批次預算並落表，首頁只讀（採用）** | 請求零 HTTP、SQL 次數固定；排名、成分股、命中率三者出自同一次計算、同一個 `method_version`，可重現、可稽核 | 排程沒跑就是舊資料（要揭露）；多一個排程工作；盤中看到的是前一交易日的結果（本來就是日線，不算退步） | 冷啟動時沒有資料 → 回 `insufficient_data` 並附原因 |
| C2 請求時即時計算 | 沒有排程依賴 | 每次請求要讀約 4 萬～12 萬列（約兩千檔 × 21～61 個交易日，粗估），逐列解析 Decimal 再做 pivot；成分股的 MA60／RSI 要 60 根以上。命中率要用整段歷史，請求內根本算不完，只能另外落表，而那樣就退化成 C1 加上 skew 風險 | 違反 ADR-0010 精神；排名與命中率可能來自不同版本的計算 → 否決 |
| C3 批次加程序內 memo | 首次請求之後都快 | 第一次請求仍然慢；API 和 scheduler 兩個程序各持一份（ADR-0010 D-5 同樣的問題） | 不需要：C1 讀表本身已經夠快 |

### D. 回測與線上排名的關係

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **D1 同一段純函式，以 `PointInTimePanel` 型別守門：線上算最新一天，評估器逐日回放（採用）** | 沒有 training/serving skew；look-ahead 守門集中在一個型別上 | 評估器逐日回放較慢（約一千多個交易日，粗估數十秒以內） | 低 |
| D2 線上用 SQL，回測用 pandas，各寫一套 | 線上可能更快 | 兩套實作必然漂移，顯示的命中率不屬於畫面上的排名 | 否決 |
| D3 線上直接取回測輸出的最後一天 | 共碼 | 線上可用性被綁在較重的評估工作上；評估器失敗就沒有排名 | 否決。改成 D1，讓兩個工作分開、各自可失敗 |

### E. 新依賴

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **E1 不新增（採用）**：pandas、numpy、APScheduler（`CronTrigger`）、stdlib 已足夠；`app.backtest.episodes.wilson_interval` 已經存在；精確二項檢定可以用 `math.comb` 寫 | 零供應鏈變動 | 較進階的檢定要自己寫 | 低 |
| E2 scipy | 統計檢定齊全 | 新依賴、體積大；只為了一個檢定 | quant 若需要 block bootstrap 以外的方法，再另外立案 |
| E3 polars／DuckDB | 快 | 偏離 ADR-0002 | 否決 |

## Decision（決策）

- **D-1（套件配置與依賴方向）**

  ```
  app/data/market_panel.py        # store: market_daily_bars, market_ingest_log (I/O)
  app/data/market_panel_sync.py   # bulk ladder + ingest job + CLI (network)
  app/data/providers/*_bulk.py    # MarketSnapshotProvider adapters
  app/sectors/                    # pure core + own store
      models.py  params.py  panel.py  index.py  ranking.py  constituents.py  membership.py
      store.py                    # sector_board*, sector_rank_stats, membership snapshots (I/O)
  app/backtest/sector_eval.py     # walk-forward hit-rate; the ONLY place forward returns are computed
  app/services/sector_board.py    # orchestration: panel -> sectors -> sector_eval -> store
  app/api/sectors.py              # read-only router
  app/api/sectors_wording.py      # risk-approved sentences, imports nothing from app.*
  ```

  依賴方向：
  - `api.sectors → sectors.store / sectors.models / data.market_panel（唯讀）`
  - `services.sector_board → {data.market_panel, sectors.*, backtest.sector_eval}`
  - `backtest.sector_eval → sectors 純核心`
  - `sectors 純核心 → {signals.*, data.interface, data.calendar, positions.sectors}`
  - **`app.sectors` 不得 import `app.backtest`**。反方向（backtest 依賴 sectors）與既有的「backtest 依賴 signals」同構。

- **D-2（全市場日線是獨立資料鏈，不寫、不讀 `price_bars_cache`）**
  - 新表 `market_daily_bars`：
    - 主鍵 `(trade_date, exchange, symbol)`，`WITHOUT ROWID`，供橫斷面讀取。
    - 次索引 `(symbol, trade_date)`，供成分股序列讀取。
    - 欄位：`market`（沿用 `Literal["TW"]`）、`exchange`（`TWSE`｜`TPEX`）、OHLC（Decimal 字串）、`volume`（一律正規化為「股」）、`change`（漲跌價差，可為 NULL）、`source`。
    - 列上**不存** `as_of`／`fetched_at`，由 ingest log 以「交易日×交易所」為單位承擔。
  - 新表 `market_ingest_log`：
    - 主鍵 `(exchange, trade_date)`。
    - `status` ∈ {`ok`, `partial`, `empty_unconfirmed`, `closed`, `failed`}，另有 `source`、`row_count`、`fetched_at`、`last_attempt_at`、`reason`。
    - `empty_unconfirmed` 只有在「之後某個交易日已經 `ok`，而該日仍然是空的」時才升級為 `closed`。這是**全市場層級**的推論，理由與 ADR-0009 Options E 否決單一序列負向推論的理由不衝突，因為全市場端點回空的成因遠比單一序列單純。
    - **這個 `closed` 判定只存在於 `market_ingest_log`，不得回饋給 `freshness.judge()`**。要回饋，須修訂 ADR-0009。

- **D-3（新 provider 介面）**
  - 在 `app/data/interface.py` 新增與 `MarketDataProvider` 同層的抽象類別 `MarketSnapshotProvider`：

    ```python
    class MarketSnapshotProvider(ABC):
        source_id: ClassVar[str]
        exchange: ClassVar[Literal["TWSE", "TPEX"]]

        @abstractmethod
        def get_market_snapshot(self, trade_date: date) -> SnapshotResult:
            """All securities' daily bars for one session on one exchange.
            Must not raise for expected failures; returns status UNAVAILABLE."""
    ```

  - `SnapshotResult` 帶 `bars`、`status: DataStatus`、`as_of`、`source`、`complete`、`reason`，以及 `published: bool | None`。`published` 表示端點本身能否區分「該日無交易」與「失敗」，能不能區分由 DE-1 決定。
  - 梯子：主來源是各交易所的全市場端點，備援是 FinMind（DE-2）。沒有 cache 層，因為表本身就是儲存。
  - 同一程序內，同一個 host 只能有一個 `RateLimitedClient`（比照 `deps._default_yfinance` 的單例原則）。

- **D-4（除權息，條件式，待 DE-5／Q-1）**
  - 族群報酬**不得**直接用「未還原收盤價比值」跨越除權息日計算。
  - 三個候選：
    - (a) 用漲跌價差推日報酬，`r_t = change_t / (close_t − change_t)`。前提是 DE-1 確認漲跌價差以除權息參考價為基準。
    - (b) 全市場除權息事件，套用 `app.dividends.adjust`。
    - (c) 視窗內有除權息日的標的，在該視窗剔除。
  - 架構師傾向 (a)：零額外資料源，而且和交易所公告的漲跌幅同口徑。
  - 不管選哪一個，報酬函式都只能有一處，放在 `app/sectors/index.py`。

- **D-5（盤後批次）**
  - scheduler 新增一個 job `sector_board_refresh`。用 `CronTrigger`，時區 `Asia/Taipei`，只在平日跑，一天可排多次補跑；首次時間必須晚於 `policy_for("TW").publish_cutoff`，確切時點列管 devops-sre／DE-7。啟動時立即補跑一次，比照 ADR-0010 D-4。
  - 一次 job 依序做三件事，每一步各自可失敗、各自記錄：
    1. ingest：對 `expected_session` 之前還沒有 `ok` 的交易日補抓。已經 `ok` 就跳過，冪等。
    2. 計算 board：寫入 `sector_board`、`sector_board_constituents`，以 `(trade_date, method_version)` 為鍵。
    3. 評估：`sector_eval` 寫入 `sector_rank_stats`，只新增列、不覆寫歷史列（backtest-protocol「不刪除難看結果」）。
  - 第 3 步失敗時第 2 步照樣生效，只是 API 的 `history` 會是 null，措辭強制降級（D-8）。
  - 歷史回補（backfill）**只走 CLI**：`python -m app.data.market_panel_sync --backfill --since YYYY-MM-DD`。在 CEO 本機執行，**每個交易日一個 transaction**，不做單一巨型 transaction。可以中斷後續跑。節流值由 DE-3 查證後寫進常數。
  - scheduler **不得**自動觸發 backfill。

- **D-6（計算核心與 look-ahead 守門層）**
  - 線上和評估器共用 `app/sectors/ranking.py::rank_sectors` 與 `constituents.py::score_constituents`。這兩個函式**只接受 `PointInTimePanel`**：

    ```python
    @dataclass(frozen=True)
    class PointInTimePanel:
        as_of: date
        frame: pd.DataFrame  # rows with trade_date <= as_of only; enforced in truncate()
        @classmethod
        def truncate(cls, panel: MarketPanel, as_of: date) -> PointInTimePanel: ...

    def rank_sectors(
        panel: PointInTimePanel, membership: MembershipView, params: RankingParams
    ) -> SectorRanking: ...
    ```

  - 分類也要 point-in-time。`MembershipView.at(t)` 取 `snapshot_date ≤ t` 的最新快照；t 早於最早快照時，退回最早快照並設 `membership_backfilled=True`。
  - **forward return 只准出現在 `app/backtest/sector_eval.py`**。評估器的執行延遲參數 `execution_lag_sessions` 必須 ≥ 1，傳入 0 就拋 `ValueError`。理由：排名要等收盤公布後才算得出來，不可能在同一個收盤成交。
  - `method_version`（例如 `"sector-momentum-v1"`）是 `params.py` 的常數。任何參數變動都要升版；統計列與 board 列都以它為鍵，API 只把同版本的兩者配在一起。

- **D-7（成分股分數）**
  - 輸入限定為 `app.signals.*` 的量測值，以及 D-1 面板上算得出來的量。**禁止使用 `app.advice` 的任何輸出**（action、confidence、weight、matched_rules）。
  - 若 PRD／Q-7 決定沿用「五項觀察條件」，`five_condition_series` 要從 `app.backtest.strategies` 下移到 `app/signals/observations.py`（純量測、無 I/O）。`app.backtest.strategies` 改成從 signals import（re-export 保持相容），既有事件研究與 look-ahead 測試必須逐字不改而且全綠。
  - 分數的組合方式（加權、排序、並列時用 symbol 決勝）放在 `app/sectors/constituents.py`，不放在 `signals`。

- **D-8（措辭層級由後端判定）**
  - `wording_tier` ∈ {`probability`, `strength_only`}，只由後端根據 `sector_rank_stats.meets_threshold` 決定。門檻由 Q-5 在樣本內定案，並以 `method_version` 凍結。
  - 以下情況一律回 `strength_only`：沒有同版本統計、`trials` 低於 quant 訂的最低樣本數、`membership_backfilled=True` 且風控要求降級。
  - 前端只把 tier 對應到風控核可的字面（`app/api/sectors_wording.py` 與前端常數），**不自行判斷**。

- **D-9（基準，條件式，待 Q-2）**
  - 架構師傾向用**同一面板算出的等權全市場指數**當基準。理由有三：
    1. 和等權族群指數是同口徑比較（apples to apples）。
    2. 不依賴 yfinance 的 `^TWII`；那條路恆為 `backup`，而且未經查證（ADR-0005）。
    3. 除權息處理和族群指數同一套。
  - 加權指數是市值加權，受單一權值股主導，「跑贏大盤」會退化成「跑贏權值股」。
  - 如果 quant 選用加權指數，必須走既有的指數路徑，並揭露 `backup` 狀態。

### API 形狀（D-10）

`GET /api/sectors/momentum?market=TW&limit={N}`

- `limit` 預設值和上限由 PRD 決定。`market` 第一階段只接受 `TW`；其他值回 `insufficient_data`。
- 端點**零 HTTP**，SQL 語句數固定、與族群數和全市場檔數無關，上限是 6 條。
- 端點不呼叫 `load_bars`、`MarketDataService`、`build_summary`，也不做任何計算。

```python
class SectorMetrics(BaseModel):
    rel_return_5d: float | None
    rel_return_20d: float | None
    advance_ratio: float | None      # advancing members / members with a bar
    volume_change: float | None      # definition per methodology Q-3

class SectorHistoryStats(BaseModel):
    rank_position: int
    horizon_sessions: int            # 5 in phase 1
    execution_lag_sessions: int      # >= 1
    trials: int
    successes: int
    hit_rate: float
    ci_low: float | None             # Wilson (app.backtest.episodes)
    ci_high: float | None
    oos_start: str                   # out-of-sample only (backtest-protocol)
    oos_end: str
    meets_threshold: bool
    computed_at: str

class ConstituentItem(BaseModel):
    symbol: str
    name: str                        # denormalised at compute time
    market: str
    score: float
    score_components: dict[str, float | bool | None]
    last_bar_date: str

class SectorItem(BaseModel):
    rank: int
    sector: str                      # one of TWSE_SECTORS (+ TPEx mapping per DE-4)
    member_count: int
    metrics: SectorMetrics
    history: SectorHistoryStats | None
    top_constituents: list[ConstituentItem]   # <= 3, deterministic order

class SectorBoard(BaseModel):
    trade_date: str
    computed_at: str
    method_version: str
    benchmark: str                   # e.g. "ew_all_market"
    wording_tier: Literal["probability", "strength_only"]
    universe_exchanges: list[str]    # ["TWSE"] or ["TWSE", "TPEX"]
    universe_symbol_count: int
    excluded_counts: dict[str, int]  # reason -> count (no sector, illiquid, ...)
    membership_as_of: str
    membership_backfilled: bool

class SectorMomentumResponse(BaseModel):
    market: str
    status: PayloadStatus            # "ok" | "insufficient_data"
    reason: str | None
    board: SectorBoard | None
    sectors: list[SectorItem]
    disclosures: list[str]           # risk-approved, always rendered
    data: DataMeta                   # reused unchanged, mapping below
    as_of: str
```

`DataMeta` 沿用，不加欄位，前端 `DataMetaStatusBadge` 不必改。語意對應如下（寫進 schema docstring）：

- `status`：有 board 時恆為 `cached_stale`，因為這是本機預算結果；沒有 board 時為 `unavailable`。
- `source`：board 那個交易日實際 ingest 的來源。多個來源用 `+` 連接，完整清單放在 `reason`。
- `staleness_minutes`：現在減去該交易日 ingest 的 `fetched_at`；有兩個交易所時取較舊者。
- `is_within_ttl`：`board.trade_date ≥ freshness.expected_session(policy_for("TW"), …)`。
- `bar_count`：面板視窗的交易日數。`first_bar_date` 是視窗起日；`last_bar_date` 是 `board.trade_date`，徽章「資料截至」讀這個欄位。
- `trading_days_behind`：`market_ingest_log`（狀態 `ok`）在 `board.trade_date` 之後又觀測到幾個交易日。`market_panel` store 實作 `TradingCalendarSource`，直接重用 `trading_days_behind_market`。
- `reason`：ingest `partial`、備援來源、分類回補等原因句，用 `_combine_reasons` 的慣例串接。所有字面都要經風控核可。

### 對實作的約束（逐條可檢查）

- **C-1**：`app.sectors` 底下任何模組，transitively 可達的 `app.*` 模組必須是白名單的子集，白名單為 `app.sectors.*`、`app.signals.*`、`app.data.interface`、`app.data.calendar`、`app.positions.sectors`。`app.sectors.store` 額外允許 `app.data.cache`，只能用來取 `resolve_db_path`。
- **C-2**：`app.sectors` 不得可達 `app.backtest`、`app.advice`、`app.playbook`、`app.kelly`、`app.portfolio`、`app.alerts`、`app.api`、`app.services`、`app.data.providers`、`app.data.service`、`app.data.http`，也不得 import `httpx`。
- **C-3**：反方向同樣禁止：`app.advice`、`app.playbook`、`app.kelly`、`app.portfolio`、`app.alerts`、`app.signals` 都不得可達 `app.sectors`。族群動能要進入建議卡、風險上限、指令或警示，須另立 ADR 並經風控審查。
- **C-4**：`app.backtest` 只能 import `app.sectors` 的純核心，不得 import `app.sectors.store`。
- **C-5**：`app.api.sectors` 的直接 import 不得包含 `app.advice`、`app.data.service`、`app.services.market`、`app.portfolio`、`app.backtest`。
- **C-6**：`/api/sectors/momentum` 零 HTTP，SQL 語句數 ≤ 6 條，而且與族群數和檔數無關。
- **C-7**：任何程式碼都不得把 bulk 資料寫進 `price_bars_cache`、`price_bars_fetch_log`、`price_bars_attempt_log`。持倉資料鏈（`load_bars`、`MarketDataService`、`get_cached_bars`）第一階段不得讀 `market_daily_bars`。
- **C-8**：`scheduler.refresh_market_data` 的行為和 `DATA_REFRESH_LOOKBACK_DAYS` 不變。族群工作是另一個 job id，`max_instances=1`，`coalesce=True`。
- **C-9**：新增的 store 一律在 `_connect` 設 `PRAGMA busy_timeout`，比照 `PriceBarCache`。注意現行 `SecurityDirectoryStore` 沒有設，**不得照抄它的寫法**。
- **C-10**：寫入 `market_daily_bars` 時，一個 transaction 最多一個交易日加一個交易所。backfill 不得由 scheduler 觸發。
- **C-11**：`rank_sectors`、`score_constituents` 的面板參數型別是 `PointInTimePanel`，不接受裸的 `DataFrame` 或 `MarketPanel`。`PointInTimePanel` 只能經由 `truncate()` 建立。
- **C-12**：forward return 只出現在 `app/backtest/sector_eval.py`；`execution_lag_sessions < 1` 會拋錯。
- **C-13**：`method_version` 只有一處定義；統計列與 board 列都以它為鍵；API 不跨版本配對。
- **C-14**：`sector_rank_stats` 只新增列，不 UPDATE、不 DELETE。API 只顯示樣本外（OOS）區間的統計。
- **C-15**：`wording_tier` 只由後端決定；前端不得用 `hit_rate` 自行推導措辭。
- **C-16**：成分股分數不得使用 `app.advice` 的任何輸出。若要沿用五項觀察條件，須依 D-7 下移，而且既有測試不得修改。
- **C-17**：報酬計算只有一處，在 `app/sectors/index.py`，並依 D-4 處理除權息；不得用裸的收盤價比值跨越除權息日。
- **C-18**：`market_ingest_log` 的 `closed` 判定不得被 `app/data/freshness.py` 或 `app/data/service.py` 讀取。
- **C-19**：所有使用者可見字面，包括 `disclosures`、`reason`、tier 對應句，都要經 risk-compliance-officer 核可並逐字鎖定在常數與測試裡。
- **C-20**：真實端點的 URL、欄位、單位都依 DE-1 查證結果撰寫，adapter 檔頭要有 `VERIFICATION STATUS`，比照 `twse.py`。

## 測試策略（全部離線，用 `httpx.MockTransport`／合成 fixture）

- **T-1 邊界測試** `tests/test_sectors_boundary.py`：沿用 `tests/import_graph.py`，涵蓋 C-1～C-5。
  - 比照 `test_playbook_boundary.py`：要求 `app/sectors/*.py` 每一個檔都列入守門清單，並驗證每個守門模組名稱都解析得到（防止拼錯讓測試變空洞）。
  - 要有 teeth test：證明 `app.api.backtest` 可達 `app.backtest` 時，掃描確實抓得到。
- **T-2 零 IO**：注入一個「任何呼叫即拋錯」的 resolver 和 HTTP transport，端點仍回 200。用 `sqlite3.Connection.set_trace_callback` 計數 SQL 語句數 ≤ 6，並在 10 個與 200 個族群的 fixture 下數值相同（C-6）。
- **T-3 資料鏈隔離**：跑完一次 ingest 後，`price_bars_cache`、`price_bars_fetch_log`、`price_bars_attempt_log` 的列數與 checksum 不變；`refresh_market_data` 的既有測試全綠（C-7、C-8）。
- **T-4 ingest 語意**：
  - 部分成功記 `partial` 而不是 `ok`。
  - 重跑冪等。
  - 回空記 `empty_unconfirmed`；之後的交易日 `ok` 才升級為 `closed`。
  - 張與股的單位正規化。
  - 每個交易日一個 transaction（C-10）。
- **T-5 未來不變性（look-ahead，決定性）**：對隨機的 t，以下三種情況下 `rank_sectors` 與 `score_constituents` 的輸出必須完全相同：原始面板截到 t；在 t 之後附加亂數列；把 t 之後的列改成極端值。此外要驗證 `PointInTimePanel.truncate` 以外的建構方式會失敗（C-11）。
- **T-6 平移敏感（backtest-protocol 鐵律 2）**：在「動能會延續」的合成面板上，把排名序列往未來平移一格，命中率必須實質改變；同時用常數訊號證明偵測器有牙齒，比照 `test_lookahead_detection.py`。
- **T-7 線上與回測一致**：同一份 fixture 面板，批次 job 寫入的 `(trade_date=t)` 排名和成分股，必須等於 `sector_eval` 在 t 的回放結果，逐欄相等（D-6）。
- **T-8 延遲與版本**：`execution_lag_sessions=0` 拋錯；版本不符時 `history` 為 null，而且 tier 是 `strength_only`（C-12、C-13、D-8）。
- **T-9 分類 point-in-time**：`MembershipView.at(t)` 只取 `snapshot_date ≤ t` 的快照；t 早於最早快照時 `membership_backfilled=True`。
- **T-10 字面鎖定**：風控核可的句子要在後端常數測試和前端 `*.test.ts` 兩邊都逐字釘住（C-19）。

## Consequences（後果）

- **好處**
  - 首頁卡片零 HTTP、SQL 語句數固定；持倉資料鏈、ADR-0009 冷卻與 ADR-0010 預算都**不受影響**。
  - 排名、成分股、命中率三者同版本、同一段計算碼，可以重現、可以稽核。
  - look-ahead 從「靠審查者細心」變成「型別加 import-graph 加決定性測試」三道防線。
  - 每日增量抓取只是「每個交易所每個交易日」一到兩次 HTTP，遠少於逐檔抓取（DE-1 確認後生效）。
- **代價（照實計）**
  - **DB 量體**：粗估約兩千檔 × 每年約 245 個交易日，約 49 萬列／年，精簡 schema 約 60 MB／年；5 年約 300 MB。這是架構師估計，DE-6 要實測。SQLite 檔和備份都會從 MB 級變成百 MB 級。
  - **backfill 負擔**：只能在 CEO 本機跑，雲端環境 egress 被封鎖。歷史深度（Q-9）直接決定請求數與耗時。
  - **跨程序限流沒有共享**：API 程序和 scheduler 程序各有自己的 `RateLimitedClient`。若 bulk 端點和 `STOCK_DAY` 同一個 host，兩個程序合計的速率可能超過交易所容忍度。若 IP 被封鎖，持倉資料鏈會降級到 FinMind，結果是持倉頁出現混源揭露。每日增量的量很小，風險主要在 backfill（DE-3）。
  - **同一檔兩份價格**：首頁成分股的 5／20 日報酬（bulk 面板，依 D-4 還原），可能和點進個股頁看到的價格走勢（持倉鏈，未還原）數字不同。需要一句風控核可的揭露，或由 PRD 決定首頁不顯示單檔報酬數字。
  - **分類 look-ahead**：分類快照只從本 ADR 落地那天開始累積，更早的歷史回測只能套用現行分類，會有倖存者偏差與重新分類的偏差。`membership_backfilled` 會常駐揭露，偏差大小由 Q-6 評估。
  - **覆蓋率缺口**：上櫃沒有產業別（DE-4 未解之前），第一階段可能只涵蓋上市。例如記憶體族群的上櫃成員會缺席，`excluded_counts` 必須在畫面上可見。
  - **盤中顯示前一交易日結果**：D-5 第一次跑之前，當日排名不存在。這是日線的本質，由徽章揭露。
  - **多一個排程工作、七張新表**：維運面增加（devops-sre）。
- **已知限制**
  - `market_trading_days` 和 ADR-0009 D-3 的正向證據沒有吃到 bulk 面板這個更完整的日曆證據，這是刻意維持持倉鏈零改動的代價。
  - 持倉鏈改由 bulk 面板供價（每日一次請求就涵蓋所有持倉）是很有吸引力的後續方向，但會改變 ADR-0009 的 coverage 語意與混源揭露，**須另立 ADR**。

## 與既有 ADR 的關係（§7）

- **ADR-0002**：不取代。其約束「所有市場資料存取走 `MarketDataProvider` 抽象介面」，本 ADR 解讀為「走 `app/data` 內可替換的抽象介面」，並新增同層的 `MarketSnapshotProvider`。若 CEO 要求字面遵守，替代作法是在 `MarketDataProvider` 加一個預設 `NotImplementedError` 的 `get_market_snapshot`，代價是既有六個 adapter 都要表態。請 CEO 在核可時一併裁定。
- **ADR-0009、ADR-0010**：不取代、不修訂。C-7、C-8、C-18 保證兩者的行為不變。
- **ADR-0005**：若 Q-2 選用加權指數，沿用指數路徑 `backup` 紀律。
- **ADR-0004、ADR-0006**：不涉及；C-3、C-16 保證建議引擎與 Kelly 輸入不受影響。

## 開放問題（§8，定案前必須回答，需記錄查證日期）

**data-engineer**（`work/stock-desk-族群動能-資料評估.md`）

- **DE-1**：TWSE 上市、TPEx 上櫃「可指定日期」的全市場單日日線端點。需要：路徑與參數、欄位（是否含漲跌價差和參考價，漲跌價差是否以除權息參考價為基準）、可回溯多遠、成交量單位、休市日的回應形狀（能否區分休市與失敗）。另外要確認 `STOCK_DAY_ALL` 是否只回最新一日，若是，就不能用於 backfill。
- **DE-2**：FinMind 在 CEO 現有 token 等級下，能否不指定 `data_id` 查全市場單日；額度多少。
- **DE-3**：TWSE／TPEx 的速率界線與封鎖行為（實測值），用來訂 backfill 節流常數。
- **DE-4**：上櫃產業別的來源與代碼對照；以及 ETF、特別股、權證、存託憑證、全額交割股、處置股的排除規則。
- **DE-5**：除權息處理方式，D-4 的 (a)、(b)、(c) 三選一，附驗證。
- **DE-6**：實測每日列數、每列位元組數、N 年 DB 增量、一次 backfill 的耗時。
- **DE-7**：bulk 端點的實際公布時間；它可能與 `STOCK_DAY` 不同，而 15:00 這個值本身也未經查證（ADR-0009 D-2）。
- **DE-8**：下市、暫停交易的標的在 bulk 回應中怎麼呈現（關係到倖存者偏差）。

**quant-researcher**（`work/stock-desk-族群動能-方法論.md`）

- **Q-1**：族群指數怎麼建：等權、成分股最低家數、流動性門檻、漲跌停與處置股怎麼處理。
- **Q-2**：基準選等權全市場還是加權指數（架構師傾向前者，見 D-9）。
- **Q-3**：排名訊號的合成方式、`volume_change` 的定義、並列時怎麼排。
- **Q-4**：命中率定義：
  - 視窗起點與 `execution_lag_sessions` 設多少；
  - 重疊的 5 日視窗怎麼處理（non-overlapping，或 block bootstrap）；
  - 顯著性檢定用什麼方法，能否不用 scipy；
  - walk-forward 的窗長；最低樣本數。
- **Q-5**：「降級為純強弱」的量化門檻，須在樣本內決定並以 `method_version` 凍結。
- **Q-6**：只有現行分類時，分類 look-ahead 的影響多大；歷史回測從哪天起算。
- **Q-7**：成分股分數的定義；它本身是否也需要回測證據（沒有證據就列三檔股票，在風控上接近推薦）；是否沿用五項觀察條件（會觸發 D-7 的下移）。
- **Q-8**：命中率要不要計入換手成本，還是另外並列淨報酬。
- **Q-9**：需要多少年的歷史，這會決定 backfill 的範圍與 DB 量體。

**其他部門**

- **product-manager**：N 值、版位、第一次盤後計算之前首頁顯示什麼、落後幾個交易日就隱藏卡片、首頁是否顯示單檔報酬數字。
- **risk-compliance-officer**：
  - 候選股列示是否構成推薦；
  - `strength_only`／`probability` 兩個層級的字面；
  - 以下情況的揭露句：面板混源、分類回補、覆蓋率缺口、同一檔兩份價格。
- **devops-sre**：cron 時點與補跑策略、scheduler 在 CEO 本機是否常駐、DB 備份量、backfill 操作手冊。
