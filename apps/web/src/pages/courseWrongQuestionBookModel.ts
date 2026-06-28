import type { ComprehensiveAssessmentPayload, LearningProfileEvent } from "../api/client";

export type WrongQuestionType = "quiz" | "code";

export interface WrongQuestionBookItem {
  id: string;
  questionId?: string;
  sourceEventId: number;
  type: WrongQuestionType;
  topic: string;
  nodeId: string;
  dimension: string;
  prompt: string;
  options?: string[];
  selectedAnswerIndex?: number;
  correctAnswerIndex?: number;
  selectedAnswer: string;
  correctAnswer: string;
  code?: string;
  actualOutput?: string;
  expectedOutput?: string;
  attempts: number;
  createdAt: string;
  resolved: boolean;
  resolvedAt?: string;
  chapterId: string;
  chapterTitle: string;
  sectionId: string;
  sectionTitle: string;
  nodeTitle: string;
}

export interface WrongQuestionBookSection {
  sectionId: string;
  sectionTitle: string;
  items: WrongQuestionBookItem[];
}

export interface WrongQuestionBookChapter {
  chapterId: string;
  chapterTitle: string;
  sections: WrongQuestionBookSection[];
}

export interface WrongQuestionBookModel {
  summary: {
    total: number;
    unresolved: number;
    resolved: number;
    chapterCount: number;
    latestCreatedAt: string;
  };
  chapterGroups: WrongQuestionBookChapter[];
}

export interface WrongQuestionRedoInput {
  selectedAnswerIndex?: number;
  code?: string;
  actualOutput?: string;
  attempts?: number;
}

export interface WrongQuestionRedoResult {
  passed: boolean;
  message: string;
}

type GraphRecord = Record<string, unknown>;

export function buildWrongQuestionBookModel(input: {
  events?: LearningProfileEvent[];
  nodes?: GraphRecord[];
}): WrongQuestionBookModel {
  const events = input.events || [];
  const nodeIndex = buildNodeIndex(input.nodes || []);
  const resolved = resolvedQuestionMap(events);
  const items = buildWrongQuestionItems(events)
    .map((item) => withGraphLocation(item, nodeIndex, resolved.get(item.id)))
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
  const chapterGroups = groupByChapter(items);

  return {
    summary: {
      total: items.length,
      unresolved: items.filter((item) => !item.resolved).length,
      resolved: items.filter((item) => item.resolved).length,
      chapterCount: chapterGroups.length,
      latestCreatedAt: items[0]?.createdAt || ""
    },
    chapterGroups
  };
}

export function evaluateWrongQuestionRedo(
  item: WrongQuestionBookItem,
  redo: WrongQuestionRedoInput
): WrongQuestionRedoResult {
  if (item.type === "quiz") {
    const passed = redo.selectedAnswerIndex !== undefined && redo.selectedAnswerIndex === item.correctAnswerIndex;
    return {
      passed,
      message: passed ? "选择题重做正确" : "答案仍未匹配，请重新分析题干和选项。"
    };
  }

  const actual = normalizeOutput(redo.actualOutput || "");
  const expected = normalizeOutput(item.expectedOutput || "");
  const passed = Boolean(expected && actual === expected);
  return {
    passed,
    message: passed ? "编程题输出匹配，重做通过" : "运行输出与期望输出不一致。"
  };
}

export function buildRedoAssessmentPayload(input: {
  courseId: number;
  item: WrongQuestionBookItem;
  redo: WrongQuestionRedoInput;
  studentId: string;
}): ComprehensiveAssessmentPayload {
  const result = evaluateWrongQuestionRedo(input.item, input.redo);
  const quizAnswers = input.item.type === "quiz"
    ? [
      {
        id: input.item.questionId || "redo_question",
        dimension: "错题重做",
        correct: result.passed,
        prompt: input.item.prompt,
        options: input.item.options || [],
        correct_answer_index: input.item.correctAnswerIndex,
        selected_answer_index: input.redo.selectedAnswerIndex,
        weight: 1
      }
    ]
    : [
      {
        id: "wrong_question_redo_code_guard",
        dimension: "错题重做",
        correct: true,
        prompt: `${input.item.topic} 编程题重做`,
        options: ["已完成编程题重做"],
        correct_answer_index: 0,
        selected_answer_index: 0,
        weight: 1
      }
    ];

  return {
    student_id: input.studentId,
    topic: input.item.topic,
    course_id: input.courseId,
    knowledge_node_id: input.item.nodeId,
    classroom_completed: true,
    notes_completed: true,
    mind_map_completed: true,
    code_lab_completed: true,
    quiz_answers: quizAnswers,
    code_attempt: {
      prompt: input.item.type === "code" ? input.item.prompt : `${input.item.topic} 错题重做`,
      code: input.item.type === "code" ? input.redo.code || "" : "# quiz redo accepted",
      expected_output: input.item.type === "code" ? input.item.expectedOutput || "" : "OK",
      actual_output: input.item.type === "code" ? input.redo.actualOutput || "" : "OK",
      passed: result.passed,
      attempts: Math.max(1, input.redo.attempts || 1)
    },
    detail: JSON.stringify({
      assessment_type: "wrong_question_redo",
      source_question_id: input.item.id,
      source_event_id: input.item.sourceEventId,
      resolved_question_ids: result.passed ? [input.item.id] : [],
      result: result.message
    })
  };
}

