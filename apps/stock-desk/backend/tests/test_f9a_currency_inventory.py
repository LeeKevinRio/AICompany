"""F-9a: ``python -m app.data.diagnose currency-inventory`` -- read-only, codes and counts only.

Every database here is built under ``tmp_path``; the product database is never
opened. Each run is checked to leave the database file byte-for-byte and
mtime-for-mtime as it was.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.admission import AdmissionReason
from app.data.cache import PriceBarCache
from app.data.diagnose import (
    US_SUFFIX_REVIEW_HEURISTIC,
    CalendarContribution,
    CurrencyMismatchSeries,
    RefusedSymbol,
    ReviewSymbol,
    currency_inventory,
    main,
    needs_suffix_review,
    open_read_only,
)
from app.data.interface import Market, PriceBar
from app.positions.models import MARKET_CURRENCY, PositionInput
from app.positions.store import PositionStore

D1, D2, D3, D4, D5 = (date(2024, 1, day) for day in (2, 3, 4, 5, 8))
#: Distinctive figures that must never reach the report.
QUANTITY = Decimal("123.4567")
AVG_COST = Decimal("98.7654")


def _bar(symbol: str, market: Market, day: date, currency: str) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market=market,
        date=day,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        volume=1,
        currency=currency,
        as_of=datetime(2024, 1, 9, tzinfo=UTC),
        source="stub",
    )


def _hold(store: PositionStore, symbol: str, market: Market) -> None:
    store.create(
        PositionInput(
            symbol=symbol,
            market=market,
            quantity=QUANTITY,
            avg_cost=AVG_COST,
            currency="TWD" if market == "TW" else "USD",
            instrument_type="stock",
        )
    )


def _seeded_db(tmp_path: Path) -> Path:
    db = tmp_path / "inventory.db"
    cache = PriceBarCache(db_path=db)
    series: list[tuple[str, Market, list[date], str]] = [
        ("2330", "TW", [D1, D2], "TWD"),
        ("00679B", "TW", [D1, D2], "TWD"),
        ("00636K", "TW", [D1, D3], "TWD"),  # refused by admission; D3 only from it
        ("AAPL", "US", [D1, D2], "USD"),
        ("BRK.B", "US", [D1, D2], "USD"),
        ("BF-A", "US", [D1], "USD"),  # common class letter: no review
        ("VOD.L", "US", [D1, D2], "USD"),  # admitted, uncommon single letter: review (d)
        ("^GSPC", "US", [D1, D2], "USD"),  # index: outside admission, still a session source
        ("TSCO.LON", "US", [D1, D4], "USD"),  # refused by admission; D4 only from it
        ("SHEL", "US", [D2, D5], "GBP"),  # off-market currency; D5 only from it
    ]
    for symbol, market, days, currency in series:
        cache.put([_bar(symbol, market, day, currency) for day in days], source="stub")
    store = PositionStore(db_path=db)
    _hold(store, "2330", "TW")
    _hold(store, "00636K", "TW")
    _hold(store, "TSCO.LON", "US")
    _hold(store, "TSCO.LON", "US")
    _hold(store, "BRK.B", "US")
    _hold(store, "VOD.L", "US")
    return db


def _fingerprint(db: Path) -> tuple[str, int, int]:
    stat = os.stat(db)
    return hashlib.sha256(db.read_bytes()).hexdigest(), stat.st_mtime_ns, stat.st_size


def _assert_untouched(db: Path, before: tuple[str, int, int]) -> None:
    assert _fingerprint(db) == before
    # SQLite may create the -wal/-shm side files to read a WAL database
    # read-only; nothing is ever written into the log.
    wal = db.with_name(db.name + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0


def test_inventory_finds_all_three_parts(tmp_path: Path) -> None:
    db = _seeded_db(tmp_path)
    before = _fingerprint(db)

    found = currency_inventory(db, market_currency=MARKET_CURRENCY)

    _assert_untouched(db, before)
    assert found.mismatched == (
        CurrencyMismatchSeries(
            symbol="SHEL", market="US", expected="USD", mismatched_rows=2, observed=("GBP",)
        ),
    )
    assert found.refused_cached == (
        RefusedSymbol("00636K", "TW", AdmissionReason.TW_FOREIGN_CURRENCY_UNIT, 2),
        RefusedSymbol("TSCO.LON", "US", AdmissionReason.US_MULTI_CHAR_SUFFIX, 2),
    )
    assert found.refused_held == (
        RefusedSymbol("00636K", "TW", AdmissionReason.TW_FOREIGN_CURRENCY_UNIT, 1),
        RefusedSymbol("TSCO.LON", "US", AdmissionReason.US_MULTI_CHAR_SUFFIX, 2),
    )
    assert found.calendar == (
        CalendarContribution(market="TW", flagged_series=1, flagged_dates=2, only_flagged_dates=1),
        CalendarContribution(market="US", flagged_series=2, flagged_dates=4, only_flagged_dates=2),
    )
    assert found.review_cached == (ReviewSymbol("VOD.L", "US", 2),)
    assert found.review_held == (ReviewSymbol("VOD.L", "US", 1),)
    assert found.missing_tables == ()
    assert found.has_findings


def test_cli_report_lists_codes_and_counts_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _seeded_db(tmp_path)
    before = _fingerprint(db)

    status = main(["currency-inventory", "--db", str(db)])

    _assert_untouched(db, before)
    out = capsys.readouterr().out
    assert status == 1
    assert out.isascii()
    assert "| SHEL | US | USD | GBP | 2 |" in out
    assert "| 00636K | TW | tw_foreign_currency_unit | 2 |" in out
    assert "| TSCO.LON | US | us_multi_char_suffix | 2 |" in out
    assert "| 00636K | TW | tw_foreign_currency_unit | 1 |" in out
    assert "| TW | 1 | 2 | 1 |" in out
    assert "| US | 2 | 4 | 2 |" in out
    assert "(d) cached series admitted with a single-letter suffix other than A,B,C" in out
    assert "| VOD.L | US | 2 |" in out
    assert "| VOD.L | US | 1 |" in out
    for admitted in ("2330", "00679B", "AAPL", "BRK.B", "BF-A", "^GSPC"):
        assert f"| {admitted} |" not in out
    # Never a quantity or a cost, in any spelling.
    for figure in (QUANTITY, AVG_COST):
        assert str(figure) not in out
        assert str(figure).rstrip("0") not in out
        assert str(float(figure)) not in out


def test_clean_database_reports_none_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "clean.db"
    PriceBarCache(db_path=db).put([_bar("2330", "TW", D1, "TWD")], source="stub")
    _hold(PositionStore(db_path=db), "2330", "TW")
    before = _fingerprint(db)

    status = main(["currency-inventory", "--db", str(db)])

    _assert_untouched(db, before)
    assert status == 0
    assert capsys.readouterr().out.count("(none)") == 6


def test_missing_tables_are_reported_not_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "bare.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE unrelated (a)")
    conn.close()
    before = _fingerprint(db)

    status = main(["currency-inventory", "--db", str(db)])

    _assert_untouched(db, before)
    assert status == 0
    assert "tables absent: price_bars_cache, positions" in capsys.readouterr().out


def test_missing_file_is_an_error_and_is_not_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "absent.db"
    assert main(["currency-inventory", "--db", str(db)]) == 2
    assert not db.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == []
    assert "read-only" in capsys.readouterr().err


def test_connection_refuses_every_write(tmp_path: Path) -> None:
    db = _seeded_db(tmp_path)
    before = _fingerprint(db)
    conn = open_read_only(db)
    try:
        for statement in (
            "DELETE FROM price_bars_cache",
            "UPDATE positions SET quantity = '0'",
            "CREATE TABLE intruder (a)",
        ):
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute(statement)
    finally:
        conn.close()
    _assert_untouched(db, before)


def test_default_path_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _seeded_db(tmp_path)
    before = _fingerprint(db)
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(db))

    assert main(["currency-inventory"]) == 1

    _assert_untouched(db, before)
    assert f"currency inventory (read-only): {db}" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--probe", "--clear-cooldown"])
def test_live_flags_are_refused_with_the_inventory(tmp_path: Path, flag: str) -> None:
    db = _seeded_db(tmp_path)
    before = _fingerprint(db)
    with pytest.raises(SystemExit) as exit_info:
        main([flag, "currency-inventory", "--db", str(db)])
    assert exit_info.value.code == 2
    _assert_untouched(db, before)


def test_positions_query_never_reads_quantity_or_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Belt and braces for the report test: the columns are not even selected."""
    db = _seeded_db(tmp_path)
    statements: list[str] = []
    real_open = open_read_only

    def traced(path: Path) -> sqlite3.Connection:
        conn = real_open(path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr("app.data.diagnose.open_read_only", traced)
    currency_inventory(db, market_currency=MARKET_CURRENCY)
    assert statements
    for statement in statements:
        assert statement.lstrip().upper().startswith("SELECT")
        assert "quantity" not in statement.lower()
        assert "avg_cost" not in statement.lower()


# --- (d) manual-review heuristic (risk ruling F9W-15) ---------------------------


def test_review_heuristic_is_an_unverified_inventory_aid() -> None:
    assert US_SUFFIX_REVIEW_HEURISTIC.common_class_letters == frozenset({"A", "B", "C"})
    assert US_SUFFIX_REVIEW_HEURISTIC.verified is False
    assert US_SUFFIX_REVIEW_HEURISTIC.verified_on is None


@pytest.mark.parametrize(
    ("symbol", "market", "review"),
    [
        ("VOD.L", "US", True),
        ("MOG-W", "US", True),
        ("ABC.U", "US", True),
        ("BRK.A", "US", False),
        ("BRK.B", "US", False),
        ("BF-B", "US", False),
        ("XYZ.C", "US", False),
        ("AAPL", "US", False),  # no suffix
        ("TSCO.LON", "US", False),  # refused by admission: listed under (b), not (d)
        ("7203.T", "US", False),  # refused by admission
        ("00631L", "TW", False),  # TW suffixes are not this heuristic's concern
        ("VOD.L", "TW", False),
    ],
)
def test_needs_suffix_review(symbol: str, market: str, review: bool) -> None:
    assert needs_suffix_review(symbol, market) is review


def test_review_alone_counts_as_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "review.db"
    PriceBarCache(db_path=db).put([_bar("2330", "TW", D1, "TWD")], source="stub")
    _hold(PositionStore(db_path=db), "VOD.L", "US")
    before = _fingerprint(db)

    status = main(["currency-inventory", "--db", str(db)])

    _assert_untouched(db, before)
    out = capsys.readouterr().out
    assert status == 1
    assert "| VOD.L | US | 1 |" in out
    assert out.count("(none)") == 5
    for figure in (QUANTITY, AVG_COST):
        assert str(figure) not in out
