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
from app.positions.models import Position
from app.signals.risk import TRADING_DAYS_PER_YEAR

ChapterStatus = Literal["ok", "partial", "insufficient_data", "not_applicable"]

DISCLOSURE: Final = (
    "本章僅中性陳述日度重置型槓桿／反向 ETF 的運作機制與可計算的數字：已發生的報酬拆解，"
    "以及在明確假設下的情境推估。情境數字不是預測，也不構成任何操作指引；"
    "所有含費用率與倍數的數字都依附於尚未查證的 metadata。"
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
    """
    cfg = config or LeverageChapterConfig()
    generated_at = datetime.now(UTC).isoformat()
    detection = detect_module.detect(position)
    index = index_bars or []

    chapter: dict[str, Any] = {
        "symbol": position.symbol,
        "position_id": position.id,
        "generated_at": generated_at,
        "disclosure": DISCLOSURE,
        "detection": detection.model_dump(),
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
        )
        drag_ok = decomposition.status == "ok"
        chapter["drag"] = decomposition.model_dump()

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
        erosion_ok = estimate.status == "ok"
        chapter["erosion"] = estimate.model_dump()

    if not index:
        chapter["notes"].append(
            "呼叫端未提供標的指數日線，拆解與情境推估皆不計算；本模組不會以其他標的替代。"
        )

    chapter["chapter_status"] = _chapter_status(drag_ok=drag_ok, erosion_ok=erosion_ok)
    chapter["reason"] = None
    return chapter
