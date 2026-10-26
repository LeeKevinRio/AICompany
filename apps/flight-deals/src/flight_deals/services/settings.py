"""Global runtime settings: config defaults overridden by ``app_setting`` rows (FR-E4)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields

from flight_deals.domain.validation import SettingRule, setting_rules, validate_settings
from flight_deals.ports import Clock
from flight_deals.storage.repository import Repository


@dataclass(frozen=True)
class EffectiveSettings:
    scan_interval_minutes: int
    max_pairs_per_scan: int
    drop_threshold_bp: int
    stale_after_hours: int
    global_hourly_query_limit: int


SETTING_KEYS = tuple(f.name for f in fields(EffectiveSettings))


class SettingsService:
    def __init__(
        self,
        repo: Repository,
        defaults: EffectiveSettings,
        *,
        min_scan_interval_minutes: int,
        clock: Clock,
    ) -> None:
        self._repo = repo
        self._defaults = defaults
        self._rules = setting_rules(min_scan_interval_minutes)
        self._clock = clock
        self.listeners: list[Callable[[EffectiveSettings, EffectiveSettings], None]] = []

    @property
    def rules(self) -> Mapping[str, SettingRule]:
        return self._rules

    @property
    def defaults(self) -> EffectiveSettings:
        return self._defaults

    def current(self) -> EffectiveSettings:
        stored = self._repo.get_settings()
        values: dict[str, int] = {}
        for key in SETTING_KEYS:
            default = int(getattr(self._defaults, key))
            raw = stored.get(key)
            try:
                value = int(raw) if raw is not None else default
            except ValueError:
                value = default
            rule = self._rules[key]
            values[key] = value if rule.minimum <= value <= rule.maximum else default
        return EffectiveSettings(**values)

    def update(self, raw: Mapping[str, object]) -> dict[str, str]:
        """Validate and persist; returns field errors (empty dict on success)."""
        values, errors = validate_settings(raw, self._rules)
        if errors:
            return errors
        before = self.current()
        if values:
            self._repo.save_settings({k: str(v) for k, v in values.items()}, self._clock())
        after = self.current()
        if after != before:
            for listener in self.listeners:
                listener(before, after)
        return {}
