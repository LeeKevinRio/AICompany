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
    assert result.is_within_ttl is True


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
    cache = PriceBarCache(db_path=tmp_path / "cache.db", ttl_seconds=60 * 60)
    fetched_at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    cache.put([_bar()], source="twse", fetched_at=fetched_at)

    now = fetched_at + timedelta(minutes=90)
    result = cache.get("2330", "TW", date(2024, 1, 1), date(2024, 1, 31), now=now)
    assert result is not None
    assert result.staleness_minutes == 90
    assert result.is_within_ttl is False  # 90 min > 60 min TTL


def test_within_ttl_true_when_fresh_enough(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db", ttl_seconds=24 * 60 * 60)
    fetched_at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    cache.put([_bar()], source="twse", fetched_at=fetched_at)

    now = fetched_at + timedelta(hours=2)
    result = cache.get("2330", "TW", date(2024, 1, 1), date(2024, 1, 31), now=now)
    assert result is not None
    assert result.is_within_ttl is True


def test_get_filters_by_symbol_and_market(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar(symbol="2330")], source="twse")
    cache.put([_bar(symbol="5483")], source="tpex")

    result = cache.get("5483", "TW", date(2024, 1, 1), date(2024, 1, 31))
    assert result is not None
    assert {bar.symbol for bar in result.bars} == {"5483"}
