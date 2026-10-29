"""Application services. Adapters are injected; concrete adapters are never imported here."""

from __future__ import annotations

from dataclasses import dataclass

from flight_deals.domain.messages import EXPLORATION_NOT_FOUND
from flight_deals.domain.models import Watch
from flight_deals.ports import Clock
from flight_deals.services.commands import CommandService
from flight_deals.services.digest import DIGEST_ZONE, DigestService
from flight_deals.services.exploration import ExplorationService
from flight_deals.services.exploration_views import ExplorationViewService
from flight_deals.services.health import HealthService
from flight_deals.services.notifications import NotificationService
from flight_deals.services.retention import RetentionService, retention_notice
from flight_deals.services.scan import ScanService
from flight_deals.services.settings import SettingsService
from flight_deals.services.views import ViewService
from flight_deals.services.watches import WatchService


@dataclass
class Services:
    """Everything the web and scheduler layers may use."""

    watches: WatchService
    views: ViewService
    settings: SettingsService
    notifications: NotificationService
    scan: ScanService
    health: HealthService
    digest: DigestService
    exploration: ExplorationService
    exploration_views: ExplorationViewService
    # Telegram commands (FD-7); None when assembled without them.
    commands: CommandService | None = None
    # Daily purge and weekly VACUUM (FD-7); None when assembled without them.
    retention: RetentionService | None = None


__all__ = [
    "EXPLORATION_NOT_FOUND",
    "Clock",
    "CommandService",
    "DIGEST_ZONE",
    "DigestService",
    "ExplorationService",
    "ExplorationViewService",
    "Watch",
    "HealthService",
    "NotificationService",
    "RetentionService",
    "ScanService",
    "Services",
    "SettingsService",
    "ViewService",
    "WatchService",
    "retention_notice",
]
