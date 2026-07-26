"""Validation schemas for the settings a user may edit from the UI.

Three sections, each validated by its own pydantic model so a bad value is
rejected field-by-field (422 with the offending ``loc``) rather than silently
clamped:

* ``risk_budget`` -- :class:`app.advice.limits.RiskBudget` verbatim. Its bounds
  are policy, not preference (a single name stays at most 50% of equity, gross
  exposure at most 150%, fractional Kelly at most a quarter and the hard Kelly
  ceiling at most 10%), so they are reused **as they stand** rather than
  re-declared here where they could drift.
* ``cost_model`` -- a validating mirror of :class:`app.backtest.CostModel`,
  which is a plain frozen dataclass. The mirror exists only to add bounds and
  JSON round-tripping; :meth:`CostModelSettings.to_cost_model` converts back.
  ``verified_on`` keeps the rate-provenance contract of ``app/backtest/costs.py``:
  ``None`` means the rates are still UNVERIFIED against a primary source.
* ``alerts`` -- how often the scheduler evaluates rules and how long a fired
  rule stays quiet.

:class:`AppSettingsPatch` is the ``PUT`` body: every section is optional, so a
caller can update one section without restating the others, and an omitted
section is left untouched (never reset to defaults).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.advice.limits import RiskBudget
from app.backtest.costs import CostModel


class CostModelSettings(BaseModel):
    """Editable transaction-cost rates; mirrors :class:`CostModel` with bounds.

    Every rate is a fraction of traded notional and is capped at 10% -- far
    above any real schedule, but low enough that a mistyped percentage (``3``
    instead of ``0.003``) is rejected instead of quietly destroying a backtest.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tw_broker_fee_rate: float = Field(default=CostModel.tw_broker_fee_rate, ge=0.0, le=0.1)
    tw_tax_rate_stock: float = Field(default=CostModel.tw_tax_rate_stock, ge=0.0, le=0.1)
    tw_tax_rate_etf: float = Field(default=CostModel.tw_tax_rate_etf, ge=0.0, le=0.1)
    us_broker_fee_rate: float = Field(default=CostModel.us_broker_fee_rate, ge=0.0, le=0.1)
    us_sell_regulatory_fee_rate: float = Field(
        default=CostModel.us_sell_regulatory_fee_rate, ge=0.0, le=0.1
    )
    slippage_bps: float = Field(default=CostModel.slippage_bps, ge=0.0, le=1000.0)
    #: ISO date the rates were last verified against a primary source; ``None``
    #: means UNVERIFIED (see ``app/backtest/costs.py``).
    verified_on: str | None = Field(default=CostModel.verified_on, pattern=r"^\d{4}-\d{2}-\d{2}$")

    def to_cost_model(self) -> CostModel:
        """Convert to the dataclass the backtester consumes."""
        return CostModel(**self.model_dump())

    @classmethod
    def from_cost_model(cls, model: CostModel) -> CostModelSettings:
        """Build settings from a cost model (the inverse of :meth:`to_cost_model`)."""
        return cls(
            tw_broker_fee_rate=model.tw_broker_fee_rate,
            tw_tax_rate_stock=model.tw_tax_rate_stock,
            tw_tax_rate_etf=model.tw_tax_rate_etf,
            us_broker_fee_rate=model.us_broker_fee_rate,
            us_sell_regulatory_fee_rate=model.us_sell_regulatory_fee_rate,
            slippage_bps=model.slippage_bps,
            verified_on=model.verified_on,
        )

    @property
    def rates_verified(self) -> bool:
        """``True`` only once a primary source has been recorded."""
        return self.verified_on is not None


class AlertSettings(BaseModel):
    """How the alert engine is scheduled and how loudly it may repeat itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Master switch. When off the scheduler skips evaluation entirely.
    enabled: bool = True
    #: Minutes between two alert-evaluation ticks (max one day).
    evaluation_interval_minutes: int = Field(default=60, ge=1, le=1440)
    #: Minutes between two events for the *same* rule. 0 disables the cooldown.
    cooldown_minutes: int = Field(default=60, ge=0, le=10_080)
    #: Whether a triggered event is pushed to the configured webhooks. The
    #: webhook URLs/tokens themselves are env-only and never stored here.
    notify_webhooks: bool = True


class AppSettings(BaseModel):
    """The full settings document returned by ``GET /api/settings``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_budget: RiskBudget = Field(default_factory=RiskBudget)
    cost_model: CostModelSettings = Field(default_factory=CostModelSettings)
    alerts: AlertSettings = Field(default_factory=AlertSettings)


class AppSettingsPatch(BaseModel):
    """The ``PUT /api/settings`` body: any subset of the sections."""

    model_config = ConfigDict(extra="forbid")

    risk_budget: RiskBudget | None = None
    cost_model: CostModelSettings | None = None
    alerts: AlertSettings | None = None

    def apply_to(self, current: AppSettings) -> AppSettings:
        """Return ``current`` with the supplied sections replaced.

        Replacement is per *section*, not per field: a section is validated as a
        whole, so a partially-specified section falls back to that model's
        defaults rather than to the stored values. This keeps every stored
        section a document that was validated in one piece.
        """
        return AppSettings(
            risk_budget=self.risk_budget if self.risk_budget is not None else current.risk_budget,
            cost_model=self.cost_model if self.cost_model is not None else current.cost_model,
            alerts=self.alerts if self.alerts is not None else current.alerts,
        )
