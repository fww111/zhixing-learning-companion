from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, create_engine_for_url, create_session_factory
from app.main import create_app
from app.models.course import Course, CourseLessonSession, CourseMaterial, GraphBuildJob, KnowledgeChunk, KnowledgeNodeMastery
from app.models.profile import StudentProfile
from app.models.profile_record import StudentProfileRecord
from app.services.course_service import CourseService
from app.services.resource_service import ResourceService
from app.llm.client import LLMClient
from app.models.resource import OpenMAICClassroom


def make_client(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'smoke-test.db'}"
    engine = create_engine_for_url(database_url)
    TestingSessionLocal = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    app = create_app(session_factory=TestingSessionLocal)
    app.state.testing_session_factory = TestingSessionLocal
    return TestClient(app)


def insert_confirmed_profile(
    client: TestClient,
    user_id: int = 1,
    student_id: str = "user-1",
    course_id: int | None = None,
    learning_goal: str = "掌握 Python 程序设计",
) -> StudentProfile:
    profile = StudentProfile(
        student_id=student_id,
        major="计算机科学",
        grade="大二",
        learning_goal=learning_goal,
        knowledge_foundation="Python 基础一般",
        learning_style="先图解再练习",
        cognitive_style="先直观理解再代码验证",
        weak_points=["列表"],
        time_preference="每天1小时",
        resource_preference=["图解", "代码实操"],
        motivation="完成课程项目",
        constraints=["碎片时间学习"],
        assessment_preference="短练习",
        knowledge_graph_focus=["列表"],
    ).with_completion_score()
    with client.app.state.testing_session_factory() as db:
        db.add(
            StudentProfileRecord(
                user_id=user_id,
                course_id=course_id,
                student_id=profile.student_id,
                profile_data=profile.model_dump(mode="json"),
            )
        )
        db.commit()
    return profile


def insert_completed_lesson_state(
    client: TestClient,
    user_id: int = 1,
    course_id: int = 1,
    node_id: str = "outline-section-1-1",
    topic: str = "1.1 初识 Python",
) -> None:
    with client.app.state.testing_session_factory() as db:
        db.add(
            CourseLessonSession(
                user_id=user_id,
                course_id=course_id,
                node_id=node_id,
                topic=topic,
                resource_types=["document", "exercise", "code_lab"],
                package_data={},
                lesson_state={
                    "current_stage": "test",
                    "classroom_completed": True,
                    "notes_completed": True,
                    "mind_map_completed": True,
                    "code_lab_completed": True,
                    "test_completed": False,
                    "assessment_completed": False,
                },
            )
        )
        db.commit()


def test_health_endpoint():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_generate_workflow_endpoint_returns_profile_resources_and_path(tmp_path):
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "smokeuser", "email": "smoke@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "我是计算机大二学生，想4周入门机器学习，梯度下降薄弱，喜欢图解和代码。",
            "topic": "梯度下降",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["resources"]) >= 6
    assert len(payload["learning_path"]["stages"]) >= 3


