import type { LearningProfileEventCreatePayload, ResourceType } from "../api/client";

export type LessonTrackedAction =
  | "classroom_completed"
  | "document_viewed"
  | "mind_map_interacted"
  | "code_attempt_run"
  | "code_attempt_passed";

export interface LessonProfileEventInput {
  action: LessonTrackedAction;
  topic: string;
  nodeId: string;
  resourceType?: ResourceType | "openmaic_classroom";
  score?: number;
  detail?: string;
  payload?: Record<string, unknown>;
}

const eventByAction: Record<LessonTrackedAction, string> = {
  classroom_completed: "openmaic_classroom_viewed",
  document_viewed: "document_viewed",
  mind_map_interacted: "mind_map_interacted",
  code_attempt_run: "code_attempt_run",
  code_attempt_passed: "code_attempt_passed"
};

const evidenceByAction: Record<LessonTrackedAction, "weak" | "medium" | "strong"> = {
  classroom_completed: "medium",
  document_viewed: "medium",
  mind_map_interacted: "medium",
  code_attempt_run: "medium",
  code_attempt_passed: "strong"
};

export function buildLessonProfileEvent(input: LessonProfileEventInput): LearningProfileEventCreatePayload {
  const resourceType = input.resourceType || resourceTypeForAction(input.action);
  return {
    event_type: eventByAction[input.action],
    topic: input.topic,
    knowledge_node_id: input.nodeId,
    detail: input.detail || `${input.topic}: ${input.action}`,
    event_payload: {
      resource_type: resourceType,
      action: input.action,
      ...(input.payload || {})
    },
    evidence_strength: evidenceByAction[input.action],
    score: input.score
  };
}

function resourceTypeForAction(action: LessonTrackedAction): ResourceType | "openmaic_classroom" {
  if (action === "classroom_completed") {
    return "openmaic_classroom";
  }
  if (action === "mind_map_interacted") {
    return "mind_map";
  }
  if (action === "code_attempt_run" || action === "code_attempt_passed") {
    return "code_lab";
  }
  return "document";
}
