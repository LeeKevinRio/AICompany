"""``is_within_ttl`` from the data layer to the snapshots, untouched (ADR-0040 Decision 3).

QB-4(b): the value is only ever copied -- ``ProviderResult`` → ``LoadedBars`` /
``LoadedBenchmark`` → ``LoadedSeries`` → ``MarketSnapshot`` / ``IndexSnapshot`` --
on the real ladders (QB-7). QB-2: ``LoadedBenchmark.meta()`` does not grow.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.playbook.service import NOTHING_LOADED, build_index_snapshot, build_market_snapshot
from app.services.index import LoadedBenchmark, load_market_benchmark
from tests import playbook_helpers as helper
from tests.n190_helpers import MON, TUE, build


def test_the_loaded_series_and_the_snapshots_carry_what_the_ladder_said(tmp_path: Path) -> None:
    rig = build(tmp_path, {"2330": "100"})
    rig.warm(["2330"], MON)
    rig.at(TUE, 10)  # before the cutoff: Monday is the latest session, the cache has it

    series = rig.desk._load_symbol_bars(["2330"], today=TUE)["2330"]
    index = rig.desk._load_index_bars(today=TUE)

    stock_load, index_load = rig.last_load("2330"), rig.last_load("^TWII")
    assert (series.status, series.is_within_ttl) == ("cached_stale", True)
    assert (index.status, index.is_within_ttl) == ("cached_stale", True)
    assert series.is_within_ttl is stock_load.is_within_ttl
    assert index.is_within_ttl is index_load.is_within_ttl

    snapshot = build_market_snapshot(
        "2330",
        series.bars,
        status=series.status,
        source=series.source,
        is_within_ttl=series.is_within_ttl,
    )
    index_snapshot = build_index_snapshot(
        index.bars,
        status=index.status,
        source=index.source,
        params=helper.params(),
        is_within_ttl=index.is_within_ttl,
    )
    assert snapshot is not None and snapshot.is_within_ttl is True
    assert index_snapshot is not None and index_snapshot.is_within_ttl is True


def test_a_live_answer_and_nothing_loaded_carry_no_ttl(tmp_path: Path) -> None:
    rig = build(tmp_path, {"2330": "100"})
    rig.at(TUE, 16)
    series = rig.desk._load_symbol_bars(["2330"], today=TUE)["2330"]
    index = rig.desk._load_index_bars(today=TUE)
    assert (series.status, series.is_within_ttl) == ("fresh", None)
    assert (index.status, index.is_within_ttl) == ("backup", None)
    assert NOTHING_LOADED.is_within_ttl is None
    assert build_market_snapshot("2330", [], status="fresh", source="twse") is None


class _Answer:
    """A ``PriceService`` returning one fixed ``ProviderResult`` -- the unit under test is
    ``load_market_benchmark`` alone, so no ladder is involved."""

    def __init__(self, result: ProviderResult) -> None:
        self.result = result

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        return self.result

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        return self.result


@pytest.mark.parametrize("ttl", [True, False, None])
def test_load_market_benchmark_copies_the_ttl_on_both_branches_with_a_result(
    ttl: bool | None,
) -> None:
    """(x1): the bars branch and the unavailable branch copy ``result.is_within_ttl``."""
    bars = [
        PriceBar(
            symbol="^TWII",
            market="TW",
            date=date(2026, 8, day),
            open=Decimal("20000"),
            high=Decimal("20000"),
            low=Decimal("20000"),
            close=Decimal("20000"),
            volume=1,
            currency="TWD",
            as_of=datetime(2026, 1, 1, tzinfo=UTC),
            source="yfinance",
        )
        for day in (10, 11)
    ]
    as_of = datetime(2026, 1, 1, tzinfo=UTC)
    cached = ProviderResult(
        bars=bars,
        status=DataStatus.CACHED_STALE,
        as_of=as_of,
        source="yfinance",
        is_within_ttl=ttl,
    )
    empty = ProviderResult(
        bars=[], status=DataStatus.UNAVAILABLE, as_of=as_of, source="none", is_within_ttl=ttl
    )
    start = date(2026, 6, 1)
    loaded = load_market_benchmark({"TW": _Answer(cached)}, market="TW", start=start, end=TUE)
    assert loaded.bars and loaded.is_within_ttl is ttl
    missing = load_market_benchmark({"TW": _Answer(empty)}, market="TW", start=start, end=TUE)
    assert not missing.bars and missing.is_within_ttl is ttl


def test_meta_does_not_publish_the_ttl() -> None:
    """QB-2 / Options 三 (x3): the API block is unchanged."""
    assert set(LoadedBenchmark(is_within_ttl=True).meta()) == {
        "series_symbol",
        "label",
        "available",
        "status",
        "source",
        "staleness_minutes",
        "bar_count",
        "reason",
        "notes",
    }
