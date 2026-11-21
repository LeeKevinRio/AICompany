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

Paths: ``register`` refuses the production database (:func:`production_path_refusal`;
the file named ``stock-desk.db``, any file in the production data folder or the
one ``STOCK_DESK_DB_PATH`` names -- read for comparison only -- the same rule as
the read-only probes) and a file that does not exist; only a test or an
explicitly named non-production ledger can be written by it.

The production database has one way in: ``python -m app.forecast.claims
bootstrap --production`` (ADR-0030 supplement 4 point 2, supplement 7 and its
addenda). Before any store exists it checks the target (``<backend>`` from this
module's location; ``resolve(strict=True)`` equal to
``<backend>/data/stock-desk.db``, a regular file), that neither the environment
nor the app's ``.env`` sets ``STOCK_DESK_DB_PATH`` (key only), the typed
``--provisional-results-seen`` (``0`` or ``1``, no default), the h3-then-h5
rule sets, the repo-relative ``--prereg-doc-path`` and the sha256 of its git
blob at ``--frozen-commit``, and the banned phrase scan. Then
``ForecastStore.bootstrap`` creates the ledger objects and both claim rows in
one transaction, and a read-only post-commit check follows. It opens no SQLite
connection itself and prints fixed text, counts, hashes, the commit and times.

Exit codes: 0 done (for ``bootstrap``: committed and checked), 2 usage
(argparse), 3 refused (nothing written), 4 path refused (``register``: nothing
opened; ``bootstrap``: a supplement 4 point 2 condition or ledger objects found
in the transaction, nothing written), 5 ``bootstrap`` committed but the
post-commit check or the output failed (fixed sentence only; do not retry).

``store.py`` imports this module for :func:`claim_id` and this module imports
the store for the CLI: both use the other's names only at call time (module
imports), so either can be imported first.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final, Literal, get_args

from app.dirdef.definition import DEFINITION_VERSION_PATTERN, DirectionDefinition, Horizon
from app.dirdef.rules import rules_logic_sha256
from app.forecast import definitions
from app.forecast import store as ledger
from app.forecast.canonical import APP_ROOT, canonical_timestamp
from app.forecast.schema import SchemaNotEmptyError

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
    _add_bootstrap_parser(commands)
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


# --- bootstrap --production (ADR-0030 supplement 4 points 2-3, supplement 7, addendum) -------

BOOTSTRAP_COMMAND: Final = "bootstrap"
#: The post-commit check did not hold (supplement 7 point 5): no retry.
EXIT_POST_COMMIT_CHECK_FAILED: Final = 5
#: The D-1 point 1 horizons, in the order the two claims must be given.
BOOTSTRAP_HORIZONS: Final = (3, 5)
#: A line of an ``.env`` file that sets ``STOCK_DESK_DB_PATH``; only the key is looked for.
#: An ``export`` prefix (any case, then whitespace) is allowed and the key matches in any case:
#: uv loads ``export KEY=`` lines, and Windows environment names ignore case. The pattern and
#: flags equal ``ENV_KEY_PATTERN`` of ``scripts/cg2_register.py`` (a test keeps them equal).
_ENV_FILE_KEY: Final = re.compile(rf"^\s*(?:export\s+)?{DB_PATH_ENV_VAR}\s*=", re.IGNORECASE)
_COMMIT: Final = re.compile(r"^[0-9a-f]{40}$")
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_DRIVE: Final = re.compile(r"^[A-Za-z]:")

