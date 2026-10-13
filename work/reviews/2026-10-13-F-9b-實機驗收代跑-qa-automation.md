# F-9b 實機驗收代跑報告（e2e-fallback）— qa-automation

> 轉存：coordinator，2026-10-13，子 agent 回報逐字轉存。只含事實，判讀由 qa-e2e 出具。
> 受測：feat/stock-desk-f9b HEAD d40e95e（worktree，未 push）。截圖與原始 JSON 留在 scratchpad，不入 repo。

---

# F-9b e2e-fallback 代跑報告（qa-automation 代跑；只交事實，不下 Verdict / BLOCKING_ISSUES）

以 e2e-fallback 代跑，代跑者：qa-automation。所有產出在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-f9b/`（下稱 `$O`）。截圖共 235 張在 `$O/shots/`，逐項 JSON 在 `$O/out/`。截圖只留在 scratchpad，驗收結束後可刪。

## 0. 先講必須知道的四件事（偏離與限制）

1. **「庫存頁 T-12」在實際 UI 上位於首頁「持倉明細表」（`PositionsTable`），不在 `/positions` 編輯庫存頁。** `/positions` 兩個寬度都沒有 T-12 文字，也沒有「查無」（`out/inventory-375.json`、`inventory-1280.json`：`hasT12=false`、`hasChaWu=false`）。第 6、7 項因此量測首頁表格；`/positions` 另有截圖。
2. **fixture 偏離（已揭露，請 qa-e2e 判斷是否忠實）：** launcher 把 `PriceBarCache.record_attempt` 換成 no-op（預設 `F9B_ARM_COOLDOWN=0`），讓每次請求都重跑梯子。原因：真實行為下同一標的第二次請求會變成冷卻句（見第 6 節補充實測），W-c 等字面只會在第一次請求出現一次，無法跨 bars／signals／advice／limits 多支端點穩定驗證。KO 的 T-15 另走「seed 一筆近期失敗 attempt」的真實冷卻分支。
3. **第 9 項 playbook：** 緊急出清的 `Directive.data_reason` 只在 `POST /api/playbook/emergency-exit` 回應 JSON 出現。出清後頁面（`EmergencyExitControl`）只印 `message`、`mode_reason`、`attribution` 與 `warnings`，沒有渲染 directives 清單。第 9 項「ledger 中 W-b 標的的 data_reason」在頁面上看不到，只能交 API 原文（第 5 節）。**第 9 項 alerts 同理：** 設定頁「手動檢查一次」只印計數句，不印 skip 原因；原因原文只在 `POST /api/alerts/evaluate` 回應。
4. **首頁用 live valuator，不會出現 W5。** W5 只在 cache-only 的建議卡出現（程式與實測一致）。第 8 項首頁只有 W4→(b)→T-11 三組，建議卡才有完整四組。

## 1. 環境探測與 provenance
- `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`；瀏覽器 `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`。
- `npm root -g` = `/opt/node22/lib/node_modules`；`require.resolve('playwright')` = `/opt/node22/lib/node_modules/playwright/index.js`，版本 1.56.1；node v22.22.2。
- runner 輸出的 provenance（stdout 原樣）：`playwrightModule=/opt/node22/lib/node_modules/playwright/index.js`、`chromiumExecutable=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`、`trustedPrefix=/opt/`、`scriptPath=$O/runner_common.js`。
- runner 開頭有 fail-closed 前綴斷言，放在 scratchpad（受測樹之外）；沒有 `ABORT`。
- 未安裝任何東西。所有行程設 `HTTP(S)_PROXY`／`ALL_PROXY` 大小寫兩組 = `http://127.0.0.1:9`，`NO_PROXY=127.0.0.1,localhost`（大小寫）。瀏覽器以 `ctx.route` abort 所有非 loopback 請求。
- 後端：主工作樹 `.venv/bin/python`（uvicorn）搭配 `PYTHONPATH=<worktree backend>:$O`，已驗證載入的 `app` 來自 worktree（backend log 第一行 `LAUNCH-F9B … app=…/agent-a14fc7d2aaea1c99b/…/app/__init__.py`）。設 `PYTHONDONTWRITEBYTECODE=1`。cwd 為 `$O`。
- 前端：把主工作樹 `node_modules` 用 `cp -a` 複製進 worktree，`rm -rf .next` 後 `next build`（Next.js 16.3.3 Turbopack，exit=0，`$O/frontend-build.log`），再 `next start --port 3000`。
- 資料庫三個環境變數都指向 `$O/db/…`（`STOCK_DESK_DB_PATH`、`…_MARKET_DB_PATH`、`…_RESEARCH_DB_PATH`）。沒有讀 `.env`；`ALPHA_VANTAGE_API_KEY`、`FINMIND_API_TOKEN` 已 unset。

