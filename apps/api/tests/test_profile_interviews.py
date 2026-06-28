from fastapi.testclient import TestClient
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import Base, create_engine_for_url, create_session_factory
from app.db import get_db
from app.models.course import Course
from app.models.profile import StudentProfile
from app.main import create_app
from app.models import profile_record  # noqa: F401
from app.routers import profiles
from app.services.profile_interview_service import ProfileInterviewService


class RecordingProfileLLM:
    mock = False

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.calls.append((system_prompt, user_prompt))
        if "question" in system_prompt:
            return {"question": "你提到想四周入门机器学习，最希望先补齐数学理解还是代码实践？"}
        return {
            "profile": {
                "major": "计算机科学与技术",
                "grade": "大二",
                "learning_goal": "四周入门机器学习",
            }
        }


class FailingProfileLLM:
    mock = False

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        raise RuntimeError("deepseek unavailable")


class PartialProfileLLM:
    mock = False

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.calls.append((system_prompt, user_prompt))
        if "question" in system_prompt:
            return {"question": "请继续说明你的知识基础和薄弱点。"}
        return {
            "profile": {
                "major": "计算机科学与技术",
                "grade": "大二",
                "learning_goal": "4周内入门机器学习",
            }
        }


class EmptyProfileLLM:
    mock = False

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:  # noqa: ARG002
        if "question" in system_prompt:
            return {"question": "请继续说明你的知识基础和薄弱点。"}
        return {"profile": {}}


class RepeatingQuestionLLM:
    mock = False

    def __init__(self) -> None:
        self.merge_calls = 0

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:  # noqa: ARG002
        if "question" in system_prompt:
            return {"question": "请继续说明你的知识基础和薄弱点。"}

        self.merge_calls += 1
        if self.merge_calls == 1:
            return {
                "profile": {
                    "major": "计算机科学与技术",
                    "grade": "大二",
                    "learning_goal": "四周入门机器学习",
                }
            }
        return {
            "profile": {
                "knowledge_foundation": "Python基础一般，线性代数薄弱",
                "weak_points": ["线性代数", "梯度下降"],
                "time_preference": "每天晚间45分钟",
            }
        }


class CourseSpecificProfileLLM:
    mock = False

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:  # noqa: ARG002
        if "question" in system_prompt:
            return {"question": "请继续补充这门课的薄弱点和学习时间。"}
        is_c_course = "C 语言" in user_prompt or "C语言" in user_prompt
        return {
            "profile": {
                "major": "计算机科学与技术",
                "grade": "大二",
                "learning_goal": "掌握 C 语言程序设计" if is_c_course else "掌握 Python 程序设计",
                "knowledge_foundation": "C 语言基础一般" if is_c_course else "Python 基础一般",
                "learning_style": "先看结构图再代码调试" if is_c_course else "先图解再代码实操",
                "cognitive_style": "通过内存模型理解概念" if is_c_course else "先直观理解再代码验证",
                "weak_points": ["指针", "内存管理"] if is_c_course else ["列表", "函数"],
                "time_preference": "周末总共2小时" if is_c_course else "每天晚上1小时",
                "resource_preference": ["结构图", "代码调试", "短练习"] if is_c_course else ["图解", "视频", "代码实操", "短练习"],
                "motivation": "通过 C 语言课程考试" if is_c_course else "完成 Python 课程项目",
                "constraints": ["周末集中学习"] if is_c_course else ["晚间碎片时间学习"],
                "assessment_preference": "课堂测验和编程题",
                "knowledge_graph_focus": ["指针", "数组", "函数"] if is_c_course else ["基础语法", "函数", "项目实践"],
            }
        }


