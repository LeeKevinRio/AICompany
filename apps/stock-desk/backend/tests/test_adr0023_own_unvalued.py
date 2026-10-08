"""ADR-0023 / task 6-a: caps 1, 4 and 5 when the symbol has unvalued lots of its own.

The symbol's own position -- market value and share count -- covers only its
valued lots, so caps 1 (single-position weight), 4 (per-trade loss) and 5
(fractional Kelly) are computed from a short numerator. Route C' (ADR-0023
Decision 4): a computed ratio at or over the cap stays ``violated`` with W-a2
appended; one under it is withheld as ``not_evaluable`` with W-a1. None of the
three is sized from (Decision 2, KC-2), and the card's D-d1 / D-d2 lose the
clause about a below-cap result (R-6).

Numbered against the implementation spec in
``work/dispatch/2026-10-07-任務單-6-a-決策卡第1與第5條在本標的有未估值批次時偏低.md``
(6A-01 to 6A-21) and the risk review
``work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md``
(R-1 to R-11, RF-1 to RF-6, section 5: R-P3-1/2, R-M3, R-RF4).

Every approved sentence is referenced through its constant; none is retyped
here, except as the digests the wording tests compare against.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.advice import book as book_module
from app.advice.book import (
    UNVALUED_DIRECTION_OWN_AND_OTHERS,
    UNVALUED_DIRECTION_OWN_ONLY,
    UNVALUED_NOTE_TEMPLATE,
    UNVALUED_POSITIONS_CAUSE,
    UNVALUED_POSITIONS_CAUSE_CACHE_ONLY,
    build_book_context,
    build_book_level_context,
)
from app.advice.engine import build_advice
from app.advice.limits import (
    LIMIT_IDS,
    LIMIT_NAMES,
    NO_SECTOR_DETAILS,
    OWN_UNVALUED_NOT_EVALUABLE_DETAIL,
    OWN_UNVALUED_VIOLATED_DETAIL,
    SECTOR_UNVALUED_UNKNOWN_PASSED_DETAIL,
    LimitCheck,
    PortfolioContext,
    RiskBudget,
    UnknownSectorLots,
    UnvaluedComposition,
    evaluate_limits,
    format_percent,
    notional_caps,
    numerator_complete,
    sector_numerator_gaps,
    suggest_quantity_range,
    symbol_has_unvalued_lots,
)
from app.advice.loader import BANNED_PHRASES
from app.alerts import snapshot as snapshot_module
from app.alerts.engine import UNEVALUATED_LIMITS_NOTE, EvaluationResult, evaluate_alerts
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api import advice as advice_module
from app.api.deps import get_cached_valuator
from app.main import app
from app.portfolio.summary import PortfolioSummary, SummaryPosition
from app.portfolio.valuation import PRICE_NOT_QUERIED, PositionValuator
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from tests.advice_helpers import (
    book_position,
    book_summary,
    kelly_inputs,
    reported_net_worth,
    uptrend_signals,
)
from tests.alerts_helpers import (
    RecordingLoader,
    add_rule,
    breaching_context,
    compliant_context,
    limit_rule,
    snapshot,
)
from tests.api_helpers import (
    FakePriceService,
    UnavailableFxProvider,
    position_payload,
    recent_bars,
    trending_closes,
)
from tests.conftest import ApiHarness
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

BUDGET = RiskBudget()
SEMI = "半導體業"
FIN = "金融保險業"
_NOW = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
STOCK_DESK_ROOT = BACKEND_ROOT.parent

#: Caps 1, 4 and 5: the caps whose ratio sits on this symbol's own position.
OWN_CAPS: tuple[str, ...] = ("single_position_weight", "per_trade_loss", "kelly_fraction")
CAUSES = ("live", "cache_only")


# --- helpers -------------------------------------------------------------------


def _composition(
    own: int, *, same: int = 0, unknown: int = 0, other: int = 0
) -> UnvaluedComposition:
    return UnvaluedComposition(
        own_lots=own,
        same_sector_lots=same,
        unknown_sector_lots=UnknownSectorLots(tw_unfiled=unknown),
        other_sector_lots=other,
    )


def _ctx(*, own_lots: int, **overrides: Any) -> PortfolioContext:
    """A context with every field :func:`build_book_context` sets, set (R-RF4).

    ``own_lots > 0`` is an ``UnvaluedComposition`` with own lots **and**
    ``book_fully_valued=False`` -- what the production builder produces for
    such a book -- never the ``None`` fallback. Defaults sit comfortably under
    caps 1 (5% < 15%), 4 (0.20% < 1%) and 5 (5% < 10%).
    """
    base: dict[str, Any] = {
        "symbol": "2330",
        "total_equity_twd": 1_000_000.0,
        "position_market_value_twd": 50_000.0,
        "position_cost_twd": 45_000.0,
        "gross_exposure_twd": None,
        "net_worth": None,
        "book_fully_valued": own_lots == 0,
        "quantity": 500.0,
        "close": 100.0,
        "fx_to_twd": 1.0,
        "atr": 2.0,
        "sector": None,
        "sector_market_value_twd": None,
        "sector_gap": "unfiled",
        "kelly": kelly_inputs(),
        "unvalued": _composition(own_lots),
        "valued_unclassified_lots": UnknownSectorLots(tw_unfiled=1),
    }
    base.update(overrides)
    return PortfolioContext(**base)


#: The same book with the symbol's position over caps 1 (30%), 4 (1.20%) and
#: 5 (30% against 10%).
_BREACH = {
    "position_market_value_twd": 300_000.0,
    "position_cost_twd": 270_000.0,
    "quantity": 3_000.0,
}


def _without_overlap(context: PortfolioContext) -> PortfolioContext:
    """The same context with no unvalued lot anywhere -- the pre-6-a verdict."""
    return context.model_copy(update={"unvalued": _composition(0), "book_fully_valued": True})


def _check(context: PortfolioContext, limit_id: str) -> LimitCheck:
    return next(check for check in evaluate_limits(BUDGET, context) if check.id == limit_id)


def _w_a1(limit_id: str) -> str:
    return OWN_UNVALUED_NOT_EVALUABLE_DETAIL.format(name=LIMIT_NAMES[limit_id])


def _w_a2(limit_id: str) -> str:
    return OWN_UNVALUED_VIOLATED_DETAIL.format(name=LIMIT_NAMES[limit_id])


def _not_queried(position: SummaryPosition) -> SummaryPosition:
    """The same unvalued lot as a cache-only book reports it (ADR-0010 D-1)."""
    valuation = position.valuation.model_copy(update={"missing": [PRICE_NOT_QUERIED]})
    return position.model_copy(update={"valuation": valuation})


def _unvalued(position_id: int, symbol: str, cause: str, **kwargs: Any) -> SummaryPosition:
    lot = book_position(position_id, symbol, price=None, **kwargs)
    return _not_queried(lot) if cause == "cache_only" else lot


def _cause(cause: str) -> str:
    return UNVALUED_POSITIONS_CAUSE if cause == "live" else UNVALUED_POSITIONS_CAUSE_CACHE_ONLY


def _card_context(summary: PortfolioSummary, **kwargs: Any) -> PortfolioContext:
    return build_book_context(
        summary, symbol="2330", market="TW", close=600.0, currency="TWD", **kwargs
    ).context


def _statuses(result: EvaluationResult) -> list[str]:
    return [outcome.status for outcome in result.outcomes]


def _unevaluable_skip(names: str) -> str:
    """The existing main sentence of an all-unevaluated risk-limit skip."""
    return f"監看的上限（{names}）缺少輸入，無法判定是否違反。"


@pytest.fixture
def store(tmp_path: Path) -> AlertStore:
    return AlertStore(db_path=tmp_path / "alerts.db")


# --- 6A-01 / 6A-02: the single predicate ------------------------------------------


@pytest.mark.parametrize(
    ("unvalued", "fully_valued", "expected"),
    [
        pytest.param(None, None, True, id="fallback-none"),
        pytest.param(None, False, True, id="fallback-false"),
        pytest.param(None, True, False, id="fallback-true"),
        pytest.param(_composition(0, other=2), False, False, id="own-0"),
        pytest.param(_composition(1), False, True, id="own-1"),
        pytest.param(_composition(3, same=1, unknown=1), False, True, id="own-3-with-others"),
    ],
)
def test_hand_built_context_falls_back_to_own_lots(
    unvalued: UnvaluedComposition | None, fully_valued: bool | None, expected: bool
) -> None:
    """KC-5: ``unvalued is None`` reads "none of its own" only on an explicit True."""
    context = PortfolioContext(symbol="2330", unvalued=unvalued, book_fully_valued=fully_valued)
    assert symbol_has_unvalued_lots(context) is expected


@pytest.mark.parametrize(
    "context",
    [
        pytest.param(_ctx(own_lots=0), id="own-0"),
        pytest.param(_ctx(own_lots=1), id="own-1"),
        pytest.param(PortfolioContext(symbol="2330"), id="bare"),
        pytest.param(PortfolioContext(symbol="2330", book_fully_valued=True), id="bare-true"),
        pytest.param(
            _ctx(own_lots=0, sector=SEMI, sector_market_value_twd=50_000.0, sector_gap=None),
            id="own-0-filed",
        ),
        pytest.param(
            _ctx(
                own_lots=0,
                sector=SEMI,
                sector_market_value_twd=50_000.0,
                sector_gap=None,
                unvalued=_composition(0, unknown=1),
                book_fully_valued=False,
            ),
            id="own-0-unknown",
        ),
    ],
)
def test_numerator_complete_covers_caps_1_to_5(context: PortfolioContext) -> None:
    """KC-2: one predicate, one branch per cap, each reading its own verdict's field."""
    own = symbol_has_unvalued_lots(context)
    expected = {
        "single_position_weight": not own,
        "sector_weight": sector_numerator_gaps(context).complete(),
        "gross_exposure": context.book_fully_valued is True,
        "per_trade_loss": not own,
        "kelly_fraction": not own,
    }
    assert set(expected) == set(LIMIT_IDS)
    assert {limit_id: numerator_complete(context, limit_id) for limit_id in LIMIT_IDS} == expected


