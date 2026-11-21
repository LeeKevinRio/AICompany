"""``python -m app.forecast.claims bootstrap --production`` (ADR-0030 supplement 4 points 2-3,
supplement 6 addendum point 7, supplement 7 points 5-6 and addendum point 3).

Every "production" database here is a synthetic ``tmp_path`` stand-in: a
stand-in backend folder ``<root>/apps/stock-desk/backend`` inside a ``tmp_path``
git repository holds ``data/stock-desk.db`` with one non-ledger table, and is
passed to ``claims.main`` as ``backend_dir`` (the way ``production_path_refusal``
is driven). The pre-registration is a synthetic file committed in that
repository. No test opens, stats or names the service database, and bootstrap
never runs on a real one. The rule sets and the definition are the published
CG-2 ones.

Covered: 0 and 1 each register (exit 0) with the output lines' exact forms and
no path or identifier in them; every exit 4 condition (target missing, resolving
elsewhere, not a regular file, ``STOCK_DESK_DB_PATH`` in the environment or in
the ``.env`` file, existing ledger objects -- refused in the transaction --, the
horizons, a replacement) and every exit 3 one (typed value, commit, path and
sha256 formats, the blob at the commit, the review refs, an unpublished
version, a store refusal), each writing nothing; exit 5 for each of the four
post-commit checks, schema first; exit 2 without the typed value (no default);
unexpected exceptions propagate; the AST boundaries of the bootstrap branch.
"""

from __future__ import annotations

import ast
import hashlib
import re
import sqlite3
import subprocess
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest

from app.forecast import claims, definitions
from app.forecast import store as store_module
from app.forecast.canonical import APP_ROOT
from app.forecast.schema import SchemaStatus
from app.forecast.store import ForecastStore, LedgerInconsistentError, RunRow
from tests.forecast_ledger_helpers import taipei

H3: Final = "outlook-market-v1.0-h3"
H5: Final = "outlook-market-v1.0-h5"
DEFINITION: Final = "dirdef-v1.0"
PREREG_PATH: Final = "work/research/prereg-v0.32.md"
PREREG: Final = b"# pre-registration v0.32 (synthetic fixture)\n"
PREREG_SHA256: Final = hashlib.sha256(PREREG).hexdigest()
REVIEW_REFS: Final = "work/reviews/risk.md work/reviews/qa.md"
APP_ROWS: Final = [("theme", "dark"), ("currency", "TWD")]
START: Final = taipei(2026, 11, 20, 21, 0)

#: The exact output lines of a successful bootstrap, in order.
OUTPUT_FORMS: Final = [
    r"bootstrap=ok",
    r"banned_phrase_scan_h3=hits 0 rules_strings \d+ definition_strings \d+ phrases \d+",
    r"banned_phrase_scan_h5=hits 0 rules_strings \d+ definition_strings \d+ phrases \d+",
    r"registered_rows=2",
    r"frozen_commit=[0-9a-f]{40}",
    r"prereg_doc_sha256=[0-9a-f]{64}",
    r"definition_sha256=[0-9a-f]{64}",
    r"definition_logic_sha256=[0-9a-f]{64}",
    r"rules_sha256_h3=[0-9a-f]{64}",
    r"rules_logic_sha256_h3=[0-9a-f]{64}",
    r"registered_at_h3=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00",
    r"rules_sha256_h5=[0-9a-f]{64}",
    r"rules_logic_sha256_h5=[0-9a-f]{64}",
    r"registered_at_h5=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00",
    r"provisional_results_seen=[01]",
    r"post_commit_check=ok",
]


class TickClock:
    """A store clock that moves one second per read."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now = self.now + timedelta(seconds=1)
        return self.now


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


#: ``iterdump`` lines and ``(journal_mode, user_version, application_id, page_size)``.
LogicalState = tuple[tuple[str, ...], tuple[object, ...]]
STATE_PRAGMAS: Final = ("journal_mode", "user_version", "application_id", "page_size")


def wal_of(db: Path) -> Path:
    return db.with_name(db.name + "-wal")


def logical_state(db: Path) -> LogicalState:
    """The database's logical content: its full dump and the four header pragmas (read-only)."""
    with closing(sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)) as conn:
        dump = tuple(conn.iterdump())
        pragmas = tuple(conn.execute(f"PRAGMA {name}").fetchone()[0] for name in STATE_PRAGMAS)
    return dump, pragmas


def app_rows(db: Path) -> list[tuple[str, str]]:
    with closing(sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)) as conn:
        return [(str(k), str(v)) for k, v in conn.execute("SELECT k, v FROM app_settings")]


