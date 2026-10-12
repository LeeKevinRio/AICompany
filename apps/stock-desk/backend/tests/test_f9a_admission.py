"""F-9a: symbol admission rules (design points ii and iii, constraint C-7).

Pure functions only: nothing here reaches a read or fetch path (that is F-9b).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.data import admission
from app.data.admission import (
    ADMISSION_RULES,
    TW_SYMBOL_RULE,
    US_SYMBOL_RULE,
    AdmissionReason,
    AdmissionResult,
    admit_symbol,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

# --- US: shape whitelist -------------------------------------------------------

US_ADMITTED = [
    "AAPL",
    "A",
    "GOOGL",
    "BRK.B",
    "BF.B",
    "BRK-B",
    # Known residual (docstring): a single-letter foreign exchange suffix has
    # the shape of a share class and cannot be told apart from one.
    "VOD.L",
]

US_REFUSED = [
    ("TSCO.LON", AdmissionReason.US_MULTI_CHAR_SUFFIX),
    ("RY.TO", AdmissionReason.US_MULTI_CHAR_SUFFIX),
    ("BRK.BB", AdmissionReason.US_MULTI_CHAR_SUFFIX),
    ("BRK-AB", AdmissionReason.US_MULTI_CHAR_SUFFIX),
    # Not canonical: F-9b must canonicalise before admission.
    ("AAPL.US", AdmissionReason.US_MULTI_CHAR_SUFFIX),
    # Refused for its numeric root, not for its single-letter suffix.
    ("7203.T", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("ABCDEF", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("ABCDEF.B", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("BRK.B.C", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("BRK..B", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("BRK-", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    (".B", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("BRK.1", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("aapl", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("BRK.b", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("AAPL\n", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    (" AAPL", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("\uff21\uff21\uff30\uff2c", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("^GSPC", AdmissionReason.US_SHAPE_NOT_ADMITTED),
    ("", AdmissionReason.US_SHAPE_NOT_ADMITTED),
]


@pytest.mark.parametrize("symbol", US_ADMITTED)
def test_us_admits_whitelisted_shapes(symbol: str) -> None:
    assert admit_symbol(symbol, "US") == AdmissionResult(
        admitted=True, reason=AdmissionReason.ADMITTED, rule_verified=False
    )


@pytest.mark.parametrize(("symbol", "reason"), US_REFUSED)
def test_us_refuses_everything_else(symbol: str, reason: AdmissionReason) -> None:
    assert admit_symbol(symbol, "US") == AdmissionResult(
        admitted=False, reason=reason, rule_verified=False
    )


# --- TW: precise blacklist of digits + K ---------------------------------------

TW_ADMITTED = ["0050", "2330", "6147", "00878", "00679B", "00631L", "00632R", "00635U", "K"]

TW_REFUSED = ["00636K", "00625K", "00703K", "2330K", "00636k"]


@pytest.mark.parametrize("symbol", TW_ADMITTED)
def test_tw_admits_twd_shapes_including_letter_suffixes(symbol: str) -> None:
    assert admit_symbol(symbol, "TW") == AdmissionResult(
        admitted=True, reason=AdmissionReason.ADMITTED, rule_verified=False
    )


@pytest.mark.parametrize("symbol", TW_REFUSED)
def test_tw_refuses_foreign_currency_units(symbol: str) -> None:
    assert admit_symbol(symbol, "TW") == AdmissionResult(
        admitted=False, reason=AdmissionReason.TW_FOREIGN_CURRENCY_UNIT, rule_verified=False
    )


def test_the_us_rule_does_not_apply_to_tw_and_back() -> None:
    # Markets are not interchangeable: a TW code is no US ticker and vice versa.
    assert admit_symbol("00679B", "US").admitted is False
    assert admit_symbol("TSCO.LON", "TW").admitted is True


def test_unknown_market_is_refused() -> None:
    assert admit_symbol("AAPL", "HK") == AdmissionResult(
        admitted=False, reason=AdmissionReason.UNKNOWN_MARKET, rule_verified=False
    )


# --- provenance and boundaries -------------------------------------------------


def test_every_rule_is_unverified_until_f9d() -> None:
    assert set(ADMISSION_RULES) == {"TW", "US"}
    assert ADMISSION_RULES["US"] is US_SYMBOL_RULE
    assert ADMISSION_RULES["TW"] is TW_SYMBOL_RULE
    for rule in ADMISSION_RULES.values():
        assert rule.verified is False
        assert rule.verified_on is None


def test_reason_codes_are_machine_readable() -> None:
    for reason in AdmissionReason:
        assert reason.value.isascii()
        assert reason.value == reason.value.lower()
        assert " " not in reason.value


def test_admission_is_not_wired_into_any_path_yet() -> None:
    """F-9a ships the rules only; the read and fetch paths stay as they were (F-9b wires them)."""
    users: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path.name == "admission.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.data.admission":
                users.append(str(path.relative_to(APP_ROOT)))
    assert users == ["data/diagnose.py"]


def test_module_holds_no_user_facing_wording() -> None:
    source = Path(admission.__file__).read_text(encoding="utf-8")
    assert source.isascii()
