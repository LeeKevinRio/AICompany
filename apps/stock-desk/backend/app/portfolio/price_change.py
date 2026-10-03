"""Day-over-day price change for the summary's holdings (ADR-0016, close-only D1).

What the change is, by construction:

    pct = (price / basis_price - 1) * 100        quantized to 0.0001

* ``price`` is exactly the ``PriceInfo.value`` on the same row -- the latest
  **unadjusted** close of the ``ProviderResult`` that priced the position.
* ``basis_price`` is the previous bar's unadjusted close out of that **same**
  ``ProviderResult`` (``ChangeBasis``, ADR-0016 D-2). No second series, no
  extra service call, no wider lookback, and never a back-adjusted or
  reference price: the label "較 {MM/DD} 收盤" has to be a literal fact.

When the change cannot be stated truthfully it is ``None`` -- a fail-closed
screen, conditions F1-F8 of ADR-0016 D-4 -- and **no reason travels with it**
(K-6: there is no approved wording for one). Why a row was withheld goes to the
log only.

Scope boundary: the change is a display column of ``GET
/api/portfolio/summary`` and nothing else. Only that endpoint injects a
:class:`ChangeScreen`; every other ``build_summary`` caller gets ``None`` on
every row (F8), and no rule engine, alert or risk cap reads it (K-4).

This module must not import ``app.dividends.adjust``, ``app.sectors`` or
``app.data.market_panel`` (K-3; import-graph test). Its two lookups are
structural Protocols satisfied by ``DividendEventStore`` and ``PriceBarCache``.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.portfolio.valuation import PositionValuation
from app.positions.models import Market, Position
from app.services.market import TradingCalendarSource

logger = logging.getLogger(__name__)

#: ``pct`` resolution: four decimal places of a percent.
PCT_QUANTUM: Final = Decimal("0.0001")

#: F7 -- TW single-day price limit and tolerance, in percent. Mirrors the
#: category-③ corporate-action insurance of the sector definition (10% + 1%)
#: but is defined here on purpose: this module must not import ``app.sectors``
#: (K-3). Leveraged / inverse ETF limits are pending data-engineer's check;
#: until then every TW holding gets this threshold (fail-closed direction).
TW_DAILY_PRICE_LIMIT_PCT: Final = Decimal("10")
TW_DAILY_PRICE_LIMIT_TOLERANCE_PCT: Final = Decimal("1")

#: F3 -- the label ``app.dividends.adjust`` gives a back-adjusted bar. Kept as a
#: local literal (K-3 forbids importing that module); a test pins it equal.
ADJUSTED_SOURCE_SUFFIX: Final = "+divadj"

#: D-5 -- show the change when ex-date coverage cannot be established, as
#: ADR-0016 D-5 states. The remaining false moves (OTC, US, unsynced periods,
#: splits) are carried by the D-6 disclosure, which the *frontend* must render in
#: the same PR as the column; this screen does not enforce that. While the D-5
#: coverage rule is only the ``CoverageNotYetJudged`` stub, ``False`` would null
#: the whole column, so this is a fail-closed fallback, not a tuning knob:
#: changing it is a CEO decision recorded by amending ADR-0016, never a hotfix.
SHOW_WHEN_COVERAGE_UNKNOWN: Final = True

BasisKind = Literal["close", "intraday"]


class PriceChange(BaseModel):
    """One row's day-over-day change (ADR-0016 D-1). JSON: decimals as strings."""

    model_config = ConfigDict(frozen=True)

    #: Percent units: ``(price / basis_price - 1) * 100``, quantized to 0.0001.
    pct: Decimal
    #: ``close`` <=> the row's ``price.price_kind == "daily_close"``.
    basis_kind: BasisKind
    #: Never ``None`` when a ``PriceChange`` exists.
    basis_date: date
    #: The raw (unadjusted) close on ``basis_date``; always ``> 0``.
    basis_price: Decimal


def change_pct(price: Decimal, basis_price: Decimal) -> Decimal:
    """``(price / basis_price - 1) * 100`` quantized to :data:`PCT_QUANTUM`.

    Computed as ``(price - basis_price) * 100 / basis_price`` (the same value,
    one rounding fewer). A result that rounds to zero is returned unsigned so a
    tiny fall never serializes as ``"-0.0000"``.
    """
    raw = (price - basis_price) * 100 / basis_price
    pct = raw.quantize(PCT_QUANTUM, rounding=ROUND_HALF_UP)
    return abs(pct) if pct.is_zero() else pct


