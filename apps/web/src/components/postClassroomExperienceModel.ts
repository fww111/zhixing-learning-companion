export type PostClassroomStage = "classroom" | "study_artifacts" | "quiz_lab" | "assessment";
export type LessonLearningViewMode = "learn" | "assess";

export const openmaicClassroomIframeAllow = "fullscreen; autoplay; clipboard-write; microphone; camera; display-capture";
export const openmaicQuizEventTypes = [
  "openmaic:quiz-started",
  "openmaic:quiz-submitted",
  "openmaic:quiz-completed",
  "pla:open-assessment"
] as const;

export type OpenMAICQuizEventType = typeof openmaicQuizEventTypes[number];

export interface PersistedLessonStateLike {
  current_stage?: string;
  classroom_completed?: boolean;
  notes_completed?: boolean;
  mind_map_completed?: boolean;
  test_completed?: boolean;
  assessment_completed?: boolean;
}

export const postClassroomStages: PostClassroomStage[] = [
  "classroom",
  "study_artifacts",
  "quiz_lab",
  "assessment"
];

export const learningFlowSteps: Array<{ key: PostClassroomStage; label: string; detail: string }> = [
  { key: "classroom", label: "课程学习", detail: "OpenMAIC 标准课堂完成知识输入" },
  { key: "study_artifacts", label: "文档笔记/思维导图", detail: "文档 Agent 与导图 Agent 生成结构化学习产物" },
  { key: "quiz_lab", label: "题库测试/代码运行", detail: "题库 Agent 与代码 Agent 检查迁移应用能力" },
  { key: "assessment", label: "评估反馈/动态规划", detail: "评估 Agent 更新图谱颜色并触发路径重规划" }
];

export function nextPostClassroomStage(current: PostClassroomStage): PostClassroomStage {
  const index = postClassroomStages.indexOf(current);
  if (index < 0 || index >= postClassroomStages.length - 1) {
    return current;
  }
  return postClassroomStages[index + 1];
}

export function shouldUnlockPostClassroom(status?: string, url?: string, classroomId?: string): boolean {
  const normalized = (status || "").toLowerCase();
  return Boolean(url || classroomId || normalized === "succeeded" || normalized === "completed");
}

export function isOpenMAICQuizEvent(data: unknown): data is { type: OpenMAICQuizEventType } {
  if (!data || typeof data !== "object") {
    return false;
  }
  const type = (data as { type?: unknown }).type;
  return typeof type === "string" && openmaicQuizEventTypes.includes(type as OpenMAICQuizEventType);
}

export function shouldOpenAssessmentForOpenMAICQuizEvent(type: OpenMAICQuizEventType): boolean {
  return type === "openmaic:quiz-completed" || type === "pla:open-assessment";
}

export function lessonViewModeFromState(state?: PersistedLessonStateLike): LessonLearningViewMode {
  if (!state) {
    return "learn";
  }
  if (state.assessment_completed || state.test_completed || state.current_stage === "test" || state.current_stage === "assessment") {
    return "assess";
  }
  return "learn";
}

export function lessonStageLabel(state?: PersistedLessonStateLike): string {
  if (state?.assessment_completed) {
    return "评估完成";
  }
  if (state?.test_completed || state?.current_stage === "assessment") {
    return "测试完成";
  }
  if (state?.current_stage === "test") {
    return "课堂测试";
  }
  if (state?.classroom_completed) {
    return "课堂已完成";
  }
  return "课堂学习";
}

export { shouldPersistLessonStageTransition } from "./lessonStageTransitionModel";

