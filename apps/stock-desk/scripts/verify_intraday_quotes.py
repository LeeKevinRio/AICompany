"""CEO local intraday-quote verification tool (TWSE MIS vs yfinance vs FinMind).

## Background

CEO approved (2026-10-02) TWSE "basic market info" (MIS, ``getStockInfo.jsp``,
free) as the primary intraday price source. The cloud dev environment blocks
every finance domain, so nothing about MIS has ever been observed for real.
This script is run by the CEO on a machine with open internet access, in three
time windows (pre-open / mid-session / post-close), and produces a report that
is pasted back to Claude so the intraday adapter can be designed from facts
instead of memory.

## How to run (Windows PowerShell)

Run from the ``apps\\stock-desk\\backend`` directory, once per time window
(windows match ``PHASE_WINDOW``). Taipei time, trading days only. A run takes a
few minutes; the window check uses the time the run STARTED:

    cd apps\\stock-desk\\backend
    uv run python ..\\scripts\\verify_intraday_quotes.py --phase pre-open   # 08:30-09:00
    uv run python ..\\scripts\\verify_intraday_quotes.py --phase mid        # 09:00-13:30
    uv run python ..\\scripts\\verify_intraday_quotes.py --phase post       # 14:30 or later

Optional credentials (environment variables only, never written to any file):

    $env:FINMIND_API_TOKEN = "..."          # enables check E (else SKIP)
    $env:ALPHA_VANTAGE_API_KEY = "..."      # only used with --include-alpha-vantage

Useful options (``--help`` lists all):

    --symbols 2330,5483,0050,00631L   defaults (max 10); prefix "otc:" / "tse:" to force a market
    --skip-rate-probe                 skip check B4 (the rate-limit probe)
    --include-alpha-vantage           run check F; this CONSUMES 1 daily AV quota unit
    --output-dir PATH                 default: <repo>/work/research

The report is written to ``work/research/驗證結果-盤中-<date>-<phase>.md`` and the
sanitized raw responses to ``...-<phase>.real.json`` next to it. Paste the
report contents back to Claude.

## Checks

    A   connectivity (MIS, TWSE, Yahoo, FinMind)
    B1  does MIS need a cookie / session
    B2  MIS response structure (required fields)
    B3  MIS update frequency and delay (bounded polling)
    B4  MIS rate-limit probe (HARD CAP: 100 requests, >= 2 s apart, stops at the
        first non-200 / redirect / empty / verification page / bad rtcode)
    B5  post-close reconciliation vs TWSE STOCK_DAY (post phase only)
    B6  behaviour when the last price ``z`` is "-" (no trade yet)
    C   yfinance intraday delay (per symbol)
    D   cross-check MIS vs yfinance last price
    E   FinMind real-time dataset permission probe (SKIP without token)
    F   Alpha Vantage (opt-in only)

Verdicts: PASS / FAIL / UNREACHABLE (connection layer failed) / SKIP (not run
or not observable in this phase). Nothing is interpolated or back-filled: a
missing value stays missing and is reported as such.

## Safety

- Credentials come from environment variables only; the report only says
  whether they were set ("有" / "無").
- Tokens, API keys and cookie values are scrubbed before anything is written.
- Uses only the standard library and httpx; no ``app.*`` imports, so it never
  touches product code or the product database.
- MIS clients never follow redirects (a hop would be an extra request that
  bypasses the 2 s spacing); any 3xx from MIS stops all further MIS requests.
- Once any MIS request hits a blocking-type failure, every later MIS request is
  skipped (``Context.mis_blocked``).
- Ctrl-C still writes the report with whatever was collected, marked as interrupted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from statistics import median
from typing import Any

import httpx

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

#: Taiwan has no DST, so a fixed offset is exact and avoids the ``tzdata``
#: dependency that ``zoneinfo`` needs on Windows.
TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")

MIS_HOST = "mis.twse.com.tw"
MIS_HOME_URL = "https://mis.twse.com.tw/stock/index.jsp"
MIS_API_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
TWSE_ROOT_URL = "https://www.twse.com.tw/"
TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
YAHOO_ROOT_URL = "https://query1.finance.yahoo.com/"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
FINMIND_ROOT_URL = "https://api.finmindtrade.com/"
FINMIND_SNAPSHOT_URL = "https://api.finmindtrade.com/api/v4/taiwan_stock_tick_snapshot"
FINMIND_DATA_URL = "https://api.finmindtrade.com/api/v4/data"
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"

FINMIND_TOKEN_ENV_VAR = "FINMIND_API_TOKEN"
ALPHA_VANTAGE_KEY_ENV_VAR = "ALPHA_VANTAGE_API_KEY"

#: Hard limits of the rate-limit probe (check B4). Not overridable upward.
MAX_RATE_PROBE_REQUESTS = 100
MIN_REQUEST_INTERVAL_S = 2.0
DEFAULT_RATE_PROBE_REQUESTS = 30
#: B5 / C send one request per symbol (spaced by MIN_REQUEST_INTERVAL_S).
MAX_SYMBOLS = 10

DEFAULT_SYMBOLS = "2330,5483,0050,00631L"
#: Known markets for the default symbols; unknown codes default to "tse".
DEFAULT_MARKETS: dict[str, str] = {"2330": "tse", "5483": "otc", "0050": "tse", "00631L": "tse"}

MIS_REQUIRED_KEYS: tuple[str, ...] = (
    "c",
    "n",
    "z",
    "y",
    "o",
    "h",
    "l",
    "v",
    "t",
    "d",
    "tlong",
    "ex",
)

#: Plain-language judgement thresholds (summary only, never alter verdicts).
MIS_DELAY_OK_S = 30.0
MIS_DELAY_SLOW_S = 120.0
YFINANCE_DELAY_OK_MIN = 2.0
CROSS_CHECK_TOLERANCE_PCT = Decimal("0.5")

PHASES: tuple[str, ...] = ("pre-open", "mid", "post")
PHASE_LABEL = {"pre-open": "盤前", "mid": "盤中", "post": "盤後"}
#: Suggested Taipei wall-clock windows (start, end) per phase; warn only.
PHASE_WINDOW = {
    "pre-open": ((8, 30), (9, 0)),
    "mid": ((9, 0), (13, 30)),
    "post": ((14, 30), (23, 59)),
}

_SENSITIVE_KEYS = frozenset(
    {"token", "apikey", "api_key", "authorization", "cookie", "set-cookie", "password"}
)
_DROPPED_RESPONSE_HEADERS = frozenset({"set-cookie", "authorization", "proxy-authorization"})
_MIN_SECRET_LEN = 6
_REDACTED = "[REDACTED]"
_TEXT_BODY_LIMIT = 2000

_USER_AGENT = "Mozilla/5.0 (verify_intraday_quotes; read-only diagnostic)"
_BROWSER_HEADERS = {"User-Agent": _USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"}
_MIS_HEADERS = {**_BROWSER_HEADERS, "Referer": MIS_HOME_URL}


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNREACHABLE = "UNREACHABLE"
    SKIP = "SKIP"


# --------------------------------------------------------------------------
# Redaction (tokens, API keys, cookies never reach disk)
# --------------------------------------------------------------------------


class Redactor:
    """Scrubs known secret values and sensitive keys from everything written."""

    def __init__(self) -> None:
        self._secrets: set[str] = set()

    def add_secret(self, value: str | None) -> None:
        if value and len(value) >= _MIN_SECRET_LEN:
            self._secrets.add(value)

    def add_cookie_header(self, set_cookie_value: str) -> None:
        """Register the value part of one ``Set-Cookie`` header as a secret."""
        first = set_cookie_value.split(";", 1)[0]
        if "=" in first:
            self.add_secret(first.split("=", 1)[1].strip())

    def scrub_text(self, text: str) -> str:
        out = text
        for secret in sorted(self._secrets, key=len, reverse=True):
            out = out.replace(secret, _REDACTED)
        out = re.sub(
            r"(?i)\b(token|apikey|api_key|authorization)=([^&\s\"']+)",
            rf"\1={_REDACTED}",
            out,
        )
        return re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", f"Bearer {_REDACTED}", out)

    def scrub_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.scrub_text(obj)
        if isinstance(obj, list):
            return [self.scrub_obj(item) for item in obj]
        if isinstance(obj, dict):
            return {
                key: (
                    _REDACTED
                    if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS
                    else self.scrub_obj(value)
                )
                for key, value in obj.items()
            }
        return obj


# --------------------------------------------------------------------------
# Symbols
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Symbol:
    code: str
    market: str  # "tse" (listed) or "otc" (TPEx)
    market_guessed: bool = False

    @property
    def mis_channel(self) -> str:
        return f"{self.market}_{self.code}.tw"

    @property
    def yahoo_symbol(self) -> str:
        return f"{self.code}.TW" if self.market == "tse" else f"{self.code}.TWO"


_CODE_RE = re.compile(r"^[0-9A-Z]{2,8}$")


def parse_symbols(raw: str) -> list[Symbol]:
    """Parse ``2330,otc:5483,...``; reject anything that is not a plain code."""
    symbols: list[Symbol] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        market: str | None = None
        if ":" in item:
            prefix, item = item.split(":", 1)
            market = prefix.strip().lower()
            if market not in ("tse", "otc"):
                raise ValueError(f"market prefix must be tse or otc, got {prefix!r}")
        code = item.strip().upper()
        if not _CODE_RE.match(code):
            raise ValueError(f"invalid symbol code: {item!r}")
        guessed = False
        if market is None:
            if code in DEFAULT_MARKETS:
                market = DEFAULT_MARKETS[code]
            else:
                market, guessed = "tse", True
        symbols.append(Symbol(code=code, market=market, market_guessed=guessed))
    if not symbols:
        raise ValueError("no symbols given")
    return symbols


# --------------------------------------------------------------------------
# MIS payload parsing
# --------------------------------------------------------------------------


def parse_decimal(raw: object) -> Decimal | None:
    """Parse a MIS numeric string; ``"-"``, empty and garbage become ``None``."""
    if not isinstance(raw, str):
        return None
    text = raw.strip().replace(",", "")
    if text in ("", "-", "--"):
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _parse_int(raw: object) -> int | None:
    value = parse_decimal(raw)
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class MisQuote:
    code: str
    name: str
    market: str
    #: Last trade price from ``z``. ``None`` when ``z`` is "-" -- NEVER
    #: replaced by yesterday's close, the open or a bid/ask price.
    last: Decimal | None
    last_is_dash: bool
    prev_close: Decimal | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    volume_lots: int | None
    trade_time: str
    trade_date: str
    trade_epoch_ms: int | None
    best_bid_raw: str
    best_ask_raw: str
    missing_keys: tuple[str, ...]
    #: The ``z`` field exactly as received (never masked); "<缺欄位>" if absent.
    last_raw: str = ""


@dataclass(frozen=True)
class MisParse:
    rtcode: str | None
    quotes: tuple[MisQuote, ...]
    server_time: datetime | None
    problems: tuple[str, ...]


def parse_server_time(query_time: object) -> datetime | None:
    if not isinstance(query_time, dict):
        return None
    sys_date, sys_time = query_time.get("sysDate"), query_time.get("sysTime")
    if not isinstance(sys_date, str) or not isinstance(sys_time, str):
        return None
    try:
        return datetime.strptime(f"{sys_date} {sys_time}", "%Y%m%d %H:%M:%S").replace(tzinfo=TAIPEI)
    except ValueError:
        return None


def parse_mis_payload(data: object) -> MisParse:
    """Validate and parse one ``getStockInfo.jsp`` JSON payload."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return MisParse(None, (), None, ("回應最外層不是 JSON 物件",))
    rtcode = data.get("rtcode")
    rtcode_s = rtcode if isinstance(rtcode, str) else None
    if rtcode_s != "0000":
        problems.append(f"rtcode={rtcode!r}（預期 '0000'）")
    msg_array = data.get("msgArray")
    if not isinstance(msg_array, list):
        problems.append("缺少 msgArray 或型別不是陣列")
        return MisParse(rtcode_s, (), parse_server_time(data.get("queryTime")), tuple(problems))
    quotes: list[MisQuote] = []
    for item in msg_array:
        if not isinstance(item, dict):
            problems.append("msgArray 內有非物件元素")
            continue
        missing = tuple(key for key in MIS_REQUIRED_KEYS if key not in item)
        z_raw = item.get("z")
        quotes.append(
            MisQuote(
                code=str(item.get("c", "")),
                name=str(item.get("n", "")),
                market=str(item.get("ex", "")),
                last=parse_decimal(z_raw),
                last_is_dash=isinstance(z_raw, str) and z_raw.strip() == "-",
                prev_close=parse_decimal(item.get("y")),
                open=parse_decimal(item.get("o")),
                high=parse_decimal(item.get("h")),
                low=parse_decimal(item.get("l")),
                volume_lots=_parse_int(item.get("v")),
                trade_time=str(item.get("t", "")),
                trade_date=str(item.get("d", "")),
                trade_epoch_ms=_parse_int(item.get("tlong")),
                best_bid_raw=str(item.get("b", "")),
                best_ask_raw=str(item.get("a", "")),
                missing_keys=missing,
                last_raw=str(z_raw) if "z" in item else "<缺欄位>",
            )
        )
    return MisParse(
        rtcode_s, tuple(quotes), parse_server_time(data.get("queryTime")), tuple(problems)
    )


