import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Code2,
  Database,
  FileUp,
  GitBranch,
  Loader2,
  Plus,
  Route
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  createCourse,
  getMyProfile,
  listCourses,
  type Course,
  type CourseCreatePayload
} from "../api/client";
import { useAuth } from "../state/auth";
import { choosePreferredCourse, persistCurrentCourse, readCurrentCourseId } from "../state/currentCourse";
import {
  courseProfileRoute,
  type BuiltInCourseKey,
  type BuiltInCourseOption
} from "./courseTemplateModel";

const builtInCourseOptions: BuiltInCourseOption[] = [
  {
    key: "c",
    title: "C语言程序设计",
    description: "围绕指针、数组、函数、结构体与文件操作建立课程知识库和图谱。",
    focus: ["指针", "数组", "函数", "结构体"]
  },
  {
    key: "python",
    title: "Python程序设计",
    description: "覆盖解释器、基础语法、数据结构、函数、文件与项目实践。",
    focus: ["基础语法", "函数", "数据结构", "项目实践"]
  }
];

const initialCourseForm: CourseCreatePayload = {
  name: "",
  major: "",
  level: "",
  description: ""
};

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("zh-CN");
}

function isBuiltInPython(course: Course): boolean {
  return course.description.includes("built-in:python");
}

function isBuiltInC(course: Course): boolean {
  return course.description.includes("built-in:c");
}

function courseKind(course: Course): BuiltInCourseKey | "custom" {
  if (isBuiltInC(course)) {
    return "c";
  }
  if (isBuiltInPython(course)) {
    return "python";
  }
  return "custom";
}

function shortCourseLabel(kind: BuiltInCourseKey | "custom"): string {
  if (kind === "c") {
    return "C 语言";
  }
  if (kind === "python") {
    return "Python";
  }
  return "自定义";
}

