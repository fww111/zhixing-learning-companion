from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import UserRead
from app.routers.auth import current_user
from app.services.code_runner import CodeRunRequest, CodeRunResult, build_default_runner
from app.services.course_service import CourseNotFoundError, CourseService
from sqlalchemy.orm import Session

from app.db import get_db


router = APIRouter(prefix="/api/courses", tags=["code-runner"])


@router.post("/{course_id}/code/run", response_model=CodeRunResult)
async def run_code(
    course_id: int,
    request: CodeRunRequest,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> CodeRunResult:
    """服务端真实沙箱：编译 + 运行 + 输出比对判分。

    编程练习、错题重做与拓展练习共用此入口，保证判分可信：
    前端无法伪造运行结果。
    """
    try:
        CourseService(db).get_course(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None

    runner = build_default_runner()
    return runner.run(request)