def test_generate_workflow_endpoint_uses_requested_types_and_course_knowledge_context(tmp_path, monkeypatch):
    def fake_semantic_search(self, user_id, course_id, query):  # noqa: ARG001
        return [
            {
                "chunk_id": 7,
                "source_locator": "page 21",
                "content": "向量库旧文本：这段内容不应该直接进入最终上下文。",
                "distance": 0.12,
            }
        ]

    monkeypatch.setattr(CourseService, "semantic_search", fake_semantic_search)
    monkeypatch.setattr(
        CourseService,
        "get_knowledge_graph",
        lambda self, user_id, course_id: {  # noqa: ARG005
            "nodes": [
                {
                    "id": "chapter-1",
                    "name": "第1章 Python 概述",
                    "node_type": "chapter",
                    "level": 1,
                    "parent_id": "",
                    "summary": "课程导论",
                    "source_chunk_ids": [],
                },
                {
                    "id": "outline-section-1-1",
                    "name": "1.1 初识 Python",
                    "node_type": "knowledge_point",
                    "level": 2,
                    "parent_id": "chapter-1",
                    "summary": "认识 Python 的基本特点",
                    "source_chunk_ids": [7],
                },
                {
                    "id": "outline-section-1-2",
                    "name": "1.2 Python 开发环境",
                    "node_type": "knowledge_point",
                    "level": 2,
                    "parent_id": "chapter-1",
                    "summary": "安装和使用开发环境",
                    "source_chunk_ids": [],
                },
            ],
            "edges": [
                {
                    "id": "edge-1",
                    "source_node_id": "outline-section-1-1",
                    "target_node_id": "outline-section-1-2",
                    "relation_type": "prerequisite",
                    "reason": "先理解语言特点，再配置开发环境。",
                    "confidence": 0.9,
                }
            ],
        },
    )
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "resourceuser", "email": "resource@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        course = Course(id=1, user_id=1, name="Python 程序设计", status="ready")
        material = CourseMaterial(
            id=1,
            course_id=1,
            user_id=1,
            filename="python.pdf",
            file_type="pdf",
            storage_path=str(tmp_path / "python.pdf"),
            size_bytes=12,
            parse_status="parsed",
        )
        chunk = KnowledgeChunk(
            id=7,
            course_id=1,
            material_id=1,
            chunk_index=1,
            source_locator="page 21",
            heading="Python 列表",
            content="MySQL权威原文：Python 列表支持有序、可变、可索引的数据管理。",
            token_count=32,
            embedding_id="chunk-7",
        )
        db.add_all([course, material, chunk, GraphBuildJob(course_id=1, status="succeeded", current_stage="done", progress=100)])
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "我是计算机大二学生，列表薄弱，喜欢图解和练习。",
            "topic": "1.1 初识 Python",
            "course_id": 1,
            "node_id": "outline-section-1-1",
            "resource_types": ["mind_map", "document", "exercise"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [resource["type"] for resource in payload["resources"]] == ["mind_map", "document", "exercise"]
    assert payload["knowledge_context"][0]["source_locator"] == "page 21"
    assert payload["knowledge_context"][0]["content"] == "MySQL权威原文：Python 列表支持有序、可变、可索引的数据管理。"
    assert "向量库旧文本" not in payload["knowledge_context"][0]["content"]
    assert payload["graph_constraints"]["current_node"]["id"] == "outline-section-1-1"
    assert payload["graph_constraints"]["parent"]["name"] == "第1章 Python 概述"
    assert payload["graph_constraints"]["successors"][0]["id"] == "outline-section-1-2"
    assert payload["retrieval_trace"][0]["vector_chunk_id"] == 7
    assert payload["retrieval_trace"][0]["mysql_chunk_id"] == 7
    assert payload["verification_report"]["decision"] == "accepted"
    assert payload["analysis_plan"]["resource_blueprint"]["evidence_chunk_ids"] == [7]
    assert payload["debate_report"]["decision"] == "accepted"
    assert payload["decision_report"]["next_action"] == "return_resources"
    assert payload["verification_report"]["evidence_count"] == 1
    assert all("MySQL权威原文" not in resource["content"] for resource in payload["resources"])
    assert all("page 21" in resource["recommendation_reason"] for resource in payload["resources"])
    assert {
        event["resource_type"]
        for event in payload["agent_events"]
        if event["event"] == "agent_completed" and "resource_type" in event
    } == {
        "mind_map",
        "document",
        "exercise",
    }


def test_resource_generation_uses_profile_for_current_course_only(tmp_path, monkeypatch):
    seen_profiles: list[str] = []

    def fake_rag_context(self, user_id, course_id, node_id, topic):  # noqa: ARG001
        return {
            "knowledge_context": [],
            "graph_constraints": {
                "current_node": {"id": node_id, "name": topic},
                "parent": None,
                "predecessors": [],
                "successors": [],
                "related": [],
                "source_chunk_ids": [],
            },
            "retrieval_trace": [],
        }

    async def fake_run_collect(
        self,
        conversation,
        topic,
        requested_resource_types=None,
        knowledge_context=None,
        profile=None,
        graph_constraints=None,
        retrieval_trace=None,
    ):  # noqa: ARG001
        seen_profiles.append(profile.learning_goal)
        return {
            "event": "workflow_completed",
            "profile": profile.model_dump(mode="json"),
            "resources": [],
            "learning_path": {"student_id": profile.student_id, "stages": []},
            "knowledge_context": knowledge_context or [],
            "graph_constraints": graph_constraints or {},
            "retrieval_trace": retrieval_trace or [],
            "analysis_plan": {},
            "verification_report": {},
            "pedagogy_report": {},
            "debate_report": {},
            "decision_report": {"decision": "accepted"},
            "agent_events": [],
        }

    async def fake_openmaic(self, **kwargs):  # noqa: ARG001
        return OpenMAICClassroom(status="failed", step="skipped", error="skip openmaic in unit test")

    monkeypatch.setattr(ResourceService, "_agentic_rag_context", fake_rag_context)
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(ResourceService, "_generate_openmaic_classroom", fake_openmaic)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "course-profile-resource", "email": "course-profile-resource@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add_all([
            Course(id=1, user_id=1, name="Python 程序设计", status="ready"),
            Course(id=2, user_id=1, name="C语言程序设计", status="ready"),
        ])
        db.commit()
    insert_confirmed_profile(client, course_id=1, learning_goal="掌握 Python 程序设计")
    insert_confirmed_profile(client, course_id=2, learning_goal="掌握 C 语言程序设计")

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "学习当前课程",
            "topic": "1.1 初识 C 语言",
            "course_id": 2,
            "node_id": "c-section-1-1",
            "resource_types": ["document"],
        },
    )

    assert response.status_code == 200
    assert seen_profiles == ["掌握 C 语言程序设计"]
    assert response.json()["profile"]["learning_goal"] == "掌握 C 语言程序设计"


