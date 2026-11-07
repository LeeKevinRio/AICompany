"""The N-177 / N-190 offline probe: every category, guards G-a..G-g, and S1-S11.

Every DB lives under ``tmp_path``. The schema comes from the real ``PlaybookStore`` and
``PriceBarCache``; hand-made rows go in through plain ``sqlite3`` so each category can be
staged exactly. The N-177a audit table does not exist in the store yet, so the tests that need
it build it from the DDL of the spec (section 4.6).
No network, no real DB, no ``.env``: the production DB is never opened, hashed or read.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.data.cache import PriceBarCache
from app.demo.series import DEMO_SOURCE
from app.playbook import engine, store, wording
from app.playbook.models import BatchState, RuleParams
from app.playbook.store import PlaybookStore

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND / "scripts" / "n177_n190_backtrack_probe.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("n177_n190_backtrack_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load()

RUN_AT = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 11, 7)
SET_AT_EARLY = "2026-08-01T00:00:00+00:00"
FILL_MOVES_DDL = """
CREATE TABLE IF NOT EXISTS playbook_fill_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    directive_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    batch_no INTEGER,
    shares_moved INTEGER NOT NULL,
    price TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('settle', 'repair')),
    created_at TEXT NOT NULL,
    CHECK ((batch_no IS NULL AND shares_moved = 0)
        OR (batch_no IS NOT NULL AND shares_moved > 0))
)
"""
FORBIDDEN_WORDS = ("建議", "應", "務必", "盡快", "否則", "安全", "對應", "需")
RISK_REVIEW = (
    BACKEND.parents[2] / "work" / "reviews" / "2026-11-07-N177實作規格審查與C6至C10確認-風控.md"
)


# ---------------------------------------------------------------- staging helpers


def _db(tmp_path: Path, *, with_bars: bool = True, with_audit: bool = False) -> Path:
    folder = tmp_path / "copy"
    folder.mkdir(exist_ok=True)
    path = folder / "stock-desk.db"
    PlaybookStore(db_path=path)
    if with_bars:
        PriceBarCache(path)
    if with_audit:
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(FILL_MOVES_DDL)
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


def _db_in(parent: Path, name: str, **kwargs: Any) -> Path:
    folder = parent / name
    folder.mkdir()
    return _db(folder, **kwargs)


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


def _executed(path: Path, *, price: str | None = "500", **fields: Any) -> int:
    settled_at = fields.pop("settled_at", "2026-08-11T23:00:00+00:00")
    return _row(
        path,
        status="executed",
        settled=1,
        settled_at=settled_at,
        settled_open_price=price,
        **fields,
    )


def _s2(path: Path, **fields: Any) -> int:
    values: dict[str, Any] = {
        "action": "sell",
        "rule_id": "S2",
        "batch_no": None,
        "shares": 150,
        "data_date": "2026-08-10",
        "execution_date": "2026-08-11",
        "rule_summary": "S2｜整檔出清",
        **fields,
    }
    return _executed(path, **values)


def _batch(path: Path, symbol: str = "2330", batch_no: int = 1, **fields: Any) -> None:
    values: dict[str, Any] = {
        "symbol": symbol,
        "batch_no": batch_no,
        "status": "open",
        "entry_date": "2026-08-05",
        "cost": "600",
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


def _bar(
    path: Path,
    symbol: str,
    day: str,
    close: str = "1",
    *,
    source: str = "twse",
    fetched_at: str = "2026-11-01T00:00:00+00:00",
    market: str = "TW",
) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "INSERT INTO price_bars_cache (symbol, market, trade_date, open, high, low, close, "
            "volume, currency, source, as_of, fetched_at) VALUES "
            "(?, ?, ?, '1', '1', '1', ?, 1, 'TWD', ?, '2026-01-01T00:00:00+00:00', ?)",
            (symbol, market, day, close, source, fetched_at),
        )


def _blacklist(path: Path, symbol: str, triggered_on: str) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "INSERT INTO playbook_blacklist (symbol, triggered_on, until, rule_id) "
            "VALUES (?, ?, '2026-12-31', 'S2')",
            (symbol, triggered_on),
        )


def _fill_move(
    path: Path, directive_id: int, symbol: str, batch_no: int | None, moved: int
) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "INSERT INTO playbook_fill_moves (directive_id, symbol, batch_no, shares_moved, "
            "price, source, created_at) VALUES (?, ?, ?, ?, '500', 'settle', "
            "'2026-08-11T23:00:00+00:00')",
            (directive_id, symbol, batch_no, moved),
        )


def _rule_params(path: Path, version: int, effective: str, payload: dict[str, str]) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "INSERT INTO playbook_rule_params (version, payload, submitted_at, effective_date, "
            "status) VALUES (?, ?, '2026-08-01T00:00:00+00:00', ?, 'effective')",
            (version, json.dumps(payload), effective),
        )


def _stage_phantom(path: Path, **s2_fields: Any) -> int:
    """Symbol 2330: two phantom batches (100 + 50) and one executed S2 for 150."""
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path, batch_no=1)
    _batch(path, batch_no=2, entry_date="2026-08-06", cost="590", shares=50, remaining_shares=50)
    return _s2(path, **s2_fields)


def _run(
    tmp_path: Path,
    db: Path,
    *extra: str,
    name: str = "out",
    env: dict[str, str] | None = None,
    until: date = AS_OF,
) -> tuple[int, dict[str, Any], str]:
    out = tmp_path / name
    out.mkdir(exist_ok=True)
    code = probe.main(
        ["--db-path", str(db), "--out-dir", str(out), *extra],
        env={} if env is None else env,
        now_utc=RUN_AT,
        today=until,
    )
    if code != 0:
        return code, {}, ""
    result = json.loads((out / "report.json").read_text(encoding="utf-8"))
    return code, result, (out / "report.md").read_text(encoding="utf-8")


def _report(tmp_path: Path, db: Path, *extra: str) -> dict[str, Any]:
    code, result, _md = _run(tmp_path, db, *extra)
    assert code == 0
    return result


def _affected(result: dict[str, Any]) -> list[dict[str, Any]]:
    affected: list[dict[str, Any]] = result["n177"]["affected"]
    return affected


# ---------------------------------------------------------------- N177-A


def test_n177_a_phantom_batches_get_a_trial_allocation_and_cash(tmp_path: Path) -> None:
    path = _db(tmp_path)
    s2_id = _stage_phantom(path)
    result = _report(tmp_path, path)
    (item,) = _affected(result)
    assert item["symbol"] == "2330"
    assert item["first_s2"] == {
        "id": s2_id,
        "data_date": "2026-08-10",
        "execution_date": "2026-08-11",
        "shares": 150,
        "settled_open_price": "500",
        "settled_at": "2026-08-11T23:00:00+00:00",
    }
    assert item["eligible_batches"] == [
        {"batch_no": 1, "remaining_shares": 100},
        {"batch_no": 2, "remaining_shares": 50},
    ]
    assert item["eligible_total"] == 150
    assert item["verdict"] == probe.TRIAL_LABEL
    assert item["guards"] == []
    assert item["trial"] == {
        "allocation": [{"batch_no": 1, "shares": 100}, {"batch_no": 2, "shares": 50}],
        "total_shares": 150,
        "price": "500",
        "cash": "75000",
    }
    assert result["gate"] == {
        "n177_affected_symbols": ["2330"],
        "n177_affected_count": 1,
        "ceo_decision_required": True,
    }


def test_n177_a_first_s2_is_the_earliest_and_later_ones_are_counted(tmp_path: Path) -> None:
    path = _db(tmp_path)
    first = _stage_phantom(path)
    _s2(path, execution_date="2026-08-12", data_date="2026-08-11")
    _s2(path, execution_date="2026-08-13", data_date="2026-08-12")
    _row(  # a pending S2 the next /today wrote
        path,
        action="sell",
        rule_id="S2",
        batch_no=None,
        shares=150,
        execution_date="2026-08-14",
    )
    (item,) = _affected(_report(tmp_path, path))
    assert item["first_s2"]["id"] == first
    assert len(item["qualifying_s2_ids"]) == 3
    assert item["later_executed_s2"] == 2
    assert item["pending_s2"] == 1
    # The later S2 lines are the same decision sent again: G-a ignores them.
    assert item["guards"] == []


def test_n177_a_a_symbol_without_eligible_batches_is_not_affected(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path, status="closed", remaining_shares=0)
    _batch(path, batch_no=2, status="planned", entry_date=None, cost=None, remaining_shares=0)
    _batch(path, batch_no=3, cost=None)  # open, remaining, but no cost
    _s2(path)
    result = _report(tmp_path, path)
    assert _affected(result) == []
    assert result["gate"]["ceo_decision_required"] is False
    assert [r["symbol"] for r in result["n177"]["not_affected_s2"]] == ["2330"]


def test_n177_a_batch_entered_after_the_s2_does_not_qualify_it(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path, entry_date="2026-08-20")
    _s2(path)  # execution_date 2026-08-11 is before the only batch entry
    assert _affected(_report(tmp_path, path)) == []


def test_allocation_follows_the_n177a_rule() -> None:
    assert probe.allocate(80, [(2, 50), (1, 50)]) == [(1, 50), (2, 30)]
    assert probe.allocate(500, [(1, 50), (2, 50)]) == [(1, 50), (2, 50)]
    assert probe.allocate(50, [(1, 50), (2, 50)]) == [(1, 50)]
    assert probe.allocate(10, []) == []


# ------------------------------------------------ guards G-a .. G-g (each one example)


def _manual(result: dict[str, Any]) -> dict[str, Any]:
    (item,) = _affected(result)
    assert item["trial"] is None
    assert item["verdict"].startswith(probe.MANUAL_LABEL + "：")
    return item


def test_g_a_another_executed_line_on_or_after_the_first_s2(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    other = _executed(path, execution_date="2026-08-12", rule_id="R1", batch_no=3)
    item = _manual(_report(tmp_path, path))
    assert item["guards"] == ["G-a"]
    assert f"ids={other}" in item["reasons"][0]["detail"]


def test_g_a_ignores_lines_before_the_first_s2_and_unsettled_ones(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    _executed(path, execution_date="2026-08-10", rule_id="R1")
    _row(path, execution_date="2026-08-12", rule_id="S1", action="sell")
    (item,) = _affected(_report(tmp_path, path))
    assert "G-a" not in item["guards"]


@pytest.mark.parametrize(
    "set_at",
    [None, "not-a-time", "2026-08-12T00:00:00+00:00"],
    ids=["absent", "unparseable", "later-than-settled-at"],
)
def test_g_b_total_deploy_set_at_missing_unparseable_or_later(
    tmp_path: Path, set_at: str | None
) -> None:
    path = _db(tmp_path)
    _batch(path, batch_no=1)
    _batch(path, batch_no=2, entry_date="2026-08-06", cost="590", shares=50, remaining_shares=50)
    _s2(path)
    if set_at is not None:
        _state(path, total_deploy_set_at=set_at)
    assert _manual(_report(tmp_path, path))["guards"] == ["G-b"]


def test_g_b_unparseable_settled_at_cannot_be_compared(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path, settled_at="garbage")
    assert _manual(_report(tmp_path, path))["guards"] == ["G-b"]


def test_g_c_prime_an_in_flight_sell_due_no_later_than_the_first_s2(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    early = _row(path, action="sell", rule_id="S1", batch_no=1, execution_date="2026-08-11")
    before = _row(path, action="sell", rule_id="P1", batch_no=2, execution_date="2026-08-10")
    # Not on an eligible batch: neither a guard hit nor listed.
    _row(path, action="sell", rule_id="S1", batch_no=9, execution_date="2026-08-01")
    result = _report(tmp_path, path)
    item = _manual(result)
    assert item["guards"] == ["G-c'"]
    assert f"ids={early},{before}" in item["reasons"][0]["detail"]
    assert [r["id"] for r in result["n177"]["inflight_on_affected"]] == [early, before]


def test_g_c_prime_covers_emergency_sells(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    _row(path, action="sell", rule_id="EMERGENCY", batch_no=2, execution_date="2026-08-11")
    assert _manual(_report(tmp_path, path))["guards"] == ["G-c'"]


def test_g_c_a_later_in_flight_sell_is_a_fact_column_and_the_trial_stays(tmp_path: Path) -> None:
    """RC-2: in-flight sells due after the first S2 no longer withhold the amount."""
    path = _db(tmp_path)
    _stage_phantom(path)
    late = _row(path, action="sell", rule_id="S1", batch_no=1, execution_date="2026-08-12")
    emergency = _row(
        path, action="sell", rule_id="EMERGENCY", batch_no=2, execution_date="2026-08-13"
    )
    result = _report(tmp_path, path)
    (item,) = _affected(result)
    assert item["guards"] == [] and item["verdict"] == probe.TRIAL_LABEL
    assert item["trial"] is not None and item["trial"]["cash"] == "75000"
    assert [r["id"] for r in result["n177"]["inflight_on_affected"]] == [late, emergency]


@pytest.mark.parametrize("price", [None, "abc", "NaN", "Infinity"])
def test_g_d_settled_open_price_missing_or_not_finite(tmp_path: Path, price: str | None) -> None:
    path = _db(tmp_path)
    _stage_phantom(path, price=price)
    assert _manual(_report(tmp_path, path))["guards"] == ["G-d"]


def test_g_e_an_eligible_batch_without_entry_date(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _state(path, total_deploy_set_at=SET_AT_EARLY)
    _batch(path, batch_no=1)
    _batch(path, batch_no=2, entry_date=None, cost="590", shares=50, remaining_shares=50)
    _s2(path, shares=100)
    item = _manual(_report(tmp_path, path))
    assert item["guards"] == ["G-e"]
    assert "批次=2" in item["reasons"][0]["detail"]


def test_g_f_s2_shares_differ_from_the_earlier_eligible_total(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path, shares=120)
    item = _manual(_report(tmp_path, path))
    assert item["guards"] == ["G-f"]
    assert "120" in item["reasons"][0]["detail"] and "150" in item["reasons"][0]["detail"]


def test_g_g_the_symbol_already_has_an_audit_row(tmp_path: Path) -> None:
    path = _db(tmp_path, with_audit=True)
    _stage_phantom(path)
    earlier = _s2(path, execution_date="2026-08-09", data_date="2026-08-08")
    _fill_move(path, earlier, "2330", 1, 10)
    result = _report(tmp_path, path)
    item = _manual(result)
    assert item["guards"] == ["G-g"]
    assert result["meta"]["tables"]["playbook_fill_moves"] is True


def test_every_guard_listed_at_once_withholds_the_amount(tmp_path: Path) -> None:
    path = _db(tmp_path, with_audit=True)
    _batch(path, batch_no=1)
    _batch(path, batch_no=2, entry_date=None, cost="590", shares=50, remaining_shares=50)
    first = _s2(path, price=None, shares=77, settled_at="2026-08-11T23:00:00+00:00")
    _executed(path, execution_date="2026-08-12", rule_id="R1", batch_no=3)
    _row(path, action="sell", rule_id="S1", batch_no=1, execution_date="2026-08-11")
    other = _s2(path, execution_date="2026-08-09", data_date="2026-08-08")
    _fill_move(path, other, "2330", 1, 10)
    item = _manual(_report(tmp_path, path))
    assert item["guards"] == ["G-a", "G-b", "G-c'", "G-d", "G-e", "G-f", "G-g"]
    assert item["first_s2"]["id"] == first != other


def test_audited_s2_lines_drop_out_of_the_candidate_list(tmp_path: Path) -> None:
    path = _db(tmp_path, with_audit=True)
    s2_id = _stage_phantom(path)
    _fill_move(path, s2_id, "2330", 1, 100)
    result = _report(tmp_path, path)
    assert _affected(result) == []
    assert result["gate"]["ceo_decision_required"] is False


def test_the_report_states_whether_the_audit_table_exists(tmp_path: Path) -> None:
    path = _db(tmp_path)
    # N-177a merged (C14): the store now creates the audit table, so a copy that no
    # N-177a build has opened is staged by dropping it again.
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("DROP TABLE playbook_fill_moves")
    _stage_phantom(path)
    result = _report(tmp_path, path)
    assert result["meta"]["tables"]["playbook_fill_moves"] is False
    assert len(_affected(result)) == 1  # the query without the NOT EXISTS clause runs


# ---------------------------------------------------------------- N177-B .. F


def test_n177_b_symbols_with_s2_but_no_phantom_batch_are_listed_apart(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _s2(path, symbol="2454", execution_date="2026-08-11")
    _s2(path, symbol="2454", execution_date="2026-08-15")
    _row(
        path, symbol="2454", action="sell", rule_id="S2", batch_no=None, execution_date="2026-08-18"
    )
    _row(
        path, symbol="2454", action="sell", rule_id="S2", batch_no=None, status="missed", settled=1
    )
    (row,) = _report(tmp_path, path)["n177"]["not_affected_s2"]
    assert row == {
        "symbol": "2454",
        "executed": 2,
        "pending": 1,
        "earliest_execution_date": "2026-08-11",
        "latest_execution_date": "2026-08-18",
    }


def test_n177_c_blacklist_distance_counts_index_bar_dates(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    for day in ("2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"):
        _bar(path, "^TWII", day)
    _bar(path, "2330", "2026-08-14")  # a stock bar must not enter the index calendar
    _blacklist(path, "2330", "2026-08-12")
    _blacklist(path, "9999", "2026-08-12")
    rows = _report(tmp_path, path)["n177"]["blacklist"]
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["2330"]["first_s2_data_date"] == "2026-08-10"
    assert by_symbol["2330"]["trading_day_difference"] == 2
    assert by_symbol["2330"]["difference_basis"] == probe.TRADING_DAY_BASIS_INDEX
    assert by_symbol["9999"]["trading_day_difference"] is None


def test_n177_c_without_index_bars_the_calendar_falls_back_and_says_so(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    for day in ("2026-08-11", "2026-08-12"):
        _bar(path, "2330", day)
    _bar(path, "2317", "2026-08-12")
    _bar(path, "2454", "2026-08-13", source=DEMO_SOURCE)  # demo dates are not a calendar
    _blacklist(path, "2330", "2026-08-13")
    (row,) = _report(tmp_path, path)["n177"]["blacklist"]
    assert row["trading_day_difference"] == 2
    assert row["difference_basis"] == probe.TRADING_DAY_BASIS_UNION


def test_n177_c_without_any_bar_there_is_no_distance(tmp_path: Path) -> None:
    path = _db(tmp_path, with_bars=False)
    _stage_phantom(path)
    _blacklist(path, "2330", "2026-08-13")
    (row,) = _report(tmp_path, path)["n177"]["blacklist"]
    assert row["trading_day_difference"] is None and row["difference_basis"] is None


def test_n177_c_distance_is_negative_when_the_blacklist_is_earlier(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    for day in ("2026-08-07", "2026-08-08", "2026-08-10"):
        _bar(path, "^TWII", day)
    _blacklist(path, "2330", "2026-08-07")
    (row,) = _report(tmp_path, path)["n177"]["blacklist"]
    assert row["trading_day_difference"] == -2


def test_n177_d_executed_lines_whose_batch_row_is_missing(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _batch(path, symbol="2330", batch_no=1)
    has_batch = _executed(path, symbol="2330", batch_no=1)
    gone = _executed(path, symbol="2317", batch_no=2, shares=40, price="25.5")
    no_number = _executed(path, symbol="2454", batch_no=None, shares=10, price=None)
    emergency = _executed(
        path, symbol="2603", batch_no=1, action="sell", rule_id="EMERGENCY", shares=5
    )
    s2 = _s2(path, symbol="2881")  # an S2 without a batch number is not this category
    unsettled = _row(path, symbol="2882", batch_no=7)
    rows = {r["id"]: r for r in _report(tmp_path, path)["n177"]["missing_batch_rows"]}
    assert set(rows) == {gone, no_number, emergency}
    assert has_batch not in rows and s2 not in rows and unsettled not in rows
    assert rows[gone]["unbooked_amount"] == "1020.0"
    assert rows[no_number]["unbooked_amount"] is None
    assert rows[emergency]["note"] == "N2 已揭露"
    assert rows[gone]["note"] is None


def test_n177_e_pending_s2_lines(tmp_path: Path) -> None:
    path = _db(tmp_path)
    pending = _row(path, symbol="2330", action="sell", rule_id="S2", batch_no=None, shares=150)
    _s2(path, symbol="2317")  # executed: not pending
    _row(path, symbol="2454", action="sell", rule_id="S1")  # not S2
    (row,) = _report(tmp_path, path)["n177"]["pending_s2"]
    assert row["id"] == pending and row["shares"] == 150


def test_n177_f_the_in_flight_detail_lists_only_affected_symbols(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    mine = _row(
        path, action="sell", rule_id="P1", batch_no=2, shares=10, execution_date="2026-08-12"
    )
    _row(path, symbol="2317", action="sell", rule_id="P1", batch_no=1)
    (row,) = _report(tmp_path, path)["n177"]["inflight_on_affected"]
    assert row == {
        "id": mine,
        "symbol": "2330",
        "rule_id": "P1",
        "batch_no": 2,
        "shares": 10,
        "execution_date": "2026-08-12",
    }


# ---------------------------------------------------------------- N190-A


def _stage_stop_loss(path: Path) -> None:
    """Symbol 2317, one batch at cost 100, bars from 2026-09-02 to 2026-09-09."""
    _batch(path, symbol="2317", entry_date="2026-09-01", cost="100")
    closes = {
        "2026-09-02": "95",
        "2026-09-03": "89",
        "2026-09-04": "91",
        "2026-09-07": "84",
        "2026-09-08": "80",
        "2026-09-09": "79",
    }
    for day, close in closes.items():
        _bar(path, "2317", day, close, fetched_at=f"{day}T09:00:00+00:00")


def _candidates(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = result["n190"]["stop_loss_candidates"]
    return rows


def _key(c: dict[str, Any]) -> tuple[str, Any, str]:
    return (c["data_date"], c["batch_no"], c["category"])


def test_n190_a_lists_the_three_threshold_categories_without_a_conclusion(
    tmp_path: Path,
) -> None:
    path = _db(tmp_path)
    _stage_stop_loss(path)
    result = _report(tmp_path, path)
    rows = _candidates(result)
    assert [_key(c) for c in rows] == [
        ("2026-09-03", 1, probe.CAT_S1),
        ("2026-09-04", 1, probe.CAT_S1_DEFENSE),
        ("2026-09-07", None, probe.CAT_S2),
        ("2026-09-07", 1, probe.CAT_S1),
        ("2026-09-08", None, probe.CAT_S2),
        ("2026-09-08", 1, probe.CAT_S1),
        ("2026-09-09", None, probe.CAT_S2),
        ("2026-09-09", 1, probe.CAT_S1),
    ]
    first = rows[0]
    assert first["close"] == "89" and first["cost"] == "100"
    assert first["close_over_cost"] == "0.8900"
    assert first["threshold"] == "90.00"
    assert first["params_version"] == "default"
    assert first["note"] is None
    assert rows[1]["note"] == probe.NOTE_DEFENSE
    assert rows[1]["threshold"] == "93.00"
    assert rows[2]["threshold"] == "85.00"
    assert result["n190"]["stats"]["since"] == "2026-09-01"


def test_n190_a_an_s1_line_or_an_s2_line_on_the_day_removes_the_candidate(
    tmp_path: Path,
) -> None:
    path = _db(tmp_path)
    _stage_stop_loss(path)
    _row(path, symbol="2317", batch_no=1, action="sell", rule_id="S1", data_date="2026-09-08")
    _row(path, symbol="2317", batch_no=None, action="sell", rule_id="S2", data_date="2026-09-09")
    keys = [_key(c) for c in _candidates(_report(tmp_path, path))]
    assert ("2026-09-08", 1, probe.CAT_S1) not in keys
    assert ("2026-09-08", None, probe.CAT_S2) in keys  # only the S1 line exists that day
    assert ("2026-09-09", 1, probe.CAT_S1) not in keys
    assert ("2026-09-09", None, probe.CAT_S2) not in keys


def test_n190_a_day_facts_symbol_rows_system_write_and_cache(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_stop_loss(path)
    # 09-03: another symbol was written at 10:00; the 2317 bar was fetched at 09:00 -> cached.
    _row(path, symbol="9999", data_date="2026-09-03", created_at="2026-09-03T10:00:00+00:00")
    # 09-04: a 2317 line exists (not S1/S2), written 08:00, but the bar was fetched at 09:00.
    _row(
        path,
        symbol="2317",
        batch_no=1,
        rule_id="R2",
        action="defer",
        data_date="2026-09-04",
        created_at="2026-09-04T08:00:00+00:00",
    )
    by_day = {c["data_date"]: c for c in _candidates(_report(tmp_path, path)) if c["batch_no"]}
    assert (
        by_day["2026-09-03"]["symbol_has_rows"],
        by_day["2026-09-03"]["system_wrote"],
        by_day["2026-09-03"]["cache_had_bar"],
    ) == (False, True, probe.CACHE_HAD_BAR)
    assert (
        by_day["2026-09-04"]["symbol_has_rows"],
        by_day["2026-09-04"]["system_wrote"],
        by_day["2026-09-04"]["cache_had_bar"],
    ) == (True, True, probe.CACHE_UNDETERMINED)
    assert by_day["2026-09-07"]["system_wrote"] is False
    assert by_day["2026-09-07"]["cache_had_bar"] == probe.CACHE_UNDETERMINED


def test_n190_a_emergency_and_rebalance_lines_are_not_an_evaluation_write(
    tmp_path: Path,
) -> None:
    path = _db(tmp_path)
    _stage_stop_loss(path)
    for rule in ("EMERGENCY", "REBALANCE"):
        _row(
            path,
            symbol="9999",
            rule_id=rule,
            data_date="2026-09-03",
            created_at="2026-09-03T10:00:00+00:00",
        )
    first = _candidates(_report(tmp_path, path))[0]
    assert first["system_wrote"] is False


def test_n190_a_demo_bars_are_excluded_and_counted(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_stop_loss(path)
    _bar(path, "2317", "2026-09-10", "10", source=DEMO_SOURCE)
    _bar(path, "2317", "2026-09-11", "10", source=DEMO_SOURCE)
    result = _report(tmp_path, path)
    assert all(c["data_date"] <= "2026-09-09" for c in _candidates(result))
    assert result["n190"]["stats"]["demo_bars_excluded"] == {"2317": 2}


def test_n190_a_rule_params_are_picked_like_active_params(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_stop_loss(path)
    _rule_params(path, 1, "2026-08-01", {"s1_ratio": "0.95", "s1_defense_ratio": "0.97"})
    _rule_params(path, 2, "2026-09-04", {"s1_ratio": "0.80", "s2_ratio": "0.50"})
    # Same effective date: the higher version wins.
    _rule_params(path, 3, "2026-09-08", {"s1_ratio": "0.10"})
    _rule_params(path, 4, "2026-09-08", {"s1_ratio": "0.85", "s2_ratio": "0.90"})
    rows = _candidates(_report(tmp_path, path))
    by_key = {_key(c): c for c in rows}
    # 09-02 close 95 with v1: 95 >= 95 -> not below the general threshold, 97 -> defense only.
    assert by_key[("2026-09-02", 1, probe.CAT_S1_DEFENSE)]["params_version"] == "1"
    assert by_key[("2026-09-02", 1, probe.CAT_S1_DEFENSE)]["threshold"] == "97.00"
    # 09-04..09-07 use v2: ratios 0.80 / default defense 0.93 / s2 0.50: close 91 is only
    # below the defense line (93), and 84 is above 80 but below 93.
    assert by_key[("2026-09-04", 1, probe.CAT_S1_DEFENSE)]["params_version"] == "2"
    assert ("2026-09-07", 1, probe.CAT_S1_DEFENSE) in by_key
    assert all(c["category"] != probe.CAT_S2 or c["data_date"] >= "2026-09-08" for c in rows)
    # 09-08 uses v4 (highest version on that effective date): s1 0.85, s2 0.90.
    assert by_key[("2026-09-08", None, probe.CAT_S2)]["threshold"] == "90.00"
    assert by_key[("2026-09-08", None, probe.CAT_S2)]["params_version"] == "4"


def test_n190_a_unparseable_rule_params_skip_the_day_and_are_counted(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_stop_loss(path)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "INSERT INTO playbook_rule_params (version, payload, submitted_at, effective_date, "
            "status) VALUES (1, 'not json', '2026-08-01T00:00:00+00:00', '2026-08-01', 'x')"
        )
    result = _report(tmp_path, path)
    assert _candidates(result) == []
    assert result["n190"]["stats"]["unusable_params_days"] == 6


def test_n190_a_weighted_average_cost_for_the_whole_symbol(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _batch(path, symbol="2317", batch_no=1, entry_date="2026-09-01", cost="100")
    _batch(path, symbol="2317", batch_no=2, entry_date="2026-09-01", cost="120")
    _bar(path, "2317", "2026-09-02", "93")
    s2 = [c for c in _candidates(_report(tmp_path, path)) if c["category"] == probe.CAT_S2]
    (row,) = s2
    assert row["batch_no"] is None
    assert row["cost"] == "110"
    assert row["threshold"] == "93.50"
    assert row["close_over_cost"] == "0.8455"


def test_n190_a_hold_is_replayed_from_executed_sells(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _batch(path, symbol="2454", entry_date="2026-09-01", cost="100", shares=100)
    for day in ("2026-08-31", "2026-09-02", "2026-09-04", "2026-09-07"):
        _bar(path, "2454", day, "50")
    # Half sold on 09-03, the rest on 09-04: held on 09-02 only (and not before entry).
    _executed(
        path,
        symbol="2454",
        batch_no=1,
        action="sell",
        rule_id="P1",
        shares=50,
        execution_date="2026-09-03",
    )
    _executed(
        path,
        symbol="2454",
        batch_no=1,
        action="sell",
        rule_id="S1",
        shares=999,
        execution_date="2026-09-04",
    )
    result = _report(tmp_path, path, "--since", "2026-08-31")
    assert sorted({c["data_date"] for c in _candidates(result)}) == ["2026-09-02"]
    assert result["n190"]["held_summary"] == [
        {
            "symbol": "2454",
            "held_days": 1,
            "days_with_symbol_rows": 0,
            "days_without_symbol_rows": 1,
        }
    ]


def test_n190_a_audit_moves_close_a_batch_on_the_s2_execution_date(tmp_path: Path) -> None:
    path = _db(tmp_path, with_audit=True)
    _batch(path, symbol="2454", entry_date="2026-09-01", cost="100", shares=100)
    for day in ("2026-09-02", "2026-09-07"):
        _bar(path, "2454", day, "50")
    s2 = _s2(path, symbol="2454", execution_date="2026-09-04", data_date="2026-09-03")
    _fill_move(path, s2, "2454", 1, 100)
    assert sorted({c["data_date"] for c in _candidates(_report(tmp_path, path))}) == ["2026-09-02"]


def test_n190_a_an_s2_before_the_fix_does_not_close_the_hold(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _batch(path, symbol="2454", entry_date="2026-09-01", cost="100", shares=100)
    _bar(path, "2454", "2026-09-07", "50")
    _s2(path, symbol="2454", execution_date="2026-09-04", data_date="2026-09-03")
    assert {c["data_date"] for c in _candidates(_report(tmp_path, path))} == {"2026-09-07"}


def test_n190_a_since_and_until_bound_the_range(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_stop_loss(path)
    result = _report(tmp_path, path, "--since", "2026-09-04", "--until", "2026-09-07")
    assert sorted({c["data_date"] for c in _candidates(result)}) == ["2026-09-04", "2026-09-07"]
    assert result["meta"]["since"] == "2026-09-04" and result["meta"]["until"] == "2026-09-07"


def test_n190_a_without_batches_or_bars_the_list_is_empty(tmp_path: Path) -> None:
    path = _db(tmp_path, with_bars=False)
    result = _report(tmp_path, path)
    assert _candidates(result) == []
    assert result["meta"]["since"] is None
    assert result["n190"]["held_summary"] == []


def test_n190_a_held_summary_counts_days_with_and_without_lines(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_stop_loss(path)
    _row(path, symbol="2317", batch_no=1, rule_id="P3", data_date="2026-09-02")
    (summary,) = _report(tmp_path, path)["n190"]["held_summary"]
    assert summary == {
        "symbol": "2317",
        "held_days": 6,
        "days_with_symbol_rows": 1,
        "days_without_symbol_rows": 5,
    }


# ---------------------------------------------------------------- N190-B .. D


def _m1_summary(status: str, count: int = 1) -> str:
    return "M1｜" + wording.INDEX_GAP_DEFER_NOTE.format(status=status, count=count)


def _stage_m1(path: Path) -> dict[str, int]:
    ids: dict[str, int] = {}
    ids["a"] = _row(
        path,
        symbol="2330",
        batch_no=1,
        rule_id="M1",
        action="defer",
        shares=0,
        data_date="2026-09-10",
        execution_date="2026-09-11",
        created_at="2026-09-10T10:00:00+00:00",
        rule_summary=_m1_summary("cached_stale", 1),
    )
    ids["b"] = _row(
        path,
        symbol="2317",
        batch_no=1,
        rule_id="M1",
        action="defer",
        shares=0,
        data_date="2026-09-10",
        execution_date="2026-09-11",
        created_at="2026-09-10T10:00:00+00:00",
        rule_summary=_m1_summary("missing", 1),
    )
    # The same K1 written by a second /today call: counted once.
    ids["dup"] = _row(
        path,
        symbol="2317",
        batch_no=1,
        rule_id="M1",
        action="defer",
        shares=0,
        data_date="2026-09-10",
        execution_date="2026-09-11",
        created_at="2026-09-10T11:00:00+00:00",
        rule_summary=_m1_summary("missing", 1),
    )
    ids["skip"] = _row(
        path,
        symbol="2330",
        batch_no=2,
        rule_id="R3",
        action="skip",
        shares=0,
        data_date="2026-09-11",
        execution_date="2026-09-14",
        created_at="2026-09-11T10:00:00+00:00",
        rule_summary="R3｜"
        + wording.INDEX_GAP_DEFER_NOTE.format(status="missing", count=3)
        + "跳過",
    )
    ids["nobar"] = _row(
        path,
        symbol="2330",
        batch_no=1,
        rule_id="M1",
        action="defer",
        shares=0,
        data_date="2026-09-12",
        execution_date="2026-09-14",
        created_at="2026-09-12T10:00:00+00:00",
        rule_summary=_m1_summary("cached_stale", 2),
    )
    # Not index related: an R3 skip without the marker, an R2 defer.
    _row(path, rule_id="R3", action="skip", data_date="2026-09-13", rule_summary="R3｜追價上限")
    _row(path, rule_id="R2", action="defer", data_date="2026-09-13", rule_summary="R2｜不追價")
    _bar(path, "^TWII", "2026-09-10", fetched_at="2026-09-10T09:00:00+00:00")
    _bar(path, "^TWII", "2026-09-11", fetched_at="2026-09-12T09:00:00+00:00")
    return ids


def test_n190_b_index_gap_days(tmp_path: Path) -> None:
    path = _db(tmp_path)
    ids = _stage_m1(path)
    _state(
        path,
        fast_market_measured_on="2026-09-09",
        defense_active="1",
        defense_since="2026-09-01",
    )
    result = _report(tmp_path, path)
    days = {d["data_date"]: d for d in result["n190"]["m1_unevaluated_days"]}
    assert sorted(days) == ["2026-09-10", "2026-09-11", "2026-09-12"]
    assert days["2026-09-10"] == {
        "data_date": "2026-09-10",
        "execution_dates": ["2026-09-11"],
        "index_status": ["cached_stale", "missing"],
        "deferred_batches": 2,
        "skipped_batches": 0,
        "line_ids": sorted([ids["a"], ids["b"], ids["dup"]]),
        "index_cache_had_bar": probe.CACHE_HAD_BAR,
    }
    assert days["2026-09-11"]["skipped_batches"] == 1
    assert days["2026-09-11"]["index_status"] == ["missing"]
    assert days["2026-09-11"]["index_cache_had_bar"] == probe.CACHE_UNDETERMINED
    assert days["2026-09-12"]["index_cache_had_bar"] == probe.CACHE_NO_BAR
    assert result["n190"]["m1_state"] == {
        "fast_market_measured_on": "2026-09-09",
        "defense_active": "1",
        "defense_since": "2026-09-01",
    }


def test_the_marker_cuts_the_status_exactly_as_the_engine_wrote_it() -> None:
    summary = _m1_summary("cached_stale", 3)
    assert probe._index_status(summary) == "cached_stale"
    assert probe._index_status("R2｜不追價") is None
    assert probe._index_status(probe.INDEX_GAP_MARKER + "unterminated") is None


def test_n190_c_accumulated_defers_per_batch(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _batch(path, symbol="2330", batch_no=1, status="open", defer_count=2)
    _batch(
        path, symbol="2330", batch_no=2, status="skipped", defer_count=3, entry_date=None, cost=None
    )
    _batch(
        path, symbol="2317", batch_no=1, status="planned", defer_count=1, entry_date=None, cost=None
    )
    _batch(path, symbol="2454", batch_no=1, status="planned", entry_date=None, cost=None)
    _stage_m1(path)
    _row(
        path,
        symbol="2330",
        batch_no=1,
        rule_id="R2",
        action="defer",
        execution_date="2026-09-15",
        rule_summary="R2｜不追價",
    )
    rows = {
        (r["symbol"], r["batch_no"]): r for r in _report(tmp_path, path)["n190"]["defer_counts"]
    }
    assert ("2454", 1) not in rows  # no defer line and defer_count 0
    one = rows[("2330", 1)]
    assert (one["status"], one["defer_count"]) == ("open", 2)
    assert (one["m1_defers"], one["m1_cached_stale"], one["r2_defers"]) == (2, 2, 2)
    assert one["m1_share"] == "0.5000"
    assert len(one["r3_skip_ids"]) == 1  # the unrelated R3 line staged by _stage_m1
    assert rows[("2317", 1)]["m1_defers"] == 1  # K1 written twice counts once
    assert rows[("2317", 1)]["m1_cached_stale"] == 0
    assert rows[("2330", 2)]["r3_skip_ids"] != []
    assert rows[("2330", 2)]["m1_share"] is None


def test_n190_d_skipped_batches_and_the_reason_category(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _batch(path, symbol="2330", batch_no=2, status="skipped", entry_date=None, cost=None)
    _batch(path, symbol="2330", batch_no=3, status="skipped", entry_date=None, cost=None)
    _batch(path, symbol="2330", batch_no=4, status="skipped", entry_date=None, cost=None)
    _batch(path, symbol="2330", batch_no=1, status="open")
    _stage_m1(path)
    other = _row(
        path, symbol="2330", batch_no=3, rule_id="R3", action="skip", rule_summary="R3｜追價上限"
    )
    rows = {r["batch_no"]: r for r in _report(tmp_path, path)["n190"]["skipped_batches"]}
    assert set(rows) == {2, 3, 4}
    assert rows[2]["reason_category"] == "指數缺漏順延累計"
    assert rows[3]["reason_category"] == "其他（R2 不追價順延或 T+1 未成交累計）"
    assert rows[3]["r3_skip_ids"] == [other]
    assert rows[4]["reason_category"] == "無 R3 跳過列"


# ---------------------------------------------------------------- report formats


def _rich_world(tmp_path: Path) -> Path:
    path = _db(tmp_path, with_audit=True)
    _stage_phantom(path)
    _stage_stop_loss(path)
    _stage_m1(path)
    _s2(path, symbol="2454", price=None)
    _batch(path, symbol="2454", batch_no=1, cost="50", shares=10, remaining_shares=10)
    _row(path, symbol="2603", action="sell", rule_id="S2", batch_no=None)
    _executed(path, symbol="2881", batch_no=4)
    _blacklist(path, "2330", "2026-08-12")
    for day in ("2026-08-10", "2026-08-11", "2026-08-12"):
        _bar(path, "^TWII", day)
    _batch(path, symbol="2330", batch_no=3, status="skipped", entry_date=None, cost=None)
    return path


def test_report_json_schema_and_limitation_codes(tmp_path: Path) -> None:
    result = _report(tmp_path, _rich_world(tmp_path))
    assert set(result) == {
        "schema_version",
        "meta",
        "gate",
        "n177",
        "n190",
        "limitations",
        "diff_vs_previous",
    }
    assert result["schema_version"] == 1
    assert set(result["n177"]) == {
        "affected",
        "not_affected_s2",
        "blacklist",
        "missing_batch_rows",
        "pending_s2",
        "inflight_on_affected",
    }
    assert {
        "stop_loss_candidates",
        "held_summary",
        "m1_unevaluated_days",
        "defer_counts",
        "skipped_batches",
    } <= set(result["n190"])
    assert set(result["gate"]) == {
        "n177_affected_symbols",
        "n177_affected_count",
        "ceo_decision_required",
    }
    assert result["diff_vs_previous"] is None
    assert result["limitations"] == [f"L{i}" for i in range(1, 12)]
    assert result["meta"]["run_at_utc"] == "2026-11-07T12:00:00+00:00"


def test_every_known_limitation_is_written_into_the_markdown(tmp_path: Path) -> None:
    _code, _result, markdown = _run(tmp_path, _rich_world(tmp_path))
    assert sorted(probe.LIMITATIONS, key=lambda c: int(c[1:])) == [f"L{i}" for i in range(1, 12)]
    for code, text in probe.LIMITATIONS.items():
        assert f"- {code}：{text}" in markdown


def test_markdown_header_summary_and_gate_line(tmp_path: Path) -> None:
    path = _rich_world(tmp_path)
    _code, result, markdown = _run(tmp_path, path)
    meta = result["meta"]
    assert markdown.startswith("# N-177 / N-190 唯讀偵測與回溯報告")
    assert f"- 腳本 SHA-256（LF 正規化）：{probe.script_fingerprint()}" in markdown
    assert f"- 執行前 DB SHA-256：{meta['db_sha256_before']}" in markdown
    assert f"- 執行後 DB SHA-256：{meta['db_sha256_after']}" in markdown
    assert "- 資料表 playbook_fill_moves：存在" in markdown
    assert "- run_at_utc：2026-11-07T12:00:00+00:00" in markdown
    assert _risk_sentences()[0].format(n=result["gate"]["n177_affected_count"]) in markdown
    for heading in (
        "## 摘要",
        "## N177-A 受影響標的",
        "## N177-B",
        "## N177-C",
        "## N177-D",
        "## N177-E",
        "## N177-F",
        "## N190-A",
        "## N190-B",
        "## N190-C",
        "## N190-D",
        "## 已知限制",
    ):
        assert heading in markdown, heading
    assert "| 標的 | 第一張 S2 id |" in markdown
    assert "可試算" in markdown


def test_markdown_for_a_manual_row_carries_the_label_and_no_amount(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path, price=None)
    _code, _result, markdown = _run(tmp_path, path)
    assert "需人工判讀：G-d" in markdown
    assert "試算回補現金" in markdown


def test_empty_book_prints_empty_sections_and_zero_gate(tmp_path: Path) -> None:
    code, result, markdown = _run(tmp_path, _db(tmp_path))
    assert code == 0
    assert result["gate"]["n177_affected_count"] == 0
    assert "N-177 部署閘門：受影響標的 0 檔" in markdown
    assert markdown.count("（無）") >= 10


def test_table_cells_escape_pipes_and_newlines() -> None:
    assert probe._cell("a|b\nc") == "a\\|b c"
    assert probe._cell(None) == "-"
    assert probe._table(["x"], []) == ["（無）", ""]


def test_stdout_is_an_ascii_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _rich_world(tmp_path)
    out = tmp_path / "ひらがな"
    out.mkdir()
    code = probe.main(
        ["--db-path", str(path), "--out-dir", str(out)], env={}, now_utc=RUN_AT, today=AS_OF
    )
    text = capsys.readouterr().out
    assert code == 0
    assert text.isascii()
    assert "version=1" in text and "gate_affected_symbols=2" in text
    assert "report_md=" in text and "report_json=" in text
    assert (out / "report.md").is_file()


def test_fingerprint_ignores_line_endings() -> None:
    text = SCRIPT_PATH.read_bytes()
    crlf = b"\r\n".join(text.splitlines()) + b"\r\n"
    assert probe.fingerprint_of(crlf) == probe.fingerprint_of(text) == probe.script_fingerprint()


# ---------------------------------------------------------------- diff vs previous


def test_previous_json_marks_rows_that_differ(tmp_path: Path) -> None:
    path = _db(tmp_path)
    s2_a = _stage_phantom(path)
    s2_b = _s2(path, symbol="2454", execution_date="2026-08-11", shares=100)
    _batch(path, symbol="2454", batch_no=1)
    _, first, _md = _run(tmp_path, path, name="first")
    assert first["diff_vs_previous"] is None
    # Nothing moved: both rows are the same as before.
    _, same, _md = _run(
        tmp_path, path, "--previous-json", str(tmp_path / "first" / "report.json"), name="same"
    )
    assert {d["key"]: d["result"] for d in same["diff_vs_previous"]} == {
        f"2330:{s2_a}": "與前次相同",
        f"2454:{s2_b}": "與前次相同",
    }
    # State moved on: a guard now holds for 2330 only.
    _executed(path, execution_date="2026-08-12", rule_id="R1", batch_no=3)
    _, moved, markdown = _run(
        tmp_path, path, "--previous-json", str(tmp_path / "first" / "report.json"), name="moved"
    )
    results = {d["key"]: d["result"] for d in moved["diff_vs_previous"]}
    assert results[f"2330:{s2_a}"] == "與前次不同"
    assert "## 與前次報告的比對" in markdown


def test_previous_json_reports_rows_that_vanished_or_are_new(tmp_path: Path) -> None:
    before = _db_in(tmp_path, "before")
    s2 = _stage_phantom(before)
    _, _first, _md = _run(tmp_path, before, name="first")
    after = _db_in(tmp_path, "after", with_audit=True)
    _stage_phantom(after)
    _fill_move(after, s2, "2330", 1, 100)  # 2330 repaired: its S2 now has an audit row
    new = _s2(after, symbol="2454", execution_date="2026-08-11", shares=100)
    _batch(after, symbol="2454", batch_no=1)
    _, result, _md = _run(
        tmp_path, after, "--previous-json", str(tmp_path / "first" / "report.json"), name="third"
    )
    statuses = {d["key"]: d["result"] for d in result["diff_vs_previous"]}
    assert statuses == {f"2330:{s2}": "本次沒有", f"2454:{new}": "前次沒有"}


@pytest.mark.parametrize("content", ["not json", "[]", '{"schema_version": 2}'])
def test_unusable_previous_json_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    path = _db(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")
    assert _run(tmp_path, path, "--previous-json", str(bad))[0] == 2
    assert "--previous-json" in capsys.readouterr().err
    assert _run(tmp_path, path, "--previous-json", str(tmp_path / "gone.json"), name="b")[0] == 2


# ---------------------------------------------------------------- exit codes 2, 3, 4


def test_missing_db_exits_two_and_is_not_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.db"
    code, _result, _md = _run(tmp_path, missing)
    assert code == 2
    assert "cannot read the DB" in capsys.readouterr().err
    assert not missing.exists()
    assert list((tmp_path / "out").iterdir()) == []


def test_db_without_the_directive_table_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "other.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
    assert _run(tmp_path, path)[0] == 2
    assert "playbook_directives" in capsys.readouterr().err


def test_a_locked_database_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)

    def locked(*args: Any, **kwargs: Any) -> Any:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(probe, "load", locked)
    assert _run(tmp_path, path)[0] == 2
    assert "database is locked" in capsys.readouterr().err
    assert list((tmp_path / "out").iterdir()) == []


def test_exit_three_when_the_db_file_changes_during_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    real_load = probe.load

    def load_then_touch(*args: Any, **kwargs: Any) -> Any:
        snapshot = real_load(*args, **kwargs)
        with open(path, "ab") as handle:
            handle.write(b"\0")
        return snapshot

    monkeypatch.setattr(probe, "load", load_then_touch)
    before = probe.sha256_file(path)
    assert _run(tmp_path, path)[0] == 3
    err = capsys.readouterr().err
    assert before in err and "changed" in err
    assert list((tmp_path / "out").iterdir()) == []


# ---------------------------------------------------------------- S1


def test_s1_the_connection_is_a_read_only_uri_with_query_only_and_five_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    calls: list[tuple[str, dict[str, Any]]] = []
    statements: list[str] = []
    real_connect = sqlite3.connect

    def traced(database: str, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        calls.append((database, kwargs))
        conn: sqlite3.Connection = real_connect(database, *args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(probe.sqlite3, "connect", traced)
    assert _run(tmp_path, path)[0] == 0
    assert len(calls) == 1
    database, kwargs = calls[0]
    assert database.startswith("file:") and database.endswith("?mode=ro")
    assert kwargs == {"uri": True, "timeout": 5}
    assert statements[0] == "PRAGMA query_only=ON"


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
def test_s1_writing_through_the_probe_connection_fails(tmp_path: Path, statement: str) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    with closing(probe.open_read_only(path)) as conn:
        assert conn.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute(statement)
        conn.execute("PRAGMA query_only=OFF")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute(statement)


def test_s1_a_missing_file_is_refused_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "nope.db"
    with pytest.raises(FileNotFoundError):
        probe.open_read_only(missing)
    assert not missing.exists()


def test_s1_a_directory_name_with_space_hash_and_percent_opens_read_only(
    tmp_path: Path,
) -> None:
    awkward = tmp_path / "my dir #1 %20"
    awkward.mkdir()
    path = _db(awkward)
    _stage_phantom(path)
    with closing(probe.open_read_only(path)) as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM playbook_directives")
    assert _run(tmp_path, path)[0] == 0


# ---------------------------------------------------------------- S2 (SELECT only)

SQL_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "ATTACH")
ALSO_FORBIDDEN = ("CREATE", "REPLACE", "VACUUM", "REINDEX", "DETACH")


def _script_tree() -> ast.Module:
    return ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))


def test_s2_every_sql_is_a_plain_module_constant_starting_with_select_or_with() -> None:
    constants: dict[str, str] = {}
    for node in _script_tree().body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id.endswith("_SQL"):
                assert isinstance(node.value, ast.Constant), target.id  # no f-string, no format
                assert isinstance(node.value.value, str)
                constants[target.id] = node.value.value
    assert len(constants) >= 20
    for name, sql in constants.items():
        if name == "S2_ELIGIBLE_BATCH_SQL":  # a predicate the queries restate, tested apart
            assert sql in constants["ELIGIBLE_BATCHES_SQL"]
            continue
        assert sql.strip().upper().startswith(("SELECT ", "WITH ")), name
        assert "{" not in sql and "%s" not in sql, name
        for word in SQL_KEYWORDS + ALSO_FORBIDDEN:
            assert not re.search(rf"\b{word}\b", sql, flags=re.IGNORECASE), (name, word)
        assert ";" not in sql, name


def test_s2_source_calls_only_execute_with_a_constant_and_no_write_api() -> None:
    tree = _script_tree()
    pragmas: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"executescript", "executemany", "commit", "rollback"}
            if node.func.attr == "execute":
                first = node.args[0]
                if isinstance(first, ast.IfExp):
                    branches = [first.body, first.orelse]
                    assert all(isinstance(b, ast.Name) and b.id.endswith("_SQL") for b in branches)
                elif isinstance(first, ast.Name):
                    assert first.id.endswith("_SQL"), first.id
                else:
                    assert isinstance(first, ast.Constant) and isinstance(first.value, str)
                    pragmas.append(first.value)
    assert pragmas == ["PRAGMA query_only=ON"]
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for word in SQL_KEYWORDS + ALSO_FORBIDDEN:
        assert not re.search(rf"\b{word}\b", source, flags=re.IGNORECASE), word
    assert source.upper().count("PRAGMA") >= 1
    assert len(re.findall(r"PRAGMA\s+\w+", source)) == 2  # the docstring mention and the call


def test_s2_only_select_statements_follow_the_one_pragma(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _rich_world(tmp_path)
    statements: list[str] = []
    real_connect = sqlite3.connect

    def traced(database: str, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(database, *args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(probe.sqlite3, "connect", traced)
    assert _run(tmp_path, path)[0] == 0
    assert statements[0] == "PRAGMA query_only=ON"
    assert len(statements) > 20
    for statement in statements[1:]:
        assert statement.lstrip().upper().startswith(("SELECT ", "WITH ")), statement


# ---------------------------------------------------------------- S3 / S4 (imports)

ALLOWED_IMPORTS = {
    "__future__",
    "argparse",
    "hashlib",
    "json",
    "os",
    "sqlite3",
    "sys",
    "io",
    "re",
    "dataclasses",
    "datetime",
    "decimal",
    "pathlib",
    "collections.abc",
    "contextlib",
    "typing",
}
NETWORK_MODULES = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "asyncio",
    "subprocess",
    "ftplib",
    "smtplib",
    "requests",
    "httpx",
    "aiohttp",
    "telnetlib",
    "xmlrpc",
}


def _imports() -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_script_tree()):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            assert node.module is not None
            modules.add(node.module)
    return modules


def test_s3_imports_are_inside_the_whitelist_and_never_app() -> None:
    modules = _imports()
    assert modules <= ALLOWED_IMPORTS, modules - ALLOWED_IMPORTS
    assert "app" not in {m.split(".")[0] for m in modules}


def test_s3_the_script_runs_under_python_isolated_mode_in_a_scratch_cwd(tmp_path: Path) -> None:
    path = _rich_world(tmp_path)
    cwd = tmp_path / "scratch"
    (cwd / "app").mkdir(parents=True)
    # Planted modules: an import of ``app`` or ``json`` from the cwd would raise.
    (cwd / "app" / "__init__.py").write_text("raise RuntimeError('app imported')\n")
    (cwd / "json.py").write_text("raise RuntimeError('cwd json imported')\n")
    out = tmp_path / "isolated-out"
    out.mkdir()
    done = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            str(SCRIPT_PATH),
            "--db-path",
            str(path),
            "--out-dir",
            str(out),
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PATH": "", "STOCK_DESK_SECRET": "must-not-matter"},
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.isascii() and "gate_affected_symbols=2" in done.stdout
    assert sorted(p.name for p in out.iterdir()) == ["report.json", "report.md"]
    assert (
        json.loads((out / "report.json").read_text(encoding="utf-8"))["gate"]["n177_affected_count"]
        == 2
    )


def test_s4_no_network_or_process_module_is_imported() -> None:
    roots = {m.split(".")[0] for m in _imports()}
    assert not roots & NETWORK_MODULES
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert not re.search(r"https?://", source)


# ---------------------------------------------------------------- S5 / S6 / S7


def test_s5_both_hashes_are_the_real_sha256_of_the_unchanged_file(tmp_path: Path) -> None:
    path = _rich_world(tmp_path)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    result = _report(tmp_path, path)
    assert result["meta"]["db_sha256_before"] == expected
    assert result["meta"]["db_sha256_after"] == expected
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def _fake_backend(tmp_path: Path) -> tuple[Path, Path]:
    backend = tmp_path / "backend"
    (backend / "data").mkdir(parents=True)
    production = backend / "data" / "stock-desk.db"
    PlaybookStore(db_path=production)
    return backend, production


def _snapshot_of(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_s6_the_production_db_path_is_refused_by_samefile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    backend, production = _fake_backend(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    before = _snapshot_of(backend)
    aliases = [
        production,
        backend / "data" / ".." / "data" / "stock-desk.db",
    ]
    link = tmp_path / "link.db"
    try:
        link.symlink_to(production)
        aliases.append(link)
    except (OSError, NotImplementedError):  # pragma: no cover - platform without symlinks
        pass
    for alias in aliases:
        code = probe.main(
            ["--db-path", str(alias), "--out-dir", str(out)],
            env={},
            now_utc=RUN_AT,
            today=AS_OF,
            backend_dir=backend,
        )
        assert code == 4
        assert "production DB" in capsys.readouterr().err
    assert list(out.iterdir()) == []
    assert _snapshot_of(backend) == before


def test_s6_the_path_named_by_the_environment_variable_is_refused_without_echoing_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    named = _db_in(tmp_path, "elsewhere-SECRET-7731")
    out = tmp_path / "out"
    out.mkdir()
    code = probe.main(
        ["--db-path", str(named), "--out-dir", str(out)],
        env={probe.DB_PATH_ENV_VAR: str(named)},
        now_utc=RUN_AT,
        today=AS_OF,
        backend_dir=tmp_path / "unrelated-backend",
    )
    captured = capsys.readouterr()
    assert code == 4
    assert "SECRET-7731" not in captured.err and "SECRET-7731" not in captured.out
    assert list(out.iterdir()) == []


def test_s6_the_production_data_folder_is_refused_as_out_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    backend, _production = _fake_backend(tmp_path)
    copy = _db(tmp_path)
    before = _snapshot_of(backend)
    code = probe.main(
        ["--db-path", str(copy), "--out-dir", str(backend / "data")],
        env={},
        now_utc=RUN_AT,
        today=AS_OF,
        backend_dir=backend,
    )
    assert code == 4
    assert "production data folder" in capsys.readouterr().err
    assert _snapshot_of(backend) == before
    # The folder that holds the env-named DB is a production folder as well.
    named_dir = tmp_path / "envdir"
    named_dir.mkdir()
    code = probe.main(
        ["--db-path", str(copy), "--out-dir", str(named_dir)],
        env={probe.DB_PATH_ENV_VAR: str(named_dir / "whatever.db")},
        now_utc=RUN_AT,
        today=AS_OF,
        backend_dir=backend,
    )
    assert code == 4
    assert list(named_dir.iterdir()) == []


def test_s6_the_real_backend_data_path_is_refused_before_anything_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default backend dir: refused by path comparison alone (the file is never read)."""

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the production path must be refused before any open")

    monkeypatch.setattr(probe.sqlite3, "connect", forbidden)
    monkeypatch.setattr(probe, "sha256_file", forbidden)
    out = tmp_path / "out"
    out.mkdir()
    code = probe.main(
        ["--db-path", str(BACKEND / "data" / "stock-desk.db"), "--out-dir", str(out)],
        env={},
        now_utc=RUN_AT,
        today=AS_OF,
    )
    assert code == 4
    assert "production DB" in capsys.readouterr().err
    assert list(out.iterdir()) == []


