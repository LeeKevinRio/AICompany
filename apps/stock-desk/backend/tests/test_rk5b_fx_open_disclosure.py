"""Task RK-5, PR-RK5b: the overview names both rates' sources, and says when they differ.

Task ``work/dispatch/2026-10-08-任務單-RK-5-fx_open來源未記錄與總覽匯率貢獻混源.md``
(R5-8, R5-11) and the risk review
``work/reviews/2026-10-08-W-RK4-1-W-RK5-1逐字審與X-11-X-12核對-風控審查.md``
(W5-T1 to W5-T7; W5-T8 is a release-checklist item, not a unit test):

* ``fx_disclosures`` lists, for every ``ok`` position in summary order, its
  ``fx_now`` sentence then its ``fx_open`` sentence, each sentence once.
* The risk-approved W-RK5-1 (:data:`app.portfolio.summary.FX_OPEN_MIXED_SOURCES_NOTE`)
  is appended, once and last, if and only if at least one ``ok`` position's two
  rates carry two different **source ids** (RK5-R2, S-1: ids, not sentences).
* A position that is not ``ok`` -- the X-3c mismatched row included, whose
  ``fx`` and ``fx_open`` are both ``None`` -- contributes nothing and triggers
  nothing.

Expected sentences in the end-to-end tests are derived from the source that
actually answered each lookup (the recording ladder), never from the scenario's
intent. W5-T5's fixtures mirror the front end's
(``frontend/app/lib/__tests__/fxBackupBadge.test.ts``, "W5-T5 badge coupling"):
``yfinance_fx`` backup with ``bank_of_taiwan`` fresh, in both directions.
"""

from __future__ import annotations

import inspect
import itertools
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.advice.loader import BANNED_PHRASES
from app.alerts.engine import evaluate_alerts
from app.data.interface import DataStatus
from app.portfolio import summary as summary_module
from app.portfolio.summary import build_summary, fx_disclosures_for
from app.portfolio.valuation import FxInfo, Valuation
from app.services import fx_notes
from app.services.fx_notes import GENERIC_SOURCE_NOTE, SOURCE_NOTES, source_note
from tests.conftest import ApiHarness
from tests.test_rk2_fx_source_set_disclosure import (
    APPROVED_BRIDGE,
    BANK,
    FOUR_B,
    OPENED,
    RK2_FORBIDDEN,
    SYMBOL,
    YAHOO,
    Scenario,
    _alerts,
    _fire,
    _hold_usd,
    _RecordingLadder,
    _serve,
    _shared_forbidden_terms,
)
from tests.test_rk4_fx_attribution import (
    APPROVED_SCOPE_NOTE,
)
from tests.test_rk4_fx_attribution import (
    test_w4_t11_tripwire_ladder_rungs_and_currencies as _ladder_premises,
)
from tests.test_rk5a_fx_open_source import (
    OPEN_BANK,
    OPEN_NOWHERE,
    OPEN_YAHOO,
    PAIR,
    _hold,
    _Ladder,
    _prices,
    _store,
    _valuator,
)
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

#: W-RK5-1 as risk-compliance approved it verbatim (main draft with the minimal
#: fix 「部分持倉」→「至少一筆持倉」, 2026-10-08). Kept here as a literal on
#: purpose: W5-T1 compares the production constant against it, so an edit to
#: either side is a red test, not a silent drift.
APPROVED_MIXED_NOTE = (
    "至少一筆持倉的買入日匯率與目前匯率來自不同來源，"
    "兩個來源的口徑差會算進「匯率貢獻」，因此也會算進「未實現損益」。"
)
W = APPROVED_MIXED_NOTE
APPROVAL_MARK = "風控核可文案,修改須重新送審(2026-10-08)"
APPROVAL_FILE = "work/reviews/2026-10-08-W-RK4-1-W-RK5-1逐字審與X-11-X-12核對-風控審查.md"
BACK_TO_RISK = "回風控重審 W-RK5-1（W5-T4）"

BANK_NOTE = SOURCE_NOTES[BANK]
YAHOO_NOTE = SOURCE_NOTES[YAHOO]

