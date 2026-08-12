"""The vocabulary rules may read: a flat, dotted-path view of the signal layer.

A rule condition names a field such as ``rsi14.last`` or ``ma60.last``. Those
names are *not* free-form: :data:`FIELD_LABELS` is the closed vocabulary, the
loader rejects any condition referring to something outside it, and
:func:`build_context` produces exactly these keys. Loader and engine therefore
cannot drift apart -- a typo in the YAML is a load-time error, not a rule that
silently never fires.

A field is ``None`` whenever the underlying indicator is missing or reported
``insufficient_data``. The engine turns a ``None`` input into a *skipped* rule
with the missing field named; it never substitutes a default.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.advice.limits import PortfolioContext

#: Every field a rule may reference, with a Traditional Chinese label used in
#: "missing input" explanations. Fields not used by the shipped rules are kept
#: available on purpose so new rules need no engine change.
FIELD_LABELS: dict[str, str] = {
    "close": "最新收盤價",
    "ma5.last": "5 日均線最新值",
    "ma20.last": "20 日均線最新值",
    "ma60.last": "60 日均線最新值",
    "rsi14.last": "14 日 RSI 最新值",
    "macd.last": "MACD 快慢線差最新值",
    "macd.signal": "MACD 訊號線最新值",
    "macd.histogram": "MACD 柱狀圖最新值",
    "bollinger.middle": "布林通道中軌",
    "bollinger.upper": "布林通道上軌",
    "bollinger.lower": "布林通道下軌",
    "bollinger.bandwidth": "布林通道寬度",
    "bollinger.percent_b": "布林通道 %B",
    "atr14.last": "ATR(14) 最新值",
    "kd.k": "KD 指標 K 值",
    "kd.d": "KD 指標 D 值",
    "volume_z.last": "成交量 z 分數最新值",
    "volatility.annualized": "年化波動度",
    "drawdown.max_drawdown": "區間最大回撤",
    "beta.value": "相對指標的 beta",
    "position.weight": "此標的佔投資組合比重",
    "position.unrealized_pnl_pct": "此部位未實現損益率",
}

KNOWN_FIELDS = frozenset(FIELD_LABELS)

#: The one raw price level the advice side may read (風控 required R19).
#:
#: Every other field above is an indicator value, a ratio or a portfolio
#: statistic; ``close`` is the only outright price in the vocabulary, and R19
#: freezes that: **this allowlist stays at length 1 and is not to be extended**.
#: The playbook keeps a separate table of its own
#: (``app.playbook.price_fields.PLAYBOOK_PRICE_FIELDS``) that this module neither
#: imports nor shares a name with -- the two tracks are checked against each
#: other in ``tests/test_playbook_price_fields.py``.
PRICE_FIELD_ALLOWLIST: frozenset[str] = frozenset({"close"})


def describe_field(path: str) -> str:
    """Render a field path with its Traditional Chinese label for messages."""
    label = FIELD_LABELS.get(path)
    return f"{path}（{label}）" if label else path


def _as_float(value: Any) -> float | None:
    """Coerce a signal value to ``float``; anything else (incl. bool) is ``None``."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _last(block: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """The ``last`` dict of one indicator; empty when absent or insufficient.

    An ``insufficient_data`` indicator carries an empty ``last`` already, so no
    special-casing of ``status`` is needed -- every lookup simply misses.
    """
    return _mapping(_mapping(block.get(name)).get("last"))


def build_context(
    signals: Mapping[str, Any], portfolio: PortfolioContext
) -> dict[str, float | None]:
    """Flatten a ``compute_signals`` output plus portfolio state into rule inputs.

    ``signals`` is the dict produced by :func:`app.signals.service.compute_signals`
    (a partially populated one is fine: absent layers just yield ``None``
    fields). The returned mapping always has exactly the :data:`KNOWN_FIELDS`
    keys.
    """
    technical = _mapping(signals.get("technical"))
    risk = _mapping(signals.get("risk"))

    ma = _last(technical, "moving_averages")
    rsi = _last(technical, "rsi")
    macd = _last(technical, "macd")
    bollinger = _last(technical, "bollinger")
    atr = _last(technical, "atr")
    kd = _last(technical, "kd")
    volume = _last(technical, "volume_zscore")
    volatility = _mapping(risk.get("volatility"))
    drawdown = _mapping(risk.get("drawdown"))
    beta = _mapping(risk.get("beta"))

    raw: dict[str, Any] = {
        "close": portfolio.close,
        "ma5.last": ma.get("ma_5"),
        "ma20.last": ma.get("ma_20"),
        "ma60.last": ma.get("ma_60"),
        "rsi14.last": rsi.get("rsi"),
        "macd.last": macd.get("macd"),
        "macd.signal": macd.get("signal"),
        "macd.histogram": macd.get("histogram"),
        "bollinger.middle": bollinger.get("middle"),
        "bollinger.upper": bollinger.get("upper"),
        "bollinger.lower": bollinger.get("lower"),
        "bollinger.bandwidth": bollinger.get("bandwidth"),
        "bollinger.percent_b": bollinger.get("percent_b"),
        "atr14.last": atr.get("atr"),
        "kd.k": kd.get("k"),
        "kd.d": kd.get("d"),
        "volume_z.last": volume.get("zscore"),
        "volatility.annualized": volatility.get("annualized_volatility"),
        "drawdown.max_drawdown": drawdown.get("max_drawdown"),
        "beta.value": beta.get("beta"),
        "position.weight": portfolio.position_weight(),
        "position.unrealized_pnl_pct": portfolio.unrealized_pnl_pct(),
    }
    return {key: _as_float(raw[key]) for key in FIELD_LABELS}
