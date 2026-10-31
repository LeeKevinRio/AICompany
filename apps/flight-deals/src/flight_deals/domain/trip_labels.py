"""Passenger, cabin and filter wording (pure functions, ADR-0002 FD-5 Decision 5, C-40).

Every price shown anywhere is the total for the whole party, so the passenger note
always accompanies it ("（1 人總價）" included). No per-person price is ever derived.
"""

from __future__ import annotations

from collections.abc import Iterable

from flight_deals.domain.airlines import airlines_label
from flight_deals.domain.models import CABINS

CABIN_LABELS: dict[str, str] = {
    "economy": "經濟艙",
    "premium_economy": "豪華經濟艙",
    "business": "商務艙",
    "first": "頭等艙",
}
NO_LIMIT = "不限"
BOOKING_FALLBACK_NOTE = "此連結只帶航線與日期，人數、艙等、篩選請在頁面上重選"


def pax_label(adults: int, children: int) -> str:
    """Short form: "2 大 1 小" with children, "N 人" without."""
    if children > 0:
        return f"{adults} 大 {children} 小"
    return f"{adults} 人"


def pax_full_label(adults: int, children: int) -> str:
    """Long form for the detail page: "2 位成人、1 位兒童" / "1 位成人"."""
    text = f"{adults} 位成人"
    if children > 0:
        text += f"、{children} 位兒童"
    return text


def cabin_label(cabin: str) -> str:
    return CABIN_LABELS.get(cabin, cabin)


def total_price_short(adults: int, children: int) -> str:
    """Same note without brackets, for compact lines: "2 大 1 小總價"."""
    return f"{pax_label(adults, children)}總價"


def total_price_note(adults: int, children: int) -> str:
    """Note that follows every displayed price: "（2 大 1 小總價）" / "（1 人總價）"."""
    return f"（{total_price_short(adults, children)}）"


def dep_window_label(dep_hour_from: int | None, dep_hour_to: int | None) -> str:
    """Outbound window in whole hours, e.g. "去程 06–12 時"; unset -> "不限"."""
    if dep_hour_from is None or dep_hour_to is None:
        return NO_LIMIT
    return f"去程 {dep_hour_from:02d}–{dep_hour_to:02d} 時"


def airlines_text(airlines: Iterable[str]) -> str:
    return airlines_label(airlines) or NO_LIMIT


def conditions_label(
    airlines: Iterable[str], dep_hour_from: int | None, dep_hour_to: int | None
) -> str:
    """List-page filter summary: "長榮、華航｜去程 06–12 時", or "不限" with no filter."""
    parts = []
    names = airlines_label(airlines)
    if names:
        parts.append(names)
    if dep_hour_from is not None and dep_hour_to is not None:
        parts.append(dep_window_label(dep_hour_from, dep_hour_to))
    return "｜".join(parts) or NO_LIMIT


def filter_line(
    airlines: Iterable[str], dep_hour_from: int | None, dep_hour_to: int | None
) -> str | None:
    """Push-message filter line, or None when no filter is set (Decision 5)."""
    parts = []
    names = airlines_label(airlines)
    if names:
        parts.append(f"航空公司 {names}")
    if dep_hour_from is not None and dep_hour_to is not None:
        parts.append(f"去程出發 {dep_hour_from:02d}–{dep_hour_to:02d} 時")
    return "篩選：" + "；".join(parts) if parts else None


def stay_range_label(min_days: int, max_days: int) -> str:
    """Trip length of a flexible window: "4 天" when equal, otherwise "3–5 天"."""
    if min_days == max_days:
        return f"{min_days} 天"
    return f"{min_days}–{max_days} 天"


def flight_duration_label(minutes: int | None) -> str | None:
    """Total flight time, e.g. "3 小時 25 分", "3 小時", "45 分"; None when unknown."""
    if minutes is None or minutes <= 0:
        return None
    hours, rest = divmod(minutes, 60)
    if hours == 0:
        return f"{rest} 分"
    return f"{hours} 小時" if rest == 0 else f"{hours} 小時 {rest} 分"


def static_texts() -> list[str]:
    """Wording added by FD-5, for the banned-phrase test."""
    return [
        *(CABIN_LABELS[c] for c in CABINS),
        NO_LIMIT,
        BOOKING_FALLBACK_NOTE,
        pax_label(2, 1),
        pax_label(1, 0),
        pax_full_label(2, 1),
        total_price_note(2, 1),
        total_price_note(1, 0),
        dep_window_label(6, 12),
        conditions_label(("BR", "CI"), 6, 12),
        filter_line(("BR", "CI"), 6, 12) or "",
    ]
