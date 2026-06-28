from app.agents.knowledge_graph_agent import KnowledgeGraphAgent


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_mock_graph_agent_returns_nodes_and_edges():
    agent = KnowledgeGraphAgent(mock=True)
    graph = agent.build_graph(
        [
            {
                "id": 1,
                "content": "Gradient descent optimizes a loss function. Learning it requires understanding loss first.",
                "source_locator": "page 1",
            }
        ]
    )

    assert graph["nodes"]
    assert graph["edges"]
    assert graph["nodes"][0]["source_chunk_ids"]
    assert graph["edges"][0]["relation_type"] in {
        "prerequisite",
        "contains",
        "applies_to",
        "common_mistake",
        "case_supports",
    }


def test_mock_graph_agent_output_has_required_node_and_edge_keys():
    agent = KnowledgeGraphAgent(mock=True)
    graph = agent.build_graph([{"id": "chunk-a", "content": "loss and gradient descent"}])

    required_node_keys = {
        "id",
        "name",
        "node_type",
        "difficulty",
        "summary",
        "source_chunk_ids",
        "confidence",
    }
    required_edge_keys = {
        "id",
        "source_node_id",
        "target_node_id",
        "relation_type",
        "reason",
        "confidence",
    }

    assert graph["nodes"]
    assert graph["edges"]
    assert required_node_keys <= set(graph["nodes"][0])
    assert required_edge_keys <= set(graph["edges"][0])


def test_build_graph_async_normalizes_malformed_llm_graph_and_drops_bad_edges():
    class FakeLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):
            return {
                "nodes": [
                    {
                        "name": "Gradient descent",
                        "node_type": "bad-type",
                        "difficulty": "expert",
                        "source_chunk_ids": ["chunk-1", "unknown"],
                        "confidence": 2,
                    },
                    {
                        "id": "valid-node",
                        "name": "Learning rate",
                        "node_type": "formula",
                        "difficulty": "advanced",
                        "summary": "Step size.",
                        "source_chunk_ids": "chunk-2",
                        "confidence": "0.4",
                    },
                ],
                "edges": [
                    {
                        "source_node_id": "node-0",
                        "target_node_id": "valid-node",
                        "relation_type": "invalid",
                    },
                    {
                        "source_node_id": "node-0",
                        "target_node_id": "missing-node",
                        "relation_type": "contains",
                    },
                    {
                        "source_node_id": "node-0",
                        "target_node_id": "valid-node",
                        "relation_type": "prerequisite",
                        "confidence": -1,
                    },
                ],
            }

    agent = KnowledgeGraphAgent(mock=False, llm=FakeLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {"id": "chunk-1", "content": "Gradient descent"},
                {"id": "chunk-2", "content": "Learning rate"},
            ]
        )
    )

    assert graph["nodes"] == [
        {
            "id": "node-0",
            "name": "Gradient descent",
            "node_type": "concept",
            "difficulty": "basic",
            "summary": "",
            "source_chunk_ids": ["chunk-1"],
            "confidence": 1.0,
            "level": 1,
            "order": 0,
            "parent_id": "",
        },
        {
            "id": "valid-node",
            "name": "Learning rate",
            "node_type": "formula",
            "difficulty": "advanced",
            "summary": "Step size.",
            "source_chunk_ids": ["chunk-2"],
            "confidence": 0.4,
            "level": 1,
            "order": 1,
            "parent_id": "",
        },
    ]
    assert graph["edges"] == [
        {
            "id": "edge-2",
            "source_node_id": "node-0",
            "target_node_id": "valid-node",
            "relation_type": "prerequisite",
            "reason": "",
            "confidence": 0.0,
        }
    ]


def test_build_graph_async_uses_mock_graph_when_injected_llm_is_mock():
    class FakeMockLLM:
        mock = True

        async def complete_json(self, system_prompt, user_prompt):
            return {"nodes": [], "edges": []}

    agent = KnowledgeGraphAgent(mock=False, llm=FakeMockLLM())
    graph = _run(agent.build_graph_async([{"id": "chunk-a", "content": "content"}]))

    assert graph["nodes"]
    assert graph["edges"]
    assert graph["nodes"][0]["source_chunk_ids"] == ["chunk-a"]