def mis_delay_seconds(quote: MisQuote, reference_now: datetime) -> float | None:
    """Seconds between ``reference_now`` and the quote's last trade time."""
    if quote.trade_epoch_ms is None:
        return None
    trade_at = datetime.fromtimestamp(quote.trade_epoch_ms / 1000, tz=UTC)
    return (reference_now - trade_at).total_seconds()


# --------------------------------------------------------------------------
# HTTP layer with recording
# --------------------------------------------------------------------------


@dataclass
class HttpOutcome:
    status: int | None
    text: str
    data: Any | None
    error: str | None
    unreachable: bool
    elapsed_s: float
    #: ``Location`` header of a 3xx response (redirects are never followed for MIS).
    location: str | None = None


@dataclass
class Recorder:
    redactor: Redactor
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(
        self,
        *,
        check: str,
        url: str,
        params: Mapping[str, str] | None,
        request_headers: Mapping[str, str] | None,
        response: httpx.Response | None,
        outcome: HttpOutcome,
        note: str | None = None,
    ) -> None:
        body: Any
        if outcome.data is not None:
            body = self.redactor.scrub_obj(outcome.data)
        else:
            body = self.redactor.scrub_text(outcome.text[:_TEXT_BODY_LIMIT])
        resp_headers: dict[str, str] = {}
        if response is not None:
            resp_headers = {
                k: self.redactor.scrub_text(v)
                for k, v in response.headers.items()
                if k.lower() not in _DROPPED_RESPONSE_HEADERS
            }
        entry: dict[str, Any] = {
            "check": check,
            "url": self.redactor.scrub_text(url),
            "params": self.redactor.scrub_obj(dict(params)) if params else {},
            "request_headers_sent": self.redactor.scrub_obj(dict(request_headers or {})),
            "status": outcome.status,
            "response_headers": resp_headers,
            "elapsed_s": round(outcome.elapsed_s, 3),
            "error": self.redactor.scrub_text(outcome.error) if outcome.error else None,
            "body": body,
        }
        if note:
            entry["note"] = note
        self.entries.append(entry)


@dataclass
class Facts:
    """Machine-readable findings consumed by the plain-language summary."""

    mis_reachable: bool | None = None
    mis_structure_ok: bool | None = None
    mis_needs_cookie: bool | None = None
    mis_cookie_issued: bool | None = None
    mis_delay_s: float | None = None
    mis_delay_symbol: str | None = None
    mis_distinct_updates: dict[str, int] = field(default_factory=dict)
    mis_poll_ok: bool | None = None  # B3 outcome; None = B3 not run
    mis_poll_reason: str = ""
    rate_state: str = "not_run"  # not_run | skipped | skipped_blocked | completed | blocked
    rate_requests: int = 0
    rate_interval: float = 0.0
    rate_reason: str = ""
    dash_observed: bool | None = None
    yf_ok: bool | None = None
    yf_reason: str = ""
    yf_unreachable: bool = False
    yf_delay_min: float | None = None
    cross_state: str = "not_run"  # not_run | all_close | mismatch | none_comparable
    finmind_verdict: Verdict | None = None
    av_verdict: Verdict | None = None


