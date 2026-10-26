"""Currency minor-unit table. The only place that knows decimal places per currency."""

from __future__ import annotations

# ISO 4217 minor unit exponents for currencies this app may encounter.
_MINOR_UNITS: dict[str, int] = {
    "TWD": 2,
    "USD": 2,
    "EUR": 2,
    "HKD": 2,
    "SGD": 2,
    "THB": 2,
    "KRW": 0,
    "JPY": 0,
    "RUB": 2,
}

DEFAULT_CURRENCY = "TWD"


class UnknownCurrencyError(ValueError):
    pass


def minor_units(currency: str) -> int:
    try:
        return _MINOR_UNITS[currency.upper()]
    except KeyError as exc:
        raise UnknownCurrencyError(currency) from exc


def _scale(currency: str) -> int:
    scale = 1
    for _ in range(minor_units(currency)):
        scale *= 10
    return scale


def major_to_minor(amount_major: int, currency: str) -> int:
    """Convert a whole-unit integer amount (as quoted by sources/forms) to minor units."""
    if isinstance(amount_major, bool) or not isinstance(amount_major, int):
        raise TypeError("amount must be an int")
    return amount_major * _scale(currency)


def minor_to_major_str(amount_minor: int, currency: str) -> str:
    """Format minor units as a grouped decimal string without float arithmetic."""
    exponent = minor_units(currency)
    sign = "-" if amount_minor < 0 else ""
    whole, frac = divmod(abs(amount_minor), _scale(currency))
    text = f"{whole:,}"
    if exponent and frac:
        text += "." + str(frac).rjust(exponent, "0")
    return sign + text


def format_money(amount_minor: int, currency: str) -> str:
    return f"{currency.upper()} {minor_to_major_str(amount_minor, currency)}"


def minor_to_major_int(amount_minor: int, currency: str) -> int:
    """Whole units, truncating any fraction (used to prefill forms)."""
    return amount_minor // _scale(currency)
