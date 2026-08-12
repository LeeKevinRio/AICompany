"""§6 頁面免責句 and the 題 12 完整性旗標 (四輪收斂裁決 2026-08-12).

Two rulings are pinned here, both about telling a *stated* fact apart from an
*absent* one:

* **§6 三句** -- the page says which closing data it was computed from, which
  rule version is in force (three branches, decided by the authorship record and
  fail-closed to the 讀取失敗 branch), and that the lines are the user's own
  rules executed mechanically. ``rules_effective_date`` may only ever be the
  ``effective_date`` of the stored row in force: the system-default parameter
  set carries a date too, and letting that one through would put a date the user
  never chose next to their name.
* **題 12 完整性旗標** -- an empty ledger only gets 「今日規則已全數評估，無任何
  規則命中」 when every R/S/P input really was available and every series really
  was evaluated. Every other day keeps the bare 「無。」, so 未命中 and 未評估
  can be told apart instead of collapsing into the same blank.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.playbook import wording
from app.playbook.engine import evaluate
from app.playbook.models import PlaybookEvaluation, SymbolState
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests import playbook_helpers as helper
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import FRIDAY, RULE_SET_DATE, TUESDAY, confirm_rule_set

SERIES_END = date(2026, 8, 14)
HISTORY = 40


@dataclass
class Harness:
    service: PlaybookService
    store: PlaybookStore


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    prices = FakePriceService()
    prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=SERIES_END))
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    store.ensure_batches(["2330"], batches_per_target=3)
    store.set_capital(
        cash=Decimal("1000000"), total_deploy=Decimal("1000000"), source="initial"
    )
    yield Harness(
        service=PlaybookService(
            store=store,
            market_resolver={"TW": prices},
            index_resolver={"TW": index, "US": index},
        ),
        store=store,
    )


# --- §6 三句 -----------------------------------------------------------------


def test_the_page_summary_is_three_sentences_in_the_ruled_order() -> None:
    summary = wording.page_summary(
        data_date=TUESDAY,
        rules_version=1,
        rules_effective_date=RULE_SET_DATE,
        user_authored=True,
    )

    assert summary == [
        "本頁面指令依 2026-08-11 收盤資料計算。",
        "採用規則版本 1（生效日 2026-01-01）。",
        "今日指令帳冊中的每筆指令是你自行設定的規則之機械執行結果，"
        "非本系統的判斷或建議；實際成交結果以你的券商回報為準。",
    ]


def test_an_unreadable_effective_date_takes_branch_b() -> None:
    summary = wording.page_summary(
        data_date=TUESDAY, rules_version=4, rules_effective_date=None, user_authored=True
    )

    assert summary[1] == "規則版本 4 的生效日期讀取失敗。"


def test_an_unauthored_rule_set_takes_branch_c_verbatim() -> None:
    summary = wording.page_summary(
        data_date=TUESDAY, rules_version=0, rules_effective_date=None, user_authored=False
    )

    assert summary[1] == wording.ATTRIBUTION_NO_USER_RULES_FIRST
    # 「首句」是逐字沿用，不是另寫一句相似的：兩者必須同源。
    assert wording.ATTRIBUTION_NO_USER_RULES.startswith(summary[1])


def test_an_undeterminable_authorship_fails_closed_to_branch_b() -> None:
    """裁決: 判定用 user_authored，無法判定 fail-closed 走 (b)."""
    summary = wording.page_summary(
        data_date=TUESDAY,
        rules_version=2,
        # 日期讀得到，但作者身分判不出來——仍然不得宣稱 (a)。
        rules_effective_date=RULE_SET_DATE,
        user_authored=None,
    )

    assert summary[1] == "規則版本 2 的生效日期讀取失敗。"
    assert RULE_SET_DATE.isoformat() not in summary[1]


def test_the_page_summary_carries_no_unresolved_placeholder() -> None:
    for authored in (True, False, None):
        for effective in (RULE_SET_DATE, None):
            for sentence in wording.page_summary(
                data_date=TUESDAY,
                rules_version=1,
                rules_effective_date=effective,
                user_authored=authored,
            ):
                assert "{" not in sentence


def test_the_service_binds_the_first_sentence_to_the_data_date(
    harness: Harness,
) -> None:
    """① 綁 data_date（依據資料日），不是呼叫當天."""
    confirm_rule_set(harness.store)

    evaluation = harness.service.evaluate_today(today=date(2026, 8, 17))

    assert evaluation.data_date == SERIES_END
    assert evaluation.page_summary[0] == f"本頁面指令依 {SERIES_END.isoformat()} 收盤資料計算。"


def test_the_effective_date_comes_from_the_row_in_force_not_from_the_default(
    harness: Harness,
) -> None:
    """禁推斷頂替: 預設參數集也帶生效日，但那不是使用者規則集的生效日."""
    assert harness.store.active_params(TUESDAY).effective_date == TUESDAY
    assert harness.store.in_force_effective_date(TUESDAY) is None

    confirm_rule_set(harness.store)

    assert harness.store.in_force_effective_date(TUESDAY) == RULE_SET_DATE


def test_an_unreadable_stored_date_is_a_gap_and_not_a_guess(
    harness: Harness,
) -> None:
    confirm_rule_set(harness.store)
    with sqlite3.connect(harness.store.db_path) as conn:
        conn.execute("UPDATE playbook_rule_params SET effective_date = 'n/a'")

    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.rules_effective_date is None
    assert evaluation.page_summary[1] == (
        f"規則版本 {evaluation.rules_version} 的生效日期讀取失敗。"
    )


def test_the_unconfirmed_path_still_carries_the_page_summary(
    harness: Harness,
) -> None:
    """§6 不可缺：待確認規則集的一天同樣要說明本頁依據什麼算出來."""
    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.rules_effective_date is None
    assert evaluation.page_summary[1] == wording.ATTRIBUTION_NO_USER_RULES_FIRST
    assert len(evaluation.page_summary) == 3


# --- 題 12 完整性旗標 ---------------------------------------------------------


def _run(**overrides: object) -> PlaybookEvaluation:
    """One evaluation whose defaults are the 全數評估 case: 排程日、資料齊、無命中."""
    kwargs: dict[str, object] = {
        "data_date": TUESDAY,
        "calendar": helper.calendar(),
        "params": helper.params(),
        "index": helper.index(data_date=TUESDAY),
        "markets": {"2330": helper.market(close="100")},
        # 三批都已進場且無任何規則命中：R 沒有下一批可買，S/P 也沒有觸價。
        "batches": [
            helper.batch(batch_no=1, cost="100", shares=100),
            helper.batch(batch_no=2, cost="100", shares=100),
            helper.batch(batch_no=3, cost="100", shares=100),
        ],
        "symbols": {},
        "portfolio": helper.portfolio(),
    }
    kwargs.update(overrides)
    return evaluate(**kwargs)  # type: ignore[arg-type]


def test_a_fully_evaluated_day_with_no_hit_sets_the_flag() -> None:
    evaluation = _run()

    assert evaluation.directives == []
    assert evaluation.rules_fully_evaluated is True


def test_a_data_gap_clears_the_flag() -> None:
    """未評估不得被說成未命中：資料不可用的一天旗標必須是 False."""
    evaluation = _run(markets={"2330": helper.market(close="100", status="unavailable")})

    assert evaluation.directives == []
    assert evaluation.rules_fully_evaluated is False


def test_a_non_schedule_day_clears_the_flag() -> None:
    evaluation = _run(data_date=FRIDAY, index=helper.index(data_date=FRIDAY))

    assert evaluation.is_schedule_day is False
    assert evaluation.rules_fully_evaluated is False


def test_an_index_gap_clears_the_flag() -> None:
    evaluation = _run(index=helper.index(status="unavailable", source="none"))

    assert evaluation.rules_fully_evaluated is False


def test_a_frozen_book_clears_the_flag() -> None:
    evaluation = _run(
        portfolio=helper.portfolio(
            freeze_until=date(2026, 8, 20), freeze_reason="S3 熔斷"
        )
    )

    assert evaluation.mode == "frozen"
    assert evaluation.rules_fully_evaluated is False


def test_a_paused_or_blacklisted_symbol_clears_the_flag() -> None:
    """R 系列今天沒為這檔評估過，就不算「全數評估」."""
    paused = _run(
        # 收盤仍在 25MA 之下，所以 S1 的排程暫停今天沒有解除（站回 25MA 會解除，
        # 那一天 R 系列就評估得到，旗標也就不該被這個理由關掉）。
        markets={"2330": helper.market(close="95", ma25="100", bias25="-5")},
        symbols={"2330": SymbolState(symbol="2330", paused=True)},
    )
    blacklisted = _run(
        symbols={
            "2330": SymbolState(
                symbol="2330", blacklisted=True, blacklist_until=date(2026, 12, 1)
            )
        }
    )

    assert paused.rules_fully_evaluated is False
    assert blacklisted.rules_fully_evaluated is False


def test_an_empty_book_clears_the_flag() -> None:
    """沒有帳冊可評估的一天，「全數評估」是空話."""
    evaluation = _run(batches=[])

    assert evaluation.rules_fully_evaluated is False


def test_a_cash_floor_shrink_clears_the_flag() -> None:
    """鐵律①動過的進場是規則命中，不能被說成無任何規則命中."""
    evaluation = _run(
        batches=[helper.planned()],
        portfolio=helper.portfolio(cash="1000", total_deploy="1000000"),
    )

    assert any("鐵律①" in warning for warning in evaluation.warnings)
    assert evaluation.rules_fully_evaluated is False


def test_the_flag_is_not_read_out_of_the_warning_text() -> None:
    """allowlist 而非字串黑名單：旗標為真的一天不靠「沒有出現某句話」成立."""
    evaluation = _run()

    assert evaluation.rules_fully_evaluated is True
    # 非排程日提示本來就會出現在許多天；旗標與這類句子沒有耦合關係。
    assert not any(
        warning.startswith(wording.NOT_SCHEDULE_DAY_NOTE[:6])
        for warning in evaluation.warnings
    )
