"""One FX quote resolver for every consumer of the risk layer.

``app/advice/book.py`` is a pure function and must stay one (ADR-0005 F-1), so
somebody else has to turn an :class:`FxRateProvider` into the
:class:`app.advice.book.FxQuote` it consumes. This is that somebody: the advice
endpoint and the alert snapshot both call it, so a rate that reaches a risk cap
is resolved by the same rules whichever door the user came in through.

Two properties are load-bearing:

* **A failure is still a quote.** When the provider has nothing, the returned
  quote carries ``rate=None`` plus its ``status``/``source``, so the caller can
  say *why* the conversion is missing instead of just that it is.
* **Nothing is invented.** No default rate, no interpolation between published
  days, and no cross-rate derived from another pair. The lookback only accepts
  a rate published **on or before** the target date, mirroring
  ``PositionValuator`` so the valuation and the risk layer never disagree about
  which day's rate applies.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Final

from app.advice.book import FxQuote
from app.data.interface import DataStatus
from app.data.providers.fx import FxRateProvider
from app.portfolio.valuation import FX_BACKTRACK_DAYS

logger = logging.getLogger(__name__)

#: The reporting currency; it needs no conversion and therefore no quote.
REPORTING_CURRENCY: Final = "TWD"

#: Emitted when no provider was wired in at all.
NO_PROVIDER_SOURCE: Final = "none"

#: Per-source standing disclosure, surfaced wherever the rate is used. Bank of
#: Taiwan publishes no single official daily close, so the adapter reports the
#: mid-point of the spot buy/sell pair -- a model value, not an official rate --
#: and its endpoint could not be verified against a live response in this
#: environment (see the ``app/data/providers/fx.py`` header and
#: ``tests/fixtures/README.md``). This text is user-facing on purpose (F-4).
SOURCE_NOTES: Final[dict[str, str]] = {
    "bank_of_taiwan": (
        "匯率為台灣銀行即期買賣中點的模型值，不是官方收盤匯率；"
        "該端點與 CSV 欄位格式未經本環境線上查證（verified=false）。"
    ),
}

#: Used for any source without an entry above: says what is unknown, and does
#: not claim anything about the source's methodology.
GENERIC_SOURCE_NOTE: Final = (
    "此匯率來源的端點與欄位格式未經本環境線上查證（verified=false），"
    "其數值口徑（即期／收盤／中點）以來源文件為準。"
)


def source_note(source: str) -> str:
    """The standing disclosure for ``source``."""
    return SOURCE_NOTES.get(source, GENERIC_SOURCE_NOTE)


def resolve_fx_quote(
    provider: FxRateProvider | None,
    *,
    currency: str | None,
    on: date,
    backtrack_days: int = FX_BACKTRACK_DAYS,
) -> FxQuote | None:
    """Resolve ``currency`` -> TWD as of ``on``, or ``None`` if none is needed.

    ``None`` means "no conversion applies" (a TWD instrument, or a candidate
    with no currency yet) -- it never means "the lookup failed". A failed
    lookup comes back as a quote with ``rate=None``.
    """
    if currency is None or currency.strip().upper() == REPORTING_CURRENCY:
        return None

    pair = f"{currency.strip().upper()}{REPORTING_CURRENCY}"
    if provider is None:
        return FxQuote(
            pair=pair,
            rate=None,
            as_of=None,
            source=NO_PROVIDER_SOURCE,
            status=DataStatus.UNAVAILABLE,
            source_note="",
        )

    result = provider.get_daily_rates(pair, on - timedelta(days=backtrack_days), on)
    note = source_note(result.source)
    candidates = [rate for rate in result.rates if rate.date <= on]
    if result.status is DataStatus.UNAVAILABLE or not candidates:
        logger.info(
            "fx: no usable rate for %s on or before %s (status=%s, source=%s)",
            pair,
            on.isoformat(),
            result.status.value,
            result.source,
        )
        return FxQuote(
            pair=pair,
            rate=None,
            as_of=None,
            source=result.source,
            status=DataStatus.UNAVAILABLE,
            source_note=note,
        )

    latest = max(candidates, key=lambda rate: rate.date)
    return FxQuote(
        pair=pair,
        rate=float(latest.rate),
        as_of=latest.date.isoformat(),
        source=result.source,
        status=result.status,
        source_note=note,
    )
