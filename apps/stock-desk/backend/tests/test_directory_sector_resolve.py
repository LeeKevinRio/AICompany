"""Code -> name resolution for the sectors written into the directory.

Every test here is really the same assertion from a different angle: a code
this build cannot resolve to an approved category produces *no* write, never a
guess and never a raw code stored as if it were a name.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.directory.providers import SectorProfileEntry
from app.directory.sector_resolve import SectorResolution, resolve_sector_assignments
from app.positions.sectors import TWSE_SECTORS, is_valid_sector

AS_OF = datetime(2026, 8, 16, 3, 0, tzinfo=UTC)
SOURCE = "twse_openapi_t187ap03_L"


def _row(symbol: str, sector_code: str, name: str = "測試公司") -> SectorProfileEntry:
    return SectorProfileEntry(
        symbol=symbol, name=name, sector=sector_code, source=SOURCE, as_of=AS_OF
    )


def _resolve(*rows: SectorProfileEntry) -> SectorResolution:
    return resolve_sector_assignments(rows, as_of=AS_OF, source=SOURCE)


def test_known_code_resolves_to_its_chinese_name() -> None:
    resolution = _resolve(_row("2330", "24"))

    assert len(resolution.assignments) == 1
    assignment = resolution.assignments[0]
    assert assignment.symbol == "2330"
    assert assignment.market == "TW"
    assert assignment.sector == "半導體業"
    assert assignment.source == SOURCE
    assert assignment.as_of == AS_OF
    assert resolution.dropped_rows == 0


def test_every_assignment_is_a_value_the_position_validator_accepts() -> None:
    """The stored value is offered to the form as a default, so it must be saveable."""
    rows = [_row(f"{i:04d}", code) for i, code in enumerate(["01", "24", "28", "91"])]

    resolution = _resolve(*rows)

    assert len(resolution.assignments) == 4
    for assignment in resolution.assignments:
        assert is_valid_sector(assignment.sector)
        assert assignment.sector in TWSE_SECTORS


def test_unknown_code_is_dropped_and_reported_never_stored_raw() -> None:
    resolution = _resolve(_row("2330", "24"), _row("9921", "99"))

    assert [a.symbol for a in resolution.assignments] == ["2330"]
    assert resolution.unknown_code_rows == 1
    assert resolution.unknown_codes == ("99",)
    # The raw code must not have leaked through as if it were a category name.
    assert all(a.sector != "99" for a in resolution.assignments)


def test_repeated_unknown_code_counts_rows_but_lists_the_code_once() -> None:
    resolution = _resolve(_row("9921", "99"), _row("9922", "99"), _row("9923", "98"))

    assert resolution.unknown_code_rows == 3
    assert resolution.unknown_codes == ("98", "99")
    assert resolution.assignments == ()


def test_blank_code_is_dropped() -> None:
    resolution = _resolve(_row("7777", ""), _row("7778", "   "))

    assert resolution.assignments == ()
    assert resolution.blank_code_rows == 2


def test_name_outside_the_closed_list_is_dropped_and_reported() -> None:
    """A mapping-table name TWSE_SECTORS does not carry can never be auto-filled."""
    resolution = resolve_sector_assignments(
        [_row("2330", "24"), _row("1234", "77")],
        as_of=AS_OF,
        source=SOURCE,
        code_to_name={"24": "半導體業", "77": "尚未納入清單的產業"},
    )

    assert [a.symbol for a in resolution.assignments] == ["2330"]
    assert resolution.outside_closed_list_rows == 1
    assert resolution.outside_closed_list_names == ("尚未納入清單的產業",)


def test_duplicate_symbol_keeps_the_first_row() -> None:
    resolution = _resolve(_row("2330", "24"), _row("2330", "28"))

    assert len(resolution.assignments) == 1
    assert resolution.assignments[0].sector == "半導體業"
    assert resolution.duplicate_symbol_rows == 1


def test_empty_input_resolves_to_nothing() -> None:
    resolution = _resolve()

    assert resolution.assignments == ()
    assert resolution.dropped_rows == 0


def test_dropped_rows_sums_every_drop_bucket() -> None:
    resolution = _resolve(
        _row("2330", "24"),
        _row("9921", "99"),  # unknown code
        _row("7777", ""),  # blank
        _row("2330", "28"),  # duplicate
    )

    assert len(resolution.assignments) == 1
    assert resolution.dropped_rows == 3
