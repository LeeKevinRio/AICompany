"""Validation of watch form input and global settings. Messages are user-facing (zh-TW)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import cast

from flight_deals.domain.airlines import MAX_AIRLINES, lookup_airline
from flight_deals.domain.airports import is_selectable, lookup, same_city_group
from flight_deals.domain.currency import DEFAULT_CURRENCY, major_to_minor
from flight_deals.domain.models import CABINS, Cabin, DateMode, TripType, WatchSpec

_INTEGER = re.compile(r"^-?\d+$")
MAX_TRIP_DAYS = 60
MAX_STOPS_LIMIT = 2
MAX_NAME_LENGTH = 80
MAX_BUDGET_MAJOR = 10_000_000
# Bounds that keep date-pair expansion small (one-year horizon, one-year window).
MAX_DAYS_AHEAD = 365
MAX_WINDOW_DAYS = 366
# Longest accepted integer text; longer input is rejected before int() conversion.
MAX_INT_DIGITS = 12
TOO_LARGE = "數值過大"
_FALSY = {"false", "0", "off", "no", ""}
UNKNOWN_PLACE = "找不到此機場或城市，請從下拉選取"
ORIGIN_REQUIRED = "請從下拉選取出發地"
UNVERIFIED_CITY = "此城市代碼尚未確認可查價，請改選個別機場"
SAME_CITY = "出發地與目的地不可為同一城市"

# Trip options (ADR-0002 FD-5 Decisions 1 and 9). The total cap of 9 is our own rule.
MAX_ADULTS = 9
MAX_CHILDREN = 8
MAX_PASSENGERS = 9
ADULTS_REQUIRED = "請填寫成人人數"
ADULTS_NOT_INT = "成人人數必須是整數"
ADULTS_RANGE = f"成人人數須介於 1 到 {MAX_ADULTS}"
CHILDREN_REQUIRED = "請填寫兒童人數（沒有兒童請填 0）"
CHILDREN_NOT_INT = "兒童人數必須是整數"
CHILDREN_RANGE = f"兒童人數須介於 0 到 {MAX_CHILDREN}"
PASSENGERS_TOTAL = f"成人與兒童合計不可超過 {MAX_PASSENGERS} 人"
CABIN_INVALID = "艙等不正確，請從選單選取"
AIRLINES_INVALID = "航空公司格式不正確，請從清單選取"
AIRLINES_TOO_MANY = f"航空公司最多選擇 {MAX_AIRLINES} 家"
DEP_HOUR_NOT_INT = "出發時刻必須是 0 到 23 的整數"
DEP_HOUR_RANGE = "出發時刻須介於 0 到 23"
DEP_HOUR_PAIR = "最早與最晚出發時刻需同時選擇或同時不限"
DEP_HOUR_ORDER = "最晚出發時刻須晚於最早出發時刻"
_AIRLINE_CODE = re.compile(r"[A-Z0-9]{2}", re.ASCII)
_AIRLINE_SPLIT = re.compile(r"[\s,，、]+")


# Placeholder whose trip-option fields are the model defaults (used on create).
_DEFAULT_TRIP = WatchSpec(
    name="",
    origin="TPE",
    destination="TPE",
    trip_type="one_way",
    date_mode="fixed",
    depart_date=None,
    return_date=None,
    window_start=None,
    window_end=None,
    min_trip_days=None,
    max_trip_days=None,
    max_stops=None,
    budget_amount_minor=None,
)


def unknown_airline(code: str) -> str:
    return f"找不到航空公司代碼 {code}，請從清單選取"


@dataclass(frozen=True)
class ValidationOutcome:
    spec: WatchSpec | None
    errors: dict[str, str]


def _text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(raw: Mapping[str, object], key: str, errors: dict[str, str]) -> date | None:
    text = _text(raw, key)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        errors[key] = "日期格式錯誤（應為 YYYY-MM-DD）"
        return None


def _parse_int(raw: Mapping[str, object], key: str, errors: dict[str, str]) -> int | None:
    value = raw.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        errors[key] = "必須是整數"
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if len(text.lstrip("-")) > MAX_INT_DIGITS:
        errors[key] = TOO_LARGE
        return None
    if not _INTEGER.match(text):
        errors[key] = "必須是整數"
        return None
    return int(text)


def _parse_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in _FALSY


def _parse_count(
    raw: Mapping[str, object],
    key: str,
    default: int,
    errors: dict[str, str],
    *,
    required: str,
    not_int: str,
) -> int:
    """Passenger count: absent key -> default; explicit blank or non-integer -> error."""
    if key not in raw:
        return default
    value = _parse_int(raw, key, errors)
    if key in errors:
        errors[key] = TOO_LARGE if errors[key] == TOO_LARGE else not_int
        return default
    if value is None:
        errors[key] = required
        return default
    return value


def _airline_items(value: object) -> list[str] | None:
    """Codes from a JSON list or a typed comma-separated string; None = bad shape."""
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in _AIRLINE_SPLIT.split(value) if part]
    if isinstance(value, list | tuple):
        items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                return None
            items.extend(part for part in _AIRLINE_SPLIT.split(item) if part)
        return items
    return None


def _parse_airlines(
    raw: Mapping[str, object], errors: dict[str, str], previous: tuple[str, ...]
) -> tuple[str, ...]:
    """Upper-case, de-duplicated, sorted codes (Decision 6).

    Only a code already stored on the watch being edited may bypass the table check.
    A missing key keeps the stored codes (partial update).
    """
    if "airlines" not in raw:
        return previous
    items = _airline_items(raw.get("airlines"))
    if items is None:
        errors["airlines"] = AIRLINES_INVALID
        return ()
    codes: list[str] = []
    for item in items:
        code = item.strip().upper()
        if code in codes:
            continue
        if not _AIRLINE_CODE.fullmatch(code):
            errors["airlines"] = AIRLINES_INVALID
            return ()
        if code not in previous and lookup_airline(code) is None:
            errors["airlines"] = unknown_airline(code)
            return ()
        codes.append(code)
    if len(codes) > MAX_AIRLINES:
        errors["airlines"] = AIRLINES_TOO_MANY
        return ()
    return tuple(sorted(codes))


def _parse_hour(
    raw: Mapping[str, object], key: str, errors: dict[str, str], previous: int | None
) -> int | None:
    if key not in raw:
        return previous  # partial update keeps the stored hour (None on create)
    value = _parse_int(raw, key, errors)
    if key in errors:
        errors[key] = DEP_HOUR_NOT_INT
        return None
    if value is not None and not 0 <= value <= 23:
        errors[key] = DEP_HOUR_RANGE
        return None
    return value


def _parse_trip_options(
    raw: Mapping[str, object], errors: dict[str, str], existing: WatchSpec | None
) -> tuple[int, int, Cabin, tuple[str, ...], int | None, int | None]:
    """Trip options. A key missing from an edit keeps the stored value, so a partial
    update never silently resets a party to 1 adult (and bumps the revision)."""
    base = existing or _DEFAULT_TRIP
    adults = _parse_count(
        raw, "adults", base.adults, errors, required=ADULTS_REQUIRED, not_int=ADULTS_NOT_INT
    )
    if "adults" not in errors and not 1 <= adults <= MAX_ADULTS:
        errors["adults"] = ADULTS_RANGE
    children = _parse_count(
        raw,
        "children",
        base.children,
        errors,
        required=CHILDREN_REQUIRED,
        not_int=CHILDREN_NOT_INT,
    )
    if "children" not in errors and not 0 <= children <= MAX_CHILDREN:
        errors["children"] = CHILDREN_RANGE
    if "adults" not in errors and "children" not in errors and adults + children > MAX_PASSENGERS:
        errors["children"] = PASSENGERS_TOTAL

    cabin_text = _text(raw, "cabin") if "cabin" in raw else base.cabin
    cabin: Cabin = base.cabin
    if cabin_text in CABINS:
        cabin = cabin_text
    else:
        errors["cabin"] = CABIN_INVALID

    airlines = _parse_airlines(raw, errors, base.airlines)

    hour_from = _parse_hour(raw, "dep_hour_from", errors, base.dep_hour_from)
    hour_to = _parse_hour(raw, "dep_hour_to", errors, base.dep_hour_to)
    if "dep_hour_from" not in errors and "dep_hour_to" not in errors:
        if (hour_from is None) != (hour_to is None):
            missing = "dep_hour_from" if hour_from is None else "dep_hour_to"
            errors[missing] = DEP_HOUR_PAIR
        elif hour_from is not None and hour_to is not None and hour_from >= hour_to:
            errors["dep_hour_to"] = DEP_HOUR_ORDER
    return adults, children, cabin, airlines, hour_from, hour_to


def validate_watch_input(
    raw: Mapping[str, object], today: date, existing: WatchSpec | None = None
) -> ValidationOutcome:
    """Validate raw form values. ``today`` is the Asia/Taipei calendar date.

    On edit (``existing`` given), date fields left unchanged are not rejected for being
    in the past, so a running flexible window can still have its budget edited. Likewise
    an origin / destination code kept unchanged skips the airport table check (FR-C1).
    """
    errors: dict[str, str] = {}

    # Default TPE only when the key is absent; an explicit blank must not become TPE.
    origin = _text(raw, "origin").upper() if "origin" in raw else "TPE"
    destination = _text(raw, "destination").upper()
    prev_origin = existing.origin if existing else None
    prev_destination = existing.destination if existing else None

    def check_place(key: str, code: str, previous: str | None) -> None:
        # C-21: only a code kept unchanged on edit may bypass the table check (FR-C1).
        if existing is not None and code == previous:
            return
        place = lookup(code)
        if place is None:
            errors[key] = UNKNOWN_PLACE
        elif not is_selectable(place):
            errors[key] = UNVERIFIED_CITY

    if not origin:
        errors["origin"] = ORIGIN_REQUIRED
    else:
        check_place("origin", origin, prev_origin)
    if not destination:
        errors["destination"] = "請填寫目的地"
    else:
        check_place("destination", destination, prev_destination)
    if "origin" not in errors and "destination" not in errors:
        unchanged = origin == prev_origin and destination == prev_destination
        if origin == destination:
            errors["destination"] = "出發地與目的地不可相同"
        elif not unchanged and same_city_group(origin, destination):
            errors["destination"] = SAME_CITY

    trip_type_text = _text(raw, "trip_type") or "round_trip"
    if trip_type_text not in ("round_trip", "one_way"):
        errors["trip_type"] = "行程型態不正確"
        trip_type_text = "round_trip"
    trip_type = cast(TripType, trip_type_text)

    date_mode_text = _text(raw, "date_mode") or "fixed"
    if date_mode_text not in ("fixed", "flexible"):
        errors["date_mode"] = "日期模式不正確"
        date_mode_text = "fixed"
    date_mode = cast(DateMode, date_mode_text)

    depart_date: date | None = None
    return_date: date | None = None
    window_start: date | None = None
    window_end: date | None = None
    min_days: int | None = None
    max_days: int | None = None

    def check_not_past(key: str, value: date | None, previous: date | None) -> None:
        if value is None or key in errors:
            return
        if value < today and not (existing is not None and previous == value):
            errors[key] = "日期不可早於今天"

    latest = today + timedelta(days=MAX_DAYS_AHEAD)

    def check_not_too_far(key: str, value: date | None) -> None:
        if value is None or key in errors:
            return
        if value > latest:
            errors[key] = f"日期不可晚於今天起 {MAX_DAYS_AHEAD} 天（{latest.isoformat()}）"

    if date_mode == "fixed":
        depart_date = _parse_date(raw, "depart_date", errors)
        if depart_date is None and "depart_date" not in errors:
            errors["depart_date"] = "請填寫出發日"
        check_not_past("depart_date", depart_date, existing.depart_date if existing else None)
        check_not_too_far("depart_date", depart_date)
        if trip_type == "round_trip":
            return_date = _parse_date(raw, "return_date", errors)
            if return_date is None and "return_date" not in errors:
                errors["return_date"] = "來回行程請填寫回程日"
            check_not_too_far("return_date", return_date)
            if (
                depart_date
                and return_date
                and "return_date" not in errors
                and return_date < depart_date
            ):
                errors["return_date"] = "回程日不可早於出發日"
    else:
        window_start = _parse_date(raw, "window_start", errors)
        window_end = _parse_date(raw, "window_end", errors)
        end_label = "最晚回程日" if trip_type == "round_trip" else "最晚出發日"
        if window_start is None and "window_start" not in errors:
            errors["window_start"] = "請填寫最早出發日"
        if window_end is None and "window_end" not in errors:
            errors["window_end"] = f"請填寫{end_label}"
        check_not_past("window_start", window_start, existing.window_start if existing else None)
        check_not_past("window_end", window_end, existing.window_end if existing else None)
        check_not_too_far("window_start", window_start)
        check_not_too_far("window_end", window_end)
        if window_start and window_end and "window_end" not in errors:
            if window_end < window_start:
                errors["window_end"] = f"{end_label}不可早於最早出發日"
            elif (window_end - window_start).days > MAX_WINDOW_DAYS:
                errors["window_end"] = f"彈性窗長度不可超過 {MAX_WINDOW_DAYS} 天"
        if trip_type == "round_trip":
            min_days = _parse_int(raw, "min_trip_days", errors)
            max_days = _parse_int(raw, "max_trip_days", errors)
            if min_days is None and "min_trip_days" not in errors:
                errors["min_trip_days"] = "請填寫旅程天數下限"
            if max_days is None and "max_trip_days" not in errors:
                errors["max_trip_days"] = "請填寫旅程天數上限"
            if min_days is not None and not 1 <= min_days <= MAX_TRIP_DAYS:
                errors["min_trip_days"] = f"天數須介於 1 到 {MAX_TRIP_DAYS}"
            if max_days is not None and not 1 <= max_days <= MAX_TRIP_DAYS:
                errors["max_trip_days"] = f"天數須介於 1 到 {MAX_TRIP_DAYS}"
            if (
                min_days is not None
                and max_days is not None
                and "min_trip_days" not in errors
                and "max_trip_days" not in errors
                and min_days > max_days
            ):
                errors["min_trip_days"] = "天數下限不可大於上限"
            if (
                not errors
                and window_start
                and window_end
                and min_days is not None
                and (window_end - window_start).days < min_days
            ):
                errors["window_end"] = "彈性窗長度短於旅程天數下限"

    max_stops = _parse_int(raw, "max_stops", errors)
    if max_stops is not None and not 0 <= max_stops <= MAX_STOPS_LIMIT:
        errors["max_stops"] = f"轉機次數上限須介於 0 到 {MAX_STOPS_LIMIT}，或留空表示不限"

    budget_major = _parse_int(raw, "budget", errors)
    if "budget" in errors:
        errors["budget"] = "預算門檻須為正整數"
    elif budget_major is None:
        errors["budget"] = "請填寫預算門檻"
    elif budget_major <= 0:
        errors["budget"] = "預算門檻須為正整數"
    elif budget_major > MAX_BUDGET_MAJOR:
        errors["budget"] = "預算門檻過大"

    notify_on_new_low = _parse_bool(raw.get("notify_on_new_low"), True)
    adults, children, cabin, airlines, hour_from, hour_to = _parse_trip_options(
        raw, errors, existing
    )

    name = _text(raw, "name")
    if len(name) > MAX_NAME_LENGTH:
        errors["name"] = f"名稱最多 {MAX_NAME_LENGTH} 字"

    if errors or budget_major is None:
        return ValidationOutcome(None, errors)

    spec = WatchSpec(
        name=name or f"{origin}→{destination}",
        origin=origin,
        destination=destination,
        trip_type=trip_type,
        date_mode=date_mode,
        depart_date=depart_date,
        return_date=return_date,
        window_start=window_start,
        window_end=window_end,
        min_trip_days=min_days,
        max_trip_days=max_days,
        max_stops=max_stops,
        budget_amount_minor=major_to_minor(budget_major, DEFAULT_CURRENCY),
        currency=DEFAULT_CURRENCY,
        notify_on_new_low=notify_on_new_low,
        adults=adults,
        children=children,
        cabin=cabin,
        airlines=airlines,
        dep_hour_from=hour_from,
        dep_hour_to=hour_to,
    )
    return ValidationOutcome(spec, {})


@dataclass(frozen=True)
class SettingRule:
    label: str
    minimum: int
    maximum: int


def setting_rules(min_scan_interval_minutes: int) -> dict[str, SettingRule]:
    return {
        "scan_interval_minutes": SettingRule("掃描週期（分鐘）", min_scan_interval_minutes, 10080),
        "max_pairs_per_scan": SettingRule("每監看每輪查詢上限", 1, 50),
        "drop_threshold_bp": SettingRule("下跌比例門檻（bp）", 1, 9999),
        "stale_after_hours": SettingRule("價格過期標示（小時）", 1, 720),
        "global_hourly_query_limit": SettingRule("全域每小時查詢上限", 1, 1000),
    }


# Daily digest settings (ADR-0002 FD-4 Decision 2): kept apart from the integer rules.
DIGEST_ENABLED_KEY = "digest_enabled"
DIGEST_TIME_KEY = "digest_time"
DIGEST_SETTING_KEYS = (DIGEST_ENABLED_KEY, DIGEST_TIME_KEY)
DIGEST_TIME_PATTERN = re.compile(r"([01]\d|2[0-3]):[0-5]\d", re.ASCII)
_DIGEST_FLAG_TEXT = {"1": True, "true": True, "0": False, "false": False}
DIGEST_ENABLED_ERROR = "每日摘要開關只能是開啟或關閉"
DIGEST_TIME_REQUIRED = "請填寫推播時間"
DIGEST_TIME_ERROR = "推播時間格式須為 HH:MM（24 小時制，00:00 到 23:59）"


def parse_digest_enabled(value: object) -> bool | None:
    """Strict flag: a bool or the text "0" / "1" / "true" / "false"; anything else is None."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _DIGEST_FLAG_TEXT.get(value.strip().lower())
    return None


