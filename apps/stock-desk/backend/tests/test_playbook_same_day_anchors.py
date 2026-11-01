"""Locating engine sentences by re-rendering them (ADR-0035 補充一 N172-C12, N172-T22).

The engine is untouched (N172-C3), so ``same_day_warnings`` finds the sentences
it drops (鐵律① shrink notes, INDEX_DATA_GAP_DEFER_NOTE) or anchors to
(FROZEN_NOTE, DATA_GAP_NOTE／DATA_GAP_HOLDING_NOTE) by rendering the same
``wording`` template with the same values and comparing whole list elements.
Two ways that can fail silently, and what guards each here:

* **The re-rendering drifts from the engine** -- a blocked shrink note stays on
  the page (fail-open), or an anchor is not found. The round-trip tests run the
  real engine, assert it did emit the sentence, then assert the service removed
  exactly that element (the list equals the engine's minus that one sentence) or
  inserted right after it. Removal and lookup are whole-element ``==`` only, so
  either outcome proves the service's rendering ``==`` the engine's sentence.
* **An anchor goes missing** -- the disclosure must still be there:
  ENTRY_NOTE first (TA NB-1), A and B at the end (風控 必改 7).

Also 風控 2026-11-01 解讀點 (b)(c) 必改 4～6, 8(c) and C-12 (b).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_cap1_reading, get_playbook_service
from app.api.playbook_cap1_wording import Cap1Reading
from app.main import app
from app.playbook import service as service_module
from app.playbook import wording
from app.playbook.engine import evaluate
from app.playbook.models import (
    Action,
    BatchState,
    Directive,
    IndexSnapshot,
    MarketSnapshot,
    PlaybookEvaluation,
    PortfolioState,
)
from app.playbook.service import DECISION_RECORD_ACTIONS, same_day_warnings
from app.playbook.store import ORDER_ACTIONS, EvaluationCommit
from tests import playbook_helpers as helper
from tests.api_helpers import CLIENT_HEADERS
from tests.same_day_helpers import (
    ONE_BUY_SHARES,
    TUESDAY,
    WEDNESDAY,
    Desk,
    bars,
    buy_line,
    hold,
    open_desk,
)

# --- pure fixtures: the real engine, a hand-made log ----------------------------------


def _engine(
    *,
    markets: dict[str, MarketSnapshot],
    batches: list[BatchState],
    portfolio: PortfolioState | None = None,
    index: IndexSnapshot | None = None,
    index_missing: bool = False,
) -> PlaybookEvaluation:
    return evaluate(
        data_date=helper.TUESDAY,
        calendar=helper.calendar(),
        params=helper.params(),
        index=None if index_missing else (index or helper.index()),
        markets=markets,
        batches=batches,
        symbols={},
        portfolio=portfolio or helper.portfolio(),
    )


def _reconcile(
    evaluation: PlaybookEvaluation,
    logged: list[Directive],
    *,
    markets: dict[str, MarketSnapshot],
    batches: list[BatchState],
    portfolio: PortfolioState | None = None,
) -> list[str]:
    """``same_day_warnings`` for a run that wrote nothing (every decision was logged)."""
    return same_day_warnings(
        evaluation,
        EvaluationCommit(written=[], logged=logged),
        markets=markets,
        batches=batches,
        portfolio=portfolio or helper.portfolio(),
    )


def _line(symbol: str, batch_no: int | None, rule_id: str, action: str) -> Directive:
    return buy_line(symbol=symbol, batch_no=batch_no).model_copy(
        update={"rule_id": rule_id, "action": action}
    )


def _planned(symbol: str = "2330") -> list[BatchState]:
    return [helper.planned(symbol, batch_no) for batch_no in (1, 2, 3)]


def _entry_note(*lines: tuple[str, int, int]) -> str:
    return wording.SAME_DAY_EARLIER_ENTRY_NOTE.format(
        entry_count=len(lines),
        entry_items="、".join(
            wording.SAME_DAY_EARLIER_ENTRY_ITEM.format(
                symbol=symbol,
                batch_no=batch_no,
                shares=shares,
                rule_id="R1",
                execution_date=WEDNESDAY.isoformat(),
            )
            for symbol, batch_no, shares in lines
        ),
    )


def _a(symbol: str, status: str, count: int) -> str:
    return wording.SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE.format(
        symbol=symbol, status=status, line_count=count
    )


def _b(symbol: str, count: int) -> str:
    return wording.SAME_DAY_EARLIER_DECISIONS_DATA_GAP_NOTE.format(
        symbol=symbol, decision_count=count
    )


def _without(warnings: list[str], sentence: str) -> list[str]:
    return [warning for warning in warnings if warning != sentence]


_MARKET = {"2330": helper.market(close="100")}


# --- N172-T22 round trip: removed sentences (風控 必改 8 (a)(b)) ---------------------------


def test_round_trip_shrink_note() -> None:
    """The service's SHRINK_NOTE for a blocked R1 is the engine's sentence, verbatim."""
    poor = helper.portfolio(cash="50000")  # budget 35,000 -> 350 股 at 100
    evaluation = _engine(markets=_MARKET, batches=_planned(), portfolio=poor)
    engine_said = "2330：" + wording.SHRINK_NOTE.format(planned=ONE_BUY_SHARES, actual=350)
    assert engine_said in evaluation.warnings  # the engine did emit it this run

    reconciled = _reconcile(
        evaluation,
        [buy_line()],  # run 1's 666-share line, same K1
        markets=_MARKET,
        batches=_planned(),
        portfolio=poor,
    )

    assert reconciled == _without(evaluation.warnings, engine_said)


def test_round_trip_shrink_to_zero_note() -> None:
    poor = helper.portfolio(cash="100")
    evaluation = _engine(markets=_MARKET, batches=_planned(), portfolio=poor)
    engine_said = wording.SHRINK_TO_ZERO_NOTE.format(symbol="2330", batch_no=1)
    assert engine_said in evaluation.warnings
    assert evaluation.directives == []

    reconciled = _reconcile(
        evaluation, [buy_line()], markets=_MARKET, batches=_planned(), portfolio=poor
    )

    assert reconciled == [
        _entry_note(("2330", 1, ONE_BUY_SHARES)),
        *_without(evaluation.warnings, engine_said),
    ]


def test_round_trip_shrink_to_zero_of_the_batch_the_engine_chose_now() -> None:
    """風控 必改 8(c): run 1 skipped batch 1 (R3); run 2's engine picks batch 2 and
    cancels it. The sentence names batch 2 -- not the logged line's batch 1 -- and
    is removed all the same."""
    batches = [helper.batch("2330", 1, status="skipped"), *_planned()[1:]]
    poor = helper.portfolio(cash="100")
    evaluation = _engine(markets=_MARKET, batches=batches, portfolio=poor)
    engine_said = wording.SHRINK_TO_ZERO_NOTE.format(symbol="2330", batch_no=2)
    assert engine_said in evaluation.warnings

    reconciled = _reconcile(
        evaluation,
        [_line("2330", 1, "R3", "skip")],
        markets=_MARKET,
        batches=batches,
        portfolio=poor,
    )

    assert reconciled == _without(evaluation.warnings, engine_said)


def test_shrink_to_zero_of_the_chosen_batch_is_removed_end_to_end(tmp_path: Path) -> None:
    """風控 必改 8(c) through ``evaluate_today``: no 鐵律① sentence on run 2."""
    desk = open_desk(tmp_path / "playbook.db")
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    desk.store.save_batch(batch.model_copy(update={"missed_count": 3}))
    first = desk.service.evaluate_today(today=TUESDAY)
    assert [(line.rule_id, line.batch_no) for line in first.directives] == [("R3", 1)]
    desk.store.set_cash(Decimal("100"))

    second = desk.service.evaluate_today(today=TUESDAY)

    zero = wording.SHRINK_TO_ZERO_NOTE.format(symbol="2330", batch_no=2)
    assert zero not in second.warnings
    assert second.directives == first.directives


def test_round_trip_index_gap_deferral_note() -> None:
    """The constant the service drops is exactly the one the engine wrote."""
    evaluation = _engine(markets=_MARKET, batches=_planned(), index_missing=True)
    assert wording.INDEX_DATA_GAP_DEFER_NOTE in evaluation.warnings
    assert [(line.rule_id, line.action) for line in evaluation.directives] == [("M1", "defer")]

    reconciled = _reconcile(evaluation, [buy_line()], markets=_MARKET, batches=_planned())

    assert reconciled == [
        _entry_note(("2330", 1, ONE_BUY_SHARES)),
        *_without(evaluation.warnings, wording.INDEX_DATA_GAP_DEFER_NOTE),
    ]


# --- N172-T22 round trip: anchors -------------------------------------------------------

#: 2317 holds shares and has no bar (DATA_GAP_HOLDING_NOTE); 2454 is planned only and
#: its snapshot is unusable (DATA_GAP_NOTE with the snapshot's own status/source).
_GAP_MARKETS = {"2454": helper.market("2454", close="100", status="cached_stale")}
_GAP_BATCHES = [helper.batch("2317", 1), *_planned("2454")]
_HOLDING_GAP = wording.DATA_GAP_HOLDING_NOTE.format(
    symbol="2317", status="unavailable", source="none"
)
_PLAIN_GAP = wording.DATA_GAP_NOTE.format(symbol="2454", status="cached_stale", source="twse")
_GAP_LOG = [
    _line("2317", 1, "S1", "sell"),
    _line("2317", 2, "R2", "defer"),
    buy_line(symbol="2454"),
]


def test_round_trip_data_gap_anchors() -> None:
    """A then B land right after each symbol's own gap sentence, so the service found
    the engine's DATA_GAP_HOLDING_NOTE and DATA_GAP_NOTE by their exact text."""
    evaluation = _engine(markets=_GAP_MARKETS, batches=_GAP_BATCHES)
    assert evaluation.warnings.index(_HOLDING_GAP) < evaluation.warnings.index(_PLAIN_GAP)

    reconciled = _reconcile(evaluation, _GAP_LOG, markets=_GAP_MARKETS, batches=_GAP_BATCHES)

    at = reconciled.index(_HOLDING_GAP)
    assert reconciled[at : at + 4] == [
        _HOLDING_GAP,
        _a("2317", "unavailable", 1),
        _b("2317", 1),
        _PLAIN_GAP,  # inserted after, not appended: the next sentence follows
    ]
    plain = reconciled.index(_PLAIN_GAP)
    assert reconciled[plain + 1] == _a("2454", "cached_stale", 1)


