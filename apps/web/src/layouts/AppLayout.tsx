import { Activity, BookOpen, Bot, CheckCircle2, GitBranch, LogOut, Network, Route, UserRound } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { listCourses, type Course } from "../api/client";
import { AttentionFloating } from "../components/AttentionFloating";
import { loadRuntimeMode, saveRuntimeMode, type AgentArtsMode } from "../api/agentarts";
import { TutorAssistantFloating } from "../components/TutorAssistantFloating";
import { useAuth } from "../state/auth";
import { isProfileScopedToCourse } from "../state/profileScopeModel";
import {
  choosePreferredCourse,
  CURRENT_COURSE_CHANGED_EVENT,
  CURRENT_COURSE_ID_KEY,
  currentCourseNavigationTargets,
  isCourseNavigationDisabled,
  persistCurrentCourse,
  readCurrentCourseId
} from "../state/currentCourse";
import { navItemState, type AppNavKey } from "./appNavigationModel";

export function AppLayout() {
  const { logout, profile, profileCourseId, refreshProfile, token, user } = useAuth();
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
  const { assessmentTarget, courseKnowledgeBaseTarget, graphTarget, pathTarget, profileTarget } = currentCourseNavigationTargets(activeCourseId);
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

  function navItem(key: AppNavKey, to: string, disabled: boolean, children: ReactNode, end = false) {
    if (disabled) {
      return (
        <span aria-disabled="true" className="nav-disabled">
          {children}
        </span>
      );
    }
    return (
      <NavLink className={() => navItemState(key, location.pathname, location.search, false)} end={end} to={to}>
        {children}
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
          <div className="brand-mark">AI</div>
          <div>
            <h1>智学引擎</h1>
            <p>多智能体学习工作台</p>
          </div>
        </div>

        <div className="nav-section-label">学习流程</div>
        {navItem("courses", courseKnowledgeBaseTarget, false, (
          <>
            <BookOpen size={16} />
            <span>课程知识库</span>
          </>
        ), true)}
        {navItem("profile", profileTarget, false, (
          <>
            <UserRound size={16} />
            <span>学生画像</span>
          </>
        ))}
        {navItem("graph", graphTarget, courseScopedDisabled, (
          <>
            <Network size={16} />
            <span>知识图谱</span>
          </>
        ))}
        {navItem("learning_path", pathTarget, courseScopedDisabled, (
          <>
            <Route size={16} />
            <span>学习路径</span>
          </>
        ))}
        {navItem("assessment", assessmentTarget, courseScopedDisabled, (
          <>
            <Activity size={16} />
            <span>学习评估</span>
          </>
        ))}

        <div className="nav-section-label">AI 互动</div>
        <NavLink className={() => /\/courses\/\d+\/tutor-stage/.test(location.pathname) ? "active" : ""} to={`/courses/${activeCourseId ?? 1}/tutor-stage`}>
          <>
            <Bot size={16} />
            <span>AI 对话大屏</span>
          </>
        </NavLink>

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
            <small>{activeCourseProfile ? "侧边栏已绑定该课程" : "先完成该课程画像"}</small>
          </div>
        </div>
        <div className="runtime-mode-switch" role="group" aria-label="运行模式切换">
          <span className="nav-section-label">运行模式</span>
          <div className="mode-options">
            <button
              type="button"
              className={runtimeMode === "local" ? "active" : ""}
              onClick={() => handleRuntimeModeChange("local")}
            >
              本地模式
            </button>
            <button
              type="button"
              className={runtimeMode === "agentarts" ? "active" : ""}
              onClick={() => handleRuntimeModeChange("agentarts")}
            >
              AgentArts
            </button>
          </div>
        </div>
      </aside>

      <section className="app-main">
        <header className="topbar app-topbar">
          <div>
            <h1>个性化学习多智能体平台</h1>
            <p>画像驱动课程知识库、知识图谱、学习路径与知识点资源生成。</p>
          </div>
          <div className="topbar-right">
            <div className={`system-status ${activeCourseProfile ? "ready" : ""}`}>
              <CheckCircle2 size={15} />
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
          onIntervene={({ nodeId, state }) => {
            setInterventionMessage(
              `我正在学习知识点「${nodeId}」，学习状态感知显示我处于「${state}」，请结合课程知识库换一种更直观的讲法：先讲直觉类比，再给一个可运行的 C++ 例子。`
            );
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