def test_build_graph_async_merges_llm_extraction_with_outline_when_outline_exists():
    class RecordingLLM:
        mock = False

        def __init__(self):
            self.calls = 0

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            self.calls += 1
            return {
                "nodes": [
                    {
                        "id": "semantic-variable",
                        "name": "变量与数据类型",
                        "node_type": "concept",
                        "difficulty": "basic",
                        "summary": "大模型从教材内容中抽取出的语义知识点。",
                        "source_chunk_ids": ["section-1"],
                        "confidence": 0.91,
                    },
                    {
                        "id": "semantic-operator",
                        "name": "表达式与运算符",
                        "node_type": "formula",
                        "difficulty": "basic",
                        "summary": "大模型识别出的后续知识点。",
                        "source_chunk_ids": ["toc-1"],
                        "confidence": 0.86,
                    },
                ],
                "edges": [
                    {
                        "id": "semantic-edge",
                        "source_node_id": "semantic-variable",
                        "target_node_id": "semantic-operator",
                        "relation_type": "prerequisite",
                        "reason": "理解变量和数据类型后才能更好理解表达式求值。",
                        "confidence": 0.83,
                    }
                ],
            }

    llm = RecordingLLM()
    agent = KnowledgeGraphAgent(mock=False, llm=llm)
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "cover",
                    "heading": "Python 程序设计",
                    "content": "Python 程序设计",
                    "source_locator": "page 1",
                },
                {
                    "id": "toc-1",
                    "heading": "目录",
                    "content": (
                        "目录 第 1 章 Python 概述 …… 1 "
                        "1.1 初识 Python 1 1.2 Python 版本和开发环境 …… 2 "
                        "第 2 章 Python 的基础语法 …… 26 "
                        "2.1 Python 程序格式 26 2.2 标识符和关键字 28"
                    ),
                    "source_locator": "page 8",
                },
                {
                    "id": "section-1",
                    "heading": "1.2.1 Python 的版本",
                    "content": "1.2.1 Python 的版本 Python 目前主要使用 Python 2 和 Python 3。",
                    "source_locator": "page 15",
                },
            ]
        )
    )

    assert llm.calls == 1
    node_ids = {node["id"] for node in graph["nodes"]}
    assert {"outline-section-1-2-1", "semantic-variable", "semantic-operator"} <= node_ids
    assert {
        "id": "semantic-edge",
        "source_node_id": "semantic-variable",
        "target_node_id": "semantic-operator",
        "relation_type": "prerequisite",
        "reason": "理解变量和数据类型后才能更好理解表达式求值。",
        "confidence": 0.83,
    } in graph["edges"]


def test_build_graph_async_preserves_outline_nodes_when_llm_returns_sparse_semantic_graph():
    class SparseLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            return {
                "nodes": [
                    {
                        "id": "semantic-python-version",
                        "name": "Python 版本选择",
                        "node_type": "concept",
                        "difficulty": "basic",
                        "summary": "大模型补充的语义知识点。",
                        "source_chunk_ids": ["body-1"],
                        "confidence": 0.9,
                    }
                ],
                "edges": [],
            }

    agent = KnowledgeGraphAgent(mock=False, llm=SparseLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "toc",
                    "heading": "目录",
                    "content": (
                        "目录 第 1 章 Python 概述 1 "
                        "1.2 Python 版本和开发环境 2 "
                        "1.2.1 Python 语言的版本 2 "
                        "1.2.2 Python 的集成开发环境 3"
                    ),
                },
                {
                    "id": "body-1",
                    "heading": "2. 科学计算",
                    "content": (
                        "1.2 Python 版本和开发环境 "
                        "1.2.1 Python 语言的版本 Python 语言由 Guido van Rossum 设计。 "
                        "1.2.2 Python 的集成开发环境 常用环境包括 IDLE、Anaconda 和 PyCharm。"
                    ),
                },
            ]
        )
    )

    node_ids = {node["id"] for node in graph["nodes"]}
    assert {
        "outline-section-1-2",
        "outline-section-1-2-1",
        "outline-section-1-2-2",
        "semantic-python-version",
    } <= node_ids


def test_build_graph_async_falls_back_to_outline_when_real_llm_times_out():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "toc",
                    "heading": "目录",
                    "content": (
                        "目录 第 1 章 Python 概述 …… 1 "
                        "1.1 初识 Python 1 1.2 Python 版本和开发环境 2"
                    ),
                },
                {
                    "id": "body",
                    "heading": "1.2.2 Python 的集成开发环境",
                    "content": "Python 2.7.13 和 Python 3.6.2 是历史版本号，不能变成知识节点。",
                },
            ]
        )
    )

    names = {node["name"] for node in graph["nodes"]}
    assert "第 1 章 Python 概述" in names
    assert "1.2.2 Python 的集成开发环境" in names
    assert any(edge["relation_type"] == "contains" for edge in graph["edges"])


