"""Application services. Adapters are injected; concrete adapters are never imported here."""

from __future__ import annotations

from dataclasses import dataclass

from flight_deals.domain.models import Watch
from flight_deals.ports import Clock
from flight_deals.services.health import HealthService
from flight_deals.services.notifications import NotificationService
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


__all__ = [
    "Clock",
    "Watch",
    "HealthService",
    "NotificationService",
    "ScanService",
    "Services",
    "SettingsService",
    "ViewService",
    "WatchService",
]
