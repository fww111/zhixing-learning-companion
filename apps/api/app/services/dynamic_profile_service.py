from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profile_record import (
    LearningPathRevision,
    LearningProfileEvent,
    ProfileUpdateLog,
    StudentProfileRecord,
)
from app.services.course_service import CourseService


class ConfirmedCourseProfileRequiredError(RuntimeError):
    pass


@dataclass
class ProfileEventInput:
    event_type: str
    topic: str = ""
    knowledge_node_id: str = ""
    lesson_session_id: int | None = None
    detail: str = ""
    event_payload: dict[str, Any] | None = None
    evidence_strength: str | None = None
    score: float | None = None


@dataclass
class ProfileUpdateResult:
    event: LearningProfileEvent
    log: ProfileUpdateLog | None
    revision: LearningPathRevision | None
    profile: StudentProfileRecord
    changed_dimensions: list[str]
    update_reason: str
    replan_required: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "course_id": self.event.course_id,
            "event_id": self.event.id,
            "log_id": self.log.id if self.log is not None else None,
            "revision_id": self.revision.id if self.revision is not None else None,
            "changed_dimensions": self.changed_dimensions,
            "update_reason": self.update_reason,
            "replan_required": self.replan_required,
            "profile_summary": self.profile.profile_data.get("profile_summary", ""),
        }


