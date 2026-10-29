"""排程台 × 第 1 條 disclosure (N-155): what is served, where, and what it never touches.

Sources, all 2026-10-28: 「風控 2026-10-28 #68 裁決（D-2 修訂／N-155 揭露規格）」 and its
follow-up (``2026-10-28-#68裁決補充-R4解讀與出貨方式-風控.md``, which governs where
they differ), ADR-0031 (CEO #69), 修訂 D-2 as rewritten under CEO #70
(「風控 2026-10-28 N-151 標籤掃描授權與 #70 D-2 改寫」). The structural halves
(C-6/C-7, T-1..T-5, R4-1) live in ``tests/test_playbook_boundary.py``; this module
is the behaviour:

* **B-1 / R4-2** -- whatever the stored risk budget (cap 1 at 0.05, 0.10, 0.50,
  unreadable, a stored budget that failed validation so the default stands in
  -- ``from_default`` True, ADR-0032 K-8 / DL-5 -- and every cap at once from
  TIGHT to LOOSE), ``/today``,
  ``/rule-set`` and every ``playbook_*`` table are identical; and **R4-5** --
  ``/confirm-rules`` is never refused and writes the same parameters.
* **B-2** -- the disclosure is on all five modes and all three endpoints,
  verbatim, with the stored (non-default) parameters and the stored cap 1, and
  across n_targets 11 / 7 / 5 against cap 1 at 10% and 25%: shown whatever the
  two percentages are.
* **B-3** -- its ``rules_version`` is the version the same response used.
* **B-4** -- it is never written to a table, and its title appears in no EXIT
  response, alerts output, ``page_summary`` or directive log.
* **缺值** and **R4-4** -- each missing value swaps in only its own sentence, the
  pct fields go ``null`` (never ``0``), no 10% stands in, and a settings failure
  of any kind still answers 200 with the same directives. A non-positive
  ``batches_per_target`` takes ①-缺b / ①-缺nb (「風控 2026-10-28 #68 裁決補充二
  （N-155 交件已知限制 2～5）」 第 1 項, four-case table).
* **②-預設** (P2, 「風控 2026-10-29 N-156 字面定稿與表態」 第 5 項, ADR-0032 K-9) --
  ②-缺 > ②-預設 > ②, the loaded value in the sentence, and a failed read is
  never reported as a fallback: ``weight is None`` always comes with
  ``from_default`` False.
* **R4-6** -- the advice, settings and portfolio responses do not change.

The sentences are retyped here, character by character, rather than imported:
a drift in ``app/api/playbook_cap1_wording.py`` has to fail this file.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advice.limits import RiskBudget
from app.api import deps
from app.api import playbook_cap1_wording as cap1_wording
from app.api.deps import get_playbook_service
from app.api.playbook import RuleSetResponse, TodayResponse
from app.api.playbook_cap1_wording import (
    Cap1Reading,
    PlaybookCap1Disclosure,
    compose,
    format_pct,
)
from app.main import app
from app.playbook.models import RuleParams
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from app.settings.models import AppSettings
from app.settings.store import LoadedSettings, SettingsStore
from tests.api_helpers import CLIENT_HEADERS, FakePriceService, recent_bars
from tests.conftest import ApiHarness
from tests.import_graph import APP_ROOT, imported_modules
from tests.playbook_helpers import batch as make_batch
from tests.playbook_helpers import confirm_rule_set
from tests.playbook_helpers import params as make_params
from tests.settings_fallback_helpers import SCHEMA_MISMATCH, write_raw

# 修訂 D-2 (5) ② as rewritten under CEO #70 (風控 N-151 與 #70 D-2 改寫 第二項第 3
# 點): every risk-budget field at its tightest and at its loosest. One copy, kept
# with the 測試 ② that first needed it, so the two matrices cannot drift apart.
from tests.test_playbook_cap1_d2 import LOOSE, TIGHT

#: A Thursday: a 排程日, so the fixed book issues entries as well as exits.
EVALUATION_DAY = date(2026, 8, 13)
HISTORY = 40

# --- the approved sentences, retyped (補充裁定 第 4 節) ------------------------------

TITLE = "排程台每檔規模與第 1 條上限"
LINE_1 = (
    "依此規則集的參數（部署比例 {deploy_ratio_pct}、{n_targets} 檔均分、每檔分 "
    "{batches_per_target} 批），每檔標的的預定投入金額為 TOTAL_DEPLOY ÷ {n_targets}，約為計算 "
    "TOTAL_DEPLOY 當時排程台總資產（含現金）的 {per_target_pct}；實際股數依各批進場時的收盤價"
    "換算，實際成本與日後市值的佔比可能與此數不同。"
)
LINE_2 = (
    "第 1 條・單一標的佔比上限目前設定為 {cap1_pct}，分母是庫存的已估值部位市值（不含現金，即"
    "設定頁所稱的「總資產」）。排程台與庫存是兩套獨立帳冊，上述兩個百分比的分母不同，不能直接"
    "比較大小。"
)
LINE_3 = (
    "如果你也把排程台的持股記入庫存，第 1 條會以庫存的分母計算這些持股的佔比：例如庫存只有排程台"
    "的 {n_targets} 檔且各檔市值相同時，每檔約佔 {per_target_book_pct}；達到或超過第 1 條設定值"
    "時，個股頁會顯示該檔已達或超過上限。"
)
LINE_4 = (
    "排程台計算股數時不讀取第 1 條或其他任何一條風險上限的設定，也不會因這些上限調整任何一批的"
    "股數；兩邊各自計算，本系統不會自動調和兩者的結果。"
)
#: ②-預設 (風控 2026-10-29 N-156 第 5 項), retyped.
LINE_2_DEFAULT = (
    "第 1 條・單一標的佔比上限目前使用預設值 {cap1_pct}：設定頁的風險預算原本存的內容沒有通過驗證，"
    "這個值不是原本存的內容；其分母是庫存的已估值部位市值（不含現金，即設定頁所稱的「總資產」）。"
    "排程台與庫存是兩套獨立帳冊，上述兩個百分比的分母不同，不能直接比較大小。"
)
LINE_2_MISSING = (
    "第 1 條・單一標的佔比上限的目前設定值讀取失敗；其分母是庫存的已估值部位市值（不含現金，即"
    "設定頁所稱的「總資產」）。排程台與庫存是兩套獨立帳冊，兩者的分母不同，不能直接比較大小。"
)
LINE_1_MISSING = (
    "此規則集的每檔規模無法由目前參數算出（標的檔數 n_targets 不是正整數），本區塊不陳述每檔佔比。"
)
#: ①-缺b / ①-缺nb (補充裁定二 第 1 項), retyped.
LINE_1_MISSING_B = (
    "此規則集的每檔批數 batches_per_target 不是正整數，本區塊不陳述每檔規模與每檔佔比。"
)
LINE_1_MISSING_NB = (
    "此規則集的每檔規模無法由目前參數算出（標的檔數 n_targets 與每檔批數 batches_per_target "
    "都不是正整數），本區塊不陳述每檔佔比。"
)
LINE_3_MISSING = (
    "如果你也把排程台的持股記入庫存，第 1 條會以庫存的分母計算這些持股的佔比；達到或超過第 1 條"
    "設定值時，個股頁會顯示該檔已達或超過上限。"
)


def expected_lines(
    *,
    deploy_ratio_pct: str,
    n_targets: int,
    batches_per_target: int,
    per_target_pct: str | None,
    cap1_pct: str | None,
    per_target_book_pct: str | None,
    cap1_from_default: bool = False,
) -> list[str]:
    """①～④ filled by hand, the 缺值 sentences swapped in where a value is missing."""
    if per_target_pct is None:
        first, third = LINE_1_MISSING, LINE_3_MISSING
    else:
        first = LINE_1.format(
            deploy_ratio_pct=deploy_ratio_pct,
            n_targets=n_targets,
            batches_per_target=batches_per_target,
            per_target_pct=per_target_pct,
        )
        third = LINE_3.format(n_targets=n_targets, per_target_book_pct=per_target_book_pct)
    if cap1_pct is None:
        second = LINE_2_MISSING
    elif cap1_from_default:
        second = LINE_2_DEFAULT.format(cap1_pct=cap1_pct)
    else:
        second = LINE_2.format(cap1_pct=cap1_pct)
    return [first, second, third, LINE_4]


# --- the stored rule set and settings ---------------------------------------------

#: A stored rule set that differs from the system default in every figure the
#: disclosure states (default: 70% / 5 / 3, version 1), so a disclosure built
#: from the defaults cannot match (補充裁定 / 原裁決 2.4 測試 ③).
STORED_VERSION = 3
STORED = {"version": STORED_VERSION, "deploy_ratio": Decimal("0.60"), "n_targets": 4}
STORED_BATCHES = 2
#: The stored cap 1: not the 10% default, so a disclosure that read
#: ``DEFAULT_MAX_POSITION_WEIGHT`` instead of the store cannot match.
STORED_CAP1 = 0.12
#: The stored risk budget every book opens with unless a test names another.
STORED_BUDGET = RiskBudget(max_position_weight=STORED_CAP1)
#: 60% ÷ 4 = 15% of 排程台總資產; 1 ÷ 4 = 25% of the book.
STORED_LINES = expected_lines(
    deploy_ratio_pct="60%",
    n_targets=4,
    batches_per_target=2,
    per_target_pct="15%",
    cap1_pct="12%",
    per_target_book_pct="25%",
)
#: What the system default (unconfirmed path) states against the stored cap 1.
DEFAULT_LINES = expected_lines(
    deploy_ratio_pct="70%",
    n_targets=5,
    batches_per_target=3,
    per_target_pct="14%",
    cap1_pct="12%",
    per_target_book_pct="20%",
)

#: A stored risk budget that fails validation, so the default stands in for it
#: and the reading says ``from_default`` (ADR-0032 K-8 / DL-5).
FALLBACK = "fallback"

#: B-1 / R4-2: cap 1 alone at 0.05, 0.10, 0.50, unreadable and on its default
#: after a failed validation, plus TIGHT and LOOSE.
BUDGETS: dict[str, RiskBudget | str | None] = {
    "cap1-0.05": RiskBudget(max_position_weight=0.05),
    "cap1-0.10": RiskBudget(max_position_weight=0.10),
    "cap1-0.50": RiskBudget(max_position_weight=0.50),
    "cap1-unreadable": None,
    "cap1-fallback": FALLBACK,
    "tight": TIGHT,
    "loose": LOOSE,
}


class _UnreadableSettings:
    """A settings store whose every read fails, the way a locked or corrupt file does."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def load(self) -> AppSettings:
        raise self._error

    def load_with_status(self) -> LoadedSettings:
        raise self._error