def test_numerator_complete_refuses_an_unknown_cap() -> None:
    with pytest.raises(ValueError):
        numerator_complete(_ctx(own_lots=0), "no_such_cap")


# --- 6A-03: the sizing gate -----------------------------------------------------


def _sizing_book(own_lots: int, *, unknown: int = 0) -> PortfolioContext:
    """Over caps 1, 4 and 5, filed under an industry, with a fresh net worth."""
    return _ctx(
        own_lots=own_lots,
        sector=SEMI,
        sector_market_value_twd=300_000.0,
        sector_gap=None,
        gross_exposure_twd=1_000_000.0,
        net_worth=reported_net_worth(10_000_000.0),
        unvalued=_composition(own_lots, unknown=unknown),
        book_fully_valued=own_lots == 0 and unknown == 0,
        valued_unclassified_lots=UnknownSectorLots(),
        **_BREACH,
    )


@pytest.mark.parametrize("unknown", [0, 1], ids=["own-only", "own-and-unknown"])
def test_own_unvalued_lots_keep_caps_1_4_5_out_of_sizing_even_when_violated(
    unknown: int,
) -> None:
    complete = _sizing_book(0)
    # Premise: the complete book does size from every cap, so the exclusion
    # below is the gate's doing and not a missing input.
    assert set(notional_caps(BUDGET, complete)) == set(LIMIT_IDS)
    for limit_id in OWN_CAPS:
        assert _check(complete, limit_id).status == "violated"

    own = _sizing_book(1, unknown=unknown)
    for limit_id in OWN_CAPS:
        assert _check(own, limit_id).status == "violated", limit_id
    # Caps 1, 4 and 5 by 6-a; cap 2 because the own lot is "same" (and, on the
    # second book, unknown too); cap 3 because the book is not fully valued.
    assert notional_caps(BUDGET, own) == {}
    for action in ("add", "reduce", "stop_loss", "take_profit"):
        assert suggest_quantity_range(BUDGET, own, action=action) is None


