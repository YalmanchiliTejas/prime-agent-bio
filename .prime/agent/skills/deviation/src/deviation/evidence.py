"""Typed claims and provenance for deviation investigations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class ClaimType(str, Enum):
    OBSERVED_FACT = "OBSERVED_FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    PROPOSED_ACTION = "PROPOSED_ACTION"


@dataclass(frozen=True)
class Provenance:
    source_system: str
    source_record_id: str
    timestamp: str
    evidence_ref: str

    def __post_init__(self) -> None:
        missing = [name for name, value in asdict(self).items() if not str(value).strip()]
        if missing:
            raise ValueError(f"Observed-fact provenance requires: {', '.join(missing)}")


@dataclass(frozen=True)
class Claim:
    claim_type: ClaimType
    statement: str
    provenance: Provenance | None = None
    evidence_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("Claim statement must not be empty")
        if self.claim_type is ClaimType.OBSERVED_FACT and self.provenance is None:
            raise ValueError("OBSERVED_FACT requires provenance")
        if self.claim_type is not ClaimType.OBSERVED_FACT and self.provenance is not None:
            raise ValueError("Only OBSERVED_FACT may carry fact provenance")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "claim_type": self.claim_type.value,
            "statement": self.statement,
            "evidence_refs": list(self.evidence_refs),
        }
        if self.provenance:
            result["provenance"] = asdict(self.provenance)
        if self.metadata:
            result["metadata"] = self.metadata
        return result


def observed_fact(
    statement: str,
    *,
    source_system: str,
    source_record_id: str,
    timestamp: str,
    evidence_ref: str,
    metadata: dict[str, Any] | None = None,
) -> Claim:
    return Claim(
        ClaimType.OBSERVED_FACT,
        statement,
        Provenance(source_system, source_record_id, timestamp, evidence_ref),
        (evidence_ref,),
        metadata,
    )


def inference(statement: str, *, evidence_refs: list[str] | None = None) -> Claim:
    return Claim(ClaimType.INFERENCE, statement, evidence_refs=tuple(evidence_refs or ()))


def hypothesis_claim(statement: str, *, evidence_refs: list[str] | None = None) -> Claim:
    return Claim(ClaimType.HYPOTHESIS, statement, evidence_refs=tuple(evidence_refs or ()))


def proposed_action(statement: str, *, evidence_refs: list[str] | None = None) -> Claim:
    return Claim(ClaimType.PROPOSED_ACTION, statement, evidence_refs=tuple(evidence_refs or ()))
