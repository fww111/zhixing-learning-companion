from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, create_engine_for_url, create_session_factory
from app.main import create_app
from app.models.course import Course, KnowledgeNodeMastery
from app.models.profile import StudentProfile
from app.models.profile_record import (
    LearningPathRevision,
    LearningProfileEvent,
    ProfileUpdateLog,
    StudentProfileRecord,
)


def make_client(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'dynamic-profile.db'}"
    engine = create_engine_for_url(database_url)
    testing_session_local = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    app = create_app(session_factory=testing_session_local)
    app.state.testing_session_factory = testing_session_local
    return TestClient(app)


def register(client: TestClient, username: str = "dynamic-profile-user") -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "secret123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def add_confirmed_profile(db, *, user_id: int, course_id: int, student_id: str, goal: str) -> None:
    profile = StudentProfile(
        student_id=student_id,
        major="Computer Science",
        grade="Sophomore",
        learning_goal=goal,
        knowledge_foundation="basic syntax is familiar, applied problem solving is weak",
        learning_style="example first, practice second",
        cognitive_style="understand the whole idea before coding details",
        weak_points=["functions"],
        time_preference="daily 1 hour",
        resource_preference=["document", "code_lab"],
        motivation="finish the course project",
        constraints=["limited evening focus"],
        assessment_preference="quiz and code task",
        knowledge_graph_focus=["functions"],
    ).with_completion_score()
    db.add(
        StudentProfileRecord(
            user_id=user_id,
            course_id=course_id,
            student_id=student_id,
            profile_data=profile.model_dump(mode="json"),
        )
    )


def test_failed_comprehensive_assessment_updates_only_current_course_profile_and_records_trace(tmp_path):
    client = make_client(tmp_path)
    token = register(client)
    with client.app.state.testing_session_factory() as db:
        db.add_all(
            [
                Course(id=1, user_id=1, name="Python Programming", status="ready"),
                Course(id=2, user_id=1, name="C Programming", status="ready"),
            ]
        )
        add_confirmed_profile(db, user_id=1, course_id=1, student_id="student-python", goal="master Python")
        add_confirmed_profile(db, user_id=1, course_id=2, student_id="student-c", goal="master C")
        db.commit()

    response = client.post(
        "/api/assessments/submit",
        headers=auth_headers(token),
        json={
            "student_id": "student-python",
            "topic": "loop boundary control",
            "course_id": 1,
            "knowledge_node_id": "py-loop-boundary",
            "classroom_completed": False,
            "notes_completed": False,
            "mind_map_completed": False,
            "code_lab_completed": False,
            "quiz_answers": [
                {"id": "concept", "dimension": "concept", "correct": False, "weight": 0.5},
                {"id": "transfer", "dimension": "transfer", "correct": False, "weight": 0.5},
            ],
            "code_attempt": {
                "prompt": "print numbers 1 to 3",
                "code": "for i in range(3): print(i)",
                "expected_output": "1\n2\n3",
                "actual_output": "0\n1\n2",
                "passed": False,
                "attempts": 3,
            },
            "detail": "student missed loop boundary and output range",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is False
    assert payload["profile_update"]["replan_required"] is True
    assert payload["profile_update"]["course_id"] == 1

    with client.app.state.testing_session_factory() as db:
        events = list(db.scalars(select(LearningProfileEvent)))
        logs = list(db.scalars(select(ProfileUpdateLog)))
        revisions = list(db.scalars(select(LearningPathRevision)))
        python_profile = db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == 1,
                StudentProfileRecord.course_id == 1,
            )
        )
        c_profile = db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == 1,
                StudentProfileRecord.course_id == 2,
            )
        )
        mastery = db.scalar(
            select(KnowledgeNodeMastery).where(
                KnowledgeNodeMastery.user_id == 1,
                KnowledgeNodeMastery.course_id == 1,
                KnowledgeNodeMastery.node_id == "py-loop-boundary",
            )
        )

    assert len(events) == 1
    assert events[0].event_type == "assessment_submitted"
    assert events[0].course_id == 1
    assert events[0].knowledge_node_id == "py-loop-boundary"
    assert events[0].evidence_strength == "strong"

    assert len(logs) == 1
    assert "weak_points" in logs[0].changed_dimensions
    assert "last_profile_update_reason" in logs[0].changed_dimensions
    assert logs[0].source_event_id == events[0].id

    assert len(revisions) == 1
    assert revisions[0].trigger_type == "assessment_failed"
    assert revisions[0].trigger_node_id == "py-loop-boundary"
    assert "remedial" in revisions[0].change_summary.lower()

    assert mastery is not None
    assert mastery.mastery_status in {"severe_weak", "basic"}
    assert "loop boundary control" in python_profile.profile_data["weak_points"]
    assert python_profile.profile_data["profile_version"] >= 2
    assert python_profile.profile_data["last_event_id"] == events[0].id
    assert python_profile.profile_data["profile_summary"]
    assert python_profile.profile_data["code_performance"]["attempts"] == 3

    assert "loop boundary control" not in c_profile.profile_data["weak_points"]
    assert c_profile.profile_data.get("last_event_id") is None