def test_the_cap_3_gate_is_added_to_the_status_gate_not_substituted_for_it() -> None:
    """ADR-0023 Decision 2 erratum: an expired net worth still keeps cap 3 out."""
    fresh = _sizing_book(0)
    assert "gross_exposure" in notional_caps(BUDGET, fresh)
    expired = fresh.model_copy(update={"net_worth": reported_net_worth(10_000_000.0, age_days=40)})
    assert expired.book_fully_valued is True
    assert _check(expired, "gross_exposure").status == "not_evaluable"
    assert "gross_exposure" not in notional_caps(BUDGET, expired)
    incomplete = fresh.model_copy(
        update={"book_fully_valued": False, "unvalued": _composition(0, other=1)}
    )
    assert "gross_exposure" not in notional_caps(BUDGET, incomplete)


# --- 6A-04 / 6A-05 / 6A-06: the verdicts, with the observed rule (R-P3-1) ----------


@pytest.mark.parametrize("limit_id", OWN_CAPS)
def test_own_unvalued_lots_withhold_cap_below_threshold(limit_id: str) -> None:
    own = _ctx(own_lots=1)
    reference = _check(_without_overlap(own), limit_id)
    assert reference.status == "passed"  # premise: computed and under the cap
    check = _check(own, limit_id)
    assert check.status == "not_evaluable"
    assert check.detail == _w_a1(limit_id)
    assert check.observed is None
    assert check.threshold == reference.threshold


@pytest.mark.parametrize("limit_id", OWN_CAPS)
def test_own_unvalued_lots_keep_a_breach_with_w_a2(limit_id: str) -> None:
    own = _ctx(own_lots=1, **_BREACH)
    reference = _check(_without_overlap(own), limit_id)
    assert reference.status == "violated"
    check = _check(own, limit_id)
    assert check.status == "violated"
    # Appended with no space to the whole existing sentence (cap 5: after
    # its disclosures), R-4.
    assert check.detail == reference.detail + _w_a2(limit_id)
    assert "上述" not in check.detail[len(reference.detail) :]
    # R-P3-2: the observed value is the computed ratio, and it is the figure
    # the detail prints.
    assert check.observed is not None
    assert check.observed == reference.observed
    assert format_percent(check.observed) in check.detail
    assert check.threshold == reference.threshold


def _r3_cases() -> list[Any]:
    """Every pre-existing cause that leaves caps 1, 4 or 5 without a ratio (R-3)."""
    return [
        pytest.param("single_position_weight", {"total_equity_twd": None}, id="cap1-no-equity"),
        pytest.param(
            "single_position_weight", {"position_market_value_twd": None}, id="cap1-no-value"
        ),
        pytest.param("per_trade_loss", {"atr": None}, id="cap4-no-atr"),
        pytest.param("per_trade_loss", {"total_equity_twd": None}, id="cap4-no-equity"),
        pytest.param(
            "per_trade_loss",
            {"quantity": None, "close": None, "position_market_value_twd": None},
            id="cap4-no-shares",
        ),
        pytest.param("per_trade_loss", {"atr": 0.0}, id="cap4-zero-atr"),
        pytest.param("kelly_fraction", {"position_market_value_twd": None}, id="cap5-no-weight"),
        pytest.param("kelly_fraction", {"kelly": None}, id="cap5-g1-no-input"),
        pytest.param("kelly_fraction", {"kelly": kelly_inputs(age_days=40)}, id="cap5-expired"),
        pytest.param(
            "kelly_fraction",
            {"kelly": kelly_inputs(age_days=None, anchored_at=None)},
            id="cap5-unanchored",
        ),
    ]


@pytest.mark.parametrize(("limit_id", "overrides"), _r3_cases())
def test_w_a1_only_when_the_ratio_was_computed(limit_id: str, overrides: dict[str, Any]) -> None:
    """R-3: own>0 with no ratio keeps the cause's own sentence, word for word."""
    own = _ctx(own_lots=1, **overrides)
    reference = _check(_without_overlap(own), limit_id)
    assert reference.status == "not_evaluable"
    check = _check(own, limit_id)
    assert check == reference
    assert check.detail != _w_a1(limit_id)


def test_kelly_unusable_keeps_g_table_detail_with_own_lots() -> None:
    for kelly in (None, kelly_inputs(age_days=40), kelly_inputs(age_days=None, anchored_at=None)):
        own = _ctx(own_lots=1, kelly=kelly, **_BREACH)
        assert _check(own, "kelly_fraction") == _check(_without_overlap(own), "kelly_fraction")


def test_w_a1_is_not_reached_through_build_advice_when_the_close_was_withheld() -> None:
    """6A-05 through ``build_advice``: a withheld close keeps cap 4's ATR sentence.

    ``build_book_context`` withholds ``close`` and ``atr`` together (mixed
    currencies, no usable rate); ``engine.py`` no longer fills ``atr`` back in
    from the signals when the close is absent (PR-0, C-2,
    ``work/dispatch/2026-10-07-任務單-PR-0-決策卡第4條ATR回填繞過book層撤下.md``).
    6-a itself adds no second withholding check in ``limits.py`` (C-3).
    """
    own = _ctx(own_lots=1, close=None, atr=None)
    card = build_advice(symbol="2330", signals=uptrend_signals(atr=2.0), portfolio=own)
    cap4 = next(c for c in card["limits_check"] if c["id"] == "per_trade_loss")
    assert cap4["detail"] == _check(_without_overlap(own), "per_trade_loss").detail
    assert cap4["detail"] != _w_a1("per_trade_loss")


@pytest.mark.parametrize("flagged", [False, True], ids=["plain", "a2-flag"])
def test_d5_with_own_unvalued_lots_only_drops_observed(flagged: bool) -> None:
    """Risk-compliance 6-a ruling (3), R-4, R-P3-2: observed None, nothing else moves."""
    for overrides in ({}, _BREACH):
        own = _ctx(
            own_lots=1,
            kelly=kelly_inputs(win_rate=0.3, payoff_ratio=1.0, ci_includes_no_edge=flagged),
            **overrides,
        )
        reference = _check(_without_overlap(own), "kelly_fraction")
        assert reference.status == "violated" and reference.threshold == 0.0  # D-5
        check = _check(own, "kelly_fraction")
        assert check.status == reference.status
        assert check.detail == reference.detail
        assert _w_a2("kelly_fraction") not in check.detail
        assert check.observed is None
        assert reference.observed is not None
        assert check.threshold == reference.threshold == 0.0  # threshold == allowed