class ExDateLookup(Protocol):
    """Known ex-dates for a whole book in one read (K-7); ``DividendEventStore``."""

    def ex_dates_between(
        self,
        keys: Collection[tuple[str, Market]],
        start: date,
        end: date,
    ) -> Mapping[tuple[str, Market], frozenset[date]]: ...


ExDateCoverage = Literal["known", "unknown"]


@dataclass(frozen=True)
class CoverageQuery:
    """What the D-5 coverage rule is asked about one row's change window."""

    symbol: str
    market: Market
    #: ``source`` of the bar behind the price; D-5 requires ``"twse"``.
    latest_source: str
    basis_date: date
    price_date: date


class ExDateCoverageRule(Protocol):
    """ADR-0016 D-5: can "no known ex-date in the window" be trusted for a row?

    ``known`` only when the latest bar's source is ``twse`` **and** the sync
    record proves every ex-date in ``(basis_date, price_date]`` was still in the
    future at some sync. Answered for the whole book at once (K-7). The real
    rule is data-engineer's to write; :class:`CoverageNotYetJudged` stands in.
    """

    def coverage(
        self, queries: Sequence[CoverageQuery]
    ) -> Mapping[CoverageQuery, ExDateCoverage]: ...


class CoverageNotYetJudged:
    """STUB for :class:`ExDateCoverageRule` until data-engineer delivers D-5.

    Answers ``unknown`` for every row -- the conservative statement, since
    nothing here proves coverage. Under :data:`SHOW_WHEN_COVERAGE_UNKNOWN` the
    change is still shown; the residual risk is D-6's disclosure.
    """

    def coverage(self, queries: Sequence[CoverageQuery]) -> Mapping[CoverageQuery, ExDateCoverage]:
        return {query: "unknown" for query in queries}


@dataclass(frozen=True)
class _Candidate:
    """A row that passed the per-row checks and awaits the book-level ones."""

    index: int
    key: tuple[str, Market]
    latest_source: str
    price_date: date
    basis_date: date
    basis_price: Decimal
    pct: Decimal


