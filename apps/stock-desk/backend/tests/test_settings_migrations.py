"""S2: the stored cap-1 value 0.15 becomes 0.10 once, with a record (CEO #63).

Covers quant constraint 4 (only 0.15 moves, a record with previous/new/time/
basis, idempotent across starts, the four named cases), the risk review's S2
附加實作約束 (never ``load`` -> ``save``; only ``risk_budget.max_position_weight``
changes; any invalid section means no migration, a record, a visible notice,
and not one byte of stored data changed), and the copy of the two verbatim
reviews of 2026-10-26: 第1條下修告知逐字審 (#1/#2/#2', 實作約束 2/6) and
遷移未執行逐字審 (U0-U5, S1/S1', I-1 ~ I-9).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.advice.limits import (
    DEFAULT_MAX_POSITION_WEIGHT,
    PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT,
    RiskBudget,
)
from app.advice.loader import BANNED_PHRASES
from app.api.deps import get_settings_store
from app.main import app
from app.settings import store as store_module
from app.settings.migrations import (
    CAP1_MIGRATION_BASIS,
    CAP1_MIGRATION_NOTICES,
    CAP1_SECTION_NAMES,
    Cap1MigrationRecord,
    SettingsNoticeCopy,
    ShortNoticeCopy,
)
from app.settings.models import AlertSettings, AppSettings, CostModelSettings
from app.settings.store import SettingsStore
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

MIGRATED_AT = datetime(2026, 10, 27, 1, 2, 3, tzinfo=UTC)
#: ``MIGRATED_AT`` the way every notice prints it.
MIGRATED_AT_TEXT = "2026-10-27 09:02（台北時間）"
LATER = datetime(2026, 11, 3, 4, 5, 6, tzinfo=UTC)
LATER_TEXT = "2026-11-03 12:05（台北時間）"

STOCK_DESK_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SETTINGS = STOCK_DESK_ROOT / "frontend" / "app" / "settings"


# --- The finalised copy, retyped from the two risk tables ----------------------
#
# Retyped by hand, never imported: a drift of one character in the shipped
# constant then fails here instead of silently becoming the new "approved" text.

MIGRATED_SETTINGS_TITLE = "第 1 條上限自動調整紀錄"
MIGRATED_SETTINGS_ITEMS = (
    (
        "改了什麼",
        "{migrated_at}，系統把「單一標的佔比上限」由 {old_value}（{old_pct}）自動改為 "
        "{new_value}（{new_pct}）。只有這一個值被改（原值等於 {old_pct} 才會改），"
        "其他設定都沒有改動。",
    ),
    (
        "為什麼改",
        "第 5 條「分數 Kelly 部位上限」的計算方式有誤，已決定停用。為了不讓上限因第 5 條"
        "停用而變寬，依 2026-10-26 的決定下修第 1 條。{new_pct} 是政策設定，"
        "沒有經過回測或歷史驗證。",
    ),
    (
        "會看到的變化",
        "佔比在 {new_pct} 以上（含剛好 {new_pct}）的持股會顯示已違反第 1 條；其中佔比未滿 "
        "{old_pct} 的，在原本 {old_pct} 的上限下不會顯示已違反。這些持股原本是加碼參考的，"
        "會改為續抱參考；減碼的股數區間可能變大，加碼區間可能變小或消失，候選標的的試算股數"
        "可能變少；若設了上限警示，可能開始收到推播。",
    ),
    ("過去的紀錄", "舊的警示和卡片保留當時的 {old_pct}，不回頭改寫。"),
    (
        "可以改回",
        "在本欄位自行修改即可，包括改回 {old_value}。改高等於放寬上限，儲存前會先要求你確認。",
    ),
)
MIGRATED_SHORT = (
    "第 1 條上限已於 {migrated_at} 由 {old_pct} 自動改為 {new_pct}；{new_pct} 是政策設定，"
    "未經回測或歷史驗證。佔比達 {new_pct} 以上的持股顯示已違反，其中未滿 {old_pct} 的，"
    "在原本 {old_pct} 的上限下不會顯示已違反。完整紀錄在設定頁。"
)
SKIPPED_SETTINGS_TITLE = "第 1 條上限自動調整未執行"
SKIPPED_U1 = (
    "發生了什麼",
    "{attempted_at}，系統檢查已存設定時，{section_names}沒有通過驗證，因此沒有執行第 1 條"
    "「單一標的佔比上限」的自動調整（已存值等於 {old_default_pct} 時改為 "
    "{new_default_pct}），已存設定沒有任何改動。",
)
SKIPPED_U2 = ("目前使用的值", "第 1 條上限目前使用 {current_pct}，取自已存設定。")
SKIPPED_U2_PRIME = (
    "目前使用的值",
    "第 1 條上限目前使用 {current_pct}。因為風險預算沒有通過驗證，在本頁按儲存之前，"
    "系統用的是預設值 {default_pct}，不是原本存的內容。",
)
SKIPPED_U3 = (
    "頁面與存檔",
    "在本頁按儲存之前，{section_names}在本頁顯示的是預設值，不是原本存的內容。本頁任何一個"
    "儲存按鈕都會把所有區段整份寫入，包括{section_names}；原本存的內容會被取代，"
    "系統內不會保留。",
)
SKIPPED_U4 = ("可用的操作", "本欄位可以自行修改數值。改高等於放寬上限，儲存前會先要求你確認。")
SKIPPED_U5 = (
    "之後",
    "系統每次啟動時會再檢查一次，所有區段都通過驗證時才會執行這次調整。在那之前，"
    "這則告知會一直顯示，按儲存之後也一樣。",
)
SKIPPED_S1 = (
    "第 1 條上限的自動調整於 {attempted_at}未執行，原因是已存設定有區段未通過驗證；"
    "目前使用的上限是 {current_pct}。詳見設定頁。"
)
SKIPPED_S1_PRIME = (
    "第 1 條上限的自動調整於 {attempted_at}未執行，原因是已存設定有區段未通過驗證，"
    "包括風險預算；目前使用的上限是 {current_pct}，在設定頁儲存之前用的是預設值 "
    "{default_pct}，不是原本存的內容。詳見設定頁。"
)

#: Interpolation of a record dated ``MIGRATED_AT`` under today's constants.
FIELDS = {
    "migrated_at": MIGRATED_AT_TEXT,
    "attempted_at": MIGRATED_AT_TEXT,
    "old_value": "0.15",
    "new_value": "0.1",
    "old_pct": "15.00%",
    "new_pct": "10.00%",
    "old_default_pct": "15.00%",
    "new_default_pct": "10.00%",
    "default_pct": "10.00%",
}


# --- Fixtures and helpers --------------------------------------------------------


def _seed(
    db: Path, sections: dict[str, str], *, updated_at: str = "2026-01-01T00:00:00+00:00"
) -> None:
    """Write raw section payloads the way an earlier build would have left them."""
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_settings ("
            "section TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO app_settings (section, payload, updated_at) VALUES (?, ?, ?)",
            [(name, payload, updated_at) for name, payload in sections.items()],
        )
    conn.close()


def _rows(db: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT section, payload, updated_at FROM app_settings ORDER BY section"
        ).fetchall()
    conn.close()
    return rows


def _full_document(max_position_weight: float, **budget: float) -> dict[str, str]:
    """Every section as a saved build writes it, with cap 1 at ``max_position_weight``."""
    settings = AppSettings(
        risk_budget=RiskBudget(max_position_weight=max_position_weight, **budget),
        cost_model=CostModelSettings(slippage_bps=7.5),
        alerts=AlertSettings(cooldown_minutes=15),
    )
    return {
        name: json.dumps(getattr(settings, name).model_dump(), ensure_ascii=False)
        for name in ("risk_budget", "cost_model", "alerts", "net_worth")
    }


def _record(store: SettingsStore) -> Cap1MigrationRecord:
    record = store.cap1_migration()
    assert record is not None
    return record


#: Not ``settings.db``: ``api_harness`` already owns that file in ``tmp_path``.
_S2_DB = "s2-settings.db"


def _skipped_store(
    tmp_path: Path, section: str, max_position_weight: float = 0.15
) -> SettingsStore:
    db = tmp_path / _S2_DB
    document = _full_document(max_position_weight)
    document[section] = '{"not": "valid"}'
    _seed(db, document)
    return SettingsStore(db, now=MIGRATED_AT)


def _migrated_store(tmp_path: Path) -> SettingsStore:
    db = tmp_path / _S2_DB
    _seed(db, _full_document(0.15))
    return SettingsStore(db, now=MIGRATED_AT)


def _filled(item: tuple[str, str], **extra: str) -> tuple[str, str]:
    label, body = item
    return label, body.format(**FIELDS, **extra)


# --- The four cases quant constraint 4 names ---------------------------------


def test_a_stored_old_default_becomes_the_new_one_with_a_record(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15, max_loss_per_trade=0.02))

    store = SettingsStore(db, now=MIGRATED_AT)

    budget = store.load().risk_budget
    assert budget.max_position_weight == 0.10
    record = _record(store)
    assert record.status == "migrated"
    assert record.previous_value == 0.15
    assert record.new_value == 0.10
    assert record.recorded_at == MIGRATED_AT.isoformat()
    assert record.basis == CAP1_MIGRATION_BASIS
    assert "#61" in record.basis and "#63" in record.basis
    assert record.failed_sections == ()
    assert record.changed_by_user is False


def test_a_stored_custom_value_is_left_exactly_as_stored(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.12))
    before = _rows(db)

    store = SettingsStore(db, now=MIGRATED_AT)

    assert store.load().risk_budget.max_position_weight == 0.12
    assert _rows(db) == before
    record = _record(store)
    assert record.status == "not_applicable"
    assert record.previous_value == 0.12
    assert record.new_value is None


def test_a_never_saved_install_reads_the_new_default(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.db", now=MIGRATED_AT)

    assert store.load().risk_budget.max_position_weight == 0.10
    assert _rows(store.db_path) == []
    record = _record(store)
    assert record.status == "not_applicable"
    assert record.previous_value is None


def test_a_second_start_changes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15))
    first = _record(SettingsStore(db, now=MIGRATED_AT))
    after_first = _rows(db)

    second = SettingsStore(db, now=LATER)

    assert _rows(db) == after_first
    assert _record(second) == first


# --- Only the old default, only that key -------------------------------------


@pytest.mark.parametrize(
    ("stored", "migrated"),
    [
        (0.15, True),
        (0.15 + 1e-12, True),
        (0.15 - 1e-12, True),
        (0.1501, False),
        (0.1499, False),
        (0.10, False),
        (0.20, False),
    ],
)
def test_only_a_value_equal_to_the_old_default_moves(
    tmp_path: Path, stored: float, migrated: bool
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(stored))

    store = SettingsStore(db, now=MIGRATED_AT)

    expected = 0.10 if migrated else stored
    assert store.load().risk_budget.max_position_weight == expected
    assert _record(store).status == ("migrated" if migrated else "not_applicable")


def test_only_max_position_weight_changes(tmp_path: Path) -> None:
    """實作約束 6 success path: every other field of every section is unchanged."""
    db = tmp_path / "settings.db"
    document = _full_document(0.15, max_loss_per_trade=0.02, max_sector_weight=0.25)
    _seed(db, document)
    before = {section: (payload, stamp) for section, payload, stamp in _rows(db)}

    SettingsStore(db, now=MIGRATED_AT)

    after = {section: (payload, stamp) for section, payload, stamp in _rows(db)}
    # Every other section's row is not written at all: payload and stamp intact.
    for section in ("cost_model", "alerts", "net_worth"):
        assert after[section] == before[section]
    old_budget = json.loads(before["risk_budget"][0])
    new_budget = json.loads(after["risk_budget"][0])
    assert {k: v for k, v in new_budget.items() if k != "max_position_weight"} == {
        k: v for k, v in old_budget.items() if k != "max_position_weight"
    }
    assert list(new_budget) == list(old_budget)
    assert new_budget["max_position_weight"] == 0.10
    assert after["risk_budget"][1] == MIGRATED_AT.isoformat()
    # The Kelly fields stay on the stored section (quant constraint 5).
    assert new_budget["kelly_fraction_cap"] == old_budget["kelly_fraction_cap"]
    assert new_budget["kelly_position_cap"] == old_budget["kelly_position_cap"]


def test_the_migration_never_goes_through_load_and_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2 附加實作約束: not ``load`` -> change -> ``save``."""

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the migration must not call SettingsStore.load/save")

    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15))
    monkeypatch.setattr(SettingsStore, "load", _refuse)
    monkeypatch.setattr(SettingsStore, "save", _refuse)

    store = SettingsStore(db, now=MIGRATED_AT)

    assert _record(store).status == "migrated"
    monkeypatch.undo()
    assert SettingsStore(db).load().risk_budget.max_position_weight == 0.10


