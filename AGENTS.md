# AGENTS.md

## Project Overview

This repository implements a contest prototype for a personalized learning resource generation, private course knowledge base, and multi-agent learning system.

The current implementation is a runnable **React + Vite + TypeScript frontend** with a **FastAPI backend**. It supports JWT login/registration, DeepSeek V4 Pro powered student-profile interviews, private course material knowledge bases, local BGE-M3 embeddings, Milvus vector retrieval, Neo4j knowledge graph storage, Agentic RAG resource generation, OpenMAIC classroom generation, Qwen TTS, a global intelligent tutoring assistant, course assessment, wrong-question redo, and Mock LLM fallback for demos without API access.

## Repository Layout

- `apps/api/` - FastAPI backend.
  - `app/main.py` - API app entrypoint.
  - `app/agents/` - profile, resource generation, path planning, tutoring, evaluation, and workflow agents.
  - `app/agents/resource_contracts.py` - shared resource blueprint, verification, pedagogy, debate, and decision report builders for the closed-loop resource workflow.
  - `app/models/` - Pydantic schemas for profiles, resources, learning paths, and assessment events.
  - `app/models/course.py` - SQLAlchemy records for private courses, uploaded materials, knowledge chunks, and graph build jobs.
  - `app/models/profile_record.py` - SQLAlchemy records for profile interviews, interview messages, and confirmed student profiles.
  - `app/routers/` - API routes.
  - `app/services/agentic_rag_service.py` - Agentic RAG evidence builder that uses Milvus for recall, MySQL chunks as final evidence, and Neo4j graph constraints.
  - `app/services/tutor_service.py` - intelligent tutoring service that combines course context, image-aware Qwen3.7-Plus calls, Agentic RAG evidence, graph constraints, and profile-event recording.
  - `app/services/openmaic_client.py` - OpenMAIC HTTP client for submitting classroom generation jobs.
  - `app/services/material_task_queue.py` - in-process background queue for uploaded material parsing/indexing.
  - `app/services/mineru_client.py` - MinerU precise parsing API client and result normalization helpers.
  - `app/services/material_parser.py` - PDF/PPT/PPTX parsing orchestration with MinerU first and local fallback.
  - `app/services/vector_service.py` - local BGE-M3/hash embeddings and Milvus vector index adapter, with the legacy Chroma adapter kept only as compatibility code.
  - `app/services/graph_store.py` - Neo4j graph read/write adapter.
  - `app/llm/` - OpenAI-compatible LLM client and Mock LLM fallback.
  - `tests/` - backend tests.
- `apps/web/` - React/Vite frontend.
  - `src/router/` - React Router route definitions and guards.
  - `src/layouts/AppLayout.tsx` - authenticated application shell.
  - `src/pages/` - staged product pages for auth, fixed course selection, course-scoped profile interview, course knowledge base, graph, learning path, assessment, wrong-question book, and knowledge learning.
  - `src/components/` - UI panels, resource cards, post-classroom learning surface, assessment widgets, and global tutor assistant.
  - `src/api/client.ts` - frontend API client and shared response types.
- `data/seed/` - demo course, student profile, and resource seed data.
- `docs/` - technical solution, deployment, testing, demo script, PPT outline, and plan docs.
- `赛题解读.md` - original contest interpretation document.

## Common Commands

Run backend tests from the repository root:

```powershell
conda activate a3
python -m pytest apps/api/tests -q
```

Start the backend:

```powershell
conda activate a3
cd D:\softbei\a3\apps\api
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Install frontend dependencies:

```powershell
cd D:\softbei\a3\apps\web
npm install
```

Start the frontend:

```powershell
cd D:\softbei\a3\apps\web
npm run dev
```

Build the frontend:

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

## Environment

The default local runtime uses DeepSeek with a local MySQL database. Keep Mock LLM available as a fallback for demos without API access:

```text
MOCK_LLM=false
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
TUTOR_VISION_API_KEY=
TUTOR_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TUTOR_VISION_MODEL=qwen3.7-plus
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/softbei?charset=utf8mb4
JWT_SECRET_KEY=replace-with-a-long-random-secret
UPLOAD_DIR=data/uploads
MAX_UPLOAD_SIZE_MB=100
MILVUS_URI=http://127.0.0.1:19530
MILVUS_TOKEN=
MILVUS_USER=
MILVUS_PASSWORD=
MILVUS_DB_NAME=
OPENMAIC_BASE_URL=http://127.0.0.1:3000
OPENMAIC_TIMEOUT_SECONDS=30
VOXCPM_MODEL_ID=D:/softbei/a3/data/models/voxcpm/VoxCPM2
VOXCPM_CACHE_DIR=D:/softbei/a3/data/models/voxcpm
VOXCPM_DEVICE=
VOXCPM_LOCAL_FILES_ONLY=true
VOXCPM_LOAD_DENOISER=false
VOXCPM_OPTIMIZE=false
VOXCPM_FALLBACK_TONE=false
TTS_QWEN_API_KEY=
TTS_QWEN_BASE_URL=
EMBEDDING_PROVIDER=local_bge
EMBEDDING_MODEL=D:/softbei/a3/data/models/embeddings/BAAI/bge-m3
EMBEDDING_DEVICE=cpu
EMBEDDING_CACHE_DIR=D:/softbei/a3/data/models/embeddings
EMBEDDING_BATCH_SIZE=16
EMBEDDING_MAX_CHARS=512
EMBEDDING_MAX_SEQ_LENGTH=512
MINERU_ENABLED=false
MINERU_API_TOKEN=
MINERU_BASE_URL=https://mineru.net
MINERU_MODEL_VERSION=vlm
MINERU_LANGUAGE=ch
MINERU_ENABLE_TABLE=true
MINERU_ENABLE_FORMULA=true
MINERU_IS_OCR=true
MINERU_POLL_INTERVAL_SECONDS=3
MINERU_POLL_TIMEOUT_SECONDS=900
MINERU_FALLBACK_TO_LOCAL=false
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
OCR_LANG=chi_sim+eng
OCR_MODEL_SIZE=mobile
OCR_TEXT_MIN_CHARS=50
OCR_MAX_PAGES=20
OCR_RENDER_SCALE=1.5
```

Use `.env.example` as the reference. Put real provider keys, MinerU tokens, and Neo4j passwords only in local `.env`; never commit them. When integrating a real model provider, keep the Mock mode working as a demo fallback.

BGE-M3 cache environment variables (`HF_HOME` and `SENTENCE_TRANSFORMERS_HOME`) are set inside `vector_service.py` before `sentence_transformers` is imported. Keep any future direct `SentenceTransformer` imports behind the same cache setup, otherwise the model may download to the default user cache instead of `D:/softbei/a3/data/models/embeddings`.

## Development Guidelines

- Keep the frontend in React unless the user explicitly requests a Vue migration.
- Keep the frontend as a routed product flow, not a single all-in-one workspace:
  1. `/auth` handles login and registration only.
  2. `/courses` is the first authenticated page and fixed course selector. It offers exactly `C语言程序设计` and `Python程序设计` as the primary contest courses.
  3. `/courses/:courseId/profile/interview` builds and confirms the selected course's private student profile.
  4. `/courses/:courseId/knowledge-base` uploads course materials and shows chunks.
  5. `/courses/:courseId/graph` builds and visualizes the course knowledge graph.
  6. `/courses/:courseId/knowledge/:nodeId` generates knowledge-point learning resources through the multi-agent workflow.
  7. `/courses/:courseId/assessment` visualizes multi-dimensional assessment and links to the course wrong-question book.
  8. `/courses/:courseId/assessment/wrong-questions` groups missed quiz/code items by graph chapter and allows redo.
- Multi-course isolation is a core requirement:
  - `student_profiles` and `profile_interviews` are course-scoped by `user_id + course_id`; do not use the old global profile as the source of truth for course pages.
  - C and Python courses must keep separate profile data, uploaded materials, MySQL chunks, Milvus collections, Neo4j graph nodes/edges, learning paths, lesson sessions, assessment events, and mastery records.
  - Selecting a course must first ensure the built-in course record exists, then load `GET /api/profiles/me?course_id=<id>`. If no profile exists, route to `/courses/:courseId/profile/interview`; if it exists, route to `/courses/:courseId/knowledge-base`.
  - Route guards for course pages must refresh the current course profile and must not allow a profile from another course to unlock the page.
- Route guards must preserve the product sequence:
  - unauthenticated users go to `/auth`;
  - authenticated users enter `/courses` first;
  - selecting C or Python without a confirmed course profile goes to `/courses/:courseId/profile/interview`;
  - selecting C or Python with a confirmed course profile goes to that course's knowledge-base page;
  - knowledge-point learning must be reached from a graph node or a valid node id.
- Preserve the contest-facing demo flow:
  1. user registration/login with JWT,
  2. multi-turn learning-needs interview,
  3. database-backed student profile,
  4. multi-agent resource generation,
  5. personalized learning path,
  6. assessment and profile update loop.
- The learning-needs conversation must be a true multi-turn interview powered by `deepseek-v4-pro`.
  - Do not generate the complete learning plan from a single textarea submission.
  - Ask one focused question at a time until enough evidence exists for the student profile.
  - Extract and update profile evidence after each user answer.
  - Stop automatically and confirm the profile when required dimensions are complete, normally within about 10 questions.
  - Require a confirmed profile before triggering resource generation; confirmation may come from automatic interview completion or the confirm endpoint.
  - Persist the finalized multi-dimensional student profile to MySQL and associate it with the authenticated user.
- Dialogue profile endpoints are part of the core product flow:
  - `POST /api/profile-interviews` starts a private interview for the authenticated user; send `{ "course_id": <id> }` for course-scoped interviews.
  - `POST /api/profile-interviews/{id}/messages` records one user answer, updates profile evidence, and returns the next focused question.
  - `POST /api/profile-interviews/{id}/confirm` stores the final profile in `student_profiles` for the interview's `course_id`.
  - `GET /api/profiles/me?course_id=<id>` returns the current authenticated user's confirmed profile for that course.
- The active student profile model should include at least these durable dimensions:
  - `major`
  - `grade`
  - `learning_goal`
  - `knowledge_foundation`
  - `learning_style`
  - `cognitive_style`
  - `weak_points`
  - `time_preference`
  - `resource_preference`
  - `motivation`
  - `constraints`
  - `assessment_preference`
  - `knowledge_graph_focus`
  - `confidence_score`
  - `completion_score`
- Resource generation must keep at least these six types:
  - `document`
  - `mind_map`
  - `exercise`
  - `reading`
  - `video`
  - `code_lab`
- Exercise and assessment behavior must remain knowledge-point specific:
  - The exercise agent should generate professional questions for the current course and node, not generic “did you remember this point” prompts.
  - Each parsed quiz item should preserve prompt, options, selected answer, and `correct_answer_index` so assessment and wrong-question redo can score dynamically.
  - Programming exercises should provide requirements, starter code, and expected output only; do not reveal a complete answer in the student-facing prompt.
  - C-language course code labs should use C starter code and C expectations; Python course code labs should use Python starter code.
- OpenMAIC classroom speech should use Aliyun Bailian Qwen TTS by default.
  - Configure `TTS_QWEN_API_KEY` in `OpenMAIC-main/OpenMAIC-main/.env.local` or OpenMAIC settings, select `Qwen TTS（阿里云百炼）`, and use a Qwen voice such as `Cherry`, `Ethan`, or `Serena`.
  - Do not use VoxCPM2 as the default classroom TTS on CPU-only or low-memory environments; local VoxCPM2 can consume several GB of memory and may terminate the backend process.
  - The FastAPI backend still exposes an optional OpenMAIC-compatible VoxCPM2 Python API adapter at `POST /tts/upload`, but it is a fallback/experimental path rather than the primary classroom speech path.
  - If VoxCPM2 is intentionally used, the local weights should live at `D:/softbei/a3/data/models/voxcpm/VoxCPM2`; keep `VOXCPM_LOCAL_FILES_ONLY=true` so synthesis does not hang on Hugging Face network access.
  - `VOXCPM_FALLBACK_TONE=true` is only for connectivity diagnostics. Keep it `false` when validating real speaker/voice behavior.
- Intelligent tutoring assistant:
  - The authenticated app shell should show the bottom-right tutor entry on every page.
  - `POST /api/tutor/chat` is course-scoped and must validate that the current user owns the requested course.
  - Text-only tutoring uses the configured text LLM plus Agentic RAG; image tutoring uses `TUTOR_VISION_MODEL` (default `qwen3.7-plus`) with image data passed as OpenAI-compatible multimodal content.
  - Tutor answers should be model-enhanced explanations grounded in local course evidence, not raw chunk dumps. The current UI intentionally hides raw RAG evidence, structured cards, and graph relation cards from the normal student answer surface.
  - Tutor questions should record `tutor_question_asked` profile events when a course profile exists.
- Knowledge-point resource generation must be driven by the learning path stage's `recommended_resource_types`.
  - When entering `/courses/:courseId/knowledge/:nodeId` from the learning path, pass the stage's recommended resource types to `POST /api/resources/generate`.
  - The backend must generate only the requested modalities unless the request omits `resource_types`, in which case the demo fallback may generate all six resource types.
  - Before generating resources, use Agentic RAG to retrieve local course knowledge-base chunks for the target `course_id` and `node_id`/topic. Milvus is the vector recall layer; the final evidence given to resource agents and OpenMAIC must be MySQL `knowledge_chunks.content`, with MySQL fallback when vector search is unavailable or empty.
  - Include Neo4j graph constraints in the generation context: current node, parent chapter, predecessors, successors, related nodes, and source chunk ids. Do not create modality resources from the topic alone when local chunks or graph constraints exist.
  - Use LangGraph `StateGraph` as the orchestration layer for the analysis-generation-validation-debate-decision closed loop. Keep a deterministic fallback path for environments where `langgraph` has not been installed yet, but `langgraph` must remain listed in `apps/api/requirements.txt`.
  - Each modality should have its own agent identity: `document`, `mind_map`, `exercise`, `reading`, `video`, and `code_lab` are separate agent responsibilities, even if some share helper code.
  - The workflow must expose these reports in the API response: `analysis_plan`, `graph_constraints`, `retrieval_trace`, `verification_report`, `pedagogy_report`, `debate_report`, `decision_report`, and `agent_events`.
  - `agent_events` should make the closed loop visible, including analysis planning, retrieval evidence, each requested modality agent, fact verification, pedagogy verification, debate/cross-validation, and final decision.
  - Decision values should preserve the closed-loop semantics: `accepted`, `retrieve_more`, `revise`, or a deterministic fallback path.
  - DeepSeek V4 Pro should generate the OpenMAIC classroom outline from the Agentic RAG evidence and graph constraints, then `OpenMAICClient` should submit it to `/api/generate-classroom`.
  - OpenMAIC classroom generation is asynchronous. The backend exposes `GET /api/resources/openmaic-jobs/{job_id}` as a same-origin polling proxy, and it must only poll the configured `OPENMAIC_BASE_URL`.
  - Backend OpenMAIC submissions should set `enableTTS=true`. Classroom speech should use OpenMAIC's configured Qwen TTS provider and Qwen voice selection; do not invent unsupported speaker fields in this backend's `/api/generate-classroom` payload.
  - OpenMAIC classroom requirements should include exactly one focused `interactive` scene policy when possible: use `widgetType: visualization3d` for abstract structures such as recursion, memory, pointers, data structures, and algorithm states; `widgetType: code` for browser runnable programming practice; `widgetType: game` for reinforcement/challenge topics; and `widgetType: simulation` for process or parameter exploration.
  - The learning page should use the OpenMAIC frontend classroom as the main learning surface, automatically polling until `/classroom/{id}` is available. It should also show the local knowledge-base chunks used as generation evidence, the retrieval trace, graph constraints, verification scores, debate summary, final decision, and the outline sent to OpenMAIC.
- Student profile should keep at least eight meaningful dimensions.
- Student profile storage should be treated as durable product data, not a transient LLM response.
- Frontend resource generation must remain disabled until `/api/profile-interviews/{id}/confirm` has produced or `/api/profiles/me` has loaded a confirmed profile.
- Course material parsing should use MinerU precise parsing when `MINERU_ENABLED=true`; missing `MINERU_API_TOKEN` should fail fast instead of silently falling back to local OCR. Keep local PDF/PPTX parsing and PaddleOCR available only as an explicit fallback path, and never commit MinerU tokens or other provider secrets.
- Course material upload must stay asynchronous from the user's perspective:
  - upload saves the file and material record, then returns `queued`;
  - `MaterialTaskQueue` runs parsing/indexing in the backend process;
  - frontend polling should handle `queued`, `processing`, `mineru_submitted`, `mineru_polling`, `ocr_running`, `chunking`, `indexing`, `parsed`, `index_failed`, and `failed`;
  - the current queue is in-process, so backend restarts can lose queued or running tasks and the user may need to re-upload or rebuild.
- The course knowledge-base pipeline is:
  1. PDF/PPT/PPTX upload to `UPLOAD_DIR`;
  2. MinerU precise parsing when enabled, otherwise local parser/OCR fallback;
  3. chunking and durable chunk writes to MySQL;
  4. BGE-M3 embedding generation through local `sentence-transformers`;
  5. Milvus course-scoped vector upsert;
  6. DeepSeek V4 Pro graph extraction;
  7. Neo4j graph replacement/query through Bolt.
- The built-in Python demo path uses `POST /api/courses/default-python` to create an idempotent per-user course named `Python 程序设计`, a built-in parsed material record, deterministic MySQL chunks, a successful graph build job, and a Neo4j graph. Keep this path stable for contest demonstrations because it avoids long PDF parsing during live walkthroughs.
- The built-in C demo path uses `POST /api/courses/default-c` to create an idempotent per-user course named `C语言程序设计` with its own deterministic materials, chunks, graph build job, and Neo4j graph. It must remain structurally aligned with the Python demo while using C-language topics.
- Personalized course learning paths must be generated dynamically from the confirmed student profile, current course knowledge graph, and per-node mastery records.
  - The backend source of truth is `POST /api/courses/{course_id}/learning-paths/plan`; frontend refresh/replan actions should call this endpoint again instead of reusing hard-coded schedules.
  - Respect `time_preference` and `constraints` from the profile when calculating `schedule_days`, `weekly_time_budget_minutes`, `scheduled_day`, `scheduled_date`, and `scheduled_minutes`. For example, `每天1小时（含周末）` means all seven days and 420 minutes per week, while `一周1小时，周末才有空` means only Saturday/Sunday and 60 minutes per week.
  - The learning path map should keep chapter nodes as chapter context and switching/navigation options only. Stage/task cards must be concrete knowledge-point nodes under the active chapter, not chapter heading nodes such as `第 1 章 Python 概述`.
  - Mainline planning should stay inside the active incomplete chapter until its knowledge points are passed, then move to the next chapter. Chapter switching may request another chapter explicitly, but returned stage cards should still be knowledge-point tasks.
  - Remedial planning should focus on the failed node, its useful dependencies, and same-chapter weak points. After assessment passes the threshold, replanning should return the student to the mainline path.
  - Keep minimum required tasks separate from additional follow-up tasks: tasks scheduled for today's date are shown as `今日任务`, and students may continue to later tasks when they have extra time.
- Assessment and wrong-question loop:
  - `POST /api/assessments/submit` is the backend entry for comprehensive assessment and wrong-question redo payloads.
  - Assessment should combine classroom state, notes/mind-map/code-lab completion, quiz answers, code output, learning detail, and persisted lesson state.
  - `掌握基础` remains not passed; only `达标良好` and `精通` count as passed.
  - Wrong-question redo uses the original stored quiz/code item. Correct redo should submit a `wrong_question_redo` assessment payload and update score, profile events, mastery, graph color, and path planning.
- Milvus collection names are scoped by course, embedding provider, and model. Long local model paths are shortened and suffixed with a hash to keep names manageable.
- Material deletion should clear uploaded file, MySQL chunks, corresponding Milvus vectors, and stale graph build jobs.
- For new backend behavior, add or update tests first, then implement.
- For frontend changes, verify with `npm run build`; for UI work, keep the interface dense, clear, and education-workbench oriented.
- Do not remove Mock LLM behavior when adding real LLM calls.
- Keep core learning endpoints protected by `Authorization: Bearer <token>`.
- Avoid committing generated or local runtime artifacts such as `node_modules/`, `dist/`, `.pytest_cache/`, `*.log`, `.playwright-mcp/`, `course_resources/`, `data/uploads/`, `data/models/`, and OpenMAIC generated classroom data.

## Verification Checklist

Before reporting work as complete, run the relevant checks:

```powershell
python -m pytest apps/api/tests -q
cd D:\softbei\a3\apps\web
npm run build
```

For end-to-end smoke verification, start both services and verify the routed product flow:

```powershell
cd D:\softbei\a3\apps\api
python -m uvicorn app.main:app --reload --port 8000
cd D:\softbei\a3\apps\web
npm run dev
```

Then use the browser flow: `/auth` register/login -> `/courses` choose `C语言程序设计` or `Python程序设计` -> `/courses/:courseId/profile/interview` auto-confirm that course profile -> `/courses/:courseId/knowledge-base` upload or use the built-in knowledge base -> wait for `parsed` or inspect `index_failed` -> build graph in `/courses/:courseId/graph` -> click a graph node -> verify `/courses/:courseId/knowledge/:nodeId` resource generation. Switch to the other built-in course and confirm its profile, graph, path, lesson state, and assessment data are independent.
