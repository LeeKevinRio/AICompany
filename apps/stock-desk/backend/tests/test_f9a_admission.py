"""F-9a: symbol admission rules (design points ii and iii, constraint C-7).

Pure functions only: nothing here reaches a read or fetch path (that is F-9b).
"""

from __future__ import annotations

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
from tests.import_graph import APP_ROOT, imported_modules

ADMISSION_MODULE = "app.data.admission"

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


def _module_name(path: Path) -> str:
    parts = path.relative_to(APP_ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(("app", *parts))


def _imports_admission(path: Path) -> bool:
    """Every spelling: ``import``, ``from ... import``, aliases and relative forms."""
    return ADMISSION_MODULE in imported_modules(path, _module_name(path))


def test_admission_is_wired_only_where_adr_0024_puts_it() -> None:
    """F-9a shipped the rules only; F-9b commit 7 wires them, and nowhere else.

    Rewritten for F-9b commit 7 (was ``test_admission_is_not_wired_into_any_path_yet``):
    the assembly layer injects it (``api/deps.py``), the service applies it at
    both entries (``data/service.py``), the Alpha Vantage adapter checks again
    before reserving quota (``data/providers/alpha_vantage.py``, D-4 defence in
    depth), and the inventory still reads it (``data/diagnose.py``).
    """
    users = [
        str(path.relative_to(APP_ROOT))
        for path in sorted(APP_ROOT.rglob("*.py"))
        if path.name != "admission.py" and _imports_admission(path)
    ]
    assert users == [
        "api/deps.py",
        "data/diagnose.py",
        "data/providers/alpha_vantage.py",
        "data/service.py",
    ]


@pytest.mark.parametrize(
    "statement",
    [
        "from app.data.admission import admit_symbol",
        "from app.data.admission import admit_symbol as admit",
        "import app.data.admission",
        "import app.data.admission as adm",
        "from app.data import admission",
        "from app.data import admission as adm",
        "from . import admission",
        "from .admission import admit_symbol",
        "def f():\n    import app.data.admission\n",
    ],
)
def test_the_wiring_guard_sees_every_import_spelling(tmp_path: Path, statement: str) -> None:
    source = tmp_path / "service.py"
    source.write_text(statement + "\n", encoding="utf-8")
    assert ADMISSION_MODULE in imported_modules(source, "app.data.service")


def test_module_holds_no_user_facing_wording() -> None:
    source = Path(admission.__file__).read_text(encoding="utf-8")
    assert source.isascii()