@dataclass
class CheckResult:
    check_id: str
    title: str
    verdict: Verdict
    detail: str
    lines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CliArgs:
    phase: str
    symbols: list[Symbol]
    output_dir: Path
    skip_rate_probe: bool
    rate_probe_requests: int
    rate_probe_interval: float
    poll_count: int
    poll_interval: float
    include_alpha_vantage: bool
    av_symbol: str
    timeout: float


@dataclass
class Context:
    args: CliArgs
    now_fn: Callable[[], datetime]
    sleep_fn: Callable[[float], None]
    transport: httpx.BaseTransport | None
    started_at: datetime
    redactor: Redactor = field(default_factory=Redactor)
    facts: Facts = field(default_factory=Facts)
    recorder: Recorder = field(init=False)
    mis_calls: int = 0
    mis_blocked: bool = False
    mis_block_reason: str = ""
    latest_quotes: dict[str, MisQuote] = field(default_factory=dict)
    yf_quotes: dict[str, YfQuote] = field(default_factory=dict)
    _clients: list[httpx.Client] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.recorder = Recorder(self.redactor)
        self.redactor.add_secret(os.environ.get(FINMIND_TOKEN_ENV_VAR))
        self.redactor.add_secret(os.environ.get(ALPHA_VANTAGE_KEY_ENV_VAR))

    def new_client(self, *, follow_redirects: bool = True) -> httpx.Client:
        client = httpx.Client(
            timeout=self.args.timeout,
            transport=self.transport,
            follow_redirects=follow_redirects,
        )
        self._clients.append(client)
        return client

    def new_mis_client(self) -> httpx.Client:
        """Client for the MIS host: redirects are NOT followed (each hop would be an
        extra request that bypasses the 2 s spacing in ``mis_get``)."""
        return self.new_client(follow_redirects=False)

    def mark_mis_blocked(self, reason: str) -> None:
        if not self.mis_blocked:
            self.mis_blocked = True
            self.mis_block_reason = self.redactor.scrub_text(reason)

    def close(self) -> None:
        for client in self._clients:
            client.close()

    def get(
        self,
        check: str,
        url: str,
        *,
        client: httpx.Client,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        record: bool = True,
    ) -> HttpOutcome:
        started = time.monotonic()
        response: httpx.Response | None = None
        error: str | None = None
        unreachable = False
        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.TransportError as exc:
            error, unreachable = f"{type(exc).__name__}: {exc}", True
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"
        elapsed = time.monotonic() - started
        text, data, status, location = "", None, None, None
        if response is not None:
            status = response.status_code
            location = (response.headers.get("location") or "")[:200] or None
            text = response.text
            for value in response.headers.get_list("set-cookie"):
                self.redactor.add_cookie_header(value)
            for cookie in client.cookies.jar:
                self.redactor.add_secret(cookie.value)
            try:
                data = response.json()
            except ValueError:
                data = None
        outcome = HttpOutcome(status, text, data, error, unreachable, elapsed, location)
        if record:
            self.recorder.add(
                check=check,
                url=url,
                params=params,
                request_headers=headers,
                response=response,
                outcome=outcome,
            )
        return outcome

    def mis_get(
        self,
        check: str,
        url: str,
        *,
        client: httpx.Client,
        params: Mapping[str, str] | None = None,
        gap: float = MIN_REQUEST_INTERVAL_S,
        record: bool = True,
        flag_block: bool = True,
    ) -> HttpOutcome:
        """Every request to the MIS host goes through here: >= 2 s apart.

        Once ``mis_blocked`` is set, no request is sent at all. ``flag_block=False``
        is only for the B1 cookie-less probe, whose failure is the very thing
        being measured and must not stop the session probe that follows.
        """
        if client.follow_redirects:
            raise ValueError("MIS clients must not follow redirects")
        if self.mis_blocked:
            return HttpOutcome(
                None,
                "",
                None,
                f"已因封鎖類失敗停止 MIS 請求，未送出（{self.mis_block_reason}）",
                False,
                0.0,
            )
        if self.mis_calls > 0:
            self.sleep_fn(max(gap, MIN_REQUEST_INTERVAL_S))
        self.mis_calls += 1
        out = self.get(
            check, url, client=client, params=params, headers=_MIS_HEADERS, record=record
        )
        if flag_block:
            reason = classify_block(out) if url == MIS_API_URL else classify_http_block(out)
            if reason is not None:
                self.mark_mis_blocked(f"{check}: {reason}")
        return out

    def mis_params(self) -> dict[str, str]:
        channels = "|".join(s.mis_channel for s in self.args.symbols)
        return {"ex_ch": channels, "json": "1", "delay": "0", "_": str(int(time.time() * 1000))}


# --------------------------------------------------------------------------
# yfinance parsing
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class YfQuote:
    price: Decimal | None
    last_trade_at: datetime | None
    problem: str | None


def parse_yfinance_chart(data: object) -> YfQuote:
    """Extract last price and last trade time from a v8 chart response."""
    try:
        assert isinstance(data, dict)
        chart = data["chart"]
        if chart.get("error"):
            return YfQuote(None, None, f"chart.error={chart['error']!r}")
        result = chart["result"][0]
        meta = result["meta"]
    except (AssertionError, KeyError, IndexError, TypeError, AttributeError):
        return YfQuote(None, None, "回應結構不符（缺 chart.result[0].meta）")
    raw_price = meta.get("regularMarketPrice")
    price = Decimal(str(raw_price)) if isinstance(raw_price, int | float) else None
    ts: int | None = meta.get("regularMarketTime")
    if not isinstance(ts, int):
        ts = None
        stamps = result.get("timestamp") or []
        closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        for stamp, close in zip(reversed(stamps), reversed(closes), strict=False):
            if close is not None and isinstance(stamp, int):
                ts = stamp
                break
    when = datetime.fromtimestamp(ts, tz=UTC) if ts is not None else None
    problem = None if price is not None and when is not None else "缺少 price 或時間戳"
    return YfQuote(price, when, problem)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def _fmt_secs(value: float | None) -> str:
    return "無法計算" if value is None else f"{value:.0f} 秒"


def exception_result(ctx: Context, check_id: str, title: str, exc: BaseException) -> CheckResult:
    """An unexpected exception becomes a FAIL that names the type and message."""
    message = ctx.redactor.scrub_text(str(exc))
    return CheckResult(
        check_id, title, Verdict.FAIL, f"未預期的例外 {type(exc).__name__}: {message}"
    )


def check_a(ctx: Context) -> list[CheckResult]:
    targets = (
        ("A.mis", "證交所盤中報價 (MIS)", MIS_HOME_URL),
        ("A.twse", "證交所官網", TWSE_ROOT_URL),
        ("A.yahoo", "Yahoo Finance", YAHOO_ROOT_URL),
        ("A.finmind", "FinMind", FINMIND_ROOT_URL),
    )
    plain = ctx.new_client()
    mis_client = ctx.new_mis_client()
    results: list[CheckResult] = []
    for check_id, title, url in targets:
        try:
            results.append(_check_a_one(ctx, check_id, title, url, plain, mis_client))
        except Exception as exc:  # noqa: BLE001 - reported as FAIL, never swallowed
            results.append(exception_result(ctx, check_id, title, exc))
    return results


def _check_a_one(
    ctx: Context,
    check_id: str,
    title: str,
    url: str,
    plain: httpx.Client,
    mis_client: httpx.Client,
) -> CheckResult:
    if check_id == "A.mis":
        out = ctx.mis_get(check_id, url, client=mis_client)
    else:
        out = ctx.get(check_id, url, client=plain, headers=_BROWSER_HEADERS)
    if out.unreachable or out.status is None:
        if check_id == "A.mis":
            ctx.facts.mis_reachable = False
        return CheckResult(check_id, title, Verdict.UNREACHABLE, f"連不上：{out.error}")
    if check_id == "A.mis":
        ctx.facts.mis_reachable = True
    if out.status >= 400:
        return CheckResult(
            check_id,
            title,
            Verdict.FAIL,
            f"伺服器有回應但狀態碼為 HTTP {out.status}（{out.elapsed_s:.2f} 秒）",
        )
    return CheckResult(
        check_id, title, Verdict.PASS, f"連得上（HTTP {out.status}，{out.elapsed_s:.2f} 秒）"
    )