def test_generate_workflow_endpoint_submits_agentic_rag_outline_to_openmaic(tmp_path, monkeypatch):
    submitted = {}

    class FakeOpenMAICClient:
        async def generate_classroom(self, *, requirement, pdf_text, language="zh-CN", agent_mode="generate", enable_tts=None):
            submitted.update(
                {
                    "requirement": requirement,
                    "pdf_text": pdf_text,
                    "language": language,
                    "agent_mode": agent_mode,
                    "enable_tts": enable_tts,
                }
            )
            return {
                "job_id": "job-openmaic-1",
                "status": "queued",
                "step": "queued",
                "poll_url": "http://127.0.0.1:3000/api/generate-classroom/job-openmaic-1",
                "url": "",
            }

    async def fake_complete_text(self, system_prompt, user_prompt):  # noqa: ARG001
        assert "MySQL权威原文" in user_prompt
        assert "第1章 Python 概述" in user_prompt
        return "OpenMAIC课堂大纲：围绕1.1初识Python，先讲语言定位，再安排交互演示和练习。"

    monkeypatch.setattr(ResourceService, "openmaic_client_cls", FakeOpenMAICClient)
    monkeypatch.setattr(LLMClient, "complete_text", fake_complete_text)
    monkeypatch.setattr(
        CourseService,
        "semantic_search",
        lambda self, user_id, course_id, query: [  # noqa: ARG005
            {
                "chunk_id": 7,
                "source_locator": "page 21",
                "content": "向量库旧文本：不能直接传给 OpenMAIC。",
                "distance": 0.12,
            }
        ],
    )
    monkeypatch.setattr(
        CourseService,
        "get_knowledge_graph",
        lambda self, user_id, course_id: {  # noqa: ARG005
            "nodes": [
                {"id": "chapter-1", "name": "第1章 Python 概述", "node_type": "chapter", "parent_id": ""},
                {
                    "id": "outline-section-1-1",
                    "name": "1.1 初识 Python",
                    "node_type": "knowledge_point",
                    "parent_id": "chapter-1",
                    "summary": "认识 Python 的语言定位",
                    "source_chunk_ids": [7],
                },
            ],
            "edges": [],
        },
    )
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "openmaic-user", "email": "openmaic@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        course = Course(id=1, user_id=1, name="Python 程序设计", status="ready")
        material = CourseMaterial(
            id=1,
            course_id=1,
            user_id=1,
            filename="python.pdf",
            file_type="pdf",
            storage_path=str(tmp_path / "python.pdf"),
            size_bytes=12,
            parse_status="parsed",
        )
        chunk = KnowledgeChunk(
            id=7,
            course_id=1,
            material_id=1,
            chunk_index=1,
            source_locator="page 21",
            heading="初识 Python",
            content="MySQL权威原文：Python 是解释型、面向对象、跨平台的高级程序设计语言。",
            token_count=32,
            embedding_id="chunk-7",
        )
        db.add_all([course, material, chunk, GraphBuildJob(course_id=1, status="succeeded", current_stage="done", progress=100)])
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "根据确认画像学习 Python。",
            "topic": "1.1 初识 Python",
            "course_id": 1,
            "node_id": "outline-section-1-1",
            "resource_types": ["document"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["openmaic_classroom"]["job_id"] == "job-openmaic-1"
    assert payload["openmaic_classroom"]["requirement"] == submitted["requirement"]
    assert "OpenMAIC课堂大纲" in submitted["requirement"]
    assert "最多 3 个场景" in submitted["requirement"]
    assert "只围绕当前知识点" in submitted["requirement"]
    assert "MySQL权威原文" in submitted["pdf_text"]
    assert "向量库旧文本" not in submitted["pdf_text"]
    assert submitted["language"] == "zh-CN"
    assert submitted["agent_mode"] == "generate"
    assert submitted["enable_tts"] is True


def test_openmaic_job_poll_endpoint_returns_classroom_status(tmp_path, monkeypatch):
    class FakeOpenMAICClient:
        async def poll_classroom(self, *, job_id="", poll_url=""):
            return {
                "job_id": job_id,
                "status": "succeeded",
                "step": "done",
                "poll_url": poll_url,
                "url": "http://127.0.0.1:3000/classroom/classroom-1",
                "classroom_id": "classroom-1",
                "poll_interval_ms": 0,
            }

    monkeypatch.setattr(ResourceService, "openmaic_client_cls", FakeOpenMAICClient)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "poll-user", "email": "poll@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]

    response = client.get(
        "/api/resources/openmaic-jobs/job-openmaic-1",
        headers={"Authorization": f"Bearer {token}"},
        params={"poll_url": "http://127.0.0.1:3000/api/generate-classroom/job-openmaic-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-openmaic-1"
    assert payload["status"] == "succeeded"
    assert payload["classroom_id"] == "classroom-1"
    assert payload["url"] == "http://127.0.0.1:3000/classroom/classroom-1"


def test_openmaic_polling_proxy_accepts_poll_url_without_job_id(tmp_path, monkeypatch):
    class FakeOpenMAICClient:
        async def poll_classroom(self, *, job_id="", poll_url=""):
            assert job_id == ""
            assert poll_url == "http://127.0.0.1:3000/api/generate-classroom/job-poll-url-only"
            return {
                "job_id": "",
                "status": "succeeded",
                "step": "completed",
                "poll_url": poll_url,
                "classroom_id": "classroom-poll-url-only",
                "url": "http://127.0.0.1:3000/classroom/classroom-poll-url-only",
                "requirement": "",
            }

    monkeypatch.setattr(ResourceService, "openmaic_client_cls", FakeOpenMAICClient)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "poll-url-only", "email": "poll-url-only@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]

    response = client.get(
        "/api/resources/openmaic-jobs/_",
        headers={"Authorization": f"Bearer {token}"},
        params={"poll_url": "http://127.0.0.1:3000/api/generate-classroom/job-poll-url-only"},
    )

    assert response.status_code == 200
    assert response.json()["classroom_id"] == "classroom-poll-url-only"


def test_cached_lesson_refreshes_pending_openmaic_job_before_returning(tmp_path, monkeypatch):
    calls = {"openmaic_submit": 0, "openmaic_poll": 0}

    class FakeOpenMAICClient:
        async def generate_classroom(self, *, requirement, pdf_text, language="zh-CN", agent_mode="generate", enable_tts=None):  # noqa: ARG002
            calls["openmaic_submit"] += 1
            return {
                "job_id": "job-refresh",
                "status": "queued",
                "step": "queued",
                "poll_url": "http://127.0.0.1:3000/api/generate-classroom/job-refresh",
                "url": "",
                "classroom_id": "",
            }

        async def poll_classroom(self, *, job_id="", poll_url=""):
            calls["openmaic_poll"] += 1
            assert job_id == "job-refresh"
            assert poll_url == "http://127.0.0.1:3000/api/generate-classroom/job-refresh"
            return {
                "job_id": "job-refresh",
                "status": "succeeded",
                "step": "completed",
                "poll_url": poll_url,
                "url": "http://127.0.0.1:3000/classroom/classroom-refresh",
                "classroom_id": "classroom-refresh",
                "poll_interval_ms": 5000,
            }

    async def fake_run_collect(
        self,
        conversation,
        topic,
        requested_resource_types=None,
        knowledge_context=None,
        profile=None,
        graph_constraints=None,
        retrieval_trace=None,
    ):  # noqa: ARG001
        return {
            "event": "workflow_completed",
            "profile": profile.model_dump(mode="json"),
            "resources": [
                {
                    "id": "resource-doc",
                    "type": "document",
                    "title": f"{topic}璁茶В鏂囨。",
                    "topic": topic,
                    "content": "缂撳瓨OpenMAIC鍒锋柊娴嬭瘯璧勬簮",
                    "recommendation_reason": "鍩轰簬鏈湴鐭ヨ瘑搴?渚濇嵁",
                    "tags": ["document"],
                }
            ],
            "learning_path": {"student_id": profile.student_id, "stages": []},
            "knowledge_context": knowledge_context or [],
            "graph_constraints": graph_constraints or {},
            "retrieval_trace": retrieval_trace or [],
            "analysis_plan": {"agent": "analysis", "topic": topic},
            "verification_report": {"decision": "accepted", "evidence_count": 1, "graph_constraint_count": 1},
            "pedagogy_report": {"agent": "pedagogy", "score": 0.9, "decision": "accepted"},
            "debate_report": {"agent": "debate", "decision": "accepted", "debate_summary": "ok"},
            "decision_report": {
                "agent": "decision",
                "decision": "accepted",
                "next_action": "return_resources",
                "revision_count": 0,
                "max_revision_count": 1,
                "reason": "ok",
                "fallback_available": True,
            },
            "agent_events": [{"event": "agent_completed", "agent": "document", "summary": "done"}],
        }

    monkeypatch.setattr(ResourceService, "openmaic_client_cls", FakeOpenMAICClient)
    monkeypatch.setattr(ResourceService, "_agentic_rag_context", lambda self, user_id, course_id, node_id, topic: {
        "knowledge_context": [],
        "graph_constraints": {},
        "retrieval_trace": [],
    })
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(LLMClient, "complete_text", lambda self, system_prompt, user_prompt: "cached refresh outline")  # noqa: ARG005
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "openmaic-refresh", "email": "openmaic-refresh@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 程序设计", status="ready"))
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    payload = {
        "conversation": "cached openmaic refresh",
        "topic": "1.1 初识 Python",
        "course_id": 1,
        "node_id": "outline-section-1-1",
        "resource_types": ["document"],
    }
    first = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)
    second = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)
    third = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert first.json()["openmaic_classroom"]["status"] == "queued"
    assert second.json()["from_cache"] is True
    assert second.json()["openmaic_classroom"]["status"] == "succeeded"
    assert second.json()["openmaic_classroom"]["classroom_id"] == "classroom-refresh"
    assert second.json()["openmaic_classroom"]["url"] == "http://127.0.0.1:3000/classroom/classroom-refresh"
    assert third.json()["openmaic_classroom"]["classroom_id"] == "classroom-refresh"
    assert calls == {"openmaic_submit": 1, "openmaic_poll": 1}


