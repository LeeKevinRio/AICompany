"""The observation window every per-symbol signal reader shares (ADR-0020).

Alerts (``app.alerts.snapshot``), the advice card, the signals page, the bars
chart and the portfolio view all load ``[today - OBSERVATION_LOOKBACK_DAYS,
today]`` for a symbol. The window-sensitive statistics -- ``drawdown.current``,
``drawdown.max_drawdown`` and ``volatility.annualized`` -- depend on where the
window starts, so two readers with different windows publish different numbers
for the same symbol on the same day. That drift is the bug this constant exists
to rule out: there is one definition, and every reader imports it.

The length is a signal-layer requirement (the longest indicator window, MA60,
plus the risk layer's return sample, with room to spare), so ``app.signals``
owns it and the API layer only re-exports it. This module is a leaf: it imports
nothing from ``app``, so any layer can depend on it without new import edges.
"""

from __future__ import annotations

from typing import Final

#: Calendar days of history a per-symbol reader requests. Roughly 18 months.
OBSERVATION_LOOKBACK_DAYS: Final = 540
