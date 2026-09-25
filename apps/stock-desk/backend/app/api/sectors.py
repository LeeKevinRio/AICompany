"""``GET /api/sectors/momentum`` -- the sector momentum card, read only (ADR-0012 D-10).

The board, the statistics and the approvals are computed and written by the
scheduler (``app.services.sector_board``); this router only reads and
assembles. Field names are ADR-0012 D-10's, verbatim.

Budget (C-6, T-2): **zero HTTP** -- no resolver, provider or client is touched --
and at most **seven SQL statements** over the two databases, whatever the
number of sectors or stocks:

* main DB, one connection (:class:`app.sectors.store.SectorCardReader`): the
  latest board as one JOIN, the latest version's statistics with their checks
  as one JOIN, that version's approvals, the registry's D0;
* market DB, read only (:class:`app.data.market_panel.MarketPanelReader`): the
  ``ok`` sessions per kind (calendar, ``pit_gaps`` input, data age) and --
  only when statistics exist -- one existence check of their source runs
  (D-14; the research DB is never opened, C-27);
* positions: one read for the 「持有中／未持有」 flags (C-34).

The effective ``gate_status`` is composed by :func:`app.sectors.gate.evaluate`
and handed over by :func:`app.sectors.gate.response_fields` (C-20). The gate's
process-level inputs -- deployed ``ci_passed_commit``, fee and DE-5
verification dates -- are read once per process by the services layer
(:mod:`app.services.sector_runtime`, C-24) and installed on the app by the
composition root (:func:`install_gate_runtime`, called from :mod:`app.main`).
Wording is :mod:`app.api.sectors_wording` (verbatim risk text, C-30).

Import boundary (ADR-0012 D-1, C-5; ``tests/test_sectors_boundary.py``): this
module reaches only the sectors core and store, ``data.market_panel``,
``positions.store`` and the shared schema/freshness modules the D-10 mapping
needs. It therefore never imports ``app.api.deps`` (which wires the market
services and portfolio) nor ``app.services`` (which reaches ``app.backtest``):
the positions store has its own provider below and the gate runtime is
installed from outside.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, FastAPI, Request

from app.api import sectors_wording as wording
from app.api.common import DataMeta
from app.data.calendar import TradingCalendar
from app.data.freshness import TW_POLICY, expected_session
from app.data.interface import SnapshotKind
from app.data.market_panel import MarketPanelReader
from app.data.panel import TAIPEI
from app.positions.store import PositionStore
from app.sectors import coverage, gate
from app.sectors.coverage import CardAssessment
from app.sectors.definition import SECTOR_MOMENTUM_V1, SectorMomentumDefinition
from app.sectors.gate import (
    UNVERIFIED_RUNTIME,
    GateInputs,
    InsufficientChecks,
    PitStatus,
    SectorGateRuntime,
)
from app.sectors.models import (
    ConstituentItem,
    ExcludedSector,
    InsufficientReason,
    ReasonCode,
    SectorItem,
    SectorMomentumResponse,
)
from app.sectors.store import CardRead, SectorCardReader, StoredBoard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sectors", tags=["sectors"])

#: The definition the card serves (its thresholds are echoed from it, C-33).
DEFINITION: Final[SectorMomentumDefinition] = SECTOR_MOMENTUM_V1
#: Sectors shown collapsed (server constant; default 3, at most 5 -- D-10, PRD FR-3).
HEADLINE_COUNT: Final = 3
#: ``data_source`` / ``DataMeta.source`` when there is no board to name one.
NO_SOURCE: Final = "none"
#: ``app.state`` attribute holding the zero-argument gate runtime loader.
GATE_RUNTIME_STATE: Final = "sector_gate_runtime"

SectorMomentumPayload = SectorMomentumResponse[DataMeta]


@dataclass(frozen=True)
class SectorCardSources:
    """The two read-only database readers behind the card."""

    card: SectorCardReader
    market: MarketPanelReader


@lru_cache(maxsize=1)
def _default_sources() -> SectorCardSources:
    market = MarketPanelReader()
    return SectorCardSources(card=SectorCardReader(verifier=market), market=market)


@lru_cache(maxsize=1)
def _default_positions() -> PositionStore:
    return PositionStore()


def get_sector_card_sources() -> SectorCardSources:
    """The process-wide card readers (schema ensured once, not per request)."""
    return _default_sources()


def get_sector_position_store() -> PositionStore:
    """The positions store, read only for the held flags (C-34).

    The card's own provider rather than ``app.api.deps.get_position_store``:
    that module wires the market services and the portfolio, which this
    router may not reach (ADR-0012 D-1, C-5). Same default database.
    """
    return _default_positions()


def install_gate_runtime(app: FastAPI, loader: Callable[[], SectorGateRuntime]) -> None:
    """Called by the composition root with the services layer's process-wide loader."""
    setattr(app.state, GATE_RUNTIME_STATE, loader)


