import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { Bot, Image as ImageIcon, Mic, MicOff, Send, Volume2, VolumeX, Loader2, Sparkles , AudioLines, AudioWaveform, CircleStop } from "lucide-react";
import {
  sendTutorMessage,
  startTutorVoiceSession,
  type TutorAttachment,
} from "../api/client";
import {
  createTutorImageAttachment,
  readTutorImageDataUrl,
  speechRecognitionAvailable,
  type TutorAttachmentDraft,
} from "../components/tutorAssistantModel";
import { loadRuntimeMode, streamAgentArtsChat } from "../api/agentarts";
import { useRealtimeVoice } from "../composables/useRealtimeVoice";
import { getSharedAttention } from "../state/attentionShared";
import { useAuth } from "../state/auth";

type StageMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  imageUrl?: string;
  followups?: string[];
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

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

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

function textValue(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

const REALTIME_PHASE_LABELS: Record<string, string> = {
  idle: "未连接",
  connecting: "连接中",
  listening: "聆听中",
  thinking: "思考中",
  speaking: "播报中"
};

/** 全屏 AI 对话大屏（issue：多模态对话界面）：文字 + 语音输入 + 图片多模态 + 回答语音朗读。 */
export function TutorStagePage() {
  const { courseId, nodeId } = useParams();
  const location = useLocation();
  const { token, user } = useAuth();
  const numericCourseId = Number(courseId);
  const decodedNodeId = decodeURIComponent(nodeId || "");
  const mode = loadRuntimeMode();

  const [messages, setMessages] = useState<StageMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [attachments, setAttachments] = useState<TutorAttachmentDraft[]>([]);
  const [listening, setListening] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  // 连续语音对话模式：持续听写 -> 句尾自动发送 -> AI 回答自动开口讲 -> 说话时打断朗读
  const [voiceConversation, setVoiceConversation] = useState(false);
  // 真·实时双向语音（issue #21）：AudioWorklet 采集 + Fun-ASR + 豆包流式 TTS，可打断
  const [realtimeVoice, setRealtimeVoice] = useState(false);
  const [voiceSessionToken, setVoiceSessionToken] = useState("");
  const realtime = useRealtimeVoice({
    token,
    voiceSession: realtimeVoice ? voiceSessionToken : undefined,
    onUserFinal: (text) => {
      setMessages((items) => [...items, { id: `voice-user-${Date.now()}`, role: "user", content: text }]);
    },
    onAssistantFinal: (content) => {
      appendAssistant(`voice-assistant-${Date.now()}`, content);
    }
  });

  async function toggleRealtimeVoice() {
    if (realtimeVoice) {
      realtime.stop();
      setRealtimeVoice(false);
      return;
    }
    if (!Number.isFinite(numericCourseId) || !token) {
      setNotice("请先进入具体课程后再使用实时语音。");
      return;
    }
    try {
      const session = await startTutorVoiceSession(token, numericCourseId, decodedNodeId);
      setVoiceSessionToken(session.voice_session);
      setRealtimeVoice(true);
      await realtime.start();
      setNotice("实时语音已开启：直接说话提问，AI 开口回答；播报中点击「打断」可随时插话。");
    } catch (caught) {
      setRealtimeVoice(false);
      setError(caught instanceof Error ? caught.message : "实时语音启动失败");
    }
  }
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const attention = getSharedAttention();
  const courseLabel = textValue(
    new URLSearchParams(location.search).get("course"),
    "当前课程"
  );
  const nodeLabel = useMemo(() => decodedNodeId || "当前知识点", [decodedNodeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => () => recognitionRef.current?.stop(), []);

  function appendAssistant(id: string, content: string, followups?: string[]) {
    setMessages((items) => {
      const last = items[items.length - 1];
      if (last && last.id === id) {
        return [...items.slice(0, -1), { ...last, content, followups }];
      }
      return [...items, { id, role: "assistant", content, followups }];
    });
  }

  const audioRef = useRef<HTMLAudioElement | null>(null);

  function stopSpeak(): void {
    audioRef.current?.pause();
    audioRef.current = null;
    window.speechSynthesis?.cancel();
  }

  /** 真人音色朗读：后端 edge-tts 合成 mp3（Natural neural voice），支持打断 */
  async function speak(text: string): Promise<void> {
    if ((!ttsEnabled && !voiceConversation) || !text.trim()) return;
    const clean = text.replace(/[#*`>\-|]/g, " ").replace(/chunk#\d+/g, "教材依据").slice(0, 1200);
    stopSpeak();
    try {
      // 优先：后端 edge-tts 真人神经网络音色
      const res = await fetch("/api/tts/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text: clean })
      });
      if (!res.ok) throw new Error("edge tts unavailable");
      const blob = await res.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      audioRef.current = audio;
      await audio.play();
    } catch {
      // 降级：edge-tts 不可用（网络/服务）时回退浏览器合成音，保证有声音
      if (typeof window.speechSynthesis === "undefined") return;
      const utterance = new SpeechSynthesisUtterance(clean.replace(/教材依据/g, "").slice(0, 500));
      utterance.lang = "zh-CN";
      utterance.rate = 1.05;
      window.speechSynthesis.speak(utterance);
    }
  }

  async function sendMessage(content: string, imageAttachments: TutorAttachmentDraft[] = []) {
    if (!Number.isFinite(numericCourseId) || !content.trim()) return;
    const outgoing = imageAttachments.map(({ preview_url: _p, ...rest }) => rest);
    const displayImages = imageAttachments
      .filter((item) => item.preview_url)
      .map((item) => item.preview_url as string);

    setMessages((items) => [
      ...items,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content: outgoing.length ? `${content}\n[已上传 ${outgoing.length} 张图片]` : content,
        imageUrl: displayImages[0]
      }
    ]);
    setLoading(true);
    setError("");
    const attention = getSharedAttention();
    const history = messages.slice(-6).map((message) => ({ role: message.role, content: message.content }));
    const followupId = `assistant-${Date.now()}`;

    try {
      if (mode === "agentarts") {
        let accumulated = "";
        await streamAgentArtsChat(
          {
            token,
            message: outgoing.length ? `${content}（附图片，请结合图片讲解）` : content,
            courseId: numericCourseId,
            nodeId: decodedNodeId,
            history
          },
          {
            onDelta: (chunk) => {
              accumulated += chunk;
              appendAssistant(followupId, accumulated);
            }
          }
        );
        if (!accumulated.trim()) {
          appendAssistant(followupId, "（AgentArts 模式未返回内容，可切换回本地模式。）");
        }
        speak(accumulated);
        return;
      }

      const result = await sendTutorMessage(token, {
        course_id: numericCourseId,
        message: content,
        node_id: decodedNodeId,
        page_context: `tutor-stage:${nodeLabel}`,
        attachments: outgoing,
        history,
        attention_state: attention?.state ?? ""
      });
      const fullText = result.answer;
      appendAssistant(followupId, fullText, result.suggested_followups ?? []);
      speak(fullText);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "请求失败，请稍后再试");
    } finally {
      setLoading(false);
    }
  }

  function handleSend() {
    const content = input.trim() || (attachments.length ? "请结合我上传的图片进行讲解。" : "");
    const pending = attachments;
    setInput("");
    setAttachments([]);
    void sendMessage(content, pending);
  }

  function handleFollowup(text: string) {
    void sendMessage(text);
  }

  async function handleImageSelected(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file || !file.type.startsWith("image/")) {
      setNotice("请选择图片文件（PNG/JPG/WebP）。");
      return;
    }
    const dataUrl = await readTutorImageDataUrl(file).catch(() => "");
    const draft = {
      ...createTutorImageAttachment(file, `image-${Date.now()}`),
      preview_url: URL.createObjectURL(file),
      data_url: dataUrl
    };
    setAttachments([draft]);
    setNotice(
      dataUrl
        ? "图片已就绪：发送后将结合课程知识库与图片内容讲解。"
        : "图片较大，将以文件信息发送，建议补充文字描述。"
    );
  }

  function handleVoiceInput() {  // eslint-disable-line
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const Recognition = (window.SpeechRecognition || window.webkitSpeechRecognition) as
      | SpeechRecognitionConstructor
      | undefined;
    if (!Recognition) {
      setNotice("当前浏览器不支持语音转文字，请使用 Chrome 或 Edge。");
      return;
    }
    const conversationMode = voiceConversation;
    const recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.continuous = conversationMode;   // 对话模式：持续听
    recognition.interimResults = true;           // 实时上屏中间结果
    recognition.onresult = (event) => {
      let finalText = "";
      let interim = "";
      for (let i = event.results.length - 1; i >= 0; i -= 1) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? "";
        if (result.isFinal) { finalText = text + finalText; break; }
        interim = text + interim;
      }
      if (conversationMode) {
        setInput((value) => (value ? `${value} ${finalText || interim}`.trim() : (finalText || interim)));
        // 句尾自动发送：讲题对话衔接关键
        if (finalText && finalText.trim().length >= 2) {
          const content = finalText.trim();
          setInput("");
          window.setTimeout(() => void sendMessage(content), 350);
        }
      } else {
        setInput((value) => (value ? `${value} ${finalText || interim}`.trim() : (finalText || interim)));
        setNotice(finalText || interim ? `语音：${finalText || interim}（单次模式）` : "没有识别到有效语音，请再试一次。");
      }
    };
    recognition.onerror = (event) => {
      setListening(false);
      setNotice(`语音输入失败：${event.error || "未知原因"}`);
    };
    recognition.onend = () => {
      setListening(false);
      // 对话模式：浏览器静音超时断开后自动续听，保持"始终在听"
      if (conversationMode) {
        window.setTimeout(() => handleVoiceInput(), 400);
      }
    };
    recognitionRef.current = recognition;
    try {
      stopSpeak();   // 用户开口即打断 AI 朗读（自然对话体验）
      recognition.start();
      setListening(true);
      setNotice(voiceConversation ? "语音对话中：说完一句自动发送，AI 会开口回答。" : "正在听写，请说出你的问题。");
    } catch (caught) {
      setListening(false);
      setNotice(caught instanceof Error ? `语音输入启动失败：${caught.message}` : "语音输入启动失败");
    }
  }

  if (!user) {
    return <div className="route-loading">请先登录后使用对话大屏。</div>;
  }

  return (
    <div className="page-stack tutor-stage">
      <div className="page-heading with-actions product-page-heading">
        <div>
          <span>AI Tutoring Stage</span>
          <h2>AI 对话大屏 · {nodeLabel}</h2>
          <p>
            文字、语音、拍照多模态提问；结合课程知识库与知识图谱作答，标注教材依据。
            {attention ? ` 当前学习状态：${attention.state}。` : " 开启左下角学习状态感知，AI 能感知你的困惑并主动换讲法。"}
            {mode === "agentarts" ? "（当前为 AgentArts 模式）" : ""}
          </p>
        </div>
        <div className="header-actions">
          <button
            className={`secondary-action compact-button ${voiceConversation ? "voice-live" : ""}`}
            onClick={() => {
              setVoiceConversation((value) => {
                const next = !value;
                if (!next) {
                  recognitionRef.current?.stop();
                  setListening(false);
                  stopSpeak();
                } else {
                  setTtsEnabled(true);
                  window.setTimeout(() => handleVoiceInput(), 100);
                }
                return next;
              });
            }}
            type="button"
          >
            {voiceConversation ? <Mic size={16} /> : <MicOff size={16} />}
            {voiceConversation ? "语音对话中（说话即提问，AI 开口讲）" : "开始语音对话"}
          </button>
          <button
            className="secondary-action compact-button"
            onClick={() => {
              setTtsEnabled((value) => !value);
              if (ttsEnabled) stopSpeak();
            }}
            type="button"
          >
            {ttsEnabled ? <Volume2 size={16} /> : <VolumeX size={16} />}
            {ttsEnabled ? "朗读开" : "朗读关"}
          </button>
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <section className="tutor-stage-stream panel">
        {messages.length === 0 ? (
          <div className="tutor-stage-empty">
            <Sparkles size={26} />
            <strong>和 AI 开始一对一学习</strong>
            <span>
              试着问："贪心算法是什么？"、"给一个可运行的 C++ 例子"、
              或直接上传题目图片。打开左下角摄像头，AI 还能感知你的困惑主动换讲法。
            </span>
          </div>
        ) : (
          messages.map((message) => (
            <article className={`tutor-stage-message ${message.role}`} key={message.id}>
              <div className="tutor-stage-avatar">{message.role === "user" ? "我" : "AI"}</div>
              <div className="tutor-stage-bubble">
                {message.imageUrl ? (
                  <img alt="上传的题目" className="tutor-stage-image" src={message.imageUrl} />
                ) : null}
                <p>{message.content}</p>
                {message.role === "assistant" && message.followups?.length && !loading ? (
                  <div className="tutor-followups">
                    {message.followups.map((item) => (
                      <button key={item} onClick={() => handleFollowup(item)} type="button">
                        {item}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </article>
          ))
        )}
        {loading ? (
          <article className="tutor-stage-message assistant">
            <div className="tutor-stage-avatar"><Bot size={16} /></div>
            <div className="tutor-stage-bubble">
              <Loader2 className="spin" size={16} /> 正在结合课程知识库思考…
            </div>
          </article>
        ) : null}
        <div ref={bottomRef} />
      </section>

      <section className="tutor-stage-composer panel">
        {attachments.length ? (
          <div className="tutor-stage-attachments">
            {attachments.map((item) => (
              <img alt="附件预览" key={item.id} src={item.preview_url} />
            ))}
            <button onClick={() => setAttachments([])} type="button">移除图片</button>
          </div>
        ) : null}
        <div className="tutor-stage-input-row">
          <button aria-label="上传图片" className="icon-action" onClick={() => fileInputRef.current?.click()} type="button">
            <ImageIcon size={18} />
          </button>
          <button
            aria-label={listening ? "停止听写" : "语音输入"}
            className={`icon-action ${listening ? "listening" : ""}`}
            onClick={handleVoiceInput}
            type="button"
          >
            {listening ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
          <textarea
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSend();
              }
            }}
            placeholder="输入问题，或点左侧图标上传图片 / 语音提问（Enter 发送）"
            rows={2}
            value={input}
          />
          <button className="primary-action compact-button" disabled={loading} onClick={handleSend} type="button">
            {loading ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
            发送
          </button>
        </div>
        <input
          accept="image/*"
          onChange={(event) => void handleImageSelected(event.target.files)}
          ref={fileInputRef}
          style={{ display: "none" }}
          type="file"
        />
      </section>
    </div>
  );
}

export type { TutorAttachment as TutorStageAttachment };
