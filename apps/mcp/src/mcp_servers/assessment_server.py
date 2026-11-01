"""assessment-server: comprehensive assessment, mastery, learning path planning, wrong-question book.

See docs/agentarts/03-MCP服务接口契约.md §3.
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

from app.agents.evaluator_agent import EvaluatorAgent  # noqa: E402
from app.models.assessment import (  # noqa: E402
    ComprehensiveAssessmentSubmit,
    LearningEvent,
)
from app.models.course import CourseLessonSession, KnowledgeNodeMastery  # noqa: E402
from app.models.profile import StudentProfile  # noqa: E402
from app.models.profile_record import (  # noqa: E402
    LearningProfileEvent,
    StudentProfileRecord,
)
from app.models.user import User, UserRead  # noqa: E402
from app.services.course_service import CourseNotFoundError, CourseService  # noqa: E402
from app.services.dynamic_profile_service import (  # noqa: E402
    DynamicProfileService,
    ProfileEventInput,
)
from app.services.learning_path_service import (  # noqa: E402
    LearningPathGraphMissingError,
    LearningPathProfileMissingError,
    LearningPathService,
)

mcp = FastMCP("assessment-server", stateless_http=True)


def _load_profile(db: Any, user_id: int, course_id: int) -> StudentProfileRecord | None:
    return db.scalar(
        select(StudentProfileRecord).where(
            StudentProfileRecord.user_id == user_id,
            StudentProfileRecord.course_id == course_id,
        )
    )


def _merge_lesson_state(
    db: Any,
    user_id: int,
    assessment: ComprehensiveAssessmentSubmit,
) -> ComprehensiveAssessmentSubmit:
    """课堂完成状态以持久化的 lesson_state 为准，不信任前端上报。"""
    if assessment.course_id is None or not assessment.knowledge_node_id:
        return assessment
    session_row = db.scalar(
        select(CourseLessonSession).where(
            CourseLessonSession.user_id == user_id,
            CourseLessonSession.course_id == assessment.course_id,
            CourseLessonSession.node_id == assessment.knowledge_node_id,
        )
    )
    state = session_row.lesson_state if session_row is not None else {}
    return assessment.model_copy(
        update={
            "classroom_completed": bool(state.get("classroom_completed")),
            "notes_completed": bool(state.get("notes_completed")),
            "mind_map_completed": bool(state.get("mind_map_completed")),
            "code_lab_completed": bool(state.get("code_lab_completed")),
        }
    )


def _comprehensive_mastery_detail(assessment: ComprehensiveAssessmentSubmit, report: Any) -> str:
    import json

    return json.dumps(
        {
            "assessment_type": "comprehensive",
            "topic": assessment.topic,
            "final_score": report.final_score,
            "passed": report.passed,
            "mastery_status": report.mastery_status,
            "dimension_scores": report.dimension_scores,
            "feedback": report.feedback,
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def submit_comprehensive_assessment_impl(
    user_id: int,
    course_id: int,
    assessment: dict[str, Any],
) -> dict[str, Any]:
    """提交综合学习评估并完成闭环回写。

    服务端依次完成：校验并合并课堂完成状态 → 综合评分（课堂/笔记/导图/代码实验/
    选择题/编程题多维度）→ 知识点掌握度写入 → 画像随学随新事件（含是否需要重规划
    路径的信号）。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        assessment: 评估 payload，Schema 见契约文档 §4.1（quiz_answers、
            code_attempt、knowledge_node_id 等字段）。

    Returns:
        report: {final_score, passed, mastery_status, dimension_scores,
        weak_points, feedback, next_adjustment}；
        profile_update: {changed_dimensions, replan_required, update_reason, ...}。
    """
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        profile_record = _load_profile(db, user_id, course_id)
        if profile_record is None:
            return fail("profile_not_found", "confirmed course profile is required")
        profile = StudentProfile(**(profile_record.profile_data or {})).with_completion_score()

        payload = {**(assessment or {}), "course_id": course_id, "student_id": profile.student_id}
        try:
            assessment_obj = ComprehensiveAssessmentSubmit.model_validate(payload)
        except (TypeError, ValidationError) as exc:
            return fail("validation_error", f"assessment payload invalid: {exc}")
        if not assessment_obj.knowledge_node_id:
            return fail("validation_error", "knowledge_node_id is required")

        assessment_obj = _merge_lesson_state(db, user_id, assessment_obj)
        report = EvaluatorAgent().evaluate_comprehensive(profile, assessment_obj)
        try:
            CourseService(db).upsert_node_mastery(
                user_id=user_id,
                course_id=course_id,
                node_id=assessment_obj.knowledge_node_id,
                topic=assessment_obj.topic,
                score=report.final_score,
                detail=_comprehensive_mastery_detail(assessment_obj, report),
            )
        except CourseNotFoundError:
            return fail("course_not_found", f"course {course_id} not found for user {user_id}")

        profile_update = DynamicProfileService(db).record_event(
            user_id=user_id,
            course_id=course_id,
            payload=ProfileEventInput(
                event_type="assessment_submitted",
                topic=assessment_obj.topic,
                knowledge_node_id=assessment_obj.knowledge_node_id,
                detail=_comprehensive_mastery_detail(assessment_obj, report),
                event_payload={
                    "assessment": assessment_obj.model_dump(mode="json"),
                    "final_score": report.final_score,
                    "passed": report.passed,
                    "mastery_status": report.mastery_status,
                    "dimension_scores": report.dimension_scores,
                    "feedback": report.feedback,
                    "code_attempt": (
                        assessment_obj.code_attempt.model_dump(mode="json")
                        if assessment_obj.code_attempt
                        else {}
                    ),
                },
                evidence_strength="strong",
                score=report.final_score,
            ),
        ).to_payload()
        return ok(report=report.model_dump(mode="json"), profile_update=profile_update)


def submit_learning_event_impl(
    user_id: int,
    course_id: int,
    event: dict[str, Any],
) -> dict[str, Any]:
    """提交轻量学习事件（观看资源、随堂练习等）并更新评估与画像。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        event: LearningEvent Schema：{event_type, topic, knowledge_node_id?,
        score?, detail?}；event_type 取值 resource_viewed / exercise_submitted /
        feedback_submitted / tutor_question。

    Returns:
        report 与 profile_update（结构与综合评估一致）。
    """
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        profile_record = _load_profile(db, user_id, course_id)
        if profile_record is None:
            return fail("profile_not_found", "confirmed course profile is required")
        profile = StudentProfile(**(profile_record.profile_data or {})).with_completion_score()

        payload = {**(event or {}), "course_id": course_id, "student_id": profile.student_id}
        try:
            event_obj = LearningEvent.model_validate(payload)
        except (TypeError, ValidationError) as exc:
            return fail("validation_error", f"event payload invalid: {exc}")

        if event_obj.knowledge_node_id:
            try:
                CourseService(db).upsert_node_mastery(
                    user_id=user_id,
                    course_id=course_id,
                    node_id=event_obj.knowledge_node_id,
                    topic=event_obj.topic,
                    score=event_obj.score,
                    detail=event_obj.detail,
                )
            except CourseNotFoundError:
                return fail("course_not_found", f"course {course_id} not found for user {user_id}")
        report = EvaluatorAgent().evaluate(profile, [event_obj])
        profile_update = DynamicProfileService(db).record_event(
            user_id=user_id,
            course_id=course_id,
            payload=ProfileEventInput(
                event_type=event_obj.event_type.value,
                topic=event_obj.topic,
                knowledge_node_id=event_obj.knowledge_node_id,
                detail=event_obj.detail,
                event_payload=event_obj.model_dump(mode="json"),
                score=event_obj.score,
            ),
        ).to_payload()
        return ok(report=report.model_dump(mode="json"), profile_update=profile_update)


def get_node_mastery_impl(user_id: int, course_id: int, node_id: str = "") -> dict[str, Any]:
    """查询知识点掌握度（不传 node_id 返回当前课程全部节点）。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        node_id: 知识图谱节点 ID；为空时返回全部节点。

    Returns:
        masteries: [{node_id, topic, mastery_score, mastery_status, detail,
        updated_at}]。
    """
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        statement = select(KnowledgeNodeMastery).where(
            KnowledgeNodeMastery.user_id == user_id,
            KnowledgeNodeMastery.course_id == course_id,
        )
        if node_id:
            statement = statement.where(KnowledgeNodeMastery.node_id == node_id)
        rows = db.scalars(statement.order_by(KnowledgeNodeMastery.node_id)).all()
        masteries = [
            {
                "node_id": row.node_id,
                "topic": row.topic,
                "mastery_score": row.mastery_score,
                "mastery_status": row.mastery_status,
                "detail": row.detail,
                "updated_at": iso(row.updated_at),
            }
            for row in rows
        ]
        return ok(masteries=masteries)


def plan_learning_path_impl(
    user_id: int,
    course_id: int,
    plan_type: str = "main",
    focus_node_id: str = "",
    chapter_id: str = "",
    max_nodes: int = 18,
) -> dict[str, Any]:
    """基于画像、知识图谱与掌握度规划个性化学习路径。

    主线路径按图谱顺序推进；plan_type="remedial" 时围绕 focus_node_id 生成
    薄弱点补救路径（含前置依赖回补）。路径已按画像中的可用时间排期，
    未通过的知识点自动插入薄弱点专项任务。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        plan_type: main（主线）或 remedial（薄弱点补救）。
        focus_node_id: 补救路径的目标节点。
        chapter_id: 限定章节（可选）。
        max_nodes: 最多规划的任务数，默认 18。

    Returns:
        path: {plan_type, current_stage_id, stages: [{node_id, topic,
        scheduled_day, scheduled_minutes, is_current, is_remedial,
        recommended_resource_types, recommendation_reason, ...}],
        schedule_summary, weekly_time_budget_minutes, active_chapter_*}。
    """
    if plan_type not in {"main", "remedial"}:
        return fail("validation_error", "plan_type must be 'main' or 'remedial'")
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        user_row = db.get(User, user_id)
        if user_row is None:
            return fail("validation_error", f"user {user_id} not found")
        user = UserRead.model_validate(user_row)
        try:
            path = LearningPathService(db).plan_course_path(
                user=user,
                course_id=course_id,
                max_nodes=max(1, min(int(max_nodes or 18), 40)),
                plan_type=plan_type,
                focus_node_id=focus_node_id or "",
                chapter_id=chapter_id or "",
            )
        except LearningPathProfileMissingError:
            return fail("profile_not_found", "confirmed course profile is required")
        except LearningPathGraphMissingError:
            return fail("graph_missing", "knowledge graph is empty; build the graph first")
        return ok(path=path.model_dump(mode="json"))


def list_wrong_questions_impl(user_id: int, course_id: int, limit: int = 100) -> dict[str, Any]:
    """按课程归档错题：未答对的选择题与未通过的编程题，供错题重做闭环使用。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        limit: 最多返回条数，默认 100，最大 300。

    Returns:
        wrong_questions: [{topic, knowledge_node_id, kind("quiz"|"code"),
        question, options, correct_answer_index, selected_answer_index,
        prompt, expected_output, actual_output, attempts, final_score,
        created_at}]，按评估时间倒序。
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
                LearningProfileEvent.event_type == "assessment_submitted",
            )
            .order_by(LearningProfileEvent.id.desc())
            .limit(clamp_limit(limit, default=100, maximum=300))
        ).all()

        wrong_questions: list[dict[str, Any]] = []
        for row in rows:
            payload = row.event_payload or {}
            assessment = payload.get("assessment") or {}
            for answer in assessment.get("quiz_answers") or []:
                if answer.get("correct") is not False:
                    continue
                wrong_questions.append(
                    {
                        "topic": row.topic,
                        "knowledge_node_id": row.knowledge_node_id,
                        "kind": "quiz",
                        "question": answer.get("prompt", ""),
                        "options": answer.get("options") or [],
                        "correct_answer_index": answer.get("correct_answer_index"),
                        "selected_answer_index": answer.get("selected_answer_index"),
                        "final_score": payload.get("final_score"),
                        "created_at": iso(row.created_at),
                    }
                )
            code = assessment.get("code_attempt") or {}
            if code and code.get("passed") is False:
                wrong_questions.append(
                    {
                        "topic": row.topic,
                        "knowledge_node_id": row.knowledge_node_id,
                        "kind": "code",
                        "prompt": code.get("prompt", ""),
                        "expected_output": code.get("expected_output", ""),
                        "actual_output": code.get("actual_output", ""),
                        "attempts": code.get("attempts", 1),
                        "final_score": payload.get("final_score"),
                        "created_at": iso(row.created_at),
                    }
                )
        return ok(wrong_questions=wrong_questions)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

mcp.tool(name="submit_comprehensive_assessment")(submit_comprehensive_assessment_impl)
mcp.tool(name="submit_learning_event")(submit_learning_event_impl)
mcp.tool(name="get_node_mastery")(get_node_mastery_impl)
mcp.tool(name="plan_learning_path")(plan_learning_path_impl)
mcp.tool(name="list_wrong_questions")(list_wrong_questions_impl)


if __name__ == "__main__":
    run_server(mcp, default_port=8102)