# --- Any invalid section: no migration, a record, nothing touched ------------


@pytest.mark.parametrize(
    ("section", "payload"),
    [
        ("cost_model", '{"slippage_bps": "nonsense"}'),
        ("alerts", "not json at all"),
        ("net_worth", '{"total_net_worth_twd": -5}'),
        ("risk_budget", '{"max_position_weight": 0.15, "removed_field": 1}'),
    ],
)
def test_an_invalid_section_stops_the_migration_and_changes_no_byte(
    tmp_path: Path, section: str, payload: str
) -> None:
    db = tmp_path / "settings.db"
    document = _full_document(0.15)
    document[section] = payload
    _seed(db, document)
    before = _rows(db)

    store = SettingsStore(db, now=MIGRATED_AT)

    assert _rows(db) == before
    record = _record(store)
    assert record.status == "skipped"
    assert record.failed_sections == (section,)
    assert record.new_value is None
    current = store.load().risk_budget.max_position_weight
    assert record.settings_notice(current_max_position_weight=current) is not None
    assert record.short_notice(current_max_position_weight=current) is not None


def test_a_skip_is_retried_and_migrates_once_the_document_is_repaired(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    document = _full_document(0.15)
    broken = dict(document, cost_model='{"slippage_bps": "nonsense"}')
    _seed(db, broken)
    assert _record(SettingsStore(db, now=MIGRATED_AT)).status == "skipped"

    _seed(db, {"cost_model": document["cost_model"]})
    store = SettingsStore(db, now=LATER)

    assert store.load().risk_budget.max_position_weight == 0.10
    record = _record(store)
    assert record.status == "migrated"
    assert record.recorded_at == LATER.isoformat()


def test_a_repaired_document_with_another_value_ends_not_applicable(tmp_path: Path) -> None:
    """I-9: after the repair, a value other than 0.15 is the user's; the skip notice goes."""
    db = tmp_path / "settings.db"
    document = _full_document(0.12)
    _seed(db, dict(document, alerts="broken"))
    assert _record(SettingsStore(db, now=MIGRATED_AT)).status == "skipped"

    _seed(db, {"alerts": document["alerts"]})
    store = SettingsStore(db, now=LATER)

    record = _record(store)
    assert record.status == "not_applicable"
    assert record.settings_notice(current_max_position_weight=0.12) is None
    assert record.short_notice(current_max_position_weight=0.12) is None
    assert store.load().risk_budget.max_position_weight == 0.12


def test_a_restored_pre_migration_backup_is_migrated_and_announced_again(tmp_path: Path) -> None:
    """Risk review point 3 (1), F4/F10: the marker lives in the same file as the value."""
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15))
    backup = db.read_bytes()
    store = SettingsStore(db, now=MIGRATED_AT)
    _put_cap1(store, 0.12)
    assert _record(store).changed_by_user is True

    db.write_bytes(backup)
    for suffix in ("-wal", "-shm"):
        (tmp_path / f"settings.db{suffix}").unlink(missing_ok=True)
    restored = SettingsStore(db, now=LATER)

    assert restored.load().risk_budget.max_position_weight == 0.10
    record = _record(restored)
    assert record.recorded_at == LATER.isoformat()
    assert record.changed_by_user is False
    assert record.short_notice(current_max_position_weight=0.10) is not None


