"""USD/TWD daily FX rate adapter, plus the FX degradation ladder.

Data source: Bank of Taiwan (台灣銀行) public exchange-rate CSV export, one
file per calendar day.

Endpoint (documented per Bank of Taiwan's public historical-rate CSV export,
widely referenced pattern; queried against project knowledge on 2026-07-23,
NOT re-verified against a live response in this sandbox because outbound
HTTPS to ``rate.bot.com.tw`` is blocked by the environment's egress policy
-- see ``tests/fixtures/README.md``)::

    GET https://rate.bot.com.tw/xrt/flcsv/0/<YYYY-MM-DD>

Response: UTF-8 CSV, one row per currency for that date. The header row
labels each rate category (cash / spot / forward) once per buy+sell pair,
in that order (buy column first, then sell column), and the currency code
appears in the first data-row column (e.g. ``USD``).

Because Bank of Taiwan does not publish a single official "daily close" for
FX, this adapter reports the mid-point of the spot ("即期") buy and sell
rates as the day's rate. Header matching is done by locating the "即期"
label rather than a hardcoded column index, so a header column reordering
degrades to a clear "unavailable" instead of silently reading the wrong
column -- but a genuine schema change could still require an update here;
this is flagged as unverified in ``tests/fixtures/README.md``.

Only the single-day CSV endpoint exists for this feed, so a date range is
fetched with one HTTP call per calendar day; days with no published rate
(weekends, holidays) are simply absent from the result, never fabricated.

CHALLENGE-PAGE DEGRADATION (CEO 本機 2026-09-19 實測, ADR-0011): as of that
date every single day's request to this endpoint returns HTTP 200 with an
HTML anti-bot "Challenge Validation" page instead of CSV (``<title>Challenge
Validation</title>``, a ``cp_clge_done`` cookie-setting script, a
``sec-cpt-if`` iframe). :meth:`BankOfTaiwanFxAdapter._looks_like_challenge_page`
detects this by response shape (``Content-Type`` or a leading ``<!doctype
html``/``<html`` tag) rather than string-matching the challenge vendor's
markup, so this keeps working even if the specific challenge product changes.
The whole page is deliberately never logged (it is large and re-fetched
every day this holds) -- only a one-line warning naming the date. Once one
day in a requested range comes back as a challenge page, the rest of the
range is not queried at all (previously this fetched up to
``FX_BACKTRACK_DAYS + 1`` pages per lookup, all doomed the same way): see
:class:`BankOfTaiwanFxAdapter` and ADR-0011 for the resulting
``FxRateLadder`` fallback to :class:`app.data.providers.fx_yfinance.
YFinanceFxAdapter`.
"""

from __future__ import annotations

import csv
import io
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus

logger = logging.getLogger(__name__)

BOT_BASE_URL = "https://rate.bot.com.tw"
FLCSV_PATH_TEMPLATE = "/xrt/flcsv/0/{date}"
SPOT_LABEL = "即期"

#: User-facing reason attached to the ``UNAVAILABLE`` result produced when the
#: endpoint is serving its anti-bot challenge page instead of CSV (ADR-0011).
CHALLENGE_PAGE_REASON = (
    "台灣銀行匯率來源目前回應為 HTML 挑戰頁（防爬機制），非 CSV 資料，本次判定為不可用。"
)
#: Joins this ladder's own layer reasons, mirroring ``app/data/service.py``'s
#: ``_REASON_SEPARATOR`` so a combined FX reason reads the same way.
_REASON_SEPARATOR = "。 "


class FxRate(BaseModel):
    """One daily USD/TWD (or other pair) rate, self-describing like PriceBar."""

    model_config = ConfigDict(frozen=True)

    pair: str
    date: date_type
    rate: Decimal
    as_of: datetime
    source: str

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC)")
        return value


class FxRateResult(BaseModel):
    """Envelope returned by every ``FxRateProvider.get_daily_rates`` call.

    ``reason`` (optional, backward-compatible default ``None``): a user-facing
    Traditional Chinese sentence explaining *why* a response degraded --
    mirrors ``ProviderResult.reason`` in ``app/data/interface.py``. ``None`` on
    ordinary success.
    """

    model_config = ConfigDict(frozen=True)

    rates: list[FxRate]
    status: DataStatus
    as_of: datetime
    source: str
    staleness_minutes: int | None = None
    reason: str | None = None


class FxRateProvider(ABC):
    """Abstract adapter for a daily FX rate source, mirroring MarketDataProvider."""

    source_id: ClassVar[str]

    @abstractmethod
    def get_daily_rates(self, pair: str, start: date_type, end: date_type) -> FxRateResult:
        """Return daily rates for ``pair`` (e.g. ``"USDTWD"``) within [start, end]."""
        raise NotImplementedError


