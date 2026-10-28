"""One-time, recorded rewrites of stored settings (S2, CEO #63, 2026-10-26).

There is exactly one migration today: cap 1's stored ``max_position_weight``
equal to the old default 0.15 becomes the new default 0.10
(:data:`app.advice.limits.DEFAULT_MAX_POSITION_WEIGHT`). Changing the default
alone would not reach any installation that had ever saved its settings,
because :meth:`app.settings.store.SettingsStore.save` writes every section in
full -- a stored 0.15 is usually the old default frozen in place, not a choice
(quant proposal 2026-10-26, conclusion 2).

The rules, each from the risk review of 2026-10-26
(``work/reviews/2026-10-26-第1條上限下修審查-風控.md`` S2 附加實作約束) and the
quant proposal's constraint 4:

* **Raw payload in, one key out.** The migration never goes through
  ``load`` -> change -> ``save``: ``load`` silently replaces any section that no
  longer validates with its defaults, and ``save`` would then write those
  defaults over the user's real data for good. It reads the stored JSON
  directly and changes ``risk_budget.max_position_weight`` and nothing else;
  every other key of that section keeps its stored value and every other
  section's row is not written at all.
* **Any invalid section, no migration.** If any stored section fails its
  schema (or is not JSON), nothing is rewritten. A ``skipped`` record naming
  the failed sections is kept and served, so the state is visible rather than
  only logged. A skip is not final: the next construction of the store looks
  again, so a repaired document is migrated then.
* **Only the old default moves.** A stored value equal to 0.15 (within
  :data:`app.advice.limits.EPSILON`) is rewritten; any other value -- 0.12,
  0.10, 0.20 -- is the user's and is left exactly as stored.
* **Recorded, once.** The record (previous value, new value, when, on what
  basis) lives in its own table, never in a ``RiskBudget`` field, where it
  would travel through ``PUT`` bodies and could be edited. ``migrated`` and
  ``not_applicable`` are terminal: a later start never rewrites again, so a
  user who sets 0.15 back on purpose keeps it. The marker sits in the same
  database as the settings, so restoring a pre-migration backup restores the
  absence of the marker too, and the migration (and its notice) runs again.
* **The record changes at store construction only** (risk 2026-10-26 遷移未執行
  逐字審 I-6). The single exception is the ``changed_by_user`` flag of a
  ``migrated`` record (第1條下修告知逐字審 實作約束 2): a save that writes a cap-1
  value other than the migrated one sets it, and only a new migration clears
  it. It never touches a ``skipped`` record, whose notice must outlive a save
  (U5「按儲存之後也一樣」).
* **Never clamps.** Evaluation keeps reading the stored value as it is; there
  is no ``min(stored, 0.10)`` anywhere (``limits.py`` "不夾值").

The user-facing copy is :data:`CAP1_MIGRATION_NOTICES`, verbatim from the two
risk-compliance verbatim reviews of 2026-10-26
(``第1條下修告知字面逐字審-風控.md`` #1/#2/#2', ``遷移未執行與股數成因字面逐字審-風控.md``
U0-U5/S1/S1'). The backend fills every slot and chooses every branch; the
front end renders what it is given and composes nothing (I-1, I-5).
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, Literal

from pydantic import BaseModel, ValidationError

from app.advice.limits import (
    DEFAULT_MAX_POSITION_WEIGHT,
    EPSILON,
    PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT,
    RiskBudget,
    format_reported_at,
)

logger = logging.getLogger(__name__)

#: Stable id of the cap-1 migration; the primary key of its record row.
CAP1_MIGRATION_ID: Final = "cap1-max-position-weight-0.15-to-0.10"

#: What the rewrite rests on, stored with the record for audit. An identifier,
#: not display copy: the notice says the "why" in words risk-compliance signed.
CAP1_MIGRATION_BASIS: Final = (
    "CEO #61/#62/#63 2026-10-26; "
    "work/reviews/2026-10-26-第1條上限下修審查-風控.md; "
    "work/reviews/2026-10-26-第1條上限下修提案-quant-researcher.md"
)

#: ``migrated`` -- the stored 0.15 was rewritten to 0.10 (terminal);
#: ``not_applicable`` -- nothing to rewrite: never saved, or saved with another
#: value (terminal); ``skipped`` -- a stored section failed validation, so
#: nothing was touched (retried on the next start).
Cap1MigrationStatus = Literal["migrated", "not_applicable", "skipped"]

_TERMINAL: Final[frozenset[str]] = frozenset({"migrated", "not_applicable"})

#: Where a notice is rendered. ``settings`` is the full version beside the
#: cap-1 field; ``short`` is the one sentence the risk gauge's cap-1 row and
#: the position page's ``LimitsCheckList`` cap-1 item share (#2/#2', S1/S1').
NoticeSurface = Literal["settings", "short"]

#: When an item of a settings notice is part of it.
#:
#: * ``always``;
#: * ``unchanged_by_user`` -- only while the user has not written another cap-1
#:   value since the migration (1-3; F1/F8);
#: * ``risk_budget_valid`` / ``risk_budget_failed`` -- whether ``risk_budget``
#:   is among the sections that failed validation (U2 / U2').
ItemCondition = Literal["always", "unchanged_by_user", "risk_budget_valid", "risk_budget_failed"]


@dataclass(frozen=True)
class NoticeItem:
    """One「標籤｜正文」item of the settings-page notice."""

    label: str
    #: A ``str.format`` template; see :meth:`Cap1MigrationRecord.notice_fields`.
    body: str
    shown: ItemCondition = "always"


@dataclass(frozen=True)
class SettingsNoticeCopy:
    """The settings-page version: a title over ordered labelled items."""

    title: str
    items: tuple[NoticeItem, ...]


@dataclass(frozen=True)
class ShortNoticeCopy:
    """The one-sentence version, with the ``risk_budget``-failed branch (S1')."""

    text: str
    #: Used instead of ``text`` when ``risk_budget`` itself failed validation;
    #: ``None`` when the status has no such branch.
    text_if_risk_budget_failed: str | None = None


#: Every user-facing sentence of the S2 notices, keyed by (status, surface)
#: (I-1). Verbatim from the risk-compliance finalised tables; dev does not
#: write or edit these. ``not_applicable`` has no notice.
CAP1_MIGRATION_NOTICES: Final[Mapping[tuple[str, str], SettingsNoticeCopy | ShortNoticeCopy]] = (
    MappingProxyType(
        {
            # 第1條下修告知字面逐字審 #1, 1-1 ~ 1-5.
            ("migrated", "settings"): SettingsNoticeCopy(
                title="第 1 條上限自動調整紀錄",
                items=(
                    NoticeItem(
                        "改了什麼",
                        "{migrated_at}，系統把「單一標的佔比上限」由 {old_value}（{old_pct}）"
                        "自動改為 {new_value}（{new_pct}）。只有這一個值被改（原值等於 {old_pct} "
                        "才會改），其他設定都沒有改動。",
                    ),
                    NoticeItem(
                        "為什麼改",
                        "第 5 條「分數 Kelly 部位上限」的計算方式有誤，已決定停用。為了不讓上限因"
                        "第 5 條停用而變寬，依 2026-10-26 的決定下修第 1 條。{new_pct} 是政策設定，"
                        "沒有經過回測或歷史驗證。",
                    ),
                    NoticeItem(
                        "會看到的變化",
                        "佔比在 {new_pct} 以上（含剛好 {new_pct}）的持股會顯示已違反第 1 條；"
                        "其中佔比未滿 {old_pct} 的，在原本 {old_pct} 的上限下不會顯示已違反。"
                        "這些持股原本是加碼參考的，會改為續抱參考；減碼的股數區間可能變大，"
                        "加碼區間可能變小或消失，候選標的的試算股數可能變少；若設了上限警示，"
                        "可能開始收到推播。",
                        shown="unchanged_by_user",
                    ),
                    # 1-4: 風控 2026-10-26「第1條下修第一批四項裁定」第二節逐字定稿, which
                    # replaced the earlier text claiming advice cards keep the old
                    # cap (they are never stored). No placeholder on purpose: older
                    # alerts may carry other caps, and the current setting may no
                    # longer be the migrated one (F1).
                    # F-g (rewritten by that ruling): withdraw 1-4 or send it back
                    # to risk-compliance if (a) advice cards ever get a store,
                    # snapshot or history, or (b) ``alert_events.message`` is ever
                    # recomputed or rewritten on read or acknowledgement.
                    NoticeItem(
                        "過去的紀錄",
                        "已觸發的警示保留觸發當時的文字（含當時的上限），不回頭改寫。"
                        "建議卡沒有存檔，每次載入都依目前的設定重新計算，所以查不到調整前的建議卡。",
                    ),
                    NoticeItem(
                        "可以改回",
                        "在本欄位自行修改即可，包括改回 {old_value}。改高等於放寬上限，"
                        "儲存前會先要求你確認。",
                    ),
                ),
            ),
            # 第1條下修告知字面逐字審 #2 / #2' (one constant, two places).
            ("migrated", "short"): ShortNoticeCopy(
                text=(
                    "第 1 條上限已於 {migrated_at} 由 {old_pct} 自動改為 {new_pct}；{new_pct} "
                    "是政策設定，未經回測或歷史驗證。佔比達 {new_pct} 以上的持股顯示已違反，"
                    "其中未滿 {old_pct} 的，在原本 {old_pct} 的上限下不會顯示已違反。"
                    "完整紀錄在設定頁。"
                ),
            ),
            # 遷移未執行與股數成因字面逐字審 第 1 組 U0 ~ U5.
            ("skipped", "settings"): SettingsNoticeCopy(
                title="第 1 條上限自動調整未執行",
                items=(
                    NoticeItem(
                        "發生了什麼",
                        "{attempted_at}，系統檢查已存設定時，{section_names}沒有通過驗證，"
                        "因此沒有執行第 1 條「單一標的佔比上限」的自動調整（已存值等於 "
                        "{old_default_pct} 時改為 {new_default_pct}），已存設定沒有任何改動。",
                    ),
                    NoticeItem(
                        "目前使用的值",
                        "第 1 條上限目前使用 {current_pct}，取自已存設定。",
                        shown="risk_budget_valid",
                    ),
                    NoticeItem(
                        "目前使用的值",
                        "第 1 條上限目前使用 {current_pct}。因為風險預算沒有通過驗證，在本頁按儲存"
                        "之前，系統用的是預設值 {default_pct}，不是原本存的內容。",
                        shown="risk_budget_failed",
                    ),
                    NoticeItem(
                        "頁面與存檔",
                        "在本頁按儲存之前，{section_names}在本頁顯示的是預設值，不是原本存的內容。"
                        "本頁任何一個儲存按鈕都會把所有區段整份寫入，包括{section_names}；"
                        "原本存的內容會被取代，系統內不會保留。",
                    ),
                    NoticeItem(
                        "可用的操作",
                        "本欄位可以自行修改數值。改高等於放寬上限，儲存前會先要求你確認。",
                    ),
                    NoticeItem(
                        "之後",
                        "系統每次啟動時會再檢查一次，所有區段都通過驗證時才會執行這次調整。"
                        "在那之前，這則告知會一直顯示，按儲存之後也一樣。",
                    ),
                ),
            ),
            # 遷移未執行與股數成因字面逐字審 第 1 組 S1 / S1'.
            ("skipped", "short"): ShortNoticeCopy(
                text=(
                    "第 1 條上限的自動調整於 {attempted_at}未執行，原因是已存設定有區段未通過驗證；"
                    "目前使用的上限是 {current_pct}。詳見設定頁。"
                ),
                text_if_risk_budget_failed=(
                    "第 1 條上限的自動調整於 {attempted_at}未執行，原因是已存設定有區段未通過驗證，"
                    "包括風險預算；目前使用的上限是 {current_pct}，在設定頁儲存之前用的是預設值 "
                    "{default_pct}，不是原本存的內容。詳見設定頁。"
                ),
            ),
        }
    )
)

#: Section id -> the name the settings page's h2 starts with (遷移未執行逐字審
#: 區段名稱對照, I-4). Every section of ``app.settings.store._SECTIONS`` must be
#: here; a missing one is a ``KeyError``, never a fallback to the internal key.
CAP1_SECTION_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "risk_budget": "風險預算",
        "cost_model": "費率",
        "alerts": "警示排程",
        "net_worth": "帳戶總淨值",
    }
)

