"""The operator report of the forecast ledger core: ``python -m app.forecast.report``.

ADR-0030 D-1 point 3 (``report.py``: operator CLI, read-only, output limited
by D-4 points 3 and 5); D-5 points 3 and 5; D-8 point 4. Commands, each with
``--db PATH``:

* ``status`` -- execution status only (D-4 point 5, F-2): the number of runs
  per ``outcome`` (and without an end row), the ``inputs_not_ready`` days, per
  recording claim failure condition F-2's first sentence over its rolling
  20-weekday windows (ADR-0030 supplement 5 point 1: the latest full window's
  range, its two numerator terms, denominator and verdict, and whether any
  window since the start held -- all derived by ``store.f2_status``), the
  phase-0 grid points and how many have no ``late = 0`` record, and per
  recording claim the D-8 point 4 review trigger:
  D_v, c_1, n-hat with :data:`N_HAT_NOTE`, d_1, T1, T2 (all derived by
  ``store.py``'s read-only queries). No label, no comparison. The two parts
  are :func:`render_execution_status` and :func:`render_review_trigger`; the
  pipeline acceptance harness prints the first only (ADR-0030 supplement 5
  point 5: no n-hat, T1 or T2 in its output);
* ``verify (--all | --claim-id ID)`` -- D-5 point 3: every record of the
  recording claims (``--all``) or of one claim is recomputed from its stored
  snapshot with the rule set and the definition rebuilt from the claim's
  *registry row* (``definitions.registered_ruleset`` /
  ``registered_definition``), and ``label``, ``band_def``,
  ``baseline_predictions_json``, ``missing_json`` and ``content_hash`` must
  be equal byte for byte (``recorder.reproduces``, the cross-commit check's
  own comparison); the stored snapshot's bytes must still hash to its
  ``content_sha256``. Each record's line says only whether it is consistent,
  and whether the running program and runtime are the ones of the run that
  wrote it (the D-5 point 3 premise). Any inconsistency is F-3: exit 1;
* ``records`` -- every record of every forward claim, by registration order
  and T. A record whose ``valid_until_session_estimate`` has not passed lists
  only T, ``late``, whether it is insufficient, ``content_hash`` and its run's
  outcome; a passed one adds the four baselines and the model label on the
  same line in one format (D-4 point 3);
* ``compare`` -- the provisional comparison (``scoring.py``; D-5 point 5) of
  every passed record, with :data:`app.forecast.scoring.PROVISIONAL_BANNER`
  as the first and the last line. Records are listed by registration order
  and T, never sorted, filtered or grouped by a comparison result.

A baseline is printed by :func:`prediction_text` in every subcommand: its
label, or ``unavailable:<reason>`` (D-4 point 3: an unavailable baseline is
listed with its reason). A stored baseline that is ``unavailable`` without a
reason is malformed (``scoring.BaselinePrediction.from_stored``): ``records``
refuses the ledger (exit 3) and ``compare`` lists that record as
``record_unreadable``; neither prints it without its reason.

D-4 point 3 / 5 on every output: when a model label is listed the four
baselines are on the same line, in the same ``name=value`` form (no colour,
bold, ordering or position that sets the model apart; the model is the last
cell); no hit rate, match count or proportion, run of matches, interval, n
(n-hat only with :data:`N_HAT_NOTE`), and no "better", "worse", "accurate" or
"effective" wording. "Passed" is read with the report's clock: a record has
passed when the Taipei date is after its ``valid_until_session_estimate``.

Read-only: every read goes through ``ForecastStore``'s read-only queries
(``_read``, a ``query_only`` connection, so a write fails in SQLite itself).
The path must be an existing file -- SQLite would create a missing one -- and
the ledger schema complete (``schema_status`` on a read-only connection).
This module calls no store write and opens no connection itself (AST).

Exit codes: 0 done (``verify``: every record consistent), 1 ``verify`` found
an inconsistency, 2 usage (argparse), 3 the ledger cannot be read or its
schema is incomplete, 4 the path is not an existing file (nothing opened).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final, get_args
from zoneinfo import ZoneInfo

from app.data.freshness import TW_POLICY
from app.forecast import definitions, recorder, scoring
from app.forecast.canonical import content_sha256
from app.forecast.errors import exception_class_name
from app.forecast.store import (
    ClaimRow,
    F2Status,
    ForecastStore,
    ForecastStoreError,
    GridLossStatus,
    LedgerInconsistentError,
    RunOutcome,
    RunRow,
    system_clock,
)
from app.outlook.inputs import MarketSnapshot

#: D-8 point 4 / D-4 point 5: the fixed note n-hat is always printed with.
N_HAT_NOTE: Final = "重審觸發用計數（近似上界估計），不是驗證統計，不代表規則有效"
#: ADR-0030 supplement 8 point 6 (b), second line (risk RC-233, RC-234): the one fixed
#: line after every review trigger line -- n-hat and T1 may differ from the validation
#: layer's recomputation and missing source sessions may make n-hat low. The wording is
#: the risk-approved text (``work/reviews/2026-11-19-重審觸發缺日加註定稿RC233至RC236-風控.md``,
#: the line "第二行定稿全文："), copied by script; any change goes back to risk review.
#: Printed once on every call, whatever the ledger holds.
REVIEW_GAP_DISCLOSURE: Final = (
    "加註：重審觸發的 n̂ 與 T1 可能與日後驗證時重算的結果不同；"
    "資料來源缺少的交易日可能使 n̂ 偏低、T1 較晚成立，此時「近似上界」不一定成立。"
)
# --- risk-approved wording of ``status`` (copied by script; changes go back to risk) ---------
#
# ``work/reviews/2026-11-19-補充九判定與F2字面定稿RC244至RC254-風控.md`` (``項目：`` labels) and
# ``work/reviews/2026-11-19-接線PR-F2視窗字面判定RC237至RC243-風控.md`` (the label line before
# each ``定稿全文：``). Templates: ``{name}`` is a value, ``{A／B}`` a choice of one
# alternative, braces and slash not printed (:func:`_fill`).

#: RC-248 段標題 (supplement 5 point 1: told apart from the prereg's delisting rule F-2).
F2_TITLE: Final = (
    "ADR-0030 失效條件 F-2（「成立」指這個失效條件成立，"
    "即記錄缺漏達到門檻，不代表規則成立或不成立；"
    "只含執行狀態，不含任何標籤或對照）："
)
#: RC-248 第一句小標題: printed on every call.
F2_FIRST_HEADING: Final = (
    "F-2 第一句（定案 session 缺漏與 inputs_not_ready）："
    "平日指週一至週五，不扣休市日；每 20 個平日為一個視窗，"
    "逐平日滾動。"
)
#: RC-238 完整視窗（分母大於 0）.
F2_FULL_LINE: Final = (
    "  {claim_id}：最近一個完整視窗 {起}～{迄}，"
    "沒有 late = 0 紀錄的定案 session 數 {a}，"
    "inputs_not_ready 日數 {b}，"
    "分母 {d}，此視窗 F-2 {成立／未成立}；"
    "自起點以來 F-2 曾否成立：{是（成立後不撤銷）／否}"
)
#: RC-247 第一句完整視窗分母為 0 (supplement 9 point 4: always held, ever held).
F2_FULL_ZERO_LINE: Final = (
    "  {claim_id}：最近一個完整視窗 {起}～{迄}，"
    "沒有 late = 0 紀錄的定案 session 數 {a}，"
    "inputs_not_ready 日數 {b}，"
    "分母 0（範圍內沒有任何定案 session，"
    "可能是停機、資料來源整段缺席或執行沒有存下快照；"
    "分母為 0 時一律判成立），"
    "此視窗 F-2 成立；自起點以來 F-2 曾否成立："
    "是（成立後不撤銷）"
)
#: RC-239 視窗未滿.
F2_SHORT_LINE: Final = (
    "  {claim_id}：視窗未滿（自起點以來 {k} 個平日："
    "{起}～{迄}），沒有 late = 0 紀錄的定案 session 數 {a}，"
    "inputs_not_ready 日數 {b}，"
    "{F-2 成立（兩項合計已超過 6，"
    "成立後不撤銷）／尚未判定（兩項合計未超過 6）}"
)
#: RC-242: a start but no weekday counted yet.
F2_NO_WEEKDAY_LINE: Final = "  {claim_id}：視窗未滿（自起點 {S_c} 以來尚無可計入的平日）"
#: No run at all yet (unchanged wording, RC-239's note: kept as it is).
F2_NO_RUN_LINE: Final = "  {claim_id}：視窗未滿（尚無執行）"
#: RC-248 第二句小標題: printed on every call.
F2_SECOND_HEADING: Final = (
    "F-2 第二句（第 0 相位格點遺失）："
    "自 D_v 起累計，不設視窗；只計入截止時點已過的格點；"
    "沒有 late = 0 紀錄的格點數的 5 倍大於計入格點數時成立。"
    "格點數少時，遺失一個格點就可能成立，"
    "而且「曾否成立：是」之後不會撤銷。"
)
#: RC-249 第二句有判定（G 大於 0）.
F2_SECOND_LINE: Final = (
    "  {claim_id}：計入的格點 {G} 個，"
    "其中沒有 late = 0 紀錄 {L} 個，"
    "目前 F-2 第二句{成立／未成立}；"
    "自 D_v 起 F-2 第二句曾否成立：{是（成立後不撤銷）／否}"
)
#: RC-249 第二句無從判定（G 為 0）: no "ever held" in it.
F2_SECOND_UNDECIDABLE_LINE: Final = (
    "  {claim_id}：F-2 第二句無從判定（計入的格點 0 個：尚無 D_v，或 D_v 的截止時點未過）"
)
#: RC-250 行動句: printed on every call, before GAP_DISCLOSURE.
F2_ACTION_LINE: Final = (
    "F-2 任一行顯示成立，"
    "或曾否成立為「是」時，請告訴 coordinator（同一項先前已告訴過就不必再告訴）；"
    "不要自己修改任何設定或檔案。"
)
#: ADR-0030 supplement 8 point 6 (b), first line, as revised by RC-251 (it revised
#: RC-230): the last line of the execution status on every call; it changes no count.
GAP_DISCLOSURE: Final = (
    "加註：核心不偵測資料來源缺少的交易日；"
    "F-2 計數、格點數值與兩句的判定都可能與日後驗證時重算的結果不同，"
    "F-2 第一句的計數可能偏低。"
)

EXIT_OK: Final = 0
EXIT_INCONSISTENT: Final = 1
EXIT_UNREADABLE: Final = 3
EXIT_PATH_REFUSED: Final = 4

#: What a ledger read can raise (each reported by class name only).
LEDGER_ERRORS: Final = (
    sqlite3.Error,
    LedgerInconsistentError,
    ForecastStoreError,
    KeyError,
    TypeError,
    ValueError,
)

_TAIPEI: Final = ZoneInfo(TW_POLICY.timezone)

Clock = Callable[[], datetime]


def taipei_date(now: datetime) -> date:
    """The Taipei calendar date of an aware ``now``."""
    return now.astimezone(_TAIPEI).date()


def has_passed(valid_until_session_estimate: object, today: date) -> bool:
    """D-4 point 3: whether a record's ``valid_until_session_estimate`` has passed on ``today``."""
    return today > date.fromisoformat(str(valid_until_session_estimate))


