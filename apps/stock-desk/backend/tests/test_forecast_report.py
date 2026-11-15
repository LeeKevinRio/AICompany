"""``python -m app.forecast.report`` (ADR-0030 D-1 point 3; D-4 points 3, 5; D-5 points 3, 5; D-8).

Every ledger is a ``tmp_path`` file filled by the real recorder over synthetic
bars (consecutive weekdays, 20:00 Taipei stamps) with the landed h3 / h5 rule
files and the G7 stand-in definition, registered for each test only (K-11).
The report's clock is injected.

Covered, each output rule with a positive and a negative case (S-10):

* a model label is listed only with the four baselines on the same line, in
  one format (D-4 point 3);
* a record whose ``valid_until_session_estimate`` has not passed is listed
  without any label (D-4 point 3);
* no hit rate, match count or proportion, run count, interval, n (n-hat only
  with its fixed note) and no "better / worse / accurate / effective" wording
  (D-4 point 5);
* ``compare`` opens and closes with the D-5 point 5 banner and lists records
  by T only;
* ``verify`` reports consistent records and catches tampered copies (label,
  ``band_def``, ``content_hash``, snapshot bytes, registry bytes) with exit 1,
  without printing a label;
* the report only reads: the ledger file is unchanged, no write connection is
  opened, every connection it opens is ``query_only``, and the module calls no
  store write (AST); a missing path is refused before anything is opened.
"""

from __future__ import annotations

import ast
import hashlib
import math
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from app.data.interface import PriceBar
from app.dirdef.registry import PublishedRuleset
from app.dirdef.rules import rules_logic_sha256
from app.forecast import definitions, report, scoring
from app.forecast import store as store_module
from app.forecast.canonical import APP_ROOT
from app.forecast.recorder import record_forecasts
from app.forecast.schema import EXPECTED_OBJECTS
from app.forecast.store import ForecastStore
from app.services.index import IndexServiceResolver, load_market_benchmark
from tests.forecast_ledger_helpers import FakeClock, file_ledger, publish_definition
from tests.import_graph import offenders, reachable_app_modules
from tests.outlook_helpers import (
    TAIPEI,
    FakeIndexService,
    definition,
    price_bar,
    rule_bytes,
    ruleset,
)

H3 = "outlook-market-v1.0-h3"
H5 = "outlook-market-v1.0-h5"
LAST = date(2026, 11, 13)  # a Friday: the last synthetic session
RUNS = 8
#: The report's clock: Tuesday after LAST, 09:00. h3 records up to 11-11 have passed.
NOW = datetime(2026, 11, 17, 9, tzinfo=TAIPEI)

LABEL_WORDS = ("bullish", "bearish", "range", "偏多", "偏空", "震盪")
#: D-4 point 5 wording and aggregates (checked after the fixed texts are removed).
BANNED_WORDS = (
    "命中率",
    "符合筆數",
    "比例",
    "連續",
    "區間",
    "優於",
    "不如",
    "準確",
    "有效",
    "勝率",
    "機率",
    "%",
    "hit rate",
    "accuracy",
    "better",
    "worse",
)
#: The D-8 point 4 note, as ADR-0030 writes it (not read from the module under test).
N_HAT_NOTE = "重審觸發用計數（近似上界估計），不是驗證統計，不代表規則有效"
FIXED_TEXTS = (scoring.PROVISIONAL_BANNER, N_HAT_NOTE)


def _sessions_ending(last: date, count: int) -> list[date]:
    days: list[date] = []
    day = last
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return list(reversed(days))


def _series(count: int = 330) -> list[PriceBar]:
    days = _sessions_ending(LAST, count)
    closes = [10000.0]
    for j in range(1, count):
        step = 0.008 * math.sin(0.7 * j) + 0.003 * (((j * 7919) % 13) - 6) / 6
        closes.append(closes[-1] * math.exp(step))
    return [
        price_bar(day, Decimal(close), datetime.combine(day, time(20), TAIPEI))
        for day, close in zip(days, closes, strict=True)
    ]


