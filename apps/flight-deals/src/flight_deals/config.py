"""Environment-driven configuration. Stdlib only.

Secrets come only from environment variables or an untracked ``.env`` file.
Tunable defaults below are this project's own starting values, not external limits.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_DIR / "data" / "flight-deals.db"
BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8795

KNOWN_SOURCES = ("google_flights", "fixture")
TEST_ONLY_SOURCES = frozenset({"fixture"})

ENV_TELEGRAM_TOKEN = "FLIGHT_DEALS_TELEGRAM_BOT_TOKEN"
ENV_TELEGRAM_CHAT_ID = "FLIGHT_DEALS_TELEGRAM_CHAT_ID"
ENV_DB_PATH = "FLIGHT_DEALS_DB_PATH"
ENV_SOURCES = "FLIGHT_DEALS_SOURCES"
ENV_PORT = "FLIGHT_DEALS_PORT"


class ConfigError(ValueError):
    """Raised when configuration is invalid or unsafe to start with."""


@dataclass(frozen=True)
class Tunables:
    """Defaults for values that ``app_setting`` rows may override at runtime."""

    scan_interval_minutes: int = 360
    max_pairs_per_scan: int = 12
    drop_threshold_bp: int = 500
    stale_after_hours: int = 24
    global_hourly_query_limit: int = 60


@dataclass(frozen=True)
class Limits:
    """Fixed operational parameters (not editable from the web UI)."""

    min_scan_interval_minutes: int = 30
    alert_max_items: int = 5
    breaker_failure_threshold: int = 3
    breaker_cooldown_minutes: int = 30
    watch_stale_after_failed_scans: int = 3
    notification_max_attempts: int = 3
    throttle_min_seconds: float = 1.5
    throttle_jitter_seconds: float = 1.5
    source_timeout_seconds: float = 20.0
    source_max_attempts: int = 2
    backoff_base_seconds: float = 2.0
    cache_ttl_seconds: float = 1800.0
    startup_stagger_seconds: int = 20
    new_watch_delay_seconds: int = 10
    telegram_timeout_seconds: float = 5.0


@dataclass(frozen=True)
class Config:
    db_path: Path = DEFAULT_DB_PATH
    sources: tuple[str, ...] = ("google_flights",)
    port: int = DEFAULT_PORT
    host: str = BIND_HOST
    telegram_bot_token: str | None = field(default=None, repr=False)
    telegram_chat_id: str | None = field(default=None, repr=False)
    tunables: Tunables = Tunables()
    limits: Limits = Limits()

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def secrets(self) -> list[str]:
        return [s for s in (self.telegram_bot_token, self.telegram_chat_id) if s]


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse a minimal ``KEY=VALUE`` .env file (comments and blank lines ignored)."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _merged_env(env: Mapping[str, str] | None, dotenv_path: Path | None) -> dict[str, str]:
    merged: dict[str, str] = {}
    if dotenv_path is not None and dotenv_path.is_file():
        merged.update(parse_dotenv(dotenv_path.read_text(encoding="utf-8")))
    merged.update(os.environ if env is None else env)
    return merged


def _optional(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key, "").strip()
    return value or None


def parse_sources(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return ("google_flights",)
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    unknown = [n for n in names if n not in KNOWN_SOURCES]
    if unknown:
        raise ConfigError(f"unknown source(s) in {ENV_SOURCES}: {', '.join(unknown)}")
    if len(set(names)) != len(names):
        raise ConfigError(f"duplicate source in {ENV_SOURCES}")
    return names


def load_config(
    env: Mapping[str, str] | None = None,
    *,
    production: bool = True,
    dotenv_path: Path | None = PROJECT_DIR / ".env",
) -> Config:
    """Build a ``Config``; in production mode test-only sources are refused."""
    merged = _merged_env(env, dotenv_path)
    sources = parse_sources(merged.get(ENV_SOURCES))
    if production:
        forbidden = sorted(TEST_ONLY_SOURCES.intersection(sources))
        if forbidden:
            raise ConfigError(
                f"test-only source(s) {', '.join(forbidden)} are not allowed in production"
            )
    port_raw = merged.get(ENV_PORT, "").strip()
    try:
        port = int(port_raw) if port_raw else DEFAULT_PORT
    except ValueError as exc:
        raise ConfigError(f"{ENV_PORT} must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ConfigError(f"{ENV_PORT} out of range")
    db_raw = _optional(merged, ENV_DB_PATH)
    return Config(
        db_path=Path(db_raw) if db_raw else DEFAULT_DB_PATH,
        sources=sources,
        port=port,
        telegram_bot_token=_optional(merged, ENV_TELEGRAM_TOKEN),
        telegram_chat_id=_optional(merged, ENV_TELEGRAM_CHAT_ID),
    )
