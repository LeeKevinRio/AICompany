"""The direction definition type and its two hashes (ADR-0027 D-1 ``app/dirdef/``, D-10, D-14).

:class:`DirectionDefinition` holds every constant of one dirdef version
(``dirdef-vMAJOR.MINOR``, pre-registration §2.4). ADR-0027 elsewhere calls
these "dirdef constants": they are the attributes of the registered definition
object for a row's ``definition_version``. The type carries:

* the D-1 list: K per horizon (``K3``, ``K5``), ``EPS``, ``SIGMA_MIN_VALID``,
  ``SIGMA_FLOOR``, ``BASKET_EXCLUSION_REASON_ORDER``, ``SPLIT_SUSPECT_ABS_RETURN``,
  and the sector basket member coverage threshold ``BASKET_MIN_MEMBER_WEIGHT``
  (B2D-3; it carries the ``SectorMomentumDefinition`` v1 coverage value so the
  threshold is fixed with the ``definition_version``);
* the three D-14 fields (G-2 machine part): ``f2_variant``, ``c8_decision_ref``,
  ``c8_decision_sha256``;
* the constants FL-31, FL-36 and FL-37 name: the F-2 exit deadlines (FL-31),
  the §4.3 and alpha* constants (FL-36), and the C-8 choice (FL-37, carried by
  ``f2_variant`` per D-14).

Field names beyond the D-1 and D-14 ones are provisional (名稱暫定); quant
confirms them when freezing ``dirdef-v1.0``. The values are not set here and
nothing is registered: validation below only rejects values that no definition
could hold (non-finite, out of range, unordered), it does not pin numbers.

It satisfies ``app.forecast.band.BandDefinition`` structurally (``EPS``,
``SIGMA_FLOOR``, ``SIGMA_MIN_VALID``, ``k_for``) without importing it.

Two hashes, one normalisation (``app.dirdef.hashing``), each defined once here
(D-10 point 1, B2D-1):

* ``definition_logic_sha256`` covers every field except
  :data:`DEFINITION_NON_LOGIC_FIELDS` -- the version label, the description,
  and the two C-8 provenance fields ``c8_decision_ref`` / ``c8_decision_sha256``
  (the C-8 choice itself is ``f2_variant``, inside). A change limited to those
  fields is a MINOR bump that keeps the claim (D-10 point 2);
* ``definition_sha256`` covers every field. Both are registered with each
  version and recomputed before it is returned, so an in-place edit that
  changes the object but not the registered hashes is refused at run time;
  a registered version's object and its two hashes are never to be modified
  (risk R-4).
"""

from __future__ import annotations

from itertools import pairwise
from typing import Annotated, Final, Literal, Self, get_args

from pydantic import ConfigDict, Field, model_validator

from app.dirdef.guard import GuardedModel
from app.dirdef.hashing import canonical_sha256

#: ``dirdef-vMAJOR.MINOR`` (pre-registration §2.4).
DEFINITION_VERSION_PATTERN: Final = r"^dirdef-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"

#: The forecast horizons (ADR-0025 D-2 point 1).
Horizon = Literal[3, 5]

#: ADR-0027 D-3 ``basket_excluded_members_json`` closed list.
BasketExclusionReason = Literal[
    "dividend_factor_unusable",
    "split_or_reduction_suspected",
    "t_plus_h_bar_unavailable",
]

#: The C-8 choice (ADR-0027 D-14 G-2; D-12).
F2Variant = Literal["F2-A", "F2-B"]

#: Fields outside ``definition_logic_sha256`` (D-10 point 1, B2D-1).
DEFINITION_NON_LOGIC_FIELDS: Final[frozenset[str]] = frozenset(
    {"definition_version", "description", "c8_decision_ref", "c8_decision_sha256"}
)

_SHA256_HEX: Final = r"^[0-9a-f]{64}$"

PositiveFinite = Annotated[float, Field(gt=0, allow_inf_nan=False)]
OpenUnit = Annotated[float, Field(gt=0, lt=1)]
PositiveInt = Annotated[int, Field(ge=1)]


def _strictly_increasing(values: tuple[int, ...]) -> bool:
    return all(earlier < later for earlier, later in pairwise(values))


def _is_repo_relative(path: str) -> bool:
    """A POSIX path relative to the repo root: no root, no ``.``/``..``, no empty part."""
    if not path or path.startswith("/") or "\\" in path:
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


