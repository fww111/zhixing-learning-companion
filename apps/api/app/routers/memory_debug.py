"""记忆引擎与 AI 结对调试路由（创新功能）。

- GET  /api/courses/{course_id}/memory/review-queue：今日复习队列（间隔重复调度）
- POST /api/courses/{course_id}/debug-hint：AI 结对调试三级提示（分级解锁由前端控制）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.llm.client import LLMClient
from app.models.profile_record import LearningProfileEvent
from app.models.user import UserRead
from app.routers.auth import current_user
from app.schemas.debug_mentor import DebugHintRequest, DebugHintResponse
from app.services.course_service import CourseNotFoundError, CourseService
from app.services.debug_mentor_service import DebugMentorService
from app.services.memory_scheduler import build_memory_schedule


router = APIRouter(prefix="/api/courses", tags=["memory-debug"])


def _load_events(db: Session, user_id: int, course_id: int) -> list[dict[str, Any]]:
    events = db.scalars(
        select(LearningProfileEvent)
        .where(LearningProfileEvent.user_id == user_id, LearningProfileEvent.course_id == course_id)
        .order_by(LearningProfileEvent.created_at.asc())
    )
    return [
        {
            "event_type": event.event_type,
            "topic": event.topic,
            "knowledge_node_id": event.knowledge_node_id,
            "score": event.score,
            "created_at": event.created_at,
            "event_payload": event.event_payload or {},
        }
        for event in events
    ]


@router.get("/{course_id}/memory/review-queue")
def get_review_queue(
    course_id: int,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """记忆引擎：按艾宾浩斯间隔计算今日到期复习队列。"""
    try:
        CourseService(db).get_course(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None

    from datetime import date

    events = _load_events(db, user.id, course_id)
    schedule = build_memory_schedule(events, today=date.today().isoformat())
    return {
        "course_id": course_id,
        "algorithm": "ebbinghaus-spaced-repetition",
        "intervals_days": [1, 3, 7, 14],
        **schedule,
    }


@router.post("/{course_id}/debug-hint", response_model=DebugHintResponse)
async def debug_hint(
    course_id: int,
    request: DebugHintRequest,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> DebugHintResponse:
    """AI 结对调试：沙箱失败 → 根因诊断 + 三级递进提示（前端分级解锁）。"""
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
    service = DebugMentorService(CourseService(db), llm=llm)
    return await service.analyze(user_id=user.id, request=request)
