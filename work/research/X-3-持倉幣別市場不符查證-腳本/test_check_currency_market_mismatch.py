"""Tests for the X-3a read-only check. Every database is built under ``tmp_path``."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = Path(__file__).with_name("check_currency_market_mismatch.py")
#: The app file the rule is copied from; read as text only, never imported.
_MODELS = (
    Path(__file__).resolve().parents[3]
    / "apps"
    / "stock-desk"
    / "backend"
    / "app"
    / "positions"
    / "models.py"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_currency_market_mismatch", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


x3 = _load_script()

# Copy of the app's ``positions`` schema (app/positions/store.py). The loose
# variant drops NOT NULL on market / currency so a NULL can be stored.
_POSITIONS_SQL = """
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT {null},
    quantity TEXT NOT NULL,
    avg_cost TEXT NOT NULL,
    currency TEXT {null},
    opened_at TEXT,
    instrument_type TEXT NOT NULL,
    sector TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

# Sentinels in every column the script must not read.
_SENTINELS = {
    "quantity": "SENTINEL-QTY-7731",
    "avg_cost": "SENTINEL-COST-4410",
    "note": "SENTINEL-NOTE-9902",
    "sector": "SENTINEL-SECTOR-5518",
    "opened_at": "SENTINEL-OPENED-2207",
    "created_at": "SENTINEL-CREATED-6164",
    "updated_at": "SENTINEL-UPDATED-3385",
}

Row = tuple[str, object, object]


def _make_db(path: Path, rows: list[Row], *, loose: bool = False) -> Path:
    """A main DB whose ``positions`` holds ``(symbol, market, currency)`` rows."""
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(_POSITIONS_SQL.format(null="" if loose else "NOT NULL"))
        conn.executemany(
            "INSERT INTO positions (symbol, market, currency, quantity, avg_cost, note, "
            "sector, opened_at, instrument_type, created_at, updated_at) "
            "VALUES (:symbol, :market, :currency, :quantity, :avg_cost, :note, :sector, "
            ":opened_at, 'stock', :created_at, :updated_at)",
            [
                {"symbol": symbol, "market": market, "currency": currency, **_SENTINELS}
                for symbol, market, currency in rows
            ],
        )
    return path


def _run(db: Path, tmp_path: Path) -> tuple[int, dict[str, Any] | None]:
    out = tmp_path / "X-3_out.json"
    code = x3.main(["--db", str(db), "--out", str(out)])
    summary = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return code, summary


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _last_err_line(capsys: Any) -> str:
    err: str = capsys.readouterr().err
    return err.rstrip("\n").splitlines()[-1]


def test_all_matched_is_low(tmp_path: Path, capsys: Any) -> None:
    db = _make_db(tmp_path / "main.db", [("2330", "TW", "TWD"), ("AAPL", "US", "USD")])
    before = _digest(db)

    code, summary = _run(db, tmp_path)

    assert code == 0
    assert summary is not None
    assert summary["check"] == x3.CHECK_NAME
    assert summary["db_file_name"] == "main.db"
    assert summary["verdict"] == "none_found"
    assert summary["escalation"] == "low"
    assert summary["counts"] == {
        "total_rows": 2,
        "matched_rows": 2,
        "mismatch_rows": 0,
        "mismatch_by_direction": {"US_stored_as_TWD": 0, "TW_stored_as_USD": 0},
        "unreadable_rows": 0,
    }
    assert summary["mismatch"] == []
    assert summary["unreadable"] == []
    last = _last_err_line(capsys)
    assert last.startswith("X-3 判定：low（僅代表執行當下）")
    assert _digest(db) == before


def test_empty_positions_is_low(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "main.db", [])

    code, summary = _run(db, tmp_path)

    assert code == 0
    assert summary is not None
    assert summary["verdict"] == "none_found"
    assert summary["escalation"] == "low"
    assert summary["counts"]["total_rows"] == 0


