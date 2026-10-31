"""The N-172 offline probe: every duplicate category, the D-A guards, and its read-only promise.

Every DB lives under ``tmp_path``. The schema comes from the real ``PlaybookStore`` and
``PriceBarCache``; hand-made rows go in through plain ``sqlite3`` so each category can be
staged exactly. One test drives the production write path (``record_directives`` twice, then
the claim and settle that ``/today`` runs) to pin the D-A estimate to the cash actually lost.
No network, no real DB, no ``.env``.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.data.cache import PriceBarCache
from app.playbook.models import Directive, FastMarketState, PlaybookEvaluation
from app.playbook.store import PlaybookStore
from tests import playbook_helpers as helper

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND / "scripts" / "n172_duplicate_probe.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("n172_duplicate_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load()

RUN_AT = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 11, 3)
SET_AT_EARLY = "2026-08-01T00:00:00+00:00"
MANUAL = "NEEDS_MANUAL_REVIEW (需人工判讀)"
TRAILING_SUMMARY = "P2｜移動停利觸發：收盤 90 跌破 25MA 95，出清該批餘額"
REDUCTION_SUMMARY = "P2｜收盤 135 ≥ 成本 100 ×1.35 = 135，再賣 1/3 = 33 股，餘轉移動停利"


# ---------------------------------------------------------------- staging helpers


def _db(tmp_path: Path, *, with_bars: bool = True) -> Path:
    path = tmp_path / "stock-desk.db"
    PlaybookStore(db_path=path)
    if with_bars:
        PriceBarCache(path)
    return path


_ROW_DEFAULTS: dict[str, Any] = {
    "created_at": "2026-08-11T10:00:00+00:00",
    "rules_version": 1,
    "symbol": "2330",
    "batch_no": 1,
    "action": "buy",
    "shares": 100,
    "rule_id": "R1",
    "rule_summary": "R1｜排程日進場",
    "data_date": "2026-08-11",
    "execution_date": "2026-08-12",
    "data_status": "fresh",
    "source": "fixture",
    "status": "pending",
    "settled": 0,
    "settled_at": None,
    "settled_open_price": None,
}


def _row(path: Path, **fields: Any) -> int:
    values = {**_ROW_DEFAULTS, **fields}
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    with closing(sqlite3.connect(path)) as conn, conn:
        cursor = conn.execute(
            f"INSERT INTO playbook_directives ({columns}) VALUES ({marks})", tuple(values.values())
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)


def _executed(path: Path, created_at: str, *, price: str | None = "600", **fields: Any) -> int:
    settled_at = fields.pop("settled_at", created_at.replace("T10", "T23"))
    return _row(
        path,
        created_at=created_at,
        status="executed",
        settled=1,
        settled_at=settled_at,
        settled_open_price=price,
        **fields,
    )


def _batch(path: Path, symbol: str = "2330", batch_no: int = 1, **fields: Any) -> None:
    values = {
        "symbol": symbol,
        "batch_no": batch_no,
        "status": "open",
        "shares": 100,
        "remaining_shares": 100,
        "defer_count": 0,
        "missed_count": 0,
        "updated_at": "2026-08-12T00:00:00+00:00",
        **fields,
    }
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            f"INSERT INTO playbook_batches ({columns}) VALUES ({marks})", tuple(values.values())
        )


def _state(path: Path, **pairs: str) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO playbook_state (key, value) VALUES (?, ?)", list(pairs.items())
        )


def _bar(path: Path, symbol: str, day: str, market: str = "TW") -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "INSERT INTO price_bars_cache (symbol, market, trade_date, open, high, low, close, "
            "volume, currency, source, as_of, fetched_at) VALUES "
            "(?, ?, ?, '1', '1', '1', '1', 1, 'TWD', 'f', '2026-01-01T00:00:00+00:00', "
            "'2026-11-01T00:00:00+00:00')",
            (symbol, market, day),
        )


def _snapshot(path: Path) -> Any:
    with closing(probe.open_read_only(path)) as conn:
        return probe.load(conn, as_of=AS_OF)


def _classified(path: Path) -> Any:
    return probe.classify(_snapshot(path))


def _run(path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    assert probe.main(["--db-path", str(path)], now_utc=RUN_AT, today=AS_OF) == 0
    return capsys.readouterr().out


def _three_executed_r1(path: Path, **overrides: Any) -> list[int]:
    return [_executed(path, f"2026-08-11T10:0{i}:00+00:00", **overrides) for i in range(3)]


# ---------------------------------------------------------------- D-A


def test_d_a_estimate_matches_the_cash_the_production_path_actually_deducted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """record_directives twice (two /today calls), then settle every row as /today does."""
    path = _db(tmp_path)
    store = PlaybookStore(db_path=path)
    store.ensure_batches(["2330"], batches_per_target=3)
    store.set_capital(
        cash=Decimal("1000000"),
        total_deploy=Decimal("700000"),
        source="user_confirmation",
        at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    directive = Directive(
        symbol="2330",
        batch_no=1,
        action="buy",
        shares=100,
        rule_id="R1",
        rule_summary="R1 排程日進場",
        data_date=helper.TUESDAY,
        execution_date=helper.WEDNESDAY,
        reference_price=Decimal("600"),
        limit_low=Decimal("588"),
        limit_high=Decimal("612"),
        limit_note="限價帶",
        data_status="fresh",
        source="twse",
    )
    evaluation = PlaybookEvaluation(
        data_date=helper.TUESDAY,
        execution_date=helper.WEDNESDAY,
        mode="normal",
        mode_reason="正常模式",
        is_schedule_day=True,
        fast_market=FastMarketState(
            active=False, annualized_vol_20d=None, large_move_days=0, reason=None
        ),
        rules_version=1,
        params=helper.params(),
        directives=[directive],
        effects=[],
        warnings=[],
        snapshot=[],
    )
    store.record_directives(evaluation)
    store.record_directives(evaluation)
    opening = Decimal("605")
    for pending in store.pending_directives():
        assert store.claim_directive(pending.directive_id, status="executed", open_price=opening)
        store.settle(
            pending.directive.model_copy(update={"status": "executed"}), fill_price=opening
        )
    lost = Decimal("1000000") - store.portfolio_state().cash - opening * 100

    result = _classified(path).d_a
    assert len(result) == 1
    assert result[0].reasons == []
    assert result[0].amount == lost == Decimal("60500")
    out = _run(path, capsys)
    assert "estimated_overcharge = (2 - 1) x 100 x 605 = 60500" in out
    assert "estimated_overcharge_total(computable only)=60500" in out


def test_d_a_three_identical_executions_estimate_two_extra(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _state(path, cash="820000", total_deploy="700000", total_deploy_set_at=SET_AT_EARLY)
    _batch(path)
    ids = _three_executed_r1(path)
    out = _run(path, capsys)
    assert f"ids={','.join(map(str, ids))}" in out
    assert "estimated_overcharge = (3 - 1) x 100 x 600 = 120000" in out
    assert MANUAL not in out


def _manual_reasons(path: Path) -> list[str]:
    (result,) = _classified(path).d_a
    assert result.amount is None
    return list(result.reasons)


def test_guard_same_created_at_repeated(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path)
    _executed(path, "2026-08-11T10:00:00+00:00")
    _executed(path, "2026-08-11T10:00:00+00:00")
    assert any("same created_at repeated" in r for r in _manual_reasons(path))


def test_guard_shares_not_uniform(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path)
    _executed(path, "2026-08-11T10:00:00+00:00", shares=100)
    _executed(path, "2026-08-11T10:01:00+00:00", shares=90)
    assert any("shares not uniform" in r for r in _manual_reasons(path))


def test_guard_price_not_uniform(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path)
    _executed(path, "2026-08-11T10:00:00+00:00", price="600")
    _executed(path, "2026-08-11T10:01:00+00:00", price="601")
    assert any("settled_open_price not uniform" in r for r in _manual_reasons(path))


def test_guard_price_missing_and_unparseable(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path)
    _batch(path, batch_no=2)
    _batch(path, batch_no=3)
    _executed(path, "2026-08-11T10:00:00+00:00", price=None)
    _executed(path, "2026-08-11T10:01:00+00:00", price=None)
    _executed(path, "2026-08-11T10:00:00+00:00", price="abc", batch_no=2)
    _executed(path, "2026-08-11T10:01:00+00:00", price="abc", batch_no=2)
    _executed(path, "2026-08-11T10:00:00+00:00", price="NaN", batch_no=3)
    _executed(path, "2026-08-11T10:01:00+00:00", price="NaN", batch_no=3)
    first, second, third = _classified(path).d_a
    assert "settled_open_price missing on some row" in first.reasons
    assert any("settled_open_price unparseable" in r for r in second.reasons)
    assert any("settled_open_price unparseable" in r for r in third.reasons)
    assert first.amount is None and second.amount is None and third.amount is None


def test_guard_batch_shares_differ_or_batch_row_absent(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path, shares=200)
    _executed(path, "2026-08-11T10:00:00+00:00")
    _executed(path, "2026-08-11T10:01:00+00:00")
    _executed(path, "2026-08-11T10:00:00+00:00", symbol="2454")
    _executed(path, "2026-08-11T10:01:00+00:00", symbol="2454")
    mismatch, absent = _classified(path).d_a
    assert "batch shares 200 != row shares 100" in mismatch.reasons
    assert "no playbook_batches row for this batch" in absent.reasons


def test_guard_capital_re_entered_after_the_first_settlement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _state(
        path,
        total_deploy_set_at="2026-08-20T00:00:00+00:00",
        total_deploy_source="user_confirmation",
    )
    _batch(path)
    _executed(path, "2026-08-11T10:00:00+00:00")
    _executed(path, "2026-08-11T10:01:00+00:00")
    reasons = _manual_reasons(path)
    assert any("is later than first settled_at 2026-08-11T23:00:00+00:00" in r for r in reasons)
    assert any("total_deploy_source=user_confirmation" in r for r in reasons)
    out = _run(path, capsys)
    assert MANUAL in out
    assert "estimated_overcharge =" not in out
    assert "estimated_overcharge_total(computable only)=0" in out


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({}, "total_deploy_set_at absent"),
        ({"total_deploy_set_at": "last week"}, "total_deploy_set_at unparseable"),
        ({"total_deploy_set_at": "2026-08-01T00:00:00"}, "not comparable"),
    ],
)
def test_guard_capital_timestamp_unusable(
    tmp_path: Path, state: dict[str, str], expected: str
) -> None:
    path = _db(tmp_path)
    if state:
        _state(path, **state)
    _batch(path)
    _executed(path, "2026-08-11T10:00:00+00:00")
    _executed(path, "2026-08-11T10:01:00+00:00")
    assert any(expected in r for r in _manual_reasons(path))


def test_guard_settled_at_missing_or_mixed_awareness(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path)
    _batch(path, batch_no=2)
    _executed(path, "2026-08-11T10:00:00+00:00", settled_at=None)
    _executed(path, "2026-08-11T10:01:00+00:00")
    _executed(path, "2026-08-11T10:00:00+00:00", batch_no=2, settled_at="2026-08-12T01:00:00")
    _executed(path, "2026-08-11T10:01:00+00:00", batch_no=2)
    missing, mixed = _classified(path).d_a
    assert "settled_at missing or unparseable on some row" in missing.reasons
    assert any("not comparable" in r for r in mixed.reasons)


def test_rows_with_different_execution_dates_are_not_one_k1_group(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _executed(path, "2026-08-11T10:00:00+00:00", execution_date="2026-08-12")
    _executed(path, "2026-08-13T10:00:00+00:00", execution_date="2026-08-14")
    snapshot = _snapshot(path)
    assert snapshot.k1_groups == []
    assert [bg.dates for bg in snapshot.r1_executed_per_batch] == [2]


# ---------------------------------------------------------------- D-A' and R1 not uniform


def test_d_a_prime_counts_the_missed_count_excess(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _batch(path, status="planned", shares=0, remaining_shares=0, missed_count=3)
    for i in range(3):
        _row(
            path,
            created_at=f"2026-08-11T10:0{i}:00+00:00",
            status="missed",
            settled=1,
            settled_at="2026-08-12T05:00:00+00:00",
            settled_open_price="650",
        )
    out = _run(path, capsys)
    assert "[D-A'] symbol=2330 batch_no=1 rule=R1 action=buy execution_date=2026-08-12" in out
    assert "missed_count_excess = 3 - 1 = 2" in out
    assert "missed_count=3" in out


def test_d_a_prime_with_repeated_created_at_needs_review(tmp_path: Path) -> None:
    path = _db(tmp_path)
    for _ in range(2):
        _row(path, status="missed", settled=1, settled_at="2026-08-12T05:00:00+00:00")
    (result,) = _classified(path).d_a_prime
    assert any("same created_at repeated" in r for r in result.reasons)


def test_unsettled_r1_duplicates_are_not_d_a_and_show_up_in_d_f(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _batch(path, status="planned", shares=0, remaining_shares=0)
    first = _row(path, created_at="2026-08-11T10:00:00+00:00")
    second = _row(path, created_at="2026-08-11T10:05:00+00:00")
    classified = _classified(path)
    assert classified.d_a == []
    assert len(classified.r1_mixed) == 1
    assert classified.d_f == [
        (
            "K1 symbol=2330 batch_no=1 rule=R1 action=buy execution_date=2026-08-12",
            [first, second],
        )
    ]
    out = _run(path, capsys)
    assert f"unsettled_ids={first},{second}" in out
    assert "not all executed and not all missed (executed=0 missed=0 other=2)" in out


# ---------------------------------------------------------------- D-B


def test_d_b_cross_day_executed_buys_are_disclosed_without_an_amount(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _batch(path)
    early = _executed(path, "2026-08-11T10:00:00+00:00", execution_date="2026-08-12")
    late = _executed(path, "2026-08-13T10:00:00+00:00", execution_date="2026-08-14")
    out = _run(path, capsys)
    assert (
        f"[D-B] symbol=2330 batch_no=1 executed_r1_rows=2 distinct_execution_dates=2 "
        f"ids={early},{late}"
    ) in out
    assert "D-A: groups=0" in out
    section = out.split("== D-B")[1].split("== D-C")[0]
    assert "estimated_overcharge" not in section


def test_d_b_same_date_executions_are_left_to_d_a(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _batch(path)
    _executed(path, "2026-08-11T10:00:00+00:00")
    _executed(path, "2026-08-11T10:01:00+00:00")
    classified = _classified(path)
    assert classified.d_b == []
    assert classified.d_b_same_date_only == 1


def test_d_b_pending_buy_on_a_batch_that_already_filled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The back-filled-bar case: the 08-12 row is still pending, the 08-14 row filled."""
    path = _db(tmp_path)
    _batch(path)
    stuck = _row(path, created_at="2026-08-11T10:00:00+00:00", execution_date="2026-08-12")
    _executed(path, "2026-08-13T10:00:00+00:00", execution_date="2026-08-14")
    _row(path, created_at="2026-08-13T10:00:00+00:00", symbol="2454", execution_date="2026-08-14")
    classified = _classified(path)
    assert classified.d_b_pending == [stuck]
    out = _run(path, capsys)
    assert "[D-B-pending] symbol=2330 batch_no=1" in out
    assert f"id={stuck} created_at=2026-08-11T10:00:00+00:00 execution_date=2026-08-12" in out


