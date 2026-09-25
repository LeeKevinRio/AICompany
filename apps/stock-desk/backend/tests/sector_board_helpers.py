"""Synthetic markets written into a real market DB, for the services / API / scheduler tests.

:func:`store_market` replays a :class:`tests.sector_eval_helpers.SyntheticMarket`
into :class:`app.data.market_panel.MarketPanelStore` through the store's own
write API, run by run in ``recorded_at`` order, with the store's injectable
clock set to each run's ``recorded_at`` -- the same way the daily capture would
have written it (``recorded_at`` is never a caller argument, C-10). Run ids
become the store's integers; everything else survives the round trip exactly
(prices are written as the decimal they print as).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.data.interface import (
    BarSnapshotRow,
    ClassificationSnapshotRow,
    DividendAnnounceSnapshotRow,
    ListingSnapshotRow,
    SnapshotKind,
)
from app.data.market_panel import MarketPanelReader, MarketPanelStore
from app.positions.store import PositionStore
from app.sectors.coverage import coverage_from_counts
from app.sectors.models import ReasonCode, StatsRecord
from app.sectors.store import (
    SectorCardReader,
    StoredBoard,
    StoredConstituent,
    StoredExcludedSector,
    StoredRankedSector,
)
from app.services.sector_runtime import SectorGateRuntime
from tests.sector_eval_helpers import SyntheticMarket


def _decimal(value: object) -> Decimal:
    return Decimal(repr(float(value)))  # type: ignore[arg-type]


def _groups(frame: pd.DataFrame) -> Mapping[str, pd.DataFrame]:
    return {str(run_id): rows for run_id, rows in frame.groupby("run_id", sort=False)}


def store_market(market: SyntheticMarket, path: Path) -> MarketPanelStore:
    """Write every run of ``market`` into a fresh market DB at ``path``."""
    clock = {"now": datetime(2000, 1, 1, tzinfo=UTC)}
    store = MarketPanelStore(path, clock=lambda: clock["now"])
    frames = market.panel.frames
    bars, listing = _groups(frames.bars), _groups(frames.listing)
    classes, dividends = _groups(frames.classification), _groups(frames.ex_dividend)
    empty = pd.DataFrame()
    runs = frames.runs.sort_values(["recorded_at", "run_id"], kind="mergesort")
    for run in runs.itertuples(index=False):
        run_id = str(run.run_id)
        clock["now"] = pd.Timestamp(run.recorded_at).to_pydatetime()
        kind = str(run.kind)
        common = {
            "kind": kind,
            "session_date": run.session_date,
            "source": str(run.source),
            "status": str(run.status),
            "expected_count": int(run.expected_count),
        }
        if kind == "bars":
            rows = [
                BarSnapshotRow(
                    symbol=str(row.symbol),
                    open=_decimal(row.open),
                    high=_decimal(row.high),
                    low=_decimal(row.low),
                    close=_decimal(row.close),
                    shares=int(row.shares),
                    traded_value=_decimal(row.traded_value),
                    change=None if math.isnan(float(row.change)) else _decimal(row.change),
                )
                for row in bars.get(run_id, empty).itertuples(index=False)
            ]
            store.record_run(**common, row_count=len(rows), bars_rows=rows)  # type: ignore[arg-type]
        elif kind == "listing":
            listed = [
                ListingSnapshotRow(symbol=str(row.symbol), security_type=str(row.security_type))
                for row in listing.get(run_id, empty).itertuples(index=False)
            ]
            store.record_run(**common, row_count=len(listed), listing_rows=listed)  # type: ignore[arg-type]
        elif kind == "classification":
            classified = [
                ClassificationSnapshotRow(
                    symbol=str(row.symbol),
                    sector_code=str(row.sector_code),
                    sector_name=str(row.sector_name),
                )
                for row in classes.get(run_id, empty).itertuples(index=False)
            ]
            store.record_run(  # type: ignore[arg-type]
                **common, row_count=len(classified), classification_rows=classified
            )
        else:
            announced = [
                DividendAnnounceSnapshotRow(
                    symbol=str(row.symbol),
                    ex_date=row.ex_date,
                    raw={"Date": row.ex_date.isoformat(), "Code": str(row.symbol)},
                )
                for row in dividends.get(run_id, empty).itertuples(index=False)
            ]
            store.record_run(  # type: ignore[arg-type]
                **common, row_count=len(announced), dividend_announce_rows=announced
            )
    return store


def stats_record(run_id: str, source_run_ids: tuple[str, ...], **overrides: object) -> StatsRecord:
    """A well-formed forward point-in-time statistics row (G1..G6 all passing)."""
    import dataclasses

    from app.sectors.definition import SECTOR_MOMENTUM_V1
    from app.sectors.models import GateCheckRecord

    base = StatsRecord(
        run_id=run_id,
        method_version=SECTOR_MOMENTUM_V1.method_version,
        regime="pit",
        data_regime="forward_pit",
        source_run_ids=source_run_ids,
        m_at_evaluation=1,
        sample_count=160,
        effective_sample_count=120.0,
        beat_count_net=110,
        beat_count_gross=118,
        base_rate_net=0.48,
        base_rate_gross=0.52,
        ci_low_net=0.60,
        ci_high_net=0.75,
        bootstrap_low_net=0.61,
        bootstrap_high_net=0.74,
        delta_real=20.75,
        delta_shuffle=3.5,
        sample_start=date(2026, 1, 5),
        sample_end=date(2029, 3, 5),
        stats_as_of=date(2029, 3, 12),
        computed_at=datetime(2029, 3, 12, 14, tzinfo=UTC),
        recompute_session=date(2029, 3, 12),
        running_commit="c0ffee",
        selfcheck_passed=True,
        data_quality_passed=True,
        pit_history_missing=False,
        gate_checks=tuple(
            GateCheckRecord(gate=name, passed=True) for name in ("G1", "G2", "G3", "G4", "G5", "G6")
        ),
    )
    return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Card fixtures for the API tests
# ---------------------------------------------------------------------------


def verified_runtime(commit: str | None = "c0ffee") -> SectorGateRuntime:
    """A verified runtime whose deployed commit matches :func:`stats_record`'s rows."""
    return SectorGateRuntime(
        ci_passed_commit=commit,
        fee_verified_on=date(2026, 9, 1),
        de5_verified_on=date(2026, 9, 1),
    )


