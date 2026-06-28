import { FormEvent, useState } from "react";
import { CheckCircle2, Loader2, MessageSquarePlus, Send, Sparkles } from "lucide-react";
import type { ProfileInterview, StudentProfile } from "../api/client";

export interface ProfileChatMessage {
  id: string;
  role: "agent" | "student";
  author: string;
  content: string;
}

interface ProfileInterviewPanelProps {
  interview?: ProfileInterview;
  profile?: StudentProfile;
  messages?: ProfileChatMessage[];
  maxTurns?: number;
  topic: string;
  loading: boolean;
  answering: boolean;
  confirming: boolean;
  generating: boolean;
  onStart: () => void;
  onAnswer: (answer: string) => void;
  onConfirm: () => void;
  onGenerate: () => void;
  onTopicChange: (topic: string) => void;
  primaryActionLabel?: string;
  readyDescription?: string;
  completionDescription?: string;
  pendingHint?: string;
}

export function ProfileInterviewPanel({
  interview,
  profile,
  messages = [],
  maxTurns = 10,
  topic,
  loading,
  answering,
  confirming,
  generating,
  onStart,
  onAnswer,
  onConfirm,
  onGenerate,
  onTopicChange,
  primaryActionLabel = "进入课程知识库",
  readyDescription = "已读取该学生的确认画像。可以直接进入课程知识库，继续上传课程材料、生成知识图谱和学习路径。",
  completionDescription = "画像维度已补齐，系统将保存画像并进入课程知识库。",
  pendingHint = "画像维度齐全后会自动保存，并进入课程知识库流程。"
}: ProfileInterviewPanelProps) {
  const [answer, setAnswer] = useState("");
  const activeProfile = interview?.profile ?? profile;
  const confirmed = Boolean(profile);
  const currentQuestion = interview?.current_question;
  const currentTurn = Math.min(maxTurns, Math.max(1, currentQuestion ? (interview?.turn_count ?? 0) + 1 : interview?.turn_count ?? 1));
  const visibleMessages = messages.length > 0
    ? messages
    : currentQuestion
      ? [{
        id: `question-${interview?.id ?? "pending"}`,
        role: "agent" as const,
        author: "画像 Agent",
        content: currentQuestion
      }]
      : [];
  const evidenceItems = activeProfile?.updated_evidence.slice(-3) ?? [];

  function submitAnswer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = answer.trim();
    if (!trimmed) {
      return;
    }
    onAnswer(trimmed);
    setAnswer("");
  }

  return (
    <section className="profile-chat-panel" aria-label="学习需求访谈">
      <div className="profile-chat-title">
        <div>
          <h3>学习需求访谈</h3>
          <span>DeepSeek V4 Pro 动态追问</span>
        </div>
        {interview ? <span className="profile-turn-tag">第 {currentTurn} 轮</span> : null}
      </div>

      {interview || confirmed ? (
        <>
          <div className="profile-chat-feed" aria-live="polite">
            {visibleMessages.map((message) => (
              <article className={`profile-chat-message ${message.role}`} key={message.id}>
                <span>{message.author}</span>
                <p>{message.content}</p>
              </article>
            ))}
            {confirmed && !interview ? (
              <article className="profile-chat-message agent">
                <span>画像 Agent</span>
                <p>{readyDescription}</p>
              </article>
            ) : null}
            {!currentQuestion && activeProfile ? (
              <article className="profile-chat-message agent">
                <span>画像 Agent</span>
                <p>{completionDescription}</p>
              </article>
            ) : null}
          </div>

          {currentQuestion ? (
            <form className="profile-answer-form" onSubmit={submitAnswer}>
              <textarea
                id="profile-answer"
                name="answer"
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                maxLength={500}
                rows={4}
                placeholder="请结合当前问题回答，系统会继续围绕目标、基础、时间、偏好和约束追问"
              />
              <div className="profile-answer-footer">
                <span>{answer.trim().length}/500</span>
                <button className="primary-action" disabled={answering || !answer.trim()} type="submit">
                  {answering ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
                  {answering ? "提交中" : "提交回答"}
                </button>
              </div>
            </form>
          ) : null}
        </>
      ) : (
        <div className="profile-start-card">
          <div className="profile-start-icon">
            <MessageSquarePlus size={22} />
          </div>
          <div className="profile-start-copy">
            <strong>从固定首问开始</strong>
            <p>后续问题由大模型根据学生回答围绕画像维度继续追问。</p>
          </div>
          <button className="primary-action" disabled={loading} onClick={onStart}>
            {loading ? <Loader2 className="spin" size={16} /> : <MessageSquarePlus size={16} />}
            {loading ? "创建中" : "开始画像访谈"}
          </button>
        </div>
      )}

      <div className="profile-topic-row">
        <label>
          学习主题
          <input id="profile-topic" name="topic" value={topic} onChange={(event) => onTopicChange(event.target.value)} />
        </label>
      </div>

      <div className="profile-evidence-chips">
        {evidenceItems.length > 0 ? evidenceItems.map((item) => (
          <span key={`${item.topic}-${item.detail}`}>
            <Sparkles size={14} />
            {item.topic}: {item.detail}
          </span>
        )) : (
          <>
            <span><Sparkles size={14} /> 自动更新画像证据</span>
            <span>问题控制在 {maxTurns} 轮以内</span>
          </>
        )}
      </div>

      {activeProfile ? (
        <div className="profile-chat-progress">
          <div>
            <span>画像完成度</span>
            <strong>{Math.round((activeProfile.completion_score || 0) * 100)}%</strong>
          </div>
          <progress max={1} value={activeProfile.completion_score || 0} />
          <p>{activeProfile.updated_evidence.length} 条对话证据 / 置信度 {Math.round((activeProfile.confidence_score || 0) * 100)}%</p>
        </div>
      ) : null}

      <div className="profile-interview-actions">
        {!confirmed && activeProfile && !currentQuestion ? (
          <button className="secondary-action" disabled={confirming} onClick={onConfirm} type="button">
            {confirming ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
            {confirming ? "Saving profile" : "Confirm profile"}
          </button>
        ) : null}
        <button className="primary-action" disabled={!confirmed || generating} onClick={onGenerate}>
          {generating ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
          {generating ? "进入中" : primaryActionLabel}
        </button>
      </div>

      {!confirmed ? <p className="kb-hint">{pendingHint}</p> : null}
    </section>
  );
}
