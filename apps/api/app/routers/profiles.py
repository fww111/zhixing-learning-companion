from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.profile_agent import ProfileAgent
from app.core.config import settings
from app.db import get_db
from app.llm.client import LLMClient
from app.models.user import UserRead
from app.routers.auth import current_user
from app.services.profile_interview_service import (
    ProfileCourseNotFoundError,
    ProfileInterviewLLMError,
    ProfileInterviewNotFoundError,
    ProfileInterviewService,
    ProfileIncompleteError,
    ProfileNotFoundError,
)


router = APIRouter(prefix="/api", tags=["profiles"])


class ProfileChatRequest(BaseModel):
    conversation: str


class ProfileAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    topic: str = Field(default="", max_length=200)


class ProfileInterviewStartRequest(BaseModel):
    course_id: int | None = None


def service(db: Session = Depends(get_db)) -> ProfileInterviewService:
    llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model, settings.mock_llm)
    return ProfileInterviewService(db, llm, require_real_llm=not settings.mock_llm)


def interview_payload(interview) -> dict:
    return {
        "id": interview.id,
        "user_id": interview.user_id,
        "course_id": interview.course_id,
        "status": interview.status,
        "turn_count": interview.turn_count,
        "current_question": interview.current_question,
        "profile": interview.profile_data,
        "created_at": interview.created_at,
        "updated_at": interview.updated_at,
    }


@router.post("/chat/profile")
async def build_profile(request: ProfileChatRequest, user: UserRead = Depends(current_user)) -> dict:
    llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model, settings.mock_llm)
    profile = await ProfileAgent(llm).extract_profile(request.conversation)
    return profile.model_dump(mode="json")


@router.post("/profile-interviews")
def start_profile_interview(
    request: ProfileInterviewStartRequest | None = None,
    user: UserRead = Depends(current_user),
    profile_service: ProfileInterviewService = Depends(service),
) -> dict:
    try:
        return interview_payload(profile_service.start_interview(user.id, course_id=request.course_id if request else None))
    except ProfileCourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.post("/profile-interviews/{interview_id}/messages")
async def answer_profile_interview(
    interview_id: int,
    request: ProfileAnswerRequest,
    user: UserRead = Depends(current_user),
    profile_service: ProfileInterviewService = Depends(service),
) -> dict:
    try:
        return interview_payload(await profile_service.answer_interview(user.id, interview_id, request.answer, request.topic))
    except ProfileInterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile interview not found") from None
    except ProfileInterviewLLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None


@router.post("/profile-interviews/{interview_id}/confirm")
def confirm_profile_interview(
    interview_id: int,
    user: UserRead = Depends(current_user),
    profile_service: ProfileInterviewService = Depends(service),
) -> dict:
    try:
        record = profile_service.confirm_interview(user.id, interview_id)
    except ProfileInterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile interview not found") from None
    except ProfileIncompleteError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return {
        "id": record.id,
        "user_id": record.user_id,
        "course_id": record.course_id,
        "status": "confirmed",
        "profile": record.profile_data,
        "updated_at": record.updated_at,
    }


@router.get("/profiles/me")
def get_my_profile(
    course_id: int | None = None,
    user: UserRead = Depends(current_user),
    profile_service: ProfileInterviewService = Depends(service),
) -> dict:
    try:
        return profile_service.get_my_profile(user.id, course_id=course_id).profile_data
    except ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found") from None


@router.get("/profiles/{student_id}")
async def get_profile(student_id: str, user: UserRead = Depends(current_user)) -> dict:
    profile = ProfileAgent(LLMClient("", mock=True)).extract_profile_sync("计算机大二，想学机器学习。")
    return profile.model_copy(update={"student_id": student_id}).model_dump(mode="json")