class Desk:
    """A stand-in repository, backend folder and main database (all under ``tmp_path``)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.backend = root / "apps" / "stock-desk" / "backend"
        self.data = self.backend / "data"
        self.data.mkdir(parents=True)
        self.db = self.data / "stock-desk.db"
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("CREATE TABLE app_settings (k TEXT PRIMARY KEY, v TEXT)")
            conn.executemany("INSERT INTO app_settings VALUES (?, ?)", APP_ROWS)
            conn.execute("PRAGMA user_version = 7")
            conn.execute("PRAGMA application_id = 21316")
            conn.commit()
        prereg = root / PREREG_PATH
        prereg.parent.mkdir(parents=True)
        prereg.write_bytes(PREREG)
        _git(root, "init", "-q")
        _git(root, "add", PREREG_PATH)
        _git(root, "commit", "-q", "-m", "prereg")
        self.commit = _git(root, "rev-parse", "HEAD")
        self.clock = TickClock(START)

    def argv(self, **overrides: str | list[str] | None) -> list[str]:
        values: dict[str, str | list[str] | None] = {
            "--rules-version": [H3, H5],
            "--definition-version": DEFINITION,
            "--frozen-commit": self.commit,
            "--prereg-doc-path": PREREG_PATH,
            "--prereg-doc-sha256": PREREG_SHA256,
            "--review-refs": REVIEW_REFS,
            "--provisional-results-seen": "0",
        }
        values.update({f"--{k.replace('_', '-')}": v for k, v in overrides.items()})
        argv = ["bootstrap", "--production"]
        for flag, value in values.items():
            if isinstance(value, list):
                for item in value:
                    argv += [flag, item]
            elif value is not None:
                argv += [flag, value]
        return argv

    def main(self, argv: list[str], *, env: dict[str, str] | None = None) -> int:
        return claims.main(argv, env=env or {}, backend_dir=self.backend, clock=self.clock)

    def state(self) -> tuple[LogicalState, str | None, list[str] | None]:
        """The main database's logical state, plus its bytes and folder only without ``-wal``.

        RC-180 / RC-181: the logical state (``iterdump`` and four pragmas) is the
        evidence; the file hash and the folder listing are compared only when no
        ``-wal`` sits next to the file, since SQLite may checkpoint one.
        """
        logical = logical_state(self.db)
        if wal_of(self.db).exists():
            return logical, None, None
        digest = hashlib.sha256(self.db.read_bytes()).hexdigest()
        return logical, digest, sorted(p.name for p in self.data.iterdir())

    def registry(self) -> list[tuple[str, int, bytes]]:
        with closing(sqlite3.connect(f"{self.db.as_uri()}?mode=ro", uri=True)) as conn:
            return [
                (str(c), int(v), bytes(b))
                for c, v, b in conn.execute(
                    "SELECT claim_id, provisional_results_seen, prereg_doc_blob"
                    " FROM forecast_claim_registry ORDER BY rowid"
                )
            ]


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    return Desk(tmp_path)


def _no_path_or_identifier(text: str, desk: Desk) -> None:
    for forbidden in (str(desk.root), "/", "\\", "|", "outlook-market", "dirdef-v", "stock-desk"):
        assert forbidden not in text, forbidden


# --- exit 0 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("typed", ["0", "1"])
def test_bootstrap_registers_both_claims_with_the_typed_value(
    desk: Desk, typed: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = desk.main(desk.argv(provisional_results_seen=typed))
    out, err = capsys.readouterr()
    assert code == claims.EXIT_OK, err
    assert err == ""
    rows = desk.registry()
    assert [c for c, _, _ in rows] == [
        f"market|h3|{H3}|{DEFINITION}|forward",
        f"market|h5|{H5}|{DEFINITION}|forward",
    ]
    assert [v for _, v, _ in rows] == [int(typed)] * 2
    assert all(blob == PREREG for _, _, blob in rows)
    lines = out.splitlines()
    assert len(lines) == len(OUTPUT_FORMS)
    for line, form in zip(lines, OUTPUT_FORMS, strict=True):
        assert re.fullmatch(form, line), (line, form)
    assert f"provisional_results_seen={typed}" in lines
    assert f"frozen_commit={desk.commit}" in lines
    assert f"prereg_doc_sha256={PREREG_SHA256}" in lines
    _no_path_or_identifier(out, desk)
    store = ForecastStore(desk.db)
    assert store.ledger_schema_status().complete and store.runs() == []
    assert app_rows(desk.db) == APP_ROWS


def test_the_stored_blob_is_the_commits_not_the_working_tree(desk: Desk) -> None:
    (desk.root / PREREG_PATH).write_bytes(b"edited after the commit\n")
    assert desk.main(desk.argv()) == claims.EXIT_OK
    assert {blob for _, _, blob in desk.registry()} == {PREREG}


def test_the_output_names_the_registered_hashes(
    desk: Desk, capsys: pytest.CaptureFixture[str]
) -> None:
    assert desk.main(desk.argv()) == claims.EXIT_OK
    out = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines())
    h3, h5 = ForecastStore(desk.db).forward_claims()
    assert out["definition_sha256"] == h3.definition_sha256
    assert out["definition_logic_sha256"] == h3.definition_logic_sha256
    assert out["rules_sha256_h3"] == h3.rules_sha256 and out["rules_sha256_h5"] == h5.rules_sha256
    assert out["rules_logic_sha256_h5"] == h5.rules_logic_sha256


# --- exit 4 ---------------------------------------------------------------------------------


def _refused(
    desk: Desk,
    argv: list[str],
    code: int,
    sentence: str,
    capsys: pytest.CaptureFixture[str],
    *,
    env: dict[str, str] | None = None,
) -> None:
    before = desk.state() if desk.db.is_file() and not desk.db.is_symlink() else None
    assert desk.main(argv, env=env) == code
    out, err = capsys.readouterr()
    assert err.strip() == sentence
    assert out == ""
    _no_path_or_identifier(err, desk)
    if before is not None:
        assert desk.state() == before  # nothing written, no side file left


def test_4_the_production_database_is_missing(
    desk: Desk, capsys: pytest.CaptureFixture[str]
) -> None:
    desk.db.unlink()
    sentence = claims.BOOTSTRAP_PATH_REFUSALS["db_missing"]
    _refused(desk, desk.argv(), claims.EXIT_PATH_REFUSED, sentence, capsys)
    assert not desk.db.exists()
    assert list(desk.data.iterdir()) == []


def test_4_the_production_database_resolves_elsewhere(
    desk: Desk, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    elsewhere = tmp_path / "elsewhere.db"
    desk.db.rename(elsewhere)
    desk.db.symlink_to(elsewhere)
    before = hashlib.sha256(elsewhere.read_bytes()).hexdigest()
    sentence = claims.BOOTSTRAP_PATH_REFUSALS["db_not_default"]
    _refused(desk, desk.argv(), claims.EXIT_PATH_REFUSED, sentence, capsys)
    assert hashlib.sha256(elsewhere.read_bytes()).hexdigest() == before


def test_4_the_production_database_is_not_a_regular_file(
    desk: Desk, capsys: pytest.CaptureFixture[str]
) -> None:
    desk.db.unlink()
    desk.db.mkdir()
    sentence = claims.BOOTSTRAP_PATH_REFUSALS["db_not_regular"]
    _refused(desk, desk.argv(), claims.EXIT_PATH_REFUSED, sentence, capsys)
    assert list(desk.db.iterdir()) == []


@pytest.mark.parametrize("value", ["", "other.db"])
def test_4_the_environment_names_a_database(
    desk: Desk, value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_PATH_REFUSALS["env_db_path"]
    env = {"STOCK_DESK_DB_PATH": value}
    _refused(desk, desk.argv(), claims.EXIT_PATH_REFUSED, sentence, capsys, env=env)


#: ``.env`` lines that set the key: an ``export`` prefix (uv loads it) and any case (Windows).
ENV_FILE_KEY_LINES: Final = [
    "export STOCK_DESK_DB_PATH=x.db\n",
    "export\tSTOCK_DESK_DB_PATH=x.db\n",
    "  export \t STOCK_DESK_DB_PATH = \n",
    "stock_desk_db_path=x.db\n",
    "Stock_Desk_Db_Path=x.db\n",
    "EXPORT STOCK_DESK_DB_PATH=x.db\n",
    "Export stock_desk_DB_path=x.db\n",
]
#: ``.env`` lines that do not: a comment, another key, a key with ``export`` glued to it.
ENV_FILE_OTHER_LINES: Final = [
    "# STOCK_DESK_DB_PATH=x.db\n",
    "  # export STOCK_DESK_DB_PATH=x.db\n",
    "X_STOCK_DESK_DB_PATH=1\n",
    "STOCK_DESK_DB_PATH_X=1\n",
    "export X_STOCK_DESK_DB_PATH=1\n",
    "exportSTOCK_DESK_DB_PATH=1\n",
]


@pytest.mark.parametrize(
    "line",
    [
        "STOCK_DESK_DB_PATH=x.db\n",
        "  STOCK_DESK_DB_PATH = \n",
        "\ufeffSTOCK_DESK_DB_PATH=a\n",
        *ENV_FILE_KEY_LINES,
    ],
)
def test_4_the_env_file_names_a_database(
    desk: Desk, line: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # The key line first, so a BOM is at the start of the file (utf-8-sig strips it).
    (desk.backend.parent / ".env").write_text(f"{line}OTHER=1\n", encoding="utf-8")
    sentence = claims.BOOTSTRAP_PATH_REFUSALS["env_file_db_path"]
    _refused(desk, desk.argv(), claims.EXIT_PATH_REFUSED, sentence, capsys)


def test_an_env_file_without_the_key_does_not_refuse(desk: Desk) -> None:
    (desk.backend.parent / ".env").write_text(
        "OTHER=1\n# STOCK_DESK_DB_PATH=commented\nX_STOCK_DESK_DB_PATH=1\n", encoding="utf-8"
    )
    assert desk.main(desk.argv()) == claims.EXIT_OK


@pytest.mark.parametrize("line", ENV_FILE_OTHER_LINES)
def test_4_an_env_file_line_naming_no_database_does_not_refuse(desk: Desk, line: str) -> None:
    (desk.backend.parent / ".env").write_text(f"{line}OTHER=1\n", encoding="utf-8")
    assert claims.env_file_sets_db_path(desk.backend.parent / ".env") is False
    assert desk.main(desk.argv()) == claims.EXIT_OK


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE forecast_extra (a)",
        "CREATE TABLE plan_items (a)",
        "CREATE VIEW Forecast_view AS SELECT 1",
        "CREATE INDEX forecast_by_v ON app_settings (v)",
    ],
)
def test_4_existing_ledger_objects_are_refused_in_the_transaction(
    desk: Desk, ddl: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with closing(sqlite3.connect(desk.db)) as conn:
        conn.execute(ddl)
        conn.commit()
    sentence = claims.BOOTSTRAP_PATH_REFUSALS["not_empty"]
    _refused(desk, desk.argv(), claims.EXIT_PATH_REFUSED, sentence, capsys)


def test_4_a_second_bootstrap_is_refused(desk: Desk, capsys: pytest.CaptureFixture[str]) -> None:
    assert desk.main(desk.argv()) == claims.EXIT_OK
    capsys.readouterr()
    sentence = claims.BOOTSTRAP_PATH_REFUSALS["not_empty"]
    _refused(desk, desk.argv(provisional_results_seen="1"), 4, sentence, capsys)
    assert [v for _, v, _ in desk.registry()] == [0, 0]


@pytest.mark.parametrize(
    "versions",
    [[H5, H3], [H3], [H3, H3], [H3, H5, H5]],
    ids=["reversed", "one", "h3_twice", "three"],
)
def test_4_the_two_claims_must_be_h3_then_h5(
    desk: Desk, versions: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_PATH_REFUSALS["horizons"]
    argv = desk.argv(rules_version=versions)
    _refused(desk, argv, claims.EXIT_PATH_REFUSED, sentence, capsys)


def test_4_a_replacement_is_refused(desk: Desk, capsys: pytest.CaptureFixture[str]) -> None:
    sentence = claims.BOOTSTRAP_PATH_REFUSALS["replaces"]
    argv = desk.argv(replaces_claim_id=f"market|h3|{H3}|{DEFINITION}|forward")
    _refused(desk, argv, claims.EXIT_PATH_REFUSED, sentence, capsys)


# --- RC-180: a refused bootstrap makes no logical write -------------------------------------

#: Statements that would be a logical write (or change the journal mode) if run.
WRITE_STATEMENT: Final = re.compile(
    r"^\s*(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|VACUUM|REPLACE|PRAGMA\s+journal_mode)\b",
    re.IGNORECASE,
)


def _trace_store_connections(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every statement run on the store's connections (a trace callback; no app/ change)."""
    statements: list[str] = []
    real_open = store_module._open_connection

    def traced(path: Path) -> sqlite3.Connection:
        conn = real_open(path)
        conn.set_trace_callback(statements.append)
        statements.append("-- connection opened")
        return conn

    monkeypatch.setattr(store_module, "_open_connection", traced)
    return statements


