"""Sector momentum card: pure core plus its own main-DB store (ADR-0012 D-1).

Pure core (``definition``, ``models``, ``universe``, ``index``, ``ranking``,
``constituents``, ``coverage``, ``gate``): no I/O, no network, and a hard
import whitelist -- ``app.sectors.*``, ``app.data.panel``,
``app.data.interface``, ``app.data.calendar``, ``app.positions.sectors``
(C-1). ``store`` may additionally take ``resolve_db_path`` from
``app.data.cache``. ``tests/test_sectors_boundary.py`` enforces both.

The package describes what already happened -- relative strength over the
last L sessions -- and never evaluates a stock or predicts anything (C-17).
"""
