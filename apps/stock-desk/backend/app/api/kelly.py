"""Read, write, import and clear the Kelly input behind risk cap 5 (ADR-0006 D-8).

Two doors lead to one row. The manual one takes a pair the user typed. The
import one (``POST .../import-backtest``) takes **a backtest request** -- never
a number -- re-runs that backtest server-side and stores what the server itself
computed from it. A body carrying p, b or f\\* is refused by
:class:`~app.api.backtest.BacktestRequest` before this module sees it (約束 31),
which is what stops the "imported from a backtest" badge from being attached to
numbers no backtest produced.

This module is also the **only** assembly point of the three packages the Kelly
path spans (約束 37): ``app.advice`` owns the single fraction formula,
``app.backtest`` owns the round-trip sample and the intervals over it, and
``app.kelly`` owns the storage and the gates. None of the three imports another;
they meet here and nowhere else.

Three rules the endpoints below implement:

* out-of-range numbers are **refused, not clamped** (約束 6). ``win_rate``
  outside (0, 1) or a non-positive ``payoff_ratio`` is a 422 that states the
  bound and says the value was not adjusted, and the stored input keeps
  standing -- the same stance the settings router takes on the reported net
  worth.
* the write stamp is the server's. :class:`KellyManualInput` carries no
  timestamp at all, so an input cannot be backdated into looking fresh.
* editing an imported pair by hand does not erase the import. The row's source
  becomes ``backtest_overridden`` and the imported numbers stay beside the new
  ones (約束 4), so "the user changed this" remains visible.

``DELETE`` removes the input row and **nothing else**: the import-attempt log
is a different table in a different store and is not touched (約束 35).
Clearing an input the user no longer trusts must not also erase how many
imports they tried before keeping one.

Every import attempt that gets past request validation is appended to that log
first, refused or not (約束 29). A **422 is a normal outcome here**, not a
fault: most windows on most symbols do not produce twenty completed round
trips, so the refusal carries a ``reason_code`` and the numbers actually
measured, and the log carries the same verdict. If the log cannot be written,
the import fails with a 500 -- an import that proceeded unlogged would
permanently under-report ``K_observed``, the count the selection-bias
disclosure rests on.

The interval fields that get stored (``p_ci_*``, ``f_star``, ``f_star_ci_*``,
``low_sample_warning``) are **disclosure and audit only** (約束 34). They never
rewrite the effective pair, and cap 5 recomputes the fraction from that pair
rather than reading the stored ``f_star``.

Freshness is stated, not acted on: this router reports ``age_days`` and which
band the input falls in (fresh / ageing / expired, D-4), and an input whose age
cannot be established at all is reported as expired with no age
(:func:`app.kelly.models.ageing_of`). Whether cap 5 still computes from an
expired input is the risk layer's decision, taken from the same helper, so the
two cannot drift into disagreeing about the same row.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict

from app.advice.book import kelly_inputs_of
from app.advice.limits import KellyInputs, kelly_fraction
from app.api.backtest import BacktestRequest, execute_backtest
from app.api.common import now_iso
from app.api.deps import (
    get_dividend_store,
    get_kelly_attempt_store,
    get_kelly_input_store,
    get_market_resolver,
    get_settings_store,
)
from app.backtest.episodes import (
    RoundTripAttribution,
    attribute_round_trips,
    bootstrap_fraction_ci,
    episode_returns,
    oos_window,
    wilson_interval,
)
from app.dividends.store import DividendEventStore
from app.kelly.attempts import KellyAttemptStore
from app.kelly.models import (
    KellyAttemptRecord,
    KellyFreshness,
    KellyGateReasonCode,
    KellyInputRecord,
    KellyInputRow,
    KellyManualInput,
    ageing_of,
    normalize_symbol,
)
from app.kelly.sample_gate import (
    KellySampleGateReview,
    review_estimates,
    review_result_status,
    review_sample,
    review_symbol_match,
)
from app.kelly.store import KellyInputStore
from app.positions.models import Market
from app.services.market import MarketDataResolver
from app.settings.store import SettingsStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kelly-inputs", tags=["kelly"])

KellyStoreDep = Annotated[KellyInputStore, Depends(get_kelly_input_store)]
KellyAttemptsDep = Annotated[KellyAttemptStore, Depends(get_kelly_attempt_store)]
ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]
DividendStoreDep = Annotated[DividendEventStore, Depends(get_dividend_store)]
MarketQuery = Annotated[Market, Query(description="市場別")]

KELLY_INPUT_NOT_FOUND_MESSAGE = "找不到 {symbol}（{market}）的 Kelly 輸入。"

#: Resamples per import. 2000 is the count the degenerate-draw analysis was run
#: against (quant-researcher 2026-08-19): with the 20/5/5 gate in force an
#: all-win or all-loss resample arrives roughly six times in two thousand, far
#: below the 2.5% tail the bounds are read off, so the degenerate draws move the
#: counters and not the stored interval.
BOOTSTRAP_DRAWS = 2000

KELLY_ATTEMPT_LOG_FAILED_MESSAGE = (
    "無法寫入 Kelly 匯入嘗試紀錄，本次匯入未完成，也未寫入 Kelly 輸入。"
)

#: 風控 2026-08-19 逐字定稿（第四輪，備案+修訂），字面含標點不得改動，漂移須重送風控。
#: The 500 body for 約束 27's should-not-happen. It stays in this module rather
#: than in :mod:`app.api.kelly_wording` because 落地條件 25 names this constant and
#: this line; :mod:`tests.test_kelly_wording` carries it in the same verbatim
#: inventory as the other twenty.
#:
#: Three things about the wording are rulings, not choices:
#:
#: * "至少有一端不是有限的數字", never "都不是". The guard below fires on *either*
#:   bound, and the reachable case is one-sided: a no-loss resample still returns
#:   a finite fraction, so the only non-finite value the bootstrap produces is the
#:   ``-inf`` of a no-win draw (``app/backtest/episodes.py``). A sentence saying
#:   both ends are non-finite would be false in the case that actually happens.
#: * "這次沒有寫入 Kelly 輸入", never "沒有數值被寫入". The attempt row *is*
#:   written, with its measured columns; what did not get written is the
#:   ``KellyInputRow``, and the sentence names that.
#: * No retry advice in either direction. "Try again" is an instruction, and
#:   "trying again will not help" is a claim about a future run this code cannot
#:   support -- reproducibility holds only for the same spec over the same bars,
#:   and bars are refetched.
#:
#: It also interpolates nothing. On this branch the bounds are non-finite by
#: construction, so the old ``.format()`` rendered ``inf`` / ``-inf`` / ``nan``
#: into a Chinese sentence -- the same fault 5-3 struck at the root in PB_NONE by
#: deleting the call rather than guarding it. The values go to ``logger.error``
#: below, which 落地條件 28 makes the one place they may not be dropped from.
#:
#: Display order is fixed (條件 27): this sentence first, then
#: :data:`app.api.kelly_wording.KELLY_NON_FINITE_ATTEMPT_LOGGED` (3-B) with (b)
#: beside it. If the surface cannot hold (b), 3-B is omitted and this sentence
#: stands alone -- which is why the fact that nothing was written lives here and
#: not only there.
KELLY_NON_FINITE_INTERVAL_MESSAGE = (
    "本次計算出的 f* 區間，其上界與下界之中至少有一端不是有限的數字，"
    "超出本系統可寫入的範圍，這次沒有寫入 Kelly 輸入。"
)


class KellyInputView(BaseModel):
    """One stored Kelly input plus the freshness facts about it.

    ``anchored_at`` is spelled out rather than left implicit because it differs
    by source: a manual input ages from when it was typed, an imported one from
    the end of the segment it was measured over (D-4). A reader who could not
    see which of the two ``age_days`` counts from would be unable to check it.

    Both are ``null`` together when the row has no anchor at all (an imported
    pair with no OOS end date). ``freshness`` is then ``expired``: no stand-in
    number is reported, because any number there would be read as evidence the
    input is current, and there is none.
    """

    model_config = ConfigDict(frozen=True)

    item: KellyInputRow
    anchored_at: str | None
    age_days: int | None
    freshness: KellyFreshness
    as_of: str


class KellyInputListView(BaseModel):
    """Every stored input, each with its own freshness verdict.

    The list is the same view object per row rather than a leaner summary: a
    caller that had to fetch each row again to learn its age would be one
    forgotten call away from showing a stale pair as if it were current.
    """

    model_config = ConfigDict(frozen=True)

    items: list[KellyInputView]
    as_of: str


class KellyImportRefusal(BaseModel):
    """The body of a refused import: which gate closed, and what it measured.

    A refusal is a normal outcome of this endpoint (D-3), so it is structured
    rather than prose-only: ``reason_code`` is what a client branches on and
    ``message`` states the numbers actually observed against the threshold.
    The message is a statement of measurement, never advice about what to do
    next.
    """

    model_config = ConfigDict(frozen=True)

    reason_code: KellyGateReasonCode
    message: str


def _view(row: KellyInputRow) -> KellyInputView:
    ageing = ageing_of(row)
    return KellyInputView(
        item=row,
        anchored_at=None if ageing.anchored_at is None else ageing.anchored_at.isoformat(),
        age_days=ageing.age_days,
        freshness=ageing.freshness,
        as_of=now_iso(),
    )


def ci_includes_no_edge(row: KellyInputRow) -> bool:
    """Whether the stored f* interval covers "no edge" (約束 36).

    The whole of what the risk layer learns about the interval: one boolean,
    reduced here because ``app/advice/limits.py`` may branch but may not compute
    a statistic, and because handing it the bounds would put a clamp within
    reach of a module forbidden to have one (約束 34).

    ``f_star_ci_low <= 0`` is the test. A row with no interval at all -- every
    manual pair, and any import predating the interval columns -- is ``False``:
    the flag reports that the interval *was seen to* include zero, and (a-2)
    states it as a finding about this estimate. Reporting it for a row that has
    no interval would be a finding about a measurement nobody made.
    """
    return row.f_star_ci_low is not None and row.f_star_ci_low <= 0.0


def kelly_inputs_for(
    store: KellyInputStore, symbol: str, market: Market
) -> KellyInputs | None:
    """Cap 5's input for one holding, or ``None`` when none was ever entered.

    The one place the "read the row -> reduce the interval -> age it" chain is
    assembled, so the advice card, the portfolio overview and the alert loop
    all put the same pair in front of cap 5. It sits in this module because D-8
    makes it the single point allowed to touch the storage package and the risk
    package at once.
    """
    row = store.get(symbol, market)
    if row is None:
        return None
    return kelly_inputs_of(row, ci_includes_no_edge=ci_includes_no_edge(row))


def kelly_inputs_by_symbol(store: KellyInputStore) -> dict[tuple[str, Market], KellyInputs]:
    """Every stored pair, keyed the way the book-level caps group holdings.

    One read for the whole overview rather than one per holding. The key is the
    normalised symbol and the market, which is what
    ``app.advice.book_limits._group_positions`` groups on and what
    ``kelly_inputs`` is keyed on (D-1) -- the two normalisations are the same
    function (:func:`app.kelly.models.normalize_symbol`), so a pair and the
    holding it constrains cannot end up under two spellings of one ticker.
    """
    built: dict[tuple[str, Market], KellyInputs] = {}
    for row in store.list_all():
        inputs = kelly_inputs_of(row, ci_includes_no_edge=ci_includes_no_edge(row))
        if inputs is not None:  # pragma: no branch - a real row always builds
            built[(normalize_symbol(row.symbol), row.market)] = inputs
    return built


def _not_found(symbol: str, market: Market) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=KELLY_INPUT_NOT_FOUND_MESSAGE.format(symbol=symbol, market=market),
    )


@router.get("", response_model=KellyInputListView)
def list_kelly_inputs(store: KellyStoreDep) -> KellyInputListView:
    """Every Kelly input on file, in key order (D-8).

    Not filtered by freshness: an expired input is part of the answer to "what
    has been entered", and dropping it here would leave a caller unable to tell
    a stale pair from one that was never entered. Nothing is read from the
    import-attempt log (約束 35) -- what is in force is read from the input rows
    themselves.
    """
    return KellyInputListView(
        items=[_view(row) for row in store.list_all()], as_of=now_iso()
    )


@router.get("/{symbol}", response_model=KellyInputView)
def read_kelly_input(
    symbol: str, store: KellyStoreDep, market: MarketQuery = "TW"
) -> KellyInputView:
    """The input in force for one instrument, with its age.

    An expired input is returned like any other, carrying ``freshness:
    expired``. Withholding it would make "entered a long time ago" look like
    "never entered", and those two states are not the same thing to a user who
    has to decide what to do next.
    """
    row = store.get(symbol, market)
    if row is None:
        raise _not_found(normalize_symbol(symbol), market)
    return _view(row)


@router.put("/{symbol}", response_model=KellyInputView)
def write_kelly_input(
    symbol: str, body: KellyManualInput, store: KellyStoreDep, market: MarketQuery = "TW"
) -> KellyInputView:
    """Store a hand-entered pair for one instrument.

    A first write creates a ``manual`` row with no provenance -- there is none,
    and a fabricated ``strategy_id`` would make a typed number look measured.
    A write over an imported row keeps everything the import established and
    only moves the effective pair, marking the row ``backtest_overridden``.

    Range violations never reach this function: they are refused by
    :class:`KellyManualInput` as a 422 naming the field and its bound, and
    nothing is written, so the previously stored pair still stands.
    """
    current = store.get(symbol, market)
    if current is None or current.source == "manual":
        record = KellyInputRecord.manual(
            symbol=symbol,
            market=market,
            win_rate=body.win_rate,
            payoff_ratio=body.payoff_ratio,
        )
    else:
        record = KellyInputRecord.overriding(
            current, win_rate=body.win_rate, payoff_ratio=body.payoff_ratio
        )
    saved = store.upsert(record)
    # No history table (D-2), but the change does leave a trace.
    logger.info(
        "kelly input written: symbol=%s market=%s source=%s win_rate=%.4f "
        "payoff_ratio=%.4f previous_source=%s",
        saved.symbol,
        saved.market,
        saved.source,
        saved.win_rate,
        saved.payoff_ratio,
        None if current is None else current.source,
    )
    return _view(saved)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kelly_input(
    symbol: str, store: KellyStoreDep, market: MarketQuery = "TW"
) -> Response:
    """Remove the input in force for one instrument.

    Only the input row. The import-attempt log keeps every row it had, so
    ``K_observed`` is unchanged by this call (約束 35).
    """
    if not store.delete(symbol, market):
        raise _not_found(normalize_symbol(symbol), market)
    logger.info(
        "kelly input deleted: symbol=%s market=%s", normalize_symbol(symbol), market
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# Import path: re-run a backtest server-side and store what it produced (D-3)
# --------------------------------------------------------------------------


def _canonical_spec(body: BacktestRequest) -> tuple[str, str]:
    """The request as canonical JSON, plus its sha256.

    Key-sorted and separator-tight, so two bodies describing the same run
    serialise identically whatever order their fields arrived in. That matters
    twice: the hash is the identity of a spec (``K_distinct_specs`` counts
    distinct hashes) and it is the source of the bootstrap seed, so an unstable
    serialisation would make a re-import of the same spec unreproducible and
    inflate the distinct-spec count at the same time.

    The spec holds a symbol, a window, a strategy id and a cost model -- no
    credential of any kind -- so storing it indefinitely is safe.
    """
    spec = json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return spec, hashlib.sha256(spec.encode("utf-8")).hexdigest()


def _bootstrap_seed(spec_hash: str) -> int:
    """The seed for this spec's bootstrap: the first 32 bits of its hash (約束 27).

    Derived rather than random so the same spec re-run against the same bars
    reproduces the same interval. That is the exact and only claim: the bars are
    fetched again on every import and may have changed, so reproducibility is
    "same spec **and** same bars", never "same spec".
    """
    return int(spec_hash[:8], 16)


def _measured_columns(
    attribution: RoundTripAttribution, *, dates: list[str]
) -> dict[str, Any]:
    """The sample facts an attempt row and a stored row both carry.

    ``oos_observations`` is the number of **bars** the out-of-sample window
    spans, not the number of round trips. The two answer different questions --
    how long the segment was, versus how many completed trades it contained --
    and a sample of twenty-something round trips cannot be read without both.

    The dates are looked up by the same bar indices the attribution used, so the
    window described here is the window the sample was taken from rather than a
    date range that happens to agree with it (約束 23).
    """
    stats = attribution.stats
    return {
        "win_rate": stats.round_trip_win_rate,
        "payoff_ratio": stats.round_trip_payoff_ratio,
        "oos_round_trips": stats.n,
        "oos_win_trips": stats.n_win,
        "oos_loss_trips": stats.n_loss,
        "oos_excluded_boundary_trips": attribution.excluded_boundary_trips,
        "oos_open_trip_at_end": attribution.open_trip_at_end,
        "oos_start_date": dates[attribution.window_start],
        "oos_end_date": dates[attribution.window_stop - 1],
        "oos_observations": attribution.window_stop - attribution.window_start,
    }


def _append_attempt(
    attempts: KellyAttemptStore,
    *,
    symbol: str,
    market: Market,
    strategy_id: str,
    request_spec: str,
    spec_hash: str,
    reason_code: KellyGateReasonCode | None,
    measured: dict[str, Any],
) -> None:
    """Append one attempt to the log, or fail the whole import (約束 29).

    A failure here is never swallowed. An import that went ahead without its
    attempt being recorded would under-report ``K_observed`` permanently, and
    ``K_observed`` is the whole basis of the selection-bias disclosure: it is
    better to refuse an import that would otherwise have succeeded than to keep
    a number whose search history is missing a row.

    ``outcome`` follows the gate verdict, not the storage result (D-2): the row
    below is written before the input row exists, and it stays true whatever
    happens next.
    """
    record = KellyAttemptRecord(
        symbol=symbol,
        market=market,
        strategy_id=strategy_id,
        request_spec=request_spec,
        spec_hash=spec_hash,
        outcome="rejected" if reason_code is not None else "ok",
        reason_code=reason_code,
        **measured,
    )
    try:
        attempts.append(record)
    except Exception as error:
        logger.exception(
            "kelly import attempt could not be logged: symbol=%s market=%s spec_hash=%s",
            symbol,
            market,
            spec_hash,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=KELLY_ATTEMPT_LOG_FAILED_MESSAGE,
        ) from error


@router.post("/{symbol}/import-backtest", response_model=KellyInputView)
def import_kelly_input_from_backtest(
    symbol: str,
    body: BacktestRequest,
    store: KellyStoreDep,
    attempts: KellyAttemptsDep,
    resolver: ResolverDep,
    settings_store: SettingsDep,
    dividend_store: DividendStoreDep,
    market: MarketQuery = "TW",
) -> KellyInputView:
    """Re-run a backtest here and store the p/b **this server** computed (D-3).

    The body is a backtest request, not a result: there is no ``backtest_id`` to
    quote because runs are not stored, so the only way to attach a run's
    authority to a pair of numbers is to produce them here. Everything about the
    run travels with the row -- strategy, window, out-of-sample segment, whether
    rates were verified, whether 除權息 was restored -- because that provenance
    is all a later reader has.

    The order of the gates is the order that spends the least and says the most:
    the symbol check first (a request whose result could not be stored anywhere
    should not spend a data-provider call proving it), then whether the run
    produced a report at all, then the sample-size gates, whose message names
    the count that fell short. Each of them appends its verdict to the attempt
    log before refusing.

    p and b come from **completed round trips** of the out-of-sample window
    (:mod:`app.backtest.episodes`), never from the fill-level ``win_rate`` /
    ``profit_factor`` of the report: the daily rebalance emits a tail of tiny
    closing fills, and counting those as trades would both inflate the sample
    past the gate and distort the rate itself (ADR-0006 Context 事實 5).

    A successful import writes ``source="backtest"`` over whatever was there.
    An imported row later edited by hand becomes ``backtest_overridden`` through
    ``PUT``; re-importing is the user replacing the whole row with a fresh
    measurement, so the previous hand edit does not survive it.
    """
    stored_symbol = normalize_symbol(symbol)
    request_spec, spec_hash = _canonical_spec(body)

    def refuse(review: KellySampleGateReview, measured: dict[str, Any]) -> HTTPException:
        """Log the refusal, then hand back the 422 for the caller to raise."""
        assert review.reason_code is not None and review.rejection is not None
        _append_attempt(
            attempts,
            symbol=stored_symbol,
            market=market,
            strategy_id=body.strategy,
            request_spec=request_spec,
            spec_hash=spec_hash,
            reason_code=review.reason_code,
            measured=measured,
        )
        logger.info(
            "kelly import refused: symbol=%s market=%s strategy=%s reason=%s",
            stored_symbol,
            market,
            body.strategy,
            review.reason_code,
        )
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=KellyImportRefusal(
                reason_code=review.reason_code, message=review.rejection
            ).model_dump(),
        )

    matched = review_symbol_match(
        path_symbol=symbol,
        path_market=market,
        body_symbol=body.symbol,
        body_market=body.market,
    )
    if not matched.passed:
        raise refuse(matched, {})

    run = execute_backtest(
        body,
        resolver=resolver,
        settings_store=settings_store,
        dividend_store=dividend_store,
    )
    ready = review_result_status(run.response.status)
    if not ready.passed:
        raise refuse(ready, {})
    result = run.result
    # ``status == "ok"`` is exactly the branch that produced both (see
    # :class:`app.api.backtest.BacktestRun`), and this is the only
    # ``BacktestResult`` this handler will ever hold (約束 31).
    assert result is not None and run.folds

    start, stop = oos_window(run.folds)
    attribution = attribute_round_trips(result, start=start, stop=stop)
    stats = attribution.stats
    measured = _measured_columns(attribution, dates=result.dates)

    sample = review_sample(stats.n, stats.n_win, stats.n_loss)
    if not sample.passed:
        raise refuse(sample, measured)
    pair = review_estimates(stats.round_trip_win_rate, stats.round_trip_payoff_ratio)
    if not pair.passed:
        # Unreachable through the gate above -- a missing p needs an empty
        # sample and a missing b needs an empty side, both of which the counts
        # already refused. Kept because "unreachable" is a property of today's
        # gate, and a pair of ``None``s must never reach the store.
        raise refuse(pair, measured)
    win_rate = stats.round_trip_win_rate
    payoff_ratio = stats.round_trip_payoff_ratio
    assert win_rate is not None and payoff_ratio is not None  # review_estimates

    p_ci = wilson_interval(stats.n_win, stats.n)
    assert p_ci is not None  # the gate guarantees a non-empty sample
    fraction = bootstrap_fraction_ci(
        episode_returns(attribution.episodes),
        fraction_fn=kelly_fraction,
        seed=_bootstrap_seed(spec_hash),
        draws=BOOTSTRAP_DRAWS,
    )

    if not (math.isfinite(fraction.low) and math.isfinite(fraction.high)):
        # 約束 27: a non-finite bound is a should-not-happen under the 20/5/5
        # gate (it takes a resample with no losses, or no wins, to land on the
        # 2.5% tail). Storing it would put an infinity into SQLite and into
        # every JSON response that later reads the row, so the import fails
        # instead. The attempt is still logged -- it happened, and its gate
        # verdict really was "ok" -- with the interval columns left null,
        # because a null reads as "not recorded" while an infinity would read
        # as a measurement.
        _append_attempt(
            attempts,
            symbol=stored_symbol,
            market=market,
            strategy_id=body.strategy,
            request_spec=request_spec,
            spec_hash=spec_hash,
            reason_code=None,
            measured=measured,
        )
        logger.error(
            "kelly import produced a non-finite f* interval: symbol=%s market=%s "
            "spec_hash=%s low=%s high=%s",
            stored_symbol,
            market,
            spec_hash,
            fraction.low,
            fraction.high,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=KELLY_NON_FINITE_INTERVAL_MESSAGE,
        )

    _append_attempt(
        attempts,
        symbol=stored_symbol,
        market=market,
        strategy_id=body.strategy,
        request_spec=request_spec,
        spec_hash=spec_hash,
        reason_code=None,
        measured={
            **measured,
            "kelly_fraction": fraction.point,
            "f_star_ci_low": fraction.low,
            "f_star_ci_high": fraction.high,
        },
    )
    # Counted after the append, so the row records the K that includes itself:
    # every attempt ever made on this key, refused ones included (約束 30).
    k_observed = attempts.k_observed(stored_symbol, market)

    saved = store.upsert(
        KellyInputRecord(
            symbol=stored_symbol,
            market=market,
            # The effective pair and the imported pair are the same thing at
            # write time (約束 4); a later hand edit moves the first and leaves
            # the second where it is.
            win_rate=win_rate,
            payoff_ratio=payoff_ratio,
            source="backtest",
            backtest_win_rate=win_rate,
            backtest_payoff_ratio=payoff_ratio,
            strategy_id=body.strategy,
            window_start=result.dates[0],
            window_end=result.dates[-1],
            oos_start_date=measured["oos_start_date"],
            oos_end_date=measured["oos_end_date"],
            produced_at=run.response.as_of,
            rates_verified=run.response.rates_verified,
            dividend_reason_code=str(run.response.dividend_adjustment["reason_code"]),
            adjust_dividends=body.adjust_dividends,
            oos_round_trips=stats.n,
            oos_win_trips=stats.n_win,
            oos_loss_trips=stats.n_loss,
            oos_excluded_boundary_trips=attribution.excluded_boundary_trips,
            oos_open_trip_at_end=attribution.open_trip_at_end,
            oos_observations=measured["oos_observations"],
            # Disclosure and audit only, all six of them (約束 34). The cap
            # recomputes its fraction from the effective pair above.
            p_ci_low=p_ci.low,
            p_ci_high=p_ci.high,
            f_star=fraction.point,
            f_star_ci_low=fraction.low,
            f_star_ci_high=fraction.high,
            bootstrap_seed=fraction.seed,
            bootstrap_draws=fraction.draws,
            bootstrap_degenerate_no_loss_draws=fraction.degenerate_no_loss_draws,
            bootstrap_degenerate_no_win_draws=fraction.degenerate_no_win_draws,
            spec_hash=spec_hash,
            low_sample_warning=sample.low_sample_warning,
            k_observed_at_write=k_observed,
        )
    )
    logger.info(
        "kelly input imported: symbol=%s market=%s strategy=%s win_rate=%.4f "
        "payoff_ratio=%.4f round_trips=%d k_observed=%d spec_hash=%s",
        saved.symbol,
        saved.market,
        body.strategy,
        saved.win_rate,
        saved.payoff_ratio,
        stats.n,
        k_observed,
        spec_hash,
    )
    return _view(saved)
