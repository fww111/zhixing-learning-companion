# Dynamic Learning Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build course-level personalized learning paths that combine the confirmed student profile, Neo4j course knowledge graph, and per-user mastery state, then update naturally after assessment results.

**Architecture:** The backend creates a deterministic graph-aware ranking first, then uses DeepSeek only for explanation text and resource recommendation wording. The frontend adds a course-level learning path route that lets the student see the next recommended knowledge points, why each point is next, and jump into the existing knowledge-point learning page.

**Tech Stack:** FastAPI, SQLAlchemy, MySQL/SQLite tests, Neo4j graph adapter, React + Vite + TypeScript, Lucide icons.

---

### Task 1: Backend Learning Path Models

**Files:**
- Modify: `apps/api/app/models/learning_path.py`
- Test: `apps/api/tests/test_courses_api.py`

- [ ] **Step 1: Write the failing model/API shape test**

Add a test that expects course-level stages to carry node ids, mastery status, graph basis, profile basis, and resource types. Use the course endpoint in Task 3 once available:

```python
def test_course_learning_path_uses_graph_profile_and_mastery(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-user", "path@example.com")
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["course_id"] == course["id"]
    assert payload["student_id"] == "user-1"
    assert payload["is_dynamic"] is True
    assert payload["adjustment_basis"]
    assert payload["stages"]
    first = payload["stages"][0]
    assert first["node_id"]
    assert first["topic"]
    assert first["mastery_status"] in {"not_started", "severe_weak", "basic", "good", "proficient"}
    assert first["graph_basis"]
    assert first["profile_basis"]
    assert first["recommended_resource_types"]
    assert first["recommendation_reason"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_course_learning_path_uses_graph_profile_and_mastery -q
```

Expected: `404 Not Found` because the endpoint does not exist yet.

- [ ] **Step 3: Add course-level Pydantic models**

Extend `apps/api/app/models/learning_path.py`:

```python
class CourseLearningStage(BaseModel):
    node_id: str
    topic: str
    level: int = 0
    order: int = 0
    mastery_status: str = "not_started"
    mastery_score: float | None = None
    priority_score: float = 0.0
    estimated_minutes: int = 30
    goal: str
    practice_task: str
    graph_basis: list[str] = Field(default_factory=list)
    profile_basis: list[str] = Field(default_factory=list)
    recommended_resource_types: list[str] = Field(default_factory=list)
    recommendation_reason: str


class CourseLearningPath(BaseModel):
    student_id: str
    course_id: int
    is_dynamic: bool = True
    adjustment_basis: list[str] = Field(default_factory=list)
    stages: list[CourseLearningStage] = Field(default_factory=list)
```

- [ ] **Step 4: Run current tests**

