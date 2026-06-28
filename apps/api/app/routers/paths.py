from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agents.path_agent import PathAgent
from app.models.profile import StudentProfile
from app.models.resource import Resource, ResourceType
from app.models.user import UserRead
from app.routers.auth import current_user


router = APIRouter(prefix="/api/paths", tags=["paths"])


class PathPlanRequest(BaseModel):
    conversation: str
    topic: str = "梯度下降"


@router.post("/plan")
async def plan_path(request: PathPlanRequest, user: UserRead = Depends(current_user)) -> dict:
    profile = StudentProfile.from_conversation(request.conversation)
    resources = [Resource.sample(resource_type, request.topic) for resource_type in ResourceType]
    return PathAgent().plan(profile, request.topic, resources).model_dump(mode="json")
