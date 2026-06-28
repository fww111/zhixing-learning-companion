import { useEffect, useMemo, useState } from "react";
import {
  answerProfileInterview,
  confirmProfileInterview,
  generateLearningPackage,
  getMyProfile,
  startProfileInterview,
  type AuthUser,
  type ProfileInterview,
  type StudentProfile,
  type WorkflowPackage
} from "../api/client";
import { AgentTimeline } from "../components/AgentTimeline";
import { AssessmentPanel } from "../components/AssessmentPanel";
import { AuthPanel } from "../components/AuthPanel";
import { CourseKnowledgeBase } from "../components/CourseKnowledgeBase";
import { LearningPath } from "../components/LearningPath";
import { MindMapViewer } from "../components/MindMapViewer";
import { ProfileInterviewPanel } from "../components/ProfileInterviewPanel";
import { ProfilePanel } from "../components/ProfilePanel";
import { ResourceCard } from "../components/ResourceCard";

export function Workspace() {
  const [token, setToken] = useState(() => localStorage.getItem("pla_token") ?? "");
  const [user, setUser] = useState<AuthUser | undefined>(() => {
    const stored = localStorage.getItem("pla_user");
    return stored ? JSON.parse(stored) as AuthUser : undefined;
  });
  const [topic, setTopic] = useState("梯度下降");
  const [loading, setLoading] = useState(false);
  const [interviewLoading, setInterviewLoading] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [interview, setInterview] = useState<ProfileInterview>();
  const [confirmedProfile, setConfirmedProfile] = useState<StudentProfile>();
  const [result, setResult] = useState<WorkflowPackage>();
  const [error, setError] = useState("");

  const mindMap = useMemo(() => result?.resources.find((resource) => resource.type === "mind_map"), [result]);

  useEffect(() => {
    if (!token) {
      return;
    }
    getMyProfile(token)
      .then((profile) => {
        setConfirmedProfile(profile);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "加载画像失败"));
  }, [token]);

  function profileToConversation(profile: StudentProfile): string {
    return [
      `专业年级：${profile.major} ${profile.grade}`,
      `学习目标：${profile.learning_goal}`,
      `知识基础：${profile.knowledge_foundation}`,
      `薄弱点：${profile.weak_points.join("、")}`,
      `学习偏好：${profile.learning_style}，资源偏好 ${profile.resource_preference.join("、")}`,
      `时间安排：${profile.time_preference}`,
      `评估偏好：${profile.assessment_preference}`,
      `图谱关注：${profile.knowledge_graph_focus.join("、")}`
    ].join("。");
  }

  async function handleStartInterview() {
    setInterviewLoading(true);
    setError("");
    try {
      const payload = await startProfileInterview(token);
      setInterview(payload);
      setConfirmedProfile(undefined);
      setResult(undefined);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建画像访谈失败");
    } finally {
      setInterviewLoading(false);
    }
  }

  async function handleAnswerInterview(answer: string) {
    if (!interview) {
      return;
    }
    setAnswering(true);
    setError("");
    try {
      const payload = await answerProfileInterview(token, interview.id, answer, topic);
      setInterview(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提交画像回答失败");
    } finally {
      setAnswering(false);
    }
  }

  async function handleConfirmProfile() {
    if (!interview) {
      return;
    }
    setConfirming(true);
    setError("");
    try {
      const payload = await confirmProfileInterview(token, interview.id);
      setConfirmedProfile(payload.profile);
      setInterview((current) => current ? { ...current, status: "confirmed", current_question: "", profile: payload.profile } : current);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "确认画像失败");
    } finally {
      setConfirming(false);
    }
  }

  async function handleSubmit() {
    if (!confirmedProfile) {
      setError("请先完成并确认学生画像");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = await generateLearningPackage({ conversation: profileToConversation(confirmedProfile), topic }, token);
      setResult(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "生成失败");
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem("pla_token");
    localStorage.removeItem("pla_user");
    setToken("");
    setUser(undefined);
    setInterview(undefined);
    setConfirmedProfile(undefined);
    setResult(undefined);
  }

  if (!token || !user) {
    return (
      <AuthPanel
        onAuthenticated={(auth) => {
          setInterview(undefined);
          setConfirmedProfile(undefined);
          setResult(undefined);
          setToken(auth.access_token);
          setUser(auth.user);
        }}
      />
    );
  }

  return (
    <main className="workspace">
      <header className="topbar">
        <div>
          <h1>个性化学习多智能体工作台</h1>
          <p>对话画像、多Agent资源生成、路径规划与学习评估的一体化演示</p>
        </div>
        <div className="user-chip">
          <span>{user.username}</span>
          <button onClick={logout}>退出</button>
        </div>
      </header>

      <CourseKnowledgeBase token={token} />

      <div className="layout">
        <aside className="left-column">
          <ProfileInterviewPanel
            interview={interview}
            profile={confirmedProfile}
            topic={topic}
            loading={interviewLoading}
            answering={answering}
            confirming={confirming}
            generating={loading}
            onStart={handleStartInterview}
            onAnswer={handleAnswerInterview}
            onConfirm={handleConfirmProfile}
            onGenerate={handleSubmit}
            onTopicChange={setTopic}
          />
          {error ? <div className="error">{error}</div> : null}
        </aside>

        <section className="center-column">
          <LearningPath path={result?.learning_path} />
          <div className="resource-grid">
            {result?.resources.map((resource) => <ResourceCard key={resource.id} resource={resource} />) ?? (
              <div className="panel empty-state">生成后展示文档、导图、练习、阅读、视频脚本和代码案例。</div>
            )}
          </div>
        </section>

        <aside className="right-column">
          <ProfilePanel profile={confirmedProfile ?? result?.profile} />
          <AgentTimeline running={loading} completed={Boolean(result)} />
          <AssessmentPanel hasResult={Boolean(result)} />
          <MindMapViewer resource={mindMap} />
        </aside>
      </div>
    </main>
  );
}
