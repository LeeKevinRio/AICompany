"""Biased (hindsight) sector-momentum research, ADR-0012 D-14 / methodology §5.4.

Everything here carries :data:`BIAS_LABEL` -- 「含已知偏誤，不得上畫面」 -- and the
three known bias directions (:data:`BIAS_DIRECTIONS`). Four lines of defence
keep it off the card:

1. import layer -- only this package imports it (C-27, import-graph test);
2. file layer -- results go to ``STOCK_DESK_RESEARCH_DB_PATH`` only
   (:mod:`.store`), a file the API process never opens;
3. type layer -- every result is ``regime="hindsight"`` /
   ``data_regime="backfill_non_pit"``, which ``sector_eval.to_stats_record``
   and ``SectorStatsRepository`` both refuse;
4. run time -- the repository rejects such rows with ``BiasedDataRejected``.

:func:`hindsight_view` is the one sanctioned way to build a view that ignores
``recorded_at``; it is defined and called nowhere else (C-27).
"""

from app.research.sector_biased.hindsight import BIAS_DIRECTIONS, BIAS_LABEL, hindsight_view

__all__ = ["BIAS_DIRECTIONS", "BIAS_LABEL", "hindsight_view"]