class StructuredCProfileLLM:
    mock = False

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:  # noqa: ARG002
        if "question" in system_prompt:
            return {
                "question": {
                    "text": "你更希望用代码实操、结构图还是短练习来学习指针和数组？",
                    "dimension": "resource_preference",
                }
            }
        return {
            "profile": {
                "major": {"value": "计算机科学与技术", "confidence": 0.91},
                "grade": {"value": "大三"},
                "learning_goal": {"summary": "系统学习 C 语言程序设计"},
                "knowledge_foundation": {
                    "summary": "需要围绕 C 语言程序设计建立知识基础",
                    "evidence": ["之前没有接触过 C 语言编程"],
                },
                "weak_points": [
                    {"name": "指针", "reason": "抽象"},
                    {"name": "内存管理", "reason": "容易出错"},
                ],
                "resource_preference": [
                    {"type": "图解"},
                    {"type": "代码实操"},
                ],
            }
        }


class InvalidQuestionProfileLLM:
    mock = False

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:  # noqa: ARG002
        if "question" in system_prompt:
            return {"question": {"metadata": {"dimension": "resources"}}}
        return {
            "profile": {
                "major": "计算机科学与技术",
                "grade": "大三",
                "learning_goal": "系统学习 C 语言程序设计",
                "knowledge_foundation": "需要围绕 C 语言程序设计建立知识基础",
                "weak_points": ["指针", "内存管理"],
            }
        }


class CompleteOnFirstTurnLLM:
    mock = False

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:  # noqa: ARG002
        if "question" in system_prompt:
            return {"question": "Please add one more detail about time and resource preferences."}
        return {
            "profile": {
                "major": "Computer Science",
                "grade": "Sophomore",
                "learning_goal": "Master Python programming",
                "knowledge_foundation": "Basic Python foundation",
                "learning_style": "Diagrams first, then coding practice",
                "cognitive_style": "Visual understanding before verification",
                "weak_points": ["lists", "functions"],
                "time_preference": "One hour daily",
                "resource_preference": ["diagrams", "code labs"],
                "motivation": "Finish the course project",
                "constraints": ["evening study"],
                "assessment_preference": "short quizzes and coding tasks",
                "knowledge_graph_focus": ["lists", "functions"],
            }
        }


def make_client(tmp_path, llm=None):
    database_url = f"sqlite:///{tmp_path / 'profile-interviews-test.db'}"
    engine = create_engine_for_url(database_url)
    TestingSessionLocal = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    app = create_app(session_factory=TestingSessionLocal)
    app.state.testing_session_factory = TestingSessionLocal
    if llm is not None:
        def override_profile_service(db: Session = Depends(get_db)) -> ProfileInterviewService:
            return ProfileInterviewService(db, llm)

        app.dependency_overrides[profiles.service] = override_profile_service
    return TestClient(app)


