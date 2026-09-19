"""Backup FX adapter: Yahoo Finance chart endpoint (ADR-0011).

Bank of Taiwan's daily-rate CSV export (``app/data/providers/fx.py``) started
serving an HTML anti-bot challenge page for every date as of 2026-09-19 (CEO
本機實測), leaving every USD/TWD-denominated valuation without a rate. This
adapter is the fallback rung of :class:`app.data.providers.fx.FxRateLadder`:
it reuses :meth:`app.data.providers.yfinance.YFinanceAdapter.fetch_chart_closes`
(the same undocumented ``v8/finance/chart`` endpoint already used for the US
equity backup and the sole index path, see that module's docstring) and
reports each day's ``close`` as the day's rate.

Yahoo FX ticker convention (queried against project knowledge on 2026-09-19,
NOT re-verified against a live response in this sandbox -- same egress-policy
caveat as every other adapter in this data layer, see
``tests/fixtures/README.md``): a currency pair is quoted as a ``"=X"``-suffixed
symbol.

- **USD-based pairs** (the only shape this codebase currently needs --
  ``app/portfolio/valuation.py`` always builds FX pairs as
  ``f"{position.currency}TWD"``, and every non-TWD holding currency in scope
  today is USD) use Yahoo's USD-implicit shorthand: ``"<QUOTE>=X"``. For
  ``USDTWD`` this is ``"TWD=X"`` -- 1 USD expressed in TWD. This is the
  well-known, widely-referenced convention (e.g. the same shorthand real
  brokerages' USD/TWD quote pages use), which is why ``USDTWD`` is the pair
  this adapter is actually exercised against.
- **Any other base currency** falls back to the general cross-pair form
  ``"<BASE><QUOTE>=X"`` (e.g. ``"EURTWD=X"``). This branch is provided for
  forward-compatibility only and is UNVERIFIED against a live response --
  nothing in this codebase constructs such a pair today.

``status`` is always ``DataStatus.BACKUP`` on success, mirroring the
non-official-source discipline ADR-0005 already applies to the yfinance index
path (ADR-0005 決策一 point 3 / I-3): this is Yahoo's data, not Bank of
Taiwan's official mid-rate, and must never be presented as ``FRESH``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from datetime import date as date_type
from typing import ClassVar

from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.data.providers.yfinance import YFinanceAdapter

logger = logging.getLogger(__name__)


def _to_yahoo_fx_symbol(pair: str) -> str:
    """Convert a 6-letter pair like ``"USDTWD"`` to Yahoo's ``"=X"`` symbol.

    Raises ``ValueError`` for anything that is not a plain 6-letter alphabetic
    code -- the caller turns that into a declared-unavailable result rather
    than letting it propagate, per the ``FxRateProvider`` contract (adapters
    must not raise for expected/foreseeable input shapes).
    """
    normalized = pair.strip().upper()
    if len(normalized) != 6 or not normalized.isalpha():
        raise ValueError(
            f"unsupported FX pair shape: {pair!r}; expected a 6-letter code like 'USDTWD'"
        )
    base, quote = normalized[:3], normalized[3:]
    if base == "USD":
        return f"{quote}=X"
    return f"{base}{quote}=X"


class YFinanceFxAdapter(FxRateProvider):
    """Backup FX adapter, reusing ``YFinanceAdapter``'s chart-endpoint parsing."""

    source_id: ClassVar[str] = "yfinance_fx"

    def __init__(self, adapter: YFinanceAdapter | None = None) -> None:
        # Callers that want the process-wide shared ``RateLimitedClient``
        # (ADR-0005 決策一 rationale, one throttle budget per host) pass the
        # existing ``YFinanceAdapter`` singleton in; this adapter never owns
        # or closes a caller-supplied instance.
        self._adapter = adapter or YFinanceAdapter()
        self._owns_adapter = adapter is None

    def close(self) -> None:
        if self._owns_adapter:
            self._adapter.close()

    def get_daily_rates(self, pair: str, start: date_type, end: date_type) -> FxRateResult:
        now = datetime.now(UTC)
        try:
            yahoo_symbol = _to_yahoo_fx_symbol(pair)
        except ValueError as exc:
            logger.warning("yfinance FX: rejecting unsupported pair %r: %s", pair, exc)
            return FxRateResult(
                rates=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
                reason=(
                    f"「{pair}」不是本 adapter 支援的匯率代碼格式"
                    "（需為 6 碼字母組合，如 USDTWD）。"
                ),
            )

        bars, error_reason = self._adapter.fetch_chart_closes(yahoo_symbol, start, end)
        if error_reason is not None:
            return FxRateResult(
                rates=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
                reason=error_reason,
            )
        if not bars:
            return FxRateResult(
                rates=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
                reason=f"yfinance 查無「{yahoo_symbol}」在指定區間的匯率資料。",
            )

        rates = [
            FxRate(pair=pair, date=bar.date, rate=bar.close, as_of=now, source=self.source_id)
            for bar in bars
        ]
        rates.sort(key=lambda rate: rate.date)
        return FxRateResult(
            rates=rates,
            status=DataStatus.BACKUP,
            as_of=now,
            source=self.source_id,
            staleness_minutes=0,
        )
