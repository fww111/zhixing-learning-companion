from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import UserRead
from app.routers.auth import current_user
from app.services.course_service import CourseNotFoundError
from app.services.kb_evaluation_service import KbEvaluationError, KbEvaluationService


router = APIRouter(prefix="/api/courses/{course_id}/kb-evaluation", tags=["kb-evaluation"])


class BenchmarkGenerateRequest(BaseModel):
    size: int = Field(default=8, ge=1, le=30)


class RunCreateRequest(BaseModel):
    retriever: str = "semantic"


def service(db: Session = Depends(get_db)) -> KbEvaluationService:
    return KbEvaluationService(db)


@router.post("/benchmark")
def generate_benchmark(
    course_id: int,
    payload: BenchmarkGenerateRequest,
    user: UserRead = Depends(current_user),
    kb_service: KbEvaluationService = Depends(service),
) -> dict:
    try:
        return kb_service.generate_benchmark(user.id, course_id, size=payload.size)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    except KbEvaluationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/benchmark")
def list_benchmark(
    course_id: int,
    user: UserRead = Depends(current_user),
    kb_service: KbEvaluationService = Depends(service),
) -> list[dict]:
    try:
        return kb_service.list_benchmark(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.post("/runs")
def create_and_run_evaluation(
    course_id: int,
    payload: RunCreateRequest,
    user: UserRead = Depends(current_user),
    kb_service: KbEvaluationService = Depends(service),
) -> dict:
    """创建并立即执行一次检索评估（演示/答辩场景为同步小任务）。"""
    try:
        run = kb_service.create_run(user.id, course_id, retriever=payload.retriever)
        return kb_service.run_evaluation(user.id, run["id"])
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    except KbEvaluationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/runs")
def list_runs(
    course_id: int,
    user: UserRead = Depends(current_user),
    kb_service: KbEvaluationService = Depends(service),
) -> list[dict]:
    try:
        return kb_service.list_runs(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.get("/runs/{run_id}")
def get_run(
    course_id: int,
    run_id: int,
    error_only: bool = Query(default=False),
    user: UserRead = Depends(current_user),
    kb_service: KbEvaluationService = Depends(service),
) -> dict:
    try:
        return kb_service.get_run(user.id, run_id, error_only=error_only)
    except KbEvaluationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