def test_cached_lesson_does_not_refresh_completed_openmaic_classroom(tmp_path, monkeypatch):
    calls = {"openmaic_submit": 0, "openmaic_poll": 0}

    class FakeOpenMAICClient:
        async def generate_classroom(self, *, requirement, pdf_text, language="zh-CN", agent_mode="generate", enable_tts=None):  # noqa: ARG002
            calls["openmaic_submit"] += 1
            return {
                "job_id": "job-completed",
                "status": "completed",
                "step": "done",
                "poll_url": "",
                "url": "http://127.0.0.1:3000/classroom/classroom-completed",
                "classroom_id": "classroom-completed",
            }

        async def poll_classroom(self, *, job_id="", poll_url=""):  # noqa: ARG002
            calls["openmaic_poll"] += 1
            return {
                "job_id": "job-completed",
                "status": "completed",
                "step": "done",
                "poll_url": poll_url,
                "url": "http://127.0.0.1:3000/classroom/classroom-completed",
                "classroom_id": "classroom-completed",
            }

    async def fake_run_collect(
        self,
        conversation,
        topic,
        requested_resource_types=None,
        knowledge_context=None,
        profile=None,
        graph_constraints=None,
        retrieval_trace=None,
    ):  # noqa: ARG001
        return {
            "event": "workflow_completed",
            "profile": profile.model_dump(mode="json"),
            "resources": [],
            "learning_path": {"student_id": profile.student_id, "stages": []},
            "knowledge_context": knowledge_context or [],
            "graph_constraints": graph_constraints or {},
            "retrieval_trace": retrieval_trace or [],
            "analysis_plan": {"agent": "analysis", "topic": topic},
            "verification_report": {"decision": "accepted", "evidence_count": 0, "graph_constraint_count": 0},
            "pedagogy_report": {"agent": "pedagogy", "score": 0.9, "decision": "accepted"},
            "debate_report": {"agent": "debate", "decision": "accepted", "debate_summary": "ok"},
            "decision_report": {
                "agent": "decision",
                "decision": "accepted",
                "next_action": "return_resources",
                "revision_count": 0,
                "max_revision_count": 1,
                "reason": "ok",
                "fallback_available": True,
            },
            "agent_events": [],
        }

    monkeypatch.setattr(ResourceService, "openmaic_client_cls", FakeOpenMAICClient)
    monkeypatch.setattr(ResourceService, "_agentic_rag_context", lambda self, user_id, course_id, node_id, topic: {
        "knowledge_context": [],
        "graph_constraints": {},
        "retrieval_trace": [],
    })
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(LLMClient, "complete_text", lambda self, system_prompt, user_prompt: "completed outline")  # noqa: ARG005
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "openmaic-completed", "email": "openmaic-completed@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 程序设计", status="ready"))
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    payload = {
        "conversation": "completed openmaic cache",
        "topic": "1.1 初识 Python",
        "course_id": 1,
        "node_id": "outline-section-1-1",
        "resource_types": ["document"],
    }
    first = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)
    second = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["openmaic_classroom"]["status"] == "completed"
    assert second.json()["from_cache"] is True
    assert second.json()["openmaic_classroom"]["status"] == "completed"
    assert second.json()["openmaic_classroom"]["classroom_id"] == "classroom-completed"
    assert calls == {"openmaic_submit": 1, "openmaic_poll": 0}


