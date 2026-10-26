"""The single string value enumeration (ADR-0027 D-1 ``app/dirdef/`` (3), N-128).

:func:`string_values` lists every string value of an object by walking its
type's field definitions recursively -- never a hand-written list of names --
so a field added to a model is scanned without anyone remembering to add it:

* a ``str`` is itself;
* a pydantic model: each field of ``type(value).model_fields``, in definition
  order;
* a dataclass instance: each of ``dataclasses.fields(value)``, in order;
* a ``list`` or ``tuple``: each element; a ``dict``: each **value**;
* ``None``, ``bool``, ``int``, ``float`` and date/time values hold no string.

Not enumerated, as ADR-0027 FL-78 discloses for (h) and (l): dict keys and the
members of a ``set`` or ``frozenset``. Any other type raises ``TypeError``
(fail-closed: a value this function cannot read is not silently passed).

The rule set validator (``app.dirdef.rules``) and ``app/forecast/definitions.py``
both enumerate through this function; ``app/`` holds no other definition of it.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

_NO_STRINGS = (bool, int, float, date, datetime, time, timedelta, set, frozenset)


def string_values(value: object) -> tuple[str, ...]:
    """Every string value reachable from ``value``, depth first, in field order."""
    found: list[str] = []
    _collect(value, found)
    return tuple(found)


def _collect(value: object, found: list[str]) -> None:
    if isinstance(value, str):
        found.append(value)
    elif value is None or isinstance(value, _NO_STRINGS):
        return
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            _collect(getattr(value, name), found)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            _collect(getattr(value, field.name), found)
    elif isinstance(value, list | tuple):
        for item in value:
            _collect(item, found)
    elif isinstance(value, dict):
        for item in value.values():
            _collect(item, found)
    else:
        raise TypeError(f"cannot enumerate the string values of a {type(value).__name__}")
