"""Display thresholds of the backtest report's round-trip detail block (F-11).

Each name is defined here once and nowhere else (tech-architect F11-A-22). The
values are quant-researcher's registered ones
(``work/research/2026-10-13-F-11-PRD-quant-回覆-Q1Q2Q10Q11.md`` §6).

Both are **disclosure** parameters of the backtest page. Neither refuses,
filters or feeds any computation; the round-trip sample flag built from
:data:`N_MIN_DISPLAY` only decides whether one fixed sentence is shown. They are
deliberately independent of every other threshold in this codebase: this
module imports nothing from ``app`` and no other threshold is read, re-exported
or tied to these values here. The only place the two families meet is a
relation test under ``tests/`` whose failure sends the values back to
quant-researcher and risk-compliance-officer for review (F11-L-2), never to an
automatic edit.

* :data:`N_MIN_DISPLAY` -- a segment with fewer complete round trips than this
  (zero included) is flagged. A disclosure convention, not a statistical
  boundary: reaching it does not make a sample sufficient (PRD D-13).
* :data:`N_WORST` -- how many lowest-return round trips each segment lists
  (PRD D-10).
"""

from __future__ import annotations

from typing import Final

N_MIN_DISPLAY: Final = 30
N_WORST: Final = 5
