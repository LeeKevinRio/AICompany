"""One-shot backfill: fill in the industry category of TW holdings that have none.

Run from the directory sync CLI, either automatically after a successful sync
or on its own with ``--backfill-sectors`` (which needs no network at all -- it
reads the directory that a previous sync already wrote).

## What it will and will not touch

- **Only empty categories.** A holding that already carries a ``sector`` is
  never rewritten, even when the directory disagrees: the user picked that
  value by hand, and a sync job silently reclassifying a holding would change
  a risk-cap bucket behind their back. Every skip is counted with its reason,
  so "nothing happened" is always explainable.
- **Only TW holdings.** A US position may not carry a TWSE category at all
  (``SECTOR_US_REJECTED_MESSAGE``, AC-12.6), so those are skipped by market.
- **Only directory hits with a category.** A symbol the directory has never
  seen, or one it lists without a category (上櫃 / ETF -- the sector dataset
  covers neither), is left empty. Nothing is inferred from the symbol shape.

The report below is returned rather than printed so the CLI owns the wording
and the tests can assert on the numbers directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.directory.store import SecurityDirectoryStore
from app.positions.sectors import is_valid_sector
from app.positions.store import PositionStore


@dataclass(frozen=True)
class SectorBackfillReport:
    """Per-holding outcome of one backfill run, every position accounted for."""

    filled: tuple[tuple[str, str], ...]
    skipped_already_set: int
    skipped_not_tw: int
    skipped_not_in_directory: int
    skipped_directory_has_no_sector: int
    skipped_invalid_directory_sector: int

    @property
    def filled_count(self) -> int:
        return len(self.filled)

    @property
    def skipped_count(self) -> int:
        return (
            self.skipped_already_set
            + self.skipped_not_tw
            + self.skipped_not_in_directory
            + self.skipped_directory_has_no_sector
            + self.skipped_invalid_directory_sector
        )

    @property
    def considered_count(self) -> int:
        return self.filled_count + self.skipped_count


def backfill_position_sectors(
    *,
    position_store: PositionStore,
    directory_store: SecurityDirectoryStore,
    now: datetime | None = None,
) -> SectorBackfillReport:
    """Fill empty TW holding categories from the directory; never overwrite.

    Idempotent: a second run finds every previously filled holding in the
    "already set" bucket and writes nothing.
    """
    filled: list[tuple[str, str]] = []
    skipped_already_set = 0
    skipped_not_tw = 0
    skipped_not_in_directory = 0
    skipped_directory_has_no_sector = 0
    skipped_invalid_directory_sector = 0

    for position in position_store.list_all():
        if position.sector is not None and position.sector.strip():
            skipped_already_set += 1
            continue
        if position.market != "TW":
            skipped_not_tw += 1
            continue
        entry = directory_store.resolve(position.symbol)
        if entry is None:
            skipped_not_in_directory += 1
            continue
        sector = entry.sector
        if sector is None or not sector.strip():
            skipped_directory_has_no_sector += 1
            continue
        if not is_valid_sector(sector):
            # The write path already refuses to store such a value, so this is
            # unreachable through the sync CLI; kept because a directory row
            # written by an older build must not become an unsaveable default.
            skipped_invalid_directory_sector += 1
            continue
        position_store.set_sector(position.id, sector, now=now)
        filled.append((position.symbol, sector))

    return SectorBackfillReport(
        filled=tuple(filled),
        skipped_already_set=skipped_already_set,
        skipped_not_tw=skipped_not_tw,
        skipped_not_in_directory=skipped_not_in_directory,
        skipped_directory_has_no_sector=skipped_directory_has_no_sector,
        skipped_invalid_directory_sector=skipped_invalid_directory_sector,
    )