#: The status each rung carries on the production two-rung ladder: the primary
#: answers as it reports itself (fresh), the backup is always re-labelled BACKUP.
LADDER_STATUS = {BANK: DataStatus.FRESH, YAHOO: DataStatus.BACKUP}

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
FRONTEND_APP = Path(__file__).resolve().parents[2] / "frontend" / "app"


# --- unit fixtures ------------------------------------------------------------------


def _info(source: str, *, status: DataStatus | None = None, pair: str = PAIR) -> FxInfo:
    return FxInfo(
        pair=pair,
        as_of="2026-10-07",
        source=source,
        data_status=status if status is not None else LADDER_STATUS.get(source, DataStatus.FRESH),
        source_note=source_note(source),
    )


def _row(status: str, fx: FxInfo | None, fx_open: FxInfo | None) -> Valuation:
    ok = status == "ok"
    return Valuation(
        status="ok" if ok else "insufficient_data",
        missing=[] if ok else ["price"],
        price=None,
        fx=fx,
        fx_open=fx_open,
        pnl_original=None,
        pnl_twd=None,
        asset_contribution_twd=None,
        fx_contribution_twd=None,
    )


def _ok(now: str, open_: str) -> Valuation:
    return _row("ok", _info(now), _info(open_))


def _unvalued(now: str, open_: str) -> Valuation:
    return _row("insufficient_data", _info(now), _info(open_))


#: A TWD row: nothing converted, nothing to say.
TWD_ROW = _row("ok", None, None)
#: The X-3c mismatched row (KX-A2): unvalued, both rates ``None``.
MISMATCH_ROW = _row("insufficient_data", None, None)


@dataclass(frozen=True)
class Case:
    rows: tuple[Valuation, ...]
    expected: tuple[str, ...]


#: W5-T3: W-RK5-1 if and only if an ``ok`` row's two source ids differ.
CASES = [
    # --- mixed: the sentence appears, once and last --------------------------------
    pytest.param(
        Case((_ok(YAHOO, BANK),), (YAHOO_NOTE, BANK_NOTE, W)),
        id="now-yahoo-backup-open-bank-fresh",
    ),
    pytest.param(
        Case((_ok(BANK, YAHOO),), (BANK_NOTE, YAHOO_NOTE, W)),
        id="now-bank-fresh-open-yahoo-backup",
    ),
    pytest.param(
        Case((_ok(YAHOO, YAHOO), _ok(YAHOO, BANK)), (YAHOO_NOTE, BANK_NOTE, W)),
        id="one-of-two-ok-rows-mixes",
    ),
    pytest.param(
        Case((_ok(YAHOO, BANK), _ok(YAHOO, BANK), _ok(YAHOO, YAHOO)), (YAHOO_NOTE, BANK_NOTE, W)),
        id="several-mixed-rows-still-one-sentence",
    ),
    pytest.param(
        Case((TWD_ROW, _ok(BANK, YAHOO), TWD_ROW), (BANK_NOTE, YAHOO_NOTE, W)),
        id="beside-twd-rows",
    ),
    pytest.param(
        Case((MISMATCH_ROW, _ok(YAHOO, BANK)), (YAHOO_NOTE, BANK_NOTE, W)),
        id="beside-a-mismatched-row",
    ),
    pytest.param(
        Case((_unvalued(BANK, BANK), _ok(YAHOO, BANK)), (YAHOO_NOTE, BANK_NOTE, W)),
        id="an-unvalued-row-lends-no-order",
    ),
    # --- not mixed: no sentence --------------------------------------------------
    pytest.param(Case((_ok(BANK, BANK),), (BANK_NOTE,)), id="same-source-bank"),
    pytest.param(Case((_ok(YAHOO, YAHOO),), (YAHOO_NOTE,)), id="same-source-yahoo"),
    pytest.param(
        Case((_unvalued(YAHOO, BANK),), ()),
        id="mixed-but-unvalued",
    ),
    pytest.param(
        Case((_unvalued(YAHOO, BANK), _ok(BANK, BANK)), (BANK_NOTE,)),
        id="mixed-unvalued-beside-a-same-source-ok-row",
    ),
    pytest.param(
        Case((_unvalued(BANK, YAHOO), _ok(YAHOO, YAHOO)), (YAHOO_NOTE,)),
        id="mixed-unvalued-beside-a-same-source-ok-row-reversed",
    ),
    pytest.param(Case((MISMATCH_ROW,), ()), id="mismatched-row-alone"),
    pytest.param(Case((MISMATCH_ROW, _ok(BANK, BANK)), (BANK_NOTE,)), id="mismatched-beside-ok"),
    pytest.param(Case((TWD_ROW,), ()), id="twd-only"),
    pytest.param(Case((), ()), id="empty-book"),
    pytest.param(
        # Not reachable within one valuation pass (risk RK4-R9: one fx_now source
        # per pair); here to pin that the trigger is a row's own pair of ids, not
        # the number of sentences the list ends up with.
        Case((_ok(BANK, BANK), _ok(YAHOO, YAHOO)), (BANK_NOTE, YAHOO_NOTE)),
        id="two-sentences-but-no-row-mixes",
    ),
    pytest.param(
        # An ok row without an open-date FxInfo cannot happen today (F0 is needed
        # to value it), and is not counted as mixed if it ever did.
        Case((_row("ok", _info(YAHOO), None),), (YAHOO_NOTE,)),
        id="ok-row-without-fx-open",
    ),
]


