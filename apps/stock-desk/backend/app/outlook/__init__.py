"""Outlook computation (ADR-0027 D-1 ``app/outlook/``) -- B1 and B2 pure modules only.

* ``missing.py`` (B1) -- the D-13 missing-item structure;
* ``volatility.py`` (B2) -- ``sigma_d``, the single sigma kernel;
* ``basket.py`` (B2) -- the equal-weight sector basket series.

The inputs and baseline modules come in later batches, and ``rules/`` holds no
rule file until the G-3 freeze. Nothing here is wired into ``app.main`` or
``app.scheduler``, and ``app.outlook.*`` never imports ``app.forecast.*`` (the
recorder calls the outlook, not the reverse); dirdef objects are passed in by
the caller as keyword arguments without defaults.
"""
