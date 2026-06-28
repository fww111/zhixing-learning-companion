# Tutor Assistant Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a global course-scoped multi-agent tutoring workbench with Agentic RAG grounding, visible analysis-retrieval-generation-verification-decision stages, and a polished floating frontend.

**Architecture:** Add a protected FastAPI tutor endpoint that reuses `AgenticRAGService` and `CourseService` to produce course-isolated evidence, graph constraints, agent events, multimodal cards, and suggested actions. Add a global React floating workbench mounted in `AppLayout`, with a small model layer for route/course context and response rendering so UI logic is testable without browser automation.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, pytest, React, Vite, TypeScript, Lucide icons, existing CSS.

---

## File Structure

- Create `apps/api/app/schemas/tutor.py`
  - Pydantic request/response contracts for tutor chat, agent events, evidence chunks, multimodal cards, verification, and decisions.
- Create `apps/api/app/services/tutor_service.py`
  - Course-scoped tutoring orchestration. Owns analysis, RAG retrieval, deterministic/mock answer generation, verification, and final response shape.
- Create `apps/api/app/routers/tutor.py`
  - Protected `/api/tutor/chat` route using `current_user`, `get_db`, `LLMClient`, `CourseService`, and `TutorService`.
- Modify `apps/api/app/main.py`
  - Include the tutor router.
- Create `apps/api/tests/test_tutor_chat.py`
  - Backend TDD tests for auth, course isolation, MySQL evidence, graph constraints, no-evidence fallback, and agent events.
- Modify `apps/web/src/api/client.ts`
  - Add tutor request/response types and `sendTutorMessage`.
- Create `apps/web/src/components/tutorAssistantModel.ts`
  - Pure helpers for current course resolution, page context, node id extraction, agent stage ordering, and response display flags.
- Create `apps/web/src/components/tutorAssistantModel.test.ts`
  - Frontend model tests.
- Create `apps/web/src/components/TutorAssistantFloating.tsx`
  - Global floating button and panel state.
- Create `apps/web/src/components/TutorAssistantPanel.tsx`
  - Workbench layout, input area, messages, evidence, multimodal cards, and agent timeline.
- Modify `apps/web/src/layouts/AppLayout.tsx`
  - Mount the global assistant for authenticated pages.
- Modify `apps/web/src/styles/app.css`
  - Add enterprise-style floating assistant, panel, timeline, evidence, cards, and responsive bottom sheet styles.
- Modify `apps/web/package.json`
  - Add `src/components/tutorAssistantModel.test.ts` to `test:models`.

## Task 1: Backend Tutor Schemas

**Files:**
- Create: `apps/api/app/schemas/tutor.py`
- Test: `apps/api/tests/test_tutor_chat.py`

- [ ] **Step 1: Write the failing schema/import test**

Add this first test to `apps/api/tests/test_tutor_chat.py`:

```python
from app.schemas.tutor import TutorChatRequest, TutorChatResponse


def test_tutor_schema_accepts_minimal_course_question():
    request = TutorChatRequest(course_id=1, message="变量名为什么不能以数字开头？")

    assert request.course_id == 1
    assert request.message == "变量名为什么不能以数字开头？"
    assert request.node_id == ""
    assert request.page_context == ""

    response = TutorChatResponse(
        answer="回答",
        agent_events=[],
        analysis_plan={"course_id": 1},
        retrieval_trace=[],
        graph_constraints={},
        evidence_chunks=[],
        verification_report={"decision": "fallback"},
        decision_report={"decision": "fallback", "next_action": "answer"},
        multimodal_cards=[],
        suggested_actions=[],
    )
    assert response.answer == "回答"
```

- [ ] **Step 2: Run the schema test and verify it fails**

Run:

```powershell
python -m pytest apps/api/tests/test_tutor_chat.py::test_tutor_schema_accepts_minimal_course_question -q
```

Expected: fail with `ModuleNotFoundError: No module named 'app.schemas.tutor'`.

- [ ] **Step 3: Add tutor schemas**

Create `apps/api/app/schemas/tutor.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TutorAttachment(BaseModel):
    id: str = ""
    filename: str = ""
    content_type: str = ""
    description: str = ""


class TutorChatRequest(BaseModel):
    course_id: int
    message: str = Field(min_length=1)
    node_id: str = ""
    page_context: str = ""
    attachments: list[TutorAttachment] = Field(default_factory=list)
    history: list[dict[str, str]] = Field(default_factory=list)


class TutorAgentEvent(BaseModel):
    event: str
    agent: str
    summary: str
    status: Literal["pending", "running", "completed", "failed"] = "completed"
    detail: dict[str, Any] = Field(default_factory=dict)


class TutorEvidenceChunk(BaseModel):
    chunk_id: int | str | None = None
    source_locator: str = ""
    heading: str = ""
    content: str = ""
    retrieval_query: str = ""
    distance: float | None = None
    storage: str = "mysql"


class TutorMultimodalCard(BaseModel):
    type: Literal["text_explanation", "diagram", "code_hint", "exercise", "video_script", "source_evidence"]
    title: str
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TutorSuggestedAction(BaseModel):
    type: Literal["continue_chat", "open_graph", "open_learning_path", "open_lesson", "open_assessment", "build_knowledge_base"]
    label: str
    target: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class TutorChatResponse(BaseModel):
    answer: str
    agent_events: list[TutorAgentEvent]
    analysis_plan: dict[str, Any]
    retrieval_trace: list[dict[str, Any]]
    graph_constraints: dict[str, Any]
    evidence_chunks: list[TutorEvidenceChunk]
    verification_report: dict[str, Any]
    decision_report: dict[str, Any]
    multimodal_cards: list[TutorMultimodalCard]
    suggested_actions: list[TutorSuggestedAction]
```

- [ ] **Step 4: Run the schema test and verify it passes**

Run:

```powershell
python -m pytest apps/api/tests/test_tutor_chat.py::test_tutor_schema_accepts_minimal_course_question -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/schemas/tutor.py apps/api/tests/test_tutor_chat.py
git commit -m "test: add tutor chat schemas"
```

## Task 2: Backend Tutor Service RAG Response

**Files:**
- Create: `apps/api/app/services/tutor_service.py`
- Modify: `apps/api/tests/test_tutor_chat.py`

- [ ] **Step 1: Write failing service tests**

Append these tests to `apps/api/tests/test_tutor_chat.py`:

```python
from app.schemas.tutor import TutorChatRequest
from app.services.tutor_service import TutorService


class FakeCourseService:
    def __init__(self, context):
        self.context = context

    def semantic_search(self, user_id, course_id, query):  # noqa: ARG002
        return self.context.get("semantic_search", [])

    def get_knowledge_graph(self, user_id, course_id):  # noqa: ARG002
        return self.context.get("graph", {"nodes": [], "edges": []})

    def list_chunks(self, user_id, course_id):  # noqa: ARG002
        return self.context.get("chunks", [])


class FakeRAGService:
    def __init__(self, course_service):  # noqa: ARG002
        pass

    def build_context(self, *, user_id, course_id, node_id, topic):
        return {
            "knowledge_context": [
                {
                    "chunk_id": 7,
                    "source_locator": "page 12",
                    "heading": "变量命名",
                    "content": "变量名由字母、数字、下划线组成，但不能以数字开头。",
                    "retrieval_query": topic,
                    "distance": 0.1,
                    "storage": "mysql",
                }
            ],
            "graph_constraints": {
                "current_node": {"id": node_id, "name": topic, "node_type": "knowledge_point"},
                "parent": {"id": "chapter-2", "name": "Python 基础"},
                "predecessors": [],
                "successors": [{"id": "node-next", "name": "输入输出"}],
                "related": [],
                "source_chunk_ids": [7],
                "node_found": True,
            },
            "retrieval_trace": [
                {
                    "query": topic,
                    "vector_chunk_id": 7,
                    "mysql_chunk_id": 7,
                    "source_locator": "page 12",
                    "strategy": "vector_to_mysql",
                }
            ],
        }


def test_tutor_service_builds_grounded_multi_agent_response():
    service = TutorService(FakeCourseService({}), rag_service_cls=FakeRAGService)

    response = service.chat(
        user_id=3,
        request=TutorChatRequest(
            course_id=9,
            node_id="node-variable",
            page_context="learning",
            message="变量名为什么不能以数字开头？",
        ),
    )

    assert "变量名" in response.answer
    assert response.evidence_chunks[0].content == "变量名由字母、数字、下划线组成，但不能以数字开头。"
    assert response.retrieval_trace[0]["strategy"] == "vector_to_mysql"
    assert response.graph_constraints["current_node"]["id"] == "node-variable"
    assert [event.agent for event in response.agent_events] == [
        "TutorAnalysisAgent",
        "TutorRetrievalAgent",
        "TutorGeneratorAgent",
        "TutorVerifierAgent",
        "TutorDecisionAgent",
    ]
    assert response.verification_report["decision"] == "accepted"
    assert response.decision_report["decision"] == "accepted"
    assert {card.type for card in response.multimodal_cards} >= {"text_explanation", "source_evidence"}


class EmptyRAGService:
    def __init__(self, course_service):  # noqa: ARG002
        pass

    def build_context(self, *, user_id, course_id, node_id, topic):  # noqa: ARG002
        return {"knowledge_context": [], "graph_constraints": {}, "retrieval_trace": []}


def test_tutor_service_marks_low_confidence_when_no_course_evidence():
    service = TutorService(FakeCourseService({}), rag_service_cls=EmptyRAGService)

    response = service.chat(
        user_id=3,
        request=TutorChatRequest(course_id=9, message="解释一个知识点"),
    )

    assert "未检索到课程知识库证据" in response.answer
    assert response.verification_report["decision"] == "fallback"
    assert response.decision_report["decision"] == "fallback"
    assert response.evidence_chunks == []
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```powershell
python -m pytest apps/api/tests/test_tutor_chat.py::test_tutor_service_builds_grounded_multi_agent_response apps/api/tests/test_tutor_chat.py::test_tutor_service_marks_low_confidence_when_no_course_evidence -q
```

Expected: fail with `ModuleNotFoundError: No module named 'app.services.tutor_service'`.

- [ ] **Step 3: Implement tutor service**

Create `apps/api/app/services/tutor_service.py`:

```python
from __future__ import annotations

from typing import Any

from app.schemas.tutor import (
    TutorAgentEvent,
    TutorChatRequest,
    TutorChatResponse,
    TutorEvidenceChunk,
    TutorMultimodalCard,
    TutorSuggestedAction,
)
from app.services.agentic_rag_service import AgenticRAGService
from app.services.course_service import CourseService