def test_both_directions_are_high(tmp_path: Path, capsys: Any) -> None:
    db = _make_db(
        tmp_path / "main.db",
        [
            ("2330", "TW", "TWD"),  # id 1, matched
            ("AAPL", "US", "TWD"),  # id 2, type A
            ("0050", "TW", "USD"),  # id 3, type B
        ],
    )
    before = _digest(db)

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["verdict"] == "found"
    assert summary["escalation"] == "high"
    assert summary["counts"] == {
        "total_rows": 3,
        "matched_rows": 1,
        "mismatch_rows": 2,
        "mismatch_by_direction": {"US_stored_as_TWD": 1, "TW_stored_as_USD": 1},
        "unreadable_rows": 0,
    }
    assert summary["mismatch"] == [
        {
            "id": 2,
            "symbol": "AAPL",
            "market": "US",
            "currency": "TWD",
            "direction": "US_stored_as_TWD",
            "symbol_has_mixed_currencies": False,
        },
        {
            "id": 3,
            "symbol": "0050",
            "market": "TW",
            "currency": "USD",
            "direction": "TW_stored_as_USD",
            "symbol_has_mixed_currencies": False,
        },
    ]
    assert summary["unreadable"] == []
    last = _last_err_line(capsys)
    assert last.startswith("X-3 判定：high")
    assert "美股記成 TWD 1 列" in last
    assert "台股記成 USD 1 列" in last
    assert "把 JSON 全文貼回給 coordinator" in last
    assert _digest(db) == before


def test_same_symbol_with_mixed_currencies_is_flagged(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path / "main.db",
        [
            ("AAPL", "US", "USD"),  # id 1, matched
            ("AAPL", "US", "TWD"),  # id 2, type A under a holding that also has USD
            ("MSFT", "US", "TWD"),  # id 3, type A alone
            ("MSFT", "TW", "TWD"),  # id 4, another market: not the same holding
        ],
    )

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    flags = {row["id"]: row["symbol_has_mixed_currencies"] for row in summary["mismatch"]}
    assert flags == {2: True, 3: False}
    assert summary["counts"]["matched_rows"] == 2


@pytest.mark.parametrize(
    ("market", "currency", "market_raw", "currency_raw"),
    [
        ("tw", "TWD", "'tw'", "'TWD'"),  # lower case market
        ("us", "TWD", "'us'", "'TWD'"),  # would be a mismatch only after case folding
        ("US", " USD", "'US'", "' USD'"),  # leading space
        ("TW ", "TWD", "'TW '", "'TWD'"),  # trailing space
        ("US", "HKD", "'US'", "'HKD'"),  # currency outside the Literal set
        ("HK", "HKD", "'HK'", "'HKD'"),  # market outside the Literal set
        ("US", None, "'US'", "None"),  # NULL currency
        (None, "USD", "None", "'USD'"),  # NULL market
    ],
)
def test_unreadable_values_are_counted_apart_and_high(
    tmp_path: Path,
    capsys: Any,
    market: object,
    currency: object,
    market_raw: str,
    currency_raw: str,
) -> None:
    db = _make_db(
        tmp_path / "main.db", [("2330", "TW", "TWD"), ("XYZ", market, currency)], loose=True
    )

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["verdict"] == "found"
    assert summary["escalation"] == "high"
    assert summary["counts"]["unreadable_rows"] == 1
    assert summary["counts"]["mismatch_rows"] == 0
    assert summary["counts"]["matched_rows"] == 1
    assert summary["mismatch"] == []
    assert summary["unreadable"] == [
        {"id": 2, "symbol": "XYZ", "market_raw": market_raw, "currency_raw": currency_raw}
    ]
    last = _last_err_line(capsys)
    assert last.startswith("X-3 判定：high")
    assert "無法讀取 1 列" in last
    assert "幣別與市場不符" not in last