def test_course_lesson_generation_is_cached_and_lesson_state_is_persisted(tmp_path, monkeypatch):
    calls = {"graph": 0, "openmaic": 0}

    def fake_rag_context(self, user_id, course_id, node_id, topic):  # noqa: ARG001
        return {
            "knowledge_context": [
                {
                    "chunk_id": 7,
                    "source_locator": "page 21",
                    "content": "MySQL权威原文：Python 是解释型、跨平台的高级程序设计语言。",
                    "retrieval_query": topic,
                }
            ],
            "graph_constraints": {
                "current_node": {"id": node_id, "name": topic},
                "parent": {"id": "chapter-1", "name": "第1章 Python 概述"},
                "predecessors": [],
                "successors": [],
                "related": [],
                "source_chunk_ids": [7],
            },
            "retrieval_trace": [{"query": topic, "vector_chunk_id": 7, "mysql_chunk_id": 7}],
        }

    async def fake_run_collect(
        self,
        conversation,
        topic,
        requested_resource_types=None,
        knowledge_context=None,
        profile=None,
        graph_constraints=None,
        retrieval_trace=None,
    ):  # noqa: ARG001
        calls["graph"] += 1
        return {
            "event": "workflow_completed",
            "profile": profile.model_dump(mode="json"),
            "resources": [
                {
                    "id": "resource-doc",
                    "type": "document",
                    "title": f"{topic}讲解文档",
                    "topic": topic,
                    "content": "缓存测试资源",
                    "recommendation_reason": "基于本地知识库",
                    "tags": ["document"],
                }
            ],
            "learning_path": {"student_id": profile.student_id, "stages": []},
            "knowledge_context": knowledge_context or [],
            "graph_constraints": graph_constraints or {},
            "retrieval_trace": retrieval_trace or [],
            "analysis_plan": {"agent": "analysis", "topic": topic},
            "verification_report": {"decision": "accepted", "evidence_count": 1, "graph_constraint_count": 1},
            "pedagogy_report": {"agent": "pedagogy", "score": 0.9, "decision": "accepted"},
            "debate_report": {"agent": "debate", "decision": "accepted", "debate_summary": "ok"},
            "decision_report": {
                "agent": "decision",
                "decision": "accepted",
                "next_action": "return_resources",
                "revision_count": 0,
                "max_revision_count": 1,
                "reason": "ok",
                "fallback_available": True,
            },
            "agent_events": [{"event": "agent_completed", "agent": "文档Agent", "summary": "done"}],
        }

    async def fake_openmaic(self, **kwargs):  # noqa: ARG001
        calls["openmaic"] += 1
        return OpenMAICClassroom(
            job_id="job-cached-lesson",
            status="succeeded",
            step="done",
            url="http://127.0.0.1:3000/classroom/cached",
            classroom_id="cached",
            requirement="缓存课堂大纲",
        )

    monkeypatch.setattr(ResourceService, "_agentic_rag_context", fake_rag_context)
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(ResourceService, "_generate_openmaic_classroom", fake_openmaic)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "cached-lesson", "email": "cached-lesson@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 程序设计", status="ready"))
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    payload = {
        "conversation": "根据确认画像学习 Python。",
        "topic": "1.1 初识 Python",
        "course_id": 1,
        "node_id": "outline-section-1-1",
        "resource_types": ["document"],
    }
    first = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)
    second = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)
    state_update = client.patch(
        "/api/resources/lessons/state",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "course_id": 1,
            "node_id": "outline-section-1-1",
            "current_stage": "test",
            "classroom_completed": True,
        },
    )
    third = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)
    forced = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={**payload, "force_regenerate": True},
    )
    after_forced = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert forced.status_code == 200
    assert after_forced.status_code == 200
    assert state_update.status_code == 200
    assert calls == {"graph": 2, "openmaic": 2}
    assert first.json()["from_cache"] is False
    assert second.json()["from_cache"] is True
    assert second.json()["openmaic_classroom"]["job_id"] == "job-cached-lesson"
    assert state_update.json()["current_stage"] == "test"
    assert third.json()["lesson_state"]["current_stage"] == "test"
    assert third.json()["lesson_state"]["classroom_completed"] is True
    assert forced.json()["from_cache"] is False
    assert forced.json()["lesson_state"]["current_stage"] == "classroom"
    assert forced.json()["lesson_state"]["classroom_completed"] is False
    assert after_forced.json()["from_cache"] is True
    assert after_forced.json()["lesson_state"]["current_stage"] == "classroom"
    assert after_forced.json()["lesson_state"]["classroom_completed"] is False


def test_course_lesson_force_regenerate_skips_cached_openmaic_classroom(tmp_path, monkeypatch):
    calls = {"graph": 0, "openmaic": 0}

    def fake_rag_context(self, user_id, course_id, node_id, topic):  # noqa: ARG001
        return {
            "knowledge_context": [],
            "graph_constraints": {
                "current_node": {"id": node_id, "name": topic},
                "parent": None,
                "predecessors": [],
                "successors": [],
                "related": [],
                "source_chunk_ids": [],
            },
            "retrieval_trace": [],
        }

    async def fake_run_collect(
        self,
        conversation,
        topic,
        requested_resource_types=None,
        knowledge_context=None,
        profile=None,
        graph_constraints=None,
        retrieval_trace=None,
    ):  # noqa: ARG001
        calls["graph"] += 1
        return {
            "event": "workflow_completed",
            "profile": profile.model_dump(mode="json"),
            "resources": [
                {
                    "id": f"resource-doc-{calls['graph']}",
                    "type": "document",
                    "title": f"{topic} document",
                    "topic": topic,
                    "content": "lesson content",
                    "recommendation_reason": "force regenerate test",
                    "tags": ["document"],
                }
            ],
            "learning_path": {"student_id": profile.student_id, "stages": []},
            "knowledge_context": knowledge_context or [],
            "graph_constraints": graph_constraints or {},
            "retrieval_trace": retrieval_trace or [],
            "analysis_plan": {"agent": "analysis", "topic": topic},
            "verification_report": {"decision": "accepted"},
            "pedagogy_report": {"decision": "accepted"},
            "debate_report": {"decision": "accepted"},
            "decision_report": {"decision": "accepted"},
            "agent_events": [],
        }

    async def fake_openmaic(self, **kwargs):  # noqa: ARG001
        calls["openmaic"] += 1
        return OpenMAICClassroom(
            job_id=f"job-{calls['openmaic']}",
            status="queued",
            step="queued",
            poll_url=f"http://127.0.0.1:3000/api/generate-classroom/job-{calls['openmaic']}",
            requirement="force regenerate classroom",
        )

    monkeypatch.setattr(ResourceService, "_agentic_rag_context", fake_rag_context)
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(ResourceService, "_generate_openmaic_classroom", fake_openmaic)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "force-regen", "email": "force-regen@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 程序设计", status="ready"))
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    payload = {
        "conversation": "learn Python",
        "topic": "1.1 Python",
        "course_id": 1,
        "node_id": "outline-section-1-1",
        "resource_types": ["document"],
    }
    first = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)
    cached = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=payload)
    forced = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={**payload, "force_regenerate": True},
    )

    assert first.status_code == 200
    assert cached.status_code == 200
    assert forced.status_code == 200
    assert calls == {"graph": 2, "openmaic": 2}
    assert cached.json()["from_cache"] is True
    assert forced.json()["from_cache"] is False
    assert forced.json()["openmaic_classroom"]["job_id"] == "job-2"