def register_user(client: TestClient, username: str, email: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "secret123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_profile_interview_requires_authentication(tmp_path):
    client = make_client(tmp_path)

    start = client.post("/api/profile-interviews")
    answer = client.post("/api/profile-interviews/1/messages", json={"answer": "我是大二学生"})
    confirm = client.post("/api/profile-interviews/1/confirm")
    profile = client.get("/api/profiles/me")

    assert start.status_code == 401
    assert answer.status_code == 401
    assert confirm.status_code == 401
    assert profile.status_code == 401


def test_user_can_complete_dialogue_profile_interview(tmp_path):
    client = make_client(tmp_path)
    token = register_user(client, "profile-user", "profile-user@example.com")

    started = client.post("/api/profile-interviews", headers=auth_headers(token))
    assert started.status_code == 200
    start_payload = started.json()
    assert start_payload["status"] == "in_progress"
    assert start_payload["current_question"]
    assert start_payload["profile"]["completion_score"] < 1

    first_answer = client.post(
        f"/api/profile-interviews/{start_payload['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我是计算机专业大二学生，想四周入门机器学习，Python基础一般。"},
    )
    assert first_answer.status_code == 200
    first_payload = first_answer.json()
    assert first_payload["turn_count"] == 1
    assert first_payload["profile"]["major"] == "计算机科学与技术"
    assert first_payload["profile"]["grade"] == "大二"
    assert first_payload["current_question"]

    second_answer = client.post(
        f"/api/profile-interviews/{start_payload['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我对线性代数和梯度下降薄弱，喜欢图解、动画和代码实操，每晚能学45分钟。"},
    )
    assert second_answer.status_code == 200
    second_payload = second_answer.json()
    assert "梯度下降" in second_payload["profile"]["weak_points"]
    assert "代码实操" in second_payload["profile"]["resource_preference"]
    assert second_payload["profile"]["completion_score"] >= first_payload["profile"]["completion_score"]

    confirmed = client.post(
        f"/api/profile-interviews/{start_payload['id']}/confirm",
        headers=auth_headers(token),
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "confirmed"
    assert confirmed_payload["profile"]["student_id"] == f"user-{confirmed_payload['user_id']}"

    my_profile = client.get("/api/profiles/me", headers=auth_headers(token))
    assert my_profile.status_code == 200
    assert my_profile.json()["student_id"] == confirmed_payload["profile"]["student_id"]


def test_course_profile_interviews_are_isolated_by_course(tmp_path):
    client = make_client(tmp_path, CourseSpecificProfileLLM())
    token = register_user(client, "course-profile-user", "course-profile-user@example.com")
    with client.app.state.testing_session_factory() as db:
        db.add_all([
            Course(id=1, user_id=1, name="Python 程序设计", status="ready"),
            Course(id=2, user_id=1, name="C语言程序设计", status="ready"),
        ])
        db.commit()

    python_started = client.post("/api/profile-interviews", headers=auth_headers(token), json={"course_id": 1})
    c_started = client.post("/api/profile-interviews", headers=auth_headers(token), json={"course_id": 2})

    assert python_started.status_code == 200
    assert c_started.status_code == 200
    assert python_started.json()["course_id"] == 1
    assert c_started.json()["course_id"] == 2

    python_answer = client.post(
        f"/api/profile-interviews/{python_started.json()['id']}/messages",
        headers=auth_headers(token),
        json={
            "answer": (
                "我是计算机专业大二学生，想掌握 Python 程序设计，Python 基础一般。"
                "列表和函数比较薄弱，喜欢图解、视频、代码实操和短练习，每天晚上能学习1小时，"
                "希望通过课堂测验和编程题检查效果，重点关注基础语法和项目实践。"
            )
        },
    )
    c_answer = client.post(
        f"/api/profile-interviews/{c_started.json()['id']}/messages",
        headers=auth_headers(token),
        json={
            "answer": (
                "我是计算机专业大二学生，想掌握 C 语言程序设计，C 语言基础一般。"
                "指针和内存管理薄弱，喜欢结构图、代码调试、案例阅读和短练习，周末总共能学习2小时，"
                "希望通过课堂测验和编程题检查效果，重点关注指针、数组和函数。"
            )
        },
    )

    assert python_answer.status_code == 200
    assert c_answer.status_code == 200

    python_confirmed = client.post(
        f"/api/profile-interviews/{python_started.json()['id']}/confirm",
        headers=auth_headers(token),
    )
    c_confirmed = client.post(
        f"/api/profile-interviews/{c_started.json()['id']}/confirm",
        headers=auth_headers(token),
    )

    assert python_confirmed.status_code == 200
    assert c_confirmed.status_code == 200
    assert python_confirmed.json()["course_id"] == 1
    assert c_confirmed.json()["course_id"] == 2
    assert "Python" in python_confirmed.json()["profile"]["learning_goal"]
    assert "C" in c_confirmed.json()["profile"]["learning_goal"]

    python_profile = client.get("/api/profiles/me", headers=auth_headers(token), params={"course_id": 1})
    c_profile = client.get("/api/profiles/me", headers=auth_headers(token), params={"course_id": 2})

    assert python_profile.status_code == 200
    assert c_profile.status_code == 200
    assert python_profile.json()["learning_goal"] != c_profile.json()["learning_goal"]
    assert "Python" in python_profile.json()["learning_goal"]
    assert "C" in c_profile.json()["learning_goal"]


def test_profile_interview_rejects_course_owned_by_another_user(tmp_path):
    client = make_client(tmp_path)
    owner_token = register_user(client, "course-owner", "course-owner@example.com")
    other_token = register_user(client, "course-other", "course-other@example.com")
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="Python 程序设计", status="ready"))
        db.commit()

    owner_started = client.post("/api/profile-interviews", headers=auth_headers(owner_token), json={"course_id": 1})
    other_started = client.post("/api/profile-interviews", headers=auth_headers(other_token), json={"course_id": 1})

    assert owner_started.status_code == 200
    assert other_started.status_code == 404
    assert other_started.json()["detail"] == "course not found"


