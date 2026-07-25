"""Detect daily-reset leveraged / inverse ETFs and look up their metadata.

METADATA-PROVENANCE NOTICE
==========================
Every entry in :data:`KNOWN_LEVERAGED_ETF` (leverage factor, underlying index,
annual expense ratio) comes from the model's **training knowledge**. This build
environment has no verified online source for fund fact sheets, so none of these
figures could be checked against the issuer's primary document. They are
therefore carried as data on a registry with an explicit ``verified=False`` flag
and a ``source_note``, exactly like the rate-provenance convention in
``app/backtest/costs.py`` -- never as constants baked into a formula.

ACTION FOR data-engineer: once a networked environment is available, verify each
row against the issuer's prospectus / fact sheet (元大投信、富邦投信、ProShares、
Direxion ...), then set ``verified=True`` and ``REGISTRY_VERIFIED_ON``. Until
then every number this package derives from an expense ratio must be read as
"subject to metadata verification".

Detection rule (deliberately conservative):

* ``instrument_type == "leveraged_etf"`` is the primary signal that the user's
  holding is a daily-reset product.
* The registry is the source of the *quantitative* metadata. A holding flagged
  ``leveraged_etf`` with no registry row is ``insufficient_data`` -- we do not
  guess a leverage factor or an expense ratio.
* ``futures_etf`` alone is **not** treated as daily-reset leveraged; a futures
  ETF has roll mechanics, not a daily leverage reset, and conflating them would
  attribute the wrong cause to the wrong number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from app.positions.models import InstrumentType, Position

DetectionStatus = Literal["ok", "insufficient_data", "not_applicable"]

#: ISO date the registry below was last verified against issuer primary sources.
#: ``None`` means UNVERIFIED -- data-engineer to set once online.
REGISTRY_VERIFIED_ON: Final[str | None] = None

_UNVERIFIED_NOTE: Final = "倍數與費用率為模型訓練知識，尚未經線上主要來源查證（verified=false）。"

_LEVERAGED_INSTRUMENT_TYPE: Final[InstrumentType] = "leveraged_etf"

#: Market suffixes stripped before a registry lookup ("00631L.TW" -> "00631L").
_SYMBOL_SUFFIXES: Final = (".TWO", ".TW", ".US")


@dataclass(frozen=True)
class LeverageMetadata:
    """Static facts about one daily-reset leveraged / inverse ETF.

    ``leverage_factor`` is the fund's stated **single-day** multiple of the
    underlying index return (``-1.0`` for a one-times inverse fund), not a
    multiple of any longer-horizon return -- which is precisely the distinction
    :mod:`app.leverage.drag` quantifies.
    """

    symbol: str
    leverage_factor: float
    underlying_index: str
    expense_ratio_annual: float
    source_note: str
    verified: bool = False
    verified_on: str | None = None


def _entry(
    symbol: str,
    *,
    leverage_factor: float,
    underlying_index: str,
    expense_ratio_annual: float,
    issuer_note: str,
) -> LeverageMetadata:
    return LeverageMetadata(
        symbol=symbol,
        leverage_factor=leverage_factor,
        underlying_index=underlying_index,
        expense_ratio_annual=expense_ratio_annual,
        source_note=f"{issuer_note}；{_UNVERIFIED_NOTE}",
        verified=False,
        verified_on=REGISTRY_VERIFIED_ON,
    )


#: symbol -> metadata. Common TW and US daily-reset products; ALL UNVERIFIED.
KNOWN_LEVERAGED_ETF: Final[dict[str, LeverageMetadata]] = {
    # --- Taiwan -------------------------------------------------------------
    "00631L": _entry(
        "00631L",
        leverage_factor=2.0,
        underlying_index="臺灣50指數（單日報酬正向兩倍）",
        expense_ratio_annual=0.0113,
        issuer_note="元大台灣50正2，元大投信",
    ),
    "00632R": _entry(
        "00632R",
        leverage_factor=-1.0,
        underlying_index="臺灣50指數（單日報酬反向一倍）",
        expense_ratio_annual=0.0113,
        issuer_note="元大台灣50反1，元大投信",
    ),
    "00675L": _entry(
        "00675L",
        leverage_factor=2.0,
        underlying_index="臺灣加權股價指數（單日報酬正向兩倍）",
        expense_ratio_annual=0.0120,
        issuer_note="富邦臺灣加權正2，富邦投信",
    ),
    "00676R": _entry(
        "00676R",
        leverage_factor=-1.0,
        underlying_index="臺灣加權股價指數（單日報酬反向一倍）",
        expense_ratio_annual=0.0120,
        issuer_note="富邦臺灣加權反1，富邦投信",
    ),
    "00670L": _entry(
        "00670L",
        leverage_factor=2.0,
        underlying_index="NASDAQ-100 指數（單日報酬正向兩倍）",
        expense_ratio_annual=0.0130,
        issuer_note="富邦NASDAQ正2，富邦投信",
    ),
    "00680L": _entry(
        "00680L",
        leverage_factor=2.0,
        underlying_index="ICE 美國政府20+年期債券指數（單日報酬正向兩倍）",
        expense_ratio_annual=0.0130,
        issuer_note="元大美債20正2，元大投信",
    ),
    # --- United States ------------------------------------------------------
    "TQQQ": _entry(
        "TQQQ",
        leverage_factor=3.0,
        underlying_index="NASDAQ-100 Index (3x single-day)",
        expense_ratio_annual=0.0088,
        issuer_note="ProShares UltraPro QQQ",
    ),
    "SQQQ": _entry(
        "SQQQ",
        leverage_factor=-3.0,
        underlying_index="NASDAQ-100 Index (-3x single-day)",
        expense_ratio_annual=0.0095,
        issuer_note="ProShares UltraPro Short QQQ",
    ),
    "QLD": _entry(
        "QLD",
        leverage_factor=2.0,
        underlying_index="NASDAQ-100 Index (2x single-day)",
        expense_ratio_annual=0.0095,
        issuer_note="ProShares Ultra QQQ",
    ),
    "SSO": _entry(
        "SSO",
        leverage_factor=2.0,
        underlying_index="S&P 500 Index (2x single-day)",
        expense_ratio_annual=0.0089,
        issuer_note="ProShares Ultra S&P500",
    ),
    "SDS": _entry(
        "SDS",
        leverage_factor=-2.0,
        underlying_index="S&P 500 Index (-2x single-day)",
        expense_ratio_annual=0.0089,
        issuer_note="ProShares UltraShort S&P500",
    ),
    "SH": _entry(
        "SH",
        leverage_factor=-1.0,
        underlying_index="S&P 500 Index (-1x single-day)",
        expense_ratio_annual=0.0089,
        issuer_note="ProShares Short S&P500",
    ),
    "UPRO": _entry(
        "UPRO",
        leverage_factor=3.0,
        underlying_index="S&P 500 Index (3x single-day)",
        expense_ratio_annual=0.0091,
        issuer_note="ProShares UltraPro S&P500",
    ),
    "SPXL": _entry(
        "SPXL",
        leverage_factor=3.0,
        underlying_index="S&P 500 Index (3x single-day)",
        expense_ratio_annual=0.0091,
        issuer_note="Direxion Daily S&P 500 Bull 3X",
    ),
    "SPXS": _entry(
        "SPXS",
        leverage_factor=-3.0,
        underlying_index="S&P 500 Index (-3x single-day)",
        expense_ratio_annual=0.0101,
        issuer_note="Direxion Daily S&P 500 Bear 3X",
    ),
    "SOXL": _entry(
        "SOXL",
        leverage_factor=3.0,
        underlying_index="ICE Semiconductor Index (3x single-day)",
        expense_ratio_annual=0.0075,
        issuer_note="Direxion Daily Semiconductor Bull 3X",
    ),
    "SOXS": _entry(
        "SOXS",
        leverage_factor=-3.0,
        underlying_index="ICE Semiconductor Index (-3x single-day)",
        expense_ratio_annual=0.0103,
        issuer_note="Direxion Daily Semiconductor Bear 3X",
    ),
}


class LeverageDetection(BaseModel):
    """Whether a holding is a daily-reset leveraged product, and its metadata.

    Three distinct states, kept separate on purpose:

    ``ok``
        Registry metadata found; the quantitative blocks can be computed.
    ``insufficient_data``
        The holding is (or is declared to be) a leveraged product but no
        verified-shaped metadata exists for it, so nothing is computed.
    ``not_applicable``
        Nothing indicates a daily-reset leveraged product; this chapter simply
        does not apply to the holding.
    """

    model_config = ConfigDict(frozen=True)

    status: DetectionStatus
    symbol: str
    normalized_symbol: str
    instrument_type: InstrumentType
    is_daily_reset_leveraged: bool
    leverage_factor: float | None
    underlying_index: str | None
    expense_ratio_annual: float | None
    metadata_verified: bool
    metadata_verified_on: str | None
    source_note: str | None
    classification_mismatch: bool
    reason: str | None
    notes: list[str]


def normalize_symbol(symbol: str) -> str:
    """Upper-case and strip a market suffix so registry lookups are stable."""
    value = symbol.strip().upper()
    for suffix in _SYMBOL_SUFFIXES:
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def lookup_metadata(symbol: str) -> LeverageMetadata | None:
    """Return registry metadata for ``symbol``, or ``None`` if unknown."""
    return KNOWN_LEVERAGED_ETF.get(normalize_symbol(symbol))


def detect(position: Position) -> LeverageDetection:
    """Classify one holding against the daily-reset leveraged-ETF registry."""
    return detect_symbol(position.symbol, position.instrument_type)


def detect_symbol(symbol: str, instrument_type: InstrumentType) -> LeverageDetection:
    """Symbol-level detection (the position-free core of :func:`detect`)."""
    normalized = normalize_symbol(symbol)
    metadata = KNOWN_LEVERAGED_ETF.get(normalized)
    declared = instrument_type == _LEVERAGED_INSTRUMENT_TYPE
    notes: list[str] = []

    if metadata is None and not declared:
        return LeverageDetection(
            status="not_applicable",
            symbol=symbol,
            normalized_symbol=normalized,
            instrument_type=instrument_type,
            is_daily_reset_leveraged=False,
            leverage_factor=None,
            underlying_index=None,
            expense_ratio_annual=None,
            metadata_verified=False,
            metadata_verified_on=REGISTRY_VERIFIED_ON,
            source_note=None,
            classification_mismatch=False,
            reason=(
                "此標的未被標記為 leveraged_etf，註冊表中也查無日度重置型槓桿／反向 ETF"
                "的 metadata，本章不適用。"
            ),
            notes=notes,
        )

    if metadata is None:
        return LeverageDetection(
            status="insufficient_data",
            symbol=symbol,
            normalized_symbol=normalized,
            instrument_type=instrument_type,
            is_daily_reset_leveraged=True,
            leverage_factor=None,
            underlying_index=None,
            expense_ratio_annual=None,
            metadata_verified=False,
            metadata_verified_on=REGISTRY_VERIFIED_ON,
            source_note=None,
            classification_mismatch=False,
            reason=(
                "此標的被標記為 leveraged_etf，但註冊表中查無其倍數與費用率 metadata；"
                "缺少輸入時不估算、不編造，因此本章的數字全部不計算。"
            ),
            notes=notes,
        )

    mismatch = not declared
    if mismatch:
        notes.append(
            f"註冊表顯示 {normalized} 為日度重置型槓桿／反向 ETF（倍數 "
            f"{metadata.leverage_factor:g}），但持倉的 instrument_type 被記為 "
            f"「{instrument_type}」；兩項事實並陳，未替使用者改寫其分類。"
        )
    if not metadata.verified:
        notes.append(
            "本章所有含費用率或倍數的數字，其 metadata 尚未查證（verified=false），"
            "數值應視為待查證狀態。"
        )

    return LeverageDetection(
        status="ok",
        symbol=symbol,
        normalized_symbol=normalized,
        instrument_type=instrument_type,
        is_daily_reset_leveraged=True,
        leverage_factor=metadata.leverage_factor,
        underlying_index=metadata.underlying_index,
        expense_ratio_annual=metadata.expense_ratio_annual,
        metadata_verified=metadata.verified,
        metadata_verified_on=metadata.verified_on,
        source_note=metadata.source_note,
        classification_mismatch=mismatch,
        reason=None,
        notes=notes,
    )