def test_course_lesson_cache_is_scoped_by_requested_resource_types(tmp_path, monkeypatch):
    calls = {"graph": 0, "openmaic": 0}

    def fake_rag_context(self, user_id, course_id, node_id, topic):  # noqa: ARG001
        return {
            "knowledge_context": [
                {
                    "chunk_id": 7,
                    "source_locator": "page 21",
                    "content": "MySQL权威原文：Python 列表支持有序、可变、可索引。",
                    "retrieval_query": topic,
                }
            ],
            "graph_constraints": {
                "current_node": {"id": node_id, "name": topic},
                "parent": {"id": "chapter-1", "name": "第 1 章 Python 概述"},
                "predecessors": [],
                "successors": [],
                "related": [],
                "source_chunk_ids": [7],
            },
            "retrieval_trace": [{"query": topic, "vector_chunk_id": 7, "mysql_chunk_id": 7}],
        }

    async def fake_run_collect(
        self,
        conversation,
        topic,
        requested_resource_types=None,
        knowledge_context=None,
        profile=None,
        graph_constraints=None,
        retrieval_trace=None,
    ):  # noqa: ARG001
        calls["graph"] += 1
        requested = [item.value if hasattr(item, "value") else str(item) for item in (requested_resource_types or [])]
        return {
            "event": "workflow_completed",
            "profile": profile.model_dump(mode="json"),
            "resources": [
                {
                    "id": f"resource-{'-'.join(requested) or 'default'}",
                    "type": resource_type,
                    "title": f"{topic}-{resource_type}",
                    "topic": topic,
                    "content": f"{resource_type} content",
                    "recommendation_reason": f"requested={','.join(requested)}",
                    "tags": [resource_type],
                }
                for resource_type in requested
            ],
            "learning_path": {"student_id": profile.student_id, "stages": []},
            "knowledge_context": knowledge_context or [],
            "graph_constraints": graph_constraints or {},
            "retrieval_trace": retrieval_trace or [],
            "analysis_plan": {"agent": "analysis", "topic": topic},
            "verification_report": {"decision": "accepted", "evidence_count": 1, "graph_constraint_count": 1},
            "pedagogy_report": {"agent": "pedagogy", "score": 0.9, "decision": "accepted"},
            "debate_report": {"agent": "debate", "decision": "accepted", "debate_summary": "ok"},
            "decision_report": {
                "agent": "decision",
                "decision": "accepted",
                "next_action": "return_resources",
                "revision_count": 0,
                "max_revision_count": 1,
                "reason": "ok",
                "fallback_available": True,
            },
            "agent_events": [{"event": "agent_completed", "agent": "resource", "summary": ",".join(requested)}],
        }

    async def fake_openmaic(self, **kwargs):  # noqa: ARG001
        calls["openmaic"] += 1
        return OpenMAICClassroom(
            job_id=f"job-{calls['openmaic']}",
            status="succeeded",
            step="done",
            url="http://127.0.0.1:3000/classroom/cached",
            classroom_id="cached",
            requirement="缓存课堂大纲",
        )

    monkeypatch.setattr(ResourceService, "_agentic_rag_context", fake_rag_context)
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(ResourceService, "_generate_openmaic_classroom", fake_openmaic)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "cached-scope", "email": "cached-scope@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 程序设计", status="ready"))
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    document_only = {
        "conversation": "根据确认画像学习 Python。",
        "topic": "1.1 初识 Python",
        "course_id": 1,
        "node_id": "outline-section-1-1",
        "resource_types": ["document"],
    }
    document_and_exercise = {
        **document_only,
        "resource_types": ["document", "exercise"],
    }

    first = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=document_only)
    second = client.post("/api/resources/generate", headers={"Authorization": f"Bearer {token}"}, json=document_and_exercise)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["from_cache"] is False
    assert second.json()["from_cache"] is False
    assert [resource["type"] for resource in first.json()["resources"]] == ["document"]
    assert [resource["type"] for resource in second.json()["resources"]] == ["document", "exercise"]
    assert calls == {"graph": 2, "openmaic": 2}


def test_course_lesson_cache_reuses_same_requested_resource_type_set(tmp_path, monkeypatch):
    calls = {"graph": 0, "openmaic": 0}

    def fake_rag_context(self, user_id, course_id, node_id, topic):  # noqa: ARG001
        return {
            "knowledge_context": [],
            "graph_constraints": {
                "current_node": {"id": node_id, "name": topic},
                "parent": None,
                "predecessors": [],
                "successors": [],
                "related": [],
                "source_chunk_ids": [],
            },
            "retrieval_trace": [],
        }

    async def fake_run_collect(
        self,
        conversation,
        topic,
        requested_resource_types=None,
        knowledge_context=None,
        profile=None,
        graph_constraints=None,
        retrieval_trace=None,
    ):  # noqa: ARG001
        calls["graph"] += 1
        requested = [item.value if hasattr(item, "value") else str(item) for item in (requested_resource_types or [])]
        return {
            "event": "workflow_completed",
            "profile": profile.model_dump(mode="json"),
            "resources": [
                {
                    "id": f"resource-{resource_type}",
                    "type": resource_type,
                    "title": resource_type,
                    "topic": topic,
                    "content": resource_type,
                    "recommendation_reason": "cache set test",
                    "tags": [resource_type],
                }
                for resource_type in requested
            ],
            "learning_path": {"student_id": profile.student_id, "stages": []},
            "knowledge_context": knowledge_context or [],
            "graph_constraints": graph_constraints or {},
            "retrieval_trace": retrieval_trace or [],
            "analysis_plan": {"agent": "analysis", "topic": topic},
            "verification_report": {"decision": "accepted"},
            "pedagogy_report": {"decision": "accepted"},
            "debate_report": {"decision": "accepted"},
            "decision_report": {"decision": "accepted"},
            "agent_events": [],
        }

    async def fake_openmaic(self, **kwargs):  # noqa: ARG001
        calls["openmaic"] += 1
        return OpenMAICClassroom(
            job_id=f"job-{calls['openmaic']}",
            status="succeeded",
            step="done",
            url="http://127.0.0.1:3000/classroom/cached",
            classroom_id="cached",
            requirement="cached classroom",
        )

    monkeypatch.setattr(ResourceService, "_agentic_rag_context", fake_rag_context)
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(ResourceService, "_generate_openmaic_classroom", fake_openmaic)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "cached-set", "email": "cached-set@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 程序设计", status="ready"))
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    base_payload = {
        "conversation": "learn Python",
        "topic": "1.1 Python",
        "course_id": 1,
        "node_id": "outline-section-1-1",
    }
    first = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={**base_payload, "resource_types": ["document", "exercise"]},
    )
    second = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={**base_payload, "resource_types": ["exercise", "document"]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["from_cache"] is False
    assert second.json()["from_cache"] is True
    assert calls == {"graph": 1, "openmaic": 1}


def test_lesson_state_update_persists_completed_openmaic_classroom(tmp_path, monkeypatch):
    async def fake_run_collect(self, *args, **kwargs):  # noqa: ARG001
        return {
            "profile": {"student_id": "user-1"},
            "resources": [],
            "learning_path": {"student_id": "user-1", "stages": []},
            "knowledge_context": [],
            "graph_constraints": {},
            "retrieval_trace": [],
            "analysis_plan": {},
            "verification_report": {},
            "pedagogy_report": {},
            "debate_report": {},
            "decision_report": {"decision": "accepted"},
            "agent_events": [],
        }

    async def fake_openmaic(self, **kwargs):  # noqa: ARG001
        return OpenMAICClassroom(job_id="job-poll", status="queued", step="queued", poll_url="/api/jobs/job-poll")

    monkeypatch.setattr(ResourceService, "_agentic_rag_context", lambda self, user_id, course_id, node_id, topic: {
        "knowledge_context": [],
        "graph_constraints": {},
        "retrieval_trace": [],
    })
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(ResourceService, "_generate_openmaic_classroom", fake_openmaic)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "openmaic-cache", "email": "openmaic-cache@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 程序设计", status="ready"))
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "根据确认画像学习 Python。",
            "topic": "1.1 初识 Python",
            "course_id": 1,
            "node_id": "outline-section-1-1",
            "resource_types": ["document"],
        },
    )
    state_update = client.patch(
        "/api/resources/lessons/state",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "course_id": 1,
            "node_id": "outline-section-1-1",
            "openmaic_classroom": {
                "job_id": "job-poll",
                "status": "succeeded",
                "step": "done",
                "url": "http://127.0.0.1:3000/classroom/classroom-poll",
                "classroom_id": "classroom-poll",
                "requirement": "缓存课堂大纲",
            },
        },
    )
    cached = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "根据确认画像学习 Python。",
            "topic": "1.1 初识 Python",
            "course_id": 1,
            "node_id": "outline-section-1-1",
            "resource_types": ["document"],
        },
    )

    assert state_update.status_code == 200
    assert cached.json()["from_cache"] is True
    assert cached.json()["openmaic_classroom"]["status"] == "succeeded"
    assert cached.json()["openmaic_classroom"]["classroom_id"] == "classroom-poll"