#: Fixed sentences: no path, value or identifier is ever printed (supplement 4 point 4).
POST_COMMIT_CHECK_FAILED: Final = (
    "STOP: bootstrap committed but the post-commit check failed; do not retry"
)
#: Exit 4: the supplement 4 point 2 conditions and the transaction's SchemaNotEmptyError.
BOOTSTRAP_PATH_REFUSALS: Final = {
    "db_missing": "refused: the production database is not at its default location",
    "db_not_default": "refused: the production database resolves to another location",
    "db_not_regular": "refused: the production database is not a regular file",
    "env_db_path": "refused: STOCK_DESK_DB_PATH is set in the environment",
    "env_file_db_path": "refused: STOCK_DESK_DB_PATH is set in the .env file of the app",
    "not_empty": "refused: the production database already holds forecast_ or plan_ objects",
    "horizons": "refused: the two claims must be the h3 then the h5 rule set",
    "replaces": "refused: a bootstrap claim replaces no claim",
}
#: Exit 3: every other refusal before or by the store.
BOOTSTRAP_REFUSALS: Final = {
    "provisional": "refused: --provisional-results-seen must be typed as 0 or 1",
    "frozen_commit": "refused: --frozen-commit must be 40 lower-case hex digits",
    "prereg_path": "refused: --prereg-doc-path is not a repo-relative path",
    "prereg_sha256": "refused: --prereg-doc-sha256 must be 64 lower-case hex digits",
    "prereg_blob": "refused: the pre-registration blob cannot be read at --frozen-commit",
    "prereg_mismatch": "refused: the pre-registration blob does not match --prereg-doc-sha256",
    "review_refs": "refused: --review-refs must be repo-relative paths separated by spaces",
    "unpublished": "refused: a rule set or the definition is not published or is rejected",
    "phrases": "refused: a banned phrase is in a rule set or the definition",
    "store": "refused: the store refused the registration; nothing was written",
}


class BootstrapRefused(Exception):
    """``bootstrap --production`` refused before the store exists; ``key`` names the sentence."""

    def __init__(self, key: str, exit_code: int) -> None:
        super().__init__(key)
        self.key = key
        self.exit_code = exit_code


def _add_bootstrap_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    bootstrap = commands.add_parser(
        BOOTSTRAP_COMMAND,
        help="create the ledger and register the two core claims in the production database",
    )
    bootstrap.add_argument(
        "--production", action="store_true", required=True, help="the production database"
    )
    bootstrap.add_argument(
        "--rules-version",
        action="append",
        required=True,
        help="a published rule set; given twice, h3 then h5",
    )
    bootstrap.add_argument("--definition-version", required=True, help="a published dirdef")
    bootstrap.add_argument("--frozen-commit", required=True, help="the frozen commit (40 hex)")
    bootstrap.add_argument(
        "--prereg-doc-path", required=True, help="repo-relative path of the pre-registration"
    )
    bootstrap.add_argument(
        "--prereg-doc-sha256",
        required=True,
        help="sha256 of the pre-registration blob at --frozen-commit",
    )
    bootstrap.add_argument(
        "--review-refs", required=True, help="repo-relative review records, space separated"
    )
    bootstrap.add_argument(
        "--replaces-claim-id", default=None, help="refused when given: bootstrap replaces nothing"
    )
    bootstrap.add_argument(
        "--provisional-results-seen",
        required=True,
        help="typed by the operator: 0 or 1 (no default; supplement 6 addendum point 7)",
    )


def repo_relative_path_ok(path: str) -> bool:
    """Supplement 4 point 3: repo-root relative, ``/``-separated; nothing is converted.

    Refused: an empty string or surrounding spaces, a leading ``/``, a ``\\``,
    a drive letter, and any empty, ``.`` or ``..`` part.
    """
    if not isinstance(path, str) or not path or path != path.strip():
        return False
    if path.startswith("/") or "\\" in path or _DRIVE.match(path):
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def env_file_sets_db_path(env_file: Path) -> bool:
    """True when a line of ``env_file`` starts with ``STOCK_DESK_DB_PATH=``; no value is kept."""
    if not env_file.is_file():
        return False
    with open(env_file, encoding="utf-8-sig", errors="ignore") as handle:
        return any(_ENV_FILE_KEY.match(line) for line in handle)


def production_target(*, backend_dir: Path, env: Mapping[str, str]) -> Path:
    """The production database, checked before any store exists (supplement 7 addendum point 3).

    ``backend_dir`` is derived from this module's location (``BACKEND_DIR``;
    tests pass a stand-in), never from the working directory. Neither the
    environment nor ``<backend>/../.env`` may set ``STOCK_DESK_DB_PATH``; the
    file must exist (``resolve(strict=True)``), resolve to
    ``<backend>/data/stock-desk.db`` and be a regular file. Nothing is opened
    as a database and no file is created.
    """
    if DB_PATH_ENV_VAR in env:
        raise BootstrapRefused("env_db_path", EXIT_PATH_REFUSED)
    if env_file_sets_db_path(backend_dir.parent / ".env"):
        raise BootstrapRefused("env_file_db_path", EXIT_PATH_REFUSED)
    target = backend_dir / "data" / PRODUCTION_DB_NAME
    try:
        resolved = target.resolve(strict=True)
        expected = backend_dir.resolve(strict=True) / "data" / PRODUCTION_DB_NAME
        mode = resolved.stat().st_mode
    except OSError:
        raise BootstrapRefused("db_missing", EXIT_PATH_REFUSED) from None
    if resolved != expected:
        raise BootstrapRefused("db_not_default", EXIT_PATH_REFUSED)
    if not stat.S_ISREG(mode):
        raise BootstrapRefused("db_not_regular", EXIT_PATH_REFUSED)
    return resolved


