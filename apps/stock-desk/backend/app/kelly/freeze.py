"""Plan D sunset: no new Kelly inputs (CEO #62, 2026-10-26).

Cap 5's formula is wrong in its units, and batch two (5-K) retires the cap. To
keep every holding's cap from widening in between, batch one freezes new input
on the server -- manual ``PUT`` and ``import-backtest`` both refuse -- while
the inputs already stored keep feeding cap 5 until each expires
(``KELLY_STALE_AFTER_DAYS``). ``DELETE`` and every read stay open: removing an
input is the user's own data, and the freeze is about adding new numbers
(risk review 2026-10-26 ``第1條上限下修審查-風控.md`` D-1).

Two layers, so that a forgotten route cannot reopen the door: the routes refuse
first (before an import attempt is even logged, so ``K_observed`` stops
growing), and the process-wide :class:`app.kelly.store.KellyInputStore` is
built refusing ``upsert`` as well.

Lifting the freeze is not a one-line change of :data:`KELLY_INPUT_WRITES_FROZEN`:
the user-facing sunset copy (``KellyInputsSection`` lead, the「已暫停」buttons,
cap 5's「計算方式有誤」line) states it and has to change with it (F-d).

A second precondition (「風控 2026-10-29 N-156 K-15 正式核對與裁示」 二-2, tracked
as N-167): before this flag may become ``False``, ``import-backtest`` must
**refuse** (fail closed) while the stored ``cost_model`` is a fallback section
(ADR-0032), and the refusal sentence must go to risk-compliance first. A
disclosure alone is not enough: a p/b computed on the default rates would be
stored, outlive the repair, and carry no trace of where it came from.
"""

from __future__ import annotations

from typing import Final

#: ``True`` from batch one of #61 until 5-K replaces this whole path.
KELLY_INPUT_WRITES_FROZEN: Final = True


class KellyInputWritesFrozenError(RuntimeError):
    """Raised by a store built with ``accept_writes=False`` on any write."""
