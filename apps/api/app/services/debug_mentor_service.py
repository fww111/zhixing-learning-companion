"""AI 结对调试导师（创新功能，配合服务端真沙箱闭环）。

教育理念（human-in-the-loop，2026 教育研究共识：AI 直接代改会削弱学生
读错能力）：提示分级解锁——
  Level 1 指路：错因类别 + 排查方向（不给代码）
  Level 2 思路：结合课程知识库证据的伪代码/要点
  Level 3 修复：参考修复代码（学生确认后一键应用 → 沙箱重跑验证）

回答基于 Agentic RAG（课程原文证据 + 图谱约束），LLM 不可用时降级为
确定性诊断（编译器输出模式匹配）。
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from app.schemas.debug_mentor import DebugHintRequest, DebugHintResponse
from app.schemas.tutor import TutorEvidenceChunk
from app.services.agentic_rag_service import AgenticRAGService
from app.services.course_service import CourseService

DEBUG_LLM_TIMEOUT_SECONDS = 45
KNOWN_COMPILE_PATTERNS = [
    (r"was not declared in this scope", "存在未声明的标识符：检查变量/函数名拼写，以及是否漏了声明或头文件。"),
    (r"expected\s*';'", "缺少分号：检查上一条语句结尾。"),
    (r"expected .* before", "语法结构不完整：检查括号/大括号是否配对、函数调用参数是否齐全。"),
    (r"invalid conversion|cannot convert", "类型不匹配：检查赋值/传参两边的类型是否一致，必要时显式转换。"),
    (r"out of range|subscript|bound", "数组越界：C++ 数组下标从 0 开始，检查循环边界是否写到了 size。"),
    (r"uninitialized|segfault|runtime_error", "使用了未初始化或非法内存：确认变量已赋初值、指针已指向有效地址。"),
    (r"no match for", "运算符或函数参数不匹配：检查操作数类型与函数签名。"),
    (r"division by zero", "除零：先判断除数是否为 0 再做除法。"),
]


class DebugMentorService:
    def __init__(
        self,
        course_service: CourseService,
        *,
        llm: Any | None = None,
        rag_service_cls: type[AgenticRAGService] = AgenticRAGService,
    ) -> None:
        self.course_service = course_service
        self.llm = llm
        self.rag_service_cls = rag_service_cls

    async def analyze(self, *, user_id: int, request: DebugHintRequest) -> DebugHintResponse:
        rag = self._rag_context(user_id, request)
        evidence = [
            TutorEvidenceChunk(**item)
            for item in (rag.get("knowledge_context") or [])[:4]
            if isinstance(item, dict)
        ]
        diagnosis = ""
        hints: list[str] = []
        fixed_code = ""
        key_concept = ""
        if self.llm is not None:
            try:
                data = await asyncio.wait_for(
                    self.llm.complete_json(
                        self._system_prompt(),
                        self._user_prompt(request, evidence),
                    ),
                    timeout=DEBUG_LLM_TIMEOUT_SECONDS,
                )
                diagnosis = str(data.get("diagnosis") or "").strip()
                hints = [str(item).strip() for item in (data.get("hints") or []) if str(item).strip()][:3]
                fixed_code = str(data.get("fixed_code") or "").strip()
                key_concept = str(data.get("key_concept") or "").strip()
            except Exception:  # noqa: BLE001
                diagnosis = ""

        category = self._categorize(request)
        if not diagnosis or not hints:
            fallback = self._fallback(request, evidence, category)
            diagnosis = diagnosis or fallback["diagnosis"]
            hints = hints or fallback["hints"]
            key_concept = key_concept or fallback["key_concept"]
            fixed_code = fixed_code or fallback["fixed_code"]

        return DebugHintResponse(
            diagnosis=diagnosis,
            error_category=category,
            hints=hints,
            fixed_code=fixed_code,
            key_concept=key_concept,
            evidence_chunks=evidence,
            verification=self._verification(evidence, request),
        )

    # ------------------------------------------------------------------ helpers
    def _rag_context(self, user_id: int, request: DebugHintRequest) -> dict[str, Any]:
        topic = (request.topic or request.node_id or request.error_output[:60]).strip()
        try:
            return self.rag_service_cls(self.course_service).build_context(
                user_id=user_id,
                course_id=request.course_id,
                node_id=request.node_id,
                topic=topic,
            )
        except Exception:  # noqa: BLE001
            return {"knowledge_context": [], "graph_constraints": {}, "retrieval_trace": []}

    @staticmethod
    def _categorize(request: DebugHintRequest) -> str:
        blob = f"{request.error_output} {request.verdict}".lower()
        if request.verdict == "timeout" or "timeout" in blob:
            return "runtime"
        if request.verdict == "compile_error" or "error:" in blob or "expected" in blob:
            return "syntax"
        if "conversion" in blob or "cannot convert" in blob or "no match" in blob:
            return "type"
        if "range" in blob or "bound" in blob or "segfault" in blob:
            return "boundary"
        if request.verdict == "wrong_answer":
            return "output"
        return "logic"

    def _system_prompt(self) -> str:
        return (
            "你是个性化学习平台的 AI 结对调试导师。学生刚在服务端沙箱跑代码失败，"
            "你需要像结对编程伙伴一样帮他：诊断根因 → 给出三级递进提示（第一条只指方向不写代码，"
            "第二条给伪代码思路，第三条给参考修复代码），并点出涉及的知识点概念。"
            "讲解必须依据课程知识库证据，不要编造教材内容；教育原则上不鼓励直接代改——"
            "修复代码只在第三级出现，供学生对照学习。"
        )

    def _user_prompt(self, request: DebugHintRequest, evidence: list[TutorEvidenceChunk]) -> str:
        evidence_text = "\n\n".join(
            f"chunk#{chunk.chunk_id} | {chunk.heading}\n{' '.join(chunk.content.split())[:600]}"
            for chunk in evidence
        ) or "（未检索到课程证据，基于错误输出分析）"
        stdin_note = f"\n测试输入：{request.stdin_text[:500]}" if request.stdin_text else ""
        output_note = ""
        if request.verdict == "wrong_answer":
            output_note = f"\n期望输出：{request.expected_output[:500]}\n实际输出：{request.actual_output[:500]}"
        return (
            f"知识点：{request.topic or request.node_id or '未标注'}\n"
            f"失败类别（初步）：{request.verdict or 'unknown'}\n"
            f"学生代码：\n{request.source_code[:6000]}\n"
            f"编译器/运行错误输出：\n{request.error_output[:3000] or '（无）'}"
            f"{stdin_note}{output_note}\n\n"
            f"课程原文证据：\n{evidence_text}\n\n"
            '输出 JSON：{"diagnosis": "根因诊断（2-3 句）", "hints": ["提示1：只指排查方向", '
            '"提示2：伪代码思路", "提示3：修复要点或直接给 fixed_code 的说明"], '
            '"fixed_code": "完整可编译的参考修复代码（无则空串）", "key_concept": "涉及的核心知识点"}'
        )

    def _fallback(
        self,
        request: DebugHintRequest,
        evidence: list[TutorEvidenceChunk],
        category: str,
    ) -> dict[str, Any]:
        citation = f"chunk#{evidence[0].chunk_id}" if evidence and evidence[0].chunk_id is not None else "课程知识库"
        matched_hint = ""
        for pattern, hint in KNOWN_COMPILE_PATTERNS:
            if re.search(pattern, request.error_output, re.IGNORECASE):
                matched_hint = hint
                break
        if category == "syntax":
            diagnosis = matched_hint or "编译器报了语法错误，程序还没有通过编译。先读懂编译器指出的那一行。"
            hints = [
                "Level 1：定位编译器输出的第一个 error 所在行——从那一行和它的上一行找问题。",
                "Level 2：逐项核对：语句是否以分号结尾、大括号是否配对、变量是否先声明再使用。",
                "Level 3：把编译器提示的类型/名称逐一修正后再运行；还不行就把该行与教材示例（" + citation + "）逐字符对比。",
            ]
        elif category == "runtime":
            diagnosis = matched_hint or "程序能编译但运行时出错或超时：常见原因是死循环、等待输入或非法内存访问。"
            hints = [
                "Level 1：确认程序有没有在读 input/cin——如果题目没给输入，去掉等待输入的语句。",
                "Level 2：检查循环终止条件是否一定会到达（循环变量是否更新），指针是否指向有效地址。",
                "Level 3：在循环体里加一个计数上限或在关键位置打印进度，定位卡住的位置。",
            ]
        elif category == "boundary":
            diagnosis = matched_hint or "发生了越界/非法访问：C++ 的数组下标从 0 开始，越界不会立刻报错但会破坏内存。"
            hints = [
                "Level 1：找出所有数组下标表达式，检查最大下标是否是 size - 1。",
                "Level 2：循环边界写成 i < size 而不是 i <= size；空容器先判断再访问。",
                "Level 3：把可疑下标打印出来对照题目数据范围验证。",
            ]
        elif category == "type":
            diagnosis = matched_hint or "存在类型不匹配：赋值、传参或运算符两侧的类型不一致。"
            hints = [
                "Level 1：看编译器指出'cannot convert/no match'的两个类型分别是什么。",
                "Level 2：核对教材（" + citation + "）中该函数/运算符的签名，确认参数类型与顺序。",
                "Level 3：显式转换（static_cast）或改用正确类型的变量保存中间结果。",
            ]
        elif category == "output":
            diagnosis = "程序正常运行，但输出与期望不一致：先逐字符对比两份输出，再定位逻辑。"
            hints = [
                "Level 1：对比期望与实际输出——是格式（空格/换行）问题还是数值问题？",
                "Level 2：格式问题检查输出语句的写法；数值问题用题目样例在纸上模拟每一步变量值。",
                "Level 3：把中间变量打印出来和手算对照，找出第一次偏离的位置。",
            ]
        else:
            diagnosis = "输出不对但编译运行都正常：核心逻辑可能与题目规则有偏差。"
            hints = [
                "Level 1：重新读题，把规则逐条列出，对照代码找漏掉的规则。",
                "Level 2：用教材（" + citation + "）里的标准写法对照自己的实现，看流程是否一致。",
                "Level 3：构造一个最小失败样例，手算正确答案再和程序输出对比。",
            ]
        return {
            "diagnosis": diagnosis,
            "hints": hints,
            "key_concept": request.topic or "程序调试",
            "fixed_code": "",
        }

    @staticmethod
    def _verification(evidence: list[TutorEvidenceChunk], request: DebugHintRequest) -> dict[str, Any]:
        return {
            "agent": "DebugMentorAgent",
            "decision": "accepted" if evidence else "fallback",
            "evidence_count": len(evidence),
            "verdict_basis": request.verdict or "unknown",
        }
