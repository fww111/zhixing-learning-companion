import { Image, Mic, Send, Sparkles, X } from "lucide-react";
import type { TutorChatResponse } from "../api/client";
import {
  agentStageState,
  shouldDisplayTutorRagEvidence,
  shouldDisplayTutorStructuredCards,
  tutorSendDisabledReason,
  type TutorAttachmentDraft,
  type TutorRouteContext,
  type TutorWorkbenchMessage
} from "./tutorAssistantModel";

interface TutorAssistantPanelProps {
  context: TutorRouteContext;
  courseName: string;
  input: string;
  messages: TutorWorkbenchMessage[];
  response?: TutorChatResponse;
  loading: boolean;
  error: string;
  mediaNotice: string;
  attachments: TutorAttachmentDraft[];
  listening: boolean;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onClose: () => void;
  onImageInput: () => void;
  onVoiceInput: () => void;
  onRemoveAttachment: (id: string) => void;
}

export function TutorAssistantPanel({
  context,
  courseName,
  input,
  messages,
  response,
  loading,
  error,
  mediaNotice,
  attachments,
  listening,
  onInputChange,
  onSend,
  onClose,
  onImageInput,
  onVoiceInput,
  onRemoveAttachment
}: TutorAssistantPanelProps) {
  const disabledReason = tutorSendDisabledReason(context.courseId, input, attachments.length);
  const stages = agentStageState(response?.agent_events ?? []);

  return (
    <section className="tutor-panel" aria-label="多智能体智能辅导工作台">
      <header className="tutor-panel-header">
        <div className="tutor-brand">
          <span className="tutor-avatar">
            <Sparkles size={18} />
          </span>
          <div>
            <h2>多智能体辅导</h2>
            <p>{context.courseId ? `${courseName || `课程 ${context.courseId}`} · ${context.pageContext}` : "请先选择课程"}</p>
          </div>
        </div>
        <button className="tutor-icon-button" aria-label="关闭智能辅导" onClick={onClose}>
          <X size={17} />
        </button>
      </header>

      <div className="tutor-stage-row" aria-label="智能体协同阶段">
        {stages.map((stage) => (
          <div className={`tutor-stage ${stage.status}`} key={stage.agent}>
            <span>{stage.label}</span>
            <small>{stage.summary}</small>
          </div>
        ))}
      </div>

      <div className="tutor-message-list" aria-live="polite">
        {messages.length === 0 ? (
          <div className="tutor-empty">
            <strong>随时提问当前课程问题</strong>
            <span>我会结合本地知识库、知识图谱和当前页面上下文回答。</span>
          </div>
        ) : (
          messages.map((message) => (
            <article className={`tutor-message ${message.role}`} key={message.id}>
              <p>{message.content}</p>
            </article>
          ))
        )}

        {response && shouldDisplayTutorRagEvidence() ? (
          <section className="tutor-evidence-block">
            <div className="tutor-section-title">RAG 证据</div>
            {response.evidence_chunks.length ? response.evidence_chunks.slice(0, 2).map((chunk) => (
              <article className="tutor-evidence-card" key={`${chunk.chunk_id}-${chunk.source_locator}`}>
                <strong>{chunk.heading || chunk.source_locator || "本地知识库"}</strong>
                <p>{chunk.content}</p>
                <span>{chunk.source_locator}</span>
              </article>
            )) : (
              <article className="tutor-evidence-card muted">未检索到课程知识库证据。</article>
            )}
          </section>
        ) : null}

        {response?.multimodal_cards.length && shouldDisplayTutorStructuredCards() ? (
          <section className="tutor-card-grid">
            {response.multimodal_cards.map((card) => (
              <article className={`tutor-modal-card ${card.type}`} key={`${card.type}-${card.title}`}>
                <span>{card.type}</span>
                <strong>{card.title}</strong>
                <p>{card.content}</p>
              </article>
            ))}
          </section>
        ) : null}

        {mediaNotice ? <div className="tutor-media-notice">{mediaNotice}</div> : null}
        {error ? <div className="tutor-error">{error}</div> : null}
      </div>

      {attachments.length ? (
        <div className="tutor-attachment-strip" aria-label="已添加的图片附件">
          {attachments.map((attachment) => (
            <article className="tutor-attachment-chip" key={attachment.id}>
              {attachment.preview_url ? <img src={attachment.preview_url} alt={attachment.filename} /> : <Image size={18} />}
              <div>
                <strong>{attachment.filename}</strong>
                <span>{attachment.content_type}</span>
              </div>
              <button type="button" aria-label={`移除图片 ${attachment.filename}`} onClick={() => onRemoveAttachment(attachment.id)}>
                <X size={14} />
              </button>
            </article>
          ))}
        </div>
      ) : null}

      <footer className="tutor-input-area">
        <div className="tutor-input-tools">
          <button type="button" aria-label="上传图片" title="上传图片" onClick={onImageInput}>
            <Image size={16} />
          </button>
          <button
            type="button"
            className={listening ? "active" : ""}
            aria-label={listening ? "停止语音输入" : "语音输入"}
            title={listening ? "停止语音输入" : "语音输入"}
            onClick={onVoiceInput}
          >
            <Mic size={16} />
          </button>
        </div>
        <textarea
          aria-label="向智能辅导提问"
          placeholder={context.courseId ? "输入你想追问的课程问题..." : "请先选择课程"}
          rows={2}
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
        />
        <button className="tutor-send" disabled={Boolean(disabledReason) || loading} title={disabledReason || "发送"} onClick={onSend}>
          <Send size={16} />
          {loading ? "生成中" : "发送"}
        </button>
      </footer>
    </section>
  );
}