def _run_outcomes(store: ForecastStore) -> dict[int, str]:
    return {run.run_id: run.outcome or "沒有 end 列" for run in store.runs()}


def _claim_line(claim: ClaimRow) -> str:
    return f"claim {claim.claim_id}"


def _record_head(row: Mapping[str, object], outcomes: Mapping[int, str]) -> str:
    """The fields every listing may show for any record (D-4 point 3)."""
    insufficient = "是" if row["label"] == "insufficient" else "否"
    run = outcomes.get(int(str(row["run_id"])), "沒有 end 列")
    return (
        f"T={row['data_as_of']} late={row['late']} 證據不足={insufficient}"
        f" content_hash={row['content_hash']} 執行結果={run}"
    )


def prediction_text(prediction: scoring.BaselinePrediction) -> str:
    """A baseline as its label, or ``unavailable:<reason>`` (D-4 point 3; every subcommand)."""
    if prediction.reason is not None:
        return f"{prediction.label}:{prediction.reason}"
    return prediction.label


def label_cells(row: Mapping[str, object]) -> str:
    """The four baselines and the model label, one format, model last (D-4 point 3)."""
    baselines = json.loads(str(row["baseline_predictions_json"]))
    cells = [
        f"{key}={prediction_text(scoring.BaselinePrediction.from_stored(baselines[key]))}"
        for key in scoring.BASELINES
    ]
    cells.append(f"模型={row['label']}")
    return " ".join(cells)


