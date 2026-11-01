import type { Resource, StudentProfile, LearningPath } from "./client";

export type AgentArtsMode = "agentarts" | "local";

export interface AgentArtsHistoryMessage {
  role: string;
  content: string;
}

export interface AgentArtsStreamEvent {
  event: string;
  data: Record<string, unknown>;
  profile?: StudentProfile;
  resources?: Resource[];
  learning_path?: LearningPath;
}

export interface AgentArtsStreamHandlers {
  onDelta?: (chunk: string) => void;
  onEvent?: (event: AgentArtsStreamEvent) => void;
  onError?: (error: Error) => void;
  onDone?: () => void;
}

export interface AgentArtsStreamOptions {
  token: string;
  message: string;
  courseId?: number;
  nodeId?: string;
  history?: AgentArtsHistoryMessage[];
  signal?: AbortSignal;
  reconnectLimit?: number;
  timeoutMs?: number;
}

const STORAGE_KEY = "pla_runtime_mode";

export function loadRuntimeMode(): AgentArtsMode {
  return localStorage.getItem(STORAGE_KEY) === "agentarts" ? "agentarts" : "local";
}

export function saveRuntimeMode(mode: AgentArtsMode): void {
  localStorage.setItem(STORAGE_KEY, mode);
}

function extractDelta(payload: Record<string, unknown>): string {
  const choices = payload.choices;
  if (Array.isArray(choices)) {
    const first = choices[0] as { delta?: { content?: string }; message?: { content?: string } } | undefined;
    return first?.delta?.content ?? first?.message?.content ?? "";
  }
  if (typeof payload.delta === "string") {
    return payload.delta;
  }
  if (typeof payload.content === "string" && payload.event === undefined) {
    return payload.content;
  }
  return "";
}

function toStreamEvent(eventName: string, payload: Record<string, unknown>): AgentArtsStreamEvent {
  return {
    event: eventName || String(payload.event ?? "message"),
    data: payload,
    profile: payload.profile as StudentProfile | undefined,
    resources: payload.resources as Resource[] | undefined,
    learning_path: payload.learning_path as LearningPath | undefined,
  };
}

async function consumeStream(
  response: Response,
  handlers: AgentArtsStreamHandlers
): Promise<void> {
  if (!response.body) {
    throw new Error("浏览器不支持流式响应体");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const dispatchFrame = (frame: string): void => {
    let eventName = "message";
    const dataLines: string[] = [];
    for (const rawLine of frame.split("\n")) {
      const line = rawLine.replace(/\r$/, "");
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (dataLines.length === 0) {
      return;
    }
    const raw = dataLines.join("\n");
    if (raw === "[DONE]") {
      handlers.onDone?.();
      return;
    }
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      if (eventName === "error" || parsed.error) {
        const detail = parsed.error as { message?: string } | undefined;
        throw new Error(detail?.message || "AgentArts 流式返回错误");
      }
      const delta = extractDelta(parsed);
      if (delta) {
        handlers.onDelta?.(delta);
      }
      if (parsed.event || parsed.profile || parsed.resources || parsed.learning_path) {
        handlers.onEvent?.(toStreamEvent(eventName, parsed));
      }
    } catch (caught) {
      if (caught instanceof SyntaxError) {
        handlers.onDelta?.(raw);
      } else {
        throw caught;
      }
    }
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      if (buffer.trim()) {
        dispatchFrame(buffer);
      }
      handlers.onDone?.();
      return;
    }
    buffer += decoder.decode(value, { stream: true });
    let separator: number;
    while ((separator = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      if (frame.trim()) {
        dispatchFrame(frame);
      }
    }
  }
}

export async function streamAgentArtsChat(
  options: AgentArtsStreamOptions,
  handlers: AgentArtsStreamHandlers
): Promise<void> {
  const maxAttempts = (options.reconnectLimit ?? 2) + 1;
  let attempt = 0;

  while (attempt < maxAttempts) {
    if (options.signal?.aborted) {
      throw new DOMException("用户中止了请求", "AbortError");
    }
    try {
      const controller = new AbortController();
      const timeoutId = globalThis.setTimeout(
        () => controller.abort(),
        options.timeoutMs ?? 60000
      );
      const onAbort = (): void => controller.abort();
      options.signal?.addEventListener("abort", onAbort);

      const response = await fetch("/api/agentarts/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${options.token}`,
        },
        body: JSON.stringify({
          message: options.message,
          course_id: options.courseId,
          node_id: options.nodeId,
          history: options.history,
        }),
        signal: controller.signal,
      });

      globalThis.clearTimeout(timeoutId);
      options.signal?.removeEventListener("abort", onAbort);

      if (!response.ok) {
        if (response.status === 503) {
          throw new Error("AgentArts 模式尚未配置，请先使用本地模式或联系后端同学");
        }
        throw new Error(`AgentArts 请求失败：HTTP ${response.status}`);
      }
      await consumeStream(response, handlers);
      return;
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        if (options.signal?.aborted) {
          throw caught;
        }
      }
      attempt += 1;
      if (attempt >= maxAttempts) {
        const error = caught instanceof Error ? caught : new Error(String(caught));
        handlers.onError?.(error);
        throw error;
      }
      await new Promise((resolve) => globalThis.setTimeout(resolve, 500 * 2 ** attempt));
    }
  }
}
