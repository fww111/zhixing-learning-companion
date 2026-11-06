from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.tutor import TutorEvidenceChunk


class WrongQuestionContext(BaseModel):
    """错题上下文：错题本卡片具备的全部判题信息。"""

    course_id: int
    node_id: str = ""
    topic: str = ""
    question_type: Literal["quiz", "code"] = "quiz"
    prompt: str = Field(min_length=1)
    options: list[str] = Field(default_factory=list)
    selected_answer: str = ""
    correct_answer: str = ""
    code: str = ""
    actual_output: str = ""
    expected_output: str = ""
    attempts: int = 1


class WrongQuestionExplanation(BaseModel):
    """AI 错题讲解：错因诊断 + 证据约束讲解 + 证据溯源。"""

    diagnosis: str
    explanation: str
    key_points: list[str] = Field(default_factory=list)
    evidence_chunks: list[TutorEvidenceChunk] = Field(default_factory=list)
    verification_report: dict[str, Any] = Field(default_factory=dict)


class VariationQuestion(BaseModel):
    """AI 拓展变式题：学生作答前不下发答案。"""

    id: str
    question_type: Literal["quiz", "short_answer"] = "quiz"
    prompt: str
    options: list[str] = Field(default_factory=list)
    # 选择题：正确选项下标；简答题为 None，判分走参考答案
    correct_answer_index: int | None = None
    reference_answer: str = ""
    focus: str = ""
    difficulty: Literal["基础", "进阶", "挑战"] = "基础"


class VariationBundle(BaseModel):
    """同类拓展题包：同一知识点的 N 道变式。"""

    node_id: str = ""
    topic: str = ""
    source_question_type: Literal["quiz", "code"] = "quiz"
    questions: list[VariationQuestion] = Field(default_factory=list)
    evidence_chunks: list[TutorEvidenceChunk] = Field(default_factory=list)


class InteractiveAnswerRequest(BaseModel):
    """AI 问、学生答：提交一道变式题的作答。"""

    course_id: int
    node_id: str = ""
    topic: str = ""
    question: VariationQuestion
    student_answer_index: int | None = None
    student_answer_text: str = ""


class InteractiveAnswerVerdict(BaseModel):
    """AI 即时判分点评。"""

    correct: bool
    score: int = Field(ge=0, le=100)
    comment: str
    reference_answer: str = ""
    focus: str = ""
