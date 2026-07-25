"""Golden and behavioural tests for the technical indicators.

Golden values are hand-computed in the docstrings so a future change that shifts
an indicator's definition fails loudly rather than silently.
"""

from __future__ import annotations

import math

from app.signals import technical as T
from tests.signals_helpers import bars_from_closes, make_bar

TOL = 1e-6


def test_moving_averages_simple_mean_and_insufficient_windows() -> None:
    # closes 1..10; MA5 last = mean(6..10)=8, MA20/MA60 not yet available.
    bars = bars_from_closes([float(i) for i in range(1, 11)])
    result = T.moving_averages(bars)
    assert result.status == "ok"
    assert result.last["ma_5"] == 8.0
    assert result.last["ma_20"] is None
    assert result.last["ma_60"] is None
    # Below the smallest window -> insufficient_data, no fabricated values.
    tiny = T.moving_averages(bars_from_closes([1.0, 2.0, 3.0]))
    assert tiny.status == "insufficient_data"
    assert tiny.series == {}
    assert tiny.inputs_used.columns == ["close"]


def test_rsi_golden_wilder() -> None:
    # 15 up-ticks (100..114) then a -2 move to 112.
    # First RSI at index 14 = 100 (all gains). Next: avg_gain=13/14, avg_loss=2/14,
    # rs=6.5, rsi = 100 - 100/7.5 = 86.6666...
    closes = [100.0 + i for i in range(15)] + [112.0]
    result = T.rsi(bars_from_closes(closes))
    assert result.status == "ok"
    assert result.last["rsi"] is not None
    assert math.isclose(result.last["rsi"], 86.66666666666667, rel_tol=1e-9)
    # The all-gain seed point saturates at 100.
    assert result.series["rsi"][14] == 100.0


def test_rsi_monotonic_down_saturates_to_zero() -> None:
    closes = [200.0 - i for i in range(16)]
    result = T.rsi(bars_from_closes(closes))
    assert result.last["rsi"] == 0.0


def test_rsi_insufficient() -> None:
    result = T.rsi(bars_from_closes([1.0] * 10))
    assert result.status == "insufficient_data"


def test_macd_constant_series_is_zero() -> None:
    # Constant close -> EMA12 == EMA26 == const -> MACD line, signal, hist all 0.
    result = T.macd(bars_from_closes([50.0] * 40))
    assert result.status == "ok"
    for line in ("macd", "signal", "histogram"):
        value = result.last[line]
        assert value is not None
        assert math.isclose(value, 0.0, abs_tol=TOL)


def test_macd_uptrend_line_positive() -> None:
    result = T.macd(bars_from_closes([100.0 + i for i in range(40)]))
    assert result.last["macd"] is not None
    assert result.last["macd"] > 0.0


def test_macd_insufficient() -> None:
    result = T.macd(bars_from_closes([1.0] * 30))
    assert result.status == "insufficient_data"


def test_bollinger_constant_collapses_bands() -> None:
    result = T.bollinger(bars_from_closes([100.0] * 25))
    assert result.status == "ok"
    assert result.last["middle"] == 100.0
    assert result.last["upper"] == 100.0
    assert result.last["lower"] == 100.0
    # Zero-width band -> bandwidth 0, percent_b undefined (division by zero).
    assert result.last["bandwidth"] == 0.0
    assert result.last["percent_b"] is None


def test_bollinger_two_sigma_width() -> None:
    # 19 values of 100 then one 110 in a 20-window.
    # mean = (19*100+110)/20 = 100.5; population var = (19*0.5^2 + 9.5^2)/20
    # = (4.75 + 90.25)/20 = 4.75; std = 2.179449...; upper = mean + 2*std.
    closes = [100.0] * 19 + [110.0]
    result = T.bollinger(bars_from_closes(closes))
    assert result.last["middle"] is not None
    assert math.isclose(result.last["middle"], 100.5, abs_tol=TOL)
    std = math.sqrt(4.75)
    assert result.last["upper"] is not None
    assert math.isclose(result.last["upper"], 100.5 + 2 * std, abs_tol=TOL)


def test_atr_constant_true_range() -> None:
    # Every bar high=105 low=95 close=100 -> TR=10 each day -> ATR=10.
    bars = [make_bar(day_offset=i, close=100.0, high=105.0, low=95.0) for i in range(20)]
    result = T.atr(bars)
    assert result.status == "ok"
    assert result.last["atr"] is not None
    assert math.isclose(result.last["atr"], 10.0, abs_tol=TOL)
    assert result.inputs_used.columns == ["high", "low", "close"]


def test_atr_insufficient() -> None:
    bars = [make_bar(day_offset=i, close=100.0, high=101.0, low=99.0) for i in range(10)]
    assert T.atr(bars).status == "insufficient_data"


def test_kd_golden_taiwan_smoothing() -> None:
    # Monotonic up -> RSV=100 at every valid point. K,D seeded at 50, 1/3 smoothing.
    # K: 66.667, 77.778, 85.185, 90.123...; D: 55.556, 62.963, 70.370, 76.955.
    result = T.kd(bars_from_closes([10.0 + i for i in range(12)]))
    assert result.status == "ok"
    assert result.last["k"] is not None
    assert result.last["d"] is not None
    assert math.isclose(result.last["k"], 90.12345679012347, rel_tol=1e-9)
    assert math.isclose(result.last["d"], 76.95473251028808, rel_tol=1e-9)
    assert result.last["rsv"] == 100.0


def test_kd_insufficient() -> None:
    assert T.kd(bars_from_closes([1.0] * 8)).status == "insufficient_data"


def test_volume_zscore_golden_spike() -> None:
    # 20 vols of 100 then a spike to 200. Latest 20-window = 19x100 + 1x200.
    # mean=105, population var=475, std=21.7945; z=(200-105)/std=4.3589; anomaly.
    bars = [make_bar(day_offset=i, close=100.0, volume=100) for i in range(20)]
    bars.append(make_bar(day_offset=20, close=100.0, volume=200))
    result = T.volume_zscore(bars)
    assert result.status == "ok"
    assert result.last["zscore"] is not None
    assert math.isclose(result.last["zscore"], 4.358898943540673, rel_tol=1e-9)
    assert result.last["anomaly"] == 1.0


def test_volume_zscore_zero_variance_is_null() -> None:
    bars = [make_bar(day_offset=i, close=100.0, volume=100) for i in range(21)]
    result = T.volume_zscore(bars)
    # Constant volume -> undefined z-score -> null, not a fake 0-that-looks-real.
    assert result.last["zscore"] is None
    assert result.last["anomaly"] is None


def test_provenance_carried_through() -> None:
    bars = bars_from_closes([100.0 + i for i in range(40)], source="finmind")
    result = T.macd(bars)
    assert result.source == "finmind"
    assert result.as_of is not None