def test_complete_interview_auto_confirms_profile_without_manual_confirm(tmp_path):
    client = make_client(tmp_path)
    token = register_user(client, "profile-auto-confirm", "profile-auto-confirm@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    first_answer = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我是计算机专业大二学生，想四周入门机器学习，Python基础一般。"},
    )
    assert first_answer.status_code == 200

    completed = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我对线性代数和梯度下降薄弱，喜欢图解、动画、视频、代码实操和短练习，每晚能学45分钟，希望用练习和测验检查效果。"},
    )

    assert completed.status_code == 200
    payload = completed.json()
    assert payload["status"] == "confirmed"
    assert payload["current_question"] == ""
    assert payload["profile"]["student_id"] == f"user-{payload['user_id']}"

    my_profile = client.get("/api/profiles/me", headers=auth_headers(token))
    assert my_profile.status_code == 200
    assert my_profile.json()["student_id"] == payload["profile"]["student_id"]


def test_follow_up_question_uses_first_question_and_answer_history(tmp_path):
    llm = RecordingProfileLLM()
    client = make_client(tmp_path, llm)
    token = register_user(client, "profile-llm-user", "profile-llm-user@example.com")

    started = client.post("/api/profile-interviews", headers=auth_headers(token))
    first_question = started.json()["current_question"]
    first_answer = "我是计算机专业大二学生，想四周入门机器学习，Python基础一般。"

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": first_answer},
    )

    assert answered.status_code == 200
    assert answered.json()["current_question"] == "你提到想四周入门机器学习，最希望先补齐数学理解还是代码实践？"
    question_prompts = [user_prompt for system_prompt, user_prompt in llm.calls if "question" in system_prompt]
    assert question_prompts
    assert first_question in question_prompts[-1]
    assert first_answer in question_prompts[-1]


def test_profile_interview_does_not_fallback_to_fixed_question_when_real_llm_fails(tmp_path):
    client = make_client(tmp_path, FailingProfileLLM())
    token = register_user(client, "profile-llm-failure", "profile-llm-failure@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我是计算机大二学生，想学习 Python。"},
    )

    assert answered.status_code == 502
    assert "DeepSeek" in answered.json()["detail"]


def test_profile_interview_requires_real_llm_when_configured(tmp_path):
    class MockBecauseMissingKeyLLM:
        mock = True

    client = make_client(tmp_path, MockBecauseMissingKeyLLM())
    token = register_user(client, "profile-requires-real-llm", "profile-requires-real-llm@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    def override_profile_service(db: Session = Depends(get_db)) -> ProfileInterviewService:
        return ProfileInterviewService(db, MockBecauseMissingKeyLLM(), require_real_llm=True)

    client.app.dependency_overrides[profiles.service] = override_profile_service

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我是大二，想学python", "topic": "python"},
    )

    assert answered.status_code == 502
    assert "LLM_API_KEY" in answered.json()["detail"]