def get_sector_gate_runtime(request: Request) -> SectorGateRuntime:
    """Deployed ``ci_passed_commit`` and verification dates (read once, by the loader).

    With no loader installed the card fails closed: every input unverified, so
    NE-3 and NE-7 hold and ``gate_status`` is ``not_evaluated`` (C-24, C-25).
    """
    loader = getattr(request.app.state, GATE_RUNTIME_STATE, None)
    runtime = loader() if callable(loader) else None
    if not isinstance(runtime, SectorGateRuntime):
        logger.error("sector card: no gate runtime installed; treating every input as unverified")
        return UNVERIFIED_RUNTIME
    return runtime


def get_sector_clock() -> Callable[[], datetime]:
    """The response clock (``as_of``, data age); injectable for tests."""
    return lambda: datetime.now(UTC)


SourcesDep = Annotated[SectorCardSources, Depends(get_sector_card_sources)]
RuntimeDep = Annotated[SectorGateRuntime, Depends(get_sector_gate_runtime)]
PositionsDep = Annotated[PositionStore, Depends(get_sector_position_store)]
ClockDep = Annotated[Callable[[], datetime], Depends(get_sector_clock)]


@router.get("/momentum", response_model=SectorMomentumPayload)
def read_sector_momentum(
    sources: SourcesDep,
    runtime: RuntimeDep,
    positions: PositionsDep,
    clock: ClockDep,
    market: Literal["TW"] = "TW",
) -> SectorMomentumPayload:
    now = clock()
    today = now.astimezone(TAIPEI).date()
    read = sources.card.read(market, DEFINITION.method_version)
    ok = sources.market.ok_sessions(_calendar_start(read, today), today)
    return build_sector_momentum(
        market=market,
        read=read,
        ok_sessions=ok,
        runtime=runtime,
        held=_held_symbols(positions),
        now=now,
    )


def _calendar_start(read: CardRead, today: date) -> date:
    """Earliest session any read-time judgement needs from the market calendar."""
    board = read.board
    candidates = [read.accumulation_start]
    if board is not None:
        candidates += [board.window_start, board.data_as_of]
    if read.stats_history:
        candidates.append(read.stats_history[-1].recompute_session)
    known = [day for day in candidates if day is not None]
    return min([*known, today])