# --- records ----------------------------------------------------------------------------


def render_records(store: ForecastStore, *, now: datetime) -> list[str]:
    """``records``: the module docstring's listing."""
    today = taipei_date(now)
    outcomes = _run_outcomes(store)
    lines = [
        "紀錄（依 claim 登記順序與 T 排列；valid_until_session_estimate 尚未過的紀錄"
        "只列 T、late、是否證據不足、雜湊與執行結果）"
    ]
    for claim in store.forward_claims():
        lines.append(_claim_line(claim))
        for row in store.stored_records(claim.claim_id):
            head = _record_head(row, outcomes)
            if has_passed(row["valid_until_session_estimate"], today):
                head = f"{head} {label_cells(row)}"
            lines.append(f"  {head}")
    return lines


# --- compare ----------------------------------------------------------------------------


def later_snapshot(
    snapshots: Sequence[MarketSnapshot], data_as_of: date, horizon: int
) -> MarketSnapshot | None:
    """The snapshot the comparison reads for T (capture order; the choice never sees a label).

    The first one holding T and at least h sessions after it; when none has h
    sessions after T, the last one holding T (so the comparison states the
    shortfall); ``None`` when no snapshot holds T.
    """
    holding: MarketSnapshot | None = None
    for snapshot in snapshots:
        sessions = [bar.session_date for bar in snapshot.bars]
        if data_as_of not in sessions:
            continue
        if len(sessions) - 1 - sessions.index(data_as_of) >= horizon:
            return snapshot
        holding = snapshot
    return holding


