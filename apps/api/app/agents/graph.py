from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, TypedDict

from app.agents.coding_agent import CodingAgent
from app.agents.document_agent import DocumentAgent
from app.agents.evaluator_agent import EvaluatorAgent
from app.agents.exercise_agent import ExerciseAgent
from app.agents.multimodal_agent import MindMapAgent, ReadingAgent, VideoScriptAgent
from app.agents.path_agent import PathAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.resource_contracts import (
    build_analysis_plan,
    build_debate_report,
    build_decision_report,
    build_pedagogy_report,
    build_verification_report,
)
from app.llm.client import LLMClient
from app.models.assessment import LearningEvent
from app.models.profile import StudentProfile
from app.models.resource import Resource, ResourceType


RESOURCE_AGENT_ORDER = [
    ResourceType.MIND_MAP,
    ResourceType.DOCUMENT,
    ResourceType.VIDEO,
    ResourceType.CODE_LAB,
    ResourceType.EXERCISE,
    ResourceType.READING,
]


class ResourceGraphState(TypedDict, total=False):
    profile: StudentProfile
    topic: str
    requested_resource_types: list[ResourceType]
    knowledge_context: list[dict[str, Any]]
    graph_constraints: dict[str, Any]
    retrieval_trace: list[dict[str, Any]]
    analysis_plan: dict[str, Any]
    verification_report: dict[str, Any]
    pedagogy_report: dict[str, Any]
    debate_report: dict[str, Any]
    decision_report: dict[str, Any]
    resources: list[Resource]
    agent_events: list[dict[str, Any]]


