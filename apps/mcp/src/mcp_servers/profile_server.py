"""profile-server: student profile persistence, interview transcript, profile update events.

See docs/agentarts/03-MCP服务接口契约.md §1.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from mcp_servers._bootstrap import ensure_api_importable

ensure_api_importable()

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_servers.runtime import (  # noqa: E402
    CourseLookupError,
    clamp_limit,
    ensure_course,
    fail,
    get_session,
    iso,
    ok,
    run_server,
)

from app.models.profile import StudentProfile  # noqa: E402
from app.models.profile_record import (  # noqa: E402
    LearningPathRevision,
    LearningProfileEvent,
    ProfileInterview,
    ProfileMessage,
    ProfileUpdateLog,
    StudentProfileRecord,
)
from app.services.course_service import CourseNotFoundError, CourseService  # noqa: E402
from app.services.dynamic_profile_service import (  # noqa: E402
    ConfirmedCourseProfileRequiredError,
    DynamicProfileService,
    ProfileEventInput,
)

mcp = FastMCP("profile-server", stateless_http=True)

_INTERVIEW_STATUS_IN_PROGRESS = "in_progress"
_MESSAGE_WINDOW = 10


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def get_student_profile_impl(user_id: int, course_id: int) -> dict[str, Any]:
    """读取当前学生在当前课程的已确认画像。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。

    Returns:
        包含 exists、student_id、profile（14 维画像 JSON）、completion_score、
        confidence_score、updated_at 的结果对象；画像不存在时 exists 为 false。
    """
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        record = db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == user_id,
                StudentProfileRecord.course_id == course_id,
            )
        )
        if record is None:
            return ok(exists=False, profile=None)
        data = dict(record.profile_data or {})
        return ok(
            exists=True,
            student_id=record.student_id,
            profile=data,
            completion_score=data.get("completion_score"),
            confidence_score=data.get("confidence_score"),
            updated_at=iso(record.updated_at),
        )


def save_student_profile_impl(
    user_id: int,
    course_id: int,
    profile: dict[str, Any],
    source: str = "agentarts_interview",
) -> dict[str, Any]:
    """保存（或覆盖更新）当前课程的学生画像。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        profile: 画像 JSON，字段见契约文档 §4.2；缺失字段用默认值补全，
            保存前自动计算 completion_score 与 confidence_score。
        source: 画像来源标识，默认 agentarts_interview。

    Returns:
        保存后的完整画像与 completion_score；created 表示是否首次创建。
    """
    del source  # 预留审计字段：当前版本画像数据内含 updated_evidence
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        try:
            candidate = StudentProfile(**(profile or {})).with_completion_score()
        except (TypeError, ValidationError) as exc:
            return fail("validation_error", f"profile fields invalid: {exc}")

        record = db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == user_id,
                StudentProfileRecord.course_id == course_id,
            )
        )
        created = record is None
        if created:
            record = StudentProfileRecord(
                user_id=user_id,
                course_id=course_id,
                interview_id=None,
                student_id=candidate.student_id,
                profile_data=candidate.model_dump(mode="json"),
            )
            db.add(record)
        else:
            # 保持 student_id 稳定，避免同一课程画像出现两个学生标识
            candidate = candidate.model_copy(update={"student_id": record.student_id})
            record.profile_data = candidate.model_dump(mode="json")
        db.flush()
        data = dict(record.profile_data)
        return ok(
            student_id=record.student_id,
            profile=data,
            completion_score=data.get("completion_score"),
            confidence_score=data.get("confidence_score"),
            created=created,
        )


def append_interview_message_impl(
    user_id: int,
    course_id: int,
    role: str,
    content: str,
) -> dict[str, Any]:
    """记录画像访谈的一轮对话，返回最近的对话历史供工作流继续追问。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        role: 消息角色，"assistant" 表示 Agent 提问，"user" 表示学生回答。
        content: 消息内容。

    Returns:
        interview_id、turn_count（学生回答轮数）、status、messages（最近 10 条，
        按 {role, content} 顺序返回），可直接作为下一次 next_question 的上下文。
    """
    if role not in {"user", "assistant"}:
        return fail("validation_error", "role must be 'user' or 'assistant'")
    if not (content or "").strip():
        return fail("validation_error", "content must not be empty")

    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        interview = db.scalar(
            select(ProfileInterview)
            .where(
                ProfileInterview.user_id == user_id,
                ProfileInterview.course_id == course_id,
            )
            .order_by(ProfileInterview.id.desc())
        )
        if interview is None or interview.status != _INTERVIEW_STATUS_IN_PROGRESS:
            interview = ProfileInterview(
                user_id=user_id,
                course_id=course_id,
                status=_INTERVIEW_STATUS_IN_PROGRESS,
                turn_count=0,
                current_question="",
                profile_data={},
            )
            db.add(interview)
            db.flush()

        db.add(
            ProfileMessage(
                interview_id=interview.id,
                user_id=user_id,
                role=role,
                content=content,
            )
        )
        if role == "user":
            interview.turn_count = (interview.turn_count or 0) + 1
        db.flush()

        recent = db.scalars(
            select(ProfileMessage)
            .where(ProfileMessage.interview_id == interview.id)
            .order_by(ProfileMessage.id.desc())
            .limit(_MESSAGE_WINDOW)
        ).all()
        messages = [{"role": item.role, "content": item.content} for item in reversed(recent)]
        return ok(
            interview_id=interview.id,
            turn_count=interview.turn_count,
            status=interview.status,
            messages=messages,
        )


def list_interview_messages_impl(user_id: int, course_id: int, limit: int = 20) -> dict[str, Any]:
    """读取当前课程画像访谈的完整对话历史。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        limit: 返回条数上限，默认 20，最大 200。

    Returns:
        按时间升序的 {role, content, created_at} 消息列表。
    """
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        interview = db.scalar(
            select(ProfileInterview)
            .where(
                ProfileInterview.user_id == user_id,
                ProfileInterview.course_id == course_id,
            )
            .order_by(ProfileInterview.id.desc())
        )
        if interview is None:
            return ok(interview_id=None, messages=[])
        rows = db.scalars(
            select(ProfileMessage)
            .where(ProfileMessage.interview_id == interview.id)
            .order_by(ProfileMessage.id.desc())
            .limit(clamp_limit(limit, default=20))
        ).all()
        messages = [
            {"role": item.role, "content": item.content, "created_at": iso(item.created_at)}
            for item in reversed(rows)
        ]
        return ok(interview_id=interview.id, messages=messages)


def record_profile_event_impl(
    user_id: int,
    course_id: int,
    event_type: str,
    topic: str,
    knowledge_node_id: str = "",
    detail: str = "",
    score: float | None = None,
    event_payload: dict[str, Any] | None = None,
    evidence_strength: str | None = None,
    lesson_session_id: int | None = None,
) -> dict[str, Any]:
    """记录一次学习事件并触发画像随学随新。

    事件写入后自动完成：画像维度增量更新、ProfileUpdateLog 审计、
    是否需要重新规划学习路径（replan_required）的判定。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID（需已确认画像）。
        event_type: 事件类型，如 assessment_submitted、tutor_question_asked、
            code_attempt_passed、lesson_completed 等（见契约文档 §1）。
        topic: 事件主题（通常是知识点名称）。
        knowledge_node_id: 知识图谱节点 ID，可为空。
        detail: 事件描述文本。
        score: 事件得分（0-1），可选。
        event_payload: 事件原始 JSON，可选。
        evidence_strength: 证据强度 strong/medium/weak，缺省按事件类型推断。
        lesson_session_id: 关联的课堂会话 ID，可选。

    Returns:
        event_id、changed_dimensions、update_reason、replan_required、
        profile_summary 等画像更新结果。
    """
    with get_session() as db:
        try:
            result = DynamicProfileService(db).record_event(
                user_id=user_id,
                course_id=course_id,
                payload=ProfileEventInput(
                    event_type=event_type,
                    topic=topic or "",
                    knowledge_node_id=knowledge_node_id or "",
                    lesson_session_id=lesson_session_id,
                    detail=detail or "",
                    event_payload=event_payload,
                    evidence_strength=evidence_strength,
                    score=score,
                ),
            )
        except CourseNotFoundError:
            return fail("course_not_found", f"course {course_id} not found for user {user_id}")
        except ConfirmedCourseProfileRequiredError:
            return fail(
                "profile_not_found",
                "confirmed course profile is required before recording events",
            )
        return ok(**result.to_payload())


def list_profile_events_impl(user_id: int, course_id: int, limit: int = 50) -> dict[str, Any]:
    """列出当前课程最近的画像事件（评估、练习、提问等）。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        limit: 返回条数上限，默认 50，最大 200。

    Returns:
        按时间倒序的画像事件列表。
    """
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        rows = db.scalars(
            select(LearningProfileEvent)
            .where(
                LearningProfileEvent.user_id == user_id,
                LearningProfileEvent.course_id == course_id,
            )
            .order_by(LearningProfileEvent.id.desc())
            .limit(clamp_limit(limit))
        ).all()
        events = [
            {
                "id": row.id,
                "event_type": row.event_type,
                "topic": row.topic,
                "knowledge_node_id": row.knowledge_node_id,
                "detail": row.detail,
                "score": row.score,
                "evidence_strength": row.evidence_strength,
                "created_at": iso(row.created_at),
            }
            for row in rows
        ]
        return ok(events=events)


def list_profile_update_logs_impl(user_id: int, course_id: int, limit: int = 20) -> dict[str, Any]:
    """列出画像增量更新的审计日志（改了哪些维度、为什么改）。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        limit: 返回条数上限，默认 20，最大 200。

    Returns:
        画像更新日志列表，含 changed_dimensions、update_reason、confidence_delta。
    """
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        rows = db.scalars(
            select(ProfileUpdateLog)
            .where(
                ProfileUpdateLog.user_id == user_id,
                ProfileUpdateLog.course_id == course_id,
            )
            .order_by(ProfileUpdateLog.id.desc())
            .limit(clamp_limit(limit, default=20))
        ).all()
        logs = [
            {
                "id": row.id,
                "changed_dimensions": row.changed_dimensions,
                "update_reason": row.update_reason,
                "confidence_delta": row.confidence_delta,
                "created_at": iso(row.created_at),
            }
            for row in rows
        ]
        return ok(logs=logs)


def list_path_revisions_impl(user_id: int, course_id: int, limit: int = 20) -> dict[str, Any]:
    """列出学习路径重规划的触发记录。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        limit: 返回条数上限，默认 20，最大 200。

    Returns:
        路径重规划记录列表，含 trigger_type、trigger_node_id、change_summary。
    """
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        rows = db.scalars(
            select(LearningPathRevision)
            .where(
                LearningPathRevision.user_id == user_id,
                LearningPathRevision.course_id == course_id,
            )
            .order_by(LearningPathRevision.id.desc())
            .limit(clamp_limit(limit, default=20))
        ).all()
        revisions = [
            {
                "id": row.id,
                "trigger_type": row.trigger_type,
                "trigger_node_id": row.trigger_node_id,
                "change_summary": row.change_summary,
                "created_at": iso(row.created_at),
            }
            for row in rows
        ]
        return ok(revisions=revisions)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Single registry so both this standalone server and the unified single-port
# entrypoint (mcp_servers.server) expose exactly the same tool set.
TOOL_IMPLS = {
    "get_student_profile": get_student_profile_impl,
    "save_student_profile": save_student_profile_impl,
    "append_interview_message": append_interview_message_impl,
    "list_interview_messages": list_interview_messages_impl,
    "record_profile_event": record_profile_event_impl,
    "list_profile_events": list_profile_events_impl,
    "list_profile_update_logs": list_profile_update_logs_impl,
    "list_path_revisions": list_path_revisions_impl,
}

for _name, _impl in TOOL_IMPLS.items():
    mcp.tool(name=_name)(_impl)


if __name__ == "__main__":
    run_server(mcp, default_port=8100)