def _mis_valid(out: HttpOutcome) -> MisParse | None:
    if out.status != 200 or out.data is None:
        return None
    parsed = parse_mis_payload(out.data)
    return parsed if parsed.quotes and not parsed.problems else None


def check_b1(ctx: Context) -> tuple[CheckResult, httpx.Client | None]:
    """Does MIS need a cookie? Returns the session client to reuse."""
    if ctx.facts.mis_reachable is False:
        return CheckResult("B1", "MIS 是否需要 cookie", Verdict.UNREACHABLE, "A 已連不上"), None
    if ctx.mis_blocked:
        return (
            CheckResult(
                "B1",
                "MIS 是否需要 cookie",
                Verdict.SKIP,
                f"A 已遇到封鎖類失敗（{ctx.mis_block_reason}），不再送出 MIS 請求",
            ),
            None,
        )
    params = ctx.mis_params()
    # flag_block=False: a failure without a cookie is the measurement, not a block.
    bare = ctx.mis_get(
        "B1.no-cookie", MIS_API_URL, client=ctx.new_mis_client(), params=params, flag_block=False
    )
    session = ctx.new_mis_client()
    home = ctx.mis_get("B1.home", MIS_HOME_URL, client=session)
    cookie_issued = len(list(session.cookies.jar)) > 0
    ctx.facts.mis_cookie_issued = cookie_issued
    with_cookie = ctx.mis_get("B1.with-session", MIS_API_URL, client=session, params=params)
    ok_bare, ok_session = _mis_valid(bare) is not None, _mis_valid(with_cookie) is not None
    lines = [
        f"- 不帶任何 cookie 直接查：{'成功' if ok_bare else '失敗'}"
        f"（HTTP {bare.status}，{bare.error or '無連線錯誤'}）",
        f"- 先開 index.jsp：HTTP {home.status}；是否取得 cookie：{'有' if cookie_issued else '無'}",
        f"- 帶 session 再查：{'成功' if ok_session else '失敗'}"
        f"（HTTP {with_cookie.status}，{with_cookie.error or '無連線錯誤'}）",
    ]
    if bare.unreachable and (with_cookie.unreachable or home.unreachable):
        return CheckResult(
            "B1", "MIS 是否需要 cookie", Verdict.UNREACHABLE, "連線失敗", lines
        ), None
    if not ok_bare and not ok_session:
        ctx.facts.mis_structure_ok = False
        return CheckResult(
            "B1", "MIS 是否需要 cookie", Verdict.FAIL, "有無 cookie 都拿不到有效報價", lines
        ), session
    ctx.facts.mis_needs_cookie = not ok_bare
    detail = (
        "需要先開首頁取得 cookie（腳本其後都帶 session）"
        if not ok_bare
        else "不需要 cookie，直接查即可"
    )
    return CheckResult("B1", "MIS 是否需要 cookie", Verdict.PASS, detail, lines), session


def _fetch_mis(ctx: Context, check: str, session: httpx.Client, gap: float) -> HttpOutcome:
    return ctx.mis_get(check, MIS_API_URL, client=session, params=ctx.mis_params(), gap=gap)


def check_b2(ctx: Context, session: httpx.Client | None) -> CheckResult:
    title = "MIS 回應結構"
    if session is None or ctx.facts.mis_structure_ok is False or ctx.mis_blocked:
        return CheckResult("B2", title, Verdict.SKIP, "B1 未通過或 MIS 已被擋，不再繼續打 MIS")
    out = _fetch_mis(ctx, "B2", session, MIN_REQUEST_INTERVAL_S)
    if out.unreachable:
        ctx.facts.mis_structure_ok = False
        return CheckResult("B2", title, Verdict.UNREACHABLE, f"連不上：{out.error}")
    parsed = parse_mis_payload(out.data) if out.data is not None else None
    if out.status != 200 or parsed is None:
        ctx.facts.mis_structure_ok = False
        return CheckResult("B2", title, Verdict.FAIL, f"HTTP {out.status}，且回應不是有效 JSON")
    problems = list(parsed.problems)
    wanted = {s.code for s in ctx.args.symbols}
    got = {q.code for q in parsed.quotes}
    if wanted - got:
        problems.append(f"查無標的：{', '.join(sorted(wanted - got))}")
    lines: list[str] = []
    for quote in parsed.quotes:
        ctx.latest_quotes[quote.code] = quote
        if quote.missing_keys:
            problems.append(f"{quote.code} 缺欄位：{','.join(quote.missing_keys)}")
        lines.append(
            f"- {quote.code} {quote.name}（{quote.market}）："
            f"z={quote.last_raw!r}，"
            f"昨收 y={quote.prev_close}，成交時間 t={quote.trade_time}，量 v={quote.volume_lots}"
        )
    lines.append(f"- 伺服器時間 queryTime：{parsed.server_time}")
    ctx.facts.mis_structure_ok = not problems
    if problems:
        return CheckResult("B2", title, Verdict.FAIL, "；".join(problems), lines)
    return CheckResult("B2", title, Verdict.PASS, f"{len(parsed.quotes)} 檔欄位齊全", lines)


def check_b3(ctx: Context, session: httpx.Client | None) -> CheckResult:
    title = "MIS 更新頻率與延遲"
    if session is None or not ctx.facts.mis_structure_ok or ctx.mis_blocked:
        return CheckResult("B3", title, Verdict.SKIP, "B2 未通過或 MIS 已被擋，不再繼續打 MIS")
    count, gap = ctx.args.poll_count, ctx.args.poll_interval
    delays: dict[str, list[float]] = {s.code: [] for s in ctx.args.symbols}
    stamps: dict[str, list[int]] = {s.code: [] for s in ctx.args.symbols}
    polls_ok = 0
    for i in range(count):
        out = _fetch_mis(ctx, f"B3.poll{i + 1}", session, gap)
        parsed = _mis_valid(out)
        if parsed is None:
            reason = classify_block(out) or "回應驗證失敗"
            # A failed poll is a blocking-type failure: B4 and later MIS requests must not run.
            ctx.mark_mis_blocked(f"B3: {reason}")
            ctx.facts.mis_poll_ok = False
            ctx.facts.mis_poll_reason = f"第 {i + 1} 次輪詢 {reason}"
            return CheckResult(
                "B3",
                title,
                Verdict.FAIL,
                f"第 {i + 1} 次輪詢拿不到有效回應（{reason}），提前停止；後續 MIS 請求一律略過",
            )
        polls_ok += 1
        reference = parsed.server_time or ctx.now_fn()
        for quote in parsed.quotes:
            ctx.latest_quotes[quote.code] = quote
            delay = mis_delay_seconds(quote, reference)
            if delay is not None and quote.code in delays:
                delays[quote.code].append(delay)
            if quote.trade_epoch_ms is not None and quote.code in stamps:
                stamps[quote.code].append(quote.trade_epoch_ms)
    ctx.facts.mis_poll_ok = True
    lines = [f"- 共輪詢 {polls_ok} 次，間隔 {gap:g} 秒（時間基準以 MIS 伺服器時間為主）"]
    medians: dict[str, float] = {}
    for code, values in delays.items():
        distinct = len(set(stamps[code]))
        ctx.facts.mis_distinct_updates[code] = distinct
        if values:
            medians[code] = float(median(values))
        lines.append(
            f"- {code}：最近一筆成交距今中位數 {_fmt_secs(medians.get(code))}；"
            f"{polls_ok} 次查詢中看到 {distinct} 種不同成交時間"
        )
    if medians:
        best = min(medians, key=lambda c: medians[c])
        ctx.facts.mis_delay_s = medians[best]
        ctx.facts.mis_delay_symbol = best
    lines.append(
        "- 註：「距今」是最近一筆成交的時間差；冷門標的久未成交時數字會偏大，不等於資料源延遲。"
    )
    return CheckResult(
        "B3",
        title,
        Verdict.PASS,
        f"最活躍標的 {ctx.facts.mis_delay_symbol} 延遲中位數 {_fmt_secs(ctx.facts.mis_delay_s)}",
        lines,
    )


