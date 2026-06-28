import asyncio

from app.agents.coding_agent import CodingAgent
from app.agents.document_agent import DocumentAgent
from app.agents.exercise_agent import ExerciseAgent
from app.agents.multimodal_agent import MultimodalAgent
from app.llm.client import LLMClient
from app.models.profile import StudentProfile
from app.models.resource import ResourceType
from app.services.resource_service import ResourceService


def test_resource_agents_generate_six_resource_types_for_same_topic():
    profile = StudentProfile.from_conversation("计算机大二，想学机器学习，梯度下降薄弱，喜欢图解和代码。")
    llm = LLMClient(api_key="", mock=True)

    async def generate_all():
        return [
            await DocumentAgent(llm).generate(profile, "梯度下降"),
            await ExerciseAgent(llm).generate(profile, "梯度下降"),
            *(await MultimodalAgent(llm).generate(profile, "梯度下降")),
            await CodingAgent(llm).generate(profile, "梯度下降"),
        ]

    resources = asyncio.run(generate_all())

    assert {resource.type for resource in resources} == {
        ResourceType.DOCUMENT,
        ResourceType.EXERCISE,
        ResourceType.MIND_MAP,
        ResourceType.READING,
        ResourceType.VIDEO,
        ResourceType.CODE_LAB,
    }
    assert all(resource.topic == "梯度下降" for resource in resources)
    assert all(resource.quality_score is not None for resource in resources)


def test_mock_exercise_agent_uses_professional_topic_questions_not_pass_label_output():
    profile = StudentProfile.from_conversation("计算机大一，正在学习 Python 版本，喜欢代码练习。")
    llm = LLMClient(api_key="", mock=True)

    resource = asyncio.run(ExerciseAgent(llm).generate(profile, "1.2.1 Python 的版本"))

    assert "Python" in resource.content
    assert "Python 2" in resource.content or "Python 3" in resource.content
    assert "1.2.1 Python 的版本 达标" not in resource.content
    assert "只作为章节标题" not in resource.content


def test_mock_exercise_agent_generates_python_variable_assessment_not_generic_or_c_code():
    profile = StudentProfile.from_conversation("计算机大一，正在学习 Python 变量、输入输出和变量交换，喜欢代码练习。")
    llm = LLMClient(api_key="", mock=True)

    resource = asyncio.run(ExerciseAgent(llm).generate(profile, "2.1 Python变量与输入输出"))

    assert "变量名" in resource.content or "标识符" in resource.content
    assert "2nd_value" in resource.content
    assert "input()" in resource.content
    assert "num1" in resource.content and "num2" in resource.content
    assert "交换前" in resource.content and "交换后" in resource.content
    assert "核心作用" not in resource.content
    assert "练习结果不符合预期" not in resource.content
    assert "#include <stdio.h>" not in resource.content
    assert "printf" not in resource.content


def test_mock_exercise_agent_generates_pseudocode_assessment_not_generic_or_c_code():
    profile = StudentProfile.from_conversation("计算机大一，正在学习算法与伪代码，喜欢用代码验证步骤。")
    llm = LLMClient(api_key="", mock=True)

    resource = asyncio.run(ExerciseAgent(llm).generate(profile, "2.5.5 用伪代码表示算法"))

    assert "伪代码" in resource.content
    assert "顺序" in resource.content or "选择" in resource.content or "循环" in resource.content
    assert "累加" in resource.content
    assert "核心作用" not in resource.content
    assert "练习结果不符合预期" not in resource.content
    assert "#include <stdio.h>" not in resource.content
    assert "printf" not in resource.content


def test_mock_exercise_agent_generates_professional_questions_across_common_topics():
    profile = StudentProfile.from_conversation("计算机大一，正在学习程序设计基础，需要专业练习题检测掌握情况。")
    llm = LLMClient(api_key="", mock=True)
    cases = [
        ("3.2 if条件分支语句", ["if", "条件", "else"], ["#include <stdio.h>", "printf"]),
        ("4.1 for循环与range函数", ["for", "range", "循环"], ["#include <stdio.h>", "printf"]),
        ("5.3 函数定义与参数传递", ["def", "参数", "return"], ["#include <stdio.h>", "printf"]),
        ("6.2 列表索引与遍历", ["列表", "索引", "遍历"], ["#include <stdio.h>", "printf"]),
        ("8.1 文件读写 open函数", ["open", "文件", "读取"], ["#include <stdio.h>", "printf"]),
        ("C语言程序设计 5.2 一维数组的定义和引用", ["数组", "下标", "int"], ["Python 简洁"]),
        ("C语言程序设计 7.1 指针变量与地址", ["指针", "地址", "&"], ["Python 简洁"]),
        ("C语言程序设计 6.1 函数定义与调用", ["函数", "参数", "return"], ["Python 简洁"]),
    ]

    for topic, expected_terms, forbidden_terms in cases:
        resource = asyncio.run(ExerciseAgent(llm).generate(profile, topic))
        for expected_term in expected_terms:
            assert expected_term in resource.content, f"{topic} should include {expected_term}\n{resource.content}"
        assert "核心作用" not in resource.content
        assert "只知道" not in resource.content
        assert "练习结果不符合预期" not in resource.content
        for forbidden_term in forbidden_terms:
            assert forbidden_term not in resource.content, f"{topic} should not include {forbidden_term}\n{resource.content}"