def test_course_profile_event_endpoint_records_event_and_updates_modality_effectiveness(tmp_path):
    client = make_client(tmp_path)
    token = register(client, "dynamic-profile-event-user")
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python Programming", status="ready"))
        add_confirmed_profile(db, user_id=1, course_id=1, student_id="student-python", goal="master Python")
        db.commit()

    created = client.post(
        "/api/courses/1/profile-events",
        headers=auth_headers(token),
        json={
            "event_type": "mind_map_interacted",
            "knowledge_node_id": "py-function-map",
            "topic": "function call flow",
            "detail": "student expanded all mind map branches and then passed the short quiz",
            "event_payload": {"resource_type": "mind_map", "duration_seconds": 180, "score": 0.9},
        },
    )
    listed = client.get("/api/courses/1/profile-events", headers=auth_headers(token))

    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["event"]["event_type"] == "mind_map_interacted"
    assert created_payload["profile_update"]["changed_dimensions"]
    assert created_payload["profile_update"]["replan_required"] is False

    assert listed.status_code == 200
    assert listed.json()[0]["event_type"] == "mind_map_interacted"

    with client.app.state.testing_session_factory() as db:
        profile = db.scalar(select(StudentProfileRecord).where(StudentProfileRecord.course_id == 1))
    modality = profile.profile_data["modality_effectiveness"]["mind_map"]
    assert modality["uses"] == 1
    assert modality["last_score"] == 0.9
    assert "mind_map" in profile.profile_data["preferred_resource_order"]


def test_profile_update_logs_and_path_revisions_are_queryable_and_course_scoped(tmp_path):
    client = make_client(tmp_path)
    token = register(client, "dynamic-profile-history-user")
    other_token = register(client, "dynamic-profile-history-other")
    with client.app.state.testing_session_factory() as db:
        db.add_all(
            [
                Course(id=1, user_id=1, name="Python Programming", status="ready"),
                Course(id=2, user_id=1, name="C Programming", status="ready"),
                Course(id=3, user_id=2, name="Python Programming", status="ready"),
            ]
        )
        add_confirmed_profile(db, user_id=1, course_id=1, student_id="student-python", goal="master Python")
        add_confirmed_profile(db, user_id=1, course_id=2, student_id="student-c", goal="master C")
        add_confirmed_profile(db, user_id=2, course_id=3, student_id="other-python", goal="learn Python")
        db.commit()

    first_event = client.post(
        "/api/courses/1/profile-events",
        headers=auth_headers(token),
        json={
            "event_type": "document_viewed",
            "knowledge_node_id": "py-function-doc",
            "topic": "function basics",
            "detail": "student opened the generated lesson document",
            "event_payload": {"resource_type": "document", "duration_seconds": 120, "score": 0.72},
        },
    )
    second_event = client.post(
        "/api/courses/1/profile-events",
        headers=auth_headers(token),
        json={
            "event_type": "assessment_submitted",
            "knowledge_node_id": "py-function-call",
            "topic": "function call flow",
            "detail": "student failed the comprehensive assessment",
            "score": 0.52,
            "event_payload": {"passed": False, "final_score": 0.52},
        },
    )
    c_event = client.post(
        "/api/courses/2/profile-events",
        headers=auth_headers(token),
        json={
            "event_type": "code_attempt_passed",
            "knowledge_node_id": "c-pointer-basic",
            "topic": "pointer basics",
            "detail": "student passed a C code lab",
            "score": 0.9,
            "event_payload": {"resource_type": "code_lab", "passed": True, "attempts": 1},
        },
    )

    assert first_event.status_code == 200
    assert second_event.status_code == 200
    assert c_event.status_code == 200

    logs = client.get("/api/courses/1/profile-update-logs", headers=auth_headers(token))
    revisions = client.get("/api/courses/1/learning-path-revisions", headers=auth_headers(token))
    c_logs = client.get("/api/courses/2/profile-update-logs", headers=auth_headers(token))
    blocked = client.get("/api/courses/1/profile-update-logs", headers=auth_headers(other_token))

    assert logs.status_code == 200
    log_payload = logs.json()
    assert [item["course_id"] for item in log_payload] == [1, 1]
    assert log_payload[0]["source_event_id"] == second_event.json()["event"]["id"]
    assert log_payload[0]["update_reason"]
    assert "last_profile_update_reason" in log_payload[0]["changed_dimensions"]
    assert "profile_summary" in log_payload[0]["after_snapshot"]

    assert revisions.status_code == 200
    revision_payload = revisions.json()
    assert len(revision_payload) == 1
    assert revision_payload[0]["course_id"] == 1
    assert revision_payload[0]["trigger_event_id"] == second_event.json()["event"]["id"]
    assert revision_payload[0]["trigger_node_id"] == "py-function-call"
    assert revision_payload[0]["next_plan"]["plan_type"] == "remedial"

    assert c_logs.status_code == 200
    assert [item["course_id"] for item in c_logs.json()] == [2]
    assert blocked.status_code == 404


