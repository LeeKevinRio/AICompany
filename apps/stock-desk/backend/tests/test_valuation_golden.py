"""Golden tests for the P&L decomposition: fixed inputs, hand-computed outputs.

Each case pins exact ``Decimal`` outputs and asserts the attribution identity
``asset_contribution + fx_contribution == total`` holds exactly.
"""

from __future__ import annotations

from decimal import Decimal

from app.portfolio.valuation import decompose


def test_tw_stock_pure_asset_gain_no_fx() -> None:
    # P0=500, P1=550, q=100, TWD so F0=F1=1.
    parts = decompose(
        quantity=Decimal("100"),
        price_open=Decimal("500"),
        price_now=Decimal("550"),
        fx_open=Decimal("1"),
        fx_now=Decimal("1"),
    )
    assert parts.total_twd == Decimal("5000")
    assert parts.asset_contribution_twd == Decimal("5000")
    assert parts.fx_contribution_twd == Decimal("0")
    assert parts.asset_contribution_twd + parts.fx_contribution_twd == parts.total_twd


def test_us_stock_asset_gain_offset_by_fx_loss() -> None:
    # P0=100, P1=110, q=10, F0=31.5, F1=30.0.
    parts = decompose(
        quantity=Decimal("10"),
        price_open=Decimal("100"),
        price_now=Decimal("110"),
        fx_open=Decimal("31.5"),
        fx_now=Decimal("30.0"),
    )
    # total = 10*(110*30 - 100*31.5) = 10*(3300 - 3150) = 1500
    assert parts.total_twd == Decimal("1500")
    # asset = 10*(110-100)*30 = 3000
    assert parts.asset_contribution_twd == Decimal("3000")
    # fx = 10*100*(30-31.5) = -1500
    assert parts.fx_contribution_twd == Decimal("-1500")
    assert parts.asset_contribution_twd + parts.fx_contribution_twd == parts.total_twd


def test_asset_loss_but_fx_gain_cross_case() -> None:
    # Price falls in USD but USD strengthens vs TWD; the two terms pull apart.
    # P0=200, P1=180 (asset loss), q=5, F0=30.0, F1=33.0 (fx gain).
    parts = decompose(
        quantity=Decimal("5"),
        price_open=Decimal("200"),
        price_now=Decimal("180"),
        fx_open=Decimal("30.0"),
        fx_now=Decimal("33.0"),
    )
    # total = 5*(180*33 - 200*30) = 5*(5940 - 6000) = 5*(-60) = -300
    assert parts.total_twd == Decimal("-300")
    # asset = 5*(180-200)*33 = 5*(-20)*33 = -3300
    assert parts.asset_contribution_twd == Decimal("-3300")
    # fx = 5*200*(33-30) = 5*200*3 = 3000
    assert parts.fx_contribution_twd == Decimal("3000")
    assert parts.asset_contribution_twd + parts.fx_contribution_twd == parts.total_twd


def test_decimal_precision_no_binary_float_drift() -> None:
    # 0.1 + 0.2 style inputs that a binary float would mangle; Decimal must be
    # exact. P0=0.1, P1=0.3, q=3, F0=1.1, F1=1.2 (treat FX as a generic factor).
    parts = decompose(
        quantity=Decimal("3"),
        price_open=Decimal("0.1"),
        price_now=Decimal("0.3"),
        fx_open=Decimal("1.1"),
        fx_now=Decimal("1.2"),
    )
    # total = 3*(0.3*1.2 - 0.1*1.1) = 3*(0.36 - 0.11) = 3*0.25 = 0.75
    assert parts.total_twd == Decimal("0.75")
    # asset = 3*(0.3-0.1)*1.2 = 3*0.2*1.2 = 0.72
    assert parts.asset_contribution_twd == Decimal("0.72")
    # fx = 3*0.1*(1.2-1.1) = 3*0.1*0.1 = 0.03
    assert parts.fx_contribution_twd == Decimal("0.03")
    assert parts.asset_contribution_twd + parts.fx_contribution_twd == parts.total_twd
    # And the identity is exact, not merely close (no float epsilon needed).
    assert parts.total_twd == Decimal("0.75")
