"""Claim identifiers, the m count and the claim registration CLI (ADR-0030 D-1, D-2, D-6).

Pure functions (ADR-0027 D-10 points 2 and 4):

* :func:`claim_id` -- the R-113 key
  ``{scope_kind}|h{h}|{rules_version}|{definition_version}|{kind}``;
* :func:`count_m` -- m, the number of registry rows with ``counts_toward_m = 1``;
* :func:`m_eff` -- ``max(m, M_EFF_FLOOR)`` with the floor taken from the claim's
  registered definition (pre-registration §4.4: 8 in v1).

The operator CLI ``python -m app.forecast.claims register`` (ADR-0030 D-1
point 3) registers one forward claim of the core scope in
``forecast_claim_registry``, through ``ForecastStore.register_claim`` -- the
store derives ``claim_id``, the hashes, ``definition_json`` and
``registered_at``, and refuses a replacement that breaks the chain rule
(supplement 3 (revised) point 6). The CLI supplies:

* the rule set, its bytes and the definition from ``app.forecast.definitions``
  (``--rules-version``, ``--definition-version``; the horizon is the
  registered rule set's), so only a published, checked version can be
  registered;
* ``--frozen-commit``, ``--prereg-doc`` (the pre-registration file; its bytes
  are ``prereg_doc_blob``), ``--review-refs``: required, non-blank;
* ``--replaces-claim-id`` with its required ``--replace-reason`` (D-1 point 2);
* ``--provisional-results-seen 0|1``: required, the operator states it.

Before registering it runs the CG-2 banned phrase check (D-6:
``definitions.registration_phrase_scan``, NFKC with whitespace removed, over
every string value of the rule set and the definition) and prints its result;
a hit refuses the registration. It prints the ``claim_id`` and
``registered_at`` that D-1 point 2 has the operator record in ``work/``.

Paths: the CLI refuses the production database (:func:`production_path_refusal`;
the file named ``stock-desk.db``, any file in the production data folder or the
one ``STOCK_DESK_DB_PATH`` names -- read for comparison only -- the same rule as
the read-only probes) and a file that does not exist; only a test or an
explicitly named non-production ledger can be registered into. How production
registration opens is the CG-2 registration PR's decision.

Exit codes: 0 registered, 2 usage (argparse), 3 refused (nothing written),
4 path refused (nothing opened).

``store.py`` imports this module for :func:`claim_id` and this module imports
the store for the CLI: both use the other's names only at call time (module
imports), so either can be imported first.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final, Literal, get_args

from app.dirdef.definition import DEFINITION_VERSION_PATTERN, DirectionDefinition, Horizon
from app.dirdef.rules import rules_logic_sha256
from app.forecast import definitions
from app.forecast import store as ledger
from app.forecast.canonical import APP_ROOT, canonical_timestamp

#: ADR-0025 D-2 point 1 scopes; v1 registers market, sector_main and symbol.
ScopeKind = Literal["market", "sector_main", "sector_sub", "theme", "symbol"]
ClaimKind = Literal["forward", "replay"]

CLAIM_ID_SEPARATOR: Final = "|"

_DEFINITION_VERSION: Final = re.compile(DEFINITION_VERSION_PATTERN)


def claim_id(
    *,
    scope_kind: ScopeKind,
    horizon: Horizon,
    rules_version: str,
    definition_version: str,
    kind: ClaimKind,
) -> str:
    """The claim key of D-10 point 2; every part is validated, none may hold the separator."""
    if scope_kind not in get_args(ScopeKind):
        raise ValueError(f"unknown scope_kind {scope_kind!r}")
    if isinstance(horizon, bool) or horizon not in get_args(Horizon):
        raise ValueError(f"unknown horizon {horizon!r}")
    if kind not in get_args(ClaimKind):
        raise ValueError(f"unknown claim kind {kind!r}")
    if not isinstance(rules_version, str) or not rules_version.strip():
        raise ValueError("rules_version must be a non-empty string")
    if rules_version != rules_version.strip() or CLAIM_ID_SEPARATOR in rules_version:
        raise ValueError("rules_version may not hold the separator or surrounding spaces")
    if not isinstance(definition_version, str) or not _DEFINITION_VERSION.fullmatch(
        definition_version
    ):
        raise ValueError("definition_version must be dirdef-vMAJOR.MINOR")
    return CLAIM_ID_SEPARATOR.join(
        (scope_kind, f"h{horizon}", rules_version, definition_version, kind)
    )


def count_m(counts_toward_m: Iterable[int]) -> int:
    """m: how many of the registry's ``counts_toward_m`` values are 1 (each must be 0 or 1)."""
    m = 0
    for value in counts_toward_m:
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
            raise ValueError(f"counts_toward_m must be 0 or 1, got {value!r}")
        m += value
    return m


