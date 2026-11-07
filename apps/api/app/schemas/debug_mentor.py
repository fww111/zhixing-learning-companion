"""AI 结对调试请求/响应模型（issue：创新功能）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.tutor import TutorEvidenceChunk


class DebugHintRequest(BaseModel):
    course_id: int
    node_id: str = ""
    topic: str = ""
    source_code: str = Field(min_length=1, max_length=30_000)
    error_output: str = Field(default="", max_length=6_000)
    verdict: str = ""  # compile_error / runtime_error / timeout / wrong_answer
    stdin_text: str = Field(default="", max_length=2_000)
    expected_output: str = Field(default="", max_length=2_000)
    actual_output: str = Field(default="", max_length=2_000)


class DebugHintResponse(BaseModel):
    diagnosis: str
    error_category: str  # syntax / type / boundary / logic / runtime / output
    hints: list[str] = Field(min_length=1, max_length=3)  # 分级提示，逐级解锁
    fixed_code: str = ""  # Level 3 参考修复，学生确认后应用
    key_concept: str = ""
    evidence_chunks: list[TutorEvidenceChunk] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
