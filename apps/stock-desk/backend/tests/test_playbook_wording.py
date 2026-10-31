"""The sentences risk-compliance signed off, pinned as tests.

Every assertion here traces to `work/reviews/快市排程-風控前置意見.md`
「覆審裁決(2026-08-12 二輪)」. Two kinds of test live in this file:

* **逐字**: the approved wording is present in the string the module emits, and
  the wording the review vetoed is absent from it. A sentence that drifts by one
  clause is a compliance regression, not a cosmetic one.
* **守門**: no threshold in :data:`app.playbook.wording.RULE_TEXT` may be a
  literal. Every number a rendered rule restatement shows has to come from the
  :class:`RuleParams` version in force, checked against a second, deliberately
  different parameter set so a forgotten literal cannot pass by coincidence.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from app.data.calendar import TradingCalendar
from app.playbook import wording
from app.playbook.engine import emergency_frozen_day
from app.playbook.models import Directive, RuleParams, RuleSetAuthorship
from tests import playbook_helpers as helper

#: Digits that belong to a *name* rather than to a threshold: the rule ids
#: themselves, the indicator names and the fractions the rule set writes out.
_NAME_TOKENS = tuple(sorted((*wording.RULE_TEXT, "BIAS25", "25MA", "1/3"), key=len, reverse=True))

#: A second parameter set with every threshold moved somewhere it could not be
#: confused with a default. If a literal survived in a sentence, rendering with
#: these makes it stand out as a number no parameter holds.
ALTERED = RuleParams(
    effective_date=date(2026, 2, 2),
    version=9,
    cash_floor_ratio=Decimal("0.25"),
    deploy_ratio=Decimal("0.66"),
    r2_change_pct_limit=Decimal("4"),
    r2_bias_limit=Decimal("11"),
    r3_max_defers=7,
    s1_ratio=Decimal("0.88"),
    s1_defense_ratio=Decimal("0.91"),
    s2_ratio=Decimal("0.82"),
    s2_blacklist_trading_days=45,
    s3_unrealized_pct=Decimal("-9"),
    s3_freeze_trading_days=12,
    p1_ratio=Decimal("1.18"),
    p2_ratio=Decimal("1.33"),
    p2_trailing_peak_ratio=Decimal("0.86"),
    p3_bias_limit=Decimal("14"),
    p3_bias_limit_high_vol=Decimal("19"),
    p3_cooldown_trading_days=8,
    m1_consecutive_days=4,
    emergency_freeze_trading_days=15,
)


def _numbers(text: str) -> list[str]:
    """Every number a reader sees, with names (rule ids, indicators) removed."""
    stripped = text
    for token in _NAME_TOKENS:
        stripped = stripped.replace(token, "")
    return re.findall(r"-?\d+(?:\.\d+)?", stripped)


def _thresholds_of(params: RuleParams) -> set[str]:
    """Every rendering a threshold of ``params`` may legitimately appear as.

    Each threshold is normalised before it is formatted. ``Decimal`` keeps the
    scale of an arithmetic result (``0.30 × 100`` is ``30.00``, and ``:g`` on a
    ``Decimal`` preserves the trailing zeros rather than dropping them), so
    formatting the raw values put strings like ``30.00`` into the allowed set --
    renderings no sentence produces, which is exactly the room a hard-coded
    literal could hide in. ``normalize`` may hand back an exponent form
    (``Decimal("6E+1")``), so ``:f`` is what writes the digits out.
    """
    allowed: set[str] = set()
    for value in params.model_dump().values():
        if isinstance(value, bool) or not isinstance(value, Decimal | int | float):
            continue
        number = Decimal(str(value)).normalize()
        scaled = (number * 100).normalize()
        allowed.update({f"{number:f}", f"{number:.2f}", f"{scaled:f}"})
    return allowed


@pytest.mark.parametrize("params", [helper.params(), ALTERED])
@pytest.mark.parametrize("rule_id", sorted(wording.RULE_TEXT))
def test_every_number_in_a_rule_restatement_comes_from_the_active_params(
    rule_id: str, params: RuleParams
) -> None:
    """守門: 渲染出來的數字必須等於 active_params，沒有任何硬編門檻."""
    allowed = _thresholds_of(params)
    rendered = wording.rule_text(rule_id, params)
    for number in _numbers(rendered):
        assert number in allowed, f"{rule_id}：{number} 不是 active_params 的任何門檻"


def test_a_dated_rule_change_moves_every_restatement_with_it() -> None:
    """門檻換版後，規則說明句跟著換，不會留著上一版的數字."""
    assert "60" in wording.rule_text("S2", helper.params())
    assert "45" in wording.rule_text("S2", ALTERED)
    assert "60" not in wording.rule_text("S2", ALTERED)
    assert "20" in wording.rule_text("EMERGENCY", helper.params())
    assert "15" in wording.rule_text("EMERGENCY", ALTERED)


def test_the_emergency_rule_text_states_the_r_series_scope() -> None:
    """VETO-1: 引擎只凍 R 系列，規則說明不得寫成「所有排程凍結」."""
    text = wording.rule_text("EMERGENCY", helper.params())
    assert text == (
        "EMERGENCY_EXIT：使用者提交全部出清，系統產生全部持倉的賣出指令，"
        "並自提交日起暫停 R 系列（新倉進場）20 交易日；S/P 系列停損停利仍照常評估。"
    )
    assert "所有排程" not in text


def test_the_s2_rule_text_says_the_blacklist_only_blocks_buying() -> None:
    """S-3: 黑名單只封買進，殘留批次的 S/P 仍照常評估."""
    text = wording.rule_text("S2", helper.params())
    assert "黑名單期間僅停止新增買進（R 系列）" in text
    assert "S/P 系列停損停利仍照常評估。" in text


def test_the_iron1_rule_text_states_the_cash_floor_as_a_parameter() -> None:
    """鐵律①的兩處百分比都來自 cash_floor_ratio，且句子逐字不變（qa 順修補 pin）."""
    assert wording.rule_text("IRON1", helper.params()) == (
        "鐵律①現金 30% 不可破：進場金額使現金低於 30% 時縮減該批股數。"
    )
    # 換版後兩處一起走，且不留上一版的數字；30.00 這種尾零渲染同樣不得出現。
    altered = wording.rule_text("IRON1", ALTERED)
    assert altered == "鐵律①現金 25% 不可破：進場金額使現金低於 25% 時縮減該批股數。"
    assert "30" not in altered
    assert "25.00" not in altered


def test_the_rebalance_rule_text_says_it_takes_effect_immediately() -> None:
    text = wording.rule_text("REBALANCE", helper.params())
    assert text == (
        "季末 REBALANCE：由使用者在季末提交，以提交當日總資產重算 "
        "TOTAL_DEPLOY=總資產 ×70%，重算後立即生效；期中已實現獲利不滾入批量。"
    )


# --- EMERGENCY_EXIT 回報與模式句 ----------------------------------------------


def test_the_exit_result_is_an_acceptance_not_a_completion() -> None:
    """定稿: 「已受理」而非「已執行/出清」，並附市價單失效條件與券商回報為準."""
    message = wording.EMERGENCY_EXIT_RESULT.format(
        batches=2,
        shares=500,
        execution_date="2026-08-13",
        executed_at="2026-08-12",
        freeze_days=20,
        until="2026-09-09",
    )
    assert message.startswith("EMERGENCY_EXIT 已受理：")
    assert "已執行" not in message
    assert "出清 " not in message
    assert "市價單在跌停或無量時可能無法成交" in message
    assert "實際成交結果以你的券商回報為準" in message
    assert "S/P 系列停損停利仍照常評估。" in message
    assert "所有排程" not in message


def test_the_empty_exit_result_says_no_line_was_produced() -> None:
    message = wording.EMERGENCY_EXIT_EMPTY.format(
        executed_at="2026-08-12", freeze_days=20, until="2026-09-09"
    )
    assert "目前無持有批次，未產生賣出指令" in message
    assert "已執行" not in message


def test_the_frozen_day_counter_is_recomputed_for_the_day_it_is_shown_on() -> None:
    """定稿: {frozen_day} 每次渲染依 TradingCalendar 即時算，禁存快照字串."""
    calendar = helper.calendar()
    until = calendar.shift(helper.TUESDAY, 20)

    def day_of(data_date: date) -> int:
        return emergency_frozen_day(
            calendar=calendar, data_date=data_date, until=until, freeze_days=20
        )

    assert day_of(helper.TUESDAY) == 1
    assert day_of(helper.WEDNESDAY) == 1
    assert day_of(calendar.shift(helper.TUESDAY, 5)) == 5
    assert day_of(until) == 20
    line = wording.mode_reason_emergency(frozen_day=5, freeze_days=20, until=until)
    assert "第 5/20 交易日" in line
    assert "R 系列（新倉進場）暫停中" in line
    assert "S/P 系列停損停利仍照常評估。" in line


# --- EXIT 確認核取句 ----------------------------------------------------------


def test_the_exit_confirmation_has_four_checks_and_no_fast_market_note() -> None:
    """定稿: 核取項 3→4，且快市加註禁止出現在 EXIT 任一步（出口零摩擦）."""
    checks = wording.exit_confirm_checks(freeze_days=20, freeze_until=date(2026, 9, 9))
    assert len(checks) == 4
    assert checks[1] == (
        "送出後，R 系列（新倉進場）暫停 20 個交易日（預計恢復日：2026-09-09，依交易日曆計算）。"
    )
    assert checks[2] == (
        "凍結期間內，S／P 系列（停損／停利）仍照常評估；凍結期間仍可再次送出全部出清。"
    )
    assert checks[3] == (
        "本操作產生的是賣出指令，不是成交：T+1 開盤以市價單送出，跌停或無量時可能無法成交。"
    )
    for check in checks:
        assert "快市" not in check
        assert "所有排程" not in check
        assert "阻止" not in check and "鎖住" not in check


def test_the_degraded_freeze_check_states_the_freeze_without_inventing_numbers() -> None:
    """四輪收斂裁決: 降級句只說「暫停」與「兩個數字這次取不到」，不得補假數字."""
    sentence = wording.EXIT_CONFIRM_FREEZE_DEGRADED

    assert sentence == (
        "送出後，R 系列（新倉進場）暫停；本次未能取得暫停交易日數與預計恢復日，"
        "兩者於送出後的執行結果中顯示。"
    )
    assert not re.findall(r"\d", sentence)
    assert "{" not in sentence
    assert "—" not in sentence
    # 降級句只服務降級分支：正常路徑的四句裡不得出現它。
    assert sentence not in wording.exit_confirm_checks(
        freeze_days=20, freeze_until=date(2026, 9, 9)
    )


def test_the_three_post_submit_sentences_all_carry_the_freeze_day_count() -> None:
    """降級句把兩個數字指到送出後才顯示——那三句就必須真的帶得出天數."""
    calendar = helper.calendar()
    until = calendar.shift(helper.TUESDAY, 20)
    rendered = [
        wording.EMERGENCY_EXIT_RESULT.format(
            batches=2,
            shares=500,
            execution_date="2026-08-12",
            executed_at="2026-08-11",
            freeze_days=20,
            until=until.isoformat(),
        ),
        wording.EMERGENCY_EXIT_EMPTY.format(
            executed_at="2026-08-11", freeze_days=20, until=until.isoformat()
        ),
        wording.mode_reason_emergency(frozen_day=1, freeze_days=20, until=until),
    ]

    for sentence in rendered:
        assert "20 交易日" in sentence
        assert until.isoformat() in sentence
        assert "{" not in sentence


# --- 歸屬語三情境 -------------------------------------------------------------


def test_the_attribution_names_the_user_and_the_rule_set_date() -> None:
    note = wording.attribution_note(
        RuleSetAuthorship(user_authored=True, version=3, rule_set_date=date(2026, 1, 1))
    )
    assert note == ("此指令是你於 2026-01-01 自行設定的規則之機械執行結果，非本系統的判斷或建議。")


def test_an_unreadable_rule_set_date_uses_the_one_permitted_status_string() -> None:
    note = wording.attribution_note(
        RuleSetAuthorship(user_authored=True, version=3, rule_set_date=None)
    )
    assert note == (
        "此指令是你自行設定的規則之機械執行結果，非本系統的判斷或建議"
        "（規則設定日期缺漏：規則版本 3 的生效日期讀取失敗）。"
    )


def test_with_no_user_record_the_attribution_is_replaced_not_shortened() -> None:
    note = wording.attribution_note(RuleSetAuthorship(user_authored=False))
    assert note == wording.ATTRIBUTION_NO_USER_RULES
    assert "自行設定的規則之機械執行結果" not in note


def test_the_block_sentence_limits_itself_and_names_the_exit() -> None:
    """三輪定稿 題 8: 限縮三句式——阻斷只及於規則驅動指令，出口在同一段被指名."""
    assert wording.ATTRIBUTION_NO_USER_RULES == (
        "目前使用的是系統預設規則集，尚無你本人的設定或修改紀錄。"
        "本模組僅依你設定的規則集產生進場、停損、停利指令，"
        "在你確認規則集之前不會產生這類指令。"
        "你隨時可送出全部出清（EMERGENCY_EXIT），不受此限制。"
    )
    # 第三句不得縮為指路句：出口本身要被寫成不受限制，而不是「詳見某處」。
    assert "你隨時可送出全部出清（EMERGENCY_EXIT），不受此限制。" in (
        wording.ATTRIBUTION_NO_USER_RULES
    )
    # 舊的無限定寫法（不產生任何指令）會把逃生口一起講死，不得回歸。
    assert "不產生任何指令" not in wording.ATTRIBUTION_NO_USER_RULES
    assert "阻止" not in wording.ATTRIBUTION_NO_USER_RULES
    assert "鎖住" not in wording.ATTRIBUTION_NO_USER_RULES


def test_the_exit_attribution_points_at_the_submitted_action_not_a_rule_set() -> None:
    """三輪定稿 題 7: EXIT 專用歸屬語，逐字."""
    assert wording.EXIT_ATTRIBUTION == (
        "此指令是你在本次操作中提交的「全部出清」要求之機械執行結果，"
        "非本系統的判斷或建議；EMERGENCY_EXIT 不依賴規則集，"
        "無論規則集是否已確認皆可送出。"
    )
    # 出口的歸屬對象是剛提交的動作，不是任何日期或版本的規則集。
    assert "{" not in wording.EXIT_ATTRIBUTION
    assert "規則集" in wording.EXIT_ATTRIBUTION
    assert "自行設定的規則" not in wording.EXIT_ATTRIBUTION


def test_the_unauthored_holding_note_discloses_every_held_symbol() -> None:
    """三輪定稿 題 9: 未確認規則集但仍有持倉，S/P 未評估須主動揭露、不得截斷."""
    note = wording.UNAUTHORED_HOLDING_NOTE.format(symbols="2330、2454、2603")
    assert note == (
        "【S/P 系列停損停利今日未依規則評估】規則集尚無你本人的設定或修改紀錄，"
        "本模組今日不產生規則驅動指令；你目前持有 2330、2454、2603 尚未出清，"
        "其停損/停利（S/P 系列）今日未依規則評估。"
    )
    assert note.startswith("【S/P 系列停損停利今日未依規則評估】")
    assert "…" not in note and "..." not in note


def test_the_unconfirmed_mode_label_does_not_read_as_a_disabled_module() -> None:
    """三輪定稿 題 10: 採「待確認規則集」，否決「未啟用」."""
    assert wording.MODE_LABELS["unconfirmed"] == "待確認規則集"
    assert wording.MODE_LABELS["unconfirmed"] != wording.MODE_LABELS["normal"]
    assert "未啟用" not in wording.MODE_LABELS.values()


# --- 快市 / 資料缺漏 / 參考價 -------------------------------------------------


def test_a_missing_volatility_is_stated_never_rendered_as_a_dash() -> None:
    """定稿: vol 不可得時禁「—%」，改說本次未採用波動率門檻."""
    note = wording.fast_market_note(vol=None, lookback=5, moves=3, move_pct=Decimal("2"))
    assert "—" not in note
    assert "20 日年化波動率資料暫缺，本次未採用波動率門檻" in note
    assert "近 5 交易日有 3 日 |漲跌幅| ≥2%" in note
    assert "快市期間規則不放寬。" in note
    reason = wording.fast_market_reason(vol=None, lookback=5, moves=3, move_pct=Decimal("2"))
    assert "—" not in reason


def test_the_index_gap_note_does_not_claim_a_deferral_by_itself() -> None:
    """定稿: 主句只說 M1 未評估、當日不新開倉；順延是另一句."""
    main = wording.INDEX_DATA_GAP_NOTE.format(status="unavailable", source="none")
    assert "當日不新開倉。" in main
    assert "順延" not in main
    assert "順延" in wording.INDEX_DATA_GAP_DEFER_NOTE


def test_a_held_symbol_says_its_stop_loss_could_not_be_evaluated() -> None:
    """S-2: 資料缺漏致停損無法評估須主動顯著揭露，不得靜默."""
    note = wording.DATA_GAP_HOLDING_NOTE.format(symbol="2330", status="unavailable", source="none")
    assert note.startswith("【停損今日無法評估】")
    assert "本檔目前持有部位" in note


def test_a_line_without_a_reference_price_says_so(directive: Directive) -> None:
    """R17 空價分支: 沒有參考價時附「（無可用參考價）」而不是收盤價註記."""
    line = wording.directive_line(directive)
    assert "（無可用參考價）" in line
    assert "不反映今日盤中變動" not in line


@pytest.fixture
def directive() -> Directive:
    return Directive(
        symbol="2330",
        batch_no=1,
        action="sell",
        shares=300,
        rule_id="EMERGENCY",
        rule_summary="",
        data_date=helper.TUESDAY,
        execution_date=helper.WEDNESDAY,
        reference_price=None,
        limit_low=None,
        limit_high=None,
        limit_note=wording.EMERGENCY_EXIT_NO_BAND_NOTE,
        data_status="unavailable",
        source="none",
    )


def test_a_priced_line_still_carries_the_r17_note(directive: Directive) -> None:
    priced = directive.model_copy(update={"reference_price": Decimal("100")})
    line = wording.directive_line(priced)
    assert "參考價 100.00（依據交易日收盤價，不反映今日盤中變動）" in line


def test_the_settlement_summary_names_the_day_it_judged_on() -> None:
    summary = wording.SETTLEMENT_SUMMARY.format(
        settled_on="2026-08-12", executed=1, missed=2, pending=3
    )
    assert "依 2026-08-12 開盤價判定" in summary
    assert "實際成交結果以你的券商回報為準。" in summary


def test_the_rebalance_line_says_the_execution_fields_do_not_apply() -> None:
    assert wording.REBALANCE_NO_ORDER_NOTE == (
        "本列為季末資金重算紀錄，不是下單指令；不會產生買賣，執行日與參考價欄位不適用。"
    )


def test_the_exit_no_band_note_is_not_the_stop_loss_sentence() -> None:
    """定稿: service 的 EXIT 指令不得再掛停損句."""
    assert wording.EMERGENCY_EXIT_NO_BAND_NOTE.startswith("EMERGENCY_EXIT 指令不設滑價帶")
    assert "停損" not in wording.EMERGENCY_EXIT_NO_BAND_NOTE
    assert "無條件" not in wording.EMERGENCY_EXIT_NO_BAND_NOTE


def test_the_calendar_helper_is_the_one_used_by_the_counter() -> None:
    """凍結第 N 日是交易日曆算出來的，不是日曆天."""
    calendar = TradingCalendar({date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)})
    assert (
        emergency_frozen_day(
            calendar=calendar,
            data_date=date(2026, 8, 12),
            until=date(2026, 8, 13),
            freeze_days=2,
        )
        == 1
    )


# --- N-166 重複出清字面 (風控 2026-10-31 S1～S9，逐字) ---------------------------------


def test_n166_s1_already_pending_is_verbatim() -> None:
    assert wording.EMERGENCY_EXIT_ALREADY_PENDING == (
        "EMERGENCY_EXIT 已受理：本次未產生新的賣出指令。目前全部 {pending_batches} 批、"
        "共 {pending_shares} 股的持有批次，都已有你先前提交全部出清時產生、尚未結算的賣出指令"
        "（預定執行日 {pending_execution_dates} 開盤以市價單送出）；這些先前的指令仍然有效，"
        "本次未取消、未修改，也未重新產生。本次回應不是另一筆賣出指令，請勿據此到券商重複下單；"
        "若你尚未依先前的指令下單，以上述 {pending_batches} 批、共 {pending_shares} 股為準。"
        "市價單在跌停或無量時可能無法成交，實際成交結果以你的券商回報為準；"
        "R 系列（新倉進場）自 {executed_at} 起暫停 {freeze_days} 交易日（依交易日曆），"
        "預計 {until} 恢復；S/P 系列停損停利仍照常評估。"
    )


def test_n166_s2_to_s9_are_verbatim() -> None:
    assert wording.EMERGENCY_EXIT_PENDING_NOTE == (
        "另有 {pending_batches} 批、共 {pending_shares} 股已有你先前提交全部出清時產生、"
        "尚未結算的賣出指令（預定執行日 {pending_execution_dates} 開盤以市價單送出），"
        "本次未重新產生；這些先前的指令仍然有效，請勿就這 {pending_batches} 批到券商重複下單；"
        "若你尚未依先前的指令下單，以這 {pending_batches} 批、共 {pending_shares} 股為準。"
    )
    assert wording.EMERGENCY_EXIT_PENDING_PAST_DUE_NOTE == (
        "先前的指令中，預定執行日 {past_due_dates} 已過、仍未結算；"
        "本系統不下單，也無法得知你在券商是否已賣出，請以你的券商回報為準。"
    )
    assert wording.EXIT_ATTRIBUTION_PRIOR == (
        "此指令是你在先前操作中提交的「全部出清」要求之機械執行結果，非本系統的判斷或建議；"
        "EMERGENCY_EXIT 不依賴規則集，無論規則集是否已確認皆可送出。"
    )
    assert wording.EXIT_ATTRIBUTION_MIXED == (
        "本次新產生與先前已有的賣出指令，都是你分別在本次與先前操作中提交的「全部出清」要求之"
        "機械執行結果，非本系統的判斷或建議；EMERGENCY_EXIT 不依賴規則集，"
        "無論規則集是否已確認皆可送出。"
    )
    assert wording.EMERGENCY_EXIT_FREEZE_EXTENDED_NOTE == (
        "因本次再次提交全部出清，R 系列（新倉進場）的預計恢復日由 {previous_until} 延後至 "
        "{until}，暫停交易日數改自 {executed_at} 起重新計算。"
    )
    assert wording.EMERGENCY_EXIT_FREEZE_KEPT_CLAUSE == (
        "R 系列（新倉進場）維持暫停，預計 {until} 恢復（依交易日曆；沿用先前已設定、較晚的"
        "恢復日，本次未縮短）；S/P 系列停損停利仍照常評估。"
    )
    assert wording.MODE_REASON_EMERGENCY_UNCOUNTED == (
        "緊急出清後凍結：R 系列（新倉進場）暫停中，預計 {until} 恢復（依交易日曆）；"
        "S/P 系列停損停利仍照常評估。"
    )
    assert wording.EXIT_CONFIRM_FREEZE_KEPT_CHECK == (
        "送出後，R 系列（新倉進場）維持暫停（預計恢復日：{FREEZE_UNTIL}，依交易日曆計算；"
        "沿用先前已設定、較晚的恢復日）。"
    )


@pytest.mark.parametrize(
    "sentence", [wording.EMERGENCY_EXIT_ALREADY_PENDING, wording.EMERGENCY_EXIT_PENDING_NOTE]
)
def test_the_pending_sentences_never_claim_completion_or_safety(sentence: str) -> None:
    """風控 第 3 節 字串檢查: S1、S2 無完成式與「安全」，且都含「請勿」與「仍然有效」."""
    for banned in ("已產生", "已執行", "已成交", "出清完成", "安全"):
        assert banned not in sentence, banned
    assert "請勿" in sentence
    assert "仍然有效" in sentence
    # 「請勿重複下單」不得單獨出現：第一次回應遺失的人要有依據可賣 (EX-2，否則 VETO)。
    assert "若你尚未依先前的指令下單" in sentence


def test_the_kept_freeze_clause_replaces_the_tail_of_every_template() -> None:
    """S7 替換「R 系列（新倉進場）自 {executed_at} 起暫停…」到「…照常評估。」整段."""
    for template in (
        wording.EMERGENCY_EXIT_RESULT,
        wording.EMERGENCY_EXIT_EMPTY,
        wording.EMERGENCY_EXIT_ALREADY_PENDING,
    ):
        kept = wording.freeze_kept_template(template)
        head = template[: template.index("R 系列（新倉進場）自 {executed_at} 起暫停")]
        assert kept == head + wording.EMERGENCY_EXIT_FREEZE_KEPT_CLAUSE
        assert "{executed_at}" not in kept and "{freeze_days}" not in kept
    with pytest.raises(ValueError, match="freeze clause"):
        wording.freeze_kept_template(wording.EMERGENCY_EXIT_PENDING_NOTE)


def test_the_kept_check_only_replaces_check_two() -> None:
    standard = wording.exit_confirm_checks(freeze_days=20, freeze_until=date(2026, 12, 31))
    kept = wording.exit_confirm_checks(
        freeze_days=20, freeze_until=date(2026, 12, 31), freeze_kept=True
    )
    assert kept[1] == (
        "送出後，R 系列（新倉進場）維持暫停（預計恢復日：2026-12-31，依交易日曆計算；"
        "沿用先前已設定、較晚的恢復日）。"
    )
    assert kept[0] == standard[0] and kept[2:] == standard[2:]


def test_date_lists_are_deduplicated_ascending_iso_and_joined_by_the_enumeration_comma() -> None:
    """風控 佔位符定義: {pending_execution_dates}／{past_due_dates}."""
    days = [date(2026, 8, 13), date(2026, 8, 12), date(2026, 8, 13)]
    assert wording.date_list(days) == "2026-08-12、2026-08-13"


def test_the_uncounted_mode_line_carries_no_counter() -> None:
    line = wording.mode_reason_emergency_uncounted(until=date(2026, 12, 31))
    assert line == (
        "緊急出清後凍結：R 系列（新倉進場）暫停中，預計 2026-12-31 恢復（依交易日曆）；"
        "S/P 系列停損停利仍照常評估。"
    )
    assert "第 " not in line


# --- 出清對話框 Q8：降級句承諾「於送出後的執行結果中顯示」 ------------------------------


_Q8_UNTIL = date(2026, 9, 9)
_Q8_PENDING = wording.ExitPending(
    batches=1,
    shares=300,
    execution_dates=(date(2026, 8, 12),),
    past_due_dates=(date(2026, 8, 12),),
)
_Q8_NONE = wording.ExitPending(batches=0, shares=0, execution_dates=(), past_due_dates=())


@pytest.mark.parametrize("freeze_kept", [False, True], ids=["standard", "f-c S7"])
@pytest.mark.parametrize(
    ("new_batches", "pending"),
    [(2, _Q8_NONE), (1, _Q8_PENDING), (0, _Q8_PENDING), (0, _Q8_NONE)],
    ids=["RESULT", "RESULT+S2", "ALREADY_PENDING S1", "EMPTY"],
)
def test_every_accepted_message_states_the_actual_recovery_date(
    new_batches: int, pending: wording.ExitPending, freeze_kept: bool
) -> None:
    """風控 Q8 合併關卡: RESULT、EMPTY、S1 與其 S7 版本都含 {until} 的實際日期."""
    message = wording.emergency_exit_message(
        new_batches=new_batches,
        new_shares=300 * new_batches,
        execution_date=date(2026, 8, 12),
        executed_at=date(2026, 8, 13),
        freeze_days=20,
        until=_Q8_UNTIL,
        pending=pending,
        extended_from=None,
        freeze_kept=freeze_kept,
    )

    assert _Q8_UNTIL.isoformat() in message
    assert "{" not in message


@pytest.mark.parametrize(
    "template",
    [
        wording.EMERGENCY_EXIT_RESULT,
        wording.EMERGENCY_EXIT_EMPTY,
        wording.EMERGENCY_EXIT_ALREADY_PENDING,
        wording.freeze_kept_template(wording.EMERGENCY_EXIT_RESULT),
        wording.freeze_kept_template(wording.EMERGENCY_EXIT_EMPTY),
        wording.freeze_kept_template(wording.EMERGENCY_EXIT_ALREADY_PENDING),
    ],
)
def test_every_accepted_template_carries_the_until_placeholder(template: str) -> None:
    assert "{until}" in template
