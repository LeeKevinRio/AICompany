"""The gate's process-start inputs (ADR-0012 D-8 read time, C-24, C-25, D-12).

:mod:`app.sectors.gate` reads no configuration, environment or file (C-24):
whatever it needs from outside the databases is read **here**, once when a
process starts, and handed in:

* ``ci_passed_commit`` of the deployed build -- the attestation's commit, but
  only when this process can confirm it is running that attested build
  (:func:`app.services.sector_attestation.verify`); otherwise ``None``, which
  the gate reads as NE-7 (fail closed);
* ``fee_verified_on`` -- ``CostModel.verified_on`` (D9); ``None`` is NE-3 (C-25);
* ``de5_verified_on`` -- ``twse_snapshot.CHANGE_SEMANTICS_VERIFIED_ON``; ``None``
  keeps ``de5_unverified`` in ``pit_gaps`` (NE-1, D-12).

The scheduler re-reads them at every judgement (it records ``running_commit``
on the statistics row); the API process reads them once and keeps them, so a
deploy switches both together only after a restart (ADR-0012 D-8 "部署期間的
預期行為").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.backtest.costs import CostModel
from app.data.providers.twse_snapshot import CHANGE_SEMANTICS_VERIFIED_ON
from app.services.sector_attestation import BACKEND_ROOT, AttestationCheck, GitProbe, verify


@dataclass(frozen=True)
class SectorGateRuntime:
    """What the gate needs besides database rows (all ``None`` = not verified)."""

    ci_passed_commit: str | None
    fee_verified_on: date | None
    de5_verified_on: date | None


def fee_verified_on(cost_model: CostModel) -> date | None:
    """``CostModel.verified_on`` as a date (NE-3 when ``None``)."""
    return date.fromisoformat(cost_model.verified_on) if cost_model.verified_on else None


def runtime_from_check(
    check: AttestationCheck,
    *,
    cost_model: CostModel | None = None,
    de5_verified_on: date | None = CHANGE_SEMANTICS_VERIFIED_ON,
) -> SectorGateRuntime:
    return SectorGateRuntime(
        ci_passed_commit=check.ci_passed_commit if check.ok else None,
        fee_verified_on=fee_verified_on(cost_model if cost_model is not None else CostModel()),
        de5_verified_on=de5_verified_on,
    )


def load_gate_runtime(
    root: Path = BACKEND_ROOT, *, git: GitProbe | None = None
) -> SectorGateRuntime:
    """Read the three inputs now (git, the attestation file, two code constants)."""
    return runtime_from_check(verify(root, git=git))
