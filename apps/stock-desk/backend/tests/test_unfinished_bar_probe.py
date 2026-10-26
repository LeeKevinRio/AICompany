"""The N-152 offline probe: close-time rule, DST handling, and its read-only promise.

Every DB is built under ``tmp_path`` through the real ``PriceBarCache`` (so the schema is the
production one); hand-made rows are inserted with plain ``sqlite3`` only where the cache
itself would refuse to write them. No network, no real DB, no ``.env``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.data.cache import PriceBarCache
from app.data.freshness import policy_for
from app.data.interface import Market, PriceBar

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "unfinished_bar_probe.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("unfinished_bar_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load()

RUN_AT = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def _bar(symbol: str, market: Market, day: date) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market=market,
        date=day,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        volume=1000,
        currency="TWD" if market == "TW" else "USD",
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        source="fixture",
    )


def _put(cache: PriceBarCache, symbol: str, market: Market, day: date, fetched: datetime) -> None:
    cache.put([_bar(symbol, market, day)], source="fixture", fetched_at=fetched)


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def _insert_raw(db: Path, row: tuple[str, str, str, str]) -> None:
    """Insert a hand-made (symbol, market, trade_date, fetched_at) row the cache would not write."""
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(
            "INSERT INTO price_bars_cache (symbol, market, trade_date, open, high, low, close, "
            "volume, currency, source, as_of, fetched_at) "
            "VALUES (?, ?, ?, '1', '1', '1', '1', 1, 'X', 'hand', '2026-01-01T00:00:00+00:00', ?)",
            (row[0], row[1], row[2], row[3]),
        )


def _db(tmp_path: Path) -> tuple[Path, PriceBarCache]:
    path = tmp_path / "stock-desk.db"
    return path, PriceBarCache(path)


def _report(path: Path) -> Any:
    with closing(probe.open_read_only(path)) as conn:
        return probe.load(conn)


def _listed(path: Path) -> list[tuple[str, str, str]]:
    return [(f.market, f.symbol, f.trade_date.isoformat()) for f in _report(path).findings]


def _run(path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    assert probe.main(["--db-path", str(path)], now_utc=RUN_AT) == 0
    return capsys.readouterr().out


# ---------------------------------------------------------------- the rule


def test_tw_and_us_each_have_one_listed_row_and_one_normal_row(tmp_path: Path) -> None:
    path, cache = _db(tmp_path)
    # TW close 2026-10-20 is 13:30 Taipei = 05:30 UTC.
    _put(cache, "2330", "TW", date(2026, 10, 20), _utc(2026, 10, 20, 3, 0))  # mid-session
    _put(cache, "2317", "TW", date(2026, 10, 20), _utc(2026, 10, 20, 8, 0))  # after the close
    # US close 2026-10-20 is 16:00 New York (EDT) = 20:00 UTC.
    _put(cache, "AAPL", "US", date(2026, 10, 20), _utc(2026, 10, 20, 17, 0))  # mid-session
    _put(cache, "MSFT", "US", date(2026, 10, 20), _utc(2026, 10, 21, 1, 0))  # after the close

    report = _report(path)

    assert report.rows_total == 4
    assert report.rows_by_market == {"TW": 2, "US": 2}
    assert _listed(path) == [("TW", "2330", "2026-10-20"), ("US", "AAPL", "2026-10-20")]
    by_symbol = {f.symbol: f for f in report.findings}
    assert by_symbol["2330"].close_utc == _utc(2026, 10, 20, 5, 30)
    assert by_symbol["AAPL"].close_utc == _utc(2026, 10, 20, 20, 0)
    assert report.not_judged == []


@pytest.mark.parametrize(
    ("market", "day", "close"),
    [
        ("TW", date(2026, 10, 20), _utc(2026, 10, 20, 5, 30)),
        ("US", date(2026, 10, 20), _utc(2026, 10, 20, 20, 0)),
    ],
)
def test_fetched_exactly_at_the_close_is_not_listed(
    tmp_path: Path, market: Market, day: date, close: datetime
) -> None:
    path, cache = _db(tmp_path)
    _put(cache, "EDGE", market, day, close)
    assert _listed(path) == []


@pytest.mark.parametrize(
    ("market", "day", "close"),
    [
        ("TW", date(2026, 10, 20), _utc(2026, 10, 20, 5, 30)),
        ("US", date(2026, 10, 20), _utc(2026, 10, 20, 20, 0)),
    ],
)
def test_one_second_either_side_of_the_close(
    tmp_path: Path, market: Market, day: date, close: datetime
) -> None:
    path, cache = _db(tmp_path)
    _put(cache, "BEFORE", market, day, close - timedelta(seconds=1))
    _put(cache, "AFTER", market, day, close + timedelta(seconds=1))
    assert [symbol for _, symbol, _ in _listed(path)] == ["BEFORE"]


@pytest.mark.parametrize(
    ("trade_day", "close_utc_hour"),
    [
        (date(2026, 3, 6), 21),  # Friday before the 2026-03-08 spring-forward: EST, UTC-5
        (date(2026, 3, 9), 20),  # Monday after it: EDT, UTC-4
        (date(2026, 10, 30), 20),  # Friday before the 2026-11-01 fall-back: EDT, UTC-4
        (date(2026, 11, 2), 21),  # Monday after it: EST, UTC-5
    ],
)
def test_us_close_follows_daylight_saving_time(
    tmp_path: Path, trade_day: date, close_utc_hour: int
) -> None:
    assert probe.close_utc("US", trade_day) == _utc(
        trade_day.year, trade_day.month, trade_day.day, close_utc_hour
    )
    path, cache = _db(tmp_path)
    close = _utc(trade_day.year, trade_day.month, trade_day.day, close_utc_hour)
    _put(cache, "BEFORE", "US", trade_day, close - timedelta(minutes=1))
    _put(cache, "AT", "US", trade_day, close)
    _put(cache, "AFTER", "US", trade_day, close + timedelta(minutes=1))
    assert [symbol for _, symbol, _ in _listed(path)] == ["BEFORE"]


def test_a_fixed_offset_would_misjudge_the_hour_between_the_two_us_closes(
    tmp_path: Path,
) -> None:
    """20:30 UTC is after the EDT close (20:00) but before the EST close (21:00)."""
    path, cache = _db(tmp_path)
    _put(cache, "SUMMER", "US", date(2026, 3, 9), _utc(2026, 3, 9, 20, 30))  # EDT: after close
    _put(cache, "WINTER", "US", date(2026, 3, 6), _utc(2026, 3, 6, 20, 30))  # EST: before close
    assert _listed(path) == [("US", "WINTER", "2026-03-06")]


def test_tw_close_does_not_move_across_the_year(tmp_path: Path) -> None:
    for day in (date(2026, 1, 5), date(2026, 7, 6)):
        assert probe.close_utc("TW", day) == datetime.combine(day, time(5, 30), tzinfo=UTC)


def test_fetched_at_with_a_non_utc_offset_is_compared_as_an_instant(tmp_path: Path) -> None:
    path, cache = _db(tmp_path)
    # 12:00+08:00 is 04:00 UTC: before the 05:30 UTC TW close.
    _insert_raw(path, ("1101", "TW", "2026-10-20", "2026-10-20T12:00:00+08:00"))
    # 14:00+08:00 is 06:00 UTC: after it.
    _insert_raw(path, ("1102", "TW", "2026-10-20", "2026-10-20T14:00:00+08:00"))
    assert _listed(path) == [("TW", "1101", "2026-10-20")]


def test_probe_rule_constants_match_the_data_service_session_policy() -> None:
    markets: tuple[Market, ...] = ("TW", "US")
    for market in markets:
        policy = policy_for(market)
        assert probe.MARKET_RULES[market].timezone == policy.timezone
        assert probe.MARKET_RULES[market].close == policy.session_close


# ---------------------------------------------------------------- latest bar flag


def test_latest_bar_flag_separates_the_newest_bar_from_a_historical_one(tmp_path: Path) -> None:
    path, cache = _db(tmp_path)
    mid_session = _utc(2026, 10, 19, 3, 0)  # 11:00 Taipei on the 19th
    # Historical position: fetched mid-session on the 19th, newer bars exist afterwards.
    _put(cache, "2330", "TW", date(2026, 10, 19), mid_session)
    _put(cache, "2330", "TW", date(2026, 10, 20), _utc(2026, 10, 21, 1, 0))
    # Newest position: the listed row is the newest stored bar of this symbol.
    _put(cache, "2317", "TW", date(2026, 10, 20), _utc(2026, 10, 20, 3, 0))
    # The same symbol on another market is tracked separately.
    _put(cache, "2317", "US", date(2026, 10, 14), _utc(2026, 10, 14, 15, 0))
    _put(cache, "2317", "US", date(2026, 10, 15), _utc(2026, 10, 16, 1, 0))

    report = _report(path)
    flags = {
        (f.market, f.symbol, f.trade_date.isoformat()): f.is_latest_bar for f in report.findings
    }

    assert flags == {
        ("TW", "2317", "2026-10-20"): True,
        ("TW", "2330", "2026-10-19"): False,
        ("US", "2317", "2026-10-14"): False,
    }
    historical = next(f for f in report.findings if f.symbol == "2330")
    assert historical.symbol_latest_trade_date == date(2026, 10, 20)


def test_counts_split_latest_and_not_latest_per_market(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, cache = _db(tmp_path)
    _put(cache, "2330", "TW", date(2026, 10, 19), _utc(2026, 10, 19, 3, 0))
    _put(cache, "2330", "TW", date(2026, 10, 20), _utc(2026, 10, 20, 3, 0))
    _put(cache, "AAPL", "US", date(2026, 10, 20), _utc(2026, 10, 20, 15, 0))
    out = _run(path, capsys)
    assert "TW: rows=2 fetched_before_close=2 is_latest_bar=1 not_latest_bar=1" in out
    assert "US: rows=1 fetched_before_close=1 is_latest_bar=1 not_latest_bar=0" in out


# ---------------------------------------------------------------- rows the rule cannot judge


def test_unjudgeable_rows_are_reported_with_their_stored_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, _ = _db(tmp_path)
    _insert_raw(path, ("AAA", "JP", "2026-10-20", "2026-10-20T00:00:00+00:00"))
    _insert_raw(path, ("BBB", "TW", "not-a-date", "2026-10-20T00:00:00+00:00"))
    _insert_raw(path, ("CCC", "TW", "2026-10-20", "yesterday"))
    _insert_raw(path, ("DDD", "US", "2026-10-20", "2026-10-20T15:00:00"))  # no offset
    _insert_raw(path, ("EEE", "TW", "2026-10-20", "2026-10-20T08:00:00+00:00"))  # judged, normal

    report = _report(path)

    assert {n.symbol: n.reason for n in report.not_judged} == {
        "AAA": "unknown_market",
        "BBB": "unparseable_trade_date",
        "CCC": "unparseable_fetched_at",
        "DDD": "timezone_naive_fetched_at",
    }
    assert report.findings == []
    out = _run(path, capsys)
    assert "rows that could not be judged: 4" in out
    assert "timezone_naive_fetched_at | US | DDD | 2026-10-20 | 2026-10-20T15:00:00 | hand" in out


# ---------------------------------------------------------------- output


def test_output_lists_every_requested_field_and_states_no_conclusion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, cache = _db(tmp_path)
    fetched = _utc(2026, 10, 20, 17, 0)
    _put(cache, "AAPL", "US", date(2026, 10, 20), fetched)
    out = _run(path, capsys)

    assert f"{fetched.isoformat()}" in out
    assert (
        "US | AAPL | 2026-10-20 | 2026-10-20T17:00:00+00:00 | 2026-10-20T20:00:00+00:00 | yes | "
        "2026-10-20 | fixture"
    ) in out
    assert "run_at_utc: 2026-10-26T12:00:00+00:00" in out
    assert "TW: 13:30 Asia/Taipei" in out
    assert "US: 16:00 America/New_York" in out
    lowered = out.lower()
    for word in ("recommend", "should", "suggest", "conclusion", "residue", "clean up", "delete"):
        assert word not in lowered.replace("could not be judged", ""), word


def test_empty_table_prints_zero_counts_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, _ = _db(tmp_path)
    out = _run(path, capsys)
    assert "price_bars_cache rows scanned: 0" in out
    assert "TW: rows=0 fetched_before_close=0 is_latest_bar=0 not_latest_bar=0" in out
    assert "US: rows=0 fetched_before_close=0 is_latest_bar=0 not_latest_bar=0" in out
    assert "rows that could not be judged: 0" in out


def test_only_the_selected_columns_are_read_and_no_price_value_is_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, cache = _db(tmp_path)
    cache.put(
        [_bar("2330", "TW", date(2026, 10, 20)).model_copy(update={"close": Decimal("987.654")})],
        source="fixture",
        fetched_at=_utc(2026, 10, 20, 3, 0),
    )
    assert "987.654" not in _run(path, capsys)
    assert "close" not in probe.SCAN_SQL.lower().split("from")[0]


# ---------------------------------------------------------------- path resolution and errors


def test_db_path_comes_from_the_environment_variable_and_the_argument_wins(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, cache = _db(tmp_path)
    _put(cache, "2330", "TW", date(2026, 10, 20), _utc(2026, 10, 20, 3, 0))
    other = tmp_path / "other.db"
    PriceBarCache(other)

    assert probe.main([], env={probe.DB_PATH_ENV_VAR: str(path)}, now_utc=RUN_AT) == 0
    assert "fetched_before_close=1" in capsys.readouterr().out

    code = probe.main(
        ["--db-path", str(other)], env={probe.DB_PATH_ENV_VAR: str(path)}, now_utc=RUN_AT
    )
    assert code == 0
    assert "price_bars_cache rows scanned: 0" in capsys.readouterr().out


def test_missing_db_is_refused_and_not_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.db"
    assert probe.main(["--db-path", str(missing)], now_utc=RUN_AT) == 2
    assert "cannot read the DB" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_db_without_the_table_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "empty.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
    assert probe.main(["--db-path", str(path)], now_utc=RUN_AT) == 2
    assert "price_bars_cache" in capsys.readouterr().err


# ---------------------------------------------------------------- read-only promise


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO price_bars_cache (symbol, market, trade_date, open, high, low, close, "
        "volume, currency, source, as_of, fetched_at) "
        "VALUES ('X', 'TW', '2026-10-20', '1', '1', '1', '1', 1, 'TWD', 's', 'a', 'f')",
        "UPDATE price_bars_cache SET fetched_at = '2099-01-01T00:00:00+00:00'",
        "DELETE FROM price_bars_cache",
        "CREATE TABLE sneaky (x INTEGER)",
        "DROP TABLE price_bars_cache",
    ],
)
def test_writing_through_the_probe_connection_fails(tmp_path: Path, statement: str) -> None:
    path, cache = _db(tmp_path)
    _put(cache, "2330", "TW", date(2026, 10, 20), _utc(2026, 10, 20, 3, 0))
    with closing(probe.open_read_only(path)) as conn:
        assert conn.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute(statement)
        # Even with the PRAGMA switched off, the mode=ro open flag still refuses the write.
        conn.execute("PRAGMA query_only=OFF")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute(statement)


def test_a_run_leaves_the_database_file_and_its_directory_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, cache = _db(tmp_path)
    _put(cache, "2330", "TW", date(2026, 10, 20), _utc(2026, 10, 20, 3, 0))
    _put(cache, "AAPL", "US", date(2026, 10, 20), _utc(2026, 10, 21, 1, 0))
    before_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    before_listing = sorted(p.name for p in tmp_path.iterdir())
    before_rows = _all_rows(path)

    _run(path, capsys)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_digest
    # SQLite itself may leave empty WAL sidecars next to a WAL-mode file it only read.
    added = {p.name for p in tmp_path.iterdir()} - set(before_listing)
    assert added <= {"stock-desk.db-wal", "stock-desk.db-shm"}
    wal = tmp_path / "stock-desk.db-wal"
    assert not wal.exists() or wal.stat().st_size == 0
    assert _all_rows(path) == before_rows


def _all_rows(path: Path) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        return conn.execute("SELECT * FROM price_bars_cache ORDER BY 1, 2, 3").fetchall()


def test_the_only_sql_issued_is_one_select_and_the_query_only_pragma(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path, cache = _db(tmp_path)
    _put(cache, "2330", "TW", date(2026, 10, 20), _utc(2026, 10, 20, 3, 0))
    statements: list[str] = []
    real_open = probe.open_read_only

    def traced(db: Path) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_open(db)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(probe, "open_read_only", traced)
    _run(path, capsys)

    assert statements == [probe.SCAN_SQL]
    assert probe.SCAN_SQL.lstrip().upper().startswith("SELECT ")
