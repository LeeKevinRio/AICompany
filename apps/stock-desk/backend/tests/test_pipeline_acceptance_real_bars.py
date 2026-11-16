"""Tests for the bar reading of ``scripts/pipeline_acceptance_real.py`` (ADR-0030 supplement 6).

Every database is a ``tmp_path`` file written by ``PriceBarCache`` (or by a raw
connection to that same ``tmp_path`` file, for rows the cache would not write);
nothing here opens the real ``<backend>/data/``, reads ``.env`` or touches the
network.

Covered (supplement 6 points 1-2, point 4 (c); TA C-2, C-3, C-4, C-7; risk RC-158b):

* the row mapping equals ``PriceBarCache.get`` field by field except ``as_of``;
  every ``as_of`` is 20:00 Taipei on its own session, as ``synthetic_series``;
* each of the five stops, with messages carrying no digit, path or value;
* read-only: the file bytes are unchanged, no ``-wal`` / ``-shm`` / ``-journal``
  appears, a missing path is not created, a copied ``-wal`` is read and kept;
* AST: one SELECT of the eight columns, no write statement, ``PRAGMA
  query_only`` only, no forbidden ``app`` module and no network module; the
  isolated-mode import is silent and leaves the forbidden modules unloaded;
* ``bars_sha256`` equals an independent ``content_sha256``;
* no other script or test hands ``read_twii_bars`` a path not built from
  ``tmp_path`` (RC-158b).
"""

from __future__ import annotations

import ast
import hashlib
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.cache import PriceBarCache
from app.data.interface import PriceBar
from app.forecast.canonical import content_sha256
from app.outlook.engine import n_snapshot
from app.outlook.inputs import SERIES_SYMBOL
from tests.forecast_pipeline_harness import (
    P0,
    P1,
    WINDOW_SESSIONS,
    PlaceholderRules,
    run_acceptance,
    synthetic_series,
)
from tests.outlook_helpers import TAIPEI, definition
from tests.pipeline_real_loader import load_script

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND / "scripts" / "pipeline_acceptance_real.py"
LAST = date(2026, 11, 13)
FORBIDDEN_APP_MODULES = ("app.services", "app.data.cache", "app.data.service", "app.data.providers")
# AST level: the script source must not import any of these (any submodule included). The one
# allowed hit is the function-local ``socket`` of the loopback port check.
NETWORK_MODULES = ("socket", "urllib", "requests", "httpx", "yfinance")
# Run time: modules that must not be in ``sys.modules`` after the script was loaded. Only modules
# that do network I/O belong here, and each must stay absent on every CI Python (3.12 and 3.13):
# - ``urllib`` / ``urllib.parse`` are allowed: Python 3.12's ``pathlib`` imports ``urllib.parse``
#   at module level (3.13 does not), and it only parses strings. ``urllib.request`` is banned.
# - ``socket`` is allowed at run time: on Python 3.12 ``email.utils`` (pulled in through
#   ``importlib.metadata`` by a third-party import) imports it, 3.13 does not. The AST check
#   above still pins the script's own ``socket`` use to the loopback port check.
RUNTIME_NETWORK_MODULES = (
    "urllib.request",
    "http.client",
    "ssl",
    "ftplib",
    "smtplib",
    "poplib",
    "imaplib",
    "xmlrpc.client",
    "requests",
    "httpx",
    "yfinance",
)
SIDE_SUFFIXES = ("-wal", "-shm", "-journal")


real = load_script()  # the script's RC-162 hooks are not left on this process


# --- fixtures ---------------------------------------------------------------------------------


def _bars(count: int = 8, *, last: date = LAST, source: str = "yfinance") -> list[PriceBar]:
    """Synthetic ^TWII bars with distinct OHLC, decimal text and volumes."""
    out = []
    for j, bar in enumerate(synthetic_series(last, count)):
        close = bar.close.quantize(Decimal("0.01"))
        out.append(
            bar.model_copy(
                update={
                    "open": close - Decimal("12.5"),
                    "high": close + Decimal("30.25"),
                    "low": close - Decimal("41.00"),
                    "close": close,
                    "volume": 1_000_000 + 7919 * j,
                    "source": source,
                    "as_of": datetime.combine(bar.date, time(14, 5), TAIPEI),
                }
            )
        )
    return out


