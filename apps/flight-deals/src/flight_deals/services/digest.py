"""Daily digest (ADR-0002 FD-4 Decisions 1, 3, 5, 6; C-32, C-34).

``DigestService.send_if_due`` is the only entry point that sends the daily digest. It
is idempotent and is called from scheduler jobs only (cron, startup catch-up, hourly
check, one-off after a settings change); web request threads never call it. The
``/digest`` command uses ``send_manual`` from its own one-off job (FD-7 Decision 5).
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Literal

from flight_deals.domain.messages import DigestRow, DigestSourceRow, daily_digest_message
from flight_deals.domain.models import SCANNABLE_STATUSES
from flight_deals.domain.rules import digest_key
from flight_deals.domain.timeutil import TAIPEI, taipei_date
from flight_deals.domain.trip_labels import depart_weekdays_label
from flight_deals.ports import Clock
from flight_deals.services.health import HealthService, describe_source
from flight_deals.services.notifications import NotificationService
from flight_deals.services.price_snapshot import Snapshot
from flight_deals.services.settings import EffectiveSettings, SettingsService
from flight_deals.storage.repository import Repository

log = logging.getLogger(__name__)

# Exported for the scheduler, which may only import ``services`` (Decision 1).
DIGEST_ZONE = TAIPEI
FAILED_SCAN_WINDOW = timedelta(hours=24)

DigestOutcome = Literal[
    "disabled", "not_yet", "handled", "retried", "retry_failed", "sent", "failed", "suppressed"
]


def digest_due_at(now: datetime, settings: EffectiveSettings) -> datetime:
    """Today's digest moment (Asia/Taipei) as an aware datetime."""
    hour, minute = settings.digest_hour_minute
    return datetime.combine(taipei_date(now), time(hour, minute), tzinfo=DIGEST_ZONE)


def taipei_midnight(now: datetime) -> datetime:
    return datetime.combine(taipei_date(now), time(0, 0), tzinfo=DIGEST_ZONE)


class DigestService:
    def __init__(
        self,
        repo: Repository,
        settings: SettingsService,
        health: HealthService,
        notifications: NotificationService,
        *,
        source_names: list[str],
        clock: Clock,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._health = health
        self._notifications = notifications
        self._source_names = list(source_names)
        self._clock = clock

    def send_if_due(self, now: datetime | None = None) -> DigestOutcome:
        """Send today's digest once: enabled, past today's time, and no record for today.

        Only today is ever considered; earlier days are not sent late. A failed digest of
        today is re-sent here (and by ``retry_pending``) until the attempt cap.
        """
        now = now or self._clock()
        settings = self._settings.current()
        if not settings.digest_enabled:
            return "disabled"
        if now < digest_due_at(now, settings):
            return "not_yet"
        key = digest_key(taipei_date(now))
        existing = self._repo.get_notification_by_key(key)
        if existing is not None:
            if existing.status in ("pending", "failed") and self._notifications.retry_record(
                existing
            ):
                return "retried"
            return "handled" if existing.status in ("sent", "suppressed") else "retry_failed"
        text = self.compose(now, settings)
        notification_id = self._notifications.send_daily_digest(key, text)
        if notification_id is None:  # another call recorded it first
            return "handled"
        record = self._repo.get_notification(notification_id)
        status = record.status if record else "failed"
        log.info("daily digest %s: %s", key, status)
        if status == "sent":
            return "sent"
        return "suppressed" if status == "suppressed" else "failed"

    def send_manual(self, now: datetime, key: str) -> DigestOutcome:
        """``/digest`` (FD-7 Decision 5): same text as the daily digest, recorded as
        ``manual_digest`` under ``key``; no daily limit, no retry, and the scheduled
        ``digest:<date>`` record is never read or written here."""
        text = self.compose(now)
        notification_id = self._notifications.send_manual_digest(key, text)
        if notification_id is None:
            return "handled"
        record = self._repo.get_notification(notification_id)
        status = record.status if record else "failed"
        if status == "sent":
            return "sent"
        return "suppressed" if status == "suppressed" else "failed"

    def compose(self, now: datetime, settings: EffectiveSettings | None = None) -> str:
        settings = settings or self._settings.current()
        today = taipei_date(now)
        midnight = taipei_midnight(now)
        stale_after = timedelta(hours=settings.stale_after_hours)
        rows: list[DigestRow] = []
        for watch in self._repo.list_watches():
            if watch.status not in SCANNABLE_STATUSES:
                continue
            spec = watch.spec
            snapshot = Snapshot.build(
                self._repo.snapshot_observations_for_watch(
                    watch.id,
                    revision=watch.revision,
                    currency=spec.currency,
                    today=today,
                    midnight=midnight,
                ),
                revision=watch.revision,
                currency=spec.currency,
                today=today,
            )
            cheapest = snapshot.cheapest
            delta = snapshot.delta_since(midnight)
            rows.append(
                DigestRow(
                    name=spec.name,
                    origin=spec.origin,
                    destination=spec.destination,
                    currency=spec.currency,
                    amount_minor=cheapest.amount_minor if cheapest else None,
                    depart_date=cheapest.depart_date if cheapest else None,
                    return_date=cheapest.return_date if cheapest else None,
                    delta_minor=delta.delta_minor if delta else None,
                    data_stale=bool(cheapest and now - cheapest.fetched_at > stale_after),
                    watch_stale=watch.status == "stale",
                    adults=spec.adults,
                    children=spec.children,
                    cabin=spec.cabin,
                    weekdays_label=depart_weekdays_label(spec.depart_weekdays),
                )
            )
        known = {r.source: r for r in self._health.records()}
        sources = []
        for name in self._source_names:
            record = known.get(name)
            label, _key = describe_source(record)
            sources.append(
                DigestSourceRow(name, label, record.breaker_state if record else "closed")
            )
        last_run = self._repo.latest_scan_run()
        return daily_digest_message(
            day=today,
            sources=sources,
            last_scan_at=last_run.started_at if last_run else None,
            failed_scans_24h=self._repo.count_failed_scan_runs_since(now - FAILED_SCAN_WINDOW),
            rows=rows,
            stale_after_hours=settings.stale_after_hours,
        )
