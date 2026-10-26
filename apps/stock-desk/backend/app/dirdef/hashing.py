"""Canonical sha256 of a JSON-able payload (ADR-0027 D-10 point 1, "normalised sha256").

Both logic hashes go through :func:`canonical_sha256`, so they share one
normalisation: keys sorted, no insignificant whitespace, UTF-8 without ASCII
escaping, and NaN or infinity refused rather than written as non-JSON tokens.
Floats are written by ``json`` as their shortest round-trip repr, so the same
double always gives the same text.
"""

from __future__ import annotations

import hashlib
import json


def canonical_json(payload: object) -> str:
    """The one canonical text of ``payload``."""
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_sha256(payload: object) -> str:
    """Lower-case hex sha256 of :func:`canonical_json` encoded as UTF-8."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
