"""Sanity rules for the account net worth a user reports (FR-9 (c)).

The value goes straight under the gross-exposure cap as its denominator, so a
mistyped one does not produce a visibly wrong number -- it produces a cap that
looks like it is working. Three bands, and none of them silently rewrites what
was typed (the same stance ``app/advice/limits.py`` takes on its ceilings: a
corrected number is one the user would later believe they had set):

* ``<= 0`` -- rejected by :class:`app.settings.models.NetWorthInput` before this
  module is reached; a ratio has no meaning with that denominator.
* below 95% of the valued book -- **rejected** here. Such a figure makes the
  exposure permanently exceed 100%, and in practice it is a cash balance or a
  single account's balance typed into a whole-account field. The 5% tolerance
  covers the ordinary gap between a close-based valuation and what a broker app
  showed a moment ago.
* above 10x the valued book -- **accepted with a prominent warning**. Holding
  mostly cash is perfectly legitimate and must not be refused; an inflated net
  worth, however, makes the cap agree with everything forever, and the user is
  the only one who can tell the two apart.

The comparison is against the **valued** book, which is all this product can
measure. When nothing could be valued there is no yardstick at all, so only the
positive-number rule applies and the response says so rather than implying the
figure was checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: A report below this multiple of the valued book is refused (FR-9 (c) row 2).
NET_WORTH_MIN_RATIO = 0.95

#: A report above this multiple of the valued book is warned about (row 3).
NET_WORTH_WARN_RATIO = 10.0

NET_WORTH_BELOW_BOOK_MESSAGE = (
    "自報淨值小於系統已估值的部位市值：你輸入新台幣 {amount:,.0f} 元，"
    "系統目前已估值的部位市值為新台幣 {valued:,.0f} 元（已保留 {tolerance:.0%} 的容差）。"
    "以這個數字計算，總曝險會恆為超過 100%；常見原因是填成了現金餘額或單一帳戶餘額。"
    "系統不會自行調整這個數字，請確認後重新輸入帳戶總淨值（新台幣）。"
)

NET_WORTH_FAR_ABOVE_BOOK_WARNING = (
    "你輸入的帳戶總淨值為系統已估值部位市值的 {multiple:,.1f} 倍"
    "（輸入新台幣 {amount:,.0f} 元，已估值部位市值新台幣 {valued:,.0f} 元）。"
    "持有大量現金是合理情況，此數值已照你輸入的存下；"
    "但若此數字有誤，第 3 條上限將失去意義——曝險比率會恆為遠低於上限。"
    "請確認金額單位為新台幣元。"
)

NET_WORTH_NO_VALUED_BOOK_NOTE = (
    "目前沒有任何部位可估值，無法用部位市值檢查這個數字是否合理；"
    "本次只檢查了數值必須大於 0。"
)

NET_WORTH_PARTIAL_BOOK_NOTE = (
    "有 {missing} 筆部位無法估值，本次的合理性檢查只比對了已估值的 {valued} 筆；"
    "比對基準因此偏低。"
)


@dataclass(frozen=True)
class NetWorthReview:
    """The verdict on one reported figure.

    ``rejection`` is a 422 message when the write must not happen at all;
    ``warnings`` are things the user has to see about a value that *was*
    stored; ``notes`` state what the check itself could and could not cover.
    """

    rejection: str | None = None
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def review_net_worth(
    amount_twd: float,
    *,
    valued_market_value_twd: float,
    valued_count: int,
    total_count: int,
) -> NetWorthReview:
    """Check one reported net worth against the book it will be divided into.

    ``amount_twd`` is assumed positive (the input model enforces that). The
    relative bands need a yardstick, so with ``valued_count == 0`` they are
    skipped and said to be skipped instead of being applied to a zero that
    would reject or warn about everything.
    """
    notes: list[str] = []
    if valued_count == 0 or valued_market_value_twd <= 0.0:
        return NetWorthReview(notes=[NET_WORTH_NO_VALUED_BOOK_NOTE])

    if valued_count < total_count:
        notes.append(
            NET_WORTH_PARTIAL_BOOK_NOTE.format(
                missing=total_count - valued_count, valued=valued_count
            )
        )

    if amount_twd < valued_market_value_twd * NET_WORTH_MIN_RATIO:
        return NetWorthReview(
            rejection=NET_WORTH_BELOW_BOOK_MESSAGE.format(
                amount=amount_twd,
                valued=valued_market_value_twd,
                tolerance=1.0 - NET_WORTH_MIN_RATIO,
            ),
            notes=notes,
        )

    warnings: list[str] = []
    if amount_twd > valued_market_value_twd * NET_WORTH_WARN_RATIO:
        warnings.append(
            NET_WORTH_FAR_ABOVE_BOOK_WARNING.format(
                multiple=amount_twd / valued_market_value_twd,
                amount=amount_twd,
                valued=valued_market_value_twd,
            )
        )
    return NetWorthReview(warnings=warnings, notes=notes)
