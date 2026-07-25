"""Leveraged / inverse ETF mechanics chapter.

A *measurement* surface, never an advice surface: this package explains what a
daily-reset leveraged or inverse ETF mechanically did to a holding (fee effect,
compounding/volatility drag, tracking residual) and what a flat-index scenario
would imply going forward. It emits numbers, explicit states and provenance
only -- no action field, no rating, no target price.

Language convention (mirrors the rest of the backend): code and technical
provenance (``inputs_used.description``) are English; strings meant to be shown
to the user verbatim (``assumptions``, ``source_note``, ``reason``) are
Traditional Chinese (Taiwan).
"""
