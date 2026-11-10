"""N-212: the N-207 pre-deployment inventory (``scripts/n207_preflight``).

Every test builds its own database under ``tmp_path``; no real DB is ever touched.
The schema comes from the app's ``_SCHEMA`` so the SQL is pinned to the real tables.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import random
import re
import sqlite3
import subprocess
import sys
from collections.abc import Iterable, Sequence
from contextlib import closing
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from app.playbook.models import RuleParams
from app.playbook.store import _SCHEMA

PREFLIGHT_DIR = Path(__file__).resolve().parents[1] / "scripts" / "n207_preflight"
RUNNER_PATH = PREFLIGHT_DIR / "run_preflight.py"

# Positive shape rule from work/reviews/2026-11-10-N207台股代號形狀規則-data-engineer.md.
TW_SYMBOL_SHAPE = re.compile(
    r"[1-9][0-9]{3}[A-JL-Z]?"
    r"|00[0-9]{2,4}[A-JL-Z]?"
    r"|91[0-9]{4}"
)

PAST = "2000-01-01"
FUTURE = "2999-01-01"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_preflight_under_test", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


# --- helpers ----------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "preflight.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        for statement in _SCHEMA:
            conn.execute(statement)
    return path


def _exec(db_path: Path, sql: str, params: Sequence[object] = ()) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(sql, params)


def add_batch(db_path: Path, symbol: object, batch_no: object, status: object = "planned") -> None:
    _exec(
        db_path,
        "INSERT INTO playbook_batches (symbol, batch_no, status, updated_at) VALUES (?, ?, ?, 'x')",
        (symbol, batch_no, status),
    )


def add_symbol(db_path: Path, symbol: object, high_volatility: object = 0) -> None:
    _exec(
        db_path,
        "INSERT INTO playbook_symbols (symbol, high_volatility) VALUES (?, ?)",
        (symbol, high_volatility),
    )


def add_params(db_path: Path, version: int, effective: str, payload: str) -> None:
    _exec(
        db_path,
        "INSERT INTO playbook_rule_params (version, payload, submitted_at, effective_date, status)"
        " VALUES (?, ?, 'x', ?, 'active')",
        (version, payload, effective),
    )


def set_state(db_path: Path, key: str, value: str = "1") -> None:
    _exec(db_path, "INSERT INTO playbook_state (key, value) VALUES (?, ?)", (key, value))


def add_directive(
    db_path: Path,
    *,
    symbol: str = "2330",
    batch_no: int | None = 1,
    action: str = "buy",
    rule_id: str = "R1",
    settled: int = 0,
) -> None:
    _exec(
        db_path,
        "INSERT INTO playbook_directives (created_at, rules_version, symbol, batch_no, action,"
        " shares, rule_id, rule_summary, data_date, execution_date, data_status, source, status,"
        " settled) VALUES ('x', 1, ?, ?, ?, 1, ?, 'x', 'x', 'x', 'x', 'x', 'pending', ?)",
        (symbol, batch_no, action, rule_id, settled),
    )


def results(db_path: Path) -> dict[str, str]:
    lines, ok = runner.run(str(db_path))
    assert ok, lines
    return dict(line.split("\t") for line in lines)


def run_sql(db_path: Path, stem: str) -> str:
    with closing(sqlite3.connect(db_path)) as conn:
        return str(runner.run_item(conn, stem))


def make_params(**overrides: object) -> str:
    base = RuleParams(version=1, effective_date=date(2000, 1, 1))
    return base.model_copy(update=overrides).model_dump_json()


ALL_LABELS = [label for label, _ in runner.ITEMS]


# --- contract of the runner -------------------------------------------------------------


def test_every_sql_file_is_wired_and_p4b_is_not() -> None:
    stems = {stem for _, stem in runner.ITEMS}
    on_disk = {p.stem for p in PREFLIGHT_DIR.glob("*.sql")}
    assert on_disk - stems == {"p4b_LOCAL_ONLY"}
    assert stems <= on_disk
    assert "p4b" not in {label.lower().replace("-", "") for label in ALL_LABELS}


def test_p4b_is_local_only_and_warns_in_its_header() -> None:
    text = (PREFLIGHT_DIR / "p4b_LOCAL_ONLY.sql").read_text(encoding="utf-8")
    head = text.split("SELECT", 1)[0]
    assert "LOCAL ONLY" in head and "NEVER executes" in head
    assert "chat" in head and "work/" in head and "any agent" in head
    assert "不得貼回" in head


def test_runner_never_reads_p4b(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    add_symbol(db, "2330", 1)
    opened: list[str] = []
    original = Path.read_text

    def spy(self: Path, *args: object, **kwargs: object) -> str:
        opened.append(self.name)
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", spy)
    runner.run(str(db))
    assert opened and not any("p4b" in name for name in opened)


def test_runner_uses_only_the_standard_library_and_no_app_or_network() -> None:
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert modules <= set(sys.stdlib_module_names)
    assert not modules & {"app", "socket", "urllib3", "http", "requests", "httpx", "ssl"}
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "urllib.request" not in source and ".db" not in source


def test_read_only_connection_rejects_every_write(db: Path) -> None:
    with closing(sqlite3.connect(runner.read_only_uri(str(db)), uri=True)) as conn:
        for statement in (
            "INSERT INTO playbook_state (key, value) VALUES ('k', 'v')",
            "CREATE TABLE t (x)",
            "DELETE FROM playbook_batches",
        ):
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute(statement)


def test_read_only_uri_does_not_create_a_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "absent.db"
    lines, ok = runner.run(str(missing))
    assert not ok and not missing.exists()
    assert lines == [f"{label}\tERROR" for label in ALL_LABELS]


def test_path_with_special_characters_is_opened(tmp_path: Path) -> None:
    folder = tmp_path / "a b#c?d%"
    folder.mkdir()
    path = folder / "x.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        for statement in _SCHEMA:
            conn.execute(statement)
    assert results(path)["P-1"] == "0"


def test_empty_tables_answer_zero_for_every_item(db: Path) -> None:
    out = results(db)
    assert list(out) == ALL_LABELS
    for label, value in out.items():
        expected = {"P-2": "0,0,0,0,0", "P-3": "0,5"}.get(label, "0")
        assert value == expected, label
    # Every number except n_targets (the default, not data) is zero.
    flat = [int(v) for value in out.values() for v in value.split(",")]
    assert sorted(flat)[-1] == RuleParams(effective_date=date(2000, 1, 1)).n_targets
    assert sorted(flat)[-2] == 0


def test_output_has_one_tab_separated_line_per_item_and_no_symbol(db: Path) -> None:
    seeded = ["2330", "00631L", "SECRETK", "ＡＢＣ", "2330k"]
    for i, symbol in enumerate(seeded):
        add_batch(db, symbol, i + 1, "bogus")
        add_symbol(db, symbol, 7)
    lines, ok = runner.run(str(db))
    assert ok and len(lines) == len(ALL_LABELS)
    text = "\n".join(lines)
    for symbol in seeded:
        assert symbol not in text
    for line in lines:
        label, value = line.split("\t")
        assert re.fullmatch(r"[0-9]+(,[0-9]+)*", value), line
        assert label in ALL_LABELS


def test_cli_prints_lines_and_exits_zero(db: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-I", str(RUNNER_PATH), str(db)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0 and done.stderr == ""
    assert done.stdout.splitlines()[0] == "P-1\t0"


def test_cli_usage_error_is_non_zero() -> None:
    assert runner.main([]) == 2
    assert runner.main(["a", "b"]) == 2


def test_main_returns_zero_and_prints(db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert runner.main([str(db)]) == 0
    assert capsys.readouterr().out.count("\t") == len(ALL_LABELS)


# --- errors are loud: ERROR + non-zero, never a silent 0 --------------------------------


def test_missing_table_prints_error_and_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "partial.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(_SCHEMA[0])  # playbook_batches only
    assert runner.main([str(path)]) == 1
    out = dict(line.split("\t") for line in capsys.readouterr().out.splitlines())
    assert out["P-5"] == "0"  # only playbook_batches is needed
    assert out["P-1"] == "ERROR"  # playbook_rule_params is missing
    assert out["P-4a"] == "ERROR"  # playbook_symbols is missing
    assert out["P-9a"] == "ERROR"
    assert out["P-6"] == "ERROR"  # playbook_state is missing: never a silent zero


def test_invalid_json_payload_is_an_error_not_a_default(db: Path) -> None:
    add_params(db, 1, PAST, "{not json")
    lines, ok = runner.run(str(db))
    assert not ok
    out = dict(line.split("\t") for line in lines)
    assert out["P-1"] == out["P-2"] == out["P-3"] == "ERROR"
    assert out["P-5"] == "0"  # items that do not read the payload are unaffected


def test_not_a_database_file_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "junk.db"
    path.write_bytes(b"this is not a sqlite database" * 20)
    lines, ok = runner.run(str(path))
    assert not ok and all(line.endswith("\tERROR") for line in lines)


def test_non_integer_result_is_an_error() -> None:
    with pytest.raises(ValueError):
        runner._format_row((None,))
    with pytest.raises(ValueError):
        runner._format_row((True,))


def test_multi_row_result_is_an_error(
    db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "p1.sql").write_text("SELECT 1 UNION ALL SELECT 2;", encoding="utf-8")
    monkeypatch.setattr(runner, "SQL_DIR", fake)
    with closing(sqlite3.connect(db)) as conn:
        with pytest.raises(ValueError):
            runner.run_item(conn, "p1")
    lines, ok = runner.run(str(db))
    assert not ok and lines[0] == "P-1\tERROR"


# --- defaults pinned to RuleParams() ----------------------------------------------------


def _default_literal(stem: str, key: str) -> int:
    sql = (PREFLIGHT_DIR / f"{stem}.sql").read_text(encoding="utf-8")
    found = re.findall(
        rf"COALESCE\(\(SELECT json_extract\(payload, '\$\.{key}'\) FROM cur\), (\d+)\)", sql
    )
    assert len(found) == 1, (stem, key)
    return int(found[0])


@pytest.mark.parametrize(
    ("stem", "key"),
    [
        ("p1", "batches_per_target"),
        ("p2", "batches_per_target"),
        ("p3", "n_targets"),
    ],
)
def test_sql_default_literals_equal_ruleparams_defaults(stem: str, key: str) -> None:
    defaults = RuleParams(effective_date=date(2000, 1, 1))
    assert _default_literal(stem, key) == getattr(defaults, key)
    assert key in RuleParams.model_fields


@pytest.mark.parametrize("stem", ["p1", "p2", "p3"])
def test_current_parameter_row_selection_matches_active_params(stem: str) -> None:
    sql = " ".join((PREFLIGHT_DIR / f"{stem}.sql").read_text(encoding="utf-8").split())
    store_source = Path(__file__).resolve().parents[1] / "app" / "playbook" / "store.py"
    store_text = " ".join(store_source.read_text(encoding="utf-8").split())
    assert "WHERE effective_date <= ? ORDER BY effective_date DESC, version DESC LIMIT 1" in (
        store_text.replace('" "', "")
    )
    assert (
        "WHERE effective_date <= date('now', '+8 hours') "
        "ORDER BY effective_date DESC, version DESC LIMIT 1"
    ) in sql


# --- P-1 --------------------------------------------------------------------------------


def _fill(db_path: Path, symbol: str, numbers: Iterable[int]) -> None:
    for number in numbers:
        add_batch(db_path, symbol, number)


def test_p1_positive_and_negative(db: Path) -> None:
    _fill(db, "A", [1, 2, 3])
    assert run_sql(db, "p1") == "0"
    _fill(db, "B", [1, 2])
    _fill(db, "C", [1, 2, 3, 4])
    assert run_sql(db, "p1") == "2"


def test_p1_uses_the_current_parameter_row(db: Path) -> None:
    _fill(db, "A", [1, 2])
    assert run_sql(db, "p1") == "1"  # default bpt 3
    add_params(db, 1, PAST, make_params(batches_per_target=2))
    assert run_sql(db, "p1") == "0"
    add_params(db, 2, FUTURE, make_params(batches_per_target=3))  # not in force yet
    assert run_sql(db, "p1") == "0"
    add_params(db, 3, "2001-01-01", make_params(batches_per_target=4))  # newer, in force
    assert run_sql(db, "p1") == "1"


def test_p1_missing_key_falls_back_to_the_default(db: Path) -> None:
    add_params(db, 1, PAST, json.dumps({"n_targets": 9}))
    _fill(db, "A", [1, 2, 3])
    assert run_sql(db, "p1") == "0"


def test_ties_on_effective_date_pick_the_highest_version(db: Path) -> None:
    add_params(db, 1, PAST, make_params(batches_per_target=2))
    add_params(db, 2, PAST, make_params(batches_per_target=3))
    _fill(db, "A", [1, 2, 3])
    assert run_sql(db, "p1") == "0"


# --- P-2 --------------------------------------------------------------------------------


def test_p2_negative_clean_book(db: Path) -> None:
    _fill(db, "A", [1, 2, 3])
    _fill(db, "B", [1, 2, 3])
    assert run_sql(db, "p2") == "0,0,0,0,0"


@pytest.mark.parametrize(
    ("numbers", "expected"),
    [
        ([1, 2, 3, 4], "1,0,0,0,0"),  # max above bpt
        ([2, 3], "0,1,0,0,0"),  # min is 2
        ([0, 1, 2], "0,1,1,0,0"),  # min below 1 (also counts as min != 1)
        ([-1, 1, 2], "0,1,1,1,0"),  # negative min with a gap
        ([1, 3], "0,0,0,1,0"),  # gap
    ],
)
def test_p2_positive_cases(db: Path, numbers: list[int], expected: str) -> None:
    _fill(db, "A", numbers)
    assert run_sql(db, "p2") == expected


def test_p2_fifth_count_catches_non_integer_batch_no(db: Path) -> None:
    _fill(db, "A", [1, 2])
    add_batch(db, "A", "x")  # stays TEXT under INTEGER affinity
    add_batch(db, "B", 1.5)  # stays REAL
    add_batch(db, "C", b"\x01")  # BLOB
    parts = run_sql(db, "p2").split(",")
    assert parts[4] == "3"


def test_p2_counts_symbols_not_rows(db: Path) -> None:
    _fill(db, "A", [2, 3])
    _fill(db, "B", [2, 3])
    assert run_sql(db, "p2") == "0,2,0,0,0"


def test_p2_uses_bpt_from_the_current_row(db: Path) -> None:
    _fill(db, "A", [1, 2, 3, 4])
    add_params(db, 1, PAST, make_params(batches_per_target=4))
    assert run_sql(db, "p2") == "0,0,0,0,0"


# --- 1d and 1d-2 ------------------------------------------------------------------------


def test_d1_positive_and_negative(db: Path) -> None:
    add_batch(db, "2330", 1)
    add_directive(db, symbol="2330", batch_no=1)  # matches a batch: clean
    add_directive(db, symbol="2330", batch_no=None)  # NULL is 1d-2's business
    add_directive(db, symbol="2330", batch_no=0, settled=1)  # settled: ignored
    assert run_sql(db, "d1") == "0"
    add_directive(db, symbol="2330", batch_no=0)  # batch_no < 1
    add_directive(db, symbol="9999", batch_no=2)  # no matching batch row
    assert run_sql(db, "d1") == "2"


def test_d1_2_positive_and_negative(db: Path) -> None:
    add_directive(db, batch_no=None, rule_id="S2", action="sell")  # S2 excluded
    add_directive(db, batch_no=None, rule_id="R2", action="defer")  # not buy/sell
    add_directive(db, batch_no=None, rule_id="R1", action="buy", settled=1)  # settled
    add_directive(db, batch_no=1, rule_id="R1", action="buy")  # batch_no present
    assert run_sql(db, "d1_2") == "0"
    add_directive(db, batch_no=None, rule_id="R1", action="buy")
    add_directive(db, batch_no=None, rule_id="P1", action="sell")
    assert run_sql(db, "d1_2") == "2"


# --- P-3 --------------------------------------------------------------------------------


def test_p3_counts_distinct_symbols_and_reports_n_targets(db: Path) -> None:
    assert run_sql(db, "p3") == "0,5"
    _fill(db, "A", [1, 2, 3])
    _fill(db, "B", [1])
    assert run_sql(db, "p3") == "2,5"  # distinct symbols, not rows
    add_params(db, 1, PAST, make_params(n_targets=1))
    assert run_sql(db, "p3") == "2,1"  # more symbols than targets: STOP-2 reading


def test_p3_ignores_a_future_parameter_row(db: Path) -> None:
    add_params(db, 1, FUTURE, make_params(n_targets=9))
    assert run_sql(db, "p3") == "0,5"


# --- P-4a / P-4c ------------------------------------------------------------------------


def test_p4_t30_seeding_gives_p4a_5_and_p4c_4(db: Path) -> None:
    values: list[object] = [0, 1, 2, -1, "x", 0.5]
    for i, value in enumerate(values):
        add_symbol(db, f"S{i}", value)
    with closing(sqlite3.connect(db)) as conn:
        types = [r[0] for r in conn.execute("SELECT typeof(high_volatility) FROM playbook_symbols")]
    assert types == ["integer", "integer", "integer", "integer", "text", "real"]
    assert run_sql(db, "p4a") == "5"
    assert run_sql(db, "p4c") == "4"


def test_p4_negative_when_only_zero_and_one(db: Path) -> None:
    add_symbol(db, "A", 0)
    add_symbol(db, "B", 0)
    assert run_sql(db, "p4a") == "0" and run_sql(db, "p4c") == "0"
    add_symbol(db, "C", 1)
    assert run_sql(db, "p4a") == "1" and run_sql(db, "p4c") == "0"


# --- P-5 --------------------------------------------------------------------------------


def test_p5_positive_and_negative(db: Path) -> None:
    for i, status in enumerate(["planned", "open", "closed", "skipped"]):
        add_batch(db, "A", i + 1, status)
    assert run_sql(db, "p5") == "0"
    add_batch(db, "B", 1, "Open")  # BINARY comparison: case matters
    add_batch(db, "B", 3, 7)  # non-TEXT value
    add_batch(db, "B", 4, "")
    assert run_sql(db, "p5") == "3"


def test_p5_counts_a_null_status_on_a_table_without_the_constraint(tmp_path: Path) -> None:
    path = tmp_path / "loose.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE playbook_batches (symbol TEXT, batch_no INTEGER, status TEXT)")
        conn.execute("INSERT INTO playbook_batches VALUES ('A', 1, NULL)")
        conn.execute("INSERT INTO playbook_batches VALUES ('A', 2, 'open')")
    assert run_sql(path, "p5") == "1"


# --- P-6 / P-7 / P-8 --------------------------------------------------------------------


def test_p6(db: Path) -> None:
    assert run_sql(db, "p6") == "0"  # unconfirmed and empty
    set_state(db, "rule_set_confirmed_at")
    assert run_sql(db, "p6") == "1"  # confirmed x empty batch table
    add_batch(db, "A", 1)
    assert run_sql(db, "p6") == "0"


def test_p6_a_parameter_row_also_confirms_authorship(db: Path) -> None:
    add_params(db, 1, PAST, make_params())
    assert run_sql(db, "p6") == "1"


def test_p7(db: Path) -> None:
    assert run_sql(db, "p7") == "0"
    set_state(db, "total_deploy")
    assert run_sql(db, "p7") == "1"  # unconfirmed x TD key present
    set_state(db, "rule_set_confirmed_at")
    assert run_sql(db, "p7") == "0"


def test_p7_a_parameter_row_means_confirmed(db: Path) -> None:
    set_state(db, "total_deploy")
    add_params(db, 1, PAST, make_params())
    assert run_sql(db, "p7") == "0"


def test_p8(db: Path) -> None:
    assert run_sql(db, "p8") == "0"  # unconfirmed
    set_state(db, "rule_set_confirmed_at")
    assert run_sql(db, "p8") == "1"  # confirmed x no cash key
    set_state(db, "cash", "100")
    assert run_sql(db, "p8") == "0"


def test_p8_a_parameter_row_confirms_and_cash_key_clears_it(db: Path) -> None:
    add_params(db, 1, PAST, make_params())
    assert run_sql(db, "p8") == "1"
    set_state(db, "cash")
    assert run_sql(db, "p8") == "0"


def test_state_key_literals_equal_the_store_constants() -> None:
    from app.playbook import store

    sql = {
        stem: (PREFLIGHT_DIR / f"{stem}.sql").read_text(encoding="utf-8")
        for stem in ("p6", "p7", "p8")
    }
    assert f"'{store.STATE_RULE_SET_CONFIRMED_AT}'" in sql["p6"]
    assert f"'{store.STATE_TOTAL_DEPLOY}'" in sql["p7"]
    assert f"'{store.STATE_CASH}'" in sql["p8"]


# --- P-9a..c (N207-T31 seeding) ---------------------------------------------------------


def test_p9a_counts_k_suffix_only(db: Path) -> None:
    for symbol in ["2330k", "00625Ｋ", "00625K ", "00625K\n", "2330"]:
        add_symbol(db, symbol)
    assert run_sql(db, "p9a") == "0"
    for symbol in ["00625K", "2330K", "ABCK", " 00625K"]:
        add_symbol(db, symbol)
    assert run_sql(db, "p9a") == "4"


def test_p9a_counts_a_symbol_in_both_tables_once_and_batches_only(db: Path) -> None:
    add_symbol(db, "00625K")
    add_batch(db, "00625K", 1)  # same symbol in both tables
    add_batch(db, "2330K", 1)  # batches only
    assert run_sql(db, "p9a") == "2"


def test_p9b_blob_symbol_counts_once_and_p9a_skips_it(db: Path) -> None:
    add_batch(db, bytes.fromhex("30303632354B"), 1)  # the bytes of "00625K"
    assert run_sql(db, "p9b") == "1"
    assert run_sql(db, "p9a") == "0"
    assert run_sql(db, "p9c") == "0"  # a non-TEXT symbol is not P-9c's business


def test_p9b_negative_for_text_symbols(db: Path) -> None:
    add_symbol(db, "2330")
    add_batch(db, "2330", 1)
    assert run_sql(db, "p9b") == "0"


POSITIVE_SHAPES = [
    "2330", "1101", "6488", "9999", "2882A", "2891B", "0050", "0056", "00878", "00940",
    "006208", "00631L", "00632R", "00635U", "00679B", "00720B", "00981A", "9103", "910322",
    "1000",
]  # fmt: skip
NEGATIVE_SHAPES = [
    "2330.TW", "2330.TWO", "2330.US", "", "  ", " 2330", "2330 ", "2330\n", "23 30",
    "２３３０", "００５０", "2330k", "00631l", "2330K",
    "00625K", "233", "23300", "1234567", "0000000", "030001", "2330AB", "2330A1", "A2330",
    "TSMC", "AAPL", "^TWII", "-2330",
]  # fmt: skip


def p9c_expected(symbol: str) -> bool:
    return not symbol.endswith("K") and TW_SYMBOL_SHAPE.fullmatch(symbol) is None


@pytest.mark.parametrize("symbol", POSITIVE_SHAPES)
def test_p9c_accepts_every_valid_shape(db: Path, symbol: str) -> None:
    add_symbol(db, symbol)
    assert run_sql(db, "p9c") == "0"
    assert run_sql(db, "p9a") == "0"


@pytest.mark.parametrize("symbol", NEGATIVE_SHAPES)
def test_p9c_matches_the_python_rule_on_every_invalid_shape(db: Path, symbol: str) -> None:
    add_symbol(db, symbol)
    assert run_sql(db, "p9c") == ("1" if p9c_expected(symbol) else "0")
    assert run_sql(db, "p9a") == ("1" if symbol.endswith("K") else "0")


def test_p9c_k_suffixed_symbols_belong_to_p9a_only(db: Path) -> None:
    add_symbol(db, "00625K")
    assert run_sql(db, "p9a") == "1" and run_sql(db, "p9c") == "0"


def test_p9c_distinct_across_tables(db: Path) -> None:
    add_symbol(db, "ABC")
    add_batch(db, "ABC", 1)
    add_batch(db, "XYZ", 1)
    assert run_sql(db, "p9c") == "2"


def test_p9_property_equivalence_with_python_rules(db: Path) -> None:
    alphabet = list("0123456789") + list("ABCKLZ") + list("abckl") + [
        "Ｋ", "０", " ", "\n", ".",
    ]  # fmt: skip
    rng = random.Random(207)
    with closing(sqlite3.connect(db)) as conn:
        for seed in range(400):
            symbol = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8)))
            if seed % 3 == 0:  # bias toward realistic shapes so both outcomes occur often
                symbol = rng.choice(POSITIVE_SHAPES + ["00625K"])[: rng.randint(0, 6)] + (
                    rng.choice(["", "K", "k", "A", "\n"])
                )
            conn.execute("DELETE FROM playbook_symbols")
            conn.execute("INSERT INTO playbook_symbols (symbol) VALUES (?)", (symbol,))
            assert runner.run_item(conn, "p9a") == ("1" if symbol.endswith("K") else "0"), symbol
            assert runner.run_item(conn, "p9c") == ("1" if p9c_expected(symbol) else "0"), symbol
