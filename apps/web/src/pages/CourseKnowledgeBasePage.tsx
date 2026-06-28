import { useEffect, useState } from "react";
import { ArrowLeft, FileUp, GitBranch, Loader2, Network, Route, Search, Sparkles } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { applyBuiltInKnowledgeBase, getCourse, type Course } from "../api/client";
import { KnowledgeChunksPanel } from "../components/KnowledgeChunksPanel";
import { MaterialUploadPanel } from "../components/MaterialUploadPanel";
import { useAuth } from "../state/auth";
import { persistCurrentCourse } from "../state/currentCourse";

type BuiltInKnowledgeBaseTemplate = "python" | "c";

const builtInKnowledgeBases: Array<{
  key: BuiltInKnowledgeBaseTemplate;
  title: string;
  shortTitle: string;
  description: string;
  focus: string[];
}> = [
  {
    key: "python",
    title: "Python 程序设计",
    shortTitle: "Python",
    description: "使用内置 Python 教材知识库，快速写入切片、向量索引和课程知识图谱。",
    focus: ["基础语法", "函数", "数据结构", "项目实践"]
  },
  {
    key: "c",
    title: "C语言程序设计",
    shortTitle: "C 语言",
    description: "使用内置 C 语言教材知识库，覆盖指针、数组、函数、结构体等核心知识点。",
    focus: ["指针", "数组", "函数", "结构体"]
  }
];

function courseCoverKind(course: Course): "c" | "python" | "custom" {
  if (course.description.includes("built-in:c")) {
    return "c";
  }
  if (course.description.includes("built-in:python")) {
    return "python";
  }
  return "custom";
}