interface RawWrongQuestionItem {
  id: string;
  questionId?: string;
  sourceEventId: number;
  type: WrongQuestionType;
  topic: string;
  nodeId: string;
  dimension: string;
  prompt: string;
  options?: string[];
  selectedAnswerIndex?: number;
  correctAnswerIndex?: number;
  selectedAnswer: string;
  correctAnswer: string;
  code?: string;
  actualOutput?: string;
  expectedOutput?: string;
  attempts: number;
  createdAt: string;
}

interface NodeLocation {
  chapterId: string;
  chapterTitle: string;
  sectionId: string;
  sectionTitle: string;
  nodeTitle: string;
}

interface NodeIndex {
  byId: Map<string, GraphRecord>;
}

function buildWrongQuestionItems(events: LearningProfileEvent[]): RawWrongQuestionItem[] {
  return events
    .filter((event) => event.event_type === "assessment_submitted")
    .flatMap((event) => {
      const payload = objectValue(event.event_payload);
      const assessment = objectValue(payload.assessment) || payload;
      const quizAnswers = arrayValue(assessment.quiz_answers);
      const codeAttempt = objectValue(assessment.code_attempt) || objectValue(payload.code_attempt);
      const quizWrong = quizAnswers
        .filter((answer) => !isQuizAnswerCorrect(answer))
        .map((answer, index) => wrongQuizItem(event, answer, index));
      const codeWrong = codeAttempt && !booleanValue(codeAttempt.passed) ? [wrongCodeItem(event, codeAttempt)] : [];
      return [...quizWrong, ...codeWrong];
    });
}

function wrongQuizItem(event: LearningProfileEvent, answer: GraphRecord, index: number): RawWrongQuestionItem {
  const options = stringArrayValue(answer.options);
  const selectedIndex = integerValue(answer.selected_answer_index);
  const correctIndex = integerValue(answer.correct_answer_index);
  const questionId = textValue(answer, "id", String(index));
  return {
    id: `${event.id}-quiz-${questionId}`,
    questionId,
    sourceEventId: event.id,
    type: "quiz",
    topic: event.topic,
    nodeId: event.knowledge_node_id,
    dimension: textValue(answer, "dimension", "选择题"),
    prompt: textValue(answer, "prompt", `${event.topic} · 选择题错题`),
    options,
    selectedAnswerIndex: selectedIndex,
    correctAnswerIndex: correctIndex,
    selectedAnswer: optionLabel(options, selectedIndex, "未作答"),
    correctAnswer: optionLabel(options, correctIndex, "待查看正确答案"),
    attempts: 1,
    createdAt: event.created_at
  };
}

function wrongCodeItem(event: LearningProfileEvent, attempt: GraphRecord): RawWrongQuestionItem {
  return {
    id: `${event.id}-code`,
    sourceEventId: event.id,
    type: "code",
    topic: event.topic,
    nodeId: event.knowledge_node_id,
    dimension: "编程题",
    prompt: textValue(attempt, "prompt", `${event.topic} 编程题`),
    selectedAnswer: "代码输出未匹配预期",
    correctAnswer: "运行输出需要与题目预期一致",
    code: textValue(attempt, "code"),
    actualOutput: textValue(attempt, "actual_output"),
    expectedOutput: textValue(attempt, "expected_output"),
    attempts: integerValue(attempt.attempts) ?? 1,
    createdAt: event.created_at
  };
}

function buildNodeIndex(nodes: GraphRecord[]): NodeIndex {
  const byId = new Map<string, GraphRecord>();
  nodes.forEach((node) => {
    const id = textValue(node, "id");
    if (id) {
      byId.set(id, node);
    }
  });
  return {
    byId
  };
}

function withGraphLocation(
  item: RawWrongQuestionItem,
  nodeIndex: NodeIndex,
  resolvedAt?: string
): WrongQuestionBookItem {
  const location = locateNode(item.nodeId, nodeIndex);
  return {
    ...item,
    ...location,
    resolved: Boolean(resolvedAt),
    resolvedAt
  };
}

