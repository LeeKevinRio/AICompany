"""Tests for the SQLite (WAL mode) price bar cache."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.data.cache import PriceBarCache
from app.data.interface import PriceBar


def _bar(symbol: str = "2330", trade_date: date = date(2024, 1, 2)) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market="TW",
        date=trade_date,
        open=Decimal("594.00"),
        high=Decimal("598.00"),
        low=Decimal("590.00"),
        close=Decimal("594.00"),
        volume=41_393_088,
        currency="TWD",
        as_of=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
        source="twse",
    )


def test_db_is_created_in_wal_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    PriceBarCache(db_path=db_path)
    conn = sqlite3.connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_put_then_get_round_trips_bar_fields(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    bar = _bar()
    fetched_at = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)
    cache.put([bar], source="twse", fetched_at=fetched_at)

    result = cache.get("2330", "TW", date(2024, 1, 1), date(2024, 1, 31), now=fetched_at)
    assert result is not None
    assert len(result.bars) == 1
    got = result.bars[0]
    assert got.symbol == bar.symbol
    assert got.open == bar.open
    assert got.high == bar.high
    assert got.low == bar.low
    assert got.close == bar.close
    assert got.volume == bar.volume
    assert got.currency == bar.currency
    assert result.source == "twse"
    assert result.staleness_minutes == 0


def test_get_returns_none_when_no_rows_in_range(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    result = cache.get("2330", "TW", date(2024, 1, 1), date(2024, 1, 31))
    assert result is None


def test_put_upserts_existing_row(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    bar_v1 = _bar()
    cache.put([bar_v1], source="twse", fetched_at=datetime(2024, 1, 2, 10, 0, tzinfo=UTC))
    bar_v2 = bar_v1.model_copy(update={"close": Decimal("601.00")})
    cache.put([bar_v2], source="twse", fetched_at=datetime(2024, 1, 2, 16, 0, tzinfo=UTC))

    result = cache.get("2330", "TW", date(2024, 1, 1), date(2024, 1, 31))
    assert result is not None
    assert len(result.bars) == 1
    assert result.bars[0].close == Decimal("601.00")


def test_staleness_minutes_computed_from_fetched_at(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    fetched_at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    cache.put([_bar()], source="twse", fetched_at=fetched_at)

    now = fetched_at + timedelta(minutes=90)
    result = cache.get("2330", "TW", date(2024, 1, 1), date(2024, 1, 31), now=now)
    assert result is not None
    assert result.staleness_minutes == 90


# --- ADR-0009: fetch coverage and attempt log --------------------------------------


def test_fetch_coverage_is_none_until_a_complete_live_fetch_is_recorded(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar()], source="twse")
    assert cache.fetch_coverage("2330", "TW") is None
    at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    cache.record_fetch("2330", "TW", start=date(2024, 1, 1), end=date(2024, 1, 31), fetched_at=at)
    coverage = cache.fetch_coverage("2330", "TW")
    assert coverage is not None
    assert (coverage.covered_start, coverage.covered_end) == (date(2024, 1, 1), date(2024, 1, 31))
    assert coverage.last_fetched_at == at


def test_overlapping_or_touching_ranges_widen_the_coverage(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.record_fetch("2330", "TW", start=date(2024, 1, 1), end=date(2024, 1, 31))
    cache.record_fetch("2330", "TW", start=date(2024, 2, 1), end=date(2024, 2, 29))  # touches
    cache.record_fetch("2330", "TW", start=date(2023, 6, 1), end=date(2024, 1, 15))  # overlaps
    coverage = cache.fetch_coverage("2330", "TW")
    assert coverage is not None
    assert (coverage.covered_start, coverage.covered_end) == (date(2023, 6, 1), date(2024, 2, 29))


def test_a_disjoint_range_replaces_the_coverage_instead_of_bridging_the_gap(
    tmp_path: Path,
) -> None:
    # qa 2026-09-13: MIN/MAX over 2020 and 2024 would claim 2021-2023 was fetched.
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.record_fetch("2330", "TW", start=date(2020, 1, 1), end=date(2020, 6, 30))
    cache.record_fetch("2330", "TW", start=date(2024, 1, 1), end=date(2024, 6, 30))
    coverage = cache.fetch_coverage("2330", "TW")
    assert coverage is not None
    assert (coverage.covered_start, coverage.covered_end) == (date(2024, 1, 1), date(2024, 6, 30))


def test_coverage_is_per_series(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.record_fetch("2330", "TW", start=date(2024, 1, 1), end=date(2024, 1, 31))
    assert cache.fetch_coverage("2330", "US") is None
    assert cache.fetch_coverage("2317", "TW") is None


def test_attempt_log_records_the_latest_ask(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    assert cache.last_attempt_at("2330", "TW") is None
    first = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    cache.record_attempt("2330", "TW", at=first)
    cache.record_attempt("2330", "TW", at=first + timedelta(hours=1))
    assert cache.last_attempt_at("2330", "TW") == first + timedelta(hours=1)


def test_deleting_a_source_forgets_the_affected_series_logs(tmp_path: Path) -> None:
    # ADR-0009 R-5: rows gone, coverage claim gone; other series untouched.
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar(symbol="2330")], source="demo_synthetic")
    cache.put([_bar(symbol="2317")], source="twse")
    for symbol in ("2330", "2317"):
        cache.record_fetch(symbol, "TW", start=date(2024, 1, 1), end=date(2024, 1, 31))
        cache.record_attempt(symbol, "TW")
    assert cache.delete_by_source("demo_synthetic") == 1
    assert cache.fetch_coverage("2330", "TW") is None
    assert cache.last_attempt_at("2330", "TW") is None
    assert cache.fetch_coverage("2317", "TW") is not None
    assert cache.last_attempt_at("2317", "TW") is not None


def test_get_filters_by_symbol_and_market(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar(symbol="2330")], source="twse")
    cache.put([_bar(symbol="5483")], source="tpex")

    result = cache.get("5483", "TW", date(2024, 1, 1), date(2024, 1, 31))
    assert result is not None
    assert {bar.symbol for bar in result.bars} == {"5483"}


def test_delete_by_source_removes_only_that_writers_rows(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar(symbol="2330")], source="twse")
    cache.put([_bar(symbol="9999")], source="demo_synthetic")

    assert cache.delete_by_source("demo_synthetic") == 1

    assert cache.get("9999", "TW", date(2024, 1, 1), date(2024, 1, 31)) is None
    assert cache.get("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)) is not None


def test_delete_by_source_is_zero_when_nothing_matches(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar()], source="twse")

    assert cache.delete_by_source("demo_synthetic") == 0


def test_find_foreign_bars_reports_rows_another_source_owns(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar(trade_date=date(2024, 1, 2))], source="twse")

    conflicts = cache.find_foreign_bars(
        [_bar(trade_date=date(2024, 1, 2)), _bar(trade_date=date(2024, 1, 3))],
        source="demo_synthetic",
    )

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert (conflict.symbol, conflict.market) == ("2330", "TW")
    assert conflict.trade_date == date(2024, 1, 2)
    assert conflict.source == "twse"


def test_find_foreign_bars_ignores_rows_the_same_source_owns(tmp_path: Path) -> None:
    """Re-seeding over its own rows is a refresh, not a conflict."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar()], source="demo_synthetic")

    assert cache.find_foreign_bars([_bar()], source="demo_synthetic") == []


def test_find_foreign_bars_ignores_other_symbols_and_dates(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar(symbol="2412", trade_date=date(2024, 1, 2))], source="twse")
    cache.put([_bar(symbol="2330", trade_date=date(2024, 1, 5))], source="twse")

    assert (
        cache.find_foreign_bars(
            [_bar(symbol="2330", trade_date=date(2024, 1, 2))], source="demo_synthetic"
        )
        == []
    )


def test_find_foreign_bars_chunks_beyond_the_sqlite_parameter_limit(tmp_path: Path) -> None:
    """A multi-year batch is probed in chunks instead of failing at the driver."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    bars = [_bar(trade_date=date(2024, 1, 1) + timedelta(days=offset)) for offset in range(1200)]
    cache.put(bars[::2], source="twse")

    conflicts = cache.find_foreign_bars(bars, source="demo_synthetic")

    assert len(conflicts) == 600
    assert [conflict.trade_date for conflict in conflicts] == sorted(
        conflict.trade_date for conflict in conflicts
    )