def _match_text(matched: bool | None) -> str:
    return "不適用" if matched is None else "符合" if matched else "不符合"


def render_compare(store: ForecastStore, *, now: datetime) -> list[str]:
    """``compare``: the provisional comparison of every passed record, between two banners."""
    today = taipei_date(now)
    known = store.final_sessions()
    snapshots = [
        recorder.stored_market_snapshot(store.snapshot(digest))
        for digest in store.snapshot_digests()
    ]
    lines = [scoring.PROVISIONAL_BANNER]
    for claim in store.forward_claims():
        rows = [
            row
            for row in store.stored_records(claim.claim_id)
            if has_passed(row["valid_until_session_estimate"], today)
        ]
        if not rows:
            continue
        lines.append(_claim_line(claim))
        for row in rows:
            head = f"T={row['data_as_of']} h={claim.horizon} late={row['late']}"
            try:
                record = scoring.ComparedRecord.from_row(row)
            except scoring.RecordUnreadableError:
                lines.append(f"  {head} 無法對照：record_unreadable")
                continue
            later = later_snapshot(snapshots, record.data_as_of, record.horizon)
            result = scoring.provisional_comparison(
                record, later, known_sessions=known, today=today
            )
            if result.reason is not None:
                lines.append(f"  {head} 無法對照：{result.reason}")
                continue
            texts = {key: prediction_text(p) for key, p in record.baseline_predictions.items()}
            texts[scoring.MODEL] = record.label
            cells = " ".join(
                f"{'模型' if party == scoring.MODEL else party}={texts[party]}"
                f"（{_match_text(matched)}）"
                for party, matched in result.matches
            )
            lines.append(f"  {head} 實現={result.realized} {cells}")
    lines.append(scoring.PROVISIONAL_BANNER)
    return lines


