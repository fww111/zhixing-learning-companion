from app.services.graph_store import Neo4jGraphStore


class FakeSession:
    def __init__(self):
        self.queries = []
        self.results = []
        self.execute_writes = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.queries.append((query, params))
        return self.results

    def execute_write(self, function, *args):
        self.execute_writes.append((function, args))
        return function(self, *args)


class FakeDriver:
    def __init__(self):
        self.session_obj = FakeSession()
        self.closed = False

    def session(self):
        return self.session_obj

    def close(self):
        self.closed = True


def test_write_graph_scopes_nodes_by_user_and_course():
    driver = FakeDriver()
    store = Neo4jGraphStore(driver=driver)
    store.replace_course_graph(
        user_id=7,
        course_id=3,
        nodes=[
            {
                "id": "n1",
                "name": "Gradient descent",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "optimization method",
                "source_chunk_ids": [1],
                "confidence": 0.9,
                "level": 2,
                "order": 3,
                "parent_id": "chapter-1",
            }
        ],
        edges=[],
    )
    assert len(driver.session_obj.execute_writes) == 1
    query, params = driver.session_obj.queries[-1]
    assert params["user_id"] == 7
    assert params["course_id"] == 3
    assert params["nodes"][0]["id"] == "n1"
    assert params["nodes"][0]["level"] == 2
    assert "knowledge.level" in query


def test_write_graph_scopes_edges_by_user_and_course():
    driver = FakeDriver()
    store = Neo4jGraphStore(driver=driver)
    store.replace_course_graph(
        user_id=7,
        course_id=3,
        nodes=[
            {
                "id": "n1",
                "name": "Gradient descent",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "optimization method",
                "source_chunk_ids": [1],
                "confidence": 0.9,
            },
            {
                "id": "n2",
                "name": "Linear regression",
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "model concept",
                "source_chunk_ids": [2],
                "confidence": 0.85,
            },
        ],
        edges=[
            {
                "id": "e1",
                "source_node_id": "n1",
                "target_node_id": "n2",
                "relation_type": "prerequisite",
                "reason": "Learn optimization before model fitting.",
                "confidence": 0.8,
            }
        ],
    )

    query, params = driver.session_obj.queries[-1]
    assert len(driver.session_obj.execute_writes) == 1
    assert "MATCH (source:KnowledgeNode" in query
    assert "MATCH (target:KnowledgeNode" in query
    assert params["user_id"] == 7
    assert params["course_id"] == 3
    assert "edge.source_node_id" in query
    assert "edge.target_node_id" in query
    assert params["edges"][0]["source_node_id"] == "n1"
    assert params["edges"][0]["target_node_id"] == "n2"


def test_get_course_graph_returns_scoped_nodes_and_edges():
    driver = FakeDriver()
    driver.session_obj.results = [
        {
            "nodes": [
                {
                    "id": "n1",
                    "user_id": 7,
                    "course_id": 3,
                    "name": "Gradient descent",
                    "node_type": "method",
                    "difficulty": "basic",
                    "summary": "optimization method",
                    "source_chunk_ids": [1],
                    "confidence": 0.9,
                    "level": 2,
                    "order": 3,
                    "parent_id": "chapter-1",
                }
            ],
            "edges": [
                {
                    "id": "e1",
                    "source_node_id": "n1",
                    "target_node_id": "n2",
                    "user_id": 7,
                    "course_id": 3,
                    "relation_type": "prerequisite",
                    "reason": "Learn optimization before model fitting.",
                    "confidence": 0.8,
                }
            ],
        }
    ]
    store = Neo4jGraphStore(driver=driver)

    graph = store.get_course_graph(user_id=7, course_id=3)

    query, params = driver.session_obj.queries[-1]
    assert "user_id: $user_id" in query
    assert "course_id: $course_id" in query
    assert params == {"user_id": 7, "course_id": 3}
    assert graph["nodes"][0]["id"] == "n1"
    assert graph["nodes"][0]["level"] == 2
    assert graph["nodes"][0]["parent_id"] == "chapter-1"
    assert graph["edges"][0]["id"] == "e1"
    assert graph["edges"][0]["source_node_id"] == "n1"
    assert graph["edges"][0]["target_node_id"] == "n2"


def test_close_closes_driver_when_available():
    driver = FakeDriver()
    store = Neo4jGraphStore(driver=driver)

    store.close()

    assert driver.closed is True