def _ok_rows(rows: tuple[Valuation, ...] | list[Valuation]) -> list[Valuation]:
    return [row for row in rows if row.status == "ok"]


def _mixes(row: Valuation) -> bool:
    return row.fx is not None and row.fx_open is not None and row.fx.source != row.fx_open.source


def _w5_t4_violations(rows: list[Valuation], disclosures: list[str]) -> list[str]:
    """W5-T4: where W-RK5-1 appears, every mixed ``ok`` row's two ids must each have
    their own sentence before it, and the two sentences must differ."""
    if W not in disclosures:
        return []
    before = disclosures[: disclosures.index(W)]
    violations: list[str] = []
    for row in _ok_rows(rows):
        if not _mixes(row):
            continue
        assert row.fx is not None and row.fx_open is not None
        now_note, open_note = source_note(row.fx.source), source_note(row.fx_open.source)
        if now_note == open_note:
            violations.append(f"{row.fx.source} and {row.fx_open.source} share one sentence")
        for note in (now_note, open_note):
            if note not in before:
                violations.append(f"missing before W-RK5-1: {note[:12]}")
    return violations


# --- W5-T1 / W5-T2: the wording itself ----------------------------------------------


def test_w5_t1_the_mixed_note_is_the_approved_wording() -> None:
    note = summary_module.FX_OPEN_MIXED_SOURCES_NOTE
    assert note == APPROVED_MIXED_NOTE
    assert len(note) == 56
    source = inspect.getsource(summary_module)
    marker = source.index("FX_OPEN_MIXED_SOURCES_NOTE: Final = (")
    header = source[source.rindex("\n\n", 0, marker) : marker]
    assert APPROVAL_MARK in header
    assert APPROVAL_FILE in header


def test_w5_t1_r5_11_never_a_sources_standing_disclosure() -> None:
    assert APPROVED_MIXED_NOTE not in SOURCE_NOTES.values()
    assert APPROVED_MIXED_NOTE != GENERIC_SOURCE_NOTE
    for source_id in (*SOURCE_NOTES, fx_notes.NO_PROVIDER_SOURCE, "fx_unknown", ""):
        assert source_note(source_id) != APPROVED_MIXED_NOTE
    # R5-11: module level in app/portfolio/summary.py only -- not next to the
    # locked sentences, not in the advice package.
    assert APPROVED_MIXED_NOTE not in inspect.getsource(fx_notes)
    assert not hasattr(fx_notes, "FX_OPEN_MIXED_SOURCES_NOTE")
    holders = sorted(
        str(path.relative_to(APP_ROOT))
        for path in APP_ROOT.rglob("*.py")
        if "FX_OPEN_MIXED_SOURCES_NOTE" in path.read_text(encoding="utf-8")
        or "買入日匯率與目前匯率" in path.read_text(encoding="utf-8")
    )
    assert holders == ["portfolio/summary.py"]


