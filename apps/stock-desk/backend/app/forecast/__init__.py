"""Forecast ledger (ADR-0027) -- B1 pure leaf modules only.

The write gate (ADR-0027 D-14) is closed: nothing in this package is wired into
``app.main`` or ``app.scheduler``. There is no ``forecast_record`` job, no
``/api/forecast`` or ``/api/outlook`` route, and no store; the guards in
``tests/test_forecast_gate_closed.py`` pin that until the gate batch lands.

B1 contents (ADR-0027 D-1):

* ``errors.py`` -- the fail-closed exception types and the exception class name
  rule (standard library only);
* ``band.py`` -- ``threshold_inputs`` and ``labeled_snapshot_violations``, the
  single definition of "missing" for the threshold snapshot (standard library
  plus the violation list from ``errors.py``).
"""
