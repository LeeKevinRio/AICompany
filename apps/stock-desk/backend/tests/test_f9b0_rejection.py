"""F-9b0 commit 0-1: ``ProviderResult.rejection`` and its invariant (ADR-0024 D-7 (2)).

The field is internal: a refused answer is always ``UNAVAILABLE`` with no bars
(C-34 (a)), it never reaches ``LoadedBars.meta()`` or any API schema (C-18),
and in F-9b0 nothing in ``app`` produces a non-``None`` value yet -- the
producers arrive with the gate itself (F-9b).
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from app.data.interface import DataStatus, PriceBar, ProviderResult, Rejection
from app.main import app
from app.services.market import LoadedBars

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
_AT = datetime(2024, 1, 2, 8, 0, tzinfo=UTC)
REJECTIONS: tuple[Rejection, ...] = get_args(Rejection)


def _bar() -> PriceBar:
    return PriceBar(
        symbol="2330",
        market="TW",
        date=date(2024, 1, 2),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        volume=1,
        currency="TWD",
        as_of=_AT,
        source="twse",
    )


def _result(*, status: DataStatus, with_bars: bool, rejection: Rejection | None) -> ProviderResult:
    return ProviderResult(
        bars=[_bar()] if with_bars else [],
        status=status,
        as_of=_AT,
        source="twse" if with_bars else "none",
        rejection=rejection,
    )


def test_the_four_categories_are_exactly_the_adr_ones() -> None:
    assert set(REJECTIONS) == {
        "symbol_not_admitted",
        "unit_mismatch",
        "unit_missing",
        "cache_unit_rejected",
    }


def test_rejection_defaults_to_none() -> None:
    result = ProviderResult(bars=[], status=DataStatus.UNAVAILABLE, as_of=_AT, source="none")
    assert result.rejection is None


#: The four ways to break "rejection set => UNAVAILABLE and no bars".
VIOLATIONS = [
    pytest.param(DataStatus.UNAVAILABLE, True, id="unavailable-with-bars"),
    pytest.param(DataStatus.FRESH, True, id="fresh-with-bars"),
    pytest.param(DataStatus.BACKUP, False, id="backup-without-bars"),
    pytest.param(DataStatus.CACHED_STALE, True, id="cached-stale-with-bars"),
]


@pytest.mark.parametrize("rejection", REJECTIONS)
@pytest.mark.parametrize(("status", "with_bars"), VIOLATIONS)
def test_a_rejection_beside_bars_or_outside_unavailable_raises(
    status: DataStatus, with_bars: bool, rejection: Rejection
) -> None:
    with pytest.raises(ValidationError, match="rejection is only allowed"):
        _result(status=status, with_bars=with_bars, rejection=rejection)


@pytest.mark.parametrize("rejection", REJECTIONS)
@pytest.mark.parametrize("status", [s for s in DataStatus if s is not DataStatus.UNAVAILABLE])
@pytest.mark.parametrize("with_bars", [True, False])
def test_every_non_unavailable_status_refuses_a_rejection(
    status: DataStatus, with_bars: bool, rejection: Rejection
) -> None:
    with pytest.raises(ValidationError):
        _result(status=status, with_bars=with_bars, rejection=rejection)


@pytest.mark.parametrize("rejection", REJECTIONS)
def test_a_refused_answer_is_unavailable_with_no_bars(rejection: Rejection) -> None:
    result = _result(status=DataStatus.UNAVAILABLE, with_bars=False, rejection=rejection)
    assert result.rejection == rejection
    assert result.bars == []


@pytest.mark.parametrize("status", list(DataStatus))
@pytest.mark.parametrize("with_bars", [True, False])
def test_no_rejection_is_allowed_on_every_answer(status: DataStatus, with_bars: bool) -> None:
    """The converse does not hold: an ordinary empty failure has ``rejection=None`` (R-57)."""
    result = _result(status=status, with_bars=with_bars, rejection=None)
    assert result.rejection is None


def test_meta_key_set_is_unchanged() -> None:
    """C-18: the ``data`` block every bar endpoint echoes gains no key."""
    assert set(LoadedBars().meta()) == {
        "status",
        "source",
        "staleness_minutes",
        "is_within_ttl",
        "bar_count",
        "first_bar_date",
        "last_bar_date",
        "trading_days_behind",
        "reason",
    }


def test_no_api_schema_mentions_rejection() -> None:
    """C-18: the whole OpenAPI document, every path and component, never says ``rejection``."""
    document = json.dumps(app.openapi(), ensure_ascii=False)
    assert "rejection" not in document


def _producer_sites() -> list[str]:
    """Every ``ProviderResult(..., rejection=...)`` / ``model_copy`` that sets it, under ``app``."""
    found: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name == "ProviderResult" and any(k.arg == "rejection" for k in node.keywords):
                found.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}")
            if name == "model_copy" and "'rejection'" in ast.unparse(node):
                found.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}")
    return found


def test_nothing_produces_a_rejection_before_the_gate_lands() -> None:
    """F-9b0 is behaviour-neutral: the producers are F-9b's (TA5 section 3, commit 0-1)."""
    assert _producer_sites() == []