def test_follow_up_question_tracks_remaining_profile_dimensions(tmp_path):
    llm = PartialProfileLLM()
    client = make_client(tmp_path, llm)
    token = register_user(client, "profile-dimension-user", "profile-dimension-user@example.com")

    started = client.post("/api/profile-interviews", headers=auth_headers(token))
    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我是计算机专业大二学生，想四周入门机器学习。"},
    )

    assert answered.status_code == 200
    question_prompts = [user_prompt for system_prompt, user_prompt in llm.calls if "question" in system_prompt]
    assert question_prompts
    assert "knowledge_foundation" in question_prompts[-1] or "知识基础" in question_prompts[-1]


def test_real_llm_empty_profile_response_still_updates_profile_from_answer(tmp_path):
    client = make_client(tmp_path, EmptyProfileLLM())
    token = register_user(client, "profile-empty-llm", "profile-empty-llm@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我是计算机专业大二学生，想四周入门机器学习，Python基础一般。"},
    )

    assert answered.status_code == 200
    payload = answered.json()
    assert payload["profile"]["major"] == "计算机科学与技术"
    assert payload["profile"]["grade"] == "大二"
    assert payload["profile"]["learning_goal"]
    assert payload["profile"]["knowledge_foundation"]
    assert payload["profile"]["completion_score"] > started.json()["profile"]["completion_score"]


def test_profile_interview_uses_learning_topic_when_answer_is_short(tmp_path):
    client = make_client(tmp_path, EmptyProfileLLM())
    token = register_user(client, "profile-topic-context", "profile-topic-context@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "大二", "topic": "python"},
    )

    assert answered.status_code == 200
    payload = answered.json()
    assert payload["profile"]["grade"] == "大二"
    assert "Python" in payload["profile"]["learning_goal"]
    assert payload["profile"]["knowledge_foundation"]
    assert "年级" not in payload["current_question"]
    assert "目标" not in payload["current_question"]
    assert "专业" in payload["current_question"]


def test_profile_interview_extracts_lowercase_python_goal_from_answer(tmp_path):
    client = make_client(tmp_path, EmptyProfileLLM())
    token = register_user(client, "profile-python-answer", "profile-python-answer@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我是大二，想学python"},
    )

    assert answered.status_code == 200
    payload = answered.json()
    assert payload["profile"]["grade"] == "大二"
    assert "Python" in payload["profile"]["learning_goal"]
    assert payload["profile"]["knowledge_foundation"]


def test_profile_interview_focus_does_not_degrade_to_raw_answer_excerpt(tmp_path):
    client = make_client(tmp_path, EmptyProfileLLM())
    token = register_user(client, "profile-focus-safety", "profile-focus-safety@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我在这门课程里想先学好 Python 基础，后面再慢慢补齐薄弱点。"},
    )

    assert answered.status_code == 200
    assert answered.json()["profile"]["knowledge_graph_focus"] == ["课程核心概念"]


def test_profile_interview_heuristics_extract_software_engineering_background_and_time(tmp_path):
    client = make_client(tmp_path, EmptyProfileLLM())
    token = register_user(client, "profile-software-engineering", "profile-software-engineering@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我是软件工程专业大二学生，想系统学好 Python 编程基础，平时晚上和周末能学，每次大约45分钟。"},
    )

    assert answered.status_code == 200
    payload = answered.json()
    assert payload["profile"]["major"] == "软件工程"
    assert payload["profile"]["grade"] == "大二"
    assert payload["profile"]["time_preference"]
    assert "45" in payload["profile"]["time_preference"]
    assert payload["profile"]["completion_score"] > started.json()["profile"]["completion_score"]