## 2. 前後狀態（`$O/state-before.txt`、`$O/state-after.txt`）
| 項目 | 前 | 後 |
|---|---|---|
| worktree HEAD | `d40e95e112069c4376b8857452fa86b527f90a30` | 同（未變） |
| worktree `git status --short` | 空 | 空（已刪我複製的 `node_modules`、`.next`、build 產生的 `next-env.d.ts`） |
| `backend/data/stock-desk-market.db`（主工作樹，只 stat） | size=98304 mtime=1791126586 ino=501649 | 同 |
| `backend/data/stock-desk.db`（主工作樹，只 stat） | size=159744 mtime=1791123341 ino=500014 | 同 |
| worktree `backend/data/` | 不存在 | 不存在 |
| 主工作樹 `git status --short` | 空 | 空 |
| 主工作樹 HEAD | `284b1a4fd8fcc61d1b6608b592b39419a0d5f719` | `7fafff5d9db8758f9622607d44a728b2c7492f45` |

- 主工作樹 HEAD 在我跑的期間變了，不是我造成的（我沒對主工作樹下任何 git 寫入）。推測是別的 agent 提交，無法確認。
- `git status --short --ignored` 在結束時列出 worktree backend 的 `.venv/`、`.mypy_cache/`、`.ruff_cache/`、`__pycache__/`。我開始時 `ls` worktree backend 沒看到 `.venv`；我沒有建立它。跑的期間 `ps` 看過別的 agent 在 worktree 跑 `.venv/bin/python -m pytest`（PID 11552，非我起的，我沒碰）。這些都是 gitignored。
- 3000／8000／8001／8099 起跑前無人占用；結束時我起的行程（fx stub 14648、backend 14649、frontend 14650、armed backend 20069）已停，`ps -eo pid,comm` 無 node／uvicorn／python／chrome 殘留，四個 port 都連不上。

## 3. fixture 設計與狀態對照
真實的 `MarketDataService`（admission、幣別閘門、快取閘門、W-d、valuator、book notes）完整執行。我只替換 `app.api.deps` 構造的五個 adapter 類別（AV、TWSE、TPEx、FinMind 用腳本化 rung；yfinance 用繼承真 `YFinanceAdapter` 的子類，只覆寫 `get_daily_bars`，指數與 FX 角色不動）。FX 兩個 base URL 指向 loopback 假上游 `:8099`，與前例同法；匯率為合成值，永遠回應。快取列與持倉由 prep 腳本經真 API（`PriceBarCache.put`、`PositionStore.create`）寫入 scratch DB。所有數據皆為合成示範資料。

| 代號 | 市場 | 造法 | 預期進入的閘門分支 |
|---|---|---|---|
| RY.TO | US | 多字元字尾 | W-a（admission，未呼叫任何 rung；provider-calls.log 無此代號） |
| 2330K | TW | 數字＋K | W-b（同上） |
| MSFT | US | AV 回 CAD bars；yfinance 無 bars、無 reason | W-c 美，無快取 |
| 2317 | TW | TWSE 回 USD bars | W-c 台，無快取 |
| NVDA | US | AV 回空幣別 bars | W-c′ 美，無快取 |
| 2454 | TW | TWSE 回空幣別 bars | W-c′ 台，無快取 |
| AAPL | US | AV 回空幣別；yfinance 回 `yfinance 連線逾時或發生錯誤，暫不可用。`；快取 USD 335 根 | C-34(b) 兩層合併 reason |
| GOOG | US | AV 回空幣別；yfinance 無 reason；快取 USD；`opened_at=None` | C-34(b) 單層；同時是 W4 來源（fx_open 缺） |
| AMZN | US | 同 GOOG，但快取前 150 根 source=alpha_vantage、後 185 根 source=yfinance | C-34(b) 拼接（F9W-37 (c)） |
| 3008 | TW | TWSE 回空幣別；快取 TWD | W-c′ 台＋快取（第 7 項反向對照） |
| KO | US | 快取 CAD；各 rung 無聲；seed 一筆 1 小時前失敗 attempt | T-15 單獨（layer-0 冷卻分支，provider-calls.log 無 KO 呼叫） |
| PEP | US | 快取 CAD；各 rung 無聲；無 attempt | T-15 單獨（fallback 分支） |
| CSCO | US | AV `Alpha Vantage API key 尚未設定，暫不可用。`、yfinance `yfinance 連線逾時或發生錯誤，暫不可用。`；快取 CAD | 合併 `AV 句。 YF 句。 T-15。` |
| 2412 | TW | 快取 USD 列；各 rung 無聲 | T-15 台 |
| 1101 | TW | 無快取、各 rung 無聲 | 對照組：一般空答案（`NO_BARS_REASON`） |
| 2603 | TW | 幣別 USD 的 legacy 持倉列（PositionInput 不檢查市場／幣別） | (b) 幣別與市場不符 |

- 兩句 reason（AV／YF）的字面取自 adapter 原始碼，不是我寫的。
- 快取內不能放空幣別列：`PriceBarCache.get` 會把 `PriceBar` 驗證失敗的列當壞列略過。所以快取側只能造非空的錯誤幣別（CAD、USD）。這是 T-15「或沒有標示價格單位」那半邊在端到端無法造出的原因。
- 另外建立 4 條警示規則（RY.TO、2330K、MSFT、AAPL 的 price_above，經 `POST /api/alerts`）。
- playbook 以 `PlaybookStore` 寫入 2330K、2317、3008 各一個 open 批次（各 1000 股），再 `POST /api/playbook/confirm-rules {"capital":"1000000"}`（合成值）。
- 這些寫入都只在 `$O/db/e2e.db`。

