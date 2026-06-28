import asyncio

from app.agents.graph import LearningAgentGraph
from app.llm.client import LLMClient
from app.models.resource import ResourceType


def test_agent_graph_emits_events_and_generates_complete_package():
    graph = LearningAgentGraph(LLMClient(api_key="", mock=True))

    async def collect_events():
        return [
            event
            async for event in graph.run(
                "计算机大二，想4周入门机器学习，梯度下降薄弱，喜欢图解动画和代码。",
                "梯度下降",
            )
        ]

    events = asyncio.run(collect_events())

    completed = [event for event in events if event["event"] == "agent_completed"]
    final = events[-1]

    assert len(completed) >= 5
    assert final["event"] == "workflow_completed"
    assert len(final["resources"]) >= 6
    assert len(final["learning_path"]["stages"]) >= 3


def test_agent_graph_generates_only_requested_modal_resources_with_knowledge_context():
    graph = LearningAgentGraph(LLMClient(api_key="", mock=True))
    knowledge_context = [
        {
            "chunk_id": 1,
            "source_locator": "page 12",
            "content": "教材说明：列表是 Python 中用于保存有序可变数据集合的核心结构。",
        }
    ]

    async def collect_events():
        return [
            event
            async for event in graph.run(
                "计算机大二，列表薄弱，偏好图解和代码实操。",
                "1.1 初识 Python",
                requested_resource_types=[ResourceType.MIND_MAP, ResourceType.DOCUMENT, ResourceType.EXERCISE],
                knowledge_context=knowledge_context,
            )
        ]

    events = asyncio.run(collect_events())
    final = events[-1]
    resources = final["resources"]

    assert final["event"] == "workflow_completed"
    assert final["knowledge_context"] == knowledge_context
    assert [resource["type"] for resource in resources] == ["mind_map", "document", "exercise"]
    completed_resource_events = [
        event for event in events if event["event"] == "agent_completed" and "resource_type" in event
    ]
    assert {event["resource_type"] for event in completed_resource_events} == {"mind_map", "document", "exercise"}
    assert {event["agent"] for event in completed_resource_events} == {"思维导图Agent", "文档生成Agent", "题库生成Agent"}
    assert all("教材说明" not in resource["content"] for resource in resources)
    assert all("page 12" in resource["recommendation_reason"] for resource in resources)


def test_agent_graph_returns_agentic_rag_guardrail_metadata():
    graph = LearningAgentGraph(LLMClient(api_key="", mock=True))
    knowledge_context = [
        {
            "chunk_id": 7,
            "source_locator": "page 21",
            "content": "教材说明：Python 列表支持有序、可变、可索引的数据管理。",
            "retrieval_query": "1.1 初识 Python Python 列表",
        }
    ]
    graph_constraints = {
        "current_node": {"id": "outline-section-1-1", "name": "1.1 初识 Python"},
        "parent": {"id": "chapter-1", "name": "第1章 Python 概述"},
        "predecessors": [],
        "successors": [{"id": "outline-section-1-2", "name": "1.2 Python 开发环境"}],
        "related": [],
    }
    retrieval_trace = [
        {
            "query": "1.1 初识 Python Python 列表",
            "vector_chunk_id": 7,
            "mysql_chunk_id": 7,
            "source_locator": "page 21",
        }
    ]

    async def collect_events():
        return [
            event
            async for event in graph.run(
                "计算机大二，列表薄弱，偏好图解和代码实操。",
                "1.1 初识 Python",
                requested_resource_types=[ResourceType.DOCUMENT],
                knowledge_context=knowledge_context,
                graph_constraints=graph_constraints,
                retrieval_trace=retrieval_trace,
            )
        ]

    final = asyncio.run(collect_events())[-1]

    assert final["graph_constraints"] == graph_constraints
    assert final["retrieval_trace"] == retrieval_trace
    assert final["verification_report"]["decision"] == "accepted"
    assert final["verification_report"]["evidence_count"] == 1
    assert final["verification_report"]["graph_constraint_count"] >= 2
    assert final["resources"][0]["citation_chunk_ids"] == [7]
    assert final["resources"][0]["grounding_status"] == "verified"


def test_agent_graph_runs_analysis_generation_validation_decision_closed_loop():
    graph = LearningAgentGraph(LLMClient(api_key="", mock=True))
    knowledge_context = [
        {
            "chunk_id": 7,
            "source_locator": "page 21",
            "content": "教材说明：Python 列表支持有序、可变、可索引的数据管理。",
            "retrieval_query": "1.1 初识 Python Python 列表",
        }
    ]
    graph_constraints = {
        "current_node": {"id": "outline-section-1-1", "name": "1.1 初识 Python"},
        "parent": {"id": "chapter-1", "name": "第1章 Python 概述"},
        "predecessors": [],
        "successors": [{"id": "outline-section-1-2", "name": "1.2 Python 开发环境"}],
        "related": [],
    }

    async def collect_events():
        return [
            event
            async for event in graph.run(
                "计算机大二，列表薄弱，偏好图解和代码实操。",
                "1.1 初识 Python",
                requested_resource_types=[ResourceType.MIND_MAP, ResourceType.DOCUMENT, ResourceType.EXERCISE],
                knowledge_context=knowledge_context,
                graph_constraints=graph_constraints,
            )
        ]

    events = asyncio.run(collect_events())
    final = events[-1]
    completed_agents = [event["agent"] for event in events if event["event"] == "agent_completed"]

    assert final["analysis_plan"]["topic"] == "1.1 初识 Python"
    assert final["analysis_plan"]["resource_blueprint"]["resource_requirements"]["document"]["resource_type"] == "document"
    assert final["verification_report"]["fact_score"] >= 0.8
    assert final["verification_report"]["pedagogy_score"] >= 0.8
    assert final["debate_report"]["decision"] == "accepted"
    assert final["decision_report"]["decision"] == "accepted"
    assert final["decision_report"]["next_action"] == "return_resources"
    assert {
        "分析规划Agent",
        "检索证据Agent",
        "事实校验Agent",
        "教学适配校验Agent",
        "辩论交叉验证Agent",
        "决策Agent",
    }.issubset(set(completed_agents))
    assert {resource["type"] for resource in final["resources"]} == {"mind_map", "document", "exercise"}
