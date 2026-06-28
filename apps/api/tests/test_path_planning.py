from app.agents.path_agent import PathAgent
from app.models.profile import StudentProfile
from app.models.resource import Resource, ResourceType


def test_path_agent_prioritizes_visual_and_basic_resources_for_weak_foundation():
    profile = StudentProfile.from_conversation("计算机大二，Python一般，梯度下降薄弱，喜欢图解和动画。")
    resources = [
        Resource.sample(ResourceType.CODE_LAB, "梯度下降"),
        Resource.sample(ResourceType.MIND_MAP, "梯度下降"),
        Resource.sample(ResourceType.DOCUMENT, "梯度下降"),
        Resource.sample(ResourceType.EXERCISE, "梯度下降"),
    ]

    path = PathAgent().plan(profile, "梯度下降", resources)

    assert len(path.stages) >= 3
    first_types = [resource.type for resource in path.stages[0].resources]
    assert ResourceType.MIND_MAP in first_types or ResourceType.DOCUMENT in first_types
    assert "梯度下降" in path.stages[0].recommendation_reason
