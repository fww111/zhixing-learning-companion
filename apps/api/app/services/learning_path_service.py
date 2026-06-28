from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import KnowledgeNodeMastery
from app.models.learning_path import CourseLearningPath, CourseLearningStage
from app.models.profile import StudentProfile
from app.models.profile_record import StudentProfileRecord
from app.models.resource import ResourceType
from app.models.user import UserRead
from app.services.course_service import CourseService


class LearningPathProfileMissingError(RuntimeError):
    pass


class LearningPathGraphMissingError(RuntimeError):
    pass


class LearningPathService:
    PASS_THRESHOLD = 0.75
    WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    def __init__(self, db: Session, course_service: CourseService | None = None) -> None:
        self.db = db
        self.course_service = course_service or CourseService(db)

    def plan_course_path(
        self,
        user: UserRead,
        course_id: int,
        max_nodes: int = 18,
        plan_type: str = "main",
        focus_node_id: str = "",
        chapter_id: str = "",
    ) -> CourseLearningPath:
        profile = self._profile(user.id, course_id)
        graph = self.course_service.get_knowledge_graph(user.id, course_id)
        nodes = [
            node
            for node in graph.get("nodes", [])
            if str(node.get("id", "")) and int(node.get("level") or 0) > 0
        ]
        if not nodes:
            raise LearningPathGraphMissingError("knowledge graph is empty")

        edges = graph.get("edges", [])
        children_by_parent = self._children_by_parent(nodes, edges)
        parent_by_child = self._parent_by_child(nodes, children_by_parent)
        mastery = self._mastery(user.id, course_id)
        normalized_plan_type = "remedial" if plan_type == "remedial" else "main"
        time_plan = self._time_plan(profile)
        ranked = self._rank_nodes(nodes, edges, mastery, profile, children_by_parent)
        if normalized_plan_type == "remedial":
            focus_dependency_ids = self._remedial_dependency_ids(
                nodes,
                edges,
                focus_node_id,
                mastery,
                children_by_parent,
            )
            if not focus_dependency_ids:
                focus_dependency_ids = self._focus_dependency_ids(nodes, edges, mastery, profile, children_by_parent=children_by_parent)
            active_chapter = self._chapter_for_focus(nodes, focus_node_id, parent_by_child)
            ordered = self._remedial_ordered_nodes(
                ranked,
                nodes,
                active_chapter,
                focus_node_id,
                focus_dependency_ids,
                children_by_parent,
            )
        else:
            focus_node_id = ""
            focus_dependency_ids = self._focus_dependency_ids(nodes, edges, mastery, profile, children_by_parent=children_by_parent)
            ordered, active_chapter = self._active_chapter_nodes(ranked, nodes, mastery, chapter_id, children_by_parent)
        learning_nodes = [node for node in ordered if self._is_learning_task_node(node, children_by_parent)]
        stages = [self._stage(node, mastery, profile, focus_dependency_ids) for node in learning_nodes[:max_nodes]]
        stages = self._insert_assessment_remedial_stages(stages, mastery, profile, max_nodes)
        for stage in stages:
            if stage.node_id in focus_dependency_ids:
                stage.is_remedial = True
        self._apply_schedule(stages, time_plan)
        current_stage_id = self._current_stage_id(stages, normalized_plan_type, focus_node_id)
        self._mark_stage_statuses(stages, current_stage_id, normalized_plan_type)
        planned_minutes = sum(stage.scheduled_minutes for stage in stages if stage.is_minimum_task)
        return CourseLearningPath(
            student_id=profile.student_id,
            course_id=course_id,
            plan_type=normalized_plan_type,
            focus_node_id=focus_node_id if normalized_plan_type == "remedial" else "",
            current_stage_id=current_stage_id,
            pass_threshold=self.PASS_THRESHOLD,
            is_dynamic=True,
            adjustment_basis=self._adjustment_basis(normalized_plan_type, time_plan),
            weekly_time_budget_minutes=time_plan["weekly_minutes"],
            planned_minutes=planned_minutes,
            minimum_task_count=sum(1 for stage in stages if stage.is_minimum_task),
            stretch_task_count=sum(1 for stage in stages if stage.is_stretch_task),
            schedule_days=time_plan["days"],
            schedule_summary=self._schedule_summary(time_plan, stages),
            active_chapter_id=str(active_chapter.get("id") or ""),
            active_chapter_title=self._display_node_name(str(active_chapter.get("name") or "")),
            chapters=self._chapter_options(nodes, mastery, active_chapter, children_by_parent),
            stages=stages,
        )

    def _profile(self, user_id: int, course_id: int) -> StudentProfile:
        record = self.db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == user_id,
                StudentProfileRecord.course_id == course_id,
            )
        )
        if record is None:
            raise LearningPathProfileMissingError("confirmed course profile is required")
        return StudentProfile(**record.profile_data)

    def _mastery(self, user_id: int, course_id: int) -> dict[str, KnowledgeNodeMastery]:
        rows = self.db.scalars(
            select(KnowledgeNodeMastery).where(
                KnowledgeNodeMastery.user_id == user_id,
                KnowledgeNodeMastery.course_id == course_id,
            )
        )
        return {row.node_id: row for row in rows}

    def _rank_nodes(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        mastery: dict[str, KnowledgeNodeMastery],
        profile: StudentProfile,
        children_by_parent: dict[str, set[str]] | None = None,
    ) -> list[dict[str, Any]]:
        by_id = {str(node["id"]): node for node in nodes}
        incoming: dict[str, int] = defaultdict(int)
        outgoing: dict[str, list[str]] = defaultdict(list)
        for node_id in by_id:
            incoming.setdefault(node_id, 0)
        dependency_parents: dict[str, set[str]] = defaultdict(set)
        children_by_parent = children_by_parent or self._children_by_parent(nodes, edges)
        hierarchy_order = self._hierarchy_order(nodes, children_by_parent)

        for edge in edges:
            if edge.get("relation_type") != "prerequisite":
                continue
            source = str(edge.get("source_node_id") or "")
            target = str(edge.get("target_node_id") or "")
            if source not in by_id or target not in by_id:
                continue
            if int(by_id[source].get("level") or 0) == 1 and int(by_id[target].get("level") or 0) == 1:
                continue
            outgoing[source].append(target)
            incoming[target] += 1
            incoming.setdefault(source, 0)
            dependency_parents[target].add(source)

        for parent_id, child_ids in children_by_parent.items():
            if parent_id not in by_id:
                continue
            for child_id in child_ids:
                if child_id not in by_id:
                    continue
                outgoing[parent_id].append(child_id)
                incoming[child_id] += 1
                incoming.setdefault(parent_id, 0)
                dependency_parents[child_id].add(parent_id)

        focus_dependency_ids = self._focus_dependency_ids(
            nodes,
            edges,
            mastery,
            profile,
            dependency_parents,
            children_by_parent,
        )
        ready = [node_id for node_id, count in incoming.items() if count == 0]
        result: list[dict[str, Any]] = []
        emitted: set[str] = set()
        while ready:
            ready.sort(
                key=lambda node_id: (
                    hierarchy_order.get(node_id, 10**9),
                    self._sort_key(by_id[node_id]),
                    -self._priority(by_id[node_id], mastery, profile, focus_dependency_ids),
                )
            )
            node_id = ready.pop(0)
            if node_id in emitted:
                continue
            emitted.add(node_id)
            result.append(by_id[node_id])
            for target in outgoing[node_id]:
                incoming[target] -= 1
                if incoming[target] == 0:
                    ready.append(target)

        remaining = [node for node_id, node in by_id.items() if node_id not in emitted]
        return result + sorted(
            remaining,
            key=lambda node: (
                hierarchy_order.get(str(node["id"]), 10**9),
                self._sort_key(node),
                -self._priority(node, mastery, profile, focus_dependency_ids),
            ),
        )

    def _focus_dependency_ids(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        mastery: dict[str, KnowledgeNodeMastery],
        profile: StudentProfile,
        dependency_parents: dict[str, set[str]] | None = None,
        children_by_parent: dict[str, set[str]] | None = None,
    ) -> set[str]:
        by_id = {str(node["id"]): node for node in nodes}
        parents = dependency_parents or defaultdict(set)
        children_by_parent = children_by_parent or self._children_by_parent(nodes, edges)
        if dependency_parents is None:
            for edge in edges:
                if edge.get("relation_type") != "prerequisite":
                    continue
                source = str(edge.get("source_node_id") or "")
                target = str(edge.get("target_node_id") or "")
                if source in by_id and target in by_id:
                    if int(by_id[source].get("level") or 0) == 1 and int(by_id[target].get("level") or 0) == 1:
                        continue
                    parents[target].add(source)
            for parent_id, child_ids in children_by_parent.items():
                if parent_id not in by_id:
                    continue
                for child_id in child_ids:
                    if child_id in by_id:
                        parents[child_id].add(parent_id)

        focus_ids: set[str] = set()
        for node in nodes:
            node_id = str(node["id"])
            has_profile_focus = self._matches_profile_focus(node, profile)
            has_weak_mastery = node_id in mastery and mastery[node_id].mastery_status in {"severe_weak", "basic"}
            if not (has_profile_focus or has_weak_mastery):
                continue
            if self._is_learning_task_node(node, children_by_parent):
                focus_ids.add(node_id)
                continue
            for descendant_id in self._descendant_ids(node_id, children_by_parent):
                descendant = by_id.get(descendant_id)
                if descendant and self._is_learning_task_node(descendant, children_by_parent):
                    focus_ids.add(descendant_id)
        focused = set(focus_ids)
        stack = list(focus_ids)
        while stack:
            node_id = stack.pop()
            for parent_id in parents.get(node_id, set()):
                if parent_id not in focused:
                    focused.add(parent_id)
                    stack.append(parent_id)
        return focused

    def _dependency_parents(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        children_by_parent: dict[str, set[str]] | None = None,
    ) -> dict[str, set[str]]:
        by_id = {str(node["id"]): node for node in nodes}
        parents: dict[str, set[str]] = defaultdict(set)
        children_by_parent = children_by_parent or self._children_by_parent(nodes, edges)
        for edge in edges:
            if edge.get("relation_type") != "prerequisite":
                continue
            source = str(edge.get("source_node_id") or "")
            target = str(edge.get("target_node_id") or "")
            if source not in by_id or target not in by_id:
                continue
            if int(by_id[source].get("level") or 0) == 1 and int(by_id[target].get("level") or 0) == 1:
                continue
            parents[target].add(source)
        for parent_id, child_ids in children_by_parent.items():
            if parent_id not in by_id:
                continue
            for child_id in child_ids:
                if child_id in by_id:
                    parents[child_id].add(parent_id)
        return parents

    def _children_by_parent(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> dict[str, set[str]]:
        node_ids = {str(node["id"]) for node in nodes}
        children: dict[str, set[str]] = defaultdict(set)
        for node in nodes:
            node_id = str(node["id"])
            parent_id = str(node.get("parent_id") or "")
            if parent_id and parent_id in node_ids and node_id != parent_id:
                children[parent_id].add(node_id)
        for edge in edges:
            if str(edge.get("relation_type") or "") != "contains":
                continue
            parent_id = str(edge.get("source_node_id") or edge.get("source") or "")
            child_id = str(edge.get("target_node_id") or edge.get("target") or "")
            if parent_id in node_ids and child_id in node_ids and parent_id != child_id:
                children[parent_id].add(child_id)
        return children

    def _parent_by_child(
        self,
        nodes: list[dict[str, Any]],
        children_by_parent: dict[str, set[str]],
    ) -> dict[str, str]:
        parents: dict[str, str] = {}
        by_id = {str(node["id"]): node for node in nodes}
        for node in nodes:
            node_id = str(node["id"])
            parent_id = str(node.get("parent_id") or "")
            if parent_id in by_id:
                parents[node_id] = parent_id
        for parent_id, child_ids in children_by_parent.items():
            if parent_id not in by_id:
                continue
            for child_id in child_ids:
                if child_id in by_id:
                    parents.setdefault(child_id, parent_id)
        return parents

    def _hierarchy_order(
        self,
        nodes: list[dict[str, Any]],
        children_by_parent: dict[str, set[str]],
    ) -> dict[str, int]:
        by_id = {str(node["id"]): node for node in nodes}
        parent_by_child = self._parent_by_child(nodes, children_by_parent)
        roots = [
            node
            for node_id, node in by_id.items()
            if parent_by_child.get(node_id, "") not in by_id
        ]
        order: dict[str, int] = {}

        def visit(node_id: str) -> None:
            if node_id in order or node_id not in by_id:
                return
            order[node_id] = len(order)
            children = [
                by_id[child_id]
                for child_id in children_by_parent.get(node_id, set())
                if child_id in by_id
            ]
            for child in sorted(children, key=self._sort_key):
                visit(str(child["id"]))

        for root in sorted(roots, key=self._sort_key):
            visit(str(root["id"]))
        for node in sorted(by_id.values(), key=self._sort_key):
            visit(str(node["id"]))
        return order

    def _descendant_ids(
        self,
        root_id: str,
        children_by_parent: dict[str, set[str]],
    ) -> set[str]:
        descendants: set[str] = set()
        stack = list(children_by_parent.get(root_id, set()))
        while stack:
            node_id = stack.pop()
            if node_id in descendants:
                continue
            descendants.add(node_id)
            stack.extend(children_by_parent.get(node_id, set()))
        return descendants

    def _remedial_dependency_ids(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        focus_node_id: str,
        mastery: dict[str, KnowledgeNodeMastery],
        children_by_parent: dict[str, set[str]] | None = None,
    ) -> set[str]:
        by_id = {str(node["id"]): node for node in nodes}
        if focus_node_id not in by_id:
            return set()
        children_by_parent = children_by_parent or self._children_by_parent(nodes, edges)
        parents = self._dependency_parents(nodes, edges, children_by_parent)
        focused = {focus_node_id}
        stack = [focus_node_id]
        while stack:
            node_id = stack.pop()
            for parent_id in parents.get(node_id, set()):
                if parent_id not in focused:
                    focused.add(parent_id)
                    stack.append(parent_id)

        focus_node = by_id[focus_node_id]
        focus_parent_id = str(focus_node.get("parent_id") or "")
        for node_id, node in by_id.items():
            same_parent = focus_parent_id and str(node.get("parent_id") or "") == focus_parent_id
            status = mastery[node_id].mastery_status if node_id in mastery else "not_started"
            if same_parent and self._is_learning_task_node(node, children_by_parent) and status in {"good", "proficient", "severe_weak", "basic"}:
                focused.add(node_id)
        if not self._is_learning_task_node(focus_node, children_by_parent):
            for node_id in self._descendant_ids(focus_node_id, children_by_parent):
                node = by_id.get(node_id)
                if not node or not self._is_learning_task_node(node, children_by_parent):
                    continue
                status = mastery[node_id].mastery_status if node_id in mastery else "not_started"
                if status in {"severe_weak", "basic", "not_started"}:
                    focused.add(node_id)
        return focused

    def _remedial_ordered_nodes(
        self,
        ranked: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
        active_chapter: dict[str, Any],
        focus_node_id: str,
        focus_dependency_ids: set[str],
        children_by_parent: dict[str, set[str]],
    ) -> list[dict[str, Any]]:
        by_id = {str(node["id"]): node for node in nodes}
        active_chapter_id = str(active_chapter.get("id") or "")
        if not active_chapter_id:
            return [node for node in ranked if str(node["id"]) in focus_dependency_ids] or ranked
        subtree_ids = self._subtree_ids(active_chapter_id, by_id)
        chapter_nodes = [node for node in ranked if str(node["id"]) in subtree_ids]
        if focus_node_id not in by_id:
            return chapter_nodes
        focused_order = [
            node
            for node in chapter_nodes
            if str(node["id"]) in focus_dependency_ids and self._is_learning_task_node(node, children_by_parent)
        ]
        if not focused_order:
            focused_order = [by_id[focus_node_id]]
        emitted = {str(node["id"]) for node in focused_order}
        tail = [
            node
            for node in chapter_nodes
            if str(node["id"]) not in emitted and self._is_learning_task_node(node, children_by_parent)
        ]
        return focused_order + tail

    def _active_chapter_nodes(
        self,
        ranked: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
        mastery: dict[str, KnowledgeNodeMastery],
        requested_chapter_id: str = "",
        children_by_parent: dict[str, set[str]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        children_by_parent = children_by_parent or self._children_by_parent(nodes, [])
        by_id = {str(node["id"]): node for node in nodes}
        chapters = self._chapters(nodes)
        chapter_ids = [str(node["id"]) for node in chapters]
        if requested_chapter_id in by_id and requested_chapter_id in chapter_ids:
            subtree_ids = self._subtree_ids(requested_chapter_id, by_id)
            chapter_ranked = [node for node in ranked if str(node["id"]) in subtree_ids]
            return chapter_ranked or [by_id[requested_chapter_id]], by_id[requested_chapter_id]
        for chapter_id in chapter_ids:
            subtree_ids = self._subtree_ids(chapter_id, by_id)
            if not self._chapter_complete(subtree_ids, by_id, mastery, children_by_parent):
                chapter_ranked = [node for node in ranked if str(node["id"]) in subtree_ids]
                return chapter_ranked or [by_id[chapter_id]], by_id[chapter_id]
        active_chapter = chapters[0] if chapters else {}
        return ranked, active_chapter

    def _chapters(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            [node for node in nodes if int(node.get("level") or 0) == 1],
            key=self._sort_key,
        )

    def _is_learning_task_node(self, node: dict[str, Any], children_by_parent: dict[str, set[str]]) -> bool:
        node_type = str(node.get("node_type") or node.get("type") or "").lower().strip()
        if node_type in {"chapter", "heading", "outline", "root"}:
            return False
        node_id = str(node.get("id") or "").lower()
        if node_id == "course-root" or "-chapter-" in node_id:
            return False
        level = int(node.get("level") or 0)
        return level > 1 and not children_by_parent.get(str(node.get("id") or ""))

    def _chapter_for_focus(
        self,
        nodes: list[dict[str, Any]],
        focus_node_id: str,
        parent_by_child: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        by_id = {str(node["id"]): node for node in nodes}
        node = by_id.get(focus_node_id)
        parent_by_child = parent_by_child or {str(item["id"]): str(item.get("parent_id") or "") for item in nodes}
        while node:
            if int(node.get("level") or 0) == 1:
                return node
            node = by_id.get(parent_by_child.get(str(node.get("id") or ""), ""))
        chapters = self._chapters(nodes)
        return chapters[0] if chapters else {}

    def _chapter_options(
        self,
        nodes: list[dict[str, Any]],
        mastery: dict[str, KnowledgeNodeMastery],
        active_chapter: dict[str, Any],
        children_by_parent: dict[str, set[str]],
    ) -> list[dict[str, str | int | bool]]:
        by_id = {str(node["id"]): node for node in nodes}
        active_id = str(active_chapter.get("id") or "")
        options: list[dict[str, str | int | bool]] = []
        for chapter in self._chapters(nodes):
            chapter_id = str(chapter["id"])
            subtree_ids = self._subtree_ids(chapter_id, by_id)
            learning_ids = self._learning_node_ids(subtree_ids, by_id, children_by_parent)
            completed = sum(
                1
                for node_id in learning_ids
                if mastery.get(node_id) and mastery[node_id].mastery_status in {"good", "proficient"}
            )
            options.append(
                {
                    "id": chapter_id,
                    "title": self._display_node_name(str(chapter.get("name") or chapter_id)),
                    "order": int(chapter.get("order") or 0),
                    "total_nodes": len(learning_ids),
                    "completed_nodes": completed,
                    "is_active": chapter_id == active_id,
                    "is_complete": bool(learning_ids) and completed == len(learning_ids),
                }
            )
        return options

    def _subtree_ids(self, root_id: str, by_id: dict[str, dict[str, Any]]) -> set[str]:
        subtree = {root_id}
        changed = True
        while changed:
            changed = False
            for node_id, node in by_id.items():
                if node_id in subtree:
                    continue
                parent_id = str(node.get("parent_id") or "")
                if parent_id in subtree:
                    subtree.add(node_id)
                    changed = True
        return subtree

    def _chapter_complete(
        self,
        subtree_ids: set[str],
        by_id: dict[str, dict[str, Any]],
        mastery: dict[str, KnowledgeNodeMastery],
        children_by_parent: dict[str, set[str]],
    ) -> bool:
        if not subtree_ids:
            return False
        learning_node_ids = set(self._learning_node_ids(subtree_ids, by_id, children_by_parent))
        target_ids = learning_node_ids or subtree_ids
        return all(mastery.get(node_id) and mastery[node_id].mastery_status in {"good", "proficient"} for node_id in target_ids)

    def _learning_node_ids(
        self,
        subtree_ids: set[str],
        by_id: dict[str, dict[str, Any]],
        children_by_parent: dict[str, set[str]],
    ) -> list[str]:
        return [
            node_id
            for node_id in subtree_ids
            if node_id in by_id and self._is_learning_task_node(by_id[node_id], children_by_parent)
        ]

    def _current_stage_id(self, stages: list[CourseLearningStage], plan_type: str, focus_node_id: str) -> str:
        if plan_type == "remedial" and focus_node_id:
            for stage in stages:
                if stage.node_id == self._assessment_remedial_stage_id(focus_node_id):
                    return stage.node_id
            for stage in stages:
                if stage.node_id == focus_node_id:
                    return stage.node_id
            for stage in stages:
                if stage.mastery_status in {"severe_weak", "basic", "not_started"}:
                    return stage.node_id
        for stage in stages:
            if (
                stage.is_remedial
                and "::remedial::" in stage.node_id
                and stage.mastery_status in {"severe_weak", "basic"}
            ):
                return stage.node_id
        for stage in stages:
            if stage.mastery_status in {"severe_weak", "basic", "not_started"}:
                return stage.node_id
        return stages[0].node_id if stages else ""

    def _insert_assessment_remedial_stages(
        self,
        stages: list[CourseLearningStage],
        mastery: dict[str, KnowledgeNodeMastery],
        profile: StudentProfile,
        max_nodes: int,
    ) -> list[CourseLearningStage]:
        result: list[CourseLearningStage] = []
        for stage in stages:
            result.append(stage)
            if len(result) >= max_nodes:
                break
            remedial_stage = self._assessment_remedial_stage(stage, mastery.get(stage.node_id), profile)
            if remedial_stage is not None:
                result.append(remedial_stage)
                if len(result) >= max_nodes:
                    break
        return result[:max_nodes]

    def _assessment_remedial_stage(
        self,
        source_stage: CourseLearningStage,
        row: KnowledgeNodeMastery | None,
        profile: StudentProfile,
    ) -> CourseLearningStage | None:
        if row is None or row.mastery_status not in {"severe_weak", "basic"}:
            return None
        detail = self._assessment_mastery_detail(row.detail)
        feedback = [
            str(item).strip()
            for item in detail.get("feedback", [])
            if str(item).strip()
        ]
        dimension_scores = detail.get("dimension_scores") if isinstance(detail.get("dimension_scores"), dict) else {}
        weak_items = self._weakness_items(feedback, dimension_scores)
        if not weak_items:
            weak_items = [source_stage.topic]
        topic = f"{source_stage.topic} · 薄弱点专项"
        focus_text = "；".join(weak_items[:3])
        return CourseLearningStage(
            node_id=self._assessment_remedial_stage_id(source_stage.node_id),
            topic=topic,
            level=source_stage.level + 1,
            order=source_stage.order,
            mastery_status=row.mastery_status,
            mastery_score=row.mastery_score,
            priority_score=source_stage.priority_score + 8,
            is_remedial=True,
            estimated_minutes=max(15, min(35, source_stage.estimated_minutes)),
            goal=f"针对{source_stage.topic}评估未达标的薄弱点进行补强：{focus_text}",
            practice_task=f"围绕{focus_text}完成一次专项练习，重新解释错误原因并运行代码验证。",
            graph_basis=[
                f"来源知识点：{source_stage.node_id}",
                "该补救任务不改变知识图谱结构，只在学习路径中插入评估驱动的专项练习。",
                *source_stage.graph_basis,
            ],
            profile_basis=[
                f"评估反馈：{focus_text}",
                f"学生画像资源偏好：{'、'.join(profile.resource_preference) or '综合资源'}",
                *source_stage.profile_basis,
            ],
            recommended_resource_types=[
                ResourceType.DOCUMENT.value,
                ResourceType.MIND_MAP.value,
                ResourceType.EXERCISE.value,
                ResourceType.CODE_LAB.value,
            ],
            recommendation_reason=f"{source_stage.topic}评估未达标，系统根据课堂测试反馈插入薄弱点专项，达标后回到主线学习下一个知识点。",
        )

    def _assessment_remedial_stage_id(self, node_id: str) -> str:
        return f"{node_id}::remedial::assessment-weakness"

    def _assessment_mastery_detail(self, detail: str) -> dict[str, Any]:
        try:
            payload = json.loads(detail or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) and payload.get("assessment_type") == "comprehensive" else {}

    def _weakness_items(self, feedback: list[str], dimension_scores: dict[str, Any]) -> list[str]:
        items = list(feedback)
        dimension_labels = {
            "quiz": "选择题理解维度未达标",
            "code": "编程题输出与要求不一致",
            "behavior": "文档、思维导图或代码练习学习证据不足",
            "classroom": "课堂学习未完整完成",
        }
        for key, label in dimension_labels.items():
            try:
                score = float(dimension_scores.get(key, 1))
            except (TypeError, ValueError):
                continue
            if score < self.PASS_THRESHOLD and label not in items:
                items.append(label)
        return list(dict.fromkeys(items))

    def _mark_stage_statuses(
        self,
        stages: list[CourseLearningStage],
        current_stage_id: str,
        plan_type: str,
    ) -> None:
        current_seen = False
        for stage in stages:
            stage.is_remedial = stage.is_remedial or plan_type == "remedial" or stage.mastery_status in {"severe_weak", "basic"}
            stage.is_current = stage.node_id == current_stage_id
            if stage.is_current:
                stage.path_status = "current"
                current_seen = True
            elif stage.mastery_status in {"good", "proficient"}:
                stage.path_status = "passed"
            elif current_seen:
                stage.path_status = "locked"
                stage.is_locked = True
            else:
                stage.path_status = "open"

    def _adjustment_basis(self, plan_type: str, time_plan: dict[str, Any]) -> list[str]:
        time_basis = (
            f"根据画像时间偏好：{time_plan['schedule_label']}共 {time_plan['weekly_minutes']} 分钟，"
            "本轮按可用日期拆分并控制总时长；当天安排会标记为今日任务，额外时间可继续学习后续关卡。"
        )
        if plan_type == "remedial":
            return [
                "Remedial plan: assessment did not pass, so the path is narrowed to the failed knowledge point.",
                "补救路径优先回看该知识点的章节父节点、前置依赖和同章节薄弱点。",
                "补救评估达标后自动回到主线任务，继续下一个知识点。",
                time_basis,
            ]
        return [
            "主线学习路径只推进当前未完成章节，章节达标后再进入下一章。",
            "根据课程知识图谱的前置关系和目录层级排序。",
            "根据学生画像中的学习目标、薄弱点和资源偏好调整优先级。",
            "根据知识点掌握状态动态前移弱项并降低已精通知识点优先级。",
            time_basis,
        ]

    def _time_plan(self, profile: StudentProfile) -> dict[str, Any]:
        text = f"{profile.time_preference} {' '.join(profile.constraints)}"
        compact_text = re.sub(r"\s+", "", text)
        days = self._schedule_days(compact_text)
        weekly_minutes = self._weekly_minutes(compact_text, days)
        return {
            "days": days,
            "weekly_minutes": weekly_minutes,
            "schedule_label": "周末" if days == ["周六", "周日"] else "、".join(days),
        }

    def _today_label(self) -> str:
        return self.WEEKDAYS[date.today().weekday()]

    def _ordered_schedule_days(self, days: list[str]) -> list[str]:
        today_weekday = date.today().weekday()

        def distance(day: str) -> int:
            try:
                target_weekday = self.WEEKDAYS.index(day)
            except ValueError:
                return 7
            return (target_weekday - today_weekday) % 7

        return sorted(days, key=distance)

    def _schedule_days(self, text: str) -> list[str]:
        lowered = text.lower()
        if any(term in lowered for term in ["workday", "weekday", "mondaytofriday"]):
            return ["周一", "周二", "周三", "周四", "周五"]
        if any(term in text for term in ["工作日", "周一到周五", "周一至周五", "星期一到星期五"]):
            return ["周一", "周二", "周三", "周四", "周五"]
        if any(term in lowered for term in ["daily", "everyday"]):
            return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        if any(term in text for term in ["每天", "每日"]):
            return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        if any(term in lowered for term in ["weekend", "saturday", "sunday"]):
            return ["周六", "周日"]
        if any(term in text for term in ["周末", "週末", "星期六", "星期日", "周六", "周日"]):
            return ["周六", "周日"]
        return ["周一", "周三", "周五"]

    def _weekly_minutes(self, text: str, days: list[str]) -> int:
        lowered = text.lower()
        explicit_week = re.search(r"(?:每周|一周|每星期|weekly)(\d+(?:\.\d+)?)(?:小时|hour|hours|h)", lowered)
        if explicit_week:
            return max(15, int(float(explicit_week.group(1)) * 60))
        explicit_week_minutes = re.search(r"(?:每周|一周|每星期|weekly)(\d+)(?:分钟|minute|minutes|min)", lowered)
        if explicit_week_minutes:
            return max(15, int(explicit_week_minutes.group(1)))
        if "一周1小时" in text or "每周1小时" in text or "weekly1hour" in lowered:
            return 60
        daily_hours = re.search(r"(?:每天|每日|daily|everyday)(\d+(?:\.\d+)?)(?:小时|hour|hours|h)", lowered)
        if daily_hours:
            return max(15, int(float(daily_hours.group(1)) * 60 * len(days)))
        daily_minutes = re.search(r"(?:每天|每日|daily|everyday)(\d+)(?:分钟|minute|minutes|min)", lowered)
        if daily_minutes:
            return max(15, int(daily_minutes.group(1)) * len(days))
        generic_hours = re.search(r"(\d+(?:\.\d+)?)(?:小时|hour|hours|h)", lowered)
        if generic_hours:
            minutes = int(float(generic_hours.group(1)) * 60)
            return max(15, minutes if len(days) <= 2 else minutes * len(days))
        generic_minutes = re.search(r"(\d+)(?:分钟|minute|minutes|min)", lowered)
        if generic_minutes:
            minutes = int(generic_minutes.group(1))
            return max(15, minutes if len(days) <= 2 else minutes * len(days))
        return 45 * len(days)

    def _apply_schedule(self, stages: list[CourseLearningStage], time_plan: dict[str, Any]) -> None:
        if not stages:
            return
        remaining = int(time_plan["weekly_minutes"])
        days = self._ordered_schedule_days(list(time_plan["days"]) or ["周一"])
        scheduled_stages = stages
        if remaining > 0:
            scheduled_stages = []
            tight_day_budget = remaining <= len(days) * 45
            for stage in stages:
                if remaining <= 0:
                    break
                if tight_day_budget and len(scheduled_stages) >= len(days):
                    break
                scheduled_stages.append(stage)
                remaining -= max(1, stage.estimated_minutes)
            if not scheduled_stages:
                scheduled_stages = [stages[0]]

        total_budget = int(time_plan["weekly_minutes"])
        if total_budget <= len(days) * 45 and scheduled_stages:
            base_minutes = max(5, total_budget // len(scheduled_stages))
            extra_minutes = total_budget % len(scheduled_stages)
            for index, stage in enumerate(scheduled_stages):
                stage.scheduled_day = days[index % len(days)]
                stage.scheduled_minutes = base_minutes + (1 if index < extra_minutes else 0)
            self._mark_task_types(stages, scheduled_stages, days)
            return

        remaining = total_budget
        for index, stage in enumerate(scheduled_stages):
            if remaining <= 0:
                break
            slots_left = len(scheduled_stages) - index
            planned = remaining if slots_left <= 1 else max(5, min(stage.estimated_minutes, remaining - 5 * (slots_left - 1)))
            stage.scheduled_day = days[index % len(days)]
            stage.scheduled_minutes = planned
            remaining -= planned
        self._mark_task_types(stages, scheduled_stages, days)

    def _mark_task_types(
        self,
        stages: list[CourseLearningStage],
        scheduled_stages: list[CourseLearningStage],
        days: list[str],
    ) -> None:
        minimum_ids = {stage.node_id for stage in scheduled_stages}
        slot_index_by_id = {stage.node_id: index for index, stage in enumerate(scheduled_stages)}
        continuation_index = len(scheduled_stages)
        for stage in stages:
            if stage.node_id in minimum_ids:
                stage.task_type = "minimum"
                stage.is_minimum_task = True
                stage.is_stretch_task = False
                slot_index = slot_index_by_id.get(stage.node_id, 0)
            else:
                stage.task_type = "stretch"
                stage.is_minimum_task = False
                stage.is_stretch_task = True
                stage.scheduled_day = days[continuation_index % len(days)]
                stage.scheduled_minutes = stage.scheduled_minutes or self._continuation_minutes(days)
                slot_index = continuation_index
                continuation_index += 1
            self._apply_schedule_label(stage, days, slot_index)

    def _continuation_minutes(self, days: list[str]) -> int:
        if len(days) <= 2:
            return max(15, 60 // max(len(days), 1))
        return 45

    def _apply_schedule_label(self, stage: CourseLearningStage, days: list[str], slot_index: int) -> None:
        if stage.scheduled_day:
            stage.scheduled_date = self._date_for_slot(stage.scheduled_day, days, slot_index).isoformat()
        stage.is_today_task = bool(stage.scheduled_date) and stage.scheduled_date == date.today().isoformat()
        if stage.is_today_task:
            stage.schedule_label = "今日任务"
        elif stage.scheduled_day:
            stage.schedule_label = f"{stage.scheduled_day}任务"
        else:
            stage.schedule_label = "后续任务"

    def _date_for_slot(self, day: str, days: list[str], slot_index: int) -> date:
        today = date.today()
        try:
            target_weekday = self.WEEKDAYS.index(day)
        except ValueError:
            return today
        days_ahead = (target_weekday - today.weekday()) % 7
        week_offset = (slot_index // max(len(days), 1)) * 7
        return today + timedelta(days=days_ahead + week_offset)

    def _schedule_summary(self, time_plan: dict[str, Any], stages: list[CourseLearningStage]) -> str:
        planned = sum(stage.scheduled_minutes for stage in stages if stage.is_minimum_task)
        follow_up_count = sum(1 for stage in stages if stage.is_stretch_task)
        if not stages:
            return f"{time_plan['schedule_label']}可用 {time_plan['weekly_minutes']} 分钟，本轮暂无可规划任务。"
        return (
            f"{time_plan['schedule_label']}可用 {time_plan['weekly_minutes']} 分钟，"
            f"已按画像安排 {planned} 分钟，任务分布在{'、'.join(time_plan['days'])}；"
            f"今日任务需当天完成，完成后可继续学习 {follow_up_count} 个后续关卡。"
        )

    def _display_node_name(self, name: str) -> str:
        text = re.sub(r"\s+", " ", name).strip()
        chapter_match = re.match(r"^(第\s*\d+\s*章)\s+(.+)$", text)
        if chapter_match:
            title = self._clean_display_title(chapter_match.group(2))
            return f"{chapter_match.group(1)} {title}".strip()
        section_match = re.match(r"^(\d{1,2}(?:\.\d{1,2}){1,3})\s+(.+)$", text)
        if section_match:
            title = self._clean_display_title(section_match.group(2))
            return f"{section_match.group(1)} {title}".strip()
        return text

    def _clean_display_title(self, value: str) -> str:
        value = value.replace("……", " ... ").replace("…", " ... ")
        value = re.split(
            r"\s*(?:\.{2,}|[-—]+)\s*\d{1,4}\s+(?=上机实验|实验|习题|第\s*\d+\s*章|\d{1,2}(?:\.\d{1,2}){1,3}\b)",
            value,
            maxsplit=1,
        )[0]
        value = re.sub(r"\s*(?:\.{2,}|[-—]+)\s*\d{1,4}\s*$", "", value)
        value = re.sub(r"\s+\d{1,4}\s*$", "", value)
        return value.strip(" .·-—：；;")

    def _matches_profile_focus(self, node: dict[str, Any], profile: StudentProfile) -> bool:
        name = str(node.get("name") or "")
        summary = str(node.get("summary") or "")
        profile_terms = list(profile.weak_points) + list(profile.knowledge_graph_focus)
        return any(term and (term in name or term in summary) for term in profile_terms)

    def _sort_key(self, node: dict[str, Any]) -> tuple[int, int, str]:
        return (int(node.get("level") or 0), int(node.get("order") or 0), str(node.get("name") or ""))

    def _priority(
        self,
        node: dict[str, Any],
        mastery: dict[str, KnowledgeNodeMastery],
        profile: StudentProfile,
        focus_dependency_ids: set[str] | None = None,
    ) -> float:
        node_id = str(node["id"])
        status = mastery[node_id].mastery_status if node_id in mastery else "not_started"
        score = {
            "severe_weak": 120,
            "basic": 95,
            "not_started": 80,
            "good": 35,
            "proficient": 5,
        }.get(status, 70)
        if self._matches_profile_focus(node, profile):
            score += 25
        if focus_dependency_ids and node_id in focus_dependency_ids:
            score += 35
        level = int(node.get("level") or 0)
        if level == 1:
            if focus_dependency_ids and node_id in focus_dependency_ids:
                score += 4
            else:
                score -= 20
        if level >= 3:
            score += 4
        return score

    def _stage(
        self,
        node: dict[str, Any],
        mastery: dict[str, KnowledgeNodeMastery],
        profile: StudentProfile,
        focus_dependency_ids: set[str] | None = None,
    ) -> CourseLearningStage:
        node_id = str(node["id"])
        topic = self._display_node_name(str(node.get("name") or node_id))
        row = mastery.get(node_id)
        status = row.mastery_status if row else "not_started"
        score = row.mastery_score if row else None
        level = int(node.get("level") or 0)
        order = int(node.get("order") or 0)
        resource_types = self._resource_types(profile, status)
        graph_basis = [
            f"图谱层级 L{level}，顺序 {order}",
            f"掌握度状态：{status}",
        ]
        profile_basis = [
            f"学习目标：{profile.learning_goal}",
            f"资源偏好：{'、'.join(profile.resource_preference) or '综合资源'}",
        ]
        if profile.weak_points:
            profile_basis.append(f"画像薄弱点：{'、'.join(profile.weak_points)}")
        return CourseLearningStage(
            node_id=node_id,
            topic=topic,
            level=level,
            order=order,
            mastery_status=status,
            mastery_score=score,
            priority_score=self._priority(node, mastery, profile, focus_dependency_ids),
            estimated_minutes=self._estimated_minutes(status, level),
            goal=f"掌握{topic}的核心概念、适用场景和常见误区",
            practice_task=f"完成{topic}的短练习，并用自己的话解释关键步骤",
            graph_basis=graph_basis,
            profile_basis=profile_basis,
            recommended_resource_types=resource_types,
            recommendation_reason=f"{topic}依据图谱前置关系和当前掌握状态进入本轮学习路径，资源形式匹配你的画像偏好。",
        )

    def _resource_types(self, profile: StudentProfile, status: str) -> list[str]:
        preferences = set(profile.resource_preference)
        resource_types = [ResourceType.DOCUMENT.value, ResourceType.EXERCISE.value]
        if {"鍥捐В", "鍔ㄧ敾", "瑙嗛"} & preferences:
            resource_types.insert(0, ResourceType.MIND_MAP.value)
            resource_types.append(ResourceType.VIDEO.value)
        if {"浠ｇ爜瀹炴搷", "缂栫▼", "瀹炴搷"} & preferences:
            resource_types.append(ResourceType.CODE_LAB.value)
        if status in {"good", "proficient"}:
            resource_types.append(ResourceType.READING.value)
        return list(dict.fromkeys(resource_types))

    def _estimated_minutes(self, status: str, level: int) -> int:
        base = 25 + max(level - 1, 0) * 8
        if status == "severe_weak":
            base += 20
        elif status == "basic":
            base += 10
        elif status == "proficient":
            base = 15
        return base
