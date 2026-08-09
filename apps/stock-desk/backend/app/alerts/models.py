"""Alert rule and event schemas.

Four rule types, each with its own parameter model so a malformed rule is
rejected at the API boundary rather than at evaluation time:

``price_above`` / ``price_below``
    The latest close crosses a threshold, in the instrument's own currency.
``signal_condition``
    One comparison over the signal vocabulary. It reuses
    :class:`app.advice.loader.Comparison` verbatim, so an alert can only name a
    field the signal layer actually publishes -- the same closed vocabulary the
    advice rules are held to, with no second list to drift.
``risk_limit_breach``
    A named risk cap (or any cap) reports ``violated`` for this symbol.

An alert is a *measurement crossing a line the user drew*. Messages therefore
state the observation and the threshold and stop there: no action verb, no
suggestion, no target. That is the advice engine's job, and it has its own
review gate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.advice.limits import LIMIT_IDS
from app.advice.loader import Comparison
from app.positions.models import Market

AlertType = Literal["price_above", "price_below", "signal_condition", "risk_limit_breach"]

#: ``risk_limit_breach`` may watch one named cap or all of them.
LimitSelector = Literal[
    "any",
    "single_position_weight",
    "sector_weight",
    "gross_exposure",
    "per_trade_loss",
    "kelly_fraction",
]

#: The selector must stay in step with the cap registry; a cap added to
#: ``LIMIT_IDS`` without a selector entry would be unwatchable, and silently so.
LIMIT_SELECTORS: frozenset[str] = frozenset(get_args(LimitSelector))
assert LIMIT_SELECTORS == frozenset(LIMIT_IDS) | {"any"}


class PriceThresholdParams(BaseModel):
    """Parameters of a ``price_above`` / ``price_below`` rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: In the instrument's own currency, matching the bars the rule reads.
    threshold: float = Field(gt=0.0)


class SignalConditionParams(BaseModel):
    """Parameters of a ``signal_condition`` rule: one comparison."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    condition: Comparison


class RiskLimitParams(BaseModel):
    """Parameters of a ``risk_limit_breach`` rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    limit_id: LimitSelector = "any"


AlertParams = Annotated[
    PriceThresholdParams | SignalConditionParams | RiskLimitParams,
    Field(union_mode="left_to_right"),
]


class AlertRuleInput(BaseModel):
    """The user-supplied fields of an alert rule (the ``POST`` body)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: AlertType
    symbol: str = Field(min_length=1)
    market: Market = "TW"
    params: AlertParams
    enabled: bool = True
    note: str | None = None

    @model_validator(mode="after")
    def _params_must_match_type(self) -> AlertRuleInput:
        """Reject a params block that does not match the declared ``type``.

        The union above accepts any of the three shapes; this pins the pairing
        so ``{"type": "price_above", "params": {"limit_id": "any"}}`` is a
        validation error instead of a rule that can never fire.
        """
        expected = _PARAMS_FOR_TYPE[self.type]
        if not isinstance(self.params, expected):
            raise ValueError(f"type 為 {self.type} 時，params 的欄位不符合該類型的規格")
        return self


class AlertRule(AlertRuleInput):
    """A stored alert rule: user fields plus its id and audit timestamps."""

    id: int
    created_at: datetime
    updated_at: datetime


class AlertRulePatch(BaseModel):
    """The ``PATCH /api/alerts/{rule_id}`` body: any subset of the user fields.

    Per *field*, not per document: an omitted field keeps its stored value, so
    turning a rule off is ``{"enabled": false}`` and nothing else (FR-1,
    AC-1.2). ``params`` is still replaced whole -- it is one validated document
    per rule type, and merging into it key by key is what would leave a
    threshold behind on a rule that is no longer a price rule.

    :meth:`apply_to` re-validates the merged result through
    :class:`AlertRuleInput`, so a patch cannot reach a state the ``POST`` body
    could not: the type/params pairing is checked on the way out of here, not
    only on the way in (AC-1.5).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: AlertType | None = None
    symbol: str | None = Field(default=None, min_length=1)
    market: Market | None = None
    params: AlertParams | None = None
    enabled: bool | None = None
    note: str | None = None
    #: ``note`` is nullable *and* optional, so "leave it alone" and "clear it"
    #: are the same JSON without this flag. Sending ``{"note": null}`` alone
    #: keeps the stored note; ``{"clear_note": true}`` removes it.
    clear_note: bool = False

    def apply_to(self, current: AlertRule) -> AlertRuleInput:
        """Return the stored rule's user fields with the supplied ones replaced.

        Raises ``pydantic.ValidationError`` when the merged rule is invalid --
        the caller turns that into a 422, and nothing is written (AC-1.3).
        """
        note = current.note
        if self.clear_note:
            note = None
        elif self.note is not None:
            note = self.note
        return AlertRuleInput(
            type=self.type if self.type is not None else current.type,
            symbol=self.symbol if self.symbol is not None else current.symbol,
            market=self.market if self.market is not None else current.market,
            params=self.params if self.params is not None else current.params,
            enabled=self.enabled if self.enabled is not None else current.enabled,
            note=note,
        )


class AlertEvent(BaseModel):
    """One firing of one rule, as stored and as returned by the API."""

    model_config = ConfigDict(frozen=True)

    id: int
    rule_id: int
    rule_type: AlertType
    symbol: str
    market: Market
    #: Traditional Chinese, observation-only (see the module docstring).
    message: str
    #: The numbers behind the message, so the event can be re-checked.
    observed: dict[str, float | str | None]
    triggered_at: datetime
    acknowledged: bool
    acknowledged_at: datetime | None


_PARAMS_FOR_TYPE: dict[AlertType, type[BaseModel]] = {
    "price_above": PriceThresholdParams,
    "price_below": PriceThresholdParams,
    "signal_condition": SignalConditionParams,
    "risk_limit_breach": RiskLimitParams,
}
