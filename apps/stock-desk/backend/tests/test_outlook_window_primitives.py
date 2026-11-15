"""The window primitives in ``app/outlook/volatility.py`` (freeze pack 2.2, 2.4).

* ``usable``: a finite float above zero, nothing else (int, Decimal, bool, NaN,
  inf, 0, negatives are not);
* ``log_return(a, b)`` is ``math.log(a / b)`` -- the division first -- when both
  are usable, else ``None``;
* ``window_log_returns`` / ``sigma_at``: position k is ``r_k`` (lag k over lag
  k + 1); a missing older bar or an unusable close makes that position ``None``,
  never filled from another day; sigma_d is judged over exactly
  ``SIGMA_WINDOW`` positions.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from app.outlook.volatility import log_return, sigma_at, usable, window_log_returns
from tests.dirdef_helpers import dirdef_v1_0 as definition


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.0, True),
        (1e-300, True),
        (0.0, False),
        (-1.0, False),
        (math.nan, False),
        (math.inf, False),
        (1, False),
        (Decimal("1"), False),
        (True, False),
        (None, False),
    ],
)
def test_usable(value: object, expected: bool) -> None:
    assert usable(value) is expected


def test_log_return_divides_first() -> None:
    a, b = 10408.107741923882, 9900.498337491681
    assert log_return(a, b) == math.log(a / b)
    assert log_return(b, a) == math.log(b / a)


@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf, None, 1])
def test_log_return_is_none_when_either_close_is_unusable(bad: object) -> None:
    assert log_return(bad, 100.0) is None
    assert log_return(100.0, bad) is None


def test_window_positions_and_missing_older_bars() -> None:
    closes = [104.0, 103.0, 0.0, 101.0, 100.0]  # by lag; lag 2 unusable
    returns = window_log_returns(closes, 0, 6)
    assert returns[0] == math.log(104.0 / 103.0)
    assert returns[1] is None and returns[2] is None  # both ends of lag 2
    assert returns[3] == math.log(101.0 / 100.0)
    assert returns[4] is None and returns[5] is None  # lags 5, 6 do not exist


def test_sigma_at_uses_exactly_the_sigma_window() -> None:
    definition_ = definition()
    closes = [100.0 * math.exp(0.01 * (k % 2)) for k in range(200)]
    at_0 = sigma_at(closes, 0, definition=definition_)
    assert at_0.valid_returns == definition_.SIGMA_WINDOW == 60
    # Starting at lag 150 only 49 positions exist: E-VOL-SHORT, nothing filled in.
    late = sigma_at(closes, 150, definition=definition_)
    assert late.valid_returns == 49 and late.missing_code == "E-VOL-SHORT"
