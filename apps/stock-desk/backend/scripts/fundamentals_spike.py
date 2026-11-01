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
  FINMIND_API_TOKEN      optional; without it FinMind runs at the anonymous tier
  ALPHA_VANTAGE_API_KEY  optional; without it the Alpha Vantage check is skipped

Planned requests (hard cap ``REQUEST_CAP`` = 20, enforced in code):

  SEC EDGAR           4  (ticker map 1, companyfacts AAPL + 2 other tickers 3)
                      +1 only if the first ticker map path fails (fallback path)
  TWSE OpenAPI        4  (swagger 1, up to 3 sample datasets)
  TPEx OpenAPI        3  (swagger 1, up to 2 sample datasets)
  FinMind             4  (dataset enum from GitHub 1, user_info 1,
                          cash-flow dataset for one TWSE and one TPEx ticker 2)
  Alpha Vantage       1  (TIME_SERIES_DAILY AAPL, compact)
  ------------------------------------------------------------------
  Normal run         16  worst case 17, cap 20

Throttling: SEC hosts are spaced at least 0.25 s apart (<= 4 req/s, well under
the 10 req/s SEC limit); every other host at least 1.0 s.

Verdict vocabulary printed per check: EXISTS / MISSING / ERROR / SKIPPED.
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

SCRIPT_VERSION = "1"
REQUEST_CAP = 20
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_BODY_BYTES = 64 * 1024 * 1024
SEC_MIN_GAP_SECONDS = 0.25
DEFAULT_MIN_GAP_SECONDS = 1.0
MASK = "***"

ENV_SEC_UA = "SEC_USER_AGENT"
ENV_FINMIND = "FINMIND_API_TOKEN"
ENV_ALPHA = "ALPHA_VANTAGE_API_KEY"
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
SEC_FALLBACK_CIKS = {"AAPL": 320193, "AMZN": 1018724, "INTC": 50863}

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
        ("us-gaap", "CommonStockDividendsPerShareDeclared"),
        ("us-gaap", "CommonStockDividendsPerShareCashPaid"),
    ),
    "SBC": (
        ("us-gaap", "ShareBasedCompensation"),
        ("us-gaap", "AllocatedShareBasedCompensationExpense"),
    ),
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


def urllib_transport(url: str, headers: Mapping[str, str]) -> HttpResult:
    """Real transport: one GET, bounded body size, never raises."""
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
            status = int(response.status)
            encoding = response.headers.get("Content-Encoding", "") or ""
    except urllib.error.HTTPError as exc:
        raw = exc.read(MAX_BODY_BYTES + 1)
        status = int(exc.code)
        encoding = (exc.headers.get("Content-Encoding", "") or "") if exc.headers else ""
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return HttpResult(None, b"", f"{type(exc).__name__}: {exc}")
    if len(raw) > MAX_BODY_BYTES:
        return HttpResult(status, b"", f"body larger than {MAX_BODY_BYTES} bytes, discarded")
    return HttpResult(status, _decode_body(raw, encoding))


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
    )


def analyze_companyfacts(doc: Any, today: date) -> FactsReport | None:
    if not isinstance(doc, dict) or not isinstance(doc.get("facts"), dict):
        return None
    facts: dict[str, Any] = doc["facts"]
    namespaces = {ns: len(tags) for ns, tags in facts.items() if isinstance(tags, dict)}
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


def run_sec(ctx: Context) -> None:
    section_header(ctx, "1. SEC EDGAR")
    user_agent = ctx.env.get(ENV_SEC_UA, "").strip()
    if "@" not in user_agent:
        ctx.say(f"  {ENV_SEC_UA} is not set or lacks a contact email; SEC rejects such requests.")
        ctx.say('  Expected format: "Your Name your@email". Section skipped, no request sent.')
        ctx.record("SEC", "all", SKIPPED, f"{ENV_SEC_UA} missing or malformed")
        return
    headers = {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip",
        "Accept": "application/json",
    }

    mapping: dict[str, int] = {}
    for url in (SEC_TICKER_URL, SEC_TICKER_FALLBACK_URL):
        result, doc, error = fetch_json(ctx, url, headers)
        mapping = parse_ticker_map(doc) if error is None else {}
        if result.status == 200 and mapping:
            ctx.say(
                f"  entries={len(mapping):,} sample={ {t: mapping.get(t) for t in SEC_TICKERS} }"
            )
            ctx.record("SEC", "ticker-map", EXISTS, f"path confirmed: {url}")
            break
        ctx.record("SEC", f"ticker-map {url}", ERROR, describe_http(result))
    else:
        ctx.say("  Both ticker-map paths failed; using built-in CIKs (NOT verified by this run).")
        mapping = dict(SEC_FALLBACK_CIKS)

    for ticker in SEC_TICKERS:
        cik = mapping.get(ticker)
        if cik is None:
            ctx.record("SEC", f"{ticker}/companyfacts", MISSING, "ticker not in ticker map")
            continue
        url = SEC_FACTS_URL.format(cik=cik)
        result, doc, error = fetch_json(ctx, url, headers)
        if result.status != 200 or error is not None:
            ctx.record("SEC", f"{ticker}/companyfacts", ERROR, describe_http(result))
            continue
        report = analyze_companyfacts(doc, ctx.today)
        if report is None:
            ctx.record("SEC", f"{ticker}/companyfacts", ERROR, "unexpected JSON layout")
            continue
        ctx.record("SEC", f"{ticker}/companyfacts", EXISTS, describe_http(result))
        print_facts_report(ctx, ticker, report, detailed=ticker == SEC_TICKERS[0])


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


# ---------------------------------------------------------------- orchestration

SECTIONS: tuple[tuple[str, Callable[[Context], None]], ...] = (
    ("SEC", run_sec),
    ("TWSE/TPEx", run_twse),
    ("FinMind", run_finmind),
    ("AlphaVantage", run_alpha),
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
        + ", ".join(f"{v}={counts.get(v, 0)}" for v in (EXISTS, MISSING, ERROR, SKIPPED))
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
