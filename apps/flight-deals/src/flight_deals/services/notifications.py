"""Notification flow: persist first, then deliver; retries are bounded (FR-C7)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from flight_deals.domain.messages import (
    command_record_text,
    ops_failure_message,
    price_alert_message,
    telegram_test_message,
)
from flight_deals.domain.models import (
    SEND_ONCE_KINDS,
    DatePair,
    FlightSearch,
    PriceKind,
    Watch,
    search_for,
)
from flight_deals.domain.rules import (
    TriggeredItem,
    digest_key,
    ops_failure_key,
    price_message_key,
    primary_reason,
    telegram_test_key,
)
from flight_deals.domain.timeutil import taipei_date
from flight_deals.ports import BookingLinkBuilder, Clock, Notifier, Redactor, SendResult
from flight_deals.storage.repository import (
    AlertStateRecord,
    NotificationItemRecord,
    NotificationRecord,
    Repository,
)

log = logging.getLogger(__name__)

NOT_CONFIGURED = "Telegram 未設定，訊息未送出"


def safe_booking_url(builder: BookingLinkBuilder | None, search: FlightSearch) -> str | None:
    """Exact booking link, or None so callers fall back to the text search (Decision 7)."""
    if builder is None:
        return None
    try:
        return builder.url(search)
    except Exception:
        log.warning("booking link could not be built; using the text search link")
        return None


class NotificationService:
    def __init__(
        self,
        repo: Repository,
        notifier: Notifier,
        *,
        max_attempts: int,
        clock: Clock,
        redactor: Redactor,
        link_builder: BookingLinkBuilder | None = None,
    ) -> None:
        self._repo = repo
        self._notifier = notifier
        self._max_attempts = max_attempts
        self._clock = clock
        self._redact = redactor
        self._links = link_builder

    @property
    def configured(self) -> bool:
        return self._notifier.is_configured()

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def send_price_alert(
        self, watch: Watch, price_kind: PriceKind, items: Sequence[TriggeredItem]
    ) -> int | None:
        """Create and deliver one merged alert; returns the notification id (None = dedupe)."""
        if not items:
            return None
        spec = watch.spec
        links = [
            safe_booking_url(
                self._links,
                search_for(
                    spec,
                    DatePair(i.candidate.depart_date, i.candidate.return_date),
                    i.candidate.currency,
                ),
            )
            for i in items
        ]
        text = price_alert_message(
            watch_name=spec.name,
            origin=spec.origin,
            destination=spec.destination,
            trip_type=spec.trip_type,
            items=items,
            links=links,
            adults=spec.adults,
            children=spec.children,
            cabin=spec.cabin,
            airlines=spec.airlines,
            dep_hour_from=spec.dep_hour_from,
            dep_hour_to=spec.dep_hour_to,
        )
        notification_id = self._repo.insert_notification(
            watch_id=watch.id,
            kind="price_alert",
            rule=primary_reason(items[0]),
            price_kind=price_kind,
            observation_id=items[0].candidate.observation_id,
            channel=self._notifier.channel,
            dedupe_key=price_message_key(watch.id, watch.revision, price_kind, items),
            message_text=text,
            created_at=self._clock(),
            items=[
                NotificationItemRecord(
                    item_key=i.item_key,
                    depart_date=i.candidate.depart_date,
                    return_date=i.candidate.return_date,
                    amount_minor=i.candidate.amount_minor,
                    currency=i.candidate.currency,
                    reasons=i.reasons,
                    carrier=i.candidate.carrier,
                    fetched_at=i.candidate.fetched_at,
                )
                for i in items
            ],
        )
        if notification_id is None:
            return None
        self._deliver(notification_id, 0, text)
        return notification_id

    def send_ops_failure(self, source: str, error: str | None) -> int | None:
        now = self._clock()
        text = ops_failure_message(source=source, error=error, now=now)
        notification_id = self._repo.insert_notification(
            watch_id=None,
            kind="ops_source_failure",
            rule=None,
            price_kind=None,
            observation_id=None,
            channel=self._notifier.channel,
            dedupe_key=ops_failure_key(source, now),
            message_text=self._redact(text),
            created_at=now,
        )
        if notification_id is None:
            log.info("ops alert for %s already recorded today; not repeating", source)
            return None
        self._deliver(notification_id, 0, self._redact(text))
        return notification_id

    def send_test(self) -> SendResult:
        now = self._clock()
        text = telegram_test_message(now)
        notification_id = self._repo.insert_notification(
            watch_id=None,
            kind="test",
            rule=None,
            price_kind=None,
            observation_id=None,
            channel=self._notifier.channel,
            dedupe_key=telegram_test_key(now),
            message_text=text,
            created_at=now,
        )
        result = self._notifier.send(text)
        error = self._redact(result.error) if result.error else None
        if notification_id is not None:
            self._repo.update_notification(
                notification_id,
                status="sent" if result.ok else "failed",
                attempts=1,
                sent_at=self._clock() if result.ok else None,
                last_error=error,
            )
        return SendResult(ok=result.ok, error=error)

    def send_daily_digest(self, key: str, text: str) -> int | None:
        """Record and deliver today's digest; None when ``key`` already exists (C-32).

        Not configured -> ``suppressed`` (handled for the day, never retried).
        """
        notification_id = self._repo.insert_notification(
            watch_id=None,
            kind="daily_digest",
            rule=None,
            price_kind=None,
            observation_id=None,
            channel=self._notifier.channel,
            dedupe_key=key,
            message_text=text,
            created_at=self._clock(),
        )
        if notification_id is None:
            return None
        self._deliver(notification_id, 0, text)
        return notification_id

    def send_manual_digest(self, key: str, text: str) -> int | None:
        """``/digest``: kind ``manual_digest``, delivered once, never retried; it never
        touches the ``digest:<date>`` key of the scheduled digest (FD-7 Decision 5)."""
        notification_id = self._repo.insert_notification(
            watch_id=None,
            kind="manual_digest",
            rule=None,
            price_kind=None,
            observation_id=None,
            channel=self._notifier.channel,
            dedupe_key=key,
            message_text=text,
            created_at=self._clock(),
        )
        if notification_id is None:
            return None
        self._deliver(notification_id, 0, text)
        return notification_id

    # ---- Telegram commands (FD-7 Decision 2: claim, execute, reply once) ----------

    def claim_command(self, key: str, command_text: str, watch_id: int | None = None) -> int | None:
        """Record a command before it runs; None means this update was already handled."""
        return self._repo.insert_notification(
            watch_id=watch_id,
            kind="command",
            rule=None,
            price_kind=None,
            observation_id=None,
            channel=self._notifier.channel,
            dedupe_key=key,
            message_text=self._redact(command_text),
            created_at=self._clock(),
        )

    def finish_command(self, notification_id: int, command_text: str, reply: str) -> bool:
        """Store "command -> reply" and send the reply once (a failure is only recorded)."""
        text = self._redact(reply)
        self._repo.update_notification_text(
            notification_id, command_record_text(self._redact(command_text), text)
        )
        return self._deliver(notification_id, 0, text)

    def send_command_message(
        self, key: str, label: str, text: str, watch_id: int | None = None
    ) -> int | None:
        """A bot message not answering one update directly (backlog note, ``/scan``
        result); ``label`` says what it relates to. None when ``key`` already exists."""
        reply = self._redact(text)
        notification_id = self._repo.insert_notification(
            watch_id=watch_id,
            kind="command",
            rule=None,
            price_kind=None,
            observation_id=None,
            channel=self._notifier.channel,
            dedupe_key=key,
            message_text=command_record_text(self._redact(label), reply),
            created_at=self._clock(),
        )
        if notification_id is None:
            return None
        self._deliver(notification_id, 0, reply)
        return notification_id

    def retry_record(self, record: NotificationRecord) -> bool:
        """Re-send one pending/failed notification if it is still eligible."""
        if not self._retry_allowed(record):
            return False
        return self._deliver(record.id, record.attempts, record.message_text)

    def retry_pending(self) -> int:
        """Re-send failed/pending alerts still under the attempt cap; returns sent count."""
        sent = 0
        for record in self._repo.retryable_notifications(self._max_attempts):
            if self.retry_record(record):
                sent += 1
        return sent

    def _retry_allowed(self, record: NotificationRecord) -> bool:
        if record.status not in ("pending", "failed") or record.attempts >= self._max_attempts:
            return False
        if record.kind in SEND_ONCE_KINDS:
            return False
        if record.kind == "daily_digest":
            # A digest is only worth sending on its own Asia/Taipei day (Decision 3).
            return record.dedupe_key == digest_key(taipei_date(self._clock()))
        return True

    def _deliver(self, notification_id: int, previous_attempts: int, text: str) -> bool:
        if not self._notifier.is_configured():
            self._repo.update_notification(
                notification_id,
                status="suppressed",
                attempts=previous_attempts,
                sent_at=None,
                last_error=NOT_CONFIGURED,
            )
            return False
        result = self._notifier.send(text)
        attempts = previous_attempts + 1
        if result.ok:
            now = self._clock()
            self._repo.update_notification(
                notification_id, status="sent", attempts=attempts, sent_at=now, last_error=None
            )
            record = self._repo.get_notification(notification_id)
            if record is not None:
                self._after_sent(record)
            return True
        error = self._redact(result.error or "unknown error")[:500]
        log.warning("notification %s failed (attempt %d): %s", notification_id, attempts, error)
        self._repo.update_notification(
            notification_id, status="failed", attempts=attempts, sent_at=None, last_error=error
        )
        return False

    def _after_sent(self, record: NotificationRecord) -> None:
        """Only a delivered alert moves the alert baseline (never a failed one)."""
        if record.kind != "price_alert" or record.watch_id is None or not record.price_kind:
            return
        items = self._repo.notification_items(record.id)
        if not items:
            return
        state = self._repo.get_alert_state(record.watch_id, record.price_kind)
        below_budget = any("below_budget" in i.reasons for i in items)
        self._repo.save_alert_state(
            record.watch_id,
            record.price_kind,
            AlertStateRecord(
                last_notified_amount_minor=min(i.amount_minor for i in items),
                last_notified_at=record.sent_at or self._clock(),
                armed=False if below_budget else state.armed,
            ),
        )
