import { useEffect, useState } from "react";
import { Route, Upload } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { getCourse, type Course } from "../api/client";
import { ErrorBlock, LoadingBlock } from "../components/StateViews";
import { KnowledgeGraphPanel } from "../components/KnowledgeGraphPanel";
import { useAuth } from "../state/auth";

function textValue(record: Record<string, unknown>, key: string, fallback = ""): string {
  const value = record[key];
  return typeof value === "string" ? value : fallback;
}

export function CourseGraphPage() {
  const { courseId } = useParams();
  const { token } = useAuth();
  const navigate = useNavigate();
  const [course, setCourse] = useState<Course>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const numericCourseId = Number(courseId);

  useEffect(() => {
    if (!Number.isFinite(numericCourseId)) {
      setError("课程 ID 无效");
      return;
    }
    setLoading(true);
    setError("");
    getCourse(token, numericCourseId)
      .then(setCourse)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "加载课程失败"))
      .finally(() => setLoading(false));
  }, [numericCourseId, token]);

  if (loading) {
    return <LoadingBlock label="正在加载课程与知识图谱…" />;
  }

  if (!course) {
    return <ErrorBlock message={error || "课程不存在"} onRetry={() => { setError(""); setLoading(true); getCourse(token, numericCourseId).then(setCourse).catch((caught) => setError(caught instanceof Error ? caught.message : "加载课程失败")).finally(() => setLoading(false)); }} />;
  }

  return (
    <div className="page-stack graph-page-workbench">
      <div className="page-heading with-actions product-page-heading graph-product-heading">
        <div>
          <span>Course Knowledge Graph</span>
          <h2>{course.name} · 知识图谱</h2>
          <p>根据本地课程知识库和大模型抽取结果展示课程全部知识结构。颜色只表示掌握情况，点击节点进入知识点学习。</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${course.id}/knowledge-base`)}>
            <Upload size={16} />
            上传材料
          </button>
          <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${course.id}/knowledge-base`)}>
            资料与重建入口
          </button>
          <button className="primary-action compact-button" onClick={() => navigate(`/courses/${course.id}/learning-path`)}>
            <Route size={16} />
            规划学习路径
          </button>
        </div>
      </div>

      <div className="mastery-legend graph-heading-legend">
        <span className="mastery-dot-label mastery-not_started"><i />未学习</span>
        <span className="mastery-dot-label mastery-severe_weak"><i />严重弱项</span>
        <span className="mastery-dot-label mastery-basic"><i />掌握基础</span>
        <span className="mastery-dot-label mastery-good"><i />达标良好</span>
        <span className="mastery-dot-label mastery-proficient"><i />精通</span>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <KnowledgeGraphPanel
        course={course}
        onNodeOpen={(node) => {
          const nodeId = encodeURIComponent(textValue(node, "id", textValue(node, "name", "knowledge")));
          navigate(`/courses/${course.id}/knowledge/${nodeId}`, { state: { node } });
        }}
        token={token}
      />
    </div>
  );
}