class DirectionDefinition(GuardedModel):
    """Every constant of one dirdef version (frozen; strict types)."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    #: ``dirdef-vMAJOR.MINOR``; outside the logic hash.
    definition_version: str = Field(pattern=DEFINITION_VERSION_PATTERN)
    #: Explanatory text; outside the logic hash.
    description: str = Field(min_length=1)

    # --- Label definition (pre-registration §2.1) ---
    K3: PositiveFinite
    K5: PositiveFinite
    EPS: PositiveFinite
    SIGMA_MIN_VALID: Annotated[int, Field(ge=2)]
    SIGMA_FLOOR: PositiveFinite

    # --- Basket exclusion and split suspicion (ADR-0027 D-3, D-9.3) ---
    BASKET_EXCLUSION_REASON_ORDER: tuple[BasketExclusionReason, ...] = Field(min_length=1)
    SPLIT_SUSPECT_ABS_RETURN: OpenUnit
    #: Minimum valid member weight of a basket day, over |S_T| (B2D-3; 名稱暫定).
    #: Range [0.90, 1]: the floor is CoverageRules.sector_coverage_threshold's
    #: "tighten only" floor, written as a literal (no app.sectors import; risk
    #: R-1, C-5'). Later versions may only raise it; lowering the floor needs an
    #: ADR revision with explicit risk-compliance and CEO approval.
    BASKET_MIN_MEMBER_WEIGHT: Annotated[float, Field(ge=0.9, le=1)]

    # --- D-14 G-2 machine part; f2_variant is the C-8 choice (FL-37) ---
    f2_variant: F2Variant
    #: Repo-relative path of the C-8 decision record; provenance, outside the logic hash.
    c8_decision_ref: str
    c8_decision_sha256: str = Field(pattern=_SHA256_HEX)

    # --- F-2 exit deadlines, in non-overlapping n (FL-31) ---
    EXIT_DEADLINE_N_MARKET_SYMBOL: PositiveInt
    EXIT_DEADLINE_N_SECTOR: PositiveInt

    # --- Checkpoints and alpha* (pre-registration §4.4, §4.5; FL-36) ---
    CHECKPOINTS_MARKET_SYMBOL: tuple[PositiveInt, ...] = Field(min_length=1)
    CHECKPOINTS_SECTOR: tuple[PositiveInt, ...] = Field(min_length=1)
    #: K_c of a historical replay claim.
    REPLAY_CHECKPOINT_COUNT: PositiveInt
    #: The family-wise level split by m_eff x K_c.
    ALPHA_FAMILY: OpenUnit
    #: m_eff = max(m, M_EFF_FLOOR).
    M_EFF_FLOOR: PositiveInt

    # --- "Better than baseline" (pre-registration §4.3; FL-36) ---
    #: (d) the model's mean recall must exceed this.
    MIN_MEAN_RECALL: OpenUnit
    #: (e) coverage of scheduled sessions.
    MIN_COVERAGE: OpenUnit
    #: (f) void rate above which (b)(c)(d) must also hold under W.
    VOID_RATE_W_THRESHOLD: OpenUnit
    BOOTSTRAP_RESAMPLES: PositiveInt
    BOOTSTRAP_BLOCK_LEN: PositiveInt
    BOOTSTRAP_BLOCK_LEN_ALTERNATIVES: tuple[PositiveInt, ...]

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if len(set(self.BASKET_EXCLUSION_REASON_ORDER)) != len(self.BASKET_EXCLUSION_REASON_ORDER):
            raise ValueError("BASKET_EXCLUSION_REASON_ORDER repeats a reason")
        if not _is_repo_relative(self.c8_decision_ref):
            raise ValueError("c8_decision_ref must be a repo-relative POSIX path")
        for name in (
            "CHECKPOINTS_MARKET_SYMBOL",
            "CHECKPOINTS_SECTOR",
            "BOOTSTRAP_BLOCK_LEN_ALTERNATIVES",
        ):
            if not _strictly_increasing(getattr(self, name)):
                raise ValueError(f"{name} must be strictly increasing")
        if self.EXIT_DEADLINE_N_MARKET_SYMBOL not in self.CHECKPOINTS_MARKET_SYMBOL:
            raise ValueError("EXIT_DEADLINE_N_MARKET_SYMBOL must be one of the checkpoints")
        if self.EXIT_DEADLINE_N_SECTOR not in self.CHECKPOINTS_SECTOR:
            raise ValueError("EXIT_DEADLINE_N_SECTOR must be one of the sector checkpoints")
        if self.BOOTSTRAP_BLOCK_LEN in self.BOOTSTRAP_BLOCK_LEN_ALTERNATIVES:
            raise ValueError("BOOTSTRAP_BLOCK_LEN_ALTERNATIVES repeats the main block length")
        return self

    def k_for(self, horizon: int) -> float:
        """The K of ``horizon`` (3 or 5); any other horizon is a ``ValueError``."""
        if isinstance(horizon, bool) or horizon not in get_args(Horizon):
            raise ValueError(f"no K for horizon {horizon!r}")
        return self.K3 if horizon == 3 else self.K5


def definition_logic_sha256(definition: DirectionDefinition) -> str:
    """The logic hash of ``definition`` (ADR-0027 D-10 point 1; single definition)."""
    return canonical_sha256(
        definition.model_dump(mode="json", exclude=set(DEFINITION_NON_LOGIC_FIELDS))
    )


def definition_sha256(definition: DirectionDefinition) -> str:
    """The full hash of ``definition``: every field (ADR-0027 D-10 point 1, B2D-1)."""
    return canonical_sha256(definition.model_dump(mode="json"))
