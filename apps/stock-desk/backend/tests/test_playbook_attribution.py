"""歸屬語 (風控 R2) and the 情境 1 blocking path, through the wired service.

覆審裁決 (2026-08-12) settled three states and this file pins all of them:

* **情境 1 -- no user record.** The 歸屬語 is not shown at all and the module
  produces no rule-driven directive. The verdict comes from an explicit record,
  never from a date: a system default carries an effective date too, and reading
  authorship out of one would put the user's name on rules they never wrote. The
  day gets its own mode (``unconfirmed``) and, when shares are still held, says
  that their S/P evaluation did not happen (三輪定稿 題 9/題 10).
* **情境 2 -- record present, date unreadable.** The sentence is the full one
  with the single permitted status string in place of the date.
* **The normal case.** The date is the 規則版本生效日 and nothing else.

The escape hatch is deliberately outside the gate (CEO EX-2/EX-4): its lines
come from an action the user just submitted, and a precondition on the exit is
the one thing the exit may not have. 三輪定稿 題 7 goes one step further -- the
exit does not consult authorship at all and carries its own attribution sentence.
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
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore, system_default_params
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import RULE_SET_DATE, TUESDAY, confirm_rule_set

SERIES_END = date(2026, 8, 14)
HISTORY = 40


@dataclass
class Harness:
    service: PlaybookService
    store: PlaybookStore
    #: The fakes themselves, so a test can assert what was *not* fetched.
    prices: FakePriceService
    index: FakePriceService


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    prices = FakePriceService()
    prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=SERIES_END))
    prices.seed("2454", recent_bars([50.0] * HISTORY, symbol="2454", end=SERIES_END))
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
        prices=prices,
        index=index,
    )


def _hold_a_batch(store: PlaybookStore, symbol: str = "2330", batch_no: int = 1) -> None:
    batch = store.get_batch(symbol, batch_no)
    assert batch is not None
    store.save_batch(
        batch.model_copy(
            update={
                "status": "open",
                "entry_date": date(2026, 7, 1),
                "cost": Decimal("100"),
                "shares": 300,
                "remaining_shares": 300,
                "peak_close": Decimal("100"),
            }
        )
    )


# --- 情境 1: 無使用者紀錄 -----------------------------------------------------


def test_without_a_confirmed_rule_set_no_directive_is_produced(
    harness: Harness,
) -> None:
    """定稿: 在你確認規則集之前不產生任何指令."""
    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.directives == []
    assert evaluation.attribution == wording.ATTRIBUTION_NO_USER_RULES
    assert evaluation.mode_reason == wording.ATTRIBUTION_NO_USER_RULES
    # 阻斷是「不產生」，不是「產生了但不顯示」：指令留存也必須是空的 (R16).
    assert harness.store.directive_log() == []


def test_the_unconfirmed_state_is_its_own_mode_and_not_normal(
    harness: Harness,
) -> None:
    """題 10: 不得沿用 normal——不產生規則驅動指令的一天不是「正常」."""
    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.mode != "normal"
    assert evaluation.mode == "unconfirmed"
    assert wording.MODE_LABELS[evaluation.mode] == "待確認規則集"


def test_a_held_position_is_disclosed_while_the_rule_set_is_unconfirmed(
    harness: Harness,
) -> None:
    """題 9: 阻斷同時停掉 S/P，未出清批次的未評估狀態必須主動說出來."""
    harness.store.ensure_batches(["2454"], batches_per_target=3)
    _hold_a_batch(harness.store, "2330")
    _hold_a_batch(harness.store, "2454")

    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.directives == []
    assert evaluation.warnings == [
        wording.UNAUTHORED_HOLDING_NOTE.format(symbols="2330、2454")
    ]
    # {symbols} 全列不截斷：每一檔持倉都要看得到。
    assert "2330" in evaluation.warnings[0] and "2454" in evaluation.warnings[0]
    # 僅存在性檢查：不載行情、不留痕。
    assert harness.prices.calls == []
    assert harness.index.calls == []
    assert harness.store.directive_log() == []


def test_a_book_with_nothing_left_to_sell_carries_no_holding_disclosure(
    harness: Harness,
) -> None:
    """存在性檢查看的是未出清的批次，不是曾經有過部位：出清完就不再揭露."""
    _hold_a_batch(harness.store)
    batch = harness.store.get_batch("2330", 1)
    assert batch is not None
    harness.store.save_batch(
        batch.model_copy(update={"status": "closed", "remaining_shares": 0})
    )

    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.warnings == []
    assert evaluation.attribution == wording.ATTRIBUTION_NO_USER_RULES


def test_the_block_lifts_the_moment_the_user_confirms_the_rule_set(
    harness: Harness,
) -> None:
    confirm_rule_set(harness.store)

    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert [item.rule_id for item in evaluation.directives] == ["R1"]
    assert evaluation.attribution == (
        f"此指令是你於 {RULE_SET_DATE.isoformat()} 自行設定的規則之機械執行結果，"
        "非本系統的判斷或建議。"
    )


def test_authorship_is_a_flag_and_not_an_inference_from_a_date(
    harness: Harness,
) -> None:
    """判定用明確旗標，不得由日期反推：預設參數集同樣帶著一個生效日."""
    default = system_default_params(TUESDAY)
    assert default.effective_date == TUESDAY  # 預設值也有日期
    assert harness.store.active_params(TUESDAY) == default  # fallback 仍可算數
    assert harness.store.rule_set_authorship(TUESDAY).user_authored is False


def test_a_submitted_rule_change_counts_as_an_authorship_record(
    harness: Harness,
) -> None:
    """「尚無你本人的設定或修改紀錄」：修改紀錄同樣是本人紀錄."""
    from app.playbook.service import request_rule_change
    from tests import playbook_helpers as helper

    request_rule_change(
        store=harness.store,
        calendar=helper.calendar(),
        changes={"s1_ratio": Decimal("0.95")},
        submitted_at=date(2026, 1, 5),
    )

    assert harness.store.rule_set_authorship(TUESDAY).user_authored is True


# --- 情境 2: 有紀錄、日期讀不到 -----------------------------------------------


def test_an_unreadable_effective_date_falls_back_to_the_status_sentence(
    harness: Harness,
) -> None:
    confirmed = confirm_rule_set(harness.store)
    with sqlite3.connect(harness.store.db_path) as conn:
        conn.execute("UPDATE playbook_rule_params SET effective_date = 'n/a'")

    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.attribution == (
        "此指令是你自行設定的規則之機械執行結果，非本系統的判斷或建議"
        f"（規則設定日期缺漏：規則版本 {confirmed.version} 的生效日期讀取失敗）。"
    )
    # 仍然是有紀錄的狀態，指令照常產生，阻斷句不得出現。
    assert evaluation.directives
    assert wording.ATTRIBUTION_NO_USER_RULES not in evaluation.attribution


# --- 出口不受閘門限制 ---------------------------------------------------------


def test_the_emergency_exit_is_not_gated_on_the_rule_set_confirmation(
    harness: Harness,
) -> None:
    """EX-2/EX-4: 出口零摩擦——指令來自使用者剛提交的動作，不是系統代持的規則."""
    _hold_a_batch(harness.store)

    result = harness.service.emergency_exit(today=TUESDAY)

    assert result.total_shares == 300
    assert [item.action for item in result.directives] == ["sell"]
    # 題 7: 未確認規則集也照樣產出指令，且回應裡零阻斷句——阻斷句與剛產出的指令
    # 互相矛盾，出現一次就是誤導。
    assert result.attribution == wording.EXIT_ATTRIBUTION
    rendered = " ".join([result.message, result.mode_reason, *result.warnings])
    assert wording.ATTRIBUTION_NO_USER_RULES not in rendered
    assert "在你確認規則集之前" not in rendered
    assert "在你確認規則集之前" not in (result.attribution or "")


def test_the_exit_attribution_is_the_same_sentence_once_the_rules_are_confirmed(
    harness: Harness,
) -> None:
    """題 7: EXIT 一律用專用句，不看 authorship——兩種狀態下字面必須相同."""
    _hold_a_batch(harness.store)
    unconfirmed = harness.service.emergency_exit(today=TUESDAY)
    confirm_rule_set(harness.store)

    confirmed = harness.service.emergency_exit(today=TUESDAY)

    assert confirmed.attribution == unconfirmed.attribution == wording.EXIT_ATTRIBUTION
    # 規則集的生效日與 EXIT 無關，不得被寫進出口的歸屬語。
    assert RULE_SET_DATE.isoformat() not in (confirmed.attribution or "")


def test_an_exit_with_nothing_held_renders_no_attribution_at_all(
    harness: Harness,
) -> None:
    """題 7 EMPTY 分支: 沒有指令就沒有可歸屬的對象，整句不渲染."""
    confirm_rule_set(harness.store)

    result = harness.service.emergency_exit(today=TUESDAY)

    assert result.directives == []
    assert result.attribution is None
    assert "目前無持有批次，未產生賣出指令" in result.message
    # 凍結仍然成立，只是沒有任何歸屬語可講。
    assert "機械執行結果" not in result.message


def test_the_exit_confirmation_is_rendered_while_the_rule_set_is_unconfirmed(
    harness: Harness,
) -> None:
    """EX-2: 出口在情境 1 也開著，確認畫面的四句與凍結天數不得因此消失."""
    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.directives == []
    assert evaluation.exit_confirm is not None
    assert evaluation.exit_confirm.freeze_days == 20
    assert evaluation.exit_confirm.checks == list(
        wording.exit_confirm_checks(
            freeze_days=20, freeze_until=evaluation.exit_confirm.freeze_until
        )
    )
    # 存在性檢查那一天仍然不載行情，凍結日只靠參數與日曆的假日外推。
    assert harness.prices.calls == []
    assert harness.index.calls == []


def test_the_exit_line_carries_its_own_no_band_sentence(harness: Harness) -> None:
    """定稿: service 的 EXIT 指令不得再掛停損句."""
    confirm_rule_set(harness.store)
    _hold_a_batch(harness.store)

    result = harness.service.emergency_exit(today=TUESDAY)

    (directive,) = result.directives
    assert directive.limit_note == wording.EMERGENCY_EXIT_NO_BAND_NOTE
    assert directive.limit_note != wording.STOP_LOSS_NO_BAND_NOTE
    assert "S/P 系列停損停利仍照常評估。" in directive.rule_summary


def test_the_exit_mode_line_is_rendered_for_today_not_stored(
    harness: Harness,
) -> None:
    """mode_reason 禁存快照字串：出口回報的模式句是當天算出來的第 1 個交易日."""
    confirm_rule_set(harness.store)
    _hold_a_batch(harness.store)

    result = harness.service.emergency_exit(today=TUESDAY)

    assert "第 1/20 交易日" in result.mode_reason
    assert result.mode_reason != result.message
    # The stored log keeps the instruction, never the day counter as a fact.
    assert all("第 1/20" not in str(row) for row in harness.store.directive_log())
