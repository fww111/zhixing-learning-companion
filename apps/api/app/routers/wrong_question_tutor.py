from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.llm.client import LLMClient
from app.models.user import UserRead
from app.routers.auth import current_user
from app.schemas.wrong_question_tutor import (
    InteractiveAnswerRequest,
    InteractiveAnswerVerdict,
    VariationBundle,
    WrongQuestionContext,
    WrongQuestionExplanation,
)
from app.services.course_service import CourseNotFoundError, CourseService
from app.services.wrong_question_tutor_service import WrongQuestionTutorService


router = APIRouter(prefix="/api/wrong-questions", tags=["wrong-question-tutor"])


def build_service(db: Session) -> WrongQuestionTutorService:
    llm = LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        mock=settings.mock_llm,
    )
    return WrongQuestionTutorService(CourseService(db), db=db, llm=llm)


@router.post("/explain", response_model=WrongQuestionExplanation)
async def explain_wrong_question(
    context: WrongQuestionContext,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> WrongQuestionExplanation:
    _validate_course_access(db, user.id, context.course_id)
    try:
        return await build_service(db).explain(user_id=user.id, context=context)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.post("/variations", response_model=VariationBundle)
async def generate_wrong_question_variations(
    context: WrongQuestionContext,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> VariationBundle:
    _validate_course_access(db, user.id, context.course_id)
    try:
        return await build_service(db).variations(user_id=user.id, context=context)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.post("/interactive-answer", response_model=InteractiveAnswerVerdict)
async def answer_variation_question(
    request: InteractiveAnswerRequest,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> InteractiveAnswerVerdict:
    _validate_course_access(db, user.id, request.course_id)
    try:
        return await build_service(db).answer(user_id=user.id, request=request)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


def _validate_course_access(db: Session, user_id: int, course_id: int) -> None:
    try:
        CourseService(db).get_course(user_id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
