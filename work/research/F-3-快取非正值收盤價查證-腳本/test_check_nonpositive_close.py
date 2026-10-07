"""Tests for the F-3 read-only check. Every database is built under ``tmp_path``."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = Path(__file__).with_name("check_nonpositive_close.py")


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_nonpositive_close", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


f3 = _load_script()

# Minimal copies of the app's schemas: only the columns the script reads plus
# the NOT NULL ones that make an insert realistic.
_PRICE_BARS_SQL = """
CREATE TABLE price_bars_cache (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    close TEXT,
    PRIMARY KEY (symbol, market, trade_date)
)
"""
_POSITIONS_SQL = """
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    quantity TEXT NOT NULL
)
"""
_ALERT_RULES_SQL = """
CREATE TABLE alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    enabled INTEGER NOT NULL
)
"""

Bar = tuple[str, str, str, str | None]


def _make_db(
    path: Path,
    *,
    bars: list[Bar] | None = None,
    positions: list[tuple[str, str]] | None = None,
    rules: list[tuple[str, str, int]] | None = None,
    with_bars: bool = True,
    with_positions: bool = True,
    with_rules: bool = True,
) -> Path:
    with closing(sqlite3.connect(path)) as conn, conn:
        if with_bars:
            conn.execute(_PRICE_BARS_SQL)
            conn.executemany("INSERT INTO price_bars_cache VALUES (?, ?, ?, ?)", bars or [])
        if with_positions:
            conn.execute(_POSITIONS_SQL)
            conn.executemany(
                "INSERT INTO positions (symbol, market, quantity) VALUES (?, ?, '1')",
                positions or [],
            )
        if with_rules:
            conn.execute(_ALERT_RULES_SQL)
            conn.executemany(
                "INSERT INTO alert_rules (type, symbol, market, enabled) "
                "VALUES ('price_below', ?, ?, ?)",
                rules or [],
            )
    return path


def _run(db: Path, tmp_path: Path) -> tuple[int, dict[str, Any] | None]:
    out = tmp_path / "F-3_out.json"
    code = f3.main(["--db", str(db), "--out", str(out)])
    summary = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return code, summary


def _affected(summary: dict[str, Any], symbol: str) -> dict[str, Any]:
    rows = summary["tables"]["price_bars_cache"]["affected"]
    matches = [row for row in rows if row["symbol"] == symbol]
    assert len(matches) == 1
    return dict(matches[0])


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_latest_bad_on_held_symbol_escalates(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path / "main.db",
        bars=[
            ("2330", "TW", "2026-10-05", "580"),
            ("2330", "TW", "2026-10-06", "0"),
            ("AAPL", "US", "2026-10-06", "190.5"),
        ],
        positions=[("2330", "TW")],
        rules=[("AAPL", "US", 1)],
    )
    before = _digest(db)

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["verdict"] == "found"
    assert summary["escalation"] == "deploy_prerequisite"
    assert summary["held_or_watched_symbols_whose_latest_bar_is_bad"] == 1
    assert summary["membership"] == {"held_symbols": 1, "watched_symbols": 1}
    body = summary["tables"]["price_bars_cache"]
    assert body["symbols_whose_latest_cached_bar_is_bad"] == 1  # legacy field kept
    assert body["latest_bar_bad"] == {
        "symbols": 1,
        "rows": 1,
        "held": {"symbols": 1, "rows": 1},
        "watched": {"symbols": 0, "rows": 0},
        "held_and_watched": {"symbols": 0, "rows": 0},
        "other": {"symbols": 0, "rows": 0},
    }
    assert body["older_bar_bad"]["symbols"] == 0
    row = _affected(summary, "2330")
    assert row["held"] is True
    assert row["watched"] is False
    assert row["latest_is_bad"] is True
    assert row["latest_cached_bar_is_bad"] is True
    assert row["older_bad_rows"] == 0
    assert _digest(db) == before


def test_latest_bad_on_watched_symbol_escalates_and_disabled_rule_does_not_watch(
    tmp_path: Path,
) -> None:
    db = _make_db(
        tmp_path / "main.db",
        bars=[
            ("aapl", "us", "2026-10-06", "-1.5"),  # case differs from the rule
            ("TSLA", "US", "2026-10-06", None),  # only a disabled rule
        ],
        rules=[("AAPL", "US", 1), ("TSLA", "US", 0)],
    )

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["escalation"] == "deploy_prerequisite"
    assert summary["held_or_watched_symbols_whose_latest_bar_is_bad"] == 1
    latest = summary["tables"]["price_bars_cache"]["latest_bar_bad"]
    assert latest["symbols"] == 2
    assert latest["watched"] == {"symbols": 1, "rows": 1}
    assert latest["held"] == {"symbols": 0, "rows": 0}
    assert latest["other"] == {"symbols": 1, "rows": 1}
    aapl = _affected(summary, "aapl")
    assert (aapl["held"], aapl["watched"], aapl["latest_is_bad"]) == (False, True, True)
    tsla = _affected(summary, "TSLA")
    assert (tsla["held"], tsla["watched"], tsla["latest_is_bad"]) == (False, False, True)


def test_held_and_watched_counted_in_both_and_in_intersection(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path / "main.db",
        bars=[
            ("2330", "TW", "2026-10-01", "0"),
            ("2330", "TW", "2026-10-02", "0"),
            ("2330", "TW", "2026-10-03", "0"),
        ],
        positions=[("2330", "TW")],
        rules=[("2330", "TW", 1)],
    )

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    body = summary["tables"]["price_bars_cache"]
    for name in ("held", "watched", "held_and_watched"):
        assert body["latest_bar_bad"][name] == {"symbols": 1, "rows": 1}
        assert body["older_bar_bad"][name] == {"symbols": 1, "rows": 2}
    assert body["latest_bar_bad"]["other"] == {"symbols": 0, "rows": 0}
    assert _affected(summary, "2330")["older_bad_rows"] == 2


def test_older_bad_on_other_symbol_does_not_block(tmp_path: Path, capsys: Any) -> None:
    db = _make_db(
        tmp_path / "main.db",
        bars=[
            ("0050", "TW", "2026-10-01", "0"),
            ("0050", "TW", "2026-10-02", "-0"),
            ("0050", "TW", "2026-10-03", "150.2"),
            ("2330", "TW", "2026-10-03", "580"),
        ],
        positions=[("2330", "TW")],
        rules=[("2330", "TW", 1)],
    )

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["verdict"] == "found"
    assert summary["escalation"] == "next_release"
    assert summary["held_or_watched_symbols_whose_latest_bar_is_bad"] == 0
    body = summary["tables"]["price_bars_cache"]
    assert body["latest_bar_bad"]["symbols"] == 0
    assert body["older_bar_bad"] == {
        "symbols": 1,
        "rows": 2,
        "held": {"symbols": 0, "rows": 0},
        "watched": {"symbols": 0, "rows": 0},
        "held_and_watched": {"symbols": 0, "rows": 0},
        "other": {"symbols": 1, "rows": 2},
    }
    row = _affected(summary, "0050")
    assert (row["held"], row["watched"], row["latest_is_bad"]) == (False, False, False)
    assert "不擋部署" in capsys.readouterr().err


def test_no_bad_rows(tmp_path: Path) -> None:
    # An unparseable close is skipped by the app's cache reader, so it is
    # reported but does not decide the verdict.
    db = _make_db(
        tmp_path / "main.db",
        bars=[
            ("2330", "TW", "2026-10-05", "abc"),
            ("2330", "TW", "2026-10-06", "580"),
        ],
        positions=[("2330", "TW")],
    )

    code, summary = _run(db, tmp_path)

    assert code == 0
    assert summary is not None
    assert summary["verdict"] == "none_found"
    assert summary["escalation"] == "next_release"
    body = summary["tables"]["price_bars_cache"]
    assert body["affected"] == []
    assert body["bad_rows_total"] == 0
    assert body["other_unusable_rows"] == {"nonfinite": 0, "unparseable": 1}
    assert body["latest_bar_bad"]["symbols"] == 0
    assert body["older_bar_bad"]["symbols"] == 0


@pytest.mark.parametrize("close", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_nonfinite_latest_bar_on_held_symbol_escalates(tmp_path: Path, close: str) -> None:
    # Decimal("NaN") does not raise, so the app's cache reader keeps the row
    # and the alert / valuation paths see it: it must decide the verdict.
    db = _make_db(
        tmp_path / "main.db",
        bars=[("2330", "TW", "2026-10-05", "580"), ("2330", "TW", "2026-10-06", close)],
        positions=[("2330", "TW")],
    )

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["verdict"] == "found"
    assert summary["escalation"] == "deploy_prerequisite"
    body = summary["tables"]["price_bars_cache"]
    assert body["bad_rows"] == {"nonpositive": 0, "null": 0, "nonfinite": 1}
    assert body["bad_rows_total"] == 1
    # The legacy field still carries the count.
    assert body["other_unusable_rows"] == {"nonfinite": 1, "unparseable": 0}
    assert body["latest_bar_bad"]["held"] == {"symbols": 1, "rows": 1}
    assert _affected(summary, "2330")["latest_is_bad"] is True


@pytest.mark.parametrize(
    "skipped_newer_row",
    [
        ("2330", "TW", "2026-10-06", "abc"),  # unparseable close
        ("2330", "TW", "2026-13-40", "600"),  # invalid date
    ],
)
def test_rows_the_app_skips_do_not_count_as_latest(tmp_path: Path, skipped_newer_row: Bar) -> None:
    # The app's cache reader skips the newer row, so the bad row before it is
    # the latest bar the app actually reads.
    db = _make_db(
        tmp_path / "main.db",
        bars=[
            ("2330", "TW", "2026-10-04", "0"),
            ("2330", "TW", "2026-10-05", "0"),
            skipped_newer_row,
        ],
        positions=[("2330", "TW")],
    )

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["escalation"] == "deploy_prerequisite"
    body = summary["tables"]["price_bars_cache"]
    assert body["latest_bar_bad"]["held"] == {"symbols": 1, "rows": 1}
    assert body["older_bar_bad"]["held"] == {"symbols": 1, "rows": 1}
    row = _affected(summary, "2330")
    assert row["latest_is_bad"] is True
    assert row["older_bad_rows"] == 1


def test_membership_match_strips_whitespace_and_case(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path / "main.db",
        bars=[("2330", "TW", "2026-10-06", "0")],
        positions=[(" 2330 ", "tw ")],
    )

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["escalation"] == "deploy_prerequisite"
    assert _affected(summary, "2330")["held"] is True


def test_market_db_only_writes_json_then_exits_2(tmp_path: Path, capsys: Any) -> None:
    db = tmp_path / "stock-desk-market.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(
            "CREATE TABLE market_daily_bars ("
            "symbol TEXT NOT NULL, session_date TEXT NOT NULL, market TEXT NOT NULL, "
            "close TEXT NOT NULL, PRIMARY KEY (symbol, session_date))"
        )
        conn.execute("INSERT INTO market_daily_bars VALUES ('2330', '2026-10-06', 'TW', '0')")
    before = _digest(db)

    code, summary = _run(db, tmp_path)

    assert code == 2
    assert summary is not None  # the JSON is written before the error exit
    assert summary["verdict"] == "alert_path_table_absent"
    assert summary["escalation"] is None
    assert summary["held_or_watched_symbols_whose_latest_bar_is_bad"] is None
    assert summary["membership"] is None
    assert summary["tables"]["price_bars_cache"] == {"present": False, "on_alert_path": True}
    market = summary["tables"]["market_daily_bars"]
    assert market["on_alert_path"] is False
    assert market["membership_known"] is False
    assert market["latest_bar_bad"]["symbols"] == 1
    assert market["latest_bar_bad"]["held"] is None
    assert market["affected"][0]["held"] is None
    err = capsys.readouterr().err
    assert "point --db at the main DB" in err
    assert "Traceback" not in err
    assert _digest(db) == before


def test_out_pointing_at_db_is_refused(tmp_path: Path, capsys: Any) -> None:
    db = _make_db(tmp_path / "main.db", bars=[("2330", "TW", "2026-10-06", "0")])
    before = _digest(db)

    code = f3.main(["--db", str(db), "--out", str(db)])

    assert code == 2
    assert "--out must not point at the --db file" in capsys.readouterr().err
    assert _digest(db) == before


@pytest.mark.parametrize(
    ("tables", "message"),
    [
        (
            {"with_bars": False, "with_positions": False, "with_rules": False},
            "none of the known daily-bar tables",
        ),
        (
            {"with_positions": False, "with_rules": False},
            "held / watched symbols cannot be told apart",
        ),
        ({"with_rules": False}, "table alert_rules is not in this database"),
        ({"with_positions": False}, "table positions is not in this database"),
    ],
)
def test_missing_table_exits_with_message(
    tmp_path: Path, capsys: Any, tables: dict[str, bool], message: str
) -> None:
    db = _make_db(
        tmp_path / "main.db",
        bars=[("2330", "TW", "2026-10-06", "0")],
        with_bars=tables.get("with_bars", True),
        with_positions=tables.get("with_positions", True),
        with_rules=tables.get("with_rules", True),
    )
    before = _digest(db)

    code, summary = _run(db, tmp_path)

    assert code == 2
    assert summary is None
    err = capsys.readouterr().err
    assert message in err
    assert "Traceback" not in err
    assert _digest(db) == before


def test_missing_column_exits_with_message(tmp_path: Path, capsys: Any) -> None:
    db = tmp_path / "main.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(_PRICE_BARS_SQL)
        conn.execute(_POSITIONS_SQL)
        conn.execute("CREATE TABLE alert_rules (id INTEGER, symbol TEXT, market TEXT)")

    code, _ = _run(db, tmp_path)

    assert code == 2
    assert "table alert_rules has no column enabled" in capsys.readouterr().err


def test_missing_db_file_is_not_created(tmp_path: Path) -> None:
    db = tmp_path / "absent.db"

    code = f3.main(["--db", str(db)])

    assert code == 2
    assert not db.exists()


def test_connection_is_read_only(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "main.db")

    with closing(f3.open_read_only(db)) as conn, pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM positions")
