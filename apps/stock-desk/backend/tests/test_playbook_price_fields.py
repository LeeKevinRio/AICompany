"""風控 required R19: the two price-field tracks stay separate, in both directions.

R19 keeps two allowlists rather than one shared vocabulary: the advice card may
read exactly one raw price (``close``, and that allowlist may not grow), while
the playbook declares its own table in :mod:`app.playbook.price_fields`, with a
per-item note on whether the *input* carries a market view.

Both directions are asserted here, because a one-way check would let the leak
travel the other way:

* no playbook price field appears in an advice payload, and
* the advice price field appears in no playbook 指令 payload.

The table is also checked for completeness against the real payload models, so a
new price column on a directive cannot ship without being classified.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.advice.context import KNOWN_FIELDS, PRICE_FIELD_ALLOWLIST
from app.advice.engine import build_advice
from app.advice.limits import PortfolioContext
from app.playbook.models import BatchSnapshot, Directive
from app.playbook.price_fields import (
    DIRECTIVE_PRICE_FIELDS,
    PLAYBOOK_PRICE_FIELDS,
    SNAPSHOT_PRICE_FIELDS,
)
from tests.advice_helpers import reported_net_worth, uptrend_signals

#: Anything whose name ends this way is a price level on a payload model.
_PRICE_SUFFIXES = ("price", "close", "cost", "low", "high")


def _advice_card() -> dict[str, Any]:
    portfolio = PortfolioContext(
        symbol="2330",
        total_equity_twd=1_000_000.0,
        position_market_value_twd=50_000.0,
        position_cost_twd=45_000.0,
        gross_exposure_twd=500_000.0,
        net_worth=reported_net_worth(1_000_000.0),
        book_fully_valued=True,
        quantity=500.0,
        close=110.0,
    )
    return build_advice(symbol="2330", signals=uptrend_signals(), portfolio=portfolio)


def _keys(payload: Any) -> set[str]:
    """Every key name anywhere in a nested payload."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(str(key))
            found |= _keys(value)
    elif isinstance(payload, list):
        for item in payload:
            found |= _keys(item)
    return found


def _directive() -> Directive:
    return Directive(
        symbol="2330",
        batch_no=1,
        action="buy",
        shares=100,
        rule_id="R1",
        rule_summary="R1 排程日進場",
        data_date=date(2026, 8, 11),
        execution_date=date(2026, 8, 12),
        reference_price=Decimal("100"),
        limit_low=Decimal("98"),
        limit_high=Decimal("102"),
        limit_note="限價帶",
        data_status="fresh",
        source="twse",
    )


def test_the_advice_price_allowlist_is_still_exactly_one_field() -> None:
    """R19: advice 維持長度 1 不得新增."""
    assert PRICE_FIELD_ALLOWLIST == frozenset({"close"})
    assert len(PRICE_FIELD_ALLOWLIST) == 1
    assert PRICE_FIELD_ALLOWLIST <= KNOWN_FIELDS


def test_the_two_tables_share_no_field_name_on_the_instruction_payload() -> None:
    """雙軌隔離：指令的價位欄位與建議的價位欄位沒有同名項."""
    assert DIRECTIVE_PRICE_FIELDS & PRICE_FIELD_ALLOWLIST == frozenset()


def test_no_playbook_price_field_appears_in_an_advice_payload() -> None:
    card_keys = _keys(_advice_card())
    leaked = sorted(set(PLAYBOOK_PRICE_FIELDS) & card_keys)
    assert leaked == [], f"playbook 價位欄位 {leaked} 出現在建議卡 payload"


def test_the_advice_price_field_appears_in_no_playbook_instruction_payload() -> None:
    directive_keys = _keys(_directive().model_dump())
    leaked = sorted(PRICE_FIELD_ALLOWLIST & directive_keys)
    assert leaked == [], f"建議價位欄位 {leaked} 出現在指令 payload"


def test_every_price_field_of_the_real_payloads_is_declared_in_the_table() -> None:
    """A new price column has to be classified, not just added."""
    directive_prices = {
        name
        for name in Directive.model_fields
        if name.endswith(_PRICE_SUFFIXES)
    }
    snapshot_prices = {
        name
        for name in BatchSnapshot.model_fields
        if name.endswith(_PRICE_SUFFIXES)
    }
    assert directive_prices == set(DIRECTIVE_PRICE_FIELDS)
    assert snapshot_prices == set(SNAPSHOT_PRICE_FIELDS)


def test_no_playbook_price_input_carries_a_market_view() -> None:
    """R19 的重點欄位：任何一項標成 True 都必須先過風控，測試會擋下來."""
    with_view = sorted(
        name for name, spec in PLAYBOOK_PRICE_FIELDS.items() if spec.contains_market_view
    )
    assert with_view == [], f"{with_view} 的輸入含市場觀點，R19 不允許進入指令價位欄位"


def test_every_declared_field_states_where_its_number_comes_from() -> None:
    for name, spec in PLAYBOOK_PRICE_FIELDS.items():
        assert spec.input_source.strip(), name
        assert spec.label.strip(), name
