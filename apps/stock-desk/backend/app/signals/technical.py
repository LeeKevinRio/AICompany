"""Technical indicators over an OHLCV frame.

Each indicator is an independent function so it can be enabled/disabled and
tested in isolation. Every one returns an :class:`IndicatorResult` that states
its window parameters, the exact inputs it used, the full aligned series (with
``None`` for undefined points, never ``NaN``), and the last defined value. When
a window is longer than the available history the indicator returns
``status="insufficient_data"`` rather than a padded or fabricated value.

Conventions (documented per indicator in ``inputs_used.description``):

* RSI and ATR use **Wilder's smoothing** seeded with a simple average of the
  first ``period`` observations -- the classic definition, matched by the golden
  tests.
* MACD uses recursive EMAs (``adjust=False``), the standard MACD convention.
* Bollinger bands and the volume z-score use **population** standard deviation
  (``ddof=0``).

All statistics here are measurements only; none of them is a recommendation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.data.interface import PriceBar
from app.signals.frame import (
    CLOSE,
    HIGH,
    LOW,
    VOLUME,
    bars_to_frame,
    clean_series,
    date_index,
    last_defined,
    provenance,
)
from app.signals.models import IndicatorResult, InputsUsed

# --- Default window parameters (overridable per call) ------------------------

MA_WINDOWS: tuple[int, ...] = (5, 20, 60)
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BOLLINGER_WINDOW = 20
BOLLINGER_NUM_STD = 2.0
ATR_PERIOD = 14
KD_PERIOD = 9
KD_K_SMOOTH = 3
KD_D_SMOOTH = 3
VOLUME_Z_WINDOW = 20
VOLUME_Z_THRESHOLD = 2.0


def _insufficient(
    name: str,
    *,
    params: dict[str, float],
    inputs_used: InputsUsed,
    bars: list[PriceBar],
) -> IndicatorResult:
    as_of, source = provenance(bars)
    return IndicatorResult(
        name=name,
        status="insufficient_data",
        params=params,
        dates=[],
        series={},
        last={},
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )


def _wilder_rma(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's running moving average of ``values``.

    ``values[0]`` is expected to be ``NaN`` (the seed comes from a ``diff``/true
    range that is undefined on the first bar). The first output is placed at
    index ``period`` as the simple mean of ``values[1..period]``; every later
    point is ``prev * (period - 1) / period + value / period``. Positions before
    ``period`` are ``NaN``.
    """
    out = np.full(values.shape, np.nan, dtype="float64")
    if len(values) <= period:
        return out
    seed = float(np.mean(values[1 : period + 1]))
    out[period] = seed
    for i in range(period + 1, len(values)):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return out


def moving_averages(
    bars: list[PriceBar], *, windows: tuple[int, ...] = MA_WINDOWS
) -> IndicatorResult:
    """Simple moving averages of close over each window in ``windows``."""
    params = {f"ma_{w}": float(w) for w in windows}
    inputs_used = InputsUsed(
        columns=[CLOSE],
        window={f"ma_{w}": w for w in windows},
        description=(
            "Simple moving average of close over each window; a given window "
            "needs at least that many bars, else its value is null."
        ),
    )
    if len(bars) < min(windows):
        return _insufficient("moving_averages", params=params, inputs_used=inputs_used, bars=bars)

    frame = bars_to_frame(bars)
    close = frame[CLOSE]
    series: dict[str, list[float | None]] = {}
    last: dict[str, float | None] = {}
    for w in windows:
        ma = close.rolling(window=w, min_periods=w).mean()
        series[f"ma_{w}"] = clean_series(ma)
        last[f"ma_{w}"] = last_defined(ma)
    as_of, source = provenance(bars)
    return IndicatorResult(
        name="moving_averages",
        status="ok",
        params=params,
        dates=date_index(frame),
        series=series,
        last=last,
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )


