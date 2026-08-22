"""Sample-size gates an imported Kelly pair has to clear (ADR-0006 D-3).

Same shape as ``app/settings/net_worth.py``: threshold constants, a refusal
message per band, and ``review_*`` functions returning a verdict object. The
caller does the writing (or refuses to); nothing here touches a store.

Every function takes **scalars only** -- counts, strings, optional floats. That
is what keeps this module free of any import from ``app.backtest`` (約束 37):
the gate needs to know *how many* round trips there were, never what a
``BacktestResult`` looks like. The counts must come from completed position
round trips, never from closing fills: fill-level counts are inflated by the
daily rebalance (ADR-0006 Context 事實 5) and would wave through a sample that
does not exist.

Three hard gates and a soft band:

* ``n < MIN_OOS_ROUND_TRIPS`` -- refused. Below this there is no sample to
  estimate a probability from at all.
* ``n_win < MIN_OOS_WIN_TRIPS`` / ``n_loss < MIN_OOS_LOSS_TRIPS`` -- refused.
  A total that clears the first gate can still be one-sided, and a payoff ratio
  built on two losses is a number with no content.
* ``MIN_OOS_ROUND_TRIPS <= n < SOFT_WARNING_ROUND_TRIPS`` -- accepted, with
  ``low_sample_warning`` set. It travels with the row as a disclosure flag and
  must never feed a calculation (約束 34).

A refusal is a **normal path**, not a fault: most windows on most symbols will
not produce twenty completed round trips, and the UI is designed around that.

The Traditional Chinese strings below are factual statements of what was
measured and which gate closed -- no recommendation, no action verb. Their
final user-facing wording is still subject to risk-compliance review (送審範圍
20(d)), which is a review of the sentence, not of the thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.kelly.models import KellyGateReasonCode

#: CEO 2026-08-19 裁決：完整回合數門檻取 20（quant-researcher 建議 20，並列 50；
#: CEO 採 20 並要求強制揭露）。This is a risk-appetite decision, not a
#: statistical constant: raising it needs the same authority that set it, and
#: lowering it to make a demo or a test pass is out of the question.
MIN_OOS_ROUND_TRIPS = 20

#: Winning round trips required before a probability estimate is accepted.
MIN_OOS_WIN_TRIPS = 5

#: Losing round trips required before an average-loss denominator exists.
MIN_OOS_LOSS_TRIPS = 5

#: Below this many round trips the sample clears the hard gate but carries a
#: standing warning -- the 50 the quant note listed as the alternative hard
#: threshold, kept as the soft band once the CEO chose 20.
SOFT_WARNING_ROUND_TRIPS = 50

LOW_ROUND_TRIPS_MESSAGE = (
    "樣本外完整回合數為 {count} 筆，未達門檻 {threshold} 筆，本次不寫入 Kelly 輸入。"
)

LOW_WIN_TRIPS_MESSAGE = (
    "樣本外獲利回合數為 {count} 筆，未達門檻 {threshold} 筆，本次不寫入 Kelly 輸入。"
)

LOW_LOSS_TRIPS_MESSAGE = (
    "樣本外虧損回合數為 {count} 筆，未達門檻 {threshold} 筆，本次不寫入 Kelly 輸入。"
)

PB_NONE_MESSAGE = (
    "本次回測的樣本外勝率或賠率為 null（勝率 {win_rate}、賠率 {payoff_ratio}），"
    "沒有可寫入的數值。"
)

SYMBOL_MISMATCH_MESSAGE = (
    "路徑指定的標的為 {path_symbol}（{path_market}），"
    "回測請求的標的為 {body_symbol}（{body_market}），兩者不一致，本次不寫入。"
)

INSUFFICIENT_DATA_MESSAGE = (
    "回測結果狀態為 {status}，不是 ok，本次不寫入 Kelly 輸入。"
)


@dataclass(frozen=True)
class KellySampleGateReview:
    """The verdict on one import attempt.

    ``rejection`` is a 422 message when the write must not happen at all, and
    ``reason_code`` names which gate produced it -- the two always travel
    together, because a refusal the caller cannot classify is a refusal the log
    cannot count. ``low_sample_warning`` belongs to an *accepted* sample and is
    a disclosure flag only.
    """

    reason_code: KellyGateReasonCode | None = None
    rejection: str | None = None
    low_sample_warning: bool = False

    @property
    def passed(self) -> bool:
        """Whether this gate let the attempt through."""
        return self.rejection is None


def review_result_status(status: str) -> KellySampleGateReview:
    """Whether the backtest produced a usable result at all.

    Anything other than ``ok`` means the run itself could not answer, so there
    is no sample to size and no pair to store.
    """
    if status == "ok":
        return KellySampleGateReview()
    return KellySampleGateReview(
        reason_code="insufficient_data",
        rejection=INSUFFICIENT_DATA_MESSAGE.format(status=status),
    )


def review_symbol_match(
    *,
    path_symbol: str,
    path_market: str,
    body_symbol: str,
    body_market: str,
) -> KellySampleGateReview:
    """Whether the run measured the instrument the write is addressed to.

    Compared on the normalised ticker, so ``aapl`` and ``AAPL`` are the same
    instrument, and on the market, because the same ticker in two markets is
    two instruments. A mismatch is refused rather than resolved in either
    direction: guessing which one the user meant would file one symbol's
    evidence under another's name.
    """
    if (
        path_symbol.strip().upper() == body_symbol.strip().upper()
        and path_market == body_market
    ):
        return KellySampleGateReview()
    return KellySampleGateReview(
        reason_code="symbol_mismatch",
        rejection=SYMBOL_MISMATCH_MESSAGE.format(
            path_symbol=path_symbol,
            path_market=path_market,
            body_symbol=body_symbol,
            body_market=body_market,
        ),
    )


def review_estimates(
    win_rate: float | None, payoff_ratio: float | None
) -> KellySampleGateReview:
    """Whether both halves of the pair exist.

    Either one missing refuses the whole attempt: a Kelly input is the pair,
    and half of it is not a smaller input, it is none.
    """
    if win_rate is not None and payoff_ratio is not None:
        return KellySampleGateReview()
    return KellySampleGateReview(
        reason_code="pb_none",
        rejection=PB_NONE_MESSAGE.format(win_rate=win_rate, payoff_ratio=payoff_ratio),
    )


def review_sample(
    round_trips: int, win_trips: int, loss_trips: int
) -> KellySampleGateReview:
    """Check one out-of-sample round-trip count against the three thresholds.

    Order is total, then wins, then losses -- the order a reader would ask the
    questions in -- and the first gate that closes is the one reported, with
    the number actually observed. A sample that fails two gates is reported by
    the first, because raising the sample size is the one action that addresses
    either.

    A passing verdict carries ``low_sample_warning`` while the total sits in
    the soft band; the row stores that flag, so the disclosure survives the tab
    being closed.
    """
    if round_trips < MIN_OOS_ROUND_TRIPS:
        return KellySampleGateReview(
            reason_code="low_round_trips",
            rejection=LOW_ROUND_TRIPS_MESSAGE.format(
                count=round_trips, threshold=MIN_OOS_ROUND_TRIPS
            ),
        )
    if win_trips < MIN_OOS_WIN_TRIPS:
        return KellySampleGateReview(
            reason_code="low_win_trips",
            rejection=LOW_WIN_TRIPS_MESSAGE.format(
                count=win_trips, threshold=MIN_OOS_WIN_TRIPS
            ),
        )
    if loss_trips < MIN_OOS_LOSS_TRIPS:
        return KellySampleGateReview(
            reason_code="low_loss_trips",
            rejection=LOW_LOSS_TRIPS_MESSAGE.format(
                count=loss_trips, threshold=MIN_OOS_LOSS_TRIPS
            ),
        )
    return KellySampleGateReview(
        low_sample_warning=round_trips < SOFT_WARNING_ROUND_TRIPS
    )
