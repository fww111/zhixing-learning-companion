import { FormEvent, useEffect, useMemo, useState } from "react";
import { BookOpen, Database, Loader2, Plus } from "lucide-react";
import {
  createCourse,
  listCourses,
  type Course,
  type CourseCreatePayload
} from "../api/client";
import { KnowledgeChunksPanel } from "./KnowledgeChunksPanel";
import { KnowledgeGraphPanel } from "./KnowledgeGraphPanel";
import { MaterialUploadPanel } from "./MaterialUploadPanel";

interface CourseKnowledgeBaseProps {
  token: string;
}

const initialCourseForm: CourseCreatePayload = {
  name: "",
  major: "",
  level: "",
  description: ""
};

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

export function CourseKnowledgeBase({ token }: CourseKnowledgeBaseProps) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<number | undefined>();
  const [form, setForm] = useState<CourseCreatePayload>(initialCourseForm);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  async function loadCourses() {
    setLoading(true);
    setError("");
    try {
      const nextCourses = await listCourses(token);
      setCourses(nextCourses);
      setSelectedCourseId((current) => {
        if (current && nextCourses.some((course) => course.id === current)) {
          return current;
        }
        return nextCourses[0]?.id;
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载课程失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadCourses();
  }, [token]);

  const selectedCourse = useMemo(
    () => courses.find((course) => course.id === selectedCourseId),
    [courses, selectedCourseId]
  );

  async function handleCreateCourse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = {
      name: form.name.trim(),
      major: form.major?.trim() || "",
      level: form.level?.trim() || "",
      description: form.description?.trim() || ""
    };

    if (!payload.name) {
      setError("课程名称不能为空");
      return;
    }

    setCreating(true);
    setError("");
    try {
      const created = await createCourse(token, payload);
      setCourses((current) => [...current, created]);
      setSelectedCourseId(created.id);
      setForm(initialCourseForm);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建课程失败");
    } finally {
      setCreating(false);
    }
  }

  function handleMaterialsChanged() {
    setRefreshKey((current) => current + 1);
  }

  return (
    <section className="panel course-kb">
      <div className="course-kb-header">
        <div className="panel-title course-kb-title">
          <Database size={18} />
          <div>
            <h2>课程知识库</h2>
            <p>课程资料、知识切片和图谱构建工作区</p>
          </div>
        </div>
        <button className="secondary-action compact-button" disabled={loading} onClick={loadCourses}>
          {loading ? <Loader2 className="spin" size={16} /> : <BookOpen size={16} />}
          刷新课程
        </button>
      </div>

      {error ? <div className="error compact-error">{error}</div> : null}

      <div className="course-kb-grid">
        <aside className="course-sidebar">
          <form className="course-form" onSubmit={handleCreateCourse}>
            <div className="form-grid">
              <label>
                课程名称
                <input
                  value={form.name}
                  onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="机器学习基础"
                />
              </label>
              <label>
                专业
                <input
                  value={form.major}
                  onChange={(event) => setForm((current) => ({ ...current, major: event.target.value }))}
                  placeholder="计算机科学"
                />
              </label>
              <label>
                层次
                <input
                  value={form.level}
                  onChange={(event) => setForm((current) => ({ ...current, level: event.target.value }))}
                  placeholder="大二 / 入门"
                />
              </label>
              <label>
                说明
                <textarea
                  rows={3}
                  value={form.description}
                  onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                  placeholder="课程范围、重点章节或资料来源"
                />
              </label>
            </div>
            <button className="primary-action" disabled={creating} type="submit">
              {creating ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
              {creating ? "创建中" : "创建课程"}
            </button>
          </form>

          <div className="course-list" aria-label="课程列表">
            {courses.length > 0 ? (
              courses.map((course) => (
                <button
                  className={`course-list-item ${course.id === selectedCourseId ? "active" : ""}`}
                  key={course.id}
                  onClick={() => setSelectedCourseId(course.id)}
                >
                  <strong>{course.name}</strong>
                  <span>{course.major || "未设置专业"} · {course.level || "未设置层次"}</span>
                  <small>{course.status} · {formatDate(course.updated_at)}</small>
                </button>
              ))
            ) : (
              <div className="empty compact-empty">{loading ? "正在加载课程" : "暂无课程"}</div>
            )}
          </div>
        </aside>

        <div className="course-detail">
          {selectedCourse ? (
            <>
              <div className="selected-course-head">
                <div>
                  <h3>{selectedCourse.name}</h3>
                  <p>{selectedCourse.description || "暂无课程说明"}</p>
                </div>
                <div className="course-meta-row">
                  <span>{selectedCourse.major || "未设置专业"}</span>
                  <span>{selectedCourse.level || "未设置层次"}</span>
                  <span>{selectedCourse.status}</span>
                </div>
              </div>

              <div className="course-tools-grid">
                <MaterialUploadPanel token={token} course={selectedCourse} onMaterialsChanged={handleMaterialsChanged} />
                <KnowledgeChunksPanel token={token} course={selectedCourse} refreshKey={refreshKey} />
                <KnowledgeGraphPanel token={token} course={selectedCourse} />
              </div>
            </>
          ) : (
            <div className="empty selected-course-empty">创建或选择课程后管理资料和图谱。</div>
          )}
        </div>
      </div>
    </section>
  );
}
