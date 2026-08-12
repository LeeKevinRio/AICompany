"""Persistence: batches, schedule rows, state effects, rule versions, the log."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.playbook.models import (
    Directive,
    FastMarketState,
    PlaybookEvaluation,
    RuleParams,
    StateEffect,
)
from app.playbook.store import PlaybookStore
from tests import playbook_helpers as helper
from tests.playbook_helpers import TUESDAY, WEDNESDAY


@pytest.fixture
def store(tmp_path: Path) -> PlaybookStore:
    return PlaybookStore(db_path=tmp_path / "playbook.db")


def _directive(**overrides: object) -> Directive:
    base = Directive(
        symbol="2330",
        batch_no=1,
        action="buy",
        shares=100,
        rule_id="R1",
        rule_summary="R1 排程日進場",
        data_date=TUESDAY,
        execution_date=WEDNESDAY,
        reference_price=Decimal("100"),
        limit_low=Decimal("98"),
        limit_high=Decimal("102"),
        limit_note="限價帶",
        data_status="fresh",
        source="twse",
    )
    return base.model_copy(update=dict(overrides))


def _evaluation(*directives: Directive) -> PlaybookEvaluation:
    return PlaybookEvaluation(
        data_date=TUESDAY,
        execution_date=WEDNESDAY,
        mode="normal",
        mode_reason="正常模式",
        is_schedule_day=True,
        fast_market=FastMarketState(
            active=False, annualized_vol_20d=None, large_move_days=0, reason=None
        ),
        rules_version=1,
        directives=list(directives),
        effects=[],
        warnings=[],
        snapshot=[],
    )


def test_ensure_batches_creates_three_planned_batches_per_symbol(store: PlaybookStore) -> None:
    store.ensure_batches(["2330", "2454"], batches_per_target=3)
    store.ensure_batches(["2330"], batches_per_target=3)  # idempotent
    batches = store.list_batches()
    assert len(batches) == 6
    assert all(batch.status == "planned" for batch in batches)


def test_a_batch_round_trips_including_decimals(store: PlaybookStore) -> None:
    store.ensure_batches(["2330"], batches_per_target=3)
    store.save_batch(
        helper.batch(cost="123.45", shares=500, remaining=200, peak="180.5", p1_done=True)
    )
    stored = store.get_batch("2330", 1)
    assert stored is not None
    assert stored.cost == Decimal("123.45")
    assert stored.peak_close == Decimal("180.5")
    assert stored.p1_done is True
    assert stored.remaining_shares == 200


def test_peak_close_only_moves_up(store: PlaybookStore) -> None:
    store.ensure_batches(["2330"], batches_per_target=3)
    store.save_batch(helper.batch(cost="100", shares=300, peak="120"))
    store.roll_peak_closes({"2330": Decimal("110")})
    assert store.get_batch("2330", 1).peak_close == Decimal("120")  # type: ignore[union-attr]
    store.roll_peak_closes({"2330": Decimal("130")})
    assert store.get_batch("2330", 1).peak_close == Decimal("130")  # type: ignore[union-attr]


def test_effects_persist_pause_blacklist_freeze_and_defense(store: PlaybookStore) -> None:
    store.ensure_batches(["2330"], batches_per_target=3)
    store.apply_effects(
        [
            StateEffect(kind="pause_symbol", symbol="2330", note="S1"),
            StateEffect(kind="blacklist", symbol="2330", value=60, note="S2"),
            StateEffect(kind="freeze_portfolio", value=10, note="S3"),
            StateEffect(kind="defense_on", note="M1"),
        ],
        data_date=TUESDAY,
        calendar=helper.calendar(),
    )
    states = store.symbol_states(TUESDAY)
    assert states["2330"].paused is True
    assert states["2330"].blacklisted is True
    assert states["2330"].blacklist_until == date(2026, 11, 3)  # 60 trading days
    portfolio = store.portfolio_state()
    assert portfolio.freeze_until == date(2026, 8, 25)
    assert portfolio.defense_active is True


def test_a_blacklist_expires_on_its_own(store: PlaybookStore) -> None:
    store.apply_effects(
        [StateEffect(kind="blacklist", symbol="2330", value=60, note="S2")],
        data_date=TUESDAY,
        calendar=helper.calendar(),
    )
    assert store.symbol_states(date(2026, 11, 4)) == {}


def test_fill_dependent_effects_are_not_applied_by_apply_effects(store: PlaybookStore) -> None:
    """A decision is not a fill: shares only move through :meth:`settle`."""
    store.ensure_batches(["2330"], batches_per_target=3)
    store.apply_effects(
        [StateEffect(kind="batch_entered", symbol="2330", batch_no=1, value=100, note="R1")],
        data_date=TUESDAY,
        calendar=helper.calendar(),
    )
    assert store.get_batch("2330", 1).status == "planned"  # type: ignore[union-attr]


def test_deferral_counter_and_skip_persist(store: PlaybookStore) -> None:
    store.ensure_batches(["2330"], batches_per_target=3)
    store.apply_effects(
        [StateEffect(kind="defer_increment", symbol="2330", batch_no=1, value=2, note="R2")],
        data_date=TUESDAY,
        calendar=helper.calendar(),
    )
    assert store.get_batch("2330", 1).defer_count == 2  # type: ignore[union-attr]
    store.apply_effects(
        [StateEffect(kind="defer_reset", symbol="2330", note="S1 恢復")],
        data_date=TUESDAY,
        calendar=helper.calendar(),
    )
    assert store.get_batch("2330", 1).defer_count == 0  # type: ignore[union-attr]
    store.apply_effects(
        [StateEffect(kind="batch_skipped", symbol="2330", batch_no=1, note="R3")],
        data_date=TUESDAY,
        calendar=helper.calendar(),
    )
    assert store.get_batch("2330", 1).status == "skipped"  # type: ignore[union-attr]


def test_selling_marks_p1_and_reduces_the_remainder(store: PlaybookStore) -> None:
    store.ensure_batches(["2330"], batches_per_target=3)
    store.save_batch(helper.batch(cost="100", shares=300))
    store.settle(
        _directive(action="sell", shares=100, rule_id="P1", status="executed")
    )
    stored = store.get_batch("2330", 1)
    assert stored is not None
    assert stored.remaining_shares == 200
    assert stored.p1_done is True
    assert stored.status == "open"


def test_selling_the_last_share_closes_the_batch(store: PlaybookStore) -> None:
    store.ensure_batches(["2330"], batches_per_target=3)
    store.save_batch(helper.batch(cost="100", shares=300))
    store.settle(_directive(action="sell", shares=300, rule_id="S1", status="executed"))
    assert store.get_batch("2330", 1).status == "closed"  # type: ignore[union-attr]


def test_rule_params_default_until_a_version_is_effective(store: PlaybookStore) -> None:
    assert store.active_params(TUESDAY).version == 1
    store.submit_rule_change(
        RuleParams(version=2, effective_date=WEDNESDAY, s1_ratio=Decimal("0.95"))
    )
    assert store.active_params(TUESDAY).s1_ratio == Decimal("0.90")
    assert store.active_params(WEDNESDAY).version == 2
    assert store.next_version() == 3


def test_the_directive_log_keeps_provenance_for_every_line(store: PlaybookStore) -> None:
    store.record_directives(_evaluation(_directive(), _directive(rule_id="S1", action="sell")))
    rows = store.directive_log()
    assert len(rows) == 2
    assert rows[0]["rules_version"] == 1
    assert rows[0]["data_date"] == TUESDAY.isoformat()
    assert rows[0]["execution_date"] == WEDNESDAY.isoformat()
    assert rows[0]["reference_price"] == "100"
    assert rows[0]["source"] == "twse"


def test_schedule_rows_record_the_planned_date_and_follow_the_outcome(
    store: PlaybookStore,
) -> None:
    store.ensure_batches(["2330"], batches_per_target=3)
    directive = _directive()
    store.record_schedule(_evaluation(directive))
    (row,) = store.list_schedule()
    assert row["scheduled_date"] == WEDNESDAY.isoformat()
    assert row["status"] == "pending"
    store.settle(directive.model_copy(update={"status": "missed"}))
    assert store.list_schedule()[0]["status"] == "missed"