def m_eff(m: int, *, definition: DirectionDefinition) -> int:
    """``max(m, definition.M_EFF_FLOOR)`` for a non-negative ``m``."""
    if isinstance(m, bool) or not isinstance(m, int) or m < 0:
        raise ValueError(f"m must be a non-negative int, got {m!r}")
    return max(m, definition.M_EFF_FLOOR)


# --- the registration CLI ---------------------------------------------------------------------

EXIT_OK: Final = 0
EXIT_REFUSED: Final = 3
EXIT_PATH_REFUSED: Final = 4

#: The production database: its file name and the variable that can name it
#: (``app.data.cache``; read here for the comparison only, never to open it).
PRODUCTION_DB_NAME: Final = "stock-desk.db"
DB_PATH_ENV_VAR: Final = "STOCK_DESK_DB_PATH"
#: The backend directory whose ``data/`` folder holds the production database.
BACKEND_DIR: Final = APP_ROOT.parent


class RegistrationRefused(Exception):
    """The registration was refused before anything was written."""


def _same_file(a: Path, b: Path) -> bool:
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except OSError:
        pass
    return a.resolve() == b.resolve()


def production_path_refusal(
    db_path: Path, *, backend_dir: Path, cwd: Path, env: Mapping[str, str]
) -> str | None:
    """Why ``db_path`` must not be registered into, or ``None``; the text echoes no value.

    Refused: a file named ``stock-desk.db`` anywhere; the production database
    (``<backend>/data/stock-desk.db``, ``./data/stock-desk.db`` from ``cwd``,
    the file ``STOCK_DESK_DB_PATH`` names); any file in one of their folders.
    """
    candidates = [
        backend_dir / "data" / PRODUCTION_DB_NAME,
        cwd / "data" / PRODUCTION_DB_NAME,
    ]
    named = env.get(DB_PATH_ENV_VAR)
    if named:
        candidates.append(cwd / named)
    db_path = cwd / db_path  # an absolute db_path stays as it is
    if db_path.name == PRODUCTION_DB_NAME:
        return "refused: --db is named like the production database"
    if any(_same_file(db_path, candidate) for candidate in candidates):
        return "refused: --db is the production database"
    folder = db_path.resolve().parent
    if any(folder == candidate.resolve().parent for candidate in candidates):
        return "refused: --db is in the production data folder"
    return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.forecast.claims",
        description="Register a forward claim of the forecast ledger core (ADR-0030 D-1).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register", help="register one forward claim")
    register.add_argument("--db", required=True, help="a non-production ledger file")
    register.add_argument("--rules-version", required=True, help="a published rule set")
    register.add_argument("--definition-version", required=True, help="a published dirdef")
    register.add_argument("--frozen-commit", required=True, help="the frozen commit")
    register.add_argument(
        "--prereg-doc", required=True, help="the pre-registration file (its bytes are stored)"
    )
    register.add_argument("--review-refs", required=True, help="risk and qa review records")
    register.add_argument("--replaces-claim-id", default=None, help="the claim it replaces")
    register.add_argument("--replace-reason", default=None, help="required when replacing")
    register.add_argument(
        "--provisional-results-seen",
        required=True,
        choices=("0", "1"),
        help="1 when any provisional comparison was seen before registering (D-1 point 2)",
    )
    return parser


def _phrase_scan_lines(scan: definitions.PhraseScan) -> list[str]:
    lines = [
        "banned phrase scan (NFKC, whitespace and zero-width removed):"
        f" rules {scan.rules_strings} strings, definition {scan.definition_strings} strings,"
        f" {scan.phrases} phrases, hits {len(scan.hits)}"
    ]
    lines += [f"  hit {hit}" for hit in scan.hits]
    return lines


