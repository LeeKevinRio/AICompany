"""Read models for the web layer: display-ready values, already formatted (zh-TW)."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import MISSING, dataclass, fields
from datetime import date, datetime, timedelta
from typing import Any, Literal, TypeVar

from flight_deals.domain.airlines import AIRLINES, lookup_airline
from flight_deals.domain.airports import full_place_label, place_label, route_label
from flight_deals.domain.currency import format_money, minor_to_major_int
from flight_deals.domain.dates import expand_pairs, first_pair
from flight_deals.domain.flight_summary import FlightFacts, FlightSummary, flight_summary
from flight_deals.domain.links import google_flights_url
from flight_deals.domain.messages import (
    DETAIL_ALL_DEPARTED,
    DISCLAIMER,
    MAINTENANCE_NEVER,
    MAINTENANCE_TABLE_LABELS,
    PRICE_KIND_LABELS,
    SAMPLED_ONLY_NOTE,
    STATUS_LABELS,
    TRIP_TYPE_LABELS,
    WEB_BOOKING_FALLBACK_NOTE,
    WEB_TEXTS,
    WEEKDAY_OPTION_LABELS,
    coverage_text,
    date_range_text,
    date_range_weekday_text,
    fetched_range_label,
    health_no_embedded_note,
    overhead_bin_label,
    reason_label,
    retention_backup_failed,
    retention_failed,
    retention_note,
    retention_summary,
    row_source_text,
    size_label,
    source_label,
    source_page_note,
    split_ticket_label,
    stale_rounds_label,
    stats_time_note,
    top_explain,
    vacuum_failed,
    vacuum_result_text,
    vacuum_skipped_disk,
    watch_settings_summary,
)
from flight_deals.domain.models import (
    CABINS,
    DatePair,
    TripType,
    Watch,
    WatchSpec,
    search_for,
)
from flight_deals.domain.timeutil import format_taipei, taipei_date, to_utc_iso, weekday_label
from flight_deals.domain.trip_labels import (
    airlines_text,
    cabin_label,
    conditions_label,
    dep_window_label,
    depart_weekdays_label,
    pax_full_label,
    pax_summary,
    stay_range_label,
    total_price_note,
    total_price_short,
    web_price_caption,
    web_price_note,
)
from flight_deals.ports import AutostartProbe, BookingLinkBuilder, Clock
from flight_deals.services.digest import taipei_midnight
from flight_deals.services.health import HealthService, describe_source, no_embedded_streak
from flight_deals.services.notifications import safe_booking_url
from flight_deals.services.price_snapshot import (
    CARD_PAIRS,
    PriceDelta,
    Snapshot,
    cheapest_pairs,
    latest_per_pair,
)
from flight_deals.services.retention import RetentionService
from flight_deals.services.settings import SETTING_KEYS, SettingsService
from flight_deals.storage.repository import ObservationRecord, Repository, ScanRunRecord

TOP_N = 10
TREND_POINTS = 60
CHART_WIDTH = 640
CHART_HEIGHT = 180
CHART_PAD = 24

QUERY_STATUS_LABELS = {
    "ok": "成功",
    "no_data": "查無航班",
    "blocked": "被擋或格式改變",
    "error": "錯誤",
    "skipped": "未查",
    "currency_mismatch": "幣別不符",
}
SKIP_REASON_LABELS = {
    "global_hourly_limit": "已達全域每小時查詢上限",
    "breaker_open": "資料源斷路器開啟中",
}
SCAN_STATUS_LABELS = {
    "running": "執行中",
    "ok": "成功",
    "partial": "部分成功",
    "failed": "失敗",
}
TRIGGER_LABELS = {"scheduled": "排程", "manual": "立即查價", "startup": "啟動補跑"}
NOTIFICATION_STATUS_LABELS = {
    "pending": "待送出",
    "sent": "成功",
    "failed": "失敗",
    "suppressed": "未送出（未設定）",
}
NOTIFICATION_KIND_LABELS = {
    "price_alert": "價格通知",
    "ops_source_failure": "資料源異常告警",
    "test": "測試訊息",
    "daily_digest": "每日摘要",
    "command": "指令",
    "manual_digest": "手動摘要",
}
# Badge colour of each command poller state key (health-* classes in app.css).
COMMAND_STATE_TONES = {
    "unconfigured": "unknown",
    "group_chat": "unknown",
    "invalid_chat": "unknown",
    "unauthorized": "down",
    "not_started": "unknown",
    "disabled": "unknown",
    "running": "ok",
    "running_failing": "warn",
}
# Command poller row of the health page (FD-7 Decision 10).
COMMAND_STATE_LABELS = {
    "unconfigured": "未設定 Telegram",
    "group_chat": "不支援群組：指令只接受與 bot 的一對一私訊（chat id 為負數）",
    "invalid_chat": "chat id 格式不正確，指令功能無作用",
    "unauthorized": "已停止（bot token 無效，更新 token 後請重新啟動服務）",
    "not_started": "未執行（此實例沒有持有排程鎖）",
    "disabled": "已關閉",
    "running": "運作中",
    "running_failing": "運作中（最近連線失敗，重試中）",
}
# New-watch form defaults come from the domain model, never from literals here (C-40).
_SPEC_DEFAULTS: dict[str, Any] = {
    f.name: f.default for f in fields(WatchSpec) if f.default is not MISSING
}
# FR-A10: with an airline / time filter, "no data" means nothing matched the filter.
NO_MATCH_LABEL = "依目前航空／時段條件沒有符合的班次"
# no_data sub-reason from the source: nothing embedded in the page (ADR FD-5 status row).
# Shown as the short label ``ui.manual_check`` (FD-12 FR-11), never as "查詢失敗".
NO_EMBEDDED_REASON = "no_embedded_results"


def hit_no_embedded(query_results: Sequence[Mapping[str, Any]]) -> bool:
    """The run hit at least one page without embedded results."""
    return any(
        r.get("status") == "no_data" and r.get("reason") == NO_EMBEDDED_REASON
        for r in query_results
    )


def flight_view(facts: FlightFacts | None, trip_type: TripType) -> FlightSummary | None:
    """The one way pages get flight wording (ADR-0002 FD-12, C-98)."""
    return None if facts is None else flight_summary(facts, trip_type=trip_type)


def return_flight_view(obs: ObservationRecord | None, currency: str) -> FlightSummary | None:
    """Only the observation's own return flight, for a live price in the watch's currency."""
    if obs is None or obs.price_kind != "live" or obs.currency != currency:
        return None
    leg = obs.return_leg
    return None if leg is None else flight_summary(leg, trip_type="round_trip", returning=True)


def coverage_counts(checked: int, spec: WatchSpec, today: date) -> tuple[int, int] | None:
    """FD-19: (pairs with a price, pairs ahead); None for a single pair."""
    total = len(expand_pairs(spec, today))
    if total <= 1:
        return None
    return min(checked, total), total


# Notification log: how many entries show before the "older" fold (FD-22 ruling M1).
NOTIFICATIONS_SHOWN = 20


def coverage_label(checked: int, spec: WatchSpec, today: date) -> str | None:
    counts = coverage_counts(checked, spec, today)
    return None if counts is None else coverage_text(*counts)


def list_page_notes(rows: list[dict[str, Any]]) -> dict[str, bool]:
    """Which page notes the list shows; the extra pairs count like the main card (FD-19 R4)."""
    priced = [r for r in rows if r["min_price"]]
    items = [(r, item) for r in priced for item in (r, *r["more_pairs"])]
    round_trip = any(
        (item["flight"] is not None and item["flight"].is_outbound_only)
        or (row["is_round_trip"] and (item["split_ticket_label"] or item["overhead_bin_label"]))
        for row, item in items
    )
    return {
        "priced": bool(priced),
        "round_trip": round_trip,
        # Summary line only (FD-22 ruling): any priced round-trip watch counts, even an old
        # record without flight data or marks. Every panel sentence keeps using "round_trip".
        "summary_round_trip": round_trip or any(r["is_round_trip"] for r in priced),
        "return_listed": any(r["return_flight"] for r in priced),
        "overhead_one_way": not round_trip and any(item["overhead_bin_label"] for _, item in items),
        "booking": any(item["booking_url"] for _, item in items),
        # Any card, priced or not: a window with no price yet is n = 0 < total too.
        "sampled": any(r["coverage_incomplete"] for r in rows),
    }


def kind_badge(price_kind: str, as_of_basis: str) -> str | None:
    """Row qualifier that must stay visible (FR-9): cached price, data time unknown."""
    if price_kind != "cached":
        return None
    if as_of_basis == "fetch_time":
        return f"{WEB_TEXTS.kind_cached}；{WEB_TEXTS.data_time_unknown}"
    return WEB_TEXTS.kind_cached


def fetched_label(moment: datetime) -> str:
    """Visible "查到時間" next to a price (risk-compliance R4)."""
    return f"{WEB_TEXTS.price_prefix}時間 {format_taipei(moment)}"


def fetched_short_label(moment: datetime, now: datetime) -> str:
    """List-card fetch time (FD-22 P2): "查到 11/01 20:33"; the year only when it is not
    the current Taipei year. The prefix stays; never a relative time."""
    stamp = format_taipei(moment)
    if stamp[:4] == format_taipei(now)[:4]:
        stamp = stamp[5:].replace("-", "/")
    return f"{WEB_TEXTS.price_prefix} {stamp}"


def route_view(spec: WatchSpec) -> dict[str, str]:
    """List-card route line (FD-22 P4). Round trip: "台北 TPE ⇄ 札幌 CTS"; one way keeps the
    arrow and "・單程". Full airport names go to the title and the screen-reader text."""
    round_trip = spec.trip_type == "round_trip"
    arrow = "⇄" if round_trip else "→"
    suffix = "" if round_trip else f"・{TRIP_TYPE_LABELS[spec.trip_type]}"
    shown = f"{place_label(spec.origin)} {arrow} {place_label(spec.destination)}{suffix}"
    full = f"{full_place_label(spec.origin)} {arrow} {full_place_label(spec.destination)}"
    spoken = f"{full}・{TRIP_TYPE_LABELS[spec.trip_type]}"
    return {"route_text": shown, "route_title": full, "route_sr": spoken}


def pair_note(entry: Mapping[str, Any]) -> str | None:
    """Explanation column of one sampled pair (FR-12): skip reason, "需人工查價" and the
    skipped-itinerary counts, joined by "；". An error without a known label becomes
    "查詢失敗"; adapter text is never returned."""
    parts: list[str] = []
    reason = entry.get("reason")
    if isinstance(reason, str) and reason in SKIP_REASON_LABELS:
        parts.append(SKIP_REASON_LABELS[reason])
    if entry.get("status") == "no_data" and reason == NO_EMBEDDED_REASON:
        parts.append(WEB_TEXTS.manual_check)
    tries = entry.get("tries")
    last = tries[-1] if isinstance(tries, list) and tries else {}
    last = last if isinstance(last, Mapping) else {}
    if last.get("error") and not parts:
        parts.append(WEB_TEXTS.query_failed)
    parts.extend(parse_notes(last))
    return "；".join(parts) or None


def run_note(run: ScanRunRecord) -> str | None:
    """Note of a scan run from its structured per-pair results only (FR-12): distinct
    status / skip labels of the pairs that did not succeed. ``error_summary`` is never
    parsed; with a summary but no label the note is "查詢失敗"."""
    if not run.error_summary:
        return None
    labels: list[str] = []
    for entry in run.query_results:
        status = str(entry.get("status") or "skipped")
        reason = entry.get("reason")
        label: str | None = None
        if status == "no_data" and reason == NO_EMBEDDED_REASON:
            label = WEB_TEXTS.manual_check
        elif isinstance(reason, str) and reason in SKIP_REASON_LABELS:
            label = SKIP_REASON_LABELS[reason]
        elif status not in ("ok", "no_data"):
            label = QUERY_STATUS_LABELS.get(status)
        tries = entry.get("tries")
        last = tries[-1] if isinstance(tries, list) and tries else {}
        last = last if isinstance(last, Mapping) else {}
        # Only the unrecognised-format count: unpriced itineraries are expected.
        for text in (label, *parse_notes({"malformed": last.get("malformed")})):
            if text and text not in labels:
                labels.append(text)
    return "；".join(labels) or WEB_TEXTS.query_failed


def known_error_label(text: str | None, known: Iterable[str]) -> str | None:
    """Exploration / comparison summaries that are system constants (scheduler off,
    restart, quota or breaker skip notes) are shown as they are; anything else, such as
    an exception, becomes "查詢失敗" (FR-12)."""
    if not text:
        return None
    for item in known:
        if text == item or text.startswith(item + "，"):
            return text
    return WEB_TEXTS.query_failed


PriceLevel = Literal["cheap", "mid", "pricey"]
K = TypeVar("K")


def price_levels(items: Sequence[tuple[K, int]]) -> dict[K, PriceLevel]:
    """Thirds of the given prices: cheapest third, priciest third (3+ items), the rest
    mid. Ties keep the input order (stable sort). Shared by the watch detail page and
    the exploration calendar (ADR-0002 FD-6 Decision 7)."""
    if not items:
        return {}
    ordered = sorted(items, key=lambda item: item[1])
    third = max(len(ordered) // 3, 1)
    cheap = {key for key, _ in ordered[:third]}
    pricey = {key for key, _ in ordered[-third:]} if len(ordered) >= 3 else set()
    return {
        key: "cheap" if key in cheap else ("pricey" if key in pricey else "mid") for key, _ in items
    }


def active_exploration_view(repo: Repository) -> dict[str, int] | None:
    """The queued / running exploration for the health and explore pages."""
    record = repo.active_exploration()
    if record is None:
        return None
    return {"id": record.id, "done": record.done, "total": record.total}


def active_comparison_view(repo: Repository) -> dict[str, int] | None:
    """The queued / running comparison for the explore, compare and health pages."""
    record = repo.active_comparison()
    if record is None:
        return None
    return {"id": record.id, "done": record.done, "total": record.total}


_ITEM_KEY_REVISION = re.compile(r"^price:\d+:r(\d+):")
BREAKER_LABELS = {
    "closed": "關閉（正常查詢）",
    "open": "開啟（暫停查詢）",
    "half_open": "半開（試查中）",
}


@dataclass
class ViewHooks:
    next_run_time: Callable[[], datetime | None] = lambda: None
    scheduler_running: Callable[[], bool] = lambda: False
    # Telegram command poller state (FD-7 Decision 10); None hides the row.
    command_status: Callable[[], Any] = lambda: None


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def parse_notes(try_info: Mapping[str, Any]) -> list[str]:
    """Explain skipped itineraries from the integer counts stored on a query try."""
    notes = []
    unpriced = _count(try_info.get("unpriced"))
    malformed = _count(try_info.get("malformed"))
    if unpriced:
        notes.append(f"略過 {unpriced} 筆無價格航班")
    if malformed:
        notes.append(f"回應中有 {malformed} 筆格式無法辨識")
    return notes


def stay_label(spec: WatchSpec) -> str | None:
    """Trip length of a flexible round trip ("4 天" / "3–5 天"); None otherwise."""
    if spec.min_trip_days is None or spec.max_trip_days is None:
        return None
    return stay_range_label(spec.min_trip_days, spec.max_trip_days)


def dates_text(spec: WatchSpec) -> str:
    if spec.date_mode == "fixed":
        if spec.depart_date is None:
            return ""
        if spec.trip_type == "round_trip" and spec.return_date:
            return f"固定 {spec.depart_date.isoformat()} 出發，{spec.return_date.isoformat()} 回程"
        return f"固定 {spec.depart_date.isoformat()} 出發"
    start = spec.window_start.isoformat() if spec.window_start else "?"
    end = spec.window_end.isoformat() if spec.window_end else "?"
    if spec.trip_type == "round_trip":
        text = f"彈性 {start} ～ {end}，旅程 {stay_label(spec) or '?'}"
    else:
        text = f"彈性出發 {start} ～ {end}"
    # FD-10: a weekday filter is part of the window; all weekdays add nothing.
    weekdays = depart_weekdays_label(spec.depart_weekdays)
    return text if weekdays is None else f"{text}，{weekdays}"


def has_filters(spec: WatchSpec) -> bool:
    return bool(spec.airlines) or spec.dep_hour_from is not None


def web_pax_view(trip_type: str, adults: int, children: int, cabin: str) -> dict[str, Any]:
    """Web price notes (C-40 as revised by FD-12): ``pax_note`` only with more than one
    traveller (shown next to every price); ``pax_summary`` is the visible summary line
    ("1 位成人・<cabin>"); ``price_caption`` heads price columns ("來回總價")."""
    return {
        "pax_note": web_price_note(adults, children),
        "pax_summary": pax_summary(adults, children, cabin),
        "price_caption": web_price_caption(trip_type, adults, children),
    }


def trip_view(spec: WatchSpec) -> dict[str, Any]:
    """Passenger / cabin / filter labels shared by the list and detail pages."""
    return {
        "adults": spec.adults,
        "children": spec.children,
        "cabin": spec.cabin,
        **web_pax_view(spec.trip_type, spec.adults, spec.children, spec.cabin),
        "pax_short": total_price_short(spec.adults, spec.children),
        "pax_full_label": pax_full_label(spec.adults, spec.children),
        "cabin_label": cabin_label(spec.cabin),
        "airlines_label": airlines_text(spec.airlines),
        "dep_window_label": dep_window_label(spec.dep_hour_from, spec.dep_hour_to),
        "conditions_label": conditions_label(spec.airlines, spec.dep_hour_from, spec.dep_hour_to),
    }


def item_key_revision(item_key: str) -> int | None:
    match = _ITEM_KEY_REVISION.match(item_key)
    return int(match.group(1)) if match else None


def delta_view(delta: PriceDelta | None) -> dict[str, str] | None:
    """List-page change: direction plus an unsigned amount label (C-34)."""
    if delta is None:
        return None
    return {
        "direction": delta.direction,
        "amount_label": format_money(abs(delta.delta_minor), delta.currency),
    }


class ViewService:
    def __init__(
        self,
        repo: Repository,
        settings: SettingsService,
        health: HealthService,
        *,
        source_names: Sequence[str],
        telegram_configured: bool,
        notification_max_attempts: int,
        breaker_threshold: int,
        clock: Clock,
        autostart: AutostartProbe | None = None,
        link_builder: BookingLinkBuilder | None = None,
        no_embedded_streak_rounds: int = 3,
    ) -> None:
        self._repo = repo
        self._streak_rounds = no_embedded_streak_rounds
        self._autostart = autostart
        self._links = link_builder
        self._settings = settings
        self._health = health
        self._source_names = list(source_names)
        self._telegram_configured = telegram_configured
        self._max_attempts = notification_max_attempts
        self._breaker_threshold = breaker_threshold
        self._clock = clock
        # The list page shows "可能已過期" without an extra settings read per request
        # (C-55: 1 + N connections); kept current through the settings listener.
        self._stale_hours = settings.current().stale_after_hours
        settings.listeners.append(self._on_settings_changed)
        self.hooks = ViewHooks()
        # Set by app.py; None leaves the health page's data maintenance block out.
        self.retention: RetentionService | None = None

    def _on_settings_changed(self, _before: Any, after: Any) -> None:
        self._stale_hours = int(after.stale_after_hours)

    # ---- shared page context -------------------------------------------------

    def base_context(self) -> dict[str, Any]:
        """Values every page needs: footer disclaimer, shared wording (``ui``) and
        today's Asia/Taipei date."""
        return {
            "disclaimer": DISCLAIMER,
            "sampled_only_note": SAMPLED_ONLY_NOTE,
            "ui": WEB_TEXTS,
            "today": taipei_date(self._clock()).isoformat(),
        }

    # ---- helpers -------------------------------------------------------------

    def _is_stale(self, fetched_at: datetime, now: datetime, hours: int) -> bool:
        return now - fetched_at > timedelta(hours=hours)

    def _price_row(
        self,
        watch: Watch,
        obs: ObservationRecord,
        now: datetime,
        stale_hours: int,
        *,
        with_flight: bool = True,
    ) -> dict[str, Any]:
        """One price row. Price, flight and booking link come from this one observation."""
        spec = watch.spec
        return {
            "dates": date_range_text(obs.depart_date, obs.return_date),
            "dates_weekday": date_range_weekday_text(obs.depart_date, obs.return_date),
            "depart": obs.depart_date.isoformat(),
            "return": obs.return_date.isoformat() if obs.return_date else None,
            "weekday": weekday_label(obs.depart_date),
            "amount_text": format_money(obs.amount_minor, obs.currency),
            "amount_minor": obs.amount_minor,
            "carrier": obs.carrier or "未提供",
            "stops": "直飛" if obs.stops == 0 else (f"轉機 {obs.stops} 次" if obs.stops else "—"),
            "fetched_text": format_taipei(obs.fetched_at),
            "fetched_label": fetched_label(obs.fetched_at),
            "fetched_short": fetched_short_label(obs.fetched_at, now),
            "stale": self._is_stale(obs.fetched_at, now, stale_hours),
            "source": source_label(obs.source),
            "source_key": obs.source,
            "kind": PRICE_KIND_LABELS.get(obs.price_kind, obs.price_kind),
            "kind_key": obs.price_kind,
            "kind_badge": kind_badge(obs.price_kind, obs.as_of_basis),
            # Set by the page: None when one page-level source line covers every row.
            "source_text": row_source_text(obs.source, obs.price_kind),
            "data_time_unknown": obs.price_kind == "cached" and obs.as_of_basis == "fetch_time",
            "currency_mismatch": obs.currency != spec.currency,
            "link": google_flights_url(
                spec.origin, spec.destination, obs.depart_date, obs.return_date
            ),
            **self._booking(watch, DatePair(obs.depart_date, obs.return_date), obs.watch_revision),
            "depart_time": obs.depart_time,
            # Old-revision rows keep only the airline column (FR-6).
            "flight": flight_view(obs, spec.trip_type) if with_flight else None,
            "overhead_bin_label": overhead_bin_label(obs.overhead_bin_excluded, spec.trip_type),
            "split_ticket_label": split_ticket_label(obs.split_ticket, spec.trip_type),
            "return_flight": return_flight_view(obs, spec.currency) if with_flight else None,
            "revision": obs.watch_revision,
        }

    def _booking(self, watch: Watch, pair: DatePair, revision: int) -> dict[str, str | None]:
        """Exact link for the current settings; old revisions and failures fall back."""
        spec = watch.spec
        url = None
        if revision == watch.revision:
            url = safe_booking_url(self._links, search_for(spec, pair, spec.currency))
        if url:
            return {"booking_url": url, "booking_note": None}
        return {
            "booking_url": google_flights_url(
                spec.origin, spec.destination, pair.depart, pair.return_date
            ),
            "booking_note": WEB_BOOKING_FALLBACK_NOTE,
        }

    def _link_pair(self, spec: WatchSpec) -> DatePair | None:
        # Constant time: never expand the whole window just to build one link.
        first = first_pair(spec, taipei_date(self._clock()))
        if first is None and spec.depart_date:
            first = DatePair(spec.depart_date, spec.return_date)
        elif first is None and spec.window_start:
            first = DatePair(spec.window_start, None)
        return first

    def watch_link(self, watch: Watch) -> str | None:
        spec = watch.spec
        first = self._link_pair(spec)
        if first is None:
            return None
        return google_flights_url(spec.origin, spec.destination, first.depart, first.return_date)

    def watch_booking(self, watch: Watch) -> dict[str, str | None]:
        first = self._link_pair(watch.spec)
        if first is None:
            return {"booking_url": None, "booking_note": None}
        return self._booking(watch, first, watch.revision)

    def _more_pair(
        self, watch: Watch, obs: ObservationRecord, now: datetime, stale_hours: int
    ) -> dict[str, Any]:
        """One of the list card's next pairs by price: amount, dates, fetched time, marks,
        outbound flight and link, all from this one observation (FD-19 R2, R3, R5, R6).
        Display only: no delta, no return flight (R8)."""
        spec = watch.spec
        return {
            "amount": format_money(obs.amount_minor, obs.currency),
            "dates_weekday_label": date_range_weekday_text(obs.depart_date, obs.return_date),
            "dates": date_range_text(obs.depart_date, obs.return_date),
            "fetched_label": fetched_label(obs.fetched_at),
            "fetched_short": fetched_short_label(obs.fetched_at, now),
            "stale": self._is_stale(obs.fetched_at, now, stale_hours),
            "flight": flight_view(obs, spec.trip_type),
            "overhead_bin_label": overhead_bin_label(obs.overhead_bin_excluded, spec.trip_type),
            "split_ticket_label": split_ticket_label(obs.split_ticket, spec.trip_type),
            **self._booking(watch, DatePair(obs.depart_date, obs.return_date), watch.revision),
        }

    def _future_watch_booking(self, watch: Watch, today: date) -> dict[str, str | None]:
        """Manual-check link of a card without a price: the first pair still ahead, never
        a departed date (FD-12, list card rule)."""
        first = self._link_pair(watch.spec)
        if first is None or first.depart < today:
            return {"booking_url": None, "booking_note": None}
        return self._booking(watch, first, watch.revision)

    # ---- pages ---------------------------------------------------------------

    def list_page(self) -> dict[str, Any]:
        rows = []
        now = self._clock()
        today = taipei_date(now)
        midnight = taipei_midnight(now)
        stale_hours = self._stale_hours
        # Watches carry their latest run's results in the same single query (C-34).
        for item in self._repo.list_watches_with_last_results(self._streak_rounds):
            watch, last_results = item.watch, item.last_results
            spec = watch.spec
            # One observation query per watch, as before FD-4 (C-34); only the rows a
            # snapshot reads (ADR-0002 FD-8 Decision 1).
            observations = self._repo.snapshot_observations_for_watch(
                watch.id,
                revision=watch.revision,
                currency=spec.currency,
                today=today,
                midnight=midnight,
            )
            snapshot = Snapshot.build(
                observations, revision=watch.revision, currency=spec.currency, today=today
            )
            cheapest = snapshot.cheapest
            # FD-19 R1: the detail page's ranking over the same population as the main
            # card; the card lists the next two after the main card's pair.
            ranked = cheapest_pairs(
                observations, revision=watch.revision, currency=spec.currency, today=today
            )
            more = (
                [
                    o
                    for o in ranked
                    if (o.depart_date, o.return_date)
                    != (cheapest.depart_date, cheapest.return_date)
                ][: CARD_PAIRS - 1]
                if cheapest is not None
                else []
            )
            coverage = coverage_counts(len(ranked), spec, today)
            streak = no_embedded_streak(item.recent_rounds, self._streak_rounds)
            if cheapest is not None:
                # Card price, flight and button come from this one observation (FD-12).
                booking = self._booking(
                    watch, DatePair(cheapest.depart_date, cheapest.return_date), watch.revision
                )
            elif watch.status != "expired":
                booking = self._future_watch_booking(watch, today)
            else:
                booking = {"booking_url": None, "booking_note": None}
            rows.append(
                {
                    "id": watch.id,
                    "name": spec.name,
                    "route": route_label(spec.origin, spec.destination),
                    **route_view(spec),
                    "trip": TRIP_TYPE_LABELS[spec.trip_type],
                    # FD-22 D#24: only one adult in economy may drop the party summary.
                    "pax_default": (
                        spec.adults == 1 and spec.children == 0 and spec.cabin == "economy"
                    ),
                    "dates": dates_text(spec),
                    "budget": (
                        format_money(spec.budget_amount_minor, spec.currency)
                        if spec.budget_amount_minor
                        else "未設定"
                    ),
                    "status": watch.status,
                    "status_label": STATUS_LABELS[watch.status],
                    "enabled": watch.status in ("active", "stale"),
                    "expired": watch.status == "expired",
                    "ended": watch.status == "expired",
                    "min_price": (
                        format_money(cheapest.amount_minor, cheapest.currency) if cheapest else None
                    ),
                    "min_price_dates": (
                        date_range_text(cheapest.depart_date, cheapest.return_date)
                        if cheapest
                        else None
                    ),
                    "dates_weekday_label": (
                        date_range_weekday_text(cheapest.depart_date, cheapest.return_date)
                        if cheapest
                        else None
                    ),
                    "cheapest_fetched_label": fetched_label(cheapest.fetched_at)
                    if cheapest
                    else None,
                    "cheapest_fetched_short": fetched_short_label(cheapest.fetched_at, now)
                    if cheapest
                    else None,
                    "stale": cheapest is not None
                    and self._is_stale(cheapest.fetched_at, now, stale_hours),
                    "flight": flight_view(cheapest, spec.trip_type),
                    "overhead_bin_label": (
                        overhead_bin_label(cheapest.overhead_bin_excluded, spec.trip_type)
                        if cheapest
                        else None
                    ),
                    "split_ticket_label": (
                        split_ticket_label(cheapest.split_ticket, spec.trip_type)
                        if cheapest
                        else None
                    ),
                    "return_flight": return_flight_view(cheapest, spec.currency),
                    **booking,
                    "is_round_trip": spec.trip_type == "round_trip",
                    "more_pairs": [self._more_pair(watch, o, now, stale_hours) for o in more],
                    "coverage_label": (
                        coverage_text(*coverage) if coverage and cheapest is not None else None
                    ),
                    "coverage_checked": coverage[0] if coverage else None,
                    "coverage_total": coverage[1] if coverage else None,
                    "coverage_incomplete": coverage is not None and coverage[0] < coverage[1],
                    # Not shown on the list since FD-22 (CEO decision on #9, option (a));
                    # kept in the row because the view-model tests and callers still read it.
                    "delta": delta_view(snapshot.delta_since_previous_run()),
                    "last_scanned": format_taipei(watch.last_scanned_at) or None,
                    # Replaces the price block of a card without a price (#47).
                    "no_price_label": (
                        None
                        if cheapest is not None
                        else WEB_TEXTS.no_displayable_price
                        if watch.last_scanned_at
                        else WEB_TEXTS.not_scanned
                    ),
                    "link": self.watch_link(watch),
                    # FR-11: "需人工查價" only without any price; with a price the streak
                    # becomes the short "近 N 輪未更新" label.
                    "manual_check": cheapest is None and hit_no_embedded(last_results),
                    "no_embedded_streak": streak,
                    "stale_rounds_label": (
                        stale_rounds_label(self._streak_rounds)
                        if streak and cheapest is not None
                        else None
                    ),
                    "filters_label": (
                        conditions_label(spec.airlines, spec.dep_hour_from, spec.dep_hour_to)
                        if has_filters(spec)
                        else None
                    ),
                    **trip_view(spec),
                }
            )
        return {
            "watches": rows,
            "notes": list_page_notes(rows),
            "disclaimer": DISCLAIMER,
        }

    def form_values(self, watch_id: int | None) -> dict[str, Any] | None:
        if watch_id is None:
            return {
                "origin": "TPE",
                "origin_label": place_label("TPE"),
                "destination": "",
                "destination_label": "",
                "trip_type": "round_trip",
                "date_mode": "fixed",
                "depart_date": "",
                "return_date": "",
                "window_start": "",
                "window_end": "",
                "min_trip_days": "",
                "max_trip_days": "",
                "max_stops": "",
                "budget": "",
                "name": "",
                "notify_on_new_low": True,
                "adults": _SPEC_DEFAULTS["adults"],
                "children": _SPEC_DEFAULTS["children"],
                "cabin": _SPEC_DEFAULTS["cabin"],
                "airlines": list(_SPEC_DEFAULTS["airlines"]),
                "dep_hour_from": _SPEC_DEFAULTS["dep_hour_from"],
                "dep_hour_to": _SPEC_DEFAULTS["dep_hour_to"],
                "depart_weekdays": list(_SPEC_DEFAULTS["depart_weekdays"]),
            }
        watch = self._repo.get_watch(watch_id)
        if watch is None:
            return None
        spec = watch.spec

        def d(value: date | None) -> str:
            return value.isoformat() if value else ""

        def n(value: int | None) -> str:
            return "" if value is None else str(value)

        return {
            "origin": spec.origin,
            "origin_label": place_label(spec.origin),
            "destination": spec.destination,
            "destination_label": place_label(spec.destination),
            "trip_type": spec.trip_type,
            "date_mode": spec.date_mode,
            "depart_date": d(spec.depart_date),
            "return_date": d(spec.return_date),
            "window_start": d(spec.window_start),
            "window_end": d(spec.window_end),
            "min_trip_days": n(spec.min_trip_days),
            "max_trip_days": n(spec.max_trip_days),
            "max_stops": n(spec.max_stops),
            "budget": (
                str(minor_to_major_int(spec.budget_amount_minor, spec.currency))
                if spec.budget_amount_minor
                else ""
            ),
            "name": spec.name,
            "notify_on_new_low": spec.notify_on_new_low,
            "adults": spec.adults,
            "children": spec.children,
            "cabin": spec.cabin,
            "airlines": list(spec.airlines),
            "dep_hour_from": spec.dep_hour_from,
            "dep_hour_to": spec.dep_hour_to,
            "depart_weekdays": list(spec.depart_weekdays),
        }

    @staticmethod
    def form_options(values: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Choices for the form: airline checkboxes in table order, cabins in order.

        A stored code that is no longer in the table is still listed (checked) so an
        edit keeps it unless the user unticks it (Decision 6 exemption).
        """
        options = [
            {"code": a.code, "zh_name": a.zh_name, "display_name": a.display_name} for a in AIRLINES
        ]
        stored = values.get("airlines", []) if values else []
        for code in stored:
            if lookup_airline(code) is None:
                options.append({"code": code, "zh_name": code, "display_name": code})
        return {
            "airline_options": options,
            "cabin_options": [{"value": c, "label": cabin_label(c)} for c in CABINS],
            # Departure weekdays, value 0 = Monday (date.weekday(); FD-10).
            "weekday_options": [
                {"value": day, "label": label} for day, label in enumerate(WEEKDAY_OPTION_LABELS)
            ],
        }

    def detail_page(self, watch_id: int) -> dict[str, Any] | None:
        watch = self._repo.get_watch(watch_id)
        if watch is None:
            return None
        spec = watch.spec
        now = self._clock()
        settings = self._settings.current()
        stale_hours = settings.stale_after_hours

        current_obs = self._repo.observations_for_watch(watch.id, revision=watch.revision)
        latest = latest_per_pair(current_obs)
        # Live, watch currency, not departed: the same ranking as /watch (FD-7 R1).
        priced = cheapest_pairs(
            current_obs, revision=watch.revision, currency=spec.currency, today=taipei_date(now)
        )
        top = [self._price_row(watch, o, now, stale_hours) for o in priced[:TOP_N]]
        # FD-9 F2: prices were found, but every one has departed (not "no price yet").
        today = taipei_date(now)
        # Main card = the snapshot minimum, which is also top[0] (same tie-break).
        snapshot = Snapshot.build(
            current_obs, revision=watch.revision, currency=spec.currency, today=today
        )
        all_departed = (
            bool(current_obs) and not top and all(o.depart_date < today for o in current_obs)
        )

        runs = self._repo.scan_runs_for_watch(watch.id, limit=TREND_POINTS)
        trend = self._trend(current_obs, runs, watch.revision)
        distribution, weekdays = self._distribution(watch, list(latest.values()), now, stale_hours)
        recent_prices = [self._price_row(watch, o, now, stale_hours) for o in current_obs[:30]]
        old = [
            self._price_row(watch, o, now, stale_hours, with_flight=False)
            for o in self._repo.old_revision_observations(watch.id, watch.revision)
        ]
        last_run = next((r for r in runs if r.finished_at is not None), None)
        shown = [*top, *recent_prices, *old]
        source_note = source_page_note((r["source_key"], r["kind_key"]) for r in shown)
        if source_note is not None:
            for row in shown:
                row["source_text"] = None
        budget = (
            format_money(spec.budget_amount_minor, spec.currency)
            if spec.budget_amount_minor
            else "未設定"
        )
        return {
            "watch": {
                "id": watch.id,
                "name": spec.name,
                "route": route_label(spec.origin, spec.destination),
                **route_view(spec),
                "trip": TRIP_TYPE_LABELS[spec.trip_type],
                # FD-22 D#24 on the detail page too: only one adult in economy drops the line.
                "pax_default": (
                    spec.adults == 1 and spec.children == 0 and spec.cabin == "economy"
                ),
                "date_mode": "固定日期" if spec.date_mode == "fixed" else "彈性窗",
                "dates": dates_text(spec),
                "depart_date": spec.depart_date.isoformat() if spec.depart_date else None,
                "return_date": spec.return_date.isoformat() if spec.return_date else None,
                "window_start": spec.window_start.isoformat() if spec.window_start else None,
                "window_end": spec.window_end.isoformat() if spec.window_end else None,
                "min_trip_days": spec.min_trip_days,
                "max_trip_days": spec.max_trip_days,
                "stay_label": stay_label(spec),
                # FD-10: "週五、週六出發" for a filtered window, None otherwise.
                "weekdays_label": depart_weekdays_label(spec.depart_weekdays),
                "max_stops": "不限"
                if spec.max_stops is None
                else ("僅直飛" if spec.max_stops == 0 else f"最多轉機 {spec.max_stops} 次"),
                "budget": (
                    format_money(spec.budget_amount_minor, spec.currency)
                    if spec.budget_amount_minor
                    else "未設定"
                ),
                **trip_view(spec),
                **self.watch_booking(watch),
                "settings_summary": watch_settings_summary(
                    origin=spec.origin,
                    destination=spec.destination,
                    trip_type=spec.trip_type,
                    dates=dates_text(spec),
                    budget=budget,
                    budget_note=(
                        web_price_note(spec.adults, spec.children)
                        if spec.budget_amount_minor
                        else None
                    ),
                ),
                "notify_on_new_low": spec.notify_on_new_low,
                "status": watch.status,
                "status_label": STATUS_LABELS[watch.status],
                "enabled": watch.status in ("active", "stale"),
                "revision": watch.revision,
                "last_scanned": format_taipei(watch.last_scanned_at) or None,
                "consecutive_failed_scans": watch.consecutive_failed_scans,
                "link": self.watch_link(watch),
            },
            "has_prices": bool(current_obs),
            "top": top,
            "best": top[0] if top else None,
            "coverage_label": coverage_label(len(priced), spec, taipei_date(now)),
            # For the decorative coverage bar (same numbers as the label).
            "coverage_counts": coverage_counts(len(priced), spec, taipei_date(now)),
            "is_round_trip": spec.trip_type == "round_trip",
            # Round-trip amounts and labels can still sit in the folded record table when
            # no price ranks (other currency, all departed); the note stays visible (FD-16).
            "round_trip_note_without_card": (
                spec.trip_type == "round_trip" and bool(current_obs) and not top
            ),
            "best_delta": delta_view(snapshot.delta_since_previous_run()) if top else None,
            "top_explain": top_explain(stale_hours),
            "source_note": source_note,
            "manual_check": snapshot.cheapest is None
            and last_run is not None
            and hit_no_embedded(last_run.query_results),
            "top_empty_note": DETAIL_ALL_DEPARTED if all_departed else None,
            "trend": trend,
            "distribution": distribution,
            # FD-22 #42: one visible fetch-time range above the grid replaces the per-cell time.
            "distribution_fetched_label": (
                fetched_range_label(
                    min(d["fetched_at"] for d in distribution),
                    max(d["fetched_at"] for d in distribution),
                    now,
                )
                if distribution
                else None
            ),
            "weekdays": weekdays,
            "recent_prices": recent_prices,
            "old_prices": old,
            "last_run": self._run_view(last_run, has_filters(spec)) if last_run else None,
            "runs": [self._run_summary(r) for r in runs[:10]],
            "stale_hours": stale_hours,
            "disclaimer": DISCLAIMER,
            "retention_note": retention_note(settings.retention_days),
        }

    def _trend(
        self,
        observations: Sequence[ObservationRecord],
        runs: Sequence[ScanRunRecord],
        revision: int,
    ) -> dict[str, Any]:
        by_run: dict[int, int] = {}
        currency = observations[0].currency if observations else "TWD"
        for obs in observations:
            if obs.price_kind != "live" or obs.currency != currency:
                continue
            by_run[obs.scan_run_id] = min(
                by_run.get(obs.scan_run_id, obs.amount_minor), obs.amount_minor
            )
        points = [
            (run.started_at, by_run[run.id])
            for run in sorted(runs, key=lambda r: r.started_at)
            if run.watch_revision == revision and run.id in by_run
        ]
        rows = [
            {"at": format_taipei(at), "amount_text": format_money(amount, currency)}
            for at, amount in points
        ]
        svg_points = ""
        low_text = high_text = ""
        if len(points) >= 2:
            amounts = [a for _, a in points]
            low, high = min(amounts), max(amounts)
            span = max(high - low, 1)
            inner_w = CHART_WIDTH - 2 * CHART_PAD
            inner_h = CHART_HEIGHT - 2 * CHART_PAD
            coords = []
            for index, (_, amount) in enumerate(points):
                x = CHART_PAD + inner_w * index // (len(points) - 1)
                y = CHART_PAD + inner_h * (high - amount) // span
                coords.append(f"{x},{y}")
            svg_points = " ".join(coords)
            low_text = format_money(low, currency)
            high_text = format_money(high, currency)
        return {
            "rows": list(reversed(rows)),
            "svg_points": svg_points,
            "width": CHART_WIDTH,
            "height": CHART_HEIGHT,
            "low_text": low_text,
            "high_text": high_text,
            # FD-22 ruling section 2 (verbatim template); empty without a drawn line.
            "caption": (
                WEB_TEXTS.trend_caption.format(high=high_text, low=low_text) if svg_points else ""
            ),
        }

    def _distribution(
        self,
        watch: Watch,
        latest: Sequence[ObservationRecord],
        now: datetime,
        stale_hours: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        currency = watch.spec.currency
        by_day: dict[date, ObservationRecord] = {}
        for obs in latest:
            if obs.currency != currency:
                continue
            best = by_day.get(obs.depart_date)
            if best is None or obs.amount_minor < best.amount_minor:
                by_day[obs.depart_date] = obs
        if not by_day:
            return [], []
        levels = price_levels([(o.depart_date, o.amount_minor) for o in by_day.values()])
        rows = []
        for day in sorted(by_day):
            obs = by_day[day]
            level = levels[day]
            rows.append(
                {
                    "depart": day.isoformat(),
                    "weekday": weekday_label(day),
                    "amount_text": format_money(obs.amount_minor, obs.currency),
                    "return": obs.return_date.isoformat() if obs.return_date else None,
                    "level": level,
                    "stale": self._is_stale(obs.fetched_at, now, stale_hours),
                    "fetched_text": format_taipei(obs.fetched_at),
                    "fetched_at": obs.fetched_at,
                }
            )
        by_weekday: dict[int, list[int]] = defaultdict(list)
        for obs in by_day.values():
            by_weekday[obs.depart_date.weekday()].append(obs.amount_minor)
        weekdays = [
            {
                "weekday": weekday_label(date(2024, 1, 1) + timedelta(days=wd)),
                "min_text": format_money(min(vals), currency),
                "count": len(vals),
            }
            for wd, vals in sorted(by_weekday.items())
        ]
        return rows, weekdays

    def _run_summary(self, run: ScanRunRecord) -> dict[str, Any]:
        return {
            "id": run.id,
            "started": format_taipei(run.started_at),
            "finished": format_taipei(run.finished_at) if run.finished_at else "執行中",
            "status": SCAN_STATUS_LABELS.get(run.status, run.status),
            "status_key": run.status,
            "trigger": TRIGGER_LABELS.get(run.trigger, run.trigger),
            "queries_used": run.queries_used,
            "sampled": len(run.sampled_pairs),
            "total_pairs": run.total_pairs,
            "limit_reached": run.limit_reached,
            "global_limit_reached": run.global_limit_reached,
            # Chinese labels only (FR-12); error_summary stays in the database and logs.
            "note": run_note(run),
            "old_revision": False,
            "revision": run.watch_revision,
        }

    def _run_view(self, run: ScanRunRecord, filtered: bool = False) -> dict[str, Any]:
        view = self._run_summary(run)
        by_pair = {(r.get("depart"), r.get("return")): r for r in run.query_results}
        pairs = []
        for pair in run.sampled_pairs:
            depart, ret = pair.as_json()
            result = by_pair.get((depart, ret), {})
            status = str(result.get("status", "skipped"))
            amount = result.get("amount_minor")
            currency = result.get("currency")
            pairs.append(
                {
                    "dates": date_range_text(pair.depart, pair.return_date),
                    "dates_weekday": date_range_weekday_text(pair.depart, pair.return_date),
                    "depart": depart,
                    "return": ret,
                    "status": (
                        WEB_TEXTS.manual_check
                        if status == "no_data" and result.get("reason") == NO_EMBEDDED_REASON
                        else NO_MATCH_LABEL
                        if filtered and status == "no_data"
                        else QUERY_STATUS_LABELS.get(status, status)
                    ),
                    "status_key": status,
                    "from_cache": bool(result.get("from_cache")),
                    "source": source_label(str(result["source"])) if result.get("source") else "—",
                    "amount_text": (
                        format_money(int(amount), str(currency))
                        if isinstance(amount, int) and currency
                        else None
                    ),
                    "note": pair_note(result) if result else None,
                }
            )
        view["pairs"] = pairs
        return view

    def scan_status(self, watch_id: int) -> dict[str, Any] | None:
        """Latest scan run of a watch for the "scan now" poller (fixed field whitelist)."""
        if self._repo.get_watch(watch_id) is None:
            return None
        run = self._repo.latest_scan_run_for_watch(watch_id)
        return {
            "watch_id": watch_id,
            "scan_run_id": run.id if run else None,
            "status": run.status if run else None,
            "started_at": to_utc_iso(run.started_at) if run else None,
            "finished_at": to_utc_iso(run.finished_at) if run and run.finished_at else None,
        }

    def notifications_page(self) -> dict[str, Any]:
        rows = []
        watches = {w.id: w for w in self._repo.list_watches()}
        for record in self._repo.list_notifications():
            items = self._repo.notification_items(record.id) if record.kind == "price_alert" else []
            reasons: list[str] = []
            for item in items:
                for reason in item.reasons:
                    label = reason_label(reason, None) if reason != "drop_pct" else "較上次通知下跌"
                    if label not in reasons:
                        reasons.append(label)
            if not reasons and record.rule:
                reasons.append(reason_label(record.rule, None))
            cheapest = items[0] if items else None
            pax_note = None
            watch = watches.get(record.watch_id) if record.watch_id is not None else None
            if cheapest is not None and watch is not None:
                # Only the current revision's party is known; older alerts keep their text.
                if item_key_revision(cheapest.item_key) == watch.revision:
                    pax_note = total_price_note(watch.spec.adults, watch.spec.children)
            rows.append(
                {
                    "created": format_taipei(record.created_at),
                    "sent": format_taipei(record.sent_at) if record.sent_at else None,
                    "watch": record.watch_name or ("（已刪除）" if record.watch_id else "系統"),
                    "watch_id": record.watch_id,
                    "kind": NOTIFICATION_KIND_LABELS.get(record.kind, record.kind),
                    "reasons": "、".join(reasons) or "—",
                    "price": (
                        format_money(cheapest.amount_minor, cheapest.currency) if cheapest else "—"
                    ),
                    "pax_note": pax_note,
                    "item_count": len(items),
                    "status": NOTIFICATION_STATUS_LABELS.get(record.status, record.status),
                    "status_key": record.status,
                    "attempts": record.attempts,
                    "max_attempts": self._max_attempts,
                    "error": record.last_error,
                    "text": record.message_text,
                }
            )
        return {
            "notifications": rows,
            # FD-22 M1: newest first, cut by count only; the rest sits in one folded block.
            "recent_notifications": rows[:NOTIFICATIONS_SHOWN],
            "older_notifications": rows[NOTIFICATIONS_SHOWN:],
        }

    def settings_page(self) -> dict[str, Any]:
        now = self._clock()
        current = self._settings.current()
        defaults = self._settings.defaults
        rules = self._settings.rules
        settings_rows = [
            {
                "key": key,
                "label": rules[key].label,
                "value": getattr(current, key),
                "default": getattr(defaults, key),
                "min": rules[key].minimum,
                "max": rules[key].maximum,
            }
            for key in SETTING_KEYS
        ]
        health_rows = []
        known = {r.source: r for r in self._health.records()}
        for name in self._source_names:
            record = known.get(name)
            state, state_key = describe_source(record)
            health_rows.append(
                {
                    "name": source_label(name),
                    "state": state,
                    "state_key": state_key,
                    "breaker": BREAKER_LABELS.get(record.breaker_state, "—") if record else "—",
                    "failures": record.consecutive_failures if record else 0,
                    "threshold": self._breaker_threshold,
                    "open_until": (
                        format_taipei(record.open_until) if record and record.open_until else None
                    ),
                    "last_success": (
                        format_taipei(record.last_success_at)
                        if record and record.last_success_at
                        else None
                    ),
                    "last_failure": (
                        format_taipei(record.last_failure_at)
                        if record and record.last_failure_at
                        else None
                    ),
                    "last_error": record.last_error if record else None,
                }
            )
        last_run = self._repo.latest_scan_run()
        watches = {w.id: w for w in self._repo.list_watches()}
        usage = []
        for watch_id, run in sorted(self._repo.latest_finished_scan_runs().items()):
            watch = watches.get(watch_id)
            if watch is None:
                continue
            usage.append(
                {
                    "watch": watch.spec.name,
                    "watch_id": watch_id,
                    "started": format_taipei(run.started_at),
                    "queries_used": run.queries_used,
                    "sampled": len(run.sampled_pairs),
                    "total_pairs": run.total_pairs,
                    "limit_reached": run.limit_reached,
                    "global_limit_reached": run.global_limit_reached,
                    "status": SCAN_STATUS_LABELS.get(run.status, run.status),
                }
            )
        next_run = self.hooks.next_run_time()
        return {
            "health": health_rows,
            "last_scan": (
                {
                    "watch": watches[last_run.watch_id].spec.name
                    if last_run.watch_id in watches
                    else "—",
                    "started": format_taipei(last_run.started_at),
                    "finished": (
                        format_taipei(last_run.finished_at) if last_run.finished_at else "執行中"
                    ),
                    "status": SCAN_STATUS_LABELS.get(last_run.status, last_run.status),
                }
                if last_run
                else None
            ),
            "next_run": format_taipei(next_run) if next_run else None,
            "scheduler_running": self.hooks.scheduler_running(),
            "events": [
                {"at": format_taipei(e.at), "kind": e.kind, "detail": e.detail}
                for e in self._repo.recent_events(10)
            ],
            "telegram_configured": self._telegram_configured,
            "autostart": self._autostart_view(),
            "settings": settings_rows,
            "digest_enabled": current.digest_enabled,
            "digest_time": current.digest_time,
            "digest_default_time": defaults.digest_time,
            "usage": usage,
            "hourly_used": self._repo.queries_used_since(now - timedelta(hours=1)),
            "hourly_limit": current.global_hourly_query_limit,
            "no_embedded_summary": self._no_embedded_summary(now),
            "active_exploration": active_exploration_view(self._repo),
            "active_comparison": active_comparison_view(self._repo),
            "telegram_commands_enabled": current.telegram_commands_enabled,
            "vacuum_enabled": current.vacuum_enabled,
            "command_status": self.command_status_view(current.telegram_commands_enabled),
            "maintenance": self.maintenance_view(now),
        }

    def _no_embedded_summary(self, now: datetime) -> dict[str, Any] | None:
        """Health-page ratio hint with its #35 sentence composed here (FD-12)."""
        summary = self._health.no_embedded_summary(now)
        if summary is None:
            return None
        note = health_no_embedded_note(summary["ratio_pct"], summary["count"], summary["total"])
        return {**summary, "note": note}

    def maintenance_view(self, now: datetime) -> dict[str, Any] | None:
        """Health-page data maintenance block (FR-H4); counts are cached (FR-H6)."""
        retention = self.retention
        if retention is None:
            return None
        settings = self._settings.current()
        stats = retention.stats(now)
        last = retention.last_results()
        result = last["result"] or {}
        summary = None
        status = result.get("status")
        if status == "done":
            summary = retention_summary(
                runs=int(result.get("runs", 0)),
                observations=int(result.get("observations", 0)),
                notifications=int(result.get("notifications", 0)),
                other=int(result.get("other", 0)),
                backup_created=bool(result.get("backup_created")),
                duration_ms=int(result.get("duration_ms", 0)),
            )
        elif status == "backup_failed":
            summary = retention_backup_failed(str(result.get("error") or "未知錯誤"))
        elif status == "failed":
            summary = retention_failed(str(result.get("error") or "未知錯誤"))
        backup_label = MAINTENANCE_NEVER
        if last["backup"]:
            when = format_taipei(last["backup_at"]) if last["backup_at"] else ""
            backup_label = f"{when}（{last['backup']}）".strip()
        return {
            "db_size_label": size_label(stats.sizes.main_bytes),
            "wal_size_label": size_label(stats.sizes.wal_bytes),
            "total_size_label": size_label(stats.sizes.total_bytes),
            "table_counts": [
                {"table": MAINTENANCE_TABLE_LABELS.get(name, name), "count": count}
                for name, count in stats.counts
            ],
            "stats_at_label": stats_time_note(format_taipei(stats.at)),
            "last_run_label": format_taipei(last["run_at"])
            if last["run_at"]
            else MAINTENANCE_NEVER,
            "last_run_summary": summary,
            "last_backup_label": backup_label,
            "last_vacuum_label": self._vacuum_label(last),
            "retention_days": settings.retention_days,
            "notification_retention_days": settings.notification_retention_days,
            "keep_runs": settings.retention_keep_runs,
        }

    @staticmethod
    def _vacuum_label(last: Mapping[str, Any]) -> str:
        vacuum = last.get("vacuum") or {}
        done_at = last.get("vacuum_at")
        label = MAINTENANCE_NEVER
        if done_at is not None:
            label = format_taipei(done_at)
            if vacuum.get("status") == "done":
                sizes = vacuum_result_text(
                    size_label(int(vacuum.get("before", 0))),
                    size_label(int(vacuum.get("after", 0))),
                )
                label = f"{label}（{sizes}）"
        status = vacuum.get("status")
        if status == "skipped":
            note = vacuum_skipped_disk(
                size_label(int(vacuum.get("need", 0))), size_label(int(vacuum.get("free", 0)))
            )
            label = f"{label}；最近一次：{note}"
        elif status == "failed":
            label = f"{label}；最近一次：{vacuum_failed(str(vacuum.get('error') or '未知錯誤'))}"
        return label

    def command_status_view(self, commands_enabled: bool) -> dict[str, Any] | None:
        """Health-page row of the Telegram command poller; None hides it."""
        status = self.hooks.command_status()
        if status is None:
            return None
        if status.unavailable is not None:
            state, key = "unconfigured", status.unavailable
        elif status.unauthorized:
            state, key = "stopped", "unauthorized"
        elif not status.started:
            state, key = "stopped", "not_started"
        elif not commands_enabled:
            state, key = "disabled", "disabled"
        else:
            state, key = "running", "running_failing" if status.failing else "running"
        error_label = None
        if status.last_error_at is not None:
            error_label = (
                f"{format_taipei(status.last_error_at)}：{status.last_error or '未知錯誤'}"
            )
        return {
            "state": state,
            "state_key": key,
            "tone": COMMAND_STATE_TONES[key],
            "label": COMMAND_STATE_LABELS[key],
            "last_command_at_label": format_taipei(status.last_command_at) or None,
            "last_error_label": error_label,
            "ignored_count": status.ignored_count,
        }

    def _autostart_view(self) -> dict[str, bool] | None:
        """None hides the row: not Windows, no probe, or the state could not be read."""
        if self._autostart is None:
            return None
        try:
            status = self._autostart.status()
        except Exception:
            return None
        if status is None:
            return None
        return {"registered": status.registered, "points_here": status.points_here}
