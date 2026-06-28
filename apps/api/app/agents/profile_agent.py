from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm.client import LLMClient
from app.models.assessment import LearningEvent
from app.models.profile import ProfileEvidence, StudentProfile


class ProfileAgent(BaseAgent):
    name = "画像构建Agent"

    def __init__(self, llm: LLMClient) -> None:
        super().__init__(llm)

    async def extract_profile(self, conversation: str) -> StudentProfile:
        data = await self.llm.complete_json("画像抽取", conversation)
        return StudentProfile(**data).with_completion_score()

    def extract_profile_sync(self, conversation: str) -> StudentProfile:
        return StudentProfile.from_conversation(conversation)

    def update_profile(self, profile: StudentProfile, event: LearningEvent) -> StudentProfile:
        evidence = ProfileEvidence(source=event.event_type.value, topic=event.topic, detail=event.detail)
        weak_points = list(profile.weak_points)
        if event.score is not None and event.score < 0.6 and event.topic not in weak_points:
            weak_points.append(event.topic)
        return profile.model_copy(
            update={
                "weak_points": weak_points,
                "updated_evidence": [*profile.updated_evidence, evidence],
            }
        )
