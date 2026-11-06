from __future__ import annotations

import json

from app.models.assessment import AssessmentReport, ComprehensiveAssessmentSubmit, LearningEvent
from app.models.profile import StudentProfile


class EvaluatorAgent:
    name = "学习评估Agent"
    pass_threshold = 0.75
    quiz_answer_key = {
        "concept": 1,
        "transfer": 1,
        "debugging": 1,
    }

    def evaluate(self, profile: StudentProfile, events: list[LearningEvent]) -> AssessmentReport:
        mastery: dict[str, float] = {}
        weak_points = list(profile.weak_points)
        for event in events:
            if event.score is not None:
                mastery[event.topic] = event.score
                if event.score < 0.6 and event.topic not in weak_points:
                    weak_points.append(event.topic)
        next_adjustment = "复习薄弱知识点，并优先推荐图解、动画和基础练习。"
        return AssessmentReport(
            student_id=profile.student_id,
            mastery=mastery,
            weak_points=weak_points,
            next_adjustment=next_adjustment,
        )

    def evaluate_comprehensive(
        self,
        profile: StudentProfile,
        payload: ComprehensiveAssessmentSubmit,
    ) -> AssessmentReport:
        quiz_score = self._quiz_score(payload)
        code_score = self._code_score(payload)
        classroom_score = 1.0 if payload.classroom_completed else 0.0
        behavior_score = self._behavior_score(payload)
        if self._is_wrong_question_redo(payload):
            classroom_score = 1.0
            behavior_score = 1.0
            final_score = self._round_score(quiz_score * 0.55 + code_score * 0.45)
        else:
            final_score = self._round_score(
                classroom_score * 0.15 +
                quiz_score * 0.30 +
                code_score * 0.35 +
                behavior_score * 0.20
            )
        passed = final_score >= self.pass_threshold and code_score >= 0.6
        weak_points = list(profile.weak_points)
        if not passed and payload.topic not in weak_points:
            weak_points.append(payload.topic)
        elif passed and final_score >= 0.9:
            weak_points = [item for item in weak_points if item != payload.topic]

        return AssessmentReport(
            student_id=payload.student_id or profile.student_id,
            mastery={payload.topic: final_score},
            weak_points=weak_points,
            next_adjustment=(
                "已通过本节学习，回到主线任务继续下一个知识点。"
                if passed
                else "未达到通过标准，系统将围绕薄弱维度重新规划补救任务。"
            ),
            dimension_scores={
                "classroom": classroom_score,
                "quiz": quiz_score,
                "code": code_score,
                "behavior": behavior_score,
            },
            final_score=final_score,
            passed=passed,
            mastery_status=self._mastery_status(final_score),
            feedback=self._feedback(payload, quiz_score, code_score, behavior_score, classroom_score, passed),
        )

    def _quiz_score(self, payload: ComprehensiveAssessmentSubmit) -> float:
        total_weight = sum(max(0, item.weight) for item in payload.quiz_answers)
        if total_weight <= 0:
            return 0.0
        earned = sum(max(0, item.weight) for item in payload.quiz_answers if self._quiz_answer_is_correct(item))
        return self._round_score(earned / total_weight)

    def _quiz_answer_is_correct(self, item) -> bool:
        if item.correct_answer_index is not None:
            return item.selected_answer_index == item.correct_answer_index
        expected_index = self.quiz_answer_key.get(item.id)
        if expected_index is None:
            return False
        return item.selected_answer_index == expected_index

    def _code_score(self, payload: ComprehensiveAssessmentSubmit) -> float:
        attempt = payload.code_attempt
        if attempt is None:
            return 0.0
        # 服务端沙箱真实判分优先：verdict 由 /code/run 生成，前端无法伪造
        server_verdict = (attempt.server_verdict or "").strip().lower()
        if server_verdict:
            penalty = min(max(attempt.attempts - 1, 0) * 0.08, 0.24)
            if server_verdict == "accepted":
                return self._round_score(max(0.76, 1.0 - penalty))
            if server_verdict == "wrong_answer":
                return self._round_score(0.25 if attempt.code.strip() else 0.0)
            # compile_error / runtime_error / timeout：至少写了代码给基础分
            return self._round_score(0.2 if attempt.code.strip() else 0.0)
        if self._code_output_matches(attempt.expected_output, attempt.actual_output):
            penalty = min(max(attempt.attempts - 1, 0) * 0.08, 0.24)
            return self._round_score(max(0.76, 1.0 - penalty))
        has_code = bool(attempt.code.strip())
        output_similarity = (
            0.25
            if attempt.expected_output and attempt.actual_output and attempt.expected_output in attempt.actual_output
            else 0
        )
        return self._round_score((0.25 if has_code else 0) + output_similarity)

    def _code_output_matches(self, expected_output: str, actual_output: str) -> bool:
        expected = (expected_output or "").strip()
        actual = (actual_output or "").strip()
        if not expected:
            return False
        return actual == expected

    def _behavior_score(self, payload: ComprehensiveAssessmentSubmit) -> float:
        completed = [
            payload.notes_completed,
            payload.mind_map_completed,
            payload.code_lab_completed,
        ]
        return self._round_score(sum(1 for item in completed if item) / len(completed))

    def _is_wrong_question_redo(self, payload: ComprehensiveAssessmentSubmit) -> bool:
        if "wrong_question_redo" in payload.detail:
            return True
        try:
            detail = json.loads(payload.detail or "{}")
        except json.JSONDecodeError:
            return False
        return isinstance(detail, dict) and detail.get("assessment_type") == "wrong_question_redo"

    def _feedback(
        self,
        payload: ComprehensiveAssessmentSubmit,
        quiz_score: float,
        code_score: float,
        behavior_score: float,
        classroom_score: float,
        passed: bool,
    ) -> list[str]:
        feedback = []
        if classroom_score < 1:
            feedback.append("课堂学习未完整完成，建议先补完 OpenMAIC 课堂。")
        if quiz_score < 0.75:
            wrong_dimensions = [item.dimension for item in payload.quiz_answers if not self._quiz_answer_is_correct(item)]
            feedback.append(f"选择题薄弱维度：{'、'.join(wrong_dimensions) if wrong_dimensions else '概念理解'}。")
        if code_score < 0.6:
            feedback.append("编程题未通过，需要继续完成可运行代码并匹配预期输出。")
        if behavior_score < 1:
            feedback.append("文档、思维导图或代码练习尚未全部完成，学习行为证据不足。")
        if passed:
            feedback.append("综合表现达到通过标准，可进入下一知识点。")
        return feedback

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

    def _round_score(self, score: float) -> float:
        return round(max(0.0, min(1.0, score)), 4)