class LearningAgentGraph:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.profile_agent = ProfileAgent(llm)
        self.document_agent = DocumentAgent(llm)
        self.exercise_agent = ExerciseAgent(llm)
        self.mind_map_agent = MindMapAgent(llm)
        self.video_agent = VideoScriptAgent(llm)
        self.reading_agent = ReadingAgent(llm)
        self.coding_agent = CodingAgent(llm)
        self.path_agent = PathAgent()
        self.evaluator_agent = EvaluatorAgent()

    async def run(
        self,
        conversation: str,
        topic: str,
        requested_resource_types: list[ResourceType | str] | None = None,
        knowledge_context: list[dict[str, Any]] | None = None,
        profile: StudentProfile | None = None,
        graph_constraints: dict[str, Any] | None = None,
        retrieval_trace: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict, None]:
        if profile is None:
            profile_start_summary = "正在抽取学生画像"
            profile = await self.profile_agent.extract_profile(conversation)
            profile_summary = "已生成多维学习画像"
        else:
            profile_start_summary = "正在读取数据库确认画像"
            profile_summary = "已读取数据库确认画像"
        yield {"event": "agent_started", "agent": self.profile_agent.name, "summary": profile_start_summary}
        yield {
            "event": "agent_completed",
            "agent": self.profile_agent.name,
            "summary": profile_summary,
            "profile": profile.model_dump(mode="json"),
        }

        normalized_types = self._resource_types(requested_resource_types)
        graph_state = await self._run_resource_graph(
            profile,
            topic,
            normalized_types,
            knowledge_context or [],
            graph_constraints or self._empty_graph_constraints(topic),
            retrieval_trace or [],
        )
        resources = graph_state["resources"]
        for event in graph_state["agent_events"]:
            yield event

        yield {"event": "agent_started", "agent": self.path_agent.name, "summary": "正在规划学习路径"}
        learning_path = self.path_agent.plan(profile, topic, resources)
        yield {
            "event": "agent_completed",
            "agent": self.path_agent.name,
            "summary": "已生成个性化学习路径",
            "learning_path": learning_path.model_dump(mode="json"),
        }

        yield {
            "event": "workflow_completed",
            "profile": profile.model_dump(mode="json"),
            "resources": [resource.model_dump(mode="json") for resource in resources],
            "learning_path": learning_path.model_dump(mode="json"),
            "knowledge_context": knowledge_context or [],
            "graph_constraints": graph_state.get("graph_constraints") or graph_constraints or self._empty_graph_constraints(topic),
            "retrieval_trace": graph_state.get("retrieval_trace") or retrieval_trace or [],
            "analysis_plan": graph_state.get("analysis_plan") or {},
            "verification_report": graph_state.get("verification_report") or {},
            "pedagogy_report": graph_state.get("pedagogy_report") or {},
            "debate_report": graph_state.get("debate_report") or {},
            "decision_report": graph_state.get("decision_report") or {},
            "agent_events": graph_state["agent_events"],
        }

    async def run_collect(
        self,
        conversation: str,
        topic: str,
        requested_resource_types: list[ResourceType | str] | None = None,
        knowledge_context: list[dict[str, Any]] | None = None,
        profile: StudentProfile | None = None,
        graph_constraints: dict[str, Any] | None = None,
        retrieval_trace: list[dict[str, Any]] | None = None,
    ) -> dict:
        final = {}
        async for event in self.run(
            conversation,
            topic,
            requested_resource_types=requested_resource_types,
            knowledge_context=knowledge_context,
            profile=profile,
            graph_constraints=graph_constraints,
            retrieval_trace=retrieval_trace,
        ):
            final = event
        return final

    def assess(self, profile: StudentProfile, events: list[LearningEvent]):
        return self.evaluator_agent.evaluate(profile, events)

    def _resource_types(self, requested_resource_types: list[ResourceType | str] | None) -> list[ResourceType]:
        if not requested_resource_types:
            return RESOURCE_AGENT_ORDER.copy()
        requested = []
        seen = set()
        for item in requested_resource_types:
            try:
                resource_type = item if isinstance(item, ResourceType) else ResourceType(str(item))
            except ValueError:
                continue
            if resource_type not in seen:
                requested.append(resource_type)
                seen.add(resource_type)
        return [resource_type for resource_type in RESOURCE_AGENT_ORDER if resource_type in seen] or RESOURCE_AGENT_ORDER.copy()

    async def _run_resource_graph(
        self,
        profile: StudentProfile,
        topic: str,
        requested_resource_types: list[ResourceType],
        knowledge_context: list[dict[str, Any]],
        graph_constraints: dict[str, Any],
        retrieval_trace: list[dict[str, Any]],
    ) -> ResourceGraphState:
        state: ResourceGraphState = {
            "profile": profile,
            "topic": topic,
            "requested_resource_types": requested_resource_types,
            "knowledge_context": knowledge_context,
            "graph_constraints": graph_constraints,
            "retrieval_trace": retrieval_trace,
            "resources": [],
            "agent_events": [],
        }
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:
            return await self._run_resource_graph_fallback(state)

        builder = StateGraph(ResourceGraphState)
        builder.add_node("analyze", self._analysis_node)
        builder.add_node("retriever_evidence", self._retriever_node)
        previous = "retriever_evidence"
        builder.add_edge(START, "analyze")
        builder.add_edge("analyze", "retriever_evidence")
        for resource_type in requested_resource_types:
            node_name = resource_type.value
            builder.add_node(node_name, self._resource_node(resource_type))
            builder.add_edge(previous, node_name)
            previous = node_name
        builder.add_node("fact_critic", self._fact_critic_node)
        builder.add_node("pedagogy_critic", self._pedagogy_critic_node)
        builder.add_node("debate", self._debate_node)
        builder.add_node("decision", self._decision_node)
        builder.add_edge(previous, "fact_critic")
        builder.add_edge("fact_critic", "pedagogy_critic")
        builder.add_edge("pedagogy_critic", "debate")
        builder.add_edge("debate", "decision")
        builder.add_edge("decision", END)
        graph = builder.compile()
        if hasattr(graph, "ainvoke"):
            return await graph.ainvoke(state)
        return await self._run_resource_graph_fallback(state)

    async def _run_resource_graph_fallback(self, state: ResourceGraphState) -> ResourceGraphState:
        state.update(await self._analysis_node(state))
        state.update(await self._retriever_node(state))
        for resource_type in state["requested_resource_types"]:
            state.update(await self._resource_node(resource_type)(state))
        state.update(await self._fact_critic_node(state))
        state.update(await self._pedagogy_critic_node(state))
        state.update(await self._debate_node(state))
        state.update(await self._decision_node(state))
        return state

    async def _analysis_node(self, state: ResourceGraphState) -> dict[str, Any]:
        analysis_plan = build_analysis_plan(
            profile=state["profile"],
            topic=state["topic"],
            requested_resource_types=state["requested_resource_types"],
            knowledge_context=state.get("knowledge_context") or [],
            graph_constraints=state.get("graph_constraints") or {},
        )
        events = list(state.get("agent_events") or [])
        events.extend(
            [
                {
                    "event": "agent_started",
                    "agent": "分析规划Agent",
                    "summary": "正在分析学生画像、图谱约束和资源目标",
                },
                {
                    "event": "agent_completed",
                    "agent": "分析规划Agent",
                    "summary": "已生成统一资源蓝图",
                    "analysis_plan": analysis_plan,
                },
            ]
        )
        return {"analysis_plan": analysis_plan, "agent_events": events}

    async def _retriever_node(self, state: ResourceGraphState) -> dict[str, Any]:
        context_count = len(state.get("knowledge_context") or [])
        trace_count = len(state.get("retrieval_trace") or [])
        events = list(state.get("agent_events") or [])
        events.extend(
            [
                {
                    "event": "agent_started",
                    "agent": "检索证据Agent",
                    "summary": "正在整理 Agentic RAG 检索证据和 MySQL 原文块",
                },
                {
                    "event": "agent_completed",
                    "agent": "检索证据Agent",
                    "summary": f"已准备 {context_count} 个原文块和 {trace_count} 条检索轨迹",
                    "knowledge_context_count": context_count,
                    "retrieval_trace_count": trace_count,
                },
            ]
        )
        return {"agent_events": events}

    def _resource_node(self, resource_type: ResourceType):
        async def node(state: ResourceGraphState) -> dict[str, Any]:
            profile = state["profile"]
            topic = state["topic"]
            knowledge_context = state.get("knowledge_context") or []
            graph_constraints = state.get("graph_constraints") or {}
            agent, produced = await self._generate_resource(
                resource_type,
                profile,
                topic,
                knowledge_context,
                graph_constraints,
            )
            resources = list(state.get("resources") or [])
            events = list(state.get("agent_events") or [])
            start_event = {
                "event": "agent_started",
                "agent": agent.name,
                "resource_type": resource_type.value,
                "summary": f"{agent.name}开始生成{resource_type.value}资源",
            }
            completed_event = {
                "event": "agent_completed",
                "agent": agent.name,
                "resource_type": resource_type.value,
                "summary": f"{agent.name}生成{len(produced)}项资源",
                "resources": [resource.model_dump(mode="json") for resource in produced],
            }
            return {
                "resources": resources + produced,
                "agent_events": events + [start_event, completed_event],
            }

        return node

    async def _fact_critic_node(self, state: ResourceGraphState) -> dict[str, Any]:
        verification_report = build_verification_report(
            resources=state.get("resources") or [],
            knowledge_context=state.get("knowledge_context") or [],
            graph_constraints=state.get("graph_constraints") or {},
            analysis_plan=state.get("analysis_plan") or {},
        )
        events = list(state.get("agent_events") or [])
        events.extend(
            [
                {"event": "agent_started", "agent": "事实校验Agent", "summary": "正在核验事实依据和图谱约束"},
                {
                    "event": "agent_completed",
                    "agent": "事实校验Agent",
                    "summary": f"事实校验完成，幻觉风险：{verification_report['hallucination_risk']}",
                    "verification_report": verification_report,
                },
            ]
        )
        return {"verification_report": verification_report, "agent_events": events}

    async def _pedagogy_critic_node(self, state: ResourceGraphState) -> dict[str, Any]:
        pedagogy_report = build_pedagogy_report(
            resources=state.get("resources") or [],
            profile=state["profile"],
            analysis_plan=state.get("analysis_plan") or {},
        )
        events = list(state.get("agent_events") or [])
        events.extend(
            [
                {"event": "agent_started", "agent": "教学适配校验Agent", "summary": "正在检查资源与画像、难度和资源蓝图的匹配"},
                {
                    "event": "agent_completed",
                    "agent": "教学适配校验Agent",
                    "summary": f"教学适配校验完成，得分 {pedagogy_report['score']:.2f}",
                    "pedagogy_report": pedagogy_report,
                },
            ]
        )
        return {"pedagogy_report": pedagogy_report, "agent_events": events}

    async def _debate_node(self, state: ResourceGraphState) -> dict[str, Any]:
        debate_report = build_debate_report(
            verification_report=state.get("verification_report") or {},
            pedagogy_report=state.get("pedagogy_report") or {},
        )
        events = list(state.get("agent_events") or [])
        events.extend(
            [
                {"event": "agent_started", "agent": "辩论交叉验证Agent", "summary": "正在整合事实校验与教学适配校验的分歧"},
                {
                    "event": "agent_completed",
                    "agent": "辩论交叉验证Agent",
                    "summary": debate_report["debate_summary"],
                    "debate_report": debate_report,
                },
            ]
        )
        return {"debate_report": debate_report, "agent_events": events}

    async def _decision_node(self, state: ResourceGraphState) -> dict[str, Any]:
        decision_report = build_decision_report(
            verification_report=state.get("verification_report") or {},
            pedagogy_report=state.get("pedagogy_report") or {},
            debate_report=state.get("debate_report") or {},
        )
        events = list(state.get("agent_events") or [])
        events.extend(
            [
                {"event": "agent_started", "agent": "决策Agent", "summary": "正在裁决通过、重检索、重生成或降级输出"},
                {
                    "event": "agent_completed",
                    "agent": "决策Agent",
                    "summary": f"决策完成：{decision_report['decision']}，下一步：{decision_report['next_action']}",
                    "decision_report": decision_report,
                },
            ]
        )
        return {"decision_report": decision_report, "agent_events": events}

    async def _generate_resource(
        self,
        resource_type: ResourceType,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict[str, Any]],
        graph_constraints: dict[str, Any] | None = None,
    ) -> tuple[object, list[Resource]]:
        if resource_type == ResourceType.MIND_MAP:
            return self.mind_map_agent, [await self.mind_map_agent.generate(profile, topic, knowledge_context, graph_constraints)]
        if resource_type == ResourceType.DOCUMENT:
            return self.document_agent, [await self.document_agent.generate(profile, topic, knowledge_context, graph_constraints)]
        if resource_type == ResourceType.VIDEO:
            return self.video_agent, [await self.video_agent.generate(profile, topic, knowledge_context, graph_constraints)]
        if resource_type == ResourceType.CODE_LAB:
            return self.coding_agent, [await self.coding_agent.generate(profile, topic, knowledge_context, graph_constraints)]
        if resource_type == ResourceType.EXERCISE:
            return self.exercise_agent, [await self.exercise_agent.generate(profile, topic, knowledge_context, graph_constraints)]
        if resource_type == ResourceType.READING:
            return self.reading_agent, [await self.reading_agent.generate(profile, topic, knowledge_context, graph_constraints)]
        return self.document_agent, [await self.document_agent.generate(profile, topic, knowledge_context, graph_constraints)]

    def _empty_graph_constraints(self, topic: str) -> dict[str, Any]:
        return {
            "current_node": {"id": "", "name": topic, "node_type": "", "summary": ""},
            "parent": None,
            "predecessors": [],
            "successors": [],
            "related": [],
            "source_chunk_ids": [],
        }
