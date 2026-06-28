# Game Map Learning Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the dynamic course learning path into a game-map level selector with automatic remedial re-planning after failed assessments.

**Architecture:** Keep the planner stateless and course-scoped. Extend the existing learning-path endpoint with `plan_type` and `focus_node_id`, then render the response as a mainline/remedial route map in React. Assessment submission writes mastery as it already does, and the frontend routes the user to main or remedial planning based on the submitted score.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React, TypeScript, Vite, lucide-react, CSS.

---

### Task 1: Backend Remedial Planner Contract

**Files:**
- Modify: `apps/api/app/models/learning_path.py`
- Modify: `apps/api/app/routers/courses.py`
- Modify: `apps/api/app/services/learning_path_service.py`
- Test: `apps/api/tests/test_courses_api.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting:
- `POST /api/courses/{id}/learning-paths/plan` accepts `{"plan_type":"remedial","focus_node_id":"outline-section-3-2"}`.
- The response includes `plan_type="remedial"` and `focus_node_id`.
- The remedial path contains the failed node and its prerequisite/parent chain.
- When the same node becomes `good`, the main path no longer prioritizes it as the first active weak node.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_course_learning_path_remedial_mode_focuses_failed_node_and_dependencies -q
```

Expected: FAIL because `plan_type` and `focus_node_id` are not part of the current contract.

- [ ] **Step 3: Implement minimal backend support**

Add:
- `CourseLearningPathRequest`
- `plan_type`, `focus_node_id`, `current_stage_id`, and `pass_threshold` fields on the response model.
- Planner logic for `main` and `remedial`.

- [ ] **Step 4: Verify GREEN**

Run focused learning path tests.

### Task 2: Frontend Game Map Route

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/pages/CourseLearningPathPage.tsx`
- Modify: `apps/web/src/pages/KnowledgeLearningPage.tsx`
- Modify: `apps/web/src/components/AssessmentPanel.tsx`
- Modify: `apps/web/src/styles/app.css`

- [ ] **Step 1: Update API types**

Add `CourseLearningPathRequest`, response fields, and optional payload support in `planCourseLearningPath`.

- [ ] **Step 2: Rebuild route page as a level map**

Render:
- plan mode switch/status badge;
- mastery legend;
- serpentine route rail;
- stage nodes with mastery color, current/locked/passed/remedial labels;
- side panel for dynamic basis and profile.

- [ ] **Step 3: Wire assessment outcome**

After assessment:
- score `< 0.75` navigates to `/courses/:courseId/learning-path?mode=remedial&focus=:nodeId`;
- score `>= 0.75` navigates to `/courses/:courseId/learning-path`.

- [ ] **Step 4: Verify build**

Run:

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

Expected: TypeScript and Vite build pass.

### Task 3: Final Verification

**Files:**
- All modified backend/frontend files.

- [ ] **Step 1: Run backend focused tests**

```powershell
python -m pytest apps/api/tests/test_courses_api.py::test_course_learning_path_uses_graph_profile_and_mastery apps/api/tests/test_courses_api.py::test_course_learning_path_prioritizes_weak_nodes_with_prerequisites apps/api/tests/test_courses_api.py::test_course_learning_path_requires_confirmed_profile apps/api/tests/test_courses_api.py::test_course_learning_path_remedial_mode_focuses_failed_node_and_dependencies apps/api/tests/test_courses_api.py::test_course_learning_path_returns_to_mainline_after_focus_node_passes -q
```

- [ ] **Step 2: Run frontend build**

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

- [ ] **Step 3: Review unstaged changes**

```powershell
git status --short
```
