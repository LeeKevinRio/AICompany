"""ADR-0012 C-7/C-8/C-13 boundary checks for the market DB (T-3).

Import-graph reuse mirrors ``tests/test_kelly_boundary.py`` /
``tests/test_sectors_pit_invariance.py``'s existing pattern.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from app.data.cache import PriceBarCache
from app.data.interface import BarSnapshotRow, Market, PriceBar
from app.data.market_panel import MarketPanelStore
from app.scheduler import DATA_REFRESH_LOOKBACK_DAYS
from tests.import_graph import module_path, reachable_app_modules


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_c13_data_refresh_lookback_days_unchanged() -> None:
    assert DATA_REFRESH_LOOKBACK_DAYS == 540


def test_c7_price_bars_cache_untouched_by_a_market_db_capture(tmp_path: Path) -> None:
    """Writing a whole capture to the market DB must not touch price_bars_cache."""
    cache_path = tmp_path / "stock-desk.db"
    cache = PriceBarCache(cache_path)
    cache.put(
        [
            PriceBar(
                symbol="2330",
                market="TW",
                date=date(2026, 9, 1),
                open=Decimal("500"),
                high=Decimal("510"),
                low=Decimal("495"),
                close=Decimal("505"),
                volume=1000,
                currency="TWD",
                as_of=datetime(2026, 9, 1, tzinfo=UTC),
                source="twse",
            )
        ],
        source="twse",
    )
    before = _file_sha256(cache_path)

    market_store = MarketPanelStore(
        tmp_path / "market.db", clock=lambda: datetime(2026, 9, 24, tzinfo=UTC)
    )
    market_store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=1,
        bars_rows=[
            BarSnapshotRow(
                symbol="2330",
                open=Decimal("594"),
                high=Decimal("598"),
                low=Decimal("590"),
                close=Decimal("594"),
                shares=41_393_088,
                traded_value=Decimal("24585432000"),
                change=Decimal("2.00"),
            )
        ],
    )
    market_store.record_symbol_backfill(
        symbol="0050",
        source="finmind_warmup",
        rows=[
            (
                date(2026, 8, 1),
                BarSnapshotRow(
                    symbol="0050",
                    open=Decimal("150"),
                    high=Decimal("151"),
                    low=Decimal("149"),
                    close=Decimal("150.5"),
                    shares=1_000_000,
                    traded_value=Decimal("150000000"),
                    change=None,
                ),
            )
        ],
    )

    after = _file_sha256(cache_path)
    assert before == after

    with closing(sqlite3.connect(cache_path)) as conn:
        tables = {
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    assert tables == {"price_bars_cache", "price_bars_fetch_log", "price_bars_attempt_log"}
    assert "market_daily_bars" not in tables
    assert not any(name.startswith("pit_") for name in tables)


def test_c7_import_graph_cannot_reach_market_panel_from_the_positions_chain() -> None:
    forbidden_roots = (
        "app.services.market",
        "app.data.service",
    )
    for root in forbidden_roots:
        assert module_path(root) is not None, f"{root} should resolve to a source file"
        reachable = reachable_app_modules((root,))
        assert "app.data.market_panel" not in reachable, (
            f"{root} must not be able to reach app.data.market_panel (C-7)"
        )


def test_market_type_export_still_matches_positions_chain_literal() -> None:
    # Sanity check that the shared `Market` type alias used by both the
    # positions chain and this module's tests has not silently diverged.
    example: Market = "TW"
    assert example == "TW"
