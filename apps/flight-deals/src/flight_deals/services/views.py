"""Read models for the web layer: display-ready values, already formatted (zh-TW)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from flight_deals.domain.airports import place_label, route_label
from flight_deals.domain.currency import format_money, minor_to_major_int
from flight_deals.domain.dates import first_pair
from flight_deals.domain.links import google_flights_url
from flight_deals.domain.messages import (
    DISCLAIMER,
    PRICE_KIND_LABELS,
    SAMPLED_ONLY_NOTE,
    STATUS_LABELS,
    TRIP_TYPE_LABELS,
    date_range_text,
    reason_label,
    source_label,
)
from flight_deals.domain.models import DatePair, Watch, WatchSpec
from flight_deals.domain.timeutil import format_taipei, taipei_date, to_utc_iso, weekday_label
from flight_deals.ports import Clock
from flight_deals.services.health import HealthService
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
}
BREAKER_LABELS = {
    "closed": "關閉（正常查詢）",
    "open": "開啟（暫停查詢）",
    "half_open": "半開（試查中）",
}


@dataclass
class ViewHooks:
    next_run_time: Callable[[], datetime | None] = lambda: None
    scheduler_running: Callable[[], bool] = lambda: False


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


def try_note(try_info: Mapping[str, Any]) -> str | None:
    """Explanation column for one query try: adapter error plus skipped-itinerary notes."""
    error = try_info.get("error")
    parts = [str(error)] if error else []
    parts.extend(parse_notes(try_info))
    return "；".join(parts) or None


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
        return f"彈性 {start} ～ {end}，旅程 {spec.min_trip_days}–{spec.max_trip_days} 天"
    return f"彈性出發 {start} ～ {end}"


def _pair_key(o: ObservationRecord) -> DatePair:
    return DatePair(o.depart_date, o.return_date)


def latest_per_pair(observations: Sequence[ObservationRecord]) -> dict[DatePair, ObservationRecord]:
    latest: dict[DatePair, ObservationRecord] = {}
    for obs in observations:
        key = _pair_key(obs)
        current = latest.get(key)
        if current is None or (obs.fetched_at, obs.id) > (current.fetched_at, current.id):
            latest[key] = obs
    return latest


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
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._health = health
        self._source_names = list(source_names)
        self._telegram_configured = telegram_configured
        self._max_attempts = notification_max_attempts
        self._breaker_threshold = breaker_threshold
        self._clock = clock
        self.hooks = ViewHooks()

    # ---- shared page context -------------------------------------------------

    def base_context(self) -> dict[str, Any]:
        """Values every page needs: footer disclaimer and today's Asia/Taipei date."""
        return {
            "disclaimer": DISCLAIMER,
            "sampled_only_note": SAMPLED_ONLY_NOTE,
            "today": taipei_date(self._clock()).isoformat(),
        }

    # ---- helpers -------------------------------------------------------------

    def _is_stale(self, fetched_at: datetime, now: datetime, hours: int) -> bool:
        return now - fetched_at > timedelta(hours=hours)

    def _price_row(
        self, watch: Watch, obs: ObservationRecord, now: datetime, stale_hours: int
    ) -> dict[str, Any]:
        spec = watch.spec
        return {
            "dates": date_range_text(obs.depart_date, obs.return_date),
            "depart": obs.depart_date.isoformat(),
            "return": obs.return_date.isoformat() if obs.return_date else None,
            "weekday": weekday_label(obs.depart_date),
            "amount_text": format_money(obs.amount_minor, obs.currency),
            "amount_minor": obs.amount_minor,
            "carrier": obs.carrier or "未提供",
            "stops": "直飛" if obs.stops == 0 else (f"轉機 {obs.stops} 次" if obs.stops else "—"),
            "fetched_text": format_taipei(obs.fetched_at),
            "stale": self._is_stale(obs.fetched_at, now, stale_hours),
            "source": source_label(obs.source),
            "kind": PRICE_KIND_LABELS.get(obs.price_kind, obs.price_kind),
            "data_time_unknown": obs.price_kind == "cached" and obs.as_of_basis == "fetch_time",
            "currency_mismatch": obs.currency != spec.currency,
            "link": google_flights_url(
                spec.origin, spec.destination, obs.depart_date, obs.return_date
            ),
            "revision": obs.watch_revision,
        }

    def _current_latest(self, watch: Watch) -> dict[DatePair, ObservationRecord]:
        observations = self._repo.observations_for_watch(watch.id, revision=watch.revision)
        live = [o for o in observations if o.price_kind == "live"]
        return latest_per_pair(live)

    def watch_link(self, watch: Watch) -> str | None:
        spec = watch.spec
        # Constant time: never expand the whole window just to build one link.
        first = first_pair(spec, taipei_date(self._clock()))
        if first is None and spec.depart_date:
            first = DatePair(spec.depart_date, spec.return_date)
        elif first is None and spec.window_start:
            first = DatePair(spec.window_start, None)
        if first is None:
            return None
        return google_flights_url(spec.origin, spec.destination, first.depart, first.return_date)

    # ---- pages ---------------------------------------------------------------

    def list_page(self) -> dict[str, Any]:
        rows = []
        for watch in self._repo.list_watches():
            spec = watch.spec
            latest = self._current_latest(watch)
            matching = [o for o in latest.values() if o.currency == spec.currency]
            cheapest = min(matching, key=lambda o: o.amount_minor, default=None)
            rows.append(
                {
                    "id": watch.id,
                    "name": spec.name,
                    "route": route_label(spec.origin, spec.destination),
                    "trip": TRIP_TYPE_LABELS[spec.trip_type],
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
                    "min_price": (
                        format_money(cheapest.amount_minor, cheapest.currency) if cheapest else None
                    ),
                    "min_price_dates": (
                        date_range_text(cheapest.depart_date, cheapest.return_date)
                        if cheapest
                        else None
                    ),
                    "last_scanned": format_taipei(watch.last_scanned_at) or None,
                    "link": self.watch_link(watch),
                }
            )
        return {"watches": rows, "disclaimer": DISCLAIMER}

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
        priced = sorted(latest.values(), key=lambda o: (o.amount_minor, o.depart_date))
        top = [self._price_row(watch, o, now, stale_hours) for o in priced[:TOP_N]]

        runs = self._repo.scan_runs_for_watch(watch.id, limit=TREND_POINTS)
        trend = self._trend(current_obs, runs, watch.revision)
        distribution, weekdays = self._distribution(watch, list(latest.values()), now, stale_hours)
        recent_prices = [self._price_row(watch, o, now, stale_hours) for o in current_obs[:30]]
        old = [
            self._price_row(watch, o, now, stale_hours)
            for o in self._repo.old_revision_observations(watch.id, watch.revision)
        ]
        last_run = next((r for r in runs if r.finished_at is not None), None)
        return {
            "watch": {
                "id": watch.id,
                "name": spec.name,
                "route": route_label(spec.origin, spec.destination),
                "trip": TRIP_TYPE_LABELS[spec.trip_type],
                "date_mode": "固定日期" if spec.date_mode == "fixed" else "彈性窗",
                "dates": dates_text(spec),
                "depart_date": spec.depart_date.isoformat() if spec.depart_date else None,
                "return_date": spec.return_date.isoformat() if spec.return_date else None,
                "window_start": spec.window_start.isoformat() if spec.window_start else None,
                "window_end": spec.window_end.isoformat() if spec.window_end else None,
                "min_trip_days": spec.min_trip_days,
                "max_trip_days": spec.max_trip_days,
                "max_stops": "不限"
                if spec.max_stops is None
                else ("僅直飛" if spec.max_stops == 0 else f"最多轉機 {spec.max_stops} 次"),
                "budget": (
                    format_money(spec.budget_amount_minor, spec.currency)
                    if spec.budget_amount_minor
                    else "未設定"
                ),
                "cabin": "經濟艙",
                "adults": 1,
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
            "trend": trend,
            "distribution": distribution,
            "weekdays": weekdays,
            "recent_prices": recent_prices,
            "old_prices": old,
            "last_run": self._run_view(last_run) if last_run else None,
            "runs": [self._run_summary(r) for r in runs[:10]],
            "stale_hours": stale_hours,
            "disclaimer": DISCLAIMER,
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
        ordered = sorted(by_day.values(), key=lambda o: o.amount_minor)
        third = max(len(ordered) // 3, 1)
        cheap = {o.depart_date for o in ordered[:third]}
        pricey = {o.depart_date for o in ordered[-third:]} if len(ordered) >= 3 else set()
        rows = []
        for day in sorted(by_day):
            obs = by_day[day]
            level = "cheap" if day in cheap else ("pricey" if day in pricey else "mid")
            rows.append(
                {
                    "depart": day.isoformat(),
                    "weekday": weekday_label(day),
                    "amount_text": format_money(obs.amount_minor, obs.currency),
                    "return": obs.return_date.isoformat() if obs.return_date else None,
                    "level": level,
                    "stale": self._is_stale(obs.fetched_at, now, stale_hours),
                    "fetched_text": format_taipei(obs.fetched_at),
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
            "error": run.error_summary,
            "old_revision": False,
            "revision": run.watch_revision,
        }

    def _run_view(self, run: ScanRunRecord) -> dict[str, Any]:
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
                    "depart": depart,
                    "return": ret,
                    "status": QUERY_STATUS_LABELS.get(status, status),
                    "status_key": status,
                    "reason": SKIP_REASON_LABELS.get(str(result.get("reason")), None),
                    "from_cache": bool(result.get("from_cache")),
                    "source": source_label(str(result["source"])) if result.get("source") else "—",
                    "amount_text": (
                        format_money(int(amount), str(currency))
                        if isinstance(amount, int) and currency
                        else None
                    ),
                    "error": try_note((result.get("tries") or [{}])[-1]) if result else None,
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
                    "item_count": len(items),
                    "status": NOTIFICATION_STATUS_LABELS.get(record.status, record.status),
                    "status_key": record.status,
                    "attempts": record.attempts,
                    "max_attempts": self._max_attempts,
                    "error": record.last_error,
                    "text": record.message_text,
                }
            )
        return {"notifications": rows}

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
            if record is None or (
                record.last_success_at is None and record.last_failure_at is None
            ):
                state, state_key = "未知（尚未查詢）", "unknown"
            elif record.breaker_state != "closed":
                state, state_key = "異常", "down"
            elif record.consecutive_failures > 0:
                state, state_key = f"正常（最近連續失敗 {record.consecutive_failures} 次）", "warn"
            else:
                state, state_key = "正常", "ok"
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
            "settings": settings_rows,
            "usage": usage,
            "hourly_used": self._repo.queries_used_since(now - timedelta(hours=1)),
            "hourly_limit": current.global_hourly_query_limit,
        }
