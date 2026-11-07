"""RAG 质量三件套 + 随堂实战练习测试。"""

import pytest

from app.services.rag_fusion import compress_chunk_to_relevant_sentences, rrf_fuse_hits
from app.services.rag_lexicon import expand_query_with_terms, extract_query_terms


# ------------------------------------------------------------------- RRF 融合
def test_rrf_prefers_chunks_hit_by_multiple_queries():
    hits = [
        {"query": "排序 时间复杂度", "chunk_id": 1, "_rank": 0, "distance": 0.1},
        {"query": "排序 时间复杂度", "chunk_id": 2, "_rank": 1, "distance": 0.2},
        {"query": "冒泡排序", "chunk_id": 2, "_rank": 0, "distance": 0.15},
        {"query": "快速排序", "chunk_id": 3, "_rank": 0, "distance": 0.3},
    ]
    fused = rrf_fuse_hits(hits, max_results=3)
    # chunk 2 被两路命中（rank1 + rank0）→ 融合分超过单路第一的 chunk 1
    assert fused[0]["chunk_id"] == 2
    assert len(fused[0]["hit_queries"]) == 2
    assert fused[0]["rrf_score"] > fused[1]["rrf_score"]


def test_rrf_respects_max_results_and_dedupes():
    hits = [
        {"query": "a", "chunk_id": 1, "_rank": 0},
        {"query": "a", "chunk_id": 1, "_rank": 1},  # 同路重复（正常不会出现，融合层兜底）
        {"query": "b", "chunk_id": 2, "_rank": 0},
        {"query": "c", "chunk_id": 3, "_rank": 0},
        {"query": "d", "chunk_id": 4, "_rank": 0},
    ]
    fused = rrf_fuse_hits(hits, max_results=2)
    assert len(fused) == 2
    ids = {item["chunk_id"] for item in fused}
    assert ids == {1, 2}


def test_rrf_skips_null_chunk_ids():
    hits = [{"query": "a", "chunk_id": None, "_rank": 0}, {"query": "b", "chunk_id": 5, "_rank": 0}]
    fused = rrf_fuse_hits(hits, max_results=5)
    assert [item["chunk_id"] for item in fused] == [5]


# ------------------------------------------------------------- 查询术语扩展
def test_expand_query_appends_chinese_synonyms():
    expanded = expand_query_with_terms("greedy algorithm 的特点")
    assert "贪心" in expanded
    assert "算法" in expanded
    assert expanded.startswith("greedy algorithm")


def test_expand_query_no_expansion_for_pure_chinese():
    assert expand_query_with_terms("背包问题的状态转移方程") == "背包问题的状态转移方程"


def test_extract_query_terms_filters_stopwords():
    terms = extract_query_terms("什么是贪心算法，please explain")
    assert "贪心" in terms or "贪心算法" in terms
    assert "please" not in terms
    assert "什么" not in terms


# ------------------------------------------------------------ 句级上下文压缩
def test_compress_keeps_relevant_sentences_in_order():
    content = (
        "冒泡排序是最基础的交换排序。它的核心思想是相邻元素两两比较。"
        "每一轮会把当前最大值沉到末尾。时间复杂度为 O(n²)。"
        "冒泡排序是稳定的排序算法。实际工程中更常用快速排序。"
    )
    compressed = compress_chunk_to_relevant_sentences(content, "冒泡排序 稳定", max_sentences=3)
    assert "稳定的排序算法" in compressed
    assert "冒泡排序是最基础的交换排序" in compressed
    assert len(compressed) < len(content)
    # 保持原句顺序、无双句号
    assert compressed.index("冒泡排序是最基础的交换排序") < compressed.index("稳定的排序算法")
    assert "。。" not in compressed


def test_compress_short_chunk_unchanged():
    content = "冒泡排序通过相邻交换完成排序。"
    assert compress_chunk_to_relevant_sentences(content, "冒泡排序", max_sentences=6) == content


# --------------------------------------------------------- 随堂实战练习
def _fallback_service():
    from app.services.practice_mentor_service import PracticeMentorService

    return PracticeMentorService(course_service=None, llm=None)


