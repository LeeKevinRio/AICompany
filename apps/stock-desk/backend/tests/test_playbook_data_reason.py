"""The data layer's own sentence travels into the playbook's output (風控 2026-09-15).

R3: every directive persists the ``reason`` of the series it was decided on, so
the ledger can show it later. R1-b: the index series' reason is shown with the
evaluation it fed, verbatim, as a warning line.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.playbook import wording
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import TUESDAY, confirm_rule_set

SERIES_END = date(2026, 8, 14)
HISTORY = 40
SPLICED = "這段日線資料由多個來源拼接（finmind、twse），每筆保留原本的來源；..."
CACHED = "最近一次向來源取得資料未成功，暫以本機快取回覆。"


@dataclass
class Harness:
    service: PlaybookService
    store: PlaybookStore


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    confirm_rule_set(store)
    prices = FakePriceService(reason=SPLICED)
    prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=SERIES_END))
    index = FakePriceService(reason=CACHED)
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    store.ensure_batches(["2330"], batches_per_target=3)
    store.set_capital(cash=Decimal("1000000"), total_deploy=Decimal("1000000"), source="initial")
    yield Harness(
        service=PlaybookService(
            store=store,
            market_resolver={"TW": prices},
            index_resolver={"TW": index, "US": index},
        ),
        store=store,
    )


def test_every_directive_persists_the_reason_of_its_series(harness: Harness) -> None:
    evaluation = harness.service.evaluate_today(today=TUESDAY)
    assert evaluation.directives, "a schedule day with confirmed rules produces a line"
    assert all(line.data_reason == SPLICED for line in evaluation.directives)
    assert all(row["data_reason"] == SPLICED for row in harness.store.directive_log())


def test_the_index_series_reason_is_shown_with_the_evaluation(harness: Harness) -> None:
    evaluation = harness.service.evaluate_today(today=TUESDAY)
    note = wording.index_data_reason_note(CACHED)
    assert note in evaluation.warnings
    # The quoted sentence's own full stop moves after the clause (風控 suggested a).
    assert note.endswith("（用於 M1 與快市判定）。") and "。（" not in note


def test_an_index_that_returned_nothing_still_has_its_reason_shown(tmp_path: Path) -> None:
    """風控 R4-a: with no index bar at all the snapshot is None, yet the loader's
    sentence (which source reported what) must still reach the page."""
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    confirm_rule_set(store)
    prices = FakePriceService()
    prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=SERIES_END))
    index = FakePriceService(reason=CACHED)  # nothing seeded: no bars come back
    store.ensure_batches(["2330"], batches_per_target=3)
    service = PlaybookService(
        store=store, market_resolver={"TW": prices}, index_resolver={"TW": index, "US": index}
    )
    evaluation = service.evaluate_today(today=TUESDAY)
    notes = [w for w in evaluation.warnings if w.startswith("加權指數資料：")]
    assert len(notes) == 1 and CACHED.rstrip("。") in notes[0]