def check_b6(ctx: Context) -> CheckResult:
    title = 'MIS z="-" 行為'
    if not ctx.latest_quotes:
        return CheckResult("B6", title, Verdict.SKIP, "沒有取得任何報價")
    dashed = [q for q in ctx.latest_quotes.values() if q.last_is_dash]
    ctx.facts.dash_observed = bool(dashed)
    if not dashed:
        return CheckResult(
            "B6",
            title,
            Verdict.SKIP,
            '本時段所有標的都有成交價，未觀察到 z="-"（請以盤前那次為準）',
        )
    lines = [
        f"- {q.code}：z='-'，開盤 o={q.open}，昨收 y={q.prev_close}，"
        f"委買 b={q.best_bid_raw!r}，委賣 a={q.best_ask_raw!r}，量 v={q.volume_lots}"
        for q in dashed
    ]
    lines.append("- 腳本處理方式：z='-' 解析為「無成交價」，不以昨收、開盤或委買賣價頂替。")
    return CheckResult(
        "B6", title, Verdict.PASS, f"{len(dashed)} 檔 z='-'，已如實記為無成交價", lines
    )


def _twse_roc_date(d: date) -> str:
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def check_b5(ctx: Context) -> CheckResult:
    title = "MIS 收盤對帳 (vs TWSE STOCK_DAY)"
    if ctx.args.phase != "post":
        return CheckResult("B5", title, Verdict.SKIP, "只在 --phase post 執行")
    if not ctx.latest_quotes:
        return CheckResult("B5", title, Verdict.SKIP, "沒有 MIS 報價可對帳")
    today = ctx.started_at.date()
    client = ctx.new_client()
    lines: list[str] = []
    compared = mismatched = requests_made = 0
    for symbol in ctx.args.symbols:
        quote = ctx.latest_quotes.get(symbol.code)
        if symbol.market != "tse":
            lines.append(f"- {symbol.code}（上櫃）：本腳本無對應官方日線來源，未對帳（見 D）")
            continue
        if quote is None or quote.last is None:
            lines.append(f"- {symbol.code}：MIS 無成交價（z='-'），無法對帳")
            continue
        if requests_made > 0:
            ctx.sleep_fn(MIN_REQUEST_INTERVAL_S)
        requests_made += 1
        out = ctx.get(
            f"B5.{symbol.code}",
            TWSE_STOCK_DAY_URL,
            client=client,
            params={"response": "json", "date": today.strftime("%Y%m%d"), "stockNo": symbol.code},
            headers=_BROWSER_HEADERS,
        )
        row = _find_stock_day_row(out.data, _twse_roc_date(today))
        if row is None:
            lines.append(f"- {symbol.code}：官方日線尚未出現 {today} 的資料（HTTP {out.status}）")
            continue
        official_close = parse_decimal(row[6])
        official_shares = _parse_int(row[1])
        compared += 1
        close_ok = official_close == quote.last
        if not close_ok:
            mismatched += 1
        volume_note = ""
        if official_shares is not None and quote.volume_lots is not None:
            volume_note = (
                f"；成交量 MIS={quote.volume_lots} 張 vs 官方={official_shares} 股"
                f"（換算 {official_shares / 1000:g} 張）"
            )
        lines.append(
            f"- {symbol.code}：MIS 最後成交價 {quote.last} vs 官方收盤 {official_close} -> "
            f"{'一致' if close_ok else '不一致'}{volume_note}"
        )
    if compared == 0:
        return CheckResult("B5", title, Verdict.SKIP, "沒有可對帳的標的（可能尚未過 14:30）", lines)
    if mismatched:
        return CheckResult("B5", title, Verdict.FAIL, f"{mismatched}/{compared} 檔不一致", lines)
    return CheckResult("B5", title, Verdict.PASS, f"{compared} 檔收盤價與官方一致", lines)


def _find_stock_day_row(data: object, roc_date: str) -> list[str] | None:
    if not isinstance(data, dict) or data.get("stat") != "OK":
        return None
    rows = data.get("data")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, list) and len(row) >= 7 and str(row[0]).strip() == roc_date:
            return [str(cell) for cell in row]
    return None


def classify_http_block(out: HttpOutcome) -> str | None:
    """Transport / HTTP-level reasons to stop sending MIS requests, else ``None``."""
    if out.error:
        return f"連線錯誤（{out.error}）"
    if out.status is not None and 300 <= out.status < 400:
        target = f" -> {out.location}" if out.location else ""
        return f"HTTP {out.status} 重導向{target}（不跟隨，視為被導向驗證頁/擋頁）"
    if out.status != 200:
        return f"HTTP {out.status}"
    if not out.text.strip():
        return "回應為空"
    return None


def classify_block(out: HttpOutcome) -> str | None:
    """Return why a MIS API response must stop all MIS requests, else ``None``."""
    http_reason = classify_http_block(out)
    if http_reason is not None:
        return http_reason
    if out.data is None:
        return "回應不是 JSON（疑似驗證頁或擋頁）"
    parsed = parse_mis_payload(out.data)
    if parsed.problems:
        return f"回應內容異常（{'；'.join(parsed.problems)}）"
    if not parsed.quotes:
        return "msgArray 為空"
    return None


def check_b4(ctx: Context, session: httpx.Client | None) -> CheckResult:
    title = "MIS 限流探測"
    if ctx.args.skip_rate_probe:
        ctx.facts.rate_state = "skipped"
        return CheckResult("B4", title, Verdict.SKIP, "已用 --skip-rate-probe 略過")
    if ctx.mis_blocked:
        ctx.facts.rate_state = "skipped_blocked"
        return CheckResult(
            "B4",
            title,
            Verdict.SKIP,
            f"先前的 MIS 請求已遇到封鎖類失敗（{ctx.mis_block_reason}），不做限流探測、不送請求",
        )
    if session is None or not ctx.facts.mis_structure_ok:
        return CheckResult("B4", title, Verdict.SKIP, "B2 未通過，不做限流探測")
    limit = min(ctx.args.rate_probe_requests, MAX_RATE_PROBE_REQUESTS)
    gap = max(ctx.args.rate_probe_interval, MIN_REQUEST_INTERVAL_S)
    ctx.facts.rate_interval = gap
    log: list[dict[str, Any]] = []
    stop_reason: str | None = None
    made = 0
    # Appended before the loop so an interrupted probe still leaves its request log.
    ctx.recorder.entries.append({"check": "B4.log", "requests": log})
    for i in range(limit):
        out = ctx.mis_get(
            "B4", MIS_API_URL, client=session, params=ctx.mis_params(), gap=gap, record=False
        )
        made += 1
        reason = classify_block(out)
        log.append({"n": i + 1, "status": out.status, "bytes": len(out.text), "stop": reason})
        if reason is not None:
            stop_reason = reason
            ctx.recorder.add(
                check="B4.stop",
                url=MIS_API_URL,
                params=None,
                request_headers=_MIS_HEADERS,
                response=None,
                outcome=out,
                note=f"rate probe stopped at request {made}: {reason}",
            )
            break
    ctx.facts.rate_requests = made
    if stop_reason is not None:
        ctx.facts.rate_state = "blocked"
        ctx.facts.rate_reason = ctx.redactor.scrub_text(stop_reason)
        return CheckResult(
            "B4",
            title,
            Verdict.FAIL,
            f"連續查詢到第 {made} 次（間隔 {gap:g} 秒）遇到異常：{stop_reason}，已立即停止",
            ["- 建議先等 10 分鐘以上再重跑，並考慮 --skip-rate-probe。"],
        )
    ctx.facts.rate_state = "completed"
    return CheckResult(
        "B4",
        title,
        Verdict.PASS,
        f"連續 {made} 次、間隔 {gap:g} 秒，均為正常 200 回應，未被限流",
        ["- 這只代表「該頻率沒被擋」，不是官方保證的額度。"],
    )


