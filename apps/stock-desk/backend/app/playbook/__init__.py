"""Playbook: the deterministic schedule-execution engine (快市排程交易系統).

A module parallel to :mod:`app.advice`, never derived from it. The advice engine
produces *soft* opinions about one symbol at one moment; this package replays a
rule set the user wrote themselves (R/S/P/M1 plus the five iron laws) over a
stateful portfolio and reports which rules fired.

Boundary (風控 required R4): nothing here may read the advice engine's output
fields (``action`` / ``confidence`` / ``weight`` / ``matched_rules`` /
``direction_weights``). The exemption that lets this package speak in
instruction wording at all rests on the user being the author of every rule, so
an advice-engine judgement leaking into an instruction would void it. The rule
is enforced by an import-graph test (``tests/test_playbook_boundary.py``),
mirroring the 還原價 boundary guard, not by prose alone.

What is shared with the rest of the product: the data layer degradation ladder,
the SQLite file, the price bar shape and the trading calendar derived from real
bar dates. What is not: any advice vocabulary or scoring.
"""
