import type { TutorAgentEvent } from "../api/client";

export interface TutorCourseRef {
  id: number;
}

export type TutorPageContext = "courses" | "profile" | "knowledge_base" | "graph" | "learning_path" | "learning" | "assessment" | "unknown";

export interface TutorRouteContext {
  courseId?: number;
  nodeId: string;
  pageContext: TutorPageContext;
}

export interface TutorWorkbenchMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  /** issue #16：assistant 消息附带的追问选项（最后一条 assistant 消息可点） */
  followups?: string[];
}

export interface TutorAttachmentDraft {
  id: string;
  filename: string;
  content_type: string;
  description: string;
  preview_url?: string;
  data_url?: string;
}

export interface TutorStageView {
  agent: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  summary: string;
}

const STAGES: Array<{ agent: string; label: string }> = [
  { agent: "TutorAnalysisAgent", label: "分析" },
  { agent: "TutorRetrievalAgent", label: "检索" },
  { agent: "TutorGeneratorAgent", label: "生成" },
  { agent: "TutorVerifierAgent", label: "校验" },
  { agent: "TutorDecisionAgent", label: "决策" },
];

export function extractTutorContextFromPath(pathname: string, fallbackCourseId?: number): TutorRouteContext {
  const courseMatch = pathname.match(/\/courses\/(\d+)/);
  const courseId = courseMatch ? Number(courseMatch[1]) : fallbackCourseId;
  const knowledgeMatch = pathname.match(/\/courses\/\d+\/knowledge\/([^/?#]+)/);
  return {
    courseId,
    nodeId: knowledgeMatch ? decodeURIComponent(knowledgeMatch[1]) : "",
    pageContext: pageContextFromPath(pathname),
  };
}

export function pageContextFromPath(pathname: string): TutorPageContext {
  if (pathname === "/courses") {
    return "courses";
  }
  if (pathname.includes("/profile/interview")) {
    return "profile";
  }
  if (pathname.includes("/knowledge-base")) {
    return "knowledge_base";
  }
  if (pathname.includes("/graph")) {
    return "graph";
  }
  if (pathname.includes("/learning-path")) {
    return "learning_path";
  }
  if (pathname.includes("/knowledge/")) {
    return "learning";
  }
  if (pathname.includes("/assessment")) {
    return "assessment";
  }
  return "unknown";
}

export function tutorSendDisabledReason(courseId: number | undefined, message: string, attachmentCount = 0): string {
  if (!courseId) {
    return "请先选择课程";
  }
  if (!message.trim() && attachmentCount <= 0) {
    return "请输入问题";
  }
  return "";
}

export function courseIdAvailableInCourses(courseId: number | undefined, courses: TutorCourseRef[]): boolean {
  return Boolean(courseId && courses.some((course) => course.id === courseId));
}

export function agentStageState(events: TutorAgentEvent[]): TutorStageView[] {
  return STAGES.map((stage) => {
    const event = events.find((item) => item.agent === stage.agent);
    return {
      agent: stage.agent,
      label: stage.label,
      status: event?.status ?? "pending",
      summary: event?.summary ?? "等待执行",
    };
  });
}

export function shouldDisplayTutorRagEvidence(): boolean {
  return false;
}

export function shouldDisplayTutorStructuredCards(): boolean {
  return false;
}

export function createTutorImageAttachment(file: { name: string; type: string; size: number }, id = `image-${Date.now()}`): TutorAttachmentDraft {
  return {
    id,
    filename: file.name || "未命名图片",
    content_type: file.type || "image/*",
    description: `用户上传图片：${file.name || "未命名图片"}，文件大小 ${formatBytes(file.size)}。请结合图片内容、当前页面和文字问题进行课程辅导。`,
  };
}

export async function readTutorImageDataUrl(file: File, maxBytes = 512 * 1024): Promise<string> {
  if (file.size > maxBytes) {
    return "";
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(reader.error ?? new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

export function appendVoiceTranscript(currentInput: string, transcript: string): string {
  const normalizedTranscript = transcript.trim();
  if (!normalizedTranscript) {
    return currentInput;
  }
  const normalizedInput = currentInput.trim();
  return normalizedInput ? `${normalizedInput}\n${normalizedTranscript}` : normalizedTranscript;
}

export function speechRecognitionAvailable(scope: unknown = globalThis): boolean {
  if (!scope || typeof scope !== "object") {
    return false;
  }
  const candidate = scope as Record<string, unknown>;
  return typeof candidate.SpeechRecognition === "function" || typeof candidate.webkitSpeechRecognition === "function";
}

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size <= 0) {
    return "未知";
  }
  if (size < 1024) {
    return `${Math.round(size)}B`;
  }
  if (size < 1024 * 1024) {
    return `${Math.round(size / 1024)}KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)}MB`;
}