# ---------------------------------------------------------------- D-C, D-D, D-E, other


def test_d_c_defer_and_skip_duplicates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _db(tmp_path)
    _batch(path, status="skipped", shares=0, remaining_shares=0, defer_count=3)
    for i in range(2):
        _row(
            path,
            created_at=f"2026-08-11T10:0{i}:00+00:00",
            action="defer",
            rule_id="R2",
            settled=1,
        )
        _row(
            path,
            created_at=f"2026-08-11T11:0{i}:00+00:00",
            action="skip",
            rule_id="R3",
            settled=1,
        )
    classified = _classified(path)
    assert [(g.rule_id, g.action, g.n) for g in classified.d_c] == [
        ("R2", "defer", 2),
        ("R3", "skip", 2),
    ]
    assert classified.d_f == []
    out = _run(path, capsys)
    assert "defer_count=3" in out


def _sells(path: Path, rule_id: str, summary: str, **fields: Any) -> list[int]:
    return [
        _executed(
            path,
            f"2026-08-11T10:0{i}:00+00:00",
            action="sell",
            rule_id=rule_id,
            rule_summary=summary,
            price="700",
            **fields,
        )
        for i in range(2)
    ]


def test_d_d_reduction_sells_and_d_e_trailing_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _batch(path, remaining_shares=34)
    _sells(path, "P1", "P1｜賣 1/3", shares=33, execution_date="2026-08-12")
    _sells(path, "P2", REDUCTION_SUMMARY, shares=33, execution_date="2026-08-14")
    _sells(path, "P3", "P3｜減 1/3", shares=11, execution_date="2026-08-19")
    _sells(path, "P2", TRAILING_SUMMARY, shares=34, execution_date="2026-08-21")
    classified = _classified(path)
    assert [(g.rule_id, g.execution_date) for g in classified.d_d] == [
        ("P1", "2026-08-12"),
        ("P2", "2026-08-14"),
        ("P3", "2026-08-19"),
    ]
    assert [(g.rule_id, g.execution_date) for g in classified.d_e] == [("P2", "2026-08-21")]
    out = _run(path, capsys)
    assert "executed_beyond_first=1" in out
    assert "(P2 trailing-exit)" in out