def test_round_trip_frozen_note_anchor() -> None:
    """ENTRY_NOTE right after FROZEN_NOTE -- the fallback would have put it first."""
    frozen_book = helper.portfolio(freeze_until=date(2026, 8, 20), freeze_reason="S3")
    evaluation = _engine(markets=_MARKET, batches=_planned(), portfolio=frozen_book)
    frozen = wording.FROZEN_NOTE.format(mode=wording.MODE_LABELS["frozen"])
    assert evaluation.mode == "frozen" and evaluation.warnings[0] == frozen

    reconciled = _reconcile(
        evaluation, [buy_line()], markets=_MARKET, batches=_planned(), portfolio=frozen_book
    )

    assert reconciled[:2] == [frozen, _entry_note(("2330", 1, ONE_BUY_SHARES))]


# --- N172-T22 anchor missing (風控 必改 7, TA NB-1) --------------------------------------


def test_entry_note_comes_first_when_frozen_note_is_missing() -> None:
    frozen_book = helper.portfolio(freeze_until=date(2026, 8, 20), freeze_reason="S3")
    evaluation = _engine(markets=_MARKET, batches=_planned(), portfolio=frozen_book)
    frozen = wording.FROZEN_NOTE.format(mode=wording.MODE_LABELS["frozen"])
    stripped = evaluation.model_copy(update={"warnings": _without(evaluation.warnings, frozen)})

    reconciled = _reconcile(
        stripped, [buy_line()], markets=_MARKET, batches=_planned(), portfolio=frozen_book
    )

    assert reconciled[0] == _entry_note(("2330", 1, ONE_BUY_SHARES))


