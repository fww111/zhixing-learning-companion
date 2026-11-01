from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import Base, create_engine_for_url, create_session_factory
from app.models.course import Course, KnowledgeChunk
from app.models.user import User
from app.services.kb_evaluation_service import (
    ERROR_RECALL_THRESHOLD,
    KbEvaluationError,
    KbEvaluationService,
)


class FakeCourseService:
    """duck-type CourseService：可注入的检索行为。"""

    def __init__(self, db, semantic_results: dict[str, list[int]] | None = None, raise_on_search=False):
        self.db = db
        self.semantic_results = semantic_results or {}
        self.raise_on_search = raise_on_search

    def get_course(self, user_id: int, course_id: int):
        course = self.db.scalar(select(Course).where(Course.id == course_id, Course.user_id == user_id))
        if course is None:
            from app.services.course_service import CourseNotFoundError

            raise CourseNotFoundError("course not found")
        return course

    def semantic_search(self, user_id: int, course_id: int, query: str) -> list[dict]:
        if self.raise_on_search:
            raise RuntimeError("milvus down")
        order = self.semantic_results.get(query, [])
        return [{"chunk_id": chunk_id, "content": f"chunk-{chunk_id}"} for chunk_id in order]


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'kb-eval-test.db'}")
    TestingSessionLocal = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture()
def seeded(db_session):
    from app.models.course import CourseMaterial

    user = User(username="kb_eval_user", email="kb-eval@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    course = Course(user_id=user.id, name="C++算法学习", status="ready")
    db_session.add(course)
    db_session.flush()
    material = CourseMaterial(
        course_id=course.id,
        user_id=user.id,
        filename="教材.pdf",
        file_type="pdf",
        storage_path="data/uploads/教材.pdf",
        size_bytes=1024,
        parse_status="parsed",
    )
    db_session.add(material)
    db_session.flush()

    chunk_specs = [
        ("1.1 时间复杂度", "时间复杂度描述算法运行时间随输入规模增长的趋势，常用大O表示法。"),
        ("1.2 空间复杂度", "空间复杂度描述算法额外占用内存随输入规模增长的趋势。"),
        ("3.3 二分查找", "二分查找在有序序列上每次把搜索范围减半，时间复杂度 O(log n)。"),
        ("6.1 动态规划", "动态规划适用于最优子结构与重叠子问题，先定义状态再列转移方程。"),
        ("7.3 最短路", "Dijkstra 算法解决非负权图单源最短路，使用优先队列优化。"),
    ]
    chunk_ids = []
    for index, (heading, content) in enumerate(chunk_specs):
        chunk = KnowledgeChunk(
            course_id=course.id,
            material_id=material.id,
            chunk_index=index,
            source_locator=f"p{index + 1}",
            heading=heading,
            content=content,
            token_count=32,
            embedding_id="",
        )
        db_session.add(chunk)
        db_session.flush()
        chunk_ids.append(chunk.id)
    db_session.commit()
    return {"user_id": user.id, "course_id": course.id, "chunk_ids": chunk_ids}


class FakeLLM:
    """模拟 LLMClient.complete_json。"""

    def __init__(self, responses: list[dict] | None = None, fail=False):
        self.responses = responses or []
        self.calls = 0
        self.fail = fail

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        if self.fail:
            raise RuntimeError("llm down")
        return self.responses[self.calls - 1 % len(self.responses)]


def test_generate_benchmark_fallback_without_llm(seeded, db_session):
    service = KbEvaluationService(db_session, course_service=FakeCourseService(db_session), llm=None)
    result = service.generate_benchmark(seeded["user_id"], seeded["course_id"], size=3)

    assert result["generated"] == 3
    assert all(item["source"] == "fallback" for item in result["items"])
    assert all(len(item["gold_chunk_ids"]) == 1 for item in result["items"])
    assert all(item["gold_chunk_ids"][0] in seeded["chunk_ids"] for item in result["items"])
    # 干扰项不含 gold
    assert all(
        not set(item["distractor_chunk_ids"]) & set(item["gold_chunk_ids"])
        for item in result["items"]
    )


def test_generate_benchmark_requires_enough_chunks(seeded, db_session):
    from sqlalchemy import delete

    db_session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.course_id == seeded["course_id"]))
    db_session.commit()
    service = KbEvaluationService(db_session, course_service=FakeCourseService(db_session), llm=None)
    with pytest.raises(KbEvaluationError):
        service.generate_benchmark(seeded["user_id"], seeded["course_id"], size=3)


