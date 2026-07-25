"""Walk-forward split tests: non-overlap, ordering, out-of-sample isolation."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.backtest.splits import walk_forward_splits


def test_rolling_folds_shape() -> None:
    folds = walk_forward_splits(10, train_size=4, test_size=2)
    # origins 0,2,4 -> 3 folds; last would need index 12 > 10 so it stops.
    assert len(folds) == 3
    assert [(f.test_start, f.test_stop) for f in folds] == [(4, 6), (6, 8), (8, 10)]
    assert [(f.train_start, f.train_stop) for f in folds] == [(0, 4), (2, 6), (4, 8)]


def test_train_and_test_never_overlap_within_a_fold() -> None:
    for f in walk_forward_splits(20, train_size=6, test_size=3):
        assert set(f.train_index).isdisjoint(set(f.test_index))
        # Test always comes strictly after train (no peeking backward in time).
        assert min(f.test_index) >= max(f.train_index) + 1


def test_out_of_sample_windows_do_not_overlap() -> None:
    folds = walk_forward_splits(30, train_size=10, test_size=5)
    seen: set[int] = set()
    for f in folds:
        idx = set(f.test_index)
        assert seen.isdisjoint(idx), "each out-of-sample bar must be scored once"
        seen |= idx


def test_expanding_window_anchors_train_start() -> None:
    folds = walk_forward_splits(20, train_size=5, test_size=3, expanding=True)
    assert all(f.train_start == 0 for f in folds)
    # Train window grows each fold.
    assert folds[0].train_stop < folds[1].train_stop


def test_custom_step_controls_overlap() -> None:
    # step 1 with test_size 2 -> overlapping test windows on purpose.
    folds = walk_forward_splits(10, train_size=4, test_size=2, step=1)
    assert folds[0].test_start == 4
    assert folds[1].test_start == 5


def test_insufficient_data_returns_no_folds() -> None:
    assert walk_forward_splits(5, train_size=4, test_size=2) == []


def test_invalid_sizes_raise() -> None:
    with pytest.raises(ValueError):
        walk_forward_splits(10, train_size=0, test_size=2)
    with pytest.raises(ValueError):
        walk_forward_splits(10, train_size=4, test_size=0)
    with pytest.raises(ValueError):
        walk_forward_splits(10, train_size=4, test_size=2, step=0)


def test_parameter_selection_never_reads_its_own_or_any_future_test_window() -> None:
    """Protocol rule: a fold's parameters may not be informed by its test window.

    Simulates a tuning loop -- pick the best parameter on each fold's train
    window -- behind a spy recording every observation index the selection
    actually read, then asserts the honest invariant *per fold*:

        every index read for fold k  <  fold k's test_start

    Note what this deliberately does NOT assert: that training never touches any
    bar that was some *earlier* fold's test window. In a rolling walk-forward
    that overlap is correct -- once fold 0 has been scored, its test bars are in
    the past and are legitimate training data for fold 1. Forbidding that would
    describe a different (anchored-disjoint) scheme, not this one. The bug that
    matters is reading at or beyond the current fold's test_start, i.e. the
    future, which is what this test pins.
    """
    n = 40
    observations = [float(i) for i in range(n)]

    def select_parameter(train_index: range, read: Callable[[int], float]) -> int:
        # A stand-in optimiser: scores candidate params using train data only.
        best_param, best_score = 0, float("-inf")
        for param in (2, 3, 5):
            score = sum(read(i) for i in train_index) / param
            if score > best_score:
                best_param, best_score = param, score
        return best_param

    folds = walk_forward_splits(n, train_size=15, test_size=5)
    assert folds, "fixture must produce folds for this test to mean anything"

    for fold in folds:
        read_indices: set[int] = set()

        def read(i: int, _sink: set[int] = read_indices) -> float:
            _sink.add(i)
            return observations[i]

        select_parameter(fold.train_index, read)
        assert read_indices, "the spy must have observed the tuning reads"
        # Nothing at or beyond this fold's test_start may inform its parameters.
        leaked = {i for i in read_indices if i >= fold.test_start}
        assert not leaked, (
            f"fold {fold.fold} parameter selection read future indices "
            f"{sorted(leaked)} (test_start={fold.test_start}); look-ahead in tuning"
        )
        assert read_indices.isdisjoint(set(fold.test_index))