#: Joins ``{section_names}`` (I-4).
SECTION_NAME_SEPARATOR: Final = "、"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings_migrations (
    migration_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    previous_value REAL,
    new_value REAL,
    failed_sections TEXT NOT NULL,
    basis TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    changed_by_user INTEGER NOT NULL DEFAULT 0
)
"""


def _percent(value: float) -> str:
    """Two decimals, the format the gauge's threshold column uses (``formatPercent``)."""
    return f"{value:.2%}"


def _plain(value: float) -> str:
    """A fraction the way the settings field shows it (``String(0.1)`` -> ``0.1``)."""
    return repr(float(value))


def _model_default_weight() -> float:
    """``RiskBudget``'s own default for ``max_position_weight`` ({default_pct})."""
    default = RiskBudget.model_fields["max_position_weight"].default
    assert isinstance(default, float)
    return default


@dataclass(frozen=True)
class SettingsNotice:
    """A filled settings-page notice: title and ordered (label, body) items."""

    title: str
    items: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Cap1MigrationRecord:
    """The stored outcome of the cap-1 migration."""

    status: Cap1MigrationStatus
    #: The stored value before the migration looked at it; ``None`` when there
    #: was no readable ``risk_budget`` row. Audit only: no notice reads it (I-3).
    previous_value: float | None
    #: The value written; ``None`` unless ``status == "migrated"``.
    new_value: float | None
    #: Section ids that failed validation, in ``_SECTIONS`` order; empty unless
    #: ``status == "skipped"``.
    failed_sections: tuple[str, ...]
    basis: str
    #: ISO 8601 UTC. For ``skipped``, the latest attempt (rewritten on every
    #: retry).
    recorded_at: str
    #: ``migrated`` only: a save has since written a cap-1 value other than
    #: ``new_value``. Cleared only by a new migration.
    changed_by_user: bool = False

    @property
    def risk_budget_failed(self) -> bool:
        return "risk_budget" in self.failed_sections

    def settings_notice(self, *, current_max_position_weight: float) -> SettingsNotice | None:
        """The settings-page notice for this record, or ``None`` (I-5)."""
        copy = CAP1_MIGRATION_NOTICES.get((self.status, "settings"))
        if copy is None:
            return None
        assert isinstance(copy, SettingsNoticeCopy)
        fields = self.notice_fields(current_max_position_weight=current_max_position_weight)
        return SettingsNotice(
            title=copy.title.format(**fields),
            items=tuple(
                (item.label, item.body.format(**fields))
                for item in copy.items
                if self._shows(item.shown)
            ),
        )

    def short_notice(self, *, current_max_position_weight: float) -> str | None:
        """The shared gauge / position-page sentence, or ``None``.

        ``migrated`` stands until the user writes another cap-1 value (F1/F8);
        ``skipped`` stands until a later start migrates or finds nothing to do.
        """
        copy = CAP1_MIGRATION_NOTICES.get((self.status, "short"))
        if copy is None:
            return None
        assert isinstance(copy, ShortNoticeCopy)
        if self.status == "migrated" and self.changed_by_user:
            return None
        template = (
            copy.text_if_risk_budget_failed
            if self.risk_budget_failed and copy.text_if_risk_budget_failed is not None
            else copy.text
        )
        return template.format(
            **self.notice_fields(current_max_position_weight=current_max_position_weight)
        )

    def _shows(self, condition: ItemCondition) -> bool:
        if condition == "unchanged_by_user":
            return not self.changed_by_user
        if condition == "risk_budget_valid":
            return not self.risk_budget_failed
        if condition == "risk_budget_failed":
            return self.risk_budget_failed
        return True

    def notice_fields(self, *, current_max_position_weight: float) -> dict[str, str]:
        """Every interpolation field the notices may use (I-3).

        The old and new values are the two constants, never
        ``previous_value``: a ``migrated`` record only exists for a stored
        value equal to the old default, and a ``skipped`` one states the rule,
        not whatever was stored. ``{current_pct}`` is the value the caller
        actually loaded for this evaluation.
        """
        when = format_reported_at(self.recorded_at)
        return {
            "migrated_at": when,
            "attempted_at": when,
            "old_value": _plain(PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT),
            "new_value": _plain(DEFAULT_MAX_POSITION_WEIGHT),
            "old_pct": _percent(PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT),
            "new_pct": _percent(DEFAULT_MAX_POSITION_WEIGHT),
            "old_default_pct": _percent(PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT),
            "new_default_pct": _percent(DEFAULT_MAX_POSITION_WEIGHT),
            "default_pct": _percent(_model_default_weight()),
            "current_pct": _percent(current_max_position_weight),
            "section_names": SECTION_NAME_SEPARATOR.join(
                CAP1_SECTION_NAMES[section] for section in self.failed_sections
            ),
        }