### launcher 全文：`$O/launch_f9b.py`
```python
"""F-9b e2e launcher: replaces ONLY the five daily-bar adapter classes constructed by app.api.deps with scripted rungs,
so the real MarketDataService (admission gate, currency gate, cache gate, W-d, valuator, book notes ...) runs unmodified on top.
Also: (1) redirects the two FX base URLs to the loopback stand-in on :8099 (same trick as earlier rounds),
      (2) optionally disarms the ADR-0009 cooldown WRITE (PriceBarCache.record_attempt -> no-op) so that every request
          re-runs the ladder instead of the 2nd request getting the cooldown text (F9B_ARM_COOLDOWN=1 keeps the real behaviour).
Nothing else is patched.  All data is synthetic.
"""
import logging, os, sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f9b_scen import SCEN  # noqa: E402

logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.WARNING)
CALLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.environ.get("F9B_CALLS_LOG", "provider-calls.log"))

import app.data.providers.fx as _fx  # noqa: E402
import app.data.providers.yfinance as _yf  # noqa: E402
_fx.BOT_BASE_URL = "http://127.0.0.1:8099"
_yf.YFINANCE_BASE_URL = "http://127.0.0.1:8099"

from app.data.cache import PriceBarCache  # noqa: E402
from app.data.interface import DataStatus, MarketDataProvider, PriceBar, ProviderResult  # noqa: E402
from app.data.providers.yfinance import YFinanceAdapter  # noqa: E402

ARM = os.environ.get("F9B_ARM_COOLDOWN", "0") == "1"
if not ARM:
    PriceBarCache.record_attempt = lambda self, symbol, market, *, at=None: None  # type: ignore[method-assign]


def _answer(source_id: str, symbol: str, start: date, end: date) -> ProviderResult:
    now = datetime.now(UTC)
    kind, arg = SCEN.get(symbol.strip().upper(), {}).get(source_id, ("none", None))
    with open(CALLS, "a") as f:
        f.write(f"{now.isoformat()} {source_id} {symbol} {start}..{end} -> {kind} {arg!r}\n")
    if kind == "none":
        return ProviderResult(bars=[], status=DataStatus.UNAVAILABLE, as_of=now, source=source_id, staleness_minutes=None, reason=arg)
    market = "TW" if source_id in ("twse", "tpex", "finmind") else "US"
    bars, d, i = [], start, 0
    while d <= end:
        if d.weekday() < 5:
            c = Decimal("100") + Decimal(i % 7)
            bar = PriceBar(symbol=symbol, market=market, date=d, open=c, high=c, low=c, close=c, volume=1,
                           currency="USD", as_of=now, source=source_id)
            bars.append(bar.model_copy(update={"currency": arg}))   # same trick as the repo's own tests: blank unit
            i += 1
        d += timedelta(days=1)
    return ProviderResult(bars=bars, status=DataStatus.FRESH, as_of=now, source=source_id, staleness_minutes=0)


def _rung(source_id):
    class Rung(MarketDataProvider):
        def __init__(self, *a, **k):
            pass
        def get_daily_bars(self, symbol, start, end):
            return _answer(source_id, symbol, start, end)
    Rung.source_id = source_id
    Rung.__name__ = f"Fake_{source_id}"
    return Rung


class FakeYF(YFinanceAdapter):
    """Real YFinanceAdapter (index + FX roles untouched); only the equity daily-bar call is scripted."""
    def get_daily_bars(self, symbol, start, end):
        return _answer("yfinance", symbol, start, end)


import app.api.deps as deps  # noqa: E402
deps.AlphaVantageAdapter = _rung("alpha_vantage")
deps.TwseAdapter = _rung("twse")
deps.TpexAdapter = _rung("tpex")
deps.FinMindAdapter = _rung("finmind")
deps.YFinanceAdapter = FakeYF

from app.main import app  # noqa: E402,F401
print("LAUNCH-F9B arm_cooldown=%s app=%s db=%s" % (ARM, sys.modules["app"].__file__, os.environ.get("STOCK_DESK_DB_PATH")), file=sys.stderr, flush=True)
```

### 場景表：`$O/f9b_scen.py`（節錄關鍵常數，完整檔在路徑）
```python
AV_NOKEY = "Alpha Vantage API key 尚未設定，暫不可用。"
YF_DOWN = "yfinance 連線逾時或發生錯誤，暫不可用。"
SCEN = {
    "MSFT": {"alpha_vantage": ("bars", "CAD")},
    "NVDA": {"alpha_vantage": ("bars", "")},
    "AAPL": {"alpha_vantage": ("bars", ""), "yfinance": ("none", YF_DOWN)},
    "GOOG": {"alpha_vantage": ("bars", "")},
    "AMZN": {"alpha_vantage": ("bars", "")},
    "KO": {}, "PEP": {},
    "CSCO": {"alpha_vantage": ("none", AV_NOKEY), "yfinance": ("none", YF_DOWN)},
    "2317": {"twse": ("bars", "USD")},
    "2454": {"twse": ("bars", "")},
    "3008": {"twse": ("bars", "")},
    "2412": {},
}
# SEED（快取列）：AAPL/GOOG USD alpha_vantage 335 根；AMZN USD 前150 alpha_vantage + 後185 yfinance；
# KO/PEP/CSCO CAD alpha_vantage；3008 TWD twse；2412 USD twse。日期 2025-07-01 ~ 2026-10-12 的週間格，fetched_at=2026-10-12T20:00Z。
# ATTEMPT_SEED = [("KO","US")]（1 小時前）。POSITIONS 共 16 筆，見檔案。
```
其餘檔案：`prep_f9b.py`（seed）、`fx_stub.py`、`prep_playbook.py`、`dump_consts.py`（從 worktree 常數產 `constants.json`）、`inpage.js`（量測函式）、`runner_common.js`、`runner1.js`～`runner4.js`、`env.sh`。

