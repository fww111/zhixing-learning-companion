import json
from datetime import datetime

import pytest
from sqlalchemy import select


# ------------------------------------------------------------- memory scheduler
def _event(event_type: str, node_id: str, *, created_at: str, score=None, payload=None, topic="背包问题"):
    return {
        "event_type": event_type,
        "topic": topic,
        "knowledge_node_id": node_id,
        "score": score,
        "created_at": created_at,
        "event_payload": payload or {},
    }


def test_memory_schedule_resets_on_failure_and_advances_on_review_pass():
    from app.services.memory_scheduler import build_memory_schedule

    events = [
        _event("assessment_submitted", "n1", created_at="2026-11-01T10:00:00", score=0.4),
        # 1 天后复习通过 → 阶梯 1（3 天）
        _event("review_completed", "n1", created_at="2026-11-02T10:00:00", payload={"passed": True, "final_score": 0.9}),
    ]
    schedule = build_memory_schedule(events, today="2026-11-04")
    item = schedule["items"][0]
    assert item["level"] == 1
    assert item["interval_days"] == 3
    assert item["next_review_date"] == "2026-11-05"
    # 11-04 还没到到期日 11-05
    assert item["due_today"] is False

    schedule_later = build_memory_schedule(events, today="2026-11-05")
    assert schedule_later["items"][0]["due_today"] is True


def test_memory_schedule_failure_resets_level_and_counts_risk():
    from app.services.memory_scheduler import build_memory_schedule

    events = [
        _event("assessment_submitted", "n1", created_at="2026-11-01T10:00:00", score=0.4),
        _event("review_completed", "n1", created_at="2026-11-02T10:00:00", payload={"passed": True, "final_score": 0.9}),
        _event("review_completed", "n1", created_at="2026-11-05T10:00:00", payload={"passed": False, "final_score": 0.5}),
    ]
    schedule = build_memory_schedule(events, today="2026-11-06")
    item = schedule["items"][0]
    assert item["level"] == 0
    assert item["interval_days"] == 1
    # 评估失败 + 复习未通过 = 2 次记忆负债信号
    assert item["failure_count"] == 2
    assert item["high_risk"] is False

    # 连续 3 次失败 → 高危
    events.append(_event("code_attempt_run", "n1", created_at="2026-11-06T11:00:00", payload={"passed": False}))
    events.append(_event("code_attempt_run", "n1", created_at="2026-11-06T12:00:00", payload={"passed": False}))
    schedule = build_memory_schedule(events, today="2026-11-07")
    assert schedule["items"][0]["high_risk"] is True
    assert schedule["stats"]["high_risk_count"] == 1


def test_memory_schedule_multiple_nodes_sorted_by_overdue():
    from app.services.memory_scheduler import build_memory_schedule

    events = [
        _event("assessment_submitted", "n-old", created_at="2026-11-01T10:00:00", score=0.4, topic="指针"),
        _event("assessment_submitted", "n-new", created_at="2026-11-06T10:00:00", score=0.4, topic="递归"),
    ]
    schedule = build_memory_schedule(events, today="2026-11-08")
    items = schedule["items"]
    assert items[0]["node_id"] == "n-old"  # 欠账更多排前
    assert schedule["stats"]["due_count"] == 2
    assert schedule["stats"]["tracked_nodes"] == 2


def test_memory_schedule_empty():
    from app.services.memory_scheduler import build_memory_schedule

    schedule = build_memory_schedule([], today="2026-11-08")
    assert schedule["items"] == []
    assert schedule["stats"]["due_count"] == 0


# ------------------------------------------------------------- debug mentor
def test_debug_mentor_fallback_diagnoses_compile_error():
    import asyncio

    from app.schemas.debug_mentor import DebugHintRequest
    from app.services.debug_mentor_service import DebugMentorService

    service = DebugMentorService(course_service=None, llm=None)
    request = DebugHintRequest(
        course_id=1,
        topic="指针",
        source_code="int main() { int x = 5 int y = 6; }",
        error_output="error: expected ';' before 'y'",
        verdict="compile_error",
    )
    response = asyncio.run(service.analyze(user_id=1, request=request))
    assert response.error_category == "syntax"
    assert len(response.hints) == 3
    assert response.hints[0].startswith("Level 1")
    assert response.hints[1].startswith("Level 2")
    assert response.hints[2].startswith("Level 3")
    assert response.verification["decision"] == "fallback"


