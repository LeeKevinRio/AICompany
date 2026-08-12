"""TWSE OpenAPI adapter for 除權除息預告表 (upcoming ex-dividend / ex-rights dates).

## Schema confidence -- endpoint and field structure VERIFIED 2026-08-12

The endpoint this module used to guess at (``TWT49U``, "除權除息計算結果表")
does not exist: it is absent from TWSE OpenAPI's published Swagger catalogue,
and a live probe of ``GET https://openapi.twse.com.tw/v1/exchangeReport/TWT49U``
returns an HTML document (body starts with ``<!``), not JSON -- a dead end,
confirmed by the CEO's own machine on 2026-08-12. That earlier guess is
retired; nothing in this module calls that path anymore.

The Swagger catalogue lists exactly two dividend-related datasets. This
adapter uses::

    GET https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL

-- 上市股票除權除息預告表 ("upcoming ex-dividend/ex-rights announcement
table"). The other candidate, ``/v1/opendata/t187ap45_L`` (上市公司股利分派
情形), was evaluated and **excluded**: it reports a company's board-level
distribution resolution, not a per-security ex-date -- there is no trading
date in that dataset to key a :class:`~app.dividends.models.DividendEvent` on,
so it cannot serve this module's purpose no matter how its columns are read.

The CEO's real fetch of ``TWT48U_ALL`` (2026-08-12) confirmed the row shape
below end to end. A representative pair of real rows::

    [
      {
        "Date": "1150814", "Code": "00401A", "Name": "...",
        "Exdividend": "息", "StockDividendRatio": "",
        "SubscriptionRatio": "", "SubscriptionPricePerShare": "",
        "CashDividend": "", "SharesOffered": "", "SharesEmpOwner": "",
        "SharesholderOwner": "", "StockHoldingRatio": ""
      },
      {
        "Date": "1150818", "Code": "00690", "Name": "...",
        "Exdividend": "息", "StockDividendRatio": "",
        "SubscriptionRatio": "", "SubscriptionPricePerShare": "",
        "CashDividend": "2.190000", "SharesOffered": "", "SharesEmpOwner": "",
        "SharesholderOwner": "", "StockHoldingRatio": ""
      }
    ]

The **field structure** (key names, both the sparse-string convention and
which columns exist) is verified against that live payload. ``Name`` values
in this docstring and in ``tests/fixtures/`` are treated as synthetic
placeholders -- the CEO's own capture noted the first sample's ``Name`` might
not exactly match ``Code`` 00401A, so nothing here or in the tests depends on
``Name`` being accurate; it is not parsed at all (see "Columns not consumed"
below).

## Only five of the eleven columns are read

``Date`` / ``Code`` / ``Exdividend`` / ``CashDividend`` / ``StockDividendRatio``
are what this adapter needs. ``Name`` and the five remaining columns
(``SubscriptionRatio``, ``SubscriptionPricePerShare``, ``SharesOffered``,
``SharesEmpOwner``, ``SharesholderOwner``, ``StockHoldingRatio``) describe
現金增資認股 (cash capital-increase subscription rights) -- a related but
distinct corporate action this module does not model. They are captured in
the fixture for provenance but never read by :func:`parse_dividend_row`.

## ``Exdividend`` value domain -- all three values observed in the real feed

The CEO's 2026-08-12 distribution check over the full live table (124 rows)
observed exactly three values: ``"息"`` (cash only, 102 rows), ``"權"``
(stock only, 12 rows) and ``"權息"`` (both, 10 rows). Note the order is
權息, not 息權 -- the first implementation guessed the latter from TWSE's
naming convention and those 10 rows were correctly refused as unrecognized
until this was fixed against the observed value.
An unrecognized value is **not** silently dropped: the row is refused via
:class:`~app.data.providers._util.UnparseableRowError`, which the adapter's
fetch loop counts in ``skipped_rows`` and logs, so an unknown value is visible
in the sync output rather than disappearing.

## Blank cells mean "no such component", not zero and not an error

Most numeric columns above are empty strings on most rows -- a pure ex-date
listing with an amount not yet announced (see the first sample row: flagged
``"息"`` with a blank ``CashDividend``). ``""`` parses to "this component is
absent" (``None`` before being defaulted to ``Decimal(0)`` where the model
requires a value), never to ``0`` treated as "confirmed zero distribution"
and never refused as unparseable on that basis alone.

The one place blank is **not** tolerated: if ``Exdividend`` is ``"權"`` or
``"權息"`` (implying a stock/rights component exists) but
``StockDividendRatio`` is blank, that is an internal inconsistency in the row,
not "no component" -- the row is refused and counted rather than silently
treated as a 0-ratio stock event.

## Coverage limitation (must stay disclosed)

Only TWSE-listed (上市) symbols are covered this phase. TPEx (上櫃) has its own
OpenAPI portal with a different, separately unverified shape; guessing a
second endpoint would double the unverified surface for no extra confidence.
Until it is added, an OTC symbol simply has no events stored, and the
backtest layer must say "未還原" for it rather than implying it had no
dividends.

## This is a forecast table -- no history to back-fill

``TWT48U_ALL`` only ever lists *upcoming* ex-dates; there is no endpoint to
fetch past occurrences from. ``app.dividends.sync`` and
``app.dividends.store`` therefore treat every run as **additive**: each sync
upserts whatever the table currently shows (keyed on symbol + ex-date, so a
rerun refreshes in place rather than duplicating), and coverage only grows
the longer this tool is run regularly. See ``app.dividends.sync``'s module
docstring for the full rationale and the CLI's user-facing wording.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

import httpx

from app.data.http import RateLimitedClient
from app.data.providers._util import ROC_YEAR_OFFSET, UnparseableRowError
from app.dividends.models import DividendEvent

logger = logging.getLogger(__name__)

TWSE_OPENAPI_BASE_URL = "https://openapi.twse.com.tw"
#: 上市股票除權除息預告表 -- verified against a live payload 2026-08-12 (see
#: module docstring). ``TWT49U`` (the previous guess) does not exist.
TWSE_EX_DIVIDEND_PATH = "/v1/exchangeReport/TWT48U_ALL"

#: The five columns this adapter reads, out of the row's eleven. See "Only
#: five of the eleven columns are read" in the module docstring for the rest.
_DATE_KEY = "Date"
_CODE_KEY = "Code"
_EXDIVIDEND_KEY = "Exdividend"
_CASH_DIVIDEND_KEY = "CashDividend"
_STOCK_DIVIDEND_RATIO_KEY = "StockDividendRatio"

#: Confirmed / inferred ``Exdividend`` domain -- see module docstring.
_KNOWN_EXDIVIDEND_VALUES = frozenset({"息", "權", "權息"})
#: Values implying a stock/rights component must accompany a StockDividendRatio.
_STOCK_COMPONENT_EXDIVIDEND_VALUES = frozenset({"權", "權息"})

_BLANK_CELLS = {"", "-", "--", "---", "N/A", "n/a", "null", "None"}

#: A parsed date outside this window is treated as a parsing bug, not a real
#: event -- the "年界防呆" the no-separator ROC format needs since a single
#: mis-sliced digit shifts the year by a century.
_MIN_PLAUSIBLE_YEAR = 2000
_MAX_PLAUSIBLE_YEAR = 2100


@dataclass(frozen=True)
class DividendFetchResult:
    """One fetch's outcome: a batch of events, or an honest failure reason.

    Mirrors ``app.directory.providers.DirectoryFetchResult``: expected failure
    modes (network down, non-JSON body, unexpected shape) come back as
    ``ok=False`` with a Traditional Chinese ``reason``, never as an exception.
    """

    events: tuple[DividendEvent, ...]
    ok: bool
    reason: str | None
    source: str
    as_of: datetime
    #: Rows the parser refused. A non-zero count alongside ``ok=True`` means
    #: partial coverage, which the CLI prints rather than swallows.
    skipped_rows: int = 0


def _cell(row: dict[str, Any], key: str) -> str | None:
    """Return ``row[key]`` stripped, or ``None`` if absent/blank."""
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text not in _BLANK_CELLS else None


def parse_twse_date(value: str) -> date_type:
    """Parse the date spellings TWSE OpenAPI datasets are known to use.

    Handles ``1130701`` (no-separator ROC, the shape ``TWT48U_ALL`` actually
    uses -- e.g. ``"1150814"`` = 民國115年08月14日 = 2026-08-14, confirmed by
    the CEO's 2026-08-12 real sample), ``113/07/01`` (slash-separated ROC),
    ``20240701`` and ``2024-07-01``. Anything else -- or a year outside
    ``[2000, 2100]`` once parsed, a defensive bound against a mis-sliced
    digit silently landing a century off -- is refused rather than guessed.
    """
    text = value.strip().replace("-", "/")
    if "/" in text:
        parts = text.split("/")
        if len(parts) != 3:
            raise UnparseableRowError(f"unrecognized date format: {value!r}")
        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError as exc:
            raise UnparseableRowError(f"unrecognized date format: {value!r}") from exc
        if year < 1911:
            year += ROC_YEAR_OFFSET
    elif len(text) == 8 and text.isdigit():
        year, month, day = int(text[0:4]), int(text[4:6]), int(text[6:8])
    elif len(text) == 7 and text.isdigit():
        year, month, day = int(text[0:3]) + ROC_YEAR_OFFSET, int(text[3:5]), int(text[5:7])
    else:
        raise UnparseableRowError(f"unrecognized date format: {value!r}")
    try:
        result = date_type(year, month, day)
    except ValueError as exc:
        raise UnparseableRowError(f"impossible date: {value!r}") from exc
    if not (_MIN_PLAUSIBLE_YEAR <= result.year <= _MAX_PLAUSIBLE_YEAR):
        raise UnparseableRowError(f"implausible year in date: {value!r}")
    return result


def _parse_amount(value: str | None, *, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise UnparseableRowError(f"unparseable {field} cell: {value!r}") from exc


def parse_dividend_row(row: Any, *, source: str, as_of: datetime) -> DividendEvent:
    """Parse one TWT48U_ALL row into a :class:`DividendEvent`, or refuse it.

    A row must yield at least a symbol, an ex-date and a recognized
    ``Exdividend`` flag; the money/ratio columns are frequently blank on this
    forecast table (an amount not yet announced) and that is not by itself a
    reason to refuse the row -- see the module docstring's "Blank cells" and
    "Exdividend value domain" sections for what *is*.
    """
    if not isinstance(row, dict):
        raise UnparseableRowError(f"row is not an object: {row!r}")

    symbol = _cell(row, _CODE_KEY)
    if symbol is None:
        raise UnparseableRowError(f"missing symbol in row: {row!r}")

    raw_date = _cell(row, _DATE_KEY)
    if raw_date is None:
        raise UnparseableRowError(f"missing ex-date in row: {row!r}")
    ex_date = parse_twse_date(raw_date)

    exdividend = _cell(row, _EXDIVIDEND_KEY)
    if exdividend is None or exdividend not in _KNOWN_EXDIVIDEND_VALUES:
        raise UnparseableRowError(f"unrecognized Exdividend flag {exdividend!r} in row: {row!r}")

    cash = _parse_amount(_cell(row, _CASH_DIVIDEND_KEY), field="cash_dividend")
    if cash is not None and cash < 0:
        raise UnparseableRowError(f"negative CashDividend in row: {row!r}")

    stock_ratio = _parse_amount(
        _cell(row, _STOCK_DIVIDEND_RATIO_KEY), field="stock_dividend_ratio"
    )
    if stock_ratio is not None and stock_ratio < 0:
        raise UnparseableRowError(f"negative StockDividendRatio in row: {row!r}")
    if exdividend in _STOCK_COMPONENT_EXDIVIDEND_VALUES and stock_ratio is None:
        raise UnparseableRowError(
            f"Exdividend={exdividend!r} implies a stock component but "
            f"StockDividendRatio is blank in row: {row!r}"
        )

    return DividendEvent(
        symbol=symbol,
        market="TW",
        ex_date=ex_date,
        cash_dividend=cash if cash is not None else Decimal(0),
        stock_dividend_ratio=stock_ratio,
        source=source,
        as_of=as_of,
    )


class TwseDividendAdapter:
    """Fetches TWSE-listed 除權除息預告表 rows from the OpenAPI portal."""

    source_id: ClassVar[str] = "twse_openapi_dividend"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self) -> DividendFetchResult:
        now = datetime.now(UTC)
        try:
            response = self._client.get(TWSE_EX_DIVIDEND_PATH)
        except httpx.TransportError as exc:
            return self._failure(
                now,
                f"連線失敗（{exc.__class__.__name__}）：{exc}。"
                "本雲端開發環境對財經網域的 egress 已知被封鎖，"
                "請在有網路的機器（如 CEO 本機）重跑本工具。",
            )
        if response.status_code != httpx.codes.OK:
            return self._failure(
                now,
                f"TWSE OpenAPI 除權息預告表端點回傳 HTTP {response.status_code}，非預期狀態碼"
                "（端點路徑已於 2026-08-12 驗證過，非預期狀態碼代表上游可能改版，"
                "需由 data-engineer 覆核）",
            )
        try:
            payload = response.json()
        except ValueError:
            return self._failure(
                now, "TWSE OpenAPI 除權息預告表端點回應非 JSON，可能是端點路徑或格式已變更"
            )
        if not isinstance(payload, list):
            return self._failure(
                now,
                f"TWSE OpenAPI 除權息預告表端點回應非陣列（收到 {type(payload).__name__}），"
                "schema 與預期不符",
            )

        events: list[DividendEvent] = []
        skipped = 0
        for row in payload:
            try:
                events.append(parse_dividend_row(row, source=self.source_id, as_of=now))
            except (UnparseableRowError, ValueError) as exc:
                logger.debug("skipping unparseable TWSE dividend row: %s", exc)
                skipped += 1
        if not events:
            return self._failure(
                now,
                f"TWSE OpenAPI 除權息預告表回應中沒有任何可解析的列（略過 {skipped} 列）；"
                "欄位名稱可能與已驗證版本不符，需覆核官方文件",
                skipped=skipped,
            )
        return DividendFetchResult(
            events=tuple(events),
            ok=True,
            reason=None,
            source=self.source_id,
            as_of=now,
            skipped_rows=skipped,
        )

    def _failure(self, now: datetime, reason: str, *, skipped: int = 0) -> DividendFetchResult:
        return DividendFetchResult(
            events=(),
            ok=False,
            reason=reason,
            source=self.source_id,
            as_of=now,
            skipped_rows=skipped,
        )