export function runInlinePythonLikeCode(source: string): string {
  const lines = source.split(/\r?\n/);
  const output: string[] = [];
  const variables = new Map<string, string | number>();
  const inputValues: Array<string | number> = defaultInlineInputValues(source);
  let inputIndex = 0;

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const rawLine = lines[lineIndex];
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    if (
      line === "int main() {"
      || line === "int main(){"
      || line === "}"
      || /^return\s+0\s*;?$/.test(line)
    ) {
      continue;
    }

    const printfCall = /^printf\((.*)\);?$/.exec(line);
    if (printfCall) {
      output.push(String(parseExpression(printfCall[1], variables)).replace(/\\n/g, "\n").replace(/\\t/g, "\t"));
      continue;
    }

    const tupleAssignment = /^([a-zA-Z_]\w*)\s*,\s*([a-zA-Z_]\w*)\s*=\s*(.+?)\s*,\s*(.+)$/.exec(line);
    if (tupleAssignment) {
      const leftName = tupleAssignment[1];
      const rightName = tupleAssignment[2];
      const leftValue = parseExpression(tupleAssignment[3], variables, () => inputValues[inputIndex++] ?? "");
      const rightValue = parseExpression(tupleAssignment[4], variables, () => inputValues[inputIndex++] ?? "");
      variables.set(leftName, leftValue);
      variables.set(rightName, rightValue);
      continue;
    }

    const rangeLoop = /^for\s+([a-zA-Z_]\w*)\s+in\s+range\((.+)\):$/.exec(line);
    if (rangeLoop) {
      const loopName = rangeLoop[1];
      const bounds = splitByTopLevelComma(rangeLoop[2]);
      const start = bounds.length > 1 ? Number(parseExpression(bounds[0], variables, () => inputValues[inputIndex++] ?? "")) : 0;
      const end = Number(parseExpression(bounds.length > 1 ? bounds[1] : bounds[0], variables, () => inputValues[inputIndex++] ?? ""));
      const bodyLines: string[] = [];
      while (lineIndex + 1 < lines.length && /^\s+/.test(lines[lineIndex + 1]) && lines[lineIndex + 1].trim()) {
        lineIndex += 1;
        bodyLines.push(lines[lineIndex].trim());
      }
      for (let value = start; value < end; value += 1) {
        variables.set(loopName, value);
        for (const bodyLine of bodyLines) {
          const bodyAssignment = /^([a-zA-Z_]\w*)\s*=\s*(.+)$/.exec(bodyLine);
          if (bodyAssignment) {
            variables.set(bodyAssignment[1], parseExpression(bodyAssignment[2], variables, () => inputValues[inputIndex++] ?? ""));
          }
        }
      }
      continue;
    }

    const assignment = /^([a-zA-Z_]\w*)\s*=\s*(.+)$/.exec(line);
    if (assignment) {
      variables.set(assignment[1], parseExpression(assignment[2], variables, () => inputValues[inputIndex++] ?? ""));
      continue;
    }

    const printCall = /^print\((.*)\)$/.exec(line);
    if (printCall) {
      output.push(String(parseExpression(printCall[1], variables, () => inputValues[inputIndex++] ?? "")));
      continue;
    }

    const inputCall = /^input\((.*)\)$/.exec(line);
    if (inputCall) {
      if (inputCall[1].trim()) {
        output.push(String(parseExpression(inputCall[1], variables, () => inputValues[inputIndex] ?? "")));
      }
      output.push(String(inputValues[inputIndex++] ?? ""));
      continue;
    }

    output.push(`暂不支持的语句：${line}`);
  }

  return output.length ? output.join("\n").trim() : "代码已运行，没有输出。";
}

export function isInlineCodeRunSuccessful(output: string): boolean {
  const normalized = output.trim();
  return Boolean(normalized && !normalized.includes("暂不支持的语句") && normalized !== "代码已运行，没有输出。");
}

function parseExpression(
  expression: string,
  variables: Map<string, string | number>,
  nextInput: () => string | number = () => ""
): string | number {
  const trimmed = expression.trim();
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  const intCall = /^int\((.*)\)$/.exec(trimmed);
  if (intCall) {
    const value = String(parseExpression(intCall[1], variables, nextInput)).trim();
    const numeric = Number.parseInt(value, 10);
    return Number.isNaN(numeric) ? 0 : numeric;
  }
  const inputCall = /^input\((.*)\)$/.exec(trimmed);
  if (inputCall) {
    return nextInput();
  }
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
    return Number(trimmed);
  }
  const fString = /^f(["'])(.*)\1$/.exec(trimmed);
  if (fString) {
    return fString[2].replace(/\{([a-zA-Z_]\w*)\}/g, (_, name: string) => String(variables.get(name) ?? ""));
  }
  if (variables.has(trimmed)) {
    return variables.get(trimmed) ?? "";
  }

  const plusParts = splitByTopLevelPlus(trimmed);
  if (plusParts.length > 1) {
    const values = plusParts.map((part) => parseExpression(part, variables, nextInput));
    if (values.every((value) => typeof value === "number")) {
      return (values as number[]).reduce((sum, value) => sum + value, 0);
    }
    return values.map(String).join("");
  }

  return trimmed;
}

function splitByTopLevelPlus(expression: string): string[] {
  return splitByTopLevelDelimiter(expression, "+");
}

function defaultInlineInputValues(source: string): Array<string | number> {
  if (/for\s+[a-zA-Z_]\w*\s+in\s+range\(/.test(source) && !/\bnum1\b/.test(source) && !/\bnum2\b/.test(source)) {
    return [5, 3, 8, "Alice"];
  }
  return [3, 8, "Alice"];
}

function splitByTopLevelComma(expression: string): string[] {
  return splitByTopLevelDelimiter(expression, ",");
}

function splitByTopLevelDelimiter(expression: string, delimiter: string): string[] {
  const parts: string[] = [];
  let quote = "";
  let start = 0;
  let depth = 0;
  for (let index = 0; index < expression.length; index += 1) {
    const char = expression[index];
    if ((char === '"' || char === "'") && expression[index - 1] !== "\\") {
      quote = quote === char ? "" : quote || char;
    }
    if (!quote && char === "(") {
      depth += 1;
    }
    if (!quote && char === ")") {
      depth = Math.max(0, depth - 1);
    }
    if (char === delimiter && !quote && depth === 0) {
      parts.push(expression.slice(start, index).trim());
      start = index + 1;
    }
  }
  parts.push(expression.slice(start).trim());
  return parts.filter(Boolean);
}
