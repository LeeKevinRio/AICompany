"""User-facing message templates (plain text, factual statements only).

Wording rule (PRD FR-C5): state what was found ("查到 ... 價"); never advise when or
whether to buy. Templates here are the single source for notification text.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime

from flight_deals.domain.airports import route_label
from flight_deals.domain.currency import format_money
from flight_deals.domain.links import google_flights_url
from flight_deals.domain.rules import TriggeredItem
from flight_deals.domain.timeutil import WEEKDAY_LABELS, format_taipei, format_travel_date
from flight_deals.domain.trip_labels import (
    BOOKING_FALLBACK_NOTE,
    cabin_label,
    depart_weekdays_label,
    filter_line,
    flight_duration_label,
    pax_full_label,
    pax_label,
    stay_range_label,
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
    "推薦",
    "最佳",
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
    # "週五、週六出發" for a filtered flexible window; None otherwise (FD-10).
    weekdays_label: str | None = None


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
    if row.weekdays_label is not None:
        parts.append(row.weekdays_label)
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
    "weekday_filtered": "未查（星期篩選）",
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

# ---- departure weekdays and month ranges (ADR-0002 FD-10 Decisions 4, 6, 7) ----------

# Single source of the span limit; validation re-exports it as EXPLORATION_MAX_SPAN_MONTHS
# (messages cannot import validation, which imports messages).
EXPLORATION_MAX_SPAN_MONTHS = 3
WEEKDAYS_REQUIRED = "請至少選一個出發星期"
WEEKDAYS_INVALID = "出發星期格式不正確，請從選項勾選"
WEEKDAYS_NO_MATCH_WINDOW = "所選日期區間內沒有符合出發星期的日子"
WEEKDAYS_NO_MATCH_MONTHS = "所選月份內沒有符合出發星期的日子"
EXPLORATION_TOO_MANY_CELLS = "請縮小月份範圍或減少星期"
MONTH_TO_BEFORE = "結束月份不可早於起始月份"
MONTH_SPAN_TOO_LONG = f"月份範圍最多連續 {EXPLORATION_MAX_SPAN_MONTHS} 個月"
# Moved verbatim from exploration.html (FD-10 Decision 9, F3).
EXPLORATION_STALE_FALLBACK = "這是較早前查到的價格，可能已變動。"
EXPLORATION_MONTH_WATCH_BUTTON = "以整月建立彈性窗監看"
EXPLORATION_RANGE_WATCH_BUTTON = "以所選月份建立彈性窗監看"
# Under the top-5 heading, always shown (risk-compliance R1).
EXPLORATION_TOP_SCOPE_NOTE = "只比較所選月份內符合出發星期、且有查到價格的出發日。"
WEEKDAY_OPTION_LABELS: tuple[str, ...] = tuple("週" + name for name in WEEKDAY_LABELS)


def no_embedded_streak_label(rounds: int) -> str:
    """List-row hint; the round count comes from config (Limits.no_embedded_streak_rounds)."""
    return f"連續 {rounds} 輪 Google 未內嵌結果，請用查票連結確認"


def exploration_quota_message(
    hourly_left: int, needed: int, reserve: int, *, months: int = 1
) -> str:
    text = f"本小時剩餘額度 {hourly_left} 次"
    if reserve > 0:
        text += f"（需保留 {reserve} 次給排程掃描）"
    scope = "整月" if months <= 1 else "所選月份"
    return f"{text}，本次需要 {needed} 次，不足以探索{scope}，請稍後再試"


def exploration_skipped_note(reason: str, count: int) -> str:
    return f"{reason}，{count} 天未查"


def exploration_unfinished_note(done: int, total: int, reason: str) -> str:
    return f"探索未完成（已查 {done}／共 {total}），原因：{reason}"


def exploration_age_note(hours: int) -> str:
    return f"價格為 {hours} 小時前查到，可能已變動"


def exploration_reused_note(hours: int) -> str:
    return f"顯示 {hours} 小時前的探索結果"


def exploration_sampled_note(max_pairs: int, *, months: int = 1) -> str:
    scope = "整月" if months <= 1 else "所選月份"
    return f"以{scope}建立的彈性窗監看每輪最多查 {max_pairs} 組日期，輪換取樣"


def month_label(year: int, month: int) -> str:
    return f"{year} 年 {month} 月"


def month_range_label(year: int, month: int, end_year: int, end_month: int) -> str:
    """Single month: ``month_label``; otherwise "2026 年 12 月～2027 年 2 月"."""
    if (end_year, end_month) == (year, month):
        return month_label(year, month)
    return f"{month_label(year, month)}～{month_label(end_year, end_month)}"


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
        exploration_sampled_note(12, months=3),
        month_label(2026, 12),
        WEEKDAYS_REQUIRED,
        WEEKDAYS_INVALID,
        WEEKDAYS_NO_MATCH_WINDOW,
        WEEKDAYS_NO_MATCH_MONTHS,
        EXPLORATION_TOO_MANY_CELLS,
        MONTH_TO_BEFORE,
        MONTH_SPAN_TOO_LONG,
        EXPLORATION_STALE_FALLBACK,
        EXPLORATION_MONTH_WATCH_BUTTON,
        EXPLORATION_RANGE_WATCH_BUTTON,
        EXPLORATION_TOP_SCOPE_NOTE,
        *WEEKDAY_OPTION_LABELS,
        exploration_quota_message(20, 24, 12, months=3),
        month_range_label(2026, 12, 2027, 2),
        depart_weekdays_label((4, 5)) or "",
    ]


# ---- multi-destination comparison (ADR-0002 FD-9 Decisions 4-6) ----------------------

COMPARISON_STATUS_LABELS: dict[str, str] = {
    "queued": "排隊中",
    "running": "進行中",
    "done": "已完成",
    "failed": "已中斷",
}
COMPARISON_ROW_LABELS: dict[str, str] = {
    "ok": "查到價格",
    "pending": "查詢中",
    "no_data": "查無航班",
    "no_embedded_results": "未內嵌結果（請用查票連結人工確認）",
    "blocked": "被擋或查詢失敗",
    "error": "被擋或查詢失敗",
    "currency_mismatch": "幣別不符，未列入排序",
    "global_hourly_limit": "未查詢（額度不足）",
    "breaker_open": "未查詢（資料源暫停查詢）",
    "interrupted": "未查詢（已中斷）",
}
COMPARISON_REFERENCE_NOTE = "比價結果為查詢當下參考值，不會寫入任何監看的價格紀錄，也不會推播。"
COMPARISON_ORDER_NOTE = (
    "有價格的目的地依 1 人總價由低到高排列，同價依加入順序；"
    "沒有價格的目的地依加入順序列在後面。排列只依價格，未比較飛行時間與轉機。"
)
COMPARISON_NO_PRICE_NOTE = (
    "沒有價格的目的地未參與比較，不代表沒有機票或價格較高；可用查票連結自行確認。"
)
COMPARISON_SINGLE_DATE_NOTE = "只比較這一組日期，其他日期的價格可能不同。"
COMPARISON_BUSY = "已有比價進行中，同一時間只能進行一個比價或探索"
COMPARISON_BLOCKED_BY_EXPLORATION = "已有探索進行中，同一時間只能進行一個比價或探索"
COMPARISON_SCHEDULER_OFF = "排程器未執行，無法在背景比價；請以一般方式啟動服務後再試"
COMPARISON_NOT_FOUND = "比價已過期或不存在（比價結果保留 7 天）。"
COMPARISON_RESTARTED = "服務重啟，比價中斷；未查的目的地不會自動補查"
COMPARISON_DEFERRED_NOTE = "比價進行中，排程掃描與立即查價會順延到比價結束後執行"
COMPARISON_PREFILL_OK = "已由比價帶入條件，請確認後送出"
COMPARISON_PREFILL_MISSING = "找不到對應的比價結果，請手動填寫"
COMPARISON_HOURLY_LIMIT = "已達全域每小時查詢上限"
COMPARISON_BREAKER_OPEN = "資料源異常（斷路器開啟）"
COMPARISON_LOCK_TIMEOUT = "掃描佔用過久，比價未執行"
COMPARISON_PAX_LABEL = pax_full_label(1, 0)
COMPARISON_NO_LIMIT_STOPS = "轉機不限"
# Validation (FD-9 Decision 2); field keys follow the request body.
COMPARISON_DESTINATIONS_INVALID = "目的地格式不正確，請從下拉選取"
COMPARISON_DESTINATIONS_COUNT = "目的地需選 2 到 8 個"
COMPARISON_DATE_INPUT_INVALID = "日期輸入方式不正確"
# Watch detail page: prices exist but every one of them has departed (FD-9 F2).
DETAIL_ALL_DEPARTED = "已查到的價格，其出發日皆已過，無可顯示的最新價格。"


def comparison_destination_unknown(code: str) -> str:
    return f"找不到目的地 {code}，請從下拉選取"


def comparison_destination_unverified(code: str) -> str:
    return f"目的地 {code} 的城市代碼尚未確認可查價，請改選個別機場"


def comparison_destination_duplicate(first: str, second: str) -> str:
    if first == second:
        return f"目的地 {first} 重複"
    return f"目的地 {first} 與 {second} 重複（城市代碼已包含其機場）"


def comparison_destination_is_origin(code: str) -> str:
    return f"目的地 {code} 與出發地相同"


def comparison_destination_same_city(code: str) -> str:
    return f"目的地 {code} 與出發地為同一城市"


def comparison_stay_too_far(latest: date) -> str:
    return f"依旅程天數計算的回程日不可晚於今天起 365 天（{latest.isoformat()}）"


def comparison_quota_message(hourly_left: int, needed: int, reserve: int) -> str:
    text = f"本小時剩餘額度 {hourly_left} 次"
    if reserve > 0:
        text += f"（需保留 {reserve} 次給排程掃描）"
    return f"{text}，本次需要 {needed} 次，本小時額度不足以開始比價，請稍後再試"


def comparison_skipped_note(reason: str, count: int) -> str:
    return f"{reason}，{count} 個目的地未查"


def comparison_unfinished_note(done: int, total: int, reason: str) -> str:
    return f"比價未完成（已查 {done}／共 {total}），原因：{reason}"


def comparison_age_note(hours: int) -> str:
    """Result older than 24 hours (same wording as the exploration note, own function)."""
    return f"價格為 {hours} 小時前查到，可能已變動"


def comparison_created_ago(hours: int) -> str:
    """Recent-list age of a comparison created more than 24 hours ago."""
    return f"{hours} 小時前"


def comparison_progress_label(done: int, total: int) -> str:
    return f"已查 {done}／共 {total}"


def comparison_reused_note(hours: int) -> str:
    return f"顯示 {hours} 小時前的比價結果"


def comparison_busy_message(path: str) -> str:
    """409 text naming the progress page of whatever is running (exploration or not)."""
    text = (
        COMPARISON_BLOCKED_BY_EXPLORATION if path.startswith("/explorations/") else COMPARISON_BUSY
    )
    return f"{text}（進度：{path}）"


def comparison_crashed(detail: str) -> str:
    return f"比價中斷：{detail}"


def comparison_stops_label(max_stops: int | None) -> str:
    if max_stops is None:
        return COMPARISON_NO_LIMIT_STOPS
    return "僅直飛" if max_stops == 0 else f"最多轉機 {max_stops} 次"


def comparison_dates_label(depart: date, return_date: date | None) -> str:
    if return_date is None:
        return f"{depart.isoformat()} 出發"
    return f"{depart.isoformat()} 出發，{return_date.isoformat()} 回程"


def comparison_static_texts() -> list[str]:
    """Wording added by FD-9 (comparison and the three follow-ups), for the policy tests."""
    return [
        *COMPARISON_STATUS_LABELS.values(),
        *COMPARISON_ROW_LABELS.values(),
        COMPARISON_REFERENCE_NOTE,
        COMPARISON_ORDER_NOTE,
        COMPARISON_NO_PRICE_NOTE,
        COMPARISON_SINGLE_DATE_NOTE,
        COMPARISON_BUSY,
        COMPARISON_BLOCKED_BY_EXPLORATION,
        COMPARISON_SCHEDULER_OFF,
        COMPARISON_NOT_FOUND,
        COMPARISON_RESTARTED,
        COMPARISON_DEFERRED_NOTE,
        COMPARISON_PREFILL_OK,
        COMPARISON_PREFILL_MISSING,
        COMPARISON_HOURLY_LIMIT,
        COMPARISON_BREAKER_OPEN,
        COMPARISON_LOCK_TIMEOUT,
        COMPARISON_PAX_LABEL,
        COMPARISON_NO_LIMIT_STOPS,
        COMPARISON_DESTINATIONS_INVALID,
        COMPARISON_DESTINATIONS_COUNT,
        COMPARISON_DATE_INPUT_INVALID,
        DETAIL_ALL_DEPARTED,
        comparison_destination_unknown("XYZ"),
        comparison_destination_unverified("SPK"),
        comparison_destination_duplicate("NRT", "NRT"),
        comparison_destination_duplicate("TYO", "NRT"),
        comparison_destination_is_origin("TPE"),
        comparison_destination_same_city("TSA"),
        comparison_stay_too_far(date(2027, 10, 25)),
        comparison_quota_message(15, 8, 12),
        comparison_quota_message(3, 8, 0),
        comparison_skipped_note(COMPARISON_HOURLY_LIMIT, 3),
        comparison_unfinished_note(3, 8, COMPARISON_BREAKER_OPEN),
        comparison_reused_note(3),
        comparison_age_note(25),
        comparison_created_ago(30),
        comparison_progress_label(3, 8),
        comparison_busy_message("/comparisons/3"),
        comparison_busy_message("/explorations/3"),
        comparison_crashed("RuntimeError: disk full"),
        comparison_stops_label(None),
        comparison_stops_label(0),
        comparison_stops_label(1),
        comparison_dates_label(date(2026, 12, 10), date(2026, 12, 15)),
        comparison_dates_label(date(2026, 12, 10), None),
        stay_range_label(4, 4),
        stay_range_label(3, 5),
        flight_duration_label(205) or "",
        flight_duration_label(180) or "",
        flight_duration_label(45) or "",
        scan_scheduled_text(12),
    ]


# ---- Telegram commands (ADR-0002 FD-7 Decisions 2-5, C-51) --------------------------

COMMAND_REPLY_MAX_CHARS = 3800  # below Telegram's 4096-character limit
COMMAND_LIST_MAX_LINES = 30
COMMAND_NAME_MAX = 20
COMMAND_TOP_N = 3
COMMAND_PREFIX = "[flight-deals]"
COMMAND_HELP = "\n".join(
    [
        f"{COMMAND_PREFIX} 可用指令",
        "/list：列出啟用中的監看與目前最低價",
        "/watch <編號>：查看單一監看的條件與已查到價格中最便宜的 3 組日期",
        "/scan <編號>：立即查價，完成後另外回覆結果",
        "/digest：立即送出一則摘要",
        "/status：資料源、查詢額度與下次掃描時間",
        "/pause <編號>：停用監看",
        "/resume <編號>：啟用監看",
        "/help：顯示這份說明",
        "編號為網頁監看列表上的編號；新增與修改監看請至網頁。",
    ]
)
COMMAND_HELP_HINT = "可用 /help 查看可用指令。"
COMMAND_UNKNOWN = f"無法辨識的指令。\n{COMMAND_HELP_HINT}"
COMMAND_NOT_TEXT = f"只接受文字指令。\n{COMMAND_HELP_HINT}"
COMMAND_TOO_LONG = f"指令過長（最多 64 字）。\n{COMMAND_HELP_HINT}"
COMMAND_FAILED = "指令執行時發生錯誤，結果可能未完成；可用 /list 或 /watch 確認目前狀態。"
COMMAND_NO_ACTIVE = "目前沒有啟用中的監看。"
COMMAND_NO_PRICE = "尚未查到價格"
COMMAND_NONE = "—"
COMMAND_FLAT = "＝"
COMMAND_TIME_NOTE = "時間為台北時間。"
COMMAND_DELTA_NOTE = (
    "較前一輪為目前最低總價與上一輪查價前最低總價的差額；"
    "兩個最低價可能是不同日期，差額不代表同一行程的漲跌。"
)
COMMAND_SCHEDULER_OFF = "排程未執行，無法排入；請以一般方式啟動服務後再試。"
COMMAND_SCAN_PAUSED = "該監看已停用，不會查價。"
COMMAND_SCAN_EXPIRED = "該監看日期已全部過期，不會查價。"
COMMAND_SCAN_PENDING = "該監看已在查價中，不重複排入。"
COMMAND_SCAN_DEFERRED = "探索進行中，將於探索結束後執行。"
COMMAND_COMPARISON_DEFERRED = "比價進行中，掃描順延"
COMMAND_SCAN_COMPARISON_DEFERRED = "比價進行中，掃描順延，將於比價結束後執行。"
COMMAND_SCAN_FOLLOW_UP = "查價完成後會另外回覆結果（服務重啟時可能不會回覆，可用 /watch 查看）。"
COMMAND_DIGEST_QUEUED = "已排入一則手動摘要，稍後送出；不影響每日排程摘要。"
COMMAND_NO_EXPLORATION = "目前沒有進行中的探索"
COMMAND_NEXT_SCAN_NONE = "目前沒有排定的掃描"
COMMAND_NEXT_SCAN_DEFERRED = "探索進行中，排程掃描順延至探索結束後"
COMMAND_NEXT_SCAN_MAYBE_DEFERRED = "探索進行中，可能順延"
COMMAND_SCHEDULER_STOPPED = "排程未執行"
COMMAND_NEVER_SCANNED = "上次掃描：尚未掃描"
COMMAND_TOP_TITLE = "已查到價格中最便宜的"
COMMAND_CARRIED_OVER = "此價格為先前掃描查到，本輪未更新"
COMMAND_STATUS_LABELS: dict[str, str] = {
    "active": "啟用中",
    "paused": "已停用",
    "stale": "啟用中（連續查價失敗）",
    "expired": "已過期",
}
SCAN_RESULT_LABELS: dict[str, str] = {
    "ok": "成功",
    "partial": "部分成功",
    "failed": "失敗",
}
SCAN_FAILURE_REASONS: dict[str, str] = {
    "global_hourly_limit": "已達全域每小時查詢上限",
    "breaker_open": "資料源斷路器開啟中，暫停查詢",
    "blocked": "資料源被擋或格式改變",
    "error": "資料源錯誤",
    "no_data": "查無航班",
    "no_embedded_results": "Google 未在頁面內嵌結果",
    "currency_mismatch": "來源回傳幣別與監看不一致",
    "not_found": "監看已不存在",
    "not_scannable": "監看已停用或不在可查價狀態",
    "expired": "監看日期已全部過期",
    "skipped_running": "另一個掃描仍在執行，本次未查價",
    "crashed": "查價執行時發生錯誤",
}
SCAN_FAILURE_FALLBACK = "沒有可用的價格"


def command_usage(name: str) -> str:
    if name in ("watch", "scan", "pause", "resume"):
        return f"用法：/{name} <編號>（編號可用 /list 查看）"
    return f"用法：/{name}（不需要參數）"


def command_not_found(watch_id: int) -> str:
    return f"找不到編號 {watch_id} 的監看，可用 /list 查看編號。"


def command_backlog(count: int, minutes: int = 10) -> str:
    return (
        f"有 {count} 則指令超過 {minutes} 分鐘才收到（可能因服務停機、網路中斷或指令功能關閉），"
        "已略過、未執行，請重新傳送。"
    )


def command_quota_exhausted(used: int, limit: int) -> str:
    return f"本小時查詢額度已用完（已用 {used}／上限 {limit}），本次未排入，請稍後再試。"


def _short_name(name: str) -> str:
    return name if len(name) <= COMMAND_NAME_MAX else name[:COMMAND_NAME_MAX] + "…"


def command_scan_queued(watch_id: int, name: str) -> str:
    return f"已排入查價：#{watch_id}「{_short_name(name)}」。"


def command_paused(watch_id: int, route: str) -> str:
    return f"已停用監看 #{watch_id}（{route}），排程不再查價。"


def command_resumed(watch_id: int, route: str) -> str:
    return f"已啟用監看 #{watch_id}（{route}），將依排程查價。"


def command_already_paused(watch_id: int) -> str:
    return f"該監看已是停用（#{watch_id}）。"


def command_already_active(watch_id: int) -> str:
    return f"該監看已是啟用（#{watch_id}）。"


def command_resume_expired(watch_id: int) -> str:
    return f"監看 #{watch_id} 的日期已全部過期，無法啟用；請至網頁修改日期。"


def command_pause_expired(watch_id: int) -> str:
    return f"監看 #{watch_id} 的日期已全部過期，不會查價，不需要停用。"


def command_hidden_note(count: int) -> str:
    return f"另有 {count} 個未列出，完整列表請見網頁。"


def command_list_title(count: int) -> str:
    return f"{COMMAND_PREFIX} 啟用中的監看：{count} 個"


def _short_time(moment: datetime | None) -> str:
    return format_taipei(moment)[5:] if moment else COMMAND_NONE


def command_delta_text(direction: str | None, delta_minor: int | None, currency: str) -> str:
    """List-page trend wording: "↓ TWD 500", "↑ TWD 500", "＝" or "—"."""
    if direction is None or delta_minor is None:
        return COMMAND_NONE
    if direction == "flat":
        return COMMAND_FLAT
    arrow = "↓" if direction == "down" else "↑"
    return f"{arrow} {format_money(abs(delta_minor), currency)}"


def _money_with_note(amount_minor: int, currency: str, adults: int, children: int) -> str:
    return f"{format_money(amount_minor, currency)}{total_price_note(adults, children)}"


def fit_reply(
    head: Sequence[str],
    items: Sequence[str],
    footer: Sequence[str],
    *,
    max_items: int | None = None,
    hidden_note: Callable[[int], str] = command_hidden_note,
    limit: int = COMMAND_REPLY_MAX_CHARS,
) -> str:
    """Join head, as many items as fit and footer; never cut silently.

    Dropped items are announced with ``hidden_note``; the footer (disclaimer, total-price
    note) is always kept, and an over-long head is cut last, from its end.
    """
    shown = len(items) if max_items is None else min(len(items), max_items)

    def render(count: int) -> str:
        body = list(items[:count])
        if count < len(items):
            body.append(hidden_note(len(items) - count))
        return "\n".join([*head, *body, *footer])

    text = render(shown)
    while len(text) > limit and shown > 0:
        shown -= 1
        text = render(shown)
    if len(text) > limit:
        tail = "\n".join(["…", *footer])
        text = text[: max(limit - len(tail) - 1, 0)] + "\n" + tail
    return text


@dataclass(frozen=True)
class CommandWatchLine:
    """One watch of ``/list`` (amounts are integer minor units, totals for the party)."""

    watch_id: int
    name: str
    origin: str
    destination: str
    currency: str
    adults: int
    children: int
    cabin: str
    amount_minor: int | None
    depart_date: date | None
    return_date: date | None
    delta_direction: str | None
    delta_minor: int | None
    last_scanned_at: datetime | None
    # The lowest price was not re-fetched within ``stale_after_hours``; the watch itself
    # has had several failed scans in a row (status ``stale``). Same marks as the digest.
    data_stale: bool = False
    watch_stale: bool = False


def command_list_line(row: CommandWatchLine, stale_after_hours: int = 24) -> str:
    parts = [
        f"#{row.watch_id} {_short_name(row.name)}",
        route_label(row.origin, row.destination),
        f"{pax_label(row.adults, row.children)}・{cabin_label(row.cabin)}",
    ]
    if row.amount_minor is None or row.depart_date is None:
        parts.append(COMMAND_NO_PRICE)
        parts.append(f"較前一輪 {COMMAND_NONE}")
    else:
        dates = date_range_text(row.depart_date, row.return_date)
        money = _money_with_note(row.amount_minor, row.currency, row.adults, row.children)
        parts.append(f"{money} {dates}")
        if row.data_stale:
            parts.append(digest_stale_label(stale_after_hours))
        delta = command_delta_text(row.delta_direction, row.delta_minor, row.currency)
        parts.append(f"較前一輪 {delta}")
    parts.append(f"上次查價 {_short_time(row.last_scanned_at)}")
    if row.watch_stale:
        parts.append(DIGEST_WATCH_STALE)
    return "｜".join(parts)


def command_list_message(
    rows: Sequence[CommandWatchLine],
    paused_ids: Sequence[int],
    expired_ids: Sequence[int],
    stale_after_hours: int = 24,
) -> str:
    extra = []
    if paused_ids:
        extra.append("停用中：" + "、".join(f"#{i}" for i in paused_ids))
    if expired_ids:
        extra.append("已過期：" + "、".join(f"#{i}" for i in expired_ids))
    if not rows:
        return "\n".join([f"{COMMAND_PREFIX} {COMMAND_NO_ACTIVE}", *extra])
    footer = [*extra, "", COMMAND_DELTA_NOTE, SAMPLED_ONLY_NOTE, COMMAND_TIME_NOTE, DISCLAIMER]
    return fit_reply(
        [command_list_title(len(rows))],
        [command_list_line(r, stale_after_hours) for r in rows],
        footer,
        max_items=COMMAND_LIST_MAX_LINES,
    )


@dataclass(frozen=True)
class CommandPriceRow:
    """One of the cheapest date pairs of ``/watch``."""

    depart_date: date
    return_date: date | None
    amount_minor: int
    currency: str
    carrier: str | None
    stops: int | None
    booking_url: str
    booking_note: str | None
    fetched_at: datetime | None = None
    data_stale: bool = False


@dataclass(frozen=True)
class CommandRunSummary:
    """The latest finished scan run, as counts and labels (no raw error text)."""

    finished_at: datetime | None
    status: str
    sampled: int
    queries_used: int
    skip_notes: tuple[str, ...]


@dataclass(frozen=True)
class CommandWatchDetail:
    watch_id: int
    name: str
    status: str
    origin: str
    destination: str
    trip_type: str
    dates: str
    adults: int
    children: int
    cabin: str
    airlines: str
    dep_window: str
    max_stops: str
    budget: str
    prices: tuple[CommandPriceRow, ...]
    last_run: CommandRunSummary | None
    stale_after_hours: int = 24


def stops_text(stops: int | None) -> str:
    if stops == 0:
        return "直飛"
    return f"轉機 {stops} 次" if stops else "轉機資訊未提供"


def _run_lines(run: CommandRunSummary | None) -> list[str]:
    if run is None:
        return [COMMAND_NEVER_SCANNED]
    when = f"{format_taipei(run.finished_at)}（台北時間）" if run.finished_at else "執行中"
    label = SCAN_RESULT_LABELS.get(run.status, run.status)
    lines = [
        f"上次掃描：{when}｜{label}｜取樣 {run.sampled} 組日期，對外查詢 {run.queries_used} 次"
    ]
    if run.skip_notes:
        lines.append("略過：" + "；".join(run.skip_notes))
    return lines


def command_watch_message(detail: CommandWatchDetail) -> str:
    trip = TRIP_TYPE_LABELS.get(detail.trip_type, detail.trip_type)
    status = COMMAND_STATUS_LABELS.get(detail.status, detail.status)
    head = [
        f"{COMMAND_PREFIX} 監看 #{detail.watch_id}「{_short_name(detail.name)}」（{status}）",
        f"路線：{route_label(detail.origin, detail.destination)}｜{trip}",
        f"日期：{detail.dates}",
        f"人數：{pax_label(detail.adults, detail.children)}｜艙等：{cabin_label(detail.cabin)}"
        f"｜航空：{detail.airlines}｜時段：{detail.dep_window}｜轉機：{detail.max_stops}",
        f"預算門檻：{detail.budget}",
    ]
    items: list[str] = []
    if not detail.prices:
        head.append(f"{COMMAND_TOP_TITLE}日期：{COMMAND_NO_PRICE}")
    else:
        head.append(f"{COMMAND_TOP_TITLE} {len(detail.prices)} 組日期：")
        for index, row in enumerate(detail.prices, start=1):
            dates = date_range_text(row.depart_date, row.return_date)
            money = _money_with_note(row.amount_minor, row.currency, detail.adults, detail.children)
            entry = (
                f"{index}. {dates} {money}｜{row.carrier or '航空公司未提供'}"
                f"｜{stops_text(row.stops)}｜查到 {_short_time(row.fetched_at)}"
            )
            if row.data_stale:
                entry += f"｜{digest_stale_label(detail.stale_after_hours)}"
            entry += f"\n   查票連結：{row.booking_url}"
            if row.booking_note:
                entry += f"\n   （{row.booking_note}）"
            items.append(entry)
    footer = ["", *_run_lines(detail.last_run), SAMPLED_ONLY_NOTE, COMMAND_TIME_NOTE, DISCLAIMER]
    return fit_reply(head, items, footer)


@dataclass(frozen=True)
class CommandScanResult:
    """``/scan`` follow-up: this run plus the watch's snapshot after it.

    ``run_status`` is None when no run happened (``failure_reason`` says why).
    """

    watch_id: int
    name: str
    currency: str
    adults: int
    children: int
    run_status: str | None
    failure_reason: str | None
    amount_minor: int | None
    depart_date: date | None
    return_date: date | None
    delta_direction: str | None
    delta_minor: int | None
    sampled: int
    queries_used: int
    skip_notes: tuple[str, ...]
    fetched_at: datetime | None = None
    data_stale: bool = False
    # The lowest price was not found by this run (failed / partial run or no run).
    carried_over: bool = False
    stale_after_hours: int = 24


def scan_scheduled_text(sampled: int) -> str:
    """``/scan`` round that sent no query: only the scheduled pairs are stated (FD-9 F1)."""
    return f"本輪排定 {sampled} 組日期，未對外查詢"


def command_scan_result_message(result: CommandScanResult) -> str:
    title = f"{COMMAND_PREFIX} /scan #{result.watch_id}「{_short_name(result.name)}」"
    lines: list[str] = []
    if result.run_status is None:
        lines.append(f"{title} 未查價：{result.failure_reason or SCAN_FAILURE_FALLBACK}")
    else:
        label = SCAN_RESULT_LABELS.get(result.run_status, result.run_status)
        lines.append(f"{title} 查價完成（{label}）")
        if result.failure_reason:
            lines.append(f"本輪未查到價格：{result.failure_reason}")
        if result.queries_used == 0:
            lines.append(scan_scheduled_text(result.sampled))
        else:
            lines.append(f"本輪取樣 {result.sampled} 組日期，對外查詢 {result.queries_used} 次")
        if result.skip_notes:
            lines.append("略過：" + "；".join(result.skip_notes))
    if result.amount_minor is not None and result.depart_date is not None:
        dates = date_range_text(result.depart_date, result.return_date)
        money = _money_with_note(
            result.amount_minor, result.currency, result.adults, result.children
        )
        delta = command_delta_text(result.delta_direction, result.delta_minor, result.currency)
        lines.append(f"目前最低價：{money} {dates}（查到 {_short_time(result.fetched_at)}）")
        if result.carried_over:
            lines.append(COMMAND_CARRIED_OVER)
        if result.data_stale:
            lines.append(digest_stale_label(result.stale_after_hours))
        lines.append(f"較前一輪：{delta}")
    else:
        pax = pax_label(result.adults, result.children)
        lines.append(f"目前最低價：{COMMAND_NO_PRICE}（{pax}）")
    return fit_reply(
        lines, [], ["", COMMAND_DELTA_NOTE, SAMPLED_ONLY_NOTE, COMMAND_TIME_NOTE, DISCLAIMER]
    )


@dataclass(frozen=True)
class CommandSourceStatus:
    source: str
    state_label: str
    breaker_label: str
    last_failure_at: datetime | None


@dataclass(frozen=True)
class CommandExplorationStatus:
    origin: str
    destination: str
    trip_type: str
    year: int
    month: int
    trip_days: int | None
    done: int
    total: int
    end_year: int | None = None
    end_month: int | None = None


@dataclass(frozen=True)
class CommandComparisonStatus:
    done: int
    total: int


@dataclass(frozen=True)
class CommandStatus:
    now: datetime
    sources: tuple[CommandSourceStatus, ...]
    hourly_used: int
    hourly_limit: int
    scheduler_running: bool
    next_scan_at: datetime | None
    exploration: CommandExplorationStatus | None
    comparison: CommandComparisonStatus | None = None


def _next_scan_text(status: CommandStatus) -> str:
    if not status.scheduler_running:
        return COMMAND_SCHEDULER_STOPPED
    if status.next_scan_at is None:
        return COMMAND_NEXT_SCAN_NONE
    when = format_taipei(status.next_scan_at)
    if status.exploration is not None:
        if status.next_scan_at <= status.now:
            return COMMAND_NEXT_SCAN_DEFERRED
        return f"{when}（台北時間；{COMMAND_NEXT_SCAN_MAYBE_DEFERRED}）"
    return f"{when}（台北時間）"


def _exploration_text(item: CommandExplorationStatus | None) -> str:
    if item is None:
        return COMMAND_NO_EXPLORATION
    trip = TRIP_TYPE_LABELS.get(item.trip_type, item.trip_type)
    if item.trip_days:
        trip += f" {item.trip_days} 天"
    months = month_range_label(
        item.year,
        item.month,
        item.end_year if item.end_year is not None else item.year,
        item.end_month if item.end_month is not None else item.month,
    )
    return (
        f"{route_label(item.origin, item.destination)} {months}"
        f" {trip}，已查 {item.done}／共 {item.total}"
    )


def comparison_status_text(item: CommandComparisonStatus) -> str:
    """``/status`` line while a comparison runs (FD-10 Decision 9, F1)."""
    return f"比價：進行中（已查 {item.done}／共 {item.total}），排程掃描順延"


def command_status_message(status: CommandStatus) -> str:
    lines = [f"{COMMAND_PREFIX} 服務狀態（{format_taipei(status.now)} 台北時間）"]
    if not status.sources:
        lines.append(f"資料源：{COMMAND_NONE}")
    for item in status.sources:
        text = (
            f"資料源：{source_label(item.source)} {item.state_label}｜斷路器：{item.breaker_label}"
        )
        if item.last_failure_at is not None:
            text += f"｜最近失敗 {_short_time(item.last_failure_at)}"
        lines.append(text)
    lines.append(f"本小時查詢額度：已用 {status.hourly_used}／上限 {status.hourly_limit}")
    lines.append(f"下次掃描：{_next_scan_text(status)}")
    lines.append(f"探索：{_exploration_text(status.exploration)}")
    if status.comparison is not None:
        lines.append(comparison_status_text(status.comparison))
    return fit_reply(lines, [], [])


def command_record_text(command_text: str, reply: str) -> str:
    """``message_text`` of a ``command`` notification row: "指令 → 回覆"."""
    return f"{command_text} → {reply}"


def command_static_texts() -> list[str]:
    """Wording added by FD-7 commands, for the banned-phrase test."""
    sample_line = CommandWatchLine(
        3,
        "東京",
        "TPE",
        "NRT",
        "TWD",
        2,
        1,
        "business",
        1_000_000,
        date(2026, 12, 10),
        date(2026, 12, 15),
        "down",
        50_000,
        None,
    )
    return [
        COMMAND_HELP,
        COMMAND_UNKNOWN,
        COMMAND_NOT_TEXT,
        COMMAND_TOO_LONG,
        COMMAND_FAILED,
        COMMAND_NO_ACTIVE,
        COMMAND_NO_PRICE,
        COMMAND_TIME_NOTE,
        COMMAND_DELTA_NOTE,
        COMMAND_SCHEDULER_OFF,
        COMMAND_SCAN_PAUSED,
        COMMAND_SCAN_EXPIRED,
        COMMAND_SCAN_PENDING,
        COMMAND_SCAN_DEFERRED,
        COMMAND_COMPARISON_DEFERRED,
        COMMAND_SCAN_COMPARISON_DEFERRED,
        comparison_status_text(CommandComparisonStatus(3, 8)),
        COMMAND_SCAN_FOLLOW_UP,
        COMMAND_DIGEST_QUEUED,
        COMMAND_NO_EXPLORATION,
        COMMAND_NEXT_SCAN_NONE,
        COMMAND_NEXT_SCAN_DEFERRED,
        COMMAND_NEXT_SCAN_MAYBE_DEFERRED,
        COMMAND_SCHEDULER_STOPPED,
        COMMAND_NEVER_SCANNED,
        COMMAND_TOP_TITLE,
        COMMAND_CARRIED_OVER,
        *COMMAND_STATUS_LABELS.values(),
        *SCAN_RESULT_LABELS.values(),
        *SCAN_FAILURE_REASONS.values(),
        SCAN_FAILURE_FALLBACK,
        command_usage("watch"),
        command_usage("list"),
        command_not_found(99),
        command_backlog(2),
        command_quota_exhausted(60, 60),
        command_scan_queued(3, "東京"),
        command_paused(3, "台北 → 東京"),
        command_resumed(3, "台北 → 東京"),
        command_already_paused(3),
        command_already_active(3),
        command_resume_expired(3),
        command_pause_expired(3),
        command_hidden_note(5),
        command_list_title(2),
        command_list_line(sample_line),
        command_list_line(replace(sample_line, data_stale=True, watch_stale=True), 24),
        stops_text(0),
        stops_text(1),
        stops_text(None),
    ]


# ---- data retention and VACUUM (ADR-0002 FD-7 Decisions 7, 8, 10) -------------------

MAINTENANCE_NEVER = "尚未執行"
MAINTENANCE_TABLE_LABELS: dict[str, str] = {
    "watch": "監看",
    "scan_run": "掃描輪",
    "price_observation": "價格觀測",
    "notification": "通知",
    "exploration": "探索",
    "comparison": "比價",
    "comparison_cell": "比價明細",
}
MAINTENANCE_RUNNING_DEFERRED = "掃描或探索進行中，清除順延"
VACUUM_DISABLED = "已關閉每週壓縮"


def size_label(size_bytes: int) -> str:
    """Whole-number friendly size: "512 KB", "12.3 MB", "1.2 GB" (integer math)."""
    if size_bytes < 1024 * 1024:
        return f"{(size_bytes + 1023) // 1024} KB"
    if size_bytes < 1024 * 1024 * 1024:
        tenths = size_bytes * 10 // (1024 * 1024)
        return f"{tenths // 10}.{tenths % 10} MB"
    tenths = size_bytes * 10 // (1024 * 1024 * 1024)
    return f"{tenths // 10}.{tenths % 10} GB"


def retention_note(days: int) -> str:
    """Detail page: price history only covers the retention period (FR-R7)."""
    return f"價格紀錄保留最近 {days} 天"


def retention_lowered_notice(days: int) -> str:
    return f"下次清除將刪除超過 {days} 天的資料"


def notification_retention_lowered_notice(days: int) -> str:
    return f"下次清除將刪除超過 {days} 天的通知紀錄"


def stats_time_note(at: str) -> str:
    """Bare time of the cached counts; the page supplies its own label and refresh note."""
    return f"{at}（台北時間）"


def duration_text(milliseconds: int) -> str:
    tenths = max(milliseconds, 0) // 100
    return f"{tenths // 10}.{tenths % 10} 秒"


def retention_summary(
    *,
    runs: int,
    observations: int,
    notifications: int,
    other: int,
    backup_created: bool,
    duration_ms: int,
) -> str:
    backup = "已先建立備份" if backup_created else "未建立新備份（沒有可刪資料或今日已備份）"
    return (
        f"刪除掃描輪 {runs:,}、價格觀測 {observations:,}、通知 {notifications:,}、"
        f"其他 {other:,}；{backup}；耗時 {duration_text(duration_ms)}"
    )


def retention_backup_failed(reason: str) -> str:
    return f"備份失敗，本次沒有刪除任何資料，下次清除會重試：{reason}"


def retention_failed(reason: str) -> str:
    return f"清除未完成，下次清除會接續：{reason}"


def vacuum_result_text(before: str, after: str) -> str:
    return f"{before} → {after}"


def vacuum_skipped_disk(need: str, free: str) -> str:
    return f"磁碟可用空間不足，略過壓縮（需要約 {need}，可用 {free}）"


def vacuum_failed(reason: str) -> str:
    return f"壓縮失敗，資料未受影響：{reason}"


def retention_static_texts() -> list[str]:
    """Wording added by FD-7 retention, for the banned-phrase test."""
    return [
        MAINTENANCE_NEVER,
        *MAINTENANCE_TABLE_LABELS.values(),
        MAINTENANCE_RUNNING_DEFERRED,
        VACUUM_DISABLED,
        size_label(12_900_000),
        retention_note(180),
        retention_lowered_notice(60),
        notification_retention_lowered_notice(60),
        stats_time_note("2026-10-29 12:00"),
        retention_summary(
            runs=1, observations=12, notifications=1, other=2, backup_created=True, duration_ms=1234
        ),
        retention_summary(
            runs=0, observations=0, notifications=0, other=0, backup_created=False, duration_ms=5
        ),
        retention_backup_failed("OSError"),
        retention_failed("OperationalError"),
        vacuum_result_text("12.0 MB", "8.0 MB"),
        vacuum_skipped_disk("24.0 MB", "10.0 MB"),
        vacuum_failed("OperationalError"),
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
        *command_static_texts(),
        *retention_static_texts(),
        *comparison_static_texts(),
    ]
