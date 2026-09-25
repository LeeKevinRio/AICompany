"""Main-DB sector tables (ADR-0012 C-8, C-9, C-21, C-27, D-6, D-14).

* T-16: UPDATE / DELETE on the four gate tables raise ``sqlite3.IntegrityError``
  from ``RAISE(ABORT)``; the registry's two NULL -> value updates succeed once
  and only once; every trigger exists, and the existence check has teeth.
* T-21: every connection runs with ``busy_timeout`` > 0.
* T-10 (repository half): hindsight / backfill / unknown-run records raise
  ``BiasedDataRejected`` on save and on load.
* T-12 (registry half): m is counted from the registry.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Collection
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.sectors import ranking, store, universe
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.definition import SectorMomentumDefinition
from app.sectors.models import ApprovalRecord, GateCheckRecord, SelfcheckRecord, StatsRecord
from app.sectors.store import (
    BiasedDataRejected,
    BoardProvenance,
    SectorApprovalStore,
    SectorBoardStore,
    SectorMethodRegistry,
    SectorStatsRepository,
)
from tests.sectors_helpers import Member, members, scenario

KNOWN_RUNS = frozenset({"101", "102", "103"})


class FakeRuns:
    def __init__(self, known: frozenset[str] = KNOWN_RUNS) -> None:
        self.known = known

    def existing_run_ids(self, run_ids: Collection[str]) -> frozenset[str]:
        return frozenset(run_ids) & self.known


def _stats(run_id: str = "s1", **kw: Any) -> StatsRecord:
    base = StatsRecord(
        run_id=run_id,
        method_version=V1.method_version,
        regime="pit",
        data_regime="forward_pit",
        source_run_ids=("101", "102"),
        m_at_evaluation=1,
        sample_count=12,
        effective_sample_count=10.5,
        beat_count_net=6,
        beat_count_gross=7,
        base_rate_net=0.45,
        base_rate_gross=0.5,
        ci_low_net=0.2,
        ci_high_net=0.8,
        bootstrap_low_net=0.2,
        bootstrap_high_net=0.8,
        delta_real=5.0,
        delta_shuffle=None,
        sample_start=date(2026, 10, 1),
        sample_end=date(2026, 12, 1),
        stats_as_of=date(2026, 12, 1),
        computed_at=datetime(2026, 12, 2, 10, tzinfo=UTC),
        recompute_session=date(2026, 12, 1),
        running_commit="abc123",
        selfcheck_passed=False,
        data_quality_passed=True,
        pit_history_missing=False,
        gate_checks=tuple(
            GateCheckRecord(gate=g, passed=g != "G1") for g in ("G1", "G2", "G3", "G4", "G5", "G6")
        ),
        selfchecks=(
            SelfcheckRecord("T1", "pass", seed=7, value=0.0),
            SelfcheckRecord("T8", "skipped_insufficient_n"),
            SelfcheckRecord("T5", "vacuous", detail="no delisting in window"),
        ),
    )
    return dataclasses.replace(base, **kw)


def _approval(kind: str = "first_transition_risk") -> ApprovalRecord:
    return ApprovalRecord(
        kind=kind,  # type: ignore[arg-type]
        run_id="s1",
        method_version=V1.method_version,
        operator="dev-lead",
        reviewer="risk-compliance-officer",
        review_doc_path="work/review.md",
        review_doc_blob_hash="deadbeef",
        approved_at=datetime(2027, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "main.db"
    store.ensure_schema(path)
    return path


def _seed_all(db: Path) -> None:
    SectorStatsRepository(FakeRuns(), db).save(_stats())
    SectorApprovalStore(db).add(_approval())
    SectorMethodRegistry(db).register(
        V1, frozen_commit="f00d", registered_at=datetime(2026, 9, 1, tzinfo=UTC)
    )


# ---------------------------------------------------------------------------
# T-16: append-only triggers
# ---------------------------------------------------------------------------

MUTATIONS = {
    "sector_rank_stats": (
        "UPDATE sector_rank_stats SET sample_count = 999",
        "DELETE FROM sector_rank_stats",
    ),
    "sector_gate_checks": (
        "UPDATE sector_gate_checks SET status = 'pass'",
        "DELETE FROM sector_gate_checks",
    ),
    "sector_gate_approvals": (
        "UPDATE sector_gate_approvals SET reviewer = 'someone else'",
        "DELETE FROM sector_gate_approvals",
    ),
    "sector_method_registry": (
        "UPDATE sector_method_registry SET frozen_commit = 'other'",
        "DELETE FROM sector_method_registry",
    ),
}


@pytest.mark.parametrize("table", store.APPEND_ONLY_TABLES)
def test_update_and_delete_abort_on_every_gate_table(db: Path, table: str) -> None:
    _seed_all(db)
    for statement in MUTATIONS[table]:
        with closing(sqlite3.connect(db)) as conn:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                conn.execute(statement)


def _registry_row(db: Path) -> tuple[object, ...]:
    with closing(sqlite3.connect(db)) as conn:
        row = conn.execute(
            "SELECT accumulation_start, first_forward_eval_at, counts_toward_m "
            "FROM sector_method_registry"
        ).fetchone()
    assert row is not None
    return tuple(row)


def test_first_forward_eval_is_written_once_with_counts_toward_m(db: Path) -> None:
    _seed_all(db)
    sql = (
        "UPDATE sector_method_registry SET first_forward_eval_at = ?, counts_toward_m = 1 "
        "WHERE method_version = ?"
    )
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(sql, ("2026-12-02T10:00:00+00:00", V1.method_version))
    assert _registry_row(db)[1:] == ("2026-12-02T10:00:00+00:00", 1)
    with closing(sqlite3.connect(db)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, ("2027-01-01T00:00:00+00:00", V1.method_version))


def test_first_forward_eval_without_counting_toward_m_is_refused(db: Path) -> None:
    _seed_all(db)
    with closing(sqlite3.connect(db)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE sector_method_registry SET first_forward_eval_at = 'x'")


def test_a_permitted_update_that_also_touches_another_column_is_refused(db: Path) -> None:
    _seed_all(db)
    with closing(sqlite3.connect(db)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE sector_method_registry SET first_forward_eval_at = 'x', "
                "counts_toward_m = 1, holding_days = 20"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE sector_method_registry SET accumulation_start = '2026-10-01', "
                "frozen_commit = 'other'"
            )
    assert _registry_row(db) == (None, None, 0)


def test_counts_toward_m_cannot_change_on_its_own(db: Path) -> None:
    _seed_all(db)
    with closing(sqlite3.connect(db)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE sector_method_registry SET counts_toward_m = 1")


def test_accumulation_start_is_written_once(db: Path) -> None:
    _seed_all(db)
    registry = SectorMethodRegistry(db)
    registry.record_accumulation_start(V1.method_version, date(2026, 10, 1))
    assert _registry_row(db)[0] == "2026-10-01"
    with pytest.raises(ValueError, match="already set"):
        registry.record_accumulation_start(V1.method_version, date(2026, 10, 2))
    with closing(sqlite3.connect(db)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE sector_method_registry SET accumulation_start = '2026-10-02'")


def _trigger_names(db: Path) -> set[str]:
    with closing(sqlite3.connect(db)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()
    return {str(name) for (name,) in rows}


def test_every_trigger_exists(db: Path) -> None:
    assert store.EXPECTED_TRIGGERS <= _trigger_names(db)


def test_trigger_existence_check_has_teeth(db: Path) -> None:
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("DROP TRIGGER sector_gate_checks_no_delete")
    assert not store.EXPECTED_TRIGGERS <= _trigger_names(db)


def test_stores_offer_no_update_or_delete_methods() -> None:
    for cls in (SectorBoardStore, SectorStatsRepository, SectorApprovalStore, SectorMethodRegistry):
        public = {name for name in dir(cls) if not name.startswith("_")}
        assert not {
            name for name in public if any(v in name for v in ("update", "delete", "remove"))
        }


# ---------------------------------------------------------------------------
# T-21: busy_timeout
# ---------------------------------------------------------------------------


def test_every_store_connection_has_a_busy_timeout(db: Path) -> None:
    for instance in (
        SectorBoardStore(db),
        SectorStatsRepository(FakeRuns(), db),
        SectorApprovalStore(db),
        SectorMethodRegistry(db),
    ):
        with closing(instance._connect()) as conn:
            (timeout,) = conn.execute("PRAGMA busy_timeout").fetchone()
        assert timeout > 0


# ---------------------------------------------------------------------------
# statistics repository (D-14, C-27)
# ---------------------------------------------------------------------------


def test_stats_round_trip_with_checks(db: Path) -> None:
    repo = SectorStatsRepository(FakeRuns(), db)
    record = _stats()
    repo.save(record)
    assert repo.load(V1.method_version) == (record,)
    assert repo.latest_history() == (record,)


@pytest.mark.parametrize(
    "overrides",
    [
        {"regime": "hindsight"},
        {"data_regime": "backfill_non_pit"},
        {"source_run_ids": ()},
        {"source_run_ids": ("101", "999")},
    ],
)
def test_non_pit_records_are_rejected_on_save(db: Path, overrides: dict[str, Any]) -> None:
    repo = SectorStatsRepository(FakeRuns(), db)
    with pytest.raises(BiasedDataRejected):
        repo.save(_stats(**overrides))
    assert repo.load(V1.method_version) == ()


def test_rows_whose_source_runs_vanished_are_rejected_on_load(db: Path) -> None:
    SectorStatsRepository(FakeRuns(), db).save(_stats())
    with pytest.raises(BiasedDataRejected):
        SectorStatsRepository(FakeRuns(frozenset({"101"})), db).load(V1.method_version)


def test_the_table_itself_refuses_non_pit_rows(db: Path) -> None:
    with closing(sqlite3.connect(db)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sector_rank_stats (run_id, method_version, regime, data_regime) "
                "VALUES ('x', 'v', 'hindsight', 'forward_pit')"
            )


def test_approval_rows_enforce_kind_and_operator(db: Path) -> None:
    approvals = SectorApprovalStore(db)
    approvals.add(_approval())
    assert approvals.list_for(V1.method_version) == (_approval(),)
    with pytest.raises(sqlite3.IntegrityError):
        approvals.add(dataclasses.replace(_approval("quarterly_qa"), operator="ceo"))
    with pytest.raises(sqlite3.IntegrityError):
        approvals.add(dataclasses.replace(_approval(), operator="qa-reviewer"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# registry: m (D-6, T-12)
# ---------------------------------------------------------------------------


def test_m_counts_versions_that_count_toward_it(db: Path) -> None:
    registry = SectorMethodRegistry(db)
    at = datetime(2026, 9, 1, tzinfo=UTC)
    registry.register(V1, frozen_commit="f00d", registered_at=at)
    assert registry.m() == 0
    registry.record_first_forward_eval(V1.method_version, datetime(2026, 12, 2, tzinfo=UTC))
    assert registry.m() == 1
    with pytest.raises(ValueError):
        registry.record_first_forward_eval(V1.method_version, datetime(2027, 1, 2, tzinfo=UTC))
    l20 = SectorMomentumDefinition(
        method_version="sector-rel-v1.1-L20-H5", lookback_days=20, holding_days=5
    )
    registry.register(l20, frozen_commit="beef", registered_at=at, counts_toward_m=True)
    assert registry.m() == 2
    row = registry.get(V1.method_version)
    assert row is not None and row.counts_toward_m and row.first_forward_eval_at is not None


# ---------------------------------------------------------------------------
# board round trip
# ---------------------------------------------------------------------------


def test_board_round_trip_keeps_counts_members_and_constituents(db: Path) -> None:
    sc = scenario(
        {
            "01": members("11", 6, ret=0.02),
            "02": [Member("1200", ex_date=True), *members("125", 5)],
            "20": members("20", 3),
        }
    )
    calc = universe.calculation_set(sc.market.as_of(sc.t), V1)
    board = ranking.rank_sectors(calc, V1)
    boards = SectorBoardStore(db)
    boards.save_board(
        definition=V1,
        calc=calc,
        ranking=board,
        provenance=BoardProvenance(
            board_id="b1",
            market="TW",
            data_source="twse_snapshot",
            bars_run_id="101",
            bars_recorded_at=datetime(2026, 4, 10, 10, tzinfo=UTC),
            computed_at=datetime(2026, 4, 10, 11, tzinfo=UTC),
            source_run_ids=("101", "102"),
            ex_dividend_feed_covered=True,
        ),
        turnover={"01": 1.1},
        names={"1105": "某公司"},
    )
    assert boards.latest_board_id("TW") == "b1"
    loaded = boards.load_board("b1")
    assert loaded is not None
    assert loaded.data_as_of == sc.t
    assert loaded.market_expected_count == len(calc.market.expected)
    assert loaded.market_ex_date_excluded_count == 1
    assert [row.sector_code for row in loaded.ranked] == ["01"]
    ranked = loaded.ranked[0]
    assert set(ranked.member_symbols) == calc.sector("01").members
    assert ranked.constituent_count == len(calc.sector("01").members)
    assert [c.symbol for c in ranked.constituents] == [
        c.symbol for c in board.ranked[0].constituents
    ]
    assert ranked.constituents[0].name == "某公司"
    assert ranked.turnover_value_ratio_5_20 == 1.1
    assert ranked.coverage == board.ranked[0].coverage
    assert {row.sector_code: row.reason_code for row in loaded.excluded} == {
        "02": "ex_dividend_exclusion",
        "20": "unranked_category",
    }
    assert loaded.excluded[0].computable_count == 5 and loaded.excluded[0].expected_count == 6
    assert boards.load_board("missing") is None
