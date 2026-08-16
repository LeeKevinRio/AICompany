"""Turn TWSE's raw ``產業別`` codes into directory rows we are allowed to store.

``app.directory.sector_audit`` answers "does the official taxonomy still match
``TWSE_SECTORS``". This module answers the *persistence* question: given one
fetch of ``t187ap03_L``, which ``代號 -> 產業別`` facts may be written into the
security directory, and which must be dropped with a stated reason.

## Three fail-safe drops -- all of them refusals to write, never guesses

1. **Blank code.** A row whose ``產業別`` is empty carries no classification.
   (``TwseSectorProfileAdapter`` already skips these at parse time; the check
   is repeated here so this function is safe for any caller.)
2. **Unknown code.** A code missing from
   ``app.directory.twse_sector_codes.TWSE_SECTOR_CODE_TO_NAME`` is dropped,
   never stored as its raw digits and never mapped to a "nearest" category --
   the same rule ``sector_audit``'s ``UNKNOWN_CODE`` bucket enforces, and the
   one the data-source-integration skill states outright.
3. **Resolved name outside the closed list.** The stored value has to be one
   the position validator accepts (``app.positions.sectors.is_valid_sector``),
   because it is offered to the position form as a pre-filled default: a name
   the mapping table knows but ``TWSE_SECTORS`` does not would auto-fill a
   value the user could not then save. Dropping it keeps the field empty and
   the write path honest, and the mismatch still surfaces through
   ``--verify-sectors``, which exists precisely to get such a gap ruled on.

Everything the directory does not cover therefore simply has no category:
TPEx (上櫃) securities and ETFs are absent from this dataset entirely, so
their ``sector`` stays NULL rather than being inferred from the symbol.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.directory.models import DirectorySectorAssignment
from app.directory.providers import SectorProfileEntry
from app.directory.twse_sector_codes import TWSE_SECTOR_CODE_TO_NAME
from app.positions.sectors import is_valid_sector


@dataclass(frozen=True)
class SectorResolution:
    """What one fetch resolved to, plus every drop and why.

    The dropped codes/names are carried (not just counted) so the CLI can name
    them: "3 rows dropped" tells the operator nothing actionable, whereas "code
    99 unknown" points straight at the mapping table that needs a human.
    """

    assignments: tuple[DirectorySectorAssignment, ...]
    blank_code_rows: int
    unknown_code_rows: int
    unknown_codes: tuple[str, ...]
    outside_closed_list_rows: int
    outside_closed_list_names: tuple[str, ...]
    duplicate_symbol_rows: int

    @property
    def dropped_rows(self) -> int:
        return (
            self.blank_code_rows
            + self.unknown_code_rows
            + self.outside_closed_list_rows
            + self.duplicate_symbol_rows
        )


def resolve_sector_assignments(
    entries: Sequence[SectorProfileEntry],
    *,
    as_of: datetime,
    source: str,
    code_to_name: Mapping[str, str] = TWSE_SECTOR_CODE_TO_NAME,
) -> SectorResolution:
    """Resolve each row's code to a storable category name.

    ``as_of``/``source`` come from the fetch result rather than being read off
    the individual entries, so every assignment from one fetch shares one
    retrieval timestamp -- the same discipline ``DirectoryEntry`` applies to
    the symbol/name source.

    Duplicate ``公司代號`` rows keep the first occurrence: TWSE publishes one
    row per company, so a repeat is a payload anomaly, and picking the first
    (rather than letting the later row silently overwrite) keeps the count the
    caller reports equal to the number of rows actually written.
    """
    assignments: list[DirectorySectorAssignment] = []
    seen_symbols: set[str] = set()
    blank_code_rows = 0
    unknown_code_rows = 0
    unknown_codes: list[str] = []
    outside_closed_list_rows = 0
    outside_closed_list_names: list[str] = []
    duplicate_symbol_rows = 0

    for entry in entries:
        code = entry.sector.strip()
        if not code:
            blank_code_rows += 1
            continue
        name = code_to_name.get(code)
        if name is None:
            unknown_code_rows += 1
            if code not in unknown_codes:
                unknown_codes.append(code)
            continue
        if not is_valid_sector(name):
            outside_closed_list_rows += 1
            if name not in outside_closed_list_names:
                outside_closed_list_names.append(name)
            continue
        if entry.symbol in seen_symbols:
            duplicate_symbol_rows += 1
            continue
        seen_symbols.add(entry.symbol)
        assignments.append(
            DirectorySectorAssignment(
                symbol=entry.symbol,
                market="TW",
                sector=name,
                source=source,
                as_of=as_of,
            )
        )

    return SectorResolution(
        assignments=tuple(assignments),
        blank_code_rows=blank_code_rows,
        unknown_code_rows=unknown_code_rows,
        unknown_codes=tuple(sorted(unknown_codes)),
        outside_closed_list_rows=outside_closed_list_rows,
        outside_closed_list_names=tuple(sorted(outside_closed_list_names)),
        duplicate_symbol_rows=duplicate_symbol_rows,
    )
