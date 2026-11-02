from __future__ import annotations

import asyncio
import re
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.tutor import (
    TutorAgentEvent,
    TutorChatRequest,
    TutorChatResponse,
    TutorEvidenceChunk,
    TutorMultimodalCard,
    TutorSuggestedAction,
)
from app.services.agentic_rag_service import AgenticRAGService
from app.services.course_service import CourseService
from app.services.dynamic_profile_service import ConfirmedCourseProfileRequiredError, DynamicProfileService, ProfileEventInput


TUTOR_LLM_TIMEOUT_SECONDS = 45

DOMAIN_TERMS = [
    "计算机",
    "程序",
    "指令",
    "算法",
    "变量名",
    "变量",
    "标识符",
    "数字",
    "字母",
    "下划线",
    "输入",
    "输出",
    "函数",
    "参数",
    "返回值",
    "循环",
    "分支",
    "条件",
    "数组",
    "指针",
    "地址",
    "结构体",
    "魔方阵",
    "排序",
    "内存",
    "编译",
    "运行",
    "语句",
    "数据类型",
    "表达式",
]

ENGLISH_TERM_SYNONYMS = {
    "computer": ["计算机"],
    "program": ["程序", "指令"],
    "programming": ["程序"],
    "instruction": ["指令"],
    "algorithm": ["算法"],
    "variable": ["变量", "变量名"],
    "variables": ["变量", "变量名"],
    "identifier": ["标识符", "变量名"],
    "identifiers": ["标识符", "变量名"],
    "naming": ["命名", "变量名"],
    "input": ["输入"],
    "output": ["输出"],
    "function": ["函数"],
    "loop": ["循环"],
    "array": ["数组"],
    "pointer": ["指针", "地址"],
    "struct": ["结构体"],
}

GENERIC_RELEVANCE_TERMS = {
    "有人",
    "认为",
    "为什么",
    "什么",
    "怎么",
    "如何",
    "题目",
    "问题",
    "完成",
    "各种",
    "事务",
    "依据",
    "解释",
    "图片",
    "截图",
    "课程",
    "知识点",
    "please",
    "explain",
    "screenshot",
    "question",
    "answer",
    "node",
    "text",
    "only",
}


