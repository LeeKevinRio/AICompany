"""``classify_exit_batches``: the one 判準 Z split, extracted from the exit (ADR-0039 T16).

ADR-0039 Decision 3 / N171-C2″: ``/today``'s pending-exit block and
:func:`plan_emergency_exit` classify EMERGENCY sells through the same pure
function, and the exit's behaviour does not move. The existing exit tests
(``test_playbook_exit_*``) keep their assertions unchanged; this file adds the
equivalence check against the inline loop the exit ran before the extraction,
over a seeded sweep of books, plus the structural guards that keep it the only
place 判準 Z is applied to a batch.
"""

from __future__ import annotations

import ast
import random
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.data.interface import PriceBar
from app.playbook import service as service_module
from app.playbook.models import BatchState, Directive
from app.playbook.service import (
    NOTHING_LOADED,
    ExitBatchClass,
    LoadedSeries,
    classify_exit_batches,
    exit_line_still_covers,
    plan_emergency_exit,
)
from app.playbook.store import EmergencyExitState, PendingDirective, PlaybookStore
from tests.api_helpers import recent_bars

DAY0 = date(2026, 8, 3)
SYMBOLS = ("1101", "2330", "2454")


def _batch(symbol: str, batch_no: int, remaining: int) -> BatchState:
    return BatchState(
        symbol=symbol,
        batch_no=batch_no,
        status="open",
        entry_date=date(2026, 7, 1),
        cost=Decimal("100"),
        shares=300,
        remaining_shares=remaining,
        peak_close=Decimal("100"),
    )


def _exit_line(symbol: str, batch_no: int | None, execution: date, shares: int) -> Directive:
    return Directive(
        symbol=symbol,
        batch_no=batch_no,
        action="sell",
        shares=shares,
        rule_id="EMERGENCY",
        rule_summary="x",
        data_date=execution - timedelta(days=1),
        execution_date=execution,
        reference_price=None,
        limit_low=None,
        limit_high=None,
        limit_note="",
        data_status="fresh",
        source="fake",
    )


def _random_book(rng: random.Random) -> tuple[EmergencyExitState, dict[str, LoadedSeries]]:
    batches = [
        _batch(symbol, batch_no, rng.choice((100, 300)))
        for symbol in SYMBOLS
        for batch_no in (1, 2, 3)
        if rng.random() < 0.6
    ]
    covering: list[PendingDirective] = []
    for directive_id in range(1, rng.randint(0, 12) + 1):
        symbol = rng.choice(SYMBOLS)
        batch_no = rng.choice((1, 2, 3, None))
        execution = DAY0 + timedelta(days=rng.randint(0, 12))
        covering.append(
            PendingDirective(directive_id, _exit_line(symbol, batch_no, execution, 300))
        )
    loaded: dict[str, LoadedSeries] = {}
    for symbol in SYMBOLS:
        if rng.random() < 0.2:
            continue  # never loaded: NOTHING_LOADED
        end = DAY0 + timedelta(days=rng.randint(0, 14))
        series = [
            bar for bar in recent_bars([100.0] * 20, symbol=symbol, end=end) if rng.random() < 0.8
        ]
        loaded[symbol] = LoadedSeries(series, "fresh", "fake")
    return EmergencyExitState(open_batches=batches, covering=covering, emergency_until=None), loaded


def _inline_reference(
    state: EmergencyExitState, loaded: Mapping[str, LoadedSeries]
) -> list[tuple[BatchState, list[int], list[date]]]:
    """The loop ``plan_emergency_exit`` ran inline before the extraction, verbatim in effect."""
    lines: dict[tuple[str, int], list[PendingDirective]] = {}
    for item in state.covering:
        if item.directive.batch_no is not None:
            lines.setdefault((item.directive.symbol, item.directive.batch_no), []).append(item)
    out: list[tuple[BatchState, list[int], list[date]]] = []
    for batch in state.open_batches:
        series = loaded.get(batch.symbol, NOTHING_LOADED)
        live: list[int] = []
        stale_dates: list[date] = []
        for item in lines.get((batch.symbol, batch.batch_no), []):
            if exit_line_still_covers(item.directive, series.bars):
                live.append(item.directive_id)
            else:
                stale_dates.append(item.directive.execution_date)
        out.append((batch, live, stale_dates))
    return out


