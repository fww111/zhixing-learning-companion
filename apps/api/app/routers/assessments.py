from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.evaluator_agent import EvaluatorAgent
from app.db import get_db
from app.models.course import CourseLessonSession
from app.models.assessment import AssessmentReport, ComprehensiveAssessmentSubmit, LearningEvent
from app.models.profile import ProfileEvidence, StudentProfile
from app.models.profile_record import StudentProfileRecord
from app.models.user import UserRead
from app.routers.auth import current_user
from app.services.course_service import CourseNotFoundError, CourseService
from app.services.dynamic_profile_service import DynamicProfileService, ProfileEventInput


router = APIRouter(prefix="/api/assessments", tags=["assessments"])


@router.post("/submit")
async def submit_assessment(
    payload: dict = Body(...),
    user: UserRead = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    payload_course_id = payload.get("course_id") if isinstance(payload, dict) else None
    profile_record = db.scalar(
        select(StudentProfileRecord).where(
            StudentProfileRecord.user_id == user.id,
            StudentProfileRecord.course_id == payload_course_id,
        )
    )
    if profile_record is None and payload_course_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="confirmed course profile is required")
    profile = (
        StudentProfile(**profile_record.profile_data).with_completion_score()
        if profile_record is not None
        else StudentProfile.from_conversation("计算机大二，想学习机器学习，梯度下降薄弱。")
    )

    if _is_comprehensive_payload(payload):
        assessment = ComprehensiveAssessmentSubmit.model_validate(payload)
        assessment = _assessment_with_persisted_lesson_state(db, user.id, assessment)
        report = EvaluatorAgent().evaluate_comprehensive(profile, assessment)
        if assessment.course_id is not None and assessment.knowledge_node_id:
            try:
                CourseService(db).upsert_node_mastery(
                    user_id=user.id,
                    course_id=assessment.course_id,
                    node_id=assessment.knowledge_node_id,
                    topic=assessment.topic,
                    score=report.final_score,
                    detail=_comprehensive_mastery_detail(assessment, report),
                )
            except CourseNotFoundError:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
        if profile_record is not None and assessment.course_id is not None:
            profile_update = DynamicProfileService(db).record_event(
                user_id=user.id,
                course_id=assessment.course_id,
                payload=ProfileEventInput(
                    event_type="assessment_submitted",
                    topic=assessment.topic,
                    knowledge_node_id=assessment.knowledge_node_id,
                    detail=assessment.detail or _comprehensive_mastery_detail(assessment, report),
                    event_payload={
                        "assessment": assessment.model_dump(mode="json"),
                        "final_score": report.final_score,
                        "passed": report.passed,
                        "mastery_status": report.mastery_status,
                        "dimension_scores": report.dimension_scores,
                        "feedback": report.feedback,
                        "code_attempt": assessment.code_attempt.model_dump(mode="json") if assessment.code_attempt else {},
                    },
                    evidence_strength="strong",
                    score=report.final_score,
                ),
            ).to_payload()
        else:
            profile_update = {}
        return {**report.model_dump(mode="json"), "profile_update": profile_update}

    event = LearningEvent.model_validate(payload)
    if event.course_id is not None and event.knowledge_node_id:
        try:
            CourseService(db).upsert_node_mastery(
                user_id=user.id,
                course_id=event.course_id,
                node_id=event.knowledge_node_id,
                topic=event.topic,
                score=event.score,
                detail=event.detail,
            )
        except CourseNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    report = EvaluatorAgent().evaluate(profile, [event])
    if profile_record is not None and event.course_id is not None:
        profile_update = DynamicProfileService(db).record_event(
            user_id=user.id,
            course_id=event.course_id,
            payload=ProfileEventInput(
                event_type=event.event_type.value,
                topic=event.topic,
                knowledge_node_id=event.knowledge_node_id,
                detail=event.detail,
                event_payload=event.model_dump(mode="json"),
                score=event.score,
            ),
        ).to_payload()
    else:
        profile_update = {}
    return {**report.model_dump(mode="json"), "profile_update": profile_update}


def _is_comprehensive_payload(payload: dict) -> bool:
    return any(
        key in payload
        for key in (
            "quiz_answers",
            "code_attempt",
            "classroom_completed",
            "notes_completed",
            "mind_map_completed",
            "code_lab_completed",
        )
    )