def test_unreadable_row_does_not_make_a_mismatch_mixed(tmp_path: Path) -> None:
    # Only currencies of the Literal set count towards "mixed"; a ' USD' row
    # is unreadable (the app cannot load it), not a second currency.
    db = _make_db(tmp_path / "main.db", [("AAPL", "US", "TWD"), ("AAPL", "US", " USD")], loose=True)

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["counts"]["mismatch_rows"] == 1
    assert summary["counts"]["unreadable_rows"] == 1
    assert summary["mismatch"][0]["symbol_has_mixed_currencies"] is False


def test_unused_columns_never_reach_the_output(tmp_path: Path, capsys: Any) -> None:
    db = _make_db(
        tmp_path / "main.db",
        [("2330", "TW", "TWD"), ("AAPL", "US", "TWD"), ("XYZ", "tw", "USD")],
    )

    code, summary = _run(db, tmp_path)
    code_stdout = x3.main(["--db", str(db)])

    assert code == code_stdout == 1
    assert summary is not None
    captured = capsys.readouterr()
    text = json.dumps(summary, ensure_ascii=False) + captured.out + captured.err
    for column, sentinel in _SENTINELS.items():
        assert sentinel not in text, column
    # The JSON (file and stdout) carries the DB file name only, never its path.
    assert summary["db_file_name"] == "main.db"
    assert str(tmp_path) not in json.dumps(summary, ensure_ascii=False) + captured.out