def test_own_zero_and_fully_valued_hand_built_contexts_are_unchanged() -> None:
    """R-P3-1 last line: own=0 reads exactly as a context that says nothing of
    its unvalued lots but says the book is complete (the KC-5 "True" fallback).
    """
    for overrides in ({}, _BREACH):
        own0 = _ctx(own_lots=0, **overrides)
        silent = own0.model_copy(update={"unvalued": None, "book_fully_valued": True})
        assert evaluate_limits(BUDGET, own0) == evaluate_limits(BUDGET, silent)


# --- 6A-07 / 6A-08: the approved wording -------------------------------------------


#: sha256 hex digests of W-a1 / W-a2 rendered with each of the three cap names,
#: computed independently of the constants from the review record itself: the
#: W-a1 and W-a2 cells of the section-1 approved-wording table in
#: ``work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md``,
#: with every ``{name}`` replaced by the cap's name, as
#: ``hashlib.sha256(text.encode("utf-8")).hexdigest()``. The template is 84
#: (W-a1) / 48 (W-a2) characters with ``{name}`` counted as one.
_W_A_DIGESTS: dict[tuple[str, str], tuple[int, str]] = {
    ("W-a1", "single_position_weight"): (
        91,
        "e22e81bff0fc2009747f3bbea06785648d0b81b1f4a41a2219cf4380ac33ced2",
    ),
    ("W-a1", "per_trade_loss"): (
        92,
        "05605465fe9277bb9e471a7d1b7db0672cc7dd408d71066160d13cd4ce477a84",
    ),
    ("W-a1", "kelly_fraction"): (
        96,
        "92351a872403181f34ab9a73bf23b0f2676dfead286cd6f57b34b2b0031b1b05",
    ),
    ("W-a2", "single_position_weight"): (
        62,
        "de53701f5ee7d01d85cc30c17b4ee542943212e4e657cb6f3a9328305e6c2470",
    ),
    ("W-a2", "per_trade_loss"): (
        64,
        "e20d394f052e254700ec49f18af4af9a2725825524f042554fd1c6c24157007f",
    ),
    ("W-a2", "kelly_fraction"): (
        72,
        "36fcc7a909d570ce8a6b42a3541250906327db22a7f1665159c7c3e602393858",
    ),
}


@pytest.mark.parametrize(("code", "limit_id"), list(_W_A_DIGESTS))
def test_w_a_wording_is_byte_identical_to_the_approved_wording(code: str, limit_id: str) -> None:
    rendered = _w_a1(limit_id) if code == "W-a1" else _w_a2(limit_id)
    length, digest = _W_A_DIGESTS[(code, limit_id)]
    assert len(rendered) == length
    assert hashlib.sha256(rendered.encode("utf-8")).hexdigest() == digest
    # R-2: the name comes from LIMIT_NAMES; R-4: no "上述" (cap 5's tail is
    # the win-rate disclosure, not a ratio).
    assert LIMIT_NAMES[limit_id] in rendered
    assert "上述" not in rendered


def _shared_forbidden_terms() -> tuple[str, ...]:
    payload = json.loads(
        (STOCK_DESK_ROOT / "shared" / "forbidden-terms.json").read_text(encoding="utf-8")
    )
    return tuple(payload["guarantee"]) + tuple(payload["price_target"])


def _rendered_new_sentences() -> list[str]:
    sentences: list[str] = []
    for limit_id in OWN_CAPS:
        sentences += [_w_a1(limit_id), _w_a2(limit_id)]
    # The D-d deleted versions, alone and joined to each cause.
    for direction in (UNVALUED_DIRECTION_OWN_ONLY, UNVALUED_DIRECTION_OWN_AND_OTHERS):
        sentences.append(direction)
        for cause in CAUSES:
            sentences.append(
                UNVALUED_NOTE_TEMPLATE.format(
                    cause=_cause(cause).format(count=2), direction=direction
                )
            )
    return sentences


@pytest.mark.parametrize("text", _rendered_new_sentences())
def test_new_sentences_pass_the_three_wording_scans(text: str) -> None:
    terms = set(FRONTEND_FORBIDDEN_TERMS) | set(_shared_forbidden_terms()) | set(BANNED_PHRASES)
    assert [term for term in sorted(terms) if term in text] == []
    assert find_bare_realtime_claims(text) == []


# --- 6A-09: D-d deleted versions -------------------------------------------------

#: The two clauses the deleted versions dropped, whole (R-M3; risk-compliance
#: section 5, "6A-09 grep 精確度"). Shorter substrings would also match W3 and
#: ``SECTOR_UNCLASSIFIED_NOTE``, which are approved and in force.
_DELETED_CLAUSES = (
    "，其低於上限的結果也可能建立在偏低的比率上",
    "，低於上限的結果也可能建立在偏低的比率上",
)