def test_outline_graph_extracts_embedded_child_sections_from_body_chunks():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "chapter-body",
                    "heading": "第1章",
                    "content": (
                        "第1章 Python 概述 Python 是一种简单易学的编程语言。 "
                        "1.1 初识 Python "
                        "1.1.1 Python语言的特点 Python 语言的特点总结为如下几条： "
                        "1.1.2 Python 语言的应用领域 Python 语言目前已经广泛应用于多个领域。 "
                        "1.2 Python 版本和开发环境 "
                        "1.2.1 Python 语言的版本 Python 语言由 Guido van Rossum 设计。 "
                        "1.2.2 Python 的集成开发环境 常用环境包括 IDLE、Anaconda 和 PyCharm。 "
                        "1.3 Python 的安装和设置 "
                        "1.3.1 Python 的下载 Python 在不同操作系统平台上的安装和配置过程基本一致。 "
                        "1.3.2 Python 的安装 Python 的安装过程如下：双击安装文件启动安装界面。"
                    ),
                }
            ]
        )
    )

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    assert nodes_by_id["outline-section-1-1-1"]["name"] == "1.1.1 Python语言的特点"
    assert nodes_by_id["outline-section-1-2-1"]["name"] == "1.2.1 Python 语言的版本"
    assert nodes_by_id["outline-section-1-3-1"]["name"] == "1.3.1 Python 的下载"
    assert nodes_by_id["outline-section-1-3-2"]["name"] == "1.3.2 Python 的安装"
    contains_edges = {
        (edge["source_node_id"], edge["target_node_id"])
        for edge in graph["edges"]
        if edge["relation_type"] == "contains"
    }
    assert ("outline-section-1-2", "outline-section-1-2-1") in contains_edges
    assert ("outline-section-1-3", "outline-section-1-3-1") in contains_edges


def test_build_graph_async_falls_back_to_mock_when_real_llm_times_out_without_outline():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(agent.build_graph_async([{"id": "chunk-a", "heading": "Loops", "content": "for and while loops"}]))

    assert graph["nodes"]
    assert graph["edges"]
    assert graph["nodes"][0]["source_chunk_ids"] == ["chunk-a"]


def test_outline_graph_ignores_quiz_decimals_and_keeps_toc_chapter_titles():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "toc",
                    "heading": "目录",
                    "content": (
                        "目录 第 1 章 Python 概述 …… 1 "
                        "1.1 初识 Python 1 1.2 Python 版本和开发环境 2"
                    ),
                },
                {
                    "id": "chapter",
                    "heading": "第 1 章",
                    "content": "第 1 章）李富宇（ Python 概述 习题 15. Python 采用( )来区分代码块 A. 0.5 B. 1 C. 0 D. 2",
                },
                {
                    "id": "body",
                    "heading": "1.2.2 Python 的集成开发环境",
                    "content": "Python 2.7.13 和 Python 3.6.2 是历史版本号，不能变成知识节点。",
                },
            ]
        )
    )

    names = {node["name"] for node in graph["nodes"]}
    assert "第 1 章 Python 概述" in names
    assert "1.2.2 Python 的集成开发环境" in names
    assert all(not name.startswith("0.5") for name in names)
    assert all("李富宇" not in name for name in names)


def test_outline_graph_extracts_inline_body_sections_under_chapter():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "chapter-body",
                    "heading": "\u7b2c1\u7ae0 \u7a0b\u5e8f\u8bbe\u8ba1\u548cC\u8bed\u8a00",
                    "content": (
                        "\u7b2c1\u7ae0 \u7a0b\u5e8f\u8bbe\u8ba1\u548cC\u8bed\u8a00 "
                        "1.1 \u4ec0\u4e48\u662f\u8ba1\u7b97\u673a\u7a0b\u5e8f "
                        "\u6240\u8c13\u7a0b\u5e8f\uff0c\u5c31\u662f\u4e00\u7ec4\u8ba1\u7b97\u673a\u80fd\u8bc6\u522b\u548c\u6267\u884c\u7684\u6307\u4ee4\u3002 "
                        "1.2 \u4ec0\u4e48\u662f\u8ba1\u7b97\u673a\u8bed\u8a00 "
                        "\u4eba\u548c\u8ba1\u7b97\u673a\u4ea4\u6d41\u4fe1\u606f\u4e5f\u8981\u89e3\u51b3\u8bed\u8a00\u95ee\u9898\u3002"
                    ),
                }
            ]
        )
    )

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    assert nodes_by_id["outline-section-1-1"]["name"] == "1.1 \u4ec0\u4e48\u662f\u8ba1\u7b97\u673a\u7a0b\u5e8f"
    assert nodes_by_id["outline-section-1-2"]["name"] == "1.2 \u4ec0\u4e48\u662f\u8ba1\u7b97\u673a\u8bed\u8a00"
    contains_targets = {
        edge["target_node_id"]
        for edge in graph["edges"]
        if edge["source_node_id"] == "outline-chapter-1" and edge["relation_type"] == "contains"
    }
    assert {"outline-section-1-1", "outline-section-1-2"} <= contains_targets


