"""Pick the one matched rule that speaks for a card's action.

A card can carry matched rules on both sides (an ``add`` from a bullish MA
stack next to two ``reduce`` rules from an overbought reading). A UI that
quotes "the" rule behind the call -- its invalidation text, say -- must quote
a rule that argues *for* the call. Taking the heaviest matched rule overall
does not: with ``uptrend_ma_stack`` (add 0.5), ``rsi_overbought`` (reduce 0.4)
and ``kd_high_level_weakening`` (reduce 0.35) the defensive side wins on its
summed weight, yet the heaviest single rule is the constructive one, and its
invalidation reads in the opposite direction to the call.

The selection here is the risk-compliance review's option C (2026-10-03):

1. only rules whose own ``action`` equals the requested action are eligible;
2. among those, the heaviest weight wins;
3. equal weights resolve to the earlier rule in rule-file order, which is the
   order ``matched_rules`` is emitted in.

There is no direction matching: the aggregated action is the heaviest action
inside the winning direction, so at least one matched rule always carries it.

Callers must only ask when the card's ``action`` equals its
``aggregated_action``. When a gate overrode the call (a defensive downgrade, a
cap blocking an ``add``), the card's action was not taken from the rules and
nothing should be quoted. That gate is the caller's: this function cannot see
it, and a matched ``hold`` rule (e.g. ``volume_spike_watch``) would still be
found for a downgraded ``hold``.

The frontend renders the card, so it carries its own copy of this rule; this
module is the backend reference both are tested against.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.advice.engine import MatchedRule


def pick_rule_for_action(matched_rules: Iterable[MatchedRule], action: str) -> MatchedRule | None:
    """The heaviest matched rule proposing ``action``; earliest wins a tie.

    Returns ``None`` when no matched rule proposes ``action``. The input is
    read in order and never mutated; the returned entry is one of its items.
    """
    picked: MatchedRule | None = None
    for rule in matched_rules:
        if rule["action"] != action:
            continue
        # Strictly heavier only, so an equal weight keeps the earlier rule.
        if picked is None or rule["weight"] > picked["weight"]:
            picked = rule
    return picked


__all__ = ["pick_rule_for_action"]
