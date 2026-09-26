"""Bounded child-investigator definitions and selective RLM spawning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rlm import spawn

from .state import CaseState


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    scope: str


WORKERS = {
    "equipment-investigator": WorkerSpec("equipment-investigator", "Equipment state, alarms, calibration, maintenance, and failure modes."),
    "material-investigator": WorkerSpec("material-investigator", "Material and supplier lots, lineage, status, sampling, and variability."),
    "lab-investigator": WorkerSpec("lab-investigator", "QC data, methods, standards, instruments, sample handling, and OOS context."),
    "historical-deviation-investigator": WorkerSpec("historical-deviation-investigator", "Similar deviations, recurrence, prior causes, and CAPA effectiveness."),
    "process-investigator": WorkerSpec("process-investigator", "Batch execution, procedures, CPPs, controls, environment, personnel, and automation."),
    "process-science-investigator": WorkerSpec("process-science-investigator", "Good-vs-bad batch analytics, CQA/CPP/CMA relationships, development knowledge, and candidate experiments."),
    "hypothesis-challenger": WorkerSpec("hypothesis-challenger", "Contradictions, alternative causes, confounders, missing evidence, unexplained observations, and historical counterexamples."),
}


PROCESS_SCIENCE_TERMS = {
    "low yield", "low potency", "high impurity", "dissolution", "stability",
    "glycosylation", "variability", "failed cqa", "out of specification", "oos",
}


def select_investigators(case: CaseState) -> list[str]:
    text = " ".join(
        [case.objective, str(case.event_context), str(case.preliminary_assessment), str(case.affected_entities)]
    ).lower()
    selected: list[str] = []
    rules = {
        "equipment-investigator": ("equipment", "alarm", "pressure", "temperature", "maintenance", "calibration"),
        "material-investigator": ("material", "supplier", "raw material", "lot"),
        "lab-investigator": ("lab", "qc", "assay", "impurity", "potency", "dissolution", "oos"),
        "historical-deviation-investigator": ("recurr", "historical", "prior", "systemic", "similar"),
        "process-investigator": ("process", "batch", "step", "operator", "procedure", "automation", "software"),
    }
    for worker, terms in rules.items():
        if any(term in text for term in terms):
            selected.append(worker)
    if any(term in text for term in PROCESS_SCIENCE_TERMS):
        selected.append("process-science-investigator")
    if not selected:
        selected.append("process-investigator")
    return selected


async def spawn_investigators(
    case: CaseState,
    worker_names: list[str],
    *,
    additional_context: str = "",
) -> dict[str, Any]:
    unknown = sorted(set(worker_names) - set(WORKERS))
    if unknown:
        raise ValueError(f"Unknown deviation workers: {', '.join(unknown)}")
    handles: dict[str, Any] = {}
    for worker_name in dict.fromkeys(worker_names):
        spec = WORKERS[worker_name]
        prompt = f"""You are the bounded {spec.name} for pharmaceutical deviation {case.case_id}.
Scope: {spec.scope}
Current stage: {case.stage}
Objective: {case.objective}
Event context: {case.event_context}
Preliminary assessment: {case.preliminary_assessment}
Affected entities: {case.affected_entities}
Current hypotheses: {case.hypotheses}
Open questions: {case.open_questions}
Missing evidence: {case.missing_evidence}
Additional context: {additional_context}

Stay within scope. Retrieve evidence through deviation manufacturing tools. Return a
structured finding with observed facts and provenance, inferences, evidence gaps, open
questions, and proposed next steps. Do not approve actions, decide disposition, or
declare an unsupported root cause. The hypothesis challenger must actively seek
contradictions, alternatives, confounders, and historical counterexamples.
"""
        handles[worker_name] = await spawn(prompt, name=worker_name)
    return handles