def check_c(ctx: Context) -> CheckResult:
    title = "yfinance 個股盤中延遲"
    client = ctx.new_client()
    lines: list[str] = []
    delays: list[float] = []
    problems: list[str] = []
    for i, symbol in enumerate(ctx.args.symbols):
        if i > 0:
            ctx.sleep_fn(MIN_REQUEST_INTERVAL_S)
        out = ctx.get(
            f"C.{symbol.yahoo_symbol}",
            YAHOO_CHART_URL.format(symbol=symbol.yahoo_symbol),
            client=client,
            params={"interval": "1m", "range": "1d"},
            headers=_BROWSER_HEADERS,
        )
        if out.unreachable:
            ctx.facts.yf_unreachable = True
            return CheckResult("C", title, Verdict.UNREACHABLE, f"連不上：{out.error}", lines)
        if out.status != 200:
            problems.append(f"{symbol.yahoo_symbol}: HTTP {out.status}")
            continue
        quote = parse_yfinance_chart(out.data)
        if quote.problem or quote.last_trade_at is None:
            problems.append(f"{symbol.yahoo_symbol}: {quote.problem}")
            continue
        ctx.yf_quotes[symbol.code] = quote
        delay_min = (ctx.now_fn() - quote.last_trade_at).total_seconds() / 60
        delays.append(delay_min)
        local = quote.last_trade_at.astimezone(TAIPEI).strftime("%H:%M:%S")
        lines.append(
            f"- {symbol.yahoo_symbol}：價格 {quote.price}，最後時間 {local}，"
            f"距今 {delay_min:.1f} 分鐘"
        )
    if delays:
        ctx.facts.yf_delay_min = float(median(delays))
    ctx.facts.yf_ok = bool(ctx.yf_quotes) and not problems
    ctx.facts.yf_reason = "；".join(problems)
    if problems:
        lines.extend(f"- 異常：{p}" for p in problems)
        return CheckResult("C", title, Verdict.FAIL, "；".join(problems), lines)
    lines.append("- 註：本機時鐘若不準，延遲數字會跟著偏；1 分 K 時間戳為該分鐘起點。")
    return CheckResult(
        "C", title, Verdict.PASS, f"延遲中位數 {ctx.facts.yf_delay_min:.1f} 分鐘", lines
    )


def _fmt_clock(moment: datetime) -> str:
    return moment.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_gap(seconds: float | None) -> str:
    if seconds is None:
        return "無法計算"
    return f"{seconds:.0f} 秒" if seconds < 120 else f"{seconds / 60:.1f} 分鐘"


def _mis_trade_at(quote: MisQuote) -> datetime | None:
    if quote.trade_epoch_ms is None:
        return None
    return datetime.fromtimestamp(quote.trade_epoch_ms / 1000, tz=UTC)


def check_d(ctx: Context) -> CheckResult:
    title = "MIS vs yfinance 交叉比對"
    lines: list[str] = []
    compared = off = 0
    for symbol in ctx.args.symbols:
        mis, yf = ctx.latest_quotes.get(symbol.code), ctx.yf_quotes.get(symbol.code)
        if mis is None or mis.last is None:
            lines.append(f"- {symbol.code}：MIS 無成交價，略過")
            continue
        if yf is None or yf.price is None:
            lines.append(f"- {symbol.code}：yfinance 無價格，略過")
            continue
        compared += 1
        diff_pct = abs(mis.last - yf.price) / mis.last * 100
        close = diff_pct <= CROSS_CHECK_TOLERANCE_PCT
        if not close:
            off += 1
        mis_at = _mis_trade_at(mis)
        mis_time = (
            _fmt_clock(mis_at) if mis_at is not None else f"無 tlong（原始 t={mis.trade_time!r}）"
        )
        yf_time = _fmt_clock(yf.last_trade_at) if yf.last_trade_at is not None else "無法取得"
        gap_s = (
            abs((mis_at - yf.last_trade_at).total_seconds())
            if mis_at is not None and yf.last_trade_at is not None
            else None
        )
        lines.append(
            f"- {symbol.code}：MIS {mis.last}（報價時間 {mis_time}） vs "
            f"yfinance {yf.price}（時間 {yf_time}）；"
            f"價差 {diff_pct:.2f}%（{'在' if close else '超過'}容忍值）、"
            f"時間差 {_fmt_gap(gap_s)}，請以時間差判讀"
        )
    if compared == 0:
        ctx.facts.cross_state = "none_comparable"
        return CheckResult("D", title, Verdict.SKIP, "沒有兩邊都有價格的標的", lines)
    ctx.facts.cross_state = "mismatch" if off else "all_close"
    if off:
        return CheckResult(
            "D", title, Verdict.FAIL, f"{off}/{compared} 檔價差超過容忍值（請對照時間差）", lines
        )
    return CheckResult(
        "D", title, Verdict.PASS, f"{compared} 檔價差在 {CROSS_CHECK_TOLERANCE_PCT}% 內", lines
    )


def check_e(ctx: Context) -> CheckResult:
    title = "FinMind 即時類 dataset 權限"
    token = os.environ.get(FINMIND_TOKEN_ENV_VAR)
    if not token:
        ctx.facts.finmind_verdict = Verdict.SKIP
        return CheckResult("E", title, Verdict.SKIP, f"未設定 {FINMIND_TOKEN_ENV_VAR}（不算失敗）")
    client = ctx.new_client()
    headers = {**_BROWSER_HEADERS, "Authorization": f"Bearer {token}"}
    today = ctx.started_at.date().isoformat()
    code = ctx.args.symbols[0].code
    probes = (
        ("E.snapshot", FINMIND_SNAPSHOT_URL, {"data_id": code}),
        (
            "E.tick",
            FINMIND_DATA_URL,
            {"dataset": "TaiwanStockPriceTick", "data_id": code, "start_date": today},
        ),
    )
    lines: list[str] = []
    verdicts: list[Verdict] = []
    for check_id, url, params in probes:
        out = ctx.get(check_id, url, client=client, params=params, headers=headers)
        verdict, text = _classify_finmind(out)
        verdicts.append(verdict)
        lines.append(f"- {check_id}（{url.rsplit('/', 1)[-1]}）：{verdict.value}，{text}")
    if Verdict.PASS in verdicts:
        final, detail = Verdict.PASS, "至少一個即時類 dataset 可取得資料"
    elif all(v is Verdict.UNREACHABLE for v in verdicts):
        final, detail = Verdict.UNREACHABLE, "連不上 FinMind"
    elif Verdict.FAIL in verdicts:
        final, detail = Verdict.FAIL, "目前方案/權限取不到即時類資料"
    else:
        final, detail = Verdict.SKIP, "有回應但無資料，需盤中重跑"
    ctx.facts.finmind_verdict = final
    return CheckResult("E", title, final, detail, lines)


def _classify_finmind(out: HttpOutcome) -> tuple[Verdict, str]:
    if out.unreachable or out.status is None:
        return Verdict.UNREACHABLE, f"連不上（{out.error}）"
    body = out.data if isinstance(out.data, dict) else {}
    api_status = body.get("status")
    msg = str(body.get("msg", ""))[:120]
    if out.status == 200 and api_status in (200, None) and body:
        rows = body.get("data")
        if isinstance(rows, list | dict) and rows:
            return Verdict.PASS, "有資料"
        return Verdict.SKIP, "權限正常但目前無資料"
    return Verdict.FAIL, f"HTTP {out.status}，api status={api_status}，{msg or '無訊息'}"


def check_f(ctx: Context) -> CheckResult:
    title = "Alpha Vantage（會吃掉 1 次每日額度）"
    if not ctx.args.include_alpha_vantage:
        ctx.facts.av_verdict = Verdict.SKIP
        return CheckResult(
            "F", title, Verdict.SKIP, "預設不執行（會吃掉每日額度），需加 --include-alpha-vantage"
        )
    key = os.environ.get(ALPHA_VANTAGE_KEY_ENV_VAR)
    if not key:
        ctx.facts.av_verdict = Verdict.SKIP
        return CheckResult(
            "F", title, Verdict.SKIP, f"未設定 {ALPHA_VANTAGE_KEY_ENV_VAR}，未發出請求（不算失敗）"
        )
    out = ctx.get(
        "F",
        ALPHA_VANTAGE_URL,
        client=ctx.new_client(),
        params={"function": "GLOBAL_QUOTE", "symbol": ctx.args.av_symbol, "apikey": key},
        headers=_BROWSER_HEADERS,
    )
    if out.unreachable or out.status is None:
        verdict, detail = Verdict.UNREACHABLE, f"連不上：{out.error}"
    else:
        body = out.data if isinstance(out.data, dict) else {}
        quote = body.get("Global Quote")
        if out.status == 200 and isinstance(quote, dict) and quote:
            verdict = Verdict.PASS
            detail = (
                f"{ctx.args.av_symbol} 價格 {quote.get('05. price')}，"
                f"最新交易日 {quote.get('07. latest trading day')}"
            )
        else:
            note = body.get("Note") or body.get("Information") or body.get("Error Message")
            verdict = Verdict.FAIL
            detail = f"HTTP {out.status}，{ctx.redactor.scrub_text(str(note or '無資料'))[:150]}"
    ctx.facts.av_verdict = verdict
    return CheckResult("F", title, verdict, detail)


