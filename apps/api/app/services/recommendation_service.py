from __future__ import annotations

from app.models.profile import StudentProfile
from app.models.resource import Resource, ResourceType


def rank_resources(profile: StudentProfile, resources: list[Resource]) -> list[Resource]:
    preferred = []
    for resource in resources:
        if "动画" in profile.resource_preference and resource.type in {ResourceType.VIDEO, ResourceType.MIND_MAP}:
            preferred.append(resource)
        elif "代码实操" in profile.resource_preference and resource.type == ResourceType.CODE_LAB:
            preferred.append(resource)
    remaining = [resource for resource in resources if resource not in preferred]
    return preferred + remaining