def test_only_the_four_columns_are_selected(tmp_path: Path, monkeypatch: Any) -> None:
    db = _make_db(tmp_path / "main.db", [("AAPL", "US", "TWD")])
    statements: list[str] = []
    original: Callable[[Path], sqlite3.Connection] = x3.open_read_only

    def traced(path: Path) -> sqlite3.Connection:
        conn = original(path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(x3, "open_read_only", traced)

    code, _ = _run(db, tmp_path)

    assert code == 1
    assert statements
    for statement in statements:
        assert statement.lstrip().upper().startswith(("SELECT", "PRAGMA")), statement
    # Every statement that names the table must be one of these, verbatim:
    # nothing else (no other column, no write) ever reaches ``positions``.
    allowed = {
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'positions'",
        "PRAGMA table_info(positions)",
        "SELECT id, symbol, market, currency FROM positions ORDER BY id",
    }
    touching = [s for s in statements if "positions" in s.lower()]
    assert touching
    assert set(touching) <= allowed, set(touching) - allowed
    assert "SELECT id, symbol, market, currency FROM positions ORDER BY id" in touching
    # Tracing starts after ``open_read_only`` set query_only, so every traced
    # statement names the table.
    assert [s for s in statements if s not in touching] == []


def test_positions_table_absent_writes_json_then_exits_2(tmp_path: Path, capsys: Any) -> None:
    db = tmp_path / "stock-desk-market.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("CREATE TABLE market_daily_bars (symbol TEXT, close TEXT)")
    before = _digest(db)

    code, summary = _run(db, tmp_path)

    assert code == 2
    assert summary is not None
    assert summary["verdict"] == "positions_table_absent"
    assert summary["escalation"] is None
    assert summary["counts"] is None
    assert summary["mismatch"] is None
    assert summary["unreadable"] is None
    err = capsys.readouterr().err
    assert "point --db at the main DB" in err
    assert "Traceback" not in err
    assert err.rstrip("\n").splitlines()[-1].startswith("X-3 判定：無法判定")
    assert _digest(db) == before


@pytest.mark.parametrize("dropped", ["id", "symbol", "market", "currency"])
def test_missing_column_exits_2(tmp_path: Path, capsys: Any, dropped: str) -> None:
    db = tmp_path / "main.db"
    columns = [c for c in ("id", "symbol", "market", "currency", "quantity") if c != dropped]
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(f"CREATE TABLE positions ({', '.join(f'{c} TEXT' for c in columns)})")
    before = _digest(db)

    code, summary = _run(db, tmp_path)

    assert code == 2
    assert summary is None
    err = capsys.readouterr().err
    assert f"table positions has no column {dropped}" in err
    assert "Traceback" not in err
    assert _digest(db) == before


def test_out_pointing_at_db_is_refused(tmp_path: Path, capsys: Any) -> None:
    db = _make_db(tmp_path / "main.db", [("AAPL", "US", "TWD")])
    before = _digest(db)

    code = x3.main(["--db", str(db), "--out", str(db)])

    assert code == 2
    assert "--out must not point at the --db file" in capsys.readouterr().err
    assert _digest(db) == before


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_out_pointing_at_a_side_file_is_refused(tmp_path: Path, capsys: Any, suffix: str) -> None:
    db = _make_db(tmp_path / "main.db", [("AAPL", "US", "TWD")])
    side = tmp_path / f"main.db{suffix}"
    before = _digest(db)

    code = x3.main(["--db", str(db), "--out", str(side)])

    assert code == 2
    assert "-wal / -shm / -journal" in capsys.readouterr().err
    assert not side.exists()
    assert _digest(db) == before


def test_out_next_to_the_db_is_allowed(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "main.db", [("AAPL", "US", "USD")])

    code = x3.main(["--db", str(db), "--out", str(tmp_path / "main.db-out.json")])

    assert code == 0


def test_out_overwrites_an_existing_file(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "main.db", [("AAPL", "US", "USD")])
    out = tmp_path / "X-3_out.json"
    out.write_text("old content\n", encoding="utf-8")

    code, summary = _run(db, tmp_path)

    assert code == 0
    assert summary is not None
    assert summary["verdict"] == "none_found"


def test_missing_db_argument_exits_2(capsys: Any) -> None:
    with pytest.raises(SystemExit) as raised:
        x3.main([])

    assert raised.value.code == 2
    assert "--db" in capsys.readouterr().err


def test_unwritable_out_exits_2(tmp_path: Path, capsys: Any) -> None:
    db = _make_db(tmp_path / "main.db", [("AAPL", "US", "TWD")])
    before = _digest(db)

    code = x3.main(["--db", str(db), "--out", str(tmp_path / "no-such-dir" / "X-3_out.json")])

    assert code == 2
    err = capsys.readouterr().err
    assert "error: cannot write --out file" in err
    assert "Traceback" not in err
    assert _digest(db) == before


def test_missing_db_file_is_not_created(tmp_path: Path, capsys: Any) -> None:
    db = tmp_path / "absent.db"

    code = x3.main(["--db", str(db)])

    assert code == 2
    assert not db.exists()
    assert "Traceback" not in capsys.readouterr().err


def test_not_a_database_exits_2(tmp_path: Path, capsys: Any) -> None:
    db = tmp_path / "notes.txt"
    db.write_text("this is not sqlite\n" * 100, encoding="utf-8")
    before = _digest(db)

    code, summary = _run(db, tmp_path)

    assert code == 2
    assert summary is None
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "Traceback" not in err
    assert _digest(db) == before


def test_mode_ro_alone_refuses_writes(tmp_path: Path) -> None:
    # First layer: the ``mode=ro`` URI refuses a write without query_only.
    db = _make_db(tmp_path / "main.db", [("2330", "TW", "TWD")])
    before = _digest(db)

    with closing(sqlite3.connect(x3.read_only_uri(db), uri=True)) as conn:
        assert conn.execute("PRAGMA query_only").fetchone() == (0,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM positions")
    assert _digest(db) == before


def test_open_read_only_turns_query_only_on(tmp_path: Path) -> None:
    # Second layer: the script's connection also has query_only set.
    db = _make_db(tmp_path / "main.db", [("2330", "TW", "TWD")])

    with closing(x3.open_read_only(db)) as conn:
        assert conn.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM positions")


def _make_wal_db(path: Path) -> sqlite3.Connection:
    """A WAL main DB with committed rows still in ``-wal``; the writer stays open."""
    writer = sqlite3.connect(path)
    assert writer.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
    writer.execute("PRAGMA wal_autocheckpoint = 0")  # keep the rows out of the main file
    writer.execute(_POSITIONS_SQL.format(null="NOT NULL"))
    writer.commit()
    writer.executemany(
        "INSERT INTO positions (symbol, market, currency, quantity, avg_cost, "
        "instrument_type, created_at, updated_at) VALUES (?, ?, ?, '1', '1', 'stock', 'x', 'x')",
        [("2330", "TW", "TWD"), ("AAPL", "US", "TWD")],
    )
    writer.commit()
    return writer


def test_wal_db_with_the_app_running(tmp_path: Path) -> None:
    db = tmp_path / "main.db"
    writer = _make_wal_db(db)
    try:
        assert Path(f"{db}-wal").stat().st_size > 0
        before = _digest(db)

        code, summary = _run(db, tmp_path)

        assert code == 1
        assert summary is not None
        # The rows only in -wal are seen.
        assert summary["counts"]["total_rows"] == 2
        assert summary["counts"]["mismatch_by_direction"]["US_stored_as_TWD"] == 1
        assert _digest(db) == before
        # The app's connection can still write afterwards.
        writer.execute("DELETE FROM positions WHERE symbol = 'AAPL'")
        writer.commit()
    finally:
        writer.close()


def test_wal_db_with_the_app_closed(tmp_path: Path) -> None:
    db = tmp_path / "main.db"
    _make_wal_db(db).close()  # the last close checkpoints and removes the side files
    wal, shm = Path(f"{db}-wal"), Path(f"{db}-shm")
    assert not wal.exists() and not shm.exists()
    before = _digest(db)

    code, summary = _run(db, tmp_path)

    assert code == 1
    assert summary is not None
    assert summary["counts"]["total_rows"] == 2
    assert summary["counts"]["mismatch_rows"] == 1
    assert _digest(db) == before
    # SQLite may leave side files behind; -wal, if any, holds no data.
    assert not wal.exists() or wal.stat().st_size == 0


def _module_level_value(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return node.value
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return node.value
    raise AssertionError(f"{name} is not assigned at module level in {_MODELS}")


def _literal_members(value: ast.expr) -> frozenset[str]:
    # ``Literal["TW", "US"]`` -> {"TW", "US"}
    assert isinstance(value, ast.Subscript)
    assert isinstance(value.value, ast.Name) and value.value.id == "Literal"
    members = ast.literal_eval(value.slice)
    return frozenset(members if isinstance(members, tuple) else (members,))


def test_rule_matches_the_app_source() -> None:
    # Drift guard: parse the app's models.py as text (no import of the app).
    tree = ast.parse(_MODELS.read_text(encoding="utf-8"), filename=str(_MODELS))

    assert ast.literal_eval(_module_level_value(tree, "MARKET_CURRENCY")) == dict(
        x3.MARKET_CURRENCY
    )
    assert _literal_members(_module_level_value(tree, "Market")) == x3.MARKETS
    assert _literal_members(_module_level_value(tree, "Currency")) == x3.CURRENCIES


def test_direction_names_cover_every_wrong_pair() -> None:
    wrong_pairs = {
        f"{market}_stored_as_{currency}"
        for market in x3.MARKETS
        for currency in x3.CURRENCIES
        if x3.MARKET_CURRENCY[market] != currency
    }
    assert set(x3.DIRECTIONS) == wrong_pairs
    assert x3.DIRECTIONS == ("US_stored_as_TWD", "TW_stored_as_USD")


def test_script_imports_the_standard_library_only() -> None:
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    imported.discard("__future__")
    assert imported <= sys.stdlib_module_names, imported - sys.stdlib_module_names