# --- verify -----------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifiedRecord:
    """One record's D-5 point 3 check (no label)."""

    claim_id: str
    data_as_of: str
    consistent: bool
    #: The running program and runtime are those of the run that wrote the record.
    same_program: bool
    #: Why it is not consistent: ``differs``, ``snapshot_hash_differs``,
    #: ``registered_material_rejected`` or ``ledger_unreadable:<class>``.
    problem: str | None


def _same_program(run: RunRow | None) -> bool:
    loaded = recorder.LOADED
    return (
        run is not None
        and run.code_digest == loaded.code_digest
        and run.runtime_json == loaded.runtime_json
    )


def _recording_claim(store: ForecastStore, claim: ClaimRow) -> recorder.RecordingClaim:
    """The claim with the rule set and definition rebuilt from its registry row."""
    material = store.registered_material(claim.claim_id)
    ruleset = definitions.registered_ruleset(
        material.rules_bytes,
        rules_sha256=claim.rules_sha256,
        logic_sha256=claim.rules_logic_sha256,
    )
    definition = definitions.registered_definition(
        material.definition_json,
        full_sha256=claim.definition_sha256,
        logic_sha256=claim.definition_logic_sha256,
    )
    if definition.definition_version != claim.definition_version:
        raise definitions.PublishedVersionRejectedError(
            "registered definition_json carries another definition_version"
        )
    return recorder.RecordingClaim(claim=claim, ruleset=ruleset, definition=definition)


def _verify_row(
    store: ForecastStore, recording: recorder.RecordingClaim, row: Mapping[str, object]
) -> str | None:
    """``None`` when ``row`` is consistent, else the problem (module docstring)."""
    try:
        stored = store.snapshot(str(row["input_series_sha256"]))
        if content_sha256(stored.bars) != stored.content_sha256:
            return "snapshot_hash_differs"
        return None if recorder.reproduces(store, recording, row) else "differs"
    except LEDGER_ERRORS as exc:
        return f"ledger_unreadable:{exception_class_name(exc)}"


def verify_records(store: ForecastStore, claims: Sequence[ClaimRow]) -> list[VerifiedRecord]:
    """D-5 point 3 for every record of ``claims`` (module docstring)."""
    runs = {run.run_id: run for run in store.runs()}
    checked: list[VerifiedRecord] = []
    for claim in claims:
        rows = store.stored_records(claim.claim_id)
        try:
            recording: recorder.RecordingClaim | None = _recording_claim(store, claim)
        except definitions.PublishedVersionRejectedError:
            recording = None
        for row in rows:
            if recording is None:
                problem: str | None = "registered_material_rejected"
            else:
                problem = _verify_row(store, recording, row)
            checked.append(
                VerifiedRecord(
                    claim_id=claim.claim_id,
                    data_as_of=str(row["data_as_of"]),
                    consistent=problem is None,
                    same_program=_same_program(runs.get(int(str(row["run_id"])))),
                    problem=problem,
                )
            )
    return checked


def render_verify(checked: Sequence[VerifiedRecord]) -> list[str]:
    """Each record's line (consistent or not, the premise) and one closing line; no label."""
    lines = ["verify（D-5 第 3 點：以快照、登記表中的規則位元組與定義重算；只輸出核對是否一致）"]
    for item in checked:
        verdict = "一致" if item.consistent else f"不一致（{item.problem}）"
        premise = "相同" if item.same_program else "不同"
        lines.append(
            f"  {item.claim_id} T={item.data_as_of}：{verdict}；"
            f"程式與執行環境與寫入該筆紀錄的執行：{premise}"
        )
    if not checked:
        lines.append("verify：沒有紀錄")
    elif all(item.consistent for item in checked):
        lines.append("verify：全部一致")
    else:
        lines.append("verify：有不一致（F-3：停止記錄並查明）")
    return lines


# --- status -----------------------------------------------------------------------------


def _yes(value: bool) -> str:
    return "成立" if value else "未成立"


_PLACEHOLDER: Final = re.compile(r"\{([^{}]*)\}")


