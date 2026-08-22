"""Kelly inputs: the stored ``p``/``b`` behind risk cap 5 (ADR-0006).

Source-agnostic by design. This package holds what a Kelly input *is* (the
effective values, their provenance and their freshness anchor), how it is
stored, and the sample-size gate an imported one has to clear -- but it never
computes a Kelly fraction and never runs a backtest. Per 約束 13/37 it imports
neither ``app.advice`` (which owns the single ``kelly_fraction`` formula) nor
``app.backtest`` (which owns round-trip extraction); ``app/api/kelly.py`` is
the only place the three meet.
"""
