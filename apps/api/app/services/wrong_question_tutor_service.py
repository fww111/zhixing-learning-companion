from __future__ import annotations

import asyncio
import re
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.tutor import TutorEvidenceChunk
from app.schemas.wrong_question_tutor import (
    InteractiveAnswerRequest,
    InteractiveAnswerVerdict,
    VariationBundle,
    VariationQuestion,
    WrongQuestionContext,
    WrongQuestionExplanation,
)
from app.services.agentic_rag_service import AgenticRAGService
from app.services.course_service import CourseService

WQ_LLM_TIMEOUT_SECONDS = 45
MAX_VARIATION_QUESTIONS = 3


class WrongQuestionTutorService:
    """错题三步闭环：AI 讲清楚 → 拓展同类题 → AI 问学生答。

    全部回答以课程知识库证据为依据（Agentic RAG），LLM 不可用时降级为
    确定性 mock 内容，保证无 Key 环境可演示。
    """

    def __init__(
        self,
        course_service: CourseService,
        *,
        db: Session | None = None,
        llm: Any | None = None,
        rag_service_cls: type[AgenticRAGService] = AgenticRAGService,
    ) -> None:
        self.course_service = course_service
        self.db = db
        self.llm = llm
        self.rag_service_cls = rag_service_cls

    # ------------------------------------------------------------------ explain
    async def explain(self, *, user_id: int, context: WrongQuestionContext) -> WrongQuestionExplanation:
        rag = self._rag_context(user_id, context)
        evidence = self._evidence_chunks(rag)
        diagnosis = ""
        explanation = ""
        key_points: list[str] = []
        if self.llm is not None and evidence:
            try:
                data = await asyncio.wait_for(
                    self.llm.complete_json(
                        self._explain_system_prompt(),
                        self._explain_user_prompt(context, evidence),
                    ),
                    timeout=WQ_LLM_TIMEOUT_SECONDS,
                )
                diagnosis = str(data.get("diagnosis") or "").strip()
                explanation = str(data.get("explanation") or "").strip()
                key_points = [str(item).strip() for item in (data.get("key_points") or []) if str(item).strip()]
            except Exception:
                diagnosis = ""
                explanation = ""

        if not diagnosis or not explanation:
            fallback = self._fallback_explanation(context, evidence)
            diagnosis = diagnosis or fallback["diagnosis"]
            explanation = explanation or fallback["explanation"]
            key_points = key_points or fallback["key_points"]

        return WrongQuestionExplanation(
            diagnosis=diagnosis,
            explanation=explanation,
            key_points=key_points[:5],
            evidence_chunks=evidence,
            verification_report=self._verification_report(evidence),
        )

    # --------------------------------------------------------------- variations
    async def variations(
        self,
        *,
        user_id: int,
        context: WrongQuestionContext,
        count: int = MAX_VARIATION_QUESTIONS,
    ) -> VariationBundle:
        rag = self._rag_context(user_id, context)
        evidence = self._evidence_chunks(rag)
        count = max(2, min(int(count or MAX_VARIATION_QUESTIONS), MAX_VARIATION_QUESTIONS))
        questions: list[VariationQuestion] = []
        if self.llm is not None and evidence:
            try:
                data = await asyncio.wait_for(
                    self.llm.complete_json(
                        self._variations_system_prompt(),
                        self._variations_user_prompt(context, evidence, count),
                    ),
                    timeout=WQ_LLM_TIMEOUT_SECONDS,
                )
                questions = self._normalize_questions(data.get("questions"), count)
            except Exception:
                questions = []

        if not questions:
            questions = self._fallback_variations(context, count)

        return VariationBundle(
            node_id=context.node_id,
            topic=context.topic or context.prompt[:40],
            source_question_type=context.question_type,
            questions=questions,
            evidence_chunks=evidence,
        )

    # ------------------------------------------------------------------- answer
    async def answer(self, *, user_id: int, request: InteractiveAnswerRequest) -> InteractiveAnswerVerdict:
        question = request.question
        reference = question.reference_answer.strip()

        # 选择题：客观判分优先，点评仍走证据约束的 LLM；简答题：LLM 判分。
        objective_correct: bool | None = None
        if question.question_type == "quiz":
            objective_correct = (
                request.student_answer_index is not None
                and question.correct_answer_index is not None
                and request.student_answer_index == question.correct_answer_index
            )

        comment = ""
        score: int | None = None
        correct: bool | None = objective_correct
        if self.llm is not None:
            try:
                data = await asyncio.wait_for(
                    self.llm.complete_json(
                        self._verdict_system_prompt(),
                        self._verdict_user_prompt(request, objective_correct),
                    ),
                    timeout=WQ_LLM_TIMEOUT_SECONDS,
                )
                comment = str(data.get("comment") or "").strip()
                raw_score = data.get("score")
                if isinstance(raw_score, (int, float)) and 0 <= float(raw_score) <= 100:
                    score = int(raw_score)
                if correct is None and isinstance(data.get("correct"), bool):
                    correct = data["correct"]
            except Exception:
                comment = ""

        if correct is None:
            correct = self._heuristic_short_answer_correct(question, request.student_answer_text)
        if score is None:
            score = 100 if correct else max(0, 40 if objective_correct is False else 30)
        if not comment:
            comment = self._fallback_verdict_comment(request, correct)

        return InteractiveAnswerVerdict(
            correct=correct,
            score=score,
            comment=comment,
            reference_answer=reference,
            focus=question.focus,
        )

    # ------------------------------------------------------------- rag helpers
    def _rag_context(self, user_id: int, context: WrongQuestionContext) -> dict[str, Any]:
        topic = (context.topic or context.prompt[:60]).strip()
        try:
            return self.rag_service_cls(self.course_service).build_context(
                user_id=user_id,
                course_id=context.course_id,
                node_id=context.node_id,
                topic=topic,
            )
        except Exception:
            return {"knowledge_context": [], "graph_constraints": {}, "retrieval_trace": []}

    def _evidence_chunks(self, rag: dict[str, Any]) -> list[TutorEvidenceChunk]:
        items = rag.get("knowledge_context") or []
        return [TutorEvidenceChunk(**item) for item in items[:4] if isinstance(item, dict)]

    def _verification_report(self, evidence: list[TutorEvidenceChunk]) -> dict[str, Any]:
        return {
            "agent": "WrongQuestionTutorAgent",
            "decision": "accepted" if evidence else "fallback",
            "evidence_count": len(evidence),
            "citation_chunk_ids": [chunk.chunk_id for chunk in evidence if chunk.chunk_id is not None],
            "hallucination_risk": "low" if evidence else "medium",
        }

    @staticmethod
    def _format_evidence(chunk: TutorEvidenceChunk) -> str:
        content = " ".join(chunk.content.split())
        if len(content) > 1000:
            content = f"{content[:1000]}..."
        label = f"chunk#{chunk.chunk_id}" if chunk.chunk_id is not None else "chunk#unknown"
        return f"{label} | {chunk.source_locator} | {chunk.heading}\n{content}"

    # ----------------------------------------------------------------- prompts
    def _explain_system_prompt(self) -> str:
        return (
            "你是个性化学习平台的错题讲解智能体。任务是给学生讲清楚一道错题："
            "先诊断错误原因（对比学生答案与正确答案/期望输出，指出具体的认知偏差或技能缺口），"
            "再基于课程知识库证据讲解正确思路（概念 → 规则 → 例子），最后给出可操作的自检要点。"
            "讲解必须依据给出的课程原文证据，引用处标注 chunk#编号；证据不足时明确说明，不要编造教材内容。"
            "面向学生输出，语气鼓励但直接，不复述题目本身。"
        )

    def _explain_user_prompt(
        self,
        context: WrongQuestionContext,
        evidence: list[TutorEvidenceChunk],
    ) -> str:
        evidence_text = "\n\n".join(self._format_evidence(chunk) for chunk in evidence)
        if context.question_type == "quiz":
            answer_block = (
                f"学生选择：{context.selected_answer or '未作答'}\n"
                f"正确答案：{context.correct_answer}\n"
                f"选项：{json_dumps_cn(context.options)}\n"
            )
        else:
            answer_block = (
                f"学生代码：\n{context.code[:1200]}\n"
                f"实际输出：{context.actual_output or '（无输出）'}\n"
                f"期望输出：{context.expected_output}\n"
                f"尝试次数：{context.attempts}\n"
            )
        return (
            f"知识点：{context.topic or '未标注'}（node_id={context.node_id or 'unknown'}）\n"
            f"题目类型：{'选择题' if context.question_type == 'quiz' else '编程题'}\n"
            f"题目：{context.prompt}\n"
            f"{answer_block}\n"
            f"课程原文证据：\n{evidence_text or '（未检索到匹配证据，请基于题目本身讲解并说明证据不足）'}\n\n"
            '输出 JSON：{"diagnosis": "错因诊断（2-3 句）", "explanation": "讲解正文 markdown（概念/规则/例子/自检，400字内）", "key_points": ["要点1", "要点2", "要点3"]}'
        )

    def _variations_system_prompt(self) -> str:
        return (
            "你是个性化学习平台的变式题生成智能体。基于一道错题和课程知识库证据，"
            "生成同一知识点的变式练习题：变式必须覆盖同一核心规则的不同侧面（概念辨析/迁移应用/易错陷阱），"
            "不得与原题题干重复。选择题给出 3-4 个选项和正确答案下标；简答题给出简短参考答案。"
            "题目表述与证据一致，不要引入教材未覆盖的概念。"
        )

    def _variations_user_prompt(
        self,
        context: WrongQuestionContext,
        evidence: list[TutorEvidenceChunk],
        count: int,
    ) -> str:
        evidence_text = "\n\n".join(self._format_evidence(chunk) for chunk in evidence)
        return (
            f"知识点：{context.topic or '未标注'}\n"
            f"原错题：{context.prompt}\n"
            f"学生暴露的问题：{context.selected_answer or context.actual_output or '思路错误'}\n\n"
            f"课程原文证据：\n{evidence_text or '（无匹配证据，围绕知识点本身出题）'}\n\n"
            f"生成 {count} 道变式题（至少 1 道简答题）。\n"
            '输出 JSON：{"questions": [{"id": "v1", "question_type": "quiz|short_answer", "prompt": "题干", '
            '"options": ["A内容", "B内容"], "correct_answer_index": 0, "reference_answer": "简答题参考答案", '
            '"focus": "考察点", "difficulty": "基础|进阶|挑战"}]}，'
            "选择题 options/correct_answer_index 必填，简答题给 reference_answer 且 options 为空数组。"
        )

    def _verdict_system_prompt(self) -> str:
        return (
            "你是个性化学习平台的判分点评智能体。学生刚回答了一道由你出的变式题，"
            "请判断对错并给出鼓励式点评：指出答对时的关键步骤，或答错时的具体偏差与纠正方向，"
            "点评要贴合题目考察点，不超过 120 字。选择题已客观判分时不要推翻客观结果。"
        )

    def _verdict_user_prompt(
        self,
        request: InteractiveAnswerRequest,
        objective_correct: bool | None,
    ) -> str:
        question = request.question
        if question.question_type == "quiz":
            options_text = json_dumps_cn(question.options)
            student_answer = (
                question.options[request.student_answer_index]
                if request.student_answer_index is not None and 0 <= request.student_answer_index < len(question.options)
                else "未作答"
            )
            answer_block = (
                f"题型：选择题\n选项：{options_text}\n正确答案下标：{question.correct_answer_index}\n学生选择下标：{request.student_answer_index}（{student_answer}）\n客观判定：{objective_correct}"
            )
        else:
            answer_block = (
                f"题型：简答题\n参考答案：{question.reference_answer}\n学生作答：{request.student_answer_text[:600] or '（空）'}"
            )
        return (
            f"知识点：{request.topic or '未标注'}\n"
            f"题目：{question.prompt}\n"
            f"{answer_block}\n\n"
            '输出 JSON：{"correct": true|false, "score": 0-100, "comment": "点评"}'
        )

    # ------------------------------------------------------------- normalizers
    def _normalize_questions(self, raw: Any, count: int) -> list[VariationQuestion]:
        if not isinstance(raw, list):
            return []
        questions: list[VariationQuestion] = []
        for index, item in enumerate(raw[:count]):
            if not isinstance(item, dict):
                continue
            question_type = "short_answer" if item.get("question_type") == "short_answer" else "quiz"
            options = [str(option).strip() for option in (item.get("options") or []) if str(option).strip()]
            prompt = str(item.get("prompt") or "").strip()
            if not prompt:
                continue
            correct_index: int | None = None
            reference = str(item.get("reference_answer") or "").strip()
            if question_type == "quiz" and options:
                raw_index = item.get("correct_answer_index")
                if isinstance(raw_index, int) and 0 <= raw_index < len(options):
                    correct_index = raw_index
                else:
                    # 选项缺失正确下标时降级为简答题，保证可判分
                    question_type = "short_answer"
                    if isinstance(raw_index, int) and 0 <= raw_index < len(options):
                        reference = reference or options[raw_index]
            if question_type == "quiz" and correct_index is None:
                continue
            if question_type == "short_answer" and not reference:
                continue
            difficulty = str(item.get("difficulty") or "基础")
            if difficulty not in {"基础", "进阶", "挑战"}:
                difficulty = "基础"
            questions.append(
                VariationQuestion(
                    id=str(item.get("id") or f"v{index + 1}") or f"v{index + 1}",
                    question_type=question_type,
                    prompt=prompt,
                    options=options if question_type == "quiz" else [],
                    correct_answer_index=correct_index,
                    reference_answer=reference,
                    focus=str(item.get("focus") or "").strip(),
                    difficulty=difficulty,  # type: ignore[arg-type]
                )
            )
        return questions

    def _heuristic_short_answer_correct(self, question: VariationQuestion, student_text: str) -> bool:
        """LLM 不可用时按参考答案关键词重合率粗判简答题。"""
        reference = question.reference_answer.strip()
        student = (student_text or "").strip()
        if not reference or not student:
            return False
        ref_terms = {term for term in re.findall(r"[\u4e00-\u9fff]{2,6}|[A-Za-z_][A-Za-z0-9_]{1,}", reference) if term}
        if not ref_terms:
            return False
        hit = sum(1 for term in ref_terms if term.lower() in student.lower())
        return hit / len(ref_terms) >= 0.5

    # ---------------------------------------------------------------- fallbacks
    def _fallback_explanation(self, context: WrongQuestionContext, evidence: list[TutorEvidenceChunk]) -> dict[str, Any]:
        citation = f"chunk#{evidence[0].chunk_id}" if evidence and evidence[0].chunk_id is not None else "chunk#unknown"
        evidence_hint = evidence[0].heading if evidence else "当前知识点（建议补充该章节教材材料）"
        if context.question_type == "quiz":
            diagnosis = (
                f"你在选择题上选择了“{context.selected_answer or '未作答'}”，而正确答案是“{context.correct_answer}”。"
                "这说明对核心规则的判定条件理解存在偏差，属于概念辨析类错误。"
            )
            explanation = (
                f"### 先看规则\n这道题考察的知识点是「{context.topic or evidence_hint}」。"
                f"课程知识库中的关键依据（{citation}）给出了它的判定规则，正确选项正是这一规则的直接体现。\n\n"
                "### 为什么其它选项不对\n错误选项通常是规则的常见误读：把必要条件当成充分条件、"
                "或把特例当成一般情况。对照题干逐项排除，就能锁定正确答案。\n\n"
                f"### 自检\n用一句话复述「{context.topic or evidence_hint}」的判定规则，"
                "再举一个自己的例子验证，能说清楚就说明真正掌握了。"
            )
        else:
            diagnosis = (
                f"你的程序实际输出为“{context.actual_output or '（无输出）'}”，与期望输出“{context.expected_output}”不一致"
                f"（已尝试 {max(1, context.attempts)} 次）。这通常出在输出格式、边界处理或核心逻辑三处之一。"
            )
            explanation = (
                f"### 定位差距\n先逐字符对比实际输出与期望输出：多空格/换行属于格式问题；"
                "数值不对属于核心逻辑问题；无输出可能是编译或运行错误。\n\n"
                f"### 正确思路\n课程知识库依据（{citation}）给出了该知识点的标准写法。"
                f"「{context.topic or evidence_hint}」的关键步骤是：明确输入 → 处理核心逻辑 → 按题目要求的格式输出。\n\n"
                "### 自检\n改完后先在脑内用题目样例走一遍代码，确认每一步的变量值，再运行验证。"
            )
        return {
            "diagnosis": diagnosis,
            "explanation": explanation,
            "key_points": [
                "对照判定规则逐项排除错误选项",
                "把实际输出与期望输出逐字符对比定位差距",
                "用自己的例子复述规则完成自检",
            ],
        }

    def _fallback_variations(self, context: WrongQuestionContext, count: int) -> list[VariationQuestion]:
        topic = context.topic or "该知识点"
        pool: list[VariationQuestion] = [
            VariationQuestion(
                id="v1",
                question_type="quiz",
                prompt=f"围绕「{topic}」：下列哪项最准确地描述了它的核心判定规则？",
                options=[
                    "凭印象选择与原错题相同的选项",
                    "按照课程定义的判定条件逐项核对题干情境",
                    "只看选项长短，表述最详细的往往正确",
                    "题目没有给出足够信息，无法判断",
                ],
                correct_answer_index=1,
                reference_answer="",
                focus="概念辨析",
                difficulty="基础",
            ),
            VariationQuestion(
                id="v2",
                question_type="quiz",
                prompt=f"围绕「{topic}」：在迁移到一个新情境时，第一步应该做什么？",
                options=[
                    "直接照抄原错题的答案",
                    "跳过分析，先写代码再试错",
                    "识别新情境与已学规则的对应关系，再套用判定条件",
                    "认为新情境一定不适用已学规则",
                ],
                correct_answer_index=2,
                reference_answer="",
                focus="迁移应用",
                difficulty="进阶",
            ),
            VariationQuestion(
                id="v3",
                question_type="short_answer",
                prompt=f"围绕「{topic}」：用你自己的话说清它的判定规则，并给出一个与原错题不同的例子。",
                options=[],
                correct_answer_index=None,
                reference_answer=(
                    f"{topic}的判定规则：依据课程定义的条件逐项核对；示例应换一个情境，"
                    "但同样满足规则的前提条件，并说明每一步如何对应规则。"
                ),
                focus="表述与自检",
                difficulty="挑战",
            ),
        ]
        return pool[: max(2, count)]

    def _fallback_verdict_comment(self, request: InteractiveAnswerRequest, correct: bool) -> str:
        focus = request.question.focus or "该知识点"
        if correct:
            return f"回答正确。你把握住了「{focus}」的关键判定条件，继续保持这种先核对规则再作答的习惯。"
        return (
            f"这次回答还没有命中「{focus}」的核心要点。对照参考答案，找到自己漏掉或理解偏差的那一条规则，"
            "再复述一遍判定过程。"
        )


def json_dumps_cn(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