def test_fallback_exercise_is_verifiable_by_sandbox():
    """无 Key 降级题（冒泡排序）必须能被真实沙箱验证通过——生成质量闭环的兜底保证。"""
    import asyncio

    service = _fallback_service()
    from app.schemas.practice import PracticeGenerateRequest

    result = asyncio.run(
        service.generate(user_id=1, request=PracticeGenerateRequest(course_id=1, topic="排序"))
    )
    exercise = result.exercise
    assert exercise.source == "fallback"
    assert exercise.verified is True
    assert exercise.visualization.steps, "visualization steps should exist"


def test_llm_exercise_normalized_and_verified():
    import asyncio

    from app.schemas.practice import PracticeGenerateRequest
    from app.services.practice_mentor_service import PracticeMentorService

    solution = (
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n"
        "int main() { int a, b; cin >> a >> b; cout << a + b << endl; return 0; }"
    )
    bad_solution = solution.replace("a + b", "a - b")

    class StubLLM:
        def __init__(self, code: str) -> None:
            self.code = code

        async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            return {
                "title": "两数之和",
                "description": "输入两个整数，输出它们的和。",
                "starter_code": "#include <bits/stdc++.h>\nusing namespace std;\nint main() {\n  // TODO\n}",
                "stdin_text": "3 4",
                "expected_output": "7",
                "hints": ["读入两个数", "输出相加结果"],
                "solution": self.code,
                "visualization": {"type": "array", "steps": [{"array": [3, 4], "highlight": [0, 1], "label": "相加"}]},
                "difficulty": "入门",
                "knowledge_point": "输入输出",
            }

    # 参考解正确 → verified
    good = asyncio.run(
        PracticeMentorService(course_service=None, llm=StubLLM(solution)).generate(
            user_id=1, request=PracticeGenerateRequest(course_id=1, topic="输入输出")
        )
    )
    assert good.exercise.verified is True
    assert good.exercise.title == "两数之和"

    # 参考解错误 → unverified（质量闭环拦截坏题）
    bad = asyncio.run(
        PracticeMentorService(course_service=None, llm=StubLLM(bad_solution)).generate(
            user_id=1, request=PracticeGenerateRequest(course_id=1, topic="输入输出")
        )
    )
    assert bad.exercise.verified is False


def test_normalize_drops_incomplete_llm_output():
    from app.services.practice_mentor_service import PracticeMentorService

    service = _fallback_service()
    request = type(service).__mro__  # 占位避免未使用警告
    exercise = service._normalize(
        {"title": "只有标题", "description": "", "solution": "", "expected_output": ""},
        __import__("app.schemas.practice", fromlist=["PracticeGenerateRequest"]).PracticeGenerateRequest(course_id=1),
    )
    assert exercise is None


# ------------------------------------------------------------- API 端到端
def test_practice_api_end_to_end(tmp_path):
    from fastapi.testclient import TestClient

    from app.db import Base, create_engine_for_url, create_session_factory
    from app.main import create_app

    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'practice.db'}")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(create_app(session_factory=session_factory))

    auth = client.post(
        "/api/auth/register",
        json={"username": "practiceser", "email": "p@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    course_id = client.post("/api/courses", headers=headers, json={"name": "C++ 算法学习"}).json()["id"]

    response = client.post(
        f"/api/courses/{course_id}/practice/generate",
        headers=headers,
        json={"course_id": course_id, "topic": "排序", "difficulty": "入门"},
    )
    assert response.status_code == 200
    payload = response.json()
    exercise = payload["exercise"]
    assert exercise["title"]
    assert exercise["description"]
    assert exercise["expected_output"]
    assert exercise["visualization"]["steps"]

    # OJ 式判分：正确解 → accepted
    run = client.post(
        f"/api/courses/{course_id}/code/run",
        headers=headers,
        json={
            "source": exercise["solution"],
            "language": "cpp",
            "stdin_text": exercise["stdin_text"],
            "expected_output": exercise["expected_output"],
        },
    )
    assert run.status_code == 200
    assert run.json()["verdict"] == "accepted"

    assert client.post(f"/api/courses/{course_id}/practice/generate", json={"course_id": course_id}).status_code == 401