def test_d_e_stop_losses_s2_null_batch_and_emergency_across_dates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _sells(path, "S1", "S1｜停損", shares=100)
    _sells(path, "S2", "S2｜出清", shares=300, batch_no=None, symbol="2454")
    _executed(
        path,
        "2026-09-01T10:00:00+00:00",
        action="sell",
        rule_id="EMERGENCY",
        execution_date="2026-09-02",
    )
    pending = _row(
        path,
        created_at="2026-09-02T10:00:00+00:00",
        action="sell",
        rule_id="EMERGENCY",
        execution_date="2026-09-03",
    )
    classified = _classified(path)
    assert [(g.rule_id, g.batch_no) for g in classified.d_e] == [("S1", 1), ("S2", None)]
    (emergency,) = classified.d_e_emergency
    assert (emergency.n, emergency.unsettled, emergency.dates) == (2, 1, 2)
    assert ("EMERGENCY sell symbol=2330 batch_no=1", [pending]) in classified.d_f
    out = _run(path, capsys)
    assert "symbol=2454 batch_no=NULL rule=S2" in out
    assert (
        "[D-E EMERGENCY] symbol=2330 batch_no=1 rows=2 unsettled=1 distinct_execution_dates=2"
        in out
    )


def test_emergency_and_rebalance_are_outside_the_k1_query(tmp_path: Path) -> None:
    path = _db(tmp_path)
    for i in range(2):
        _row(path, created_at=f"2026-09-01T10:0{i}:00+00:00", rule_id="EMERGENCY", action="sell")
        _row(
            path,
            created_at=f"2026-09-01T11:0{i}:00+00:00",
            rule_id="REBALANCE",
            action="none",
            batch_no=None,
            settled=1,
        )
    assert _snapshot(path).k1_groups == []


