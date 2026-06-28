import type { CourseLearningStage, ResourceType } from "../api/client";

const resourceSequence: ResourceType[] = ["document", "mind_map", "exercise", "code_lab", "video", "reading"];
const requiredLessonResourceTypes: ResourceType[] = ["document", "mind_map", "code_lab"];
const nonLearnableNodeIds = new Set(["course-root"]);
const nonLearnableNodeTypes = new Set(["chapter", "section"]);

type RouteNode = Record<string, unknown>;

type RouteState = {
  node?: RouteNode;
  resourceTypes?: ResourceType[];
  stage?: CourseLearningStage;
} | null | undefined;

function textValue(record: Record<string, unknown> | undefined, key: string, fallback = ""): string {
  const value = record?.[key];
  return typeof value === "string" ? value : fallback;
}

export function orderedKnowledgeResourceTypes(types?: ResourceType[]): ResourceType[] {
  const requested = new Set<ResourceType>(types?.length ? types : []);
  return resourceSequence.filter((type) => requested.has(type));
}

export function lessonGenerationResourceTypes(types?: ResourceType[]): ResourceType[] | undefined {
  const ordered = orderedKnowledgeResourceTypes(types);
  if (!ordered.length) {
    return undefined;
  }
  const requested = new Set<ResourceType>([...requiredLessonResourceTypes, ...ordered]);
  return resourceSequence.filter((type) => requested.has(type));
}


export function isLearnableKnowledgeNodeId(nodeId: string): boolean {
  return Boolean(nodeId) && !nonLearnableNodeIds.has(nodeId) && !/-chapter-\d+$/i.test(nodeId);
}

export function isLearnableKnowledgeNode(node: RouteNode | undefined, decodedNodeId = textValue(node, "id")): boolean {
  const nodeType = textValue(node, "node_type", textValue(node, "type", "")).toLowerCase();
  return isLearnableKnowledgeNodeId(decodedNodeId) && !nonLearnableNodeTypes.has(nodeType);
}

export function knowledgeLearningRouteState(state: RouteState, decodedNodeId: string): {
  node?: RouteNode;
  resourceTypes: ResourceType[];
  stage?: CourseLearningStage;
} {
  const routeNode = state?.node;
  const routeNodeId = textValue(routeNode, "id");
  const routeStage = state?.stage;
  const stageNodeId = routeStage?.node_id || "";
  const keepNode =
    routeNode && routeNodeId && routeNodeId === decodedNodeId && isLearnableKnowledgeNode(routeNode, decodedNodeId)
      ? routeNode
      : undefined;
  const keepStage = stageNodeId && stageNodeId === decodedNodeId ? routeStage : undefined;
  const keepResourceTypes = Boolean(keepNode || keepStage);

  return {
    node: keepNode,
    resourceTypes: keepResourceTypes ? orderedKnowledgeResourceTypes(state?.resourceTypes) : [],
    stage: keepStage
  };
}

export function knowledgeLearningNavigationSignature(state: RouteState, decodedNodeId: string): string {
  const resolved = knowledgeLearningRouteState(state, decodedNodeId);
  const stageId = resolved.stage?.node_id || "";
  const stageOrder = resolved.stage?.order ?? "";
  return [
    decodedNodeId,
    textValue(resolved.node, "id"),
    resolved.resourceTypes.join(","),
    stageId,
    stageOrder
  ].join("|");
}
