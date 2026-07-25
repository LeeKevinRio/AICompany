"""Event-driven backtest framework enforcing the backtest-protocol.

Point-in-time by construction (``engine``), configurable costs (``costs``),
walk-forward splitting (``splits``) and the standard report with Buy & Hold and
separate in/out-of-sample segments (``report``). See
``.claude/skills/backtest-protocol/SKILL.md`` for the rules these modules
implement, and ``tests/test_lookahead_detection.py`` for the look-ahead guards.
"""
