from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TutorAttachment(BaseModel):
    id: str = ""
    filename: str = ""
    content_type: str = ""
    description: str = ""
    data_url: str = Field(default="", max_length=700_000)


class TutorChatRequest(BaseModel):
    course_id: int
    message: str = Field(min_length=1)
    node_id: str = ""
    page_context: str = ""
    attachments: list[TutorAttachment] = Field(default_factory=list)
    history: list[dict[str, str]] = Field(default_factory=list)
    # 学习状态感知（issue #15）：focused/confused/distracted/tired/no_face，空串表示未开启
    attention_state: str = ""


class TutorAgentEvent(BaseModel):
    event: str
    agent: str
    summary: str
    status: Literal["pending", "running", "completed", "failed"] = "completed"
    detail: dict[str, Any] = Field(default_factory=dict)


class TutorEvidenceChunk(BaseModel):
    chunk_id: int | str | None = None
    source_locator: str = ""
    heading: str = ""
    content: str = ""
    retrieval_query: str = ""
    distance: float | None = None
    storage: str = "mysql"


class TutorMultimodalCard(BaseModel):
    type: Literal["text_explanation", "diagram", "code_hint", "exercise", "video_script", "source_evidence"]
    title: str
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TutorSuggestedAction(BaseModel):
    type: Literal["continue_chat", "open_graph", "open_learning_path", "open_lesson", "open_assessment", "build_knowledge_base"]
    label: str
    target: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class TutorChatResponse(BaseModel):
    answer: str
    agent_events: list[TutorAgentEvent]
    analysis_plan: dict[str, Any]
    retrieval_trace: list[dict[str, Any]]
    graph_constraints: dict[str, Any]
    evidence_chunks: list[TutorEvidenceChunk]
    verification_report: dict[str, Any]
    decision_report: dict[str, Any]
    multimodal_cards: list[TutorMultimodalCard]
    suggested_actions: list[TutorSuggestedAction]
    # issue #16：可点击的追问选项（2-3 条，与当前知识点/问题上下文相关）
    suggested_followups: list[str] = Field(default_factory=list)
