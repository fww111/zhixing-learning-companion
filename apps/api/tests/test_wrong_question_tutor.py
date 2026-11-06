import asyncio

import pytest

from app.llm.client import LLMClient
from app.schemas.wrong_question_tutor import (
    InteractiveAnswerRequest,
    VariationQuestion,
    WrongQuestionContext,
)
from app.services.course_service import CourseService
from app.services.wrong_question_tutor_service import WrongQuestionTutorService


def quiz_context() -> WrongQuestionContext:
    return WrongQuestionContext(
        course_id=1,
        node_id="node-1-2",
        topic="变量与标识符",
        question_type="quiz",
        prompt="下列哪个变量名在 Python 中是不合法的？",
        options=["_my_var", "2nd_value", "userName", "PI"],
        selected_answer="A",
        correct_answer="B",
        attempts=1,
    )


def code_context() -> WrongQuestionContext:
    return WrongQuestionContext(
        course_id=1,
        node_id="node-2-1",
        topic="循环结构",
        question_type="code",
        prompt="输入 n，输出 1 到 n 的累加和。",
        code="n = int(input())\ntotal = 0\nprint(total)",
        actual_output="0",
        expected_output="15",
        attempts=2,
    )


class StubLLM:
    """按 system prompt 分流返回固定 JSON，验证 LLM 正常路径。"""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[str] = []

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.calls.append(system_prompt)
        return self.payload


class StubRAGService:
    """提供固定证据块，让 LLM 正常路径可被触发。"""

    def __init__(self, course_service=None) -> None:
        pass

    def build_context(self, **kwargs):
        return {
            "knowledge_context": [
                {
                    "chunk_id": 3,
                    "source_locator": "page 12",
                    "heading": "标识符规则",
                    "content": "变量名不能以数字开头，也不能使用语言关键字。",
                    "retrieval_query": "变量名",
                    "distance": 0.12,
                    "storage": "mysql",
                }
            ],
            "graph_constraints": {},
            "retrieval_trace": [],
        }


def test_explain_quiz_without_llm_falls_back_to_deterministic_content():
    service = WrongQuestionTutorService(course_service=None, llm=None)
    result = asyncio.run(service.explain(user_id=1, context=quiz_context()))

    assert result.diagnosis
    assert "变量与标识符" in result.explanation or "核心规则" in result.explanation
    assert result.key_points
    assert result.verification_report["decision"] == "fallback"


def test_explain_uses_llm_payload_when_valid():
    stub = StubLLM(
        {
            "diagnosis": "把标识符规则记反了。",
            "explanation": "### 规则\n变量名不能以数字开头（chunk#3）。",
            "key_points": ["首字符不能是数字", "不能与关键字冲突"],
        }
    )
    service = WrongQuestionTutorService(course_service=None, llm=stub, rag_service_cls=StubRAGService)
    result = asyncio.run(service.explain(user_id=1, context=quiz_context()))

    assert result.diagnosis == "把标识符规则记反了。"
    assert result.key_points == ["首字符不能是数字", "不能与关键字冲突"]
    assert any("错题讲解智能体" in call for call in stub.calls)


def test_variations_without_llm_returns_two_quiz_and_one_short_answer():
    service = WrongQuestionTutorService(course_service=None, llm=None)
    bundle = asyncio.run(service.variations(user_id=1, context=code_context()))

    assert len(bundle.questions) == 3
    quiz_items = [q for q in bundle.questions if q.question_type == "quiz"]
    short_items = [q for q in bundle.questions if q.question_type == "short_answer"]
    assert len(quiz_items) >= 2
    assert len(short_items) >= 1
    for item in quiz_items:
        assert item.correct_answer_index is not None
        assert 0 <= item.correct_answer_index < len(item.options)
    for item in short_items:
        assert item.reference_answer