## 4. 各項結果（每項 × 375／1280）
量測方法：對每個目標字串逐字元取 `Range.getClientRects()`，檢查是否有 rect（rendered／chars）、是否超出 viewport 水平範圍（outX）、是否被任一 `overflow≠visible` 祖先的盒子裁切（clip）、折成幾行（以 rect.top 分組）；另掃區塊內元素的 `text-overflow:ellipsis`、`-webkit-line-clamp`、`scrollWidth>clientWidth` 且 overflow 非 visible、rect 超出 viewport。截圖檔名規則：`shots/pos-<case>-<vp>-{fullpage,kline-closed,kline-open,opsum-closed,opsum-open,advice-closed,advice-open}.png`、`shots/home-<vp>-{fullpage,table,gauge-closed,gauge-open}.png`。每個 case 的 JSON：`out/pos-<case>-<vp>.json`；彙整：`$O/analysis3.txt`。

### 共同事實（第 1～5 項）
- 逐字比對（機械子字串，常數由 `dump_consts.py` 從 worktree 取得）：所有案例的預期 reason 字串都在 DOM 找到，每個出現處的字元都有 rect（rendered = chars），`outsideViewportX = 0`，`clippedByAncestor = 0`。
- 全部案例、兩個寬度、三個區塊與首頁 gauge：區塊掃描的 `clipped`／`ellipsis`／`lineClamp`／`beyondViewport` 皆為空陣列。文件 `scrollWidth` = `innerWidth`（375/375、1280/1280），無橫向溢位。
- 沿用的「…」：除 reason 之外，區塊文字內 `…` 與 `...` 出現 0 次。
- 無 bars 案例（W-a/b/c/c′、T-15、1101）的區塊文字（扣除 reason 字串後）：`價格單位` 0 次、`價格單位：` 0 次、`來源回報：` 0 次、`（主來源、備援與快取皆無）` 0 次、`查無` 0 次。扣除 reason 後無任何數字記號（`numbers(non-reason)=none`）。
- 唯一例外是對照組 1101 的 reason 本身（`NO_BARS_REASON`）含 `（主來源、備援與快取皆無）`；1101 沒有 `來源回報：`（因為各層 reason 皆 None）。
- 注意：W-a、T-15 句子本身含「價格單位」字樣（句內詞），這是 reason 的一部分，不是標籤。上述計數已先扣掉 reason。
- 區塊出現次數（無 bars）：技術分析 3 處（主視圖 `InsufficientPanel` 1 處；`<details>` 內「資料來源：…」兩段各 1 處）；操作摘要 2 處（主視圖 `InsufficientPanel` 1 處＋`<details>` 內 1 處）；建議卡 1 處（`InsufficientPanel`）；首頁 gauge「詳細」內至少 1 處（各標的資料來源清單），部分標的另有「未納入」清單的重複。

折行數（行數 375／1280，K 線主視圖面板；操作摘要與建議卡面板同數）：

| 案例（代號） | 字數 | K 線 375／1280 | 首頁 gauge 各出現處行數 375／1280 |
|---|---|---|---|
| W-a（RY.TO，最長美股句） | 119 | 6／2 | 6／2 |
| W-b（2330K） | 71 | 4／2 | 4／2 |
| W-c 美（MSFT） | 52 | 3／1 | 3／1 |
| W-c 台（2317） | 45 | 3／1 | 3／1 |
| W-c′ 美（NVDA） | 47 | 3／1 | 2,2,2,2／1,1,1,1（4 處） |
| W-c′ 台（2454） | 39 | 2／1 | 2,2／1,1 |
| T-15 單獨（KO 冷卻分支） | 49 | 3／1 | 3,3,4,3／1,1,2,1 |
| T-15 單獨（PEP fallback） | 49 | 3／1 | 同 KO |
| T-15 台（2412） | 49 | 3／1 | 同 KO |
| T-15 合併 `AV 句。 YF 句。 T-15。`（CSCO） | 107 | 5／2 | 5／2 |
| 對照 1101（一般空答案） | 37 | 2／1 | 2／1 |