def test_a_and_b_go_to_the_end_when_the_holding_gap_note_is_missing() -> None:
    evaluation = _engine(markets=_GAP_MARKETS, batches=_GAP_BATCHES)
    stripped = evaluation.model_copy(
        update={"warnings": _without(evaluation.warnings, _HOLDING_GAP)}
    )

    reconciled = _reconcile(stripped, _GAP_LOG, markets=_GAP_MARKETS, batches=_GAP_BATCHES)

    assert reconciled[-2:] == [_a("2317", "unavailable", 1), _b("2317", 1)]


def test_a_goes_to_the_end_when_the_plain_gap_note_is_missing() -> None:
    evaluation = _engine(markets=_GAP_MARKETS, batches=_GAP_BATCHES)
    stripped = evaluation.model_copy(update={"warnings": _without(evaluation.warnings, _PLAIN_GAP)})

    reconciled = _reconcile(stripped, _GAP_LOG, markets=_GAP_MARKETS, batches=_GAP_BATCHES)

    assert reconciled[-1] == _a("2454", "cached_stale", 1)


def test_b_alone_goes_to_the_end_when_its_gap_note_is_missing() -> None:
    evaluation = _engine(markets=_GAP_MARKETS, batches=_GAP_BATCHES)
    stripped = evaluation.model_copy(
        update={"warnings": _without(evaluation.warnings, _HOLDING_GAP)}
    )
    only_decision = [_line("2317", 2, "R2", "defer")]

    reconciled = _reconcile(stripped, only_decision, markets=_GAP_MARKETS, batches=_GAP_BATCHES)

    assert reconciled[-1] == _b("2317", 1)
    assert not [warning for warning in reconciled if warning.startswith("2317 本次資料狀態")]