def register(
    store: ledger.ForecastStore,
    *,
    rules_version: str,
    definition_version: str,
    frozen_commit: str,
    prereg_doc_path: str,
    prereg_doc_blob: bytes,
    review_refs: str,
    replaces_claim_id: str | None,
    replace_reason: str | None,
    provisional_results_seen: bool,
    out: list[str],
) -> ledger.ClaimRow:
    """Register one forward claim through the store; ``RegistrationRefused`` writes nothing.

    The rule set, its bytes and the definition come from
    ``app.forecast.definitions``; the banned phrase scan runs first and its
    result lines are appended to ``out``.
    """
    try:
        definition = definitions.get_definition(definition_version)
        ruleset = definitions.get_ruleset(rules_version)
        entry = definitions.get_ruleset_entry(rules_version)
        rules_bytes = definitions.get_rules_bytes(rules_version)
    except (definitions.UnpublishedVersionError, definitions.PublishedVersionRejectedError) as exc:
        raise RegistrationRefused(f"{type(exc).__name__}: {exc}") from None
    scan = definitions.registration_phrase_scan(ruleset, definition)
    out.extend(_phrase_scan_lines(scan))
    if scan.hits:
        raise RegistrationRefused("a banned phrase is in the rule set or the definition")
    try:
        new_id = store.register_claim(
            horizon=entry.horizon,
            rules_version=rules_version,
            rules_bytes=rules_bytes,
            rules_logic_sha256=rules_logic_sha256(ruleset),
            definition=definition,
            frozen_commit=frozen_commit,
            prereg_doc_path=prereg_doc_path,
            prereg_doc_blob=prereg_doc_blob,
            review_refs=review_refs,
            replaces_claim_id=replaces_claim_id,
            replace_reason=replace_reason,
            provisional_results_seen=provisional_results_seen,
        )
    except (ValueError, sqlite3.Error) as exc:
        raise RegistrationRefused(f"{type(exc).__name__}: {exc}") from None
    row = store.claim(new_id)
    if row is None:  # pragma: no cover - the store just inserted it
        raise ledger.LedgerInconsistentError("the registered claim cannot be read back")
    return row


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    backend_dir: Path = BACKEND_DIR,
    clock: ledger.Clock | None = None,
) -> int:
    """The CLI; returns the exit code (module docstring).

    ``env``, ``cwd``, ``backend_dir`` and ``clock`` are for tests; the defaults
    are the process environment, its working directory, this checkout's backend
    and the store's system clock.
    """
    args = _parser().parse_args(argv)
    db_path = Path(args.db)
    reason = production_path_refusal(
        db_path,
        backend_dir=backend_dir,
        cwd=Path.cwd() if cwd is None else cwd,
        env=os.environ if env is None else env,
    )
    if reason is None and not db_path.is_file():
        reason = "refused: --db is not an existing ledger file"
    if reason is not None:
        print(reason, file=sys.stderr)
        return EXIT_PATH_REFUSED
    out: list[str] = []
    try:
        try:
            prereg_blob = Path(args.prereg_doc).read_bytes()
        except OSError as exc:
            raise RegistrationRefused(
                f"--prereg-doc cannot be read ({type(exc).__name__})"
            ) from None
        row = register(
            ledger.ForecastStore(db_path, clock=clock or ledger.system_clock),
            rules_version=args.rules_version,
            definition_version=args.definition_version,
            frozen_commit=args.frozen_commit,
            prereg_doc_path=args.prereg_doc,
            prereg_doc_blob=prereg_blob,
            review_refs=args.review_refs,
            replaces_claim_id=args.replaces_claim_id,
            replace_reason=args.replace_reason,
            provisional_results_seen=args.provisional_results_seen == "1",
            out=out,
        )
    except RegistrationRefused as refused:
        if out:
            print("\n".join(out))
        print(f"refused: {refused}", file=sys.stderr)
        return EXIT_REFUSED
    out.append(f"registered claim_id={row.claim_id}")
    out.append(f"registered_at={canonical_timestamp(row.registered_at)}")
    out.append(
        "record claim_id and registered_at in work/ with a commit today (ADR-0030 D-1 point 2)"
    )
    print("\n".join(out))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