def test_exercise_agent_prompt_requires_topic_specific_professional_assessment():
    class RecordingLLM:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def complete_text(self, system_prompt: str, user_prompt: str) -> str:
            self.calls.append((system_prompt, user_prompt))
            return "1. Python 3 中 print 的正确用法是什么？\nA. print(x)\nB. print x\nC. echo x\n答案：A"

    profile = StudentProfile.from_conversation("计算机大一，正在学习 Python 版本。")
    llm = RecordingLLM()

    asyncio.run(ExerciseAgent(llm).generate(profile, "1.2.1 Python 的版本"))

    assert llm.calls
    prompt = llm.calls[0][1]
    assert "不能生成询问是否记住标题、是否记住要点、是否看过视频" in prompt
    assert "编程题必须随知识点变化" in prompt
    assert "本知识点的专业概念、应用场景、错误诊断或代码行为" in prompt


def test_coding_agent_generates_c_code_lab_for_c_course_topics():
    class RecordingLLM:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def complete_text(self, system_prompt: str, user_prompt: str) -> str:
            self.calls.append((system_prompt, user_prompt))
            return "```c\n#include <stdio.h>\nint main(void) {\n  printf(\"ok\\n\");\n  return 0;\n}\n```"

    profile = StudentProfile.from_conversation("大一，正在学习C语言程序设计，喜欢代码练习。")
    llm = RecordingLLM()

    resource = asyncio.run(CodingAgent(llm).generate(profile, "6.3.2 字符数组的初始化"))

    assert llm.calls
    prompt = llm.calls[0][1]
    assert "C 语言代码实操任务" in prompt
    assert "```c" in prompt
    assert "```python" not in prompt
    assert "c" in resource.tags
    assert "python" not in resource.tags
    assert "#include <stdio.h>" in resource.content


def test_resource_agents_use_knowledge_context_as_llm_prompt_not_final_content():
    class RecordingLLM:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def complete_text(self, system_prompt: str, user_prompt: str) -> str:
            self.calls.append((system_prompt, user_prompt))
            return "AI生成内容：围绕列表的概念、操作和易错点重新组织讲解。"

    profile = StudentProfile.from_conversation("计算机大二，Python列表薄弱，喜欢图解和代码。")
    llm = RecordingLLM()
    raw_chunk = "RAW_KB_FRAGMENT_SHOULD_ONLY_APPEAR_IN_PROMPT"

    resource = asyncio.run(
        DocumentAgent(llm).generate(
            profile,
            "Python列表",
            knowledge_context=[
                {
                    "chunk_id": 7,
                    "source_locator": "page 21",
                    "content": raw_chunk,
                }
            ],
        )
    )

    assert llm.calls
    assert raw_chunk in llm.calls[0][1]
    assert "AI生成内容" in resource.content
    assert raw_chunk not in resource.content
    assert "page 21" in resource.recommendation_reason


def test_openmaic_requirement_adds_3d_interaction_for_abstract_algorithm_topics():
    class EmptyLLM:
        async def complete_text(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
            return "课堂先解释递归调用栈，再安排交互探索，最后随堂测验。"

    requirement = asyncio.run(
        ResourceService(EmptyLLM())._openmaic_requirement(
            profile=StudentProfile.from_conversation("大一，喜欢图解，基础一般。"),
            topic="递归函数调用栈",
            knowledge_context=[{"chunk_id": 1, "source_locator": "page 12", "content": "递归函数在调用时会形成层层调用关系。"}],
            graph_constraints={
                "current_node": {"id": "node-1", "name": "递归函数调用栈", "node_type": "knowledge_point"},
                "parent": {"id": "chapter-6", "name": "函数"},
                "predecessors": [],
                "successors": [],
                "related": [],
            },
            analysis_plan={},
        )
    )

    assert "widgetType: visualization3d" in requirement
    assert "调用栈" in requirement
    assert "Qwen TTS" in requirement
    assert "VoxCPM2" not in requirement
    assert "enableTTS" in requirement


def test_openmaic_requirement_adds_code_simulation_for_practical_programming_topics():
    class EmptyLLM:
        async def complete_text(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
            return "课堂演示文件读写流程，安排代码实验，然后完成即时练习。"

    requirement = asyncio.run(
        ResourceService(EmptyLLM())._openmaic_requirement(
            profile=None,
            topic="Python 文件读写实操",
            knowledge_context=[{"chunk_id": 2, "source_locator": "page 56", "content": "使用 open 函数读写文件。"}],
            graph_constraints={
                "current_node": {"id": "node-2", "name": "Python 文件读写实操", "node_type": "method"},
                "parent": {"id": "chapter-8", "name": "文件"},
                "predecessors": [],
                "successors": [],
                "related": [],
            },
            analysis_plan={},
        )
    )

    assert "widgetType: code" in requirement
    assert "在线编程" in requirement
    assert "open 函数" in requirement


def test_openmaic_requirement_adds_game_interaction_for_reinforcement_topics():
    class EmptyLLM:
        async def complete_text(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
            return "课堂讲解选择结构易错点，并通过挑战巩固条件判断。"

    requirement = asyncio.run(
        ResourceService(EmptyLLM())._openmaic_requirement(
            profile=None,
            topic="if 语句易错点练习挑战",
            knowledge_context=[{"chunk_id": 3, "source_locator": "page 42", "content": "if 语句根据条件决定执行路径。"}],
            graph_constraints={
                "current_node": {"id": "node-3", "name": "if 语句易错点练习挑战", "node_type": "exercise"},
                "parent": {"id": "chapter-3", "name": "选择结构"},
                "predecessors": [],
                "successors": [],
                "related": [],
            },
            analysis_plan={},
        )
    )

    assert "widgetType: game" in requirement
    assert "挑战" in requirement
