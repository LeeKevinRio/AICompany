"""Direction definitions and outlook rule sets (ADR-0027 D-1 ``app/dirdef/``, N-113).

A leaf package: standard library, ``pydantic`` and ``yaml``, plus its own
modules; it imports no ``app.*`` outside this package (B2D-4), and does no DB,
clock, environment or file IO. Rule files are read by
``app/forecast/definitions.py`` and handed to the loader here as bytes.
``app.forecast.*`` and ``app.outlook.*`` may import this package; no other
``app.*`` package may.

Modules:

* ``guard.py`` -- the model base that disables ``model_construct`` and
  ``model_copy(update=...)``;
* ``hashing.py`` -- the canonical JSON sha256 both logic hashes share;
* ``strings.py`` -- ``string_values``, the one string value enumeration in
  ``app/`` (rule set validator and ``app/forecast/definitions.py``; N-128);
* ``definition.py`` -- ``DirectionDefinition``, ``definition_logic_sha256`` and
  ``definition_sha256``;
* ``rules.py`` -- the outlook rule set models, ``OUTLOOK_RULE_FIELDS``,
  ``rules_logic_sha256`` and the rule set loader;
* ``registry.py`` -- the two published registries (only the versions
  registered after their freeze; ADR-0030 D-6 CG-2).

Constant values are not set by the type modules: a registered definition object
is a constant in ``registry.py`` or in a module of this package holding only
that constant, landed with its registration.
"""