def test_d_d_deleted_versions_carry_no_below_cap_clause() -> None:
    for clause in _DELETED_CLAUSES:
        assert clause not in UNVALUED_DIRECTION_OWN_ONLY
        assert clause not in UNVALUED_DIRECTION_OWN_AND_OTHERS
    offenders = [
        f"{path.relative_to(BACKEND_ROOT)}: {clause}"
        for path in sorted(APP_ROOT.rglob("*.py"))
        for clause in _DELETED_CLAUSES
        if clause in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
    # Why the comparison is on whole clauses: the approved sentences still in
    # force share the shorter substrings.
    assert "低於上限的結果" in SECTOR_UNVALUED_UNKNOWN_PASSED_DETAIL
    assert "建立在偏低的比率上" in book_module.SECTOR_UNCLASSIFIED_NOTE


# --- 6A-10: one own>0 predicate in the repo --------------------------------------


def _reads_own_lots(node: ast.Compare) -> bool:
    return any(
        isinstance(sub, ast.Attribute) and sub.attr == "own_lots"
        for operand in (node.left, *node.comparators)
        for sub in ast.walk(operand)
    )


def _own_lots_comparisons() -> list[tuple[str, str | None]]:
    """``(file, innermost enclosing function)`` of each comparison reading ``own_lots``.

    One entry per comparison, so a second comparison in the same function
    shows up as a second entry. ``None`` marks one outside every function.
    """
    found: list[tuple[str, str | None]] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or not _reads_own_lots(node):
                continue
            scope: ast.AST | None = parents.get(node)
            while scope is not None and not isinstance(
                scope, ast.FunctionDef | ast.AsyncFunctionDef
            ):
                scope = parents.get(scope)
            name = scope.name if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef) else None
            found.append((str(path.relative_to(APP_ROOT)), name))
    return found


def test_own_lots_is_compared_only_in_the_single_predicate() -> None:
    """KA-2 / RA-2 / F-9: ``own_lots`` is read as a yes/no in exactly one place."""
    assert _own_lots_comparisons() == [("advice/limits.py", "symbol_has_unvalued_lots")]


def test_the_direction_clause_asks_the_same_predicate() -> None:
    """6A-10: ``_symbol_direction`` calls :func:`symbol_has_unvalued_lots`."""
    tree = ast.parse((APP_ROOT / "advice" / "book.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_symbol_direction"
    )
    called = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "symbol_has_unvalued_lots" in called


# --- 6A-12: the book-level context ------------------------------------------------


@pytest.mark.parametrize("cause", CAUSES)
def test_book_level_context_never_has_own_lots(cause: str) -> None:
    """R-10, second route: the book-level context is classified, with own = 0."""
    books = [
        book_summary(book_position(1, "2330", sector=SEMI)),
        book_summary(book_position(1, "2330", sector=SEMI), _unvalued(2, "2330", cause)),
        book_summary(
            book_position(1, "2330", sector=SEMI),
            _unvalued(2, "2303", cause, sector=SEMI),
            _unvalued(3, "2317", cause),
            _unvalued(4, "2881", cause, sector=FIN),
        ),
        book_summary(_unvalued(1, "2330", cause)),
    ]
    for summary in books:
        context = build_book_level_context(summary).context
        assert context.unvalued is not None
        assert context.unvalued.own_lots == 0
        assert symbol_has_unvalued_lots(context) is False


# --- 6A-13: the alert fixtures and their counterparts (RF-3, RF-4) ---------------


def _unset_fully_valued(context: PortfolioContext) -> PortfolioContext:
    """The fixture's original inputs, with ``book_fully_valued`` not set at all."""
    return PortfolioContext(**context.model_dump(exclude={"book_fully_valued"}))


def test_the_any_rule_on_the_original_compliant_inputs_is_skipped(store: AlertStore) -> None:
    """RF-3 (i): the fallback is pinned -- unknown coverage is not a complete book."""
    add_rule(store, limit_rule(limit_id="any"))
    context = _unset_fully_valued(compliant_context())
    assert context.book_fully_valued is None
    result = evaluate_alerts(store, RecordingLoader(snapshot(context=context)), now=_NOW)
    assert _statuses(result) == ["skipped"]
    names = "、".join(LIMIT_NAMES[limit_id] for limit_id in LIMIT_IDS)
    assert result.outcomes[0].reason == _unevaluable_skip(names)
    assert "上限未評估，未納入判定" not in (result.outcomes[0].reason or "")


def test_the_original_breaching_inputs_fire_the_same_entries_with_w_a2(
    tmp_path: Path,
) -> None:
    """RF-3 (ii): the same caps fire as on the complete book; detail ends with W-a2."""
    results: dict[str, EvaluationResult] = {}
    for label, context in (
        ("true", breaching_context()),
        ("unset", _unset_fully_valued(breaching_context())),
    ):
        store = AlertStore(db_path=tmp_path / f"{label}.db")
        add_rule(store, limit_rule(limit_id="any"))
        results[label] = evaluate_alerts(
            store, RecordingLoader(snapshot(context=context)), now=_NOW
        )
    complete, fallback = results["true"].events, results["unset"].events
    assert len(complete) == len(fallback) == 1
    assert fallback[0].observed == complete[0].observed
    assert fallback[0].message == complete[0].message + _w_a2("single_position_weight")
    assert fallback[0].message.endswith(_w_a2("single_position_weight"))


def test_any_rule_turns_skipped_with_own_lots(store: AlertStore) -> None:
    """RF-4: own=0 is a mixed quiet (caps 1 and 4 passed); own>0 withholds both."""
    add_rule(store, limit_rule(limit_id="any"))
    own0 = _ctx(own_lots=0, kelly=None)
    result0 = evaluate_alerts(store, RecordingLoader(snapshot(context=own0)), now=_NOW)
    assert _statuses(result0) == ["quiet"]
    assert result0.outcomes[0].reason == UNEVALUATED_LIMITS_NOTE.format(
        n=3,
        names="、".join(
            LIMIT_NAMES[i] for i in ("sector_weight", "gross_exposure", "kelly_fraction")
        ),
    )

    other = AlertStore(db_path=store.db_path.with_name("own.db"))
    add_rule(other, limit_rule(limit_id="any"))
    own = _ctx(own_lots=1, kelly=None)
    result = evaluate_alerts(other, RecordingLoader(snapshot(context=own)), now=_NOW)
    assert _statuses(result) == ["skipped"]
    names = "、".join(LIMIT_NAMES[limit_id] for limit_id in LIMIT_IDS)
    assert result.outcomes[0].reason == _unevaluable_skip(names)


@pytest.mark.parametrize("cause", CAUSES)
def test_any_rule_with_own_lots_cannot_turn_mixed_quiet_from_a_built_book(
    tmp_path: Path, cause: str
) -> None:
    """RF-4 case "any -> mixed quiet": no production-built own>0 book reaches it.

    A mixed quiet needs a ``passed`` cap. With own lots, caps 1, 4 and 5 never
    pass (6-a); cap 2 counts the symbol's own lots as "same" whenever it has an
    industry, so it never passes either (ADR-0022 route C'); and cap 3 needs
    ``book_fully_valued is True``, which a book with an unvalued lot never is.
    Pinned here as evidence for the spec owner; see the PR notes.
    """
    for sector in (None, SEMI):
        for net_worth in (None, reported_net_worth(100_000_000.0)):
            valued = [
                book_position(1, "2330", sector=sector),
                book_position(3, "2881", sector=FIN, quantity="100000"),
            ]
            kwargs: dict[str, Any] = {
                "atr": 2.0,
                "net_worth": net_worth,
                "kelly": kelly_inputs(),
            }
            # Guards the premise: without the unvalued lot, the same book passes
            # every cap it can evaluate -- caps 1, 4 and 5 always, cap 2 once it
            # has an industry, cap 3 once it has a net worth -- so what removes
            # the passes below is the own lot and nothing else.
            complete = _card_context(book_summary(*valued), **kwargs)
            passed = {
                check.id for check in evaluate_limits(BUDGET, complete) if check.status == "passed"
            }
            expected = set(OWN_CAPS)
            if sector is not None:
                expected.add("sector_weight")
            if net_worth is not None:
                expected.add("gross_exposure")
            assert passed == expected, (sector, net_worth)

            summary = book_summary(*valued, _unvalued(2, "2330", cause, sector=sector))
            context = _card_context(summary, **kwargs)
            assert symbol_has_unvalued_lots(context)
            statuses = {check.status for check in evaluate_limits(BUDGET, context)}
            assert "passed" not in statuses, (sector, net_worth)
            # And the any rule itself never lands on a quiet.
            store = AlertStore(db_path=tmp_path / f"{sector}-{net_worth is None}.db")
            add_rule(store, limit_rule(limit_id="any"))
            result = evaluate_alerts(store, RecordingLoader(snapshot(context=context)), now=_NOW)
            assert _statuses(result)[0] in {"skipped", "fired"}, (sector, net_worth)


def test_only_cap_1_watched_turns_skipped_without_the_fx_tail(store: AlertStore) -> None:
    """RF-4: an own>0 cap 1 skip never names a failed conversion (scope gate)."""
    fx_failure = "這是一句匯率失敗哨兵句。"
    add_rule(store, limit_rule(limit_id="single_position_weight"))
    own0 = snapshot(context=_ctx(own_lots=0), price_cap_cause=fx_failure)
    assert _statuses(evaluate_alerts(store, RecordingLoader(own0), now=_NOW)) == ["quiet"]

    other = AlertStore(db_path=store.db_path.with_name("own.db"))
    add_rule(other, limit_rule(limit_id="single_position_weight"))
    own = snapshot(context=_ctx(own_lots=1), price_cap_cause=fx_failure)
    result = evaluate_alerts(other, RecordingLoader(own), now=_NOW)
    assert _statuses(result) == ["skipped"]
    assert result.outcomes[0].reason == _unevaluable_skip(LIMIT_NAMES["single_position_weight"])
    assert fx_failure not in (result.outcomes[0].reason or "")


def test_violated_fires_the_same_entries_as_own_zero_with_w_a2(tmp_path: Path) -> None:
    """RF-4 / R-RF4: built by ``build_book_context`` itself."""
    own0 = _card_context(book_summary(book_position(1, "2330")), atr=2.0)
    own = _card_context(
        book_summary(book_position(1, "2330"), book_position(2, "2330", price=None)), atr=2.0
    )
    assert own0.unvalued is not None and own0.unvalued.own_lots == 0
    assert own.unvalued is not None and own.unvalued.own_lots == 1
    assert own.book_fully_valued is False
    events = {}
    for label, context in (("own0", own0), ("own", own)):
        store = AlertStore(db_path=tmp_path / f"{label}.db")
        add_rule(store, limit_rule(limit_id="any"))
        events[label] = evaluate_alerts(
            store, RecordingLoader(snapshot(context=context)), now=_NOW
        ).events
    assert len(events["own0"]) == len(events["own"]) == 1
    assert events["own"][0].observed == events["own0"][0].observed
    assert events["own"][0].observed["violated_limit_ids"] == "single_position_weight"
    assert events["own"][0].message == events["own0"][0].message + _w_a2("single_position_weight")


# --- 6A-14: GWT 1 / 2 end to end ----------------------------------------------------


def _seed_2330(api_harness: ApiHarness) -> None:
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))


