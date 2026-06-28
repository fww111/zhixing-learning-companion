# Enterprise Learning Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the enterprise learning workbench flow with a built-in Python knowledge base and polished SaaS-style page layout.

**Architecture:** Add an idempotent backend endpoint that seeds a per-user built-in Python course, chunks, graph build job, and Neo4j graph. Refactor the `/courses` frontend into a knowledge-base center with two primary paths: built-in Python and custom upload. Apply a cohesive enterprise UI layer through shared CSS tokens and component-level layout adjustments.

**Tech Stack:** FastAPI, SQLAlchemy, MySQL/SQLite tests, Neo4j graph store abstraction, React, Vite, TypeScript, Lucide icons, CSS.

---

### Task 1: Backend Default Python Knowledge Base

**Files:**
- Modify: `apps/api/app/services/course_service.py`
- Modify: `apps/api/app/routers/courses.py`
- Modify: `apps/api/app/schemas/course.py`
- Modify: `apps/api/tests/test_courses_api.py`

- [x] **Step 1: Write failing backend tests**

Add tests that call `POST /api/courses/default-python`, assert idempotency, assert chunks exist, assert graph is non-empty, and assert another user cannot access the returned course id.

- [x] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONIOENCODING='utf-8'; C:\Users\Administrator\.conda\envs\a3\python.exe -m pytest apps/api/tests/test_courses_api.py -q
```

Expected: new default Python endpoint tests fail with `404 Not Found`.

- [x] **Step 3: Implement seed data and service method**

Add `CourseService.ensure_default_python_course(user_id)` that:

- finds an existing course named `Python 程序设计` with a built-in marker in description
- creates it if absent
- inserts deterministic chunks if absent
- writes a Python graph via `graph_store_cls().replace_course_graph(...)`
- adds a successful `GraphBuildJob` if absent
- returns the `Course`

- [x] **Step 4: Add router endpoint**

Add:

```python
@router.post("/default-python", response_model=CourseRead)
def ensure_default_python_course(...)
```

- [x] **Step 5: Run backend tests**

Run the same pytest command. Expected: all selected tests pass.

### Task 2: Frontend API And Knowledge-Base Center Flow

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/pages/CoursesPage.tsx`

- [x] **Step 1: Add frontend API client**

Add `ensureDefaultPythonCourse(token: string): Promise<Course>` calling `POST /api/courses/default-python`.

- [x] **Step 2: Refactor `CoursesPage` flow**

Replace the current simple create/list page with:

- profile summary header
- Python example knowledge-base action card
- custom course creation action panel
- existing course library section

The Python action should call `ensureDefaultPythonCourse`, update course list, and navigate to `/courses/:id/graph`.

- [x] **Step 3: Run frontend build**

Run:

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

Expected: build passes.

### Task 3: Enterprise Layout And Visual System

**Files:**
- Modify: `apps/web/src/layouts/AppLayout.tsx`
- Modify: `apps/web/src/pages/AuthPage.tsx`
- Modify: `apps/web/src/pages/ProfileInterviewPage.tsx`
- Modify: `apps/web/src/pages/CourseKnowledgeBasePage.tsx`
- Modify: `apps/web/src/pages/CourseGraphPage.tsx`
- Modify: `apps/web/src/pages/KnowledgeLearningPage.tsx`
- Modify: `apps/web/src/styles/app.css`

- [x] **Step 1: Define CSS tokens**

Update `:root` with enterprise tokens for background, surface, border, text, primary, accent, success, warning, danger, shadows, and radius.

- [x] **Step 2: Refine app shell**

Make `AppLayout` feel like a mature workbench:

- topbar with product name and concise status
- left rail with staged navigation
- active and disabled states
- content surface with consistent spacing

- [x] **Step 3: Refine core page surfaces**

Apply consistent page heading, panel, action card, status chip, and grid styling. Keep card radius at 8px or below.

- [x] **Step 4: Preserve graph mastery colors**

Ensure graph mastery colors still map to gray, red, orange, light green, and green.

- [x] **Step 5: Run frontend build**

Run `npm run build`. Expected: build passes.

### Task 4: Full Verification And Review

**Files:**
- Review all modified files.

- [x] **Step 1: Run backend focused tests**

```powershell
$env:PYTHONIOENCODING='utf-8'; C:\Users\Administrator\.conda\envs\a3\python.exe -m pytest apps/api/tests/test_course_models.py apps/api/tests/test_courses_api.py -q
```

- [x] **Step 2: Run backend full tests**

```powershell
$env:PYTHONIOENCODING='utf-8'; C:\Users\Administrator\.conda\envs\a3\python.exe -m pytest apps/api/tests -q
```

- [x] **Step 3: Run frontend build**

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

- [x] **Step 4: Check git diff**

Review:

```powershell
git status --short
git diff --stat
git diff --check
```

- [x] **Step 5: Report completion**

Summarize changed files, verification output, and any remaining manual browser verification needs.