### 第 1 項 W-a（RY.TO，最長美股句）
- 逐字 reason：`本系統只查詢這種形式的美股代號：1 至 5 個英文字母，可接單一字母的類別字尾（如 BRK.B）；此代號不在其內，未向任何來源查詢。帶其他字尾的代號可能是外國交易所的掛牌（價格單位未必是美元），也可能是特別股等美國商品，系統無法逐一分辨。`
- 該文字不含 `價格單位：` 標籤；區塊內沒有 `PriceUnitBadge`（K 線標題列無「價格單位」晶片）；沒有價格數字。
- 在 375 的 K 線主視圖面板：外框內文字寬 266.02px、容器 `clientWidth` 307px，6 行。

### 第 2 項 W-b（2330K）
- 逐字 reason：`此台股代號是「數字後接英文字母 K」的形式，本系統不處理這種形式，未向任何來源查詢。這類代號可能是以外幣計價的掛牌商品，價格單位未必是新台幣。`
- 同第 1 項：無價格數字、無 `價格單位：` 標籤。375：4 行、文字寬 266／容器 307；1280：2 行、文字寬 923.23／容器 956。

### 第 3 項 無 bars 的 W-c／W-c′
- 美 W-c（MSFT）：`alpha_vantage 這次回傳的日線，標示的價格單位不是美元（美股日線以美元為準），整段都不採用。`
- 台 W-c（2317）：`twse 這次回傳的日線，標示的價格單位不是新台幣（台股日線以新台幣為準），整段都不採用。`
- 美 W-c′（NVDA）：`alpha_vantage 這次回傳的日線沒有標示價格單位，無法確認是否為美元，整段都不採用。`
- 台 W-c′（2454）：`twse 這次回傳的日線沒有標示價格單位，無法確認是否為新台幣，整段都不採用。`
- 四者：reason 原樣；`價格單位：`標籤 0；`來源回報：` 0；`（主來源、備援與快取皆無）` 0；價格數字 0。
- 補充：NVDA 與 2454 在 backend log 各有 45 次以上 `ERROR app.data.service: no provider and no cache entry available for <sym>`（`_fall_back_to_cache` 無快取時的 `logger.error`，W-c′ 無快取路徑會走到）。這是 log，不是畫面。

### 第 4 項 T-15
- T-15 單獨（KO、PEP、2412）reason 為 `本機快取中此標的的日線資料，標示的價格單位與市場所用的單位不同，或沒有標示價格單位，整段都不採用。`
- 合併（CSCO）reason 為 `Alpha Vantage API key 尚未設定，暫不可用。 yfinance 連線逾時或發生錯誤，暫不可用。 本機快取中此標的的日線資料，標示的價格單位與市場所用的單位不同，或沒有標示價格單位，整段都不採用。`
- 兩種都在三處完整呈現，無價格、無單位標籤。

### 第 5 項 C-34 (b)（AAPL 兩層／GOOG 單層／AMZN 拼接；對照 3008 台股）
- **主畫面 compact 三者並存**（K 線區 closed 狀態，`chipsClosed`）：
  - 「快取資料」晶片 2 個（日線、指標各一），375 的位置 L=175.03～R=223.03 與 L=275.03～R=323.03（viewport 375），1280 為 L=965～1013 與 1065～1113；
  - 「收盤 113.98」（`近 335 根日線，收盤 113.98。`）9/9 字可見；
  - 「價格單位：美元」7/7 字可見（375：L=120～R=204；1280：L=248～R=332）。
  - 三者 `outX=0`、`clip=0`、1 行。375 的 `<main>` 文件寬 375，無橫向捲動。
  - K 線標題列 closed 的 innerText：`技術分析 / 價格單位：美元 / 資料截至 10-12 / 日線 / 快取資料 / 指標 / 快取資料`。
- **`<details>` 內**（JSON `details lines`，原文）：
  - AAPL：`資料來源：alpha_vantage快取資料，資料截至 2026-10-12（933 分鐘前取得，可能未含最近交易日）alpha_vantage 這次回傳的日線沒有標示價格單位，無法確認是否為美元，整段都不採用。 yfinance 連線逾時或發生錯誤，暫不可用。`
  - GOOG：同上，只到 `…整段都不採用。` 結束。
  - AMZN：`資料來源：yfinance快取資料，資料截至 2026-10-12（933 分鐘前取得，可能未含最近交易日）alpha_vantage 這次回傳的日線沒有標示價格單位，無法確認是否為美元，整段都不採用。 這段日線資料由多個來源拼接（alpha_vantage、yfinance），每筆保留原本的來源；不同來源的價格處理方式可能不同，接合處的數值可能出現落差。`
  - DOM 文字中「快取資料，資料截至…（…）」與 reason 之間、「資料來源：alpha_vantage」與「快取資料」之間沒有空格或標點，只靠 `span.ml-1.5` 的 CSS margin 分隔。
- reason 字元可見性：AAPL 72/72、GOOG 47/47、AMZN 125/125；375 折行 3／2／6 行，1280 為 2／2／3 行；`outX=0`、`clip=0`。
  - AAPL 375 折行：`alpha_vantage 這次回傳的日線沒有標示價格單` / `位，無法確認是否為美元，整段都不採用。 ` / `yfinance 連線逾時或發生錯誤，暫不可用。`
  - AMZN 375 折行 6 行（F9W-37 (c) 的 375 加驗）：`alpha_vantage 這次回傳的日線沒有標示價格單` / `位，無法確認是否為美元，整段都不採用。 這段` / `日線資料由多個來源拼接（alpha_vantage、` / `yfinance），每筆保留原本的來源；不同來源的價` / `格處理方式可能不同，接合處的數值可能出現落` / `差。`
