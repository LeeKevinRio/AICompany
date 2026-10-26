"""User-facing message templates (plain text, factual statements only).

Wording rule (PRD FR-C5): state what was found ("查到 ... 價"); never advise when or
whether to buy. Templates here are the single source for notification text.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from flight_deals.domain.currency import format_money
from flight_deals.domain.links import google_flights_url
from flight_deals.domain.rules import TriggeredItem
from flight_deals.domain.timeutil import format_taipei, format_travel_date

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
) -> str:
    """One merged message for all triggered items of a watch in a single scan."""
    trip = TRIP_TYPE_LABELS.get(trip_type, trip_type)
    lines = [f"[flight-deals] 監看「{watch_name}」查到 {len(items)} 筆符合條件的價格（{trip}）"]
    for index, item in enumerate(items, start=1):
        cand = item.candidate
        dates = date_range_text(cand.depart_date, cand.return_date)
        lines.append("")
        lines.append(
            f"{index}. 查到 {origin}→{destination} {dates} "
            f"{format_money(cand.amount_minor, cand.currency)}"
        )
        lines.append(f"   觸發原因：{item_reasons_text(item)}")
        lines.append(f"   航空公司：{cand.carrier or '未提供'}")
        lines.append(
            f"   查到時間：{format_taipei(cand.fetched_at)}（台北時間）"
            f"｜來源：{source_label(cand.source)}"
            f"（{PRICE_KIND_LABELS.get(cand.price_kind, cand.price_kind)}）"
        )
        lines.append(
            "   查票連結："
            + google_flights_url(origin, destination, cand.depart_date, cand.return_date)
        )
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
    ]