def test_variations_normalizes_llm_output_and_drops_invalid_questions():
    stub = StubLLM(
        {
            "questions": [
                {
                    "id": "v1",
                    "question_type": "quiz",
                    "prompt": "quiz 题正常返回",
                    "options": ["甲", "乙", "丙"],
                    "correct_answer_index": 2,
                    "focus": "概念",
                    "difficulty": "基础",
                },
                {
                    "id": "v2",
                    "question_type": "quiz",
                    "prompt": "缺正确下标应降级为简答题",
                    "options": ["甲", "乙"],
                    "correct_answer_index": 5,
                    "reference_answer": "乙不合法，因为变量名不能以数字开头。",
                    "focus": "陷阱",
                    "difficulty": "进阶",
                },
                {"id": "v3", "question_type": "quiz", "prompt": "", "options": ["甲"], "correct_answer_index": 0},
                {
                    "id": "v4",
                    "question_type": "short_answer",
                    "prompt": "简答题正常返回",
                    "options": [],
                    "reference_answer": "参考答案",
                    "difficulty": "挑战",
                },
            ]
        }
    )
    service = WrongQuestionTutorService(course_service=None, llm=stub, rag_service_cls=StubRAGService)
    bundle = asyncio.run(service.variations(user_id=1, context=quiz_context(), count=4))

    by_id = {q.id: q for q in bundle.questions}
    assert by_id["v1"].correct_answer_index == 2
    assert by_id["v1"].options == ["甲", "乙", "丙"]
    # v2: quiz 缺合法下标 → 降级 short_answer，保留参考答案；无参考答案则丢弃（v3）
    assert by_id["v2"].question_type == "short_answer"
    assert by_id["v2"].reference_answer == "乙不合法，因为变量名不能以数字开头。"
    assert "v3" not in by_id


def test_answer_quiz_is_objectively_graded_with_llm_comment():
    stub = StubLLM({"correct": False, "score": 10, "comment": "忽略客观结果也不会被采纳。"})
    service = WrongQuestionTutorService(course_service=None, llm=stub)
    request = InteractiveAnswerRequest(
        course_id=1,
        topic="变量与标识符",
        question=VariationQuestion(
            id="v1",
            question_type="quiz",
            prompt="哪个变量名不合法？",
            options=["_my_var", "2nd_value"],
            correct_answer_index=1,
        ),
        student_answer_index=1,
    )
    verdict = asyncio.run(service.answer(user_id=1, request=request))

    assert verdict.correct is True
    assert verdict.score >= 0
    assert verdict.comment


def test_answer_short_answer_uses_heuristic_without_llm():
    service = WrongQuestionTutorService(course_service=None, llm=None)
    question = VariationQuestion(
        id="v3",
        question_type="short_answer",
        prompt="说清判定规则并举例。",
        reference_answer="变量名不能以数字开头，且不能使用关键字。",
    )
    good = InteractiveAnswerRequest(
        course_id=1,
        topic="变量",
        question=question,
        student_answer_text="变量名不能以数字开头，也不能用关键字，比如 2nd_value 是错的。",
    )
    bad = InteractiveAnswerRequest(
        course_id=1,
        topic="变量",
        question=question,
        student_answer_text="不知道，随便写一个。",
    )

    assert asyncio.run(service.answer(user_id=1, request=good)).correct is True
    assert asyncio.run(service.answer(user_id=1, request=bad)).correct is False


def test_answer_quiz_wrong_gets_fallback_comment_without_llm():
    service = WrongQuestionTutorService(course_service=None, llm=None)
    request = InteractiveAnswerRequest(
        course_id=1,
        topic="循环结构",
        question=VariationQuestion(
            id="v1",
            question_type="quiz",
            prompt="range(1, 5) 产生哪些值？",
            options=["1-4", "1-5"],
            correct_answer_index=0,
            focus="边界",
        ),
        student_answer_index=1,
    )
    verdict = asyncio.run(service.answer(user_id=1, request=request))

    assert verdict.correct is False
    assert "循环结构" not in verdict.comment or "边界" in verdict.comment
    assert verdict.score < 100


def test_mock_llm_client_degrades_to_deterministic_fallback():
    """无 Key 环境（mock LLM 返回画像 JSON）下，讲解与变式仍可用。"""
    service = WrongQuestionTutorService(
        course_service=None,
        llm=LLMClient(api_key="", mock=True),
    )
    explanation = asyncio.run(service.explain(user_id=1, context=quiz_context()))
    bundle = asyncio.run(service.variations(user_id=1, context=quiz_context()))

    assert explanation.diagnosis
    assert len(bundle.questions) >= 2


