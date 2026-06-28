import {
  isLearnableKnowledgeNodeId,
  lessonGenerationResourceTypes,
  knowledgeLearningNavigationSignature,
  knowledgeLearningRouteState
} from "./knowledgeLearningRouteStateModel.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

test("keeps matching node and orders resource types from route state", () => {
  const routeState = knowledgeLearningRouteState(
    {
      node: { id: "node-1", name: "变量" },
      resourceTypes: ["video", "exercise"]
    },
    "node-1"
  );

  assert(routeState.node?.id === "node-1", "matching route node should be kept");
  assert(
    JSON.stringify(routeState.resourceTypes) === JSON.stringify(["exercise", "video"]),
    `unexpected resource order: ${JSON.stringify(routeState.resourceTypes)}`
  );
});

test("passes exactly the learning path recommended modalities when supplied", () => {
  const routeState = knowledgeLearningRouteState(
    {
      node: { id: "node-1", name: "鍙橀噺" },
      resourceTypes: ["reading"],
      stage: {
        node_id: "node-1",
        topic: "鍙橀噺",
        level: 1,
        order: 1,
        mastery_status: "current",
        priority_score: 100,
        path_status: "current",
        is_current: true,
        is_locked: false,
        is_remedial: false,
        estimated_minutes: 15,
        scheduled_day: "鍛ㄤ竴",
        scheduled_date: "2026-05-28",
        scheduled_minutes: 15,
        schedule_label: "浠婃棩浠诲姟",
        is_today_task: true,
        task_type: "minimum",
        is_minimum_task: true,
        is_stretch_task: false,
        goal: "鐞嗚В鍙橀噺瀹氫箟",
        practice_task: "瀹屾垚鍙橀噺缁冧範",
        graph_basis: [],
        profile_basis: [],
        recommended_resource_types: ["reading"],
        recommendation_reason: "棣栬疆瀛︿範"
      }
    },
    "node-1"
  );

  assert(
    JSON.stringify(routeState.resourceTypes) === JSON.stringify(["reading"]),
    `recommended resource types should not be expanded: ${JSON.stringify(routeState.resourceTypes)}`
  );
});

test("learning page generation always includes post-classroom artifacts", () => {
  const requested = lessonGenerationResourceTypes(["reading"]);

  assert(
    JSON.stringify(requested) === JSON.stringify(["document", "mind_map", "code_lab", "reading"]),
    `lesson generation should include mandatory artifacts plus recommendations: ${JSON.stringify(requested)}`
  );
});

test("drops stale node state after navigating to a different node", () => {
  const routeState = knowledgeLearningRouteState(
    {
      node: { id: "node-1", name: "变量" },
      resourceTypes: ["reading"]
    },
    "node-2"
  );

  assert(routeState.node === undefined, "stale route node should not leak into the next knowledge page");
  assert(
    JSON.stringify(routeState.resourceTypes) === JSON.stringify([]),
    `stale resource types should be dropped: ${JSON.stringify(routeState.resourceTypes)}`
  );
  assert(routeState.stage === undefined, "stale stage should not leak into the next knowledge page");
});

test("treats the synthetic course root as non-learnable state", () => {
  const routeState = knowledgeLearningRouteState(
    {
      node: { id: "course-root", name: "Python 程序设计" },
      resourceTypes: ["video", "reading"]
    },
    "course-root"
  );

  assert(routeState.node === undefined, "course root should not be treated as a learnable knowledge node");
  assert(isLearnableKnowledgeNodeId("course-root") === false, "course root should be rejected as a learnable node id");
  assert(isLearnableKnowledgeNodeId("1.1") === true, "ordinary knowledge nodes should remain learnable");
});

test("treats chapter and section heading nodes as non-learnable state", () => {
  const routeState = knowledgeLearningRouteState(
    {
      node: { id: "c-chapter-1", name: "第 1 章 C语言概述", node_type: "chapter" },
      resourceTypes: ["document"]
    },
    "c-chapter-1"
  );

  assert(routeState.node === undefined, "chapter heading should not be kept as a learnable route node");
  assert(isLearnableKnowledgeNodeId("c-chapter-1") === false, "chapter ids should be rejected as learnable node ids");
  assert(isLearnableKnowledgeNodeId("outline-section-1-1") === true, "ordinary outline section ids should remain learnable");
});

test("navigation signature changes when the same node is reopened with different recommended resources", () => {
  const first = knowledgeLearningNavigationSignature(
    {
      node: { id: "node-1", name: "变量" },
      resourceTypes: ["video"],
      stage: {
        node_id: "node-1",
        topic: "变量",
        level: 1,
        order: 1,
        mastery_status: "current",
        priority_score: 100,
        path_status: "current",
        is_current: true,
        is_locked: false,
        is_remedial: false,
        estimated_minutes: 15,
        scheduled_day: "周一",
        scheduled_date: "2026-05-28",
        scheduled_minutes: 15,
        schedule_label: "今日任务",
        is_today_task: true,
        task_type: "minimum",
        is_minimum_task: true,
        is_stretch_task: false,
        goal: "理解变量定义",
        practice_task: "完成变量练习",
        graph_basis: [],
        profile_basis: [],
        recommended_resource_types: ["document", "video"],
        recommendation_reason: "首轮学习"
      }
    },
    "node-1"
  );

  const second = knowledgeLearningNavigationSignature(
    {
      node: { id: "node-1", name: "变量" },
      resourceTypes: ["reading"],
      stage: {
        node_id: "node-1",
        topic: "变量",
        level: 1,
        order: 2,
        mastery_status: "current",
        priority_score: 100,
        path_status: "current",
        is_current: true,
        is_locked: false,
        is_remedial: true,
        estimated_minutes: 20,
        scheduled_day: "周二",
        scheduled_date: "2026-05-29",
        scheduled_minutes: 20,
        schedule_label: "补救任务",
        is_today_task: true,
        task_type: "minimum",
        is_minimum_task: true,
        is_stretch_task: false,
        goal: "补救变量薄弱点",
        practice_task: "完成补救练习",
        graph_basis: [],
        profile_basis: [],
        recommended_resource_types: ["document", "reading"],
        recommendation_reason: "补救学习"
      }
    },
    "node-1"
  );

  assert(first !== second, "same-node navigation should reset when recommended resources or stage context changes");
});
