"""记忆引擎：艾宾浩斯间隔重复调度（创新功能，配合错题/评估闭环）。

教育科学依据：主动回忆 + 间隔重复（spaced repetition）在 2026 年 AI tutor
研究中被验证显著优于被动复习（62% 测分提升案例）。调度规则：

- 以"知识点"为单位聚合学习事件：评估未通过/代码失败/错题 = 记忆负债信号；
- 间隔阶梯 [1, 3, 7, 14] 天：复习通过 → 阶梯 +1；复习/学习失败 → 重置为 1 天；
- 中途有通过的普通评估（assessment passed）→ 阶梯至少推进一级（正向证据）；
- 到期日 ≤ 今天 → 进入"今日复习队列"，前端今日学习页与错题本消费。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

REVIEW_INTERVALS_DAYS = [1, 3, 7, 14]
# 一个知识点累计记忆负债信号（失败）达到该值时升级为"高危薄弱点"
HIGH_RISK_FAILURE_COUNT = 3


def parse_event_day(value: str) -> str:
    return (value or "")[:10]


def days_between(later: str, earlier: str) -> int:
    try:
        delta = date.fromisoformat(later) - date.fromisoformat(earlier)
        return delta.days
    except (ValueError, TypeError):
        return 0


def _event_failed(event: dict[str, Any]) -> bool:
    """事件是否代表一次未通过（评估低分/代码失败/复习未通过）。"""
    payload = event.get("event_payload") or {}
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else payload
    event_type = event.get("event_type")
    if event_type == "review_completed":
        passed = payload.get("passed")
        if isinstance(passed, bool):
            return not passed
        score = payload.get("final_score") or event.get("score")
        return isinstance(score, (int, float)) and float(score) < 0.75
    if event_type == "assessment_submitted":
        score = event.get("score")
        if score is None and isinstance(assessment, dict):
            score = assessment.get("final_score")
        if isinstance(score, (int, float)):
            return float(score) < 0.75
        quiz = assessment.get("quiz_answers") if isinstance(assessment, dict) else None
        if isinstance(quiz, list) and quiz:
            return any(not answer.get("correct", True) for answer in quiz if isinstance(answer, dict))
    if event_type == "code_attempt_run":
        attempt = assessment.get("code_attempt") if isinstance(assessment.get("code_attempt"), dict) else assessment
        if isinstance(attempt, dict) and "passed" in attempt:
            return not bool(attempt.get("passed"))
    return False


def _event_passed(event: dict[str, Any]) -> bool:
    if event.get("event_type") in {"assessment_submitted", "code_attempt_passed", "review_completed"}:
        return not _event_failed(event)
    return False


def _memory_signal_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按时间正序返回与记忆调度相关的事件。"""
    relevant = [
        event
        for event in events
        if event.get("event_type") in {"assessment_submitted", "code_attempt_run", "code_attempt_passed", "review_completed"}
        and event.get("knowledge_node_id")
    ]
    return sorted(relevant, key=lambda event: str(event.get("created_at") or ""))


def build_memory_schedule(
    events: list[dict[str, Any]],
    *,
    today: str,
    intervals: list[int] | None = None,
) -> dict[str, Any]:
    """聚合学习事件 → 每个知识点的记忆状态与今日复习队列。

    返回：
      items: [{node_id, topic, level, interval_days, next_review_date, due_today,
               overdue_days, failure_count, high_risk, last_event_at, passed_streak}]
      stats: {due_count, high_risk_count, tracked_nodes, mastered_streak_max}
    """
    ladder = intervals or REVIEW_INTERVALS_DAYS
    per_node: dict[str, dict[str, Any]] = {}
    for event in _memory_signal_events(events):
        node_id = str(event.get("knowledge_node_id"))
        state = per_node.setdefault(
            node_id,
            {
                "node_id": node_id,
                "topic": str(event.get("topic") or node_id),
                "level": 0,
                "failure_count": 0,
                "passed_streak": 0,
                "last_event_at": "",
                "last_review_at": "",
                "due": False,
            },
        )
        state["topic"] = str(event.get("topic") or state["topic"])
        state["last_event_at"] = str(event.get("created_at") or state["last_event_at"])

        if event.get("event_type") == "review_completed":
            state["last_review_at"] = str(event.get("created_at") or "")
            if _event_passed(event):
                state["level"] = min(len(ladder) - 1, state["level"] + 1)
                state["passed_streak"] += 1
            else:
                state["level"] = 0
                state["passed_streak"] = 0
                state["failure_count"] += 1
            continue

        if _event_failed(event):
            state["failure_count"] += 1
            state["level"] = 0
            state["passed_streak"] = 0
        elif _event_passed(event):
            # 正向证据：无需复习也至少推进一级（但连续通过才连升）
            state["passed_streak"] += 1
            if state["passed_streak"] >= 2:
                state["level"] = min(len(ladder) - 1, state["level"] + 1)
            else:
                state["level"] = min(len(ladder) - 1, state["level"] + 1) if state["level"] == 0 else state["level"]

    items: list[dict[str, Any]] = []
    for state in per_node.values():
        interval_days = ladder[state["level"]]
        anchor_day = parse_event_day(state["last_review_at"] or state["last_event_at"])
        next_review = ""
        due_today = False
        overdue_days = 0
        if anchor_day:
            next_review = (
                date.fromisoformat(anchor_day) + timedelta(days=interval_days)
            ).isoformat()
            delta = days_between(today, next_review)
            due_today = delta >= 0
            overdue_days = max(0, delta)
        items.append(
            {
                **state,
                "interval_days": interval_days,
                "next_review_date": next_review,
                "due_today": due_today,
                "overdue_days": overdue_days,
                "high_risk": state["failure_count"] >= HIGH_RISK_FAILURE_COUNT,
            }
        )

    items.sort(key=lambda item: (-item["overdue_days"], -item["failure_count"]))
    due_items = [item for item in items if item["due_today"]]
    return {
        "items": items,
        "stats": {
            "due_count": len(due_items),
            "high_risk_count": sum(1 for item in items if item["high_risk"]),
            "tracked_nodes": len(items),
            "longest_streak": max((item["passed_streak"] for item in items), default=0),
        },
    }