def weekdays_between(first: date, last: date) -> list[date]:
    from datetime import timedelta

    days: list[date] = []
    cursor = first
    while cursor <= last:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def ok_map(days: Collection[date]) -> dict[SnapshotKind, frozenset[date]]:
    """Every kind ``ok`` on every one of ``days`` (what a healthy market DB reports)."""
    every = frozenset(days)
    return {kind: every for kind in ("bars", "listing", "classification", "dividend_announce")}


def ranked_sector(
    rank: int, code: str, *, members: int = 8, sector_return: float = 0.01
) -> StoredRankedSector:
    symbols = tuple(f"{code}{i:02d}" for i in range(members))
    return StoredRankedSector(
        rank=rank,
        sector_code=code,
        sector_name=f"產業{code}",
        sector_return_L=sector_return,
        rel_return_L=sector_return - 0.002,
        up_count=members // 2,
        coverage=coverage_from_counts(expected=members, missing=0, ex_date=0, corporate_action=0),
        turnover_value_ratio_5_20=1.1,
        top_contributor_share=0.3,
        single_stock_dominated=False,
        member_symbols=symbols,
        constituents=tuple(
            StoredConstituent(symbol=symbol, name=f"公司{symbol}", return_L=0.02 - 0.01 * i)
            for i, symbol in enumerate((symbols[0], symbols[1], symbols[-1]))
        ),
    )


def excluded_sector(
    code: str, reason: ReasonCode, *, expected: int = 6, missing: int = 0, ex_date: int = 0
) -> StoredExcludedSector:
    return StoredExcludedSector(
        sector_code=code,
        sector_name=f"產業{code}",
        reason_code=reason,
        coverage=coverage_from_counts(
            expected=expected, missing=missing, ex_date=ex_date, corporate_action=0
        ),
        internal_reason=None,
    )


