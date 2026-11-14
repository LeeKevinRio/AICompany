"""The ledger store (ADR-0030 D-2, D-3, D-8, D-9).

Append-only writes, write validation and the read-only queries.

Every database is a ``tmp_path`` file; the clock is injected (``FakeClock``).
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.dirdef.definition import DirectionDefinition, definition_logic_sha256, definition_sha256
from app.forecast import store as store_module
from app.forecast.canonical import canonical_timestamp, content_sha256, record_content_hash
from app.forecast.definitions import UnpublishedVersionError
from app.forecast.errors import LabeledThresholdSnapshotIncompleteError
from app.forecast.schema import SchemaIncompleteError
from app.forecast.store import (
    ForecastStore,
    ForecastStoreError,
    LedgerInconsistentError,
    late_cutoff_at,
    new_ulid,
    valid_until_session_estimate,
)
from app.outlook.missing import MissingItem
from tests.forecast_ledger_helpers import (
    BASELINES,
    FakeClock,
    band,
    bar,
    file_ledger,
    fixture_definition,
    publish_definition,
    taipei,
    weekdays,
)

T = date(2026, 11, 13)  # a Friday
DAYS = weekdays(date(2026, 10, 1), 30)
RULES_H3 = b"version: 1.0.0\nrules: []\n"
RULES_H5 = b"version: 1.0.0\nrules: [h5]\n"
LOGIC = "1" * 64
CODE = "2" * 64


def _missing(day: date) -> MissingItem:
    return MissingItem(
        code="E-BARS-SHORT",
        item="index_bars",
        required="315",
        available="12",
        source=None,
        source_status=None,
        attempted_at=None,
        latest_available=None,
        as_of=day,
        detail={},
    )


class Ledger:
    """A store on a fresh ``tmp_path`` ledger, with the two core claims registered."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.path = file_ledger(tmp_path)
        self.clock = FakeClock(taipei(2026, 10, 1, 9))
        self.store = ForecastStore(self.path, clock=self.clock)
        self.definition = fixture_definition()
        publish_definition(monkeypatch, self.definition)
        self.h3 = self.register(3, RULES_H3)
        self.clock.advance(seconds=1)
        self.h5 = self.register(5, RULES_H5)

    def register(self, horizon: Any, rules: bytes, **overrides: Any) -> str:
        kwargs: dict[str, Any] = {
            "horizon": horizon,
            "rules_version": "1.0.0",
            "rules_bytes": rules,
            "rules_logic_sha256": LOGIC,
            "definition": self.definition,
            "frozen_commit": "abc123",
            "prereg_doc_path": "docs/prereg-v0.32.md",
            "prereg_doc_blob": b"prereg",
            "review_refs": "work/reviews/x.md",
            "replaces_claim_id": None,
            "replace_reason": None,
            "provisional_results_seen": False,
        }
        kwargs.update(overrides)
        return self.store.register_claim(**kwargs)

    def snapshot(
        self, last: date, *, count: int = 3, catch_up: bool = True, **overrides: Any
    ) -> str:
        days = [d for d in weekdays(last - timedelta(days=count * 2 + 4), count * 3) if d <= last]
        kwargs: dict[str, Any] = {
            "bars": [bar(d) for d in days[-count:]],
            "source": "yfinance",
            "source_status": "backup",
            "staleness_minutes": None,
            "reason": None,
            "dropped_rows": [],
            "raw_timestamp_available": False,
        }
        kwargs.update(overrides)
        if catch_up:
            # A snapshot is captured no earlier than its bars were fetched (point in
            # time), so the clock moves up to the latest bar stamp if it is behind it.
            latest = max(max(b["fetched_at"], b["as_of"]) for b in kwargs["bars"])
            self.clock.now = max(self.clock.now, latest)
        return self.store.put_input_series(**kwargs)

    def run(self) -> int:
        return self.store.begin_run(code_commit="abc123", code_digest=CODE, runtime={"py": "3.13"})

    def record(self, run_id: int, claim: str, day: date, series: str, **overrides: Any) -> str:
        kwargs: dict[str, Any] = {
            "run_id": run_id,
            "claim_id": claim,
            "data_as_of": day,
            "label": "range",
            "range_basis": None,
            "missing": [],
            "evidence": {"rules_fired": []},
            "band_def": band(self.definition, 3 if claim == self.h3 else 5),
            "base_close": Decimal("17000.5"),
            "baseline_predictions": dict(BASELINES),
            "input_series_sha256": series,
        }
        kwargs.update(overrides)
        return self.store.write_record(**kwargs)

    def insufficient(self, run_id: int, claim: str, day: date, series: str) -> str:
        none_band = dict.fromkeys(("K_h", "EPS", "sigma_d", "valid_returns", "up_pct", "down_pct"))
        return self.record(
            run_id,
            claim,
            day,
            series,
            label="insufficient",
            missing=[_missing(day)],
            band_def=none_band,
        )

    def rows(self, table: str) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        finally:
            conn.close()


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Ledger:
    return Ledger(tmp_path, monkeypatch)


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return taipei(day.year, day.month, day.day, hour, minute)