def test_outline_graph_keeps_c_section_titles_with_parentheses():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "c-operators",
                    "heading": "3.3 运算符和表达式",
                    "content": (
                        "3.3 运算符和表达式 "
                        "3.3.1 C运算符 C语言提供了丰富的运算符。 "
                        "3.3.2 基本的算术运算符 最常用的算术运算符包括加减乘除。 "
                        "3.3.3 自增(十)、自减(一)运算符 自增、自减运算符使变量的值加1或减1。 "
                        "3.3.4 算术表达式和运算符的优先级与结合性 "
                        "用算术运算符和括号将运算对象连接起来的式子称为算术表达式。"
                    ),
                }
            ]
        )
    )

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    assert nodes_by_id["outline-section-3-3-3"]["name"] == "3.3.3 自增(十)、自减(一)运算符"
    assert nodes_by_id["outline-section-3-3-4"]["name"] == "3.3.4 算术表达式和运算符的优先级与结合性"
    contains_edges = {
        (edge["source_node_id"], edge["target_node_id"])
        for edge in graph["edges"]
        if edge["relation_type"] == "contains"
    }
    assert ("outline-section-3-3", "outline-section-3-3-3") in contains_edges
    assert ("outline-section-3-3", "outline-section-3-3-4") in contains_edges


def test_outline_graph_extracts_c_child_section_from_mid_body_text():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "c-array",
                    "heading": "6.1.1 怎样定义一维数组",
                    "content": (
                        "6.1 怎样定义和引用一维数组 "
                        "6.1.1 怎样定义一维数组 用 int a[10] 定义数组后，在内存中划出一片存储空间。 "
                        "图6.1 a[0] a[1] a[2] a[3] a[4] "
                        "6.1.2 怎样引用一维数组元素 在定义数组并对其中各元素赋值后，"
                        "就可以引用数组中的元素。引用数组元素的表示形式为数组名[下标]。 "
                        "6.1.3 一维数组的初始化 可以在定义数组时使数组元素得到初值。"
                    ),
                }
            ]
        )
    )

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    assert nodes_by_id["outline-section-6-1-2"]["name"] == "6.1.2 怎样引用一维数组元素"
    contains_edges = {
        (edge["source_node_id"], edge["target_node_id"])
        for edge in graph["edges"]
        if edge["relation_type"] == "contains"
    }
    assert ("outline-section-6-1", "outline-section-6-1-2") in contains_edges


def test_outline_graph_merges_split_c_pdf_material_chunks():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "part-1-toc",
                    "material_id": 10,
                    "chunk_index": 0,
                    "heading": "目录",
                    "content": (
                        "目录 第1章 程序设计和C语言 1 "
                        "1.1 什么是计算机程序 2 "
                        "1.2 什么是计算机语言 5 "
                        "1.2.1 计算机语言的发展 6 "
                        "1.2.2 C语言的特点 8 "
                        "第2章 算法 20 "
                        "2.1 算法的概念 21"
                    ),
                },
                {
                    "id": "part-1-body",
                    "material_id": 10,
                    "chunk_index": 1,
                    "heading": "1.2 什么是计算机语言",
                    "content": (
                        "1.2 什么是计算机语言 人和计算机交流信息也要解决语言问题。 "
                        "1.2.1 计算机语言的发展 机器语言、汇编语言和高级语言分别代表不同抽象层次。 "
                        "1.2.2 C语言的特点 C语言兼具高级语言和低级语言的特点。"
                    ),
                },
                {
                    "id": "part-2-toc",
                    "material_id": 11,
                    "chunk_index": 0,
                    "heading": "目录",
                    "content": (
                        "目录 第6章 数组 201 "
                        "6.1 怎样定义和引用一维数组 202 "
                        "6.1.1 怎样定义一维数组 203 "
                        "6.1.2 怎样引用一维数组元素 205 "
                        "第7章 函数 230 "
                        "7.1 为什么要用函数 231"
                    ),
                },
                {
                    "id": "part-2-body",
                    "material_id": 11,
                    "chunk_index": 1,
                    "heading": "6.1.1 怎样定义一维数组",
                    "content": (
                        "6.1 怎样定义和引用一维数组 "
                        "6.1.1 怎样定义一维数组 用 int a[10] 定义数组后，在内存中划出一片存储空间。 "
                        "图6.1 a[0] a[1] a[2] a[3] a[4] "
                        "6.1.2 怎样引用一维数组元素 引用数组元素的表示形式为数组名[下标]。"
                    ),
                },
            ]
        )
    )

    node_ids = {node["id"] for node in graph["nodes"]}
    assert {
        "outline-chapter-1",
        "outline-section-1-2",
        "outline-section-1-2-1",
        "outline-section-1-2-2",
        "outline-chapter-6",
        "outline-section-6-1",
        "outline-section-6-1-1",
        "outline-section-6-1-2",
    } <= node_ids

    contains_edges = {
        (edge["source_node_id"], edge["target_node_id"])
        for edge in graph["edges"]
        if edge["relation_type"] == "contains"
    }
    assert ("course-root", "outline-chapter-1") in contains_edges
    assert ("course-root", "outline-chapter-6") in contains_edges
    assert ("outline-section-1-2", "outline-section-1-2-1") in contains_edges
    assert ("outline-section-6-1", "outline-section-6-1-1") in contains_edges


