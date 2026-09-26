"""Durable case state and lifecycle controls for deviation investigations."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .evidence import Claim


class Stage(str, Enum):
    DETECTED = "DETECTED"
    INITIAL_REPORTING = "INITIAL_REPORTING"
    IMMEDIATE_ACTIONS_AND_CONTAINMENT = "IMMEDIATE_ACTIONS_AND_CONTAINMENT"
    PRELIMINARY_ASSESSMENT = "PRELIMINARY_ASSESSMENT"
    CLASSIFICATION = "CLASSIFICATION"
    FORMAL_INVESTIGATION = "FORMAL_INVESTIGATION"
    ROOT_CAUSE_ANALYSIS = "ROOT_CAUSE_ANALYSIS"
    EXTENSION_ASSESSMENT = "EXTENSION_ASSESSMENT"
    PRODUCT_IMPACT_ASSESSMENT = "PRODUCT_IMPACT_ASSESSMENT"
    CAPA_OR_CHANGE = "CAPA_OR_CHANGE"
    QA_AND_SPONSOR_REVIEW = "QA_AND_SPONSOR_REVIEW"
    EFFECTIVENESS_MONITORING = "EFFECTIVENESS_MONITORING"
    CLOSED = "CLOSED"


STAGE_SEQUENCE = tuple(Stage)


class Classification(str, Enum):
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class HypothesisStatus(str, Enum):
    OPEN = "OPEN"
    SUPPORTED = "SUPPORTED"
    WEAKENED = "WEAKENED"
    REJECTED = "REJECTED"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"


class ProductImpactStatus(str, Enum):
    NO_EVIDENCE_OF_IMPACT = "NO_EVIDENCE_OF_IMPACT"
    POTENTIAL_IMPACT = "POTENTIAL_IMPACT"
    CONFIRMED_IMPACT = "CONFIRMED_IMPACT"
    INCONCLUSIVE = "INCONCLUSIVE"


class CapaType(str, Enum):
    CORRECTION = "CORRECTION"
    CORRECTIVE_ACTION = "CORRECTIVE_ACTION"
    PREVENTIVE_ACTION = "PREVENTIVE_ACTION"


DEFAULT_CLASSIFICATION_POLICY = {
    "policy_id": "CONFIGURABLE_DEFAULT_V1",
    "source": "built-in fallback; replace with site/QMS/product/Quality Agreement criteria",
    "MINOR": "No apparent product-quality/CQA impact and limited scope.",
    "MAJOR": "Potential product-quality/CQA impact or meaningful GMP/process impact; formal investigation required.",
    "CRITICAL": "Potential direct safety, efficacy, sterility, identity, strength, purity, or serious data-integrity impact; immediate escalation required.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Claim):
        return value.to_dict()
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


@dataclass
class Hypothesis:
    hypothesis_id: str
    statement: str
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = HypothesisStatus.OPEN.value

    def validate(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("Hypothesis confidence must be between 0 and 1")
        HypothesisStatus(self.status)
        if self.status in {HypothesisStatus.SUPPORTED.value, HypothesisStatus.HUMAN_CONFIRMED.value}:
            if not self.evidence_for:
                raise ValueError("A supported hypothesis requires evidence_for")


@dataclass
class CAPA:
    capa_id: str
    action: str
    type: str
    linked_root_cause: str
    supporting_evidence: list[str]
    owner: str | None
    expected_effect: str
    verification_method: str
    effectiveness_criteria: str
    human_approval_required: bool = True
    status: str = "PROPOSED"

    def validate(self) -> None:
        CapaType(self.type)
        if not self.linked_root_cause.strip() or not self.supporting_evidence:
            raise ValueError("CAPA must link a root cause and supporting evidence")


@dataclass
class CaseState:
    case_id: str
    objective: str
    stage: str = Stage.DETECTED.value
    detected_at: str | None = None
    reported_at: str | None = None
    reporting_delay: str | None = None
    event_context: dict[str, Any] = field(
        default_factory=lambda: {
            "event_timestamp": None, "batch": None, "product": None, "site": None,
            "process_step": None, "equipment": [], "material_lots": [], "operator_personnel": [],
            "process_values": {}, "alarm_event": None, "observed_condition": None,
            "expected_condition": None, "source_record": None,
        }
    )
    immediate_actions: list[dict[str, Any]] = field(default_factory=list)
    containment_status: str = "NOT_ASSESSED"
    evidence_preserved: list[dict[str, Any]] = field(default_factory=list)
    preliminary_assessment: dict[str, Any] = field(
        default_factory=lambda: {
            "what_happened": None, "affected_process": None, "scope_signal": None,
            "potentially_affected_product_batches": [], "potential_cqa_impact": [],
            "potential_patient_or_product_quality_risk": None, "urgent_evidence_to_preserve": [],
        }
    )
    classification: str | None = None
    classification_rationale: str | None = None
    classification_evidence: list[str] = field(default_factory=list)
    policy_used: dict[str, Any] = field(default_factory=dict)
    risk_assessment: dict[str, Any] = field(
        default_factory=lambda: {
            "risk_question": None, "hazards": [], "severity": None, "probability": None,
            "detectability": None, "uncertainty": None, "risk_level": None,
            "risk_controls": [], "review_trigger": None, "method": None,
            "formality_rationale": None, "policy_used": None,
        }
    )
    observations: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    affected_entities: dict[str, list[str]] = field(
        default_factory=lambda: {
            "batches": [], "products": [], "equipment": [], "materials": [],
            "process_steps": [], "CPPs": [], "CQAs": [],
        }
    )
    extension_assessment: dict[str, Any] = field(
        default_factory=lambda: {
            "potentially_affected_batches": [], "potentially_affected_products": [],
            "extension_searches": [], "extension_conclusion": None,
        }
    )
    product_impact: dict[str, Any] = field(
        default_factory=lambda: {
            "impacted_cqas": [], "product_impact_evidence": [], "product_impact_status": None,
            "affected_cpp_excursions": [], "exposure_duration": None, "exposed_product": [],
            "downstream_steps": [], "qc_results": [], "stability_development_evidence": [],
            "additional_testing_proposed": [],
        }
    )
    open_questions: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    proposed_actions: list[dict[str, Any]] = field(default_factory=list)
    CAPAs: list[dict[str, Any]] = field(default_factory=list)
    effectiveness_monitoring: dict[str, Any] = field(
        default_factory=lambda: {
            "effectiveness_plan": None, "batches_to_monitor": [], "metrics": [],
            "observation_period": None, "recurrence_condition": None,
            "success_condition": None, "failure_condition": None, "status": "NOT_STARTED",
        }
    )
    sponsor_requirements: dict[str, Any] = field(
        default_factory=lambda: {
            "sponsor": None, "cdmo_site": None, "quality_agreement": None,
            "sponsor_notification_required": None, "notification_deadline": None,
            "sponsor_review_required": None, "required_approvers": [],
            "investigation_ownership": None, "CAPA_ownership": None,
            "batch_disposition_responsibility": None, "responsible_party": None,
        }
    )
    human_decisions: list[dict[str, Any]] = field(default_factory=list)
    worker_findings: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    revision: int = 0

    def validate(self) -> None:
        Stage(self.stage)
        if self.classification is not None:
            Classification(self.classification)
        for item in self.hypotheses:
            Hypothesis(**item).validate()
        for item in self.CAPAs:
            CAPA(**item).validate()
        for claim in self.observations:
            if claim.get("claim_type") == "OBSERVED_FACT":
                provenance = claim.get("provenance", {})
                required = {"source_system", "source_record_id", "timestamp", "evidence_ref"}
                if required - set(provenance) or any(not provenance.get(key) for key in required):
                    raise ValueError("Stored OBSERVED_FACT has incomplete provenance")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return _json_value(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaseState":
        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in data.items() if key in known})


class CaseStore:
    def __init__(self, root: str | Path | None = None) -> None:
        configured = os.environ.get("PRIME_DEVIATION_CASE_DIR")
        self.root = Path(root or configured or Path.cwd() / ".prime" / "deviation-cases")

    @staticmethod
    def _safe_id(case_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", case_id):
            raise ValueError("case_id must contain only letters, numbers, dot, underscore, or hyphen")
        return case_id

    def path(self, case_id: str) -> Path:
        return self.root / f"{self._safe_id(case_id)}.json"

    def create(self, case_id: str, objective: str) -> CaseState:
        path = self.path(case_id)
        if path.exists():
            raise FileExistsError(f"Deviation case already exists: {case_id}")
        case = CaseState(case_id=case_id, objective=objective)
        self.save(case)
        return case

    def load(self, case_id: str) -> CaseState:
        data = json.loads(self.path(case_id).read_text(encoding="utf-8"))
        case = CaseState.from_dict(data)
        case.validate()
        return case

    def save(self, case: CaseState) -> CaseState:
        self.root.mkdir(parents=True, exist_ok=True)
        case.updated_at = _now()
        case.revision += 1
        case.validate()
        path = self.path(case.case_id)
        temporary = path.with_suffix(f".json.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(case.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return case

    def update(self, case_id: str, mutation: Callable[[CaseState], None]) -> CaseState:
        case = self.load(case_id)
        mutation(case)
        return self.save(case)

    def list_cases(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(path.stem for path in self.root.glob("*.json"))


def create_case(case_id: str, objective: str, *, store: CaseStore | None = None) -> CaseState:
    return (store or CaseStore()).create(case_id, objective)


def set_detection_context(
    case_id: str,
    *,
    detected_at: str | None = None,
    reported_at: str | None = None,
    event_context: dict[str, Any] | None = None,
    store: CaseStore | None = None,
) -> CaseState:
    case_store = store or CaseStore()

    def mutate(case: CaseState) -> None:
        case.detected_at = detected_at or case.detected_at
        case.reported_at = reported_at or case.reported_at
        case.event_context.update(event_context or {})
        if case.detected_at and case.reported_at:
            detected = datetime.fromisoformat(case.detected_at.replace("Z", "+00:00"))
            reported = datetime.fromisoformat(case.reported_at.replace("Z", "+00:00"))
            seconds = (reported - detected).total_seconds()
            case.reporting_delay = f"PT{seconds:g}S"

    return case_store.update(case_id, mutate)


def _has_approved(case: CaseState, action: str) -> bool:
    return any(item.get("action") == action and item.get("decision") == "APPROVE" for item in case.human_decisions)


def _validate_transition(case: CaseState, target: Stage) -> None:
    current = Stage(case.stage)
    current_index = STAGE_SEQUENCE.index(current)
    if target is Stage.FORMAL_INVESTIGATION and current is Stage.EFFECTIVENESS_MONITORING:
        return
    if STAGE_SEQUENCE.index(target) != current_index + 1:
        raise ValueError(f"Invalid stage transition: {current.value} -> {target.value}")
    if target is Stage.PRELIMINARY_ASSESSMENT and case.containment_status == "NOT_ASSESSED":
        raise ValueError("Containment must be assessed before preliminary assessment")
    if target is Stage.CLASSIFICATION and not case.preliminary_assessment.get("what_happened"):
        raise ValueError("Preliminary assessment must be recorded before classification")
    if target is Stage.FORMAL_INVESTIGATION and not case.classification:
        raise ValueError("Classification must be recorded before formal investigation")
    if target is Stage.ROOT_CAUSE_ANALYSIS:
        scoped_findings = [
            finding for finding in case.worker_findings
            if finding.get("worker_type") != "hypothesis-challenger"
        ]
        if not scoped_findings:
            raise ValueError("At least one relevant formal-investigation finding is required before RCA")
    if target is Stage.EXTENSION_ASSESSMENT:
        challenged = any(f.get("worker_type") == "hypothesis-challenger" for f in case.worker_findings)
        if not challenged:
            raise ValueError("Hypothesis challenger must be completed before extension assessment")
    if target is Stage.PRODUCT_IMPACT_ASSESSMENT:
        if not case.extension_assessment.get("extension_conclusion"):
            raise ValueError("Extension conclusion must be recorded before product-impact assessment")
    if target is Stage.CAPA_OR_CHANGE:
        status = case.product_impact.get("product_impact_status")
        if status not in {item.value for item in ProductImpactStatus}:
            raise ValueError("A valid product-impact status must be recorded before CAPA or change")
    if target is Stage.QA_AND_SPONSOR_REVIEW:
        if not _has_approved(case, "confirm_root_cause"):
            raise ValueError("Human root-cause confirmation is required before QA and sponsor review")
        if not _has_approved(case, "approve_product_impact"):
            raise ValueError("Human product-impact approval is required before QA and sponsor review")
        if any(capa.get("human_approval_required", True) for capa in case.CAPAs) and not _has_approved(case, "approve_capa"):
            raise ValueError("Human CAPA approval is required before QA and sponsor review")
    if target is Stage.EFFECTIVENESS_MONITORING:
        if not case.effectiveness_monitoring.get("effectiveness_plan"):
            raise ValueError("An effectiveness plan is required before monitoring")
    if target is Stage.CLOSED:
        monitoring = case.effectiveness_monitoring
        if monitoring.get("status") != "SUCCESSFUL":
            raise ValueError("Effectiveness monitoring must be successful before closure")
        if not _has_approved(case, "deviation_closure"):
            raise ValueError("An approved deviation_closure human decision is required")
        if case.sponsor_requirements.get("sponsor_review_required") and not _has_approved(case, "sponsor_review"):
            raise ValueError("Required sponsor review has not been approved")


def advance_case(case_id: str, target_stage: Stage | str, *, store: CaseStore | None = None) -> CaseState:
    target = Stage(target_stage)
    case_store = store or CaseStore()

    def mutate(case: CaseState) -> None:
        _validate_transition(case, target)
        case.stage = target.value

    return case_store.update(case_id, mutate)


def reopen_case(case_id: str, reason: str, *, store: CaseStore | None = None) -> CaseState:
    case_store = store or CaseStore()

    def mutate(case: CaseState) -> None:
        if Stage(case.stage) not in {Stage.EFFECTIVENESS_MONITORING, Stage.CLOSED}:
            raise ValueError("Only effectiveness monitoring or closed cases can be reopened")
        case.stage = Stage.FORMAL_INVESTIGATION.value
        case.effectiveness_monitoring["status"] = "FAILED"
        case.open_questions.append(f"Reopened investigation: {reason}")

    return case_store.update(case_id, mutate)


def record_observation(case_id: str, claim: Claim, *, store: CaseStore | None = None) -> CaseState:
    return (store or CaseStore()).update(case_id, lambda case: case.observations.append(claim.to_dict()))


def add_hypothesis(case_id: str, hypothesis: Hypothesis, *, store: CaseStore | None = None) -> CaseState:
    hypothesis.validate()
    return (store or CaseStore()).update(case_id, lambda case: case.hypotheses.append(_json_value(hypothesis)))


def add_capa(case_id: str, capa: CAPA, *, store: CaseStore | None = None) -> CaseState:
    capa.validate()
    return (store or CaseStore()).update(case_id, lambda case: case.CAPAs.append(_json_value(capa)))


def classify_case(
    case_id: str,
    classification: Classification | str,
    rationale: str,
    evidence_refs: list[str],
    *,
    policy: dict[str, Any] | None = None,
    store: CaseStore | None = None,
) -> CaseState:
    level = Classification(classification)
    used_policy = policy or DEFAULT_CLASSIFICATION_POLICY

    def mutate(case: CaseState) -> None:
        case.classification = level.value
        case.classification_rationale = rationale
        case.classification_evidence = evidence_refs
        case.policy_used = used_policy

    return (store or CaseStore()).update(case_id, mutate)


def record_worker_finding(
    case_id: str,
    worker_type: str,
    finding: dict[str, Any],
    *,
    store: CaseStore | None = None,
) -> CaseState:
    allowed_stages = {Stage.FORMAL_INVESTIGATION.value, Stage.ROOT_CAUSE_ANALYSIS.value}
    case_store = store or CaseStore()
    current = case_store.load(case_id)
    if current.stage not in allowed_stages:
        raise ValueError("Worker findings may only be recorded during formal investigation or RCA")
    if worker_type == "hypothesis-challenger" and current.stage != Stage.ROOT_CAUSE_ANALYSIS.value:
        raise ValueError("The hypothesis challenger runs during ROOT_CAUSE_ANALYSIS")
    claims = finding.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("Worker finding must contain a non-empty claims list")
    allowed_claim_types = {"OBSERVED_FACT", "INFERENCE", "HYPOTHESIS", "PROPOSED_ACTION"}
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("claim_type") not in allowed_claim_types:
            raise ValueError("Every worker claim must have a valid claim_type")
        if claim.get("claim_type") == "OBSERVED_FACT":
            provenance = claim.get("provenance", {})
            required = {"source_system", "source_record_id", "timestamp", "evidence_ref"}
            if required - set(provenance) or any(not provenance.get(key) for key in required):
                raise ValueError("Worker OBSERVED_FACT requires complete provenance")
    entry = {"worker_type": worker_type, "recorded_at": _now(), "finding": finding}
    return case_store.update(case_id, lambda case: case.worker_findings.append(entry))