class TutorService:
    def __init__(
        self,
        course_service: CourseService,
        *,
        rag_service_cls: type[AgenticRAGService] = AgenticRAGService,
    ) -> None:
        self.course_service = course_service
        self.rag_service_cls = rag_service_cls

    def chat(self, *, user_id: int, request: TutorChatRequest) -> TutorChatResponse:
        topic = self._topic_from_request(request)
        analysis_plan = self._analysis_plan(user_id, request, topic)
        rag_context = self.rag_service_cls(self.course_service).build_context(
            user_id=user_id,
            course_id=request.course_id,
            node_id=request.node_id,
            topic=topic,
        )
        evidence_chunks = [TutorEvidenceChunk(**item) for item in rag_context.get("knowledge_context", [])]
        graph_constraints = rag_context.get("graph_constraints") or {}
        retrieval_trace = rag_context.get("retrieval_trace") or []
        answer = self._answer(request, topic, evidence_chunks, graph_constraints)
        verification_report = self._verification_report(evidence_chunks, graph_constraints)
        decision_report = self._decision_report(verification_report)
        multimodal_cards = self._multimodal_cards(topic, answer, evidence_chunks, graph_constraints, request)
        suggested_actions = self._suggested_actions(request)
        agent_events = self._agent_events(analysis_plan, evidence_chunks, verification_report, decision_report)

        return TutorChatResponse(
            answer=answer,
            agent_events=agent_events,
            analysis_plan=analysis_plan,
            retrieval_trace=retrieval_trace,
            graph_constraints=graph_constraints,
            evidence_chunks=evidence_chunks,
            verification_report=verification_report,
            decision_report=decision_report,
            multimodal_cards=multimodal_cards,
            suggested_actions=suggested_actions,
        )

    def _topic_from_request(self, request: TutorChatRequest) -> str:
        current_node = request.node_id.strip()
        message = request.message.strip()
        return current_node or message[:40] or "课程问题"

    def _analysis_plan(self, user_id: int, request: TutorChatRequest, topic: str) -> dict[str, Any]:
        return {
            "agent": "TutorAnalysisAgent",
            "user_id": user_id,
            "course_id": request.course_id,
            "node_id": request.node_id,
            "page_context": request.page_context,
            "topic": topic,
            "intent": "course_tutoring",
            "requires_rag": True,
            "attachment_count": len(request.attachments),
        }

    def _answer(
        self,
        request: TutorChatRequest,
        topic: str,
        evidence_chunks: list[TutorEvidenceChunk],
        graph_constraints: dict[str, Any],
    ) -> str:
        if not evidence_chunks:
            return "未检索到课程知识库证据。请先确认该课程知识库已构建，或补充更具体的问题后再试。"

        evidence = evidence_chunks[0]
        parent = graph_constraints.get("parent") or {}
        current = graph_constraints.get("current_node") or {}
        relation_text = ""
        if parent.get("name"):
            relation_text = f"它属于“{parent.get('name')}”下的知识点。"
        current_name = current.get("name") or topic
        return (
            f"围绕“{current_name}”，本地知识库给出的依据是：{evidence.content} "
            f"{relation_text}结合你的问题“{request.message.strip()}”，可以先把规则、反例和练习放在一起理解。"
        ).strip()

    def _verification_report(
        self,
        evidence_chunks: list[TutorEvidenceChunk],
        graph_constraints: dict[str, Any],
    ) -> dict[str, Any]:
        evidence_count = len(evidence_chunks)
        graph_count = sum(1 for key in ("current_node", "parent", "predecessors", "successors", "related") if graph_constraints.get(key))
        decision = "accepted" if evidence_count else "fallback"
        return {
            "agent": "TutorVerifierAgent",
            "decision": decision,
            "evidence_count": evidence_count,
            "graph_constraint_count": graph_count,
            "citation_chunk_ids": [chunk.chunk_id for chunk in evidence_chunks if chunk.chunk_id is not None],
            "hallucination_risk": "low" if evidence_count else "medium",
            "unsupported_claims": [] if evidence_count else ["缺少课程知识库证据"],
        }

    def _decision_report(self, verification_report: dict[str, Any]) -> dict[str, Any]:
        accepted = verification_report.get("decision") == "accepted"
        return {
            "agent": "TutorDecisionAgent",
            "decision": "accepted" if accepted else "fallback",
            "next_action": "answer" if accepted else "ask_for_more_context",
            "reason": "回答已绑定课程证据" if accepted else "缺少课程知识库证据，已降级提示",
            "fallback_available": True,
        }

    def _multimodal_cards(
        self,
        topic: str,
        answer: str,
        evidence_chunks: list[TutorEvidenceChunk],
        graph_constraints: dict[str, Any],
        request: TutorChatRequest,
    ) -> list[TutorMultimodalCard]:
        cards = [
            TutorMultimodalCard(type="text_explanation", title="结构化讲解", content=answer),
        ]
        if evidence_chunks:
            cards.append(
                TutorMultimodalCard(
                    type="source_evidence",
                    title="本地知识库证据",
                    content=evidence_chunks[0].content,
                    payload={
                        "chunk_id": evidence_chunks[0].chunk_id,
                        "source_locator": evidence_chunks[0].source_locator,
                    },
                )
            )
        if graph_constraints.get("current_node"):
            cards.append(
                TutorMultimodalCard(
                    type="diagram",
                    title="知识图谱关系",
                    content=f"{topic} 与父章节、前后继知识点的关系可作为理解路径。",
                    payload={"graph_constraints": graph_constraints},
                )
            )
        elif "代码" in request.message or "编程" in request.message:
            cards.append(
                TutorMultimodalCard(
                    type="code_hint",
                    title="代码练习提示",
                    content="先写最小可运行代码，再用输入输出样例验证。",
                )
            )
        return cards[:3]

    def _suggested_actions(self, request: TutorChatRequest) -> list[TutorSuggestedAction]:
        base = f"/courses/{request.course_id}"
        actions = [
            TutorSuggestedAction(type="open_graph", label="查看知识图谱", target=f"{base}/graph"),
            TutorSuggestedAction(type="open_learning_path", label="查看学习路径", target=f"{base}/learning-path"),
        ]
        if request.node_id:
            actions.append(
                TutorSuggestedAction(
                    type="open_lesson",
                    label="进入对应课堂",
                    target=f"{base}/knowledge/{request.node_id}",
                )
            )
        return actions

    def _agent_events(
        self,
        analysis_plan: dict[str, Any],
        evidence_chunks: list[TutorEvidenceChunk],
        verification_report: dict[str, Any],
        decision_report: dict[str, Any],
    ) -> list[TutorAgentEvent]:
        return [
            TutorAgentEvent(
                event="analysis_completed",
                agent="TutorAnalysisAgent",
                summary=f"识别为课程 {analysis_plan['course_id']} 的辅导问题",
                detail=analysis_plan,
            ),
            TutorAgentEvent(
                event="retrieval_completed",
                agent="TutorRetrievalAgent",
                summary=f"检索到 {len(evidence_chunks)} 个 MySQL 原文证据块",
                detail={"evidence_count": len(evidence_chunks)},
            ),
            TutorAgentEvent(
                event="generation_completed",
                agent="TutorGeneratorAgent",
                summary="已基于课程证据生成辅导回答和多模态卡片",
            ),
            TutorAgentEvent(
                event="verification_completed",
                agent="TutorVerifierAgent",
                summary=f"校验结论：{verification_report['decision']}",
                detail=verification_report,
            ),
            TutorAgentEvent(
                event="decision_completed",
                agent="TutorDecisionAgent",
                summary=f"最终决策：{decision_report['decision']}",
                detail=decision_report,
            ),
        ]
```

- [ ] **Step 4: Run service tests and verify they pass**

Run:

```powershell
python -m pytest apps/api/tests/test_tutor_chat.py::test_tutor_service_builds_grounded_multi_agent_response apps/api/tests/test_tutor_chat.py::test_tutor_service_marks_low_confidence_when_no_course_evidence -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/services/tutor_service.py apps/api/tests/test_tutor_chat.py
git commit -m "feat: add tutor rag service"
```

## Task 3: Backend Tutor API Route

**Files:**
- Create: `apps/api/app/routers/tutor.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_tutor_chat.py`

- [ ] **Step 1: Write failing API tests**

Append these tests to `apps/api/tests/test_tutor_chat.py`:

```python
from fastapi.testclient import TestClient

from app.db import Base, create_engine_for_url, create_session_factory
from app.main import create_app
from app.models.course import Course, CourseMaterial, GraphBuildJob, KnowledgeChunk
from app.services.course_service import CourseService


def make_tutor_client(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'tutor-test.db'}"
    engine = create_engine_for_url(database_url)
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    app = create_app(session_factory=session_factory)
    app.state.testing_session_factory = session_factory
    return TestClient(app)


def auth_token(client: TestClient, username: str = "tutor-user") -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "secret123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def seed_course_with_chunk(client: TestClient, user_id: int, course_id: int, content: str) -> None:
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=course_id, user_id=user_id, name=f"course-{course_id}", status="ready"))
        db.add(
            CourseMaterial(
                id=course_id,
                course_id=course_id,
                user_id=user_id,
                filename="course.pdf",
                file_type="pdf",
                storage_path="test.pdf",
                size_bytes=10,
                parse_status="parsed",
            )
        )
        db.add(
            KnowledgeChunk(
                id=course_id * 10,
                course_id=course_id,
                material_id=course_id,
                chunk_index=1,
                source_locator="page 1",
                heading="变量命名",
                content=content,
                token_count=20,
                embedding_id=f"chunk-{course_id * 10}",
            )
        )
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        db.commit()