# --- The user writes cap 1 after a migration (實作約束 2, F1/F8) ---------------


def _put_cap1(store: SettingsStore, value: float) -> None:
    current = store.load()
    store.save(
        AppSettings(
            risk_budget=current.risk_budget.model_copy(update={"max_position_weight": value}),
            cost_model=current.cost_model,
            alerts=current.alerts,
            net_worth=current.net_worth,
        )
    )


def test_setting_the_old_value_back_is_not_undone_by_a_later_start(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15))
    store = SettingsStore(db, now=MIGRATED_AT)
    record = _record(store)
    _put_cap1(store, 0.15)

    restarted = SettingsStore(db, now=LATER)

    assert restarted.load().risk_budget.max_position_weight == 0.15
    after = _record(restarted)
    assert after.status == record.status and after.recorded_at == record.recorded_at
    assert after.changed_by_user is True


def test_a_save_of_the_migrated_value_does_not_set_the_flag(tmp_path: Path) -> None:
    store = _migrated_store(tmp_path)
    _put_cap1(store, 0.10)
    assert _record(store).changed_by_user is False


def test_the_flag_sticks_once_set(tmp_path: Path) -> None:
    """Only a new migration clears it: writing 0.10 back does not."""
    store = _migrated_store(tmp_path)
    _put_cap1(store, 0.12)
    _put_cap1(store, 0.10)
    record = _record(store)
    assert record.changed_by_user is True
    assert record.recorded_at == MIGRATED_AT.isoformat()