def test_generate_workflow_endpoint_falls_back_to_mysql_chunks_when_vector_search_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(CourseService, "semantic_search", lambda self, user_id, course_id, query: [])  # noqa: ARG005
    monkeypatch.setattr(
        CourseService,
        "get_knowledge_graph",
        lambda self, user_id, course_id: {  # noqa: ARG005
            "nodes": [
                {
                    "id": "outline-section-1-1",
                    "name": "1.1 初识 Python",
                    "node_type": "knowledge_point",
                    "level": 2,
                    "parent_id": "",
                    "summary": "认识 Python 的基本特点",
                    "source_chunk_ids": [],
                }
            ],
            "edges": [],
        },
    )
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "mysql-fallback", "email": "mysql-fallback@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        course = Course(id=1, user_id=1, name="Python 程序设计", status="ready")
        material = CourseMaterial(
            id=1,
            course_id=1,
            user_id=1,
            filename="python.pdf",
            file_type="pdf",
            storage_path=str(tmp_path / "python.pdf"),
            size_bytes=12,
            parse_status="parsed",
        )
        list_chunk = KnowledgeChunk(
            id=10,
            course_id=1,
            material_id=1,
            chunk_index=1,
            source_locator="page 21",
            heading="初识 Python",
            content="Python 是一种解释型、面向对象、跨平台的高级程序设计语言。",
            token_count=28,
            embedding_id="chunk-10",
        )
        unrelated_chunk = KnowledgeChunk(
            id=11,
            course_id=1,
            material_id=1,
            chunk_index=2,
            source_locator="page 99",
            heading="数据库",
            content="关系数据库使用表结构保存数据。",
            token_count=18,
            embedding_id="chunk-11",
        )
        db.add_all([course, material, list_chunk, unrelated_chunk, GraphBuildJob(course_id=1, status="succeeded", current_stage="done", progress=100)])
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "我是计算机大二学生，正在学习 Python。",
            "topic": "1.1 初识 Python",
            "course_id": 1,
            "node_id": "outline-section-1-1",
            "resource_types": ["document"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_context"][0]["chunk_id"] == 10
    assert payload["retrieval_trace"][0]["strategy"] == "mysql_fallback"
    assert payload["verification_report"]["decision"] == "accepted"


def test_generate_workflow_endpoint_uses_confirmed_profile_without_llm_profile_json(tmp_path, monkeypatch):
    async def broken_complete_json(self, system_prompt, user_prompt):  # noqa: ARG001
        raise AssertionError("resource generation should not extract profile through LLM when profile is confirmed")

    monkeypatch.setattr(LLMClient, "complete_json", broken_complete_json)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "confirmed-profile", "email": "confirmed-profile@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]

    profile = insert_confirmed_profile(client)

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "前端传入的拼接文本不要求是 JSON。",
            "topic": "1.1 初识 Python",
            "resource_types": ["document", "exercise"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["student_id"] == "user-1"
    assert [resource["type"] for resource in payload["resources"]] == ["document", "exercise"]


def test_generate_workflow_endpoint_requires_confirmed_profile_for_course_learning(tmp_path):
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "missing-profile", "email": "missing-profile@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "前端拼接文本不能替代确认画像。",
            "topic": "1.1 初识 Python",
            "course_id": 1,
            "node_id": "outline-section-1-1",
            "resource_types": ["document"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "confirmed course profile is required"


def test_generate_workflow_endpoint_rejects_unknown_course_node_without_saving_session(tmp_path, monkeypatch):
    calls = {"graph": 0, "openmaic": 0}

    async def fake_run_collect(self, *args, **kwargs):  # noqa: ARG001
        calls["graph"] += 1
        return {"profile": {"student_id": "user-1"}, "resources": [], "learning_path": {"student_id": "user-1", "stages": []}}

    async def fake_openmaic(self, **kwargs):  # noqa: ARG001
        calls["openmaic"] += 1
        return OpenMAICClassroom(status="queued")

    monkeypatch.setattr(
        CourseService,
        "get_knowledge_graph",
        lambda self, user_id, course_id: {  # noqa: ARG005
            "nodes": [
                {"id": "outline-section-1-1", "name": "1.1 鍒濊瘑 Python", "node_type": "concept", "level": 2},
            ],
            "edges": [],
        },
    )
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(ResourceService, "_generate_openmaic_classroom", fake_openmaic)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "unknown-node-resource", "email": "unknown-node-resource@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 绋嬪簭璁捐", status="ready"))
        db.add(GraphBuildJob(course_id=1, status="succeeded", current_stage="done", progress=100))
        db.commit()
    insert_confirmed_profile(client, course_id=1)

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "fabricated node should not generate lesson",
            "topic": "C 璇█鎸囬拡",
            "course_id": 1,
            "node_id": "c-section-pointer",
            "resource_types": ["document"],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "knowledge-point learning requires a current-course graph node"
    assert calls == {"graph": 0, "openmaic": 0}
    with client.app.state.testing_session_factory() as db:
        sessions = list(db.scalars(select(CourseLessonSession)))
    assert sessions == []


def test_generate_workflow_endpoint_rejects_chapter_heading_node(tmp_path, monkeypatch):
    calls = {"graph": 0, "openmaic": 0}

    def fake_rag_context(self, user_id, course_id, node_id, topic):  # noqa: ARG001
        return {
            "knowledge_context": [],
            "graph_constraints": {
                "current_node": {"id": "c-chapter-1", "name": "第 1 章 C语言概述", "node_type": "chapter"},
                "parent": {"id": "c-course-root", "name": "C语言程序设计"},
                "predecessors": [],
                "successors": [],
                "related": [],
                "source_chunk_ids": [],
            },
            "retrieval_trace": [],
        }

    async def fake_run_collect(self, *args, **kwargs):  # noqa: ARG001
        calls["graph"] += 1
        return {"profile": {"student_id": "user-1"}, "resources": [], "learning_path": {"student_id": "user-1", "stages": []}}

    async def fake_openmaic(self, **kwargs):  # noqa: ARG001
        calls["openmaic"] += 1
        return OpenMAICClassroom(status="queued")

    monkeypatch.setattr(ResourceService, "_agentic_rag_context", fake_rag_context)
    monkeypatch.setattr("app.agents.graph.LearningAgentGraph.run_collect", fake_run_collect)
    monkeypatch.setattr(ResourceService, "_generate_openmaic_classroom", fake_openmaic)
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "chapter-resource", "email": "chapter-resource@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="C语言程序设计", status="ready"))
        db.commit()
    insert_confirmed_profile(client, course_id=1, learning_goal="掌握 C 语言程序设计")

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "chapter heading should not generate lesson",
            "topic": "第 1 章 C语言概述",
            "course_id": 1,
            "node_id": "c-chapter-1",
            "resource_types": ["document"],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "knowledge-point learning requires a concrete knowledge node"
    assert calls == {"graph": 0, "openmaic": 0}


def test_course_resource_generation_rejects_account_profile_without_course_profile(tmp_path):
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={
            "username": "course-resource-global-profile",
            "email": "course-resource-global@example.com",
            "password": "secret123",
        },
    )
    token = auth.json()["access_token"]
    insert_confirmed_profile(client, course_id=None)
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python course", status="ready"))
        db.commit()

    response = client.post(
        "/api/resources/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "conversation": "account profile should not unlock a course lesson",
            "topic": "1.1 Python",
            "course_id": 1,
            "node_id": "outline-section-1-1",
            "resource_types": ["document"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "confirmed course profile is required"


def test_generate_workflow_endpoint_requires_login(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/resources/generate",
        json={"conversation": "想学习机器学习", "topic": "梯度下降"},
    )

    assert response.status_code == 401


def test_learning_business_endpoints_require_login(tmp_path):
    client = make_client(tmp_path)

    profile = client.post("/api/chat/profile", json={"conversation": "计算机大二，想学机器学习"})
    path = client.post("/api/paths/plan", json={"conversation": "计算机大二，想学机器学习", "topic": "梯度下降"})
    assessment = client.post(
        "/api/assessments/submit",
        json={
            "student_id": "student-xm",
            "event_type": "exercise_submitted",
            "topic": "梯度下降",
            "score": 0.5,
            "detail": "学习率判断错误",
        },
    )

    assert profile.status_code == 401
    assert path.status_code == 401
    assert assessment.status_code == 401


def test_comprehensive_assessment_endpoint_updates_mastery_and_profile(tmp_path):
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={"username": "assessment-full", "email": "assessment-full@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 程序设计", status="ready"))
        db.commit()
    insert_confirmed_profile(client, course_id=1)
    insert_completed_lesson_state(client, course_id=1, topic="1.1 初识 Python")

    response = client.post(
        "/api/assessments/submit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "student_id": "user-1",
            "topic": "1.1 初识 Python",
            "course_id": 1,
            "knowledge_node_id": "outline-section-1-1",
            "classroom_completed": True,
            "notes_completed": True,
            "mind_map_completed": True,
            "code_lab_completed": True,
            "quiz_answers": [
                {"id": "concept", "dimension": "概念理解", "correct": True, "selected_answer_index": 1, "weight": 0.5},
                {"id": "transfer", "dimension": "迁移应用", "correct": True, "selected_answer_index": 1, "weight": 0.5},
            ],
            "code_attempt": {
                "prompt": "输出 Hello Python",
                "code": "print('Hello Python')",
                "expected_output": "Hello Python",
                "actual_output": "Hello Python",
                "passed": True,
                "attempts": 1,
            },
        },
    )
    profile = client.get("/api/profiles/me", headers={"Authorization": f"Bearer {token}"}, params={"course_id": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is True
    assert payload["final_score"] >= 0.9
    assert payload["dimension_scores"]["code"] == 1.0
    with client.app.state.testing_session_factory() as db:
        mastery = db.query(KnowledgeNodeMastery).filter_by(
            user_id=1,
            course_id=1,
            node_id="outline-section-1-1",
        ).one()
        assert mastery.mastery_status == "proficient"
        assert mastery.mastery_score == payload["final_score"]
    assert profile.json()["updated_evidence"][-1]["topic"] == "1.1 初识 Python"


def test_course_assessment_rejects_account_profile_without_course_profile(tmp_path):
    client = make_client(tmp_path)
    auth = client.post(
        "/api/auth/register",
        json={
            "username": "assessment-global-profile",
            "email": "assessment-global@example.com",
            "password": "secret123",
        },
    )
    token = auth.json()["access_token"]
    insert_confirmed_profile(client, course_id=None)
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python course", status="ready"))
        db.commit()

    response = client.post(
        "/api/assessments/submit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "student_id": "user-1",
            "event_type": "exercise_submitted",
            "topic": "1.1 Python",
            "course_id": 1,
            "knowledge_node_id": "outline-section-1-1",
            "score": 0.4,
            "detail": "course assessment should require course profile",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "confirmed course profile is required"
