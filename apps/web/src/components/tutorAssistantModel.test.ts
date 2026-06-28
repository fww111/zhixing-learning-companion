import { listCourses, sendTutorMessage, type TutorChatResponse } from "../api/client.js";
import {
  agentStageState,
  appendVoiceTranscript,
  courseIdAvailableInCourses,
  createTutorImageAttachment,
  extractTutorContextFromPath,
  speechRecognitionAvailable,
  shouldDisplayTutorRagEvidence,
  shouldDisplayTutorStructuredCards,
  tutorSendDisabledReason,
  type TutorWorkbenchMessage
} from "./tutorAssistantModel.js";

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

async function testAsync(name: string, fn: () => Promise<void>) {
  try {
    await fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

test("tutor response type exposes closed-loop workbench fields", () => {
  const response: TutorChatResponse = {
    answer: "回答",
    agent_events: [{ event: "analysis_completed", agent: "TutorAnalysisAgent", summary: "done", status: "completed", detail: {} }],
    analysis_plan: { course_id: 1 },
    retrieval_trace: [],
    graph_constraints: {},
    evidence_chunks: [],
    verification_report: { decision: "fallback" },
    decision_report: { decision: "fallback", next_action: "ask_for_more_context" },
    multimodal_cards: [{ type: "text_explanation", title: "讲解", content: "回答", payload: {} }],
    suggested_actions: [],
  };

  assert(response.agent_events[0].agent === "TutorAnalysisAgent", "agent event should be typed");
  assert(response.multimodal_cards[0].type === "text_explanation", "multimodal card should be typed");
});

test("tutor answer hides raw RAG evidence cards by default", () => {
  assert(!shouldDisplayTutorRagEvidence(), "floating tutor should not show raw RAG evidence after the answer");
});

test("tutor answer hides structured explanation and graph/evidence cards by default", () => {
  assert(!shouldDisplayTutorStructuredCards(), "floating tutor should only show the natural language answer, not structured cards");
});

test("tutor api client exports send function", () => {
  assert(typeof sendTutorMessage === "function", "sendTutorMessage should be exported");
});

await testAsync("tutor api client times out stalled requests", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = ((_input: RequestInfo | URL, init?: RequestInit) => {
    return new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => {
        reject(new DOMException("aborted", "AbortError"));
      });
    });
  }) as typeof fetch;

  try {
    let message = "";
    try {
      await sendTutorMessage("token", { course_id: 1, message: "解释变量" }, 1);
    } catch (error) {
      message = error instanceof Error ? error.message : String(error);
    }
    assert(message === "智能辅导请求超时，请稍后重试", "stalled tutor requests should fail with a clear timeout message");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

await testAsync("tutor api client allows long-running multimodal RAG answers", async () => {
  const originalFetch = globalThis.fetch;
  const originalSetTimeout = globalThis.setTimeout;
  let observedSignal: AbortSignal | null | undefined;
  const observedTimeouts: number[] = [];
  globalThis.setTimeout = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
    observedTimeouts.push(Number(timeout || 0));
    return originalSetTimeout(handler, timeout, ...args);
  }) as typeof setTimeout;
  globalThis.fetch = ((_input: RequestInfo | URL, init?: RequestInit) => {
    observedSignal = init?.signal;
    return new Promise<Response>((resolve) => {
      globalThis.setTimeout(() => {
        resolve(new Response(JSON.stringify({
          answer: "图片辅导回答",
          agent_events: [],
          analysis_plan: {},
          retrieval_trace: [],
          graph_constraints: {},
          evidence_chunks: [],
          verification_report: {},
          decision_report: {},
          multimodal_cards: [],
          suggested_actions: []
        }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }, 40);
    });
  }) as typeof fetch;

  try {
    const result = await sendTutorMessage("token", {
      course_id: 1,
      message: "这张图片哪里错了？",
      attachments: [{ filename: "error.png", content_type: "image/png", data_url: "data:image/png;base64,AAA" }]
    });
    assert(result.answer === "图片辅导回答", "multimodal tutor request should be allowed to finish");
    assert(observedSignal?.aborted === false, "default tutor timeout should not abort short delayed multimodal requests");
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalSetTimeout;
  }
  assert(observedTimeouts.some((timeout) => timeout >= 120000), "default multimodal tutor timeout should be at least 120 seconds");
});

await testAsync("course list request bypasses browser cache for authenticated course scope", async () => {
  const originalFetch = globalThis.fetch;
  let capturedInit: RequestInit | undefined;
  globalThis.fetch = ((_input: RequestInfo | URL, init?: RequestInit) => {
    capturedInit = init;
    return Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }));
  }) as typeof fetch;

  try {
    await listCourses("token");
    assert(capturedInit?.cache === "no-store", "authenticated course list should not reuse cached courses");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("extracts course, page context, and node id from course routes", () => {
  const learning = extractTutorContextFromPath("/courses/39/knowledge/node-variable", 12);
  assert(learning.courseId === 39, "route course id should win over fallback");
  assert(learning.nodeId === "node-variable", "knowledge route should expose node id");
  assert(learning.pageContext === "learning", "knowledge route should map to learning context");

  const courses = extractTutorContextFromPath("/courses", 12);
  assert(courses.courseId === 12, "courses page should use fallback current course");
  assert(courses.pageContext === "courses", "courses page context should be courses");
});

test("returns clear disabled reasons for missing course and empty input", () => {
  assert(tutorSendDisabledReason(undefined, "解释变量") === "请先选择课程", "missing course should block send");
  assert(tutorSendDisabledReason(1, "   ") === "请输入问题", "empty question should block send");
  assert(tutorSendDisabledReason(1, "解释变量") === "", "valid question should be enabled");
  assert(tutorSendDisabledReason(1, "   ", 1) === "", "image-only question should be enabled");
});

test("rejects stale fallback course ids that are not in the current user's courses", () => {
  const courses = [
    { id: 11, name: "C语言程序设计", description: "built-in:c demo" },
    { id: 22, name: "Python 程序设计", description: "built-in:python demo" },
  ];

  assert(courseIdAvailableInCourses(22, courses), "current user's course id should be available");
  assert(!courseIdAvailableInCourses(1, courses), "stale course id from another user should be rejected");
  assert(!courseIdAvailableInCourses(undefined, courses), "missing course id should not be available");
});

test("agent stages are derived from response events", () => {
  const stages = agentStageState([
    { event: "analysis_completed", agent: "TutorAnalysisAgent", summary: "done", status: "completed", detail: {} },
    { event: "retrieval_completed", agent: "TutorRetrievalAgent", summary: "done", status: "completed", detail: {} },
  ]);

  assert(stages[0].status === "completed", "analysis should be completed");
  assert(stages[1].status === "completed", "retrieval should be completed");
  assert(stages[2].status === "pending", "generation should still be pending");
});

test("workbench message model supports user and assistant messages", () => {
  const message: TutorWorkbenchMessage = { id: "m1", role: "assistant", content: "回答" };
  assert(message.role === "assistant", "assistant role should be valid");
});

test("creates image attachment metadata for tutor questions", () => {
  const attachment = createTutorImageAttachment({ name: "error.png", type: "image/png", size: 2048 }, "img-1");

  assert(attachment.id === "img-1", "image attachment should keep stable id");
  assert(attachment.filename === "error.png", "image attachment should keep filename");
  assert(attachment.content_type === "image/png", "image attachment should keep content type");
  assert(attachment.description.includes("error.png"), "image attachment should describe uploaded image");
  assert(attachment.description.includes("2KB"), "image attachment should include readable size");
});

test("voice transcript appends to existing tutor input", () => {
  assert(appendVoiceTranscript("", " 解释变量 ") === "解释变量", "empty input should become transcript");
  assert(appendVoiceTranscript("先解释规则", "再给例子") === "先解释规则\n再给例子", "transcript should append on a new line");
  assert(appendVoiceTranscript("原内容", "   ") === "原内容", "blank transcript should not change input");
});

test("detects browser speech recognition support", () => {
  assert(speechRecognitionAvailable({ SpeechRecognition: function Recognition() {} }), "standard SpeechRecognition should be supported");
  assert(speechRecognitionAvailable({ webkitSpeechRecognition: function Recognition() {} }), "webkit speech recognition should be supported");
  assert(!speechRecognitionAvailable({}), "missing speech recognition should be unsupported");
});