def _settings_provider(root: Path, budget: RiskBudget | str | None) -> Callable[[], object]:
    """What ``deps._default_settings_store`` answers with for ``budget``.

    ``None`` is a store whose reads raise: the production path then reads
    ``Cap1Reading(None, False)`` through the real :func:`deps.get_cap1_reading`,
    which is what this module tests -- the dependency itself is never
    overridden here. :data:`FALLBACK` is a store whose ``risk_budget`` row fails
    validation, so the same function reads the default with ``from_default``.
    """
    if budget is None:
        unreadable = _UnreadableSettings(sqlite3.OperationalError("database is locked"))
        return lambda: unreadable
    store = SettingsStore(root / "settings.db")
    if budget == FALLBACK:
        store.save(AppSettings())
        write_raw(store, "risk_budget", SCHEMA_MISMATCH)
        return lambda: store
    assert isinstance(budget, RiskBudget)
    store.save(AppSettings(risk_budget=budget))
    return lambda: store


class _PinnedService(PlaybookService):
    """The real service, with the clock pinned to :data:`EVALUATION_DAY`."""

    def evaluate_today(self, *, today: date | None = None) -> Any:
        return super().evaluate_today(today=today or EVALUATION_DAY)

    def rule_set_status(self, *, today: date | None = None) -> Any:
        return super().rule_set_status(today=today or EVALUATION_DAY)

    def confirm_rules(self, *, capital: Decimal, today: date | None = None) -> Any:
        return super().confirm_rules(capital=capital, today=today or EVALUATION_DAY)

    def emergency_exit(self, *, today: date | None = None) -> Any:
        return super().emergency_exit(today=today or EVALUATION_DAY)


@dataclass
class Book:
    client: TestClient
    store: PlaybookStore
    db: Path


Mode = str
MODES: tuple[Mode, ...] = ("normal", "defense", "frozen", "emergency_frozen", "unconfirmed")


def _index_closes(mode: Mode) -> list[float]:
    if mode == "defense":
        # Four closes under the 20-day line (19,800): M1 turns defense on.
        return [20000.0] * (HISTORY - 4) + [19000.0] * 4
    return [20000.0] * HISTORY


def _seed(
    root: Path,
    *,
    mode: Mode = "normal",
    holdings: bool = True,
    rule_set: dict[str, object] | None = None,
) -> tuple[PlaybookStore, PlaybookService]:
    """One fixed book: a stop-loss, a take-profit and an entry, in ``mode``."""
    root.mkdir(parents=True, exist_ok=True)
    db = root / "playbook.db"
    store = PlaybookStore(db_path=db)
    overrides = dict(STORED if rule_set is None else rule_set)
    batches = overrides.pop("batches_per_target", STORED_BATCHES)
    assert isinstance(batches, int)
    if mode != "unconfirmed":
        confirm_rule_set(store, batches_per_target=batches, **overrides)
    prices = FakePriceService()
    index = FakePriceService()
    index.seed("^TWII", recent_bars(_index_closes(mode), symbol="^TWII", end=EVALUATION_DAY))
    if holdings:
        store.ensure_batches(["2330", "2317", "2454"], batches_per_target=max(batches, 1))
        store.save_batch(make_batch(cost="100", shares=300))
        store.save_batch(make_batch(symbol="2454", cost="100", shares=300))
        prices.seed(
            "2330",
            recent_bars([100.0] * (HISTORY - 1) + [85.0], symbol="2330", end=EVALUATION_DAY),
        )
        prices.seed("2317", recent_bars([100.0] * HISTORY, symbol="2317", end=EVALUATION_DAY))
        prices.seed(
            "2454",
            recent_bars([100.0] * (HISTORY - 1) + [121.0], symbol="2454", end=EVALUATION_DAY),
        )
    store.set_capital(cash=Decimal("1000000"), total_deploy=Decimal("600000"), source="initial")
    if mode == "frozen":
        store.freeze(until=EVALUATION_DAY + timedelta(days=30), reason="S3 測試凍結")
    elif mode == "emergency_frozen":
        store.freeze_emergency(until=EVALUATION_DAY + timedelta(days=30))
    service = _PinnedService(
        store=store, market_resolver={"TW": prices}, index_resolver={"TW": index, "US": index}
    )
    return store, service