def test_groups_without_a_category_are_printed_not_dropped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _sells(path, "P2", TRAILING_SUMMARY)
    _executed(
        path,
        "2026-08-11T10:05:00+00:00",
        action="sell",
        rule_id="P2",
        price="700",
        rule_summary=REDUCTION_SUMMARY,
    )
    for i in range(2):
        _row(
            path, created_at=f"2026-08-11T11:0{i}:00+00:00", action="none", rule_id="M1", settled=1
        )
    reasons = [why for _, why in _classified(path).other]
    # Groups come back ordered by rule_id within one execution date: M1 before P2.
    assert reasons == [
        "no category for this rule/action",
        "P2 rows mix trailing-exit and one-third reduction",
    ]
    assert "other duplicate groups: 2" in _run(path, capsys)


def test_the_p2_trailing_marker_is_the_engine_wording_of_the_trailing_exit_only() -> None:
    engine = (BACKEND / "app" / "playbook" / "engine.py").read_text(encoding="utf-8")
    hits = [line for line in engine.splitlines() if probe.P2_TRAILING_MARKER in line]
    assert len(hits) == 1
    assert 'rule_summary=_measured("P2"' in hits[0]
    assert probe.P2_TRAILING_MARKER not in REDUCTION_SUMMARY


# ---------------------------------------------------------------- D-G