def test_outline_graph_extracts_c_child_section_after_figure_labels():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "c-array-figure",
                    "heading": "6.1.1 怎样定义一维数组",
                    "content": (
                        "6.1 怎样定义和引用一维数组 "
                        "6.1.1 怎样定义一维数组 用 int a[10] 定义数组后，在内存中划出存储空间。 "
                        "图6.1 a[0] a[1] a[2] a[3] a[4] a[5] a[6] a[7] a[8] a[9] "
                        "6.1.2 怎样引用一维数组元素 在定义数组并对其中各元素赋值后，"
                        "就可以引用数组中的元素。"
                    ),
                }
            ]
        )
    )

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    assert nodes_by_id["outline-section-6-1-2"]["name"] == "6.1.2 怎样引用一维数组元素"


def test_outline_graph_trims_c_child_section_title_before_body_sentence():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "c-pointer-array",
                    "heading": "8.7 指针数组和多重指针",
                    "content": (
                        "8.7 指针数组和多重指针 "
                        "8.7.1 什么是指针数组 一个数组，若其元素均为指针类型数据，"
                        "称为指针数组，也就是说，指针数组中的每一个元素都存放一个地址。 "
                        "8.7.2 指向指针数据的指针变量 在了解了指针数组的基础上继续学习多重指针。"
                    ),
                }
            ]
        )
    )

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    assert nodes_by_id["outline-section-8-7-1"]["name"] == "8.7.1 什么是指针数组"
    assert nodes_by_id["outline-section-8-7-2"]["name"] == "8.7.2 指向指针数据的指针变量"


def test_outline_graph_trims_c_child_section_title_before_numbered_subpoint():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "c-file-random-access",
                    "heading": "(1) 数据的存储方式",
                    "content": (
                        "10.4 随机读写数据文件 对文件进行顺序读写比较容易理解。 "
                        "10.4.1 文件位置标记及其定位 1. 文件位置标记 "
                        "为了对读写进行控制，系统为每个文件设置了一个文件读写位置标记。 "
                        "10.4.2 随机读写 随机读写需要先定位文件位置。"
                    ),
                }
            ]
        )
    )

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    assert nodes_by_id["outline-section-10-4-1"]["name"] == "10.4.1 文件位置标记及其定位"
    assert nodes_by_id["outline-section-10-4-2"]["name"] == "10.4.2 随机读写"


def test_outline_graph_cleans_chapter_title_when_toc_line_leaks_following_lab_items():
    class TimeoutLLM:
        mock = False

        async def complete_json(self, system_prompt, user_prompt):  # noqa: ARG002
            raise TimeoutError()

    agent = KnowledgeGraphAgent(mock=False, llm=TimeoutLLM())
    graph = _run(
        agent.build_graph_async(
            [
                {
                    "id": "toc",
                    "heading": "目录",
                    "content": (
                        "目录 第 8 章 文件操作 …… 160 "
                        "第 9 章 异常处理 …… 187 上机实验 1 常见异常 …… 192 "
                        "上机实验 2 带异常处理的文件读写 …… 196 "
                        "9.1 异常概述 …… 188 9.2 捕获和处理异常 …… 190"
                    ),
                },
                {
                    "id": "body",
                    "heading": "9.1 异常概述",
                    "content": "9.1 异常概述 Python 通过异常机制处理运行时错误。",
                },
            ]
        )
    )

    names = {node["name"] for node in graph["nodes"]}
    assert "第 9 章 异常处理" in names
    assert all("上机实验" not in name for name in names if name.startswith("第 9 章"))