def test_with_the_flag_set_1_3_and_the_short_notice_go(tmp_path: Path) -> None:
    store = _migrated_store(tmp_path)
    _put_cap1(store, 0.12)
    record = _record(store)

    notice = record.settings_notice(current_max_position_weight=0.12)
    assert notice is not None
    assert notice.title == MIGRATED_SETTINGS_TITLE
    kept = [item for item in MIGRATED_SETTINGS_ITEMS if item[0] != "會看到的變化"]
    assert notice.items == tuple(_filled(item) for item in kept)
    assert record.short_notice(current_max_position_weight=0.12) is None


# --- A skipped record outlives a save (U5, I-6) ---------------------------------


def test_a_save_leaves_a_skipped_record_and_its_notice_in_place(tmp_path: Path) -> None:
    store = _skipped_store(tmp_path, "cost_model")
    before = _record(store)
    _put_cap1(store, 0.12)

    after = _record(store)
    assert after == before
    assert after.settings_notice(current_max_position_weight=0.12) is not None
    assert after.short_notice(current_max_position_weight=0.12) is not None


def test_a_put_leaves_a_skipped_record_and_its_notices_in_place(
    api_harness: ApiHarness, tmp_path: Path
) -> None:
    """I-9:「按儲存之後也一樣」through the real endpoint."""
    store = _skipped_store(tmp_path, "cost_model")
    app.dependency_overrides[get_settings_store] = lambda: store

    response = api_harness.client.put(
        "/api/settings", json={"risk_budget": {"max_position_weight": 0.12}}
    )

    assert response.status_code == 200
    view = response.json()["cap1_migration"]
    assert view["status"] == "skipped"
    assert view["recorded_at"] == MIGRATED_AT.isoformat()
    assert view["notice"]["title"] == SKIPPED_SETTINGS_TITLE
    gauge = api_harness.client.get("/api/portfolio/limits").json()
    assert gauge["cap1_migration_notice"] == SKIPPED_S1.format(**FIELDS, current_pct="12.00%")


