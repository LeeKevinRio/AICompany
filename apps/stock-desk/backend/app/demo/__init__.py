"""Offline demo data: synthetic series and the seeder that stores them.

EVERYTHING THIS PACKAGE PRODUCES IS FABRICATED. It exists so an environment
with no outbound network (CI, an acceptance box, a demo laptop) can render the
four pages with real numbers instead of a wall of ``insufficient_data``.

Nothing here may be used for a real decision, and nothing here may be mistaken
for market data: every bar is tagged ``source="demo_synthetic"``
(:data:`app.demo.series.DEMO_SOURCE`), which is exactly the string the UI
prints in its "來源" line, and every seeded position/alert rule carries the
:data:`app.demo.seed.DEMO_NOTE_PREFIX` marker in its note.
"""

from __future__ import annotations

from app.demo.series import DEMO_SOURCE

__all__ = ["DEMO_SOURCE"]