def test_run_evaluation_semantic_metrics(seeded, db_session):
    user_id, course_id = seeded["user_id"], seeded["course_id"]

    llm = FakeLLM(
        responses=[
            {"query": "评测问题一：核心概念是什么？", "gold_answer": "答案一"},
            {"query": "评测问题二：方法如何使用？", "gold_answer": "答案二"},
        ]
    )
    service = KbEvaluationService(db_session, course_service=FakeCourseService(db_session), llm=llm)
    generated = service.generate_benchmark(user_id, course_id, size=2)
    assert llm.calls == 2
    assert all(item["source"] == "llm_generated" for item in generated["items"])
    items = generated["items"]

    # 注入检索行为：第一条 gold 命中 top1，第二条 gold 排到第 3 位
    other_ids = [cid for cid in seeded["chunk_ids"] if cid not in {items[0]["gold_chunk_ids"][0], items[1]["gold_chunk_ids"][0]}]
    semantic_results = {
        items[0]["query"]: [items[0]["gold_chunk_ids"][0], *other_ids],
        items[1]["query"]: [*other_ids[:2], items[1]["gold_chunk_ids"][0], *other_ids[2:]],
    }
    evaluator = KbEvaluationService(
        db_session,
        course_service=FakeCourseService(db_session, semantic_results=semantic_results),
        llm=None,
    )
    created = evaluator.create_run(user_id, course_id, retriever="semantic")
    result = evaluator.run_evaluation(user_id, created["id"])

    assert result["status"] == "completed"
    assert result["item_count"] == 2
    details = result["details"]
    assert details[0]["metrics"]["recall@1"] == 1.0
    assert details[0]["metrics"]["recall@3"] == 1.0
    assert details[0]["is_error"] is False
    assert details[1]["metrics"]["recall@1"] == 0.0
    assert details[1]["metrics"]["recall@3"] == 1.0
    # recall@5 均达标（>= 阈值）→ 无坏例
    assert details[1]["metrics"]["recall@5"] >= ERROR_RECALL_THRESHOLD
    assert result["error_count"] == 0
    assert 0 < result["overall_metrics"]["overall_score"] <= 1


def test_run_evaluation_flags_error_cases(seeded, db_session):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    service = KbEvaluationService(db_session, course_service=FakeCourseService(db_session), llm=None)
    service.generate_benchmark(user_id, course_id, size=4)

    # 检索器永远返回不相关结果 → 全部为坏例
    evaluator = KbEvaluationService(
        db_session,
        course_service=FakeCourseService(db_session, semantic_results={}),
        llm=None,
    )
    created = evaluator.create_run(user_id, course_id, retriever="semantic")
    result = evaluator.run_evaluation(user_id, created["id"])

    assert result["error_count"] == result["item_count"] == 4
    assert result["overall_metrics"]["recall@1"] == 0.0

    run_detail = evaluator.get_run(user_id, created["id"], error_only=True)
    assert len(run_detail["details"]) == 4


def test_run_evaluation_mysql_like_retriever(seeded, db_session):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    service = KbEvaluationService(db_session, course_service=FakeCourseService(db_session), llm=None)
    service.generate_benchmark(user_id, course_id, size=1)

    # mysql_like 检索器走真实 LIKE 评分；课程只有 5 个 chunk 且 limit=10，
    # 因此 gold 必然进入 top5，recall@5 应为 1.0
    evaluator = KbEvaluationService(db_session, course_service=FakeCourseService(db_session), llm=None)
    created = evaluator.create_run(user_id, course_id, retriever="mysql_like")
    result = evaluator.run_evaluation(user_id, created["id"])
    detail = result["details"][0]

    assert detail["retrieved_chunk_ids"], "expected at least one retrieved chunk"
    assert detail["metrics"]["recall@5"] == 1.0
    assert set(detail["retrieved_chunk_ids"]) & set(
        service.list_benchmark(user_id, course_id)[0]["gold_chunk_ids"]
    )


def test_semantic_retriever_failure_marks_run_failed(seeded, db_session):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    service = KbEvaluationService(db_session, course_service=FakeCourseService(db_session), llm=None)
    service.generate_benchmark(user_id, course_id, size=2)

    evaluator = KbEvaluationService(
        db_session,
        course_service=FakeCourseService(db_session, raise_on_search=True),
        llm=None,
    )
    created = evaluator.create_run(user_id, course_id, retriever="semantic")
    with pytest.raises(KbEvaluationError):
        evaluator.run_evaluation(user_id, created["id"])

    run = evaluator.get_run(user_id, created["id"])
    assert run["status"] == "failed"
    assert run["error_message"]


def test_invalid_retriever_rejected(seeded, db_session):
    service = KbEvaluationService(db_session, course_service=FakeCourseService(db_session), llm=None)
    with pytest.raises(KbEvaluationError):
        service.create_run(seeded["user_id"], seeded["course_id"], retriever="bm25")