@pytest.mark.parametrize("wal", [False, True], ids=["no_wal", "wal"])
@pytest.mark.parametrize(
    "ddl",
    ["CREATE TABLE forecast_extra (a)", "CREATE TABLE plan_items (a)"],
    ids=["forecast_object", "plan_object"],
)
def test_rc180_a_refused_bootstrap_makes_no_logical_write(
    desk: Desk,
    ddl: str,
    wal: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    holder: sqlite3.Connection | None = None
    if wal:
        # A -wal with uncheckpointed rows stays next to the file while ``holder`` is open.
        holder = sqlite3.connect(desk.db, isolation_level=None)
        holder.execute("PRAGMA journal_mode = WAL")
        holder.execute("PRAGMA wal_autocheckpoint = 0")
        holder.execute(ddl)
        holder.execute("INSERT INTO app_settings VALUES ('in_wal', 'yes')")
        assert wal_of(desk.db).stat().st_size > 0
    else:
        with closing(sqlite3.connect(desk.db)) as conn:
            conn.execute(ddl)
            conn.commit()
    try:
        before = logical_state(desk.db)
        digest = None if wal else hashlib.sha256(desk.db.read_bytes()).hexdigest()
        statements = _trace_store_connections(monkeypatch)
        assert desk.main(desk.argv()) == claims.EXIT_PATH_REFUSED
        out, err = capsys.readouterr()
        assert err.strip() == claims.BOOTSTRAP_PATH_REFUSALS["not_empty"] and out == ""
        assert logical_state(desk.db) == before
        assert before[1][0] == ("wal" if wal else "delete")
        assert before[1][1:3] == (7, 21316)
        assert any("in_wal" in line for line in before[0]) == wal  # the dump sees the -wal
        # The trace has teeth: one connection, one transaction, rolled back.
        assert statements.count("-- connection opened") == 1
        assert "BEGIN IMMEDIATE" in statements and statements[-1] == "ROLLBACK"
        assert "COMMIT" not in statements
        assert [s for s in statements if WRITE_STATEMENT.match(s)] == []
        if wal:
            assert wal_of(desk.db).exists()  # no hash claim: SQLite may checkpoint
        else:
            assert hashlib.sha256(desk.db.read_bytes()).hexdigest() == digest
            assert sorted(p.name for p in desk.data.iterdir()) == ["stock-desk.db"]
    finally:
        if holder is not None:
            holder.close()


def test_rc180_the_write_statement_pattern_has_teeth() -> None:
    for statement in (
        "CREATE TABLE x (a)",
        "  insert into t values (1)",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "ALTER TABLE t ADD b",
        "VACUUM",
        "REPLACE INTO t VALUES (1)",
        "PRAGMA journal_mode = WAL",
        "pragma JOURNAL_MODE",
    ):
        assert WRITE_STATEMENT.match(statement), statement
    for statement in ("BEGIN IMMEDIATE", "ROLLBACK", "SELECT 1", "PRAGMA busy_timeout = 5000"):
        assert not WRITE_STATEMENT.match(statement), statement


def test_rc180_an_exit_3_store_refusal_makes_no_logical_write(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # ForecastStoreError in the transaction (the store clock never gets later): the
    # objects and the h3 row were created inside it and rolled back; nothing committed.
    desk.clock = lambda: START  # type: ignore[assignment]
    before = logical_state(desk.db)
    digest = hashlib.sha256(desk.db.read_bytes()).hexdigest()
    statements = _trace_store_connections(monkeypatch)
    assert desk.main(desk.argv()) == claims.EXIT_REFUSED
    assert capsys.readouterr().err.strip() == claims.BOOTSTRAP_REFUSALS["store"]
    assert logical_state(desk.db) == before
    assert statements[-1] == "ROLLBACK" and "COMMIT" not in statements
    assert hashlib.sha256(desk.db.read_bytes()).hexdigest() == digest
    assert sorted(p.name for p in desk.data.iterdir()) == ["stock-desk.db"]


def test_rc180_an_exit_3_input_refusal_opens_no_connection(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = desk.state()
    statements = _trace_store_connections(monkeypatch)
    assert desk.main(desk.argv(provisional_results_seen="2")) == claims.EXIT_REFUSED
    capsys.readouterr()
    assert statements == []
    assert desk.state() == before


# --- exit 3 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("typed", ["2", "", " 0", "0 ", "01", "true", "yes", "-1", "0.0", "１"])
def test_3_a_typed_value_that_is_not_0_or_1_writes_nothing(
    desk: Desk, typed: str, capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_REFUSALS["provisional"]
    argv = desk.argv(provisional_results_seen=typed)
    _refused(desk, argv, claims.EXIT_REFUSED, sentence, capsys)


def test_2_the_typed_value_has_no_default(desk: Desk) -> None:
    before = desk.state()
    with pytest.raises(SystemExit) as exited:
        desk.main(desk.argv(provisional_results_seen=None))
    assert exited.value.code == 2
    assert desk.state() == before


@pytest.mark.parametrize("commit", ["abc123", "A" * 40, "g" * 40, "0" * 39, "0" * 41])
def test_3_the_frozen_commit_format(
    desk: Desk, commit: str, capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_REFUSALS["frozen_commit"]
    _refused(desk, desk.argv(frozen_commit=commit), claims.EXIT_REFUSED, sentence, capsys)


BAD_PATHS: Final = [
    "./work/x.md",
    "work/./x.md",
    "../work/x.md",
    "work/../x.md",
    "work\\x.md",
    "C:/work/x.md",
    "c:work/x.md",
    "/work/x.md",
    "work//x.md",
    "work/x.md/",
    " work/x.md",
    "",
]


@pytest.mark.parametrize("path", BAD_PATHS)
def test_3_the_prereg_path_format_is_checked_not_converted(
    desk: Desk, path: str, capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_REFUSALS["prereg_path"]
    _refused(desk, desk.argv(prereg_doc_path=path), claims.EXIT_REFUSED, sentence, capsys)


@pytest.mark.parametrize("refs", ["work/a.md  work/b.md", "work/a.md ./b.md", "C:/a.md", ""])
def test_3_the_review_refs_format(
    desk: Desk, refs: str, capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_REFUSALS["review_refs"]
    _refused(desk, desk.argv(review_refs=refs), claims.EXIT_REFUSED, sentence, capsys)


@pytest.mark.parametrize("digest", ["0" * 63, "G" * 64, PREREG_SHA256.upper()])
def test_3_the_prereg_sha256_format(
    desk: Desk, digest: str, capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_REFUSALS["prereg_sha256"]
    argv = desk.argv(prereg_doc_sha256=digest)
    _refused(desk, argv, claims.EXIT_REFUSED, sentence, capsys)


def test_3_the_prereg_blob_must_match_the_sha256(
    desk: Desk, capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_REFUSALS["prereg_mismatch"]
    argv = desk.argv(prereg_doc_sha256="0" * 64)
    _refused(desk, argv, claims.EXIT_REFUSED, sentence, capsys)


def test_3_the_working_tree_bytes_do_not_count(
    desk: Desk, capsys: pytest.CaptureFixture[str]
) -> None:
    edited = b"edited after the commit\n"
    (desk.root / PREREG_PATH).write_bytes(edited)
    sentence = claims.BOOTSTRAP_REFUSALS["prereg_mismatch"]
    argv = desk.argv(prereg_doc_sha256=hashlib.sha256(edited).hexdigest())
    _refused(desk, argv, claims.EXIT_REFUSED, sentence, capsys)


@pytest.mark.parametrize(
    "overrides",
    [{"prereg_doc_path": "work/research/absent.md"}, {"frozen_commit": "0" * 40}],
    ids=["path_not_in_the_commit", "commit_not_in_the_repo"],
)
def test_3_the_prereg_blob_must_exist_at_the_commit(
    desk: Desk, overrides: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_REFUSALS["prereg_blob"]
    _refused(desk, desk.argv(**overrides), claims.EXIT_REFUSED, sentence, capsys)


@pytest.mark.parametrize(
    "overrides",
    [
        {"definition_version": "dirdef-v9.9"},
        {"rules_version": [H3, "outlook-market-v9.9-h5"]},
    ],
    ids=["definition", "rule_set"],
)
def test_3_an_unpublished_version(
    desk: Desk, overrides: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = claims.BOOTSTRAP_REFUSALS["unpublished"]
    _refused(desk, desk.argv(**overrides), claims.EXIT_REFUSED, sentence, capsys)


def test_3_a_store_refusal_writes_nothing(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A store clock that never gets later: the second row times out in the transaction.
    desk.clock = lambda: START  # type: ignore[assignment]
    sentence = claims.BOOTSTRAP_REFUSALS["store"]
    _refused(desk, desk.argv(), claims.EXIT_REFUSED, sentence, capsys)


def test_3_a_banned_phrase_is_refused(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real = definitions.registration_phrase_scan

    def hit(ruleset: Any, definition: Any) -> Any:
        scan = real(ruleset, definition)
        return type(scan)(
            rules_strings=scan.rules_strings,
            definition_strings=scan.definition_strings,
            phrases=scan.phrases,
            hits=("rules: x",),
        )

    monkeypatch.setattr(definitions, "registration_phrase_scan", hit)
    before = desk.state()
    assert desk.main(desk.argv()) == claims.EXIT_REFUSED
    out, err = capsys.readouterr()
    assert err.strip() == claims.BOOTSTRAP_REFUSALS["phrases"]
    assert out == ""
    assert desk.state() == before


# --- unexpected exceptions are not caught ---------------------------------------------------


@pytest.mark.parametrize("error", [RuntimeError("boom"), sqlite3.OperationalError("locked")])
def test_unexpected_exceptions_propagate(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fail(self: ForecastStore, *, claims: Any) -> tuple[str, str]:
        raise error

    monkeypatch.setattr(ForecastStore, "bootstrap", fail)
    with pytest.raises(type(error)):
        desk.main(desk.argv())


# --- exit 5 ---------------------------------------------------------------------------------


INCOMPLETE: Final = SchemaStatus(missing=("table:forecast_run",), altered=(), unexpected=())


def _fail_check(name: str) -> Callable[..., Any]:
    """A stand-in for one post-commit query that makes its check fail."""
    real_seen = ForecastStore.provisional_results_seen

    def schema(self: ForecastStore) -> SchemaStatus:
        return INCOMPLETE

    def forward(self: ForecastStore) -> list[Any]:
        return []

    def runs(self: ForecastStore) -> list[RunRow]:
        return [object()]  # type: ignore[list-item]

    def flipped(self: ForecastStore) -> list[tuple[str, int]]:
        return [(c, 1 - v) for c, v in real_seen(self)]

    def inconsistent(self: ForecastStore) -> list[tuple[str, int]]:
        raise LedgerInconsistentError("x")

    return {
        "ledger_schema_status": schema,
        "forward_claims": forward,
        "runs": runs,
        "provisional_results_seen": flipped,
        "inconsistent": inconsistent,
    }[name]


@pytest.mark.parametrize(
    "check",
    ["ledger_schema_status", "forward_claims", "runs", "provisional_results_seen", "inconsistent"],
)
def test_5_a_failed_post_commit_check_stops_without_retry(
    desk: Desk, check: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[int] = []
    real_bootstrap = ForecastStore.bootstrap

    def counted(self: ForecastStore, *, claims: Any) -> tuple[str, str]:
        calls.append(1)
        return real_bootstrap(self, claims=claims)

    monkeypatch.setattr(ForecastStore, "bootstrap", counted)
    name = "provisional_results_seen" if check == "inconsistent" else check
    monkeypatch.setattr(ForecastStore, name, _fail_check(check))
    assert desk.main(desk.argv()) == claims.EXIT_POST_COMMIT_CHECK_FAILED
    out, err = capsys.readouterr()
    assert err.strip() == claims.POST_COMMIT_CHECK_FAILED
    assert out == ""
    assert calls == [1]  # no retry
    assert len(desk.registry()) == 2  # committed before the check


def test_5_the_schema_is_checked_before_the_typed_value_is_read(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(self: ForecastStore) -> list[tuple[str, int]]:
        raise AssertionError("provisional_results_seen read before the schema check")

    monkeypatch.setattr(ForecastStore, "ledger_schema_status", _fail_check("ledger_schema_status"))
    monkeypatch.setattr(ForecastStore, "provisional_results_seen", never)
    assert desk.main(desk.argv()) == claims.EXIT_POST_COMMIT_CHECK_FAILED


def test_the_post_commit_check_reads_only(desk: Desk, monkeypatch: pytest.MonkeyPatch) -> None:
    real_write = ForecastStore._write
    writes: list[bool] = []

    def spy(self: ForecastStore, *, fresh: bool = False) -> Any:
        writes.append(fresh)
        return real_write(self, fresh=fresh)

    monkeypatch.setattr(ForecastStore, "_write", spy)
    assert desk.main(desk.argv()) == claims.EXIT_OK
    assert writes == [True]  # the one bootstrap transaction, nothing after it


# --- supplement 7 addendum 2 point 4: exceptions after the commit ---------------------------


def _raise_in_check(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def fail(self: ForecastStore) -> list[RunRow]:
        raise error

    monkeypatch.setattr(ForecastStore, "runs", fail)  # the third post-commit check


def _raise_in_output(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def fail(value: datetime) -> str:
        raise error

    monkeypatch.setattr(claims, "canonical_timestamp", fail)  # used only by the output


@pytest.mark.parametrize("where", [_raise_in_check, _raise_in_output], ids=["check", "output"])
@pytest.mark.parametrize(
    "error",
    [sqlite3.OperationalError("disk I/O error at /secret/path"), RuntimeError("boom")],
    ids=["OperationalError", "RuntimeError"],
)
def test_5_an_exception_after_the_commit_is_the_fixed_sentence(
    desk: Desk,
    where: Callable[[pytest.MonkeyPatch, Exception], None],
    error: Exception,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[int] = []
    real_bootstrap = ForecastStore.bootstrap

    def counted(self: ForecastStore, *, claims: Any) -> tuple[str, str]:
        calls.append(1)
        return real_bootstrap(self, claims=claims)

    monkeypatch.setattr(ForecastStore, "bootstrap", counted)
    where(monkeypatch, error)
    assert desk.main(desk.argv()) == claims.EXIT_POST_COMMIT_CHECK_FAILED
    out, err = capsys.readouterr()
    assert err == claims.POST_COMMIT_CHECK_FAILED + "\n"
    assert out == ""
    assert calls == [1]
    assert len(desk.registry()) == 2


def test_a_base_exception_after_the_commit_is_not_caught(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(self: ForecastStore) -> list[RunRow]:
        raise KeyboardInterrupt

    monkeypatch.setattr(ForecastStore, "runs", interrupted)
    with pytest.raises(KeyboardInterrupt):
        desk.main(desk.argv())


# --- supplement 7 addendum 2 point 7: git_blob's environment --------------------------------


def test_git_blob_ignores_git_variables_that_point_elsewhere(
    desk: Desk, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path_factory.mktemp("other-repo")
    (other / "work" / "research").mkdir(parents=True)
    (other / PREREG_PATH).write_bytes(b"another repository\n")
    _git(other, "init", "-q")
    _git(other, "add", PREREG_PATH)
    _git(other, "commit", "-q", "-m", "other")
    other_commit = _git(other, "rev-parse", "HEAD")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    assert claims.git_blob(desk.backend, desk.commit, PREREG_PATH) == PREREG
    assert claims.git_blob(desk.backend, other_commit, PREREG_PATH) is None
    assert desk.main(desk.argv()) == claims.EXIT_OK


def test_git_blob_ignores_replace_refs(desk: Desk) -> None:
    original = _git(desk.root, "rev-parse", f"HEAD:{PREREG_PATH}")
    swapped = desk.root / "swap.txt"
    swapped.write_bytes(b"replacement bytes\n")
    replacement = _git(desk.root, "hash-object", "-w", str(swapped))
    _git(desk.root, "replace", original, replacement)
    assert _git(desk.root, "cat-file", "blob", f"HEAD:{PREREG_PATH}") == "replacement bytes"
    assert claims.git_blob(desk.backend, desk.commit, PREREG_PATH) == PREREG


# --- supplement 7 addendum 2 point 6: the module docstring ----------------------------------


def test_the_module_docstring_names_bootstrap_and_every_exit_code() -> None:
    doc = ast.get_docstring(ast.parse((APP_ROOT / "forecast" / "claims.py").read_text("utf-8")))
    assert doc is not None
    assert "bootstrap --production" in " ".join(doc.split())
    for code in ("0 done", "2 usage", "3 refused", "4 path refused", "5 ``bootstrap``"):
        assert code in " ".join(doc.split()), code
    assert re.search(r"[0-9a-f]{40}", doc) is None
    assert "market|h" not in doc and "dirdef-v1" not in doc
    for word in ("already registered", "not registered", "is registered", "unregistered"):
        assert word not in doc.lower(), word


# --- the stand-in paths and the AST boundaries ----------------------------------------------


def test_no_test_here_names_the_real_backend() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    mains = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "main"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "claims"
    ]
    assert mains and all(any(k.arg == "backend_dir" for k in m.keywords) for m in mains)
    assert "BACKEND_DIR" not in source.replace('"BACKEND_DIR"', "")


#: The top-level definitions of the bootstrap branch (CG-2 PR).
BOOTSTRAP_FUNCTIONS: Final = {
    "_add_bootstrap_parser",
    "repo_relative_path_ok",
    "env_file_sets_db_path",
    "production_target",
    "git_blob",
    "bootstrap_claim_inputs",
    "post_commit_check",
    "bootstrap_main",
    "bootstrap_output",
}
#: What the branch may call on the store: ``bootstrap`` and read-only queries.
STORE_CALLS: Final = {
    "bootstrap",
    "ledger_schema_status",
    "forward_claims",
    "runs",
    "provisional_results_seen",
}


def _claims_functions() -> dict[str, ast.FunctionDef]:
    tree = ast.parse((APP_ROOT / "forecast" / "claims.py").read_text(encoding="utf-8"))
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _called(node: ast.AST) -> set[str]:
    return {
        call.func.attr if isinstance(call.func, ast.Attribute) else call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute | ast.Name)
    }


def test_claims_calls_bootstrap_from_its_bootstrap_branch_only() -> None:
    functions = _claims_functions()
    assert BOOTSTRAP_FUNCTIONS <= set(functions)
    callers = {name for name, fn in functions.items() if "bootstrap" in _called(fn)}
    assert callers == {"bootstrap_main"}


def test_the_bootstrap_branch_calls_no_other_write_path() -> None:
    functions = _claims_functions()
    forbidden = {
        "register_claim",
        "register",
        "_write",
        "_connect",
        "create_objects",
        "create_schema",
        "execute",
        "executemany",
        "executescript",
        "connect",
        "begin_run",
        "end_run",
        "write_run_records",
        "put_input_series",
        "write_record",
    }
    found = {name: _called(functions[name]) & forbidden for name in BOOTSTRAP_FUNCTIONS}
    assert {name: calls for name, calls in found.items() if calls} == {}


def test_the_bootstrap_branch_calls_only_bootstrap_and_read_queries_on_the_store() -> None:
    functions = _claims_functions()
    store_methods = {
        name
        for name, value in vars(ForecastStore).items()
        if callable(value) and not name.startswith("__")
    }
    used = {
        name
        for fn in BOOTSTRAP_FUNCTIONS
        for name in _called(functions[fn])
        if name in store_methods
    }
    assert used == STORE_CALLS


def test_the_post_commit_check_reads_the_schema_first() -> None:
    fn = _claims_functions()["post_commit_check"]
    attributes = sorted(
        (
            (n.lineno, n.col_offset, n.func.attr)
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        ),
    )
    order = [attr for _, _, attr in attributes if attr in STORE_CALLS]
    assert order == ["ledger_schema_status", "forward_claims", "runs", "provisional_results_seen"]


def test_the_typed_value_has_no_default_and_no_other_source() -> None:
    fn = _claims_functions()["_add_bootstrap_parser"]
    (argument,) = [
        call
        for call in ast.walk(fn)
        if isinstance(call, ast.Call)
        and any(
            isinstance(a, ast.Constant) and a.value == "--provisional-results-seen"
            for a in call.args
        )
    ]
    keywords = {k.arg: ast.unparse(k.value) for k in argument.keywords}
    assert keywords.get("required") == "True"
    assert "default" not in keywords and "choices" not in keywords
    # production_target / env_file_sets_db_path read the key only; git_blob passes the
    # process environment, minus every GIT_* variable, to git.
    exempt = {"env_file_sets_db_path", "production_target", "git_blob"}
    for name in BOOTSTRAP_FUNCTIONS - exempt:
        text = ast.unparse(_claims_functions()[name])
        assert "environ" not in text and "getenv" not in text and "open(" not in text, name
    git_blob = ast.unparse(_claims_functions()["git_blob"])
    assert "getenv" not in git_blob and "open(" not in git_blob
    assert "if not k.upper().startswith('GIT_')" in git_blob