@dataclass(frozen=True)
class ChangeScreen:
    """Decides, row by row, whether a change may be shown (ADR-0016 D-3/D-4).

    Injected by ``GET /api/portfolio/summary`` only. Each book costs one
    ex-date read and one calendar read per market (K-7), and none at all when
    no row survives the per-row checks.
    """

    ex_dates: ExDateLookup
    calendar: TradingCalendarSource
    coverage_rule: ExDateCoverageRule = field(default_factory=CoverageNotYetJudged)

    def screen(
        self, rows: Sequence[tuple[Position, PositionValuation]]
    ) -> list[PriceChange | None]:
        """One ``PriceChange | None`` per row, in order.

        Fail-closed as a whole: any exception -- a lookup that fails, or a
        per-row computation that raises on an extreme value -- withholds every
        change in the book rather than failing the summary. The column is
        auxiliary; the valuation is not.
        """
        try:
            return self._screen(rows)
        except Exception:
            logger.exception("price change withheld for the whole book: screen failed")
            return [None] * len(rows)

    def _screen(
        self, rows: Sequence[tuple[Position, PositionValuation]]
    ) -> list[PriceChange | None]:
        candidates: list[_Candidate] = []
        for index, (position, valued) in enumerate(rows):
            candidate, withheld = _row_candidate(index, position, valued)
            if candidate is None:
                _log_withheld(position, withheld)
                continue
            candidates.append(candidate)
        results: list[PriceChange | None] = [None] * len(rows)
        if not candidates:
            return results
        for candidate in self._book_checks(candidates, rows):
            results[candidate.index] = PriceChange(
                pct=candidate.pct,
                basis_kind="close",
                basis_date=candidate.basis_date,
                basis_price=candidate.basis_price,
            )
        return results

    def _book_checks(
        self,
        candidates: list[_Candidate],
        rows: Sequence[tuple[Position, PositionValuation]],
    ) -> list[_Candidate]:
        start = min(candidate.basis_date for candidate in candidates)
        end = max(candidate.price_date for candidate in candidates)

        # F5 -- one calendar read per market.
        sessions: dict[Market, frozenset[date]] = {}
        for market in sorted({candidate.key[1] for candidate in candidates}):
            sessions[market] = self.calendar.market_trading_days(market, start, end)

        # F6 -- one ex-date read for the whole book.
        ex_dates = self.ex_dates.ex_dates_between(
            {candidate.key for candidate in candidates}, start, end
        )

        passed: list[_Candidate] = []
        for candidate in candidates:
            position = rows[candidate.index][0]
            observed = sessions.get(candidate.key[1], frozenset())
            if any(candidate.basis_date < day < candidate.price_date for day in observed):
                _log_withheld(position, "F5_missing_session")
                continue
            known = ex_dates.get(candidate.key, frozenset())
            if any(candidate.basis_date < day <= candidate.price_date for day in known):
                _log_withheld(position, "F6_ex_date_in_window")
                continue
            passed.append(candidate)

        # D-5 -- coverage of "no known ex-date", one call for the whole book.
        queries = {
            candidate.index: CoverageQuery(
                symbol=candidate.key[0],
                market=candidate.key[1],
                latest_source=candidate.latest_source,
                basis_date=candidate.basis_date,
                price_date=candidate.price_date,
            )
            for candidate in passed
        }
        verdicts = self.coverage_rule.coverage(list(queries.values())) if queries else {}
        shown: list[_Candidate] = []
        for candidate in passed:
            verdict = verdicts.get(queries[candidate.index], "unknown")
            if verdict != "known":
                position = rows[candidate.index][0]
                if not SHOW_WHEN_COVERAGE_UNKNOWN:
                    _log_withheld(position, "D5_coverage_unknown")
                    continue
                logger.debug(
                    "price change shown with unknown ex-date coverage (ADR-0016 D-5/D-6): %s %s",
                    position.market,
                    position.symbol,
                )
            shown.append(candidate)
        return shown


def _row_candidate(
    index: int, position: Position, valued: PositionValuation
) -> tuple[_Candidate | None, str]:
    """The per-row checks F1-F4 and F7; ``(None, code)`` when one fails."""
    price_info = valued.valuation.price
    basis = valued.change_basis
    # F1 -- no usable price on this row.
    if price_info is None or basis is None or price_info.value <= 0:
        return None, "F1_no_price"
    # The change describes the price on screen and nothing else; a row whose
    # price did not come from these bars has no change to state.
    if price_info.value != basis.latest.close or price_info.as_of != basis.latest.date.isoformat():
        return None, "F1_price_not_from_basis"
    # Intraday bases are ADR-0016 D-7 (after W15) and are not built here.
    if price_info.price_kind != "daily_close":
        return None, "D7_not_enabled"
    previous = basis.previous
    # F2 -- fewer than two bars in the same ProviderResult.
    if previous is None:
        return None, "F2_single_bar"
    latest = basis.latest
    # F3 -- spliced sources, or a back-adjusted bar.
    if (
        latest.source != previous.source
        or latest.source.endswith(ADJUSTED_SOURCE_SUFFIX)
        or previous.source.endswith(ADJUSTED_SOURCE_SUFFIX)
    ):
        return None, "F3_source_mismatch"
    # F4 -- a basis that cannot be divided by or does not precede the price.
    if previous.close <= 0 or previous.date >= latest.date:
        return None, "F4_bad_basis"
    pct = change_pct(price_info.value, previous.close)
    # F7 -- a TW move past the daily limit is an unhandled corporate action.
    if position.market == "TW" and abs(pct) > (
        TW_DAILY_PRICE_LIMIT_PCT + TW_DAILY_PRICE_LIMIT_TOLERANCE_PCT
    ):
        return None, "F7_beyond_price_limit"
    return (
        _Candidate(
            index=index,
            key=(position.symbol.strip().upper(), position.market),
            latest_source=latest.source,
            price_date=latest.date,
            basis_date=previous.date,
            basis_price=previous.close,
            pct=pct,
        ),
        "",
    )


def _log_withheld(position: Position, code: str) -> None:
    logger.debug("price change withheld (%s): %s %s", code, position.market, position.symbol)