# --------------------------------------------------------------------------
# Plain-language summary and report
# --------------------------------------------------------------------------


def build_plain_summary(facts: Facts, phase: str) -> list[str]:
    """Non-technical summary lines for the terminal and the report."""
    lines: list[str] = []
    if facts.mis_reachable is False:
        lines.append("證交所盤中報價：連不上（這台電腦無法連到 mis.twse.com.tw）。")
    elif facts.mis_structure_ok is not True:
        lines.append("證交所盤中報價：連得上，但回傳內容不符預期，目前不能直接用。")
    elif phase == "mid" and facts.mis_poll_ok is False:
        lines.append(f"證交所盤中輪詢失敗：{facts.mis_poll_reason or '原因不明'}。")
    elif phase == "mid" and facts.mis_poll_ok is True and facts.mis_delay_s is None:
        lines.append("證交所盤中報價：輪詢成功，但缺少成交時間，無法計算延遲。")
    elif phase == "mid" and facts.mis_delay_s is not None:
        delay = facts.mis_delay_s
        verdict = (
            "可用"
            if delay <= MIS_DELAY_OK_S
            else "可用但略有延遲"
            if delay <= MIS_DELAY_SLOW_S
            else "延遲偏大"
        )
        lines.append(f"證交所盤中報價：{verdict}，延遲約 {delay:.0f} 秒。")
    else:
        lines.append(
            "證交所盤中報價：連線與欄位正常；本時段不判斷延遲，請以『盤中』那次的結果為準。"
        )
    if phase != "mid" and facts.mis_poll_ok is False:
        lines.append(f"  - 輪詢測試失敗：{facts.mis_poll_reason or '原因不明'}。")
    if facts.mis_needs_cookie is not None:
        lines.append(
            "  - 需要先取得 cookie："
            + ("是（腳本已自動處理）。" if facts.mis_needs_cookie else "否。")
        )
    if facts.rate_state == "completed":
        lines.append(
            f"  - 連續查詢測試：{facts.rate_requests} 次、"
            f"每 {facts.rate_interval:g} 秒一次，沒被擋。"
        )
    elif facts.rate_state == "blocked":
        lines.append(
            f"  - 連續查詢測試：做到第 {facts.rate_requests} 次就被擋（{facts.rate_reason}），"
            "已自動停止；正式使用頻率要比這更保守。"
        )
    elif facts.rate_state == "skipped":
        lines.append("  - 連續查詢測試：這次略過。")
    elif facts.rate_state == "skipped_blocked":
        lines.append("  - 連續查詢測試：先前的 MIS 請求已被擋，為免加重負擔，未執行。")
    if facts.dash_observed is True:
        lines.append(
            '  - 尚無成交時成交價顯示為 "-"：已觀察到，系統會顯示「尚無成交價」而非亂補數字。'
        )
    elif facts.dash_observed is False:
        lines.append('  - 尚無成交時的 "-" 行為：本時段沒遇到，請以『盤前』那次為準。')

    if facts.yf_unreachable:
        lines.append("yfinance：連不上。")
    elif facts.yf_ok is None:
        lines.append("yfinance：未取得結果。")
    elif facts.yf_ok is False:
        lines.append(f"yfinance：取不到可用資料（{facts.yf_reason or '原因不明'}）。")
    elif phase == "mid" and facts.yf_delay_min is not None:
        if facts.yf_delay_min > YFINANCE_DELAY_OK_MIN:
            lines.append(f"yfinance：延遲約 {facts.yf_delay_min:.0f} 分鐘，不適合當盤中價。")
        else:
            lines.append(
                f"yfinance：延遲約 {facts.yf_delay_min:.1f} 分鐘，接近即時（仍建議以證交所為主）。"
            )
    else:
        lines.append("yfinance：可連線；本時段不判斷延遲，請以『盤中』那次為準。")

    cross = {
        "all_close": "兩邊價格接近，互相印證。",
        "mismatch": "兩邊價格有差距，請對照報告 D 項的時間差判讀，在釐清前不能混用。",
        "none_comparable": "這次沒有兩邊都有價格可比。",
        "not_run": "未執行。",
    }[facts.cross_state]
    lines.append(f"交叉比對（證交所 vs yfinance）：{cross}")

    finmind = {
        Verdict.PASS: "FinMind 即時資料：目前方案可取得。",
        Verdict.FAIL: "FinMind 即時資料：目前方案取不到。",
        Verdict.UNREACHABLE: "FinMind：連不上。",
        Verdict.SKIP: "FinMind 即時資料：未檢查或無法判斷（沒設 token 不算失敗）。",
        None: "FinMind 即時資料：未檢查。",
    }[facts.finmind_verdict]
    lines.append(finmind)
    if facts.av_verdict is not None and facts.av_verdict is not Verdict.SKIP:
        lines.append(f"Alpha Vantage：{facts.av_verdict.value}（本次已消耗 1 次每日額度）。")
    return lines


def _phase_warning(phase: str, started_at: datetime) -> str | None:
    """Judged on the time the run STARTED, not when it finished."""
    (sh, sm), (eh, em) = PHASE_WINDOW[phase]
    if started_at.weekday() >= 5:
        return "今天是週末，市場休市，這次結果不具代表性。"
    current = (started_at.hour, started_at.minute)
    if not ((sh, sm) <= current <= (eh, em)):
        return (
            f"起跑時的台北時間 {started_at:%H:%M} 不在建議時段 "
            f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d} 內，延遲數字可能不具代表性。"
        )
    return None


