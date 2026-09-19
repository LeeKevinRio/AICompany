"""Contract tests for ``FxRateLadder`` (ADR-0011): primary -> backup -> unavailable."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateLadder, FxRateProvider, FxRateResult

_NOW = datetime(2026, 9, 19, tzinfo=UTC)


class _PrimaryStub(FxRateProvider):
    """A minimal, fully-controllable ``FxRateProvider`` standing in for the primary rung."""

    source_id = "bank_of_taiwan"

    def __init__(self, result: FxRateResult | None = None, *, raises: bool = False) -> None:
        self._result = result
        self._raises = raises
        self.calls = 0

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.calls += 1
        if self._raises:
            raise RuntimeError("boom")
        assert self._result is not None
        return self._result


class _BackupStub(FxRateProvider):
    """A minimal, fully-controllable ``FxRateProvider`` standing in for the backup rung."""

    source_id = "yfinance_fx"

    def __init__(self, result: FxRateResult | None = None, *, raises: bool = False) -> None:
        self._result = result
        self._raises = raises
        self.calls = 0

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.calls += 1
        if self._raises:
            raise RuntimeError("boom")
        assert self._result is not None
        return self._result


def _rate(day: date, value: str, *, source: str) -> FxRate:
    return FxRate(pair="USDTWD", date=day, rate=Decimal(value), as_of=_NOW, source=source)


def _ok_result(source: str, status: DataStatus = DataStatus.FRESH) -> FxRateResult:
    return FxRateResult(
        rates=[_rate(date(2026, 9, 19), "32.500", source=source)],
        status=status,
        as_of=_NOW,
        source=source,
        staleness_minutes=0,
    )


def _unavailable_result(source: str, reason: str) -> FxRateResult:
    return FxRateResult(
        rates=[],
        status=DataStatus.UNAVAILABLE,
        as_of=_NOW,
        source=source,
        staleness_minutes=None,
        reason=reason,
    )


def test_primary_success_is_returned_untouched_and_backup_is_never_called() -> None:
    primary = _PrimaryStub(_ok_result("bank_of_taiwan"))
    backup = _BackupStub(_ok_result("yfinance_fx"))
    ladder = FxRateLadder(primary=primary, backup=backup)

    result = ladder.get_daily_rates("USDTWD", date(2026, 9, 12), date(2026, 9, 19))

    assert result.status is DataStatus.FRESH
    assert result.source == "bank_of_taiwan"
    assert backup.calls == 0


def test_primary_failure_falls_back_to_backup_labelled_backup_with_reason() -> None:
    primary = _PrimaryStub(
        _unavailable_result("bank_of_taiwan", "台灣銀行匯率來源目前回應為 HTML 挑戰頁")
    )
    backup = _BackupStub(_ok_result("yfinance_fx"))
    ladder = FxRateLadder(primary=primary, backup=backup)

    result = ladder.get_daily_rates("USDTWD", date(2026, 9, 12), date(2026, 9, 19))

    assert result.status is DataStatus.BACKUP
    assert result.source == "yfinance_fx"
    assert result.rates
    assert result.reason is not None
    assert "bank_of_taiwan" in result.reason
    assert "HTML 挑戰頁" in result.reason


def test_both_fail_returns_unavailable_with_combined_reason() -> None:
    primary = _PrimaryStub(_unavailable_result("bank_of_taiwan", "台灣銀行原因 A"))
    backup = _BackupStub(_unavailable_result("yfinance_fx", "yfinance 原因 B"))
    ladder = FxRateLadder(primary=primary, backup=backup)

    result = ladder.get_daily_rates("USDTWD", date(2026, 9, 12), date(2026, 9, 19))

    assert result.status is DataStatus.UNAVAILABLE
    assert result.rates == []
    assert result.reason is not None
    assert "台灣銀行原因 A" in result.reason
    assert "yfinance 原因 B" in result.reason


def test_primary_never_upgraded_and_backup_never_labelled_fresh() -> None:
    """Even if a stub backup claims FRESH, the ladder must still label it BACKUP."""
    primary = _PrimaryStub(_unavailable_result("bank_of_taiwan", "不可用"))
    backup = _BackupStub(_ok_result("yfinance_fx", status=DataStatus.FRESH))
    ladder = FxRateLadder(primary=primary, backup=backup)

    result = ladder.get_daily_rates("USDTWD", date(2026, 9, 12), date(2026, 9, 19))
    assert result.status is DataStatus.BACKUP


def test_a_raising_provider_is_treated_as_a_declined_rung() -> None:
    primary = _PrimaryStub(raises=True)
    backup = _BackupStub(_ok_result("yfinance_fx"))
    ladder = FxRateLadder(primary=primary, backup=backup)

    result = ladder.get_daily_rates("USDTWD", date(2026, 9, 12), date(2026, 9, 19))
    assert result.status is DataStatus.BACKUP
    assert backup.calls == 1


def test_both_raising_returns_unavailable_without_propagating() -> None:
    primary = _PrimaryStub(raises=True)
    backup = _BackupStub(raises=True)
    ladder = FxRateLadder(primary=primary, backup=backup)

    result = ladder.get_daily_rates("USDTWD", date(2026, 9, 12), date(2026, 9, 19))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.rates == []