def _comprehensive_mastery_detail(assessment: ComprehensiveAssessmentSubmit, report: AssessmentReport) -> str:
    return json.dumps(
        {
            "assessment_type": "comprehensive",
            "topic": assessment.topic,
            "final_score": report.final_score,
            "passed": report.passed,
            "mastery_status": report.mastery_status,
            "dimension_scores": report.dimension_scores,
            "feedback": report.feedback,
            "classroom_completed": assessment.classroom_completed,
            "notes_completed": assessment.notes_completed,
            "mind_map_completed": assessment.mind_map_completed,
            "code_lab_completed": assessment.code_lab_completed,
        },
        ensure_ascii=False,
    )


def _assessment_with_persisted_lesson_state(
    db: Session,
    user_id: int,
    assessment: ComprehensiveAssessmentSubmit,
) -> ComprehensiveAssessmentSubmit:
    if assessment.course_id is None or not assessment.knowledge_node_id:
        return assessment
    session = db.scalar(
        select(CourseLessonSession).where(
            CourseLessonSession.user_id == user_id,
            CourseLessonSession.course_id == assessment.course_id,
            CourseLessonSession.node_id == assessment.knowledge_node_id,
        )
    )
    state = session.lesson_state if session is not None else {}
    return assessment.model_copy(
        update={
            "classroom_completed": bool(state.get("classroom_completed")),
            "notes_completed": bool(state.get("notes_completed")),
            "mind_map_completed": bool(state.get("mind_map_completed")),
            "code_lab_completed": bool(state.get("code_lab_completed")),
        }
    )


def _profile_after_assessment(profile: StudentProfile, event: LearningEvent) -> StudentProfile:
    evidence = ProfileEvidence(
        source=event.event_type.value,
        topic=event.topic,
        detail=event.detail or f"{event.topic}评估得分 {event.score}",
    )
    weak_points = list(profile.weak_points)
    knowledge_focus = list(profile.knowledge_graph_focus)
    if event.score is not None and event.score < 0.75:
        if event.topic not in weak_points:
            weak_points.append(event.topic)
        if event.topic not in knowledge_focus:
            knowledge_focus.insert(0, event.topic)
    elif event.score is not None and event.score >= 0.9:
        weak_points = [item for item in weak_points if item != event.topic]

    confidence_delta = 0.03 if event.score is not None and event.score >= 0.75 else -0.04
    next_confidence = min(0.95, max(0.2, profile.confidence_score + confidence_delta))
    return profile.model_copy(
        update={
            "weak_points": weak_points,
            "knowledge_graph_focus": knowledge_focus[:5] or profile.knowledge_graph_focus,
            "confidence_score": next_confidence,
            "updated_evidence": [*profile.updated_evidence, evidence],
        }
    ).with_completion_score()


def _profile_after_comprehensive_assessment(
    profile: StudentProfile,
    assessment: ComprehensiveAssessmentSubmit,
    report: AssessmentReport,
) -> StudentProfile:
    feedback = "；".join(report.feedback) if report.feedback else report.next_adjustment
    evidence = ProfileEvidence(
        source="comprehensive_assessment",
        topic=assessment.topic,
        detail=f"综合评估得分 {round(report.final_score * 100)}%，状态 {report.mastery_status}。{feedback}",
    )
    weak_points = list(profile.weak_points)
    knowledge_focus = list(profile.knowledge_graph_focus)
    if report.passed:
        weak_points = [item for item in weak_points if item != assessment.topic]
        confidence_delta = 0.05 if report.final_score >= 0.9 else 0.03
    else:
        if assessment.topic not in weak_points:
            weak_points.append(assessment.topic)
        if assessment.topic not in knowledge_focus:
            knowledge_focus.insert(0, assessment.topic)
        confidence_delta = -0.06 if report.final_score < 0.6 else -0.03

    next_confidence = min(0.95, max(0.2, profile.confidence_score + confidence_delta))
    return profile.model_copy(
        update={
            "weak_points": weak_points,
            "knowledge_graph_focus": knowledge_focus[:5] or profile.knowledge_graph_focus,
            "confidence_score": next_confidence,
            "updated_evidence": [*profile.updated_evidence, evidence],
        }
    ).with_completion_score()
