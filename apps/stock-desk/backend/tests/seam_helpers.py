"""Scenarios for the ``/today`` seam guards (ADR-0035 補充四 S-4, SEAM-T1／T2).

Only names that already existed before the seam are imported here, so the same
scenarios can be run against the pre-seam code to record
``tests/golden/seam/pre_seam_responses.json`` (see :func:`record`). SEAM-T2
compares today's responses, minus the keys the seam adds, with that record.

Every clock is pinned: ``evaluate_today`` through :class:`ClockedService`, and
``emergency_exit`` here, so the bodies are identical run to run once the
``as_of`` timestamps are dropped.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.api.deps import get_cap1_reading, get_playbook_service
from app.api.playbook_cap1_wording import Cap1Reading
from app.main import app
from app.playbook.models import EmergencyExitResult
from tests.api_helpers import CLIENT_HEADERS
from tests.same_day_helpers import (
    WEDNESDAY,
    ClockedService,
    Desk,
    buy_line,
    hold,
    log_like_before_n172a,
    open_desk,
)

GOLDEN = Path(__file__).resolve().parent / "golden" / "seam" / "pre_seam_responses.json"


class FullyClockedService(ClockedService):
    """:class:`ClockedService` with the exit's clock pinned as well."""

    def emergency_exit(self, *, today: date | None = None) -> EmergencyExitResult:
        return super().emergency_exit(today=today or self.pinned)


def clocked_desk(db_path: Path, *, seed: bool = True) -> Desk:
    """:func:`open_desk`, served by a :class:`FullyClockedService`."""
    desk = open_desk(db_path, seed=seed)
    service = FullyClockedService(
        store=desk.store,
        market_resolver={"TW": desk.prices},
        index_resolver={"TW": desk.index, "US": desk.index},
    )
    return Desk(service=service, store=desk.store, prices=desk.prices, index=desk.index)


@contextmanager
def serving(desk: Desk) -> Iterator[TestClient]:
    app.dependency_overrides[get_playbook_service] = lambda: desk.service
    app.dependency_overrides[get_cap1_reading] = lambda: Cap1Reading(
        weight=Decimal("0.10"), from_default=False
    )
    try:
        with TestClient(app, headers=CLIENT_HEADERS) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def without(value: Any, keys: frozenset[str]) -> Any:
    """``value`` with every ``keys`` entry dropped, at any depth."""
    if isinstance(value, dict):
        return {key: without(item, keys) for key, item in value.items() if key not in keys}
    if isinstance(value, list):
        return [without(item, keys) for item in value]
    return value


#: Wall-clock fields; never part of a comparison.
CLOCK_KEYS = frozenset({"as_of"})


def authored(db_path: Path) -> dict[str, Any]:
    """An R1 schedule day, refreshed once: the ledger, a settlement, the exit confirm."""
    desk = clocked_desk(db_path)
    with serving(desk) as client:
        first = client.get("/api/playbook/today").json()
        second = client.get("/api/playbook/today").json()
    return {"today": first, "today_again": second}


def after_exit(db_path: Path) -> dict[str, Any]:
    """Two held batches, an R1 buy in flight, an exit, a repeat, and the next day's page."""
    desk = clocked_desk(db_path)
    hold(desk.store, "2330", 2)
    hold(desk.store, "2330", 3)
    log_like_before_n172a(desk.store, [buy_line(execution_date=WEDNESDAY)])
    with serving(desk) as client:
        exit_body = client.post("/api/playbook/emergency-exit").json()
        repeat = client.post("/api/playbook/emergency-exit").json()
        today = client.get("/api/playbook/today").json()
        desk.service.pinned = WEDNESDAY
        next_day = client.get("/api/playbook/today").json()
    return {"exit": exit_body, "exit_repeat": repeat, "today": today, "today_next_day": next_day}


def unauthored(db_path: Path) -> dict[str, Any]:
    """No rule set confirmed; one held batch, so the 情境 1 holding sentence shows."""
    desk = clocked_desk(db_path, seed=False)
    desk.store.ensure_batches(["2330"], batches_per_target=3)
    hold(desk.store, "2330", 1)
    with serving(desk) as client:
        today = client.get("/api/playbook/today").json()
        exit_body = client.post("/api/playbook/emergency-exit").json()
        after = client.get("/api/playbook/today").json()
    return {"today": today, "exit": exit_body, "today_after_exit": after}


SCENARIOS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "authored": authored,
    "after_exit": after_exit,
    "unauthored": unauthored,
}


def record(work_dir: Path) -> dict[str, Any]:
    """Every scenario's bodies, ``as_of`` dropped, one database each under ``work_dir``."""
    return {
        name: without(run(work_dir / f"{name}.db"), CLOCK_KEYS) for name, run in SCENARIOS.items()
    }


if __name__ == "__main__":  # pragma: no cover - run by hand against the pre-seam code
    out = Path(sys.argv[1])
    out.write_text(
        json.dumps(record(Path(sys.argv[2])), ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