def test_attention_samples_write_weak_point_evidence_when_confused_dense(tmp_path):
    """issue #15：困惑密集采样 → weak_points 证据写入画像更新日志。"""
    client = make_client(tmp_path)
    token = register(client, "attention-user")
    auth = {"Authorization": f"Bearer {token}"}
    course = client.post(
        "/api/courses",
        headers=auth,
        json={"name": "C++ 算法学习", "major": "计算机", "level": "大二", "description": "attention test"},
    )
    course_id = course.json()["id"]
    with client.app.state.testing_session_factory() as db:
        add_confirmed_profile(db, user_id=1, course_id=course_id, student_id="student-attention", goal="master C++ algorithms")
        db.commit()

    def sample(dominant: str):
        response = client.post(
            f"/api/courses/{course_id}/profile-events",
            headers=auth,
            json={
                "event_type": "attention_sample",
                "topic": "6.3 背包问题",
                "knowledge_node_id": "node-6-3",
                "detail": f"专注度采样（主导状态 {dominant}）",
                "event_payload": {"dominant": dominant, "confidence": 0.8},
                "evidence_strength": "weak",
            },
        )
        assert response.status_code == 200, response.text

    # 5 次采样中 3 次困惑（60% ≥ 40%）→ 触发薄弱点写入
    for dominant in ("confused", "confused", "focused", "confused", "focused"):
        sample(dominant)

    profile = client.get(f"/api/profiles/me?course_id={course_id}", headers=auth).json()
    assert "6.3 背包问题" in (profile.get("weak_points") or [])
    attention = profile.get("attention_pattern") or {}
    node_stats = (attention.get("confused_by_node") or {})["node-6-3"]
    assert node_stats == {"total": 5, "confused": 3}

    # 画像更新日志包含困惑证据
    logs = client.get(f"/api/courses/{course_id}/profile-update-logs", headers=auth).json()
    evidence_entries = [
        entry
        for log in logs
        for entry in (log.get("after_snapshot", {}).get("updated_evidence") or [])
        if entry.get("source") == "attention_sample" and "困惑占" in str(entry.get("detail") or "")
    ]
    assert evidence_entries, "attention confused evidence should appear in profile update logs"
    assert any("weak_points" in (log.get("changed_dimensions") or []) for log in logs), (
        "weak_points change should be logged"
    )


def test_attention_samples_do_not_write_weak_point_when_sparse(tmp_path):
    client = make_client(tmp_path)
    token = register(client, "attention-sparse-user")
    auth = {"Authorization": f"Bearer {token}"}
    course = client.post(
        "/api/courses",
        headers=auth,
        json={"name": "Python 程序设计", "major": "计算机", "level": "大二", "description": "attention sparse"},
    )
    course_id = course.json()["id"]
    with client.app.state.testing_session_factory() as db:
        add_confirmed_profile(db, user_id=1, course_id=course_id, student_id="student-attention-sparse", goal="master Python")
        db.commit()

    # 仅 2 次采样（未达 5 次门槛），即使全是困惑也不写入
    for dominant in ("confused", "confused"):
        client.post(
            f"/api/courses/{course_id}/profile-events",
            headers=auth,
            json={
                "event_type": "attention_sample",
                "topic": "1.1 变量",
                "knowledge_node_id": "node-1-1",
                "detail": "专注度采样",
                "event_payload": {"dominant": dominant},
                "evidence_strength": "weak",
            },
        )

    profile = client.get(f"/api/profiles/me?course_id={course_id}", headers=auth).json()
    assert "1.1 变量" not in (profile.get("weak_points") or [])
    node_stats = (profile.get("attention_pattern") or {}).get("confused_by_node", {})["node-1-1"]
    assert node_stats == {"total": 2, "confused": 2}