# --- The copy itself: verbatim, every branch -------------------------------------


def test_the_shipped_copy_is_the_finalised_copy_verbatim() -> None:
    migrated = CAP1_MIGRATION_NOTICES[("migrated", "settings")]
    assert isinstance(migrated, SettingsNoticeCopy)
    assert migrated.title == MIGRATED_SETTINGS_TITLE
    assert tuple((i.label, i.body) for i in migrated.items) == MIGRATED_SETTINGS_ITEMS

    short = CAP1_MIGRATION_NOTICES[("migrated", "short")]
    assert isinstance(short, ShortNoticeCopy)
    assert short.text == MIGRATED_SHORT
    assert short.text_if_risk_budget_failed is None

    skipped = CAP1_MIGRATION_NOTICES[("skipped", "settings")]
    assert isinstance(skipped, SettingsNoticeCopy)
    assert skipped.title == SKIPPED_SETTINGS_TITLE
    assert tuple((i.label, i.body) for i in skipped.items) == (
        SKIPPED_U1,
        SKIPPED_U2,
        SKIPPED_U2_PRIME,
        SKIPPED_U3,
        SKIPPED_U4,
        SKIPPED_U5,
    )

    skipped_short = CAP1_MIGRATION_NOTICES[("skipped", "short")]
    assert isinstance(skipped_short, ShortNoticeCopy)
    assert skipped_short.text == SKIPPED_S1
    assert skipped_short.text_if_risk_budget_failed == SKIPPED_S1_PRIME


def test_the_copy_is_keyed_by_status_and_surface() -> None:
    """I-1: structured, one entry per (status, surface); nothing for not_applicable."""
    assert set(CAP1_MIGRATION_NOTICES) == {
        ("migrated", "settings"),
        ("migrated", "short"),
        ("skipped", "settings"),
        ("skipped", "short"),
    }


