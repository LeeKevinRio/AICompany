"""Global runtime settings: config defaults overridden by ``app_setting`` rows (FR-E4).

Integer settings and the daily digest settings use separate key lists (ADR-0002 FD-4
Decision 2). A stored value that no longer validates falls back to the default.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from flight_deals.domain.validation import (
    DIGEST_ENABLED_KEY,
    DIGEST_SETTING_KEYS,
    DIGEST_TIME_KEY,
    SettingRule,
    parse_digest_enabled,
    parse_digest_time,
    setting_rules,
    validate_digest_settings,
    validate_settings,
)
from flight_deals.ports import Clock
from flight_deals.storage.repository import Repository


@dataclass(frozen=True)
class EffectiveSettings:
    scan_interval_minutes: int
    max_pairs_per_scan: int
    drop_threshold_bp: int
    stale_after_hours: int
    global_hourly_query_limit: int
    digest_enabled: bool = True
    digest_time: str = "08:00"
    exploration_reserve_for_scans: int = 12

    @property
    def digest_hour_minute(self) -> tuple[int, int]:
        hour, minute = self.digest_time.split(":")
        return int(hour), int(minute)


# Integer settings shown as numeric rows on the settings page.
SETTING_KEYS = (
    "scan_interval_minutes",
    "max_pairs_per_scan",
    "drop_threshold_bp",
    "stale_after_hours",
    "global_hourly_query_limit",
    "exploration_reserve_for_scans",
)
__all__ = ["DIGEST_SETTING_KEYS", "SETTING_KEYS", "EffectiveSettings", "SettingsService"]


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
        enabled = parse_digest_enabled(stored.get(DIGEST_ENABLED_KEY))
        digest_time = parse_digest_time(stored.get(DIGEST_TIME_KEY))
        return EffectiveSettings(
            **values,
            digest_enabled=self._defaults.digest_enabled if enabled is None else enabled,
            digest_time=digest_time or self._defaults.digest_time,
        )

    def update(self, raw: Mapping[str, object]) -> dict[str, str]:
        """Validate and persist; returns field errors (empty dict on success).

        Listeners run on the caller's thread (a web request); they may only schedule work.
        """
        values, errors = validate_settings(raw, self._rules)
        digest_values, digest_errors = validate_digest_settings(
            {k: v for k, v in raw.items() if k in DIGEST_SETTING_KEYS}
        )
        errors.update(digest_errors)
        if errors:
            return errors
        before = self.current()
        stored = {k: str(v) for k, v in values.items()} | digest_values
        if stored:
            self._repo.save_settings(stored, self._clock())
        after = self.current()
        if after != before:
            for listener in self.listeners:
                listener(before, after)
        return {}