def _held_symbols(positions: PositionStore) -> frozenset[str] | None:
    """TW symbols held; ``None`` when the lookup failed (no badge, H-2, C-34)."""
    try:
        return frozenset(p.symbol for p in positions.list_all() if p.market == "TW")
    except Exception:  # noqa: BLE001 - any failure means "unknown", never "not held"
        logger.exception("sector card: positions lookup failed; held flags are unknown")
        return None


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_sector_momentum(
    *,
    market: str,
    read: CardRead,
    ok_sessions: Mapping[SnapshotKind, frozenset[date]],
    runtime: SectorGateRuntime,
    held: frozenset[str] | None,
    now: datetime,
    definition: SectorMomentumDefinition = DEFINITION,
) -> SectorMomentumPayload:
    """The D-10 payload from what the readers returned (no I/O)."""
    rules = definition.coverage
    board = usable_board(read.board)
    # The source is the stored board's even when that board is ignored (R-5):
    # a demo_synthetic board must keep its demo warning (IP-6, NR-2).
    data_source = read.board.data_source if read.board is not None else NO_SOURCE
    card = (
        coverage.card_from_counts(
            expected=board.market_expected_count,
            missing=board.market_missing_count,
            ex_date=board.market_ex_date_excluded_count,
            corporate_action=board.market_corporate_action_excluded_count,
            rules=rules,
        )
        if board is not None
        else None
    )
    excluded_codes = tuple(row.reason_code for row in board.excluded) if board else ()
    insufficient = gate.insufficient_reason(
        InsufficientChecks(data_as_of_known=False)
        if board is None or card is None
        else InsufficientChecks(
            data_as_of_known=True,
            ex_dividend_feed_covered=board.ex_dividend_feed_covered,
            completeness_low=card.completeness_low,
            computable_low=card.computable_low,
            any_sector_ranked=bool(board.ranked),
        )
    )

    lookback = board.lookback_days if board is not None else definition.lookback_days
    holding = board.holding_days if board is not None else definition.holding_days
    bars_days = tuple(
        sorted(day for day in ok_sessions["bars"] if board is None or day <= board.data_as_of)
    )
    outcome = gate.evaluate(
        GateInputs(
            definition=definition,
            data_source=data_source,
            board_method_version=board.method_version if board is not None else None,
            board_invariant_violated=(
                board.constituent_invariant_violated if board is not None else False
            ),
            as_of_session=board.data_as_of if board is not None else None,
            calendar=TradingCalendar(ok_sessions["bars"]),
            fee_verified_on=runtime.fee_verified_on,
            de5_verified_on=runtime.de5_verified_on,
            ci_passed_commit=runtime.ci_passed_commit,
            pit_status=PitStatus(
                accumulation_start=read.accumulation_start,
                ok_sessions={
                    "listing": ok_sessions["listing"],
                    "classification": ok_sessions["classification"],
                    "dividend_announce": ok_sessions["dividend_announce"],
                },
            ),
            window=gate.judged_window(bars_days, read.accumulation_start, holding),
            stats_history=read.stats_history,
            approvals=read.approvals,
            stats_rejected=read.stats_rejected is not None,
        )
    )
    if read.stats_rejected is not None:
        logger.error("sector card: statistics refused on read: %s", read.stats_rejected)
    for error in outcome.internal_errors:
        logger.error("sector card: gate internal error %s", error)

    if insufficient is not None:
        main, detail = wording.INSUFFICIENT_SENTENCES[insufficient]
        values = _insufficient_values(insufficient, card, excluded_codes, definition)
        reason: str | None = wording.fill(main, values, lookback_days=lookback)
        disclosures = [wording.fill(detail, values, lookback_days=lookback)]
    else:
        reason = None
        disclosures = _standing_disclosures(board, card, lookback)

    return SectorMomentumPayload(
        market=market,
        status="insufficient_data" if insufficient is not None else "ok",
        insufficient_reason=insufficient,
        reason=reason,
        method_version=board.method_version if board is not None else definition.method_version,
        lookback_days=lookback,
        holding_days=holding,
        data_as_of=board.data_as_of.isoformat() if board is not None else None,
        market_scope=definition.market_scope,
        benchmark=definition.benchmark,
        data_source=data_source,
        coverage=card.coverage if card is not None else None,
        min_constituents=rules.min_constituents,
        sector_coverage_threshold=rules.sector_coverage_threshold,
        overall_coverage_threshold=rules.overall_coverage_threshold,
        computable_ratio=card.computable_ratio if card is not None else None,
        computable_ratio_min=rules.computable_ratio_min,
        computable_ratio_pct_display=card.computable_ratio_pct_display if card else None,
        completeness_pct_display=card.completeness_pct_display if card else None,
        market_expected_count=card.market_expected_count if card else None,
        market_missing_count=card.market_missing_count if card else None,
        market_ex_date_excluded_count=card.market_ex_date_excluded_count if card else None,
        market_corporate_action_excluded_count=(
            card.market_corporate_action_excluded_count if card else None
        ),
        market_ex_date_excluded_ratio=card.market_ex_date_excluded_ratio if card else None,
        ex_date_tag_ratio_min=rules.ex_date_tag_ratio_min,
        ex_date_tag=coverage.ex_date_tag(card, excluded_codes) if card is not None else False,
        excluded_reason_counts=(
            coverage.excluded_reason_counts(excluded_codes)
            if insufficient == "no_sector_computable"
            else None
        ),
        headline_count=HEADLINE_COUNT,
        sectors=[] if insufficient or board is None else _sector_items(board, held),
        excluded_sectors=[] if insufficient or board is None else _excluded_items(board),
        disclosures=disclosures,
        data=_data_meta(board, ok_sessions["bars"], now=now),
        as_of=now.isoformat(),
        **gate.response_fields(outcome, insufficient=insufficient is not None),
    )


def _standing_disclosures(
    board: StoredBoard | None, card: CardAssessment | None, lookback: int
) -> list[str]:
    """The ok card's 「詳細」 sentences, numbers bound to the response's own fields."""
    if board is None or card is None:  # unreachable: no board is as_of_unknown
        raise ValueError("an ok sector card needs a board")
    return wording.standing_disclosures(
        lookback_days=lookback,
        market_expected_count=card.market_expected_count,
        market_missing_count=card.market_missing_count,
        market_ex_date_excluded_count=card.market_ex_date_excluded_count,
        market_corporate_action_excluded_count=card.market_corporate_action_excluded_count,
        has_taiex_reference=board.reference_taiex_return_L is not None,
    )


def usable_board(board: StoredBoard | None) -> StoredBoard | None:
    """``None`` for a board with no expected stock at all (risk R-5).

    With |E_M| = 0 no market data was taken in, so the board's date says
    nothing about any close; the card reads as having no usable board and
    reports ① ``as_of_unknown`` -- never ⑤ with 「成分股不足 0 個」.
    """
    if board is not None and board.market_expected_count <= 0:
        logger.warning("sector card: board %s has no expected stock; ignored", board.board_id)
        return None
    return board


