import {
  Activity,
  BadgeCheck,
  BookOpen,
  Bot,
  CheckCircle2,
  Cpu,
  Moon,
  GitBranch,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Network,
  Route,
  Sun,
  UserRound
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { listCourses, type Course } from "../api/client";
import { AttentionFloating } from "../components/AttentionFloating";
import { loadRuntimeMode, saveRuntimeMode, type AgentArtsMode } from "../api/agentarts";
import { TutorAssistantFloating } from "../components/TutorAssistantFloating";
import { useAuth } from "../state/auth";
import { isProfileScopedToCourse } from "../state/profileScopeModel";
import { useThemeMode } from "../state/themeMode";
import {
  choosePreferredCourse,
  CURRENT_COURSE_CHANGED_EVENT,
  CURRENT_COURSE_ID_KEY,
  currentCourseNavigationTargets,
  isCourseNavigationDisabled,
  persistCurrentCourse,
  readCurrentCourseId
} from "../state/currentCourse";
import { appNavGroups, navItemState, type AppNavKey } from "./appNavigationModel";

const NAV_ICONS: Record<AppNavKey, ReactNode> = {
  today: <LayoutDashboard size={16} />,
  learning_path: <Route size={16} />,
  graph: <Network size={16} />,
  tutor_stage: <Bot size={16} />,
  profile: <UserRound size={16} />,
  assessment: <Activity size={16} />,
  wrong_questions: <ListChecks size={16} />,
  courses: <BookOpen size={16} />
};

const NAV_LABELS: Record<AppNavKey, string> = {
  today: "今日学习",
  learning_path: "学习路径",
  graph: "知识图谱",
  tutor_stage: "AI 对话大屏",
  profile: "学生画像",
  assessment: "学习评估",
  wrong_questions: "错题本",
  courses: "课程中心"
};

export function AppLayout() {
  const { logout, profile, profileCourseId, refreshProfile, token, user } = useAuth();
  const [themeMode, setThemeMode] = useThemeMode();
  const location = useLocation();
  const navigate = useNavigate();
  const courseId = location.pathname.match(/\/courses\/(\d+)/)?.[1];
  const [courses, setCourses] = useState<Course[]>([]);
  const [runtimeMode, setRuntimeMode] = useState<AgentArtsMode>(() => loadRuntimeMode());
  const [fallbackCourseId, setFallbackCourseId] = useState<number | undefined>(() => readCurrentCourseId());
  const activeCourseId = courseId ? Number(courseId) : fallbackCourseId;
  const activeCourse = courses.find((course) => course.id === activeCourseId);
  const knowledgeNodeId = decodeURIComponent(location.pathname.match(/\/courses\/\d+\/knowledge\/([^/?#]+)/)?.[1] || "");
  const [tutorOpenSignal, setTutorOpenSignal] = useState(0);
  const [interventionMessage, setInterventionMessage] = useState("");
  const activeCourseProfile = isProfileScopedToCourse(profile, profileCourseId, activeCourseId) ? profile : undefined;
  const {
    assessmentTarget,
    courseKnowledgeBaseTarget,
    graphTarget,
    pathTarget,
    profileTarget,
    todayTarget,
    tutorStageTarget,
    wrongQuestionsTarget
  } = currentCourseNavigationTargets(activeCourseId);
  const courseScopedDisabled = isCourseNavigationDisabled(activeCourseId);

  useEffect(() => {
    if (!token) {
      setFallbackCourseId(undefined);
      setCourses([]);
      persistCurrentCourse(undefined);
      return;
    }

    let cancelled = false;
    listCourses(token)
      .then((courses) => {
        if (cancelled) {
          return;
        }
        setCourses(courses);
        const routeCourseId = courseId ? Number(courseId) : undefined;
        const selectedCourse = choosePreferredCourse(courses, routeCourseId ?? readCurrentCourseId());
        setFallbackCourseId(selectedCourse?.id);
        if (selectedCourse) {
          persistCurrentCourse(selectedCourse);
        } else if (routeCourseId) {
          localStorage.setItem(CURRENT_COURSE_ID_KEY, String(routeCourseId));
          window.dispatchEvent(new CustomEvent(CURRENT_COURSE_CHANGED_EVENT, { detail: { courseId: routeCourseId } }));
        } else {
          persistCurrentCourse(undefined);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFallbackCourseId(readCurrentCourseId());
        }
      });

    return () => {
      cancelled = true;
    };
  }, [courseId, token]);

  useEffect(() => {
    function handleCurrentCourseChanged() {
      const selectedId = readCurrentCourseId();
      setFallbackCourseId(selectedId);
      if (token) {
        void listCourses(token).then(setCourses).catch(() => undefined);
      }
    }
    window.addEventListener(CURRENT_COURSE_CHANGED_EVENT, handleCurrentCourseChanged);
    window.addEventListener("storage", handleCurrentCourseChanged);
    return () => {
      window.removeEventListener(CURRENT_COURSE_CHANGED_EVENT, handleCurrentCourseChanged);
      window.removeEventListener("storage", handleCurrentCourseChanged);
    };
  }, [token]);

  useEffect(() => {
    if (!token || !activeCourseId) {
      return;
    }
    void refreshProfile(activeCourseId).catch(() => undefined);
  }, [activeCourseId, refreshProfile, token]);

  function navTarget(key: AppNavKey): { to: string; disabled: boolean } {
    switch (key) {
      case "today":
        return { to: todayTarget, disabled: courseScopedDisabled };
      case "learning_path":
        return { to: pathTarget, disabled: courseScopedDisabled };
      case "graph":
        return { to: graphTarget, disabled: courseScopedDisabled };
      case "tutor_stage":
        return { to: tutorStageTarget, disabled: courseScopedDisabled };
      case "profile":
        return { to: profileTarget, disabled: false };
      case "assessment":
        return { to: assessmentTarget, disabled: courseScopedDisabled };
      case "wrong_questions":
        return { to: wrongQuestionsTarget, disabled: courseScopedDisabled };
      case "courses":
        return { to: courseKnowledgeBaseTarget, disabled: false };
    }
  }

  function navItem(key: AppNavKey) {
    const { to, disabled } = navTarget(key);
    if (disabled) {
      return (
        <span aria-disabled="true" className="nav-disabled" key={key}>
          {NAV_ICONS[key]}
          <span>{NAV_LABELS[key]}</span>
        </span>
      );
    }
    return (
      <NavLink className={() => navItemState(key, location.pathname, location.search, false)} end={false} key={key} to={to}>
        {NAV_ICONS[key]}
        <span>{NAV_LABELS[key]}</span>
      </NavLink>
    );
  }

  function handleRuntimeModeChange(mode: AgentArtsMode) {
    setRuntimeMode(mode);
    saveRuntimeMode(mode);
  }

  function handleLogout() {
    logout();
    navigate("/auth", { replace: true });
  }

  return (
    <main className="workspace app-shell">
      <aside className="app-nav" aria-label="主导航">
        <div className="brand-block app-brand">
          <div className="brand-mark">知行</div>
          <div>
            <h1>知行学习伙伴</h1>
            <p>多智能体个性化学习引擎</p>
          </div>
        </div>

        {appNavGroups.map((group) => (
          <div key={group.key}>
            <div className="nav-section-label">{group.label}</div>
            {group.items.map((key) => navItem(key))}
          </div>
        ))}

        <div className="nav-progress">
          <span>画像完整度</span>
          <strong>{Math.round((activeCourseProfile?.completion_score ?? 0) * 100)}%</strong>
          <div className="progress">
            <span style={{ width: `${Math.round((activeCourseProfile?.completion_score ?? 0) * 100)}%` }} />
          </div>
        </div>
        <div className="nav-side-card">
          <GitBranch size={18} />
          <div>
            <span>当前课程</span>
            <strong>{activeCourse?.name || (activeCourseId ? `课程 ${activeCourseId}` : "未选择课程")}</strong>
            <small>{activeCourseProfile ? "学习流程已绑定该课程" : "先完成该课程画像"}</small>
          </div>
        </div>
      </aside>

      <section className="app-main">
        <header className="topbar app-topbar">
          <div>
            <h1>{activeCourse ? `${activeCourse.name} · 学习工作台` : "学习工作台"}</h1>
            <p>画像驱动知识库、知识图谱、学习路径与知识点资源生成。</p>
          </div>
          <div className="topbar-right">
            <button
              aria-label={themeMode === "dark" ? "切换到浅色模式" : "切换到深色模式"}
              className="theme-toggle"
              onClick={() => setThemeMode(themeMode === "dark" ? "light" : "dark")}
              title={themeMode === "dark" ? "浅色模式" : "深色模式"}
              type="button"
            >
              {themeMode === "dark" ? <Sun size={15} /> : <Moon size={15} />}
            </button>
            <div className="engine-badge" role="group" aria-label="编排引擎切换">
              <Cpu size={14} />
              <span className="engine-badge-label">编排引擎</span>
              <button
                type="button"
                className={runtimeMode === "local" ? "active" : ""}
                onClick={() => handleRuntimeModeChange("local")}
              >
                本地
              </button>
              <button
                type="button"
                className={runtimeMode === "agentarts" ? "active" : ""}
                onClick={() => handleRuntimeModeChange("agentarts")}
              >
                AgentArts
              </button>
              <span className={`engine-dot ${runtimeMode}`} aria-hidden="true" />
            </div>
            <div className={`system-status ${activeCourseProfile ? "ready" : ""}`}>
              {activeCourseProfile ? <BadgeCheck size={15} /> : <CheckCircle2 size={15} />}
              <span>{activeCourseProfile ? "画像已确认" : "等待画像构建"}</span>
            </div>
            <div className="user-chip">
              <span>{user?.username}</span>
              <button aria-label="退出登录" onClick={handleLogout}>
                <LogOut size={14} />
                退出
              </button>
            </div>
          </div>
        </header>
        <section className="app-content">
          <Outlet />
        </section>
      </section>
      {user ? (
        <AttentionFloating
          activeCourseId={activeCourseId}
          nodeId={knowledgeNodeId}
          onIntervene={({ nodeId, state, codeError, highConfidence }) => {
            const codePart = highConfidence
              ? `我的代码实验连续没跑通（最近错误：${codeError || "运行失败"}），请帮我看看代码哪里不对，再结合课程知识库和图谱前置约束换一种更直观的讲法：先讲直觉类比，再给一个可运行的 C++ 例子。`
              : `我正在学习知识点「${nodeId}」，学习状态感知显示我处于「${state}」，请结合课程知识库换一种更直观的讲法：先讲直觉类比，再给一个可运行的 C++ 例子。`;
            setInterventionMessage(codePart);
            setTutorOpenSignal((n) => n + 1);
          }}
          token={token}
          topic={knowledgeNodeId}
        />
      ) : null}
      <TutorAssistantFloating courses={courses} activeCourseId={activeCourseId} openSignal={tutorOpenSignal}
          interventionMessage={interventionMessage}
        />
    </main>
  );
}
