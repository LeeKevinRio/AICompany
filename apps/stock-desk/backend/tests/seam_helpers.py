"""Scenarios for the ``/today`` seam guards (ADR-0035 補充四 S-4, SEAM-T1／T2).

Only names that already existed before the seam are imported here, so the same
scenarios can be run against the pre-seam code to record
``tests/golden/seam/pre_seam_responses.json`` (see :func:`record`). SEAM-T2
compares today's responses, minus the keys the seam adds, with that record.

Every clock is pinned: ``evaluate_today`` through :class:`ClockedService`, and
``emergency_exit`` here, so the bodies are identical run to run once the
``as_of`` timestamps are dropped.

The golden is frozen byte for byte at ``5c2d3e1`` (ADR-0035 補充四釐清二 E-5,
:data:`GOLDEN_SHA256`). A legitimate difference after the seam is registered in
``tests/golden/seam/approved/<owner>.json`` (E-6) and read by
:func:`load_registrations`; SEAM-T2 compares each body with the golden *after*
:func:`expected_bodies` applied the registered deltas, with the clock keys, the
seam's keys and every registered ``added_keys`` dropped (:func:`dropped_keys`).
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
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

#: sha256 of ``git show 5c2d3e1:apps/stock-desk/backend/tests/golden/seam/pre_seam_responses.json``
#: (釐清二 E-5 第 2 點). Written once by the mechanism commit; never edited.
GOLDEN_SHA256 = "3e2d4bfe01321a8b6936b37056d9cb2f4c69db86a29a8146fba127de012abf7c"

#: 釐清二 E-6 第 1 點: one registration file per owner.
APPROVED = GOLDEN.parent / "approved"

#: The four keys the seam itself added (ADR-0035 補充四 2.2), always dropped.
SEAM_LIST_KEYS = (
    "pending_exit_directives",
    "entry_before_exit_directives",
    "entry_before_exit_blocked_directives",
)
SEAM_NOTE_KEY = "entry_before_exit_note"
SEAM_KEYS = frozenset({*SEAM_LIST_KEYS, SEAM_NOTE_KEY})


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


def golden_sha256() -> str:
    return hashlib.sha256(GOLDEN.read_bytes()).hexdigest()


# --- 釐清二 E-6: the approved-difference registry ---------------------------------------

#: E-6 第 2 點: what a ``filled`` entry may name, per kind.
FILLED_NAMES: dict[str, frozenset[str]] = {
    "today_lists": frozenset(SEAM_LIST_KEYS),
    "note": frozenset({SEAM_NOTE_KEY}),
    "in_flight": frozenset({"exits", "entries"}),
}
DELTA_OPS = frozenset({"replace", "insert", "remove"})
_REGISTRATION_KEYS = frozenset({"owner", "added_keys", "filled", "deltas"})
_DELTA_KEYS = frozenset({"id", "source", "approval", "scenario", "body", "path", "op"})
#: Characters that would make a path element a pattern rather than a key (E-6 第 4 點).
_PATTERN_CHARACTERS = frozenset("*?[]{}()|^$\\")


class RegistryError(AssertionError):
    """A registration file breaks 釐清二 E-6; SEAM-T2 fails on it."""


@dataclass(frozen=True)
class Registration:
    """One ``approved/<owner>.json`` file, validated (E-6 第 2 點)."""

    file: str
    owner: str
    added_keys: tuple[str, ...]
    #: ``(kind, name)`` pairs, e.g. ``("today_lists", "pending_exit_directives")``.
    filled: tuple[tuple[str, str], ...]
    #: ``(kind, name, test node id)`` for each ``filled`` entry.
    filled_tests: tuple[tuple[str, str, str], ...]
    deltas: tuple[dict[str, Any], ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def parse_registration(file: str, raw: Any) -> Registration:
    """Validate one file's content; raises :class:`RegistryError` on any breach."""
    _require(isinstance(raw, dict), f"{file}: not an object")
    _require(set(raw) == _REGISTRATION_KEYS, f"{file}: keys must be {sorted(_REGISTRATION_KEYS)}")
    owner = raw["owner"]
    _require(isinstance(owner, str) and owner != "", f"{file}: owner")
    _require(file == f"{owner}.json", f"{file}: one file per owner, named <owner>.json")

    added: list[str] = []
    for item in raw["added_keys"]:
        _require(
            isinstance(item, dict) and set(item) == {"key", "source"}, f"{file}: added_keys item"
        )
        _require(isinstance(item["source"], str) and item["source"] != "", f"{file}: source")
        key = item["key"]
        _require(isinstance(key, str) and key != "", f"{file}: added key")
        _require(not set(key) & _PATTERN_CHARACTERS, f"{file}: pattern in added key {key!r}")
        added.append(key)

    filled: list[tuple[str, str]] = []
    filled_tests: list[tuple[str, str, str]] = []
    for item in raw["filled"]:
        _require(
            isinstance(item, dict) and set(item) == {"kind", "name", "source", "test"},
            f"{file}: filled item",
        )
        kind, name = item["kind"], item["name"]
        _require(kind in FILLED_NAMES, f"{file}: filled kind {kind!r}")
        _require(name in FILLED_NAMES[kind], f"{file}: filled name {name!r} for {kind}")
        _require(isinstance(item["source"], str) and item["source"] != "", f"{file}: source")
        test = item["test"]
        _require(isinstance(test, str) and "::" in test, f"{file}: test node id")
        filled.append((kind, name))
        filled_tests.append((kind, name, test))

    deltas: list[dict[str, Any]] = []
    for item in raw["deltas"]:
        _require(isinstance(item, dict), f"{file}: delta")
        op = item.get("op")
        _require(op in DELTA_OPS, f"{file}: op {op!r}")
        required = set(_DELTA_KEYS)
        if op in ("replace", "remove"):
            required.add("before")
        if op in ("replace", "insert"):
            required.add("after")
        _require(set(item) == required, f"{file}: delta {item.get('id')!r} keys")
        for key in ("id", "source", "approval", "scenario", "body"):
            _require(isinstance(item[key], str) and item[key] != "", f"{file}: delta {key}")
        path = item["path"]
        _require(isinstance(path, list) and path != [], f"{file}: delta path")
        for step in path:
            _require(
                (isinstance(step, int) and not isinstance(step, bool))
                or (isinstance(step, str) and step != "" and not set(step) & _PATTERN_CHARACTERS),
                f"{file}: path element {step!r}",
            )
        if op == "replace":
            _require(item["after"] != item["before"], f"{file}: empty delta {item['id']}")
            _require(
                not isinstance(item["before"], list), f"{file}: whole-list replace {item['id']}"
            )
        deltas.append(item)
    return Registration(
        file=file,
        owner=owner,
        added_keys=tuple(added),
        filled=tuple(filled),
        filled_tests=tuple(filled_tests),
        deltas=tuple(deltas),
    )


