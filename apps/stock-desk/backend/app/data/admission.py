"""Symbol admission: which ticker shapes the daily-bar ladder may ask about at all.

Task F-9 (dispatch of 2026-10-08 under ``work/dispatch/``), the tech-architect
assessment of 2026-10-12, design points (ii) and (iii). Every
adapter stamps the *market's* currency on the bars it returns, so a ticker that
names a security priced in another currency comes back with a foreign price
labelled USD or TWD. Admission is the shape check that keeps such a ticker out
before any source is asked.

F-9a shipped the rules as pure functions; F-9b wires them in front of layer 0
of both service entries (:func:`admit_equity_daily_bars`, injected by the
assembly layer; no cache read, no provider call, no quota, no attempt log for
a refused symbol -- ADR-0024 D-4) and into the Alpha Vantage adapter before
it reserves quota (defence in depth). The read-only inventory in
:mod:`app.data.diagnose` still calls :func:`admit_symbol` directly.

The result is structured -- admitted or not, plus a machine-readable reason
code -- and carries no sentence of any kind: what a reader is told about a
refused symbol is wording for creative-lead and risk-compliance-officer, and
belongs to F-9b.

US (design point ii): a whitelist of shapes. The root is 1-5 letters, followed
by at most one single-letter class (``.X`` or ``-X``), which keeps ``BRK.B``,
``BF.B`` and ``BRK-B``. A suffix of two or more characters (``TSCO.LON``,
``RY.TO``) is refused, as is any digit (``7203.T`` is refused for its numeric
root, not for its suffix). Known residuals, pinned by tests:

* a *single-letter* foreign exchange suffix has the very shape of a share
  class and is admitted (``VOD.L``, London) -- the rule cannot tell them apart;
* preferred shares, warrants and units written with a multi-letter suffix are
  refused along with the foreign listings.

The rule expects the canonical form (:func:`app.data.providers.us_symbols.canonical_us_symbol`:
stripped, upper-case, ``.US`` dropped). It does not canonicalise on its own,
so ``AAPL.US`` or ``aapl`` is refused here; F-9b must canonicalise first.

TW (design point iii): a precise blacklist. Digits followed by ``K`` name a
trading unit priced in a foreign currency and are refused; every other shape
is admitted. The letters ``B``, ``L``, ``R`` and ``U`` are legitimate TWD
suffixes (bond ETFs, leveraged and inverse ETFs, futures ETFs -- ``00679B``,
``00631L``, ``00632R``, ``00635U``) and must never be caught. TW symbols are
stored as typed (no case folding upstream), so a lower-case ``k`` is refused
too; the rule is otherwise exact and refuses nothing it was not written for.

Neither rule has been checked against a live response (no outbound network in
the environment that wrote it): each carries ``verified=False`` until F-9d
records the evidence and the date.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.data.providers.us_symbols import InvalidUsSymbolError, canonical_us_symbol


class AdmissionReason(StrEnum):
    """Machine-readable outcome of an admission check."""

    ADMITTED = "admitted"
    #: US: the shape matches no admitted form and has a suffix of two or
    #: more characters after ``.`` or ``-`` (typically an exchange code).
    US_MULTI_CHAR_SUFFIX = "us_multi_char_suffix"
    #: US: any other shape outside the whitelist (digits, a root longer than
    #: five letters, more than one separator, an empty string).
    US_SHAPE_NOT_ADMITTED = "us_shape_not_admitted"
    #: TW: digits followed by ``K``, a trading unit priced in a foreign currency.
    TW_FOREIGN_CURRENCY_UNIT = "tw_foreign_currency_unit"
    #: A market no rule exists for; refused rather than waved through.
    UNKNOWN_MARKET = "unknown_market"


@dataclass(frozen=True)
class AdmissionRule:
    """One market's shape rule, with its provenance.

    ``admits_on_match`` says how ``pattern`` is read: ``True`` for a whitelist
    (a symbol is admitted only if it matches), ``False`` for a blacklist (a
    symbol is refused if it matches). ``pattern`` is always applied with
    :meth:`re.Pattern.fullmatch`.
    """

    market: str
    pattern: re.Pattern[str]
    admits_on_match: bool
    reason_on_refusal: AdmissionReason
    verified: bool
    verified_on: str | None
    note: str


@dataclass(frozen=True)
class AdmissionResult:
    """Outcome of :func:`admit_symbol`: no wording, only codes and provenance."""

    admitted: bool
    reason: AdmissionReason
    #: Whether the rule that decided has been checked against a live response;
    #: ``False`` for every rule today, and for an unknown market.
    rule_verified: bool


#: ASCII ranges written out on purpose: ``\d`` would also accept non-ASCII
#: (e.g. full-width) digits, which no exchange code uses.
US_SYMBOL_RULE: Final = AdmissionRule(
    market="US",
    pattern=re.compile(r"[A-Z]{1,5}(?:[.\-][A-Z])?"),
    admits_on_match=True,
    reason_on_refusal=AdmissionReason.US_SHAPE_NOT_ADMITTED,
    verified=False,
    verified_on=None,
    note=(
        "Root of 1-5 letters with an optional single-letter class (.X or -X). "
        "A single-letter foreign exchange suffix (e.g. VOD.L) is admitted: known residual."
    ),
)

#: Only used to pick the more specific refusal code; never to admit anything.
_US_MULTI_CHAR_SUFFIX: Final = re.compile(r"[A-Z0-9]+[.\-][A-Z0-9]{2,}")

TW_SYMBOL_RULE: Final = AdmissionRule(
    market="TW",
    pattern=re.compile(r"[0-9]+[Kk]"),
    admits_on_match=False,
    reason_on_refusal=AdmissionReason.TW_FOREIGN_CURRENCY_UNIT,
    verified=False,
    verified_on=None,
    note=(
        "Digits followed by K: a trading unit priced in a foreign currency. "
        "B, L, R and U suffixes are TWD-priced and stay admitted."
    ),
)

#: market -> its rule. A market absent here is refused (fail-closed).
ADMISSION_RULES: Final[dict[str, AdmissionRule]] = {
    US_SYMBOL_RULE.market: US_SYMBOL_RULE,
    TW_SYMBOL_RULE.market: TW_SYMBOL_RULE,
}


def admit_symbol(symbol: str, market: str) -> AdmissionResult:
    """Whether ``symbol`` may be asked about as a ``market`` daily-bar series.

    Pure: no I/O, no logging, no normalisation of ``symbol``. Index series
    (``^``-prefixed) are outside this check by design (ADR-0024 draft D-4: the
    index service checks currency only, never shape); callers must not route
    them here.
    """
    rule = ADMISSION_RULES.get(market)
    if rule is None:
        return AdmissionResult(
            admitted=False, reason=AdmissionReason.UNKNOWN_MARKET, rule_verified=False
        )
    matched = rule.pattern.fullmatch(symbol) is not None
    if matched == rule.admits_on_match:
        return AdmissionResult(
            admitted=True, reason=AdmissionReason.ADMITTED, rule_verified=rule.verified
        )
    reason = rule.reason_on_refusal
    if rule is US_SYMBOL_RULE and _US_MULTI_CHAR_SUFFIX.fullmatch(symbol) is not None:
        reason = AdmissionReason.US_MULTI_CHAR_SUFFIX
    return AdmissionResult(admitted=False, reason=reason, rule_verified=rule.verified)


#: How a daily-bar service decides whether a symbol may be asked about at all
#: (ADR-0024 D-4): ``(symbol, market) -> admitted``. Injected by the assembly
#: layer as a required argument; never defaulted.
SymbolAdmission = Callable[[str, str], bool]


def admit_equity_daily_bars(symbol: str, market: str) -> bool:
    """The equity ladders' admission: :func:`admit_symbol` on the canonical form.

    A US symbol is judged in its :func:`canonical_us_symbol` form (stripped,
    upper-case, ``.US`` dropped) -- the form every source is asked with -- and
    one that cannot be canonicalised is refused. The symbol handed on to the
    sources is never rewritten here (ADR-0024 D-4, verification note).
    """
    candidate = symbol
    if market == "US":
        try:
            candidate = canonical_us_symbol(symbol)
        except InvalidUsSymbolError:
            return False
    return admit_symbol(candidate, market).admitted


def admit_any_shape(symbol: str, market: str) -> bool:
    """The index ladder's admission: no shape is checked, only the currency is (D-4).

    Passed explicitly by the index construction point -- never a default -- and
    never inferred from a ``^`` prefix (TA5 R-59).
    """
    return True