@pytest.fixture
def open_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Book]]:
    """Open a seeded book behind the real app, with the settings store as given."""
    clients: list[TestClient] = []

    def _open(
        name: str,
        *,
        budget: RiskBudget | str | None = STORED_BUDGET,
        settings: Callable[[], object] | None = None,
        **seed: Any,
    ) -> Book:
        root = tmp_path / name
        store, service = _seed(root, **seed)
        provider = settings if settings is not None else _settings_provider(root, budget)
        monkeypatch.setattr(deps, "_default_settings_store", provider)
        app.dependency_overrides[get_playbook_service] = lambda: service
        client = TestClient(app, headers=CLIENT_HEADERS)
        clients.append(client)
        return Book(client=client, store=store, db=root / "playbook.db")

    yield _open
    for client in clients:
        client.close()
    app.dependency_overrides.clear()


#: Columns and ``playbook_state`` keys that hold a wall-clock write time, the
#: only thing two otherwise identical runs may differ in.
_TIMESTAMP_COLUMNS = frozenset({"created_at", "updated_at", "submitted_at", "settled_at"})
_TIMESTAMP_STATE_KEYS = frozenset({"rule_set_confirmed_at", "total_deploy_set_at"})


def _playbook_tables(db: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every ``playbook_*`` table, every row, timestamps masked."""
    with sqlite3.connect(db) as conn:
        names = [
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'playbook_%' "
                "ORDER BY name"
            )
        ]
        dump: dict[str, list[tuple[Any, ...]]] = {}
        for name in names:
            # ``name`` comes from sqlite_master, not from any input.
            cursor = conn.execute(f"SELECT * FROM {name}")
            columns = [column[0] for column in cursor.description]
            rows = []
            for row in cursor.fetchall():
                values = dict(zip(columns, row, strict=True))
                for column in _TIMESTAMP_COLUMNS & set(columns):
                    values[column] = "<ts>"
                if name == "playbook_state" and values["key"] in _TIMESTAMP_STATE_KEYS:
                    values["value"] = "<ts>"
                rows.append(tuple(values[column] for column in columns))
            dump[name] = sorted(rows, key=repr)
    return dump


# --- the wording module itself ---------------------------------------------------


def test_every_sentence_in_the_module_is_the_approved_one() -> None:
    """逐字: each constant equals the retyped 定稿 (補充裁定 第 4 節)."""
    assert cap1_wording.TITLE == TITLE
    assert cap1_wording.LINE_PER_TARGET == LINE_1
    assert cap1_wording.LINE_CAP1 == LINE_2
    assert cap1_wording.LINE_BOOK_EXAMPLE == LINE_3
    assert cap1_wording.LINE_INDEPENDENCE == LINE_4
    assert cap1_wording.LINE_CAP1_UNREADABLE == LINE_2_MISSING
    assert cap1_wording.LINE_CAP1_DEFAULT == LINE_2_DEFAULT
    assert cap1_wording.LINE_PER_TARGET_UNAVAILABLE == LINE_1_MISSING
    assert cap1_wording.LINE_BOOK_EXAMPLE_UNAVAILABLE == LINE_3_MISSING
    assert cap1_wording.LINE_PER_TARGET_NO_BATCHES == LINE_1_MISSING_B
    assert cap1_wording.LINE_PER_TARGET_UNAVAILABLE_NO_BATCHES == LINE_1_MISSING_NB


def test_no_sentence_carries_the_word_for_advice() -> None:
    """排程台用語紀律: the block never says 建議 (原裁決 2.3)."""
    for sentence in (
        TITLE,
        LINE_1,
        LINE_2,
        LINE_3,
        LINE_4,
        LINE_1_MISSING,
        LINE_1_MISSING_B,
        LINE_1_MISSING_NB,
        LINE_2_MISSING,
        LINE_2_DEFAULT,
        LINE_3_MISSING,
    ):
        assert "建議" not in sentence


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (Decimal("0.14"), "14%"),
        (Decimal("0.1"), "10%"),
        (Decimal("0.2"), "20%"),
        (Decimal("0.125"), "12.5%"),
        # ROUND_HALF_UP, not banker's rounding: 14.25 -> 14.3 and 0.05 -> 0.1.
        (Decimal("0.1425"), "14.3%"),
        (Decimal("0.0005"), "0.1%"),
        (Decimal("0.70") / 11, "6.4%"),
        (Decimal(1) / 7, "14.3%"),
        (Decimal(str(0.12)), "12%"),
    ],
)
def test_percentages_round_half_up_to_one_place_and_drop_a_trailing_zero(
    ratio: Decimal, expected: str
) -> None:
    """ADR-0031 C-3 / 補充裁定 第 4 節: 「14%」, never 「14.0%」."""
    assert format_pct(ratio) == expected


def test_compose_takes_only_keyword_arguments_and_has_no_defaults() -> None:
    """C-1: no positional slot to transpose and no default to fall back on."""
    parameters = inspect.signature(compose).parameters.values()
    assert {p.name for p in parameters} == {
        "rules_version",
        "deploy_ratio",
        "n_targets",
        "batches_per_target",
        "deploy_ratio_pct",
        "cap1_reading",
    }
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters)
    assert all(p.default is inspect.Parameter.empty for p in parameters)


def test_the_disclosure_has_no_comparison_flag_or_status_field() -> None:
    """C-2 / PD-6: facts and sentences only -- whether to show it is never a field."""
    assert set(PlaybookCap1Disclosure.model_fields) == {
        "title",
        "lines",
        "rules_version",
        "per_target_pct",
        "cap1_pct",
        "per_target_book_pct",
    }


def test_the_lines_can_never_be_empty() -> None:
    with pytest.raises(ValueError):
        PlaybookCap1Disclosure(
            title=TITLE,
            lines=[],
            rules_version=1,
            per_target_pct=None,
            cap1_pct=None,
            per_target_book_pct=None,
        )


def _reading(cap1: Decimal | None, *, from_default: bool = False) -> Cap1Reading:
    return Cap1Reading(weight=cap1, from_default=from_default)


def _compose(
    *, n_targets: int = 5, cap1: Decimal | None = Decimal("0.10"), from_default: bool = False
) -> Any:
    return compose(
        rules_version=7,
        deploy_ratio=Decimal("0.70"),
        n_targets=n_targets,
        batches_per_target=3,
        deploy_ratio_pct="70%",
        cap1_reading=_reading(cap1, from_default=from_default),
    )


# --- ②-預設 (P2) -------------------------------------------------------------------------


def test_a_default_cap1_takes_sentence_2_default_with_the_loaded_value() -> None:
    """②-預設: the value actually loaded is stated, the rest is unchanged."""
    disclosure = _compose(cap1=Decimal("0.1"), from_default=True)

    assert disclosure.lines == expected_lines(
        deploy_ratio_pct="70%",
        n_targets=5,
        batches_per_target=3,
        per_target_pct="14%",
        cap1_pct="10%",
        per_target_book_pct="20%",
        cap1_from_default=True,
    )
    assert disclosure.lines[1] == LINE_2_DEFAULT.format(cap1_pct="10%")
    assert disclosure.cap1_pct == "10%"
    # {cap1_pct} is the reading's weight, not a constant: another value shows.
    other = _compose(cap1=Decimal("0.125"), from_default=True)
    assert other.lines[1] == LINE_2_DEFAULT.format(cap1_pct="12.5%")


@pytest.mark.parametrize(
    ("reading", "expected"),
    [
        (Cap1Reading(weight=None, from_default=False), LINE_2_MISSING),
        (
            Cap1Reading(weight=Decimal("0.1"), from_default=True),
            LINE_2_DEFAULT.format(cap1_pct="10%"),
        ),
        (Cap1Reading(weight=Decimal("0.1"), from_default=False), LINE_2.format(cap1_pct="10%")),
    ],
    ids=["missing", "default", "stored"],
)
def test_sentence_2_is_one_of_three_by_precedence(reading: Cap1Reading, expected: str) -> None:
    """②-缺 > ②-預設 > ②, mutually exclusive; ①, ③ and ④ do not move."""
    disclosure = compose(
        rules_version=7,
        deploy_ratio=Decimal("0.70"),
        n_targets=5,
        batches_per_target=3,
        deploy_ratio_pct="70%",
        cap1_reading=reading,
    )
    reference = _compose()
    assert disclosure.lines[1] == expected
    assert [disclosure.lines[i] for i in (0, 2, 3)] == [reference.lines[i] for i in (0, 2, 3)]
    assert len(disclosure.lines) == 4


def test_an_unreadable_value_can_never_be_a_fallback() -> None:
    """ADR-0032 延伸 7 / DL-5: ``weight is None`` forces ``from_default`` False."""
    with pytest.raises(ValueError):
        Cap1Reading(weight=None, from_default=True)


def test_the_default_sentence_carries_no_remedy() -> None:
    """Like ②-缺: no 「請」, no 「覆寫」, no instruction to do anything."""
    for word in ("請", "覆寫", "確認", "儲存"):
        assert word not in LINE_2_DEFAULT


def test_an_unreadable_cap1_replaces_sentence_2_only() -> None:
    """②-缺: the rest stays, the pct is ``null`` and no 10% stands in for it."""
    disclosure = _compose(cap1=None)

    assert disclosure.lines == expected_lines(
        deploy_ratio_pct="70%",
        n_targets=5,
        batches_per_target=3,
        per_target_pct="14%",
        cap1_pct=None,
        per_target_book_pct="20%",
    )
    assert disclosure.cap1_pct is None
    assert (disclosure.per_target_pct, disclosure.per_target_book_pct) == ("14%", "20%")
    assert not any("10%" in line for line in disclosure.lines)


@pytest.mark.parametrize("n_targets", [0, -1, -5])
def test_a_non_positive_n_targets_replaces_sentences_1_and_3_only(n_targets: int) -> None:
    """①-缺 / ③-缺: no per-target figure, and the raw count is never written out."""
    disclosure = _compose(n_targets=n_targets)

    assert disclosure.lines == [
        LINE_1_MISSING,
        LINE_2.format(cap1_pct="10%"),
        LINE_3_MISSING,
        LINE_4,
    ]
    assert disclosure.per_target_pct is None
    assert disclosure.per_target_book_pct is None
    assert disclosure.cap1_pct == "10%"
    text = "".join(disclosure.lines)
    assert f"{n_targets} 檔" not in text
    assert "÷ 0" not in text and f"÷ {n_targets}" not in text


def test_both_missing_values_replace_their_own_sentences_and_4_stays() -> None:
    disclosure = _compose(n_targets=0, cap1=None)

    assert disclosure.lines == [LINE_1_MISSING, LINE_2_MISSING, LINE_3_MISSING, LINE_4]
    assert (disclosure.per_target_pct, disclosure.cap1_pct, disclosure.per_target_book_pct) == (
        None,
        None,
        None,
    )
    assert disclosure.title == TITLE
    assert disclosure.rules_version == 7


#: 補充裁定二 第 1 項 four-case table, for a non-positive batch count: (n_targets,
#: batches_per_target) -> the ① sentence, whether ③ keeps its example, and the
#: book pct that goes with it. The (> 0, > 0) and (≤ 0, > 0) rows are the cases
#: above.
BATCH_CASES = [
    (5, 0, LINE_1_MISSING_B, "20%"),
    (5, -1, LINE_1_MISSING_B, "20%"),
    (7, 0, LINE_1_MISSING_B, "14.3%"),
    (0, 0, LINE_1_MISSING_NB, None),
    (0, -1, LINE_1_MISSING_NB, None),
    (-3, -1, LINE_1_MISSING_NB, None),
]


def _compose_batches(n_targets: int, batches: int, cap1: Decimal | None) -> Any:
    return compose(
        rules_version=7,
        deploy_ratio=Decimal("0.70"),
        n_targets=n_targets,
        batches_per_target=batches,
        deploy_ratio_pct="70%",
        cap1_reading=_reading(cap1),
    )


@pytest.mark.parametrize("cap1", [Decimal("0.10"), None], ids=["cap1-read", "cap1-missing"])
@pytest.mark.parametrize(
    ("n_targets", "batches", "first", "book_pct"),
    BATCH_CASES,
    ids=[f"n{n}-b{b}" for n, b, _, _ in BATCH_CASES],
)
def test_a_non_positive_batch_count_takes_its_own_sentence_1(
    n_targets: int, batches: int, first: str, book_pct: str | None, cap1: Decimal | None
) -> None:
    """①-缺b / ①-缺nb: ① replaced, ③ follows n_targets alone, ② and ④ independent.

    The raw batch count is never written out, and ``per_target_pct`` is ``None``
    because ① no longer states a share (AV-16).
    """
    disclosure = _compose_batches(n_targets, batches, cap1)

    second = LINE_2_MISSING if cap1 is None else LINE_2.format(cap1_pct="10%")
    third = (
        LINE_3_MISSING
        if book_pct is None
        else LINE_3.format(n_targets=n_targets, per_target_book_pct=book_pct)
    )
    assert disclosure.lines == [first, second, third, LINE_4]
    assert len(disclosure.lines) == 4
    assert disclosure.lines[3] == LINE_4
    assert disclosure.per_target_pct is None
    assert disclosure.per_target_book_pct == book_pct
    assert disclosure.cap1_pct == (None if cap1 is None else "10%")
    text = "".join(disclosure.lines)
    assert "分 0 批" not in text and "分 -1 批" not in text
    assert f"分 {batches}" not in text and f"{batches} 批" not in text
    assert "÷ 0" not in text


def test_a_stored_non_positive_batch_count_gets_its_sentence_through_the_endpoints(
    open_book: Callable[..., Book],
) -> None:
    """①-缺b end to end: stored 4 targets with 0 batches, stored cap 1 = 0.12."""
    book = open_book(
        "bad-batches",
        holdings=False,
        rule_set={
            "version": 2,
            "deploy_ratio": Decimal("0.70"),
            "n_targets": 4,
            "batches_per_target": 0,
        },
    )
    for response in (
        book.client.get("/api/playbook/rule-set"),
        book.client.post("/api/playbook/confirm-rules", json={"capital": "1000000"}),
        book.client.get("/api/playbook/today"),
    ):
        assert response.status_code == 200
        disclosure = response.json()["cap1_disclosure"]
        assert disclosure["lines"] == [
            LINE_1_MISSING_B,
            LINE_2.format(cap1_pct="12%"),
            LINE_3.format(n_targets=4, per_target_book_pct="25%"),
            LINE_4,
        ]
        assert disclosure["per_target_pct"] is None
        assert disclosure["per_target_book_pct"] == "25%"


def test_missing_pct_fields_serialise_as_null_not_zero() -> None:
    """AV-16: a figure that could not be computed is absent, not 0."""
    body = json.loads(_compose(n_targets=0, cap1=None).model_dump_json())
    assert body["per_target_pct"] is None
    assert body["cap1_pct"] is None
    assert body["per_target_book_pct"] is None


# --- deps.get_cap1_reading (C-4 as amended by ADR-0032 K-9, R4-4) ----------------------


def test_get_cap1_reading_reads_the_stored_value_through_the_shared_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same store, same field as the advice card; no store built per call."""
    store = SettingsStore(tmp_path / "settings.db")
    store.save(AppSettings(risk_budget=RiskBudget(max_position_weight=STORED_CAP1)))
    built: list[SettingsStore] = []

    def provider() -> SettingsStore:
        built.append(store)
        return store

    monkeypatch.setattr(deps, "_default_settings_store", provider)
    expected = Cap1Reading(weight=Decimal("0.12"), from_default=False)
    assert deps.get_cap1_reading() == expected
    assert deps.get_cap1_reading() == expected
    assert built == [store, store]  # the memoized provider, never ``SettingsStore(...)``


def test_get_cap1_reading_says_from_default_for_a_failed_stored_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K-9: ``from_default`` is the settings layer's one judgement, the weight the default."""
    store = SettingsStore(tmp_path / "settings.db")
    store.save(AppSettings(risk_budget=RiskBudget(max_position_weight=STORED_CAP1)))
    write_raw(store, "risk_budget", SCHEMA_MISMATCH)
    monkeypatch.setattr(deps, "_default_settings_store", lambda: store)

    assert deps.get_cap1_reading() == Cap1Reading(weight=Decimal("0.1"), from_default=True)


def test_get_cap1_reading_ignores_fallbacks_of_other_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SettingsStore(tmp_path / "settings.db")
    store.save(AppSettings(risk_budget=RiskBudget(max_position_weight=STORED_CAP1)))
    for section in ("cost_model", "alerts", "net_worth"):
        write_raw(store, section, SCHEMA_MISMATCH)
    monkeypatch.setattr(deps, "_default_settings_store", lambda: store)

    assert deps.get_cap1_reading() == Cap1Reading(weight=Decimal("0.12"), from_default=False)


def test_get_cap1_reading_reads_once_with_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K-9: exactly one ``load_with_status()``, no ``load()``, no raw payload."""
    calls: list[str] = []

    class _Counting(SettingsStore):
        def load(self) -> AppSettings:
            calls.append("load")
            return super().load()

        def load_with_status(self) -> LoadedSettings:
            calls.append("load_with_status")
            return super().load_with_status()

    store = _Counting(tmp_path / "settings.db")
    monkeypatch.setattr(deps, "_default_settings_store", lambda: store)
    deps.get_cap1_reading()
    assert calls == ["load_with_status"]
    source = inspect.getsource(deps.get_cap1_reading)
    assert "app_settings" not in source and "_parse_section" not in source


def test_get_cap1_reading_is_built_on_the_memoized_store() -> None:
    """C-4: the provider it calls is the ``lru_cache``-d process-wide store."""
    source = inspect.getsource(deps.get_cap1_reading)
    assert "_default_settings_store()" in source
    assert "SettingsStore(" not in source
    assert hasattr(deps._default_settings_store, "cache_clear")


@pytest.mark.parametrize(
    "failure",
    [
        sqlite3.OperationalError("database is locked"),
        RuntimeError("anything at all"),
        ValueError("validation"),
        KeyError("risk_budget"),
    ],
    ids=["sqlite", "runtime", "validation", "key"],
)
def test_get_cap1_reading_answers_unreadable_on_any_read_failure(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """R4-4 / 延伸 7: every failure reads as "unreadable", never as a fallback."""
    unreadable = _UnreadableSettings(failure)
    monkeypatch.setattr(deps, "_default_settings_store", lambda: unreadable)
    reading = deps.get_cap1_reading()
    assert reading == Cap1Reading(weight=None, from_default=False)
    assert reading.from_default is False


def test_get_cap1_reading_answers_unreadable_when_the_store_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R4-4: building the store (and its S2 migration) failing is a read failure too."""

    def broken() -> SettingsStore:
        raise sqlite3.DatabaseError("file is not a database")

    monkeypatch.setattr(deps, "_default_settings_store", broken)
    assert deps.get_cap1_reading() == Cap1Reading(weight=None, from_default=False)


@pytest.mark.parametrize("from_default", [False, True])
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_get_cap1_reading_answers_unreadable_for_a_non_finite_value(
    monkeypatch: pytest.MonkeyPatch, value: float, from_default: bool
) -> None:
    """Non-finite is unreadable even when the section was reported as a fallback."""
    fake = SimpleNamespace(
        load_with_status=lambda: SimpleNamespace(
            settings=SimpleNamespace(risk_budget=SimpleNamespace(max_position_weight=value)),
            fallback_sections=("risk_budget",) if from_default else (),
        )
    )
    monkeypatch.setattr(deps, "_default_settings_store", lambda: fake)
    assert deps.get_cap1_reading() == Cap1Reading(weight=None, from_default=False)


# --- B-1 / R4-2 / R4-5: nothing the risk budget holds changes anything -------------------

#: ``/today`` fields R4-2 names, compared verbatim across every budget.
TODAY_FIELDS = ("directives", "snapshot", "page_summary", "warnings", "attribution", "mode_reason")
#: ``/rule-set`` fields R4-2 names.
RULE_SET_FIELDS = ("rules", "params", "attribution")


def _today_and_rule_set(book: Book) -> dict[str, Any]:
    today = book.client.get("/api/playbook/today")
    rule_set = book.client.get("/api/playbook/rule-set")
    assert today.status_code == 200 and rule_set.status_code == 200
    today_body, rule_set_body = today.json(), rule_set.json()
    return {
        "today": {field: today_body[field] for field in TODAY_FIELDS},
        "rule_set": {field: rule_set_body[field] for field in RULE_SET_FIELDS},
        "tables": _playbook_tables(book.db),
    }


def test_the_budget_matrix_moves_cap_1_and_then_every_cap() -> None:
    """The matrix is what 修訂 D-2 (5) ② and R4-2 ask for, not a subset of it."""
    caps = {
        name: b.max_position_weight if isinstance(b, RiskBudget) else b
        for name, b in BUDGETS.items()
    }
    assert caps == {
        "cap1-0.05": 0.05,
        "cap1-0.10": 0.10,
        "cap1-0.50": 0.50,
        "cap1-unreadable": None,
        "cap1-fallback": FALLBACK,
        "tight": 0.05,
        "loose": 0.50,
    }
    # TIGHT and LOOSE differ in every field, so a field added later has to be
    # placed in both (補充 #70 D-2 改寫 第二項第 3 點).
    assert {f for f in RiskBudget.model_fields if getattr(TIGHT, f) != getattr(LOOSE, f)} == set(
        RiskBudget.model_fields
    )
    # 0.15 would trip the S2 migration and quietly test 0.10 instead.
    assert 0.15 not in caps.values()


def test_today_rule_set_and_every_playbook_table_are_identical_whatever_the_risk_budget(
    open_book: Callable[..., Book], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-1 / R4-2 (and PD-4): seven budgets, one answer.

    Cap 1 at 0.05 / 0.10 / 0.50 / unreadable / on its default after a failed
    validation (``from_default`` True; every other entry is False, ADR-0032
    K-8), then every risk-budget field at once from TIGHT to LOOSE (CEO #70).
    Compared verbatim: ``/today``'s
    directives, snapshot, page_summary, warnings, attribution and mode_reason;
    ``/rule-set``'s rules, params and attribution; every ``playbook_*`` table.
    """
    results = {
        name: _today_and_rule_set(open_book(name, budget=budget))
        for name, budget in BUDGETS.items()
    }

    reference = results["cap1-0.10"]
    for name, result in results.items():
        assert result == reference, name
    # Not vacuous: the matrix really holds both ``from_default`` values.
    readings = {
        name: _reading_for(budget, tmp_path / f"reading-{name}", monkeypatch)
        for name, budget in BUDGETS.items()
    }
    assert {reading.from_default for reading in readings.values()} == {False, True}
    assert readings["cap1-fallback"] == Cap1Reading(weight=Decimal("0.1"), from_default=True)
    assert readings["cap1-unreadable"] == Cap1Reading(weight=None, from_default=False)
    # DL-5: whenever the weight is unreadable, ``from_default`` is False.
    assert all(not r.from_default for r in readings.values() if r.weight is None)
    # Not vacuous: the book really produced sized buys and sells, and wrote them.
    actions = {line["directive"]["action"] for line in reference["today"]["directives"]}
    assert {"buy", "sell"} <= actions
    assert any(
        line["directive"]["shares"] > 0
        for line in reference["today"]["directives"]
        if line["directive"]["action"] == "buy"
    )
    assert reference["tables"]["playbook_directives"]


def _reading_for(
    budget: RiskBudget | str | None, root: Path, monkeypatch: pytest.MonkeyPatch
) -> Cap1Reading:
    """What the real dependency reads for one matrix entry."""
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(deps, "_default_settings_store", _settings_provider(root, budget))
    return deps.get_cap1_reading()


def test_a_fallback_budget_states_the_default_through_every_endpoint(
    open_book: Callable[..., Book],
) -> None:
    """②-預設 end to end: the stored budget failed validation, the default 10% stands."""
    book = open_book("fallback-default", budget=FALLBACK)
    for response in (
        book.client.get("/api/playbook/today"),
        book.client.get("/api/playbook/rule-set"),
        book.client.post("/api/playbook/confirm-rules", json={"capital": "1000000"}),
    ):
        assert response.status_code == 200
        disclosure = response.json()["cap1_disclosure"]
        assert disclosure["lines"][1] == LINE_2_DEFAULT.format(cap1_pct="10%")
        assert disclosure["cap1_pct"] == "10%"
        assert len(disclosure["lines"]) == 4
        # K-8: no new field -- the response shape is the one ② has.
        assert set(disclosure) == set(PlaybookCap1Disclosure.model_fields)


def test_confirm_rules_is_never_refused_and_writes_the_same_params_whatever_the_risk_budget_r4_5(
    open_book: Callable[..., Book],
) -> None:
    """R4-5: cap 1 can neither refuse a confirmation nor change what it writes."""
    results = {}
    for name, budget in BUDGETS.items():
        book = open_book(f"confirm-{name}", budget=budget, mode="unconfirmed")
        response = book.client.post("/api/playbook/confirm-rules", json={"capital": "1000000"})
        assert response.status_code == 200, name
        body = response.json()
        results[name] = {
            "response": {
                field: body[field]
                for field in (*RULE_SET_FIELDS, "user_authored", "rules_version", "total_deploy")
            },
            "tables": _playbook_tables(book.db),
        }

    reference = results["cap1-0.10"]
    for name, result in results.items():
        assert result == reference, name
    assert reference["response"]["user_authored"] is True
    assert reference["tables"]["playbook_rule_params"]


def test_an_unreadable_settings_store_still_answers_200_with_the_same_directives(
    open_book: Callable[..., Book],
) -> None:
    """R4-4: a broken settings page may not take the stop-loss lines down with it."""
    readable = open_book("readable").client.get("/api/playbook/today")
    broken_store = open_book(
        "broken-load", settings=lambda: _UnreadableSettings(RuntimeError("boom"))
    ).client.get("/api/playbook/today")

    def unbuildable() -> SettingsStore:
        raise sqlite3.DatabaseError("file is not a database")

    unbuilt = open_book("broken-build", settings=unbuildable)

    for response in (broken_store, unbuilt.client.get("/api/playbook/today")):
        assert response.status_code == 200
        body = response.json()
        assert body["directives"] == readable.json()["directives"]
        assert body["cap1_disclosure"]["cap1_pct"] is None
        assert body["cap1_disclosure"]["lines"][1] == LINE_2_MISSING
        assert "10%" not in json.dumps(body["cap1_disclosure"], ensure_ascii=False)
    assert unbuilt.client.get("/api/playbook/rule-set").status_code == 200
    assert (
        unbuilt.client.post("/api/playbook/confirm-rules", json={"capital": "1000000"}).status_code
        == 200
    )


# --- B-2: always there, verbatim, with the numbers actually in use ---------------------


@pytest.mark.parametrize("mode", MODES)
def test_today_carries_the_disclosure_verbatim_in_every_mode(
    open_book: Callable[..., Book], mode: Mode
) -> None:
    """B-2: five modes, stored (non-default) parameters, stored cap 1 = 0.12."""
    body = open_book(mode, mode=mode).client.get("/api/playbook/today").json()

    assert body["mode"] == mode
    disclosure = body["cap1_disclosure"]
    assert disclosure["title"] == TITLE
    assert disclosure["lines"]
    if mode == "unconfirmed":
        # 待確認規則集 runs on the system default -- the set a confirmation adopts.
        assert disclosure["lines"] == DEFAULT_LINES
        assert disclosure["per_target_pct"] == "14%"
    else:
        assert disclosure["lines"] == STORED_LINES
        assert (disclosure["per_target_pct"], disclosure["per_target_book_pct"]) == ("15%", "25%")
    assert disclosure["cap1_pct"] == "12%"


def test_rule_set_and_confirm_rules_carry_the_disclosure_verbatim(
    open_book: Callable[..., Book],
) -> None:
    """B-2: the two rule-set endpoints, unconfirmed before and confirmed after."""
    book = open_book("rule-set", mode="unconfirmed")

    before = book.client.get("/api/playbook/rule-set").json()
    assert before["user_authored"] is False
    assert before["cap1_disclosure"]["title"] == TITLE
    assert before["cap1_disclosure"]["lines"] == DEFAULT_LINES

    after = book.client.post("/api/playbook/confirm-rules", json={"capital": "1000000"}).json()
    assert after["user_authored"] is True
    assert after["cap1_disclosure"]["lines"] == DEFAULT_LINES

    stored = open_book("rule-set-stored").client.get("/api/playbook/rule-set").json()
    assert stored["cap1_disclosure"]["lines"] == STORED_LINES
    confirmed_again = open_book("confirm-stored").client.post(
        "/api/playbook/confirm-rules", json={"capital": "1000000"}
    )
    assert confirmed_again.json()["cap1_disclosure"]["lines"] == STORED_LINES


#: 補充裁定 第 2 節: per-target share below, at and above cap 1 (n = 11 / 7 / 5
#: against 10%), then cap 1 at 25%. Every figure is written out by hand.
MATRIX = [
    (11, 0.10, "6.4%", "10%", "9.1%"),
    (7, 0.10, "10%", "10%", "14.3%"),
    (5, 0.10, "14%", "10%", "20%"),
    (5, 0.25, "14%", "25%", "20%"),
]


@pytest.mark.parametrize(
    ("n_targets", "cap1", "per_target", "cap1_pct", "book_pct"),
    MATRIX,
    ids=["n11-cap10", "n7-cap10", "n5-cap10", "n5-cap25"],
)
@pytest.mark.parametrize("path", ["/api/playbook/today", "/api/playbook/rule-set"])
def test_the_disclosure_is_shown_whatever_the_two_percentages_are(
    open_book: Callable[..., Book],
    path: str,
    n_targets: int,
    cap1: float,
    per_target: str,
    cap1_pct: str,
    book_pct: str,
) -> None:
    """B-2 matrix: below, equal and above -- the same block, the figures verbatim."""
    book = open_book(
        f"matrix-{n_targets}-{cap1}-{path.rsplit('/', 1)[-1]}",
        budget=RiskBudget(max_position_weight=cap1),
        holdings=False,
        rule_set={
            "version": 2,
            "deploy_ratio": Decimal("0.70"),
            "n_targets": n_targets,
            "batches_per_target": 3,
        },
    )
    disclosure = book.client.get(path).json()["cap1_disclosure"]

    assert disclosure["title"] == TITLE
    assert disclosure["lines"] == expected_lines(
        deploy_ratio_pct="70%",
        n_targets=n_targets,
        batches_per_target=3,
        per_target_pct=per_target,
        cap1_pct=cap1_pct,
        per_target_book_pct=book_pct,
    )
    assert (disclosure["per_target_pct"], disclosure["cap1_pct"]) == (per_target, cap1_pct)
    assert disclosure["per_target_book_pct"] == book_pct


@pytest.mark.parametrize("n_targets", [0, -2])
def test_a_stored_non_positive_n_targets_gets_the_missing_value_sentences(
    open_book: Callable[..., Book], n_targets: int
) -> None:
    """①-缺 / ③-缺 through the endpoints, and ``null`` rather than ``0``."""
    book = open_book(
        f"bad-n-{n_targets}",
        holdings=False,
        rule_set={"version": 2, "deploy_ratio": Decimal("0.70"), "n_targets": n_targets},
    )
    for response in (
        book.client.get("/api/playbook/rule-set"),
        book.client.post("/api/playbook/confirm-rules", json={"capital": "1000000"}),
    ):
        assert response.status_code == 200
        disclosure = response.json()["cap1_disclosure"]
        assert disclosure["lines"] == [
            LINE_1_MISSING,
            LINE_2.format(cap1_pct="12%"),
            LINE_3_MISSING,
            LINE_4,
        ]
        assert disclosure["per_target_pct"] is None
        assert disclosure["per_target_book_pct"] is None


def test_the_first_batch_placeholder_for_the_disclosure_is_now_bound_to_the_field() -> None:
    """The strict xfail of 測試 ③ is gone; this module carries B-2 from here."""
    source = (Path(__file__).parent / "test_playbook_cap1_d2.py").read_text(encoding="utf-8")
    assert "pytest.mark.xfail" not in source
    assert '["cap1_disclosure"]' in source


# --- B-3: the version the numbers came from --------------------------------------------


def test_the_disclosure_names_the_version_the_same_response_used(
    open_book: Callable[..., Book],
) -> None:
    """B-3, with a later version already submitted: the in-force one is used, not it."""
    book = open_book("versions")
    book.store.submit_rule_change(
        make_params(
            version=STORED_VERSION + 1,
            effective_date=EVALUATION_DAY + timedelta(days=10),
            n_targets=9,
        )
    )

    today = book.client.get("/api/playbook/today").json()
    assert today["rules_version"] == STORED_VERSION
    assert today["cap1_disclosure"]["rules_version"] == STORED_VERSION
    assert today["cap1_disclosure"]["lines"] == STORED_LINES

    rule_set = book.client.get("/api/playbook/rule-set").json()
    assert rule_set["rules_version"] == STORED_VERSION
    assert rule_set["cap1_disclosure"]["rules_version"] == STORED_VERSION
    assert {"field": "n_targets", "value": "4"} in rule_set["params"]


def test_the_unconfirmed_disclosure_names_the_version_in_force(
    open_book: Callable[..., Book],
) -> None:
    """B-3 on 待確認規則集: the default set's own version, the one rule-set states."""
    book = open_book("unconfirmed-version", mode="unconfirmed")
    in_force = book.store.active_params(EVALUATION_DAY)

    today = book.client.get("/api/playbook/today").json()
    rule_set = book.client.get("/api/playbook/rule-set").json()
    assert today["cap1_disclosure"]["rules_version"] == in_force.version
    assert rule_set["cap1_disclosure"]["rules_version"] == in_force.version
    assert today["cap1_disclosure"] == rule_set["cap1_disclosure"]


def test_the_evaluation_carries_the_params_it_ran_with(tmp_path: Path) -> None:
    """C-5: ``PlaybookEvaluation.params`` is the version the engine was handed."""
    store, service = _seed(tmp_path / "eval")
    evaluation = service.evaluate_today()
    assert evaluation.params == store.active_params(evaluation.data_date)
    assert evaluation.params.version == evaluation.rules_version == STORED_VERSION

    _, unconfirmed = _seed(tmp_path / "eval-unconfirmed", mode="unconfirmed")
    assert unconfirmed.evaluate_today().params == RuleParams(effective_date=EVALUATION_DAY)


def test_today_does_not_read_the_rule_set_a_second_time(
    open_book: Callable[..., Book], monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-5: ``/today`` takes the figures from the evaluation, not ``rule_set_status``."""
    book = open_book("single-read")

    def refuse(self: PlaybookService, **_: Any) -> None:
        raise AssertionError("/today read the rule set a second time")

    monkeypatch.setattr(PlaybookService, "rule_set_status", refuse)
    monkeypatch.setattr(_PinnedService, "rule_set_status", refuse)
    assert book.client.get("/api/playbook/today").status_code == 200


# --- B-4: stored nowhere, and only where it belongs -------------------------------------


def _disclosure_fragments() -> list[str]:
    return [
        TITLE,
        *STORED_LINES,
        *DEFAULT_LINES,
        LINE_4,
        "單一標的佔比上限",
        LINE_2_MISSING,
        LINE_2_DEFAULT.format(cap1_pct="10%"),
    ]


def test_no_playbook_table_ever_holds_any_disclosure_text(
    open_book: Callable[..., Book],
) -> None:
    """B-4 / AV-11 / H2: after ``/today``, ``/confirm-rules`` and an exit, no cell has it."""
    confirmed = open_book("b4")
    confirmed.client.get("/api/playbook/today")
    confirmed.client.get("/api/playbook/rule-set")
    confirmed.client.post("/api/playbook/emergency-exit")
    confirmed.client.get("/api/playbook/today")
    unconfirmed = open_book("b4-confirm", mode="unconfirmed")
    unconfirmed.client.post("/api/playbook/confirm-rules", json={"capital": "1000000"})
    unconfirmed.client.get("/api/playbook/today")

    for book in (confirmed, unconfirmed):
        tables = _playbook_tables(book.db)
        assert tables["playbook_directives"] or book is unconfirmed
        cells = [str(cell) for rows in tables.values() for row in rows for cell in row]
        for fragment in _disclosure_fragments():
            assert not [cell for cell in cells if fragment in cell], fragment
        # The cap-1 figure itself is not recorded anywhere either (H2).
        assert not [cell for cell in cells if "12%" in cell or cell == "0.12"]


def test_the_title_is_not_in_exit_page_summary_warnings_or_the_directive_log(
    open_book: Callable[..., Book],
) -> None:
    """B-4: EXIT 流程、page_summary、warnings、指令 log never carry the block."""
    book = open_book("b4-surfaces")
    today = book.client.get("/api/playbook/today").json()
    exit_response = book.client.post("/api/playbook/emergency-exit").json()

    assert today["cap1_disclosure"]["title"] == TITLE  # it is here, in its own field...
    elsewhere = {key: value for key, value in today.items() if key != "cap1_disclosure"}
    for surface in (
        elsewhere,
        today["page_summary"],
        today["warnings"],
        today["exit_confirm"],
        exit_response,
        book.store.directive_log(),
    ):
        text = json.dumps(surface, ensure_ascii=False, default=str)
        for fragment in _disclosure_fragments():
            assert fragment not in text, fragment


def test_the_alerts_output_never_carries_the_disclosure(api_harness: ApiHarness) -> None:
    """B-4 / R18: the block is never pushed through alerts."""
    for response in (
        api_harness.client.post("/api/alerts/evaluate"),
        api_harness.client.get("/api/alerts/events"),
        api_harness.client.get("/api/alerts"),
    ):
        assert response.status_code == 200
        text = response.text
        assert TITLE not in text and "cap1_disclosure" not in text


def test_only_the_playbook_router_assembles_the_disclosure() -> None:
    """B-4 / H4, statically: no other module imports the sentences or holds the title.

    Which also means no alerts, advice, settings, portfolio or EXIT path can emit
    them: the text exists in one source file and is served by one router. The
    one other importer is ``app.api.deps``, and only for the :class:`Cap1Reading`
    type its dependency returns (ADR-0032 K-9 defines it in the wording module).
    """
    importers = []
    holders = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT.parent)
        module = ".".join(relative.with_suffix("").parts).removesuffix(".__init__")
        if "app.api.playbook_cap1_wording" in imported_modules(path, module):
            importers.append(module)
        if TITLE in path.read_text(encoding="utf-8"):
            holders.append(module)
    assert importers == ["app.api.deps", "app.api.playbook"]
    assert holders == ["app.api.playbook_cap1_wording"]
    deps_names = {
        name
        for name in imported_modules(APP_ROOT / "api" / "deps.py", "app.api.deps")
        if name.startswith("app.api.playbook_cap1_wording.")
    }
    assert deps_names == {"app.api.playbook_cap1_wording.Cap1Reading"}


# --- R4-6: the advice side does not change ---------------------------------------------


def test_the_advice_settings_and_portfolio_surfaces_are_untouched() -> None:
    """R4-6 / H5 / 修訂 D-2 (4): none of them gains the field or the module."""
    from app.api.advice import AdviceResponse
    from app.api.portfolio import PortfolioLimitsResponse
    from app.api.settings import SettingsResponse
    from app.portfolio.summary import PortfolioSummary

    for model in (AdviceResponse, PortfolioLimitsResponse, PortfolioSummary, SettingsResponse):
        schema = json.dumps(model.model_json_schema(), ensure_ascii=False)
        assert "cap1_disclosure" not in schema, model.__name__
        assert "PlaybookCap1Disclosure" not in schema, model.__name__
    for router in ("advice", "settings", "portfolio"):
        path = APP_ROOT / "api" / f"{router}.py"
        imported = imported_modules(path, f"app.api.{router}")
        assert "app.api.playbook_cap1_wording" not in imported, router
        assert "get_cap1_weight" not in path.read_text(encoding="utf-8"), router
        assert "get_cap1_reading" not in path.read_text(encoding="utf-8"), router


def test_the_settings_response_does_not_carry_the_disclosure(api_harness: ApiHarness) -> None:
    """R4-6 at runtime: ``GET /api/settings`` still answers without the block."""
    response = api_harness.client.get("/api/settings")
    assert response.status_code == 200
    assert "cap1_disclosure" not in response.json()
    assert TITLE not in response.text


def test_the_disclosure_field_is_on_exactly_the_three_responses() -> None:
    """C-5: ``/today``, ``/rule-set``, ``/confirm-rules`` -- and nowhere else in the router."""
    assert TodayResponse.model_fields["cap1_disclosure"].annotation is PlaybookCap1Disclosure
    assert RuleSetResponse.model_fields["cap1_disclosure"].annotation is PlaybookCap1Disclosure
    from app.api import playbook as router_module

    carrying = sorted(
        name
        for name, value in vars(router_module).items()
        if isinstance(value, type)
        and hasattr(value, "model_fields")
        and "cap1_disclosure" in value.model_fields
    )
    assert carrying == ["RuleSetResponse", "TodayResponse"]