def test_d_g_pending_rows_past_their_execution_date_with_bar_facts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    gap = _row(path, symbol="2330", execution_date="2026-08-12")
    _bar(path, "2330", "2026-08-11")
    _bar(path, "2330", "2026-08-13")
    _bar(path, "2330", "2026-08-14")
    has_bar = _row(path, symbol="2317", execution_date="2026-10-29", action="sell", rule_id="S1")
    _bar(path, "2317", "2026-10-29")
    nothing = _row(path, symbol="9999", execution_date="2026-10-30")
    _row(path, symbol="2454", execution_date=AS_OF.isoformat())  # due today: not past
    _executed(path, "2026-08-11T10:00:00+00:00", symbol="1101")  # settled: not listed
    _row(path, symbol="1102", action="defer", rule_id="R2", settled=1)  # no order
    snapshot = _snapshot(path)
    facts = {
        p.row.id: (p.bar_on_execution_date, p.bars_after, p.first_bar_after, p.latest_bar)
        for p in snapshot.past_pending
    }
    assert facts == {
        gap: (False, 2, "2026-08-13", "2026-08-14"),
        has_bar: (True, 0, None, "2026-10-29"),
        nothing: (False, 0, None, None),
    }
    out = _run(path, capsys)
    assert "D-G: pending_rows_past_execution_date=3" in out
    assert (
        "bar_on_execution_date=no bars_after_execution_date=2 first_bar_after=2026-08-13 "
        "latest_bar=2026-08-14"
    ) in out
    assert out.count("fact: no bar on execution_date and later bars exist") == 1