def git_blob(backend_dir: Path, commit: str, path: str) -> bytes | None:
    """``git cat-file blob <commit>:<path>`` in the checkout of ``backend_dir``; else ``None``.

    Every ``GIT_*`` variable is removed from git's environment and replace refs
    are ignored (``--no-replace-objects``), so the blob is this checkout's
    object (supplement 7 addendum 2 point 7).
    """
    clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    try:
        done = subprocess.run(
            ["git", "--no-replace-objects", "cat-file", "blob", f"{commit}:{path}"],
            cwd=backend_dir,
            env=clean_env,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def bootstrap_claim_inputs(
    args: argparse.Namespace, *, backend_dir: Path
) -> tuple[list[ledger.ClaimInput], bool, list[str]]:
    """The two ``ClaimInput`` of ``args``, the typed value and the phrase scan lines.

    Every refusal here happens before the store exists (exit 3, or 4 for the
    supplement 4 point 2 conditions). ``provisional_results_seen`` is taken
    exactly as typed, ``0`` or ``1``: no default, no conversion. The
    pre-registration bytes are the git blob at ``--frozen-commit`` and must
    hash to ``--prereg-doc-sha256`` (supplement 4 point 3).
    """
    typed = args.provisional_results_seen
    if typed not in ("0", "1"):
        raise BootstrapRefused("provisional", EXIT_REFUSED)
    if args.replaces_claim_id is not None:
        raise BootstrapRefused("replaces", EXIT_PATH_REFUSED)
    if not _COMMIT.fullmatch(args.frozen_commit):
        raise BootstrapRefused("frozen_commit", EXIT_REFUSED)
    if not repo_relative_path_ok(args.prereg_doc_path):
        raise BootstrapRefused("prereg_path", EXIT_REFUSED)
    if not _SHA256.fullmatch(args.prereg_doc_sha256):
        raise BootstrapRefused("prereg_sha256", EXIT_REFUSED)
    if not all(repo_relative_path_ok(ref) for ref in args.review_refs.split(" ")):
        raise BootstrapRefused("review_refs", EXIT_REFUSED)
    try:
        definition = definitions.get_definition(args.definition_version)
        entries = [definitions.get_ruleset_entry(v) for v in args.rules_version]
    except (definitions.UnpublishedVersionError, definitions.PublishedVersionRejectedError):
        raise BootstrapRefused("unpublished", EXIT_REFUSED) from None
    if tuple(entry.horizon for entry in entries) != BOOTSTRAP_HORIZONS:
        raise BootstrapRefused("horizons", EXIT_PATH_REFUSED)
    blob = git_blob(backend_dir, args.frozen_commit, args.prereg_doc_path)
    if not blob:
        raise BootstrapRefused("prereg_blob", EXIT_REFUSED)
    if hashlib.sha256(blob).hexdigest() != args.prereg_doc_sha256:
        raise BootstrapRefused("prereg_mismatch", EXIT_REFUSED)
    lines: list[str] = []
    claims: list[ledger.ClaimInput] = []
    for version, entry in zip(args.rules_version, entries, strict=True):
        try:
            ruleset = definitions.get_ruleset(version)
            rules_bytes = definitions.get_rules_bytes(version)
        except (definitions.UnpublishedVersionError, definitions.PublishedVersionRejectedError):
            raise BootstrapRefused("unpublished", EXIT_REFUSED) from None
        scan = definitions.registration_phrase_scan(ruleset, definition)
        lines.append(
            f"banned_phrase_scan_h{entry.horizon}=hits {len(scan.hits)}"
            f" rules_strings {scan.rules_strings} definition_strings"
            f" {scan.definition_strings} phrases {scan.phrases}"
        )
        if scan.hits:
            raise BootstrapRefused("phrases", EXIT_REFUSED)
        claims.append(
            ledger.ClaimInput(
                horizon=entry.horizon,
                rules_version=version,
                rules_bytes=rules_bytes,
                rules_logic_sha256=rules_logic_sha256(ruleset),
                definition=definition,
                frozen_commit=args.frozen_commit,
                prereg_doc_path=args.prereg_doc_path,
                prereg_doc_blob=blob,
                review_refs=args.review_refs,
                replaces_claim_id=None,
                replace_reason=None,
                provisional_results_seen=typed == "1",
            )
        )
    return claims, typed == "1", lines


def post_commit_check(store: ledger.ForecastStore, ids: tuple[str, str], *, seen: bool) -> bool:
    """Supplement 7 point 5, read-only: the schema first, then the rows, the runs, the value."""
    if not store.ledger_schema_status().complete:
        return False
    if [row.claim_id for row in store.forward_claims()] != list(ids):
        return False
    if store.runs():
        return False
    try:
        values = store.provisional_results_seen()
    except ledger.LedgerInconsistentError:
        return False
    return values == [(claim, int(seen)) for claim in ids]


def bootstrap_main(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str],
    backend_dir: Path,
    clock: ledger.Clock | None,
) -> int:
    """``bootstrap --production``: checks, ``store.bootstrap``, the post-commit check, the output.

    Exit codes: 0 registered and checked; 3 refused (the input checks and any
    other ``ForecastStoreError``); 4 refused by a supplement 4 point 2
    condition or a ``SchemaNotEmptyError`` in the transaction; 5 committed but
    the post-commit check failed (no retry). 3 and 4 write nothing. Unexpected
    exceptions are not caught. The output holds fixed text, counts, hashes,
    the commit and times only -- no path and no identifier.
    """
    try:
        target = production_target(backend_dir=backend_dir, env=env)
        claims, seen, lines = bootstrap_claim_inputs(args, backend_dir=backend_dir)
    except BootstrapRefused as refused:
        sentences = {**BOOTSTRAP_PATH_REFUSALS, **BOOTSTRAP_REFUSALS}
        print(sentences[refused.key], file=sys.stderr)
        return refused.exit_code
    store = ledger.ForecastStore(target, clock=clock or ledger.system_clock)
    try:
        ids = store.bootstrap(claims=claims)
    except SchemaNotEmptyError:
        print(BOOTSTRAP_PATH_REFUSALS["not_empty"], file=sys.stderr)
        return EXIT_PATH_REFUSED
    except ledger.ForecastStoreError:
        print(BOOTSTRAP_REFUSALS["store"], file=sys.stderr)
        return EXIT_REFUSED
    # Committed: from here to the success output, any Exception is exit 5 with the
    # fixed sentence only (supplement 7 addendum 2 point 4); BaseException is not caught.
    try:
        if not post_commit_check(store, ids, seen=seen):
            raise LookupError("post-commit check")
        out = bootstrap_output(store, ids, args=args, seen=seen, lines=lines)
    except Exception:
        print(POST_COMMIT_CHECK_FAILED, file=sys.stderr)
        return EXIT_POST_COMMIT_CHECK_FAILED
    print("\n".join(out))
    return EXIT_OK