function locateNode(nodeId: string, nodeIndex: NodeIndex): NodeLocation {
  const node = nodeIndex.byId.get(nodeId);
  const nodeTitle = nodeName(node, nodeId || "未命名知识点");
  const ancestors = ancestorsOf(node, nodeIndex.byId);
  const chapter = ancestors.find((ancestor) => isNodeType(ancestor, "chapter"));
  const section = [...ancestors].reverse().find((ancestor) => isNodeType(ancestor, "section"));
  return {
    chapterId: textValue(chapter, "id", "unclassified"),
    chapterTitle: nodeName(chapter, inferChapterTitle(nodeTitle)),
    sectionId: textValue(section, "id", textValue(chapter, "id", "unclassified-section")),
    sectionTitle: nodeName(section, "未归类小节"),
    nodeTitle
  };
}

function ancestorsOf(node: GraphRecord | undefined, byId: Map<string, GraphRecord>): GraphRecord[] {
  const ancestors: GraphRecord[] = [];
  let current = node;
  const visited = new Set<string>();
  while (current) {
    const parentId = textValue(current, "parent_id");
    if (!parentId || visited.has(parentId)) {
      break;
    }
    visited.add(parentId);
    const parent = byId.get(parentId);
    if (!parent) {
      break;
    }
    ancestors.unshift(parent);
    current = parent;
  }
  return ancestors;
}

function groupByChapter(items: WrongQuestionBookItem[]): WrongQuestionBookChapter[] {
  const chapters = new Map<string, WrongQuestionBookChapter>();
  for (const item of items) {
    const chapter = chapters.get(item.chapterId) || {
      chapterId: item.chapterId,
      chapterTitle: item.chapterTitle,
      sections: []
    };
    let section = chapter.sections.find((entry) => entry.sectionId === item.sectionId);
    if (!section) {
      section = {
        sectionId: item.sectionId,
        sectionTitle: item.sectionTitle,
        items: []
      };
      chapter.sections.push(section);
    }
    section.items.push(item);
    chapters.set(item.chapterId, chapter);
  }
  return [...chapters.values()];
}

function resolvedQuestionMap(events: LearningProfileEvent[]): Map<string, string> {
  const resolved = new Map<string, string>();
  for (const event of events) {
    if (event.event_type !== "assessment_submitted") {
      continue;
    }
    const payload = objectValue(event.event_payload);
    const redo = objectValue(payload.wrong_question_redo);
    const detailRedo = parseJsonObject(event.detail);
    const questionIds = [
      ...stringArrayValue(redo.resolved_question_ids),
      ...stringArrayValue(detailRedo.resolved_question_ids)
    ];
    for (const id of questionIds) {
      resolved.set(id, event.created_at);
    }
  }
  return resolved;
}

function isQuizAnswerCorrect(answer: GraphRecord): boolean {
  const selectedIndex = integerValue(answer.selected_answer_index);
  const correctIndex = integerValue(answer.correct_answer_index);
  if (correctIndex !== undefined) {
    return selectedIndex === correctIndex;
  }
  return booleanValue(answer.correct);
}

function parseJsonObject(value: string): GraphRecord {
  if (!value.trim().startsWith("{")) {
    return {};
  }
  try {
    return objectValue(JSON.parse(value));
  } catch {
    return {};
  }
}

function inferChapterTitle(text: string): string {
  const match = text.match(/第\s*\d+\s*章[^/\\|，。]*/);
  return match?.[0] || "未归类章节";
}

function nodeName(node: GraphRecord | undefined, fallback: string): string {
  return textValue(node, "name", textValue(node, "label", fallback));
}

function isNodeType(node: GraphRecord | undefined, expected: string): boolean {
  const type = textValue(node, "node_type", textValue(node, "type")).toLowerCase();
  return type === expected;
}

function normalizeOutput(value: string): string {
  return value.replace(/\r\n/g, "\n").trim();
}

function textValue(record: GraphRecord | undefined, key: string, fallback = ""): string {
  const value = record?.[key];
  return typeof value === "string" ? value : fallback;
}

function objectValue(value: unknown): GraphRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as GraphRecord : {};
}

function arrayValue(value: unknown): GraphRecord[] {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") as GraphRecord[] : [];
}

function stringArrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function booleanValue(value: unknown): boolean {
  return value === true;
}

function integerValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) ? value : undefined;
}

function optionLabel(options: string[], index: number | undefined, fallback: string): string {
  if (index === undefined) {
    return fallback;
  }
  return options[index] || `第 ${index + 1} 项`;
}
