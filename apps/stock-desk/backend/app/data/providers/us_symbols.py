"""Canonical U.S.-market ticker symbols and per-provider symbol conversion.

ADR-0005 (stock-desk 指數來源與美股額度管理), 決策三 "ticker 正規化":

- **Canonical form is the dotted form** (``BRK.B``, ``BF.B``), matching what a
  user types or imports via CSV and what ``app.leverage.detect.normalize_symbol``
  already expects. Every ``PriceBar.symbol`` and every cache key for a US-market
  symbol MUST be this canonical form -- never a provider-specific spelling.
- :func:`canonical_us_symbol` only *validates and cleans* a raw string (strip,
  upper-case, drop a trailing ``.US`` suffix, and reject characters outside
  ``[A-Z0-9.-]``). It deliberately does **not** rewrite a hyphenated symbol
  into dotted form: a hyphen is a legal canonical character (some tickers use
  it natively), and a hyphen->dot rewrite would not be a safe, reversible
  operation. Callers upstream of the data layer (position input, CSV import)
  are responsible for supplying the dotted convention consistently; this
  function's job is only to reject clearly malformed input and to be the one
  place every US provider adapter goes through before touching a symbol.
- ``^``-prefixed strings (index symbols like ``^NDX``) are rejected outright.
  Index series are a structurally separate path (see
  ``app/data/providers/yfinance.py``'s ``get_index_daily_bars``) that never
  goes through this module, per ADR-0005 決策三 point 5 ("^ 前綴專屬指數路徑").
- Each provider then converts canonical -> its own wire format via
  :func:`to_provider_symbol`, a declarative default rule plus a table of
  explicit overrides (:data:`US_SYMBOL_OVERRIDES`). **This conversion is
  one-directional (canonical -> provider) on purpose** -- ADR-0005 decision
  three explicitly rejects a reverse mapping because it is not guaranteed to
  be invertible. A ``PriceBar`` returned by any provider must therefore carry
  the *canonical* symbol it was asked for, never the provider-wire symbol it
  used to build the HTTP request.

UNVERIFIED (see ``tests/fixtures/README.md``): every entry in
:data:`US_SYMBOL_OVERRIDES`, and the default rules themselves, are the
model's best understanding of each vendor's ticker convention. None of it has
been checked against a live response in this sandbox (outbound HTTPS is
blocked). In particular Alpha Vantage's handling of multi-class symbols like
``BRK.B`` has not been confirmed at all -- see ADR-0005 "尚缺的事實" #6 -- so
its default rule is the most conservative option (identity: pass the
canonical dotted form straight through) until someone verifies otherwise in a
networked environment.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

#: Canonical symbols are upper-case and made only of letters, digits, '.', '-'.
_VALID_CHARS_RE: Final = re.compile(r"^[A-Z0-9.\-]+$")

#: Suffix some CSV/import conventions append to disambiguate a market; it
#: carries no information once ``Market`` is already "US", so it is dropped.
_US_MARKET_SUFFIX: Final = ".US"

#: Provider identifiers this module knows a default conversion rule for.
ALPHA_VANTAGE_PROVIDER_ID: Final = "alpha_vantage"
YFINANCE_PROVIDER_ID: Final = "yfinance"


class InvalidUsSymbolError(ValueError):
    """Raised when a raw string cannot be normalized into a canonical US ticker.

    This is an *expected* failure mode (bad user input, typo, or -- most
    importantly -- an index symbol misrouted into the per-security path), not
    a bug. Callers in the data layer must catch it and degrade to
    ``DataStatus.UNAVAILABLE`` rather than letting it propagate as a 500.
    """


def canonical_us_symbol(raw: str) -> str:
    """Normalize ``raw`` into the canonical dotted-form US ticker.

    Steps: strip whitespace -> upper-case -> drop a trailing ``.US`` suffix
    -> reject anything outside ``[A-Z0-9.-]`` (this also rejects a leading
    ``^``, since ``^`` is not in the allowed character set) -> reject an
    empty result.
    """
    if raw is None:  # defensive; type checkers already forbid this
        raise InvalidUsSymbolError("symbol must not be None")
    value = raw.strip().upper()
    if not value:
        raise InvalidUsSymbolError(f"symbol {raw!r} is blank after stripping whitespace")
    if value.startswith("^"):
        raise InvalidUsSymbolError(
            f"symbol {raw!r} starts with '^', which marks an index series, not a "
            "security; index series must not go through canonical_us_symbol() "
            "(see app.data.providers.yfinance.get_index_daily_bars)"
        )
    if value.endswith(_US_MARKET_SUFFIX):
        value = value[: -len(_US_MARKET_SUFFIX)]
    if not value:
        raise InvalidUsSymbolError(f"symbol {raw!r} has nothing left after stripping .US suffix")
    if not _VALID_CHARS_RE.match(value):
        raise InvalidUsSymbolError(
            f"symbol {raw!r} contains characters other than A-Z, 0-9, '.', '-'"
        )
    return value


@dataclass(frozen=True)
class SymbolOverride:
    """One explicit canonical -> provider-symbol exception to a default rule.

    Kept separate from the default rule (rather than baked into a bigger
    if/else) so every override carries its own provenance: which symbol,
    why it needed an exception, and whether that exception has ever been
    checked against a live response.
    """

    provider_symbol: str
    note: str
    verified: bool = False
    verified_on: str | None = None


#: ISO date the table below was verified against a live provider response, if
#: ever. ``None`` means every row (there currently are none) is unverified.
US_SYMBOL_OVERRIDES_VERIFIED_ON: Final[str | None] = None

#: provider_id -> canonical_symbol -> override. Empty today: the default
#: rules below are believed to already cover every symbol Phase 7 needs
#: (single- and multi-class dotted tickers). Add a row here -- with a `note`
#: explaining why the default rule is wrong for that symbol -- only once a
#: real mismatch is found; do not pre-populate speculative entries.
US_SYMBOL_OVERRIDES: Final[dict[str, dict[str, SymbolOverride]]] = {
    ALPHA_VANTAGE_PROVIDER_ID: {},
    YFINANCE_PROVIDER_ID: {},
}


def _yahoo_family_default_rule(canonical: str) -> str:
    """Yahoo-family default: ``.`` -> ``-`` (e.g. ``BRK.B`` -> ``BRK-B``).

    UNVERIFIED (per module docstring): this is the widely-cited convention
    for Yahoo Finance multi-class tickers, not a fact checked against a live
    response in this sandbox.
    """
    return canonical.replace(".", "-")


def _alpha_vantage_default_rule(canonical: str) -> str:
    """Alpha Vantage default: identity (kept in canonical dotted form).

    UNVERIFIED and, unlike the Yahoo-family rule, not even backed by a widely
    cited convention: Alpha Vantage's accepted format for multi-class symbols
    such as ``BRK.B`` has not been confirmed in any way in this build (ADR-0005
    "尚缺的事實" #6). Identity is the conservative default -- it does not
    invent a transformation nobody has verified.
    """
    return canonical


_DEFAULT_RULES: Final[dict[str, Callable[[str], str]]] = {
    ALPHA_VANTAGE_PROVIDER_ID: _alpha_vantage_default_rule,
    YFINANCE_PROVIDER_ID: _yahoo_family_default_rule,
}


def to_provider_symbol(canonical: str, *, provider_id: str) -> str:
    """Convert a canonical US symbol to ``provider_id``'s wire format.

    One-directional only (see module docstring): there is no corresponding
    ``from_provider_symbol``. Looks up an explicit override first, falling
    back to the provider's declarative default rule.
    """
    override = US_SYMBOL_OVERRIDES.get(provider_id, {}).get(canonical)
    if override is not None:
        return override.provider_symbol
    rule = _DEFAULT_RULES.get(provider_id)
    if rule is None:
        raise ValueError(f"no symbol conversion rule registered for provider {provider_id!r}")
    return rule(canonical)