def test_d_g_without_a_price_bars_cache_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path, with_bars=False)
    _row(path, execution_date="2026-08-12")
    out = _run(path, capsys)
    assert "price_bars_cache: (table absent)" in out


def test_as_of_argument_moves_the_d_g_cutoff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _row(path, execution_date="2026-08-12")
    assert probe.main(["--db-path", str(path), "--as-of", "2026-08-12"], now_utc=RUN_AT) == 0
    assert "D-G: pending_rows_past_execution_date=0" in capsys.readouterr().out
    assert probe.main(["--db-path", str(path), "--as-of", "2026-08-13"], now_utc=RUN_AT) == 0
    assert "D-G: pending_rows_past_execution_date=1" in capsys.readouterr().out
    with pytest.raises(SystemExit) as raised:
        probe.main(["--db-path", str(path), "--as-of", "tomorrow"])
    assert raised.value.code == 2


# ---------------------------------------------------------------- header and state


def test_header_and_playbook_state_are_printed_as_stored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _state(path, cash="812345.5", total_deploy="700000", total_deploy_source="quarterly_rebalance")
    out = _run(path, capsys)
    assert "script_version: 1" in out
    assert f"script_sha256_lf: {probe.script_fingerprint()}" in out
    assert "git log -1 --format=%H -- scripts/n172_duplicate_probe.py" in out
    assert "run_at_utc: 2026-10-31T12:00:00+00:00" in out
    assert "as_of (D-G lists pending rows with execution_date < as_of): 2026-11-03" in out
    assert "cash: 812345.5" in out
    assert "total_deploy: 700000" in out
    assert "total_deploy_set_at: (absent)" in out
    assert "total_deploy_source: quarterly_rebalance" in out


def test_fingerprint_ignores_line_endings() -> None:
    text = SCRIPT_PATH.read_bytes()
    crlf = b"\r\n".join(text.splitlines()) + b"\r\n"
    assert probe.fingerprint_of(crlf) == probe.fingerprint_of(text) == probe.script_fingerprint()


def test_an_empty_book_prints_zero_counts_and_states_no_conclusion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    out = _run(path, capsys)
    assert "playbook_directives rows: 0" in out
    assert "K1 duplicate groups (EMERGENCY and REBALANCE excluded): 0" in out
    body = "\n".join(line for line in out.splitlines() if not line.startswith("db_path:"))
    for word in ("recommend", "should", "suggest", "conclusion", "refund", "repair", "fix"):
        assert word not in body.lower(), word


