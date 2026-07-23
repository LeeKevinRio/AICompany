"""Data layer package: provider adapters, cache, quality checks, orchestration.

Every object returned to callers outside this package carries ``as_of`` and
``source`` so downstream consumers (API layer, UI) can always answer "when
was this true, and who said so".
"""