def _publish(monkeypatch: pytest.MonkeyPatch) -> None:
    publish_definition(monkeypatch, definition())
    entries = {
        H3: PublishedRuleset(horizon=3, rules_sha256=hashlib.sha256(rule_bytes(3)).hexdigest()),
        H5: PublishedRuleset(horizon=5, rules_sha256=hashlib.sha256(rule_bytes(5)).hexdigest()),
    }
    monkeypatch.setattr(definitions, "PUBLISHED_RULESETS", MappingProxyType(entries))
    monkeypatch.setattr(definitions, "_RULESET_CACHE", {})


class Ledger:
    """A ``tmp_path`` ledger: two claims, :data:`RUNS` recorder runs on the last sessions."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.path = file_ledger(root)
        self.clock = FakeClock(datetime(2026, 10, 1, 9, tzinfo=TAIPEI))
        self.store = ForecastStore(self.path, clock=self.clock)
        _publish(monkeypatch)
        self.claims = [self._register(3), self._register(5)]
        bars = _series()
        service = FakeIndexService(bars)
        resolver: IndexServiceResolver = {"TW": service}
        self.sessions = [b.date for b in bars][-RUNS:]
        for day in self.sessions:
            self.clock.now = datetime.combine(day, time(22, 10), TAIPEI)
            result = record_forecasts(
                self.store, load_benchmark=load_market_benchmark, resolver=resolver
            )
            assert result.outcome == "ok"

    def _register(self, horizon: int) -> str:
        self.clock.advance(seconds=1)
        return self.store.register_claim(
            horizon=3 if horizon == 3 else 5,
            rules_version=H3 if horizon == 3 else H5,
            rules_bytes=rule_bytes(horizon),
            rules_logic_sha256=rules_logic_sha256(ruleset(horizon)),
            definition=definition(),
            frozen_commit="abc123",
            prereg_doc_path="docs/prereg-v0.32.md",
            prereg_doc_blob=b"prereg",
            review_refs="work/reviews/x.md",
            replaces_claim_id=None,
            replace_reason=None,
            provisional_results_seen=False,
        )

    def rows(self) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM forecast_record ORDER BY rowid")]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """One ledger file per module (the recorder runs are the slow part); tests copy it."""
    with pytest.MonkeyPatch.context() as patch:
        root = tmp_path_factory.mktemp("report")
        yield Ledger(root, patch).path


@pytest.fixture
def ledger(built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    copy = tmp_path / "ledger.db"
    shutil.copy2(built, copy)
    _publish(monkeypatch)
    return copy


def _run(path: Path, *args: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    code = report.main([args[0], "--db", str(path), *args[1:]], clock=lambda: NOW)
    return code, capsys.readouterr().out.splitlines()


def _records(path: Path) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM forecast_record ORDER BY rowid")]


def _unpassed_hashes(path: Path, today: date) -> set[str]:
    return {
        str(r["content_hash"])
        for r in _records(path)
        if not report.has_passed(r["valid_until_session_estimate"], today)
    }


# --- the D-4 checker and its teeth -------------------------------------------------------------


def d4_violations(lines: Sequence[str], *, unpassed_hashes: set[str]) -> list[str]:
    """Every D-4 point 3 / 5 rule over an output (the fixed texts removed first)."""
    found: list[str] = []
    for line in lines:
        if "\x1b[" in line or "**" in line or "<b>" in line:
            found.append(f"emphasis: {line}")
        if "模型=" in line and not all(f"{key}=" in line for key in scoring.BASELINES):
            found.append(f"model label without the four baselines: {line}")
        positions = [line.index(f"{key}=") for key in scoring.BASELINES if f"{key}=" in line]
        if "模型=" in line and positions and line.index("模型=") < max(positions):
            found.append(f"model label set apart by position: {line}")
        if any(digest in line for digest in unpassed_hashes):
            if any(word in line for word in LABEL_WORDS) or "B1=" in line or "模型=" in line:
                found.append(f"label of an unpassed record: {line}")
        if "n̂" in line and N_HAT_NOTE not in line:
            found.append(f"n-hat without its note: {line}")
        text = line
        for fixed in FIXED_TEXTS:
            text = text.replace(fixed, "")
        text = text.replace("n̂", "")
        found += [f"banned {word!r}: {line}" for word in BANNED_WORDS if word in text]
        if re.search(r"(?<![A-Za-z_])n(?![A-Za-z_])", text):
            found.append(f"n: {line}")
    return found


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("  T=2026-11-02 模型=bullish", id="model-alone"),
        pytest.param(
            "  T=2026-11-02 B1=range B6=range B8=range 模型=bullish", id="three-baselines"
        ),
        pytest.param("  模型=bullish B1=range B2=range B6=range B8=range", id="model-first"),
        pytest.param("  T=2026-11-02 \x1b[1mB1=range B2=range B6=range B8=range 模型=x", id="bold"),
        pytest.param("  T=HASH late=0 B1=range B2=range B6=range B8=range 模型=x", id="unpassed"),
        pytest.param("  T=HASH late=0 證據不足=否 震盪", id="unpassed-word"),
        pytest.param("符合筆數：3", id="match-count"),
        pytest.param("命中率 40", id="hit-rate"),
        pytest.param("模型優於基準", id="better"),
        pytest.param("規則有效", id="effective"),
        pytest.param("比例 0.4", id="proportion"),
        pytest.param("連續 3 筆", id="streak"),
        pytest.param("信賴區間", id="interval"),
        pytest.param("n=12", id="n"),
        pytest.param("n̂=3", id="n-hat-without-note"),
        pytest.param("40%", id="percent"),
    ],
)
def test_the_d4_checker_has_teeth(line: str) -> None:
    assert d4_violations([line], unpassed_hashes={"HASH"}) != []


def test_the_d4_checker_lets_the_fixed_texts_and_n_hat_through() -> None:
    lines = [
        scoring.PROVISIONAL_BANNER,
        f"n̂=3（{N_HAT_NOTE}）",
        "  T=2026-11-02 late=0 B1=range B2=unavailable:b2_realized_short B6=range B8=x 模型=y",
    ]
    assert d4_violations(lines, unpassed_hashes=set()) == []


# --- records ----------------------------------------------------------------------------------


def test_records_list_labels_only_for_passed_records_with_the_four_baselines(
    ledger: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = _run(ledger, "records", capsys=capsys)
    assert code == report.EXIT_OK
    today = report.taipei_date(NOW)
    rows = _records(ledger)
    unpassed = _unpassed_hashes(ledger, today)
    assert 0 < len(unpassed) < len(rows)  # both kinds are present
    assert d4_violations(lines, unpassed_hashes=unpassed) == []
    for row in rows:
        (line,) = [line for line in lines if str(row["content_hash"]) in line]
        assert f"T={row['data_as_of']} late={row['late']}" in line
        assert "執行結果=ok" in line
        if str(row["content_hash"]) in unpassed:
            assert "B1=" not in line and "模型=" not in line
        else:
            assert line.endswith(report.label_cells(row))
            assert f"模型={row['label']}" in line


def test_records_would_show_labels_if_every_record_had_passed(
    ledger: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Negative case for the "not passed" rule: the checker catches the leak.
    today = report.taipei_date(NOW)
    unpassed = _unpassed_hashes(ledger, today)
    monkeypatch.setattr(report, "has_passed", lambda value, day: True)
    _, lines = _run(ledger, "records", capsys=capsys)
    assert any(
        "label of an unpassed record" in v for v in d4_violations(lines, unpassed_hashes=unpassed)
    )


def test_records_are_in_registration_and_t_order(
    ledger: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, lines = _run(ledger, "records", capsys=capsys)
    dates = [re.search(r"T=(\S+)", line).group(1) for line in lines if line.startswith("  T=")]  # type: ignore[union-attr]
    assert dates == sorted(dates[:RUNS]) + sorted(dates[RUNS:])
    claims = [line for line in lines if line.startswith("claim ")]
    assert [c.split("|")[1] for c in claims] == ["h3", "h5"]


def test_has_passed_is_strictly_after_the_estimate() -> None:
    assert report.has_passed("2026-11-16", date(2026, 11, 17))
    assert not report.has_passed("2026-11-17", date(2026, 11, 17))


# --- compare ----------------------------------------------------------------------------------


def test_compare_opens_and_closes_with_the_banner_and_lists_passed_records_only(
    ledger: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = _run(ledger, "compare", capsys=capsys)
    assert code == report.EXIT_OK
    assert lines[0] == lines[-1] == scoring.PROVISIONAL_BANNER
    assert lines.count(scoring.PROVISIONAL_BANNER) == 2
    today = report.taipei_date(NOW)
    unpassed = _unpassed_hashes(ledger, today)
    assert d4_violations(lines, unpassed_hashes=unpassed) == []
    rows = [line for line in lines if line.startswith("  T=")]
    passed = [r for r in _records(ledger) if str(r["content_hash"]) not in unpassed]
    assert len(rows) == len(passed) > 0
    for line in rows:
        assert "實現=" in line or "無法對照：" in line
    # Records the later snapshots cover are compared, the rest say why not.
    assert any("實現=" in line for line in rows)
    assert any("無法對照：sessions_after_t_short" in line for line in rows)


def test_compare_rows_hold_every_party_in_one_format(
    ledger: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, lines = _run(ledger, "compare", capsys=capsys)
    for line in [line for line in lines if "實現=" in line]:
        cells = re.findall(r"(B1|B2|B6|B8|模型)=(\S+?)（(符合|不符合|不適用)）", line)
        assert [cell[0] for cell in cells] == ["B1", "B2", "B6", "B8", "模型"]


def test_compare_order_does_not_follow_the_results(
    ledger: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, lines = _run(ledger, "compare", capsys=capsys)
    dates = [re.search(r"T=(\S+) h=3", line) for line in lines]
    h3 = [m.group(1) for m in dates if m]
    assert h3 == sorted(h3)


# --- verify -----------------------------------------------------------------------------------


def test_verify_all_is_consistent_and_prints_no_label(
    ledger: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = _run(ledger, "verify", "--all", capsys=capsys)
    assert code == report.EXIT_OK
    assert lines[-1] == "verify：全部一致"
    rows = [line for line in lines if line.startswith("  ")]
    assert len(rows) == 2 * RUNS
    assert all("：一致；" in line and line.endswith("：相同") for line in rows)
    assert not any(word in line for line in lines for word in LABEL_WORDS)
    assert d4_violations(lines, unpassed_hashes=set()) == []


def test_verify_one_claim(ledger: Path, capsys: pytest.CaptureFixture[str]) -> None:
    claim = "market|h5|outlook-market-v1.0-h5|dirdef-v1.0|forward"
    code, lines = _run(ledger, "verify", "--claim-id", claim, capsys=capsys)
    assert code == report.EXIT_OK
    assert sum(1 for line in lines if line.startswith(f"  {claim} ")) == RUNS
    code, _ = _run(ledger, "verify", "--claim-id", "nope", capsys=capsys)
    assert code == report.EXIT_UNREADABLE


def _tamper(path: Path, table: str, sql: str, params: tuple[object, ...] = ()) -> None:
    """A test double that bypasses the append-only trigger: drop, change, put the trigger back."""
    trigger = f"{table}_no_update"
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        conn.execute(f"DROP TRIGGER {trigger}")
        conn.execute(sql, params)
        conn.execute(EXPECTED_OBJECTS[("trigger", trigger)])


@pytest.mark.parametrize(
    ("case", "problem"),
    [
        ("label", "differs"),
        ("band_def", "differs"),
        ("content_hash", "differs"),
        ("baselines", "differs"),
        ("missing", "differs"),
        ("snapshot", "snapshot_hash_differs"),
        ("registry-rules", "registered_material_rejected"),
        ("registry-definition", "registered_material_rejected"),
    ],
)
def test_verify_catches_a_tampered_copy(
    ledger: Path, capsys: pytest.CaptureFixture[str], case: str, problem: str
) -> None:
    first = _records(ledger)[0]
    where = (first["forecast_id"],)
    if case == "label":
        other = "bearish" if first["label"] != "bearish" else "bullish"
        _tamper(
            ledger,
            "forecast_record",
            "UPDATE forecast_record SET label = ? WHERE forecast_id = ?",
            (other, *where),
        )
    elif case == "band_def":
        band = str(first["band_def"]).replace('"EPS":', '"EPS": ', 1)
        _tamper(
            ledger,
            "forecast_record",
            "UPDATE forecast_record SET band_def = ? WHERE forecast_id = ?",
            (band, *where),
        )
    elif case == "content_hash":
        _tamper(
            ledger,
            "forecast_record",
            "UPDATE forecast_record SET content_hash = ? WHERE forecast_id = ?",
            ("0" * 64, *where),
        )
    elif case == "baselines":
        text = str(first["baseline_predictions_json"]).replace(
            '"B6":{"label":"range"}', '"B6":{"label":"bullish"}'
        )
        assert text != first["baseline_predictions_json"]
        _tamper(
            ledger,
            "forecast_record",
            "UPDATE forecast_record SET baseline_predictions_json = ? WHERE forecast_id = ?",
            (text, *where),
        )
    elif case == "missing":
        _tamper(
            ledger,
            "forecast_record",
            "UPDATE forecast_record SET missing_json = ? WHERE forecast_id = ?",
            ("[]  ", *where),
        )
    elif case == "snapshot":
        # One bar's volume changes: no label moves, only the snapshot bytes.
        _tamper(
            ledger,
            "forecast_input_series",
            "UPDATE forecast_input_series SET bars_json = replace(bars_json, ?, ?)"
            " WHERE content_sha256 = ?",
            ('"volume":0', '"volume":1', first["input_series_sha256"]),
        )
    elif case == "registry-rules":
        _tamper(
            ledger,
            "forecast_claim_registry",
            "UPDATE forecast_claim_registry SET rules_bytes = ? WHERE claim_id = ?",
            (rule_bytes(3) + b"# x\n", first["claim_id"]),
        )
    else:
        # A text-only field of the definition: definition_sha256 no longer holds.
        _tamper(
            ledger,
            "forecast_claim_registry",
            "UPDATE forecast_claim_registry SET definition_json = replace(definition_json, ?, ?)"
            " WHERE claim_id = ?",
            ('"description":"', '"description":"x', first["claim_id"]),
        )
    assert ForecastStore(ledger).ledger_schema_status().complete
    code, lines = _run(ledger, "verify", "--all", capsys=capsys)
    assert code == report.EXIT_INCONSISTENT
    assert lines[-1] == "verify：有不一致（F-3：停止記錄並查明）"
    bad = [line for line in lines if "不一致（" in line and line.startswith("  ")]
    assert bad and all(f"不一致（{problem}）" in line for line in bad)
    assert any(f"T={first['data_as_of']}" in line for line in bad)
    assert not any(word in line for line in lines for word in LABEL_WORDS)


def test_verify_reports_a_different_program_as_the_premise(
    ledger: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.forecast import recorder

    other = recorder.Provenance(
        code_commit="x", code_digest="9" * 64, runtime=recorder.LOADED.runtime
    )
    monkeypatch.setattr(recorder, "LOADED", other)
    code, lines = _run(ledger, "verify", "--all", capsys=capsys)
    assert code == report.EXIT_OK  # the same bytes under another program
    assert all(line.endswith("：不同") for line in lines if line.startswith("  "))


# --- status -----------------------------------------------------------------------------------


def test_status_is_execution_status_only(ledger: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, lines = _run(ledger, "status", capsys=capsys)
    assert code == report.EXIT_OK
    text = "\n".join(lines)
    assert (
        f"ok={RUNS}，no_new_session=0，inputs_not_ready=0，gate_closed=0，error=0，沒有 end 列=0"
        in text
    )
    assert "inputs_not_ready 日數（全部期間，台北日期）：0" in text
    assert text.count("n̂=") == 2 and text.count(N_HAT_NOTE) == 2
    for line in lines:
        if "n̂=" in line:
            assert f"（{N_HAT_NOTE}）" in line
    assert "T1=未成立" in text and "c₁=30" in text
    assert not any(word in text for word in LABEL_WORDS)
    assert d4_violations(lines, unpassed_hashes=set()) == []


def test_status_n_hat_without_its_note_is_caught(
    ledger: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Negative case for the n-hat exception: without its fixed note the checker objects.
    monkeypatch.setattr(report, "N_HAT_NOTE", "近似計數")
    _, lines = _run(ledger, "status", capsys=capsys)
    found = d4_violations(lines, unpassed_hashes=set())
    assert [v for v in found if v.startswith("n-hat without its note")] != []


def test_status_counts_the_f2_window(ledger: Path, capsys: pytest.CaptureFixture[str]) -> None:
    window = report.f2_window(report.taipei_date(NOW))
    assert len(window) == report.F2_WEEKDAYS and window[-1] == date(2026, 11, 16)
    assert all(day.weekday() < 5 for day in window)
    _, lines = _run(ledger, "status", capsys=capsys)
    # The latest snapshot ends on LAST; every recorded session has a late = 0 record,
    # the window sessions before the first run do not (registered 2026-10-01).
    missed = [line for line in lines if "沒有 late = 0 紀錄的定案 session 數" in line]
    expected = sum(
        1 for day in window if day <= LAST and day not in set(_sessions_ending(LAST, RUNS))
    )
    assert [int(line.rsplit("：", 1)[1]) for line in missed] == [expected, expected]


# --- read-only ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args", [["status"], ["records"], ["compare"], ["verify", "--all"]], ids=lambda a: a[0]
)
def test_the_report_only_reads(
    ledger: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> None:
    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    files = sorted(p.name for p in ledger.parent.iterdir())

    def no_write(self: ForecastStore) -> Any:
        raise AssertionError("the report opened a write connection")

    monkeypatch.setattr(ForecastStore, "_connect", no_write)
    flags: list[int] = []
    real_closing = closing

    @contextmanager
    def spying(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        with real_closing(conn):
            try:
                yield conn
            finally:
                flags.append(conn.execute("PRAGMA query_only").fetchone()[0])
                with pytest.raises(sqlite3.OperationalError, match="readonly"):
                    conn.execute("DELETE FROM forecast_run_end")

    monkeypatch.setattr(store_module, "closing", spying)
    code, _ = _run(ledger, *args, capsys=capsys)
    assert code == report.EXIT_OK
    assert flags and set(flags) == {1}
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in ledger.parent.iterdir()) == files


def test_the_report_module_calls_no_store_write_and_opens_no_connection() -> None:
    tree = ast.parse((APP_ROOT / "forecast" / "report.py").read_text(encoding="utf-8"))
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    writes = {
        "begin_run",
        "end_run",
        "put_input_series",
        "write_run_records",
        "write_record",
        "register_claim",
        "_write",
        "_connect",
        "_read",
        "connect",
        "execute",
        "executemany",
        "executescript",
        "create_schema",
    }
    assert attributes & writes == set()
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "record_forecasts" not in names and "create_schema" not in names
    sql = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|SELECT)\b\s", node.value)
    ]
    assert sql == []


def test_a_missing_path_is_refused_and_not_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "absent.db"
    assert (
        report.main(["status", "--db", str(missing)], clock=lambda: NOW) == report.EXIT_PATH_REFUSED
    )
    assert not missing.exists()
    assert "refused: --db is not an existing ledger file" in capsys.readouterr().err


@pytest.mark.parametrize("content", [b"", b"not a database at all, just bytes" * 64])
def test_a_ledger_without_the_schema_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes
) -> None:
    path = tmp_path / "other.db"
    path.write_bytes(content)
    assert report.main(["records", "--db", str(path)], clock=lambda: NOW) == report.EXIT_UNREADABLE
    assert path.read_bytes() == content
    assert capsys.readouterr().err.startswith("refused: ")


def test_the_module_runs_as_main(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "app.forecast.report", "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(APP_ROOT.parent)},
    )
    assert done.returncode == 0, done.stderr
    assert "verify" in done.stdout


# --- boundaries ---------------------------------------------------------------------------------


@pytest.mark.parametrize("package", ["app.api", "app.services", "app.main", "app.scheduler"])
def test_the_report_reaches_none_of_the_forbidden_packages(package: str) -> None:
    assert offenders(reachable_app_modules(("app.forecast.report",)), package) == []


def test_the_fixed_texts_are_the_adr_wording() -> None:
    assert report.N_HAT_NOTE == N_HAT_NOTE
    assert scoring.PROVISIONAL_BANNER == (
        "暫定對照：非正式結算，結果可能與日後正式結算不同；只對照發布當下可算的四個基準；"
        "不計入任何驗證統計，單筆符合與否不代表規則有效；規則未經驗證。"
    )


def test_the_report_is_not_reachable_from_the_recorder_or_the_store() -> None:
    for module in ("app.forecast.recorder", "app.forecast.store", "app.forecast.schema"):
        assert offenders(reachable_app_modules((module,)), "app.forecast.report") == []
    assert "app.forecast.scoring" in reachable_app_modules(("app.forecast.report",))