@pytest.mark.parametrize("count,expected", [(1, 2), (2, 2), (5, 3)])
def test_variations_clamps_count(count: int, expected: int):
    service = WrongQuestionTutorService(course_service=None, llm=None)
    bundle = asyncio.run(service.variations(user_id=1, context=quiz_context(), count=count))
    assert len(bundle.questions) == expected


# ---------------------------------------------------------------- API smoke
def test_wrong_question_tutor_api_end_to_end(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.db import Base, create_engine_for_url, create_session_factory
    from app.main import create_app

    def fake_semantic_search(self, user_id, course_id, query):  # noqa: ARG001
        return [
            {
                "chunk_id": 3,
                "source_locator": "chapter-01.md#1.2",
                "content": "教材说明：变量名只能由字母、数字与下划线组成，且首字符不能是数字。",
                "distance": 0.11,
            }
        ]

    monkeypatch.setattr(CourseService, "semantic_search", fake_semantic_search)

    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'wq-tutor.db'}")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(create_app(session_factory=session_factory))

    auth = client.post(
        "/api/auth/register",
        json={"username": "wqtutor", "email": "wq@example.com", "password": "secret123"},
    )
    assert auth.status_code == 200
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    course = client.post(
        "/api/courses",
        headers=headers,
        json={"name": "Python 程序设计", "major": "计算机", "level": "大二", "description": "冒烟"},
    )
    assert course.status_code == 200
    course_id = course.json()["id"]

    # 注入一条课程原文 chunk，保证向量命中可回表
    from app.models.course import CourseMaterial, KnowledgeChunk

    with session_factory() as db:
        material = CourseMaterial(
            course_id=course_id,
            user_id=1,
            filename="chapter-01.md",
            file_type="md",
            storage_path="data/courses/1/chapter-01.md",
            size_bytes=1024,
            parse_status="parsed",
            parse_error="",
            ocr_used=False,
        )
        db.add(material)
        db.flush()
        db.add(
            KnowledgeChunk(
                id=3,
                course_id=course_id,
                material_id=material.id,
                chunk_index=3,
                source_locator="chapter-01.md#1.2",
                heading="变量与标识符",
                content="教材说明：变量名只能由字母、数字与下划线组成，且首字符不能是数字。",
                token_count=32,
                embedding_id="emb-3",
            )
        )
        db.commit()

    context_payload = {
        "course_id": course_id,
        "node_id": "node-1-2",
        "topic": "变量与标识符",
        "question_type": "quiz",
        "prompt": "下列哪个变量名在 Python 中是不合法的？",
        "options": ["_my_var", "2nd_value", "userName", "PI"],
        "selected_answer": "A",
        "correct_answer": "B",
        "code": "",
        "actual_output": "",
        "expected_output": "",
        "attempts": 1,
    }

    explain = client.post("/api/wrong-questions/explain", headers=headers, json=context_payload)
    assert explain.status_code == 200
    explanation = explain.json()
    assert explanation["diagnosis"]
    assert explanation["explanation"]
    assert explanation["verification_report"]["evidence_count"] >= 1
    assert explanation["evidence_chunks"][0]["chunk_id"] == 3

    variations = client.post("/api/wrong-questions/variations", headers=headers, json=context_payload)
    assert variations.status_code == 200
    bundle = variations.json()
    assert len(bundle["questions"]) >= 2
    quiz_question = next(q for q in bundle["questions"] if q["question_type"] == "quiz")

    answer = client.post(
        "/api/wrong-questions/interactive-answer",
        headers=headers,
        json={
            "course_id": course_id,
            "node_id": "node-1-2",
            "topic": "变量与标识符",
            "question": quiz_question,
            "student_answer_index": quiz_question["correct_answer_index"],
            "student_answer_text": "",
        },
    )
    assert answer.status_code == 200
    verdict = answer.json()
    assert verdict["correct"] is True
    assert verdict["comment"]

    # 未授权访问被拒
    assert client.post("/api/wrong-questions/explain", json=context_payload).status_code == 401
    # 他人的课程不可见
    other = client.post(
        "/api/auth/register",
        json={"username": "wqtutor2", "email": "wq2@example.com", "password": "secret123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    foreign = client.post("/api/wrong-questions/explain", headers=other_headers, json=context_payload)
    assert foreign.status_code == 404