class TutorService:
    def __init__(
        self,
        course_service: CourseService,
        *,
        rag_service_cls: type[AgenticRAGService] = AgenticRAGService,
        db: Session | None = None,
        llm: Any | None = None,
        vision_llm: Any | None = None,
    ) -> None:
        self.course_service = course_service
        self.rag_service_cls = rag_service_cls
        self.db = db
        self.llm = llm
        self.vision_llm = vision_llm

    async def chat(self, *, user_id: int, request: TutorChatRequest) -> TutorChatResponse:
        self._validate_course_access(user_id, request.course_id)
        topic = self._topic_from_request(request)
        analysis_plan = self._analysis_plan(user_id, request, topic)
        rag_context = self.rag_service_cls(self.course_service).build_context(
            user_id=user_id,
            course_id=request.course_id,
            node_id=request.node_id,
            topic=topic,
        )
        graph_constraints = rag_context.get("graph_constraints") or {}
        raw_evidence_chunks = [TutorEvidenceChunk(**item) for item in rag_context.get("knowledge_context", [])]
        evidence_chunks = self._filter_relevant_evidence(request, topic, raw_evidence_chunks, graph_constraints)
        retrieval_trace = rag_context.get("retrieval_trace") or []
        answer = await self._answer(request, topic, evidence_chunks, graph_constraints)
        verification_report = self._verification_report(evidence_chunks, graph_constraints)
        decision_report = self._decision_report(verification_report)
        multimodal_cards = self._multimodal_cards(topic, answer, evidence_chunks, graph_constraints, request)
        suggested_actions = self._suggested_actions(request)
        agent_events = self._agent_events(analysis_plan, evidence_chunks, verification_report, decision_report)
        suggested_followups = await self._suggested_followups(request, topic, answer)
        self._record_tutor_event(user_id, request, verification_report)

        return TutorChatResponse(
            answer=answer,
            agent_events=agent_events,
            analysis_plan=analysis_plan,
            retrieval_trace=retrieval_trace,
            graph_constraints=graph_constraints,
            evidence_chunks=evidence_chunks,
            verification_report=verification_report,
            decision_report=decision_report,
            multimodal_cards=multimodal_cards,
            suggested_actions=suggested_actions,
            suggested_followups=suggested_followups,
        )

    def _validate_course_access(self, user_id: int, course_id: int) -> None:
        get_course = getattr(self.course_service, "get_course", None)
        if callable(get_course):
            get_course(user_id, course_id)

    def _topic_from_request(self, request: TutorChatRequest) -> str:
        message = request.message.strip()
        current_node = request.node_id.strip()
        return message or current_node or "课程问题"

    def _record_tutor_event(
        self,
        user_id: int,
        request: TutorChatRequest,
        verification_report: dict[str, Any],
    ) -> None:
        if self.db is None:
            return
        try:
            DynamicProfileService(self.db, self.course_service).record_event(
                user_id=user_id,
                course_id=request.course_id,
                payload=ProfileEventInput(
                    event_type="tutor_question_asked",
                    topic=request.node_id or request.message[:40],
                    knowledge_node_id=request.node_id,
                    detail=request.message,
                    event_payload={
                        "page_context": request.page_context,
                        "evidence_count": verification_report.get("evidence_count", 0),
                        "decision": verification_report.get("decision"),
                    },
                    evidence_strength="medium" if verification_report.get("evidence_count", 0) else "weak",
                    score=None,
                ),
            )
        except ConfirmedCourseProfileRequiredError:
            self.db.rollback()

    def _analysis_plan(self, user_id: int, request: TutorChatRequest, topic: str) -> dict[str, Any]:
        return {
            "agent": "TutorAnalysisAgent",
            "user_id": user_id,
            "course_id": request.course_id,
            "node_id": request.node_id,
            "page_context": request.page_context,
            "topic": topic,
            "intent": "course_tutoring",
            "requires_rag": True,
            "attachment_count": len(request.attachments),
            "attachments": [self._attachment_summary(attachment) for attachment in request.attachments],
            "multimodal_required": self._has_image_attachment(request),
            "generation_model": self._generation_model_label(request),
        }

    async def _answer(
        self,
        request: TutorChatRequest,
        topic: str,
        evidence_chunks: list[TutorEvidenceChunk],
        graph_constraints: dict[str, Any],
    ) -> str:
        vision_images = self._vision_images(request)
        if not evidence_chunks and not vision_images:
            return "未检索到课程知识库证据，或未检索到与该问题直接匹配的证据。请先确认该知识点资料已入库，或补充更具体的章节/知识点后再试。"

        if vision_images and self.vision_llm is not None:
            try:
                answer = (await asyncio.wait_for(
                    self.vision_llm.complete_multimodal_text(
                        self._answer_system_prompt(),
                        self._answer_user_prompt(request, topic, evidence_chunks, graph_constraints),
                        vision_images,
                    ),
                    timeout=TUTOR_LLM_TIMEOUT_SECONDS,
                )).strip()
                if answer:
                    return answer
            except Exception:
                pass

        if not evidence_chunks:
            return "未检索到课程知识库证据，或未检索到与该问题直接匹配的证据。图片内容可作为问题线索，但当前课程原文证据不足，建议补充对应章节资料后再追问。"

        if self.llm is not None:
            try:
                answer = (await asyncio.wait_for(
                    self.llm.complete_text(
                        self._answer_system_prompt(),
                        self._answer_user_prompt(request, topic, evidence_chunks, graph_constraints),
                    ),
                    timeout=TUTOR_LLM_TIMEOUT_SECONDS,
                )).strip()
                if answer:
                    return answer
            except Exception:
                pass

        return self._fallback_answer(request, topic, evidence_chunks, graph_constraints)

    def _filter_relevant_evidence(
        self,
        request: TutorChatRequest,
        topic: str,
        evidence_chunks: list[TutorEvidenceChunk],
        graph_constraints: dict[str, Any],
    ) -> list[TutorEvidenceChunk]:
        if not evidence_chunks:
            return []
        query_text = " ".join(
            [
                topic,
                request.message,
                request.node_id,
                " ".join(self._attachment_summary(attachment)["description"] for attachment in request.attachments),
                self._graph_relevance_text(graph_constraints),
            ]
        )
        query_terms = self._relevance_terms(query_text)
        if not query_terms:
            return []
        relevant = [
            chunk
            for chunk in evidence_chunks
            if self._evidence_relevance_score(chunk, query_terms) >= 2
        ]
        return relevant[:5]

    def _graph_relevance_text(self, graph_constraints: dict[str, Any]) -> str:
        current = graph_constraints.get("current_node") or {}
        parent = graph_constraints.get("parent") or {}
        related_parts = []
        for key in ("predecessors", "successors", "related"):
            for node in graph_constraints.get(key) or []:
                related_parts.append(f"{node.get('name', '')} {node.get('summary', '')}")
        return " ".join(
            [
                str(current.get("name") or ""),
                str(current.get("summary") or ""),
                str(parent.get("name") or ""),
                " ".join(related_parts),
            ]
        )

    def _relevance_terms(self, text: str) -> set[str]:
        normalized = re.sub(r"[-+]+", " ", (text or "").lower())
        terms: set[str] = set()
        for term in DOMAIN_TERMS:
            if term.lower() in normalized:
                terms.add(term.lower())
        for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}", normalized):
            if word in GENERIC_RELEVANCE_TERMS:
                continue
            terms.add(word)
            for synonym in ENGLISH_TERM_SYNONYMS.get(word, []):
                terms.add(synonym.lower())
        for sequence in re.findall(r"[\u4e00-\u9fff]{2,8}", text or ""):
            if sequence in GENERIC_RELEVANCE_TERMS:
                continue
            if len(sequence) <= 4:
                terms.add(sequence.lower())
        return {term for term in terms if term and term not in GENERIC_RELEVANCE_TERMS}

    def _evidence_relevance_score(self, chunk: TutorEvidenceChunk, query_terms: set[str]) -> int:
        evidence_text = f"{chunk.heading} {chunk.content} {chunk.source_locator}".lower()
        score = 0
        for term in query_terms:
            if term not in evidence_text:
                continue
            if term in {"程序", "输入", "输出", "运行", "语句"}:
                score += 1
            else:
                score += 2 if self._contains_cjk(term) else 1
        return score

    def _contains_cjk(self, text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text))

    def _fallback_answer(
        self,
        request: TutorChatRequest,
        topic: str,
        evidence_chunks: list[TutorEvidenceChunk],
        graph_constraints: dict[str, Any],
    ) -> str:
        evidence = evidence_chunks[0]
        parent = graph_constraints.get("parent") or {}
        current = graph_constraints.get("current_node") or {}
        relation_text = ""
        if parent.get("name"):
            relation_text = f"它属于“{parent.get('name')}”下的知识点。"
        current_name = current.get("name") or topic
        return (
            f"围绕“{current_name}”，本地知识库给出的依据是：{evidence.content} "
            f"{relation_text}结合你的问题“{request.message.strip()}”，可以先把规则、反例和练习放在一起理解。"
        ).strip()

    def _answer_system_prompt(self) -> str:
        return (
            "你是个性化学习平台的智能辅导生成智能体。"
            "回答必须以课程本地知识库证据和知识图谱约束为依据，不能简单复制原文。"
            "请先解释学生问题，再补充例子、易错点或下一步练习建议。"
            "如使用证据，请在自然语言中标注 chunk#编号；如果证据不足，要明确说明不足。"
            "不要编造教材中不存在的事实。"
        )

    def _answer_user_prompt(
        self,
        request: TutorChatRequest,
        topic: str,
        evidence_chunks: list[TutorEvidenceChunk],
        graph_constraints: dict[str, Any],
    ) -> str:
        evidence_text = "\n\n".join(
            self._format_evidence_chunk(chunk)
            for chunk in evidence_chunks[:4]
        ) or "未检索到与该问题直接匹配的课程原文证据。"
        graph_text = self._format_graph_constraints(graph_constraints)
        attachment_text = self._format_attachments(request)
        history_text = self._format_history(request.history)
        attention_text = self._format_attention_state(request.attention_state)
        return (
            f"课程ID：{request.course_id}\n"
            f"页面上下文：{request.page_context or 'unknown'}\n"
            f"当前知识点：{topic}\n"
            f"学生问题：{request.message.strip()}\n\n"
            f"学习状态感知：\n{attention_text}\n\n"
            f"图片/语音等附件上下文：\n{attachment_text}\n\n"
            f"最近对话：\n{history_text}\n\n"
            f"知识图谱约束：\n{graph_text}\n\n"
            f"MySQL 原文证据块：\n{evidence_text}\n\n"
            "请输出面向学生的中文回答，结构建议：直接回答、为什么、例子或操作建议、引用依据。"
            "若学习状态为 confused（困惑），先用一个直觉类比讲清核心，再进入推导，并主动提出'换个方式讲'；"
            "若为 distracted，回答开头温和地把注意力拉回当前知识点；若为 tired，建议先做一道短练习再继续。"
        )

    @staticmethod
    def _format_attention_state(attention_state: str) -> str:
        state = (attention_state or "").strip().lower()
        labels = {
            "focused": "专注中（正常讲解即可）",
            "confused": "困惑中（学生可能卡住了：先直觉类比，再推导，主动提出换一种讲法）",
            "distracted": "走神中（温和地把注意力拉回当前知识点，不要说教）",
            "tired": "疲劳（建议先做一道短练习或稍作休息再继续）",
            "no_face": "未检测到学生（正常讲解）",
        }
        if not state:
            return "未开启学习状态感知（按正常方式讲解）。"
        return labels.get(state, f"状态：{state}")

    def _format_evidence_chunk(self, chunk: TutorEvidenceChunk) -> str:
        content = " ".join(chunk.content.split())
        if len(content) > 1200:
            content = f"{content[:1200]}..."
        chunk_label = f"chunk#{chunk.chunk_id}" if chunk.chunk_id is not None else "chunk#unknown"
        locator = chunk.source_locator or "unknown source"
        heading = chunk.heading or "未命名片段"
        return f"{chunk_label} | {locator} | {heading}\n{content}"

    def _format_graph_constraints(self, graph_constraints: dict[str, Any]) -> str:
        current = graph_constraints.get("current_node") or {}
        parent = graph_constraints.get("parent") or {}
        predecessors = graph_constraints.get("predecessors") or []
        successors = graph_constraints.get("successors") or []
        related = graph_constraints.get("related") or []
        source_chunk_ids = graph_constraints.get("source_chunk_ids") or []
        return "\n".join(
            [
                f"当前节点：{current.get('name') or current.get('id') or '未知'}",
                f"父章节：{parent.get('name') or '无'}",
                f"前置节点：{self._node_names(predecessors)}",
                f"后续节点：{self._node_names(successors)}",
                f"相关节点：{self._node_names(related)}",
                f"证据块ID：{', '.join(str(item) for item in source_chunk_ids) or '无'}",
            ]
        )

    def _format_attachments(self, request: TutorChatRequest) -> str:
        if not request.attachments:
            return "无"
        return "\n".join(
            f"- {summary['filename']} ({summary['content_type']}): {summary['description']}"
            for summary in (self._attachment_summary(attachment) for attachment in request.attachments)
        )

    def _attachment_summary(self, attachment: Any) -> dict[str, str]:
        filename = (getattr(attachment, "filename", "") or "").strip()
        content_type = (getattr(attachment, "content_type", "") or "").strip()
        description = (getattr(attachment, "description", "") or "").strip()
        return {
            "id": (getattr(attachment, "id", "") or "").strip(),
            "filename": filename or "未命名附件",
            "content_type": content_type or "application/octet-stream",
            "description": self._attachment_description(attachment, description),
        }

    def _attachment_description(self, attachment: Any, description: str) -> str:
        data_url = (getattr(attachment, "data_url", "") or "").strip()
        payload_text = ""
        if data_url.startswith("data:image/"):
            payload_text = f" 已接收图片数据，约 {len(data_url)} 个字符；请结合图片语境回答，但不要在回答中复述图片编码。"
        base_description = description or "用户提供的多模态问题附件，需结合文字问题进行辅导。"
        return f"{base_description}{payload_text}".strip()

    def _has_image_attachment(self, request: TutorChatRequest) -> bool:
        return bool(self._vision_images(request))

    def _vision_images(self, request: TutorChatRequest) -> list[dict[str, str]]:
        images: list[dict[str, str]] = []
        for attachment in request.attachments:
            data_url = (getattr(attachment, "data_url", "") or "").strip()
            content_type = (getattr(attachment, "content_type", "") or "").strip()
            if not data_url.startswith("data:image/"):
                continue
            images.append(
                {
                    "id": (getattr(attachment, "id", "") or "").strip(),
                    "filename": (getattr(attachment, "filename", "") or "").strip(),
                    "content_type": content_type or "image/*",
                    "data_url": data_url,
                }
            )
        return images

    def _generation_model_label(self, request: TutorChatRequest) -> str:
        if self._has_image_attachment(request) and self.vision_llm is not None:
            return str(getattr(self.vision_llm, "model", "") or "qwen3.7-plus")
        if self.llm is not None:
            return str(getattr(self.llm, "model", "") or "text-llm")
        return "deterministic-rag-fallback"

    def _format_history(self, history: list[dict[str, str]]) -> str:
        if not history:
            return "无"
        lines = []
        for item in history[-6:]:
            role = str(item.get("role") or "unknown")[:20]
            content = " ".join(str(item.get("content") or "").split())
            lines.append(f"{role}: {content[:300]}")
        return "\n".join(lines) if lines else "无"

    def _node_names(self, nodes: list[dict[str, Any]]) -> str:
        names = [str(node.get("name") or node.get("id") or "").strip() for node in nodes]
        names = [name for name in names if name]
        return "、".join(names[:6]) if names else "无"

    def _verification_report(
        self,
        evidence_chunks: list[TutorEvidenceChunk],
        graph_constraints: dict[str, Any],
    ) -> dict[str, Any]:
        evidence_count = len(evidence_chunks)
        graph_count = sum(1 for key in ("current_node", "parent", "predecessors", "successors", "related") if graph_constraints.get(key))
        decision = "accepted" if evidence_count else "fallback"
        return {
            "agent": "TutorVerifierAgent",
            "decision": decision,
            "evidence_count": evidence_count,
            "graph_constraint_count": graph_count,
            "citation_chunk_ids": [chunk.chunk_id for chunk in evidence_chunks if chunk.chunk_id is not None],
            "hallucination_risk": "low" if evidence_count else "medium",
            "unsupported_claims": [] if evidence_count else ["缺少课程知识库证据"],
        }

    def _decision_report(self, verification_report: dict[str, Any]) -> dict[str, Any]:
        accepted = verification_report.get("decision") == "accepted"
        return {
            "agent": "TutorDecisionAgent",
            "decision": "accepted" if accepted else "fallback",
            "next_action": "answer" if accepted else "ask_for_more_context",
            "reason": "回答已绑定课程证据" if accepted else "缺少课程知识库证据，已降级提示",
            "fallback_available": True,
        }

    def _multimodal_cards(
        self,
        topic: str,
        answer: str,
        evidence_chunks: list[TutorEvidenceChunk],
        graph_constraints: dict[str, Any],
        request: TutorChatRequest,
    ) -> list[TutorMultimodalCard]:
        cards = [
            TutorMultimodalCard(type="text_explanation", title="结构化讲解", content=answer),
        ]
        if evidence_chunks:
            cards.append(
                TutorMultimodalCard(
                    type="source_evidence",
                    title="本地知识库证据",
                    content=evidence_chunks[0].content,
                    payload={
                        "chunk_id": evidence_chunks[0].chunk_id,
                        "source_locator": evidence_chunks[0].source_locator,
                    },
                )
            )
        if graph_constraints.get("current_node"):
            cards.append(
                TutorMultimodalCard(
                    type="diagram",
                    title="知识图谱关系",
                    content=f"{topic} 与父章节、前后继知识点的关系可作为理解路径。",
                    payload={"graph_constraints": graph_constraints},
                )
            )
        elif "代码" in request.message or "编程" in request.message:
            cards.append(
                TutorMultimodalCard(
                    type="code_hint",
                    title="代码练习提示",
                    content="先写最小可运行代码，再用输入输出样例验证。",
                )
            )
        return cards[:3]

    def _suggested_actions(self, request: TutorChatRequest) -> list[TutorSuggestedAction]:
        base = f"/courses/{request.course_id}"
        actions = [
            TutorSuggestedAction(type="open_graph", label="查看知识图谱", target=f"{base}/graph"),
            TutorSuggestedAction(type="open_learning_path", label="查看学习路径", target=f"{base}/learning-path"),
        ]
        if request.node_id:
            actions.append(
                TutorSuggestedAction(
                    type="open_lesson",
                    label="进入对应课堂",
                    target=f"{base}/knowledge/{request.node_id}",
                )
            )
        return actions

    async def _suggested_followups(
        self,
        request: TutorChatRequest,
        topic: str,
        answer: str,
    ) -> list[str]:
        """issue #16：为辅导回答生成 2-3 条可点击追问，让对话向教学目标收敛。

        LLM 生成失败或结果不足两条时，回退到场景化模板（代码实验/错题场景优先
        "帮我看看代码"类选项），保证每次回答都有可点的追问。
        """
        prompt = (
            "基于学生问题与助教回答，生成 3 条学生可能点击的追问，分别覆盖三种层次：\n"
            "①澄清型：确认一个具体概念点；②深入型：问原理或复杂度；③实操型：要一个可运行的 C++ 例子或变式练习。\n"
            "每条不超过 22 个字，必须与知识点和问题上下文强相关，禁止'再讲讲''继续'式空泛选项。\n\n"
            f"知识点：{topic}\n"
            f"学生问题：{request.message.strip()[:200]}\n"
            f"回答摘要：{answer[:400]}"
        )
        if self.llm is not None:
            try:
                data = await asyncio.wait_for(
                    self.llm.complete_json(
                        "你是辅导追问选项生成器，只输出 JSON。",
                        prompt + '\n\n输出格式：{"followups": ["选项1", "选项2", "选项3"]}',
                    ),
                    timeout=15,
                )
                items = [str(item).strip() for item in (data.get("followups") or []) if str(item).strip()]
                items = items[:3]
                if len(items) >= 2:
                    return items
            except Exception:
                pass
        return self._default_followups(request, topic)

    @staticmethod
    def _default_followups(request: TutorChatRequest, topic: str) -> list[str]:
        message = (request.message or "").lower()
        code_scene = any(
            key in message for key in ("代码", "编译", "报错", "运行", "输出", "调试", "error")
        )
        if code_scene:
            return [
                "我的代码输出不对，帮我看看哪里错了",
                f"给一个{topic}的完整可运行 C++ 示例",
                f"{topic}最容易犯的错误是什么？",
            ]
        return [
            f"能讲讲{topic}背后的原理吗？",
            f"给一个{topic}的可运行 C++ 例子",
            f"{topic}和易错点：出一道变式题考考我",
        ]

    def _agent_events(
        self,
        analysis_plan: dict[str, Any],
        evidence_chunks: list[TutorEvidenceChunk],
        verification_report: dict[str, Any],
        decision_report: dict[str, Any],
    ) -> list[TutorAgentEvent]:
        return [
            TutorAgentEvent(
                event="analysis_completed",
                agent="TutorAnalysisAgent",
                summary=f"识别为课程 {analysis_plan['course_id']} 的辅导问题",
                detail=analysis_plan,
            ),
            TutorAgentEvent(
                event="retrieval_completed",
                agent="TutorRetrievalAgent",
                summary=f"检索到 {len(evidence_chunks)} 个 MySQL 原文证据块",
                detail={"evidence_count": len(evidence_chunks)},
            ),
            TutorAgentEvent(
                event="generation_completed",
                agent="TutorGeneratorAgent",
                summary="已基于课程证据生成辅导回答和多模态卡片",
            ),
            TutorAgentEvent(
                event="verification_completed",
                agent="TutorVerifierAgent",
                summary=f"校验结论：{verification_report['decision']}",
                detail=verification_report,
            ),
            TutorAgentEvent(
                event="decision_completed",
                agent="TutorDecisionAgent",
                summary=f"最终决策：{decision_report['decision']}",
                detail=decision_report,
            ),
        ]