def _fill(template: str, choices: Sequence[bool], **values: object) -> str:
    """A risk-approved template rendered: ``{A／B}`` is A when the next choice is true, else B.

    ``{name}`` takes ``values[name]``. Formatting only: every value and choice
    is the store's (supplement 9 point 5: no determination in this module).
    """
    picks = iter(choices)

    def one(match: re.Match[str]) -> str:
        name = match.group(1)
        if "／" in name:
            first, second = name.split("／")
            return first if next(picks) else second
        return str(values[name])

    return _PLACEHOLDER.sub(one, template)


def _f2_line(status: F2Status) -> str:
    """One claim's F-2 first sentence line (supplement 5 point 1 (g); supplement 9 point 4)."""
    item = status.window
    if status.start is None:
        return _fill(F2_NO_RUN_LINE, (), claim_id=status.claim_id)
    if item is None:
        return _fill(F2_NO_WEEKDAY_LINE, (), claim_id=status.claim_id, S_c=status.start)
    values: dict[str, object] = {
        "claim_id": status.claim_id,
        "起": item.first.isoformat(),
        "迄": item.last.isoformat(),
        "a": item.missed_sessions,
        "b": item.not_ready_days,
    }
    if not status.full:
        return _fill(F2_SHORT_LINE, (item.holds,), k=status.weekdays, **values)
    if item.denominator == 0:
        return _fill(F2_FULL_ZERO_LINE, (), **values)
    return _fill(F2_FULL_LINE, (item.holds, status.ever_held), d=item.denominator, **values)


def _grid_line(status: GridLossStatus) -> str:
    """One claim's F-2 second sentence line (supplement 9 point 5); values from the store."""
    if status.verdict == "undecidable":
        return _fill(F2_SECOND_UNDECIDABLE_LINE, (), claim_id=status.claim_id)
    return _fill(
        F2_SECOND_LINE,
        (status.verdict == "holds", status.ever_held),
        claim_id=status.claim_id,
        G=status.counted,
        L=status.lost,
    )


def render_status(store: ForecastStore, *, now: datetime) -> list[str]:
    """``status``: execution status only (module docstring).

    :func:`render_execution_status` followed by :func:`render_review_trigger`.
    """
    return [
        *render_execution_status(store, now=now),
        *render_review_trigger(store, now=now),
    ]


def _recording_claims(store: ForecastStore) -> list[ClaimRow]:
    recording = store.recording_claims()
    return [recording[key] for key in sorted(recording)]


def render_execution_status(store: ForecastStore, *, now: datetime) -> list[str]:
    """``status`` without the review trigger: runs per outcome and the F-2 counts.

    No n-hat and no T1 / T2: the pipeline acceptance harness prints only this
    part (ADR-0030 supplement 5 point 5, C5-1). The F-2 lines print what
    ``store.f2_status`` derived; this module counts nothing for F-2 (C5-3).
    The F-2 lines print what ``store.f2_status`` and ``store.grid_loss_status``
    derived. Order (RC-252): the three run lines, :data:`F2_TITLE`,
    :data:`F2_FIRST_HEADING`, the first sentence per recording claim,
    :data:`F2_SECOND_HEADING`, the second sentence per recording claim,
    :data:`F2_ACTION_LINE` and :data:`GAP_DISCLOSURE` last -- the headings and
    the last two on every call, whatever the ledger holds; so in ``status``
    they precede the review trigger lines (supplement 8 point 6 (b)).
    """
    runs = store.runs()
    counts = {outcome: 0 for outcome in get_args(RunOutcome)}
    interrupted = 0
    for run in runs:
        if run.outcome is None:
            interrupted += 1
        else:
            counts[run.outcome] = counts.get(run.outcome, 0) + 1
    not_ready_days = sorted(
        {taipei_date(run.started_at) for run in runs if run.outcome == "inputs_not_ready"}
    )
    recording = _recording_claims(store)
    lines = [
        "執行狀態（只含執行狀態，不含任何標籤或對照）",
        "執行次數："
        + "，".join(f"{outcome}={count}" for outcome, count in counts.items())
        + f"，沒有 end 列={interrupted}",
        f"inputs_not_ready 日數（全部期間，台北日期）：{len(not_ready_days)}",
        F2_TITLE,
        F2_FIRST_HEADING,
    ]
    lines.extend(_f2_line(store.f2_status(claim.claim_id, now=now)) for claim in recording)
    lines.append(F2_SECOND_HEADING)
    lines.extend(_grid_line(store.grid_loss_status(claim.claim_id, now=now)) for claim in recording)
    # RC-250 and supplement 8 point 6 (b) (RC-251): always the last two lines.
    lines.append(F2_ACTION_LINE)
    lines.append(GAP_DISCLOSURE)
    return lines