def _serve_summary(monkeypatch: pytest.MonkeyPatch, module: Any, summary: PortfolioSummary) -> None:
    """Stand in for the valuator's verdict on one lot (DB-direct in e2e round 25).

    The API refuses a TW lot in USD, so one valued and one unvalued lot of the
    same symbol is not something the test client can create; everything after
    the summary -- the book context, the caps, the card -- is the real path.
    """

    def _summary(*_args: Any, **_kwargs: Any) -> PortfolioSummary:
        return summary

    monkeypatch.setattr(module, "build_summary", _summary)


def _own_book(cause: str, *, all_unvalued: bool, breach: bool) -> PortfolioSummary:
    lots = [
        _unvalued(1, "2330", cause) if all_unvalued else book_position(1, "2330"),
        _unvalued(2, "2330", cause),
    ]
    if not breach:
        # Another valued holding large enough to keep 2330 under every cap.
        lots.append(book_position(3, "2881", quantity="100000"))
    return book_summary(*lots)


def _limits(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {check["id"]: check for check in body["advice"]["limits_check"]}


@pytest.mark.parametrize("cause", CAUSES)
@pytest.mark.parametrize("all_unvalued", [False, True], ids=["one-unvalued", "all-unvalued"])
def test_api_advice_own_unvalued_lots_withhold_caps_1_4_5(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch, cause: str, all_unvalued: bool
) -> None:
    _seed_2330(api_harness)
    api_harness.client.put("/api/kelly-inputs/2330", json={"win_rate": 0.6, "payoff_ratio": 2.0})
    _serve_summary(
        monkeypatch, advice_module, _own_book(cause, all_unvalued=all_unvalued, breach=False)
    )
    body = api_harness.client.get("/api/advice/2330").json()
    assert body["status"] == "ok"
    assert body["portfolio_context"]["unvalued"]["own_lots"] == (2 if all_unvalued else 1)
    limits = _limits(body)
    for limit_id in OWN_CAPS:
        assert limits[limit_id]["status"] == "not_evaluable", limit_id
        assert limits[limit_id]["detail"] == _w_a1(limit_id)
        assert limits[limit_id]["observed"] is None
    assert limits["single_position_weight"]["threshold"] == BUDGET.max_position_weight
    assert limits["per_trade_loss"]["threshold"] == BUDGET.max_loss_per_trade
    assert limits["kelly_fraction"]["threshold"] is not None
    # P-5 / R-P5-1: no range, so no "未參與計算" sentence either.
    assert body["advice"]["quantity_range"] is None
    # The deleted-clause D-d1 travels on the same card.
    count = 2 if all_unvalued else 1
    assert (
        UNVALUED_NOTE_TEMPLATE.format(
            cause=_cause(cause).format(count=count), direction=UNVALUED_DIRECTION_OWN_ONLY
        )
        in body["context_notes"]
    )


@pytest.mark.parametrize("cause", CAUSES)
def test_api_advice_own_unvalued_lots_keep_a_breach_with_w_a2(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch, cause: str
) -> None:
    _seed_2330(api_harness)
    api_harness.client.put("/api/kelly-inputs/2330", json={"win_rate": 0.6, "payoff_ratio": 2.0})
    _serve_summary(monkeypatch, advice_module, _own_book(cause, all_unvalued=False, breach=True))
    body = api_harness.client.get("/api/advice/2330").json()
    limits = _limits(body)
    for limit_id in ("single_position_weight", "kelly_fraction"):
        check = limits[limit_id]
        assert check["status"] == "violated", limit_id
        assert check["detail"].endswith(_w_a2(limit_id))
        assert check["observed"] is not None
        assert format_percent(check["observed"]) in check["detail"]
    assert limits["per_trade_loss"]["detail"] == _w_a1("per_trade_loss")
    assert body["advice"]["action"] == "hold"
    assert body["advice"]["quantity_range"] is None
    assert "仍然超標" not in json.dumps(body, ensure_ascii=False)


def test_api_advice_reaches_own_lots_through_the_cache_only_valuator(
    api_harness: ApiHarness,
) -> None:
    """The production route to own>0 on an ``ok`` card, with no stand-in.

    The card values the book from the local cache (ADR-0010 D-1) while the bars
    behind the card are loaded live: a symbol the cache has not seen is
    unvalued (``price_not_queried``) on a card that still has a price.
    """
    _seed_2330(api_harness)
    cache = FakePriceService()
    cache.seed("2881", recent_bars(trending_closes(60), symbol="2881"))
    app.dependency_overrides[get_cached_valuator] = lambda: PositionValuator(
        market_services={"TW": cache},
        fx_provider=UnavailableFxProvider(),
        price_mode="cache_only",
    )
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.post("/api/positions", json=position_payload(symbol="2881"))
    api_harness.client.put("/api/kelly-inputs/2330", json={"win_rate": 0.6, "payoff_ratio": 2.0})
    body = api_harness.client.get("/api/advice/2330").json()
    assert body["status"] == "ok"
    assert body["portfolio_context"]["unvalued"]["own_lots"] == 1
    assert body["portfolio_context"]["book_fully_valued"] is False
    limits = _limits(body)
    for limit_id in OWN_CAPS:
        assert limits[limit_id]["status"] == "not_evaluable", limit_id
        assert limits[limit_id]["detail"] == _w_a1(limit_id)
        assert limits[limit_id]["observed"] is None
    assert body["advice"]["quantity_range"] is None


def test_build_advice_add_is_blocked_by_cap_1_with_w_a2() -> None:
    """GWT 2: the breach blocks the ``add`` with the standing sentence.

    At the 15% cap with a close above the moving averages, as in
    ``test_advice_engine``'s golden case, so the signals aggregate to ``add``.
    """
    own = _ctx(
        own_lots=1,
        position_market_value_twd=150_000.0,
        position_cost_twd=135_000.0,
        quantity=1_363.0,
        close=110.0,
    )
    card = build_advice(symbol="2330", signals=uptrend_signals(), portfolio=own)
    reference = build_advice(
        symbol="2330", signals=uptrend_signals(), portfolio=_without_overlap(own)
    )
    assert reference["aggregated_action"] == "add" and reference["blocked_action"] == "add"
    assert card["action"] == "hold"
    assert card["blocked_action"] == "add"
    # The same caps block, so the same standing sentences, verbatim.
    assert card["blocked_notices"] == reference["blocked_notices"]
    assert card["quantity_range"] is None
    cap1 = next(c for c in card["limits_check"] if c["id"] == "single_position_weight")
    assert cap1["detail"].endswith(_w_a2("single_position_weight"))


def test_build_advice_sell_side_has_no_range_and_no_still_breached_sentence() -> None:
    own = _ctx(own_lots=1, **_BREACH)
    signals = uptrend_signals(max_drawdown=-0.35, current_drawdown=-0.35)
    card = build_advice(symbol="2330", signals=signals, portfolio=own)
    assert card["action"] in {"reduce", "stop_loss"}
    assert card["quantity_range"] is None
    assert "仍然超標" not in json.dumps(card, ensure_ascii=False)


def _snapshot_inputs(tmp_path: Path, *, cache_only: bool) -> dict[str, Any]:
    """A real store, resolver and valuator; the valuator has no price for 2330."""
    store = PositionStore(db_path=tmp_path / "positions.db")
    for symbol, quantity in (("2330", 1000), ("2881", 100000)):
        store.create(
            PositionInput(
                symbol=symbol,
                market="TW",
                quantity=Decimal(quantity),
                avg_cost=Decimal(600),
                currency="TWD",
                opened_at=date(2024, 1, 2),
                instrument_type="stock",
                sector=None,
                note=None,
            )
        )
    bars = FakePriceService()
    bars.seed("2330", recent_bars(trending_closes(60), symbol="2330"))
    valuation_prices = FakePriceService()
    valuation_prices.seed("2881", recent_bars(trending_closes(60), symbol="2881"))
    return {
        "resolver": {"TW": bars},
        "store": store,
        "valuator": PositionValuator(
            market_services={"TW": valuation_prices},
            fx_provider=UnavailableFxProvider(),
            price_mode="cache_only" if cache_only else "live",
        ),
        "budget": BUDGET,
        "fx_provider": None,
        "kelly": kelly_inputs(),
        "today": datetime.now(UTC).date(),
    }


@pytest.mark.parametrize("cause", CAUSES)
def test_snapshot_own_unvalued_lots_withhold_caps_1_4_5(
    tmp_path: Path, store: AlertStore, cause: str
) -> None:
    snap = build_snapshot(
        "2330", "TW", **_snapshot_inputs(tmp_path, cache_only=cause == "cache_only")
    )
    limits = {check.id: check for check in snap.limits}
    for limit_id in OWN_CAPS:
        assert limits[limit_id].status == "not_evaluable", limit_id
        assert limits[limit_id].detail == _w_a1(limit_id)
        assert limits[limit_id].observed is None
    add_rule(store, limit_rule(limit_id="any"))
    result = evaluate_alerts(store, RecordingLoader(snap), now=_NOW)
    assert _statuses(result) == ["skipped"]


def test_snapshot_own_unvalued_lots_fire_with_w_a2(
    tmp_path: Path, store: AlertStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_summary(monkeypatch, snapshot_module, _own_book("live", all_unvalued=False, breach=True))
    snap = build_snapshot("2330", "TW", **_snapshot_inputs(tmp_path, cache_only=False))
    add_rule(store, limit_rule(limit_id="any"))
    result = evaluate_alerts(store, RecordingLoader(snap), now=_NOW)
    assert len(result.events) == 1
    message = result.events[0].message
    assert _w_a2("single_position_weight") in message
    assert _w_a2("kelly_fraction") in message


# --- 6A-15: own = 0 leaves caps 1, 4 and 5 word for word ---------------------------


def _own_zero_books() -> dict[str, tuple[PortfolioSummary, str]]:
    return {
        "a-same-sector": (
            book_summary(
                book_position(1, "2330", sector=SEMI),
                book_position(2, "2303", sector=SEMI, price=None),
            ),
            "2330",
        ),
        "b-unknown": (
            book_summary(
                book_position(1, "2330", sector=SEMI), book_position(2, "2317", price=None)
            ),
            "2330",
        ),
        "c-other": (
            book_summary(
                book_position(1, "2330", sector=SEMI),
                book_position(2, "2881", sector=FIN, price=None),
            ),
            "2330",
        ),
        "candidate": (
            book_summary(
                book_position(1, "2881", sector=FIN), book_position(2, "2317", price=None)
            ),
            "2330",
        ),
    }


@pytest.mark.parametrize("name", list(_own_zero_books()))
def test_own_zero_leaves_caps_1_4_5_word_for_word(name: str) -> None:
    summary, symbol = _own_zero_books()[name]
    context = build_book_context(
        summary,
        symbol=symbol,
        market="TW",
        close=600.0,
        currency="TWD",
        atr=2.0,
        kelly=kelly_inputs(),
    ).context
    assert context.unvalued is not None and context.unvalued.own_lots == 0
    reference = _without_overlap(context)
    for limit_id in OWN_CAPS:
        assert _check(context, limit_id) == _check(reference, limit_id), limit_id
    caps, reference_caps = notional_caps(BUDGET, context), notional_caps(BUDGET, reference)
    for limit_id in OWN_CAPS:
        assert caps.get(limit_id) == reference_caps.get(limit_id), limit_id


# --- 6A-16 / 6A-17 ------------------------------------------------------------------


def test_d5_own_lots_fires_without_w_a2(store: AlertStore) -> None:
    """Risk-compliance 6-a ruling (3): ``violated`` with ``observed`` None does not break alerts."""
    own = _ctx(own_lots=1, kelly=kelly_inputs(win_rate=0.3, payoff_ratio=1.0))
    assert _check(own, "kelly_fraction").observed is None
    add_rule(store, limit_rule(limit_id="kelly_fraction"))
    result = evaluate_alerts(store, RecordingLoader(snapshot(context=own)), now=_NOW)
    assert len(result.events) == 1
    event = result.events[0]
    assert event.observed == {"violated_limit_ids": "kelly_fraction", "violated_count": 1.0}
    assert _w_a2("kelly_fraction") not in event.message


@pytest.mark.parametrize("cause", CAUSES)
def test_bare_context_with_own_lots_is_not_no_position(cause: str) -> None:
    """Risk-compliance 6-a suggested: own lots never read as "not held".

    A built context always names its sector gap, so a holding whose every lot
    is unvalued (zero valued value and shares) is still a holding to cap 2.
    The alert engine's own bare context feeds the signal rules only and never
    reaches :func:`evaluate_limits`.
    """
    summary = book_summary(_unvalued(1, "2330", cause), book_position(2, "2881", sector=FIN))
    context = _card_context(summary)
    assert context.position_market_value_twd == 0.0 and context.quantity == 0.0
    assert context.sector_gap == "unfiled"
    assert _check(context, "sector_weight").detail == NO_SECTOR_DETAILS["unfiled"]
    assert _check(context, "sector_weight").detail != NO_SECTOR_DETAILS["no_position"]
    # A hand-built context with a valued part of its own infers the same.
    hand_built = _ctx(own_lots=1, sector_gap=None)
    assert _check(hand_built, "sector_weight").detail == NO_SECTOR_DETAILS["unfiled"]


def test_the_alert_bare_context_never_reaches_the_caps() -> None:
    """6A-17: ``signal_context`` builds rule inputs only; no cap is evaluated on it."""
    source = (APP_ROOT / "alerts" / "engine.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {
        getattr(node.func, "id", getattr(node.func, "attr", ""))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "evaluate_limits" not in called