def test_the_migrated_settings_notice_renders_every_item_in_order(tmp_path: Path) -> None:
    record = _record(_migrated_store(tmp_path))
    notice = record.settings_notice(current_max_position_weight=0.10)
    assert notice is not None
    assert notice.title == MIGRATED_SETTINGS_TITLE
    assert notice.items == tuple(_filled(item) for item in MIGRATED_SETTINGS_ITEMS)
    assert notice.items[0] == (
        "改了什麼",
        "2026-10-27 09:02（台北時間），系統把「單一標的佔比上限」由 0.15（15.00%）"
        "自動改為 0.1（10.00%）。只有這一個值被改（原值等於 15.00% 才會改），"
        "其他設定都沒有改動。",
    )


def test_the_migrated_short_notice_renders(tmp_path: Path) -> None:
    record = _record(_migrated_store(tmp_path))
    assert record.short_notice(current_max_position_weight=0.10) == (
        "第 1 條上限已於 2026-10-27 09:02（台北時間） 由 15.00% 自動改為 10.00%；10.00% "
        "是政策設定，未經回測或歷史驗證。佔比達 10.00% 以上的持股顯示已違反，其中未滿 "
        "15.00% 的，在原本 15.00% 的上限下不會顯示已違反。完整紀錄在設定頁。"
    )


def test_u2_and_s1_when_risk_budget_validated(tmp_path: Path) -> None:
    store = _skipped_store(tmp_path, "cost_model")
    record = _record(store)
    current = store.load().risk_budget.max_position_weight
    assert current == 0.15  # the stored value, still in force

    notice = record.settings_notice(current_max_position_weight=current)
    assert notice is not None
    assert notice.title == SKIPPED_SETTINGS_TITLE
    extra = {"current_pct": "15.00%", "section_names": "費率"}
    assert notice.items == tuple(
        _filled(item, **extra)
        for item in (SKIPPED_U1, SKIPPED_U2, SKIPPED_U3, SKIPPED_U4, SKIPPED_U5)
    )
    assert notice.items[0][1] == (
        "2026-10-27 09:02（台北時間），系統檢查已存設定時，費率沒有通過驗證，因此沒有執行"
        "第 1 條「單一標的佔比上限」的自動調整（已存值等於 15.00% 時改為 10.00%），"
        "已存設定沒有任何改動。"
    )
    assert record.short_notice(current_max_position_weight=current) == (
        "第 1 條上限的自動調整於 2026-10-27 09:02（台北時間）未執行，原因是已存設定有區段"
        "未通過驗證；目前使用的上限是 15.00%。詳見設定頁。"
    )


def test_u2_prime_and_s1_prime_when_risk_budget_failed(tmp_path: Path) -> None:
    store = _skipped_store(tmp_path, "risk_budget")
    record = _record(store)
    current = store.load().risk_budget.max_position_weight
    assert current == DEFAULT_MAX_POSITION_WEIGHT  # the section fell back to defaults

    notice = record.settings_notice(current_max_position_weight=current)
    assert notice is not None
    extra = {"current_pct": "10.00%", "section_names": "風險預算"}
    assert notice.items == tuple(
        _filled(item, **extra)
        for item in (SKIPPED_U1, SKIPPED_U2_PRIME, SKIPPED_U3, SKIPPED_U4, SKIPPED_U5)
    )
    assert record.short_notice(current_max_position_weight=current) == SKIPPED_S1_PRIME.format(
        **FIELDS, current_pct="10.00%"
    )


def test_section_names_follow_sections_order_joined_by_the_ideographic_comma(
    tmp_path: Path,
) -> None:
    db = tmp_path / "settings.db"
    document = _full_document(0.15)
    document["net_worth"] = "broken"
    document["cost_model"] = "broken"
    _seed(db, document)
    record = _record(SettingsStore(db, now=MIGRATED_AT))

    assert record.failed_sections == ("cost_model", "net_worth")
    notice = record.settings_notice(current_max_position_weight=0.15)
    assert notice is not None
    assert "費率、帳戶總淨值沒有通過驗證" in notice.items[0][1]
    assert "包括費率、帳戶總淨值；" in notice.items[2][1]
    # Never the internal key.
    assert "cost_model" not in json.dumps(notice.items, ensure_ascii=False)