def render_report(
    *,
    args: CliArgs,
    started_at: datetime,
    finished_at: datetime,
    results: Sequence[CheckResult],
    summary: Sequence[str],
    credentials: Mapping[str, bool],
    json_name: str,
    interrupted: bool = False,
) -> str:
    day_name = "一二三四五六日"[started_at.weekday()]
    weekday_text = (
        f"是（週{day_name}；未檢查國定假日）"
        if started_at.weekday() < 5
        else f"否（週{day_name}，休市）"
    )
    lines = [
        f"# 盤中報價核實結果（{PHASE_LABEL[args.phase]}，phase={args.phase}）",
        "",
        f"- **起跑時間**：{started_at:%Y-%m-%d %H:%M:%S}",
        f"- **結束時間**：{finished_at:%Y-%m-%d %H:%M:%S}",
        "- **時區**：Asia/Taipei（UTC+8）",
        f"- **起跑當天是否為平日**：{weekday_text}",
        "- **執行工具**：`apps/stock-desk/scripts/verify_intraday_quotes.py`",
        "- **標的**："
        + "、".join(f"{s.code}（{'上市' if s.market == 'tse' else '上櫃'}）" for s in args.symbols),
        "- **憑證**："
        + "；".join(f"{name} {'有' if ok else '無'}設定" for name, ok in credentials.items()),
        f"- **原始回應（已移除 token / cookie）**：`{json_name}`",
    ]
    if interrupted:
        lines += [
            "",
            "> 注意：**中途中斷**（KeyboardInterrupt）。以下只含中斷前已完成的檢查，"
            "未完成的項目標為 SKIP，結論不完整。",
        ]
    warning = _phase_warning(args.phase, started_at)
    if warning:
        lines += ["", f"> 注意：{warning}"]
    guessed = [s.code for s in args.symbols if s.market_guessed]
    if guessed:
        lines += ["", f"> 注意：{', '.join(guessed)} 未指定市場，預設視為上市；上櫃請寫 otc:代號。"]
    if args.include_alpha_vantage:
        lines += [
            "",
            "> 提醒：本次有加 --include-alpha-vantage，會吃掉 1 次 Alpha Vantage 每日額度。",
        ]
    lines += ["", "## 白話摘要", ""]
    lines += [f"- {line}" if not line.startswith("  -") else line for line in summary]
    lines += [
        "",
        "## 檢查結果一覽",
        "",
        "| 項目 | 名稱 | 結果 | 說明 |",
        "| --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(f"| {r.check_id} | {r.title} | **{r.verdict.value}** | {r.detail} |")
    lines += ["", "## 各項細節", ""]
    for r in results:
        if not r.lines:
            continue
        lines += [f"### {r.check_id} {r.title}", "", *r.lines, ""]
    return "\n".join(lines) + "\n"


def terminal_summary(summary: Sequence[str], report_path: Path, json_path: Path) -> str:
    out = ["=" * 60, "盤中報價核實 -- 白話摘要", "=" * 60, *summary, "-" * 60]
    out += [f"完整報告：{report_path}", f"原始回應：{json_path}"]
    out += ["", "請把報告檔內容貼給 Claude。"]
    return "\n".join(out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _bounded_int(low: int, high: int) -> Callable[[str], int]:
    def parse(raw: str) -> int:
        value = int(raw)
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return value

    return parse


def _min_interval(raw: str) -> float:
    value = float(raw)
    if value < MIN_REQUEST_INTERVAL_S:
        raise argparse.ArgumentTypeError(f"must be >= {MIN_REQUEST_INTERVAL_S:g} seconds")
    return value


def _symbols_arg(raw: str) -> list[Symbol]:
    try:
        symbols = parse_symbols(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if len(symbols) > MAX_SYMBOLS:
        raise argparse.ArgumentTypeError(f"at most {MAX_SYMBOLS} symbols, got {len(symbols)}")
    return symbols


def parse_args(argv: Sequence[str] | None) -> CliArgs:
    parser = argparse.ArgumentParser(
        description="Stock Desk 盤中報價核實工具（證交所 MIS / yfinance / FinMind）。",
    )
    parser.add_argument("--phase", required=True, choices=PHASES)
    parser.add_argument("--symbols", type=_symbols_arg, default=parse_symbols(DEFAULT_SYMBOLS))
    parser.add_argument("--output-dir", type=Path, default=_REPO_ROOT / "work" / "research")
    parser.add_argument("--skip-rate-probe", action="store_true")
    parser.add_argument(
        "--rate-probe-requests",
        type=_bounded_int(1, MAX_RATE_PROBE_REQUESTS),
        default=DEFAULT_RATE_PROBE_REQUESTS,
        help=f"1-{MAX_RATE_PROBE_REQUESTS} (hard cap)",
    )
    parser.add_argument(
        "--rate-probe-interval",
        type=_min_interval,
        default=MIN_REQUEST_INTERVAL_S,
        help=f"seconds between probe requests, >= {MIN_REQUEST_INTERVAL_S:g}",
    )
    parser.add_argument("--poll-count", type=_bounded_int(2, 20), default=6)
    parser.add_argument("--poll-interval", type=_min_interval, default=5.0)
    parser.add_argument("--include-alpha-vantage", action="store_true")
    parser.add_argument("--av-symbol", default="TSM")
    parser.add_argument("--timeout", type=float, default=10.0)
    ns = parser.parse_args(argv)
    return CliArgs(
        phase=ns.phase,
        symbols=ns.symbols,
        output_dir=ns.output_dir,
        skip_rate_probe=ns.skip_rate_probe,
        rate_probe_requests=ns.rate_probe_requests,
        rate_probe_interval=ns.rate_probe_interval,
        poll_count=ns.poll_count,
        poll_interval=ns.poll_interval,
        include_alpha_vantage=ns.include_alpha_vantage,
        av_symbol=ns.av_symbol,
        timeout=ns.timeout,
    )


@dataclass(frozen=True)
class RunResult:
    results: tuple[CheckResult, ...]
    summary: tuple[str, ...]
    report: str
    raw_json: str
    report_path: Path
    json_path: Path
    interrupted: bool = False
    facts: Facts = field(default_factory=Facts)


def run(
    args: CliArgs,
    *,
    transport: httpx.BaseTransport | None = None,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> RunResult:
    clock = now_fn or (lambda: datetime.now(TAIPEI))
    started_at = clock().astimezone(TAIPEI)
    ctx = Context(
        args=args,
        now_fn=clock,
        sleep_fn=sleep_fn or time.sleep,
        transport=transport,
        started_at=started_at,
    )
    results: list[CheckResult] = []
    state: dict[str, httpx.Client | None] = {"session": None}

    def step_b1() -> list[CheckResult]:
        b1, state["session"] = check_b1(ctx)
        return [b1]

    steps: list[tuple[str, str, Callable[[], list[CheckResult]]]] = [
        ("A", "連線檢查", lambda: check_a(ctx)),
        ("B1", "MIS 是否需要 cookie", step_b1),
        ("B2", "MIS 回應結構", lambda: [check_b2(ctx, state["session"])]),
        ("B3", "MIS 更新頻率與延遲", lambda: [check_b3(ctx, state["session"])]),
        ("B6", 'MIS z="-" 行為', lambda: [check_b6(ctx)]),
        ("B5", "MIS 收盤對帳 (vs TWSE STOCK_DAY)", lambda: [check_b5(ctx)]),
        ("B4", "MIS 限流探測", lambda: [check_b4(ctx, state["session"])]),
        ("C", "yfinance 個股盤中延遲", lambda: [check_c(ctx)]),
        ("D", "MIS vs yfinance 交叉比對", lambda: [check_d(ctx)]),
        ("E", "FinMind 即時類 dataset 權限", lambda: [check_e(ctx)]),
        ("F", "Alpha Vantage", lambda: [check_f(ctx)]),
    ]
    interrupted = False
    current: tuple[str, str] | None = None
    try:
        for check_id, title, step in steps:
            current = (check_id, title)
            try:
                results.extend(step())
            except Exception as exc:  # noqa: BLE001 - reported as FAIL, never swallowed
                results.append(exception_result(ctx, check_id, title, exc))
            current = None
    except KeyboardInterrupt:
        interrupted = True
        if current is not None:
            results.append(
                CheckResult(current[0], current[1], Verdict.SKIP, "中途中斷，此項未完成")
            )
    finally:
        ctx.close()
    finished_at = clock().astimezone(TAIPEI)
    summary = [ctx.redactor.scrub_text(line) for line in build_plain_summary(ctx.facts, args.phase)]
    if interrupted:
        summary.insert(0, "中途中斷：只完成部分檢查，以下結論不完整。")
    stem = f"驗證結果-盤中-{started_at.date().isoformat()}-{args.phase}"
    report_path = args.output_dir / f"{stem}.md"
    json_path = args.output_dir / f"{stem}.real.json"
    credentials = {
        FINMIND_TOKEN_ENV_VAR: bool(os.environ.get(FINMIND_TOKEN_ENV_VAR)),
        ALPHA_VANTAGE_KEY_ENV_VAR: bool(os.environ.get(ALPHA_VANTAGE_KEY_ENV_VAR)),
        "MIS cookie": bool(ctx.facts.mis_cookie_issued),
    }
    report = ctx.redactor.scrub_text(
        render_report(
            args=args,
            started_at=started_at,
            finished_at=finished_at,
            results=results,
            summary=summary,
            credentials=credentials,
            json_name=json_path.name,
            interrupted=interrupted,
        )
    )
    raw = {
        "tool": "verify_intraday_quotes.py",
        "phase": args.phase,
        "started_at_taipei": started_at.isoformat(),
        "finished_at_taipei": finished_at.isoformat(),
        "interrupted": interrupted,
        "note": "token / cookie values removed before writing",
        "entries": ctx.recorder.entries,
    }
    raw_json = ctx.redactor.scrub_text(json.dumps(raw, ensure_ascii=False, indent=2, default=str))
    return RunResult(
        tuple(results),
        tuple(summary),
        report,
        raw_json,
        report_path,
        json_path,
        interrupted,
        ctx.facts,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    result = run(args, transport=transport, now_fn=now_fn, sleep_fn=sleep_fn)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result.report_path.write_text(result.report, encoding="utf-8")
    result.json_path.write_text(result.raw_json, encoding="utf-8")
    print(terminal_summary(result.summary, result.report_path, result.json_path))
    if result.interrupted:
        return 130
    bad = (Verdict.FAIL, Verdict.UNREACHABLE)
    return 1 if any(r.verdict in bad for r in result.results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
