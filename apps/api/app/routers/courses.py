from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.learning_path import CourseLearningPath, CourseLearningPathRequest
from app.models.user import UserRead
from app.routers.auth import current_user
from app.schemas.course import (
    BuiltInKnowledgeBaseApply,
    ChunkRead,
    CourseCreate,
    CourseRead,
    KnowledgeGraphRead,
    LearningProfileEventCreate,
    LearningProfileEventCreateResult,
    LearningProfileEventRead,
    LearningPathRevisionRead,
    MaterialRead,
    ProfileUpdateLogRead,
    SemanticSearchResult,
    VectorIndexRebuildResult,
)
from app.services.course_service import (
    CourseNotFoundError,
    CourseService,
    MaterialNotFoundError,
    UnsupportedMaterialTypeError,
)
from app.services.learning_path_service import (
    LearningPathGraphMissingError,
    LearningPathProfileMissingError,
    LearningPathService,
)
from app.services.dynamic_profile_service import (
    ConfirmedCourseProfileRequiredError,
    DynamicProfileService,
    ProfileEventInput,
)
from app.services.material_parser import MaterialParseError


router = APIRouter(prefix="/api/courses", tags=["courses"])


def service(db: Session = Depends(get_db)) -> CourseService:
    return CourseService(db)


@router.post("", response_model=CourseRead)
def create_course(
    payload: CourseCreate,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    return course_service.create_course(user.id, payload)


@router.get("", response_model=list[CourseRead])
def list_courses(
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    return course_service.list_courses(user.id)


@router.post("/default-python", response_model=CourseRead)
def ensure_default_python_course(
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    return course_service.ensure_default_python_course(user.id)


@router.post("/default-c", response_model=CourseRead)
def ensure_default_c_course(
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    return course_service.ensure_default_c_course(user.id)


@router.post("/{course_id}/builtin-knowledge-base", response_model=CourseRead)
def apply_builtin_knowledge_base(
    course_id: int,
    payload: BuiltInKnowledgeBaseApply,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        return course_service.apply_builtin_knowledge_base(user.id, course_id, payload.template)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/{course_id}", response_model=CourseRead)
def get_course(
    course_id: int,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        return course_service.get_course(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.post("/{course_id}/materials", response_model=MaterialRead)
async def upload_material(
    course_id: int,
    file: Annotated[UploadFile, File()],
    request: Request,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        material = await course_service.add_material_from_upload(user.id, course_id, file)
        request.app.state.material_task_queue.enqueue(user.id, course_id, material.id)
        return material
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    except UnsupportedMaterialTypeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except (MaterialParseError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/{course_id}/materials", response_model=list[MaterialRead])
def list_materials(
    course_id: int,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        return course_service.list_materials(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.delete("/{course_id}/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(
    course_id: int,
    material_id: int,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        course_service.delete_material(user.id, course_id, material_id)
    except (CourseNotFoundError, MaterialNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="material not found") from None


@router.get("/{course_id}/chunks", response_model=list[ChunkRead])
def list_chunks(
    course_id: int,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        return course_service.list_chunks(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.get("/{course_id}/semantic-search", response_model=list[SemanticSearchResult])
def semantic_search(
    course_id: int,
    q: str = Query(min_length=1),
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        return course_service.semantic_search(user.id, course_id, q)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.post("/{course_id}/vector-index/rebuild", response_model=VectorIndexRebuildResult)
def rebuild_vector_index(
    course_id: int,
    request: Request,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        chunks = course_service.list_chunks(user.id, course_id)
        request.app.state.material_task_queue.enqueue_vector_rebuild(user.id, course_id)
        return {"course_id": course_id, "indexed_chunks": len(chunks)}
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.post("/{course_id}/knowledge-graph/build", response_model=KnowledgeGraphRead)
async def build_knowledge_graph(
    course_id: int,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        return await course_service.build_knowledge_graph(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.get("/{course_id}/knowledge-graph", response_model=KnowledgeGraphRead)
def get_knowledge_graph(
    course_id: int,
    user: UserRead = Depends(current_user),
    course_service: CourseService = Depends(service),
):
    try:
        return course_service.get_knowledge_graph(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.post("/{course_id}/profile-events", response_model=LearningProfileEventCreateResult)
def create_learning_profile_event(
    course_id: int,
    payload: LearningProfileEventCreate,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        result = DynamicProfileService(db).record_event(
            user_id=user.id,
            course_id=course_id,
            payload=ProfileEventInput(
                event_type=payload.event_type,
                topic=payload.topic,
                knowledge_node_id=payload.knowledge_node_id,
                lesson_session_id=payload.lesson_session_id,
                detail=payload.detail,
                event_payload=payload.event_payload,
                evidence_strength=payload.evidence_strength,
                score=payload.score,
            ),
        )
        return {"event": result.event, "profile_update": result.to_payload()}
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    except ConfirmedCourseProfileRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/{course_id}/profile-events", response_model=list[LearningProfileEventRead])
def list_learning_profile_events(
    course_id: int,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        return DynamicProfileService(db).list_events(user.id, course_id)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.get("/{course_id}/profile-update-logs", response_model=list[ProfileUpdateLogRead])
def list_profile_update_logs(
    course_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        return DynamicProfileService(db).list_update_logs(user.id, course_id, limit)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.get("/{course_id}/learning-path-revisions", response_model=list[LearningPathRevisionRead])
def list_learning_path_revisions(
    course_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        return DynamicProfileService(db).list_path_revisions(user.id, course_id, limit)
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None


@router.post("/{course_id}/learning-paths/plan", response_model=CourseLearningPath)
def plan_course_learning_path(
    course_id: int,
    payload: CourseLearningPathRequest | None = None,
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        request_payload = payload or CourseLearningPathRequest()
        return LearningPathService(db).plan_course_path(
            user,
            course_id,
            plan_type=request_payload.plan_type,
            focus_node_id=request_payload.focus_node_id,
            chapter_id=request_payload.chapter_id,
        )
    except CourseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    except LearningPathProfileMissingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except LearningPathGraphMissingError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="knowledge graph is empty") from None
