from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.db import get_db
from app.llm.client import LLMClient
from app.models.resource import OpenMAICClassroom
from app.models.resource import ResourceType
from app.models.user import UserRead
from app.routers.auth import current_user
from app.services.course_service import CourseService
from app.services.resource_service import ConfirmedProfileRequiredError, LearnableKnowledgeNodeRequiredError, ResourceService
from sqlalchemy.orm import Session


router = APIRouter(prefix="/api/resources", tags=["resources"])


class GenerateRequest(BaseModel):
    conversation: str
    topic: str = "梯度下降"
    course_id: int | None = None
    node_id: str = ""
    resource_types: list[ResourceType] = []
    force_regenerate: bool = False


class LessonStateUpdateRequest(BaseModel):
    course_id: int
    node_id: str
    current_stage: str | None = None
    classroom_completed: bool | None = None
    notes_completed: bool | None = None
    mind_map_completed: bool | None = None
    code_lab_completed: bool | None = None
    test_completed: bool | None = None
    assessment_completed: bool | None = None
    score: float | None = None
    openmaic_classroom: OpenMAICClassroom | None = None


@router.post("/generate")
async def generate_resources(
    request: GenerateRequest,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    llm = LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        mock=settings.mock_llm,
    )
    try:
        return await ResourceService(llm, CourseService(db)).generate_package(
            request.conversation,
            request.topic,
            user_id=user.id,
            course_id=request.course_id,
            node_id=request.node_id,
            resource_types=request.resource_types,
            force_regenerate=request.force_regenerate,
        )
    except ConfirmedProfileRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LearnableKnowledgeNodeRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/lessons/state")
async def update_lesson_state(
    request: LessonStateUpdateRequest,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    llm = LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        mock=settings.mock_llm,
    )
    state = ResourceService(llm, CourseService(db)).update_lesson_state(
        user_id=user.id,
        course_id=request.course_id,
        node_id=request.node_id,
        current_stage=request.current_stage,
        classroom_completed=request.classroom_completed,
        notes_completed=request.notes_completed,
        mind_map_completed=request.mind_map_completed,
        code_lab_completed=request.code_lab_completed,
        test_completed=request.test_completed,
        assessment_completed=request.assessment_completed,
        score=request.score,
        openmaic_classroom=request.openmaic_classroom.model_dump(mode="json") if request.openmaic_classroom else None,
    )
    if state is None:
        raise HTTPException(status_code=404, detail="lesson state not found")
    return state


@router.get("/openmaic-jobs/{job_id}", response_model=OpenMAICClassroom)
async def poll_openmaic_job(
    job_id: str,
    poll_url: str = "",
    user: UserRead = Depends(current_user),  # noqa: ARG001
) -> OpenMAICClassroom:
    normalized_job_id = "" if job_id == "_" else job_id
    try:
        status = await ResourceService.openmaic_client_cls().poll_classroom(job_id=normalized_job_id, poll_url=poll_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenMAIC任务查询失败：{exc}") from exc
    return OpenMAICClassroom(**status)
