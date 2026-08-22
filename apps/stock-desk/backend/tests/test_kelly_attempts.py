"""The import-attempt log: append-only, refusals included, never rewritten."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.kelly import attempts as attempts_module
from app.kelly.attempts import KellyAttemptStore
from app.kelly.models import KellyAttemptRecord

_NOW = datetime(2026, 8, 19, 3, 0, tzinfo=UTC)


def _attempt(
    *,
    symbol: str = "2330",
    market: str = "TW",
    strategy_id: str = "ma_cross",
    spec_hash: str = "a" * 64,
    outcome: str = "ok",
    reason_code: str | None = None,
) -> KellyAttemptRecord:
    return KellyAttemptRecord.model_validate(
        {
            "symbol": symbol,
            "market": market,
            "strategy_id": strategy_id,
            "request_spec": '{"symbol":"2330","market":"TW"}',
            "spec_hash": spec_hash,
            "outcome": outcome,
            "reason_code": reason_code,
            "win_rate": 0.6 if outcome == "ok" else None,
            "payoff_ratio": 2.0 if outcome == "ok" else None,
            "kelly_fraction": 0.4 if outcome == "ok" else None,
            "oos_round_trips": 24,
            "oos_win_trips": 14,
            "oos_loss_trips": 10,
            "oos_excluded_boundary_trips": 2,
            "oos_open_trip_at_end": 1,
            "oos_start_date": "2025-01-02",
            "oos_end_date": "2026-06-30",
            "oos_observations": 372,
            "f_star_ci_low": -0.05,
            "f_star_ci_high": 0.61,
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> KellyAttemptStore:
    return KellyAttemptStore(db_path=tmp_path / "kelly.db")


def test_an_attempt_is_appended_with_every_column(store: KellyAttemptStore) -> None:
    new_id = store.append(_attempt(), attempted_at=_NOW)

    with closing(sqlite3.connect(store.db_path)) as conn:
        row = conn.execute(
            "SELECT symbol, market, strategy_id, spec_hash, outcome, reason_code,"
            " win_rate, oos_round_trips, oos_end_date, f_star_ci_low, attempted_at"
            " FROM kelly_import_attempts WHERE id = ?",
            (new_id,),
        ).fetchone()

    assert row == (
        "2330",
        "TW",
        "ma_cross",
        "a" * 64,
        "ok",
        None,
        0.6,
        24,
        "2026-06-30",
        -0.05,
        _NOW.isoformat(),
    )


def test_a_refused_attempt_is_counted_too(store: KellyAttemptStore) -> None:
    """D-3: the 422 path is the common one, and it is the point of the log."""
    store.append(_attempt(outcome="rejected", reason_code="low_round_trips"))

    assert store.k_observed("2330", "TW") == 1


def test_k_observed_spans_every_strategy_and_has_no_time_window(
    store: KellyAttemptStore,
) -> None:
    store.append(_attempt(strategy_id="ma_cross"), attempted_at=_NOW - timedelta(days=900))
    store.append(_attempt(strategy_id="rsi_reversion"), attempted_at=_NOW)
    store.append(
        _attempt(outcome="rejected", reason_code="pb_none", strategy_id="donchian"),
        attempted_at=_NOW,
    )

    assert store.k_observed("2330", "TW") == 3


def test_k_distinct_specs_counts_the_search_not_the_repetition(
    store: KellyAttemptStore,
) -> None:
    store.append(_attempt(spec_hash="a" * 64))
    store.append(_attempt(spec_hash="a" * 64))
    store.append(_attempt(spec_hash="b" * 64))

    assert store.k_observed("2330", "TW") == 3
    assert store.k_distinct_specs("2330", "TW") == 2


def test_the_counts_are_per_instrument(store: KellyAttemptStore) -> None:
    store.append(_attempt(symbol="2330", market="TW"))
    store.append(_attempt(symbol="AAPL", market="US"))

    assert store.k_observed("2330", "TW") == 1
    assert store.k_observed("AAPL", "US") == 1
    assert store.k_observed("AAPL", "TW") == 0
    assert store.k_distinct_specs("2317", "TW") == 0


def test_the_counts_normalise_the_symbol(store: KellyAttemptStore) -> None:
    store.append(_attempt(symbol=" aapl ", market="US"))

    assert store.k_observed("AAPL", "US") == 1
    assert store.k_observed("aapl", "US") == 1


def test_an_ok_attempt_may_not_carry_a_reason_code() -> None:
    with pytest.raises(ValidationError, match="reason_code"):
        _attempt(outcome="ok", reason_code="pb_none")


def test_a_refused_attempt_must_carry_a_reason_code() -> None:
    with pytest.raises(ValidationError, match="reason_code"):
        _attempt(outcome="rejected", reason_code=None)


def test_the_module_contains_no_statement_that_rewrites_or_removes_a_row() -> None:
    """約束 35, checkable by reading one file: the log is append-only.

    A narrow, well-meant edit path is exactly how ``K_observed`` would start
    disagreeing with what the user actually did, so the guard is on the source
    rather than on any one method.
    """
    source = Path(attempts_module.__file__).read_text(encoding="utf-8")

    assert re.search(r"\b(UPDATE|DELETE|REPLACE|DROP)\b", source) is None
