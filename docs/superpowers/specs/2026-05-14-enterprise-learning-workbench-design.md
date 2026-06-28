# Enterprise Learning Workbench Design

> Status note: this is an older UI/workbench design spec. The current implementation is course-first and course-scoped: `/courses` is the authenticated entry, each course has its own profile, knowledge base, graph, path, lesson state, assessment, wrong-question book, and tutor context. Current technical facts are maintained in `docs/current-technical-overview.md`.

## Goal

Refine the current contest prototype into an enterprise-grade learning workbench while preserving the existing core capabilities:

- user registration and login
- profile-gated product flow
- multi-turn student profile interview
- course-local knowledge base construction
- course knowledge graph visualization
- knowledge-point learning resource generation
- assessment-driven graph mastery colors

The current polished flow supports both `Python程序设计` and `C语言程序设计` as contest courses, while still supporting user-created courses and uploaded PDF/PPT/PPTX materials.

## Product Flow

The application keeps a strict staged route flow:

1. Unauthenticated users enter `/auth`.
2. Authenticated users enter `/courses`.
3. Selecting a course checks `GET /api/profiles/me?course_id=<id>`.
4. Users without a confirmed course profile enter `/courses/:courseId/profile/interview`.
5. Users with a confirmed profile enter `/courses/:courseId/knowledge-base`.
6. Knowledge-base construction supports uploaded PDF/PPT/PPTX files or explicit confirmation of a built-in course knowledge base.
7. The course then flows through graph, learning path, knowledge-point learning, assessment, and wrong-question redo.
8. Assessment on a knowledge point updates course-scoped mastery, profile, graph color, and dynamic learning path.

## Built-In Python Knowledge Base

The built-in Python course is the stable demonstration path. It avoids depending on long PDF parsing during a live demo.

Backend behavior:

- Add `POST /api/courses/default-python`.
- The endpoint is protected by the current authenticated user.
- If the user already has the built-in Python course, return it instead of creating duplicates.
- If absent, create a course such as:
  - name: `Python 程序设计`
  - major: user's profile major when available, otherwise `计算机科学`
  - level: user's profile grade when available, otherwise `本科`
  - description: built-in course knowledge base for Python programming fundamentals
- Seed durable local knowledge chunks for the Python course.
- Seed or replace the Neo4j graph for this user and course.
- Create a successful graph build job so `/knowledge-graph` returns the graph immediately.

Initial Python graph coverage:

- Python 课程导论
- 变量与数据类型
- 表达式与运算符
- 条件分支
- 循环结构
- 函数定义与调用
- 列表、元组、字典、集合
- 字符串处理
- 文件读写
- 异常处理
- 模块与包
- 面向对象基础
- 综合实践

The built-in graph should include containment and prerequisite relations. It may include simple application or common-mistake relations where useful.

## Custom Course Knowledge Base

The existing upload path remains:

- user creates a course
- user uploads PDF/PPT/PPTX
- backend parses with MinerU when enabled
- pages are chunked
- chunks are stored in MySQL
- embeddings use local BGE-M3 and Milvus; ChromaDB is no longer the active vector retrieval layer
- the semantic graph is generated and stored in Neo4j

The UI should make custom parsing state obvious:

- uploaded
- parsing
- chunking
- indexing
- parsed
- failed
- index failed

Error states must provide a retry or recovery path, such as rebuilding vector index or deleting failed materials.

## Page Architecture

### Auth Page

Purpose: account entry only.

Design:

- centered authentication panel
- product identity in a restrained brand header
- login/register tabs
- clear form labels and error states
- no marketing landing page

After authentication, navigation is handled by profile status.

### Profile Interview Page

Purpose: build a student profile before any learning flow starts.

Design:

- two-column workbench
- left: conversational interview panel
- right: live profile completeness panel
- progress and status should be visible
- no manual profile confirmation when backend marks the profile complete
- preserve the existing multi-turn DeepSeek interview behavior

### Course Knowledge-Base Center

Route: `/courses`

Purpose: the main post-profile landing page.

Design:

- page header with user profile summary:
  - major
  - grade
  - learning goal
  - weak points
  - resource preference
- primary task band with two large action panels:
  - Python example knowledge base
  - custom course upload