# --- S-2, S-3: no timestamp, late or id parameters --------------------------------------

STAMP_PARAMS = {"started_at", "created_at", "captured_at", "registered_at", "ended_at"}
DERIVED_PARAMS = {
    "late",
    "late_cutoff_at",
    "forecast_id",
    "content_hash",
    "validation_status",
    "inputs_max_fetched_at",
    "claim_id_override",
    "registered",
}


@pytest.mark.parametrize(
    "method", ["begin_run", "end_run", "put_input_series", "register_claim", "write_record"]
)
def test_write_functions_take_no_timestamp_or_derived_column(method: str) -> None:
    params = set(inspect.signature(getattr(ForecastStore, method)).parameters)
    assert params.isdisjoint(STAMP_PARAMS | DERIVED_PARAMS)


def _executed_sql(source: str) -> str:
    """Every string constant inside the first argument of an ``.execute(...)`` call."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"execute", "executemany", "executescript"}
            and node.args
        ):
            found.extend(
                sub.value
                for sub in ast.walk(node.args[0])
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
            )
    return " ".join(found).upper()


def test_the_store_never_updates_deletes_or_replaces() -> None:
    sql = _executed_sql(Path(store_module.__file__).read_text(encoding="utf-8"))
    assert "INSERT INTO" in sql
    for word in ("UPDATE", "DELETE", "REPLACE", "DROP", "ALTER", "CREATE"):
        assert re.search(rf"\b{word}\b", sql) is None, word


def test_the_sql_scan_has_teeth() -> None:
    assert re.search(r"\bREPLACE\b", _executed_sql('c.execute(f"INSERT OR REPLACE INTO t {x}")'))
    assert re.search(r"\bREPLACE\b", _executed_sql('c.execute("SELECT replace_reason")')) is None
    assert "UPDATE" not in _executed_sql('"""UPDATE in a docstring"""')


# --- runs ----------------------------------------------------------------------------------


def test_a_run_is_stamped_by_the_store_clock(ledger: Ledger) -> None:
    ledger.clock.now = taipei(2026, 11, 13, 22, 10)
    run_id = ledger.run()
    (stored,) = ledger.rows("forecast_run")
    assert stored["run_id"] == run_id
    assert stored["started_at"] == "2026-11-13T14:10:00.000000+00:00"
    assert stored["trigger"] == "scheduled"
    assert stored["schema_version"] == 1
    assert json.loads(stored["runtime_json"]) == {"py": "3.13"}
    latest = ledger.store.latest_run()
    assert latest is not None and latest.outcome is None and latest.code_digest == CODE


def test_ending_a_run(ledger: Ledger) -> None:
    run_id = ledger.run()
    ledger.clock.advance(minutes=2)
    ledger.store.end_run(run_id, outcome="no_new_session", candidate_t=T, records_written=0)
    (end,) = ledger.rows("forecast_run_end")
    assert end["outcome"] == "no_new_session"
    assert end["candidate_t"] == "2026-11-13"
    assert end["error_class"] is None
    assert end["ended_at"] == canonical_timestamp(ledger.clock.now)
    latest = ledger.store.latest_run()
    assert latest is not None and latest.outcome == "no_new_session"
    with pytest.raises(ForecastStoreError, match="already ended"):
        ledger.store.end_run(run_id, outcome="ok", candidate_t=T, records_written=0)


def test_the_error_class_comes_from_exception_class_name(ledger: Ledger) -> None:
    class Bad(Exception):
        pass

    Bad.__name__ = "bad name!"
    first, second = ledger.run(), ledger.run()
    ledger.store.end_run(
        first, outcome="error", candidate_t=None, records_written=0, error=KeyError()
    )
    ledger.store.end_run(second, outcome="error", candidate_t=None, records_written=0, error=Bad())
    assert [e["error_class"] for e in ledger.rows("forecast_run_end")] == [
        "KeyError",
        "invalid_exception_class",
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"outcome": "late", "candidate_t": None, "records_written": 0},
        {"outcome": "ok", "candidate_t": None, "records_written": True},
        {"outcome": "ok", "candidate_t": datetime(2026, 11, 13, tzinfo=UTC), "records_written": 0},
    ],
)
def test_bad_end_values_are_refused(ledger: Ledger, kwargs: dict[str, Any]) -> None:
    run_id = ledger.run()
    with pytest.raises(ForecastStoreError):
        ledger.store.end_run(run_id, **kwargs)


def test_an_unknown_run_cannot_end(ledger: Ledger) -> None:
    with pytest.raises(ForecastStoreError, match="not a started run"):
        ledger.store.end_run(99, outcome="ok", candidate_t=None, records_written=0)


def test_a_table_check_still_applies_behind_the_store(ledger: Ledger) -> None:
    run_id = ledger.run()
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        ledger.store.end_run(run_id, outcome="error", candidate_t=None, records_written=0)
    assert ledger.rows("forecast_run_end") == []


def test_bad_run_inputs_are_refused(ledger: Ledger) -> None:
    with pytest.raises(ForecastStoreError):
        ledger.store.begin_run(code_commit="", code_digest=CODE, runtime={})
    with pytest.raises(ForecastStoreError):
        ledger.store.begin_run(code_commit="x", code_digest="Z" * 64, runtime={})
    with pytest.raises(ForecastStoreError):
        ledger.store.begin_run(code_commit="x", code_digest=CODE, runtime=[])  # type: ignore[arg-type]
    with pytest.raises(ForecastStoreError):
        ledger.store.begin_run(code_commit="x", code_digest=CODE, runtime={"x": float("nan")})
    assert ledger.store.latest_run() is None


# --- snapshots ------------------------------------------------------------------------------


def test_a_snapshot_is_stored_once_per_content(ledger: Ledger) -> None:
    first = ledger.snapshot(T)
    captured = canonical_timestamp(ledger.clock.now)
    ledger.clock.advance(hours=1)
    again = ledger.snapshot(T, source_status="fresh")
    (stored,) = ledger.rows("forecast_input_series")
    assert first == again == stored["content_sha256"]
    assert stored["captured_at"] == captured
    assert stored["source_status"] == "backup"
    assert stored["raw_timestamp_available"] == 0
    bars = json.loads(stored["bars_json"])
    assert content_sha256(bars) == first
    assert bars[-1]["session_date"] == T.isoformat()


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": ""},
        {"source_status": " "},
        {"reason": ""},
        {"staleness_minutes": 1.5},
        {"staleness_minutes": True},
        {"raw_timestamp_available": 0},
        {"bars": []},
        {"dropped_rows": [{"x": float("inf")}]},
    ],
)
def test_bad_snapshot_inputs_are_refused(ledger: Ledger, overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ledger.snapshot(T, **overrides)
    assert ledger.rows("forecast_input_series") == []


# --- claims ---------------------------------------------------------------------------------


def test_registration_derives_the_id_and_the_hashes(ledger: Ledger) -> None:
    rows = ledger.rows("forecast_claim_registry")
    assert [r["claim_id"] for r in rows] == [
        "market|h3|1.0.0|dirdef-v1.0|forward",
        "market|h5|1.0.0|dirdef-v1.0|forward",
    ]
    first = rows[0]
    assert first["scope_key"] == "TAIEX" and first["kind"] == "forward"
    assert first["rules_bytes"] == RULES_H3
    assert first["definition_sha256"] == definition_sha256(ledger.definition)
    assert first["definition_logic_sha256"] == definition_logic_sha256(ledger.definition)
    # Read back in JSON mode: the strict model takes JSON arrays for its tuples there.
    stored = DirectionDefinition.model_validate_json(first["definition_json"])
    assert definition_sha256(stored) == first["definition_sha256"]
    assert first["registered_at"] == "2026-10-01T01:00:00.000000+00:00"
    assert first["provisional_results_seen"] == 0


def test_registration_order_must_follow_the_clock(ledger: Ledger) -> None:
    with pytest.raises(ForecastStoreError, match="later than every registration"):
        ledger.register(3, b"other")  # the clock has not moved since the h5 registration
    ledger.clock.advance(seconds=-5)
    with pytest.raises(ForecastStoreError, match="later than every registration"):
        ledger.register(3, b"other")


def test_a_replacement_needs_a_reason_and_the_same_horizon(ledger: Ledger) -> None:
    ledger.clock.advance(seconds=1)
    with pytest.raises(ForecastStoreError, match="replace_reason"):
        ledger.register(3, b"v2", rules_version="1.1.0", replaces_claim_id=ledger.h3)
    with pytest.raises(ForecastStoreError, match="scope and horizon"):
        ledger.register(
            3, b"v2", rules_version="1.1.0", replaces_claim_id=ledger.h5, replace_reason="x"
        )
    with pytest.raises(ForecastStoreError, match="not a registered forward claim"):
        ledger.register(
            3, b"v2", rules_version="1.1.0", replaces_claim_id="market|h3|x", replace_reason="x"
        )
    new = ledger.register(
        3,
        b"v2",
        rules_version="1.1.0",
        replaces_claim_id=ledger.h3,
        replace_reason="rules text changed",
        provisional_results_seen=True,
    )
    recording = ledger.store.recording_claims()
    assert recording[("market", 3)].claim_id == new
    assert recording[("market", 3)].replaces_claim_id == ledger.h3
    assert recording[("market", 5)].claim_id == ledger.h5
    assert [c.claim_id for c in ledger.store.forward_claims()] == [ledger.h3, ledger.h5, new]


@pytest.mark.parametrize(
    "overrides",
    [
        {"horizon": 4},
        {"rules_version": "a|b"},
        {"rules_bytes": b""},
        {"rules_logic_sha256": "x"},
        {"frozen_commit": ""},
        {"prereg_doc_path": " "},
        {"prereg_doc_blob": "text"},
        {"review_refs": ""},
        {"provisional_results_seen": 1},
        {"definition": {"definition_version": "dirdef-v1.0"}},
        {"replaces_claim_id": None, "replace_reason": "dangling"},
    ],
)
def test_bad_registrations_are_refused(ledger: Ledger, overrides: dict[str, Any]) -> None:
    ledger.clock.advance(seconds=1)
    with pytest.raises(ForecastStoreError):
        kwargs: dict[str, Any] = {"horizon": 3, "rules": b"other", "rules_version": "2.0.0"}
        kwargs.update(overrides)
        ledger.register(**kwargs)
    assert len(ledger.rows("forecast_claim_registry")) == 2


def test_an_unregistered_claim_is_none(ledger: Ledger) -> None:
    assert ledger.store.claim("market|h3|nope|dirdef-v1.0|forward") is None


# --- records --------------------------------------------------------------------------------


def test_a_record_is_written_with_store_derived_columns(ledger: Ledger) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    run_id = ledger.run()
    forecast_id = ledger.record(run_id, ledger.h3, T, series)
    (stored,) = ledger.rows("forecast_record")
    assert stored["forecast_id"] == forecast_id
    assert stored["scope_kind"] == "market" and stored["scope_key"] == "TAIEX"
    assert stored["horizon"] == 3
    assert stored["rules_sha256"] == ledger.rows("forecast_claim_registry")[0]["rules_sha256"]
    assert stored["created_at"] == "2026-11-13T14:10:00.000000+00:00"
    assert stored["late"] == 0
    assert stored["late_cutoff_at"] == "2026-11-13T16:00:00.000000+00:00"
    assert stored["valid_until_session_estimate"] == "2026-11-18"  # Fri + 3 weekdays
    assert stored["validation_status"] == "unverified"
    assert stored["inputs_max_fetched_at"] == "2026-11-13T12:00:00.000000+00:00"
    assert stored["base_close"] == "17000.5"
    assert stored["missing_json"] == "[]"
    assert set(json.loads(stored["baseline_predictions_json"])) == {"B1", "B2", "B6", "B8"}
    assert stored["content_hash"] == record_content_hash(stored)


def test_the_content_hash_ignores_the_run_columns(ledger: Ledger) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    ledger.record(ledger.run(), ledger.h3, T, series)
    ledger.clock.now = _at(T, 23, 30)
    ledger.record(ledger.run(), ledger.h5, T, series)
    first, second = ledger.rows("forecast_record")
    assert first["content_hash"] != second["content_hash"]  # claim and horizon differ
    same = dict(second, claim_id=first["claim_id"], horizon=3)
    same.update({k: first[k] for k in ("rules_sha256", "valid_until_session_estimate", "band_def")})
    assert record_content_hash(same) == first["content_hash"]


@pytest.mark.parametrize(
    ("clock", "late"),
    [
        (datetime(2026, 11, 13, 23, 59, 59, 999999), 0),
        (datetime(2026, 11, 14, 0, 0, 0), 1),
        (datetime(2026, 11, 14, 0, 0, 0, 1), 1),
        (datetime(2026, 11, 13, 15, 30), 0),
    ],
    ids=["23:59:59.999999", "00:00:00", "00:00:00.000001", "15:30"],
)
def test_late_is_decided_by_the_store_clock(ledger: Ledger, clock: datetime, late: int) -> None:
    # T's bar is fetched at 15:10, so even the 15:30 record is later than its capture.
    series = ledger.snapshot(T, bars=[bar(date(2026, 11, 12)), bar(T, fetched=_at(T, 15, 10))])
    ledger.clock.now = clock.replace(tzinfo=ledger.clock.now.tzinfo)
    ledger.record(ledger.run(), ledger.h3, T, series)
    (stored,) = ledger.rows("forecast_record")
    assert stored["late"] == late
    assert stored["late_cutoff_at"] == "2026-11-13T16:00:00.000000+00:00"


def test_the_clock_zone_does_not_matter(ledger: Ledger) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = datetime(2026, 11, 13, 15, 59, 59, 999999, tzinfo=UTC)
    ledger.record(ledger.run(), ledger.h3, T, series)
    ledger.clock.now = datetime(2026, 11, 13, 16, 0, tzinfo=UTC)
    ledger.record(ledger.run(), ledger.h5, T, series)
    assert [r["late"] for r in ledger.rows("forecast_record")] == [0, 1]


def test_the_default_clock_is_aware_utc() -> None:
    now = store_module.system_clock()
    assert now.utcoffset() == timedelta(0)


def test_a_naive_clock_is_refused(ledger: Ledger) -> None:
    ledger.clock.now = datetime(2026, 11, 13, 22, 10)
    with pytest.raises(ForecastStoreError, match="timezone-aware"):
        ledger.run()


def test_one_record_per_claim_and_day(ledger: Ledger) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    ledger.record(ledger.run(), ledger.h3, T, series)
    ledger.clock.now = _at(T, 23, 10)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.record(ledger.run(), ledger.h3, T, series, label="bearish")
    assert [r["label"] for r in ledger.rows("forecast_record")] == ["range"]
    ledger.record(ledger.run(), ledger.h5, T, series)  # the other claim on the same day
    assert len(ledger.rows("forecast_record")) == 2


def test_an_insufficient_record(ledger: Ledger) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    ledger.insufficient(ledger.run(), ledger.h3, T, series)
    (stored,) = ledger.rows("forecast_record")
    assert stored["label"] == "insufficient"
    (item,) = json.loads(stored["missing_json"])
    assert MissingItem.model_validate(item) == _missing(T)


def _rejected(ledger: Ledger, **overrides: Any) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    run_id = ledger.run()
    with pytest.raises((ForecastStoreError, LabeledThresholdSnapshotIncompleteError)):
        ledger.record(run_id, ledger.h3, T, series, **overrides)
    assert ledger.rows("forecast_record") == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"label": "neutral"},
        {"label": "insufficient"},  # with no missing item
        {"missing": [_missing(T)]},  # labelled, with a missing item
        {"missing": ["E-BARS-SHORT"]},
        {"missing": "E-BARS-SHORT"},
        {"band_def": {"K_h": 0.43}},
        {"band_def": [("K_h", 0.43)]},
        {"band_def": {**{"K_h": 0.43, "EPS": 1e-12, "sigma_d": 0.01}, "extra": 1}},
        {"baseline_predictions": {"B1": "range", "B2": "range", "B6": "range"}},
        {"baseline_predictions": []},
        {"evidence": []},
        {"evidence": {"x": float("nan")}},
        {"base_close": 17000.5},
        {"range_basis": ""},
        {"data_as_of": datetime(2026, 11, 13, tzinfo=UTC)},
        {"input_series_sha256": "x"},
    ],
)
def test_bad_record_inputs_are_refused(ledger: Ledger, overrides: dict[str, Any]) -> None:
    _rejected(ledger, **overrides)


def test_an_insufficient_record_has_no_bounds(ledger: Ledger) -> None:
    _rejected(ledger, label="insufficient", missing=[_missing(T)])  # band has up/down pct


def test_a_broken_missing_item_is_revalidated(ledger: Ledger) -> None:
    broken = MissingItem.model_construct(**{**_missing(T).model_dump(), "source": "yfinance"})
    _rejected(ledger, label="insufficient", missing=[broken])


@pytest.mark.parametrize(
    ("key", "value", "violation"),
    [
        ("sigma_d", None, "sigma_d_missing"),
        ("sigma_d", 0.0, "sigma_d_not_positive_finite"),
        ("K_h", 0.5, "k_h_mismatch"),
        ("valid_returns", 3, "valid_returns_below_min"),
    ],
)
def test_a_labelled_record_goes_through_band(
    ledger: Ledger, key: str, value: object, violation: str
) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    bad = band(ledger.definition)
    bad[key] = value
    with pytest.raises(LabeledThresholdSnapshotIncompleteError) as caught:
        ledger.record(ledger.run(), ledger.h3, T, series, band_def=bad)
    assert violation in caught.value.violations
    assert caught.value.source == "record"
    assert ledger.rows("forecast_record") == []


def test_a_labelled_record_needs_the_published_definition(
    ledger: Ledger, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    run_id = ledger.run()
    other = fixture_definition().model_validate(
        {**ledger.definition.model_dump(), "description": "edited"}
    )
    publish_definition(monkeypatch, other)
    with pytest.raises(ForecastStoreError, match="differs from the claim"):
        ledger.record(run_id, ledger.h3, T, series)
    from app.forecast import definitions

    monkeypatch.setattr(definitions, "PUBLISHED_DIRECTION_DEFINITIONS", {})
    monkeypatch.setattr(definitions, "_DEFINITION_CACHE", {})
    with pytest.raises(UnpublishedVersionError):
        ledger.record(run_id, ledger.h3, T, series)
    ledger.insufficient(run_id, ledger.h3, T, series)  # no band judgement for insufficient
    assert len(ledger.rows("forecast_record")) == 1


def test_t_must_be_the_snapshots_latest_session(ledger: Ledger) -> None:
    series = ledger.snapshot(date(2026, 11, 12))
    ledger.clock.now = _at(T, 22, 10)
    with pytest.raises(ForecastStoreError, match="latest session"):
        ledger.record(ledger.run(), ledger.h3, T, series)


def test_every_snapshot_bar_must_be_final(ledger: Ledger) -> None:
    early = bar(T, fetched=_at(T, 14, 59))
    bars = [bar(date(2026, 11, 12)), early]
    series = ledger.snapshot(T, bars=bars)
    ledger.clock.now = _at(T, 22, 10)
    with pytest.raises(ForecastStoreError, match="not final"):
        ledger.record(ledger.run(), ledger.h3, T, series)
    assert ledger.store.final_sessions() == [date(2026, 11, 12)]


def test_the_snapshot_must_not_postdate_the_record(ledger: Ledger) -> None:
    ledger.clock.now = _at(T, 22, 10)
    series = ledger.snapshot(T)
    run_id = ledger.run()
    ledger.clock.now = _at(T, 22, 9)  # the clock stepped back
    with pytest.raises(ForecastStoreError, match="captured after"):
        ledger.record(run_id, ledger.h3, T, series)


@pytest.mark.parametrize("stamp", ["fetched_at", "as_of"])
@pytest.mark.parametrize("record_hour", [22, 23])
def test_a_bar_stamped_after_the_capture_is_refused(
    ledger: Ledger, stamp: str, record_hour: int
) -> None:
    # M1 (point in time): one bar's fetched_at / as_of is an hour after the store
    # clock that stamps captured_at. At 23:30 the record itself is later than the
    # bar, so only the captured_at comparison can catch it.
    ledger.clock.now = _at(T, 22, 10)
    future = bar(T)
    future[stamp] = _at(T, 23, 10)
    series = ledger.snapshot(T, bars=[bar(date(2026, 11, 12)), future], catch_up=False)
    (stored,) = ledger.rows("forecast_input_series")
    assert stored["captured_at"] == "2026-11-13T14:10:00.000000+00:00"
    ledger.clock.now = _at(T, record_hour, 30)
    run_id = ledger.run()
    with pytest.raises(ForecastStoreError, match="stamped after its captured_at"):
        ledger.record(run_id, ledger.h3, T, series)
    assert ledger.rows("forecast_record") == []


def test_a_bar_stamped_exactly_at_the_capture_is_accepted(ledger: Ledger) -> None:
    ledger.clock.now = _at(T, 20, 0)
    bars = [bar(date(2026, 11, 12)), bar(T, fetched=_at(T, 20, 0))]
    series = ledger.snapshot(T, bars=bars, catch_up=False)
    ledger.clock.now = _at(T, 22, 10)
    ledger.record(ledger.run(), ledger.h3, T, series)
    (stored,) = ledger.rows("forecast_record")
    (snapshot,) = ledger.rows("forecast_input_series")
    assert stored["inputs_max_fetched_at"] == snapshot["captured_at"]
    assert stored["inputs_max_fetched_at"] == "2026-11-13T12:00:00.000000+00:00"


def test_unknown_references_are_refused(ledger: Ledger) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    run_id = ledger.run()
    with pytest.raises(ForecastStoreError, match="not a stored snapshot"):
        ledger.record(run_id, ledger.h3, T, "9" * 64)
    with pytest.raises(ForecastStoreError, match="not a registered forward claim"):
        ledger.record(run_id, "market|h3|x|dirdef-v1.0|forward", T, series)
    with pytest.raises(ForecastStoreError, match="not a started run"):
        ledger.record(99, ledger.h3, T, series)
    with pytest.raises(ForecastStoreError, match="run_id must be an int"):
        ledger.record(True, ledger.h3, T, series)
    ledger.store.end_run(run_id, outcome="ok", candidate_t=T, records_written=0)
    with pytest.raises(ForecastStoreError, match="already ended"):
        ledger.record(run_id, ledger.h3, T, series)


def test_writes_are_refused_on_an_incomplete_schema(ledger: Ledger) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    run_id = ledger.run()
    conn = sqlite3.connect(ledger.path)
    conn.execute("DROP TRIGGER forecast_record_no_update")
    conn.close()
    with pytest.raises(SchemaIncompleteError):
        ledger.record(run_id, ledger.h3, T, series)
    with pytest.raises(SchemaIncompleteError):
        ledger.run()
    assert ledger.rows("forecast_record") == []
    assert len(ledger.rows("forecast_run")) == 1


def test_the_store_creates_no_schema(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    store = ForecastStore(path, clock=FakeClock(_at(T, 22, 10)))
    with pytest.raises(SchemaIncompleteError):
        store.begin_run(code_commit="x", code_digest=CODE, runtime={})
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0
    conn.close()


def test_a_replace_through_the_store_connection_is_refused(ledger: Ledger) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    ledger.record(ledger.run(), ledger.h3, T, series)
    (stored,) = ledger.rows("forecast_record")
    replaced = dict(stored, label="bearish")
    names = ", ".join(replaced)
    marks = ", ".join("?" for _ in replaced)
    conn = ledger.store._connect()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(
                f"INSERT OR REPLACE INTO forecast_record ({names}) VALUES ({marks})",
                tuple(replaced.values()),
            )
    finally:
        conn.close()
    assert [r["label"] for r in ledger.rows("forecast_record")] == ["range"]


# --- queries --------------------------------------------------------------------------------


def test_first_record_at_and_m_db(ledger: Ledger) -> None:
    assert ledger.store.first_record_at(ledger.h3) is None
    assert ledger.store.counts_toward_m(ledger.h3) is False
    assert ledger.store.m_db() == 0
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 0, 30) + timedelta(days=1)  # late
    ledger.record(ledger.run(), ledger.h3, T, series)
    first = ledger.clock.now
    later = ledger.snapshot(date(2026, 11, 16))
    ledger.clock.now = _at(date(2026, 11, 16), 22, 10)
    ledger.record(ledger.run(), ledger.h3, date(2026, 11, 16), later)
    assert ledger.store.first_record_at(ledger.h3) == first.astimezone(UTC)
    assert ledger.store.counts_toward_m(ledger.h3) is True
    assert ledger.store.m_db() == 1
    ledger.record(ledger.run(), ledger.h5, date(2026, 11, 16), later)
    assert ledger.store.m_db() == 2


def test_m_db_counts_a_replaced_claim_with_records(ledger: Ledger) -> None:
    series = ledger.snapshot(T)
    ledger.clock.now = _at(T, 22, 10)
    ledger.record(ledger.run(), ledger.h3, T, series)
    ledger.clock.advance(seconds=1)
    ledger.register(
        3, b"v2", rules_version="1.1.0", replaces_claim_id=ledger.h3, replace_reason="x"
    )
    assert ledger.store.m_db() == 1  # the new claim has no record yet; the old one still counts


def test_d_v_skips_late_records(ledger: Ledger) -> None:
    first, second = date(2026, 11, 12), T
    s1 = ledger.snapshot(first)
    ledger.clock.now = _at(first, 23) + timedelta(hours=2)  # 01:00 the next day: late
    ledger.record(ledger.run(), ledger.h3, first, s1)
    assert ledger.store.d_v(ledger.h3) is None
    assert ledger.store.n_hat(ledger.h3) == 0
    s2 = ledger.snapshot(second)
    ledger.clock.now = _at(second, 22, 10)
    ledger.record(ledger.run(), ledger.h3, second, s2)
    assert ledger.store.d_v(ledger.h3) == second


def _on_time(ledger: Ledger, claim: str, index: int, *, late: bool = False) -> None:
    day = DAYS[index]
    series = ledger.snapshot(day, count=index + 1, bars=[bar(d) for d in DAYS[: index + 1]])
    ledger.clock.now = _at(day, 22, 10) + (timedelta(hours=3) if late else timedelta(0))
    ledger.insufficient(ledger.run(), claim, day, series)


def test_n_hat_counts_grid_points_whose_h_th_session_has_appeared(ledger: Ledger) -> None:
    for index in (0, 3, 6):
        _on_time(ledger, ledger.h3, index)
    assert ledger.store.final_sessions() == DAYS[:7]
    # Grid D_v, +3, +6. Index 6 has no third session after it yet.
    assert ledger.store.n_hat(ledger.h3) == 2
    _on_time(ledger, ledger.h3, 7)  # off the grid: never counted
    _on_time(ledger, ledger.h3, 9, late=True)  # on the grid, but late
    assert ledger.store.final_sessions() == DAYS[:10]
    assert ledger.store.n_hat(ledger.h3) == 3
    ledger.snapshot(DAYS[12], bars=[bar(d) for d in DAYS[:13]])
    assert ledger.store.n_hat(ledger.h3) == 3  # 9 is late; 12 has no record
    assert ledger.store.n_hat(ledger.h5) == 0


def test_n_hat_needs_a_registered_claim(ledger: Ledger) -> None:
    with pytest.raises(ForecastStoreError):
        ledger.store.n_hat("market|h3|x|dirdef-v1.0|forward")


def test_n_hat_refuses_a_d_v_outside_the_snapshots(ledger: Ledger) -> None:
    _on_time(ledger, ledger.h3, 0)
    conn = sqlite3.connect(ledger.path)
    stored = conn.execute("SELECT bars_json FROM forecast_input_series").fetchone()[0]
    conn.close()
    assert json.loads(stored)[-1]["session_date"] == DAYS[0].isoformat()
    ledger.store.final_sessions = lambda: DAYS[1:5]  # type: ignore[method-assign]
    with pytest.raises(LedgerInconsistentError):
        ledger.store.n_hat(ledger.h3)


# --- pure helpers ---------------------------------------------------------------------------


def test_the_cutoff_is_t_plus_one_midnight_taipei() -> None:
    assert late_cutoff_at(T) == datetime(2026, 11, 13, 16, 0, tzinfo=UTC)
    assert late_cutoff_at(date(2026, 12, 31)) == datetime(2026, 12, 31, 16, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("day", "horizon", "expected"),
    [
        (T, 3, date(2026, 11, 18)),
        (T, 5, date(2026, 11, 20)),
        (date(2026, 11, 10), 3, date(2026, 11, 13)),
    ],
)
def test_valid_until_counts_weekdays(day: date, horizon: int, expected: date) -> None:
    assert valid_until_session_estimate(day, horizon) == expected


def test_ulids_encode_the_millisecond_and_are_crockford() -> None:
    at = datetime(2026, 11, 13, 14, 10, tzinfo=UTC)
    zero = new_ulid(at, lambda n: bytes(n))
    assert len(zero) == 26 and zero.endswith("0" * 16)
    millis = int(at.timestamp() * 1000)
    decoded = 0
    for char in zero[:10]:
        decoded = decoded * 32 + "0123456789ABCDEFGHJKMNPQRSTVWXYZ".index(char)
    assert decoded == millis
    assert new_ulid(at) != new_ulid(at)
    with pytest.raises(ValueError):
        new_ulid(datetime(1969, 12, 31, tzinfo=UTC))