def render_review_trigger(store: ForecastStore, *, now: datetime) -> list[str]:
    """The D-8 point 4 review trigger of each recording claim, n-hat with its fixed note.

    Ends with :data:`REVIEW_GAP_DISCLOSURE`, once, on every call (supplement 8
    point 6 (b), RC-233 / RC-234); it is the last line of ``status``.
    """
    today = taipei_date(now)
    lines: list[str] = []
    for claim in _recording_claims(store):
        trigger = store.review_trigger(claim.claim_id, today=today)
        d_v = "無" if trigger.d_v is None else trigger.d_v.isoformat()
        d_1 = "無" if trigger.d_1 is None else trigger.d_1.isoformat()
        lines.append(
            f"重審觸發（{claim.claim_id}）：D_v={d_v}，c₁={trigger.c1}，"
            f"n̂={trigger.n_hat}（{N_HAT_NOTE}），d₁={d_1}，"
            f"T1={_yes(trigger.t1)}，T2={_yes(trigger.t2)}"
        )
    # Supplement 8 point 6 (b), RC-233 / RC-234: always the last line, once.
    lines.append(REVIEW_GAP_DISCLOSURE)
    return lines


# --- the CLI ----------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.forecast.report",
        description="Read-only operator report of the forecast ledger core (ADR-0030 D-1).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("status", "execution status (no label)"),
        ("records", "records; labels only once valid_until_session_estimate has passed"),
        ("compare", "provisional comparison of the passed records (D-5 point 5)"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("--db", required=True, help="the ledger file (opened read-only)")
    verify = commands.add_parser("verify", help="D-5 point 3 recomputation (no label)")
    verify.add_argument("--db", required=True, help="the ledger file (opened read-only)")
    scope = verify.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="every recording claim")
    scope.add_argument("--claim-id", default=None, help="one registered claim")
    return parser


def run_command(store: ForecastStore, args: argparse.Namespace, *, now: datetime) -> int:
    """One parsed command on an existing ledger with a complete schema; prints its lines."""
    code = EXIT_OK
    if args.command == "status":
        lines = render_status(store, now=now)
    elif args.command == "records":
        lines = render_records(store, now=now)
    elif args.command == "compare":
        lines = render_compare(store, now=now)
    else:
        if args.all:
            recording = store.recording_claims()
            claims = [recording[key] for key in sorted(recording)]
        else:
            claim = store.claim(args.claim_id)
            if claim is None:
                print("refused: --claim-id is not a registered claim", file=sys.stderr)
                return EXIT_UNREADABLE
            claims = [claim]
        checked = verify_records(store, claims)
        lines = render_verify(checked)
        if not all(item.consistent for item in checked):
            code = EXIT_INCONSISTENT
    print("\n".join(lines))
    return code


def main(argv: Sequence[str] | None = None, *, clock: Clock | None = None) -> int:
    """The CLI; returns the exit code (module docstring). ``clock`` is for tests."""
    args = _parser().parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_file():
        print("refused: --db is not an existing ledger file", file=sys.stderr)
        return EXIT_PATH_REFUSED
    read_clock = clock or system_clock
    store = ForecastStore(db_path, clock=read_clock)
    try:
        if not store.ledger_schema_status().complete:
            print("refused: the ledger schema is incomplete", file=sys.stderr)
            return EXIT_UNREADABLE
        return run_command(store, args, now=read_clock())
    except LEDGER_ERRORS as exc:
        print(f"refused: the ledger cannot be read ({exception_class_name(exc)})", file=sys.stderr)
        return EXIT_UNREADABLE


if __name__ == "__main__":
    raise SystemExit(main())
