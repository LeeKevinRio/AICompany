"""Outlook computation (ADR-0027 D-1 ``app/outlook/``) -- B1 pure leaf only.

B1 holds ``missing.py`` (the D-13 missing-item structure) and nothing else; the
inputs, volatility, basket and baseline modules come in later batches. Nothing
here is wired into ``app.main`` or ``app.scheduler``, and ``app.outlook.*`` never
imports ``app.forecast.*`` (the recorder calls the outlook, not the reverse).
"""