def test_profile_interview_heuristics_extract_c_course_weak_points(tmp_path):
    client = make_client(tmp_path, EmptyProfileLLM())
    token = register_user(client, "profile-c-heuristics", "profile-c-heuristics@example.com")
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="C语言程序设计", status="ready"))
        db.commit()
    started = client.post("/api/profile-interviews", headers=auth_headers(token), json={"course_id": 1})

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={
            "answer": "我是计算机大二学生，想系统学习 C 语言程序设计，指针和数组比较薄弱，喜欢图解、代码实操和短练习，平时晚上和周末每次45分钟。",
            "topic": "C语言程序设计",
        },
    )

    assert answered.status_code == 200
    payload = answered.json()
    assert payload["profile"]["major"] == "计算机科学与技术"
    assert payload["profile"]["grade"] == "大二"
    assert payload["profile"]["learning_goal"] == "系统学习 C 语言程序设计"
    assert "C 语言" in payload["profile"]["knowledge_foundation"]
    assert {"指针", "数组"}.issubset(set(payload["profile"]["weak_points"]))
    assert payload["profile"]["knowledge_graph_focus"][:2] == ["指针", "数组"]
    assert payload["status"] == "confirmed"
    assert payload["current_question"] == ""

    my_profile = client.get("/api/profiles/me", headers=auth_headers(token), params={"course_id": 1})
    assert my_profile.status_code == 200
    assert my_profile.json()["knowledge_graph_focus"][:2] == ["指针", "数组"]


def test_profile_interview_normalizes_structured_llm_profile_fields(tmp_path):
    client = make_client(tmp_path, StructuredCProfileLLM())
    token = register_user(client, "profile-c-structured", "profile-c-structured@example.com")
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="C语言程序设计", status="ready"))
        db.commit()
    started = client.post("/api/profile-interviews", headers=auth_headers(token), json={"course_id": 1})

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={
            "answer": "大三，计算机科学，想要学习C语言，但是暂时没有接触过C语言编程。",
            "topic": "C语言程序设计",
        },
    )

    assert answered.status_code == 200
    profile = answered.json()["profile"]
    assert profile["major"] == "计算机科学与技术"
    assert profile["grade"] == "大三"
    assert profile["learning_goal"] == "系统学习 C 语言程序设计"
    assert "C 语言" in profile["knowledge_foundation"]
    assert "指针" in profile["weak_points"]
    assert "内存管理" in profile["weak_points"]
    assert "图解" in profile["resource_preference"]
    assert "代码实操" in profile["resource_preference"]
    assert isinstance(answered.json()["current_question"], str)


def test_profile_interview_falls_back_to_dimension_question_when_llm_question_invalid(tmp_path):
    client = make_client(tmp_path, InvalidQuestionProfileLLM())
    token = register_user(client, "profile-invalid-question", "profile-invalid-question@example.com")
    with client.app.state.testing_session_factory() as db:
        db.add(Course(id=1, user_id=1, name="C语言程序设计", status="ready"))
        db.commit()
    started = client.post("/api/profile-interviews", headers=auth_headers(token), json={"course_id": 1})

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={
            "answer": "大三，计算机科学，想系统学习 C 语言程序设计，指针和内存管理比较薄弱。",
            "topic": "C语言程序设计",
        },
    )

    assert answered.status_code == 200
    assert answered.json()["status"] == "in_progress"
    assert answered.json()["current_question"] == "你更偏好的学习资源是什么，例如图解、视频、代码实操、阅读材料或短练习？"


def test_complete_llm_extraction_still_requires_multiple_interview_turns(tmp_path):
    client = make_client(tmp_path, CompleteOnFirstTurnLLM())
    token = register_user(client, "profile-min-turns", "profile-min-turns@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    answered = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "I supplied all profile dimensions in one answer."},
    )

    assert answered.status_code == 200
    payload = answered.json()
    assert payload["turn_count"] == 1
    assert payload["status"] == "in_progress"
    assert payload["current_question"]
    assert payload["profile"]["completion_score"] >= 0.95


