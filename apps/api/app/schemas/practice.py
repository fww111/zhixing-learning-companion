"""随堂实战练习请求/响应模型（创新功能）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PracticeGenerateRequest(BaseModel):
    course_id: int
    node_id: str = ""
    topic: str = ""
    difficulty: str = ""  # 入门 / 进阶 / 挑战，空则 Agent 自定


class PracticeVisualization(BaseModel):
    type: str = "array"
    steps: list[dict[str, Any]] = Field(default_factory=list)


class PracticeExercise(BaseModel):
    id: str
    title: str
    description: str
    starter_code: str
    stdin_text: str = ""
    expected_output: str
    hints: list[str] = Field(default_factory=list)
    solution: str = ""
    visualization: PracticeVisualization = Field(default_factory=PracticeVisualization)
    difficulty: str = "入门"
    knowledge_point: str = ""
    verified: bool = False
    verify_message: str = ""
    evidence_chunks: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "llm"  # llm | fallback


class PracticeGenerateResult(BaseModel):
    course_id: int
    topic: str
    exercise: PracticeExercise
