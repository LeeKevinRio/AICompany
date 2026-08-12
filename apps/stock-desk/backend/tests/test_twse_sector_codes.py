"""Coverage test for ``app.directory.twse_sector_codes``.

Pins the one hard requirement this module exists to satisfy: every TWSE
產業別 code CEO's first real ``--verify-sectors`` run actually observed
(2026-08-12, 33 distinct codes against production TWSE data) must resolve
to a name, i.e. the mapping table must not be missing any of them. A
regression here means a real, previously-seen code would now surface as a
spurious UNKNOWN_CODE finding.
"""

from __future__ import annotations

from app.directory.twse_sector_codes import (
    CEO_OBSERVED_CODES,
    TWSE_SECTOR_CODE_TO_NAME,
    resolve_sector_name,
)


def test_ceo_observed_codes_count_matches_the_real_run() -> None:
    assert len(CEO_OBSERVED_CODES) == 33


def test_every_ceo_observed_code_resolves_to_a_name() -> None:
    missing = CEO_OBSERVED_CODES - TWSE_SECTOR_CODE_TO_NAME.keys()

    assert missing == set(), f"table is missing codes CEO's real run saw: {sorted(missing)}"


def test_every_ceo_observed_code_resolves_via_resolve_sector_name() -> None:
    for code in sorted(CEO_OBSERVED_CODES):
        name = resolve_sector_name(code)
        assert name is not None, f"code {code!r} did not resolve"
        assert name.strip() == name
        assert name != ""


def test_resolve_sector_name_returns_none_for_unknown_code() -> None:
    assert resolve_sector_name("99") is None


def test_all_codes_are_two_digit_strings() -> None:
    for code in TWSE_SECTOR_CODE_TO_NAME:
        assert len(code) == 2
        assert code.isdigit()
