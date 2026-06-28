from __future__ import annotations

from app.models.learning_path import LearningPath, LearningStage
from app.models.profile import StudentProfile
from app.models.resource import Resource, ResourceType


class PathAgent:
    name = "路径规划Agent"

    def plan(self, profile: StudentProfile, topic: str, resources: list[Resource]) -> LearningPath:
        by_type = {resource.type: resource for resource in resources}
        visual = [resource for resource in [by_type.get(ResourceType.MIND_MAP), by_type.get(ResourceType.DOCUMENT)] if resource]
        practice = [resource for resource in [by_type.get(ResourceType.EXERCISE), by_type.get(ResourceType.CODE_LAB)] if resource]
        extension = [
            resource
            for resource in [by_type.get(ResourceType.VIDEO), by_type.get(ResourceType.READING)]
            if resource
        ]
        stages = [
            LearningStage(
                title="阶段一：建立直观认识",
                goal=f"用图解和短文档理解{topic}的目标与流程",
                estimated_minutes=45,
                resources=visual,
                practice_task="复述参数更新流程",
                recommendation_reason=f"{topic}是画像薄弱点，先用图解降低理解门槛。",
            ),
            LearningStage(
                title="阶段二：练习与代码验证",
                goal=f"通过题目和代码掌握{topic}常见误区",
                estimated_minutes=60,
                resources=practice,
                practice_task="完成选择题并运行代码案例",
                recommendation_reason="你偏好代码实操，练习可以及时暴露学习率相关误区。",
            ),
            LearningStage(
                title="阶段三：拓展和复盘",
                goal=f"通过动画脚本和拓展阅读形成完整学习闭环",
                estimated_minutes=40,
                resources=extension,
                practice_task="写出学习率过大和过小的现象对比",
                recommendation_reason="复盘材料用于把概念、题目和代码经验连接起来。",
            ),
        ]
        return LearningPath(student_id=profile.student_id, stages=stages)
