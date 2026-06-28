from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProfileInterview(Base):
    __tablename__ = "profile_interviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            name="fk_profile_interviews_course_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", nullable=False)
    turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_question: Mapped[str] = mapped_column(Text, default="", nullable=False)
    profile_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProfileMessage(Base):
    __tablename__ = "profile_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("profile_interviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StudentProfileRecord(Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_student_profiles_user_course"),
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            name="fk_student_profiles_course_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("profile_interviews.id", ondelete="SET NULL"), nullable=True
    )
    student_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    profile_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LearningProfileEvent(Base):
    __tablename__ = "learning_profile_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            name="fk_learning_profile_events_course_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False)
    student_profile_id: Mapped[int] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    knowledge_node_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    lesson_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    topic: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    event_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(16), default="weak", nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfileUpdateLog(Base):
    __tablename__ = "profile_update_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            name="fk_profile_update_logs_course_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False)
    student_profile_id: Mapped[int] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_event_id: Mapped[int] = mapped_column(
        ForeignKey("learning_profile_events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    changed_dimensions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    before_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    after_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    update_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningPathRevision(Base):
    __tablename__ = "learning_path_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            name="fk_learning_path_revisions_course_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    trigger_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_profile_events.id", ondelete="SET NULL"), index=True, nullable=True
    )
    trigger_node_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    previous_plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    next_plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
