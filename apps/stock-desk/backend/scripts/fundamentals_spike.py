"""Fundamentals data source spike (CEO #92, 2026-11-01).

Purpose: the sandbox has no outbound network, so the CEO runs this once on a
networked machine and pastes the console output back. It answers, with the
fewest possible requests, whether the free sources can feed a "Financials" tab
(free cash flow, buybacks, dividends, SBC, share count) for US and TW stocks.

Strictly read-only:
  * GET requests only, standard library only (``urllib``), no ``app.*`` import.
  * Touches no database and writes no file; every line goes to stdout.
  * Secrets come from environment variables only and are masked in all output
    (``SEC_USER_AGENT``, ``FINMIND_API_TOKEN``, ``ALPHA_VANTAGE_API_KEY``).
  * No retries on purpose: a spike must report what the source did on the
    first try, not hide flakiness behind backoff.

Environment variables (names only; see ``apps/stock-desk/.env.example``):
  SEC_USER_AGENT         required for SEC, format "Your Name your@email"
  SPIKE_US_HOLDINGS      optional, up to 3 US tickers you hold, e.g. "NVDA,TSLA"; used
                         only to judge ADR-0038 P-12 (non-USD or IFRS filers)
  FINMIND_API_TOKEN      optional; without it FinMind runs at the anonymous tier
  ALPHA_VANTAGE_API_KEY  optional; without it the Alpha Vantage check is skipped

Planned requests (hard cap ``REQUEST_CAP`` = 30, enforced in code):

  SEC EDGAR          10  ticker map 1; companyfacts AAPL, AMZN, INTC 3;
                         foreign-filer sample TSM 1; AAPL filing list 1 and the
                         same request again with ETag/If-Modified-Since 1;
                         ETF sample SPY filing list 1 and companyfacts 1;
                         SEC fair-access page 1
                         +1 if the first ticker map path fails (fallback path)
                         +up to 3 companyfacts, one per ticker in SPIKE_US_HOLDINGS
                         (the conditional repeat is skipped if AAPL answers
                         without ETag/Last-Modified, so 9 in that case)
  TWSE OpenAPI        4  (swagger 1, up to 3 sample datasets)
  TPEx OpenAPI        3  (swagger 1, up to 2 sample datasets)
  FinMind             4  (dataset enum from GitHub 1, user_info 1,
                          cash-flow dataset for one TWSE and one TPEx ticker 2)
  Alpha Vantage       1  (TIME_SERIES_DAILY AAPL, compact)
  ------------------------------------------------------------------
  Normal run         22  (no holdings given); worst case 26, cap 30

The ADR-0038 P items (P-1..P-9, P-12) are judged from those same responses:
section 5 of the output issues no request of its own.

Throttling: SEC hosts are spaced at least 0.25 s apart (<= 4 req/s, well under
the 10 req/s SEC limit); every other host at least 1.0 s.

Verdict vocabulary printed per check: EXISTS / MISSING / ERROR / SKIPPED, and for
the P items HOLDS / NOT_HOLD / PARTIAL / MEASURED / INCONCLUSIVE.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2"
REQUEST_CAP = 30
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_BODY_BYTES = 64 * 1024 * 1024
SEC_MIN_GAP_SECONDS = 0.25
DEFAULT_MIN_GAP_SECONDS = 1.0
MASK = "***"

ENV_SEC_UA = "SEC_USER_AGENT"
ENV_FINMIND = "FINMIND_API_TOKEN"
ENV_ALPHA = "ALPHA_VANTAGE_API_KEY"
ENV_HOLDINGS = "SPIKE_US_HOLDINGS"
SECRET_ENV_VARS = (ENV_SEC_UA, ENV_FINMIND, ENV_ALPHA)

EXISTS = "EXISTS"
MISSING = "MISSING"
ERROR = "ERROR"
SKIPPED = "SKIPPED"

# ---------------------------------------------------------------- endpoints

SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_TICKER_FALLBACK_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
#: First ticker is the baseline; the other two are picked because large caps
#: commonly tag capital expenditure with a different element than AAPL does.
SEC_TICKERS = ("AAPL", "AMZN", "INTC")
#: Used only if both ticker-map paths fail, so companyfacts can still be probed.
#: These come from public knowledge and are NOT verified by this run.
SEC_FALLBACK_CIKS = {
    "AAPL": 320193,
    "AMZN": 1018724,
    "INTC": 50863,
    "TSM": 1046179,
    "SPY": 884394,
}
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_DOCS_URL = "https://www.sec.gov/os/accessing-edgar-data"
#: A US-listed foreign private issuer (files 20-F, IFRS, reports in TWD): P-12 sample.
FOREIGN_SAMPLE = "TSM"
#: A plain ETF: P-4 and P-8 sample (ETFs have no companyfacts).
ETF_SAMPLE = "SPY"
#: Dotted class-share ticker as the product spells it; SEC may spell it with a hyphen.
CLASS_SHARE_SAMPLE = "BRK.B"
#: Looked up in the ticker map only (no request) for P-4.
PROBE_TICKERS = ("AAPL", "BRK.B", "GOOG", "GOOGL", "SPY", "TQQQ")
MAX_HOLDINGS = 3
HOLDING_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
SUBMISSION_FIELDS = ("accessionNumber", "filingDate", "acceptanceDateTime", "form", "reportDate")
ACCEPTANCE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z?$")
PERIODIC_FORMS = {"10-K", "10-Q", "20-F"}
FISCAL_YEAR_END_RE = re.compile(r"^\d{4}$")
P_TITLES = {
    "P-1": "every fact carries filed/accn/form/start/end/fy/fp/frame; fy/fp belong to the filing",
    "P-2": "older filings (comparatives) are retained, so the first-published value can be rebuilt",
    "P-3": "tag whitelist per item (CapEx, dividends, buyback, revenue) and what is verified",
    "P-4": "ticker to CIK map; class shares (BRK.B) and ETFs",
    "P-5": "current rate limit and User-Agent format",
    "P-6": "filing list fields, conditional requests, companyfacts freshness",
    "P-7": "response size per issuer",
    "P-8": "SIC and entity type available; how an ETF is recognised",
    "P-9": "fiscal year end available",
    "P-12": "holdings that report in a non-USD currency or under IFRS",
}

TWSE_SWAGGER_URL = "https://openapi.twse.com.tw/v1/swagger.json"
TWSE_BASE_URL = "https://openapi.twse.com.tw/v1"
TPEX_SWAGGER_URL = "https://www.tpex.org.tw/openapi/v1/swagger.json"
TPEX_BASE_URL = "https://www.tpex.org.tw/openapi/v1"

FINMIND_DATA_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_USER_INFO_URL = "https://api.web.finmindtrade.com/v2/user_info"
FINMIND_ENUM_URL = "https://raw.githubusercontent.com/FinMind/FinMind/master/FinMind/schema/data.py"
FINMIND_CASHFLOW_DATASET = "TaiwanStockCashFlowsStatement"
FINMIND_CASHFLOW_START = "2024-01-01"
#: One listed (TWSE) and one over-the-counter (TPEx) ticker.
FINMIND_TICKERS = (("TWSE", "2330"), ("TPEx", "6488"))

ALPHA_URL = "https://www.alphavantage.co/query"
ALPHA_SYMBOL = "AAPL"

# ---------------------------------------------------------------- SEC concepts

#: concept -> candidate (namespace, tag) pairs; the first pair is the primary tag.
CONCEPTS: dict[str, tuple[tuple[str, str], ...]] = {
    "OCF": (
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    ),
    "CapEx": (
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
        ("us-gaap", "PaymentsToAcquireProductiveAssets"),
        ("us-gaap", "PaymentsForCapitalImprovements"),
        ("us-gaap", "PaymentsToAcquireOtherPropertyPlantAndEquipment"),
        ("us-gaap", "CapitalExpendituresIncurredButNotYetPaid"),
    ),
    "Buyback": (
        ("us-gaap", "PaymentsForRepurchaseOfCommonStock"),
        ("us-gaap", "PaymentsForRepurchaseOfEquity"),
        ("us-gaap", "StockRepurchasedAndRetiredDuringPeriodValue"),
        ("us-gaap", "StockRepurchasedDuringPeriodValue"),
        ("us-gaap", "TreasuryStockValueAcquiredCostMethod"),
    ),
    "Dividends": (
        ("us-gaap", "PaymentsOfDividends"),
        ("us-gaap", "PaymentsOfDividendsCommonStock"),
        ("us-gaap", "DividendsCommonStockCash"),
    ),
    "SBC": (
        ("us-gaap", "ShareBasedCompensation"),
        ("us-gaap", "AllocatedShareBasedCompensationExpense"),
    ),
    "Revenue": (
        ("us-gaap", "Revenues"),
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
        ("us-gaap", "SalesRevenueNet"),
    ),
    "NetIncome": (
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "ProfitLoss"),
    ),
    "DilutedEPS": (("us-gaap", "EarningsPerShareDiluted"),),
    "Shares": (
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
        ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
        ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
    ),
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STALE_AFTER_DAYS = 400

# ---------------------------------------------------------------- TWSE / TPEx keywords

KEYWORDS: dict[str, tuple[str, ...]] = {
    "cashflow": ("現金流量", "cash flow", "cashflow"),
    "treasury": ("庫藏股", "買回", "treasury", "buyback", "repurchase"),
    "statement": ("資產負債表", "損益表", "balance sheet", "income statement"),
}
MAX_LISTED_T187AP = 60
MAX_FIELDS_SHOWN = 40
MAX_SAMPLE_FIELDS = 8

FINMIND_TYPE_KEYWORDS = (
    "operating",
    "property",
    "treasury",
    "dividend",
    "acquisition",
    "repurchase",
    "營業活動",
    "不動產",
    "庫藏股",
    "股利",
    "買回",
)
FINMIND_ENUM_KEYWORDS = (
    "cash",
    "treasur",
    "buyback",
    "buy_back",
    "repurchase",
    "balance",
    "financial",
    "dividend",
    "usstock",
)
FINMIND_QUOTA_KEYS = ("user_count", "api_request_limit", "level", "level_title")


# ---------------------------------------------------------------- redaction


class Redactor:
    """Masks secrets, emails and credential-looking fragments in any text."""

    #: Each pattern keeps group 1 (the label) and masks group 2 (the value).
    #: Scheme patterns run first so "Authorization: Bearer X" masks X, not "Bearer".
    _PATTERNS = (
        re.compile(r"(?i)\b(bearer\s+|basic\s+)([^\s\"',}]+)"),
        re.compile(r"(?i)\b((?:token|apikey|api_key|key)=)([^&\s\"']+)"),
        re.compile(r"(?i)(\"?(?:token|apikey|api_key|authorization)\"?\s*[:=]\s*\"?)([^\",&\s}]+)"),
    )
    _EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

    def __init__(self, secrets: Iterable[str]) -> None:
        variants: set[str] = set()
        for secret in secrets:
            secret = secret.strip()
            if len(secret) < 4:
                continue
            variants.add(secret)
            variants.add(urllib.parse.quote(secret))
            variants.add(urllib.parse.quote_plus(secret))
        # Longest first so a secret containing another secret is masked whole.
        self._secrets = sorted(variants, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, MASK)
        for pattern in self._PATTERNS:
            text = pattern.sub(lambda m: f"{m.group(1)}{MASK}", text)
        return self._EMAIL.sub(MASK, text)


# ---------------------------------------------------------------- HTTP layer


@dataclass(frozen=True)
class HttpResult:
    """Outcome of one GET. ``status`` is None when no HTTP response arrived."""

    status: int | None
    body: bytes
    error: str | None = None
    #: Lower-cased copies of a few response headers (validators, size, rate limits).
    headers: Mapping[str, str] = field(default_factory=dict)
    #: Bytes received before content decoding (the gzip size when compressed).
    wire_size: int | None = None


Transport = Callable[[str, Mapping[str, str]], HttpResult]


class BudgetExceededError(RuntimeError):
    """Raised instead of sending request number ``cap + 1``."""


class Budget:
    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.used = 0

    def take(self) -> None:
        if self.used >= self.cap:
            raise BudgetExceededError(f"request cap {self.cap} reached")
        self.used += 1


def _decode_body(raw: bytes, encoding: str) -> bytes:
    if "gzip" in encoding.lower():
        try:
            return gzip.decompress(raw)
        except (OSError, EOFError):
            return raw
    return raw


HEADERS_KEPT = (
    "etag",
    "last-modified",
    "content-length",
    "content-encoding",
    "date",
    "cache-control",
    "expires",
    "retry-after",
)


def keep_headers(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Keep only validators, size and rate-limit headers; never cookies or auth."""
    kept: dict[str, str] = {}
    for name, value in items:
        lowered = name.lower()
        if lowered in HEADERS_KEPT or lowered.startswith(("x-ratelimit", "ratelimit")):
            kept[lowered] = str(value)
    return kept