# ---------------------------------------------------------------- paths and errors


def test_db_path_from_the_environment_variable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    assert probe.main([], env={probe.DB_PATH_ENV_VAR: str(path)}, now_utc=RUN_AT) == 0
    assert "playbook_directives rows: 0" in capsys.readouterr().out


def test_missing_db_is_refused_and_not_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.db"
    assert probe.main(["--db-path", str(missing)], now_utc=RUN_AT, today=AS_OF) == 2
    assert "cannot read the DB" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_db_without_the_directive_table_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "other.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
    assert probe.main(["--db-path", str(path)], now_utc=RUN_AT, today=AS_OF) == 2
    assert "playbook_directives" in capsys.readouterr().err


# ---------------------------------------------------------------- read-only promise


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO playbook_state (key, value) VALUES ('cash', '1')",
        "UPDATE playbook_directives SET settled = 0",
        "DELETE FROM playbook_directives",
        "CREATE TABLE sneaky (x INTEGER)",
        "DROP TABLE playbook_directives",
    ],
)
def test_writing_through_the_probe_connection_fails(tmp_path: Path, statement: str) -> None:
    path = _db(tmp_path)
    _executed(path, "2026-08-11T10:00:00+00:00")
    with closing(probe.open_read_only(path)) as conn:
        assert conn.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute(statement)
        conn.execute("PRAGMA query_only=OFF")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute(statement)


def _all_rows(path: Path) -> list[list[tuple[object, ...]]]:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        return [
            conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in ("playbook_directives", "playbook_batches", "playbook_state")
        ]


def test_a_run_leaves_the_database_file_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path)
    _three_executed_r1(path)
    _row(path, symbol="2454", execution_date="2026-08-12")
    _bar(path, "2454", "2026-08-13")
    before_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    before_listing = {p.name for p in tmp_path.iterdir()}
    before_rows = _all_rows(path)

    _run(path, capsys)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_digest
    added = {p.name for p in tmp_path.iterdir()} - before_listing
    assert added <= {"stock-desk.db-wal", "stock-desk.db-shm"}
    assert _all_rows(path) == before_rows


def test_only_the_query_only_pragma_and_selects_are_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path)
    _three_executed_r1(path)
    _row(path, symbol="2454", execution_date="2026-08-12")
    statements: list[str] = []
    uris: list[str] = []
    real_connect = sqlite3.connect

    def traced(database: str, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        uris.append(database)
        conn: sqlite3.Connection = real_connect(database, *args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(probe.sqlite3, "connect", traced)
    _run(path, capsys)

    assert len(uris) == 1 and uris[0].endswith("?mode=ro")
    assert statements[0] == "PRAGMA query_only=ON"
    assert len(statements) > 5
    for statement in statements[1:]:
        assert statement.lstrip().upper().startswith("SELECT "), statement


def test_a_directory_name_with_space_hash_and_percent_opens_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    awkward = tmp_path / "my dir #1 %20"
    awkward.mkdir()
    path = _db(awkward)
    _executed(path, "2026-08-11T10:00:00+00:00")
    with closing(probe.open_read_only(path)) as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM playbook_directives")
    assert "playbook_directives rows: 1" in _run(path, capsys)


# ---------------------------------------------------------------- source code guard

FORBIDDEN_SQL = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "ATTACH")
#: Also refused, for the same reason: each one writes or reshapes a database.
ALSO_FORBIDDEN = ("CREATE", "REPLACE", "VACUUM", "REINDEX", "DETACH")
NETWORK_MODULES = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "subprocess"}


def test_script_source_holds_no_write_keyword() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for word in FORBIDDEN_SQL + ALSO_FORBIDDEN:
        assert not re.search(rf"\b{word}\b", source, flags=re.IGNORECASE), word


def test_script_imports_only_the_standard_library_and_never_app() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            assert node.module is not None
            modules.add(node.module)
    roots = {name.split(".")[0] for name in modules}
    assert "app" not in roots
    assert not roots & NETWORK_MODULES
    assert roots <= set(sys.stdlib_module_names) | {"__future__"}
