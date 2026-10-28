"""User-facing message templates (plain text, factual statements only).

Wording rule (PRD FR-C5): state what was found ("查到 ... 價"); never advise when or
whether to buy. Templates here are the single source for notification text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from flight_deals.domain.airports import route_label
from flight_deals.domain.currency import format_money
from flight_deals.domain.links import google_flights_url
from flight_deals.domain.rules import TriggeredItem
from flight_deals.domain.timeutil import format_taipei, format_travel_date
from flight_deals.domain.trip_labels import (
    BOOKING_FALLBACK_NOTE,
    cabin_label,
    filter_line,
    pax_label,
    total_price_note,
)
from flight_deals.domain.trip_labels import static_texts as trip_static_texts

DISCLAIMER = "價格為查到當下的參考值，實際以航空公司或訂票網站為準。"
SAMPLED_ONLY_NOTE = "只涵蓋已取樣的日期；未取樣的日期不代表沒有更便宜的價格。"

# Advisory / urgency wording that must never appear in notifications or UI copy
# (risk-compliance review). Fix the copy, not this list, when a phrase collides.
BANNED_PHRASES: tuple[str, ...] = (
    "建議",
    "最佳時機",
    "現在買",
    "快買",
    "趕快",
    "必買",
    "推薦購買",
    "保證",
    "穩賺",
    "划算",
    "超值",
    "值得",
    "搶",
    "錯過",
    "把握",
    "趁",
    "下手",
)

SOURCE_LABELS: dict[str, str] = {
    "google_flights": "Google Flights",
    "fixture": "測試資料（fixture）",
    "travelpayouts": "Travelpayouts",
}

PRICE_KIND_LABELS: dict[str, str] = {
    "live": "即時價",
    "cached": "快取價，非即時",
}

TRIP_TYPE_LABELS: dict[str, str] = {"round_trip": "來回", "one_way": "單程"}

STATUS_LABELS: dict[str, str] = {
    "active": "啟用中",
    "paused": "已停用",
    "stale": "啟用中（連續查價失敗）",
    "expired": "已過期",
}


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def reason_label(reason: str, drop_percent: int | None = None) -> str:
    if reason == "below_budget":
        return "低於門檻"
    if reason == "drop_pct":
        return f"較上次通知下跌 {drop_percent or 0}%"
    if reason == "new_low":
        return "此監看紀錄新低"
    return reason


def item_reasons_text(item: TriggeredItem) -> str:
    return "、".join(reason_label(r, item.drop_percent) for r in item.reasons)


def date_range_text(depart: date, return_date: date | None) -> str:
    text = format_travel_date(depart)
    if return_date is not None:
        text += "–" + format_travel_date(return_date)
    return text


def price_alert_message(
    *,
    watch_name: str,
    origin: str,
    destination: str,
    trip_type: str,
    items: Sequence[TriggeredItem],
    links: Sequence[str | None],
    adults: int = 1,
    children: int = 0,
    cabin: str = "economy",
    airlines: Sequence[str] = (),
    dep_hour_from: int | None = None,
    dep_hour_to: int | None = None,
) -> str:
    """One merged message for all triggered items of a watch in a single scan.

    ``links[i]`` is the exact booking link for ``items[i]`` (None when it could not be
    built); missing links fall back to the route-and-date search plus a note
    (ADR-0002 FD-5 Decision 7). Prices are totals for the whole party.
    """
    trip = TRIP_TYPE_LABELS.get(trip_type, trip_type)
    route = route_label(origin, destination)
    note = total_price_note(adults, children)
    header = f"{trip}・{pax_label(adults, children)}・{cabin_label(cabin)}"
    lines = [f"[flight-deals] 監看「{watch_name}」查到 {len(items)} 筆符合條件的價格（{header}）"]
    filters = filter_line(airlines, dep_hour_from, dep_hour_to)
    if filters:
        lines.append(filters)
    for index, item in enumerate(items, start=1):
        cand = item.candidate
        dates = date_range_text(cand.depart_date, cand.return_date)
        link = links[index - 1] if index - 1 < len(links) else None
        lines.append("")
        lines.append(
            f"{index}. 查到 {route} {dates} {format_money(cand.amount_minor, cand.currency)}{note}"
        )
        lines.append(f"   觸發原因：{item_reasons_text(item)}")
        lines.append(f"   航空公司：{cand.carrier or '未提供'}")
        lines.append(
            f"   查到時間：{format_taipei(cand.fetched_at)}（台北時間）"
            f"｜來源：{source_label(cand.source)}"
            f"（{PRICE_KIND_LABELS.get(cand.price_kind, cand.price_kind)}）"
        )
        if link:
            lines.append("   查票連結：" + link)
        else:
            lines.append(
                "   查票連結："
                + google_flights_url(origin, destination, cand.depart_date, cand.return_date)
            )
            lines.append(f"   （{BOOKING_FALLBACK_NOTE}）")
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def ops_failure_message(*, source: str, error: str | None, now: datetime) -> str:
    return "\n".join(
        [
            f"[flight-deals] 資料源異常：{source_label(source)} 連續查價失敗，已暫停查詢一段時間。",
            f"時間：{format_taipei(now)}（台北時間）",
            f"最近錯誤：{error or '未提供'}",
            "期間沒有收到價格通知不代表沒有低價；可到設定與健康頁查看狀態，"
            "或用監看詳情頁的人工查價連結自行查詢。",
        ]
    )


def telegram_test_message(now: datetime) -> str:
    return (
        f"[flight-deals] 測試訊息：Telegram 通道設定成功。"
        f"發送時間 {format_taipei(now)}（台北時間）。"
    )


# ---- daily digest (ADR-0002 FD-4 Decision 6, C-34) ----------------------------------

DIGEST_MAX_WATCH_LINES = 20
DIGEST_MAX_CHARS = 3800  # below Telegram's 4096-character limit
DIGEST_NAME_MAX = 20
DIGEST_TITLE = "[flight-deals] 每日摘要"
DIGEST_NO_WATCHES = "目前沒有啟用中的監看。"
DIGEST_NO_PRICE = "尚無價格"
DIGEST_WATCH_STALE = "連續查價失敗"
DIGEST_FLAT = "持平"
DIGEST_NONE = "—"
DIGEST_DELTA_NOTE = (
    "漲跌為目前最低總價與前一日（台北時間）結束時最低總價的差額；"
    "只計目前設定的即時價，不含已出發的日期。"
    "兩個最低價可能是不同日期，差額不代表同一行程的漲跌。"
)
NO_PRICE_ALERT_NOTE = "沒有收到價格通知不代表沒有低價。"
_BREAKER_NOTES = {"open": "（斷路器開啟，暫停查詢）", "half_open": "（斷路器半開，試查中）"}


@dataclass(frozen=True)
class DigestRow:
    """One enabled watch in the digest. Amounts are integer minor units."""

    name: str
    origin: str
    destination: str
    currency: str
    amount_minor: int | None
    depart_date: date | None
    return_date: date | None
    delta_minor: int | None
    data_stale: bool
    watch_stale: bool
    adults: int = 1
    children: int = 0
    cabin: str = "economy"


@dataclass(frozen=True)
class DigestSourceRow:
    """Data source state, worded like the health page (never the raw last error)."""

    source: str
    state_label: str
    breaker_state: str


def digest_hidden_note(count: int) -> str:
    return f"另有 {count} 個監看未列出，完整列表請見網頁。"


def _digest_delta_text(row: DigestRow) -> str:
    if row.amount_minor is None or row.delta_minor is None:
        return DIGEST_NONE
    if row.delta_minor == 0:
        return DIGEST_FLAT
    sign = "+" if row.delta_minor > 0 else "-"
    return sign + format_money(abs(row.delta_minor), row.currency)


def digest_stale_label(stale_after_hours: int) -> str:
    """Marker for a lowest price not re-fetched within the stale threshold (hours)."""
    return f"此價格逾 {stale_after_hours} 小時未重查"


def _digest_line(row: DigestRow, stale_after_hours: int) -> str:
    name = row.name if len(row.name) <= DIGEST_NAME_MAX else row.name[:DIGEST_NAME_MAX] + "…"
    parts = [f"• {name}", route_label(row.origin, row.destination), cabin_label(row.cabin)]
    if row.amount_minor is None or row.depart_date is None:
        parts.append(f"{DIGEST_NO_PRICE}（{pax_label(row.adults, row.children)}）")
    else:
        dates = date_range_text(row.depart_date, row.return_date)
        money = format_money(row.amount_minor, row.currency)
        parts.append(f"{money}{total_price_note(row.adults, row.children)}（{dates}）")
    parts.append(f"較前一日 {_digest_delta_text(row)}")
    if row.amount_minor is not None and row.data_stale:
        parts.append(digest_stale_label(stale_after_hours))
    if row.watch_stale:
        parts.append(DIGEST_WATCH_STALE)
    return "｜".join(parts)


def _digest_sources_text(sources: Sequence[DigestSourceRow]) -> str:
    if not sources:
        return DIGEST_NONE
    return "；".join(
        f"{source_label(s.source)} {s.state_label}{_BREAKER_NOTES.get(s.breaker_state, '')}"
        for s in sources
    )


def daily_digest_message(
    *,
    day: date,
    sources: Sequence[DigestSourceRow],
    last_scan_at: datetime | None,
    failed_scans_24h: int,
    rows: Sequence[DigestRow],
    stale_after_hours: int,
) -> str:
    """Daily status digest: facts only, footer always kept, at most DIGEST_MAX_CHARS.

    ``stale_after_hours`` is the price-staleness setting; it is stated in the marker.
    """
    header = [
        f"{DIGEST_TITLE}｜{day.isoformat()}（台北時間）",
        f"資料源：{_digest_sources_text(sources)}",
        "上次掃描："
        + (f"{format_taipei(last_scan_at)}（台北時間）" if last_scan_at else DIGEST_NONE),
        f"過去 24 小時查價失敗的掃描：{failed_scans_24h} 次",
    ]
    if not rows:
        return "\n".join(
            [header[0], DIGEST_NO_WATCHES, *header[1:], "", DISCLAIMER, NO_PRICE_ALERT_NOTE]
        )
    footer = ["", DIGEST_DELTA_NOTE, SAMPLED_ONLY_NOTE, DISCLAIMER, NO_PRICE_ALERT_NOTE]
    lines = [_digest_line(r, stale_after_hours) for r in rows]
    shown = min(len(lines), DIGEST_MAX_WATCH_LINES)

    def render(count: int) -> str:
        body = [f"啟用中的監看：{len(rows)} 個", *lines[:count]]
        if count < len(lines):
            body.append(digest_hidden_note(len(lines) - count))
        return "\n".join([*header, "", *body, *footer])

    text = render(shown)
    while len(text) > DIGEST_MAX_CHARS and shown > 0:
        shown -= 1
        text = render(shown)
    return text


# ---- exploration mode (ADR-0002 FD-6 Decisions 3, 5-7) ------------------------------

EXPLORATION_STATUS_LABELS: dict[str, str] = {
    "queued": "排隊中",
    "running": "進行中",
    "done": "已完成",
    "failed": "已中斷",
}
EXPLORATION_DONE_WITH_GAPS = "已完成（部分日期未查）"
EXPLORATION_CELL_LABELS: dict[str, str] = {
    "ok": "查到價格",
    "pending": "查詢中",
    "no_data": "無資料",
    "no_embedded_results": "未內嵌結果",
    "blocked": "被擋",
    "error": "錯誤",
    "currency_mismatch": "幣別不符，未列入排名",
    "global_hourly_limit": "額度不足略過",
    "breaker_open": "資料源暫停略過",
    "interrupted": "中斷未查",
    "past": "未查詢（已過去的日期）",
    "out_of_range": "未查詢（超出可查日期範圍）",
}
EXPLORATION_REFERENCE_NOTE = "探索結果為查詢當下參考值，不會寫入任何監看的價格紀錄，也不會推播。"
EXPLORATION_BUSY = "已有探索進行中，同一時間只能進行一個探索"
EXPLORATION_SCHEDULER_OFF = "排程器未執行，無法在背景探索；請以一般方式啟動服務後再試"
EXPLORATION_NO_DATES = "此月份沒有可查詢的出發日（已過去或超出可查日期範圍）"
EXPLORATION_NOT_FOUND = "探索已過期或不存在（探索結果保留 7 天）。"
EXPLORATION_HOURLY_LIMIT = "已達全域每小時查詢上限"
EXPLORATION_BREAKER_OPEN = "資料源異常（斷路器開啟）"
EXPLORATION_RESTARTED = "服務重啟，探索中斷；未查的日期不會自動補查"
EXPLORATION_PREFILL_OK = "已從探索帶入條件，請填預算與名稱"
EXPLORATION_PREFILL_MISSING = "找不到對應的探索結果，請手動填寫"


def no_embedded_streak_label(rounds: int) -> str:
    """List-row hint; the round count comes from config (Limits.no_embedded_streak_rounds)."""
    return f"連續 {rounds} 輪 Google 未內嵌結果，請用查票連結確認"


def exploration_quota_message(hourly_left: int, needed: int, reserve: int) -> str:
    text = f"本小時剩餘額度 {hourly_left} 次"
    if reserve > 0:
        text += f"（需保留 {reserve} 次給排程掃描）"
    return f"{text}，本次需要 {needed} 次，不足以探索整月，請稍後再試"


def exploration_skipped_note(reason: str, count: int) -> str:
    return f"{reason}，{count} 天未查"


def exploration_unfinished_note(done: int, total: int, reason: str) -> str:
    return f"探索未完成（已查 {done}／共 {total}），原因：{reason}"


def exploration_age_note(hours: int) -> str:
    return f"價格為 {hours} 小時前查到，可能已變動"


def exploration_reused_note(hours: int) -> str:
    return f"顯示 {hours} 小時前的探索結果"


def exploration_sampled_note(max_pairs: int) -> str:
    return f"以整月建立的彈性窗監看每輪最多查 {max_pairs} 組日期，輪換取樣"


def month_label(year: int, month: int) -> str:
    return f"{year} 年 {month} 月"


def exploration_static_texts() -> list[str]:
    return [
        *EXPLORATION_STATUS_LABELS.values(),
        EXPLORATION_DONE_WITH_GAPS,
        *EXPLORATION_CELL_LABELS.values(),
        EXPLORATION_REFERENCE_NOTE,
        EXPLORATION_BUSY,
        EXPLORATION_SCHEDULER_OFF,
        EXPLORATION_NO_DATES,
        EXPLORATION_NOT_FOUND,
        EXPLORATION_HOURLY_LIMIT,
        EXPLORATION_BREAKER_OPEN,
        EXPLORATION_RESTARTED,
        EXPLORATION_PREFILL_OK,
        EXPLORATION_PREFILL_MISSING,
        no_embedded_streak_label(3),
        exploration_quota_message(20, 31, 12),
        exploration_skipped_note(EXPLORATION_HOURLY_LIMIT, 3),
        exploration_unfinished_note(12, 31, EXPLORATION_BREAKER_OPEN),
        exploration_age_note(25),
        exploration_reused_note(3),
        exploration_sampled_note(12),
        month_label(2026, 12),
    ]


def all_static_texts() -> list[str]:
    """Static wording used in templates (for wording-policy tests)."""
    return [
        DISCLAIMER,
        SAMPLED_ONLY_NOTE,
        *SOURCE_LABELS.values(),
        *PRICE_KIND_LABELS.values(),
        *TRIP_TYPE_LABELS.values(),
        *STATUS_LABELS.values(),
        reason_label("below_budget"),
        reason_label("drop_pct", 6),
        reason_label("new_low"),
        DIGEST_TITLE,
        DIGEST_NO_WATCHES,
        DIGEST_NO_PRICE,
        digest_stale_label(24),
        DIGEST_WATCH_STALE,
        DIGEST_FLAT,
        DIGEST_DELTA_NOTE,
        NO_PRICE_ALERT_NOTE,
        digest_hidden_note(3),
        *_BREAKER_NOTES.values(),
        "啟用中的監看：2 個",
        "過去 24 小時查價失敗的掃描：0 次",
        "較前一日",
        "每日摘要",
        *trip_static_texts(),
        *exploration_static_texts(),
    ]