# --- 風控 必改 4: every Action belongs to exactly one class --------------------------------

#: A = 買賣 (SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE), B = 順延／跳過
#: (SAME_DAY_EARLIER_DECISIONS_DATA_GAP_NOTE), or not on the list at all. A new action
#: makes this test fail until it is placed here and in the code.
_ACTION_CLASS: dict[str, str] = {
    "buy": "A",
    "sell": "A",
    "defer": "B",
    "skip": "B",
    "none": "not listed",  # REBALANCE only, which the list excludes (UNKEYED_RULE_IDS)
}


def test_every_action_is_classified_once() -> None:
    assert set(_ACTION_CLASS) == set(get_args(Action))
    assert set(ORDER_ACTIONS) == {action for action, kind in _ACTION_CLASS.items() if kind == "A"}
    assert set(DECISION_RECORD_ACTIONS) == {
        action for action, kind in _ACTION_CLASS.items() if kind == "B"
    }
    assert not set(ORDER_ACTIONS) & set(DECISION_RECORD_ACTIONS)


# --- 風控 必改 5: (c) on the service path -----------------------------------------------


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    """2330 under test; 2454 keeps the 依據資料日 on Tuesday when 2330 has no data."""
    return open_desk(tmp_path / "playbook.db", symbols=("2330", "2454"))


def _gap_warnings(desk: Desk, symbol: str = "2330") -> tuple[list[str], str]:
    """Run 2 with no ``symbol`` data: its warnings and the gap sentence there."""
    held = any(
        batch.symbol == symbol and batch.status == "open" for batch in desk.store.list_batches()
    )
    desk.prices.seed(symbol, [])
    second = desk.service.evaluate_today(today=TUESDAY)
    gap = (wording.DATA_GAP_HOLDING_NOTE if held else wording.DATA_GAP_NOTE).format(
        symbol=symbol, status="unavailable", source="none"
    )
    return second.warnings, gap


