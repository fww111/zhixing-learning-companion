"""随堂实战练习路由（创新功能）：学完算法 → 按知识点出题 → 沙箱预验证 → OJ 式判分。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.llm.client import LLMClient
from app.models.user import UserRead
from app.routers.auth import current_user
from app.schemas.practice import PracticeGenerateRequest, PracticeGenerateResult
from app.services.course_service import CourseNotFoundError, CourseService
from app.services.practice_mentor_service import PracticeMentorService


router = APIRouter(prefix="/api/courses", tags=["practice"])


@router.post("/{course_id}/practice/generate", response_model=PracticeGenerateResult)
async def generate_practice(
    course_id: int,
    request: PracticeGenerateRequest,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> PracticeGenerateResult:
    """按知识点生成一道随堂实战题：LLM 出题 + 服务端沙箱预验证参考解。"""
    try:
        CourseService(db).get_course(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None

    llm = LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        mock=settings.mock_llm,
    )
    service = PracticeMentorService(CourseService(db), llm=llm)
    return await service.generate(user_id=user.id, request=request)
