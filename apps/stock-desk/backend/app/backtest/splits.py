"""Walk-forward splitting: rolling train/test windows, in-sample vs out-of-sample.

Backtest-protocol rule 3 forbids a single train/test cut; parameters must be
chosen on rolling in-sample windows and judged only on the following, untouched
out-of-sample windows. This module produces those windows as index ranges over
an ordered sequence (the caller maps indices to dates/bars).

Guarantees, asserted by tests:

* Within a fold, the test window comes strictly *after* the train window (no
  overlap, no peeking).
* Successive test windows do not overlap (each out-of-sample bar is scored once).
* Test indices are never handed to any parameter-selection step -- that is the
  caller's responsibility, but the split makes the boundary explicit and
  machine-checkable via :attr:`WalkForwardFold.test_index`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardFold:
    """One rolling fold: an in-sample train range and an out-of-sample test range.

    Ranges are half-open ``[start, stop)`` index bounds into the ordered
    sequence. ``train_index`` / ``test_index`` expose the concrete indices so a
    test can assert the two never intersect.
    """

    fold: int
    train_start: int
    train_stop: int
    test_start: int
    test_stop: int

    @property
    def train_index(self) -> range:
        """In-sample indices (parameters may be fit here)."""
        return range(self.train_start, self.train_stop)

    @property
    def test_index(self) -> range:
        """Out-of-sample indices (never used for any parameter choice)."""
        return range(self.test_start, self.test_stop)


def walk_forward_splits(
    n: int,
    *,
    train_size: int,
    test_size: int,
    step: int | None = None,
    expanding: bool = False,
) -> list[WalkForwardFold]:
    """Generate rolling walk-forward folds over ``n`` ordered observations.

    * ``train_size`` -- length of each in-sample window (the initial window when
      ``expanding``).
    * ``test_size`` -- length of each out-of-sample window immediately after it.
    * ``step`` -- how far the window origin advances each fold; defaults to
      ``test_size`` so out-of-sample windows tile without overlap.
    * ``expanding`` -- if ``True`` the train window grows from a fixed start
      (anchored) instead of sliding a fixed-width window.

    Raises ``ValueError`` on non-positive sizes. Returns an empty list if there
    is not enough data for even one train+test fold.
    """
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must be positive")
    advance = test_size if step is None else step
    if advance <= 0:
        raise ValueError("step must be positive")

    folds: list[WalkForwardFold] = []
    origin = 0
    fold = 0
    while True:
        train_start = 0 if expanding else origin
        train_stop = origin + train_size
        test_start = train_stop
        test_stop = test_start + test_size
        if test_stop > n:
            break
        folds.append(
            WalkForwardFold(
                fold=fold,
                train_start=train_start,
                train_stop=train_stop,
                test_start=test_start,
                test_stop=test_stop,
            )
        )
        origin += advance
        fold += 1
    return folds
