"""Forecast ledger (ADR-0027; core per ADR-0030) -- B1, B2 and the NM-5 storage layer.

Wiring (ADR-0030 D-6 CG-4, K-3): ``app.scheduler`` registers job
``forecast_record`` and enters this package only through ``recorder.py``;
``app.main`` reaches nothing here and mounts no ``/api/forecast`` or
``/api/outlook`` route (D-4 point 6). The ledger schema is created in the
production database only by ``python -m app.forecast.claims bootstrap
--production``; every other write refuses an incomplete schema. The guards in
``tests/test_forecast_gate_closed.py`` pin this. This package file imports
nothing.

Contents (ADR-0027 D-1):

* ``errors.py`` -- the fail-closed exception types and the exception class name
  rule (standard library only);
* ``band.py`` -- ``threshold_inputs`` and ``labeled_snapshot_violations``, the
  single definition of "missing" for the threshold snapshot (standard library
  plus the violation list from ``errors.py``);
* ``definitions.py`` (B2) -- the one reader of the published dirdef and rule set
  registries in ``app.dirdef``; an unpublished version raises;
* ``claims.py`` (B2; NM-5) -- the claim id and m / m_eff pure functions, and
  the operator registration CLI ``python -m app.forecast.claims register``
  (ADR-0030 D-1 point 3), which refuses the production database, and
  ``bootstrap --production``, the production database's one way in;
* ``schema.py`` (NM-5) -- the DDL of the five append-only tables (ADR-0030
  D-2) and the ``sqlite_master`` completeness check;
* ``canonical.py`` (NM-5) -- bar normalisation, ``content_sha256``,
  ``record_content_hash`` and ``code_digest`` (ADR-0030 D-2, D-5);
* ``store.py`` (NM-5) -- append-only writes with write validation and the
  read-only queries (ADR-0030 D-2 points 6 and 7, D-8 point 4);
* ``recorder.py`` (NM-5) -- job ``forecast_record``'s one orchestration
  (ADR-0030 D-1 point 3): CG-2 run-time check, cross-commit check, T, snapshot,
  computation, writes; the D-8 point 4 review trigger WARNING after the run.
"""
