import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowRight, Brain, Database, MessageSquarePlus, ShieldCheck, Sparkles } from "lucide-react";
import {
  answerProfileInterview,
  confirmProfileInterview,
  startProfileInterview,
  type ProfileInterview
} from "../api/client";
import { ProfileInterviewPanel, type ProfileChatMessage } from "../components/ProfileInterviewPanel";
import { ProfilePanel } from "../components/ProfilePanel";
import { useAuth } from "../state/auth";
import { scopedProfile } from "../state/profileScopeModel";
import {
  profileInterviewCompletionTarget,
  profileInterviewLayout,
  shouldAutoConfirmProfileInterview
} from "./profileInterviewLayoutModel";

const MAX_INTERVIEW_TURNS = 10;

function normalizeMessageContent(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function ProfileInterviewPage() {
  const { handleAuthError, profile, profileCourseId, setProfile, token, user } = useAuth();
  const navigate = useNavigate();
  const { courseId } = useParams();
  const numericCourseId = Number(courseId);
  const isCourseScoped = Number.isFinite(numericCourseId);
  const courseHomePath = profileInterviewCompletionTarget(isCourseScoped ? numericCourseId : undefined);
  const [topic, setTopic] = useState(isCourseScoped ? "当前课程学习画像" : "Python 程序设计");
  const [interview, setInterview] = useState<ProfileInterview>();
  const [messages, setMessages] = useState<ProfileChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const confirmedProfile = scopedProfile(profile, profileCourseId, numericCourseId, isCourseScoped);
  const activeProfile = confirmedProfile ?? interview?.profile;
  const currentTurn = Math.min(
    MAX_INTERVIEW_TURNS,
    Math.max(1, interview?.current_question ? interview.turn_count + 1 : interview?.turn_count ?? 1)
  );
  const statusText = confirmedProfile
    ? "画像已确认"
    : interview
      ? `问题 ${currentTurn} / ${MAX_INTERVIEW_TURNS}`
      : `问题 1 / ${MAX_INTERVIEW_TURNS}`;
  const layout = profileInterviewLayout(Boolean(confirmedProfile));
  const userInitial = useMemo(() => (user?.username?.trim().slice(0, 1) || "学").toUpperCase(), [user?.username]);
  const completionPercent = Math.round((activeProfile?.completion_score ?? 0) * 100);
  const evidenceCount = activeProfile?.updated_evidence.length ?? 0;

  async function handleStart() {
    setLoading(true);
    setError("");
    try {
      const payload = await startProfileInterview(token, isCourseScoped ? numericCourseId : undefined);
      setInterview(payload);
      setProfile(undefined);
      setMessages(payload.current_question ? [{
        id: `agent-${payload.id}-0`,
        role: "agent",
        author: "画像 Agent",
        content: payload.current_question
      }] : []);
    } catch (caught) {
      if (handleAuthError(caught)) {
        navigate("/auth", { replace: true });
        return;
      }
      setError(caught instanceof Error ? caught.message : "创建画像访谈失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnswer(answer: string) {
    if (!interview) {
      return;
    }
    setAnswering(true);
    setError("");
    const userMessage: ProfileChatMessage = {
      id: `student-${interview.id}-${Date.now()}`,
      role: "student",
      author: user?.username || "我",
      content: answer
    };
    setMessages((current) => [...current, userMessage]);
    try {
      const payload = await answerProfileInterview(token, interview.id, answer, topic);
      setInterview(payload);
      if (payload.current_question) {
        setMessages((current) => {
          const normalizedQuestion = normalizeMessageContent(payload.current_question);
          const lastAgentMessage = [...current].reverse().find((message) => message.role === "agent");
          if (lastAgentMessage && normalizeMessageContent(lastAgentMessage.content) === normalizedQuestion) {
            return current;
          }
          return [...current, {
            id: `agent-${payload.id}-${payload.turn_count}-${Date.now()}`,
            role: "agent",
            author: "画像 Agent",
            content: payload.current_question
          }];
        });
      }
      if (payload.status === "confirmed") {
        setProfile(payload.profile, isCourseScoped ? numericCourseId : null);
        navigate(courseHomePath, { replace: true });
        return;
      }
      if (shouldAutoConfirmProfileInterview(payload.status)) {
        const confirmed = await confirmProfileInterview(token, payload.id);
        setProfile(confirmed.profile, isCourseScoped ? numericCourseId : null);
        navigate(courseHomePath, { replace: true });
      }
    } catch (caught) {
      if (handleAuthError(caught)) {
        navigate("/auth", { replace: true });
        return;
      }
      setError(caught instanceof Error ? caught.message : "提交画像回答失败");
    } finally {
      setAnswering(false);
    }
  }

  async function handleConfirm() {
    if (!interview) {
      return;
    }
    setConfirming(true);
    setError("");
    try {
      const payload = await confirmProfileInterview(token, interview.id);
      setProfile(payload.profile, isCourseScoped ? numericCourseId : null);
      navigate(courseHomePath, { replace: true });
    } catch (caught) {
      if (handleAuthError(caught)) {
        navigate("/auth", { replace: true });
        return;
      }
      setError(caught instanceof Error ? caught.message : "确认画像失败");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="profile-workbench course-kb-preview-page profile-course-workbench">
      <section className={layout.heroClassName}>
        <div>
          <span className="eyebrow">STUDENT PROFILE</span>
          <h2>{isCourseScoped ? layout.heading : "对话式学习画像"}</h2>
          <p>{isCourseScoped ? layout.description : "每门课程独立构建画像；切换到另一门课时，画像、知识库、图谱和学习记录不会混用。"}</p>
          <div className="kb-preview-actions">
            {!interview && !confirmedProfile ? (
              <button className="primary-action compact-button" disabled={loading} onClick={() => void handleStart()} type="button">
                {loading ? <Sparkles className="spin" size={16} /> : <MessageSquarePlus size={16} />}
                {loading ? "创建访谈中" : "开始画像访谈"}
              </button>
            ) : null}
            <button className="secondary-action compact-button" disabled={!confirmedProfile} onClick={() => navigate(courseHomePath)} type="button">
              <ArrowRight size={16} />
              进入课程知识库
            </button>
          </div>
        </div>
        <div className="profile-header-actions">
          <span className={`profile-question-pill ${confirmedProfile ? "done" : ""}`}>{statusText}</span>
          <span className="profile-avatar" aria-label="当前学生">
            {userInitial}
          </span>
        </div>
      </section>

      <section className="kb-preview-metrics profile-course-metrics" aria-label="画像构建概览">
        <div className="kb-preview-metric"><div>{completionPercent}%</div><span>画像完成度</span><strong>{confirmedProfile ? "已确认" : "构建中"}</strong></div>
        <div className="kb-preview-metric"><div>{currentTurn}</div><span>访谈轮次</span><strong>{MAX_INTERVIEW_TURNS} 轮以内</strong></div>
        <div className="kb-preview-metric"><div>{evidenceCount}</div><span>画像证据</span><strong>随答随新</strong></div>
        <div className="kb-preview-metric"><div>KB</div><span>下一步</span><strong>课程知识库</strong></div>
      </section>

      <section className="profile-flow-strip" aria-label="课程画像流程">
        <div className={interview || confirmedProfile ? "active" : ""}><MessageSquarePlus size={16} /><span>访谈采集</span></div>
        <div className={activeProfile ? "active" : ""}><Brain size={16} /><span>画像抽取</span></div>
        <div className={confirmedProfile ? "active" : ""}><ShieldCheck size={16} /><span>确认画像</span></div>
        <div className={confirmedProfile ? "active" : ""}><Database size={16} /><span>进入知识库</span></div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <div className={layout.gridClassName}>
        {layout.mode === "interview_builder" ? (
          <ProfileInterviewPanel
            answering={answering}
            confirming={confirming}
            generating={false}
            interview={interview}
            loading={loading}
            maxTurns={MAX_INTERVIEW_TURNS}
            messages={messages}
            onAnswer={handleAnswer}
            onConfirm={handleConfirm}
            onGenerate={() => navigate(courseHomePath)}
            onStart={handleStart}
            onTopicChange={setTopic}
            primaryActionLabel={layout.primaryActionLabel}
            profile={confirmedProfile}
            readyDescription={layout.readyDescription}
            completionDescription={layout.completionDescription}
            pendingHint={layout.pendingHint}
            topic={topic}
          />
        ) : null}
        <ProfilePanel profile={activeProfile} />
      </div>
    </div>
  );
}