def test_debug_mentor_fallback_diagnoses_wrong_answer():
    import asyncio

    from app.schemas.debug_mentor import DebugHintRequest
    from app.services.debug_mentor_service import DebugMentorService

    service = DebugMentorService(course_service=None, llm=None)
    request = DebugHintRequest(
        course_id=1,
        topic="循环",
        source_code="print(total)",
        error_output="",
        verdict="wrong_answer",
        expected_output="15",
        actual_output="10",
    )
    response = asyncio.run(service.analyze(user_id=1, request=request))
    assert response.error_category == "output"
    assert "逐字符对比" in response.diagnosis


def test_debug_mentor_uses_llm_payload_when_available():
    import asyncio

    from app.schemas.debug_mentor import DebugHintRequest
    from app.services.debug_mentor_service import DebugMentorService

    class StubLLM:
        async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            return {
                "diagnosis": "循环边界写到了 size。",
                "hints": ["看循环条件", "用 i < size", "改为 i < 3"],
                "fixed_code": "for (int i = 0; i < 3; i++)",
                "key_concept": "数组边界",
            }

    service = DebugMentorService(course_service=None, llm=StubLLM())
    request = DebugHintRequest(
        course_id=1,
        node_id="n1",
        topic="数组",
        source_code="for (int i = 0; i <= 3; i++) {}",
        error_output="",
        verdict="runtime_error",
    )
    response = asyncio.run(service.analyze(user_id=1, request=request))
    assert response.diagnosis == "循环边界写到了 size。"
    assert response.hints == ["看循环条件", "用 i < size", "改为 i < 3"]
    assert response.fixed_code == "for (int i = 0; i < 3; i++)"
    assert response.key_concept == "数组边界"


# ------------------------------------------------------------------- API smoke
def test_memory_and_debug_api_end_to_end(tmp_path):
    from fastapi.testclient import TestClient

    from app.db import Base, create_engine_for_url, create_session_factory
    from app.main import create_app

    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'memory-debug.db'}")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(create_app(session_factory=session_factory))

    auth = client.post(
        "/api/auth/register",
        json={"username": "memuser", "email": "mem@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    course_id = client.post(
        "/api/courses", headers=headers, json={"name": "C++ 算法学习"}
    ).json()["id"]

    # 建 confirmed profile（事件外键依赖）+ 三天前的失败评估事件
    from app.models.profile import StudentProfile
    from app.models.profile_record import LearningProfileEvent, StudentProfileRecord

    with session_factory() as db:
        profile = StudentProfile(
            student_id="student-mem",
            major="Computer Science",
            grade="Sophomore",
            learning_goal="master C++ algorithms",
            knowledge_foundation="basic",
            learning_style="code first",
            cognitive_style="example driven",
            weak_points=["functions"],
            time_preference="daily 1 hour",
            resource_preference=["code_lab"],
            motivation="course project",
            constraints=["evenings only"],
            assessment_preference="quiz",
            knowledge_graph_focus=["functions"],
        ).with_completion_score()
        db.add(
            StudentProfileRecord(
                user_id=1,
                course_id=course_id,
                student_id="student-mem",
                profile_data=profile.model_dump(mode="json"),
            )
        )
        db.flush()
        profile_record_id = db.scalar(select(StudentProfileRecord.id).limit(1))
        db.add(
            LearningProfileEvent(
                user_id=1,
                course_id=course_id,
                student_profile_id=profile_record_id,
                knowledge_node_id="node-6-3",
                event_type="assessment_submitted",
                topic="6.3 背包问题",
                detail="评估未通过",
                event_payload={"final_score": 0.4},
                evidence_strength="medium",
                score=0.4,
                created_at=datetime(2026, 11, 1, 10, 0, 0),
            )
        )
        db.commit()

    queue = client.get(f"/api/courses/{course_id}/memory/review-queue", headers=headers)
    assert queue.status_code == 200
    payload = queue.json()
    assert payload["algorithm"] == "ebbinghaus-spaced-repetition"
    assert payload["stats"]["due_count"] == 1
    assert payload["items"][0]["node_id"] == "node-6-3"
    assert payload["items"][0]["due_today"] is True

    hint = client.post(
        f"/api/courses/{course_id}/debug-hint",
        headers=headers,
        json={
            "course_id": course_id,
            "node_id": "node-6-3",
            "topic": "背包问题",
            "source_code": "int main() { return 0 }",
            "error_output": "error: expected ';'",
            "verdict": "compile_error",
        },
    )
    assert hint.status_code == 200
    hint_payload = hint.json()
    assert hint_payload["error_category"] == "syntax"
    assert len(hint_payload["hints"]) == 3

    # 未授权访问被拒
    assert client.get(f"/api/courses/{course_id}/memory/review-queue").status_code == 401