def _series_for(loaded: Mapping[str, LoadedSeries]) -> Callable[[str], Sequence[PriceBar]]:
    return lambda symbol: loaded.get(symbol, NOTHING_LOADED).bars


def test_classification_equals_the_inline_loop_it_was_extracted_from() -> None:
    rng = random.Random(171)
    for _ in range(400):
        state, loaded = _random_book(rng)
        classes = classify_exit_batches(state, _series_for(loaded))
        expected = _inline_reference(state, loaded)
        assert [
            (
                entry.batch,
                [item.directive_id for item in entry.live],
                [item.directive.execution_date for item in entry.stale],
            )
            for entry in classes
        ] == expected


def test_one_entry_per_open_batch_and_every_batched_line_in_exactly_one_list() -> None:
    rng = random.Random(1711)
    for _ in range(200):
        state, loaded = _random_book(rng)
        classes = classify_exit_batches(state, _series_for(loaded))
        assert [entry.batch for entry in classes] == state.open_batches
        open_keys = {(batch.symbol, batch.batch_no) for batch in state.open_batches}
        placed = [item for entry in classes for item in (*entry.live, *entry.stale)]
        expected = [
            item
            for item in state.covering
            if (item.directive.symbol, item.directive.batch_no) in open_keys
        ]
        assert sorted(item.directive_id for item in placed) == sorted(
            item.directive_id for item in expected
        )
        for entry in classes:
            assert all(isinstance(entry, ExitBatchClass) for entry in classes)
            ids = [item.directive_id for item in (*entry.live, *entry.stale)]
            assert len(ids) == len(set(ids))
            # Both lists keep the oldest-first order of the read.
            assert [item.directive_id for item in entry.live] == sorted(
                item.directive_id for item in entry.live
            )
            assert [item.directive_id for item in entry.stale] == sorted(
                item.directive_id for item in entry.stale
            )


def test_the_exit_plan_is_unchanged_by_the_extraction(tmp_path: Path) -> None:
    """``plan_emergency_exit`` decides exactly what the inline loop decided."""
    rng = random.Random(17)
    params = PlaybookStore(db_path=tmp_path / "playbook.db").active_params(DAY0)
    for _ in range(200):
        state, loaded = _random_book(rng)
        plan = plan_emergency_exit(
            state,
            loaded=loaded,
            params=params,
            as_of=DAY0,
            execution_date=DAY0 + timedelta(days=1),
            computed_until=DAY0 + timedelta(days=28),
        )
        expected = _inline_reference(state, loaded)
        assert plan.covered == [batch for batch, live, _ in expected if live]
        assert [(item.symbol, item.batch_no, item.shares, item.dates) for item in plan.stale] == [
            (batch.symbol, batch.batch_no, batch.remaining_shares, tuple(dates))
            for batch, _, dates in expected
            if dates
        ]
        live_ids = {directive_id for _, live, _ in expected for directive_id in live}
        assert plan.pending == [item for item in state.covering if item.directive_id in live_ids]
        assert [(line.symbol, line.batch_no, line.shares) for line in plan.directives] == [
            (batch.symbol, batch.batch_no, batch.remaining_shares)
            for batch, live, _ in expected
            if not live
        ]


def test_exit_line_still_covers_is_called_from_classify_exit_batches_and_n1_only() -> None:
    """C2″: 判準 Z reaches a batch only through the helper; N1 keeps its own line-level use."""
    tree = ast.parse(Path(service_module.__file__).read_text(encoding="utf-8"))
    callers: list[str] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "exit_line_still_covers"
            ):
                callers.append(function.name)
    assert sorted(callers) == ["_with_stale_exit_notes", "classify_exit_batches"]