def _after(warnings: list[str], gap: str, count: int) -> list[str]:
    at = warnings.index(gap)
    return warnings[at + 1 : at + 1 + count]


def _gap_notes(warnings: list[str], symbol: str) -> list[str]:
    head_a = f"{symbol} 本次資料狀態"
    head_b = f"指令帳冊中 {symbol} 的"
    return [warning for warning in warnings if warning.startswith((head_a, head_b))]


def test_c_a_an_r2_deferral_alone_gets_b_only(desk: Desk) -> None:
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))
    desk.service.evaluate_today(today=TUESDAY)
    warnings, gap = _gap_warnings(desk)

    assert _after(warnings, gap, 1) == [_b("2330", 1)]
    assert _gap_notes(warnings, "2330") == [_b("2330", 1)]


def test_c_b_an_r3_skip_alone_gets_b_only(desk: Desk) -> None:
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    desk.store.save_batch(batch.model_copy(update={"missed_count": 3}))
    desk.service.evaluate_today(today=TUESDAY)
    warnings, gap = _gap_warnings(desk)

    assert _gap_notes(warnings, "2330") == [_b("2330", 1)]
    assert _after(warnings, gap, 1) == [_b("2330", 1)]


def test_c_c_an_index_gap_deferral_then_a_symbol_gap_gets_b_only(desk: Desk) -> None:
    desk.index.seed("^TWII", [])
    first = desk.service.evaluate_today(today=TUESDAY)
    assert ("2330", "M1", "defer") in {(d.symbol, d.rule_id, d.action) for d in first.directives}
    warnings, gap = _gap_warnings(desk)

    assert _gap_notes(warnings, "2330") == [_b("2330", 1)]
    assert _after(warnings, gap, 1) == [_b("2330", 1)]


def test_c_d_a_sell_and_a_deferral_get_a_then_b(desk: Desk) -> None:
    """P1 on batch 1 (cost 80) and R2 on batch 2 (+10%): A=1, B=1, right after the gap."""
    hold(desk.store, "2330", 1, shares=300, cost="80")
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))
    first = desk.service.evaluate_today(today=TUESDAY)
    assert {
        (line.rule_id, line.batch_no) for line in first.directives if line.symbol == "2330"
    } == {
        ("P1", 1),
        ("R2", 2),
    }
    warnings, gap = _gap_warnings(desk)

    assert _after(warnings, gap, 2) == [_a("2330", "unavailable", 1), _b("2330", 1)]
    assert _gap_notes(warnings, "2330") == [_a("2330", "unavailable", 1), _b("2330", 1)]


def test_c_e_a_sell_alone_gets_a_only(desk: Desk) -> None:
    hold(desk.store, "2454", 1, shares=300, cost="100")
    desk.prices.seed("2454", bars("2454", 100.0, {TUESDAY: 85.0}))  # S1
    desk.service.evaluate_today(today=TUESDAY)
    warnings, gap = _gap_warnings(desk, "2454")

    assert _gap_notes(warnings, "2454") == [_a("2454", "unavailable", 1)]
    assert _after(warnings, gap, 1) == [_a("2454", "unavailable", 1)]


# --- 風控 必改 6: (b) INDEX_DATA_GAP_DEFER_NOTE stays tied to an M1 deferral -------------


@pytest.fixture
def client(desk: Desk) -> Iterator[TestClient]:
    app.dependency_overrides[get_playbook_service] = lambda: desk.service
    app.dependency_overrides[get_cap1_reading] = lambda: Cap1Reading(
        weight=Decimal("0.10"), from_default=False
    )
    with TestClient(app, headers=CLIENT_HEADERS) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _deferred_twice(desk: Desk, symbol: str) -> None:
    batch = desk.store.get_batch(symbol, 1)
    assert batch is not None
    desk.store.save_batch(batch.model_copy(update={"defer_count": 2}))