#: W5-T2's own lists on top of the three shared ones and RK2-T8's.
W5_T2_BRIDGE_PHRASES = (
    "混用",
    "緊接在前",
    "依序對應",
    "僅適用於部分查詢",
    "價格與 ATR",
    "持倉市值與總資產",
)
W5_T2_MEASURE_WORDS = (
    "很小",
    "不大",
    "有限",
    "輕微",
    "顯著",
    "約",
    "%",
    "％",
    "高估",
    "低估",
    "偏高",
    "偏低",
    "較準",
    "可靠",
    "官方",
)
W5_T2_REASSURANCE = ("暫時", "不影響", "放心", "修正", "恢復")
W5_T2_INTERNAL = (
    "估值器",
    "snapshot",
    "梯子",
    "fx_now",
    "fx_open",
    "source id",
    "source",
    BANK,
    YAHOO,
    "{",
    "}",
)


def test_w5_t2_the_mixed_note_passes_every_wording_scan() -> None:
    terms = set(FRONTEND_FORBIDDEN_TERMS) | set(_shared_forbidden_terms()) | set(BANNED_PHRASES)
    assert terms  # not vacuous
    assert [term for term in sorted(terms) if term in W] == []
    assert find_bare_realtime_claims(W) == []
    assert [term for term in RK2_FORBIDDEN if term in W] == []
    for listed in (W5_T2_BRIDGE_PHRASES, W5_T2_MEASURE_WORDS, W5_T2_REASSURANCE, W5_T2_INTERNAL):
        assert [term for term in listed if term in W] == []
    assert re.search(r"[0-9０-９]", W) is None
    for required in ("買入日匯率", "目前匯率", "「匯率貢獻」", "「未實現損益」", "至少一筆"):
        assert required in W
    # Never a reuse of another approved sentence (RK5-R2).
    for other in (APPROVED_BRIDGE, APPROVED_SCOPE_NOTE, *SOURCE_NOTES.values()):
        assert other not in W and W not in other


# --- W5-T3: if and only if a valued row's two source ids differ, once, last ---------


@pytest.mark.parametrize("case", CASES)
def test_w5_t3_the_list_and_when_the_mixed_note_appears(case: Case) -> None:
    rows = list(case.rows)
    disclosures = fx_disclosures_for(rows)
    assert disclosures == list(case.expected)
    expected_mixed = any(_mixes(row) for row in _ok_rows(rows))
    assert disclosures.count(W) == (1 if expected_mixed else 0)
    if expected_mixed:
        assert disclosures[-1] == W
    assert len(set(disclosures)) == len(disclosures)  # each sentence once


@pytest.mark.parametrize("case", CASES)
def test_w5_t3_a_row_that_is_not_ok_changes_nothing(case: Case) -> None:
    """Dropping every non-``ok`` row (mismatched rows included) leaves the list as is."""
    rows = list(case.rows)
    assert fx_disclosures_for(rows) == fx_disclosures_for(_ok_rows(rows))


# --- W5-T4: two ids, two different sentences -------------------------------------


@pytest.mark.parametrize(
    ("now", "open_"),
    list(itertools.permutations(sorted(SOURCE_NOTES), 2)),
)
def test_w5_t4_every_reachable_pair_of_ids_has_two_sentences(now: str, open_: str) -> None:
    rows = [_ok(now, open_)]
    disclosures = fx_disclosures_for(rows)
    assert disclosures == [source_note(now), source_note(open_), W]
    assert source_note(now) != source_note(open_), BACK_TO_RISK
    assert _w5_t4_violations(rows, disclosures) == [], BACK_TO_RISK


