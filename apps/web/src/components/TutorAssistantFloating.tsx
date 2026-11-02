import { Bot, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { sendTutorMessage, type Course, type TutorChatResponse } from "../api/client";
import { loadRuntimeMode, streamAgentArtsChat } from "../api/agentarts";
import { useAuth } from "../state/auth";
import { getSharedAttention } from "../state/attentionShared";
import { readCurrentCourseId } from "../state/currentCourse";
import {
  appendVoiceTranscript,
  courseIdAvailableInCourses,
  createTutorImageAttachment,
  extractTutorContextFromPath,
  readTutorImageDataUrl,
  speechRecognitionAvailable,
  type TutorAttachmentDraft,
  type TutorWorkbenchMessage
} from "./tutorAssistantModel";
import { TutorAssistantPanel } from "./TutorAssistantPanel";

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal?: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

interface TutorAssistantFloatingProps {
  courses: Course[];
  activeCourseId?: number;
  /** 外部（学习状态介入）触发打开的信号：数字递增表示打开一次 */
  openSignal?: number;
  /** 介入触发时预填并自动发送的消息 */
  interventionMessage?: string;
}

export function TutorAssistantFloating({ courses, activeCourseId, openSignal = 0, interventionMessage = "" }: TutorAssistantFloatingProps) {
  const { token, user } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<TutorWorkbenchMessage[]>([]);
  const [response, setResponse] = useState<TutorChatResponse | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mediaNotice, setMediaNotice] = useState("");
  const [attachments, setAttachments] = useState<TutorAttachmentDraft[]>([]);
  const [listening, setListening] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const context = useMemo(
    () => {
      const routeContext = extractTutorContextFromPath(location.pathname, activeCourseId ?? readCurrentCourseId());
      if (!courseIdAvailableInCourses(routeContext.courseId, courses)) {
        return { ...routeContext, courseId: undefined };
      }
      return routeContext;
    },
    [activeCourseId, courses, location.pathname]
  );
  const courseName = courses.find((course) => course.id === context.courseId)?.name ?? "";

  useEffect(() => {
    if (openSignal > 0) {
      setOpen(true);
    }
  }, [openSignal]);

  useEffect(() => {
    if (interventionMessage && open && context.courseId && !loading) {
      setInput(interventionMessage);
    }
  }, [interventionMessage, open, context.courseId, loading]);

  if (!user) {
    return null;
  }

  /** AgentArts 模式：经后端代理走平台应用 API（SSE 流式），平台未配置时后端返回 503 提示切回本地模式 */
  async function sendViaAgentArts(content: string) {
    const userMessage: TutorWorkbenchMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content
    };
    setMessages((items) => [...items, userMessage]);
    setLoading(true);
    setError("");
    const streamId = `assistant-stream-${Date.now()}`;
    let accumulated = "";
    try {
      await streamAgentArtsChat(
        {
          token,
          message: content,
          courseId: context.courseId,
          nodeId: context.nodeId,
          history: messages.slice(-6).map((message) => ({ role: message.role, content: message.content }))
        },
        {
          onDelta: (chunk) => {
            accumulated += chunk;
            setMessages((items) => {
              const last = items[items.length - 1];
              if (last && last.id === streamId) {
                return [...items.slice(0, -1), { ...last, content: accumulated }];
              }
              return [...items, { id: streamId, role: "assistant", content: accumulated }];
            });
          }
        }
      );
      if (!accumulated.trim()) {
        setMessages((items) => [...items, {
          id: `assistant-empty-${Date.now()}`,
          role: "assistant",
          content: "（AgentArts 模式未返回内容，可切换回本地模式使用完整功能。）"
        }]);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "AgentArts 请求失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleSend() {
    const content = input.trim() || (attachments.length ? "请结合我上传的图片进行讲解。" : "");
    await sendMessage(content);
  }

  /** 追问选项点击等场景：直接发送指定文本（不经过输入框） */
  async function sendMessage(content: string) {
    if (!context.courseId || !content) {
      return;
    }
    if (loadRuntimeMode() === "agentarts") {
      await sendViaAgentArts(content);
      return;
    }
    const userMessage: TutorWorkbenchMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: attachments.length ? `${content}\n[已上传 ${attachments.length} 张图片]` : content
    };
    setMessages((items) => [...items, userMessage]);
    setLoading(true);
    setError("");
    setMediaNotice("");
    try {
      const outgoingAttachments = attachments.map(({ preview_url: _previewUrl, ...attachment }) => attachment);
      const attention = getSharedAttention();
      const result = await sendTutorMessage(token, {
        course_id: context.courseId,
        message: content,
        node_id: context.nodeId,
        page_context: context.pageContext,
        attachments: outgoingAttachments,
        history: messages.slice(-6).map((message) => ({ role: message.role, content: message.content })),
        attention_state: attention?.state ?? ""
      });
      setResponse(result);
      setMessages((items) => [...items, {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: result.answer,
        followups: result.suggested_followups ?? []
      }]);
      setInput("");
      setAttachments((items) => {
        items.forEach((item) => {
          if (item.preview_url) {
            URL.revokeObjectURL(item.preview_url);
          }
        });
        return [];
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "智能辅导请求失败");
    } finally {
      setLoading(false);
    }
  }

  function handleImageInput() {
    fileInputRef.current?.click();
  }

  async function handleImageSelected(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file) {
      return;
    }
    if (!file.type.startsWith("image/")) {
      setMediaNotice("请选择图片文件，例如 PNG、JPG 或 WebP。");
      return;
    }
    const dataUrl = await readTutorImageDataUrl(file).catch(() => "");
    const attachment = {
      ...createTutorImageAttachment(file, `image-${Date.now()}`),
      preview_url: URL.createObjectURL(file),
      data_url: dataUrl
    };
    setAttachments((items) => {
      items.forEach((item) => {
        if (item.preview_url) {
          URL.revokeObjectURL(item.preview_url);
        }
      });
      return [attachment];
    });
    setMediaNotice(dataUrl
      ? "图片已作为问题附件加入。发送时会结合课程知识库、知识图谱和图片上下文生成增强回答。"
      : "图片已作为问题附件加入。图片较大时会先发送文件信息，建议补充文字描述以便辅导。");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function handleRemoveAttachment(id: string) {
    setAttachments((items) => {
      const removed = items.find((item) => item.id === id);
      if (removed?.preview_url) {
        URL.revokeObjectURL(removed.preview_url);
      }
      return items.filter((item) => item.id !== id);
    });
  }

  function handleVoiceInput() {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      setMediaNotice("已停止语音输入。");
      return;
    }
    if (!speechRecognitionAvailable(window)) {
      setMediaNotice("当前浏览器不支持语音转文字，请使用 Chrome 或 Edge 后再试。");
      return;
    }
    const Recognition = (window.SpeechRecognition || window.webkitSpeechRecognition) as SpeechRecognitionConstructor | undefined;
    if (!Recognition) {
      setMediaNotice("当前浏览器不支持语音转文字，请使用 Chrome 或 Edge 后再试。");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join("")
        .trim();
      setInput((value) => appendVoiceTranscript(value, transcript));
      setMediaNotice(transcript ? "语音已转成文字，可继续编辑后发送。" : "没有识别到有效语音，请再试一次。");
    };
    recognition.onerror = (event) => {
      setListening(false);
      setMediaNotice(`语音输入失败：${event.error || "浏览器未返回具体原因"}`);
    };
    recognition.onend = () => {
      setListening(false);
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
      setListening(true);
      setMediaNotice("正在听写，请说出你的课程问题。");
    } catch (caught) {
      setListening(false);
      setMediaNotice(caught instanceof Error ? `语音输入启动失败：${caught.message}` : "语音输入启动失败");
    }
  }

  return (
    <div className="tutor-floating-root">
      {open ? (
        <TutorAssistantPanel
          context={context}
          courseName={courseName}
          input={input}
          messages={messages}
          response={response}
          loading={loading}
          error={error}
          mediaNotice={mediaNotice}
          attachments={attachments}
          listening={listening}
          onInputChange={setInput}
          onSend={handleSend}
          onClose={() => setOpen(false)}
          onImageInput={handleImageInput}
          onVoiceInput={handleVoiceInput}
          onRemoveAttachment={handleRemoveAttachment}
          onFollowupClick={(text) => { void sendMessage(text); }}
        />
      ) : null}
      <input
        ref={fileInputRef}
        className="tutor-hidden-file"
        type="file"
        accept="image/*"
        onChange={(event) => handleImageSelected(event.target.files)}
      />
      <button className={`tutor-floating-button ${open ? "open" : ""}`} aria-label="打开智能辅导" onClick={() => setOpen((value) => !value)}>
        {open ? <Sparkles size={22} /> : <Bot size={23} />}
        <span>{context.courseId ? "智能辅导" : "选择课程"}</span>
      </button>
    </div>
  );
}
