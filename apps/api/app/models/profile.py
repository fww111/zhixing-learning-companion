from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field


class ProfileEvidence(BaseModel):
    source: str
    topic: str
    detail: str


class StudentProfile(BaseModel):
    student_id: str = Field(default_factory=lambda: f"student-{uuid4().hex[:8]}")
    major: str = "计算机科学与技术"
    grade: str = "大二"
    learning_goal: str = "4周内入门机器学习"
    knowledge_foundation: str = "Python基础一般，线性代数薄弱"
    learning_style: str = "偏好图解、案例和短练习"
    cognitive_style: str = "先直观理解再公式推导"
    weak_points: list[str] = Field(default_factory=lambda: ["梯度下降", "矩阵运算", "模型评估"])
    time_preference: str = "每天晚间45分钟"
    resource_preference: list[str] = Field(default_factory=lambda: ["动画", "代码实操", "短练习"])
    motivation: str = ""
    constraints: list[str] = Field(default_factory=list)
    assessment_preference: str = ""
    knowledge_graph_focus: list[str] = Field(default_factory=list)
    confidence_score: float = 0.5
    completion_score: float = 0.0
    updated_evidence: list[ProfileEvidence] = Field(default_factory=list)

    @property
    def dimension_count(self) -> int:
        return len(self._completion_dimensions())

    def _completion_dimensions(self) -> list[object]:
        normalized_assessment = self.assessment_preference or ("短练习和阶段测验" if self.resource_preference else "")
        normalized_focus = self.knowledge_graph_focus or self.weak_points[:3]
        return [
            self.major,
            self.grade,
            self.learning_goal,
            self.knowledge_foundation,
            self.learning_style,
            self.cognitive_style,
            self.weak_points,
            self.time_preference,
            self.resource_preference,
            self.motivation,
            self.constraints,
            normalized_assessment,
            normalized_focus,
        ]

    def is_complete(self) -> bool:
        return all(bool(value) for value in self._completion_dimensions())

    def with_completion_score(self) -> "StudentProfile":
        dimensions = self._completion_dimensions()
        filled = sum(1 for value in dimensions if bool(value))
        score = round(filled / len(dimensions), 2) if dimensions else 0.0
        confidence = min(0.95, max(self.confidence_score, round(0.35 + score * 0.55, 2)))
        return self.model_copy(
            update={
                "assessment_preference": self.assessment_preference or ("短练习和阶段测验" if self.resource_preference else ""),
                "knowledge_graph_focus": self.knowledge_graph_focus or self.weak_points[:3],
                "completion_score": score,
                "confidence_score": confidence,
            }
        )

    @classmethod
    def from_conversation(cls, conversation: str) -> "StudentProfile":
        weak_points = []
        for keyword in ["梯度下降", "线性代数", "矩阵运算", "模型评估", "学习率调优"]:
            if keyword in conversation:
                weak_points.append(keyword)
        if not weak_points:
            weak_points = ["梯度下降"]

        preferences = []
        for keyword in ["动画", "代码实操", "图解", "短练习", "阅读材料"]:
            if keyword in conversation:
                preferences.append(keyword)
        if "代码" in conversation and "代码实操" not in preferences:
            preferences.append("代码实操")
        if not preferences:
            preferences = ["图解", "代码实操"]

        grade = "大二" if "大二" in conversation else "本科"
        foundation = "Python基础一般，线性代数薄弱" if "一般" in conversation or "薄弱" in conversation else "具备基础编程能力"
        motivation = "希望快速建立机器学习入门能力" if "入门" in conversation else "提升课程学习效率"
        constraints = []
        if "晚" in conversation or "45分钟" in conversation:
            constraints.append("晚间学习时间有限")
        assessment_preference = "短练习和阶段测验" if "练习" in conversation else "阶段性检查"
        knowledge_graph_focus = weak_points[:2] or ["课程核心概念"]

        return cls(
            grade=grade,
            knowledge_foundation=foundation,
            weak_points=weak_points,
            resource_preference=preferences,
            motivation=motivation,
            constraints=constraints,
            assessment_preference=assessment_preference,
            knowledge_graph_focus=knowledge_graph_focus,
            updated_evidence=[
                ProfileEvidence(source="conversation", topic="画像构建", detail=conversation[:120])
            ],
        ).with_completion_score()