def _iter_dates(start: date_type, end: date_type) -> list[date_type]:
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def _looks_like_challenge_page(response: httpx.Response) -> bool:
    """Detect the anti-bot HTML challenge page by response shape, not markup text.

    Checking the ``Content-Type`` header (this feed's genuine responses are
    ``text/csv``-ish, never HTML) or a leading ``<!doctype html``/``<html`` tag
    means this keeps working even if the specific challenge product changes
    its page content -- unlike string-matching ``cp_clge_done`` or
    ``sec-cpt-if`` verbatim, which would silently stop firing the day the
    vendor tweaks its markup.
    """
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" in content_type or "application/xhtml" in content_type:
        return True
    # Only the first bytes are needed and this avoids materializing/decoding
    # the whole (possibly large) body just for the sniff.
    head = response.text[:200].lstrip().lower()
    return head.startswith("<!doctype html") or head.startswith("<html")


class _ChallengePageEncountered(Exception):
    """Internal control-flow signal: a request returned an HTML challenge page.

    Never escapes :meth:`BankOfTaiwanFxAdapter.get_daily_rates` -- it is
    caught there to short-circuit the remaining dates in the requested range
    and turn into a plain ``UNAVAILABLE`` result with ``reason`` set.
    """


class BankOfTaiwanFxAdapter(FxRateProvider):
    """Primary FX adapter: Bank of Taiwan daily spot-rate CSV export."""

    source_id: ClassVar[str] = "bank_of_taiwan"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(base_url=BOT_BASE_URL, min_interval_seconds=0.5)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_daily_rates(self, pair: str, start: date_type, end: date_type) -> FxRateResult:
        now = datetime.now(UTC)
        currency_code = pair[:3].upper()
        rates: list[FxRate] = []
        try:
            for day in _iter_dates(start, end):
                rate = self._fetch_one_day(pair, currency_code, day, now)
                if rate is not None:
                    rates.append(rate)
        except _ChallengePageEncountered:
            # ADR-0011: once the endpoint is confirmed to be serving the
            # challenge page for one date in this range, every remaining date
            # is doomed the same way -- stop instead of burning one HTTP call
            # (and one throttle wait) per remaining calendar day. The whole
            # request is reported as unavailable, discarding any rates
            # collected so far in this same call: a mixed "some real days,
            # then the source turned into a challenge wall mid-loop" result
            # would be surprising to a caller expecting either "this pair
            # works" or "it doesn't", and ADR-0011's motivating case (every
            # day blocked) never hits this trade-off in practice.
            return FxRateResult(
                rates=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
                reason=CHALLENGE_PAGE_REASON,
            )
        except httpx.TransportError as exc:
            logger.warning("Bank of Taiwan FX request failed for %s: %s", pair, exc)
            return FxRateResult(
                rates=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
            )

        if not rates:
            return FxRateResult(
                rates=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
            )
        return FxRateResult(
            rates=rates,
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
            staleness_minutes=0,
        )

    def _fetch_one_day(
        self, pair: str, currency_code: str, day: date_type, now: datetime
    ) -> FxRate | None:
        response = self._client.get(FLCSV_PATH_TEMPLATE.format(date=day.isoformat()))
        if response.status_code != httpx.codes.OK:
            logger.debug(
                "Bank of Taiwan FX: HTTP %d for %s on %s",
                response.status_code,
                pair,
                day.isoformat(),
            )
            return None
        if _looks_like_challenge_page(response):
            # Never log the body: it is a full HTML page, repeated once per
            # requested day for as long as this holds (ADR-0011).
            logger.warning(
                "Bank of Taiwan FX returned an HTML challenge page for %s; treating as unavailable",
                day.isoformat(),
            )
            raise _ChallengePageEncountered
        return self._parse_csv(response.text, pair, currency_code, day, now)

    def _parse_csv(
        self, body: str, pair: str, currency_code: str, day: date_type, now: datetime
    ) -> FxRate | None:
        reader = csv.reader(io.StringIO(body))
        rows = list(reader)
        if not rows:
            logger.debug("Bank of Taiwan FX: empty CSV for %s on %s", pair, day.isoformat())
            return None

        header = rows[0]
        spot_indices = [idx for idx, cell in enumerate(header) if SPOT_LABEL in cell]
        if len(spot_indices) < 2:
            logger.warning(
                "Bank of Taiwan FX: could not locate spot-rate columns for %s on %s "
                "(header=%r) -- schema may have changed",
                pair,
                day.isoformat(),
                header,
            )
            return None
        buy_idx, sell_idx = spot_indices[0], spot_indices[1]

        for row in rows[1:]:
            if not row or not row[0].strip().upper().startswith(currency_code):
                continue
            if len(row) <= max(buy_idx, sell_idx):
                continue
            try:
                buy = Decimal(row[buy_idx].strip())
                sell = Decimal(row[sell_idx].strip())
            except InvalidOperation:
                logger.debug(
                    "Bank of Taiwan FX: unparseable rate cells for %s on %s: %r",
                    pair,
                    day.isoformat(),
                    row,
                )
                return None
            mid_rate = (buy + sell) / Decimal(2)
            return FxRate(
                pair=pair,
                date=day,
                rate=mid_rate,
                as_of=now,
                source=self.source_id,
            )
        logger.debug(
            "Bank of Taiwan FX: currency %s row not found for %s", currency_code, day.isoformat()
        )
        return None


