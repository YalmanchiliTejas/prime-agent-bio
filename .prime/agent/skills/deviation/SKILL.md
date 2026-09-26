---
name: deviation
description: Own and progress pharmaceutical manufacturing deviation cases through reporting, containment, assessment, classification, investigation, RCA challenge, extension, product impact, CAPA, review, effectiveness monitoring, and closure. Use for GMP deviations, excursions, OOS-related investigations, failed CQAs, and sponsor/CDMO deviation handling.
---

# Deviation Investigation

Use this skill as the durable case system of record. Its JSON files live under
`.prime/deviation-cases/`, outside conversation history.

```python
from deviation import CaseStore, Stage, create_case

case = create_case("DEV-2026-001", "Investigate reactor pressure excursion")
case = CaseStore().load("DEV-2026-001")
```

## Required lifecycle

Progress one stage at a time with `advance_case(case_id, target_stage)`: `DETECTED`,
`INITIAL_REPORTING`, `IMMEDIATE_ACTIONS_AND_CONTAINMENT`, `PRELIMINARY_ASSESSMENT`,
`CLASSIFICATION`, `FORMAL_INVESTIGATION`, `ROOT_CAUSE_ANALYSIS`,
`EXTENSION_ASSESSMENT`, `PRODUCT_IMPACT_ASSESSMENT`, `CAPA_OR_CHANGE`,
`QA_AND_SPONSOR_REVIEW`, `EFFECTIVENESS_MONITORING`, `CLOSED`.

At intake, record available detection context, `detected_at`, `reported_at`, and the
calculated reporting delay. Compare it with retrieved site policy; never invent a
universal reporting deadline. Assess and recommend containment before RCA. Preserve
samples and records when relevant, but do not execute regulated actions.

At preliminary assessment, answer what happened, affected process and entities,
whether the signal appears isolated or systemic, potential CQA or patient/product
risk, and urgent evidence needs. Do not conduct deep RCA in this stage.

Classify using retrieved policy. Built-in Minor/Major/Critical semantics are fallback
defaults and must be identified as such in `policy_used`. Record rationale and evidence.

## Investigation and RCA

Retrieve through these manufacturing interfaces:

```python
get_batch(...)
get_process_steps(...)
get_process_trace(...)
get_equipment_history(...)
get_material_lineage(...)
get_lab_results(...)
find_similar_deviations(...)
get_previous_capas(...)
get_governing_documents(...)
find_related_batches(...)
compare_batches(...)
get_process_knowledge(...)
```

When `PRIME_DEVIATION_API_BASE` is set, these functions use Bio-Demo's authorized,
tenant-scoped agent-tool API. Otherwise they use read-only JSON exports from
`.prime/deviation-data/`. Never bypass either connector with raw database queries.

Use `select_investigators(case)` and `spawn_investigators(case, worker_names)` to run
only relevant bounded workers. Available workers are equipment, material, lab,
historical-deviation, process, process-science, and hypothesis-challenger. The root RLM
owns synthesis and case progression.

Represent competing RCA hypotheses with evidence for and against, missing evidence,
open questions, confidence, and status. `plausible` is not a root cause. Before calling
the human gate for `confirm_root_cause`, run the challenger and persist its finding with
`record_worker_finding(..., worker_type="hypothesis-challenger")`.

Use the process-science worker for failed product outputs or CQAs such as yield,
potency, impurity, dissolution, stability, glycosylation, or unexpected variability.
Use `compare_batches` for numerical comparisons; do not infer statistics by scanning
large tables in prose. Changes and experiments remain proposals.

## Extension, impact, and CAPA

Make extension a separate stage. Use `find_related_batches` across same product,
equipment, material/supplier lot, time window, process version, and procedure, then
record searched dimensions, potentially affected batches/products, and conclusion.

Assess product impact separately from cause. Record CQAs, CPP excursion duration,
exposed product, downstream processing, QC results, and relevant stability/development
evidence. Product-impact status is `NO_EVIDENCE_OF_IMPACT`, `POTENTIAL_IMPACT`,
`CONFIRMED_IMPACT`, or `INCONCLUSIVE`, and requires human review.

Each CAPA has an explicit `CORRECTION`, `CORRECTIVE_ACTION`, or `PREVENTIVE_ACTION`
type, linked supported cause, evidence, owner, expected effect, verification method,
effectiveness criteria, and human approval requirement. Do not default to retraining
when evidence indicates equipment, controls, maintenance, procedure, material,
monitoring, formulation, or process-design causes.

Define effectiveness metrics, batches, observation period, recurrence, success, and
failure conditions. On failure use `reopen_case`; do not close. Retrieve sponsor/CDMO
roles, notification rules, deadlines, approvers, investigation/CAPA ownership, and
batch-disposition responsibility from governing documents.

## Evidence and human decisions

Create sourced facts with `observed_fact(...)`. It rejects incomplete provenance.
Use `inference(...)`, `hypothesis_claim(...)`, and `proposed_action(...)` for other
claim types. Save claims with `record_observation` or in the applicable case section.

For regulated decisions, call the `deviation_human_gate` extension tool with the case
ID, decision action, concise proposal, rationale, and evidence references. Its result is
the human decision. It records approval or rejection in the case and performs no
downstream action. Reload the case afterward.

Before closure, verify the stage is `EFFECTIVENESS_MONITORING`, effectiveness succeeded,
required root-cause/product-impact/CAPA decisions are approved, sponsor review is
complete when required, and an approved `deviation_closure` gate decision exists.
