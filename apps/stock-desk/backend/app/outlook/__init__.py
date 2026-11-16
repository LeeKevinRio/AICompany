"""Outlook computation (ADR-0027 D-1 ``app/outlook/``; ADR-0030 D-1 point 3) -- pure modules.

* ``missing.py`` (B1) -- the D-13 missing-item structure;
* ``volatility.py`` (B2; NM-5) -- ``sigma_d``, the single sigma kernel, and the
  window primitives ``usable`` / ``log_return`` / ``window_log_returns`` /
  ``sigma_at`` (freeze pack 2.2, 2.4);
* ``basket.py`` (B2) -- the equal-weight sector basket series (not used by the core);
* ``inputs.py`` (NM-5) -- the ``^TWII`` snapshot of final bars from the index
  service's answer, the one snapshot cut, and ``late_cutoff_at``;
* ``baselines.py`` (NM-5) -- B1, B2, B6, B8 at publication (ADR-0030 D-4 point 1);
* ``engine.py`` (NM-5) -- the features, the rule evaluation and the record
  content (ADR-0025 D-2.3 (a)-(c); freeze pack G2);
* ``rules/h3.yaml``, ``rules/h5.yaml`` -- the frozen market rule files (freeze
  pack section 4), landed but not registered: the rule set registry is filled
  by the CG-2 registration batch.

Nothing here is wired into ``app.main`` or ``app.scheduler``, and
``app.outlook.*`` never imports ``app.forecast.*`` (the recorder calls the
outlook, not the reverse); dirdef objects and rule sets are passed in by the
caller as keyword arguments without defaults.
"""
