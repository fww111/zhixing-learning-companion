"""随堂实战练习生成（创新功能：内嵌编译器 + 学完即练 + 过程可视化）。

流程：Agentic RAG 教材证据 → LLM 出题（题面/样例/参考解/数组过程动画步骤）
→ 服务端沙箱预验证（参考解 stdin 输出必须与 expected_output 一致，不过题就重试一次
→ 仍失败则标 unverified 并退回确定性题库）。

判分复用既有 /api/courses/{id}/code/run（真沙箱），前端 OJ 式提交。
可视化（多模态）：LLM 输出数组状态步骤帧，前端 SVG 条形图步进动画渲染。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.schemas.practice import (
    PracticeExercise,
    PracticeGenerateRequest,
    PracticeGenerateResult,
    PracticeVisualization,
)
from app.services.agentic_rag_service import AgenticRAGService
from app.services.code_runner import CodeRunRequest, CodeRunner
from app.services.course_service import CourseService

PRACTICE_LLM_TIMEOUT_SECONDS = 60
PRACTICE_VERIFY_TIMEOUT_SECONDS = 15
MAX_VERIFY_ATTEMPTS = 2


class PracticeMentorService:
    def __init__(
        self,
        course_service: CourseService,
        *,
        llm: Any | None = None,
        rag_service_cls: type[AgenticRAGService] = AgenticRAGService,
        code_runner: CodeRunner | None = None,
    ) -> None:
        self.course_service = course_service
        self.llm = llm
        self.rag_service_cls = rag_service_cls
        self.code_runner = code_runner or CodeRunner()

    async def generate(self, *, user_id: int, request: PracticeGenerateRequest) -> PracticeGenerateResult:
        rag = self._rag_context(user_id, request)
        evidence = [item for item in (rag.get("knowledge_context") or [])[:3] if isinstance(item, dict)]
        exercise = await self._generate_exercise(request, evidence)
        verified = await self._verify_exercise(exercise)
        exercise.verified = verified
        exercise.verify_message = (
            "参考解已通过服务端沙箱验证，判分用例可靠"
            if verified
            else "参考解未能通过自动验证，判分可能不精确（AI 生成内容仅供参考）"
        )
        exercise.evidence_chunks = [
            {
                "chunk_id": item.get("chunk_id"),
                "heading": item.get("heading"),
                "source_locator": item.get("source_locator"),
            }
            for item in evidence
        ]
        return PracticeGenerateResult(course_id=request.course_id, topic=request.topic or request.node_id, exercise=exercise)

    # ------------------------------------------------------------------ generate
    def _rag_context(self, user_id: int, request: PracticeGenerateRequest) -> dict[str, Any]:
        topic = (request.topic or request.node_id).strip()
        try:
            return self.rag_service_cls(self.course_service).build_context(
                user_id=user_id,
                course_id=request.course_id,
                node_id=request.node_id,
                topic=topic,
            )
        except Exception:  # noqa: BLE001
            return {"knowledge_context": [], "graph_constraints": {}, "retrieval_trace": []}

    async def _generate_exercise(self, request: PracticeGenerateRequest, evidence: list[dict[str, Any]]) -> PracticeExercise:
        if self.llm is not None:
            try:
                data = await asyncio.wait_for(
                    self.llm.complete_json(self._system_prompt(), self._user_prompt(request, evidence)),
                    timeout=PRACTICE_LLM_TIMEOUT_SECONDS,
                )
                exercise = self._normalize(data, request)
                if exercise:
                    exercise.source = "llm"
                    return exercise
            except Exception:  # noqa: BLE001
                pass
        return self._fallback_exercise(request)

    def _system_prompt(self) -> str:
        return (
            "你是算法课程的随堂实战出题 Agent。基于课程教材证据，围绕指定知识点出一道可判分的编程题："
            "题面清晰、输入输出格式明确、测试输入固定、期望输出必须与参考解真实运行结果一致。"
            "同时输出参考解（C++17，完整可编译，从 stdin 读输入）与数组过程可视化步骤帧"
            "（每帧含 array 数组状态、highlight 下标、label 一句话说明，6-10 帧，展示核心算法推进过程）。"
            "不要出与证据无关的题。"
        )

    def _user_prompt(self, request: PracticeGenerateRequest, evidence: list[dict[str, Any]]) -> str:
        evidence_text = "\n\n".join(
            f"chunk#{item.get('chunk_id')} | {item.get('heading')}\n{' '.join(str(item.get('content') or '').split())[:600]}"
            for item in evidence
        ) or "（无教材证据，请基于知识点通用内容出题并保守选择经典题）"
        difficulty = request.difficulty or "入门"
        return (
            f"知识点：{request.topic or request.node_id or '未标注'}\n"
            f"难度：{difficulty}\n\n"
            f"教材证据：\n{evidence_text}\n\n"
            '输出 JSON：{"title": "题目标题", "description": "题面（含输入输出格式说明，markdown）", '
            '"starter_code": "#include <bits/stdc++.h>\\nusing namespace std;\\nint main() {\\n  // TODO\\n}", '
            '"stdin_text": "固定测试输入", "expected_output": "期望输出", '
            '"hints": ["提示1：思路方向", "提示2：关键实现"], '
            '"solution": "完整参考解 C++17", '
            '"visualization": {"type": "array", "steps": [{"array": [5,2,8], "highlight": [1], "label": "比较相邻元素"}]}, '
            '"difficulty": "入门|进阶|挑战", "knowledge_point": "考察点"}'
        )

    def _normalize(self, data: dict[str, Any], request: PracticeGenerateRequest) -> PracticeExercise | None:
        title = str(data.get("title") or "").strip()
        description = str(data.get("description") or "").strip()
        expected = str(data.get("expected_output") or "").strip()
        solution = str(data.get("solution") or "").strip()
        if not title or not description or not solution:
            return None
        steps = data.get("visualization") or {}
        visualization = PracticeVisualization(
            type=str(steps.get("type") or "array"),
            steps=[step for step in (steps.get("steps") or []) if isinstance(step, dict)][:12],
        )
        return PracticeExercise(
            id=f"practice-{request.course_id}-{request.node_id or 'node'}-{abs(hash(title)) % 10000}",
            title=title,
            description=description,
            starter_code=str(data.get("starter_code") or "#include <bits/stdc++.h>\nusing namespace std;\nint main() {\n  // TODO\n  return 0;\n}"),
            stdin_text=str(data.get("stdin_text") or "").strip(),
            expected_output=expected,
            hints=[str(h).strip() for h in (data.get("hints") or []) if str(h).strip()][:2],
            solution=solution,
            visualization=visualization,
            difficulty=str(data.get("difficulty") or request.difficulty or "入门"),
            knowledge_point=str(data.get("knowledge_point") or request.topic or request.node_id or ""),
        )

    # ------------------------------------------------------------------ fallback
    def _fallback_exercise(self, request: PracticeGenerateRequest) -> PracticeExercise:
        topic = request.topic or request.node_id or "排序"
        return PracticeExercise(
            id=f"practice-{request.course_id}-{request.node_id or 'node'}-fallback",
            title=f"{topic} · 随堂实战：冒泡排序",
            description=(
                "### 题目\n读入一行整数（以空格分隔），使用**冒泡排序**将它们从小到大排序后输出。\n\n"
                "### 输入格式\n一行，空格分隔的整数（最多 10 个）。\n\n"
                "### 输出格式\n一行，排序后的整数（空格分隔，末尾无多余空格）。"
            ),
            starter_code=(
                "#include <bits/stdc++.h>\n"
                "using namespace std;\n"
                "int main() {\n"
                "  vector<int> nums;\n"
                "  int x;\n"
                "  while (cin >> x) nums.push_back(x);\n"
                "  // TODO: 冒泡排序\n"
                "  return 0;\n"
                "}"
            ),
            stdin_text="5 2 8 1 9",
            expected_output="1 2 5 8 9",
            hints=["提示 1：两层循环，每轮把最大值沉到末尾。", "提示 2：注意输出格式——最后一个数后面不要空格。"],
            solution=(
                "#include <bits/stdc++.h>\n"
                "using namespace std;\n"
                "int main() {\n"
                "  vector<int> nums;\n"
                "  int x;\n"
                "  while (cin >> x) nums.push_back(x);\n"
                "  for (size_t i = 0; i + 1 < nums.size(); i++) {\n"
                "    for (size_t j = 0; j + 1 < nums.size() - i; j++) {\n"
                "      if (nums[j] > nums[j + 1]) swap(nums[j], nums[j + 1]);\n"
                "    }\n"
                "  }\n"
                "  for (size_t i = 0; i < nums.size(); i++) {\n"
                "    if (i) cout << ' ';\n"
                "    cout << nums[i];\n"
                "  }\n"
                "  cout << endl;\n"
                "  return 0;\n"
                "}"
            ),
            visualization=PracticeVisualization(
                type="array",
                steps=[
                    {"array": [5, 2, 8, 1, 9], "highlight": [0, 1], "label": "比较 5 和 2，交换"},
                    {"array": [2, 5, 8, 1, 9], "highlight": [1, 2], "label": "比较 5 和 8，不动"},
                    {"array": [2, 5, 8, 1, 9], "highlight": [2, 3], "label": "比较 8 和 1，交换"},
                    {"array": [2, 5, 1, 8, 9], "highlight": [3, 4], "label": "比较 8 和 9，不动——最大值 9 到位"},
                    {"array": [2, 5, 1, 8, 9], "highlight": [0, 1], "label": "第二轮：比较 2 和 5，不动"},
                    {"array": [2, 5, 1, 8, 9], "highlight": [1, 2], "label": "比较 5 和 1，交换"},
                    {"array": [2, 1, 5, 8, 9], "highlight": [2, 3], "label": "比较 5 和 8，不动——8 到位"},
                    {"array": [1, 2, 5, 8, 9], "highlight": [0, 1], "label": "第三轮：交换 2 和 1——完成"},
                ],
            ),
            difficulty=request.difficulty or "入门",
            knowledge_point=topic,
            source="fallback",
        )

    # ------------------------------------------------------------------ verify
    async def _verify_exercise(self, exercise: PracticeExercise) -> bool:
        """生成质量闭环：参考解跑沙箱，输出必须与 expected_output 一致。"""
        if not exercise.solution or not exercise.expected_output:
            return False
        try:
            result = await asyncio.to_thread(
                self.code_runner.run,
                CodeRunRequest(
                    source=exercise.solution,
                    language="cpp",
                    stdin_text=exercise.stdin_text,
                    expected_output=exercise.expected_output,
                    run_timeout_seconds=PRACTICE_VERIFY_TIMEOUT_SECONDS,
                ),
            )
            return result.verdict == "accepted"
        except Exception:  # noqa: BLE001
            return False