class DynamicProfileService:
    STRONG_EVENTS = {
        "assessment_submitted",
        "quiz_submitted",
        "code_attempt_passed",
        "lesson_completed",
        "exercise_submitted",
    }
    MEDIUM_EVENTS = {
        "profile_interview_answered",
        "openmaic_classroom_viewed",
        "mind_map_interacted",
        "code_attempt_run",
        "tutor_question_asked",
        "feedback_submitted",
        "document_viewed",
    }

    def __init__(self, db: Session, course_service: CourseService | None = None) -> None:
        self.db = db
        self.course_service = course_service or CourseService(db)

    def record_event(
        self,
        user_id: int,
        course_id: int,
        payload: ProfileEventInput,
        *,
        commit: bool = True,
    ) -> ProfileUpdateResult:
        self.course_service.get_course(user_id, course_id)
        profile = self._profile(user_id, course_id)
        event = LearningProfileEvent(
            user_id=user_id,
            course_id=course_id,
            student_profile_id=profile.id,
            knowledge_node_id=self._truncate(payload.knowledge_node_id, 255),
            lesson_session_id=payload.lesson_session_id,
            event_type=self._truncate(payload.event_type, 64),
            topic=self._truncate(payload.topic, 255),
            detail=payload.detail or "",
            event_payload=payload.event_payload or {},
            evidence_strength=payload.evidence_strength or self._evidence_strength(payload.event_type),
            score=payload.score,
        )
        self.db.add(event)
        self.db.flush()

        before = deepcopy(profile.profile_data or {})
        after, changed_dimensions, update_reason, confidence_delta, replan_required = self._updated_profile_data(
            before,
            event,
        )
        profile.profile_data = after
        profile.student_id = str(after.get("student_id") or profile.student_id)

        log = None
        if changed_dimensions:
            log = ProfileUpdateLog(
                user_id=user_id,
                course_id=course_id,
                student_profile_id=profile.id,
                source_event_id=event.id,
                changed_dimensions=changed_dimensions,
                before_snapshot=before,
                after_snapshot=after,
                update_reason=update_reason,
                confidence_delta=confidence_delta,
            )
            self.db.add(log)

        revision = None
        if replan_required:
            revision = LearningPathRevision(
                user_id=user_id,
                course_id=course_id,
                trigger_type=self._replan_trigger(event),
                trigger_event_id=event.id,
                trigger_node_id=event.knowledge_node_id,
                previous_plan={},
                next_plan={
                    "plan_type": "remedial" if self._is_failed_event(event) else "main",
                    "focus_node_id": event.knowledge_node_id,
                    "reason": update_reason,
                },
                change_summary=self._replan_summary(event),
            )
            self.db.add(revision)

        if commit:
            self.db.commit()
            self.db.refresh(event)
            if log is not None:
                self.db.refresh(log)
            if revision is not None:
                self.db.refresh(revision)
            self.db.refresh(profile)

        return ProfileUpdateResult(
            event=event,
            log=log,
            revision=revision,
            profile=profile,
            changed_dimensions=changed_dimensions,
            update_reason=update_reason,
            replan_required=replan_required,
        )

    def list_events(self, user_id: int, course_id: int, limit: int = 50) -> list[LearningProfileEvent]:
        self.course_service.get_course(user_id, course_id)
        return list(
            self.db.scalars(
                select(LearningProfileEvent)
                .where(
                    LearningProfileEvent.user_id == user_id,
                    LearningProfileEvent.course_id == course_id,
                )
                .order_by(LearningProfileEvent.created_at.desc(), LearningProfileEvent.id.desc())
                .limit(limit)
            )
        )

    def list_update_logs(self, user_id: int, course_id: int, limit: int = 20) -> list[ProfileUpdateLog]:
        self.course_service.get_course(user_id, course_id)
        return list(
            self.db.scalars(
                select(ProfileUpdateLog)
                .where(
                    ProfileUpdateLog.user_id == user_id,
                    ProfileUpdateLog.course_id == course_id,
                )
                .order_by(ProfileUpdateLog.created_at.desc(), ProfileUpdateLog.id.desc())
                .limit(limit)
            )
        )

    def list_path_revisions(self, user_id: int, course_id: int, limit: int = 20) -> list[LearningPathRevision]:
        self.course_service.get_course(user_id, course_id)
        return list(
            self.db.scalars(
                select(LearningPathRevision)
                .where(
                    LearningPathRevision.user_id == user_id,
                    LearningPathRevision.course_id == course_id,
                )
                .order_by(LearningPathRevision.created_at.desc(), LearningPathRevision.id.desc())
                .limit(limit)
            )
        )

    def _profile(self, user_id: int, course_id: int) -> StudentProfileRecord:
        profile = self.db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == user_id,
                StudentProfileRecord.course_id == course_id,
            )
        )
        if profile is None:
            raise ConfirmedCourseProfileRequiredError("confirmed course profile is required")
        return profile

    def _updated_profile_data(
        self,
        before: dict[str, Any],
        event: LearningProfileEvent,
    ) -> tuple[dict[str, Any], list[str], str, float, bool]:
        after = self._with_extended_defaults(before)
        changed: set[str] = set()
        event_payload = event.event_payload or {}
        score = self._score_from_event(event)
        topic = event.topic or event.knowledge_node_id or "current knowledge point"

        after["profile_version"] = int(after.get("profile_version") or 1) + 1
        after["last_event_id"] = event.id
        changed.update({"profile_version", "last_event_id"})

        confidence_delta = self._confidence_delta(event, score)
        after["confidence_score"] = round(
            min(0.95, max(0.2, float(after.get("confidence_score") or 0.5) + confidence_delta)),
            4,
        )
        changed.add("confidence_score")

        if event.event_type in {"assessment_submitted", "quiz_submitted", "exercise_submitted"}:
            self._update_assessment_profile(after, event, score, topic, changed)
        if event.event_type in {"code_attempt_run", "code_attempt_passed", "assessment_submitted"}:
            self._update_code_profile(after, event, score, topic, changed)
        if event.event_type in {"mind_map_interacted", "document_viewed", "openmaic_classroom_viewed"}:
            self._update_modality_profile(after, event, score, event_payload, changed)
        if event.event_type in {"lesson_completed", "assessment_submitted"}:
            self._update_growth_profile(after, event, score, changed)
        if event.event_type == "attention_sample":
            self._update_attention_sample_profile(after, event, topic, changed)

        reason = self._update_reason(event, score, topic)
        after["last_profile_update_reason"] = reason
        after["updated_evidence"] = [
            *self._list(after.get("updated_evidence")),
            {
                "source": event.event_type,
                "topic": topic,
                "detail": event.detail or reason,
            },
        ][-30:]
        after["profile_summary"] = self._profile_summary(after)
        changed.update({"last_profile_update_reason", "updated_evidence", "profile_summary"})
        self._update_dimension_confidence(after, changed, event.evidence_strength)
        changed.add("dimension_confidence")

        replan_required = self._requires_replan(event, score)
        if replan_required:
            after["last_replanned_at"] = "pending"
            changed.add("last_replanned_at")

        ordered_changed = [key for key in after.keys() if key in changed]
        return after, ordered_changed, reason, confidence_delta, replan_required

    def _with_extended_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        next_data = deepcopy(data)
        next_data.setdefault("profile_version", 1)
        next_data.setdefault("last_event_id", None)
        next_data.setdefault("last_replanned_at", None)
        next_data.setdefault("profile_summary", "")
        next_data.setdefault("dimension_confidence", {})
        next_data.setdefault("short_term_goal", "")
        next_data.setdefault("long_term_goal", next_data.get("learning_goal", ""))
        next_data.setdefault("course_goal", next_data.get("learning_goal", ""))
        next_data.setdefault("motivation_profile", {"type": next_data.get("motivation", ""), "level": 0.5})
        next_data.setdefault("motivation_level", 0.5)
        next_data.setdefault("persistence_level", 0.5)
        next_data.setdefault("prior_knowledge_map", {})
        next_data.setdefault("mastery_distribution", {})
        next_data.setdefault("strong_points", [])
        next_data.setdefault("misconception_patterns", [])
        next_data.setdefault("learning_strategy", {})
        next_data.setdefault("metacognition_level", 0.5)
        next_data.setdefault("reflection_quality", 0.5)
        next_data.setdefault("debugging_strategy", "")
        next_data.setdefault("available_days", [])
        next_data.setdefault("weekly_time_budget_minutes", 0)
        next_data.setdefault("daily_time_budget_minutes", {})
        next_data.setdefault("attention_pattern", {"started": 0, "completed": 0})
        next_data.setdefault("cognitive_load_tolerance", "medium")
        next_data.setdefault("modality_effectiveness", {})
        next_data.setdefault("preferred_resource_order", list(next_data.get("resource_preference") or []))
        next_data.setdefault("interaction_preference", "")
        next_data.setdefault("quiz_performance", {"attempts": 0, "last_score": None})
        next_data.setdefault("code_performance", {"attempts": 0, "passed": 0, "last_score": None})
        next_data.setdefault("application_ability", 0.5)
        next_data.setdefault("accuracy_trend", [])
        next_data.setdefault("completion_trend", [])
        next_data.setdefault("affective_state", {"confidence": next_data.get("confidence_score", 0.5)})
        next_data.setdefault("learning_risk", {"level": "normal", "signals": []})
        next_data.setdefault("growth_trend", {"mastery_scores": [], "completion_scores": []})
        next_data.setdefault("last_profile_update_reason", "")
        next_data.setdefault("updated_evidence", [])
        return next_data

    def _update_assessment_profile(
        self,
        profile: dict[str, Any],
        event: LearningProfileEvent,
        score: float | None,
        topic: str,
        changed: set[str],
    ) -> None:
        if score is None:
            return
        mastery = dict(profile.get("mastery_distribution") or {})
        mastery[event.knowledge_node_id or topic] = {
            "topic": topic,
            "score": score,
            "status": self._mastery_status(score),
        }
        profile["mastery_distribution"] = mastery
        changed.add("mastery_distribution")

        quiz = dict(profile.get("quiz_performance") or {})
        quiz["attempts"] = int(quiz.get("attempts") or 0) + 1
        quiz["last_score"] = score
        profile["quiz_performance"] = quiz
        changed.add("quiz_performance")

        trend = list(profile.get("accuracy_trend") or [])
        profile["accuracy_trend"] = [*trend, score][-20:]
        changed.add("accuracy_trend")

        weak_points = self._list(profile.get("weak_points"))
        strong_points = self._list(profile.get("strong_points"))
        focus = self._list(profile.get("knowledge_graph_focus"))
        if score < 0.75:
            if topic not in weak_points:
                weak_points.append(topic)
            if topic not in focus:
                focus.insert(0, topic)
            profile["learning_risk"] = self._risk(profile, "assessment_not_passed")
            changed.add("learning_risk")
        else:
            weak_points = [item for item in weak_points if item != topic]
            if topic not in strong_points:
                strong_points.append(topic)
        profile["weak_points"] = weak_points
        profile["strong_points"] = strong_points[-10:]
        profile["knowledge_graph_focus"] = focus[:8]
        changed.update({"weak_points", "strong_points", "knowledge_graph_focus"})

    def _update_code_profile(
        self,
        profile: dict[str, Any],
        event: LearningProfileEvent,
        score: float | None,
        topic: str,
        changed: set[str],
    ) -> None:
        payload = event.event_payload or {}
        attempt = payload.get("code_attempt") if isinstance(payload.get("code_attempt"), dict) else payload
        attempts = int(attempt.get("attempts") or payload.get("attempts") or 1)
        passed = bool(attempt.get("passed")) or event.event_type == "code_attempt_passed" or (score is not None and score >= 0.75)
        code = dict(profile.get("code_performance") or {})
        code["attempts"] = int(code.get("attempts") or 0) + attempts
        code["passed"] = int(code.get("passed") or 0) + (1 if passed else 0)
        code["last_score"] = score
        profile["code_performance"] = code
        changed.add("code_performance")

        if not passed or (score is not None and score < 0.6):
            patterns = self._list(profile.get("misconception_patterns"))
            detail = event.detail or str(attempt.get("actual_output") or "")
            pattern = self._code_misconception(topic, detail)
            if pattern not in patterns:
                patterns.append(pattern)
            profile["misconception_patterns"] = patterns[-10:]
            profile["debugging_strategy"] = "需要引导式调试和预期输出对照"
            profile["application_ability"] = round(max(0.1, float(profile.get("application_ability") or 0.5) - 0.08), 4)
            changed.update({"misconception_patterns", "debugging_strategy", "application_ability"})
        elif passed:
            profile["application_ability"] = round(min(0.95, float(profile.get("application_ability") or 0.5) + 0.06), 4)
            changed.add("application_ability")

    def _update_modality_profile(
        self,
        profile: dict[str, Any],
        event: LearningProfileEvent,
        score: float | None,
        payload: dict[str, Any],
        changed: set[str],
    ) -> None:
        modality = str(payload.get("resource_type") or self._resource_type_for_event(event.event_type))
        if not modality:
            return
        effectiveness = dict(profile.get("modality_effectiveness") or {})
        current = dict(effectiveness.get(modality) or {})
        uses = int(current.get("uses") or 0) + 1
        last_score = score if score is not None else payload.get("score")
        current["uses"] = uses
        if last_score is not None:
            current["last_score"] = float(last_score)
            previous_avg = float(current.get("avg_score") or last_score)
            current["avg_score"] = round(((previous_avg * (uses - 1)) + float(last_score)) / uses, 4)
        effectiveness[modality] = current
        profile["modality_effectiveness"] = effectiveness
        changed.add("modality_effectiveness")

        order = self._list(profile.get("preferred_resource_order"))
        if modality not in order:
            order.insert(0, modality)
        elif last_score is not None and float(last_score) >= 0.75:
            order = [modality, *[item for item in order if item != modality]]
        profile["preferred_resource_order"] = order[:8]
        changed.add("preferred_resource_order")

    def _update_attention_sample_profile(
        self,
        profile: dict[str, Any],
        event: LearningProfileEvent,
        topic: str,
        changed: set[str],
    ) -> None:
        """issue #15：聚合专注度采样，困惑密集的知识点写入薄弱点证据。

        每条 attention_sample 更新 attention_pattern.confused_by_node 计数；
        当某知识点样本 ≥5 且困惑占比 ≥40% 时，把该知识点追加进 weak_points，
        并写一条 medium 证据，供画像更新日志与学习路径补救规划使用。
        """
        payload = event.event_payload or {}
        dominant = str(payload.get("dominant") or "").strip().lower()
        if not dominant:
            return

        attention = dict(profile.get("attention_pattern") or {})
        by_node = dict(attention.get("confused_by_node") or {})
        node_key = event.knowledge_node_id or topic
        node_stats = dict(by_node.get(node_key) or {"total": 0, "confused": 0})
        node_stats["total"] = int(node_stats.get("total") or 0) + 1
        if dominant == "confused":
            node_stats["confused"] = int(node_stats.get("confused") or 0) + 1
        by_node[node_key] = node_stats
        attention["confused_by_node"] = by_node
        attention["last_dominant"] = dominant
        attention["last_sample_topic"] = topic
        profile["attention_pattern"] = attention
        changed.add("attention_pattern")

        total = int(node_stats["total"])
        confused = int(node_stats["confused"])
        if total >= 5 and confused / total >= 0.4 and topic:
            weak_points = self._list(profile.get("weak_points"))
            if topic not in weak_points:
                weak_points.append(topic)
                profile["weak_points"] = weak_points
                profile["learning_risk"] = self._risk(profile, "attention_confused_pattern")
                changed.update({"weak_points", "learning_risk"})
                # 用 updated_evidence 记录困惑证据（画像更新日志可见）
                evidence = self._list(profile.get("updated_evidence"))
                evidence.append(
                    {
                        "source": "attention_sample",
                        "topic": topic,
                        "detail": (
                            f"知识点「{topic}」累计 {total} 次专注度采样中困惑占 {confused} 次"
                            f"（{round(confused / total * 100)}%），判定为易卡难点并写入薄弱点。"
                        ),
                    }
                )
                profile["updated_evidence"] = evidence[-30:]
                changed.add("updated_evidence")

    def _update_growth_profile(
        self,
        profile: dict[str, Any],
        event: LearningProfileEvent,
        score: float | None,
        changed: set[str],
    ) -> None:
        completion = 1.0 if self._is_passed_event(event, score) else 0.0
        attention = dict(profile.get("attention_pattern") or {})
        attention["completed"] = int(attention.get("completed") or 0) + (1 if completion else 0)
        profile["attention_pattern"] = attention
        changed.add("attention_pattern")

        growth = dict(profile.get("growth_trend") or {})
        mastery_scores = list(growth.get("mastery_scores") or [])
        completion_scores = list(growth.get("completion_scores") or [])
        if score is not None:
            growth["mastery_scores"] = [*mastery_scores, score][-20:]
        growth["completion_scores"] = [*completion_scores, completion][-20:]
        profile["growth_trend"] = growth
        changed.add("growth_trend")

        if completion:
            profile["persistence_level"] = round(min(0.95, float(profile.get("persistence_level") or 0.5) + 0.04), 4)
        else:
            profile["persistence_level"] = round(max(0.1, float(profile.get("persistence_level") or 0.5) - 0.03), 4)
        changed.add("persistence_level")

    def _update_dimension_confidence(self, profile: dict[str, Any], changed: set[str], evidence_strength: str) -> None:
        confidence = dict(profile.get("dimension_confidence") or {})
        delta = {"strong": 0.12, "medium": 0.07, "weak": 0.03, "system": 0.02}.get(evidence_strength, 0.03)
        for key in changed:
            confidence[key] = round(min(0.95, float(confidence.get(key) or 0.4) + delta), 4)
        profile["dimension_confidence"] = confidence

    def _score_from_event(self, event: LearningProfileEvent) -> float | None:
        if event.score is not None:
            return event.score
        payload = event.event_payload or {}
        for key in ("final_score", "score"):
            value = payload.get(key)
            if isinstance(value, int | float):
                return float(value)
        return None

    def _requires_replan(self, event: LearningProfileEvent, score: float | None) -> bool:
        if event.event_type == "assessment_submitted":
            return True
        if event.event_type in {"quiz_submitted", "exercise_submitted"} and score is not None and score < 0.75:
            return True
        if event.event_type == "code_attempt_run" and score is not None and score < 0.6:
            return True
        return False

    def _replan_trigger(self, event: LearningProfileEvent) -> str:
        if self._is_failed_event(event):
            return "assessment_failed" if event.event_type == "assessment_submitted" else "learning_event_failed"
        return "assessment_passed" if event.event_type == "assessment_submitted" else "profile_updated"

    def _replan_summary(self, event: LearningProfileEvent) -> str:
        if self._is_failed_event(event):
            return f"Remedial path required for {event.topic or event.knowledge_node_id} based on {event.event_type}."
        return f"Mainline path can continue after {event.topic or event.knowledge_node_id}."

    def _is_failed_event(self, event: LearningProfileEvent) -> bool:
        score = self._score_from_event(event)
        payload = event.event_payload or {}
        if isinstance(payload.get("passed"), bool):
            return not bool(payload["passed"])
        return score is not None and score < 0.75

    def _is_passed_event(self, event: LearningProfileEvent, score: float | None) -> bool:
        payload = event.event_payload or {}
        if isinstance(payload.get("passed"), bool):
            return bool(payload["passed"])
        return score is not None and score >= 0.75

    def _confidence_delta(self, event: LearningProfileEvent, score: float | None) -> float:
        if event.evidence_strength == "strong":
            return 0.04 if score is None or score >= 0.75 else -0.05
        if event.evidence_strength == "medium":
            return 0.02 if score is None or score >= 0.75 else -0.02
        return 0.01

    def _evidence_strength(self, event_type: str) -> str:
        if event_type in self.STRONG_EVENTS:
            return "strong"
        if event_type in self.MEDIUM_EVENTS:
            return "medium"
        if event_type == "path_replanned":
            return "system"
        return "weak"

    def _mastery_status(self, score: float | None) -> str:
        if score is None:
            return "not_started"
        if score < 0.6:
            return "severe_weak"
        if score < 0.75:
            return "basic"
        if score < 0.9:
            return "good"
        return "proficient"

    def _risk(self, profile: dict[str, Any], signal: str) -> dict[str, Any]:
        risk = dict(profile.get("learning_risk") or {})
        signals = self._list(risk.get("signals"))
        if signal not in signals:
            signals.append(signal)
        risk["signals"] = signals[-10:]
        risk["level"] = "high" if len(risk["signals"]) >= 3 else "watch"
        return risk

    def _update_reason(self, event: LearningProfileEvent, score: float | None, topic: str) -> str:
        if event.event_type == "assessment_submitted":
            state = "已通过" if score is not None and score >= 0.75 else "未通过"
            return f"{topic} 综合评估{state}，得分 {score}。"
        if event.event_type == "mind_map_interacted":
            return f"{topic} 的思维导图交互已更新资源模态有效性。"
        if event.event_type == "code_attempt_run":
            return f"{topic} 的代码练习已更新编程能力证据。"
        return f"{topic} 的 {event.event_type} 学习行为已更新课程画像。"

    def _profile_summary(self, profile: dict[str, Any]) -> str:
        weak = "、".join(self._list(profile.get("weak_points"))[:4]) or "暂无明显薄弱点"
        strong = "、".join(self._list(profile.get("strong_points"))[:3]) or "仍在积累证据"
        resources = "、".join(self._list(profile.get("preferred_resource_order"))[:4]) or "综合资源"
        goal = str(profile.get("course_goal") or profile.get("learning_goal") or "完成课程学习")
        time = str(profile.get("time_preference") or "学习时间偏好待确认")
        return (
            f"该学生当前目标是{goal}。当前薄弱点：{weak}。优势方向：{strong}。"
            f"更有效的资源形式偏向：{resources}。学习时间规律：{time}。"
        )

    def _code_misconception(self, topic: str, detail: str) -> str:
        text = f"{topic} {detail}".lower()
        if "boundary" in text or "range" in text:
            return f"{topic}: 循环边界或 range 使用误区"
        if "type" in text:
            return f"{topic}: 类型转换误区"
        if "parameter" in text or "argument" in text:
            return f"{topic}: 函数参数误区"
        return f"{topic}: 代码调试误区"

    def _resource_type_for_event(self, event_type: str) -> str:
        return {
            "mind_map_interacted": "mind_map",
            "document_viewed": "document",
            "openmaic_classroom_viewed": "openmaic_classroom",
        }.get(event_type, "")

    def _list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return list(value)
        if value in (None, ""):
            return []
        return [value]

    def _truncate(self, value: str, length: int) -> str:
        return (value or "")[:length]