def load_registrations(directory: Path = APPROVED) -> list[Registration]:
    """Every registration file, in file-name order (E-6 第 3 點 2))."""
    files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    registrations = [
        parse_registration(path.name, json.loads(path.read_text(encoding="utf-8")))
        for path in files
    ]
    ids = [delta["id"] for registration in registrations for delta in registration.deltas]
    _require(len(ids) == len(set(ids)), f"duplicate delta id among {ids}")
    return registrations


def _keys_at_any_depth(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys_at_any_depth(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys_at_any_depth(item)}
    return set()


def dropped_keys(registrations: Sequence[Registration], golden: Any) -> frozenset[str]:
    """Clock keys ∪ the seam's four ∪ every ``added_keys`` (E-6 第 3 點 3))."""
    added = {key for registration in registrations for key in registration.added_keys}
    collisions = added & (_keys_at_any_depth(golden) | CLOCK_KEYS | SEAM_KEYS)
    _require(not collisions, f"added_keys already in the golden: {sorted(collisions)}")
    return CLOCK_KEYS | SEAM_KEYS | frozenset(added)


def filled(registrations: Sequence[Registration], kind: str) -> frozenset[str]:
    """The names of ``kind`` some owner registered as filled (E-6 第 6 點)."""
    return frozenset(
        name
        for registration in registrations
        for filled_kind, name in registration.filled
        if filled_kind == kind
    )


def _parent(document: Any, path: Sequence[Any], where: str) -> Any:
    node = document
    for step in path[:-1]:
        if isinstance(node, dict):
            _require(isinstance(step, str) and step in node, f"{where}: no key {step!r}")
        else:
            _require(
                isinstance(node, list) and isinstance(step, int) and 0 <= step < len(node),
                f"{where}: no index {step!r}",
            )
        node = node[step]
    return node


def expected_bodies(golden: Any, registrations: Sequence[Registration]) -> Any:
    """The golden with every registered delta applied, file then in-file order (E-6 第 3 點 4))."""
    expected = copy.deepcopy(golden)
    touched: dict[tuple[Any, ...], str] = {}
    for registration in registrations:
        for delta in registration.deltas:
            where = f"{registration.file}:{delta['id']}"
            _require(delta["scenario"] in expected, f"{where}: scenario")
            _require(delta["body"] in expected[delta["scenario"]], f"{where}: body")
            document = expected[delta["scenario"]][delta["body"]]
            parent = _parent(document, delta["path"], where)
            # Two owners may not land on one list or one leaf (E-6 第 4 點).
            full = (delta["scenario"], delta["body"], *delta["path"])
            shared = [full, full[:-1]] if isinstance(parent, list) else [full]
            for key in shared:
                other = touched.get(key)
                _require(
                    other is None or other == registration.owner,
                    f"{where}: shares {key} with {other}",
                )
                touched[key] = registration.owner
            last = delta["path"][-1]
            op = delta["op"]
            if last == "message":
                _require(op == "replace", f"{where}: message may only be replaced")
                _require(
                    isinstance(delta["after"], str) and delta["after"].startswith(delta["before"]),
                    f"{where}: a message may only be appended to (C-B5)",
                )
            if op == "insert":
                _require(
                    isinstance(parent, list) and isinstance(last, int) and 0 <= last <= len(parent),
                    f"{where}: insert index",
                )
                parent.insert(last, delta["after"])
                continue
            if isinstance(parent, dict):
                _require(isinstance(last, str) and last in parent, f"{where}: no key {last!r}")
            else:
                _require(
                    isinstance(parent, list) and isinstance(last, int) and 0 <= last < len(parent),
                    f"{where}: no index {last!r}",
                )
            _require(parent[last] == delta["before"], f"{where}: before does not match")
            if op == "replace":
                parent[last] = delta["after"]
            else:
                del parent[last]
    return expected


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
