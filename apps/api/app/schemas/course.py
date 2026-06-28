from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    major: str = ""
    level: str = ""
    description: str = ""


class CourseRead(BaseModel):
    id: int
    user_id: int
    name: str
    major: str
    level: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MaterialRead(BaseModel):
    id: int
    course_id: int
    user_id: int
    filename: str
    file_type: str
    size_bytes: int
    parse_status: str
    parse_error: str
    ocr_used: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ChunkRead(BaseModel):
    id: int
    course_id: int
    material_id: int
    chunk_index: int
    source_locator: str
    heading: str
    content: str
    token_count: int
    embedding_id: str

    model_config = {"from_attributes": True}


class SemanticSearchResult(BaseModel):
    id: str
    chunk_id: int | None = None
    course_id: int | None = None
    source_locator: str | None = None
    content: str | None = None
    distance: float | None = None

    model_config = {"from_attributes": True}


class VectorIndexRebuildResult(BaseModel):
    course_id: int
    indexed_chunks: int


class BuiltInKnowledgeBaseApply(BaseModel):
    template: str = Field(pattern="^(python|c)$")


class KnowledgeGraphRead(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]

    model_config = {"from_attributes": True}


class LearningProfileEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    topic: str = ""
    knowledge_node_id: str = ""
    lesson_session_id: int | None = None
    detail: str = ""
    event_payload: dict[str, Any] = Field(default_factory=dict)
    evidence_strength: str | None = None
    score: float | None = None


class LearningProfileEventRead(BaseModel):
    id: int
    user_id: int
    course_id: int
    student_profile_id: int
    knowledge_node_id: str
    lesson_session_id: int | None = None
    event_type: str
    topic: str
    detail: str
    event_payload: dict[str, Any]
    evidence_strength: str
    score: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LearningProfileEventCreateResult(BaseModel):
    event: LearningProfileEventRead
    profile_update: dict[str, Any]


class ProfileUpdateLogRead(BaseModel):
    id: int
    user_id: int
    course_id: int
    student_profile_id: int
    source_event_id: int
    changed_dimensions: list[str]
    before_snapshot: dict[str, Any]
    after_snapshot: dict[str, Any]
    update_reason: str
    confidence_delta: float
    created_at: datetime

    model_config = {"from_attributes": True}


class LearningPathRevisionRead(BaseModel):
    id: int
    user_id: int
    course_id: int
    trigger_type: str
    trigger_event_id: int | None = None
    trigger_node_id: str
    previous_plan: dict[str, Any]
    next_plan: dict[str, Any]
    change_summary: str
    created_at: datetime

    model_config = {"from_attributes": True}