def test_w5_t4_tripwire_the_reachable_ids_are_the_two_listed_rungs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回風控重審 W-RK5-1 if this fails: W5-T4 holds over the production ids only
    while every rung has its own entry in ``SOURCE_NOTES`` and no two entries (nor
    the generic sentence) coincide -- two ids sharing one sentence would leave a
    single item before a sentence that says "兩個來源"."""
    _ladder_premises(monkeypatch)  # two rungs, (bank_of_taiwan, yfinance_fx), TWD/USD
    assert set(SOURCE_NOTES) == {BANK, YAHOO}, BACK_TO_RISK
    sentences = [*SOURCE_NOTES.values(), GENERIC_SOURCE_NOTE]
    assert len(set(sentences)) == len(sentences), BACK_TO_RISK


def test_w5_t4_two_ids_sharing_one_sentence_is_caught() -> None:
    """The trigger compares ids, not sentences (RK5-R2, S-1), so two unlisted ids
    -- both read as the generic sentence -- still trigger W-RK5-1, and the W5-T4
    check goes red on them. Unreachable today (tripwire above); if it ever
    becomes reachable, it goes back to risk-compliance."""
    rows = [_ok("fx_unlisted_a", "fx_unlisted_b")]
    disclosures = fx_disclosures_for(rows)
    assert disclosures[-1] == W
    assert _w5_t4_violations(rows, disclosures) != []


def test_w5_t4_same_id_twice_is_one_sentence_and_no_mixed_note() -> None:
    """Sentence dedup does not hide a mix, and a shared id is never a mix."""
    rows = [_ok("fx_unlisted_a", "fx_unlisted_a")]
    assert fx_disclosures_for(rows) == [GENERIC_SOURCE_NOTE]


# --- end to end: the real valuator over the production ladder ----------------------


@dataclass(frozen=True)
class Book:
    """One USD holding valued over the production ladder by one scripted scenario."""

    name: str
    scenario: Scenario
    mixed: bool


#: Lookup order for one USD holding opened on ``OPENED``: fx_now (window ends
#: today), then fx_open (window ends on the open date).
BOOKS = [
    pytest.param(Book("4b", FOUR_B, mixed=True), id="now-yahoo-open-bank"),
    pytest.param(
        Book(
            "bank-recent-only",
            Scenario(bank=lambda call, day, today: day >= today - timedelta(days=3)),
            mixed=True,
        ),
        id="now-bank-open-yahoo",
    ),
    pytest.param(
        Book("both-bank", Scenario(bank=lambda call, day, today: True), mixed=False),
        id="both-bank",
    ),
    pytest.param(
        Book("both-yahoo", Scenario(bank=lambda call, day, today: False), mixed=False),
        id="both-yahoo",
    ),
]


def _recorded(ladder: _RecordingLadder, today: date) -> tuple[str, str]:
    """``(fx_now source, fx_open source)`` as they happened (the open date is OPENED)."""
    return ladder.source_on(today), ladder.source_on(OPENED)


@pytest.mark.parametrize("book", BOOKS)
def test_w5_t3_t5_the_summary_payload_end_to_end(api_harness: ApiHarness, book: Book) -> None:
    ladder, today = _serve(api_harness, book.scenario)
    _hold_usd(api_harness.positions)

    response = api_harness.client.get("/api/portfolio/summary")
    assert response.status_code == 200
    body = response.json()
    [row] = body["positions"]
    valuation = row["valuation"]
    assert valuation["status"] == "ok"
    now_source, open_source = _recorded(ladder, today)
    assert (valuation["fx"]["source"], valuation["fx_open"]["source"]) == (now_source, open_source)
    assert (now_source != open_source) is book.mixed  # not vacuous

    expected = list(dict.fromkeys([source_note(now_source), source_note(open_source)]))
    if book.mixed:
        expected.append(W)
        # W5-T5, back-end half: a mixed row always shows a backup side, and the
        # front end's badge fixture is exactly this pair of (source, status).
        statuses = {valuation["fx"]["data_status"], valuation["fx_open"]["data_status"]}
        assert DataStatus.BACKUP.value in statuses
        pairs = {
            (valuation["fx"]["source"], valuation["fx"]["data_status"]),
            (valuation["fx_open"]["source"], valuation["fx_open"]["data_status"]),
        }
        assert pairs == {(YAHOO, DataStatus.BACKUP.value), (BANK, DataStatus.FRESH.value)}
    assert body["fx_disclosures"] == expected
    assert APPROVED_BRIDGE not in body["fx_disclosures"]  # W5-T7


def test_w5_t3_unvalued_mixed_and_mismatched_rows_end_to_end(tmp_path: Path) -> None:
    """The production ladder gives AAPL a Yahoo fx_now and a Bank of Taiwan fx_open,
    but AAPL has no price (unvalued) and 2330/USD is an X-3c mismatched row; only
    MSFT, opened on a Yahoo day, is valued -- so no mix is stated."""
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, "AAPL", opened_at=OPEN_BANK)
    _hold(store, "MSFT", opened_at=OPEN_YAHOO)
    _hold(store, "2330", market="TW", currency="USD", opened_at=OPEN_BANK)
    services = _prices(("MSFT", "US", "400"), ("2330", "TW", "600"))

    summary = build_summary(store, _valuator(ladder.provider, services))

    rows = {row.symbol: row.valuation for row in summary.positions}
    assert rows["AAPL"].status == "insufficient_data"
    assert rows["AAPL"].fx is not None and rows["AAPL"].fx_open is not None
    assert rows["AAPL"].fx.source != rows["AAPL"].fx_open.source  # not vacuous
    assert rows["2330"].fx is None and rows["2330"].fx_open is None
    assert rows["MSFT"].status == "ok"
    assert summary.fx_disclosures == [YAHOO_NOTE]


def test_w5_t3_a_valued_mix_beside_them_is_stated_once(tmp_path: Path) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, "AAPL", opened_at=OPEN_BANK)
    _hold(store, "MSFT", opened_at=OPEN_YAHOO)
    _hold(store, "NVDA", opened_at=OPEN_BANK)
    _hold(store, "2330", market="TW", currency="USD", opened_at=OPEN_BANK)
    _hold(store, "TSLA", opened_at=OPEN_NOWHERE)  # fx_open UNAVAILABLE: unvalued
    services = _prices(
        ("AAPL", "US", "150"), ("MSFT", "US", "400"), ("NVDA", "US", "120"), ("TSLA", "US", "200")
    )

    summary = build_summary(store, _valuator(ladder.provider, services))

    statuses = {row.symbol: row.valuation.status for row in summary.positions}
    assert statuses == {
        "AAPL": "ok",
        "MSFT": "ok",
        "NVDA": "ok",
        "2330": "insufficient_data",
        "TSLA": "insufficient_data",
    }
    assert summary.fx_disclosures == [YAHOO_NOTE, BANK_NOTE, W]
    valuations = [row.valuation for row in summary.positions]
    assert _w5_t4_violations(valuations, summary.fx_disclosures) == []
    # W5-T5: at least one ok row has a backup side.
    assert any(
        info is not None and info.data_status is DataStatus.BACKUP
        for row in _ok_rows(valuations)
        for info in (row.fx, row.fx_open)
    )


# --- W5-T5: the front end's badge fixtures are these very rows --------------------


_FRONTEND_MIXED_ROW = re.compile(
    r'row\(\s*"ok",\s*"(\w+)",\s*"(\w+)",\s*\{\s*fxSource:\s*"(\w+)",\s*fxOpenSource:\s*"(\w+)"'
)


def test_w5_t5_the_front_end_fixtures_are_the_back_end_mixed_rows() -> None:
    """Every front-end W5-T5 fixture is a back-end row for which W-RK5-1 appears,
    with a backup side -- the badge and the sentence are read off the same rows."""
    text = (FRONTEND_APP / "lib" / "__tests__" / "fxBackupBadge.test.ts").read_text(
        encoding="utf-8"
    )
    block = text[text.index('describe("W5-T5 badge coupling') :]
    fixtures = _FRONTEND_MIXED_ROW.findall(block)
    assert len(fixtures) == 2  # not vacuous
    seen: set[tuple[str, str]] = set()
    for now_status, open_status, now_source, open_source in fixtures:
        now = _info(now_source, status=DataStatus(now_status))
        open_ = _info(open_source, status=DataStatus(open_status))
        # The front end's statuses are the ladder's labels for these ids.
        assert now.data_status is LADDER_STATUS[now_source]
        assert open_.data_status is LADDER_STATUS[open_source]
        rows = [_row("ok", now, open_)]
        disclosures = fx_disclosures_for(rows)
        assert disclosures[-1] == W
        assert DataStatus.BACKUP in {now.data_status, open_.data_status}
        seen.add((now_source, open_source))
    assert seen == {(YAHOO, BANK), (BANK, YAHOO)}


@pytest.mark.parametrize("case", CASES)
def test_w5_t5_wherever_the_mixed_note_appears_an_ok_row_is_backup(case: Case) -> None:
    rows = list(case.rows)
    if W not in fx_disclosures_for(rows):
        return
    assert any(
        info is not None and info.data_status is DataStatus.BACKUP
        for row in _ok_rows(rows)
        for info in (row.fx, row.fx_open)
    )


# --- W5-T6: no new string in the front end ------------------------------------------


def test_w5_t6_the_front_end_adds_no_string() -> None:
    """The sentence reaches the page only through ``fx_disclosures``, rendered
    verbatim as the last ``<li>`` of the 匯率貢獻 card's ``<details>``."""
    sources = [
        path
        for path in FRONTEND_APP.rglob("*")
        if path.suffix in {".ts", ".tsx"} and "node_modules" not in path.parts
    ]
    assert sources  # not vacuous
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for fragment in ("買入日匯率", "口徑差", "至少一筆持倉", "FX_OPEN_MIXED_SOURCES_NOTE"):
            assert fragment not in text, path
    cards = (FRONTEND_APP / "components" / "SummaryCards.tsx").read_text(encoding="utf-8")
    assert "<li key={disclosure}>{disclosure}</li>" in cards