Run:

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_course_learning_path_uses_graph_profile_and_mastery -q
```

Expected: still fails with missing endpoint. That is fine; the schema is ready for Task 2/3.

### Task 2: Dynamic Path Planning Service

**Files:**
- Create: `apps/api/app/services/learning_path_service.py`
- Modify: `apps/api/tests/test_courses_api.py`

- [ ] **Step 1: Add a failing service ranking test**

Create fake graph nodes and mastery rows by using default Python course, then mark one downstream node as weak. Assert that weak/basic/unstarted nodes rank ahead of good/proficient nodes but prerequisites still appear before their dependents.

```python
def test_course_learning_path_prioritizes_weak_nodes_with_prerequisites(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-ranking", "ranking@example.com")
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        service = CourseService(db)
        service.upsert_node_mastery(1, course["id"], "outline-section-3-2", "3.2 列表", 0.42, "列表操作薄弱")
        service.upsert_node_mastery(1, course["id"], "outline-section-1-1", "1.1 初识 Python", 0.96, "已掌握")

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    stages = response.json()["stages"]
    ids = [stage["node_id"] for stage in stages]
    assert "outline-section-3-2" in ids
    assert ids.index("outline-chapter-3") < ids.index("outline-section-3-2")
    assert ids.index("outline-section-1-1") > 5
    weak_stage = next(stage for stage in stages if stage["node_id"] == "outline-section-3-2")
    assert weak_stage["mastery_status"] == "severe_weak"
    assert "掌握度" in "，".join(weak_stage["graph_basis"] + weak_stage["profile_basis"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_course_learning_path_prioritizes_weak_nodes_with_prerequisites -q
```

Expected: fail because endpoint/service is missing.

- [ ] **Step 3: Implement `LearningPathService`**

Create `apps/api/app/services/learning_path_service.py` with:

```python
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import KnowledgeNodeMastery
from app.models.learning_path import CourseLearningPath, CourseLearningStage
from app.models.profile import StudentProfile
from app.models.profile_record import StudentProfileRecord
from app.models.resource import ResourceType
from app.models.user import UserRead
from app.services.course_service import CourseNotFoundError, CourseService


class LearningPathProfileMissingError(RuntimeError):
    pass


class LearningPathGraphMissingError(RuntimeError):
    pass


class LearningPathService:
    def __init__(self, db: Session, course_service: CourseService | None = None) -> None:
        self.db = db
        self.course_service = course_service or CourseService(db)

    def plan_course_path(self, user: UserRead, course_id: int, max_nodes: int = 18) -> CourseLearningPath:
        profile = self._profile(user.id)
        graph = self.course_service.get_knowledge_graph(user.id, course_id)
        nodes = [node for node in graph.get("nodes", []) if str(node.get("id", "")) and int(node.get("level") or 0) > 0]
        edges = graph.get("edges", [])
        if not nodes:
            raise LearningPathGraphMissingError("knowledge graph is empty")
        mastery = self._mastery(user.id, course_id)
        ordered = self._rank_nodes(nodes, edges, mastery, profile)
        stages = [self._stage(node, mastery, profile) for node in ordered[:max_nodes]]
        return CourseLearningPath(
            student_id=profile.student_id,
            course_id=course_id,
            is_dynamic=True,
            adjustment_basis=[
                "根据课程知识图谱的前置关系排序",
                "根据学生画像中的学习目标、薄弱点和资源偏好调整优先级",
                "根据知识点掌握状态动态前移弱项并降低已精通知识点优先级",
            ],
            stages=stages,
        )

    def _profile(self, user_id: int) -> StudentProfile:
        record = self.db.scalar(select(StudentProfileRecord).where(StudentProfileRecord.user_id == user_id))
        if record is None:
            raise LearningPathProfileMissingError("confirmed profile is required")
        return StudentProfile(**record.profile_data)

    def _mastery(self, user_id: int, course_id: int) -> dict[str, KnowledgeNodeMastery]:
        rows = self.db.scalars(
            select(KnowledgeNodeMastery).where(
                KnowledgeNodeMastery.user_id == user_id,
                KnowledgeNodeMastery.course_id == course_id,
            )
        )
        return {row.node_id: row for row in rows}

    def _rank_nodes(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        mastery: dict[str, KnowledgeNodeMastery],
        profile: StudentProfile,
    ) -> list[dict[str, Any]]:
        by_id = {str(node["id"]): node for node in nodes}
        prereq_edges = [
            edge for edge in edges
            if edge.get("relation_type") == "prerequisite"
            and str(edge.get("source_node_id")) in by_id
            and str(edge.get("target_node_id")) in by_id
        ]
        incoming = defaultdict(int)
        outgoing = defaultdict(list)
        for edge in prereq_edges:
            source = str(edge["source_node_id"])
            target = str(edge["target_node_id"])
            incoming[target] += 1
            outgoing[source].append(target)
            incoming.setdefault(source, 0)
        for node_id in by_id:
            incoming.setdefault(node_id, 0)
        ready = sorted([node_id for node_id, count in incoming.items() if count == 0], key=lambda node_id: self._sort_key(by_id[node_id]))
        result = []
        while ready:
            ready.sort(key=lambda node_id: (-self._priority(by_id[node_id], mastery, profile), self._sort_key(by_id[node_id])))
            node_id = ready.pop(0)
            result.append(by_id[node_id])
            for target in outgoing[node_id]:
                incoming[target] -= 1
                if incoming[target] == 0:
                    ready.append(target)
        remaining = [node for node_id, node in by_id.items() if node not in result]
        return result + sorted(remaining, key=lambda node: (-self._priority(node, mastery, profile), self._sort_key(node)))

    def _sort_key(self, node: dict[str, Any]) -> tuple[int, int, str]:
        return (int(node.get("level") or 0), int(node.get("order") or 0), str(node.get("name") or ""))

    def _priority(self, node: dict[str, Any], mastery: dict[str, KnowledgeNodeMastery], profile: StudentProfile) -> float:
        status = mastery.get(str(node["id"])).mastery_status if str(node["id"]) in mastery else "not_started"
        score = {"severe_weak": 120, "basic": 95, "not_started": 80, "good": 35, "proficient": 5}.get(status, 70)
        name = str(node.get("name") or "")
        summary = str(node.get("summary") or "")
        profile_terms = list(profile.weak_points) + list(profile.knowledge_graph_focus)
        if any(term and (term in name or term in summary) for term in profile_terms):
            score += 25
        level = int(node.get("level") or 0)
        if level == 1:
            score += 8
        if level >= 3:
            score += 4
        return score

    def _stage(
        self,
        node: dict[str, Any],
        mastery: dict[str, KnowledgeNodeMastery],
        profile: StudentProfile,
    ) -> CourseLearningStage:
        node_id = str(node["id"])
        topic = str(node.get("name") or node_id)
        row = mastery.get(node_id)
        status = row.mastery_status if row else "not_started"
        score = row.mastery_score if row else None
        resource_types = self._resource_types(profile, status)
        graph_basis = [
            f"图谱层级 L{int(node.get('level') or 0)}，顺序 {int(node.get('order') or 0)}",
            f"掌握度状态：{status}",
        ]
        profile_basis = [
            f"学习目标：{profile.learning_goal}",
            f"资源偏好：{'、'.join(profile.resource_preference) or '综合资源'}",
        ]
        if profile.weak_points:
            profile_basis.append(f"画像薄弱点：{'、'.join(profile.weak_points)}")
        return CourseLearningStage(
            node_id=node_id,
            topic=topic,
            level=int(node.get("level") or 0),
            order=int(node.get("order") or 0),
            mastery_status=status,
            mastery_score=score,
            priority_score=self._priority(node, mastery, profile),
            estimated_minutes=self._estimated_minutes(status, int(node.get("level") or 0)),
            goal=f"掌握{topic}的核心概念、适用场景和常见误区",
            practice_task=f"完成{topic}的短练习，并用自己的话解释关键步骤",
            graph_basis=graph_basis,
            profile_basis=profile_basis,
            recommended_resource_types=resource_types,
            recommendation_reason=f"{topic}依据图谱前置关系和当前掌握状态进入本轮学习路径，资源形式匹配你的画像偏好。",
        )

    def _resource_types(self, profile: StudentProfile, status: str) -> list[str]:
        preferences = set(profile.resource_preference)
        types = [ResourceType.DOCUMENT.value, ResourceType.EXERCISE.value]
        if {"图解", "动画", "视频"} & preferences:
            types.insert(0, ResourceType.MIND_MAP.value)
            types.append(ResourceType.VIDEO.value)
        if {"代码实操", "编程", "实操"} & preferences:
            types.append(ResourceType.CODE_LAB.value)
        if status in {"good", "proficient"}:
            types.append(ResourceType.READING.value)
        return list(dict.fromkeys(types))

    def _estimated_minutes(self, status: str, level: int) -> int:
        base = 25 + max(level - 1, 0) * 8
        if status == "severe_weak":
            base += 20
        elif status == "basic":
            base += 10
        elif status == "proficient":
            base = 15
        return base
```

- [ ] **Step 4: Run service test**

Run:

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_course_learning_path_prioritizes_weak_nodes_with_prerequisites -q
```

Expected: still fails until Task 3 registers the endpoint.

### Task 3: Course Learning Path API

**Files:**
- Modify: `apps/api/app/routers/courses.py`
- Modify: `apps/api/app/schemas/course.py` if response model import is preferred
- Test: `apps/api/tests/test_courses_api.py`

- [ ] **Step 1: Add profile fixture helper in tests**

Add helper to `apps/api/tests/test_courses_api.py`:

```python
from app.models.profile import StudentProfile
from app.models.profile_record import StudentProfileRecord


def confirm_profile_for_user(db, user_id: int, **overrides):
    profile = StudentProfile(
        student_id=f"user-{user_id}",
        major="计算机科学",
        grade="大二",
        learning_goal="系统掌握 Python 程序设计",
        knowledge_foundation="Python 基础一般，列表和函数薄弱",
        learning_style="先图解再练习",
        cognitive_style="先直观理解再代码验证",
        weak_points=["列表", "函数"],
        time_preference="每天晚间 45 分钟",
        resource_preference=["图解", "代码实操", "短练习"],
        motivation="通过课程考试并完成项目",
        constraints=["碎片时间学习"],
        assessment_preference="短练习和代码任务",
        knowledge_graph_focus=["列表", "函数"],
    ).model_copy(update=overrides).with_completion_score()
    db.add(StudentProfileRecord(user_id=user_id, student_id=profile.student_id, profile_data=profile.model_dump(mode="json")))
    db.commit()
    return profile
```

Call this helper before path endpoint tests.

- [ ] **Step 2: Register the endpoint**

In `apps/api/app/routers/courses.py`, import:

```python
from app.models.learning_path import CourseLearningPath
from app.services.learning_path_service import (
    LearningPathGraphMissingError,
    LearningPathProfileMissingError,
    LearningPathService,
)
```

Add route:

```python
@router.post("/{course_id}/learning-paths/plan", response_model=CourseLearningPath)
def plan_course_learning_path(
    course_id: int,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        return LearningPathService(db).plan_course_path(user, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    except LearningPathProfileMissingError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="confirmed profile is required") from None
    except LearningPathGraphMissingError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="knowledge graph is empty") from None
```

- [ ] **Step 3: Run path API tests**

Run:

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_course_learning_path_uses_graph_profile_and_mastery apps/api/tests/test_courses_api.py::test_course_learning_path_prioritizes_weak_nodes_with_prerequisites -q
```

Expected: pass.

- [ ] **Step 4: Add missing-profile test**

Add:

```python
def test_course_learning_path_requires_confirmed_profile(tmp_path):
    client = make_client(tmp_path)
    token = register_user(client, "path-no-profile", "no-profile@example.com")
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 400
    assert response.json()["detail"] == "confirmed profile is required"
```

Run:

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_course_learning_path_requires_confirmed_profile -q
```

Expected: pass.

### Task 4: Frontend API Client and Route

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/router/AppRouter.tsx`
- Create: `apps/web/src/pages/CourseLearningPathPage.tsx`
- Modify: `apps/web/src/pages/CoursesPage.tsx`
- Modify: `apps/web/src/pages/CourseGraphPage.tsx` if graph page header has actions.

- [ ] **Step 1: Extend TypeScript types**

In `apps/web/src/api/client.ts`, add:

```ts
export interface CourseLearningStage {
  node_id: string;
  topic: string;
  level: number;
  order: number;
  mastery_status: string;
  mastery_score?: number | null;
  priority_score: number;
  estimated_minutes: number;
  goal: string;
  practice_task: string;
  graph_basis: string[];
  profile_basis: string[];
  recommended_resource_types: ResourceType[];
  recommendation_reason: string;
}

export interface CourseLearningPath {
  student_id: string;
  course_id: number;
  is_dynamic: boolean;
  adjustment_basis: string[];
  stages: CourseLearningStage[];
}
```

Add function:

```ts
export async function planCourseLearningPath(token: string | undefined, courseId: number): Promise<CourseLearningPath> {
  const response = await fetch(`/api/courses/${courseId}/learning-paths/plan`, {
    method: "POST",
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "生成学习路径失败");
  }
  return response.json();
}
```

- [ ] **Step 2: Add route**

In `apps/web/src/router/AppRouter.tsx`, import `CourseLearningPathPage` and add:

```tsx
<Route element={<CourseLearningPathPage />} path="/courses/:courseId/learning-path" />
```

- [ ] **Step 3: Create course learning path page**

Implement page that:
- loads course by id,
- calls `planCourseLearningPath`,
- shows adjustment basis,
- lists stages with mastery status, recommended resource chips, graph/profile basis,
- navigates to `/courses/:courseId/knowledge/:nodeId` with node id.

Use existing classes where possible: `page-stack`, `panel`, `primary-action`, `secondary-action`, `status-chip`, `path-stage`.

- [ ] **Step 4: Add entry buttons**

Add “学习路径” button from course cards and graph header actions.

- [ ] **Step 5: Build frontend**

Run:

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

Expected: TypeScript and Vite build pass.

### Task 5: Assessment Flow Refresh Hint

**Files:**
- Modify: `apps/web/src/components/AssessmentPanel.tsx`
- Modify: `apps/web/src/pages/KnowledgeLearningPage.tsx`

- [ ] **Step 1: Add callback prop**

Allow `AssessmentPanel` to call `onSubmitted(report)` after successful assessment.

- [ ] **Step 2: Show dynamic path hint**

In `KnowledgeLearningPage`, pass callback that shows a short inline notice:

```tsx
setPathNotice("评估已写回知识图谱，课程学习路径会在下次打开时自动调整。");
```

- [ ] **Step 3: Build frontend**

Run:

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

Expected: build pass.

### Task 6: Verification

**Files:**
- No production edits unless verification reveals a bug.

- [ ] **Step 1: Run focused backend tests**

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_course_learning_path_uses_graph_profile_and_mastery apps/api/tests/test_courses_api.py::test_course_learning_path_prioritizes_weak_nodes_with_prerequisites apps/api/tests/test_courses_api.py::test_course_learning_path_requires_confirmed_profile -q
```

Expected: all pass.

- [ ] **Step 2: Run existing graph/mastery tests**

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_knowledge_graph_nodes_include_default_mastery_status apps/api/tests/test_courses_api.py::test_assessment_updates_knowledge_graph_node_mastery -q
```

Expected: all pass.

- [ ] **Step 3: Run frontend build**

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

Expected: build pass.

- [ ] **Step 4: Manual browser smoke test if services are running**

Navigate:

```text
/courses -> select Python course -> /courses/:id/learning-path -> click a stage -> submit assessment -> return to learning path
```

Expected:
- learning path page loads stages,
- weak/basic/not_started statuses are visible,
- stage click opens knowledge learning page,
- assessment submission updates mastery and the next learning path refresh reflects changed status.