def init_migrations_table(conn: sqlite3.Connection) -> None:
    """Create the record table if missing (DDL only, no transaction opened)."""
    conn.execute(_CREATE_TABLE_SQL)


def read_cap1_migration(conn: sqlite3.Connection) -> Cap1MigrationRecord | None:
    """The cap-1 record, or ``None`` if the migration has never run here."""
    row = conn.execute(
        "SELECT status, previous_value, new_value, failed_sections, basis, recorded_at, "
        "changed_by_user FROM settings_migrations WHERE migration_id = ?",
        (CAP1_MIGRATION_ID,),
    ).fetchone()
    if row is None:
        return None
    status, previous_value, new_value, failed_sections, basis, recorded_at, changed = row
    return Cap1MigrationRecord(
        status=status,
        previous_value=None if previous_value is None else float(previous_value),
        new_value=None if new_value is None else float(new_value),
        failed_sections=tuple(json.loads(failed_sections)),
        basis=str(basis),
        recorded_at=str(recorded_at),
        changed_by_user=bool(changed),
    )


def note_cap1_write(conn: sqlite3.Connection, written_max_position_weight: float) -> None:
    """Flag a ``migrated`` record once a save writes another cap-1 value.

    Called by :meth:`app.settings.store.SettingsStore.save` inside its own
    transaction. Only ``changed_by_user`` of a ``migrated`` record can change
    here; status, timestamps and every other record leave this untouched (I-6).
    """
    record = read_cap1_migration(conn)
    if record is None or record.status != "migrated" or record.changed_by_user:
        return
    if record.new_value is not None and math.isclose(
        written_max_position_weight, record.new_value, rel_tol=0.0, abs_tol=EPSILON
    ):
        return
    conn.execute(
        "UPDATE settings_migrations SET changed_by_user = 1 WHERE migration_id = ?",
        (CAP1_MIGRATION_ID,),
    )


