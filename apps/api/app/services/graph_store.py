from __future__ import annotations

from typing import Any

from app.core.config import settings


class Neo4jGraphStore:
    def __init__(self, driver: Any | None = None):
        self.driver = driver if driver is not None else self._create_driver()

    def _create_driver(self) -> Any:
        from neo4j import GraphDatabase

        return GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def replace_course_graph(
        self,
        user_id: int,
        course_id: int,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        with self.driver.session() as session:
            session.execute_write(self._replace_course_graph_tx, user_id, course_id, nodes, edges)

    def delete_course_graph(self, user_id: int, course_id: int) -> None:
        with self.driver.session() as session:
            session.execute_write(self._delete_course_graph_tx, user_id, course_id)

    def _delete_course_graph_tx(self, tx: Any, user_id: int, course_id: int) -> None:
        tx.run(
            """
            MATCH (node:KnowledgeNode {user_id: $user_id, course_id: $course_id})
            DETACH DELETE node
            """,
            user_id=user_id,
            course_id=course_id,
        )

    def _replace_course_graph_tx(
        self,
        tx: Any,
        user_id: int,
        course_id: int,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        self._delete_course_graph_tx(tx, user_id, course_id)

        if nodes:
            tx.run(
                """
                UNWIND $nodes AS node
                MERGE (knowledge:KnowledgeNode {
                    id: node.id,
                    user_id: $user_id,
                    course_id: $course_id
                })
                SET knowledge.name = node.name,
                    knowledge.node_type = node.node_type,
                    knowledge.difficulty = node.difficulty,
                    knowledge.summary = node.summary,
                    knowledge.source_chunk_ids = node.source_chunk_ids,
                    knowledge.confidence = node.confidence,
                    knowledge.level = coalesce(node.level, 1),
                    knowledge.order = coalesce(node.order, 0),
                    knowledge.parent_id = coalesce(node.parent_id, "")
                """,
                user_id=user_id,
                course_id=course_id,
                nodes=nodes,
            )

        if edges:
            tx.run(
                """
                UNWIND $edges AS edge
                MATCH (source:KnowledgeNode {
                    id: edge.source_node_id,
                    user_id: $user_id,
                    course_id: $course_id
                })
                MATCH (target:KnowledgeNode {
                    id: edge.target_node_id,
                    user_id: $user_id,
                    course_id: $course_id
                })
                MERGE (source)-[relation:RELATES_TO {id: edge.id}]->(target)
                SET relation.user_id = $user_id,
                    relation.course_id = $course_id,
                    relation.relation_type = edge.relation_type,
                    relation.reason = edge.reason,
                    relation.confidence = edge.confidence
                """,
                user_id=user_id,
                course_id=course_id,
                edges=edges,
            )

    def close(self) -> None:
        close = getattr(self.driver, "close", None)
        if close is not None:
            close()

    def get_course_graph(self, user_id: int, course_id: int) -> dict[str, list[dict[str, Any]]]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (node:KnowledgeNode {user_id: $user_id, course_id: $course_id})
                WITH collect(node {
                    .id,
                    .user_id,
                    .course_id,
                    .name,
                    .node_type,
                    .difficulty,
                    .summary,
                    .source_chunk_ids,
                    .confidence,
                    .level,
                    .order,
                    .parent_id
                }) AS nodes
                OPTIONAL MATCH (source:KnowledgeNode {user_id: $user_id, course_id: $course_id})
                    -[relation:RELATES_TO {user_id: $user_id, course_id: $course_id}]->
                    (target:KnowledgeNode {user_id: $user_id, course_id: $course_id})
                RETURN nodes,
                    collect(relation {
                        .id,
                        .user_id,
                        .course_id,
                        .relation_type,
                        .reason,
                        .confidence,
                        source_node_id: source.id,
                        target_node_id: target.id
                    }) AS edges
                """,
                user_id=user_id,
                course_id=course_id,
            )
            records = list(result)

        if not records:
            return {"nodes": [], "edges": []}

        record = records[0]
        return {
            "nodes": record["nodes"] or [],
            "edges": record["edges"] or [],
        }
