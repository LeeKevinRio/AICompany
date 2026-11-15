"""The one definition of snapshot bar normalisation and the ledger digests (ADR-0030 D-1, D-2, D-5).

Single definitions (ADR-0030 K-6), all pure apart from :func:`code_digest`,
which reads the source files it digests:

* :func:`canonical_bars` -- a snapshot's bars in their one stored form
  (D-5 point 1: ``session_date``, OHLCV, ``source``, ``as_of``, ``fetched_at``
  per bar, nothing else);
* :func:`bars_json` -- the stored text of those bars (``forecast_input_series.bars_json``);
* :func:`content_sha256` -- the snapshot's content hash, sha256 of :func:`bars_json`
  (``forecast_input_series.content_sha256`` and ``forecast_record.input_series_sha256``);
* :func:`record_content_hash` -- ``forecast_record.content_hash`` over every
  column except :data:`RECORD_HASH_EXCLUDED_COLUMNS` (D-2 point 4);
* :func:`code_digest` -- the normalised sha256 of the ``app/forecast``,
  ``app/outlook``, ``app/dirdef`` and ``app/data/session_calendar.py`` sources
  (D-2 point 1).

Normalisation, chosen so a value read back from the ledger hashes the same as
the value first written (``canonical_bars(json.loads(bars_json(b))) ==
canonical_bars(b)``):

* prices are exact decimals (the bar cache stores them as decimal text and
  ``PriceBar`` carries ``Decimal``): ``Decimal``, ``int`` or a decimal string,
  written as plain decimal text without exponent or trailing zeros
  (``"17000.50"`` and ``"17000.5"`` are one value; ``-0`` is ``"0"``); a
  ``float`` is refused, because its decimal value is ambiguous;
* ``volume`` is a non-negative ``int`` (``PriceBar.volume``);
* ``as_of`` / ``fetched_at`` are timezone-aware, written in UTC with
  microseconds (``2026-11-13T07:00:00.000000+00:00``); a naive one is refused;
* ``session_date`` is an ISO date; bars must be in strictly ascending
  ``session_date`` order, so a duplicated or shuffled snapshot is refused
  rather than silently reordered;
* key order of the input mappings does not matter; a missing or extra key is
  refused.

JSON text goes through :func:`app.dirdef.hashing.canonical_json` (sorted keys,
no whitespace, UTF-8), the normalisation the dirdef hashes already use.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Context, Decimal, InvalidOperation
from pathlib import Path
from typing import Final

from app.dirdef.hashing import canonical_json, canonical_sha256

#: The keys of one snapshot bar (D-5 point 1), no more and no fewer.
BAR_KEYS: Final[frozenset[str]] = frozenset(
    {
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "source",
        "as_of",
        "fetched_at",
    }
)
_PRICE_KEYS: Final = ("open", "high", "low", "close")
_STAMP_KEYS: Final = ("as_of", "fetched_at")

#: ``forecast_record`` columns outside ``content_hash`` (D-2 point 4), plus the hash itself.
RECORD_HASH_EXCLUDED_COLUMNS: Final[frozenset[str]] = frozenset(
    {"forecast_id", "run_id", "created_at", "late", "content_hash"}
)

#: ``app/`` directory of this checkout: the root :func:`code_digest` reads by default.
APP_ROOT: Final = Path(__file__).resolve().parent.parent

#: What ``code_digest`` covers, relative to the app root (D-2 point 1).
CODE_DIGEST_PACKAGES: Final = ("forecast", "outlook", "dirdef")
CODE_DIGEST_FILES: Final = ("data/session_calendar.py",)


class CanonicalFormError(ValueError):
    """A value has no canonical form; it is refused, never coerced."""


# --- Values ---------------------------------------------------------------------------


def canonical_price(value: object) -> str:
    """The canonical decimal text of a price (``Decimal``, ``int`` or decimal string)."""
    if isinstance(value, bool) or isinstance(value, float):
        raise CanonicalFormError("a price must be a Decimal, an int or a decimal string")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, str):
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise CanonicalFormError("a price string must be a decimal literal") from None
    else:
        raise CanonicalFormError("a price must be a Decimal, an int or a decimal string")
    if not number.is_finite():
        raise CanonicalFormError("a price must be finite")
    if number.is_zero():
        return "0"
    # A context as precise as the value itself, so trailing zeros are stripped
    # and nothing is ever rounded (the default context keeps only 28 digits).
    exact = Context(prec=max(len(number.as_tuple().digits), 1))
    return format(number.normalize(exact), "f")


def canonical_timestamp(value: object) -> str:
    """A timezone-aware ``datetime`` (or ISO text with an offset) as UTC ISO text."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise CanonicalFormError("a timestamp string must be ISO 8601") from None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise CanonicalFormError("a timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def canonical_date(value: object) -> str:
    """A ``date`` (not a ``datetime``) or an ISO date string, as ISO text."""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            raise CanonicalFormError("a date string must be ISO 8601 (YYYY-MM-DD)") from None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise CanonicalFormError("a session date must be a date")
    return value.isoformat()


