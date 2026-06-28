# Dialogue Student Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a database-backed, multi-turn student profile interview that asks one focused question at a time, incrementally updates a multi-dimensional profile, and gates resource generation until the profile is confirmed.

**Architecture:** Add SQLAlchemy interview/message/profile tables and a `ProfileInterviewService` that owns interview state, LLM/mock question generation, profile merging, and confirmation. Expose protected FastAPI endpoints under `/api/profile-interviews` and `/api/profiles/me`, then replace the frontend textarea workflow with a compact one-question-at-a-time interview panel.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, MySQL/SQLite test support, React/Vite/TypeScript, DeepSeek-compatible `LLMClient` with Mock fallback.

---

### Task 1: Backend Interview Contract

**Files:**
- Modify: `apps/api/tests/test_profile_interviews.py`
- Create: `apps/api/app/models/profile_record.py`
- Create: `apps/api/app/services/profile_interview_service.py`
- Modify: `apps/api/app/routers/profiles.py`
- Modify: `apps/api/app/db.py`

- [ ] Write failing tests for creating an interview, submitting answers, confirming a profile, reading `/api/profiles/me`, and cross-user isolation.
- [ ] Run `conda activate a3; python -m pytest apps/api/tests/test_profile_interviews.py -q` and verify the new endpoints fail before implementation.
- [ ] Add SQLAlchemy models for `profile_interviews`, `profile_messages`, and `student_profiles`.
- [ ] Add service methods: `start_interview`, `answer_interview`, `confirm_interview`, `get_my_profile`.
- [ ] Keep Mock LLM deterministic and make real DeepSeek calls only through the existing `LLMClient`.
- [ ] Run the focused test file until it passes.

### Task 2: Profile Schema Upgrade

**Files:**
- Modify: `apps/api/app/models/profile.py`
- Modify: `apps/api/app/agents/profile_agent.py`
- Modify: `apps/api/tests/test_profile_agent.py`

- [ ] Write failing tests proving the profile has expanded dimensions, completion score, evidence, and interview-derived fields.
- [ ] Extend `StudentProfile` with `motivation`, `constraints`, `assessment_preference`, `knowledge_graph_focus`, `confidence_score`, and completion helpers while preserving existing fields consumed by agents.
- [ ] Make `ProfileAgent` normalize missing LLM keys into the expanded schema.
- [ ] Run `conda activate a3; python -m pytest apps/api/tests/test_profile_agent.py apps/api/tests/test_schemas.py -q`.

### Task 3: Frontend Interview Workflow

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Create: `apps/web/src/components/ProfileInterviewPanel.tsx`
- Modify: `apps/web/src/components/ProfilePanel.tsx`
- Modify: `apps/web/src/pages/Workspace.tsx`
- Modify: `apps/web/src/styles/app.css`

- [ ] Add TypeScript API types and client calls for profile interviews and `/api/profiles/me`.
- [ ] Replace the one-shot textarea workflow with a focused interview panel showing question, answer box, transcript, profile completion, and confirm action.
- [ ] Disable resource generation until a confirmed profile exists; generate from a synthesized conversation based on the confirmed profile to keep existing resource endpoint compatible.
- [ ] Run `npm run build`.

### Task 4: Documentation, Audit, and Verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md` if command or flow details change.

- [ ] Update `AGENTS.md` to document the dialogue-first profile rules and the new endpoints.
- [ ] Run `conda activate a3; python -m pytest apps/api/tests -q`.
- [ ] Run `cd apps/web; npm run build`.
- [ ] Perform code audit with findings first: security, tenant isolation, data durability, frontend state races, missing tests.
- [ ] Commit the completed work.