- **操作摘要**同一 reason 各 1 處（`DataMetaPrefixLine`），完整；**首頁 gauge**「各標的資料來源」清單各 1 處，AAPL 的是：`AAPL（美股（US））快取資料，資料截至 2026-10-12（934 分鐘前取得，可能未含最近交易日）alpha_vantage …整段都不採用。 yfinance …`（兩寬度都 `clip=0`，AAPL 375 3 行、1280 1 行）。GOOG 在 gauge 另有 3 處（未納入清單），皆完整。
- 建議卡區塊（opened）中這三檔的 reason 出現 0 次（建議卡 ok 狀態不印 DataMeta reason；該區塊沒有 `價格單位` 以外的相關字）。
- 對照 3008（W-c′ 台＋快取）：K 線標題列為 `價格單位：新台幣`，compact「快取資料」晶片、價格 `NT$113.98`（首頁）皆在；reason 39/39 字。

### 第 6 項 T-12（首頁「持倉明細表」價格欄；`$O/out/home-*.json`、`$O/out/runner3.json`）
- 對 RY.TO、2330K、MSFT、2317、NVDA、2454、KO、PEP、CSCO、2412 各列：價格欄 `textContent` = `—資料不足代號或價格單位不採用`（「—」＋「資料不足」badge＋小字）。
- 10 字小字：`<p class="mt-0.5 text-xs …">`，字級 12px，每列 10/10 字有 rect、`clippedByAncestor=0`、`outX=0`，無 `text-overflow:ellipsis`、無 line-clamp、無 `…`、無「查無」。
  - 375：1 行；文字寬 120px、段落 `clientWidth` 122px（`scrollWidth` 122）。
  - 1280：1 行；文字寬 120px、段落 `clientWidth` 212px。
- 補測 320（寬）：文字寬 84px、`clientWidth` 89px，折成 2 行（`代號或價格單位` / `不採用`），無裁切、無溢位；360：寬 108／`clientWidth` 113，折 2 行（`代號或價格單位不採` / `用`），無裁切、無溢位。這兩個寬度是我自己多加的補測。
- 該列「查無」：0（`hasChaWu=false`）。對照 1101（一般空答案）：`—資料不足查無價格資料`（有「查無」），GOOG：`—10/12 收盤資料較舊查無建倉匯率`（有「查無」），2603：`幣別與市場不符` 晶片（無「資料不足」badge）。
- 截圖：`shots/home-375-table.png`、`home-1280-table.png`、`home-320-table.png`。

### 第 7 項 反向對照（W-c′ 台＋快取：3008）
- 首頁價格欄 `textContent` = `NT$113.9810/12 收盤資料較舊`（價格＋日期＋「資料較舊」badge）；沒有 T-12、沒有「—」、沒有「資料不足」、沒有「查無」；`valuation.status` 正常估值（損益 NT$63,980、+127.96%，見截圖 `home-375-table.png`）。
- 該列 `rowScan` 無裁切。

### 第 8 項 整書四組並列
- **建議卡（AAPL，cache-only）**，`風險預算輸入的假設與限制（9）` 清單依序（原文）：
  1. 取自本機快取的前導句；
  2. 總資產說明；
  3. 總曝險說明；
  4. `組合中有 1 筆部位無法估值（缺價格或匯率），未計入總資產；比率會因此偏高。`（W4）
  5. `組合中有 5 筆部位無法估值（本次未向來源查詢，本機尚無可用的價格或匯率），未計入總資產；比率會因此偏高。`（W5）
  6. `組合中有 1 筆部位因幣別與市場不符而無法估值（紀錄不一致，非價格或匯率中斷），可於庫存頁的「更多」視窗更正幣別與平均成本；系統不猜幣別而未計入總資產；比率會因此偏高。`（(b)）
  7. `組合中有 6 筆部位無法估值（代號形式不在本系統查詢的範圍內，或日線標示的價格單位與市場所用的單位不同，或日線沒有標示價格單位），未計入總資產；比率會因此偏高。`（T-11）
  8. 匯率換算說明；9. 匯率模型值說明。
  - 折行（`runner4.json`）：375 為 5/3/3/2/3/4/4/3/3 行；1280 為 2/1/1/1/1/2/2/1/1 行。九項皆字元全可見、`outX=0`、`clip=0`。
  - W4 的 1 筆是 GOOG（opened_at 缺 → fx_open 缺）；W5 的 5 筆是 MSFT、NVDA、2317、2454、1101（cache-only 無快取 → price_not_queried）；T-11 的 6 筆是 RY.TO、2330K、KO、PEP、CSCO、2412。
- **首頁總覽 notes（live valuator）** 依序：總資產說明、總曝險說明、W4（2 筆，1101＋GOOG）、(b)（1 筆）、T-11（10 筆）、匯率模型值說明。沒有 W5（見第 0 節第 4 點）。折行：375 為 3/3/2/4/4/3 行；1280 為 1/1/1/2/2/1 行；皆無裁切、無溢位。
- 截圖：`shots/advice-notes-AAPL-{375,1280}.png`、`shots/home-{375,1280}-gauge-open.png`。