- below that, a compact course library grid or table:
  - course name
  - source type: built-in or custom
  - material count when available
  - graph status
  - updated date
  - actions: knowledge base, graph

The Python example action should be the most stable and prominent route for demonstrations.

### Course Knowledge-Base Page

Route: `/courses/:courseId/knowledge-base`

Purpose: manage uploaded materials and local chunks.

Design:

- split workbench layout
- left: upload/material management
- right: parsed chunks and semantic search
- visible parsing pipeline status
- clear buttons for upload, refresh, rebuild vector index, delete failed material

### Course Graph Page

Route: `/courses/:courseId/graph`

Purpose: visualize the course knowledge structure.

Design:

- large graph canvas
- right or bottom description panel depending on viewport
- mastery-color legend:
  - gray: 未学习
  - red: 严重弱项
  - orange: 掌握基础
  - light green: 达标良好
  - green: 精通
- graph node type remains textual metadata, not color
- clear action to enter selected knowledge-point learning

### Knowledge Learning Page

Route: `/courses/:courseId/knowledge/:nodeId`

Purpose: multi-agent learning resource generation for one knowledge point.

Design:

- learning path and generated resources as the main content
- profile and agent timeline as side context
- assessment panel writes mastery back to the graph
- return-to-graph action remains obvious

## Enterprise UI Direction

Use a professional, spacious, enterprise SaaS workbench style.

Visual principles:

- light background, white surfaces, low-saturation borders
- restrained navy/blue primary palette
- green only for success and mastery states
- red only for errors and severe weakness
- no decorative orbs, bokeh, heavy gradients, or marketing-style hero sections
- no nested cards
- cards only for specific tasks, repeated items, modals, and tool panels
- dense but readable information layout
- stable dimensions for toolbar buttons, status chips, graph areas, and repeated cards
- use lucide icons for navigation/actions
- no emoji as structural UI

Suggested tokens:

- primary: `#0f172a`
- accent: `#0369a1`
- success: `#16a34a`
- warning: `#f59e0b`
- danger: `#dc2626`
- background: `#f8fafc`
- surface: `#ffffff`
- muted: `#f1f5f9`
- border: `#e2e8f0`
- text main: `#020617`
- text muted: `#64748b`
- radius: `8px`

## Routing And Guard Requirements

- `/auth` must not be accessible as the main route for an already authenticated user.
- authenticated users without a confirmed profile must be redirected to `/profile/interview`.
- authenticated users with a confirmed profile must enter `/courses`.
- resource generation and graph learning routes stay protected.
- knowledge learning must continue to be reached from a valid graph node id or node state.

## Data Model Requirements

Built-in Python course support may reuse existing `courses`, `knowledge_chunks`, `graph_build_jobs`, and Neo4j graph storage.

The endpoint must be idempotent per user. A practical implementation can identify the built-in course by a stable course name and description marker, or by an added source marker if the data model is extended.

Per-node mastery remains durable in `knowledge_node_masteries`.

## Error Handling

- If default Python graph seeding fails, show a recoverable error and allow retry.
- If upload parsing fails, show material-level error details and allow delete/retry.
- If graph generation fails for a custom course, leave the knowledge base page usable.
- If assessment writeback fails, keep generated resources visible and show an inline retry message.

## Testing Requirements

Backend:

- default Python endpoint creates a course for a profiled user
- repeated calls return the same course
- created Python course has chunks
- created Python course returns a non-empty knowledge graph
- user A cannot access user B's default Python course

Frontend:

- build passes with `npm run build`
- authenticated/no-profile users route to interview
- profiled users route to knowledge-base center
- Python example action calls the default endpoint and navigates to graph
- custom course creation/upload path remains available

End-to-end smoke:

- login
- ensure profile exists or complete interview
- click Python example knowledge base
- view graph
- click a graph node
- generate learning resources
- submit an assessment
- return to graph and see node mastery color update

## Non-Goals

- No full LMS administration module.
- No multi-user teacher dashboard in this phase.
- No manual graph editing or node dragging.
- No replacement of the existing upload/MinerU/BGE-M3/Neo4j pipeline.
- No landing-page redesign; this remains an authenticated workbench application.
