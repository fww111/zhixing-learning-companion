from app.agents.evaluator_agent import EvaluatorAgent
from app.agents.profile_agent import ProfileAgent
from app.llm.client import LLMClient
from app.models.assessment import ComprehensiveAssessmentSubmit, LearningEvent, LearningEventType
from app.models.profile import StudentProfile


def test_evaluator_reports_mastery_and_next_adjustment():
    profile = StudentProfile.from_conversation("计算机大二，想学机器学习，梯度下降薄弱。")
    event = LearningEvent(
        student_id=profile.student_id,
        event_type=LearningEventType.EXERCISE_SUBMITTED,
        topic="梯度下降",
        score=0.3,
        detail="学习率过大判断错误",
    )

    report = EvaluatorAgent().evaluate(profile, [event])

    assert report.mastery["梯度下降"] < 0.6
    assert "复习" in report.next_adjustment


def test_low_score_assessment_can_update_profile():
    agent = ProfileAgent(LLMClient(api_key="", mock=True))
    profile = StudentProfile.from_conversation("计算机大二，想学机器学习。")
    event = LearningEvent(
        student_id=profile.student_id,
        event_type=LearningEventType.EXERCISE_SUBMITTED,
        topic="梯度下降",
        score=0.2,
        detail="梯度方向理解错误",
    )

    updated = agent.update_profile(profile, event)

    assert "梯度下降" in updated.weak_points


def test_comprehensive_assessment_scores_quiz_code_and_learning_behavior():
    payload = ComprehensiveAssessmentSubmit(
        student_id="student-xm",
        topic="Python 变量",
        course_id=1,
        knowledge_node_id="node-variable",
        classroom_completed=True,
        notes_completed=True,
        mind_map_completed=True,
        code_lab_completed=True,
        quiz_answers=[
            {"id": "concept", "dimension": "概念理解", "correct": True, "selected_answer_index": 1, "weight": 0.5},
            {"id": "transfer", "dimension": "迁移应用", "correct": False, "selected_answer_index": 0, "weight": 0.5},
        ],
        code_attempt={
            "prompt": "输出 Hello Python",
            "code": "print('Hello Python')",
            "expected_output": "Hello Python",
            "actual_output": "Hello Python",
            "passed": True,
            "attempts": 1,
        },
    )

    report = EvaluatorAgent().evaluate_comprehensive(
        StudentProfile.from_conversation("计算机大二，Python 基础一般，喜欢代码实操。"),
        payload,
    )

    assert report.dimension_scores["quiz"] == 0.5
    assert report.dimension_scores["code"] == 1.0
    assert report.dimension_scores["classroom"] == 1.0
    assert report.dimension_scores["behavior"] == 1.0
    assert report.final_score >= 0.75
    assert report.passed is True
    assert report.mastery["Python 变量"] == report.final_score


def test_comprehensive_assessment_scores_dynamic_quiz_answer_indexes():
    payload = ComprehensiveAssessmentSubmit(
        student_id="student-xm",
        topic="Python 变量",
        course_id=1,
        knowledge_node_id="node-variable",
        classroom_completed=True,
        notes_completed=True,
        mind_map_completed=True,
        code_lab_completed=True,
        quiz_answers=[
            {
                "id": "agent_question_1",
                "dimension": "概念理解",
                "prompt": "在 Python 中，下列哪个变量名是不合法的？",
                "options": ["_my_var", "2nd_value", "userName", "PI"],
                "correct_answer_index": 1,
                "selected_answer_index": 1,
                "weight": 0.5,
                "correct": False,
            },
            {
                "id": "agent_question_2",
                "dimension": "迁移应用",
                "prompt": "input() 的返回值类型是什么？",
                "options": ["int", "str", "bool"],
                "correct_answer_index": 1,
                "selected_answer_index": 0,
                "weight": 0.5,
                "correct": True,
            },
        ],
        code_attempt={
            "prompt": "输出 Hello Python",
            "code": "print('Hello Python')",
            "expected_output": "Hello Python",
            "actual_output": "Hello Python",
            "passed": True,
            "attempts": 1,
        },
    )

    report = EvaluatorAgent().evaluate_comprehensive(
        StudentProfile.from_conversation("计算机大二，Python 基础一般，喜欢代码实操。"),
        payload,
    )

    assert report.dimension_scores["quiz"] == 0.5
    assert "迁移应用" in "、".join(report.feedback)


def test_wrong_question_redo_can_update_mastery_after_correct_redo():
    payload = ComprehensiveAssessmentSubmit(
        student_id="student-xm",
        topic="Python 变量",
        course_id=1,
        knowledge_node_id="node-variable",
        classroom_completed=False,
        notes_completed=False,
        mind_map_completed=False,
        code_lab_completed=False,
        quiz_answers=[
            {
                "id": "agent_question_1",
                "dimension": "错题重做",
                "prompt": "在 Python 中，下列哪个变量名是不合法的？",
                "options": ["_my_var", "2nd_value", "userName", "PI"],
                "correct_answer_index": 1,
                "selected_answer_index": 1,
                "weight": 1,
                "correct": False,
            }
        ],
        code_attempt={
            "prompt": "错题重做",
            "code": "# quiz redo accepted",
            "expected_output": "OK",
            "actual_output": "OK",
            "passed": True,
            "attempts": 1,
        },
        detail='{"assessment_type":"wrong_question_redo","source_question_id":"12-quiz-agent_question_1"}',
    )

    report = EvaluatorAgent().evaluate_comprehensive(
        StudentProfile.from_conversation("计算机大二，Python 基础一般，喜欢代码实操。"),
        payload,
    )

    assert report.passed is True
    assert report.mastery_status in {"good", "proficient"}
    assert report.final_score >= 0.75


def test_comprehensive_assessment_requires_code_practice_for_code_topic_pass():
    payload = ComprehensiveAssessmentSubmit(
        student_id="student-xm",
        topic="Python 变量",
        course_id=1,
        knowledge_node_id="node-variable",
        classroom_completed=True,
        notes_completed=True,
        mind_map_completed=True,
        code_lab_completed=False,
        quiz_answers=[
            {"id": "concept", "dimension": "概念理解", "correct": True, "selected_answer_index": 1, "weight": 1.0},
        ],
        code_attempt={
            "prompt": "输出 Hello Python",
            "code": "print('Hello')",
            "expected_output": "Hello Python",
            "actual_output": "Hello",
            "passed": False,
            "attempts": 2,
        },
    )

    report = EvaluatorAgent().evaluate_comprehensive(
        StudentProfile.from_conversation("计算机大二，Python 基础一般，喜欢代码实操。"),
        payload,
    )

    assert report.dimension_scores["quiz"] == 1.0
    assert report.dimension_scores["code"] < 0.6
    assert report.passed is False
    assert "Python 变量" in report.weak_points
