"""Validation schemas for the settings a user may edit from the UI.

Four sections, each validated by its own pydantic model so a bad value is
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
* ``net_worth`` -- the account net worth the user reports themselves (FR-9),
  the sole denominator of the gross-exposure cap. Stored as *one* current
  value plus the moment it was written, because the freshness rule needs a
  report time and nothing in this product needs a history of them.

:class:`AppSettingsPatch` is the ``PUT`` body: every section is optional, so a
caller can update one section without restating the others, and an omitted
section is left untouched (never reset to defaults). ``net_worth`` is the one
section whose patch shape differs from its stored shape -- the caller sends the
amount, the server stamps the time -- so a client cannot backdate a figure into
looking fresher than it is.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.advice.limits import RiskBudget
from app.backtest.costs import CostModel

#: Rejection message for a non-positive net worth (FR-9 (c), first row). It is
#: a 422 rather than a clamp: a denominator of zero is not a preference that
#: could be nudged into range, and a silently corrected number is one the user
#: would later believe they had entered.
NET_WORTH_NON_POSITIVE_MESSAGE = (
    "帳戶總淨值必須大於 0。這個數字是總曝險比率的分母，"
    "0 或負數無法構成比率，系統不會自行改成其他數值。"
)


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


class NetWorthInput(BaseModel):
    """The ``net_worth`` section of a ``PUT`` body: the amount, nothing else.

    TWD only, one field, by decision FR-9 (f): a second currency would need an
    exchange rate at the moment of entry, and the only FX source available here
    is a mid-point model value from an unverified endpoint -- not something that
    belongs under a risk cap. The label and the reminder that the user must
    convert their own foreign holdings live on the settings page.

    ``updated_at`` is deliberately **not** accepted here. The server stamps it,
    so "how old is this figure" is always the age of a real user action.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_net_worth_twd: float

    @field_validator("total_net_worth_twd")
    @classmethod
    def _must_be_positive(cls, value: float) -> float:
        if value <= 0.0:
            raise ValueError(NET_WORTH_NON_POSITIVE_MESSAGE)
        return value


class NetWorthSettings(BaseModel):
    """The stored net worth: the current value and when the user reported it.

    Only the latest one is kept (FR-9 (d)). Both fields are ``None`` until the
    user fills the field in for the first time, which is the state that leaves
    the gross-exposure cap ``not_evaluable`` exactly as it was before FR-9.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_net_worth_twd: float | None = None
    #: ISO 8601 UTC, written by the server on every accepted change.
    updated_at: str | None = None

    @field_validator("total_net_worth_twd")
    @classmethod
    def _must_be_positive_when_present(cls, value: float | None) -> float | None:
        if value is not None and value <= 0.0:
            raise ValueError(NET_WORTH_NON_POSITIVE_MESSAGE)
        return value


class AppSettings(BaseModel):
    """The full settings document returned by ``GET /api/settings``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_budget: RiskBudget = Field(default_factory=RiskBudget)
    cost_model: CostModelSettings = Field(default_factory=CostModelSettings)
    alerts: AlertSettings = Field(default_factory=AlertSettings)
    net_worth: NetWorthSettings = Field(default_factory=NetWorthSettings)


class AppSettingsPatch(BaseModel):
    """The ``PUT /api/settings`` body: any subset of the sections."""

    model_config = ConfigDict(extra="forbid")

    risk_budget: RiskBudget | None = None
    cost_model: CostModelSettings | None = None
    alerts: AlertSettings | None = None
    net_worth: NetWorthInput | None = None

    def apply_to(self, current: AppSettings, *, now: datetime | None = None) -> AppSettings:
        """Return ``current`` with the supplied sections replaced.

        Replacement is per *section*, not per field: a section is validated as a
        whole, so a partially-specified section falls back to that model's
        defaults rather than to the stored values. This keeps every stored
        section a document that was validated in one piece.

        ``net_worth`` is stamped with ``now`` whenever it is present, including
        when the amount is unchanged: re-submitting the same figure is the user
        confirming it still holds, which is exactly what the freshness rule
        asks of them. The section is therefore only sent when the user acts on
        that field -- the rest of the settings form leaves it out, so saving a
        fee rate cannot refresh a net worth nobody looked at.
        """
        moment = now if now is not None else datetime.now(UTC)
        net_worth = (
            NetWorthSettings(
                total_net_worth_twd=self.net_worth.total_net_worth_twd,
                updated_at=moment.isoformat(),
            )
            if self.net_worth is not None
            else current.net_worth
        )
        return AppSettings(
            risk_budget=self.risk_budget if self.risk_budget is not None else current.risk_budget,
            cost_model=self.cost_model if self.cost_model is not None else current.cost_model,
            alerts=self.alerts if self.alerts is not None else current.alerts,
            net_worth=net_worth,
        )
