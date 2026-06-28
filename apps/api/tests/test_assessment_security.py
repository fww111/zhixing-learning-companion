from app.agents.evaluator_agent import EvaluatorAgent
from app.models.assessment import ComprehensiveAssessmentSubmit
from app.models.profile import StudentProfile


def test_comprehensive_assessment_does_not_trust_forged_client_booleans():
    payload = ComprehensiveAssessmentSubmit(
        student_id="student-xm",
        topic="Python variable",
        course_id=1,
        knowledge_node_id="node-variable",
        classroom_completed=True,
        notes_completed=True,
        mind_map_completed=True,
        code_lab_completed=True,
        quiz_answers=[
            {"id": "concept", "dimension": "concept", "correct": True, "weight": 0.35},
            {"id": "transfer", "dimension": "transfer", "correct": True, "weight": 0.3},
            {"id": "debugging", "dimension": "debugging", "correct": True, "weight": 0.35},
        ],
        code_attempt={
            "prompt": "Print Hello Python",
            "code": "print('wrong')",
            "expected_output": "Hello Python",
            "actual_output": "wrong",
            "passed": True,
            "attempts": 1,
        },
    )

    report = EvaluatorAgent().evaluate_comprehensive(
        StudentProfile.from_conversation("Computer science student learning Python with coding practice."),
        payload,
    )

    assert report.dimension_scores["quiz"] == 0.0
    assert report.dimension_scores["code"] < 0.6
    assert report.passed is False
    assert "Python variable" in report.weak_points


def test_comprehensive_assessment_ignores_forged_completion_when_lesson_state_is_missing(tmp_path):
    from fastapi.testclient import TestClient

    from app.db import Base, create_engine_for_url, create_session_factory
    from app.main import create_app
    from app.models.course import Course
    from app.models.profile_record import StudentProfileRecord

    database_url = f"sqlite:///{tmp_path / 'assessment-security.db'}"
    engine = create_engine_for_url(database_url)
    testing_session_local = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(create_app(session_factory=testing_session_local))
    auth = client.post(
        "/api/auth/register",
        json={"username": "forged-state", "email": "forged-state@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    profile = StudentProfile.from_conversation("Computer science student learning Python with coding practice.")
    with testing_session_local() as db:
        db.add(Course(id=1, user_id=1, name="Python", status="ready"))
        db.add(
            StudentProfileRecord(
                user_id=1,
                course_id=1,
                student_id=profile.student_id,
                profile_data=profile.model_dump(mode="json"),
            )
        )
        db.commit()

    response = client.post(
        "/api/assessments/submit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "student_id": "student-xm",
            "topic": "Python variable",
            "course_id": 1,
            "knowledge_node_id": "node-variable",
            "classroom_completed": True,
            "notes_completed": True,
            "mind_map_completed": True,
            "code_lab_completed": True,
            "quiz_answers": [
                {"id": "concept", "dimension": "concept", "correct": True, "selected_answer_index": 1, "weight": 0.35},
                {"id": "transfer", "dimension": "transfer", "correct": True, "selected_answer_index": 1, "weight": 0.3},
                {"id": "debugging", "dimension": "debugging", "correct": True, "selected_answer_index": 1, "weight": 0.35},
            ],
            "code_attempt": {
                "prompt": "Print Hello Python",
                "code": "print('Hello Python')",
                "expected_output": "Hello Python",
                "actual_output": "Hello Python",
                "passed": True,
                "attempts": 1,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension_scores"]["classroom"] == 0.0
    assert payload["dimension_scores"]["behavior"] == 0.0
    assert payload["passed"] is False
