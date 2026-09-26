"""The single definition of the sector momentum method (ADR-0012 D-6, C-16).

Every parameter the ranking, the coverage checks and the gate read lives here,
once. The API echoes the coverage thresholds straight off
``SectorMomentumDefinition.coverage`` (C-33), so the number a sentence prints
and the number the gate compares against are the same object.

Frozen values follow the methodology's §11.1 (v1). Thresholds may only be
tightened: construction rejects anything looser than v1, and changing any value
means a new ``method_version`` (methodology §11.2: freeze -> m + 1 -> risk
re-review -> tell the CEO). Nothing here may be switched at run time on the
strength of a statistic.

Type layers (ADR-0012 D-15, C-46). The core functions read a definition
through four structural protocols defined here and nowhere else --
:class:`UniverseRulesView`, :class:`CoverageRulesView`,
:class:`SectorCoreDefinition` and :class:`SectorEvalDefinition` -- every member
a read-only property, while ``gate`` is always the concrete :class:`GateRules`
(nobody may loosen the judgement thresholds, research included). That lets the
isolated research package run the very same core functions on its sensitivity
variants (methodology §11.1) without a loosened value ever being expressible
in :class:`SectorMomentumDefinition`.

Published definitions (C-16, C-47). The structural types weaken what mypy can
promise, so every entry that persists or outputs something checks at run time
that its definition **is** one of :data:`PUBLISHED_DEFINITIONS`
(:func:`require_published`, object identity): an equal copy, a subclass
instance or a research variant is refused with :class:`UnpublishedDefinition`.
A new version is frozen, added as a constant and listed in
:data:`PUBLISHED_DEFINITIONS` in the same commit, and then registered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol

#: ``sector-rel-v<major>.<minor>-L<lookback>-H<holding>``.
_VERSION_PATTERN: Final = re.compile(r"^sector-rel-v(\d+)\.(\d+)-L(\d+)-H(\d+)$")

#: The only lookback windows the methodology registered (§3.2).
ALLOWED_LOOKBACK_DAYS: Final[frozenset[int]] = frozenset({5, 20})

#: ``PanelFrames.listing.security_type`` value of an ordinary listed share.
#: The listing snapshot is the full common-stock roster of ``t187ap03_L``
#: (ADR-0012 D-3 as amended 2026-09-25: it no longer depends on that day's
#: ``STOCK_DAY_ALL``; code 91 rows are typed ``tdr``); this is the
#: belt-and-braces type check.
COMMON_STOCK_SECURITY_TYPE: Final = "common_stock"


@dataclass(frozen=True)
class UniverseRules:
    """Who belongs to E_g(t) (methodology §2.3, ADR-0012 Q-1)."""

    min_listing_sessions: int = 60
    liquidity_window_sessions: int = 20
    #: NT$ -- median traded value over the liquidity window.
    min_median_traded_value: float = 10_000_000.0
    min_traded_sessions: int = 18
    eligible_security_types: frozenset[str] = frozenset({COMMON_STOCK_SECURITY_TYPE})
    #: Counted in B_EW, never ranked (其他業).
    unranked_sector_codes: frozenset[str] = frozenset({"20"})
    #: Out of the universe entirely, B_EW included (存託憑證).
    excluded_sector_codes: frozenset[str] = frozenset({"91"})
    #: Category ③ insurance: a single-day close-to-close move beyond the daily
    #: price limit plus this tolerance marks an unhandled corporate action.
    daily_price_limit: float = 0.10
    daily_price_limit_tolerance: float = 0.01

    def __post_init__(self) -> None:
        if self.min_listing_sessions < 60:
            raise ValueError("min_listing_sessions may only be tightened (>= 60)")
        if self.liquidity_window_sessions != 20:
            raise ValueError("liquidity_window_sessions is frozen at 20")
        if self.min_median_traded_value < 10_000_000.0:
            raise ValueError("min_median_traded_value may only be tightened")
        if not 18 <= self.min_traded_sessions <= self.liquidity_window_sessions:
            raise ValueError("min_traded_sessions must lie in [18, window]")
        if self.daily_price_limit <= 0 or self.daily_price_limit_tolerance < 0:
            raise ValueError("daily price limit and tolerance must be positive")


@dataclass(frozen=True)
class CoverageRules:
    """Sector and card coverage thresholds (methodology §2.3; risk §6.2, §8, §9)."""

    min_constituents: int = 5
    sector_coverage_threshold: float = 0.90
    #: Card-level completeness: missing (category ①) only (risk §8-1).
    overall_coverage_threshold: float = 0.98
    #: Card-level |C_M| / |E_M|. Provisional; may only be tightened (risk §8 C1-1).
    computable_ratio_min: float = 0.80
    ex_date_tag_ratio_min: float = 0.05

    def __post_init__(self) -> None:
        # Anything >= 3 keeps top-2 + bottom-1 well defined (C-35); v1 froze 5.
        if self.min_constituents < 5:
            raise ValueError("min_constituents may only be tightened (>= 5)")
        for name, floor in (
            ("sector_coverage_threshold", 0.90),
            ("overall_coverage_threshold", 0.98),
            ("computable_ratio_min", 0.80),
        ):
            value = getattr(self, name)
            if not floor <= value <= 1.0:
                raise ValueError(f"{name} must lie in [{floor}, 1]")
        if not 0.0 < self.ex_date_tag_ratio_min <= 0.05:
            # A lower tag threshold shows the tag more often: that is the strict side.
            raise ValueError("ex_date_tag_ratio_min must lie in (0, 0.05]")


@dataclass(frozen=True)
class GateRules:
    """Three-state gate parameters (methodology §6, §8.2, §11.1)."""

    min_samples: int = 150
    min_effective_samples: float = 60.0
    #: b = max(q_gross, base_rate_floor).
    base_rate_floor: float = 0.5
    #: p_net - b must reach this (5 percentage points).
    min_effect: float = 0.05
    #: Family-wise level; the gate uses alpha / m.
    alpha: float = 0.05
    #: NE-4: more than this many trading days since the last recompute.
    stale_after_sessions: int = 20
    bootstrap_block_length: int = 4
    bootstrap_draws: int = 10_000
    permutation_draws: int = 10_000
    label_shuffle_draws: int = 1_000
    #: T8 time-shift placebo: |median Δ_k| must stay below this (2.5pp).
    placebo_shift_tolerance: float = 0.025
    #: T1 runtime: decision dates drawn for the future-perturbation check.
    lookahead_sample_dates: int = 50
    #: Runtime checks that depend on statistics may skip only below this N.
    skip_allowed_below_samples: int = 30
    #: T3a delta_leak: the leaked ranking must beat the real one by at least this
    #: (p_leak - p_real >= leak_margin). Calibrated on CI synthetic data and frozen
    #: with the version (methodology §11.1; tests/test_sector_eval_lookahead.py).
    leak_margin: float = 0.20

    def __post_init__(self) -> None:
        if self.min_samples < 150 or self.min_effective_samples < 60:
            raise ValueError("sample thresholds may only be tightened")
        if self.leak_margin < 0.20:
            raise ValueError("leak_margin may only be tightened (>= 0.20)")
        if self.base_rate_floor < 0.5 or self.min_effect < 0.05:
            raise ValueError("base_rate_floor / min_effect may only be tightened")
        if not 0.0 < self.alpha <= 0.05:
            raise ValueError("alpha may only be tightened (<= 0.05)")
        if not 0 < self.stale_after_sessions <= 20:
            raise ValueError("stale_after_sessions may only be tightened (<= 20)")

    def significance(self, m: int) -> float:
        """Per-test level alpha / m (Bonferroni, methodology §6.2)."""
        if m < 1:
            raise ValueError("m counts at least the version under evaluation")
        return self.alpha / m

    def confidence_level(self, m: int) -> float:
        """Interval level 1 - alpha / m used by Wilson and the bootstrap (G2)."""
        return 1.0 - self.significance(m)


@dataclass(frozen=True)
class SectorMomentumDefinition:
    """One frozen method version. Construction validates the version string."""

    method_version: str
    lookback_days: Literal[5, 20]
    holding_days: int
    market_scope: Literal["twse_only"] = "twse_only"
    ranking_signal: Literal["rel_return_L"] = "rel_return_L"
    benchmark: Literal["equal_weight_market"] = "equal_weight_market"
    ex_dividend_lookback: Literal["exclude_window"] = "exclude_window"
    label_adjustment: Literal["pit_multiplicative_factor"] = "pit_multiplicative_factor"
    constituent_rule: Literal["top2_bottom1"] = "top2_bottom1"
    universe: UniverseRules = field(default_factory=UniverseRules)
    coverage: CoverageRules = field(default_factory=CoverageRules)
    gate: GateRules = field(default_factory=GateRules)
    open_limit_up_factor: float = 1.095
    #: A single constituent contributing more than this share of the sector's
    #: absolute return is flagged ``single_stock_dominated`` (disclosure only).
    single_stock_dominance_share: float = 0.5

    def __post_init__(self) -> None:
        match = _VERSION_PATTERN.fullmatch(self.method_version)
        if match is None:
            raise ValueError(
                f"method_version {self.method_version!r} must look like 'sector-rel-v1.0-L5-H5'"
            )
        encoded_l, encoded_h = int(match.group(3)), int(match.group(4))
        if self.lookback_days not in ALLOWED_LOOKBACK_DAYS:
            raise ValueError(f"lookback_days must be one of {sorted(ALLOWED_LOOKBACK_DAYS)}")
        if encoded_l != self.lookback_days:
            raise ValueError(
                f"method_version encodes L{encoded_l} but lookback_days={self.lookback_days}"
            )
        if self.holding_days < 1 or encoded_h != self.holding_days:
            raise ValueError(
                f"method_version encodes H{encoded_h} but holding_days={self.holding_days}"
            )
        for name, expected in (
            ("market_scope", "twse_only"),
            ("ranking_signal", "rel_return_L"),
            ("benchmark", "equal_weight_market"),
            ("ex_dividend_lookback", "exclude_window"),
            ("label_adjustment", "pit_multiplicative_factor"),
            ("constituent_rule", "top2_bottom1"),
        ):
            if getattr(self, name) != expected:
                raise ValueError(f"{name} is frozen at {expected!r} in this method family")
        if self.open_limit_up_factor != 1.095:
            raise ValueError("open_limit_up_factor is frozen at 1.095")
        if not 0.0 < self.single_stock_dominance_share < 1.0:
            raise ValueError("single_stock_dominance_share must lie in (0, 1)")


#: v1, frozen before D0 (methodology §11.1).
SECTOR_MOMENTUM_V1: Final = SectorMomentumDefinition(
    method_version="sector-rel-v1.0-L5-H5",
    lookback_days=5,
    holding_days=5,
)

#: Every published method version, as the frozen objects themselves (C-16, D-15).
#: Read through the module at call time (:func:`require_published`,
#: :func:`published_versions`), never imported by name elsewhere.
PUBLISHED_DEFINITIONS: Final = (SECTOR_MOMENTUM_V1,)


# ---------------------------------------------------------------------------
# Structural views (ADR-0012 D-15, C-46): read-only, defined here only
# ---------------------------------------------------------------------------


class UniverseRulesView(Protocol):
    """Every field of :class:`UniverseRules`, read-only."""

    @property
    def min_listing_sessions(self) -> int: ...
    @property
    def liquidity_window_sessions(self) -> int: ...
    @property
    def min_median_traded_value(self) -> float: ...
    @property
    def min_traded_sessions(self) -> int: ...
    @property
    def eligible_security_types(self) -> frozenset[str]: ...
    @property
    def unranked_sector_codes(self) -> frozenset[str]: ...
    @property
    def excluded_sector_codes(self) -> frozenset[str]: ...
    @property
    def daily_price_limit(self) -> float: ...
    @property
    def daily_price_limit_tolerance(self) -> float: ...


class CoverageRulesView(Protocol):
    """Every field of :class:`CoverageRules`, read-only."""

    @property
    def min_constituents(self) -> int: ...
    @property
    def sector_coverage_threshold(self) -> float: ...
    @property
    def overall_coverage_threshold(self) -> float: ...
    @property
    def computable_ratio_min(self) -> float: ...
    @property
    def ex_date_tag_ratio_min(self) -> float: ...


class SectorCoreDefinition(Protocol):
    """What the universe, the coverage checks and the ranking read (D-15)."""

    @property
    def method_version(self) -> str: ...
    @property
    def lookback_days(self) -> int: ...
    @property
    def universe(self) -> UniverseRulesView: ...
    @property
    def coverage(self) -> CoverageRulesView: ...
    @property
    def single_stock_dominance_share(self) -> float: ...


class SectorEvalDefinition(SectorCoreDefinition, Protocol):
    """What the evaluator's engine room reads on top of the core (D-15).

    ``gate`` is the concrete :class:`GateRules`: a research variant carries the
    published object itself, so the judgement thresholds cannot be loosened.
    """

    @property
    def holding_days(self) -> int: ...
    @property
    def open_limit_up_factor(self) -> float: ...
    @property
    def gate(self) -> GateRules: ...


# ---------------------------------------------------------------------------
# Published definitions (ADR-0012 C-16, C-47)
# ---------------------------------------------------------------------------


class UnpublishedDefinition(Exception):
    """A definition that is not one of :data:`PUBLISHED_DEFINITIONS` reached a guarded entry."""


def is_method_version(value: str) -> bool:
    """Whether ``value`` has the shape of a method version (``sector-rel-v1.0-L5-H5``).

    The public face of the version pattern: a research variant's name must not
    match it (D-15), and nothing outside this module reads the pattern itself.
    """
    return _VERSION_PATTERN.fullmatch(value) is not None


def published_versions() -> frozenset[str]:
    """The ``method_version`` strings of :data:`PUBLISHED_DEFINITIONS`, read now."""
    return frozenset(definition.method_version for definition in PUBLISHED_DEFINITIONS)


def require_published(definition: object) -> SectorMomentumDefinition:
    """``definition`` itself when it **is** a published object; else :class:`UnpublishedDefinition`.

    Identity, not equality: ``dataclasses.replace(SECTOR_MOMENTUM_V1)`` compares
    equal and is still refused, and so is a subclass instance, a tightened copy
    that reuses a published version string, and every research variant.
    :data:`PUBLISHED_DEFINITIONS` is looked up on each call, not captured.
    """
    for published in PUBLISHED_DEFINITIONS:
        if definition is published:
            return published
    version = getattr(definition, "method_version", None)
    raise UnpublishedDefinition(
        f"definition {version!r} ({type(definition).__name__}) is not one of the published "
        "objects in PUBLISHED_DEFINITIONS; equal copies, subclasses and research variants "
        "are refused (ADR-0012 C-47)"
    )