### 第 9 項（suggested）
- **alerts：**設定頁「手動檢查一次」的頁面回饋原文：`已評估 1 條規則、略過 3 條，本次觸發 0 筆事件。` 與 `已評估的規則中，1 條符合條件但在冷卻中，本次未觸發事件。` 頁面（含所有 `<details>` 展開）不含 W-a、W-b、W-c 句（`pageContainsW_A=false` 等）。
  - `POST /api/alerts/evaluate` 回應原文（`out/alerts-evaluate-api-raw.json` 為第一次、`out/runner2.json` 內瀏覽器那次為第二次）：RY.TO 規則 `status:"skipped"`，`reason` 為 W-a 原句；2330K 為 W-b 原句；MSFT 為 W-c 美原句；AAPL 第一次 `fired`、第二次 `suppressed`（`距離上次觸發不足 60 分鐘，本次不重複發出。`）。
  - 第一次 evaluate 觸發的 AAPL 事件 `message` 原文：`AAPL 最新收盤價 113.98 USD，高於設定的門檻 100 USD。 上述數值之資料日為 2026-10-12。 資料來自 cached_stale 層（alpha_vantage）。 alpha_vantage 這次回傳的日線沒有標示價格單位，無法確認是否為美元，整段都不採用。 yfinance 連線逾時或發生錯誤，暫不可用。`
  - 首頁含 `AAPL 最新收盤價` 事件文字（`homeContainsAaplEvent=true`）。
- **playbook：**`POST /api/playbook/emergency-exit` 回應中各 directive 的 `data_reason` 原文：
  - 2317：`twse 這次回傳的日線，標示的價格單位不是新台幣（台股日線以新台幣為準），整段都不採用。`（`data_status:"unavailable"`、`source:"none"`、`reference_price:null`）
  - 2330K（W-b）：`此台股代號是「數字後接英文字母 K」的形式，本系統不處理這種形式，未向任何來源查詢。這類代號可能是以外幣計價的掛牌商品，價格單位未必是新台幣。`（同 unavailable／none）
  - 3008：`twse 這次回傳的日線沒有標示價格單位，無法確認是否為新台幣，整段都不採用。`（`data_status:"cached_stale"`、`source:"twse"`、`reference_price:"113.98"`）
  - 頁面渲染：出清後頁面只印 message、mode_reason、attribution 與 warnings（`2317 資料狀態為 unavailable（來源 none），依鐵律⑤當日不產生指令。`、`2330K …` 同句）；頁面文字不含 W-b 原句（`reasonOcc` 為空）。`GET /api/playbook/today` 在 confirm-rules 後 `directives` 為空，因此 `DirectiveLedger` 沒有渲染這三條。
  - 凍結後 `today` 的 warnings 有一條 `3008 資料狀態為 cached_stale（來源 twse）…`；未含任何 W 句。
  - 兩個寬度 playbook 文件 `scrollWidth` 與 `innerWidth` 相同。截圖 `shots/playbook-*`。

### 第 10 項 禁詞掃描（`$O/scan_all.txt`）
- 清單來源：`frontend/app/lib/adviceWording.ts` 的 `FRONTEND_FORBIDDEN_TERMS`（陣列字面，去掉註解，共 81 條，存 `constants.json`）。比對規則同 `wordingScanHelpers.ts` 的 `assertNoForbiddenTerms`（逐字子字串，不套 `allowedContexts`）與 `findBareRealtimeClaims`（「即時」前一字不是「非」）。
- 掃描對象：渲染後頁面的 `document.body.textContent`（去 script／style／noscript，`<details>` 與 `hidden` 全展開），共 36 份（15 個 case × 2 寬度的 position 頁、首頁 × 2、`/positions` × 2、設定頁 × 2、playbook × 2；文字檔 `out/*.pagetext.txt`）。
- 原始命中：共 44 個命中實例、5 種不同上下文，全是同一個詞「勝率」：
  - `「尚未輸入 Kelly 所需的勝率與盈虧比（可透過手動輸入或回」`（14 頁）
  - `「映規則一致性與資料完整度，非勝率或機率——5 日均線低於 2」`（8 頁）
  - `「。權重為規則優先序，非機率、勝率或預期報酬防禦型收盤價跌破季」`（8 頁）
  - `「。權重為規則優先序，非機率、勝率或預期報酬命中規則方向防禦型」`（8 頁）
  - `「。權重為規則優先序，非機率、勝率或預期報酬中性單一標的佔比偏」`（6 頁）
- 裸「即時」：0 處。
- 命中全落在 AAPL／GOOG／AMZN／3008 的建議卡與操作摘要既有免責句、Kelly 句。W-a／W-b／W-c／W-c′／T-15／T-11／T-12 等 F-9b 字面的頁面（無 bars 案例）命中數為 0（`pos-W-a-*` 等 `forbidden=0`）。