def test_tutor_chat_endpoint_requires_login(tmp_path):
    client = make_tutor_client(tmp_path)

    response = client.post("/api/tutor/chat", json={"course_id": 1, "message": "解释变量"})

    assert response.status_code == 401


def test_tutor_chat_endpoint_returns_course_scoped_rag_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(
        CourseService,
        "semantic_search",
        lambda self, user_id, course_id, query: [  # noqa: ARG005
            {"chunk_id": course_id * 10, "source_locator": "page 1", "distance": 0.1}
        ],
    )
    monkeypatch.setattr(
        CourseService,
        "get_knowledge_graph",
        lambda self, user_id, course_id: {  # noqa: ARG005
            "nodes": [
                {"id": "node-variable", "name": "变量命名", "node_type": "knowledge_point", "parent_id": "chapter-1"},
                {"id": "chapter-1", "name": "Python 基础", "node_type": "chapter", "parent_id": ""},
            ],
            "edges": [],
        },
    )
    client = make_tutor_client(tmp_path)
    token = auth_token(client)
    seed_course_with_chunk(client, user_id=1, course_id=1, content="Python 变量名不能以数字开头。")
    seed_course_with_chunk(client, user_id=1, course_id=2, content="C 语言变量名不能以数字开头。")

    response = client.post(
        "/api/tutor/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"course_id": 1, "node_id": "node-variable", "message": "为什么变量不能以数字开头？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Python 变量名不能以数字开头" in payload["answer"]
    assert payload["evidence_chunks"][0]["content"] == "Python 变量名不能以数字开头。"
    assert "C 语言变量名" not in payload["answer"]
    assert payload["graph_constraints"]["current_node"]["id"] == "node-variable"
    assert [event["agent"] for event in payload["agent_events"]] == [
        "TutorAnalysisAgent",
        "TutorRetrievalAgent",
        "TutorGeneratorAgent",
        "TutorVerifierAgent",
        "TutorDecisionAgent",
    ]
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```powershell
python -m pytest apps/api/tests/test_tutor_chat.py::test_tutor_chat_endpoint_requires_login apps/api/tests/test_tutor_chat.py::test_tutor_chat_endpoint_returns_course_scoped_rag_answer -q
```

Expected: fail with 404 for `/api/tutor/chat`.

- [ ] **Step 3: Add tutor router**

Create `apps/api/app/routers/tutor.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.llm.client import LLMClient
from app.models.user import UserRead
from app.routers.auth import current_user
from app.schemas.tutor import TutorChatRequest, TutorChatResponse
from app.services.course_service import CourseService
from app.services.tutor_service import TutorService


router = APIRouter(prefix="/api/tutor", tags=["tutor"])


@router.post("/chat", response_model=TutorChatResponse)
async def tutor_chat(
    request: TutorChatRequest,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> TutorChatResponse:
    # LLMClient is constructed here to keep the router consistent with existing resource endpoints.
    # The first implementation uses deterministic generation in TutorService and keeps LLM wiring ready for enhancement.
    LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        mock=settings.mock_llm,
    )
    return TutorService(CourseService(db)).chat(user_id=user.id, request=request)
```

- [ ] **Step 4: Include tutor router in app**

Modify `apps/api/app/main.py` imports and router registration:

```python
from app.routers import assessments, auth, chat, courses, paths, profiles, resources, tts, tutor
```

Add after `app.include_router(tts.router)`:

```python
    app.include_router(tutor.router)
```

- [ ] **Step 5: Run API tests and verify they pass**

Run:

```powershell
python -m pytest apps/api/tests/test_tutor_chat.py::test_tutor_chat_endpoint_requires_login apps/api/tests/test_tutor_chat.py::test_tutor_chat_endpoint_returns_course_scoped_rag_answer -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add apps/api/app/routers/tutor.py apps/api/app/main.py apps/api/tests/test_tutor_chat.py
git commit -m "feat: expose tutor chat endpoint"
```

## Task 4: Tutor Learning Event Recording

**Files:**
- Modify: `apps/api/app/services/tutor_service.py`
- Modify: `apps/api/app/routers/tutor.py`
- Modify: `apps/api/tests/test_tutor_chat.py`

- [ ] **Step 1: Write failing event test**

Append this test to `apps/api/tests/test_tutor_chat.py`:

```python
from app.models.assessment import LearningProfileEvent


def test_tutor_chat_records_course_learning_event(tmp_path, monkeypatch):
    monkeypatch.setattr(CourseService, "semantic_search", lambda self, user_id, course_id, query: [])  # noqa: ARG005
    monkeypatch.setattr(CourseService, "get_knowledge_graph", lambda self, user_id, course_id: {"nodes": [], "edges": []})  # noqa: ARG005
    client = make_tutor_client(tmp_path)
    token = auth_token(client, "tutor-event")
    seed_course_with_chunk(client, user_id=1, course_id=1, content="Python 变量。")

    response = client.post(
        "/api/tutor/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"course_id": 1, "node_id": "node-variable", "message": "变量是什么？"},
    )

    assert response.status_code == 200
    with client.app.state.testing_session_factory() as db:
        events = list(db.query(LearningProfileEvent).filter_by(user_id=1, course_id=1))
    assert len(events) == 1
    assert events[0].event_type in {"tutor_question", "tutor_question_asked"}
    assert events[0].knowledge_node_id == "node-variable"
    assert "变量是什么" in events[0].detail
```

- [ ] **Step 2: Run event test and verify it fails**

Run:

```powershell
python -m pytest apps/api/tests/test_tutor_chat.py::test_tutor_chat_records_course_learning_event -q
```

Expected: fail because no `LearningProfileEvent` is recorded.

- [ ] **Step 3: Implement event recording**

Inspect the existing `LearningProfileEvent` constructor in `apps/api/app/models/assessment.py`. Add an optional `db` parameter to `TutorService.__init__`:

```python
from sqlalchemy.orm import Session
from app.models.assessment import LearningProfileEvent
```

```python
    def __init__(
        self,
        course_service: CourseService,
        *,
        rag_service_cls: type[AgenticRAGService] = AgenticRAGService,
        db: Session | None = None,
    ) -> None:
        self.course_service = course_service
        self.rag_service_cls = rag_service_cls
        self.db = db
```

At the end of `chat`, before `return TutorChatResponse(...)`, call:

```python
        self._record_tutor_event(user_id, request, verification_report)
```

Add method:

```python
    def _record_tutor_event(
        self,
        user_id: int,
        request: TutorChatRequest,
        verification_report: dict[str, Any],
    ) -> None:
        if self.db is None:
            return
        event = LearningProfileEvent(
            user_id=user_id,
            course_id=request.course_id,
            knowledge_node_id=request.node_id,
            event_type="tutor_question",
            topic=request.node_id or request.message[:40],
            detail=request.message,
            event_payload={
                "page_context": request.page_context,
                "evidence_count": verification_report.get("evidence_count", 0),
                "decision": verification_report.get("decision"),
            },
            evidence_strength="medium" if verification_report.get("evidence_count", 0) else "low",
            score=None,
        )
        self.db.add(event)
        self.db.commit()
```

Modify `apps/api/app/routers/tutor.py`:

```python
    return TutorService(CourseService(db), db=db).chat(user_id=user.id, request=request)
```

- [ ] **Step 4: Run event test and verify it passes**

Run:

```powershell
python -m pytest apps/api/tests/test_tutor_chat.py::test_tutor_chat_records_course_learning_event -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/services/tutor_service.py apps/api/app/routers/tutor.py apps/api/tests/test_tutor_chat.py
git commit -m "feat: record tutor learning events"
```

## Task 5: Frontend Tutor API Client

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Create: `apps/web/src/components/tutorAssistantModel.test.ts`

- [ ] **Step 1: Write failing API client type test**

Create `apps/web/src/components/tutorAssistantModel.test.ts`:

```typescript
import type { TutorChatResponse } from "../api/client.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

test("tutor response type exposes closed-loop workbench fields", () => {
  const response: TutorChatResponse = {
    answer: "回答",
    agent_events: [{ event: "analysis_completed", agent: "TutorAnalysisAgent", summary: "done", status: "completed", detail: {} }],
    analysis_plan: { course_id: 1 },
    retrieval_trace: [],
    graph_constraints: {},
    evidence_chunks: [],
    verification_report: { decision: "fallback" },
    decision_report: { decision: "fallback", next_action: "ask_for_more_context" },
    multimodal_cards: [{ type: "text_explanation", title: "讲解", content: "回答", payload: {} }],
    suggested_actions: [],
  };

  assert(response.agent_events[0].agent === "TutorAnalysisAgent", "agent event should be typed");
  assert(response.multimodal_cards[0].type === "text_explanation", "multimodal card should be typed");
});
```

- [ ] **Step 2: Run frontend model test and verify it fails**

Run:

```powershell
cd D:\softbei\a3\apps\web
npx tsx src/components/tutorAssistantModel.test.ts
```

Expected: TypeScript compile failure because `TutorChatResponse` is not exported.

- [ ] **Step 3: Add API types and send function**

Modify `apps/web/src/api/client.ts` after existing `AgentEvent` interfaces:

```typescript
export interface TutorAttachment {
  id?: string;
  filename?: string;
  content_type?: string;
  description?: string;
}

export interface TutorChatPayload {
  course_id: number;
  message: string;
  node_id?: string;
  page_context?: string;
  attachments?: TutorAttachment[];
  history?: Array<{ role: string; content: string }>;
}

export interface TutorAgentEvent {
  event: string;
  agent: string;
  summary: string;
  status: "pending" | "running" | "completed" | "failed";
  detail: Record<string, unknown>;
}

export interface TutorEvidenceChunk {
  chunk_id?: number | string | null;
  source_locator: string;
  heading: string;
  content: string;
  retrieval_query: string;
  distance?: number | null;
  storage: string;
}

export interface TutorMultimodalCard {
  type: "text_explanation" | "diagram" | "code_hint" | "exercise" | "video_script" | "source_evidence";
  title: string;
  content: string;
  payload: Record<string, unknown>;
}

export interface TutorSuggestedAction {
  type: "continue_chat" | "open_graph" | "open_learning_path" | "open_lesson" | "open_assessment" | "build_knowledge_base";
  label: string;
  target: string;
  payload: Record<string, unknown>;
}

export interface TutorChatResponse {
  answer: string;
  agent_events: TutorAgentEvent[];
  analysis_plan: Record<string, unknown>;
  retrieval_trace: RetrievalTraceItem[];
  graph_constraints: GraphConstraints;
  evidence_chunks: TutorEvidenceChunk[];
  verification_report: Record<string, unknown>;
  decision_report: Record<string, unknown>;
  multimodal_cards: TutorMultimodalCard[];
  suggested_actions: TutorSuggestedAction[];
}
```

Add near other API functions:

```typescript
export async function sendTutorMessage(
  token: string | undefined,
  payload: TutorChatPayload
): Promise<TutorChatResponse> {
  const response = await fetch("/api/tutor/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "智能辅导请求失败");
  }
  return response.json();
}
```

- [ ] **Step 4: Run frontend model test and verify it passes**

Run:

```powershell
cd D:\softbei\a3\apps\web
npx tsx src/components/tutorAssistantModel.test.ts
```

Expected: pass.

- [ ] **Step 5: Add test to package script**

Modify `apps/web/package.json` `test:models` script by adding:

```text
&& tsx src/components/tutorAssistantModel.test.ts
```

Place it with the other `src/components/...` tests.

- [ ] **Step 6: Run frontend tests**

Run:

```powershell
cd D:\softbei\a3\apps\web
npm run test:models
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add apps/web/src/api/client.ts apps/web/src/components/tutorAssistantModel.test.ts apps/web/package.json
git commit -m "feat: add tutor api client types"
```

## Task 6: Frontend Tutor Context Model

**Files:**
- Create: `apps/web/src/components/tutorAssistantModel.ts`
- Modify: `apps/web/src/components/tutorAssistantModel.test.ts`

- [ ] **Step 1: Write failing context model tests**

Append to `apps/web/src/components/tutorAssistantModel.test.ts`:

```typescript
import {
  agentStageState,
  extractTutorContextFromPath,
  tutorSendDisabledReason,
  type TutorWorkbenchMessage
} from "./tutorAssistantModel.js";

test("extracts course, page context, and node id from course routes", () => {
  const learning = extractTutorContextFromPath("/courses/39/knowledge/node-variable", 12);
  assert(learning.courseId === 39, "route course id should win over fallback");
  assert(learning.nodeId === "node-variable", "knowledge route should expose node id");
  assert(learning.pageContext === "learning", "knowledge route should map to learning context");

  const courses = extractTutorContextFromPath("/courses", 12);
  assert(courses.courseId === 12, "courses page should use fallback current course");
  assert(courses.pageContext === "courses", "courses page context should be courses");
});

test("returns clear disabled reasons for missing course and empty input", () => {
  assert(tutorSendDisabledReason(undefined, "解释变量") === "请先选择课程", "missing course should block send");
  assert(tutorSendDisabledReason(1, "   ") === "请输入问题", "empty question should block send");
  assert(tutorSendDisabledReason(1, "解释变量") === "", "valid question should be enabled");
});

test("agent stages are derived from response events", () => {
  const stages = agentStageState([
    { event: "analysis_completed", agent: "TutorAnalysisAgent", summary: "done", status: "completed", detail: {} },
    { event: "retrieval_completed", agent: "TutorRetrievalAgent", summary: "done", status: "completed", detail: {} },
  ]);

  assert(stages[0].status === "completed", "analysis should be completed");
  assert(stages[1].status === "completed", "retrieval should be completed");
  assert(stages[2].status === "pending", "generation should still be pending");
});

test("workbench message model supports user and assistant messages", () => {
  const message: TutorWorkbenchMessage = { id: "m1", role: "assistant", content: "回答" };
  assert(message.role === "assistant", "assistant role should be valid");
});
```

- [ ] **Step 2: Run model tests and verify they fail**

Run:

```powershell
cd D:\softbei\a3\apps\web
npx tsx src/components/tutorAssistantModel.test.ts
```

Expected: fail because `tutorAssistantModel.ts` does not exist.

- [ ] **Step 3: Implement context model**

Create `apps/web/src/components/tutorAssistantModel.ts`:

```typescript
import type { TutorAgentEvent } from "../api/client";

export type TutorPageContext = "courses" | "profile" | "knowledge_base" | "graph" | "learning_path" | "learning" | "assessment" | "unknown";

export interface TutorRouteContext {
  courseId?: number;
  nodeId: string;
  pageContext: TutorPageContext;
}

export interface TutorWorkbenchMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
}

export interface TutorStageView {
  agent: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  summary: string;
}

const STAGES: Array<{ agent: string; label: string }> = [
  { agent: "TutorAnalysisAgent", label: "分析" },
  { agent: "TutorRetrievalAgent", label: "检索" },
  { agent: "TutorGeneratorAgent", label: "生成" },
  { agent: "TutorVerifierAgent", label: "校验" },
  { agent: "TutorDecisionAgent", label: "决策" },
];

export function extractTutorContextFromPath(pathname: string, fallbackCourseId?: number): TutorRouteContext {
  const courseMatch = pathname.match(/\/courses\/(\d+)/);
  const courseId = courseMatch ? Number(courseMatch[1]) : fallbackCourseId;
  const knowledgeMatch = pathname.match(/\/courses\/\d+\/knowledge\/([^/?#]+)/);
  return {
    courseId,
    nodeId: knowledgeMatch ? decodeURIComponent(knowledgeMatch[1]) : "",
    pageContext: pageContextFromPath(pathname),
  };
}

export function pageContextFromPath(pathname: string): TutorPageContext {
  if (pathname === "/courses") {
    return "courses";
  }
  if (pathname.includes("/profile/interview")) {
    return "profile";
  }
  if (pathname.includes("/knowledge-base")) {
    return "knowledge_base";
  }
  if (pathname.includes("/graph")) {
    return "graph";
  }
  if (pathname.includes("/learning-path")) {
    return "learning_path";
  }
  if (pathname.includes("/knowledge/")) {
    return "learning";
  }
  if (pathname.includes("/assessment")) {
    return "assessment";
  }
  return "unknown";
}

export function tutorSendDisabledReason(courseId: number | undefined, message: string): string {
  if (!courseId) {
    return "请先选择课程";
  }
  if (!message.trim()) {
    return "请输入问题";
  }
  return "";
}

export function agentStageState(events: TutorAgentEvent[]): TutorStageView[] {
  return STAGES.map((stage) => {
    const event = events.find((item) => item.agent === stage.agent);
    return {
      agent: stage.agent,
      label: stage.label,
      status: event?.status ?? "pending",
      summary: event?.summary ?? "等待执行",
    };
  });
}
```

- [ ] **Step 4: Run model tests and verify they pass**

Run:

```powershell
cd D:\softbei\a3\apps\web
npx tsx src/components/tutorAssistantModel.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/components/tutorAssistantModel.ts apps/web/src/components/tutorAssistantModel.test.ts
git commit -m "feat: add tutor assistant route model"
```

## Task 7: Frontend Global Tutor Workbench UI

**Files:**
- Create: `apps/web/src/components/TutorAssistantFloating.tsx`
- Create: `apps/web/src/components/TutorAssistantPanel.tsx`
- Modify: `apps/web/src/layouts/AppLayout.tsx`
- Modify: `apps/web/src/styles/app.css`

- [ ] **Step 1: Add component files**

Create `apps/web/src/components/TutorAssistantPanel.tsx`:

```tsx
import { Image, Mic, Send, Sparkles, X } from "lucide-react";
import type { TutorChatResponse } from "../api/client";
import { agentStageState, tutorSendDisabledReason, type TutorRouteContext, type TutorWorkbenchMessage } from "./tutorAssistantModel";

interface TutorAssistantPanelProps {
  context: TutorRouteContext;
  courseName: string;
  input: string;
  messages: TutorWorkbenchMessage[];
  response?: TutorChatResponse;
  loading: boolean;
  error: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onClose: () => void;
}

export function TutorAssistantPanel({
  context,
  courseName,
  input,
  messages,
  response,
  loading,
  error,
  onInputChange,
  onSend,
  onClose
}: TutorAssistantPanelProps) {
  const disabledReason = tutorSendDisabledReason(context.courseId, input);
  const stages = agentStageState(response?.agent_events ?? []);

  return (
    <section className="tutor-panel" aria-label="多智能体智能辅导工作台">
      <header className="tutor-panel-header">
        <div className="tutor-brand">
          <span className="tutor-avatar">
            <Sparkles size={18} />
          </span>
          <div>
            <h2>多智能体辅导</h2>
            <p>{context.courseId ? `${courseName || `课程 ${context.courseId}`} · ${context.pageContext}` : "请先选择课程"}</p>
          </div>
        </div>
        <button className="tutor-icon-button" aria-label="关闭智能辅导" onClick={onClose}>
          <X size={17} />
        </button>
      </header>

      <div className="tutor-stage-row" aria-label="智能体协同阶段">
        {stages.map((stage) => (
          <div className={`tutor-stage ${stage.status}`} key={stage.agent}>
            <span>{stage.label}</span>
            <small>{stage.summary}</small>
          </div>
        ))}
      </div>

      <div className="tutor-message-list" aria-live="polite">
        {messages.length === 0 ? (
          <div className="tutor-empty">
            <strong>随时提问当前课程问题</strong>
            <span>我会结合本地知识库、知识图谱和当前页面上下文回答。</span>
          </div>
        ) : (
          messages.map((message) => (
            <article className={`tutor-message ${message.role}`} key={message.id}>
              <p>{message.content}</p>
            </article>
          ))
        )}

        {response ? (
          <section className="tutor-evidence-block">
            <div className="tutor-section-title">RAG 证据</div>
            {response.evidence_chunks.length ? response.evidence_chunks.slice(0, 2).map((chunk) => (
              <article className="tutor-evidence-card" key={`${chunk.chunk_id}-${chunk.source_locator}`}>
                <strong>{chunk.heading || chunk.source_locator || "本地知识库"}</strong>
                <p>{chunk.content}</p>
                <span>{chunk.source_locator}</span>
              </article>
            )) : (
              <article className="tutor-evidence-card muted">未检索到课程知识库证据。</article>
            )}
          </section>
        ) : null}

        {response?.multimodal_cards.length ? (
          <section className="tutor-card-grid">
            {response.multimodal_cards.map((card) => (
              <article className={`tutor-modal-card ${card.type}`} key={`${card.type}-${card.title}`}>
                <span>{card.type}</span>
                <strong>{card.title}</strong>
                <p>{card.content}</p>
              </article>
            ))}
          </section>
        ) : null}

        {error ? <div className="tutor-error">{error}</div> : null}
      </div>

      <footer className="tutor-input-area">
        <div className="tutor-input-tools">
          <button type="button" aria-label="上传图片" title="上传图片">
            <Image size={16} />
          </button>
          <button type="button" aria-label="语音输入" title="语音输入">
            <Mic size={16} />
          </button>
        </div>
        <textarea
          aria-label="向智能辅导提问"
          placeholder={context.courseId ? "输入你想追问的课程问题..." : "请先选择课程"}
          rows={2}
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
        />
        <button className="tutor-send" disabled={Boolean(disabledReason) || loading} title={disabledReason || "发送"} onClick={onSend}>
          <Send size={16} />
          {loading ? "生成中" : "发送"}
        </button>
      </footer>
    </section>
  );
}
```

Create `apps/web/src/components/TutorAssistantFloating.tsx`:

```tsx
import { Bot, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { sendTutorMessage, type Course, type TutorChatResponse } from "../api/client";
import { useAuth } from "../state/auth";
import { readCurrentCourseId } from "../state/currentCourse";
import { extractTutorContextFromPath, type TutorWorkbenchMessage } from "./tutorAssistantModel";
import { TutorAssistantPanel } from "./TutorAssistantPanel";

interface TutorAssistantFloatingProps {
  courses: Course[];
  activeCourseId?: number;
}

export function TutorAssistantFloating({ courses, activeCourseId }: TutorAssistantFloatingProps) {
  const { token, user } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<TutorWorkbenchMessage[]>([]);
  const [response, setResponse] = useState<TutorChatResponse | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const context = useMemo(
    () => extractTutorContextFromPath(location.pathname, activeCourseId ?? readCurrentCourseId()),
    [activeCourseId, location.pathname]
  );
  const courseName = courses.find((course) => course.id === context.courseId)?.name ?? "";

  if (!user) {
    return null;
  }

  async function handleSend() {
    if (!context.courseId || !input.trim()) {
      return;
    }
    const userMessage: TutorWorkbenchMessage = { id: `user-${Date.now()}`, role: "user", content: input.trim() };
    setMessages((items) => [...items, userMessage]);
    setLoading(true);
    setError("");
    try {
      const result = await sendTutorMessage(token, {
        course_id: context.courseId,
        message: input.trim(),
        node_id: context.nodeId,
        page_context: context.pageContext
      });
      setResponse(result);
      setMessages((items) => [...items, { id: `assistant-${Date.now()}`, role: "assistant", content: result.answer }]);
      setInput("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "智能辅导请求失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="tutor-floating-root">
      {open ? (
        <TutorAssistantPanel
          context={context}
          courseName={courseName}
          input={input}
          messages={messages}
          response={response}
          loading={loading}
          error={error}
          onInputChange={setInput}
          onSend={handleSend}
          onClose={() => setOpen(false)}
        />
      ) : null}
      <button className={`tutor-floating-button ${open ? "open" : ""}`} aria-label="打开智能辅导" onClick={() => setOpen((value) => !value)}>
        {open ? <Sparkles size={22} /> : <Bot size={23} />}
        <span>{context.courseId ? "智能辅导" : "选择课程"}</span>
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Mount in AppLayout**

Modify `apps/web/src/layouts/AppLayout.tsx`:

```tsx
import { TutorAssistantFloating } from "../components/TutorAssistantFloating";
```

Add before closing `</main>`:

```tsx
      <TutorAssistantFloating courses={courses} activeCourseId={activeCourseId} />
```

- [ ] **Step 3: Add CSS**

Append to `apps/web/src/styles/app.css`:

```css
.tutor-floating-root {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 90;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}

.tutor-floating-button,
.tutor-icon-button,
.tutor-input-tools button,
.tutor-send {
  cursor: pointer;
}

.tutor-floating-button {
  min-width: 132px;
  min-height: 52px;
  border: 0;
  border-radius: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  color: #fff;
  background: linear-gradient(135deg, #1769e8, #0f9f72);
  box-shadow: 0 18px 36px rgba(23, 105, 232, 0.28);
  font-weight: 800;
  transition: transform 180ms ease, box-shadow 180ms ease;
}

.tutor-floating-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 22px 42px rgba(23, 105, 232, 0.34);
}

.tutor-panel {
  width: min(480px, calc(100vw - 40px));
  max-height: min(760px, calc(100vh - 112px));
  border: 1px solid rgba(148, 163, 184, 0.34);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.22);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(14px);
}

