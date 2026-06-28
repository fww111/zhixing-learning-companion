from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.llm.client import LLMClient
from app.models.user import UserRead
from app.routers.auth import current_user
from app.schemas.tutor import TutorChatRequest, TutorChatResponse
from app.services.course_service import CourseNotFoundError, CourseService
from app.services.tutor_service import TutorService


router = APIRouter(prefix="/api/tutor", tags=["tutor"])


@router.post("/chat", response_model=TutorChatResponse)
async def tutor_chat(
    request: TutorChatRequest,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> TutorChatResponse:
    llm = LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        mock=settings.mock_llm,
    )
    vision_llm = LLMClient(
        api_key=settings.tutor_vision_api_key,
        base_url=settings.tutor_vision_base_url,
        model=settings.tutor_vision_model,
        mock=settings.mock_llm,
    )
    try:
        return await TutorService(CourseService(db), db=db, llm=llm, vision_llm=vision_llm).chat(
            user_id=user.id,
            request=request,
        )
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