# --- W5-T7: the bridge stays out of the overview, W-RK5-1 out of the card and push --


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/api/portfolio/summary", id="overview"),
        pytest.param(f"/api/advice/{SYMBOL}?market=US", id="card"),
        pytest.param("/api/portfolio/limits", id="limits"),
    ],
)
def test_w5_t7_only_the_overview_carries_the_mixed_note(api_harness: ApiHarness, path: str) -> None:
    """Each request on a fresh 4b ladder, so the book it values does mix."""
    _hold_usd(api_harness.positions)
    ladder, today = _serve(api_harness, FOUR_B)

    response = api_harness.client.get(path)
    assert response.status_code == 200
    now_source, open_source = _recorded(ladder, today)
    assert now_source != open_source  # not vacuous: the book behind this answer mixes
    body = response.json()
    if path == "/api/portfolio/summary":
        assert body["fx_disclosures"][-1] == W
        assert body["fx_disclosures"].count(W) == 1
        assert APPROVED_BRIDGE not in body["fx_disclosures"]
        assert APPROVED_BRIDGE not in response.text
    else:
        assert W not in response.text
        if path.startswith("/api/advice"):
            assert body["status"] == "ok"  # not vacuous: a card was produced
            assert APPROVED_BRIDGE in body["context_notes"]  # the card's own sentence