export function CoursesPage() {
  const { handleAuthError, setProfile, token } = useAuth();
  const navigate = useNavigate();
  const [courses, setCourses] = useState<Course[]>([]);
  const [form, setForm] = useState<CourseCreatePayload>(initialCourseForm);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [currentCourseId, setCurrentCourseId] = useState<number | undefined>(() => readCurrentCourseId());
  const [error, setError] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);

  const builtInPythonCourse = useMemo(() => courses.find(isBuiltInPython), [courses]);
  const builtInCCourse = useMemo(() => courses.find(isBuiltInC), [courses]);
  const customCourses = useMemo(() => courses.filter((course) => !isBuiltInPython(course) && !isBuiltInC(course)), [courses]);
  const currentCourse = useMemo(() => courses.find((course) => course.id === currentCourseId), [courses, currentCourseId]);
  const visibleCourseCards = useMemo(() => {
    return [
      builtInCCourse,
      builtInPythonCourse,
      ...customCourses.filter((course) => course.id !== builtInCCourse?.id && course.id !== builtInPythonCourse?.id)
    ].filter(Boolean) as Course[];
  }, [builtInCCourse, builtInPythonCourse, customCourses]);

  async function loadCourses() {
    setLoading(true);
    setError("");
    try {
      const nextCourses = await listCourses(token);
      setCourses(nextCourses);
      const selectedCourse = choosePreferredCourse(nextCourses, readCurrentCourseId());
      if (selectedCourse) {
        persistCurrentCourse(selectedCourse);
        setCurrentCourseId(selectedCourse.id);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载课程失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadCourses();
  }, [token]);

  async function enterCourse(course: Course) {
    try {
      persistCurrentCourse(course);
      setCurrentCourseId(course.id);
      setError("");
      const courseProfile = await getMyProfile(token, course.id);
      setProfile(courseProfile, course.id);
      navigate(courseProfile ? `/courses/${course.id}/knowledge-base` : `/courses/${course.id}/profile/interview`);
    } catch (caught) {
      if (handleAuthError(caught)) {
        navigate("/auth", { replace: true });
        return;
      }
      setProfile(undefined, course.id);
      setError(caught instanceof Error ? caught.message : "进入课程失败");
    }
  }

  function setAsCurrentCourse(course?: Course) {
    if (!course) {
      return;
    }
    persistCurrentCourse(course);
    setCurrentCourseId(course.id);
    setError("");
  }

  function goToCoursePage(course: Course, path: "knowledge-base" | "learning-path" | "graph") {
    setAsCurrentCourse(course);
    navigate(`/courses/${course.id}/${path}`);
  }

  async function handleCreateCourse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = {
      name: form.name.trim(),
      major: form.major?.trim() || "",
      level: form.level?.trim() || "",
      description: form.description?.trim() || "用户自建课程知识库"
    };
    if (!payload.name) {
      setError("课程名称不能为空");
      return;
    }

    setCreating(true);
    setError("");
    try {
      const created = await createCourse(token, payload);
      setCourses((current) => [created, ...current]);
      setForm(initialCourseForm);
      setShowCreateForm(false);
      persistCurrentCourse(created);
      setCurrentCourseId(created.id);
      setProfile(undefined, created.id);
      navigate(courseProfileRoute(created.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建课程失败");
    } finally {
      setCreating(false);
    }
  }

  function renderCourseCard(course: Course) {
    const kind = courseKind(course);
    const isCurrentCourse = course.id === currentCourseId;
    const tags = kind === "custom"
      ? [course.major || "自建课程", course.level || "待完善", formatDate(course.updated_at)]
      : [...(builtInCourseOptions.find((option) => option.key === kind)?.focus ?? []), formatDate(course.updated_at)];

    return (
      <article className={`kb-course-card ${kind} ${isCurrentCourse ? "active" : ""}`} key={course.id}>
        <div className={`kb-course-cover ${kind}`}>
          <svg viewBox="0 0 360 126" aria-hidden="true">
            <path d="M28 94 C80 54, 120 108, 176 60 S280 42, 332 84" fill="none" stroke="rgba(255,255,255,.68)" strokeWidth="5" />
            <rect fill="rgba(255,255,255,.2)" height="54" rx="9" width="84" x="30" y="24" />
            <rect fill="rgba(255,255,255,.55)" height="12" rx="6" width="70" x="132" y="34" />
            <rect fill="rgba(255,255,255,.32)" height="12" rx="6" width="118" x="132" y="56" />
          </svg>
          <strong>{shortCourseLabel(kind)}</strong>
        </div>
        <div className="kb-course-card-head">
          <h3>{course.name}</h3>
          <span className={`status-chip ${isCurrentCourse ? "success-chip" : "blue-chip"}`}>
            {isCurrentCourse ? "当前课程" : course.status || "ready"}
          </span>
        </div>
        <p>{course.description.replace(/built-in:(python|c)/g, "").trim() || "课程数据独立保存，画像、知识库、图谱和学习路径均按课程隔离。"}</p>
        <div className="tag-row">{tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div>
        <div className="kb-course-snapshots" aria-hidden="true">
          <div><span /><i /></div>
          <div><b /><b /><b /></div>
          <div><em /></div>
        </div>
        <div className="kb-course-actions">
          <button className="primary-action" onClick={() => void enterCourse(course)} type="button">
            <ArrowRight size={15} />
            进入课程
          </button>
          <button className="secondary-action" disabled={isCurrentCourse} onClick={() => setAsCurrentCourse(course)} type="button">
            <CheckCircle2 size={15} />
            {isCurrentCourse ? "当前课程" : "设为当前"}
          </button>
          <button className="secondary-action" onClick={() => goToCoursePage(course, "knowledge-base")} type="button">
            <FileUp size={15} />
            知识库
          </button>
          <button className="secondary-action" onClick={() => goToCoursePage(course, "learning-path")} type="button">
            <Route size={15} />
            路径
          </button>
        </div>
      </article>
    );
  }

  return (
    <div className="page-stack courses-workbench course-kb-preview-page">
      <section className="kb-preview-hero">
        <div>
          <span className="eyebrow">COURSE CENTER</span>
          <h2>课程知识库</h2>
          <p>先选择或创建课程，再进入该课程专属的学生画像、知识库、知识图谱、学习路径与评估闭环。</p>
          <div className="kb-preview-actions">
            <button className="primary-action compact-button" onClick={() => setShowCreateForm((value) => !value)} type="button">
              <Plus size={16} />
              创建我的课程
            </button>
            <button className="secondary-action compact-button" onClick={() => currentCourse ? void enterCourse(currentCourse) : setShowCreateForm(true)} type="button">
              <ArrowRight size={16} />
              {currentCourse ? "进入当前课程" : "先创建课程"}
            </button>
          </div>
        </div>
        <div className="kb-hero-visual" aria-hidden="true">
          <div className="kb-window-dots"><i /><i /><i /></div>
          <div className="kb-hero-board">
            <div className="kb-book-card"><i /><span /><span /><span /></div>
            <svg viewBox="0 0 260 142" role="img" aria-label="知识图谱预览">
              <path d="M130 24 L70 64 L130 104 L190 64 Z" fill="none" stroke="#67e8f9" strokeWidth="2.5" />
              <path d="M70 64 L42 108 M70 64 L46 26 M190 64 L218 28 M190 64 L218 110 M130 104 L130 130" stroke="#93c5fd" strokeWidth="2" />
              <circle cx="130" cy="24" fill="#5eead4" r="16" />
              <circle cx="70" cy="64" fill="#60a5fa" r="14" />
              <circle cx="190" cy="64" fill="#fbbf24" r="14" />
              <circle cx="130" cy="104" fill="#86efac" r="14" />
              <circle cx="46" cy="26" fill="#c4b5fd" r="9" />
              <circle cx="42" cy="108" fill="#fda4af" r="9" />
              <circle cx="218" cy="28" fill="#bae6fd" r="9" />
              <circle cx="218" cy="110" fill="#fed7aa" r="9" />
              <circle cx="130" cy="130" fill="#bbf7d0" r="9" />
            </svg>
          </div>
        </div>
      </section>

      <section className="kb-preview-metrics" aria-label="课程概览">
        <div className="kb-preview-metric"><div>{courses.length}</div><span>我的课程</span><strong>{loading ? "同步中" : "已加载"}</strong></div>
        <div className="kb-preview-metric"><div>{currentCourse ? shortCourseLabel(courseKind(currentCourse)) : "未"}</div><span>当前课程</span><strong>{currentCourse?.name ?? "尚未选择"}</strong></div>
        <div className="kb-preview-metric"><div>1:1</div><span>数据范围</span><strong>课程级隔离</strong></div>
        <div className="kb-preview-metric"><div>AI</div><span>学习闭环</span><strong>动态更新</strong></div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      {showCreateForm ? (
        <section className="panel kb-create-course-panel">
          <div className="panel-title">
            <Plus size={18} />
            <h2>创建我的课程</h2>
            <span>创建后进入课程专属画像构建</span>
          </div>
          <form className="form-grid compact-course-form inline-course-form" onSubmit={handleCreateCourse}>
            <label>
              课程名称
              <input
                autoFocus
                name="course-name"
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="例如：数据结构、Java 程序设计"
                value={form.name}
              />
            </label>
            <div className="form-row">
              <label>
                专业方向
                <input
                  name="course-major"
                  onChange={(event) => setForm((current) => ({ ...current, major: event.target.value }))}
                  placeholder="计算机科学与技术"
                  value={form.major}
                />
              </label>
              <label>
                课程层次
                <input
                  name="course-level"
                  onChange={(event) => setForm((current) => ({ ...current, level: event.target.value }))}
                  placeholder="本科 / 入门 / 提高"
                  value={form.level}
                />
              </label>
            </div>
            <label>
              课程说明
              <textarea
                name="course-description"
                onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                placeholder="课程范围、教材版本、重点章节或学习目标"
                rows={3}
                value={form.description}
              />
            </label>
            <div className="form-actions-row">
              <button className="secondary-action" disabled={creating} onClick={() => setShowCreateForm(false)} type="button">
                取消
              </button>
              <button className="primary-action" disabled={creating} type="submit">
                {creating ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
                {creating ? "正在创建" : "创建并构建画像"}
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="panel kb-course-gallery">
        <div className="panel-title">
          <Database size={18} />
          <h2>我的课程</h2>
          <span>{loading ? "同步中" : `${courses.length} 门课程`}</span>
        </div>
        {visibleCourseCards.length ? (
          <div className="kb-course-card-grid">
            {visibleCourseCards.map(renderCourseCard)}
          </div>
        ) : (
          <div className="kb-empty-gallery">
            <Code2 size={26} />
            <strong>还没有课程</strong>
            <span>创建课程后进入知识库页面，可以上传教材或选择 Python / C 内置知识库。</span>
          </div>
        )}
      </section>

      <div className="library-footnote">
        <GitBranch size={15} />
        课程入口页只负责选择当前课程；材料上传、内置知识库、MinerU 解析、Milvus 向量索引和知识图谱生成在进入课程后完成。
      </div>
    </div>
  );
}
