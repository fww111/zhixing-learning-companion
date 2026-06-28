import asyncio

from fastapi.testclient import TestClient

from app.db import Base, create_engine_for_url, create_session_factory
from app.main import create_app
from app.models.course import Course, CourseMaterial, GraphBuildJob, KnowledgeChunk
from app.models.profile import StudentProfile
from app.models.profile_record import LearningProfileEvent, StudentProfileRecord
from app.schemas.tutor import TutorChatRequest, TutorChatResponse
from app.services.course_service import CourseService
from app.services.tutor_service import TutorService


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


class FakeTutorLLM:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""
        self.calls = 0

    async def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return "enhanced tutor answer with chunk#7"


class HangingTutorLLM:
    async def complete_text(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
        await asyncio.sleep(10)
        return "不应该返回"


class FakeVisionTutorLLM:
    model = "qwen3.7-plus"

    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""
        self.images = []
        self.calls = 0

    async def complete_multimodal_text(self, system_prompt: str, user_prompt: str, images: list[dict]) -> str:
        self.calls += 1
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.images = images
        return "Qwen3.7-Plus grounded answer with chunk#7"


class FailingVisionTutorLLM:
    async def complete_multimodal_text(self, system_prompt: str, user_prompt: str, images: list[dict]) -> str:  # noqa: ARG002
        raise AssertionError("vision LLM should not be called for text-only tutoring")


class HangingVisionTutorLLM:
    model = "qwen3.7-plus"

    async def complete_multimodal_text(self, system_prompt: str, user_prompt: str, images: list[dict]) -> str:  # noqa: ARG002
        await asyncio.sleep(10)
        return "should not return"


def test_tutor_service_builds_grounded_multi_agent_response():
    service = TutorService(FakeCourseService({}), rag_service_cls=FakeRAGService)

    response = asyncio.run(service.chat(
        user_id=3,
        request=TutorChatRequest(
            course_id=9,
            node_id="node-variable",
            page_context="learning",
            message="变量名为什么不能以数字开头？",
        ),
    ))

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


def test_tutor_service_uses_llm_to_enhance_rag_answer_and_includes_image_context():
    llm = FakeTutorLLM()
    service = TutorService(FakeCourseService({}), rag_service_cls=FakeRAGService, llm=llm)

    response = asyncio.run(service.chat(
        user_id=3,
        request=TutorChatRequest(
            course_id=9,
            node_id="node-variable",
            page_context="learning",
            message="看这张图片里的变量命名哪里错了？",
            attachments=[
                {
                    "id": "img-1",
                    "filename": "variable-error.png",
                    "content_type": "image/png",
                    "description": "用户上传图片：variable-error.png，可能包含变量命名报错截图。",
                    "data_url": "data:image/png;base64,AAAABBBB",
                }
            ],
        ),
    ))

    assert response.answer.startswith("enhanced tutor answer")
    assert response.answer != response.evidence_chunks[0].content
    assert response.analysis_plan["attachment_count"] == 1
    assert response.analysis_plan["attachments"][0]["filename"] == "variable-error.png"
    assert "已接收图片数据" in response.analysis_plan["attachments"][0]["description"]
    assert "variable-error.png" in llm.user_prompt
    assert "AAAABBBB" not in llm.user_prompt
    assert "变量名由字母、数字、下划线组成" in llm.user_prompt
    assert "chunk#7" in llm.user_prompt


def test_tutor_service_routes_image_attachment_to_qwen_vision_llm():
    text_llm = FakeTutorLLM()
    vision_llm = FakeVisionTutorLLM()
    service = TutorService(
        FakeCourseService({}),
        rag_service_cls=FakeRAGService,
        llm=text_llm,
        vision_llm=vision_llm,
    )

    response = asyncio.run(service.chat(
        user_id=3,
        request=TutorChatRequest(
            course_id=9,
            node_id="node-variable",
            page_context="profile-interview",
            message="Please explain the screenshot.",
            attachments=[
                {
                    "id": "img-1",
                    "filename": "variable-error.png",
                    "content_type": "image/png",
                    "description": "variable naming error screenshot",
                    "data_url": "data:image/png;base64,AAAABBBB",
                }
            ],
        ),
    ))

    assert response.answer.startswith("Qwen3.7-Plus")
    assert text_llm.calls == 0
    assert vision_llm.calls == 1
    assert vision_llm.images == [
        {
            "id": "img-1",
            "filename": "variable-error.png",
            "content_type": "image/png",
            "data_url": "data:image/png;base64,AAAABBBB",
        }
    ]
    assert "AAAABBBB" not in vision_llm.user_prompt
    assert "chunk#7" in vision_llm.user_prompt
    assert response.analysis_plan["multimodal_required"] is True
    assert response.analysis_plan["generation_model"] == "qwen3.7-plus"


def test_tutor_service_does_not_use_vision_llm_for_text_only_question():
    llm = FakeTutorLLM()
    service = TutorService(
        FakeCourseService({}),
        rag_service_cls=FakeRAGService,
        llm=llm,
        vision_llm=FailingVisionTutorLLM(),
    )

    response = asyncio.run(service.chat(
        user_id=3,
        request=TutorChatRequest(
            course_id=9,
            node_id="node-variable",
            page_context="learning",
            message="text-only question",
        ),
    ))

    assert response.answer.startswith("enhanced tutor answer")
    assert llm.calls == 1
    assert response.analysis_plan["multimodal_required"] is False


def test_tutor_service_falls_back_when_qwen_vision_llm_times_out(monkeypatch):
    monkeypatch.setattr("app.services.tutor_service.TUTOR_LLM_TIMEOUT_SECONDS", 0.01)
    service = TutorService(
        FakeCourseService({}),
        rag_service_cls=FakeRAGService,
        vision_llm=HangingVisionTutorLLM(),
    )

    response = asyncio.run(service.chat(
        user_id=3,
        request=TutorChatRequest(
            course_id=9,
            node_id="node-variable",
            page_context="learning",
            message="Please explain the screenshot.",
            attachments=[
                {
                    "id": "img-1",
                    "filename": "variable-error.png",
                    "content_type": "image/png",
                    "description": "variable naming error screenshot",
                    "data_url": "data:image/png;base64,AAAABBBB",
                }
            ],
        ),
    ))

    assert "Please explain the screenshot." in response.answer
    assert response.verification_report["decision"] == "accepted"


def test_tutor_service_falls_back_when_llm_times_out(monkeypatch):
    monkeypatch.setattr("app.services.tutor_service.TUTOR_LLM_TIMEOUT_SECONDS", 0.01)
    service = TutorService(FakeCourseService({}), rag_service_cls=FakeRAGService, llm=HangingTutorLLM())

    response = asyncio.run(service.chat(
        user_id=3,
        request=TutorChatRequest(
            course_id=9,
            node_id="node-variable",
            page_context="learning",
            message="变量名为什么不能以数字开头？",
        ),
    ))

    assert "变量名由字母、数字、下划线组成" in response.answer
    assert response.verification_report["decision"] == "accepted"


class EmptyRAGService:
    def __init__(self, course_service):  # noqa: ARG002
        pass

    def build_context(self, *, user_id, course_id, node_id, topic):  # noqa: ARG002
        return {"knowledge_context": [], "graph_constraints": {}, "retrieval_trace": []}


class IrrelevantRAGService:
    def __init__(self, course_service):  # noqa: ARG002
        pass

    def build_context(self, *, user_id, course_id, node_id, topic):  # noqa: ARG002
        return {
            "knowledge_context": [
                {
                    "chunk_id": 5703,
                    "source_locator": "page 101",
                    "heading": "指针数组排序",
                    "content": "本节习题解析 C 语言中指针数组排序、魔方阵以及结构体变量比较。",
                    "retrieval_query": topic,
                    "distance": 0.1,
                    "storage": "mysql",
                },
                {
                    "chunk_id": 5577,
                    "source_locator": "page 97",
                    "heading": "魔方阵",
                    "content": "魔方阵程序要求按照行列规律填充二维数组并输出矩阵。",
                    "retrieval_query": topic,
                    "distance": 0.12,
                    "storage": "mysql",
                },
            ],
            "graph_constraints": {
                "current_node": {"id": node_id, "name": "计算机基础概念", "node_type": "knowledge_point"},
                "parent": {"id": "chapter-1", "name": "程序设计基础"},
                "predecessors": [],
                "successors": [],
                "related": [],
                "source_chunk_ids": [5703, 5577],
                "node_found": True,
            },
            "retrieval_trace": [
                {"query": topic, "vector_chunk_id": 5703, "mysql_chunk_id": 5703, "strategy": "vector_to_mysql"},
                {"query": topic, "vector_chunk_id": 5577, "mysql_chunk_id": 5577, "strategy": "vector_to_mysql"},
            ],
        }


def test_tutor_service_marks_low_confidence_when_no_course_evidence():
    service = TutorService(FakeCourseService({}), rag_service_cls=EmptyRAGService)

    response = asyncio.run(service.chat(
        user_id=3,
        request=TutorChatRequest(course_id=9, message="解释一个知识点"),
    ))

    assert "未检索到课程知识库证据" in response.answer
    assert response.verification_report["decision"] == "fallback"
    assert response.decision_report["decision"] == "fallback"
    assert response.evidence_chunks == []


def test_tutor_service_filters_irrelevant_retrieved_chunks_before_answering():
    service = TutorService(FakeCourseService({}), rag_service_cls=IrrelevantRAGService)

    response = asyncio.run(service.chat(
        user_id=3,
        request=TutorChatRequest(
            course_id=9,
            page_context="profile",
            message="有人认为计算机是万能的，计算机完成各种事务的依据是什么？",
        ),
    ))

    assert response.evidence_chunks == []
    assert "chunk#5703" not in response.answer
    assert "指针数组排序" not in response.answer
    assert "魔方阵" not in response.answer
    assert response.verification_report["decision"] == "fallback"
    assert response.decision_report["decision"] == "fallback"


class CapturingRAGService:
    last_topic = ""
    last_node_id = ""

    def __init__(self, course_service):  # noqa: ARG002
        pass

    def build_context(self, *, user_id, course_id, node_id, topic):  # noqa: ARG002
        CapturingRAGService.last_topic = topic
        CapturingRAGService.last_node_id = node_id
        return {"knowledge_context": [], "graph_constraints": {}, "retrieval_trace": []}


def test_tutor_service_uses_student_question_as_retrieval_topic_not_opaque_node_id():
    service = TutorService(FakeCourseService({}), rag_service_cls=CapturingRAGService)

    asyncio.run(service.chat(
        user_id=3,
        request=TutorChatRequest(
            course_id=9,
            node_id="outline-section-1-1",
            page_context="learning",
            message="变量名为什么不能以数字开头？",
        ),
    ))

    assert CapturingRAGService.last_topic == "变量名为什么不能以数字开头？"
    assert CapturingRAGService.last_node_id == "outline-section-1-1"


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


def seed_confirmed_profile(client: TestClient, user_id: int, course_id: int, student_id: str = "student-tutor") -> None:
    profile = StudentProfile(
        student_id=student_id,
        major="计算机科学",
        grade="大一",
        learning_goal="掌握程序设计基础",
        knowledge_foundation="变量和输入输出基础一般",
        learning_style="先图解再练习",
        cognitive_style="先理解规则再写代码",
        weak_points=["变量命名"],
        time_preference="每天1小时",
        resource_preference=["document", "code_lab"],
        motivation="完成课程项目",
        constraints=["晚间学习"],
        assessment_preference="选择题和编程题",
        knowledge_graph_focus=["变量"],
    ).with_completion_score()
    with client.app.state.testing_session_factory() as db:
        db.add(
            StudentProfileRecord(
                user_id=user_id,
                course_id=course_id,
                student_id=student_id,
                profile_data=profile.model_dump(mode="json"),
            )
        )
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


def test_tutor_chat_endpoint_rejects_course_owned_by_another_user(tmp_path):
    client = make_tutor_client(tmp_path)
    auth_token(client, "course-owner")
    other_token = auth_token(client, "course-outsider")
    seed_course_with_chunk(client, user_id=1, course_id=1, content="Python 变量名不能以数字开头。")

    response = client.post(
        "/api/tutor/chat",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"course_id": 1, "message": "为什么变量不能以数字开头？"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "course not found"


def test_tutor_chat_records_course_learning_event(tmp_path, monkeypatch):
    monkeypatch.setattr(CourseService, "semantic_search", lambda self, user_id, course_id, query: [])  # noqa: ARG005
    monkeypatch.setattr(CourseService, "get_knowledge_graph", lambda self, user_id, course_id: {"nodes": [], "edges": []})  # noqa: ARG005
    client = make_tutor_client(tmp_path)
    token = auth_token(client, "tutor-event")
    seed_course_with_chunk(client, user_id=1, course_id=1, content="Python 变量。")
    seed_confirmed_profile(client, user_id=1, course_id=1)

    response = client.post(
        "/api/tutor/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"course_id": 1, "node_id": "node-variable", "message": "变量是什么？"},
    )

    assert response.status_code == 200
    with client.app.state.testing_session_factory() as db:
        events = list(db.query(LearningProfileEvent).filter_by(user_id=1, course_id=1))
    assert len(events) == 1
    assert events[0].event_type == "tutor_question_asked"
    assert events[0].knowledge_node_id == "node-variable"
    assert "变量是什么" in events[0].detail
