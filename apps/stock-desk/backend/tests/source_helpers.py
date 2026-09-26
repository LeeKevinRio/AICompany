"""Source fingerprints and a fake market DB for the statistics-repository tests (ADR-0012 C-50).

:class:`FakeSources` stands in for ``app.data.market_panel``'s two verifier
capabilities -- the write-time full recompute (``source_fingerprint``) and the
read-time light check (``source_tally``) -- over a fixed set of fingerprints,
and counts how often each is asked. Tests that need the real market DB use
``MarketPanelStore`` / ``MarketPanelReader`` instead.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Iterable
from datetime import date

from app.data.panel import SourceFingerprint, SourceTally
from app.sectors.models import StatsRecord

#: A well-formed digest; the fake knows no content, only the fingerprints given to it.
FAKE_DIGEST = "a" * 64


def fingerprint(
    run_min: int = 101,
    run_max: int = 102,
    session_end: date = date(2026, 12, 1),
    run_count: int = 2,
    digest: str = FAKE_DIGEST,
) -> SourceFingerprint:
    return SourceFingerprint(
        run_min=run_min,
        run_max=run_max,
        session_end=session_end,
        run_count=run_count,
        digest=digest,
    )


#: The fingerprint :func:`tests.sector_board_helpers.stats_record` and friends default to.
DEFAULT_FINGERPRINT = fingerprint()


def source_fields(sources: SourceFingerprint) -> dict[str, object]:
    """The five ``StatsRecord`` source fields of ``sources``."""
    return {
        "source_run_min": sources.run_min,
        "source_run_max": sources.run_max,
        "source_session_end": sources.session_end,
        "source_run_count": sources.run_count,
        "source_digest": sources.digest,
    }


def with_sources(record: StatsRecord, sources: SourceFingerprint) -> StatsRecord:
    return dataclasses.replace(record, **source_fields(sources))  # type: ignore[arg-type]


class FakeSources:
    """A market DB that holds exactly the source sets of ``fingerprints``.

    ``ok_runs`` defaults to every fingerprint's first and last run. Both
    capabilities count their calls, so tests can assert "one light check per
    read, no digest on the read path".
    """

    def __init__(
        self,
        fingerprints: Iterable[SourceFingerprint] = (DEFAULT_FINGERPRINT,),
        *,
        ok_runs: Collection[int] | None = None,
    ) -> None:
        known = tuple(fingerprints)
        self.fingerprints = {(item.run_max, item.session_end): item for item in known}
        self.ok_runs = (
            frozenset(ok_runs)
            if ok_runs is not None
            else frozenset(run for item in known for run in (item.run_min, item.run_max))
        )
        self.fingerprint_calls = 0
        self.tally_calls = 0

    def source_fingerprint(self, run_max: int, session_end: date) -> SourceFingerprint | None:
        self.fingerprint_calls += 1
        return self.fingerprints.get((run_max, session_end))

    def source_tally(
        self, endpoints: Collection[int], run_max: int, session_end: date
    ) -> SourceTally:
        self.tally_calls += 1
        found = self.fingerprints.get((run_max, session_end))
        return SourceTally(
            ok_endpoints=frozenset(endpoints) & self.ok_runs,
            run_count=found.run_count if found is not None else 0,
            run_min=found.run_min if found is not None else None,
            run_max=found.run_max if found is not None else None,
        )
