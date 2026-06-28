from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.resource import Resource


class LearningStage(BaseModel):
    title: str
    goal: str
    estimated_minutes: int
    resources: list[Resource] = Field(default_factory=list)
    practice_task: str
    recommendation_reason: str


class LearningPath(BaseModel):
    student_id: str
    stages: list[LearningStage]


class CourseLearningStage(BaseModel):
    node_id: str
    topic: str
    level: int = 0
    order: int = 0
    mastery_status: str = "not_started"
    mastery_score: float | None = None
    priority_score: float = 0.0
    path_status: str = "open"
    is_current: bool = False
    is_locked: bool = False
    is_remedial: bool = False
    estimated_minutes: int = 30
    scheduled_day: str = ""
    scheduled_date: str = ""
    scheduled_minutes: int = 0
    schedule_label: str = ""
    is_today_task: bool = False
    task_type: str = "stretch"
    is_minimum_task: bool = False
    is_stretch_task: bool = True
    goal: str
    practice_task: str
    graph_basis: list[str] = Field(default_factory=list)
    profile_basis: list[str] = Field(default_factory=list)
    recommended_resource_types: list[str] = Field(default_factory=list)
    recommendation_reason: str


class CourseLearningPath(BaseModel):
    student_id: str
    course_id: int
    plan_type: str = "main"
    focus_node_id: str = ""
    current_stage_id: str = ""
    pass_threshold: float = 0.75
    is_dynamic: bool = True
    adjustment_basis: list[str] = Field(default_factory=list)
    weekly_time_budget_minutes: int = 0
    planned_minutes: int = 0
    minimum_task_count: int = 0
    stretch_task_count: int = 0
    schedule_days: list[str] = Field(default_factory=list)
    schedule_summary: str = ""
    active_chapter_id: str = ""
    active_chapter_title: str = ""
    chapters: list[dict[str, str | int | bool]] = Field(default_factory=list)
    stages: list[CourseLearningStage] = Field(default_factory=list)


class CourseLearningPathRequest(BaseModel):
    plan_type: str = "main"
    focus_node_id: str = ""
    chapter_id: str = ""
