import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { StringEnum } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const GateAction = StringEnum([
	"confirm_root_cause",
	"approve_product_impact",
	"request_consequential_qc_testing",
	"oos_disposition",
	"approve_capa",
	"process_change",
	"formulation_change",
	"material_change",
	"deviation_closure",
	"batch_disposition",
	"sponsor_notification",
	"sponsor_review",
] as const);

const GateParams = Type.Object({
	case_id: Type.String({ minLength: 1, maxLength: 128 }),
	action: GateAction,
	proposal: Type.String({ minLength: 1 }),
	rationale: Type.String({ minLength: 1 }),
	evidence_refs: Type.Array(Type.String(), { minItems: 1 }),
});

interface HumanDecision {
	decision_id: string;
	action: string;
	decision: "APPROVE" | "REJECT";
	proposal: string;
	rationale: string;
	evidence_refs: string[];
	decided_at: string;
	decision_source: "deviation_human_gate";
}

interface DeviationCase {
	case_id: string;
	stage: string;
	hypotheses: Array<{ status?: string; evidence_for?: string[] }>;
	worker_findings: Array<{ worker_type?: string }>;
	product_impact: { product_impact_status?: string | null };
	CAPAs: Array<{ human_approval_required?: boolean }>;
	effectiveness_monitoring: { status?: string };
	human_decisions: HumanDecision[];
	revision: number;
	updated_at: string;
}

function gatePrecondition(deviationCase: DeviationCase, action: string): string | undefined {
	if (action === "confirm_root_cause") {
		const rootCauseStages = new Set(["PRODUCT_IMPACT_ASSESSMENT", "CAPA_OR_CHANGE"]);
		if (!rootCauseStages.has(deviationCase.stage)) {
			return "Root-cause confirmation is only available after extension and product-impact assessment and before QA review.";
		}
		if (!deviationCase.worker_findings.some((finding) => finding.worker_type === "hypothesis-challenger")) {
			return "A recorded hypothesis-challenger finding is required before root-cause confirmation.";
		}
		if (!deviationCase.hypotheses.some((hypothesis) => hypothesis.status === "SUPPORTED" && hypothesis.evidence_for?.length)) {
			return "A supported, evidenced hypothesis is required before root-cause confirmation.";
		}
	}
	if (action === "approve_product_impact" && !deviationCase.product_impact?.product_impact_status) {
		return "A product-impact assessment and status are required before approval.";
	}
	if (action === "approve_capa" && !deviationCase.CAPAs?.length) {
		return "At least one proposed CAPA is required before approval.";
	}
	if (action === "deviation_closure") {
		if (deviationCase.stage !== "EFFECTIVENESS_MONITORING") {
			return "The case must be in EFFECTIVENESS_MONITORING before closure approval.";
		}
		if (deviationCase.effectiveness_monitoring?.status !== "SUCCESSFUL") {
			return "Effectiveness monitoring must be successful before closure approval.";
		}
	}
	return undefined;
}

function casePath(cwd: string, caseId: string): string {
	if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(caseId)) {
		throw new Error("Invalid deviation case ID");
	}
	return join(cwd, ".prime", "deviation-cases", `${caseId}.json`);
}

async function persistDecision(path: string, decision: HumanDecision): Promise<void> {
	const content = await readFile(path, "utf8");
	const deviationCase = JSON.parse(content) as DeviationCase;
	if (!Array.isArray(deviationCase.human_decisions)) {
		throw new Error("Deviation case has invalid human_decisions state");
	}
	deviationCase.human_decisions.push(decision);
	deviationCase.revision = Number(deviationCase.revision ?? 0) + 1;
	deviationCase.updated_at = decision.decided_at;
	const temporary = `${path}.${process.pid}.tmp`;
	await mkdir(dirname(path), { recursive: true });
	await writeFile(temporary, `${JSON.stringify(deviationCase, null, 2)}\n`, "utf8");
	await rename(temporary, path);
}

export default function deviationHitl(pi: ExtensionAPI): void {
	pi.registerTool({
		name: "deviation_human_gate",
		label: "Deviation human gate",
		description:
			"Request a real human approve/reject decision for a regulated deviation decision. Records the decision in the durable case and never executes the proposed downstream action.",
		promptGuidelines: [
			"Use deviation_human_gate for regulated deviation decisions; an approval records authorization but does not execute containment, testing, disposition, notification, CAPA, or manufacturing changes.",
		],
		parameters: GateParams,
		executionMode: "sequential",

		async execute(toolCallId, params, _signal, _onUpdate, ctx) {
			const path = casePath(ctx.cwd, params.case_id);
			if (!ctx.hasUI) {
				return {
					content: [{ type: "text", text: "REJECTED: human approval UI is unavailable; no decision was recorded." }],
					details: { decision: "REJECT", recorded: false, reason: "UI_UNAVAILABLE" },
				};
			}

			let deviationCase: DeviationCase;
			try {
				deviationCase = JSON.parse(await readFile(path, "utf8")) as DeviationCase;
			} catch {
				return {
					content: [{ type: "text", text: `REJECTED: deviation case ${params.case_id} does not exist.` }],
					details: { decision: "REJECT", recorded: false, reason: "CASE_NOT_FOUND" },
				};
			}
			const preconditionError = gatePrecondition(deviationCase, params.action);
			if (preconditionError) {
				return {
					content: [{ type: "text", text: `REJECTED: ${preconditionError} No decision was recorded.` }],
					details: { decision: "REJECT", recorded: false, reason: "PRECONDITION_FAILED" },
				};
			}

			const choice = await ctx.ui.select(
				`Deviation ${params.case_id}: ${params.action}\n\nProposal: ${params.proposal}\n\nRationale: ${params.rationale}\n\nEvidence: ${params.evidence_refs.join(", ")}\n\nThis records a decision only and executes no downstream action.`,
				["Approve", "Reject"],
			);
			const decision: HumanDecision = {
				decision_id: toolCallId,
				action: params.action,
				decision: choice === "Approve" ? "APPROVE" : "REJECT",
				proposal: params.proposal,
				rationale: params.rationale,
				evidence_refs: params.evidence_refs,
				decided_at: new Date().toISOString(),
				decision_source: "deviation_human_gate",
			};
			await persistDecision(path, decision);

			return {
				content: [
					{
						type: "text",
						text: `${decision.decision}: decision recorded for ${params.action}. No downstream action was executed.`,
					},
				],
				details: { ...decision, recorded: true, downstream_action_executed: false },
			};
		},
	});
}