def bootstrap_output(
    store: ledger.ForecastStore,
    ids: tuple[str, str],
    *,
    args: argparse.Namespace,
    seen: bool,
    lines: list[str],
) -> list[str]:
    """The success lines: fixed text, counts, hashes, the commit and times (no path, no id)."""
    rows = {row.claim_id: row for row in store.forward_claims()}
    first = rows[ids[0]]
    out = [
        "bootstrap=ok",
        *lines,
        f"registered_rows={len(rows)}",
        f"frozen_commit={args.frozen_commit}",
        f"prereg_doc_sha256={args.prereg_doc_sha256}",
        f"definition_sha256={first.definition_sha256}",
        f"definition_logic_sha256={first.definition_logic_sha256}",
    ]
    for claim in ids:
        row = rows[claim]
        out.append(f"rules_sha256_h{row.horizon}={row.rules_sha256}")
        out.append(f"rules_logic_sha256_h{row.horizon}={row.rules_logic_sha256}")
        out.append(f"registered_at_h{row.horizon}={canonical_timestamp(row.registered_at)}")
    out.append(f"provisional_results_seen={int(seen)}")
    out.append("post_commit_check=ok")
    return out


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
    if args.command == BOOTSTRAP_COMMAND:
        return bootstrap_main(
            args, env=os.environ if env is None else env, backend_dir=backend_dir, clock=clock
        )
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