def urllib_transport(url: str, headers: Mapping[str, str]) -> HttpResult:
    """Real transport: one GET, bounded body size, never raises."""
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
            status = int(response.status)
            kept = keep_headers(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read(MAX_BODY_BYTES + 1)
        status = int(exc.code)
        kept = keep_headers(exc.headers.items()) if exc.headers else {}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return HttpResult(None, b"", f"{type(exc).__name__}: {exc}")
    if len(raw) > MAX_BODY_BYTES:
        return HttpResult(status, b"", f"body larger than {MAX_BODY_BYTES} bytes, discarded", kept)
    return HttpResult(
        status, _decode_body(raw, kept.get("content-encoding", "")), None, kept, len(raw)
    )


@dataclass
class Fetcher:
    """Budget + per-host spacing in front of a transport. No retries."""

    transport: Transport
    budget: Budget
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    _last: dict[str, float] = field(default_factory=dict)

    @staticmethod
    def _bucket(url: str) -> tuple[str, float]:
        host = urllib.parse.urlsplit(url).hostname or ""
        if host == "sec.gov" or host.endswith(".sec.gov"):
            return "sec.gov", SEC_MIN_GAP_SECONDS
        return host, DEFAULT_MIN_GAP_SECONDS

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> HttpResult:
        bucket, gap = self._bucket(url)
        last = self._last.get(bucket)
        if last is not None:
            wait = gap - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        self.budget.take()
        result = self.transport(url, headers or {})
        self._last[bucket] = self.clock()
        return result


# ---------------------------------------------------------------- reporting


@dataclass(frozen=True)
class Result:
    section: str
    check: str
    verdict: str
    detail: str = ""


@dataclass
class Context:
    fetcher: Fetcher
    say: Callable[[str], None]
    env: Mapping[str, str]
    today: date
    results: list[Result] = field(default_factory=list)
    evidence: SecEvidence = field(default_factory=lambda: SecEvidence())

    def record(self, section: str, check: str, verdict: str, detail: str = "") -> None:
        self.results.append(Result(section, check, verdict, detail))
        suffix = f" -- {detail}" if detail else ""
        self.say(f"  => [{verdict}] {section}/{check}{suffix}")


def short(value: object, limit: int = 40) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def describe_http(result: HttpResult) -> str:
    if result.status is None:
        return f"NO HTTP RESPONSE ({result.error})"
    extra = f" ({result.error})" if result.error else ""
    return f"HTTP {result.status}, {len(result.body):,} bytes{extra}"


def parse_json(body: bytes) -> tuple[Any, str | None]:
    try:
        return json.loads(body.decode("utf-8-sig")), None
    except (UnicodeDecodeError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {short(exc, 80)}"


def fetch_json(
    ctx: Context, url: str, headers: Mapping[str, str] | None = None, shown_url: str | None = None
) -> tuple[HttpResult, Any, str | None]:
    """GET + describe + parse. ``shown_url`` lets callers print a trimmed URL."""
    ctx.say(f"GET {shown_url or url}")
    result = ctx.fetcher.get(url, headers)
    ctx.say(f"  {describe_http(result)}")
    if result.status is None or not result.body:
        return result, None, result.error or "empty body"
    obj, error = parse_json(result.body)
    if error:
        ctx.say(f"  JSON parse failed: {error}; first bytes: {short(result.body[:80], 90)!r}")
    return result, obj, error


def section_header(ctx: Context, title: str) -> None:
    ctx.say("")
    ctx.say(f"== {title} ==")


# ---------------------------------------------------------------- SEC analysis

FACT_FIELDS = ("accn", "filed", "form", "end", "fy", "fp", "frame")
#: Tags whose facts are point-in-time balances; every other tag is a period flow with ``start``.
INSTANT_TAGS = {
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
}
#: A fiscal-year fact filed within this many days of its period end is the original 10-K.
ORIGINAL_FILING_MAX_DAYS = 130
#: Only periods ended longer ago than this are expected to have a settled filing history.
OLD_PERIOD_AFTER_DAYS = 400
CURRENCY_UNIT_RE = re.compile(r"^([A-Z]{3})(?:/[A-Za-z]+)?$")


@dataclass
class PeriodInfo:
    """Everything the facts of one (start, end) period say about who reported it."""

    vals_by_accn: dict[str, str] = field(default_factory=dict)
    fys: set[str] = field(default_factory=set)
    min_filed: str | None = None


@dataclass
class FactStats:
    total: int = 0
    present: Counter[str] = field(default_factory=Counter)
    flow_total: int = 0
    flow_with_start: int = 0
    periods: dict[tuple[str, str], PeriodInfo] = field(default_factory=dict)
    fyfp_by_accn: dict[str, set[tuple[str, str]]] = field(default_factory=dict)
    max_filed: str | None = None


@dataclass
class TagSummary:
    namespace: str
    tag: str
    units: dict[str, int]
    entries: int
    forms: Counter[str]
    fps: Counter[str]
    earliest_end: str | None
    latest_end: str | None
    stale: bool
    bad_dates: dict[str, int]
    distinct_periods: int
    durations: Counter[str]
    latest_fy: dict[str, Any] | None
    latest_interim: dict[str, Any] | None
    sample_unit: str | None
    stats: FactStats

    @property
    def verified(self) -> bool:
        """Usable as an annual series: still in use and at least three fiscal years."""
        return not self.stale and self.fps.get("FY", 0) >= 3


@dataclass
class ConceptReport:
    found: list[TagSummary]
    missing: list[str]

    @property
    def verdict(self) -> str:
        return EXISTS if self.found else MISSING


@dataclass
class FactsReport:
    entity_name: str
    cik: object
    namespaces: dict[str, int]
    concepts: dict[str, ConceptReport]
    #: unit -> number of tags (across the whole document) that report in that unit
    unit_tags: Counter[str]

    @property
    def uses_us_gaap(self) -> bool:
        return self.namespaces.get("us-gaap", 0) > 0

    @property
    def summaries(self) -> list[TagSummary]:
        return [s for c in self.concepts.values() for s in c.found]

    @property
    def max_filed(self) -> str | None:
        filed = [s.stats.max_filed for s in self.summaries if s.stats.max_filed]
        return max(filed) if filed else None


def foreign_currency_units(unit_tags: Mapping[str, int]) -> list[str]:
    """Units quoted in a currency other than USD, e.g. TWD or EUR/shares."""
    found: list[str] = []
    for unit in unit_tags:
        match = CURRENCY_UNIT_RE.match(unit)
        if match and match.group(1) != "USD":
            found.append(unit)
    return sorted(found)


def _days_between(start: object, end: object) -> int | None:
    if not (isinstance(start, str) and isinstance(end, str)):
        return None
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return None


def _duration_bucket(days: int | None) -> str:
    if days is None:
        return "instant-or-bad"
    for label, low, high in (("~3m", 80, 100), ("~6m", 170, 195), ("~9m", 260, 285)):
        if low <= days <= high:
            return label
    return "~12m" if 350 <= days <= 380 else "other"


def _sort_key(entry: Mapping[str, Any]) -> tuple[str, str]:
    return str(entry.get("end", "")), str(entry.get("filed", ""))


def _has(row: Mapping[str, Any], name: str) -> bool:
    return row.get(name) not in (None, "")


def collect_stats(entries: list[dict[str, Any]], *, instant: bool) -> FactStats:
    """Field coverage and per-period reporting history, for the ADR-0038 P items."""
    stats = FactStats()
    for row in entries:
        stats.total += 1
        for name in FACT_FIELDS:
            if _has(row, name):
                stats.present[name] += 1
        if not instant:
            stats.flow_total += 1
            if _has(row, "start"):
                stats.flow_with_start += 1
        filed = str(row.get("filed", ""))
        filed_ok = bool(DATE_RE.match(filed))
        if filed_ok and (stats.max_filed is None or filed > stats.max_filed):
            stats.max_filed = filed
        end = row.get("end")
        if not isinstance(end, str):
            continue
        accn = str(row.get("accn", ""))
        info = stats.periods.setdefault((str(row.get("start", "")), end), PeriodInfo())
        info.vals_by_accn[accn] = str(row.get("val"))
        info.fys.add(str(row.get("fy")))
        if filed_ok and (info.min_filed is None or filed < info.min_filed):
            info.min_filed = filed
        stats.fyfp_by_accn.setdefault(accn, set()).add((str(row.get("fy")), str(row.get("fp"))))
    return stats


def summarize_tag(namespace: str, tag: str, tag_obj: Any, today: date) -> TagSummary:
    units_obj = tag_obj.get("units") if isinstance(tag_obj, dict) else None
    units: dict[str, list[dict[str, Any]]] = {}
    if isinstance(units_obj, dict):
        for unit, rows in units_obj.items():
            if isinstance(rows, list):
                units[str(unit)] = [row for row in rows if isinstance(row, dict)]
    entries = [row for rows in units.values() for row in rows]
    sample_unit = max(units, key=lambda u: len(units[u])) if units else None
    sample_rows = units[sample_unit] if sample_unit else []

    bad = {"end": 0, "start": 0, "filed": 0}
    for row in entries:
        if not DATE_RE.match(str(row.get("end", ""))):
            bad["end"] += 1
        if "start" in row and not DATE_RE.match(str(row.get("start", ""))):
            bad["start"] += 1
        if not DATE_RE.match(str(row.get("filed", ""))):
            bad["filed"] += 1

    ends = sorted(str(row["end"]) for row in entries if DATE_RE.match(str(row.get("end", ""))))
    latest_end = ends[-1] if ends else None
    stale = False
    if latest_end is not None:
        stale = (today - date.fromisoformat(latest_end)).days > STALE_AFTER_DAYS

    fy_rows = sorted((r for r in sample_rows if r.get("fp") == "FY"), key=_sort_key)
    interim_rows = sorted((r for r in sample_rows if r.get("fp") != "FY"), key=_sort_key)
    return TagSummary(
        namespace=namespace,
        tag=tag,
        units={unit: len(rows) for unit, rows in units.items()},
        entries=len(entries),
        forms=Counter(str(r.get("form", "?")) for r in entries),
        fps=Counter(str(r.get("fp", "?")) for r in entries),
        earliest_end=ends[0] if ends else None,
        latest_end=latest_end,
        stale=stale,
        bad_dates=bad,
        distinct_periods=len({(r.get("start"), r.get("end")) for r in entries}),
        durations=Counter(
            _duration_bucket(_days_between(r.get("start"), r.get("end"))) for r in entries
        ),
        latest_fy=fy_rows[-1] if fy_rows else None,
        latest_interim=interim_rows[-1] if interim_rows else None,
        sample_unit=sample_unit,
        stats=collect_stats(entries, instant=(namespace, tag) in INSTANT_TAGS),
    )


def analyze_companyfacts(doc: Any, today: date) -> FactsReport | None:
    if not isinstance(doc, dict) or not isinstance(doc.get("facts"), dict):
        return None
    facts: dict[str, Any] = doc["facts"]
    namespaces = {ns: len(tags) for ns, tags in facts.items() if isinstance(tags, dict)}
    unit_tags: Counter[str] = Counter()
    for tags in facts.values():
        if not isinstance(tags, dict):
            continue
        for tag_obj in tags.values():
            units = tag_obj.get("units") if isinstance(tag_obj, dict) else None
            if isinstance(units, dict):
                unit_tags.update(str(unit) for unit in units)
    concepts: dict[str, ConceptReport] = {}
    for concept, candidates in CONCEPTS.items():
        found: list[TagSummary] = []
        missing: list[str] = []
        for namespace, tag in candidates:
            tags = facts.get(namespace)
            tag_obj = tags.get(tag) if isinstance(tags, dict) else None
            if isinstance(tag_obj, dict):
                found.append(summarize_tag(namespace, tag, tag_obj, today))
            else:
                missing.append(f"{namespace}:{tag}")
        concepts[concept] = ConceptReport(found, missing)
    return FactsReport(
        entity_name=str(doc.get("entityName", "?")),
        cik=doc.get("cik"),
        namespaces=namespaces,
        concepts=concepts,
        unit_tags=unit_tags,
    )


def format_entry(entry: Mapping[str, Any]) -> str:
    days = _days_between(entry.get("start"), entry.get("end"))
    parts = [
        f"end={entry.get('end')}",
        f"start={entry.get('start', '(none)')}",
        f"val={short(entry.get('val'), 24)}",
        f"fy={entry.get('fy')}",
        f"fp={entry.get('fp')}",
        f"form={entry.get('form')}",
        f"filed={entry.get('filed')}",
        f"accn={entry.get('accn', '(none)')}",
        f"frame={entry.get('frame', '(none)')}",
        f"dur={f'{days}d' if days is not None else 'n/a'}",
    ]
    return " ".join(parts)


def print_facts_report(
    ctx: Context, ticker: str, report: FactsReport, *, detailed: bool = True
) -> None:
    """``detailed`` prints period mix and interim samples; others get a compact view."""
    ctx.say(
        f"  entity={short(report.entity_name, 50)} cik={report.cik} "
        f"namespaces={dict(report.namespaces)}"
    )
    all_bad = {"end": 0, "start": 0, "filed": 0}
    for concept, concept_report in report.concepts.items():
        ctx.say(f"  -- {concept} ({'primary tag: ' + CONCEPTS[concept][0][1]})")
        for summary in concept_report.found:
            primary = (summary.namespace, summary.tag) == CONCEPTS[concept][0]
            for key, count in summary.bad_dates.items():
                all_bad[key] += count
            ctx.say(
                f"     [{'primary' if primary else 'alternate'}] {summary.namespace}:{summary.tag}"
                f" units={summary.units} entries={summary.entries}"
                f" distinct_periods={summary.distinct_periods}"
            )
            ctx.say(
                f"        forms={dict(summary.forms.most_common(6))}"
                f" fp={dict(summary.fps.most_common(6))}"
                f" span={summary.earliest_end}..{summary.latest_end}"
                f"{' STALE(tag not used recently)' if summary.stale else ''}"
            )
            if detailed:
                ctx.say(f"        period_length={dict(summary.durations)}")
            if summary.latest_fy:
                ctx.say(f"        latest FY     : {format_entry(summary.latest_fy)}")
            if detailed and summary.latest_interim:
                ctx.say(f"        latest interim: {format_entry(summary.latest_interim)}")
        if concept_report.missing and detailed:
            ctx.say(f"     not present: {', '.join(concept_report.missing)}")
        primary_found = any(
            (s.namespace, s.tag) == CONCEPTS[concept][0] for s in concept_report.found
        )
        if primary_found:
            detail = "primary tag present"
        elif concept_report.found:
            detail = "primary missing, alternate(s): " + ", ".join(
                s.tag for s in concept_report.found
            )
        else:
            detail = "no candidate tag present"
        ctx.record("SEC", f"{ticker}/{concept}", concept_report.verdict, detail)
    bad_total = sum(all_bad.values())
    ctx.record(
        "SEC",
        f"{ticker}/date-format",
        EXISTS if bad_total == 0 else ERROR,
        "all end/start/filed match YYYY-MM-DD"
        if bad_total == 0
        else f"entries not matching YYYY-MM-DD: {all_bad}",
    )


def print_brief_report(ctx: Context, label: str, report: FactsReport) -> None:
    """One-screen view for companies probed only for taxonomy and currency (P-12)."""
    ctx.say(
        f"  entity={short(report.entity_name, 50)} cik={report.cik} "
        f"namespaces={dict(report.namespaces)}"
    )
    foreign = foreign_currency_units(report.unit_tags)
    ctx.say(f"  non-USD currency units used: {foreign if foreign else 'none'}")
    ctx.say(f"  top units by tag count: {dict(report.unit_tags.most_common(6))}")
    covered = {concept: ("-" if not rep.found else "+") for concept, rep in report.concepts.items()}
    ctx.say(f"  whitelist concepts with a tag (us-gaap/dei only): {covered}")
    n_found = sum(1 for rep in report.concepts.values() if rep.found)
    ctx.record(
        "SEC",
        f"{label}/companyfacts-brief",
        EXISTS if n_found else MISSING,
        f"{n_found}/{len(report.concepts)} concepts have a us-gaap/dei tag; "
        f"ifrs-full={'yes' if 'ifrs-full' in report.namespaces else 'no'}; "
        f"non-USD units={foreign if foreign else 'none'}",
    )


def parse_ticker_map(doc: Any) -> dict[str, int]:
    """Accepts both SEC ticker file layouts; returns {TICKER: cik}."""
    mapping: dict[str, int] = {}
    if isinstance(doc, dict) and isinstance(doc.get("data"), list):
        fields = doc.get("fields")
        if isinstance(fields, list) and "cik" in fields and "ticker" in fields:
            cik_at, ticker_at = fields.index("cik"), fields.index("ticker")
            for row in doc["data"]:
                if isinstance(row, list) and len(row) > max(cik_at, ticker_at):
                    try:
                        mapping[str(row[ticker_at]).upper()] = int(row[cik_at])
                    except (TypeError, ValueError):
                        continue
    elif isinstance(doc, dict):
        for row in doc.values():
            if isinstance(row, dict) and "ticker" in row and "cik_str" in row:
                try:
                    mapping[str(row["ticker"]).upper()] = int(row["cik_str"])
                except (TypeError, ValueError):
                    continue
    return mapping


def ticker_variants(ticker: str) -> list[str]:
    """Spellings of a class-share ticker that different systems use."""
    upper = ticker.upper()
    variants = [upper, upper.replace(".", "-"), upper.replace("/", "-"), upper.replace(".", "")]
    return list(dict.fromkeys(variants))


def lookup_ticker(mapping: Mapping[str, int], ticker: str) -> tuple[int | None, str | None]:
    """Return (cik, spelling that matched); (None, None) when no spelling matches."""
    for variant in ticker_variants(ticker):
        if variant in mapping:
            return mapping[variant], variant
    return None, None


def parse_holdings(raw: str) -> tuple[list[str], list[str]]:
    """Split the optional holdings list into (accepted, ignored); accepted is capped."""
    accepted: list[str] = []
    ignored: list[str] = []
    for part in re.split(r"[,\s;]+", raw.strip()):
        if not part:
            continue
        ticker = part.upper()
        if (
            not HOLDING_RE.match(ticker)
            or ticker in accepted
            or ticker in SEC_TICKERS
            or ticker == FOREIGN_SAMPLE
            or len(accepted) >= MAX_HOLDINGS
        ):
            ignored.append(part)
        else:
            accepted.append(ticker)
    return accepted, ignored


# ---------------------------------------------------------------- SEC evidence for the P items


@dataclass
class FactsFetch:
    status: int | None
    decoded_bytes: int
    wire_bytes: int | None
    last_modified: str | None


@dataclass
class SubmissionsInfo:
    status: int | None = None
    ok: bool = False
    name: str = ""
    sic: str = ""
    sic_description: str = ""
    entity_type: str = ""
    category: str = ""
    fiscal_year_end: str = ""
    exchanges: list[str] = field(default_factory=list)
    recent_fields: dict[str, bool] = field(default_factory=dict)
    recent_count: int = 0
    filing_date_format_ok: bool | None = None
    acceptance_format_ok: bool | None = None
    latest_periodic: dict[str, str] | None = None


@dataclass
class SecEvidence:
    """What the SEC section saw; the ADR-0038 P items are judged from this alone."""

    attempted: bool = False
    map_from_network: bool = False
    map_url: str | None = None
    ticker_map: dict[str, int] = field(default_factory=dict)
    reports: dict[str, FactsReport] = field(default_factory=dict)
    facts_fetch: dict[str, FactsFetch] = field(default_factory=dict)
    holdings: list[str] = field(default_factory=list)
    submissions: dict[str, SubmissionsInfo] = field(default_factory=dict)
    submissions_validators: dict[str, str] = field(default_factory=dict)
    conditional_status: int | None = None
    conditional_note: str = ""
    etf_cik_source: str = ""
    etf_facts_status: int | None = None
    docs_status: int | None = None
    docs_limit: int | None = None
    docs_snippets: list[str] = field(default_factory=list)
    rate_headers: dict[str, str] = field(default_factory=dict)
    sec_statuses: list[int | None] = field(default_factory=list)


def analyze_submissions(doc: Any, status: int | None) -> SubmissionsInfo:
    info = SubmissionsInfo(status=status)
    if not isinstance(doc, dict):
        return info
    info.ok = True
    info.name = str(doc.get("name", ""))
    info.sic = str(doc.get("sic", "") or "")
    info.sic_description = str(doc.get("sicDescription", "") or "")
    info.entity_type = str(doc.get("entityType", "") or "")
    info.category = str(doc.get("category", "") or "")
    info.fiscal_year_end = str(doc.get("fiscalYearEnd", "") or "")
    exchanges = doc.get("exchanges")
    if isinstance(exchanges, list):
        info.exchanges = [str(e) for e in exchanges if e]
    filings = doc.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else None
    if not isinstance(recent, dict):
        return info
    for name in SUBMISSION_FIELDS:
        info.recent_fields[name] = isinstance(recent.get(name), list) and bool(recent[name])
    raw_forms = recent.get("form")
    forms: list[Any] = raw_forms if isinstance(raw_forms, list) else []
    info.recent_count = len(forms)

    def column(name: str) -> list[Any]:
        values = recent.get(name)
        return values if isinstance(values, list) else []

    dates = [str(v) for v in column("filingDate")]
    stamps = [str(v) for v in column("acceptanceDateTime")]
    info.filing_date_format_ok = bool(dates) and all(DATE_RE.match(d) for d in dates)
    info.acceptance_format_ok = bool(stamps) and all(ACCEPTANCE_RE.match(s) for s in stamps)
    best: dict[str, str] | None = None
    accessions = column("accessionNumber")
    for index, form in enumerate(forms):
        if form not in PERIODIC_FORMS or index >= len(dates):
            continue
        if best is None or dates[index] > best["filingDate"]:
            best = {
                "form": str(form),
                "filingDate": dates[index],
                "acceptanceDateTime": stamps[index] if index < len(stamps) else "",
                "accessionNumber": str(accessions[index]) if index < len(accessions) else "",
            }
    info.latest_periodic = best
    return info


def extract_doc_facts(html: str) -> tuple[int | None, list[str]]:
    """Pull the documented request limit and User-Agent sentences out of the SEC page."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    limit_match = re.search(r"(?i)(\d+)\s+requests?\s+per\s+second", text)
    limit = int(limit_match.group(1)) if limit_match else None
    sentences = re.split(r"(?<=[.!?])\s+", text)
    snippets = [
        short(s.strip(), 240)
        for s in sentences
        if re.search(r"(?i)requests?\s+per\s+second|user[- ]agent", s)
    ]
    return limit, snippets[:4]


def _sec_get(
    ctx: Context, url: str, headers: Mapping[str, str], *, shown_url: str | None = None
) -> HttpResult:
    """GET that also remembers the status so P-5 can look for throttling."""
    ctx.say(f"GET {shown_url or url}")
    result = ctx.fetcher.get(url, headers)
    ctx.say(f"  {describe_http(result)}")
    ctx.evidence.sec_statuses.append(result.status)
    return result


def _sec_json(
    ctx: Context, url: str, headers: Mapping[str, str]
) -> tuple[HttpResult, Any, str | None]:
    result = _sec_get(ctx, url, headers)
    if result.status is None or not result.body:
        return result, None, result.error or "empty body"
    obj, error = parse_json(result.body)
    if error:
        ctx.say(f"  JSON parse failed: {error}; first bytes: {short(result.body[:80], 90)!r}")
    return result, obj, error


def _fetch_facts(
    ctx: Context, label: str, cik: int, headers: Mapping[str, str], *, mode: str
) -> None:
    """One companyfacts request. ``mode``: full, compact or brief (see the printers)."""
    ev = ctx.evidence
    result, doc, error = _sec_json(ctx, SEC_FACTS_URL.format(cik=cik), headers)
    ev.facts_fetch[label] = FactsFetch(
        result.status,
        len(result.body),
        result.wire_size,
        result.headers.get("last-modified"),
    )
    if result.status != 200 or error is not None:
        ctx.record("SEC", f"{label}/companyfacts", ERROR, describe_http(result))
        return
    report = analyze_companyfacts(doc, ctx.today)
    if report is None:
        ctx.record("SEC", f"{label}/companyfacts", ERROR, "unexpected JSON layout")
        return
    ev.reports[label] = report
    ctx.record("SEC", f"{label}/companyfacts", EXISTS, describe_http(result))
    if mode == "brief":
        print_brief_report(ctx, label, report)
    else:
        print_facts_report(ctx, label, report, detailed=mode == "full")


def _fetch_submissions(
    ctx: Context, label: str, cik: int, headers: Mapping[str, str]
) -> SubmissionsInfo:
    ev = ctx.evidence
    result, doc, error = _sec_json(ctx, SEC_SUBMISSIONS_URL.format(cik=cik), headers)
    info = analyze_submissions(doc if error is None else None, result.status)
    ev.submissions[label] = info
    if label == SEC_TICKERS[0]:
        ev.submissions_validators = {
            k: v for k, v in result.headers.items() if k in ("etag", "last-modified")
        }
        ev.rate_headers.update(
            {k: v for k, v in result.headers.items() if k.startswith(("x-ratelimit", "ratelimit"))}
        )
    if result.status != 200 or not info.ok:
        ctx.record("SEC", f"{label}/submissions", ERROR, describe_http(result))
        return info
    ctx.say(
        f"  name={short(info.name, 40)} sic={info.sic or '(none)'} "
        f"sicDescription={short(info.sic_description, 40)!r} "
        f"entityType={info.entity_type or '(none)'} "
        f"category={short(info.category, 40)!r} fiscalYearEnd={info.fiscal_year_end or '(none)'} "
        f"exchanges={info.exchanges}"
    )
    ctx.say(
        f"  filings.recent: {info.recent_count} rows, columns present={info.recent_fields}, "
        f"filingDate format ok={info.filing_date_format_ok}, "
        f"acceptanceDateTime format ok={info.acceptance_format_ok}"
    )
    if info.latest_periodic:
        ctx.say(f"  latest periodic filing: {info.latest_periodic}")
    ctx.record("SEC", f"{label}/submissions", EXISTS, describe_http(result))
    return info


def _check_conditional(ctx: Context, headers: Mapping[str, str]) -> None:
    """Repeat the AAPL submissions request with validators to see whether 304 is honoured."""
    ev = ctx.evidence
    validators = ev.submissions_validators
    if not validators:
        ev.conditional_note = "first response carried no ETag or Last-Modified; request skipped"
        ctx.say(f"  conditional request skipped: {ev.conditional_note}")
        return
    conditional = dict(headers)
    if "etag" in validators:
        conditional["If-None-Match"] = validators["etag"]
    if "last-modified" in validators:
        conditional["If-Modified-Since"] = validators["last-modified"]
    cik = ev.ticker_map.get(SEC_TICKERS[0]) or SEC_FALLBACK_CIKS[SEC_TICKERS[0]]
    ctx.say(f"  repeating with validators {sorted(validators)}")
    result = _sec_get(ctx, SEC_SUBMISSIONS_URL.format(cik=cik), conditional)
    ev.conditional_status = result.status
    ev.conditional_note = f"validators sent: {sorted(validators)}; got {describe_http(result)}"
    ctx.record(
        "SEC",
        "conditional-request",
        EXISTS if result.status == 304 else MISSING,
        ev.conditional_note,
    )


def run_sec(ctx: Context) -> None:
    section_header(ctx, "1. SEC EDGAR")
    ev = ctx.evidence
    user_agent = ctx.env.get(ENV_SEC_UA, "").strip()
    if "@" not in user_agent:
        ctx.say(f"  {ENV_SEC_UA} is not set or lacks a contact email; SEC rejects such requests.")
        ctx.say('  Expected format: "Your Name your@email". Section skipped, no request sent.')
        ctx.record("SEC", "all", SKIPPED, f"{ENV_SEC_UA} missing or malformed")
        return
    ev.attempted = True
    headers = {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip",
        "Accept": "application/json",
    }

    mapping: dict[str, int] = {}
    for url in (SEC_TICKER_URL, SEC_TICKER_FALLBACK_URL):
        result, doc, error = _sec_json(ctx, url, headers)
        mapping = parse_ticker_map(doc) if error is None else {}
        if result.status == 200 and mapping:
            ctx.say(
                f"  entries={len(mapping):,} sample={ {t: mapping.get(t) for t in SEC_TICKERS} }"
            )
            ctx.record("SEC", "ticker-map", EXISTS, f"path confirmed: {url}")
            ev.map_from_network, ev.map_url = True, url
            break
        ctx.record("SEC", f"ticker-map {url}", ERROR, describe_http(result))
    else:
        ctx.say("  Both ticker-map paths failed; using built-in CIKs (NOT verified by this run).")
        mapping = dict(SEC_FALLBACK_CIKS)
    ev.ticker_map = mapping

    for ticker in SEC_TICKERS:
        cik = mapping.get(ticker)
        if cik is None:
            ctx.record("SEC", f"{ticker}/companyfacts", MISSING, "ticker not in ticker map")
            continue
        _fetch_facts(
            ctx, ticker, cik, headers, mode="full" if ticker == SEC_TICKERS[0] else "compact"
        )

    ctx.say("")
    ctx.say(
        f"-- foreign-filer sample ({FOREIGN_SAMPLE}) and your holdings: taxonomy and currency --"
    )
    foreign_cik, _ = lookup_ticker(mapping, FOREIGN_SAMPLE)
    if foreign_cik is None:
        foreign_cik = SEC_FALLBACK_CIKS[FOREIGN_SAMPLE]
        ctx.say(f"  {FOREIGN_SAMPLE} not in ticker map; using built-in CIK (NOT verified).")
    _fetch_facts(ctx, FOREIGN_SAMPLE, foreign_cik, headers, mode="brief")

    holdings, ignored = parse_holdings(ctx.env.get(ENV_HOLDINGS, ""))
    ev.holdings = holdings
    if ignored:
        ctx.say(f"  {ENV_HOLDINGS}: ignored {ignored} (invalid, duplicate, or over {MAX_HOLDINGS})")
    for ticker in holdings:
        cik, matched = lookup_ticker(mapping, ticker)
        if cik is None:
            ctx.record("SEC", f"holding {ticker}/companyfacts", MISSING, "ticker not in ticker map")
            continue
        ctx.say(f"  holding {ticker} resolved as {matched}")
        _fetch_facts(ctx, ticker, cik, headers, mode="brief")

    ctx.say("")
    ctx.say("-- filing list (submissions): fields, entity metadata, conditional requests --")
    aapl_cik = mapping.get(SEC_TICKERS[0])
    if aapl_cik is not None:
        _fetch_submissions(ctx, SEC_TICKERS[0], aapl_cik, headers)
        _check_conditional(ctx, headers)

    ctx.say("")
    ctx.say(f"-- ETF ({ETF_SAMPLE}): how the SEC treats a fund --")
    etf_cik, matched = lookup_ticker(mapping, ETF_SAMPLE)
    ev.etf_cik_source = (
        f"ticker map ({matched})" if etf_cik is not None else "built-in (not in map)"
    )
    if etf_cik is None:
        etf_cik = SEC_FALLBACK_CIKS[ETF_SAMPLE]
        ctx.say(f"  {ETF_SAMPLE} not in the ticker map; using built-in CIK (NOT verified).")
    _fetch_submissions(ctx, ETF_SAMPLE, etf_cik, headers)
    etf_result = _sec_get(ctx, SEC_FACTS_URL.format(cik=etf_cik), headers)
    ev.etf_facts_status = etf_result.status
    ctx.record(
        "SEC",
        f"{ETF_SAMPLE}/companyfacts",
        EXISTS if etf_result.status == 200 else MISSING,
        f"{describe_http(etf_result)} (a 404 here means the fund has no XBRL facts)",
    )

    ctx.say("")
    ctx.say("-- SEC fair-access page: documented request limit and User-Agent rule --")
    docs_headers = {k: v for k, v in headers.items() if k != "Accept"}
    docs = _sec_get(ctx, SEC_DOCS_URL, docs_headers)
    ev.docs_status = docs.status
    if docs.status == 200 and docs.body:
        ev.docs_limit, ev.docs_snippets = extract_doc_facts(docs.body.decode("utf-8", "replace"))
        ctx.say(f"  documented limit: {ev.docs_limit} requests/second")
        for snippet in ev.docs_snippets:
            ctx.say(f"  page says: {snippet}")
        ctx.record("SEC", "fair-access-page", EXISTS, f"limit={ev.docs_limit}")
    else:
        ctx.record("SEC", "fair-access-page", ERROR, describe_http(docs))
    ev.rate_headers.update(
        {k: v for k, v in docs.headers.items() if k.startswith(("x-ratelimit", "retry-after"))}
    )


# ---------------------------------------------------------------- OpenAPI (TWSE / TPEx)


@dataclass(frozen=True)
class DatasetInfo:
    path: str
    summary: str
    fields: tuple[str, ...]


def _resolve_ref(doc: Any, ref: str) -> Any:
    if not ref.startswith("#/"):
        return None
    node = doc
    for part in ref[2:].split("/"):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _schema_fields(doc: Any, schema: Any, depth: int = 0) -> list[str]:
    if not isinstance(schema, dict) or depth > 5:
        return []
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return _schema_fields(doc, _resolve_ref(doc, ref), depth + 1)
    if schema.get("type") == "array":
        return _schema_fields(doc, schema.get("items"), depth + 1)
    properties = schema.get("properties")
    return [str(name) for name in properties] if isinstance(properties, dict) else []


def _response_fields(doc: Any, operation: Mapping[str, Any]) -> list[str]:
    responses = operation.get("responses")
    ok = responses.get("200") if isinstance(responses, dict) else None
    if not isinstance(ok, dict):
        return []
    schema = ok.get("schema")
    if schema is None and isinstance(ok.get("content"), dict):
        content: dict[str, Any] = ok["content"]
        media = content.get("application/json") or next(iter(content.values()), None)
        schema = media.get("schema") if isinstance(media, dict) else None
    return _schema_fields(doc, schema)


def parse_openapi(doc: Any) -> list[DatasetInfo]:
    paths = doc.get("paths") if isinstance(doc, dict) else None
    if not isinstance(paths, dict):
        return []
    datasets: list[DatasetInfo] = []
    for path, item in paths.items():
        operation = item.get("get") if isinstance(item, dict) else None
        if not isinstance(operation, dict):
            continue
        summary = str(operation.get("summary") or operation.get("description") or "")
        datasets.append(DatasetInfo(str(path), summary, tuple(_response_fields(doc, operation))))
    return datasets


def _contains_any(text: str, words: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def classify(datasets: list[DatasetInfo]) -> dict[str, list[DatasetInfo]]:
    """Dataset-level hits: keyword in path or summary."""
    hits: dict[str, list[DatasetInfo]] = {name: [] for name in KEYWORDS}
    for info in datasets:
        for name, words in KEYWORDS.items():
            if _contains_any(f"{info.path} {info.summary}", words):
                hits[name].append(info)
    return hits


def field_hits(datasets: list[DatasetInfo], category: str) -> list[tuple[DatasetInfo, list[str]]]:
    """Field-level hits: keyword inside a column name (e.g. a balance-sheet line item)."""
    words = KEYWORDS[category]
    found: list[tuple[DatasetInfo, list[str]]] = []
    for info in datasets:
        matched = [name for name in info.fields if _contains_any(name, words)]
        if matched:
            found.append((info, matched))
    return found


def pick_samples(datasets: list[DatasetInfo], limit: int) -> list[DatasetInfo]:
    hits = classify(datasets)
    ordered: list[DatasetInfo] = []
    ordered += hits["cashflow"][:1]
    ordered += hits["treasury"][:1]
    for category in ("cashflow", "treasury"):
        ordered += [info for info, _ in field_hits(datasets, category)][:1]
    ordered += hits["statement"]
    chosen: list[DatasetInfo] = []
    for info in ordered:
        if info not in chosen:
            chosen.append(info)
        if len(chosen) >= limit:
            break
    return chosen


def print_sample(ctx: Context, name: str, info: DatasetInfo, result: HttpResult, doc: Any) -> None:
    if result.status != 200 or not isinstance(doc, list):
        kind = type(doc).__name__
        ctx.record(name, f"sample {info.path}", ERROR, f"{describe_http(result)}, JSON {kind}")
        return
    rows = [row for row in doc if isinstance(row, dict)]
    keys = list(rows[0].keys()) if rows else []
    ctx.say(f"  rows={len(rows):,} keys({len(keys)})={keys[:MAX_FIELDS_SHOWN]}")
    for row in rows[:2]:
        sample = {k: short(v, 24) for k, v in list(row.items())[:MAX_SAMPLE_FIELDS]}
        ctx.say(f"  sample row: {sample}")
    ctx.record(name, f"sample {info.path}", EXISTS if rows else MISSING, f"{len(rows):,} rows")


def run_openapi(ctx: Context, name: str, swagger_url: str, base_url: str, max_samples: int) -> None:
    ctx.say("")
    ctx.say(f"-- {name} swagger --")
    result, doc, error = fetch_json(ctx, swagger_url)
    datasets = parse_openapi(doc) if error is None else []
    if result.status != 200 or not datasets:
        ctx.record(name, "swagger", ERROR, f"{describe_http(result)}, datasets parsed: 0")
        return
    t187 = [d for d in datasets if "t187ap" in d.path.lower()]
    ctx.record(name, "swagger", EXISTS, f"{len(datasets)} datasets, {len(t187)} with 't187ap'")

    ctx.say(f"  t187ap datasets (showing up to {MAX_LISTED_T187AP}):")
    for info in t187[:MAX_LISTED_T187AP]:
        ctx.say(f"    {info.path} | {short(info.summary, 60)} | {len(info.fields)} fields")

    hits = classify(datasets)
    for category, label in (("cashflow", "cash flow statement"), ("treasury", "treasury stock")):
        ctx.say(f"  dataset-level matches for {label}:")
        for info in hits[category]:
            ctx.say(f"    {info.path} | {short(info.summary, 60)} | {len(info.fields)} fields")
        fhits = field_hits(datasets, category)
        ctx.say(f"  field-level matches for {label} (column names containing the keyword):")
        for info, matched in fhits[:8]:
            ctx.say(f"    {info.path} | {short(info.summary, 40)} | columns: {matched[:6]}")
        if hits[category]:
            verdict, detail = EXISTS, f"{len(hits[category])} dataset(s) by path/summary"
        elif fhits:
            verdict = MISSING
            detail = f"no dataset-level match; {len(fhits)} dataset(s) only carry it as a column"
        else:
            verdict, detail = MISSING, "no dataset-level or field-level match"
        ctx.record(name, label, verdict, detail)

    for info in pick_samples(datasets, max_samples):
        sample_result, sample_doc, sample_error = fetch_json(ctx, base_url + info.path)
        if sample_error is not None:
            ctx.record(name, f"sample {info.path}", ERROR, describe_http(sample_result))
            continue
        print_sample(ctx, name, info, sample_result, sample_doc)


def run_twse(ctx: Context) -> None:
    section_header(ctx, "2. TWSE OpenAPI (listed) and TPEx OpenAPI (OTC)")
    run_openapi(ctx, "TWSE", TWSE_SWAGGER_URL, TWSE_BASE_URL, max_samples=3)
    run_openapi(ctx, "TPEx", TPEX_SWAGGER_URL, TPEX_BASE_URL, max_samples=2)


# ---------------------------------------------------------------- FinMind


def parse_enum_names(source: str) -> list[str]:
    return sorted(set(re.findall(r"=\s*\(?\s*\"([A-Za-z][A-Za-z0-9_]+)\"", source)))


def analyze_finmind_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    types: dict[str, str] = {}
    dates: set[str] = set()
    for row in rows:
        types.setdefault(str(row.get("type", "?")), str(row.get("origin_name", "")))
        dates.add(str(row.get("date", "")))
    matched = {
        t: origin
        for t, origin in types.items()
        if _contains_any(f"{t} {origin}", FINMIND_TYPE_KEYWORDS)
    }
    return {"types": types, "dates": sorted(dates), "matched": matched}


def run_finmind(ctx: Context) -> None:
    section_header(ctx, "3. FinMind")
    token = ctx.env.get(ENV_FINMIND, "").strip()
    ctx.say(f"  {ENV_FINMIND} is {'set' if token else 'NOT set (anonymous tier, lower quota)'}")

    ctx.say("")
    ctx.say("-- dataset names known to the FinMind client library (not an official full list) --")
    result = ctx.fetcher.get(FINMIND_ENUM_URL)
    ctx.say(f"GET {FINMIND_ENUM_URL}")
    ctx.say(f"  {describe_http(result)}")
    if result.status == 200 and result.body:
        names = parse_enum_names(result.body.decode("utf-8", errors="replace"))
        interesting = [n for n in names if _contains_any(n, FINMIND_ENUM_KEYWORDS)]
        ctx.say(f"  dataset names parsed: {len(names)}")
        ctx.say(f"  keyword matches ({', '.join(FINMIND_ENUM_KEYWORDS)}): {interesting}")
        treasury = [n for n in names if _contains_any(n, ("treasur", "buyback", "repurchase"))]
        ctx.record(
            "FinMind",
            "treasury dataset name",
            EXISTS if treasury else MISSING,
            str(treasury) if treasury else "no treasury/buyback name in the library enum",
        )
    else:
        ctx.record("FinMind", "dataset enum", ERROR, describe_http(result))

    ctx.say("")
    ctx.say("-- quota (user_info) --")
    if token:
        result, doc, error = fetch_json(
            ctx, FINMIND_USER_INFO_URL, {"Authorization": f"Bearer {token}"}
        )
        if result.status == 200 and error is None and isinstance(doc, dict):
            ctx.say(f"  keys={sorted(doc.keys())}")
            ctx.say(f"  quota fields: { {k: doc[k] for k in FINMIND_QUOTA_KEYS if k in doc} }")
            ctx.record("FinMind", "quota", EXISTS, "user_info answered")
        else:
            ctx.record("FinMind", "quota", ERROR, describe_http(result))
    else:
        ctx.say("  skipped: needs a token")
        ctx.record("FinMind", "quota", SKIPPED, f"{ENV_FINMIND} not set")

    for market, stock_id in FINMIND_TICKERS:
        ctx.say("")
        ctx.say(f"-- {FINMIND_CASHFLOW_DATASET} {market} {stock_id} --")
        params = {
            "dataset": FINMIND_CASHFLOW_DATASET,
            "data_id": stock_id,
            "start_date": FINMIND_CASHFLOW_START,
        }
        shown = f"{FINMIND_DATA_URL}?{urllib.parse.urlencode(params)}"
        if token:
            params["token"] = token
        url = f"{FINMIND_DATA_URL}?{urllib.parse.urlencode(params)}"
        result, doc, error = fetch_json(ctx, url, shown_url=shown)
        check = f"cash-flow {market} {stock_id}"
        if error is not None or not isinstance(doc, dict):
            ctx.record("FinMind", check, ERROR, describe_http(result))
            continue
        ctx.say(f"  body status={doc.get('status')} msg={short(doc.get('msg'), 80)!r}")
        rows = [r for r in doc.get("data", []) if isinstance(r, dict)]
        if result.status != 200 or doc.get("status") != 200 or not rows:
            ctx.record(
                "FinMind", check, ERROR if doc.get("status") != 200 else MISSING, "no usable rows"
            )
            continue
        summary = analyze_finmind_rows(rows)
        ctx.say(f"  rows={len(rows):,} fields={list(rows[0].keys())}")
        ctx.say(f"  dates({len(summary['dates'])}): {summary['dates'][-8:]}")
        ctx.say(f"  distinct type values={len(summary['types'])}")
        ctx.say("  types matching operating/capex/treasury/dividend keywords:")
        for type_name, origin in list(summary["matched"].items())[:30]:
            latest = [(r.get("date"), r.get("value")) for r in rows if r.get("type") == type_name][
                -4:
            ]
            ctx.say(f"    {type_name} | {short(origin, 30)} | last 4 (date,value): {latest}")
        ctx.record("FinMind", check, EXISTS, f"{len(rows):,} rows, {len(summary['types'])} types")


# ---------------------------------------------------------------- Alpha Vantage


def run_alpha(ctx: Context) -> None:
    section_header(ctx, "4. Alpha Vantage US daily price (one request)")
    key = ctx.env.get(ENV_ALPHA, "").strip()
    if not key:
        ctx.say(f"  {ENV_ALPHA} not set; skipped, no request sent.")
        ctx.record("AlphaVantage", "daily", SKIPPED, f"{ENV_ALPHA} missing")
        return
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": ALPHA_SYMBOL,
        "outputsize": "compact",
    }
    shown = f"{ALPHA_URL}?{urllib.parse.urlencode(params)}&apikey={MASK}"
    url = f"{ALPHA_URL}?{urllib.parse.urlencode({**params, 'apikey': key})}"
    result, doc, error = fetch_json(ctx, url, shown_url=shown)
    if error is not None or not isinstance(doc, dict):
        ctx.record("AlphaVantage", "daily", ERROR, describe_http(result))
        return
    ctx.say(f"  top-level keys={sorted(doc.keys())}")
    series = doc.get("Time Series (Daily)")
    if isinstance(series, dict) and series:
        dates = sorted(series.keys())
        raw_meta = doc.get("Meta Data")
        meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        ctx.say(f"  meta={ {k: short(v, 30) for k, v in meta.items()} }")
        ctx.say(f"  rows={len(dates)} span={dates[0]}..{dates[-1]}")
        for day in dates[-3:]:
            ctx.say(f"    {day}: {dict(series[day])}")
        lag = (ctx.today - date.fromisoformat(dates[-1])).days if DATE_RE.match(dates[-1]) else None
        ctx.record(
            "AlphaVantage",
            "daily",
            EXISTS,
            f"{len(dates)} bars, newest {dates[-1]} ({lag} days before today)",
        )
        return
    for message_key in ("Error Message", "Note", "Information"):
        if message_key in doc:
            ctx.say(f"  {message_key}: {short(doc[message_key], 300)}")
            ctx.record("AlphaVantage", "daily", ERROR, f"vendor returned '{message_key}'")
            return
    ctx.record("AlphaVantage", "daily", ERROR, "no 'Time Series (Daily)' and no known error key")


# ---------------------------------------------------------------- ADR-0038 P items

#: Verdicts for P items. HOLDS / NOT_HOLD are decisive; the rest say why not.
HOLDS = "HOLDS"
NOT_HOLD = "NOT_HOLD"
PARTIAL = "PARTIAL"
MEASURED = "MEASURED"
INCONCLUSIVE = "INCONCLUSIVE"

#: ADR item code for each whitelist concept (docs: ADR-0038 D-1 point 3).
ITEM_CONCEPTS = {
    "OCF": "operating_cash_flow",
    "CapEx": "capital_expenditure",
    "Dividends": "dividends_paid",
    "Buyback": "share_repurchase_paid",
    "SBC": "stock_based_compensation",
    "Revenue": "revenue",
    "NetIncome": "net_income",
    "DilutedEPS": "diluted_earnings_per_share",
}
P1_REQUIRED_FIELDS = ("accn", "filed", "form", "end", "fy", "fp")
P2_PARTIAL_RATIO = 0.5
P2_HOLDS_RATIO = 0.9


@dataclass
class PResult:
    pid: str
    verdict: str
    detail: str
    lines: list[str] = field(default_factory=list)


def _us_gaap_reports(ev: SecEvidence) -> dict[str, FactsReport]:
    """Operating companies reporting in us-gaap among the base tickers and the holdings."""
    names = [*SEC_TICKERS, *ev.holdings]
    return {n: ev.reports[n] for n in names if n in ev.reports and ev.reports[n].uses_us_gaap}


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({100.0 * part / whole:.1f}%)" if whole else "0/0"


def eval_p1(ev: SecEvidence) -> PResult:
    reports = _us_gaap_reports(ev)
    stats = [s.stats for rep in reports.values() for s in rep.summaries]
    total = sum(st.total for st in stats)
    if not total:
        return PResult("P-1", INCONCLUSIVE, "no us-gaap companyfacts were fetched")
    present: Counter[str] = Counter()
    for st in stats:
        present.update(st.present)
    flow_total = sum(st.flow_total for st in stats)
    flow_start = sum(st.flow_with_start for st in stats)
    periods = [info for st in stats for info in st.periods.values()]
    multi_fy = sum(1 for info in periods if len(info.fys) > 1)
    accn_sets = [combos for st in stats for combos in st.fyfp_by_accn.values()]
    mixed_accn = sum(1 for combos in accn_sets if len(combos) > 1)
    lines = [f"facts examined: {total:,} across {len(stats)} tags of {sorted(reports)}"]
    lines.append(
        "field coverage: "
        + ", ".join(
            f"{name} {_pct(present[name], total)}" for name in (*P1_REQUIRED_FIELDS, "frame")
        )
    )
    lines.append(f"start present on period (flow) facts: {_pct(flow_start, flow_total)}")
    lines.append(
        f"periods whose facts carry more than one fy: {multi_fy} of {len(periods)}; "
        f"accn whose facts carry more than one (fy, fp): {mixed_accn} of {len(accn_sets)}"
    )
    structural_gaps = [n for n in P1_REQUIRED_FIELDS if present[n] != total]
    if flow_start != flow_total:
        structural_gaps.append("start")
    filing_level = multi_fy > 0 and mixed_accn == 0
    lines.append(
        "fy/fp are filing attributes, not period attributes: "
        + ("yes" if filing_level else "NOT shown by this data")
    )
    if structural_gaps:
        return PResult("P-1", NOT_HOLD, f"keys missing on some facts: {structural_gaps}", lines)
    if mixed_accn:
        return PResult(
            "P-1", NOT_HOLD, "one filing carries several (fy, fp): fy/fp not filing-level", lines
        )
    if present["frame"] == total and filing_level:
        return PResult(
            "P-1", HOLDS, "all eight fields on every fact; fy/fp are filing-level", lines
        )
    return PResult(
        "P-1",
        PARTIAL,
        f"accn/filed/form/start/end/fy/fp on every fact; frame on {_pct(present['frame'], total)} "
        f"(frame cannot be a key); fy/fp filing-level={'yes' if filing_level else 'not shown'}",
        lines,
    )


def _is_full_year(start: str, end: str) -> bool:
    days = _days_between(start, end)
    return days is not None and 350 <= days <= 380


def eval_p2(ev: SecEvidence, today: date) -> PResult:
    reports = _us_gaap_reports(ev)
    periods = 0
    multi = 0
    changed = 0
    old_full_years = 0
    original_kept = 0
    examples: list[str] = []
    for label, rep in reports.items():
        for summary in rep.summaries:
            for (start, end), info in summary.stats.periods.items():
                periods += 1
                if len(info.vals_by_accn) > 1:
                    multi += 1
                    if len(set(info.vals_by_accn.values())) > 1:
                        changed += 1
                        if len(examples) < 2:
                            examples.append(
                                f"{label} {summary.tag} {start or '(instant)'}..{end}: "
                                f"{dict(list(info.vals_by_accn.items())[:3])}"
                            )
                if not (start and _is_full_year(start, end) and info.min_filed):
                    continue
                try:
                    age = (today - date.fromisoformat(end)).days
                    lag = (date.fromisoformat(info.min_filed) - date.fromisoformat(end)).days
                except ValueError:
                    continue
                if age > OLD_PERIOD_AFTER_DAYS:
                    old_full_years += 1
                    if lag <= ORIGINAL_FILING_MAX_DAYS:
                        original_kept += 1
    if not periods:
        return PResult("P-2", INCONCLUSIVE, "no us-gaap companyfacts were fetched")
    lines = [
        f"periods seen: {periods:,}; reported by more than one filing: {_pct(multi, periods)}; "
        f"of those the value differs between filings: {changed}",
        f"closed full years (older than {OLD_PERIOD_AFTER_DAYS}d) whose earliest fact was filed "
        f"within {ORIGINAL_FILING_MAX_DAYS} days of period end (= original 10-K kept): "
        f"{_pct(original_kept, old_full_years)}",
    ]
    lines += [f"value changed across filings: {example}" for example in examples]
    if not old_full_years:
        return PResult("P-2", INCONCLUSIVE, "no closed full-year periods to test", lines)
    ratio = original_kept / old_full_years
    if multi == 0 or ratio < P2_PARTIAL_RATIO:
        return PResult("P-2", NOT_HOLD, "older filings and comparatives are not retained", lines)
    verdict = HOLDS if ratio >= P2_HOLDS_RATIO else PARTIAL
    return PResult(
        "P-2",
        verdict,
        f"original values kept for {_pct(original_kept, old_full_years)} of closed years; "
        f"{changed} restated period(s) seen",
        lines,
    )


def eval_p3(ev: SecEvidence) -> PResult:
    reports = _us_gaap_reports(ev)
    if not reports:
        return PResult("P-3", INCONCLUSIVE, "no us-gaap companyfacts were fetched")
    lines: list[str] = []
    uncovered: list[str] = []
    partial: list[str] = []
    alternates: list[str] = []
    for concept, item in ITEM_CONCEPTS.items():
        picks: list[str] = []
        covered = 0
        for label, rep in reports.items():
            concept_report = rep.concepts.get(concept)
            chosen = next(
                (s for s in (concept_report.found if concept_report else []) if s.verified), None
            )
            if chosen is None:
                found = [s.tag for s in concept_report.found] if concept_report else []
                why = f"present but not verified: {found}" if found else "no candidate tag present"
                picks.append(f"{label}: none ({why})")
                continue
            covered += 1
            is_primary = (chosen.namespace, chosen.tag) == CONCEPTS[concept][0]
            picks.append(f"{label}: {chosen.tag}{'' if is_primary else ' [alternate]'}")
            if not is_primary:
                alternates.append(f"{label}/{item}")
        lines.append(f"{item}: {covered}/{len(reports)}  " + "; ".join(picks))
        if covered == 0:
            uncovered.append(item)
        elif covered < len(reports):
            partial.append(item)
    lines.append(f"items served only by an alternate tag somewhere: {alternates or 'none'}")
    lines.append("verified = tag still in use (not stale) and at least 3 fiscal-year (fp=FY) facts")
    if uncovered:
        return PResult("P-3", NOT_HOLD, f"no verified tag for any company: {uncovered}", lines)
    if partial:
        return PResult("P-3", PARTIAL, f"some companies lack a verified tag for: {partial}", lines)
    return PResult(
        "P-3", HOLDS, f"every item has a verified tag for all {len(reports)} companies", lines
    )


def eval_p4(ev: SecEvidence) -> PResult:
    if not ev.attempted:
        return PResult("P-4", INCONCLUSIVE, "SEC section did not run")
    if not ev.map_from_network:
        return PResult("P-4", INCONCLUSIVE, "ticker map was not fetched; built-in CIKs only")
    mapping = ev.ticker_map
    lines = [f"map source: {ev.map_url}; entries: {len(mapping):,}"]
    for ticker in (*PROBE_TICKERS, "ZZZZNOTREAL"):
        cik, matched = lookup_ticker(mapping, ticker)
        sharing = sum(1 for value in mapping.values() if value == cik) if cik else 0
        direct = "direct" if matched == ticker.upper() else f"as {matched}"
        lines.append(
            f"{ticker}: "
            + (f"cik {cik} ({direct}); tickers sharing this cik: {sharing}" if cik else "not found")
        )
    lines.append(
        f"{ETF_SAMPLE} lookup source: {ev.etf_cik_source}; "
        f"its companyfacts status: {ev.etf_facts_status}"
    )
    aapl_cik, _ = lookup_ticker(mapping, SEC_TICKERS[0])
    if aapl_cik is None:
        return PResult("P-4", NOT_HOLD, "AAPL is not in the ticker map", lines)
    _, class_match = lookup_ticker(mapping, CLASS_SHARE_SAMPLE)
    etf_note = (
        f"ETF {ETF_SAMPLE}: companyfacts status {ev.etf_facts_status} (failure is detectable)"
    )
    if class_match is None:
        return PResult(
            "P-4", NOT_HOLD, f"{CLASS_SHARE_SAMPLE} found under no spelling; {etf_note}", lines
        )
    if class_match == CLASS_SHARE_SAMPLE.upper():
        return PResult("P-4", HOLDS, f"class share found as written; {etf_note}", lines)
    return PResult(
        "P-4",
        PARTIAL,
        f"class share only found as {class_match!r}: dotted tickers need normalising; {etf_note}",
        lines,
    )


def eval_p5(ev: SecEvidence) -> PResult:
    if not ev.attempted:
        return PResult("P-5", INCONCLUSIVE, "SEC section did not run")
    statuses = [s for s in ev.sec_statuses]
    throttled = [s for s in statuses if s in (403, 429)]
    lines = [
        f"SEC requests sent: {len(statuses)}; statuses seen: {dict(Counter(map(str, statuses)))}",
        f"observed pace: at most {1 / SEC_MIN_GAP_SECONDS:.0f} requests/second "
        f"(gap {SEC_MIN_GAP_SECONDS}s)",
        f"documented limit on the fair-access page: {ev.docs_limit}",
        f"rate-limit headers seen: {ev.rate_headers or 'none'}",
        "User-Agent format 'Name email' accepted: "
        + ("yes" if statuses and not throttled else "no/unknown"),
    ]
    lines += [f"page says: {s}" for s in ev.docs_snippets]
    if throttled:
        return PResult(
            "P-5",
            NOT_HOLD,
            f"SEC answered 403/429 ({len(throttled)}x): format or pace rejected",
            lines,
        )
    if ev.docs_limit is None:
        return PResult(
            "P-5", INCONCLUSIVE, "no throttling seen but the documented limit was not read", lines
        )
    return PResult(
        "P-5",
        HOLDS,
        f"documented limit {ev.docs_limit} requests/second; no 403/429 at <= "
        f"{1 / SEC_MIN_GAP_SECONDS:.0f}/s with the 'Name email' User-Agent",
        lines,
    )


def eval_p6(ev: SecEvidence) -> PResult:
    info = ev.submissions.get(SEC_TICKERS[0])
    if info is None or not info.ok:
        return PResult("P-6", INCONCLUSIVE, "AAPL submissions were not fetched")
    needed = ("accessionNumber", "filingDate", "acceptanceDateTime", "form")
    fields_ok = all(info.recent_fields.get(name) for name in needed)
    lines = [
        f"filing list columns present: {info.recent_fields}",
        f"filingDate YYYY-MM-DD: {info.filing_date_format_ok}; "
        f"acceptanceDateTime ISO timestamp: {info.acceptance_format_ok}",
        f"conditional request: {ev.conditional_note or 'not attempted'}",
    ]
    report = ev.reports.get(SEC_TICKERS[0])
    latest = info.latest_periodic
    if report is not None and latest is not None:
        facts_filed = report.max_filed
        behind = (
            (date.fromisoformat(latest["filingDate"]) - date.fromisoformat(facts_filed)).days
            if facts_filed and DATE_RE.match(latest["filingDate"])
            else None
        )
        lines.append(
            f"newest 10-K/10-Q in filing list: {latest['form']} filed {latest['filingDate']}; "
            f"newest filed date inside companyfacts: {facts_filed}; "
            f"companyfacts behind by: {behind} day(s) (one snapshot, not a latency measurement)"
        )
    fetched = ev.facts_fetch.get(SEC_TICKERS[0])
    lines.append(f"companyfacts Last-Modified header: {fetched.last_modified if fetched else None}")
    if not fields_ok:
        return PResult("P-6", NOT_HOLD, f"filing list lacks columns {needed}", lines)
    if ev.conditional_status == 304:
        return PResult(
            "P-6",
            HOLDS,
            "filing list has all columns and honours conditional requests (304)",
            lines,
        )
    return PResult(
        "P-6",
        PARTIAL,
        "filing list has all columns; conditional requests NOT honoured "
        f"(status {ev.conditional_status}): S2 must download the list each time",
        lines,
    )


def _mb(size: int | None) -> str:
    return f"{size / 1e6:.2f} MB" if size else "unknown"


def eval_p7(ev: SecEvidence) -> PResult:
    fetched = {k: v for k, v in ev.facts_fetch.items() if v.status == 200}
    if not fetched:
        return PResult("P-7", INCONCLUSIVE, "no companyfacts response was fetched")
    lines: list[str] = []
    for label, item in fetched.items():
        lines.append(
            f"{label}: decoded {item.decoded_bytes / 1e6:.2f} MB, "
            f"on the wire (gzip) {_mb(item.wire_bytes)}"
        )
    biggest = max(item.decoded_bytes for item in fetched.values())
    wire_known = [item.wire_bytes for item in fetched.values() if item.wire_bytes]
    detail = f"largest decoded {biggest / 1e6:.2f} MB"
    if wire_known:
        detail += f", largest compressed {max(wire_known) / 1e6:.2f} MB"
    return PResult(
        "P-7", MEASURED, detail + " (numbers only; the threshold is the ADR's call)", lines
    )


def eval_p8(ev: SecEvidence) -> PResult:
    company = ev.submissions.get(SEC_TICKERS[0])
    fund = ev.submissions.get(ETF_SAMPLE)
    if company is None or not company.ok:
        return PResult("P-8", INCONCLUSIVE, "AAPL submissions were not fetched")

    def signature(info: SubmissionsInfo) -> str:
        return (
            f"sic={info.sic or '-'} entityType={info.entity_type or '-'} "
            f"category={info.category or '-'}"
        )

    lines = [f"AAPL: {signature(company)}"]
    if not (company.sic and company.entity_type):
        return PResult("P-8", NOT_HOLD, "SIC or entityType missing for an operating company", lines)
    if fund is None or not fund.ok:
        lines.append(f"{ETF_SAMPLE}: submissions not fetched")
        return PResult(
            "P-8", INCONCLUSIVE, "SIC/entityType exist but no ETF sample to compare", lines
        )
    lines.append(f"{ETF_SAMPLE}: {signature(fund)} (sicDescription {fund.sic_description!r})")
    lines.append(f"{ETF_SAMPLE} companyfacts status: {ev.etf_facts_status}")
    if signature(fund) != signature(company):
        return PResult(
            "P-8", HOLDS, "SIC and entityType exist and differ between company and ETF", lines
        )
    return PResult(
        "P-8", PARTIAL, "SIC and entityType exist but look the same for company and ETF", lines
    )


def eval_p9(ev: SecEvidence) -> PResult:
    info = ev.submissions.get(SEC_TICKERS[0])
    if info is None or not info.ok:
        return PResult("P-9", INCONCLUSIVE, "AAPL submissions were not fetched")
    lines = [f"fiscalYearEnd from submissions: {info.fiscal_year_end or '(none)'}"]
    if not FISCAL_YEAR_END_RE.match(info.fiscal_year_end):
        return PResult("P-9", NOT_HOLD, "fiscalYearEnd missing or not MMDD", lines)
    report = ev.reports.get(SEC_TICKERS[0])
    # Full-year period facts only: a cover-page date (dei shares outstanding) is no year end.
    ends = sorted(
        str(s.latest_fy["end"])
        for s in (report.summaries if report else [])
        if s.latest_fy
        and DATE_RE.match(str(s.latest_fy.get("end", "")))
        and _is_full_year(str(s.latest_fy.get("start", "")), str(s.latest_fy["end"]))
    )
    if not ends:
        return PResult(
            "P-9", PARTIAL, "fiscalYearEnd present; no companyfacts FY end to cross-check", lines
        )
    latest = ends[-1]
    lines.append(f"latest fiscal-year end in companyfacts: {latest}")
    if latest[5:7] == info.fiscal_year_end[:2]:
        return PResult(
            "P-9",
            HOLDS,
            f"fiscalYearEnd {info.fiscal_year_end} matches the {latest} year end month",
            lines,
        )
    return PResult(
        "P-9",
        PARTIAL,
        f"fiscalYearEnd {info.fiscal_year_end} present but month differs from {latest}",
        lines,
    )


def eval_p12(ev: SecEvidence) -> PResult:
    lines: list[str] = []
    flagged: list[str] = []

    def describe(label: str) -> bool | None:
        rep = ev.reports.get(label)
        if rep is None:
            lines.append(f"{label}: companyfacts not fetched")
            return None
        foreign = foreign_currency_units(rep.unit_tags)
        ifrs = "ifrs-full" in rep.namespaces
        whitelist_units = sorted({u for s in rep.summaries for u in s.units})
        lines.append(
            f"{label}: ifrs-full={'yes' if ifrs else 'no'}; non-USD units={foreign or 'none'}; "
            f"units of whitelist tags={whitelist_units}"
        )
        return ifrs or bool(foreign)

    sample = describe(FOREIGN_SAMPLE)
    checked = [describe(t) for t in (*SEC_TICKERS, *ev.holdings)]
    for label, outcome in zip((*SEC_TICKERS, *ev.holdings), checked, strict=True):
        if outcome:
            flagged.append(label)
    fetched = [outcome for outcome in checked if outcome is not None]
    if ev.holdings and fetched:
        if flagged:
            return PResult(
                "P-12", HOLDS, f"non-USD or IFRS filers among checked companies: {flagged}", lines
            )
        return PResult(
            "P-12", NOT_HOLD, f"none of {len(fetched)} checked companies is non-USD or IFRS", lines
        )
    if sample:
        return PResult(
            "P-12",
            INCONCLUSIVE,
            f"{FOREIGN_SAMPLE} proves such filers exist in the SEC data; "
            f"set {ENV_HOLDINGS} to your US holdings to judge them",
            lines,
        )
    return PResult(
        "P-12",
        INCONCLUSIVE,
        f"no holdings given and the {FOREIGN_SAMPLE} sample was not usable",
        lines,
    )


def run_p_items(ctx: Context) -> None:
    section_header(ctx, "5. ADR-0038 P items (judged from the SEC evidence above, no new requests)")
    ev = ctx.evidence
    if not ev.attempted:
        ctx.say("  SEC section did not run, so no P item can be judged.")
        ctx.record("ADR-0038", "P-items", SKIPPED, "SEC section skipped")
        return
    results = [
        eval_p1(ev),
        eval_p2(ev, ctx.today),
        eval_p3(ev),
        eval_p4(ev),
        eval_p5(ev),
        eval_p6(ev),
        eval_p7(ev),
        eval_p8(ev),
        eval_p9(ev),
        eval_p12(ev),
    ]
    for item in results:
        ctx.say("")
        ctx.say(f"-- {item.pid}: {P_TITLES[item.pid]}")
        for line in item.lines:
            ctx.say(f"   {line}")
        ctx.record("ADR-0038", item.pid, item.verdict, item.detail)


# ---------------------------------------------------------------- orchestration

SECTIONS: tuple[tuple[str, Callable[[Context], None]], ...] = (
    ("SEC", run_sec),
    ("TWSE/TPEx", run_twse),
    ("FinMind", run_finmind),
    ("AlphaVantage", run_alpha),
    ("ADR-0038", run_p_items),
)


def script_digest() -> str:
    """SHA-256 of this file with CRLF folded to LF, so Windows checkouts compare equal."""
    try:
        data = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    except (OSError, NameError):
        return "(unavailable)"
    return hashlib.sha256(data).hexdigest()


def print_summary(ctx: Context, budget: Budget) -> None:
    ctx.say("")
    ctx.say("== Summary ==")
    counts = Counter(r.verdict for r in ctx.results)
    ctx.say(f"requests used: {budget.used} / {budget.cap}")
    ctx.say(
        "verdict counts: "
        + ", ".join(
            f"{v}={counts.get(v, 0)}"
            for v in (
                EXISTS,
                MISSING,
                ERROR,
                SKIPPED,
                HOLDS,
                NOT_HOLD,
                PARTIAL,
                MEASURED,
                INCONCLUSIVE,
            )
        )
    )
    for result in ctx.results:
        suffix = f" -- {result.detail}" if result.detail else ""
        ctx.say(f"[{result.verdict}] {result.section}/{result.check}{suffix}")


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    sleep: Callable[[float], None] | None = None,
    emit: Callable[[str], None] | None = None,
    today: date | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only financial data source spike; configuration is via environment only."
    )
    parser.parse_args(argv)

    environment: Mapping[str, str] = os.environ if env is None else env
    redact = Redactor(environment.get(name, "") for name in SECRET_ENV_VARS)
    sink = emit if emit is not None else (lambda text: print(text, flush=True))

    def say(text: str) -> None:
        sink(redact(text))

    budget = Budget(REQUEST_CAP)
    fetcher = Fetcher(
        transport=transport or urllib_transport,
        budget=budget,
        sleep=sleep or time.sleep,
    )
    ctx = Context(fetcher=fetcher, say=say, env=environment, today=today or date.today())

    say("Fundamentals data source spike")
    say(f"script_version: {SCRIPT_VERSION}")
    say(f"script_sha256_lf: {script_digest()}")
    say(f"run_at_utc: {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    say(f"python: {sys.version.split()[0]}")
    say(f"request cap: {REQUEST_CAP} (GET only, no retries, no files, no database)")
    for name in SECRET_ENV_VARS:
        state = "set (value hidden)" if environment.get(name, "").strip() else "NOT set"
        say(f"env {name} is {state}")
    holdings_given = environment.get(ENV_HOLDINGS, "").strip()
    say(
        f"env {ENV_HOLDINGS} is "
        + ("set" if holdings_given else "NOT set (P-12 uses the sample only)")
    )

    for title, runner in SECTIONS:
        try:
            runner(ctx)
        except BudgetExceededError as exc:
            ctx.record(title, "budget", ERROR, str(exc))
        except Exception as exc:  # one broken section must not hide the others
            ctx.record(title, "unexpected", ERROR, f"{type(exc).__name__}: {short(exc, 120)}")

    print_summary(ctx, budget)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")
    raise SystemExit(main())