def make_board(
    *,
    data_as_of: date,
    ranked: Sequence[StoredRankedSector] = (),
    excluded: Sequence[StoredExcludedSector] = (),
    expected: int = 1000,
    missing: int = 5,
    ex_date: int = 10,
    corporate_action: int = 0,
    feed_covered: bool = True,
    data_source: str = "twse_snapshot",
    taiex: float | None = None,
    lookback_days: int = 5,
) -> StoredBoard:
    from datetime import timedelta

    from app.sectors.definition import SECTOR_MOMENTUM_V1

    window = weekdays_between(data_as_of - timedelta(days=12), data_as_of)[-(lookback_days + 1) :]
    return StoredBoard(
        board_id="board-1",
        market="TW",
        method_version=SECTOR_MOMENTUM_V1.method_version,
        lookback_days=lookback_days,
        holding_days=5,
        data_as_of=data_as_of,
        window_start=window[0],
        data_source=data_source,
        bars_run_id="41",
        bars_recorded_at=datetime.combine(data_as_of, datetime.min.time(), tzinfo=UTC)
        .replace(hour=10)
        .isoformat(),
        computed_at="2029-03-12T10:05:00+00:00",
        benchmark_return_L=0.004,
        reference_taiex_return_L=taiex,
        market_expected_count=expected,
        market_missing_count=missing,
        market_ex_date_excluded_count=ex_date,
        market_corporate_action_excluded_count=corporate_action,
        ex_dividend_feed_covered=feed_covered,
        constituent_invariant_violated=False,
        source_run_ids=("41",),
        ranked=tuple(ranked),
        excluded=tuple(excluded),
    )


@contextmanager
def card_client(
    *,
    main_db: Path,
    market_db: Path,
    positions: PositionStore,
    runtime: SectorGateRuntime,
    now: datetime,
) -> Iterator[TestClient]:
    """``TestClient`` on the real app with the card's dependencies on temp files.

    The readers are built here, before any request, so a statement counter
    installed afterwards sees only what one request runs.
    """
    from app.api.deps import get_position_store
    from app.api.sectors import (
        SectorCardSources,
        get_sector_card_sources,
        get_sector_clock,
        get_sector_gate_runtime,
    )
    from app.main import app

    market = MarketPanelReader(market_db)
    sources = SectorCardSources(
        card=SectorCardReader(verifier=market, db_path=main_db), market=market
    )
    overrides: dict[Callable[..., object], Callable[..., object]] = {
        get_sector_card_sources: lambda: sources,
        get_sector_gate_runtime: lambda: runtime,
        get_position_store: lambda: positions,
        get_sector_clock: lambda: lambda: now,
    }
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


@dataclass(frozen=True)
class LiveCard:
    """A market DB, a main DB with a board, statistics, an approval and D0, and positions."""

    main_db: Path
    market_db: Path
    positions: PositionStore
    sectors: int


def live_card(tmp_path: Path, sector_count: int, *, now: datetime) -> LiveCard:
    """Everything the endpoint reads, built through the real stores and service."""
    from decimal import Decimal as D

    from app.positions.models import PositionInput
    from app.sectors.definition import SECTOR_MOMENTUM_V1
    from app.sectors.models import ApprovalRecord
    from app.sectors.store import (
        SectorApprovalStore,
        SectorMethodRegistry,
        SectorStatsRepository,
    )
    from app.services.sector_board import SectorBoardService
    from tests.sector_eval_helpers import synthetic_market

    sizes = {f"{10 + i:02d}": 5 + (i % 3) for i in range(sector_count)}
    market = synthetic_market(seed=3, sectors=sizes, warmup=62, forward=30, n_dividends=2)
    market_db, main_db = tmp_path / "market.db", tmp_path / "main.db"
    store = store_market(market, market_db)
    registry = SectorMethodRegistry(main_db)
    registry.register(SECTOR_MOMENTUM_V1, frozen_commit="c0ffee", registered_at=now)
    SectorBoardService(market_store=store, main_db=main_db, clock=lambda: now).refresh_board(
        market.calendar[-1]
    )
    frames = store.load_panel_frames(market.calendar[0], market.calendar[-1])
    run_ids = tuple(sorted(frames.runs["run_id"])[:5])
    SectorStatsRepository(MarketPanelReader(market_db), main_db).save(
        stats_record("stats-1", run_ids, recompute_session=market.calendar[-1])
    )
    SectorApprovalStore(main_db).add(
        ApprovalRecord(
            kind="first_transition_risk",
            run_id="stats-1",
            method_version=SECTOR_MOMENTUM_V1.method_version,
            operator="ceo",
            reviewer="risk-compliance-officer",
            review_doc_path="work/reviews/x.md",
            review_doc_blob_hash="0" * 40,
            approved_at=now,
        )
    )
    registry.record_accumulation_start(SECTOR_MOMENTUM_V1.method_version, market.d0)
    positions = PositionStore(tmp_path / "positions.db")
    positions.create(
        PositionInput(
            symbol=market.members[next(iter(sizes))][0],
            market="TW",
            quantity=D(1000),
            avg_cost=D(50),
            currency="TWD",
            opened_at=None,
            instrument_type="stock",
        )
    )
    return LiveCard(main_db=main_db, market_db=market_db, positions=positions, sectors=sector_count)
