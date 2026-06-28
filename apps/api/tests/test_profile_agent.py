import asyncio

from app.agents.profile_agent import ProfileAgent
from app.llm.client import LLMClient
from app.models.assessment import LearningEvent, LearningEventType


def test_profile_agent_extracts_profile_from_conversation():
    agent = ProfileAgent(LLMClient(api_key="", mock=True))

    profile = asyncio.run(
        agent.extract_profile(
            "我是计算机专业大二学生，想4周入门机器学习。Python基础一般，线性代数和梯度下降薄弱，喜欢图解、动画和代码实操。"
        )
    )

    assert profile.dimension_count >= 8
    assert profile.learning_goal == "4周内入门机器学习"
    assert "动画" in profile.resource_preference
    assert profile.completion_score > 0
    assert profile.confidence_score > 0
    assert profile.knowledge_graph_focus


def test_student_profile_tracks_dialogue_dimensions():
    profile = ProfileAgent(LLMClient(api_key="", mock=True)).extract_profile_sync(
        "我是计算机专业大二学生，想4周入门机器学习。Python基础一般，梯度下降薄弱，喜欢图解和代码实操，每天晚上45分钟，用短练习检查效果。"
    )

    assert profile.dimension_count >= 12
    assert profile.motivation
    assert profile.constraints
    assert profile.assessment_preference
    assert "梯度下降" in profile.knowledge_graph_focus
    assert profile.completion_score >= 0.75


def test_profile_agent_updates_weak_points_from_learning_event():
    profile = ProfileAgent(LLMClient(api_key="", mock=True)).extract_profile_sync(
        "计算机大二，想学机器学习，Python一般，喜欢代码实操。"
    )
    event = LearningEvent(
        student_id=profile.student_id,
        event_type=LearningEventType.EXERCISE_SUBMITTED,
        topic="学习率调优",
        score=0.2,
        detail="答错学习率过大导致损失震荡的问题",
    )

    updated = ProfileAgent(LLMClient(api_key="", mock=True)).update_profile(profile, event)

    assert "学习率调优" in updated.weak_points
    assert updated.updated_evidence[-1].topic == "学习率调优"