def test_b_a_an_r3_skip_writing_day_and_its_refresh(desk: Desk, client: TestClient) -> None:
    """Only R3 skips are written on the index-gap day: no DEFER_NOTE, the gap note
    stays, the R3 lines are listed -- and the second ``/today`` says the same."""
    for symbol in ("2330", "2454"):
        _deferred_twice(desk, symbol)
    desk.index.seed("^TWII", [])
    first = client.get("/api/playbook/today").json()
    second = client.get("/api/playbook/today").json()

    assert wording.INDEX_DATA_GAP_DEFER_NOTE not in first["warnings"]
    assert (
        wording.INDEX_DATA_GAP_NOTE.format(status="unavailable", source="none")
        in (first["warnings"])
    )
    assert {
        (item["directive"]["rule_id"], item["directive"]["action"]) for item in first["directives"]
    } == {("R3", "skip")}
    assert second["warnings"] == first["warnings"]


@pytest.mark.parametrize("defer_count", [0, 2], ids=["r2-defer", "r2-r3-skip"])
def test_b_b_an_r2_decision_then_an_index_gap_has_no_deferral_note(
    desk: Desk, defer_count: int
) -> None:
    for symbol in ("2330", "2454"):
        desk.prices.seed(symbol, bars(symbol, 100.0, {TUESDAY: 110.0}))
        batch = desk.store.get_batch(symbol, 1)
        assert batch is not None
        desk.store.save_batch(batch.model_copy(update={"defer_count": defer_count}))
    first = desk.service.evaluate_today(today=TUESDAY)
    assert {line.rule_id for line in first.directives} == ({"R2"} if defer_count == 0 else {"R3"})
    desk.index.seed("^TWII", [])

    second = desk.service.evaluate_today(today=TUESDAY)

    assert wording.INDEX_DATA_GAP_DEFER_NOTE not in second.warnings
    assert wording.INDEX_DATA_GAP_NOTE.format(status="unavailable", source="none") in (
        second.warnings
    )


def test_b_c_an_m1_deferral_next_to_an_r3_skip_keeps_the_deferral_note(desk: Desk) -> None:
    _deferred_twice(desk, "2454")
    desk.index.seed("^TWII", [])

    evaluation = desk.service.evaluate_today(today=TUESDAY)

    assert {(line.symbol, line.rule_id) for line in evaluation.directives} == {
        ("2330", "M1"),
        ("2454", "R3"),
    }
    assert wording.INDEX_DATA_GAP_DEFER_NOTE in evaluation.warnings


# --- N172-C12 (b): the values are re-rendered from the snapshot the engine ran on ---------


def test_the_reconciliation_reads_the_snapshot_handed_to_the_engine(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same ``batches``／``portfolio``／``markets`` objects as ``evaluate()`` got --
    nothing re-read after the commit."""
    seen: dict[str, Any] = {}
    real_evaluate = evaluate  # what the service imported from the engine
    real_reconcile = service_module.same_day_warnings

    def spy_evaluate(**kwargs: Any) -> PlaybookEvaluation:
        seen["engine"] = kwargs
        return real_evaluate(**kwargs)

    def spy_reconcile(evaluation: PlaybookEvaluation, commit: Any, **kwargs: Any) -> list[str]:
        seen["service"] = kwargs
        seen["params"] = evaluation.params
        return real_reconcile(evaluation, commit, **kwargs)

    monkeypatch.setattr(service_module, "evaluate", spy_evaluate)
    monkeypatch.setattr(service_module, "same_day_warnings", spy_reconcile)
    desk.service.evaluate_today(today=TUESDAY)

    for name in ("batches", "portfolio", "markets"):
        assert seen["service"][name] is seen["engine"][name], name
    assert seen["params"] is seen["engine"]["params"]
