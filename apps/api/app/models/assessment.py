from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class LearningEventType(StrEnum):
    RESOURCE_VIEWED = "resource_viewed"
    EXERCISE_SUBMITTED = "exercise_submitted"
    FEEDBACK_SUBMITTED = "feedback_submitted"
    TUTOR_QUESTION = "tutor_question"


class LearningEvent(BaseModel):
    student_id: str
    event_type: LearningEventType
    topic: str
    course_id: int | None = None
    knowledge_node_id: str = ""
    score: float | None = None
    detail: str = ""


class QuizAnswer(BaseModel):
    id: str
    dimension: str
    correct: bool
    prompt: str = ""
    options: list[str] = Field(default_factory=list)
    correct_answer_index: int | None = None
    selected_answer_index: int | None = None
    weight: float = 1.0


class CodeAttempt(BaseModel):
    prompt: str = ""
    code: str = ""
    expected_output: str = ""
    actual_output: str = ""
    passed: bool = False
    attempts: int = 1
    # 服务端沙箱判分结论（accepted/wrong_answer/compile_error/runtime_error/timeout），
    # 由 /api/courses/{id}/code/run 返回并随评估提交回传，优先于前端自报结果
    server_verdict: str | None = None


class ComprehensiveAssessmentSubmit(BaseModel):
    student_id: str
    topic: str
    course_id: int | None = None
    knowledge_node_id: str = ""
    classroom_completed: bool = False
    notes_completed: bool = False
    mind_map_completed: bool = False
    code_lab_completed: bool = False
    quiz_answers: list[QuizAnswer] = Field(default_factory=list)
    code_attempt: CodeAttempt | None = None
    detail: str = ""


class AssessmentReport(BaseModel):
    student_id: str
    mastery: dict[str, float] = Field(default_factory=dict)
    weak_points: list[str] = Field(default_factory=list)
    next_adjustment: str
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    final_score: float = 0
    passed: bool = False
    mastery_status: str = "not_started"
    feedback: list[str] = Field(default_factory=list)