def test_w5_t7_the_push_never_carries_the_mixed_note(tmp_path: Path) -> None:
    harness = _alerts(tmp_path, FOUR_B)
    snap = harness.snapshot()
    ladder = harness.ladders[-1]
    assert _recorded(ladder, harness.today)[0] != _recorded(ladder, harness.today)[1]
    assert W not in (snap.fx_disclosure or "")
    result = evaluate_alerts(
        _fire(tmp_path, harness), harness.load, now=datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
    )
    assert len(result.events) == 1  # not vacuous
    assert W not in result.events[0].message


def test_w5_t7_only_the_summary_module_reads_the_constant() -> None:
    readers = sorted(
        str(path.relative_to(APP_ROOT))
        for path in APP_ROOT.rglob("*.py")
        if "FX_OPEN_MIXED_SOURCES_NOTE" in path.read_text(encoding="utf-8")
    )
    assert readers == ["portfolio/summary.py"]


# --- R5-4 and W-RK5-1 share one definition of "mixed" ----------------------------


@pytest.mark.parametrize("case", CASES)
def test_r5_4_the_warning_and_the_sentence_agree(
    case: Case, caplog: pytest.LogCaptureFixture
) -> None:
    rows = list(case.rows)
    with caplog.at_level("WARNING", logger="app.portfolio.summary"):
        summary_module._log_mixed_fx_sources(rows)
    logged = any("sources differ" in record.getMessage() for record in caplog.records)
    assert logged is (W in fx_disclosures_for(rows))