def _insufficient_values(
    reason: InsufficientReason,
    card: CardAssessment | None,
    excluded_codes: Collection[ReasonCode],
    definition: SectorMomentumDefinition,
) -> dict[str, object]:
    """Each sentence's own numbers (C-44: ③④⑤ never share a ratio or threshold)."""
    rules = definition.coverage
    if card is None:
        return {}
    if reason == "overall_completeness_low" and card.completeness_pct_display is not None:
        return {
            "x": wording.display_pct(card.completeness_pct_display),
            "門檻": wording.threshold_pct(rules.overall_coverage_threshold),
            "e": card.market_expected_count,
            "a": card.market_missing_count,
        }
    if reason == "computable_ratio_low" and card.computable_ratio_pct_display is not None:
        return {
            "x": wording.display_pct(card.computable_ratio_pct_display),
            "門檻": wording.threshold_pct(rules.computable_ratio_min),
            "e": card.market_expected_count,
            "a": card.market_missing_count,
            "b": card.market_ex_date_excluded_count,
            "c": card.market_corporate_action_excluded_count,
        }
    if reason == "no_sector_computable":
        counts = coverage.excluded_reason_counts(excluded_codes)
        return {
            "最小數": rules.min_constituents,
            "族群門檻": wording.threshold_pct(rules.sector_coverage_threshold),
            "n1": counts.too_few_members,
            "n2": counts.low_coverage,
            "n3": counts.ex_dividend_exclusion,
        }
    return {}


def _sector_items(board: StoredBoard, held: frozenset[str] | None) -> list[SectorItem]:
    return [
        SectorItem(
            rank=row.rank,
            sector_code=row.sector_code,
            sector_name=row.sector_name,
            sector_return_L=row.sector_return_L,
            benchmark_return_L=board.benchmark_return_L,
            rel_return_L=row.rel_return_L,
            up_count=row.up_count,
            constituent_count=row.constituent_count,
            turnover_value_ratio_5_20=row.turnover_value_ratio_5_20,
            reference_taiex_return_L=board.reference_taiex_return_L,
            coverage=row.coverage,
            top_contributor_share=row.top_contributor_share,
            single_stock_dominated=row.single_stock_dominated,
            constituents=[
                ConstituentItem(
                    symbol=item.symbol,
                    name=item.name,
                    return_L=item.return_L,
                    held=(item.symbol in held) if held is not None else None,
                )
                for item in row.constituents
            ],
        )
        for row in board.ranked
    ]


def _excluded_items(board: StoredBoard) -> list[ExcludedSector]:
    return [
        ExcludedSector(
            sector_code=row.sector_code,
            sector_name=row.sector_name,
            reason_code=row.reason_code,
            computable_count=row.computable_count,
            expected_count=row.expected_count,
            coverage=row.coverage,
        )
        for row in board.excluded
    ]


def _data_meta(
    board: StoredBoard | None, bars_sessions: frozenset[date], *, now: datetime
) -> DataMeta:
    """``DataMeta`` reused unchanged, mapped as ADR-0012 D-10 lists."""
    if board is None:
        return DataMeta(
            status="unavailable",
            source=NO_SOURCE,
            staleness_minutes=None,
            is_within_ttl=None,
            bar_count=0,
            first_bar_date=None,
            last_bar_date=None,
            trading_days_behind=None,
            reason=None,
        )
    staleness: int | None = None
    if board.bars_recorded_at is not None:
        recorded = datetime.fromisoformat(board.bars_recorded_at)
        if recorded.tzinfo is not None:
            staleness = max(0, int((now - recorded).total_seconds() // 60))
    today = now.astimezone(TAIPEI).date()
    window = sorted(
        day
        for day in bars_sessions
        if board.window_start is not None and board.window_start <= day <= board.data_as_of
    )
    return DataMeta(
        status="cached_stale",
        source=board.data_source,
        staleness_minutes=staleness,
        is_within_ttl=board.data_as_of >= expected_session(TW_POLICY, requested_end=today, now=now),
        bar_count=len(window),
        first_bar_date=board.window_start.isoformat() if board.window_start else None,
        last_bar_date=board.data_as_of.isoformat(),
        trading_days_behind=trading_days_behind(bars_sessions, board.data_as_of, today),
        reason=None,
    )


def trading_days_behind(sessions: Collection[date], last: date, today: date) -> int | None:
    """Observed ``ok`` bars sessions after ``last`` (C4 semantics; ``None`` = cannot judge).

    The same rule as ``app.services.market.trading_days_behind_market`` over the
    market DB's own calendar (that module may not be imported here, C-5):
    ``None`` when nothing was observed in ``[last, today]``, else the observed
    sessions strictly after ``last`` -- never the weekday fallback.
    """
    observed = [day for day in sessions if last <= day <= today]
    if not observed:
        return None
    return TradingCalendar(observed).observed_days_after(last)
