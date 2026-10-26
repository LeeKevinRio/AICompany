"""Watch CRUD use cases. Scheduler wiring is injected by the composition root."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from flight_deals.domain.dates import is_expired
from flight_deals.domain.models import Watch, WatchStatus
from flight_deals.domain.timeutil import taipei_date
from flight_deals.domain.validation import validate_watch_input
from flight_deals.ports import Clock
from flight_deals.storage.repository import Repository


def _noop(_watch_id: int) -> None:
    return None


@dataclass
class WatchHooks:
    """Callbacks set by ``app.py`` so services never import the scheduler."""

    changed: Callable[[int], None] = _noop
    deleted: Callable[[int], None] = _noop
    trigger_scan: Callable[[int], None] = _noop


@dataclass(frozen=True)
class WatchResult:
    watch_id: int | None
    errors: dict[str, str]
    message: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


class WatchService:
    def __init__(self, repo: Repository, *, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock
        self.hooks = WatchHooks()

    def create(self, raw: Mapping[str, object]) -> WatchResult:
        now = self._clock()
        outcome = validate_watch_input(raw, taipei_date(now))
        if outcome.spec is None:
            return WatchResult(None, outcome.errors)
        watch_id = self._repo.insert_watch(outcome.spec, now)
        self.hooks.changed(watch_id)
        return WatchResult(watch_id, {})

    def update(self, watch_id: int, raw: Mapping[str, object]) -> WatchResult:
        existing = self._repo.get_watch(watch_id)
        if existing is None:
            return WatchResult(None, {"_": "找不到此監看"})
        now = self._clock()
        today = taipei_date(now)
        outcome = validate_watch_input(raw, today, existing.spec)
        if outcome.spec is None:
            return WatchResult(watch_id, outcome.errors)
        spec = outcome.spec
        shape_changed = spec.search_shape() != existing.spec.search_shape()
        revision = existing.revision + 1 if shape_changed else existing.revision
        status: WatchStatus = existing.status
        if shape_changed and existing.status in ("stale", "expired"):
            status = "active"
        if is_expired(spec, today):
            status = "expired"
        self._repo.update_watch_spec(
            watch_id,
            spec,
            revision=revision,
            status=status,
            reset_progress=shape_changed,
            now=now,
        )
        if shape_changed:
            # Baselines are per revision: old prices must not drive alerts for new settings.
            self._repo.reset_alert_state(watch_id)
        self.hooks.changed(watch_id)
        return WatchResult(watch_id, {})

    def set_enabled(self, watch_id: int, enabled: bool) -> WatchResult:
        watch = self._repo.get_watch(watch_id)
        if watch is None:
            return WatchResult(None, {"_": "找不到此監看"})
        if watch.status == "expired":
            return WatchResult(watch_id, {"_": "此監看日期已全部過期，請先修改日期"})
        target: WatchStatus = "active" if enabled else "paused"
        if enabled and watch.status == "stale":
            target = "stale"
        self._repo.set_watch_status(watch_id, target, self._clock())
        self.hooks.changed(watch_id)
        return WatchResult(watch_id, {})

    def delete(self, watch_id: int) -> bool:
        deleted = self._repo.delete_watch(watch_id)
        if deleted:
            self.hooks.deleted(watch_id)
        return deleted

    def request_scan(self, watch_id: int) -> WatchResult:
        watch = self._repo.get_watch(watch_id)
        if watch is None:
            return WatchResult(None, {"_": "找不到此監看"})
        if watch.status == "paused":
            return WatchResult(watch_id, {"_": "此監看已停用，請先啟用"})
        if watch.status == "expired":
            return WatchResult(watch_id, {"_": "此監看日期已全部過期"})
        self.hooks.trigger_scan(watch_id)
        return WatchResult(watch_id, {}, "已排入立即查價，完成後重新整理頁面即可看到結果")

    def get(self, watch_id: int) -> Watch | None:
        return self._repo.get_watch(watch_id)