def rsi(bars: list[PriceBar], *, period: int = RSI_PERIOD) -> IndicatorResult:
    """Wilder's RSI of close over ``period`` (needs ``period + 1`` bars)."""
    params = {"period": float(period)}
    inputs_used = InputsUsed(
        columns=[CLOSE],
        window={"period": period},
        description=(
            f"Wilder's RSI({period}) of close; needs at least {period + 1} bars "
            "(one extra for the first price change)."
        ),
    )
    if len(bars) < period + 1:
        return _insufficient("rsi", params=params, inputs_used=inputs_used, bars=bars)

    frame = bars_to_frame(bars)
    delta = frame[CLOSE].diff().to_numpy()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain[0] = np.nan
    loss[0] = np.nan
    avg_gain = _wilder_rma(gain, period)
    avg_loss = _wilder_rma(loss, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(avg_loss == 0.0, np.inf, avg_gain / avg_loss)
        rsi_values = 100.0 - 100.0 / (1.0 + rs)
    # All-gain windows (avg_loss == 0) saturate to 100; keep seed positions NaN.
    rsi_values = np.where(np.isnan(avg_gain), np.nan, rsi_values)
    rsi_series = pd.Series(rsi_values, index=frame.index)
    as_of, source = provenance(bars)
    return IndicatorResult(
        name="rsi",
        status="ok",
        params=params,
        dates=date_index(frame),
        series={"rsi": clean_series(rsi_series)},
        last={"rsi": last_defined(rsi_series)},
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )


def macd(
    bars: list[PriceBar],
    *,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> IndicatorResult:
    """MACD line, signal line and histogram from close EMAs."""
    params = {"fast": float(fast), "slow": float(slow), "signal": float(signal)}
    inputs_used = InputsUsed(
        columns=[CLOSE],
        window={"fast": fast, "slow": slow, "signal": signal},
        description=(
            f"MACD = EMA({fast}) - EMA({slow}) of close (adjust=False); signal = "
            f"EMA({signal}) of MACD; histogram = MACD - signal. Needs at least "
            f"{slow + signal} bars for a meaningful signal line."
        ),
    )
    if len(bars) < slow + signal:
        return _insufficient("macd", params=params, inputs_used=inputs_used, bars=bars)

    frame = bars_to_frame(bars)
    close = frame[CLOSE]
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    as_of, source = provenance(bars)
    return IndicatorResult(
        name="macd",
        status="ok",
        params=params,
        dates=date_index(frame),
        series={
            "macd": clean_series(macd_line),
            "signal": clean_series(signal_line),
            "histogram": clean_series(histogram),
        },
        last={
            "macd": last_defined(macd_line),
            "signal": last_defined(signal_line),
            "histogram": last_defined(histogram),
        },
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )


def bollinger(
    bars: list[PriceBar],
    *,
    window: int = BOLLINGER_WINDOW,
    num_std: float = BOLLINGER_NUM_STD,
) -> IndicatorResult:
    """Bollinger bands (population std) with bandwidth and %B."""
    params = {"window": float(window), "num_std": num_std}
    inputs_used = InputsUsed(
        columns=[CLOSE],
        window={"window": window},
        description=(
            f"Bollinger({window}, {num_std}sigma) of close using population std "
            f"(ddof=0). middle=SMA; bandwidth=(upper-lower)/middle; percent_b="
            f"(close-lower)/(upper-lower). Needs at least {window} bars."
        ),
    )
    if len(bars) < window:
        return _insufficient("bollinger", params=params, inputs_used=inputs_used, bars=bars)

    frame = bars_to_frame(bars)
    close = frame[CLOSE]
    middle = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = upper - lower
    with np.errstate(divide="ignore", invalid="ignore"):
        bandwidth = width.where(middle != 0.0) / middle
        percent_b = (close - lower).where(width != 0.0) / width
    as_of, source = provenance(bars)
    return IndicatorResult(
        name="bollinger",
        status="ok",
        params=params,
        dates=date_index(frame),
        series={
            "middle": clean_series(middle),
            "upper": clean_series(upper),
            "lower": clean_series(lower),
            "bandwidth": clean_series(bandwidth),
            "percent_b": clean_series(percent_b),
        },
        last={
            "middle": last_defined(middle),
            "upper": last_defined(upper),
            "lower": last_defined(lower),
            "bandwidth": last_defined(bandwidth),
            "percent_b": last_defined(percent_b),
        },
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )


def atr(bars: list[PriceBar], *, period: int = ATR_PERIOD) -> IndicatorResult:
    """Average True Range via Wilder's smoothing (needs ``period + 1`` bars)."""
    params = {"period": float(period)}
    inputs_used = InputsUsed(
        columns=[HIGH, LOW, CLOSE],
        window={"period": period},
        description=(
            f"ATR({period}) = Wilder's smoothing of true range "
            "(max of high-low, |high-prev_close|, |low-prev_close|); needs at "
            f"least {period + 1} bars."
        ),
    )
    if len(bars) < period + 1:
        return _insufficient("atr", params=params, inputs_used=inputs_used, bars=bars)

    frame = bars_to_frame(bars)
    prev_close = frame[CLOSE].shift(1)
    high_low = frame[HIGH] - frame[LOW]
    high_pc = (frame[HIGH] - prev_close).abs()
    low_pc = (frame[LOW] - prev_close).abs()
    true_range = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
    true_range.iloc[0] = np.nan  # first bar has no previous close; seed excludes it
    atr_values = _wilder_rma(true_range.to_numpy(), period)
    atr_series = pd.Series(atr_values, index=frame.index)
    as_of, source = provenance(bars)
    return IndicatorResult(
        name="atr",
        status="ok",
        params=params,
        dates=date_index(frame),
        series={"atr": clean_series(atr_series)},
        last={"atr": last_defined(atr_series)},
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )


def kd(
    bars: list[PriceBar],
    *,
    period: int = KD_PERIOD,
    k_smooth: int = KD_K_SMOOTH,
    d_smooth: int = KD_D_SMOOTH,
) -> IndicatorResult:
    """Stochastic KD (Taiwan convention: recursive 1/n smoothing, K/D seeded 50)."""
    params = {
        "period": float(period),
        "k_smooth": float(k_smooth),
        "d_smooth": float(d_smooth),
    }
    inputs_used = InputsUsed(
        columns=[HIGH, LOW, CLOSE],
        window={"period": period, "k_smooth": k_smooth, "d_smooth": d_smooth},
        description=(
            f"Stochastic KD({period},{k_smooth},{d_smooth}). RSV=(close-min_low)/"
            "(max_high-min_low)*100 over period; K=(1-1/k_smooth)*prevK+"
            "(1/k_smooth)*RSV; D=(1-1/d_smooth)*prevD+(1/d_smooth)*K; K,D seeded "
            f"at 50. Needs at least {period} bars."
        ),
    )
    if len(bars) < period:
        return _insufficient("kd", params=params, inputs_used=inputs_used, bars=bars)

    frame = bars_to_frame(bars)
    lowest = frame[LOW].rolling(window=period, min_periods=period).min()
    highest = frame[HIGH].rolling(window=period, min_periods=period).max()
    span = highest - lowest
    with np.errstate(divide="ignore", invalid="ignore"):
        rsv = (frame[CLOSE] - lowest).where(span != 0.0, 0.0) / span.where(span != 0.0, 1.0) * 100.0
    rsv_np = rsv.to_numpy()
    k_alpha = 1.0 / k_smooth
    d_alpha = 1.0 / d_smooth
    k_np = np.full(rsv_np.shape, np.nan, dtype="float64")
    d_np = np.full(rsv_np.shape, np.nan, dtype="float64")
    k_prev = 50.0
    d_prev = 50.0
    for i in range(len(rsv_np)):
        if np.isnan(rsv_np[i]):
            continue
        k_prev = (1.0 - k_alpha) * k_prev + k_alpha * rsv_np[i]
        d_prev = (1.0 - d_alpha) * d_prev + d_alpha * k_prev
        k_np[i] = k_prev
        d_np[i] = d_prev
    k_series = pd.Series(k_np, index=frame.index)
    d_series = pd.Series(d_np, index=frame.index)
    as_of, source = provenance(bars)
    return IndicatorResult(
        name="kd",
        status="ok",
        params=params,
        dates=date_index(frame),
        series={
            "rsv": clean_series(rsv),
            "k": clean_series(k_series),
            "d": clean_series(d_series),
        },
        last={
            "rsv": last_defined(rsv),
            "k": last_defined(k_series),
            "d": last_defined(d_series),
        },
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )


def volume_zscore(
    bars: list[PriceBar],
    *,
    window: int = VOLUME_Z_WINDOW,
    threshold: float = VOLUME_Z_THRESHOLD,
) -> IndicatorResult:
    """Rolling volume z-score (population std) and an anomaly flag past threshold."""
    params = {"window": float(window), "threshold": threshold}
    inputs_used = InputsUsed(
        columns=[VOLUME],
        window={"window": window},
        description=(
            f"Volume z-score over a {window}-bar window using population std "
            f"(ddof=0); anomaly flagged when |z| > {threshold}. A zero-variance "
            "window yields a null z-score (undefined). Needs at least "
            f"{window} bars."
        ),
    )
    if len(bars) < window:
        return _insufficient("volume_zscore", params=params, inputs_used=inputs_used, bars=bars)

    frame = bars_to_frame(bars)
    volume = frame[VOLUME]
    mean = volume.rolling(window=window, min_periods=window).mean()
    std = volume.rolling(window=window, min_periods=window).std(ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        zscore = (volume - mean).where(std != 0.0) / std.where(std != 0.0)
    anomaly_series: list[float | None] = [
        None if pd.isna(z) else float(bool(abs(z) > threshold)) for z in zscore
    ]
    last_z = last_defined(zscore)
    as_of, source = provenance(bars)
    return IndicatorResult(
        name="volume_zscore",
        status="ok",
        params=params,
        dates=date_index(frame),
        series={
            "zscore": clean_series(zscore),
            "anomaly": anomaly_series,
        },
        last={
            "zscore": last_z,
            "anomaly": None if last_z is None else float(abs(last_z) > threshold),
        },
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )
