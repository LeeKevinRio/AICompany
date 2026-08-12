"""The playbook's own price-level field table (風控 required R19).

R19 asks for a **two-track** separation of price fields: the advice card keeps
its single-entry allowlist (:data:`app.advice.context.PRICE_FIELD_ALLOWLIST`,
length 1, not to be extended), and the playbook declares its own table here.
The two are never merged and never imported into each other -- the playbook may
not read the advice package at all (R4, enforced by
``tests/test_playbook_boundary.py``), so this file duplicates nothing: it is the
complete list of price-level numbers a playbook payload may carry.

Every entry states, item by item, whether its **input** contains a market view
(判斷／評分／建議引擎輸出). All of them are ``False`` today and that is the
point of the column: a future field whose number comes from an opinion has to be
marked ``True`` here, and the guard test then fails, rather than the opinion
travelling quietly inside a 指令.

"Contains a market view" means the number was produced by *judging* the market.
A close, a cost and an arithmetic band around a close are measurements or the
user's own arithmetic; none of them is a judgement about where the price should
go.
"""

from __future__ import annotations

from typing import NamedTuple


class PriceFieldSpec(NamedTuple):
    """One price-level field of a playbook payload."""

    #: Which payload carries it: the 今日指令表 line or the 部位快照 row.
    payload: str
    label: str
    #: What the number is computed from, in the user's own terms.
    input_source: str
    #: Whether the input contains a market view (judgement / score / advice).
    contains_market_view: bool


#: The 今日指令表 line payload.
DIRECTIVE_PAYLOAD = "directive"
#: The 部位快照 row payload.
SNAPSHOT_PAYLOAD = "snapshot"

#: Every price-level field the playbook emits, with its market-view annotation.
PLAYBOOK_PRICE_FIELDS: dict[str, PriceFieldSpec] = {
    "reference_price": PriceFieldSpec(
        payload=DIRECTIVE_PAYLOAD,
        label="參考價",
        input_source="依據資料日 T 的日線收盤價，原值照抄",
        contains_market_view=False,
    ),
    "limit_low": PriceFieldSpec(
        payload=DIRECTIVE_PAYLOAD,
        label="限價帶下緣",
        input_source="參考價 ×(1 − 滑價帶%)，滑價帶為使用者規則參數",
        contains_market_view=False,
    ),
    "limit_high": PriceFieldSpec(
        payload=DIRECTIVE_PAYLOAD,
        label="限價帶上緣",
        input_source="參考價 ×(1 + 滑價帶%)，滑價帶為使用者規則參數",
        contains_market_view=False,
    ),
    "cost": PriceFieldSpec(
        payload=SNAPSHOT_PAYLOAD,
        label="該批成本",
        input_source="該批實際成交價（T+1 結算寫入），非估算",
        contains_market_view=False,
    ),
    "close": PriceFieldSpec(
        payload=SNAPSHOT_PAYLOAD,
        label="依據資料日收盤價",
        input_source="依據資料日 T 的日線收盤價，原值照抄",
        contains_market_view=False,
    ),
    "peak_close": PriceFieldSpec(
        payload=SNAPSHOT_PAYLOAD,
        label="波段最高收盤",
        input_source="進場後每交易日收盤價的最大值，逐日累進",
        contains_market_view=False,
    ),
}


def fields_of(payload: str) -> frozenset[str]:
    """Names of the price-level fields carried by one payload."""
    return frozenset(
        name for name, spec in PLAYBOOK_PRICE_FIELDS.items() if spec.payload == payload
    )


#: The price fields of one 指令 line -- the payload R19's separation is about.
DIRECTIVE_PRICE_FIELDS: frozenset[str] = fields_of(DIRECTIVE_PAYLOAD)

#: The price fields of one 部位快照 row.
SNAPSHOT_PRICE_FIELDS: frozenset[str] = fields_of(SNAPSHOT_PAYLOAD)
