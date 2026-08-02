"""Assemble the leveraged-ETF chapter for a single position.

Composes the three layers -- detection/metadata, realised drag decomposition,
flat-index erosion scenario -- into one machine-readable ``dict``, each block
carrying its own status, provenance and assumptions so nothing loses its
qualifiers on the way to the API.

Statuses are honest about partial coverage, mirroring
``app/portfolio/summary.py``:

``ok``                both quantitative blocks computed
``partial``           one computed, one ``insufficient_data``
``insufficient_data`` the holding is a daily-reset product but nothing could be
                      computed (missing metadata, missing bars, too short)
``not_applicable``    nothing indicates a daily-reset leveraged product

Two verification flags travel with the chapter and mean different things:
``detection.metadata_verified`` (does the issuer really state this leverage
factor and expense ratio) and ``index_mapping_verified`` (is this really the
fund's benchmark, under a code that really returns data). Both are ``false``
today, and the second one is emitted as a top-level field because the UI has to
show it wherever the index-based blocks appear (ADR-0005 constraint C-7).

This is a measurement surface. There is deliberately no action, rating, score,
target price or holding-period suggestion field anywhere in the output; the
chapter states mechanics and numbers and stops there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

from app.data.interface import PriceBar
from app.leverage import detect as detect_module
from app.leverage import drag as drag_module
from app.leverage import erosion as erosion_module
from app.leverage import index_mapping as index_mapping_module
from app.positions.models import Position
from app.signals.risk import TRADING_DAYS_PER_YEAR

ChapterStatus = Literal["ok", "partial", "insufficient_data", "not_applicable"]

DISCLOSURE: Final = (
    "本章僅中性陳述日度重置型槓桿／反向 ETF 的運作機制與可計算的數字：已發生的報酬拆解，"
    "以及在明確假設下的情境推估。情境數字不是預測，也不構成任何操作指引；"
    "所有含費用率與倍數的數字都依附於尚未查證的 metadata。"
)

#: Stated when the registry knows the fund but the mapping table has no row for
#: it. C-3 forbids this state and a test enforces it; the chapter still answers
#: rather than assuming the row is there.
NO_MAPPING_ROW_REASON: Final = (
    "此標的沒有標的指數對應資料，無法得知要查詢哪一個指數代號，"
    "因此拆解與情境推估都不計算，也不以其他標的替代。"
)

#: Stated whenever the mapping row itself is still unverified (C-7).
UNVERIFIED_MAPPING_NOTE: Final = (
    "標的指數對應尚未查證（index_mapping_verified=false）："
    "序列代號是否確為該基金的標的指數，以及其含息口徑，都屬待查證狀態。"
)


@dataclass(frozen=True)
class LeverageChapterConfig:
    """Switches and windows for the chapter."""

    enable_drag: bool = True
    enable_erosion: bool = True
    erosion_window: int = erosion_module.DEFAULT_WINDOW
    erosion_min_observations: int = erosion_module.DEFAULT_MIN_OBSERVATIONS
    erosion_horizons: tuple[tuple[str, int], ...] = erosion_module.DEFAULT_HORIZONS
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR


def _holding_block(position: Position, etf_bars: list[PriceBar]) -> dict[str, Any]:
    """Holding duration measured from ``opened_at`` against available bars."""
    opened_at = position.opened_at
    if opened_at is None:
        # No open date was stated, so no duration can be measured. The window
        # the other blocks use is reported as-is; the "since opened_at" counts
        # stay null rather than being filled from an assumed date.
        all_bars = sorted(bar.date for bar in etf_bars)
        return {
            "status": "insufficient_data",
            "opened_at": None,
            "first_bar_date": all_bars[0].isoformat() if all_bars else None,
            "last_bar_date": all_bars[-1].isoformat() if all_bars else None,
            "bars_since_opened_at": None,
            "holding_trading_days": None,
            "holding_days": None,
            "reason": "未填寫建倉日期，無法計算持有天數；拆解改以全部可用日線為窗。",
        }
    held = sorted(bar.date for bar in etf_bars if bar.date >= opened_at)
    if not held:
        return {
            "status": "insufficient_data",
            "opened_at": opened_at.isoformat(),
            "first_bar_date": None,
            "last_bar_date": None,
            "bars_since_opened_at": 0,
            "holding_trading_days": None,
            "holding_days": None,
            "reason": "建倉日之後沒有可用的 ETF 日線，無法計算持有天數。",
        }
    return {
        "status": "ok",
        "opened_at": opened_at.isoformat(),
        "first_bar_date": held[0].isoformat(),
        "last_bar_date": held[-1].isoformat(),
        "bars_since_opened_at": len(held),
        "holding_trading_days": len(held) - 1,
        "holding_days": (held[-1] - opened_at).days,
        "reason": None,
    }


def _index_mapping_block(ref: index_mapping_module.IndexRef | None) -> dict[str, Any] | None:
    """The mapping row as data, so the reader can check it rather than trust it."""
    if ref is None:
        return None
    return {
        "etf_symbol": ref.etf_symbol,
        "underlying_index_text": ref.underlying_index_text,
        "basis": ref.basis,
        "series_symbol": ref.series_symbol,
        "series_market": ref.series_market,
        "return_basis": ref.return_basis,
        "verified": ref.verified,
        "verified_on": ref.verified_on,
        "mapping_verified_on": index_mapping_module.MAPPING_VERIFIED_ON,
        "note": ref.note,
    }


def _series_unavailable_reason(ref: index_mapping_module.IndexRef | None) -> str | None:
    """Why no index series may be used at all, or ``None`` when one may be.

    The wording comes from the mapping row itself, which states what is
    established about the benchmark -- never a "temporarily unavailable" framing
    (constraint I-5): nothing about these rows is temporary or a malfunction.
    """
    if ref is None:
        return NO_MAPPING_ROW_REASON
    if not index_mapping_module.has_queryable_series(ref):
        return ref.note or NO_MAPPING_ROW_REASON
    return None


def _chapter_status(*, drag_ok: bool, erosion_ok: bool) -> ChapterStatus:
    if drag_ok and erosion_ok:
        return "ok"
    if drag_ok or erosion_ok:
        return "partial"
    return "insufficient_data"


def build_leverage_chapter(
    position: Position,
    etf_bars: list[PriceBar],
    index_bars: list[PriceBar] | None = None,
    *,
    config: LeverageChapterConfig | None = None,
) -> dict[str, Any]:
    """Build the full leveraged-ETF chapter for one position.

    ``index_bars`` are the underlying index's daily bars, supplied by the caller
    (the data layer decides how to source an index series). Without them the
    drag decomposition reports ``insufficient_data`` rather than substituting a
    proxy series, and the erosion scenario -- which is also index-based --
    reports the same.

    The mapping row from ``app/leverage/index_mapping.py`` is looked up here
    rather than passed in, so the chapter's disclosure can never disagree with
    the table the series was chosen from. When that row establishes there is no
    queryable index (``basis="unmapped"``), both quantitative blocks report
    ``insufficient_data`` **even if the caller supplied bars**: the row's note
    is the reason, and computing an attribution against an unestablished series
    is the one failure this chapter is built to avoid.
    """
    cfg = config or LeverageChapterConfig()
    generated_at = datetime.now(UTC).isoformat()
    detection = detect_module.detect(position)
    index_ref = index_mapping_module.lookup_index_ref(position.symbol)
    series_unavailable_reason = _series_unavailable_reason(index_ref)
    index = [] if series_unavailable_reason is not None else list(index_bars or [])

    chapter: dict[str, Any] = {
        "symbol": position.symbol,
        "position_id": position.id,
        "generated_at": generated_at,
        "disclosure": DISCLOSURE,
        "detection": detection.model_dump(),
        "index_mapping": _index_mapping_block(index_ref),
        "index_mapping_verified": bool(index_ref is not None and index_ref.verified),
        "holding": _holding_block(position, etf_bars),
        "drag": None,
        "erosion": None,
        "notes": list(detection.notes),
    }

    if detection.status != "ok":
        chapter["chapter_status"] = (
            "not_applicable" if detection.status == "not_applicable" else "insufficient_data"
        )
        chapter["reason"] = detection.reason
        return chapter

    # Guarded by detection.status == "ok"; present for the type checker.
    assert detection.leverage_factor is not None
    assert detection.expense_ratio_annual is not None
    leverage_factor = detection.leverage_factor
    expense_ratio = detection.expense_ratio_annual

    drag_ok = False
    if cfg.enable_drag:
        decomposition = drag_module.decompose_drag(
            etf_bars=etf_bars,
            index_bars=index,
            leverage_factor=leverage_factor,
            expense_ratio_annual=expense_ratio,
            opened_at=position.opened_at,
            trading_days_per_year=cfg.trading_days_per_year,
            index_basis=index_ref.basis if index_ref else "unmapped",
            index_return_basis=index_ref.return_basis if index_ref else "unknown",
        )
        if series_unavailable_reason is not None:
            # Same insufficient_data block the module produces for "no bars",
            # with the generic wording replaced by what is actually established
            # about this benchmark (I-5).
            decomposition = decomposition.model_copy(
                update={"reason": series_unavailable_reason}
            )
        drag_ok = decomposition.status == "ok"
        chapter["drag"] = decomposition.model_dump()
        # The residual trip is a chapter-level qualifier, not a detail buried in
        # one block (constraint I-6).
        chapter["notes"].extend(decomposition.notes)

    erosion_ok = False
    if cfg.enable_erosion:
        estimate = erosion_module.estimate_erosion(
            index_bars=index,
            leverage_factor=leverage_factor,
            expense_ratio_annual=expense_ratio,
            window=cfg.erosion_window,
            min_observations=cfg.erosion_min_observations,
            horizons=cfg.erosion_horizons,
            trading_days_per_year=cfg.trading_days_per_year,
        )
        if series_unavailable_reason is not None:
            estimate = estimate.model_copy(update={"reason": series_unavailable_reason})
        erosion_ok = estimate.status == "ok"
        chapter["erosion"] = estimate.model_dump()

    if series_unavailable_reason is not None:
        chapter["notes"].append(series_unavailable_reason)
    elif not index:
        chapter["notes"].append(
            "呼叫端未提供標的指數日線，拆解與情境推估皆不計算；本模組不會以其他標的替代。"
        )
    if index_ref is not None and not index_ref.verified:
        chapter["notes"].append(UNVERIFIED_MAPPING_NOTE)

    chapter["chapter_status"] = _chapter_status(drag_ok=drag_ok, erosion_ok=erosion_ok)
    chapter["reason"] = None
    return chapter