## 5. console／network 原始清單
- console error／warning、pageerror：runner1、runner2 兩次共 **0 筆**。
- HTTP ≥ 400：**0 筆**。
- 被 `ctx.route` abort 的外部請求：**0 筆**（頁面沒有發出任何非 loopback 請求）。
- `requestfailed` 共 54（runner1）＋12（runner2）筆，全為 Next 的連結預取與被導覽中止的請求（`net::ERR_ABORTED`）。範例：
  - `GET http://localhost:3000/position/2454?market=TW&_rsc=tXyZJ52UQVBCVsD3 net::ERR_ABORTED`
  - runner2 第一次嘗試因我只等 2.5 秒就換頁，`POST http://localhost:8000/api/alerts/evaluate net::ERR_ABORTED`（`out/runner2-first-attempt.json`）。evaluate 實測約 11.6 秒；第二次改等回應後完成，沒有 ABORTED。
  - 完整清單在 `out/runner1-summary.json`、`out/runner2.json` 的 `log.failed`。
- 後端 log（`$O/backend.log`）統計：`WARNING app.data.service`（幣別／快取閘門記錄，每次請求都寫）約 1054、`ERROR app.data.service: no provider and no cache entry available for …`（NVDA 46、2454 45、1101 45、`^TWII` 12、2603 10、`^GSPC` 8）、`WARNING app.portfolio.valuation: position currency does not match market`（2603）、`WARNING app.api.settings: … ALPHA_VANTAGE_DAILY_LIMIT is not set`（設定頁，環境未設額度）。

## 6. 補充實測：cooldown 武裝模式（`F9B_ARM_COOLDOWN=1`，port 8001，新 DB `$O/db2`，用完即停）
同一個 launcher，保留真實的 `record_attempt`。用 curl 對 `/api/bars/<sym>` 各打兩次：
- MSFT 第一次：`data.reason`＝W-c 美原句；第二次：`US MSFT 在指定區間內沒有可用的日線資料（主來源、備援與快取皆無）。來源回報：本機尚無此標的的日線資料，最近一次向來源取得已於約 0 分鐘前未成功，冷卻期內暫不重試。冷卻期為 24 小時，冷卻期內系統不會自動重試；冷卻期結束後的下一次查詢才會重新向來源取得。`（`COOLDOWN_NO_CACHE_REASON`，無 `rejection`，走 `NO_BARS_REASON`＋「來源回報：」）
- AAPL 第一次：`data.reason`＝`alpha_vantage …整段都不採用。 yfinance …`（兩層合併）；第二次：`最近一次向來源取得資料未成功，暫以本機快取回覆。`（`RECENT_ATTEMPT_FAILED_REASON`）
- 即真實運作下，W-c／W-c′ 句只在冷卻期內的第一次請求出現。這是否屬 F-9b 範圍內（壞處 9／F-9b2）由 qa-e2e 與風控判讀；本報告只呈現事實。

## 7. 自我揭露
- 執行過的指令類型：`ls`、`stat`、`ps -eo pid,comm`（含一次 `ps -o … -p 11552` 看別人的行程，未碰它）、`git rev-parse`／`git status`／`git log`／`git show`（唯讀）、`cp -a`（主工作樹 `node_modules` → worktree frontend）、`rm -rf`（只刪我複製的 `node_modules`、`.next`、`next-env.d.ts`，以及 `$O/db` 下我自己的資料）、`node next build`／`next start`、uvicorn（2 個實例）、python（prep／dump 腳本，在 scratchpad，寫 scratch DB）、`node` 跑 playwright runner、`curl`（loopback：8000／8001／8099／3000，含 POST 建警示規則、evaluate、confirm-rules）、`kill`（僅我記錄的 PID）、`sed`／`grep`／`cat`／`python3 -`／`node -e` 讀寫 scratchpad 檔案。
- 沒有安裝任何套件；沒有 `playwright install`、`npm install`、`pip`、`uv`；沒有對外連網（瀏覽器零外部請求，行程走 `127.0.0.1:9` proxy）。
- 沒有修改 worktree 內任何受測程式或測試、沒有 commit、沒有 `git` 寫入。沒有改主工作樹任何檔案。沒有讀、複製、hash 或寫入 `apps/stock-desk/backend/data/*.db`（僅 `stat` 前後各一次，數值不變）。沒有讀 `.env`。
- 越界或灰區（供判斷）：
  - (1) 我用 `cp -a` 把主工作樹的 `node_modules` 複製進 worktree 的 frontend（指示允許），結束時已刪除。
  - (2) `next build` 在 worktree 生成了 `.next`、`next-env.d.ts`，均已刪除；`tsconfig.tsbuildinfo` 原本就存在（gitignored），我沒動它，但 build 可能改寫其內容。
  - (3) 在 scratch DB 內我用了真實 API 的寫入（建警示規則、`confirm-rules`、`emergency-exit`、建立持倉與快取列），非產品資料。
  - (4) 前述 `record_attempt` no-op 屬 fixture 偏離，已於第 0 節與第 6 節揭露。
  - (5) 前述 worktree 內他人建立的 `.venv` 與主工作樹 HEAD 變動，不是我的動作。
- 本報告未對「是否符合預期」作結論；`provenance` 欄位原樣附在第 1 節，qa-e2e 請依 skill 第 6 節儀器來源查核。