def parse_digest_time(value: object) -> str | None:
    """Strict ``HH:MM`` (00:00-23:59); returns the text unchanged or None."""
    if isinstance(value, str) and DIGEST_TIME_PATTERN.fullmatch(value):
        return value
    return None


def validate_digest_settings(raw: Mapping[str, object]) -> tuple[dict[str, str], dict[str, str]]:
    """Validate digest keys present in ``raw``; values come back in their stored form."""
    values: dict[str, str] = {}
    errors: dict[str, str] = {}
    if DIGEST_ENABLED_KEY in raw:
        enabled = parse_digest_enabled(raw[DIGEST_ENABLED_KEY])
        if enabled is None:
            errors[DIGEST_ENABLED_KEY] = DIGEST_ENABLED_ERROR
        else:
            values[DIGEST_ENABLED_KEY] = "1" if enabled else "0"
    if DIGEST_TIME_KEY in raw:
        value = raw[DIGEST_TIME_KEY]
        parsed = parse_digest_time(value)
        if parsed is not None:
            values[DIGEST_TIME_KEY] = parsed
        elif value is None or (isinstance(value, str) and not value.strip()):
            errors[DIGEST_TIME_KEY] = DIGEST_TIME_REQUIRED
        else:
            errors[DIGEST_TIME_KEY] = DIGEST_TIME_ERROR
    return values, errors


def validate_settings(
    raw: Mapping[str, object], rules: Mapping[str, SettingRule]
) -> tuple[dict[str, int], dict[str, str]]:
    """Validate a partial integer-settings update. Unknown keys are rejected.

    Digest keys are not integer settings; they are accepted here (not flagged as
    unknown) and validated by ``validate_digest_settings``.
    """
    values: dict[str, int] = {}
    errors: dict[str, str] = {}
    for key in raw:
        if key not in rules and key not in DIGEST_SETTING_KEYS:
            errors[key] = "不支援的設定項目"
    for key, rule in rules.items():
        if key not in raw:
            continue
        parsed = _parse_int(raw, key, errors)
        if key in errors:
            reason = TOO_LARGE if errors[key] == TOO_LARGE else "必須是整數"
            errors[key] = f"{rule.label}{reason}"
            continue
        if parsed is None:
            errors[key] = f"請填寫{rule.label}"
            continue
        if not rule.minimum <= parsed <= rule.maximum:
            errors[key] = f"{rule.label}須介於 {rule.minimum} 到 {rule.maximum}"
            continue
        values[key] = parsed
    return values, errors