def test_a_stored_twelve_with_a_broken_cost_model_states_the_rule_not_the_value(
    tmp_path: Path,
) -> None:
    """I-3 / I-9: item 1 prints 15.00% and 10.00%, never the stored 12%."""
    store = _skipped_store(tmp_path, "cost_model", max_position_weight=0.12)
    record = _record(store)
    assert record.previous_value == 0.12

    notice = record.settings_notice(current_max_position_weight=0.12)
    assert notice is not None
    first = notice.items[0][1]
    assert "（已存值等於 15.00% 時改為 10.00%）" in first
    assert "12" not in first
    assert notice.items[1][1] == "第 1 條上限目前使用 12.00%，取自已存設定。"


def test_percentages_have_two_decimals_and_follow_the_constants() -> None:
    record = Cap1MigrationRecord(
        status="migrated",
        previous_value=0.15 + 1e-12,
        new_value=0.10,
        failed_sections=(),
        basis=CAP1_MIGRATION_BASIS,
        recorded_at=MIGRATED_AT.isoformat(),
    )
    fields = record.notice_fields(current_max_position_weight=0.125)
    assert fields["old_pct"] == f"{PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT:.2%}" == "15.00%"
    assert fields["new_pct"] == "10.00%"
    assert fields["current_pct"] == "12.50%"
    assert fields["default_pct"] == "10.00%"
    assert fields["old_value"] == "0.15"


def test_not_applicable_shows_nothing() -> None:
    record = Cap1MigrationRecord(
        status="not_applicable",
        previous_value=0.12,
        new_value=None,
        failed_sections=(),
        basis=CAP1_MIGRATION_BASIS,
        recorded_at=MIGRATED_AT.isoformat(),
    )
    assert record.settings_notice(current_max_position_weight=0.12) is None
    assert record.short_notice(current_max_position_weight=0.12) is None


def _every_rendered_notice() -> list[str]:
    texts: list[str] = []
    for status, failed in (
        ("migrated", ()),
        ("skipped", ("cost_model",)),
        ("skipped", ("risk_budget",)),
    ):
        for changed in (False, True):
            record = Cap1MigrationRecord(
                status=status,  # type: ignore[arg-type]
                previous_value=0.15,
                new_value=0.10 if status == "migrated" else None,
                failed_sections=failed,
                basis=CAP1_MIGRATION_BASIS,
                recorded_at=MIGRATED_AT.isoformat(),
                changed_by_user=changed,
            )
            notice = record.settings_notice(current_max_position_weight=0.10)
            assert notice is not None
            texts.append(notice.title)
            texts.extend(f"{label}｜{body}" for label, body in notice.items)
            short = record.short_notice(current_max_position_weight=0.10)
            if short is not None:
                texts.append(short)
    return texts


@pytest.mark.parametrize("text", _every_rendered_notice())
def test_every_notice_passes_the_wording_scans(text: str) -> None:
    """I-9 / 實作約束 6: the forbidden-term lists, plus the review's three words."""
    shared = json.loads(
        (STOCK_DESK_ROOT / "shared" / "forbidden-terms.json").read_text(encoding="utf-8")
    )
    terms = (
        set(FRONTEND_FORBIDDEN_TERMS)
        | set(shared["guarantee"])
        | set(shared["price_target"])
        | set(BANNED_PHRASES)
        | {"更安全", "保護你", "確保", "帶入回測結果", "最近一次"}
    )
    assert [term for term in sorted(terms) if term in text] == []
    assert find_bare_realtime_claims(text) == []


def test_no_notice_mentions_cap_5_on_the_skipped_path() -> None:
    """遷移未執行逐字審 第三節 6 (前審): the skipped copy does not name cap 5."""
    for surface in ("settings", "short"):
        copy = CAP1_MIGRATION_NOTICES[("skipped", surface)]
        text = json.dumps(copy.__dict__, ensure_ascii=False, default=lambda o: o.__dict__)
        assert "第 5 條" not in text and "Kelly" not in text


# --- Section names (I-4) -----------------------------------------------------------


def test_section_name_table_covers_exactly_the_stored_sections() -> None:
    assert set(CAP1_SECTION_NAMES) == set(store_module._SECTIONS)


