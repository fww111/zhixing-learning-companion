"""Functional smoke tests for the three MCP servers (sqlite backend)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mcp_servers import assessment_server, graph_server, profile_server

USER_ID = 1
COURSE_ID = 1

GRAPH_FIXTURE: dict[str, Any] = {
    "nodes": [
        {
            "id": "py-root",
            "name": "Python程序设计",
            "node_type": "chapter",
            "difficulty": "basic",
            "summary": "课程根节点",
            "level": 0,
            "order": 0,
            "parent_id": "",
            "source_chunk_ids": [],
            "mastery_status": "not_started",
            "mastery_score": None,
        },
        {
            "id": "py-1",
            "name": "第一章 Python基础",
            "node_type": "chapter",
            "difficulty": "basic",
            "summary": "",
            "level": 1,
            "order": 1,
            "parent_id": "py-root",
            "source_chunk_ids": [],
            "mastery_status": "not_started",
            "mastery_score": None,
        },
        {
            "id": "py-1-1",
            "name": "列表基础",
            "node_type": "concept",
            "difficulty": "basic",
            "summary": "列表的定义与索引",
            "level": 2,
            "order": 1,
            "parent_id": "py-1",
            "source_chunk_ids": [1],
            "mastery_status": "not_started",
            "mastery_score": None,
        },
        {
            "id": "py-1-2",
            "name": "列表切片",
            "node_type": "concept",
            "difficulty": "basic",
            "summary": "seq[start:stop:step] 语法",
            "level": 2,
            "order": 2,
            "parent_id": "py-1",
            "source_chunk_ids": [],
            "mastery_status": "not_started",
            "mastery_score": None,
        },
        {
            "id": "py-2-1",
            "name": "for循环",
            "node_type": "method",
            "difficulty": "basic",
            "summary": "for 循环与 range",
            "level": 2,
            "order": 1,
            "parent_id": "py-root",
            "source_chunk_ids": [],
            "mastery_status": "not_started",
            "mastery_score": None,
        },
    ],
    "edges": [
        {
            "id": "e1",
            "source_node_id": "py-1-1",
            "target_node_id": "py-1-2",
            "relation_type": "prerequisite",
            "reason": "切片依赖索引",
            "confidence": 0.9,
        },
        {
            "id": "e2",
            "source_node_id": "py-1-2",
            "target_node_id": "py-2-1",
            "relation_type": "prerequisite",
            "reason": "循环遍历列表",
            "confidence": 0.85,
        },
        {
            "id": "e3",
            "source_node_id": "py-1",
            "target_node_id": "py-1-1",
            "relation_type": "contains",
            "reason": "章节包含",
            "confidence": 1.0,
        },
    ],
}


@pytest.fixture(scope="module")
def seeded():
    from app.db import SessionLocal
    from app.models.course import Course, CourseMaterial, KnowledgeChunk
    from app.models.user import User

    with SessionLocal() as db:
        user = User(
            username="mcp_tester",
            email="mcp-test@example.com",
            password_hash="not-a-real-hash",
        )
        db.add(user)
        db.flush()
        course = Course(
            user_id=user.id,
            name="Python程序设计",
            major="计算机",
            level="本科",
            status="ready",
        )
        db.add(course)
        db.flush()
        material = CourseMaterial(
            course_id=course.id,
            user_id=user.id,
            filename="python教材.pdf",
            file_type="pdf",
            storage_path="data/uploads/python教材.pdf",
            size_bytes=1024,
            parse_status="parsed",
        )
        db.add(material)
        db.flush()
        chunk = KnowledgeChunk(
            course_id=course.id,
            material_id=material.id,
            chunk_index=0,
            source_locator="p12",
            heading="1.1 列表基础",
            content="列表是 Python 中最常用的数据结构。列表切片使用 seq[start:stop:step] 语法，起始索引包含在结果中，结束索引不包含。",
            token_count=64,
            embedding_id="",
        )
        db.add(chunk)
        db.commit()
        return {"user_id": user.id, "course_id": course.id}


@pytest.fixture()
def fake_graph(monkeypatch):
    from app.services.course_service import CourseService

    def _fake(self, user_id: int, course_id: int) -> dict[str, Any]:
        return GRAPH_FIXTURE

    monkeypatch.setattr(CourseService, "get_knowledge_graph", _fake)


def test_all_tools_registered():
    expected = {
        "profile-server": {
            "get_student_profile",
            "save_student_profile",
            "append_interview_message",
            "list_interview_messages",
            "record_profile_event",
            "list_profile_events",
            "list_profile_update_logs",
            "list_path_revisions",
        },
        "graph-server": {
            "get_course_graph",
            "get_node_constraints",
            "get_knowledge_evidence",
            "search_course_chunks",
        },
        "assessment-server": {
            "submit_comprehensive_assessment",
            "submit_learning_event",
            "get_node_mastery",
            "plan_learning_path",
            "list_wrong_questions",
        },
    }
    servers = {
        "profile-server": profile_server.mcp,
        "graph-server": graph_server.mcp,
        "assessment-server": assessment_server.mcp,
    }
    for name, server in servers.items():
        tools = {tool.name for tool in asyncio.run(server.list_tools())}
        assert expected[name] <= tools, f"{name} missing tools: {expected[name] - tools}"


def test_profile_save_and_get(seeded):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    saved = profile_server.save_student_profile_impl(
        user_id=user_id,
        course_id=course_id,
        profile={
            "major": "计算机科学与技术",
            "grade": "大二",
            "learning_goal": "4周内掌握Python基础",
            "knowledge_foundation": "有C语言基础",
            "learning_style": "偏好案例",
            "cognitive_style": "先直观后推导",
            "weak_points": ["列表切片"],
            "time_preference": "每天晚间45分钟",
            "resource_preference": ["代码实操"],
        },
    )
    assert saved["ok"] is True
    assert saved["created"] is True
    assert saved["student_id"].startswith("student-")
    assert saved["completion_score"] and saved["completion_score"] > 0

    # 再次保存保持 student_id 稳定
    again = profile_server.save_student_profile_impl(
        user_id=user_id,
        course_id=course_id,
        profile={"learning_goal": "2周内掌握Python基础"},
    )
    assert again["ok"] is True
    assert again["created"] is False
    assert again["student_id"] == saved["student_id"]

    got = profile_server.get_student_profile_impl(user_id=user_id, course_id=course_id)
    assert got["ok"] is True
    assert got["exists"] is True
    assert got["profile"]["learning_goal"] == "2周内掌握Python基础"


def test_course_isolation(seeded):
    saved = profile_server.save_student_profile_impl(
        user_id=seeded["user_id"],
        course_id=99999,
        profile={"major": "机械"},
    )
    assert saved["ok"] is False
    assert saved["error_type"] == "course_not_found"


def test_interview_messages(seeded):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    first = profile_server.append_interview_message_impl(
        user_id=user_id,
        course_id=course_id,
        role="assistant",
        content="请介绍一下你的专业、年级和学习目标。",
    )
    assert first["ok"] is True
    assert first["turn_count"] == 0

    second = profile_server.append_interview_message_impl(
        user_id=user_id,
        course_id=course_id,
        role="user",
        content="计算机大二，想4周掌握Python基础。",
    )
    assert second["turn_count"] == 1
    assert [item["role"] for item in second["messages"]] == ["assistant", "user"]

    listed = profile_server.list_interview_messages_impl(user_id=user_id, course_id=course_id)
    assert listed["ok"] is True
    assert len(listed["messages"]) == 2


def test_record_profile_event(seeded):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    result = profile_server.record_profile_event_impl(
        user_id=user_id,
        course_id=course_id,
        event_type="tutor_question_asked",
        topic="列表基础",
        detail="问了切片语法",
    )
    assert result["ok"] is True
    assert result["event_id"] > 0

    events = profile_server.list_profile_events_impl(user_id=user_id, course_id=course_id)
    assert any(item["event_type"] == "tutor_question_asked" for item in events["events"])


def test_node_constraints(fake_graph, seeded):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    result = graph_server.get_node_constraints_impl(
        user_id=user_id,
        course_id=course_id,
        node_id="py-1-2",
    )
    assert result["ok"] is True
    assert result["node"]["id"] == "py-1-2"
    assert result["parent"]["id"] == "py-1"
    assert [item["id"] for item in result["prerequisites"]] == ["py-1-1"]
    assert [item["id"] for item in result["successors"]] == ["py-2-1"]
    assert result["children"] == []

    missing = graph_server.get_node_constraints_impl(
        user_id=user_id,
        course_id=course_id,
        node_id="no-such-node",
    )
    assert missing["ok"] is False
    assert missing["error_type"] == "validation_error"


def test_knowledge_evidence_uses_chunk_ids(fake_graph, seeded):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    result = graph_server.get_knowledge_evidence_impl(
        user_id=user_id,
        course_id=course_id,
        node_id="py-1-1",
    )
    assert result["ok"] is True
    assert result["evidence"]
    assert "列表切片" in result["evidence"][0]["content"]


def test_search_course_chunks(seeded):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    result = graph_server.search_course_chunks_impl(
        user_id=user_id,
        course_id=course_id,
        query="切片",
    )
    assert result["ok"] is True
    assert result["chunks"]


def test_comprehensive_assessment_closure(fake_graph, seeded):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    result = assessment_server.submit_comprehensive_assessment_impl(
        user_id=user_id,
        course_id=course_id,
        assessment={
            "topic": "列表切片",
            "knowledge_node_id": "py-1-2",
            "classroom_completed": True,
            "quiz_answers": [
                {
                    "id": "q1",
                    "dimension": "concept",
                    "correct": True,
                    "prompt": "seq[1:3] 包含索引几？",
                    "options": ["1和2", "1和3"],
                    "correct_answer_index": 0,
                    "selected_answer_index": 0,
                },
                {
                    "id": "q2",
                    "dimension": "transfer",
                    "correct": False,
                    "prompt": "seq[:2] 表示？",
                    "options": ["前两个", "后两个"],
                    "correct_answer_index": 0,
                    "selected_answer_index": 1,
                },
            ],
            "code_attempt": {
                "prompt": "输出列表前3项",
                "code": "print(nums[1:4])",
                "expected_output": "1 2 3",
                "actual_output": "2 3 4",
                "passed": False,
                "attempts": 2,
            },
        },
    )
    assert result["ok"] is True, result
    report = result["report"]
    assert report["passed"] is False
    assert report["mastery_status"] in {"severe_weak", "basic"}
    assert result["profile_update"]["event_id"] > 0

    mastery = assessment_server.get_node_mastery_impl(
        user_id=user_id,
        course_id=course_id,
        node_id="py-1-2",
    )
    assert mastery["ok"] is True
    assert mastery["masteries"][0]["mastery_score"] == report["final_score"]

    wrong = assessment_server.list_wrong_questions_impl(
        user_id=user_id,
        course_id=course_id,
    )
    assert wrong["ok"] is True
    kinds = {item["kind"] for item in wrong["wrong_questions"]}
    assert kinds == {"quiz", "code"}


def test_assessment_requires_profile(seeded):
    result = assessment_server.submit_comprehensive_assessment_impl(
        user_id=seeded["user_id"],
        course_id=99999,
        assessment={"topic": "x", "knowledge_node_id": "n"},
    )
    assert result["ok"] is False
    assert result["error_type"] == "course_not_found"


def test_plan_learning_path(fake_graph, seeded):
    user_id, course_id = seeded["user_id"], seeded["course_id"]
    result = assessment_server.plan_learning_path_impl(
        user_id=user_id,
        course_id=course_id,
        plan_type="main",
    )
    assert result["ok"] is True, result
    path = result["path"]
    assert path["plan_type"] == "main"
    assert path["stages"], "expected non-empty stages"
    topics = [stage["topic"] for stage in path["stages"]]
    assert "列表切片" in topics