def _volume(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CanonicalFormError("volume must be a non-negative int")
    return value


def _source(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise CanonicalFormError("source must be a non-blank string without surrounding spaces")
    return value


# --- Bars -----------------------------------------------------------------------------


def canonical_bar(bar: Mapping[str, object]) -> dict[str, object]:
    """One bar in its stored form; exactly the :data:`BAR_KEYS` keys."""
    keys = set(bar)
    if keys != BAR_KEYS:
        missing = sorted(BAR_KEYS - keys)
        extra = sorted(keys - BAR_KEYS)
        raise CanonicalFormError(f"bar keys differ: missing={missing} extra={extra}")
    out: dict[str, object] = {"session_date": canonical_date(bar["session_date"])}
    for key in _PRICE_KEYS:
        out[key] = canonical_price(bar[key])
    out["volume"] = _volume(bar["volume"])
    out["source"] = _source(bar["source"])
    for key in _STAMP_KEYS:
        out[key] = canonical_timestamp(bar[key])
    return out


def canonical_bars(bars: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Every bar in stored form, in strictly ascending ``session_date`` order; at least one."""
    out = [canonical_bar(bar) for bar in bars]
    if not out:
        raise CanonicalFormError("a snapshot holds at least one bar")
    dates = [str(bar["session_date"]) for bar in out]
    if any(later <= earlier for earlier, later in zip(dates, dates[1:], strict=False)):
        raise CanonicalFormError("bars must be in strictly ascending session_date order")
    return out


def bars_json(bars: Iterable[Mapping[str, object]]) -> str:
    """The stored text of a snapshot (``forecast_input_series.bars_json``)."""
    return canonical_json(canonical_bars(bars))


def content_sha256(bars: Iterable[Mapping[str, object]]) -> str:
    """The content hash of a snapshot: sha256 of :func:`bars_json` as UTF-8."""
    return hashlib.sha256(bars_json(bars).encode("utf-8")).hexdigest()


# --- Record -----------------------------------------------------------------------------


def record_content_hash(columns: Mapping[str, object]) -> str:
    """``forecast_record.content_hash`` of the stored column values (D-2 point 4).

    ``columns`` is the row as stored, keyed by column name; the
    :data:`RECORD_HASH_EXCLUDED_COLUMNS` are dropped and every other column is
    hashed as stored (JSON columns as their stored text).
    """
    covered = {
        key: value for key, value in columns.items() if key not in RECORD_HASH_EXCLUDED_COLUMNS
    }
    return canonical_sha256(covered)


# --- Code -------------------------------------------------------------------------------


def normalised_source(data: bytes) -> bytes:
    """Source bytes with every line ending (CRLF, CR) written as LF; nothing else changes."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def code_digest_files(app_root: Path = APP_ROOT) -> list[Path]:
    """The files :func:`code_digest` covers: ``*.py`` sources, sorted; missing parts raise."""
    files: list[Path] = []
    for package in CODE_DIGEST_PACKAGES:
        root = app_root / package
        if not root.is_dir():
            raise FileNotFoundError(f"code_digest package app/{package} is missing")
        files.extend(
            path
            for path in root.rglob("*.py")
            if path.is_file() and "__pycache__" not in path.relative_to(root).parts
        )
    for name in CODE_DIGEST_FILES:
        path = app_root / name
        if not path.is_file():
            raise FileNotFoundError(f"code_digest file app/{name} is missing")
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(app_root).as_posix())


def code_digest(app_root: Path = APP_ROOT) -> str:
    """The normalised sha256 of the covered sources (D-2 point 1; single definition).

    A manifest of ``[path, sha256]`` pairs -- the path relative to the app root
    as ``app/...`` in POSIX form, the hash over :func:`normalised_source` -- is
    hashed with :func:`app.dirdef.hashing.canonical_sha256`. So a changed byte,
    an added, removed or renamed file all change the digest, while a checkout
    with CRLF line endings gives the same digest as one with LF.
    """
    manifest = [
        [
            "app/" + path.relative_to(app_root).as_posix(),
            hashlib.sha256(normalised_source(path.read_bytes())).hexdigest(),
        ]
        for path in code_digest_files(app_root)
    ]
    return canonical_sha256(manifest)
