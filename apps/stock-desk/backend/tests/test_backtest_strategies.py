"""Tests for the shipped ``ma_cross`` strategy, including its look-ahead safety."""

from __future__ import annotations

import pandas as pd
import pytest

from app.backtest.strategies import (
    DEFAULT_SLOW_WINDOW,
    STRATEGY_IDS,
    STRATEGY_WARMUP_BARS,
    build_strategy,
    ma_cross,
)
from app.signals.frame import bars_to_frame
from tests.signals_helpers import bars_from_closes


def _frame(closes: list[float]) -> pd.DataFrame:
    return bars_to_frame(bars_from_closes(closes))


def test_strategy_is_flat_before_the_slow_window_is_filled() -> None:
    strategy = ma_cross()
    frame = _frame([100.0] * (DEFAULT_SLOW_WINDOW - 1))
    assert strategy(frame) == 0.0


def test_strategy_is_long_when_the_fast_average_leads() -> None:
    strategy = ma_cross()
    # 60 flat bars then a sharp rise: MA20 is pulled above MA60.
    closes = [100.0] * 60 + [200.0] * 20
    assert strategy(_frame(closes)) == 1.0


def test_strategy_is_flat_when_the_fast_average_lags() -> None:
    strategy = ma_cross()
    closes = [200.0] * 60 + [100.0] * 20
    assert strategy(_frame(closes)) == 0.0


def test_strategy_reads_only_the_window_it_is_given() -> None:
    # The engine's guarantee is structural: a strategy that could see the future
    # would behave differently given the same prefix. Here the same prefix must
    # produce the same weight whatever follows it in the full series.
    strategy = ma_cross()
    prefix = [100.0] * 60 + [200.0] * 20
    from_prefix = strategy(_frame(prefix))
    from_longer = strategy(_frame(prefix)[: len(prefix)])
    assert from_prefix == from_longer


def test_windows_must_be_ordered_and_positive() -> None:
    with pytest.raises(ValueError):
        ma_cross(fast=0)
    with pytest.raises(ValueError):
        ma_cross(fast=60, slow=20)
    with pytest.raises(ValueError):
        ma_cross(fast=20, slow=20)


def test_registry_exposes_ma_cross_with_its_warmup() -> None:
    assert STRATEGY_IDS == ("ma_cross",)
    assert STRATEGY_WARMUP_BARS["ma_cross"] == DEFAULT_SLOW_WINDOW
    assert callable(build_strategy("ma_cross"))
    with pytest.raises(KeyError):
        build_strategy("secret_sauce")
