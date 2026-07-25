"""Rule-based, explainable position advice (M3).

Three separable pieces:

* ``rules/default.yaml`` + ``loader`` -- the rule set is *data*, not code, so a
  reviewer can read every rule, its evidence, its counter-argument and its
  invalidation condition without reading Python.
* ``limits`` -- the risk budget (position/sector/gross caps, ATR-derived
  per-trade loss, fractional Kelly). A cap it cannot evaluate reports
  ``not_evaluable``; it never pretends to have checked something.
* ``engine`` -- evaluates the rules against a flat context built from the
  signal layer, aggregates matched rules into one action, and renders an advice
  card that always lists the rules it fired, the opposing view, and the caps it
  was measured against.

Red lines honoured throughout: no target price anywhere, no guarantee-flavoured
wording (the loader rejects it), "insufficient data" instead of a guess, and an
``add`` that is never emitted while any risk cap is violated.
"""