def test_repeated_llm_follow_up_question_falls_back_to_next_missing_dimension(tmp_path):
    client = make_client(tmp_path, RepeatingQuestionLLM())
    token = register_user(client, "profile-repeat-question", "profile-repeat-question@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    first_answer = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "我是计算机专业大二学生，想四周入门机器学习。"},
    )
    assert first_answer.status_code == 200
    first_question = first_answer.json()["current_question"]
    assert first_question == "请继续说明你的知识基础和薄弱点。"

    second_answer = client.post(
        f"/api/profile-interviews/{started.json()['id']}/messages",
        headers=auth_headers(token),
        json={"answer": "Python基础一般，线性代数和梯度下降薄弱，每晚能学45分钟。"},
    )

    assert second_answer.status_code == 200
    next_question = second_answer.json()["current_question"]
    assert next_question
    assert next_question != first_question
    assert any(keyword in next_question for keyword in ["资源", "图解", "视频", "代码", "练习"])


def test_high_score_profile_with_missing_dimensions_stays_in_interview_flow():
    profile = StudentProfile(
        major="计算机科学与技术",
        grade="大二",
        learning_goal="4周内入门机器学习",
        knowledge_foundation="Python基础一般，线性代数薄弱",
        learning_style="",
        cognitive_style="",
        weak_points=["梯度下降", "矩阵运算", "模型评估"],
        time_preference="每天晚间45分钟",
        resource_preference=["视频", "代码实操", "短练习"],
        motivation="围绕4周内入门机器学习建立可执行学习路径",
        constraints=["学习时间需要拆成短时段"],
        assessment_preference="短练习和阶段测验",
        knowledge_graph_focus=["梯度下降", "矩阵运算", "模型评估"],
    ).with_completion_score()

    service = ProfileInterviewService(db=None)

    assert profile.completion_score == 0.85
    assert profile.is_complete() is False
    assert service._should_auto_confirm(profile, 5) is False
    assert service._next_focus_bucket(profile)[0] == "style"


def test_profile_interview_auto_completes_by_tenth_turn(tmp_path):
    llm = PartialProfileLLM()
    client = make_client(tmp_path, llm)
    token = register_user(client, "profile-ten-turns", "profile-ten-turns@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))
    interview_id = started.json()["id"]

    payload = None
    for _ in range(10):
        response = client.post(
            f"/api/profile-interviews/{interview_id}/messages",
            headers=auth_headers(token),
            json={"answer": "继续"},
        )
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == "confirmed":
            break

    assert payload is not None
    assert payload["status"] == "confirmed"
    assert payload["current_question"] == ""
    assert payload["turn_count"] <= 10
    assert payload["profile"]["completion_score"] >= 0.95

    my_profile = client.get("/api/profiles/me", headers=auth_headers(token))
    assert my_profile.status_code == 200
    assert my_profile.json()["student_id"] == payload["profile"]["student_id"]


def test_cannot_confirm_incomplete_profile_interview(tmp_path):
    client = make_client(tmp_path)
    token = register_user(client, "profile-incomplete", "profile-incomplete@example.com")
    started = client.post("/api/profile-interviews", headers=auth_headers(token))

    confirmed = client.post(
        f"/api/profile-interviews/{started.json()['id']}/confirm",
        headers=auth_headers(token),
    )

    assert confirmed.status_code == 400
    assert "incomplete" in confirmed.json()["detail"]


def test_second_user_cannot_access_first_users_interview_or_profile(tmp_path):
    client = make_client(tmp_path)
    owner_token = register_user(client, "profile-owner", "profile-owner@example.com")
    other_token = register_user(client, "profile-other", "profile-other@example.com")

    started = client.post("/api/profile-interviews", headers=auth_headers(owner_token))
    interview_id = started.json()["id"]

    other_answer = client.post(
        f"/api/profile-interviews/{interview_id}/messages",
        headers=auth_headers(other_token),
        json={"answer": "我想查看别人的画像"},
    )
    other_confirm = client.post(
        f"/api/profile-interviews/{interview_id}/confirm",
        headers=auth_headers(other_token),
    )
    other_profile = client.get("/api/profiles/me", headers=auth_headers(other_token))

    assert other_answer.status_code == 404
    assert other_confirm.status_code == 404
    assert other_profile.status_code == 404