export function CourseKnowledgeBasePage() {
  const { courseId } = useParams();
  const { token } = useAuth();
  const navigate = useNavigate();
  const [course, setCourse] = useState<Course>();
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [applyingTemplate, setApplyingTemplate] = useState<BuiltInKnowledgeBaseTemplate | "">("");
  const [error, setError] = useState("");
  const numericCourseId = Number(courseId);

  useEffect(() => {
    let cancelled = false;
    if (!Number.isFinite(numericCourseId)) {
      setError("课程 ID 无效");
      return;
    }

    setLoading(true);
    setError("");
    getCourse(token, numericCourseId)
      .then((nextCourse) => {
        if (cancelled) {
          return;
        }
        setCourse(nextCourse);
        persistCurrentCourse(nextCourse);
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "加载课程失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [numericCourseId, token]);

  function handleMaterialsChanged() {
    setRefreshKey((current) => current + 1);
  }

  async function handleApplyBuiltInKnowledgeBase(template: BuiltInKnowledgeBaseTemplate) {
    if (!course) {
      return;
    }
    const option = builtInKnowledgeBases.find((item) => item.key === template);
    const confirmed = window.confirm(
      `确认使用「${option?.title ?? template}」内置知识库构建当前课程「${course.name}」吗？这会把内置教材切片和知识图谱写入当前课程。`
    );
    if (!confirmed) {
      return;
    }

    setApplyingTemplate(template);
    setError("");
    try {
      const nextCourse = await applyBuiltInKnowledgeBase(token, course.id, template);
      setCourse(nextCourse);
      persistCurrentCourse(nextCourse);
      handleMaterialsChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "使用内置知识库失败");
    } finally {
      setApplyingTemplate("");
    }
  }

  if (loading) {
    return <div className="route-loading">正在加载课程知识库</div>;
  }

  if (!course) {
    return <div className="error">{error || "课程不存在"}</div>;
  }

  return (
    <div className="page-stack course-kb-preview-page course-material-workspace">
      <section className="kb-preview-hero kb-material-hero">
        <div className="kb-workspace-copy">
          <span className="eyebrow">COURSE KNOWLEDGE BASE</span>
          <h2>{course.name} · 知识库构建</h2>
          <p>
            这里是当前课程的教材知识库工作区。上传 PDF/PPT/PPTX 后，后台会完成 MinerU 解析、MySQL 切片入库、
            BGE-M3 向量化与 Milvus 索引，后续知识图谱、学习路径和课堂生成都使用这门课的独立数据。
          </p>
          <div className="kb-preview-actions">
            <button className="primary-action compact-button" onClick={() => document.getElementById("material-upload")?.scrollIntoView({ behavior: "smooth", block: "start" })} type="button">
              <FileUp size={16} />
              上传课程教材
            </button>
            <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${course.id}/graph`)} type="button">
              <Network size={16} />
              查看知识图谱
            </button>
            <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${course.id}/learning-path`)} type="button">
              <Route size={16} />
              学习路径
            </button>
            <button className="secondary-action compact-button" onClick={() => navigate("/courses")} type="button">
              <ArrowLeft size={16} />
              返回课程入口
            </button>
          </div>
        </div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="panel kb-builtin-panel kb-workspace-builtin" id="built-in-examples">
        <div className="panel-title">
          <Sparkles size={18} />
          <h2>使用内置知识库</h2>
          <span>可替代上传教材，直接为当前课程写入示例知识库</span>
        </div>
        <div className="kb-builtin-grid">
          {builtInKnowledgeBases.map((option) => {
            const coverKind = courseCoverKind(course);
            const isCurrentTemplate = coverKind === option.key;
            const isApplying = applyingTemplate === option.key;
            return (
              <article className={`kb-builtin-card ${option.key} ${isCurrentTemplate ? "active" : ""}`} key={option.key}>
                <div className={`kb-builtin-cover ${option.key}`} aria-hidden="true">
                  <svg viewBox="0 0 220 124">
                    <path d="M20 88 C48 48, 84 98, 116 54 S170 34, 202 76" fill="none" stroke="rgba(255,255,255,.72)" strokeWidth="5" />
                    <rect fill="rgba(255,255,255,.2)" height="46" rx="9" width="54" x="28" y="22" />
                    <rect fill="rgba(255,255,255,.52)" height="10" rx="5" width="70" x="100" y="30" />
                    <rect fill="rgba(255,255,255,.32)" height="10" rx="5" width="92" x="100" y="52" />
                  </svg>
                  <strong>{option.shortTitle}</strong>
                </div>
                <div className="kb-builtin-meta">
                  <h3>{option.title}</h3>
                  <p>{option.description}</p>
                  <div className="tag-row">{option.focus.map((item) => <span className="tag" key={item}>{item}</span>)}</div>
                </div>
                <button
                  className="primary-action"
                  disabled={Boolean(applyingTemplate)}
                  onClick={() => void handleApplyBuiltInKnowledgeBase(option.key)}
                  type="button"
                >
                  {isApplying ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />}
                  {isApplying ? "正在写入" : isCurrentTemplate ? "重新使用" : "使用内置"}
                </button>
              </article>
            );
          })}
        </div>
      </section>

      <section className="kb-real-workbench kb-material-workbench" id="material-upload">
        <div className="panel-title">
          <GitBranch size={18} />
          <h2>教材解析与索引工作台</h2>
          <span>上传、解析、向量化、检索</span>
        </div>
        <div className="course-tools-grid material-workbench-grid">
          <MaterialUploadPanel course={course} onMaterialsChanged={handleMaterialsChanged} token={token} />
          <KnowledgeChunksPanel course={course} refreshKey={refreshKey} token={token} />
        </div>
      </section>

      <section className="kb-workspace-next">
        <article>
          <Network size={18} />
          <div>
            <strong>生成知识图谱</strong>
            <p>资料入库后，进入知识图谱页面提取课程章节、知识点和依赖关系。</p>
          </div>
          <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${course.id}/graph`)} type="button">
            查看图谱
          </button>
        </article>
        <article>
          <Search size={18} />
          <div>
            <strong>验证知识切片</strong>
            <p>使用右侧语义检索检查教材内容是否完整，确认后再进入学习路径规划。</p>
          </div>
          <button className="secondary-action compact-button" onClick={() => document.querySelector<HTMLInputElement>(".search-row input")?.focus()} type="button">
            检索切片
          </button>
        </article>
      </section>
    </div>
  );
}