def migrate_cap1_default(
    conn: sqlite3.Connection,
    sections: Mapping[str, type[BaseModel]],
    *,
    now: datetime,
) -> Cap1MigrationRecord:
    """Run the cap-1 migration once; return the record in force afterwards.

    ``sections`` is the store's section -> model map, so "every section
    validates" means exactly what ``load`` means by it. Runs inside one
    ``BEGIN IMMEDIATE`` (the device ``app.kelly.store`` uses for its own
    migration): the backend and the scheduler may start against the same file
    at once, and the loser must find the winner's record, not repeat the work.
    Must be called outside any open transaction.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = read_cap1_migration(conn)
        if existing is not None and existing.status in _TERMINAL:
            conn.execute("COMMIT")
            return existing
        record = _decide_and_apply(conn, sections, now=now)
        _write_record(conn, record)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    _log(record)
    return record


def _decide_and_apply(
    conn: sqlite3.Connection,
    sections: Mapping[str, type[BaseModel]],
    *,
    now: datetime,
) -> Cap1MigrationRecord:
    stored = {
        str(section): str(payload)
        for section, payload in conn.execute("SELECT section, payload FROM app_settings")
    }
    moment = now.isoformat()

    failed = tuple(
        name
        for name, model in sections.items()
        if name in stored and not _validates(model, stored[name])
    )
    raw_budget = stored.get("risk_budget")
    previous = _stored_weight(raw_budget) if raw_budget is not None else None
    if failed:
        return Cap1MigrationRecord(
            status="skipped",
            previous_value=previous,
            new_value=None,
            failed_sections=failed,
            basis=CAP1_MIGRATION_BASIS,
            recorded_at=moment,
        )
    if (
        raw_budget is None
        or previous is None
        or not math.isclose(
            previous, PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT, rel_tol=0.0, abs_tol=EPSILON
        )
    ):
        # Never saved (the model default is already 0.10), or saved with a value
        # other than the old default: that value is the user's.
        return Cap1MigrationRecord(
            status="not_applicable",
            previous_value=previous,
            new_value=None,
            failed_sections=(),
            basis=CAP1_MIGRATION_BASIS,
            recorded_at=moment,
        )

    payload: dict[str, Any] = json.loads(raw_budget)
    payload["max_position_weight"] = DEFAULT_MAX_POSITION_WEIGHT
    # Re-validated before it is written: the rewritten section has to be one
    # ``load`` will accept, or the migration would itself be the corruption.
    RiskBudget.model_validate(payload)
    conn.execute(
        "UPDATE app_settings SET payload = ?, updated_at = ? WHERE section = 'risk_budget'",
        (json.dumps(payload, ensure_ascii=False), moment),
    )
    return Cap1MigrationRecord(
        status="migrated",
        previous_value=previous,
        new_value=DEFAULT_MAX_POSITION_WEIGHT,
        failed_sections=(),
        basis=CAP1_MIGRATION_BASIS,
        recorded_at=moment,
    )


def _validates(model: type[BaseModel], payload: str) -> bool:
    try:
        model.model_validate_json(payload)
    except ValidationError:
        return False
    return True


def _stored_weight(raw_budget: str) -> float | None:
    """``max_position_weight`` as stored, or ``None`` if it cannot be read."""
    try:
        payload = json.loads(raw_budget)
    except ValueError:
        return None
    value = payload.get("max_position_weight") if isinstance(payload, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _write_record(conn: sqlite3.Connection, record: Cap1MigrationRecord) -> None:
    # A new record always starts with ``changed_by_user`` cleared: only a new
    # migration may clear the flag (F4/F10: a restored backup migrates again
    # and the notice comes back in full).
    conn.execute(
        """
        INSERT INTO settings_migrations (
            migration_id, status, previous_value, new_value, failed_sections, basis,
            recorded_at, changed_by_user
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(migration_id) DO UPDATE SET
            status = excluded.status,
            previous_value = excluded.previous_value,
            new_value = excluded.new_value,
            failed_sections = excluded.failed_sections,
            basis = excluded.basis,
            recorded_at = excluded.recorded_at,
            changed_by_user = 0
        """,
        (
            CAP1_MIGRATION_ID,
            record.status,
            record.previous_value,
            record.new_value,
            json.dumps(list(record.failed_sections)),
            record.basis,
            record.recorded_at,
        ),
    )


def _log(record: Cap1MigrationRecord) -> None:
    if record.status == "migrated":
        logger.info(
            "settings migration %s: max_position_weight %s -> %s at %s",
            CAP1_MIGRATION_ID,
            record.previous_value,
            record.new_value,
            record.recorded_at,
        )
    elif record.status == "skipped":
        logger.warning(
            "settings migration %s skipped: stored sections failed validation: %s",
            CAP1_MIGRATION_ID,
            ", ".join(record.failed_sections),
        )
