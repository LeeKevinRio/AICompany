"""Internal research only -- never reachable from the API, the scheduler or the sector core.

ADR-0012 D-14 / C-27: no ``app.*`` module outside this package may import
anything from it (``tests/test_research_isolation.py`` walks the import graph),
and its results live in their own database file, which the API process never
opens.
"""