def test_s7_only_the_two_report_files_are_written_and_the_db_folder_is_untouched(
    tmp_path: Path,
) -> None:
    path = _rich_world(tmp_path)
    before_listing = {p.name for p in path.parent.iterdir()}
    before_bytes = path.read_bytes()
    out = tmp_path / "fresh-out"
    out.mkdir()
    assert (
        probe.main(
            ["--db-path", str(path), "--out-dir", str(out)], env={}, now_utc=RUN_AT, today=AS_OF
        )
        == 0
    )
    assert sorted(p.name for p in out.iterdir()) == ["report.json", "report.md"]
    assert {p.name for p in path.parent.iterdir()} - before_listing <= {
        "stock-desk.db-wal",
        "stock-desk.db-shm",
    }
    assert path.read_bytes() == before_bytes


def test_s7_an_existing_report_file_is_refused_and_left_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.json").write_text("precious", encoding="utf-8")
    assert _run(tmp_path, path)[0] == 4
    assert (out / "report.json").read_text(encoding="utf-8") == "precious"
    assert not (out / "report.md").exists()
    assert "already exists" in capsys.readouterr().err


def test_s7_the_report_files_are_opened_in_exclusive_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _db(tmp_path)
    modes: list[str] = []
    real_open = open

    def spy(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if "report." in str(file):
            modes.append(mode)
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", spy)
    assert _run(tmp_path, path)[0] == 0
    assert modes == ["x", "x"]


def test_s7_a_missing_or_non_directory_out_dir_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    missing = tmp_path / "no-such-folder"
    argv = ["--db-path", str(path), "--out-dir", str(missing)]
    assert probe.main(argv, env={}, now_utc=RUN_AT, today=AS_OF) == 4
    assert not missing.exists()
    plain = tmp_path / "file.txt"
    plain.write_text("x", encoding="utf-8")
    argv = ["--db-path", str(path), "--out-dir", str(plain)]
    assert probe.main(argv, env={}, now_utc=RUN_AT, today=AS_OF) == 4
    assert "--out-dir" in capsys.readouterr().err


def test_the_two_required_options_have_no_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(probe.DB_PATH_ENV_VAR, str(_db(tmp_path)))
    for argv in ([], ["--db-path", "x"], ["--out-dir", str(tmp_path)]):
        with pytest.raises(SystemExit) as raised:
            probe.main(argv)
        assert raised.value.code == 2
    with pytest.raises(SystemExit):
        probe.main(["--db-path", "x", "--out-dir", str(tmp_path), "--since", "yesterday"])


# ---------------------------------------------------------------- S8 / S9 / S10


def _scan(text: str) -> list[str]:
    """Words found after the one allowed label is removed (RC-3)."""
    return [w for w in FORBIDDEN_WORDS if w in text.replace(probe.MANUAL_LABEL, "")]


def test_s8_the_report_holds_facts_only_no_advice_words(tmp_path: Path) -> None:
    path = _rich_world(tmp_path)
    _code, _result, markdown = _run(tmp_path, path)
    json_text = (tmp_path / "out" / "report.json").read_text(encoding="utf-8")
    body = "\n".join(line for line in markdown.splitlines() if not line.startswith("- db_path"))
    assert _scan(body) == []
    assert _scan(json_text) == []
    assert probe.MANUAL_LABEL in body  # the label is used, and only the label
    assert probe.MANUAL_LABEL == "需人工判讀"
    assert _scan("這需要") == ["需"] and _scan("需人工判讀") == []
    lowered = body.lower()
    for english in ("recommend", "should", "suggest", "must "):
        assert english not in lowered, english


def test_s8_every_string_constant_of_the_script_is_clean() -> None:
    checked = 0
    for node in ast.walk(_script_tree()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert _scan(node.value) == [], node.value[:60]
            checked += 1
    assert checked > 100


def test_s8_db_free_text_never_reaches_the_report(tmp_path: Path) -> None:
    """RC-3: a rule summary or a price column with advice words is cut down to a token."""
    path = _db(tmp_path)
    _stage_phantom(path, price="建議務必安全", settled_at="應盡快否則")
    _row(
        path,
        symbol="2317",
        batch_no=1,
        rule_id="M1",
        action="defer",
        data_date="2026-09-10",
        rule_summary="M1｜" + probe.INDEX_GAP_MARKER + "對應需建議）本批順延第 1 次。",
    )
    _row(
        path,
        symbol="2330",
        batch_no=1,
        rule_id="M1",
        action="defer",
        data_date="2026-09-11",
        rule_summary="M1｜" + probe.INDEX_GAP_MARKER + "cached_stale）本批順延第 1 次。",
    )
    code, result, markdown = _run(tmp_path, path)
    assert code == 0
    json_text = (tmp_path / "out" / "report.json").read_text(encoding="utf-8")
    assert _scan(markdown) == [] and _scan(json_text) == []
    statuses = {d["data_date"]: d["index_status"] for d in result["n190"]["m1_unevaluated_days"]}
    assert statuses == {
        "2026-09-10": [probe.UNEXPECTED_TOKEN],
        "2026-09-11": ["cached_stale"],
    }
    assert "本批順延" not in markdown and "本批順延" not in json_text
    (item,) = _affected(result)
    assert item["first_s2"]["settled_open_price"] == probe.UNEXPECTED_TOKEN
    assert item["first_s2"]["settled_at"] == probe.UNEXPECTED_TOKEN


def test_sanitize_keeps_fixed_wording_and_tokens_only() -> None:
    cleaned = probe.sanitize(
        {
            "verdict": "可試算 中文",
            "symbol": "2330",
            "free": "自由文字",
            "long": "x" * 65,
            "nested": [{"detail": "固定句", "other": "另一句"}],
            "n": 3,
            "none": None,
        }
    )
    assert cleaned == {
        "verdict": "可試算 中文",
        "symbol": "2330",
        "free": probe.UNEXPECTED_TOKEN,
        "long": probe.UNEXPECTED_TOKEN,
        "nested": [{"detail": "固定句", "other": probe.UNEXPECTED_TOKEN}],
        "n": 3,
        "none": None,
    }


# ---------------------------------------------------------------- RC-4 / RC-5


def _risk_sentences() -> list[str]:
    """The three sentences risk control fixed, cut out of the review file between quotes."""
    text = RISK_REVIEW.read_text(encoding="utf-8")
    segment = text[text.index("**RC-4") : text.index("- 自查")]
    return re.findall(r"^「(.+)」$", segment, flags=re.MULTILINE)


def test_rc4_the_three_sentences_equal_the_risk_review_verbatim() -> None:
    gate, note, legend = _risk_sentences()
    assert probe.GATE_LINE_TEMPLATE == gate
    assert probe.TRIAL_NOTE == note
    assert probe.TRIAL_LEGEND == legend
    assert gate.count("{") == 1 and "{n}" in gate


def test_rc4_the_sentences_sit_where_risk_control_put_them(tmp_path: Path) -> None:
    gate, note, legend = _risk_sentences()
    path = _rich_world(tmp_path)
    _code, result, markdown = _run(tmp_path, path)
    assert markdown.count(gate.format(n=2)) == 1
    assert markdown.count(note) == 1 and markdown.count(legend) == 1
    assert markdown.index(legend) < markdown.index("## N177-A")
    assert markdown.index(note) > markdown.index("## N177-A")
    assert markdown.index(note) < markdown.index("| 標的 | 第一張 S2 id |")
    assert result["gate"]["n177_affected_count"] == 2


def test_rc5_an_out_dir_inside_a_git_work_tree_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    linked = tmp_path / "linked"
    (linked / "sub").mkdir(parents=True)
    (linked / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")  # a linked work tree
    for folder in (repo, nested, linked / "sub"):
        code = probe.main(
            ["--db-path", str(path), "--out-dir", str(folder)],
            env={},
            now_utc=RUN_AT,
            today=AS_OF,
        )
        assert code == 4
        assert "git work tree" in capsys.readouterr().err
        assert not (folder / "report.md").exists()
    assert probe.inside_git_work_tree(tmp_path / "plain") is False


def test_rc6_the_module_documents_that_the_report_is_private() -> None:
    doc = ast.get_docstring(_script_tree()) or ""
    assert "holds holdings and cash" in doc and "never commit it" in doc


def test_s9_no_env_file_and_no_environment_value_is_read_or_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert not re.search(r"\.env\b", source) and "dotenv" not in source and "getenv" not in source
    assert re.findall(r"\bos\.environ\b", source) == ["os.environ"]  # the default mapping only
    path = _rich_world(tmp_path)
    env = {
        "STOCK_DESK_API_KEY": "sk-live-9f3a",
        "TWSE_TOKEN": "tok-5521",
        probe.DB_PATH_ENV_VAR: str(tmp_path / "some-other" / "stock-desk.db"),
    }
    out = tmp_path / "out"
    out.mkdir()
    code = probe.main(
        ["--db-path", str(path), "--out-dir", str(out)], env=env, now_utc=RUN_AT, today=AS_OF
    )
    assert code == 0
    printed = capsys.readouterr()
    written = (out / "report.md").read_text(encoding="utf-8") + (out / "report.json").read_text(
        encoding="utf-8"
    )
    for secret in ("sk-live-9f3a", "tok-5521", "some-other"):
        assert secret not in printed.out + printed.err + written


def test_s10_two_runs_on_one_db_give_identical_reports_except_run_at(tmp_path: Path) -> None:
    path = _rich_world(tmp_path)
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    for folder, moment in ((first, RUN_AT), (second, datetime(2026, 11, 7, 18, 30, tzinfo=UTC))):
        assert (
            probe.main(
                ["--db-path", str(path), "--out-dir", str(folder)],
                env={},
                now_utc=moment,
                today=AS_OF,
            )
            == 0
        )

    def strip_md(text: str) -> str:
        return "\n".join(line for line in text.splitlines() if not line.startswith("- run_at_utc"))

    assert strip_md((first / "report.md").read_text(encoding="utf-8")) == strip_md(
        (second / "report.md").read_text(encoding="utf-8")
    )
    one = json.loads((first / "report.json").read_text(encoding="utf-8"))
    two = json.loads((second / "report.json").read_text(encoding="utf-8"))
    assert one["meta"].pop("run_at_utc") != two["meta"].pop("run_at_utc")
    assert one == two


def test_s10_json_has_sorted_keys_and_money_as_strings(tmp_path: Path) -> None:
    path = _rich_world(tmp_path)
    _report(tmp_path, path)
    text = (tmp_path / "out" / "report.json").read_text(encoding="utf-8")
    parsed = json.loads(text)
    assert text == json.dumps(parsed, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    item = _affected(parsed)[0]
    assert isinstance(item["trial"]["cash"], str) and isinstance(item["trial"]["price"], str)
    for candidate in parsed["n190"]["stop_loss_candidates"]:
        for field in ("close", "cost", "threshold", "close_over_cost"):
            assert isinstance(candidate[field], str)
    assert "\r" not in text


# ---------------------------------------------------------------- S11 (aligned copies)


def test_s11_index_gap_marker_is_the_text_before_the_status_in_the_engine_note() -> None:
    assert probe.INDEX_GAP_MARKER == wording.INDEX_GAP_DEFER_NOTE.split("{status}")[0]


def test_s11_rule_param_defaults_match_rule_params() -> None:
    defaults = RuleParams(effective_date=date(2026, 1, 1))
    assert Decimal(probe.DEFAULT_S1_RATIO) == defaults.s1_ratio
    assert Decimal(probe.DEFAULT_S1_DEFENSE_RATIO) == defaults.s1_defense_ratio
    assert Decimal(probe.DEFAULT_S2_RATIO) == defaults.s2_ratio
    assert store.system_default_params(date(2026, 1, 1)) == defaults


def test_s11_demo_source_and_index_keys_match_the_app() -> None:
    assert probe.DEMO_SOURCE == DEMO_SOURCE == vars(engine)["DEMO_SOURCE"]
    from app.playbook import service

    assert probe.INDEX_MARKET == service.PLAYBOOK_MARKET


def test_s11_the_state_and_table_names_the_probe_reads_exist_in_the_store() -> None:
    assert store.STATE_TOTAL_DEPLOY_SET_AT == "total_deploy_set_at"
    assert store.STATE_FAST_MARKET_MEASURED_ON == "fast_market_measured_on"
    assert store.STATE_DEFENSE_ACTIVE == "defense_active"
    assert store.STATE_DEFENSE_SINCE == "defense_since"
    schema = "\n".join(store._SCHEMA)
    for table in probe.REPORT_TABLES:
        if table.startswith("playbook_") and table != probe.FILL_MOVES_TABLE:
            assert f"CREATE TABLE IF NOT EXISTS {table} " in schema, table


def _assert_s2_constants_align(module: Any) -> None:
    entry = module.S2_FILL_ENTRY
    assert (probe.S2_ENTRY_STATUS, probe.S2_ENTRY_ACTION, probe.S2_ENTRY_RULE_ID) == (
        entry.status,
        entry.action,
        entry.rule_id,
    )
    assert probe.S2_ELIGIBLE_BATCH_SQL == module.S2_ELIGIBLE_BATCH_SQL
    assert probe.FILL_MOVES_TABLE == module.FILL_MOVES_TABLE
    # Whitespace is normalised on both sides: the probe SQL is laid out over several lines.
    wanted = " ".join(module.s2_fill_entry_sql("d").split())
    for sql in (probe.S2_UNAUDITED_SQL, probe.S2_UNAUDITED_NO_TABLE_SQL):
        assert wanted in " ".join(sql.split())


def test_s11_the_s2_constants_equal_the_store_once_n177a_defines_them() -> None:
    module: Any = store
    if not hasattr(module, "S2_FILL_ENTRY"):
        pytest.skip("N-177a is not merged: the store has no S2_FILL_ENTRY yet")
    _assert_s2_constants_align(module)


def test_s11_the_alignment_check_passes_against_the_spec_shaped_constants() -> None:
    """A stand-in for N-177a section 4.2, so the check is known to pass once it lands."""
    from types import SimpleNamespace

    entry = SimpleNamespace(status="executed", action="sell", rule_id="S2")

    def s2_fill_entry_sql(alias: str) -> str:
        assert alias.isidentifier()
        return (
            f"{alias}.status = 'executed' AND {alias}.action = 'sell' AND "
            f"{alias}.rule_id = 'S2' AND {alias}.batch_no IS NULL"
        )

    fake = SimpleNamespace(
        S2_FILL_ENTRY=entry,
        S2_ELIGIBLE_BATCH_SQL=(
            "b.status = 'open' AND b.remaining_shares > 0 AND b.cost IS NOT NULL"
        ),
        FILL_MOVES_TABLE="playbook_fill_moves",
        s2_fill_entry_sql=s2_fill_entry_sql,
    )
    _assert_s2_constants_align(fake)
    fake.S2_ELIGIBLE_BATCH_SQL += " AND 1"
    with pytest.raises(AssertionError):
        _assert_s2_constants_align(fake)


def test_s11_the_probe_sql_restates_its_own_constants() -> None:
    entry = (
        f"d.status = '{probe.S2_ENTRY_STATUS}' AND d.action = '{probe.S2_ENTRY_ACTION}' AND "
        f"d.rule_id = '{probe.S2_ENTRY_RULE_ID}' AND d.batch_no IS NULL"
    )
    flat = " ".join(probe.S2_UNAUDITED_SQL.split())
    assert entry in flat
    assert entry in " ".join(probe.S2_UNAUDITED_NO_TABLE_SQL.split())
    assert probe.S2_ELIGIBLE_BATCH_SQL in " ".join(probe.ELIGIBLE_BATCHES_SQL.split())
    assert f"FROM {probe.FILL_MOVES_TABLE} AS m" in probe.S2_UNAUDITED_SQL
    assert probe.FILL_MOVES_TABLE not in probe.S2_UNAUDITED_NO_TABLE_SQL.replace("x", "x")


def test_s11_eligible_batch_query_matches_the_engine_average_cost_parity(tmp_path: Path) -> None:
    """The probe's eligible set equals the batches ``_symbol_average_cost`` counts."""
    rng = random.Random(20261107)
    path = _db(tmp_path, with_bars=False)
    symbols = ["2330", "2317", "2454"]
    expected: dict[str, list[BatchState]] = {s: [] for s in symbols}
    for symbol in symbols:
        for batch_no in range(1, 200):
            status = rng.choice(["planned", "open", "closed", "skipped"])
            cost = rng.choice([None, Decimal("0"), Decimal(rng.randint(1, 900))])
            remaining = rng.randint(0, 300)
            _batch(
                path,
                symbol=symbol,
                batch_no=batch_no,
                status=status,
                cost=None if cost is None else str(cost),
                remaining_shares=remaining,
                shares=remaining,
            )
            expected[symbol].append(
                BatchState(
                    symbol=symbol,
                    batch_no=batch_no,
                    status=status,  # type: ignore[arg-type]
                    cost=cost,
                    shares=remaining,
                    remaining_shares=remaining,
                )
            )
    with closing(probe.open_read_only(path)) as conn:
        found = probe.load(conn, since=None, until=AS_OF).eligible
    counted = 0
    for symbol in symbols:
        _average, shares = engine._symbol_average_cost(expected[symbol])
        assert sum(b.remaining_shares for b in found.get(symbol, [])) == shares
        numbers = {
            b.batch_no
            for b in expected[symbol]
            if b.status == "open" and b.cost is not None and b.remaining_shares > 0
        }
        assert {b.batch_no for b in found.get(symbol, [])} == numbers
        counted += len(numbers)
    assert counted > 30


def test_s11_the_marker_selects_exactly_the_index_gap_lines(tmp_path: Path) -> None:
    path = _db(tmp_path)
    ids = _stage_m1(path)
    with closing(probe.open_read_only(path)) as conn:
        snapshot = probe.load(conn, since=None, until=AS_OF)
    assert {r.id for r in snapshot.m1_rows} == {
        ids["a"],
        ids["b"],
        ids["dup"],
        ids["skip"],
        ids["nobar"],
    }


# ---------------------------------------------------------------- review follow-ups


def test_s1_enumerated_columns_print_only_known_values_and_the_count_is_reported(
    tmp_path: Path,
) -> None:
    path = _db(tmp_path)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "INSERT INTO playbook_blacklist (symbol, triggered_on, until, rule_id) "
            "VALUES ('2330', '2026-08-12', '2026-12-31', 'a harmless English sentence')"
        )
        conn.execute(
            "INSERT INTO playbook_blacklist (symbol, triggered_on, until, rule_id) "
            "VALUES ('2317', '2026-08-12', '2026-12-31', 'S2')"
        )
    _executed(path, symbol="2454", batch_no=3, rule_id="ZZ9", action="sell")
    code, result, markdown = _run(tmp_path, path)
    assert code == 0
    by_symbol = {r["symbol"]: r for r in result["n177"]["blacklist"]}
    assert by_symbol["2330"]["rule_id"] == probe.ENUM_UNEXPECTED == "（非預期值）"
    assert by_symbol["2317"]["rule_id"] == "S2"
    (missing,) = result["n177"]["missing_batch_rows"]
    assert (missing["rule_id"], missing["action"]) == (probe.ENUM_UNEXPECTED, "sell")
    assert result["meta"]["unexpected_enum_values"] == 2
    assert "中的非預期值個數（D-9 用到的列另見理由句）：2" in markdown
    assert "harmless English" not in markdown and "ZZ9" not in markdown


def test_s1_a_clean_book_reports_zero_unexpected_enum_values(tmp_path: Path) -> None:
    result = _report(tmp_path, _rich_world(tmp_path))
    assert result["meta"]["unexpected_enum_values"] == 0


def test_s1_the_sanitize_enum_rules() -> None:
    counter = [0]
    cleaned = probe.sanitize(
        {
            "rule_id": "R1",
            "action": "buy",
            "status": "weird",
            "source": "twse",
            "other": "plain",
            "list": [{"status": "open"}, {"status": 5}],
        },
        None,
        counter,
    )
    assert cleaned == {
        "rule_id": "R1",
        "action": "buy",
        "status": probe.ENUM_UNEXPECTED,
        "source": probe.ENUM_UNEXPECTED,
        "other": "plain",
        "list": [{"status": "open"}, {"status": 5}],
    }
    assert counter == [2]


def test_s2_demo_index_bars_do_not_enter_the_calendar_or_the_cache_fact(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    for day in ("2026-08-10", "2026-08-12"):
        _bar(path, "^TWII", day)
    _bar(path, "^TWII", "2026-08-11", source=DEMO_SOURCE)
    _blacklist(path, "2330", "2026-08-12")
    (row,) = _report(tmp_path, path)["n177"]["blacklist"]
    assert row["trading_day_difference"] == 1  # only 08-12 counts; the demo bar of 08-11 does not
    with closing(probe.open_read_only(path)) as conn:
        snapshot = probe.load(conn, since=None, until=AS_OF)
    assert sorted(snapshot.index_bars) == ["2026-08-10", "2026-08-12"]


def test_s4_a_non_positive_cost_is_left_out_of_the_whole_symbol_average(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _batch(path, symbol="2317", batch_no=1, entry_date="2026-09-01", cost="-50")
    _batch(path, symbol="2317", batch_no=2, entry_date="2026-09-01", cost="50")
    _bar(path, "2317", "2026-09-02", "-1")
    result = _report(tmp_path, path)  # an average of 0 would divide by zero
    (row,) = [c for c in _candidates(result) if c["category"] == probe.CAT_S2]
    assert row["cost"] == "50"  # the batch with a positive cost alone
    assert result["n190"]["stats"]["unusable_cost_batches"] >= 1


def test_s5_a_previous_json_with_missing_fields_exits_two_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    bad = tmp_path / "prev.json"
    bad.write_text(
        json.dumps({"schema_version": 1, "n177": {"affected": [{"symbol": "2330"}]}}),
        encoding="utf-8",
    )
    assert _run(tmp_path, path, "--previous-json", str(bad))[0] == 2
    err = capsys.readouterr().err
    assert "cannot build the report (KeyError)" in err and err.isascii()
    assert list((tmp_path / "out").iterdir()) == []


def test_s5_dirty_data_in_the_db_exits_two_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _db(tmp_path)
    _batch(path, batch_no="CELL-VALUE-7731")  # type: ignore[arg-type]
    assert _run(tmp_path, path)[0] == 2
    err = capsys.readouterr().err
    assert "cannot read the DB" in err and err.isascii()
    assert "CELL-VALUE-7731" not in err and "ValueError" in err
    assert list((tmp_path / "out").iterdir()) == []


def test_s3_the_wal_sidecar_caveat_is_in_the_docstring_and_the_limitations() -> None:
    doc = ast.get_docstring(_script_tree()) or ""
    assert "-shm" in doc and "main file" in doc
    assert "-shm" in probe.LIMITATIONS["L8"] and "主檔" in probe.LIMITATIONS["L8"]


def test_d9_a_row_with_an_unexpected_enum_value_withholds_the_trial(tmp_path: Path) -> None:
    """Risk control D-9: any row feeding the judgement with a value outside the set."""
    path = _db(tmp_path)
    _stage_phantom(path)
    odd = _executed(path, batch_no=3, rule_id="ZZ9", action="buy", execution_date="2026-08-12")
    item = _manual(_report(tmp_path, path))
    assert item["guards"] == ["G-a", "D-9"]
    assert item["reasons"][-1]["code"] == "D-9"
    assert item["reasons"][-1]["detail"].endswith(f"ids={odd}")


def test_d9_in_flight_row_and_s2_status_with_unknown_values(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    _row(path, action="sell", rule_id="ZZ9", batch_no=1, execution_date="2026-08-20")
    item = _manual(_report(tmp_path, path))
    assert item["guards"] == ["D-9"]
    other = _db_in(tmp_path, "second")
    _stage_phantom(other)
    _row(
        other,
        action="sell",
        rule_id="S2",
        batch_no=None,
        status="vanished",
        execution_date="2026-08-14",
    )
    assert _manual(_report_in(tmp_path, other))["guards"] == ["D-9"]


def _report_in(tmp_path: Path, db: Path) -> dict[str, Any]:
    code, result, _md = _run(tmp_path, db, name="second-out")
    assert code == 0
    return result


def test_d9_known_values_leave_the_trial_alone(tmp_path: Path) -> None:
    path = _db(tmp_path)
    _stage_phantom(path)
    (item,) = _affected(_report(tmp_path, path))
    assert item["guards"] == [] and item["trial"] is not None
