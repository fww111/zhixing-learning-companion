from app.models.assessment import LearningEvent, LearningEventType
from app.models.learning_path import LearningPath, LearningStage
from app.models.profile import StudentProfile
from app.models.resource import Resource, ResourceType


def test_student_profile_has_at_least_eight_learning_dimensions():
    profile = StudentProfile.from_conversation(
        "我是计算机大二学生，想4周入门机器学习。Python一般，线性代数和梯度下降薄弱，喜欢图解、动画和代码实操，每天晚上45分钟。"
    )

    assert profile.dimension_count >= 8
    assert profile.major == "计算机科学与技术"
    assert "梯度下降" in profile.weak_points
    assert "代码实操" in profile.resource_preference


def test_resource_type_includes_required_six_types():
    assert {
        ResourceType.DOCUMENT,
        ResourceType.MIND_MAP,
        ResourceType.EXERCISE,
        ResourceType.READING,
        ResourceType.VIDEO,
        ResourceType.CODE_LAB,
    }.issubset(set(ResourceType))


def test_learning_path_stage_contains_recommendation_reason():
    resource = Resource.sample(ResourceType.DOCUMENT, "梯度下降")
    stage = LearningStage(
        title="建立直观认识",
        goal="理解梯度下降的目标和更新过程",
        estimated_minutes=45,
        resources=[resource],
        practice_task="完成2道基础选择题",
        recommendation_reason="学生偏好图解且梯度下降为薄弱点",
    )
    path = LearningPath(student_id="student-xm", stages=[stage])

    assert path.stages[0].recommendation_reason.startswith("学生偏好")


def test_learning_event_keeps_assessment_evidence():
    event = LearningEvent(
        student_id="student-xm",
        event_type=LearningEventType.EXERCISE_SUBMITTED,
        topic="梯度下降",
        score=0.25,
        detail="学习率过大导致震荡判断错误",
    )

    assert event.score == 0.25
    assert event.topic == "梯度下降"