.tutor-panel-header {
  padding: 16px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  background: linear-gradient(135deg, #f6faff, #effdf7);
}

.tutor-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.tutor-avatar {
  width: 40px;
  height: 40px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(135deg, #1769e8, #0f9f72);
  flex: 0 0 auto;
}

.tutor-brand h2 {
  margin: 0;
  font-size: 16px;
  color: #102033;
}

.tutor-brand p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
}

.tutor-icon-button {
  width: 36px;
  height: 36px;
  border: 1px solid #d9e4f0;
  border-radius: 12px;
  background: #fff;
  color: #34516f;
}

.tutor-stage-row {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid #e6edf5;
  background: #fff;
}

.tutor-stage {
  min-height: 54px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 7px;
  background: #f8fafc;
}

.tutor-stage span {
  display: block;
  font-size: 12px;
  font-weight: 800;
  color: #21344d;
}

.tutor-stage small {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 10px;
  line-height: 1.25;
}

.tutor-stage.completed {
  border-color: #b8ead6;
  background: #effdf7;
}

.tutor-message-list {
  flex: 1;
  overflow: auto;
  padding: 14px;
  background: #fbfdff;
}

.tutor-empty {
  border: 1px dashed #cbd8e6;
  border-radius: 16px;
  padding: 18px;
  background: #fff;
  display: grid;
  gap: 6px;
  color: #64748b;
}

.tutor-empty strong {
  color: #102033;
}

.tutor-message {
  max-width: 88%;
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 14px;
  line-height: 1.55;
  font-size: 13px;
}

.tutor-message p {
  margin: 0;
}

.tutor-message.user {
  margin-left: auto;
  color: #fff;
  background: #102033;
  border-top-right-radius: 5px;
}

.tutor-message.assistant {
  color: #15365f;
  background: #eef6ff;
  border-top-left-radius: 5px;
}

.tutor-section-title {
  margin: 14px 0 8px;
  font-size: 12px;
  font-weight: 900;
  color: #34516f;
}

.tutor-evidence-card,
.tutor-modal-card {
  border: 1px solid #dce7f2;
  border-radius: 14px;
  background: #fff;
  padding: 10px;
}

.tutor-evidence-card {
  margin-bottom: 8px;
}

.tutor-evidence-card strong,
.tutor-modal-card strong {
  display: block;
  color: #102033;
  font-size: 13px;
}

.tutor-evidence-card p,
.tutor-modal-card p {
  margin: 6px 0;
  color: #4c6078;
  font-size: 12px;
  line-height: 1.5;
}

.tutor-evidence-card span,
.tutor-modal-card span {
  color: #1769e8;
  font-size: 11px;
  font-weight: 800;
}

.tutor-evidence-card.muted {
  color: #64748b;
  background: #f8fafc;
}

.tutor-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.tutor-error {
  margin-top: 10px;
  border: 1px solid #fecaca;
  border-radius: 12px;
  padding: 10px;
  color: #991b1b;
  background: #fef2f2;
  font-size: 12px;
}

.tutor-input-area {
  border-top: 1px solid #e2e8f0;
  padding: 12px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 9px;
  align-items: end;
  background: #fff;
}

.tutor-input-tools {
  display: flex;
  gap: 6px;
}

.tutor-input-tools button {
  width: 36px;
  height: 36px;
  border: 1px solid #dbe5f0;
  border-radius: 12px;
  background: #fff;
  color: #37506b;
}

.tutor-input-area textarea {
  resize: none;
  min-height: 42px;
  max-height: 96px;
  border: 1px solid #dbe5f0;
  border-radius: 13px;
  padding: 10px 11px;
  color: #102033;
  background: #f8fafc;
}

.tutor-send {
  min-width: 72px;
  min-height: 42px;
  border: 0;
  border-radius: 13px;
  color: #fff;
  background: #1769e8;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-weight: 800;
}

.tutor-send:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

@media (max-width: 720px) {
  .tutor-floating-root {
    right: 14px;
    bottom: 14px;
    left: 14px;
  }

  .tutor-panel {
    width: 100%;
    max-height: 82vh;
    border-radius: 20px;
  }

  .tutor-stage-row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .tutor-card-grid {
    grid-template-columns: 1fr;
  }

  .tutor-floating-button {
    align-self: flex-end;
  }
}
```

- [ ] **Step 4: Build frontend**

Run:

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/components/TutorAssistantFloating.tsx apps/web/src/components/TutorAssistantPanel.tsx apps/web/src/layouts/AppLayout.tsx apps/web/src/styles/app.css
git commit -m "feat: add global tutor workbench"
```

## Task 8: Browser Smoke Verification

**Files:**
- No code changes unless verification finds a defect.

- [ ] **Step 1: Run backend tests**

Run:

```powershell
python -m pytest apps/api/tests/test_tutor_chat.py -q
```

Expected: all tutor tests pass.

- [ ] **Step 2: Run full backend test suite**

Run:

```powershell
python -m pytest apps/api/tests -q
```

Expected: all tests pass or only known unrelated skipped tests.

- [ ] **Step 3: Run frontend tests and build**

Run:

```powershell
cd D:\softbei\a3\apps\web
npm run test:frontend
npm run build
```

Expected: both pass.

- [ ] **Step 4: Start services if not already running**

Backend:

```powershell
cd D:\softbei\a3\apps\api
python -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd D:\softbei\a3\apps\web
npm run dev
```

Expected: frontend available at `http://127.0.0.1:5173`.

- [ ] **Step 5: Browser smoke test**

Use the in-app browser:

1. Open `http://127.0.0.1:5173/auth`.
2. Log in with an existing local account or register a temporary account.
3. Navigate to `/courses`.
4. Confirm the bottom-right `智能辅导` entry appears.
5. Open the panel with no current course selected and confirm it asks for course selection.
6. Select a course and open `/courses/:courseId/knowledge-base`.
7. Ask `变量名为什么不能以数字开头？`.
8. Confirm the panel shows agent stages, answer text, evidence area, and multimodal cards.
9. Navigate to `/courses/:courseId/graph`, `/courses/:courseId/learning-path`, `/courses/:courseId/assessment`, and confirm the floating entry remains visible.

- [ ] **Step 6: Fix any smoke defects with TDD**

If a defect appears, write the smallest failing backend or frontend model test first, verify it fails, then fix and rerun the relevant commands.

- [ ] **Step 7: Finalize verification**

If verification found no defects, do not create another commit. If verification found a defect, create a new focused TDD task for that defect with concrete file paths, a failing test, the minimal fix, and its own commit.

## Self-Review

- Spec coverage:
  - Global floating entry: Task 7.
  - Multi-agent visible stages: Tasks 2, 5, 6, 7.
  - Course-scoped Agentic RAG: Tasks 2 and 3.
  - MySQL evidence and graph constraints: Tasks 2 and 3.
  - Text/image/voice input entry points: Task 7.
  - Multimodal response cards: Tasks 2, 5, 7.
  - Event recording for profile update loop: Task 4.
  - Verification commands and browser smoke: Task 8.
- Placeholder scan:
  - No implementation step uses vague placeholders. Every code-changing step includes concrete code or directs the worker to create a new concrete TDD task for discovered smoke defects.
- Type consistency:
  - Backend schema names match router and service use: `TutorChatRequest`, `TutorChatResponse`.
  - Frontend API names match component use: `sendTutorMessage`, `TutorChatResponse`.
  - Agent names match the design: `TutorAnalysisAgent`, `TutorRetrievalAgent`, `TutorGeneratorAgent`, `TutorVerifierAgent`, `TutorDecisionAgent`.
