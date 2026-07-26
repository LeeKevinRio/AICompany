"""Leveraged-ETF symbol -> queryable underlying-index code (ADR-0005 decision 2).

MAPPING-PROVENANCE NOTICE
========================
``detect.KNOWN_LEVERAGED_ETF`` answers "what does the issuer say this fund
tracks", as a human-readable sentence. This table answers a *different*
question: "which queryable series code is that index, and on what return
basis". The two facts are verified against different primary sources (issuer
prospectus vs. data-source availability), so they carry **separate** verified
flags rather than sharing one -- see ADR-0005 decision 2.

Nothing here has been checked against a live response in this sandbox:
``MAPPING_VERIFIED_ON`` is ``None`` and every row is ``verified=False``. Only
devops-sre may flip a row to ``verified=True`` after actually querying the code
in a networked environment, and must set ``verified_on`` at the same time.

Module discipline (ADR-0005 constraints I-1 / C-1):

* pure data and pure functions -- **no I/O**, and no import of
  ``app.data.providers.*``. Who fetches ``^NDX`` is data-layer knowledge and
  lives in ``app/services/index.py``;
* the key is the normalized ETF symbol, never the ``underlying_index``
  description string: a description is prose for humans, and a single edited
  bracket would make the lookup fail silently;
* ``unmapped`` is expressed as a **present row**, never as an absent one.
  "Never looked into it" and "looked into it, cannot be obtained" are different
  facts, and ``note`` is where the second one is written down.

Phase 7 release list: 12 mapped rows, 5 ``unmapped`` rows. ``proxy_etf`` exists
as a value in :data:`IndexBasis` but **no row may use it** -- substituting a
tracking ETF for its index would fold the proxy's own expense ratio and
tracking error into the ``residual``/``reset_effect`` split that
``app/leverage/drag.py`` reports as clean attribution numbers. Enabling one is
a CEO decision plus a new ADR, not an edit here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from app.data.interface import Market
from app.leverage.detect import normalize_symbol

#: How the series in :class:`IndexRef` relates to the fund's stated benchmark.
#:
#: ``official_index``  the index itself, by its own code (the only kind Phase 7
#:                     releases);
#: ``proxy_etf``       a tracking ETF standing in for the index -- reserved,
#:                     and blocked at the data level (constraint I-2);
#: ``unmapped``        no queryable code is established for this benchmark.
IndexBasis = Literal["official_index", "proxy_etf", "unmapped"]

#: Whether the series includes dividends. ``unknown`` until verified; the
#: difference then lands in the drag decomposition's ``residual``.
ReturnBasis = Literal["price", "total_return", "unknown"]

#: ISO date this whole table was last verified against live responses.
#: ``None`` means UNVERIFIED -- devops-sre sets it (see the module docstring).
MAPPING_VERIFIED_ON: Final[str | None] = None

#: Index series codes carry this prefix, which keeps them in a namespace no
#: canonical equity ticker can occupy (constraint I-7: an index series must
#: never be written under the same cache key as a stock).
INDEX_SYMBOL_PREFIX: Final = "^"


@dataclass(frozen=True)
class IndexRef:
    """One ETF's underlying index expressed as a queryable series.

    ``series_market`` is the market the *index series* is sourced from, not the
    market the ETF trades in: 00670L is a Taiwan-listed fund whose benchmark
    (``^NDX``) is a US series. For an ``unmapped`` row it records where such a
    series would have to come from, so the row stays informative.
    """

    etf_symbol: str
    #: Verbatim snapshot of ``detect.KNOWN_LEVERAGED_ETF[...].underlying_index``,
    #: compared character by character by the drift test (constraint C-4).
    underlying_index_text: str
    basis: IndexBasis
    #: e.g. ``"^NDX"``; ``None`` when ``basis == "unmapped"``.
    series_symbol: str | None
    series_market: Market
    return_basis: ReturnBasis
    #: Whether the *code's availability* was checked against a live response.
    verified: bool = False
    verified_on: str | None = None
    #: For an ``unmapped`` row: why the series cannot be obtained, and why no
    #: proxy is substituted. Required (constraint C-5).
    note: str = ""


def _mapped(
    etf_symbol: str,
    *,
    underlying_index_text: str,
    series_symbol: str,
    series_market: Market,
    return_basis: ReturnBasis,
    note: str = "",
) -> IndexRef:
    """An ``official_index`` row. ``verified`` is not a parameter on purpose."""
    return IndexRef(
        etf_symbol=etf_symbol,
        underlying_index_text=underlying_index_text,
        basis="official_index",
        series_symbol=series_symbol,
        series_market=series_market,
        return_basis=return_basis,
        verified=False,
        verified_on=MAPPING_VERIFIED_ON,
        note=note,
    )


def _unmapped(
    etf_symbol: str,
    *,
    underlying_index_text: str,
    series_market: Market,
    note: str,
) -> IndexRef:
    """An ``unmapped`` row: a stated absence, with its reason attached."""
    return IndexRef(
        etf_symbol=etf_symbol,
        underlying_index_text=underlying_index_text,
        basis="unmapped",
        series_symbol=None,
        series_market=series_market,
        return_basis="unknown",
        verified=False,
        verified_on=MAPPING_VERIFIED_ON,
        note=note,
    )


_TW50_NOTE: Final = (
    "臺灣50指數目前沒有已查證的免費日線代號可查詢，因此取不到指數序列；"
    "也不以 0050 等追蹤 ETF 代理，代理標的自身的經理費與折溢價會混進報酬拆解，"
    "使費用效應、重置效應與殘差三項數字失真。"
)

_US_TREASURY_NOTE: Final = (
    "ICE 美國政府20+年期債券指數沒有已查證的免費日線來源可查詢，因此取不到指數序列；"
    "也不以 TLT 等追蹤 ETF 代理，代理標的自身的經理費與折溢價會混進報酬拆解，"
    "使費用效應、重置效應與殘差三項數字失真。"
)

_SEMICONDUCTOR_NOTE: Final = (
    "註冊表登記的標的指數為 ICE Semiconductor Index，"
    "公開常見的 ^SOX 是另一支半導體指數，兩者並非同一標的，查證前無法確定可查詢代號；"
    "也不以任何半導體 ETF 代理，代理序列會使費用效應、重置效應與殘差三項數字失真。"
)

_TWII_NOTE: Final = (
    "註冊表記為臺灣加權股價指數；該類基金常以期貨複製，且可能對應報酬指數，"
    "含息口徑未查證，差異會落在殘差。"
)

_SP500_NOTE: Final = "以價格指數對應，含息差異落在殘差。"


#: normalized ETF symbol -> its underlying index as a queryable series.
#: Every key must exist in ``detect.KNOWN_LEVERAGED_ETF`` (C-2) and every
#: registry row must appear here (C-3), including as an ``unmapped`` row.
INDEX_MAPPING: Final[dict[str, IndexRef]] = {
    # --- NASDAQ-100 ---------------------------------------------------------
    "00670L": _mapped(
        "00670L",
        underlying_index_text="NASDAQ-100 指數（單日報酬正向兩倍）",
        series_symbol="^NDX",
        series_market="US",
        return_basis="unknown",
    ),
    "TQQQ": _mapped(
        "TQQQ",
        underlying_index_text="NASDAQ-100 Index (3x single-day)",
        series_symbol="^NDX",
        series_market="US",
        return_basis="unknown",
    ),
    "SQQQ": _mapped(
        "SQQQ",
        underlying_index_text="NASDAQ-100 Index (-3x single-day)",
        series_symbol="^NDX",
        series_market="US",
        return_basis="unknown",
    ),
    "QLD": _mapped(
        "QLD",
        underlying_index_text="NASDAQ-100 Index (2x single-day)",
        series_symbol="^NDX",
        series_market="US",
        return_basis="unknown",
    ),
    # --- S&P 500 ------------------------------------------------------------
    "SSO": _mapped(
        "SSO",
        underlying_index_text="S&P 500 Index (2x single-day)",
        series_symbol="^GSPC",
        series_market="US",
        return_basis="price",
        note=_SP500_NOTE,
    ),
    "SDS": _mapped(
        "SDS",
        underlying_index_text="S&P 500 Index (-2x single-day)",
        series_symbol="^GSPC",
        series_market="US",
        return_basis="price",
        note=_SP500_NOTE,
    ),
    "SH": _mapped(
        "SH",
        underlying_index_text="S&P 500 Index (-1x single-day)",
        series_symbol="^GSPC",
        series_market="US",
        return_basis="price",
        note=_SP500_NOTE,
    ),
    "UPRO": _mapped(
        "UPRO",
        underlying_index_text="S&P 500 Index (3x single-day)",
        series_symbol="^GSPC",
        series_market="US",
        return_basis="price",
        note=_SP500_NOTE,
    ),
    "SPXL": _mapped(
        "SPXL",
        underlying_index_text="S&P 500 Index (3x single-day)",
        series_symbol="^GSPC",
        series_market="US",
        return_basis="price",
        note=_SP500_NOTE,
    ),
    "SPXS": _mapped(
        "SPXS",
        underlying_index_text="S&P 500 Index (-3x single-day)",
        series_symbol="^GSPC",
        series_market="US",
        return_basis="price",
        note=_SP500_NOTE,
    ),
    # --- Taiwan weighted index ----------------------------------------------
    "00675L": _mapped(
        "00675L",
        underlying_index_text="臺灣加權股價指數（單日報酬正向兩倍）",
        series_symbol="^TWII",
        series_market="TW",
        return_basis="unknown",
        note=_TWII_NOTE,
    ),
    "00676R": _mapped(
        "00676R",
        underlying_index_text="臺灣加權股價指數（單日報酬反向一倍）",
        series_symbol="^TWII",
        series_market="TW",
        return_basis="unknown",
        note=_TWII_NOTE,
    ),
    # --- Stated absences ----------------------------------------------------
    "00631L": _unmapped(
        "00631L",
        underlying_index_text="臺灣50指數（單日報酬正向兩倍）",
        series_market="TW",
        note=_TW50_NOTE,
    ),
    "00632R": _unmapped(
        "00632R",
        underlying_index_text="臺灣50指數（單日報酬反向一倍）",
        series_market="TW",
        note=_TW50_NOTE,
    ),
    "00680L": _unmapped(
        "00680L",
        underlying_index_text="ICE 美國政府20+年期債券指數（單日報酬正向兩倍）",
        series_market="US",
        note=_US_TREASURY_NOTE,
    ),
    "SOXL": _unmapped(
        "SOXL",
        underlying_index_text="ICE Semiconductor Index (3x single-day)",
        series_market="US",
        note=_SEMICONDUCTOR_NOTE,
    ),
    "SOXS": _unmapped(
        "SOXS",
        underlying_index_text="ICE Semiconductor Index (-3x single-day)",
        series_market="US",
        note=_SEMICONDUCTOR_NOTE,
    ),
}


def lookup_index_ref(symbol: str) -> IndexRef | None:
    """Return the index reference for ``symbol``, or ``None`` if it has no row.

    ``None`` means "this symbol is not in the table at all", which is a
    different state from a present ``unmapped`` row ("in the table, and the
    series is established to be unobtainable"). Callers must keep them apart.
    """
    return INDEX_MAPPING.get(normalize_symbol(symbol))


def has_queryable_series(ref: IndexRef | None) -> bool:
    """Whether ``ref`` names a series this build is allowed to fetch.

    Only ``official_index`` qualifies: ``proxy_etf`` is reserved but blocked
    (constraint I-2), and ``unmapped`` has no code by definition.
    """
    return ref is not None and ref.basis == "official_index" and ref.series_symbol is not None