def _other_series(count: int = 4) -> list[PriceBar]:
    """Rows the reader must leave out: another symbol, and ^TWII under another market."""
    base = _bars(count)
    return [b.model_copy(update={"symbol": "2330"}) for b in base] + [
        b.model_copy(update={"market": "US", "currency": "USD"}) for b in base
    ]


def _cache(path: Path, bars: list[PriceBar], *, source: str = "yfinance") -> PriceBarCache:
    cache = PriceBarCache(path)
    cache.put(bars, source=source, fetched_at=datetime(2026, 11, 14, 1, tzinfo=TAIPEI))
    return cache


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _side_files(db: Path) -> list[Path]:
    return [db.with_name(db.name + s) for s in SIDE_SUFFIXES if db.with_name(db.name + s).exists()]


def _without_as_of(bar: PriceBar) -> dict[str, object]:
    fields = bar.model_dump()
    del fields["as_of"]
    return fields


# --- row mapping and as_of (C-4, supplement 6 point 2) -----------------------------------------


def test_the_mapping_equals_the_cache_read_except_as_of(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    bars = _bars()
    cache = _cache(db, bars + _other_series())
    cached = cache.get(SERIES_SYMBOL, "TW", bars[0].date, bars[-1].date)
    assert cached is not None

    read = real.read_twii_bars(db)

    assert [_without_as_of(b) for b in read] == [_without_as_of(b) for b in cached.bars]
    assert len(read) == len(bars)
    # Field types too (Decimal stays Decimal, volume stays int), not only equal values.
    for ours, theirs in zip(read, cached.bars, strict=True):
        for name in _without_as_of(ours):
            assert type(getattr(ours, name)) is type(getattr(theirs, name))


def test_every_as_of_is_twenty_hundred_taipei_on_its_own_session(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    bars = _bars()
    _cache(db, bars)

    read = real.read_twii_bars(db)

    assert [b.as_of for b in read] == [datetime.combine(b.date, time(20), TAIPEI) for b in read]
    assert all(b.as_of.utcoffset() == timedelta(hours=8) for b in read)
    # The same rule as synthetic_series' default stamp, for the same sessions.
    reference = synthetic_series(bars[-1].date, len(bars))
    assert [b.date for b in reference] == [b.date for b in read]
    assert [b.as_of for b in reference] == [b.as_of for b in read]
    # The cached stamp (14:05) is not what comes back.
    assert all(b.as_of != c.as_of for b, c in zip(read, bars, strict=True))


# --- the five stops (supplement 6 point 1 (e)) -------------------------------------------------


def _assert_stop(raised: pytest.ExceptionInfo[Exception], kind: str, *secrets: str) -> None:
    error = raised.value
    assert isinstance(error, real.AcceptanceStop)
    assert error.kind == kind
    text = str(error)
    assert text == real.STOP_SENTENCES[kind]
    assert not re.search(r"\d", text)
    assert "/" not in text and "\\" not in text
    assert error.args == (text,)
    for secret in secrets:
        assert secret not in text
    # No chained parser error to leak a value through a traceback.
    assert error.__cause__ is None


def test_no_rows_stops(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    _cache(db, _other_series())
    with pytest.raises(real.AcceptanceStop) as raised:
        real.read_twii_bars(db)
    _assert_stop(raised, "no_rows", str(tmp_path), str(db))


def test_an_empty_cache_table_stops_as_no_rows(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    PriceBarCache(db)
    with pytest.raises(real.AcceptanceStop) as raised:
        real.read_twii_bars(db)
    _assert_stop(raised, "no_rows", str(db))


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("open", "not-a-number"),
        ("close", "17,000.5"),
        ("trade_date", "2026-13-40"),
        ("volume", -5),
        ("currency", "   "),
    ],
)
def test_an_unparseable_row_stops_and_no_row_is_skipped(
    tmp_path: Path, column: str, value: object
) -> None:
    db = tmp_path / "copy.db"
    bars = _bars()
    _cache(db, bars)
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(
            f"UPDATE price_bars_cache SET {column} = ? WHERE trade_date = ?",
            (value, bars[3].date.isoformat()),
        )
    with pytest.raises(real.AcceptanceStop) as raised:
        real.read_twii_bars(db)
    _assert_stop(raised, "unparseable_row", str(value), str(db))
    assert raised.value.__suppress_context__ is True


def test_a_demo_row_stops(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    bars = _bars()
    _cache(db, bars[:-1])
    _cache(db, bars[-1:], source="demo_synthetic")
    with pytest.raises(real.AcceptanceStop) as raised:
        real.read_twii_bars(db)
    _assert_stop(raised, "demo_source", "demo_synthetic")


def test_a_row_from_another_source_stops(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    bars = _bars()
    _cache(db, bars[:-1])
    _cache(db, bars[-1:], source="twse_snapshot")
    with pytest.raises(real.AcceptanceStop) as raised:
        real.read_twii_bars(db)
    _assert_stop(raised, "foreign_source", "twse_snapshot")


def test_a_short_cache_stops(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    required = real.required_sessions(definition())
    run_date = LAST + timedelta(days=3)  # the Monday after LAST
    # Today's and later bars do not count toward the depth.
    _cache(db, _bars(required - 1) + _bars(2, last=run_date + timedelta(days=1)))
    bars = real.read_twii_bars(db)
    with pytest.raises(real.AcceptanceStop) as raised:
        real.check_depth(bars, run_date=run_date, required=required)
    _assert_stop(raised, "cache_short", str(required), str(required - 1))


def test_exactly_the_required_depth_passes() -> None:
    required = real.required_sessions(definition())
    bars = _bars(required)
    real.check_depth(bars, run_date=LAST + timedelta(days=1), required=required)
    with pytest.raises(real.AcceptanceStop):
        real.check_depth(bars, run_date=LAST, required=required)


def test_the_required_depth_is_n_snapshot_plus_the_window() -> None:
    rulesets = real.placeholder_rulesets((P0, P1))
    assert len(rulesets) == 4
    expected = n_snapshot(definition=definition(), rulesets=rulesets) + WINDOW_SESSIONS
    assert real.required_sessions(definition()) == expected
    # The design figure (N_SNAPSHOT 315, see test_outlook_engine) plus the window.
    assert expected == 315 + WINDOW_SESSIONS


@pytest.mark.parametrize("rules", [P0, P1], ids=lambda r: r.name)
def test_the_harness_runs_on_exactly_the_required_depth(
    tmp_path: Path, rules: PlaceholderRules
) -> None:
    # The stop threshold is not below what the harness itself needs.
    required = real.required_sessions(definition())
    (tmp_path / "backend" / "data").mkdir(parents=True)
    (tmp_path / "work").mkdir()
    result = run_acceptance(
        tmp_path / "work",
        bars=synthetic_series(LAST, required),
        rules=rules,
        definition=definition(),
        wall_clock=lambda: datetime(2026, 11, 16, 9, tzinfo=TAIPEI),
        backend_dir=tmp_path / "backend",
        env={},
        cwd=tmp_path,
    )
    assert result.passed


def test_every_stop_kind_has_a_clean_fixed_sentence() -> None:
    assert set(real.STOP_SENTENCES) == {
        "no_rows",
        "unparseable_row",
        "demo_source",
        "foreign_source",
        "cache_short",
    }
    for kind, sentence in real.STOP_SENTENCES.items():
        error = real.AcceptanceStop(kind)
        assert str(error) == sentence and error.kind == kind
        assert sentence.isascii() and not re.search(r"\d", sentence)
        assert "/" not in sentence and "\\" not in sentence
    with pytest.raises(ValueError):
        real.AcceptanceStop("anything_else")


# --- read-only (supplement 6 point 1 (a), (c)) ------------------------------------------------


def test_reading_changes_no_byte_and_creates_no_side_file(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    _cache(db, _bars())
    assert _side_files(db) == []
    before = _digest(db)
    listing = sorted(p.name for p in tmp_path.iterdir())

    assert real.read_twii_bars(db)

    assert _digest(db) == before
    assert _side_files(db) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == listing


def test_a_missing_path_is_not_created(tmp_path: Path) -> None:
    db = tmp_path / "absent" / "copy.db"
    with pytest.raises(sqlite3.Error):
        real.read_twii_bars(db)
    assert not db.exists() and not db.parent.exists()
    flat = tmp_path / "copy.db"
    with pytest.raises(sqlite3.Error):
        real.read_twii_bars(flat)
    assert list(tmp_path.iterdir()) == []


def _wal_copy(root: Path) -> tuple[Path, list[PriceBar]]:
    """A byte copy of a WAL database whose last bar is only in the ``-wal``."""
    origin = root / "origin" / "stock-desk.db"
    bars = _bars()
    _cache(origin, bars[:-1])
    holder = sqlite3.connect(origin)
    try:
        holder.execute("SELECT 1 FROM price_bars_cache").fetchall()
        _cache(origin, bars[-1:])  # into the WAL; the open holder stops the close checkpoint
        assert origin.with_name(origin.name + "-wal").stat().st_size > 0
        copy = root / "copy" / "stock-desk.db"
        copy.parent.mkdir()
        for suffix in ("", "-wal", "-shm"):
            shutil.copyfile(
                origin.with_name(origin.name + suffix), copy.with_name(copy.name + suffix)
            )
    finally:
        holder.close()
    return copy, bars


def test_a_copied_wal_is_read_and_not_written(tmp_path: Path) -> None:
    copy, bars = _wal_copy(tmp_path)
    wal = copy.with_name(copy.name + "-wal")
    before = {p: _digest(p) for p in (copy, wal)}

    read = real.read_twii_bars(copy)

    assert [b.date for b in read] == [b.date for b in bars]
    assert {p: _digest(p) for p in (copy, wal)} == before
    assert not copy.with_name(copy.name + "-journal").exists()


def test_the_uri_is_read_only(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    _cache(db, _bars())
    assert real.copy_uri(db) == f"{db.resolve().as_uri()}?mode=ro&immutable=1"
    db.with_name(db.name + "-wal").write_bytes(b"")
    assert real.copy_uri(db) == f"{db.resolve().as_uri()}?mode=ro"


def test_reading_works_with_the_socket_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "copy.db"
    _cache(db, _bars())

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("network use")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert len(real.read_twii_bars(db)) == len(_bars())


# --- AST and import boundaries (C-2, C-3) ------------------------------------------------------


def _script_tree() -> ast.Module:
    return ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))


def _docstrings(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def _string_literals(tree: ast.AST) -> list[str]:
    skip = _docstrings(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
    ]


def _sql_words(text: str) -> set[str]:
    return {w.upper() for w in re.findall(r"[A-Za-z_]+", text)}


def test_the_script_has_one_select_of_the_eight_columns_and_no_write() -> None:
    literals = _string_literals(_script_tree())
    selects = [s for s in literals if "SELECT" in _sql_words(s)]
    assert len(selects) == 1
    select = " ".join(selects[0].split())
    assert select.startswith(
        "SELECT trade_date, open, high, low, close, volume, currency, source FROM price_bars_cache "
    )
    for word in ("as_of", "fetched_at"):
        assert word not in select.lower()
    banned = {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ATTACH", "REPLACE", "VACUUM"}
    for literal in literals:
        assert not _sql_words(literal) & banned, literal
    pragmas = [s for s in literals if "PRAGMA" in _sql_words(s)]
    assert pragmas == ["PRAGMA query_only=ON"]


def test_the_script_opens_one_connection_and_runs_two_statements() -> None:
    tree = _script_tree()
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    attrs = [n.func.attr for n in calls if isinstance(n.func, ast.Attribute)]
    assert attrs.count("connect") == 1
    assert attrs.count("execute") == 2
    for name in ("executescript", "executemany", "backup", "iterdump", "commit"):
        assert name not in attrs
    assert "PriceBarCache" not in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    # The reader part (above the outer flow) opens no file of its own: the outer flow's byte
    # copy is the only ``open`` of the script, and it is outside this part.
    reader = ast.Module(
        body=[n for n in tree.body if n.lineno < _outer_flow_line()], type_ignores=[]
    )
    assert "open" not in {n.id for n in ast.walk(reader) if isinstance(n, ast.Name)}


def _outer_flow_line() -> int:
    """The line of the marker comment that starts the outer flow."""
    for number, line in enumerate(SCRIPT_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("# === the outer flow"):
            return number
    raise AssertionError("the outer flow marker is missing")


def _script_imports(*, without: str | None = None) -> set[str]:
    """Every module the script imports; ``without`` names a function whose body is skipped."""
    tree = _script_tree()
    skipped: set[int] = set()
    for function in ast.walk(tree):
        if isinstance(function, ast.FunctionDef) and function.name == without:
            skipped.update(id(n) for n in ast.walk(function))
    found: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            base = node.module or ""
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def _hits(modules: set[str], banned: tuple[str, ...]) -> set[str]:
    return {m for m in modules if any(m == b or m.startswith(f"{b}.") for b in banned)}


def test_the_script_imports_no_forbidden_module() -> None:
    imports = _script_imports()
    assert "app.forecast.canonical" in imports  # the scan sees the real imports
    assert _hits(imports, FORBIDDEN_APP_MODULES) == set()
    # The one socket use is the loopback port check, a function-local import.
    assert _hits(_script_imports(without="port_is_listening"), NETWORK_MODULES) == set()
    assert _hits(imports, NETWORK_MODULES) == {"socket"}
    assert "importlib" not in imports and "__import__" not in {
        n.id for n in ast.walk(_script_tree()) if isinstance(n, ast.Name)
    }


def test_the_isolated_import_is_silent_and_loads_no_forbidden_module(tmp_path: Path) -> None:
    # The way the one-click file will run it: ``python -I`` from an unrelated folder.
    banned = FORBIDDEN_APP_MODULES + RUNTIME_NETWORK_MODULES
    code = (
        "import runpy, sys\n"
        f"runpy.run_path({str(SCRIPT_PATH)!r})\n"
        f"banned = {banned!r}\n"
        "hits = [m for m in sys.modules if any(m == b or m.startswith(b + '.') for b in banned)]\n"
        "sys.exit(3 if hits else 0)\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
    assert list(tmp_path.iterdir()) == []


def test_the_depth_numbers_are_derived_not_written() -> None:
    tree = _script_tree()
    for name in ("required_sessions", "check_depth", "placeholder_rulesets"):
        function = next(
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name
        )
        numbers = [
            n.value
            for n in ast.walk(function)
            if isinstance(n, ast.Constant) and type(n.value) in (int, float)
        ]
        assert numbers == [], name


# --- bars_sha256 (C-7, K-6) --------------------------------------------------------------------


def _independent_digest(bars: list[PriceBar]) -> str:
    return content_sha256(
        [
            {
                "session_date": b.date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "source": b.source,
                "as_of": b.as_of,
                "fetched_at": b.as_of,
            }
            for b in bars
        ]
    )


def test_bars_sha256_is_the_content_sha256_of_the_injected_series(tmp_path: Path) -> None:
    db = tmp_path / "copy.db"
    _cache(db, _bars())
    bars = real.read_twii_bars(db)

    digest = real.bars_sha256(bars)

    assert digest == _independent_digest(bars)
    assert digest == real.bars_sha256(bars) == real.bars_sha256(real.read_twii_bars(db))
    changed = [*bars[:-1], bars[-1].model_copy(update={"close": bars[-1].close + 1})]
    assert real.bars_sha256(changed) != digest


def test_bars_sha256_has_no_serialisation_of_its_own() -> None:
    tree = _script_tree()
    function = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "bars_sha256"
    )
    called = {
        n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
        for n in ast.walk(function)
        if isinstance(n, ast.Call)
    }
    assert "content_sha256" in called
    assert not called & {"dumps", "sha256", "hexdigest", "encode", "canonical_json"}


# --- RC-158b: nobody else points read_twii_bars at a real path --------------------------------


#: No literal: the scan flags a string that is just the name (a ``getattr`` route).
TARGET: str = real.read_twii_bars.__name__
TMP_ROOTS = frozenset({"tmp_path", "tmp_path_factory"})


def _mentions(node: ast.AST, names: set[str]) -> bool:
    return any(isinstance(n, ast.Name) and n.id in names for n in ast.walk(node))


def _tmp_derived(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names in ``function`` bound (directly or transitively) from a ``tmp_path`` parameter.

    A fixture may hand a ``tmp_path`` built value to a test only through
    another parameter, which this scan does not follow -- that case is reported,
    never silently allowed.
    """
    derived = {a.arg for a in function.args.args + function.args.kwonlyargs if a.arg in TMP_ROOTS}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(function):
            if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if _mentions(node.value, derived):
                    for target in targets:
                        for name in ast.walk(target):
                            if isinstance(name, ast.Name) and name.id not in derived:
                                derived.add(name.id)
                                changed = True
    return derived


def rc158b_violations(source: str) -> list[str]:
    """Every use of ``read_twii_bars`` in ``source`` that is not a call on a ``tmp_path`` path."""
    tree = ast.parse(source)
    found: list[str] = []
    calls: set[int] = set()
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        derived = _tmp_derived(function)
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name != TARGET:
                continue
            calls.add(id(func))
            arguments = [*node.args, *(k.value for k in node.keywords)]
            if len(arguments) != 1 or not _mentions(arguments[0], derived):
                found.append(ast.unparse(node))
    # ``x.read_twii_bars.__name__`` only names the function; it reads nothing.
    calls.update(
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "__name__"
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute | ast.Name) and id(node) not in calls:
            if (node.attr if isinstance(node, ast.Attribute) else node.id) == TARGET:
                found.append(f"reference: {ast.unparse(node)}")
        elif isinstance(node, ast.alias) and node.name == TARGET and node.asname:
            found.append(f"alias: {node.asname}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.fullmatch(r"\s*read_twii_bars\s*", node.value):
                found.append(f"string: {node.value!r}")
    return found


def _other_sources() -> dict[Path, str]:
    files = [*(BACKEND / "scripts").rglob("*.py"), *(BACKEND / "tests").rglob("*.py")]
    return {p: p.read_text(encoding="utf-8") for p in files if p != SCRIPT_PATH}


def test_rc158b_no_other_script_or_test_reads_a_non_tmp_path() -> None:
    sources = _other_sources()
    assert Path(__file__).resolve() in {p.resolve() for p in sources}
    violations = {p: v for p, s in sources.items() if (v := rc158b_violations(s))}
    assert violations == {}
    # Other scripts may not call it at all: the real-data reader is this script's alone.
    scripts = {p for p in sources if p.is_relative_to(BACKEND / "scripts") and TARGET in sources[p]}
    assert scripts == set()


def test_rc158b_finds_this_files_own_calls() -> None:
    own = Path(__file__).read_text(encoding="utf-8")
    assert own.count(f"real.{TARGET}(") >= 10
    assert rc158b_violations(own) == []


@pytest.mark.parametrize(
    "source",
    [
        "def f():\n    real.read_twii_bars(Path('data/stock-desk.db'))\n",
        "def f(path):\n    read_twii_bars(path)\n",
        "def test(tmp_path):\n    read_twii_bars(BACKEND / 'data' / 'stock-desk.db')\n",
        "def test(tmp_path):\n    p = resolve_db_path()\n    read_twii_bars(p)\n",
        "def test(tmp_path):\n    read_twii_bars(copy_path=os.environ['STOCK_DESK_DB_PATH'])\n",
        "reader = real.read_twii_bars\n",
        "from pipeline_acceptance_real import read_twii_bars as r\n",
        "def f():\n    getattr(real, 'read_twii_bars')(x)\n",
        "real.read_twii_bars(x)\n",
    ],
)
def test_the_rc158b_scan_has_teeth(source: str) -> None:
    assert rc158b_violations(source) != []


@pytest.mark.parametrize(
    "source",
    [
        "def test(tmp_path):\n    read_twii_bars(tmp_path / 'copy.db')\n",
        "def test(tmp_path):\n    db = tmp_path / 'c' / 'copy.db'\n    real.read_twii_bars(db)\n",
        "def test(tmp_path):\n    a = tmp_path / 'c'\n    b = a / 'x.db'\n    read_twii_bars(b)\n",
    ],
)
def test_the_rc158b_scan_allows_tmp_path_reads(source: str) -> None:
    assert rc158b_violations(source) == []