@pytest.mark.parametrize(
    ("section", "source"),
    [
        ("risk_budget", "SettingsForm.tsx"),
        ("cost_model", "SettingsForm.tsx"),
        ("alerts", "SettingsForm.tsx"),
        ("net_worth", "NetWorthSection.tsx"),
    ],
)
def test_each_section_name_starts_its_settings_page_h2(section: str, source: str) -> None:
    text = (FRONTEND_SETTINGS / source).read_text(encoding="utf-8")
    headings = re.findall(r"<h2[^>]*>([^<{]+)</h2>", text)
    assert any(h.strip().startswith(CAP1_SECTION_NAMES[section]) for h in headings), headings


# --- Where the record and the notices travel ------------------------------------


def test_settings_gauge_and_position_responses_carry_the_notices(
    api_harness: ApiHarness, tmp_path: Path
) -> None:
    store = _migrated_store(tmp_path)
    app.dependency_overrides[get_settings_store] = lambda: store
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())

    body = api_harness.client.get("/api/settings").json()
    assert body["settings"]["risk_budget"]["max_position_weight"] == 0.10
    view = body["cap1_migration"]
    assert view["status"] == "migrated"
    assert view["previous_value"] == 0.15
    assert view["new_value"] == 0.10
    assert view["recorded_at"] == MIGRATED_AT.isoformat()
    assert view["basis"] == CAP1_MIGRATION_BASIS
    assert view["failed_sections"] == []
    assert view["changed_by_user"] is False
    assert view["notice"] == {
        "title": MIGRATED_SETTINGS_TITLE,
        "items": [
            {"label": label, "body": body}
            for label, body in (_filled(item) for item in MIGRATED_SETTINGS_ITEMS)
        ],
    }
    # The record is not part of the editable document.
    assert "cap1_migration" not in body["settings"]
    assert "migration" not in json.dumps(body["settings"]["risk_budget"])

    short = MIGRATED_SHORT.format(**FIELDS)
    gauge = api_harness.client.get("/api/portfolio/limits").json()
    assert gauge["cap1_migration_notice"] == short
    advice = api_harness.client.get("/api/advice/2330").json()
    assert advice["status"] == "ok"
    # #2' is the same constant as #2.
    assert advice["cap1_migration_notice"] == short

    # The user moves cap 1 themselves: the short notice stops everywhere, the
    # settings page keeps the record without 1-3 (F1/F8).
    response = api_harness.client.put(
        "/api/settings", json={"risk_budget": {"max_position_weight": 0.12}}
    )
    assert response.status_code == 200
    after = response.json()["cap1_migration"]
    assert after["changed_by_user"] is True
    assert [item["label"] for item in after["notice"]["items"]] == [
        "改了什麼",
        "為什麼改",
        "過去的紀錄",
        "可以改回",
    ]
    assert api_harness.client.get("/api/portfolio/limits").json()["cap1_migration_notice"] is None
    assert api_harness.client.get("/api/advice/2330").json()["cap1_migration_notice"] is None


def test_the_record_cannot_be_written_through_put(api_harness: ApiHarness) -> None:
    response = api_harness.client.put(
        "/api/settings", json={"cap1_migration": {"status": "not_applicable"}}
    )
    assert response.status_code == 422
    response = api_harness.client.put(
        "/api/settings",
        json={"risk_budget": {"max_position_weight": 0.1, "cap1_migrated": True}},
    )
    assert response.status_code == 422


def test_a_fresh_install_serves_a_record_with_no_notice(api_harness: ApiHarness) -> None:
    body = api_harness.client.get("/api/settings").json()
    assert body["cap1_migration"]["status"] == "not_applicable"
    assert body["cap1_migration"]["notice"] is None
    assert api_harness.client.get("/api/portfolio/limits").json()["cap1_migration_notice"] is None


def test_an_insufficient_advice_response_carries_no_notice(
    api_harness: ApiHarness, tmp_path: Path
) -> None:
    store = _migrated_store(tmp_path)
    app.dependency_overrides[get_settings_store] = lambda: store
    body = api_harness.client.get("/api/advice/9999").json()
    assert body["status"] == "insufficient_data"
    assert body["cap1_migration_notice"] is None


def test_a_store_without_a_record_serves_none(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.db", now=MIGRATED_AT)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DELETE FROM settings_migrations")
    conn.close()
    assert store.cap1_migration() is None