def _combine_fx_reasons(reasons: list[str | None]) -> str | None:
    """Fold every rung's own wording into one sentence, losing none of them.

    Mirrors ``app/data/service.py``'s ``_combine_reasons`` for the price-bar
    ladder; kept as a separate small copy here rather than a shared import
    because ``FxRateResult``/``ProviderResult`` are distinct envelope types
    and this file must not import ``app/data/service.py`` (that module
    depends on ``PriceBarCache``, which the FX vertical has no equivalent of
    yet -- ADR-0011 explicitly notes there is no FX cache layer).
    """
    kept = [reason.strip() for reason in reasons if reason and reason.strip()]
    if not kept:
        return None
    return _REASON_SEPARATOR.join(text.rstrip("。") for text in kept) + "。"


class FxRateLadder(FxRateProvider):
    """FX degradation ladder: ``primary`` live, then ``backup`` live, then unavailable.

    Mirrors the shape of ``MarketDataService`` (``app/data/service.py``) for
    the FX vertical, minus the cache layer -- there is no local FX cache yet
    (ADR-0011), so "backup" is this ladder's whole degradation story today.

    - ``primary`` succeeding (a non-``UNAVAILABLE`` status with at least one
      rate) is returned untouched, status and all.
    - ``primary`` declining falls through to ``backup``; a successful backup
      answer is re-labelled ``DataStatus.BACKUP`` (never upgraded to
      ``FRESH`` -- ADR-0011 requires the yfinance-backed fallback to always
      disclose as non-official, matching the ADR-0005 discipline already
      applied to the index path) and carries a ``reason`` explaining *why*
      the primary was skipped, so a user is never left thinking the backup
      quote is the bank's own rate for no visible reason.
    - Both declining returns ``UNAVAILABLE`` with both rungs' reasons joined.

    A provider that raises (a bug, not an expected "no data" outcome) is
    caught here and logged, then treated the same as a declined rung -- one
    misbehaving adapter must not take the whole FX lookup down.
    """

    source_id: ClassVar[str] = "fx_ladder"

    def __init__(self, *, primary: FxRateProvider, backup: FxRateProvider) -> None:
        self._primary = primary
        self._backup = backup

    def close(self) -> None:
        for rung in (self._primary, self._backup):
            close_fn = getattr(rung, "close", None)
            if callable(close_fn):
                close_fn()

    def get_daily_rates(self, pair: str, start: date_type, end: date_type) -> FxRateResult:
        now = datetime.now(UTC)
        primary_result = self._safe_call(self._primary, pair, start, end)
        if primary_result is not None and self._is_usable(primary_result):
            return primary_result

        primary_label = getattr(self._primary, "source_id", self._primary.__class__.__name__)
        primary_reason = primary_result.reason if primary_result is not None else None
        skip_note = f"主來源（{primary_label}）本次無法提供匯率"
        primary_summary = f"{skip_note}：{primary_reason}" if primary_reason else f"{skip_note}。"

        backup_result = self._safe_call(self._backup, pair, start, end)
        if backup_result is not None and self._is_usable(backup_result):
            return FxRateResult(
                rates=backup_result.rates,
                status=DataStatus.BACKUP,
                as_of=backup_result.as_of,
                source=backup_result.source,
                staleness_minutes=backup_result.staleness_minutes,
                reason=_combine_fx_reasons([primary_summary]),
            )

        backup_reason = backup_result.reason if backup_result is not None else None
        logger.warning(
            "FX ladder: both %s and %s failed for %s",
            primary_label,
            getattr(self._backup, "source_id", self._backup.__class__.__name__),
            pair,
        )
        return FxRateResult(
            rates=[],
            status=DataStatus.UNAVAILABLE,
            as_of=now,
            source="none",
            staleness_minutes=None,
            reason=_combine_fx_reasons([primary_summary, backup_reason]),
        )

    @staticmethod
    def _is_usable(result: FxRateResult) -> bool:
        return result.status is not DataStatus.UNAVAILABLE and bool(result.rates)

    @staticmethod
    def _safe_call(
        provider: FxRateProvider, pair: str, start: date_type, end: date_type
    ) -> FxRateResult | None:
        label = getattr(provider, "source_id", provider.__class__.__name__)
        try:
            return provider.get_daily_rates(pair, start, end)
        except Exception:
            logger.exception(
                "unexpected FX provider error: %s raised while fetching %s", label, pair
            )
            return None
