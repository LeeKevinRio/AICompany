"""Store tests for the narrow ``PATCH`` write and the hard delete (庫存頁).

Covers tech-architect C2 (``patch_fields`` is one UPDATE over the sent columns,
never a read-then-write-back) and C6 (deleting a holding leaves every other
table alone). Every database lives under ``tmp_path``.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.alerts.models import AlertRuleInput
from app.alerts.store import AlertStore
from app.kelly.models import KellyInputRecord
from app.kelly.store import KellyInputStore
from app.playbook.store import PlaybookStore
from app.positions.models import Position, PositionInput
from app.positions.store import PositionStore
from tests.alerts_helpers import price_rule

T0 = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
T2 = T0 + timedelta(hours=2)


@pytest.fixture
def store(tmp_path: Path) -> PositionStore:
    return PositionStore(db_path=tmp_path / "positions.db")


def _create(
    store: PositionStore, *, note: str | None = "台積電", sector: str | None = None
) -> Position:
    return store.create(
        PositionInput(
            symbol="2330",
            market="TW",
            quantity=Decimal("1000"),
            avg_cost=Decimal("600.5"),
            currency="TWD",
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            sector=sector,
            note=note,
        ),
        now=T0,
    )


def test_patch_quantity_changes_only_quantity_and_advances_updated_at(
    store: PositionStore,
) -> None:
    before = _create(store, sector="半導體業")

    after = store.patch_fields(before.id, {"quantity": Decimal("1500")}, now=T1)

    assert after is not None
    assert after.quantity == Decimal("1500")
    assert after.updated_at == T1
    assert after.created_at == before.created_at == T0
    untouched = {"quantity", "updated_at"}
    assert after.model_dump(exclude=untouched) == before.model_dump(exclude=untouched)


def test_patch_after_a_sector_backfill_keeps_the_backfilled_sector(store: PositionStore) -> None:
    """The race PUT loses (PRD §4 item 1): the page read before the backfill wrote."""
    created = _create(store, sector=None)
    stale_snapshot = store.list_all()  # what the inventory page rendered
    assert stale_snapshot[0].sector is None

    assert store.fill_sector_if_empty(created.id, "半導體業", now=T1) is not None
    after = store.patch_fields(stale_snapshot[0].id, {"quantity": Decimal("2000")}, now=T2)

    assert after is not None
    assert after.quantity == Decimal("2000")
    assert after.sector == "半導體業"


@pytest.mark.parametrize(
    ("changes", "expected_note"),
    [
        ({"avg_cost": Decimal("610")}, "台積電"),  # note omitted: unchanged
        ({"note": None}, None),  # explicit null: cleared
        ({"note": "   "}, None),  # blank: cleared
    ],
    ids=["omitted", "null", "blank"],
)
def test_note_omitted_null_and_blank(
    store: PositionStore,
    changes: dict[str, Decimal | str | None],
    expected_note: str | None,
) -> None:
    created = _create(store, note="台積電")

    after = store.patch_fields(created.id, changes, now=T1)

    assert after is not None
    assert after.note == expected_note
    with closing(sqlite3.connect(store.db_path)) as conn:
        (stored,) = conn.execute(
            "SELECT note FROM positions WHERE id = ?", (created.id,)
        ).fetchone()
    assert stored == expected_note  # SQL NULL, not ''


def test_patch_of_a_missing_id_returns_none(store: PositionStore) -> None:
    _create(store)
    assert store.patch_fields(9999, {"quantity": Decimal("1")}, now=T1) is None


def test_empty_patch_returns_the_row_without_advancing_updated_at(store: PositionStore) -> None:
    created = _create(store)

    after = store.patch_fields(created.id, {}, now=T1)

    assert after == created
    assert after is not None and after.updated_at == T0
    assert store.patch_fields(9999, {}, now=T1) is None


def test_patch_refuses_a_column_outside_the_allow_list(store: PositionStore) -> None:
    created = _create(store)
    with pytest.raises(ValueError, match="not patchable: sector"):
        store.patch_fields(created.id, {"sector": "半導體業"}, now=T1)
    assert store.get(created.id) == created


def _snapshot_other_tables(db_path: Path) -> dict[str, list[tuple[object, ...]]]:
    with closing(sqlite3.connect(db_path)) as conn:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT IN ('positions', 'sqlite_sequence') ORDER BY name"
            )
        ]
        return {name: conn.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall() for name in names}


def test_delete_is_a_hard_delete_that_cascades_nowhere(tmp_path: Path) -> None:
    """C6: alert rules, Kelly inputs and playbook state outlive the holding."""
    db_path = tmp_path / "shared.db"
    positions = PositionStore(db_path)
    alerts = AlertStore(db_path)
    kelly = KellyInputStore(db_path)
    playbook = PlaybookStore(db_path)

    holding = _create(positions)
    alerts.create_rule(AlertRuleInput.model_validate(price_rule(symbol="2330")), now=T0)
    kelly.upsert(
        KellyInputRecord(
            symbol="2330",
            market="TW",
            win_rate=0.6,
            payoff_ratio=2.0,
            source="backtest",
            backtest_win_rate=0.6,
            backtest_payoff_ratio=2.0,
            strategy_id="ma_cross",
            oos_start_date="2025-01-02",
            oos_end_date="2026-06-30",
            oos_round_trips=24,
        ),
        now=T0,
    )
    playbook.ensure_batches(["2330"], batches_per_target=3)
    playbook.set_paused("2330", paused=True, on_date=date(2026, 9, 1))

    before = _snapshot_other_tables(db_path)
    assert before["alert_rules"] and before["kelly_inputs"]
    assert any(name.startswith("playbook_") and rows for name, rows in before.items())

    assert positions.delete(holding.id) is True

    assert positions.get(holding.id) is None
    assert _snapshot_other_tables(db_path) == before
