"""Forecast ledger (ADR-0027; core per ADR-0030) -- B1, B2 and the NM-5 storage layer.

The write gate (ADR-0030 D-6) is closed: nothing in this package is wired into
``app.main`` or ``app.scheduler``. There is no ``forecast_record`` job, no
``/api/forecast`` or ``/api/outlook`` route, and no ledger table is created in
any service database; the guards in ``tests/test_forecast_gate_closed.py`` pin
that until the wiring PR. This package file imports nothing.

Contents (ADR-0027 D-1):

* ``errors.py`` -- the fail-closed exception types and the exception class name
  rule (standard library only);
* ``band.py`` -- ``threshold_inputs`` and ``labeled_snapshot_violations``, the
  single definition of "missing" for the threshold snapshot (standard library
  plus the violation list from ``errors.py``);
* ``definitions.py`` (B2) -- the one reader of the published dirdef and rule set
  registries in ``app.dirdef``; both are empty, so every lookup raises;
* ``claims.py`` (B2) -- the claim id and m / m_eff pure functions (no
  registration, no CLI);
* ``schema.py`` (NM-5) -- the DDL of the five append-only tables (ADR-0030
  D-2) and the ``sqlite_master`` completeness check;
* ``canonical.py`` (NM-5) -- bar normalisation, ``content_sha256``,
  ``record_content_hash`` and ``code_digest`` (ADR-0030 D-2, D-5);
* ``store.py`` (NM-5) -- append-only writes with write validation and the
  read-only queries (ADR-0030 D-2 points 6 and 7, D-8 point 4).
"""
