from __future__ import annotations

from dataclasses import dataclass

from app.agents.graph import LearningAgentGraph
from app.llm.client import LLMClient
from app.models.course import CourseLessonSession, KnowledgeChunk
from app.models.profile import StudentProfile
from app.models.profile_record import StudentProfileRecord
from app.models.resource import OpenMAICClassroom, ResourceType
from app.services.agentic_rag_service import AgenticRAGService
from app.services.course_service import CourseService
from app.services.openmaic_client import OpenMAICClient
from sqlalchemy import select


class ConfirmedProfileRequiredError(RuntimeError):
    pass


class LearnableKnowledgeNodeRequiredError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClassroomInteractionPolicy:
    widget_type: str
    title: str
    reason: str
    widget_outline: dict
    requirement_text: str


class ResourceService:
    openmaic_client_cls = OpenMAICClient

    def __init__(self, llm: LLMClient, course_service: CourseService | None = None) -> None:
        self.graph = LearningAgentGraph(llm)
        self.llm = llm
        self.course_service = course_service

    async def generate_package(
        self,
        conversation: str,
        topic: str,
        *,
        user_id: int | None = None,
        course_id: int | None = None,
        node_id: str = "",
        resource_types: list[ResourceType | str] | None = None,
        force_regenerate: bool = False,
    ) -> dict:
        normalized_types = self._normalize_resource_types(resource_types)
        cached_session = self._lesson_session(user_id, course_id, node_id)
        if (
            not force_regenerate
            and cached_session is not None
            and self._resource_types_match(cached_session.resource_types, normalized_types)
        ):
            cached_package = dict(cached_session.package_data or {})
            cached_package = await self._refresh_cached_openmaic_classroom(cached_session, cached_package)
            cached_package["from_cache"] = True
            cached_package["lesson_state"] = self._lesson_state(cached_session)
            return cached_package

        profile = self._confirmed_profile(user_id, course_id)
        if profile is None and course_id is not None:
            raise ConfirmedProfileRequiredError("confirmed course profile is required")
        if profile is None and node_id:
            raise ConfirmedProfileRequiredError("confirmed profile is required")

        rag_context = self._agentic_rag_context(user_id, course_id, node_id, topic)
        self._ensure_learnable_node(rag_context["graph_constraints"])
        knowledge_context = rag_context["knowledge_context"]
        package = await self.graph.run_collect(
            conversation,
            topic,
            requested_resource_types=resource_types,
            knowledge_context=knowledge_context,
            profile=profile,
            graph_constraints=rag_context["graph_constraints"],
            retrieval_trace=rag_context["retrieval_trace"],
        )
        package["openmaic_classroom"] = (
            await self._generate_openmaic_classroom(
                profile=profile,
                topic=topic,
                knowledge_context=knowledge_context,
                graph_constraints=rag_context["graph_constraints"],
                analysis_plan=package.get("analysis_plan") or {},
            )
        ).model_dump(mode="json")
        package["from_cache"] = False
        package["lesson_state"] = self._default_lesson_state()
        self._save_lesson_session(
            user_id=user_id,
            course_id=course_id,
            node_id=node_id,
            topic=topic,
            resource_types=normalized_types,
            package=package,
            reset_lesson_state=force_regenerate,
        )
        return package

    def get_lesson_state(self, user_id: int, course_id: int, node_id: str) -> dict | None:
        session = self._lesson_session(user_id, course_id, node_id)
        if session is None:
            return None
        return self._lesson_state(session)

    def update_lesson_state(
        self,
        *,
        user_id: int,
        course_id: int,
        node_id: str,
        current_stage: str | None = None,
        classroom_completed: bool | None = None,
        notes_completed: bool | None = None,
        mind_map_completed: bool | None = None,
        code_lab_completed: bool | None = None,
        test_completed: bool | None = None,
        assessment_completed: bool | None = None,
        score: float | None = None,
        openmaic_classroom: dict | None = None,
    ) -> dict | None:
        if self.course_service is None:
            return None
        session = self._lesson_session(user_id, course_id, node_id)
        if session is None:
            return None
        state = self._lesson_state(session)
        if current_stage is not None:
            state["current_stage"] = current_stage
        for key, value in {
            "classroom_completed": classroom_completed,
            "notes_completed": notes_completed,
            "mind_map_completed": mind_map_completed,
            "code_lab_completed": code_lab_completed,
            "test_completed": test_completed,
            "assessment_completed": assessment_completed,
        }.items():
            if value is not None:
                state[key] = value
        if score is not None:
            state["score"] = score
        if openmaic_classroom:
            package = dict(session.package_data or {})
            package["openmaic_classroom"] = {
                **(package.get("openmaic_classroom") or {}),
                **openmaic_classroom,
            }
            session.package_data = package
        session.lesson_state = state
        self.course_service.db.commit()
        self.course_service.db.refresh(session)
        return self._lesson_state(session)

    async def _refresh_cached_openmaic_classroom(
        self,
        session: CourseLessonSession,
        package: dict,
    ) -> dict:
        classroom = package.get("openmaic_classroom") or {}
        if not isinstance(classroom, dict) or not self._should_refresh_openmaic_classroom(classroom):
            return package

        try:
            refreshed = await self.openmaic_client_cls().poll_classroom(
                job_id=str(classroom.get("job_id") or ""),
                poll_url=str(classroom.get("poll_url") or ""),
            )
        except Exception:
            return package

        next_classroom = {
            **classroom,
            **refreshed,
            "requirement": classroom.get("requirement") or refreshed.get("requirement") or "",
        }
        next_package = {
            **package,
            "openmaic_classroom": next_classroom,
        }
        session.package_data = next_package
        if self.course_service is not None:
            self.course_service.db.commit()
            self.course_service.db.refresh(session)
        return next_package

    def _should_refresh_openmaic_classroom(self, classroom: dict) -> bool:
        status = str(classroom.get("status") or "").lower()
        if classroom.get("url") or classroom.get("classroom_id") or status in {"succeeded", "completed", "failed", "error"}:
            return False
        return bool(classroom.get("job_id") or classroom.get("poll_url"))

    def _confirmed_profile(self, user_id: int | None, course_id: int | None = None) -> StudentProfile | None:
        if user_id is None or self.course_service is None:
            return None

        record = self.course_service.db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == user_id,
                StudentProfileRecord.course_id == course_id,
            )
        )
        if record is None:
            return None
        return StudentProfile(**record.profile_data).with_completion_score()

    def _lesson_session(
        self,
        user_id: int | None,
        course_id: int | None,
        node_id: str,
    ) -> CourseLessonSession | None:
        if user_id is None or course_id is None or not node_id or self.course_service is None:
            return None
        return self.course_service.db.scalar(
            select(CourseLessonSession).where(
                CourseLessonSession.user_id == user_id,
                CourseLessonSession.course_id == course_id,
                CourseLessonSession.node_id == node_id,
            )
        )

    def _save_lesson_session(
        self,
        *,
        user_id: int | None,
        course_id: int | None,
        node_id: str,
        topic: str,
        resource_types: list[str],
        package: dict,
        reset_lesson_state: bool = False,
    ) -> None:
        if user_id is None or course_id is None or not node_id or self.course_service is None:
            return
        session = self._lesson_session(user_id, course_id, node_id)
        if session is None:
            session = CourseLessonSession(
                user_id=user_id,
                course_id=course_id,
                node_id=node_id,
                topic=topic,
                resource_types=resource_types,
                package_data=package,
                lesson_state=self._default_lesson_state(),
            )
            self.course_service.db.add(session)
        else:
            session.topic = topic
            session.resource_types = resource_types
            session.package_data = package
            session.lesson_state = self._default_lesson_state() if reset_lesson_state else (session.lesson_state or self._default_lesson_state())
        self.course_service.db.commit()

    def _default_lesson_state(self) -> dict:
        return {
            "current_stage": "classroom",
            "classroom_completed": False,
            "notes_completed": False,
            "mind_map_completed": False,
            "code_lab_completed": False,
            "test_completed": False,
            "assessment_completed": False,
            "score": None,
        }

    def _lesson_state(self, session: CourseLessonSession) -> dict:
        state = self._default_lesson_state()
        state.update(session.lesson_state or {})
        state["course_id"] = session.course_id
        state["node_id"] = session.node_id
        state["topic"] = session.topic
        return state

    def _normalize_resource_types(self, resource_types: list[ResourceType | str] | None) -> list[str]:
        normalized: list[str] = []
        for item in resource_types or []:
            value = item.value if isinstance(item, ResourceType) else str(item)
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    def _resource_types_match(self, cached: list[str] | None, requested: list[str]) -> bool:
        cached_types = [str(item) for item in (cached or []) if str(item)]
        return set(cached_types) == set(requested)

    def _knowledge_context(self, user_id: int | None, course_id: int | None, query: str) -> list[dict]:
        if user_id is None or course_id is None or self.course_service is None:
            return []

        try:
            results = self.course_service.semantic_search(user_id, course_id, query)
        except Exception:
            results = []

        normalized = [self._normalize_context_item(item) for item in results if item.get("content")]
        if normalized:
            return normalized[:5]

        try:
            chunks = self.course_service.list_chunks(user_id, course_id)
        except Exception:
            return []
        return [self._chunk_context(chunk) for chunk in self._rank_chunks(chunks, query)[:5]]

    def _normalize_context_item(self, item: dict) -> dict:
        return {
            "chunk_id": item.get("chunk_id"),
            "source_locator": item.get("source_locator") or "本地知识库",
            "content": item.get("content") or "",
            "distance": item.get("distance"),
        }

    def _chunk_context(self, chunk: KnowledgeChunk) -> dict:
        return {
            "chunk_id": chunk.id,
            "source_locator": chunk.source_locator or chunk.heading or "本地知识库",
            "content": chunk.content,
        }

    def _rank_chunks(self, chunks: list[KnowledgeChunk], query: str) -> list[KnowledgeChunk]:
        compact_query = (query or "").lower()
        terms = [term for term in compact_query.replace(".", " ").split() if term]

        def score(chunk: KnowledgeChunk) -> tuple[int, int]:
            text = f"{chunk.heading} {chunk.content}".lower()
            lexical = sum(1 for term in terms if term and term in text)
            return (lexical, -chunk.chunk_index)

        return sorted(chunks, key=score, reverse=True)

    def _agentic_rag_context(
        self,
        user_id: int | None,
        course_id: int | None,
        node_id: str,
        topic: str,
    ) -> dict:
        if user_id is None or course_id is None or self.course_service is None:
            return {
                "knowledge_context": [],
                "graph_constraints": {
                    "current_node": {"id": node_id or "", "name": topic or "", "node_type": "", "summary": ""},
                    "parent": None,
                    "predecessors": [],
                    "successors": [],
                    "related": [],
                    "source_chunk_ids": [],
                },
                "retrieval_trace": [],
            }
        return AgenticRAGService(self.course_service).build_context(
            user_id=user_id,
            course_id=course_id,
            node_id=node_id,
            topic=topic,
        )

    def _ensure_learnable_node(self, graph_constraints: dict) -> None:
        current_node = graph_constraints.get("current_node") or {}
        node_id = str(current_node.get("id") or "")
        node_type = str(current_node.get("node_type") or "").lower()
        if not node_id:
            return
        if graph_constraints.get("node_found") is False:
            raise LearnableKnowledgeNodeRequiredError("knowledge-point learning requires a current-course graph node")
        if node_id == "course-root" or node_type in {"chapter", "section"} or "-chapter-" in node_id:
            raise LearnableKnowledgeNodeRequiredError("knowledge-point learning requires a concrete knowledge node")

    async def _generate_openmaic_classroom(
        self,
        *,
        profile: StudentProfile | None,
        topic: str,
        knowledge_context: list[dict],
        graph_constraints: dict,
        analysis_plan: dict,
    ) -> OpenMAICClassroom:
        requirement = await self._openmaic_requirement(
            profile=profile,
            topic=topic,
            knowledge_context=knowledge_context,
            graph_constraints=graph_constraints,
            analysis_plan=analysis_plan,
        )
        pdf_text = self._openmaic_pdf_text(knowledge_context)
        try:
            classroom = await self.openmaic_client_cls().generate_classroom(
                requirement=requirement,
                pdf_text=pdf_text,
                language="zh-CN",
                agent_mode="generate",
                enable_tts=True,
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__ or "OpenMAIC classroom submission failed"
            return OpenMAICClassroom(
                status="failed",
                step="openmaic_submit_failed",
                requirement=requirement,
                error=message,
            )
        return OpenMAICClassroom(**classroom, requirement=requirement)

    async def _openmaic_requirement(
        self,
        *,
        profile: StudentProfile | None,
        topic: str,
        knowledge_context: list[dict],
        graph_constraints: dict,
        analysis_plan: dict,
    ) -> str:
        interaction_policy = self._classroom_interaction_policy(topic, knowledge_context, graph_constraints, analysis_plan)
        system_prompt = (
            "你是课程教学设计专家。请基于本地知识库证据、知识图谱约束和学生画像，"
            "为 OpenMAIC 生成一份课堂生成 requirement。只输出中文大纲文本，不要输出 JSON。"
        )
        user_prompt = "\n".join(
            [
                f"知识点：{topic}",
                f"学生画像：{self._profile_text(profile)}",
                f"知识图谱约束：{self._graph_text(graph_constraints)}",
                f"资源蓝图：{analysis_plan.get('resource_blueprint') or {}}",
                "OpenMAIC 交互策略：",
                interaction_policy.requirement_text,
                "语音要求：启用 enableTTS；使用 OpenMAIC 已配置的阿里云百炼 Qwen TTS，教师、助教、学生可使用不同百炼发音人。",
                "MySQL 原文证据：",
                self._openmaic_pdf_text(knowledge_context),
                "要求：生成适合 OpenMAIC 的课堂大纲，包含教学目标、场景顺序、交互/练习建议、评价方式，并严格基于上述原文证据。必须保留上述 widgetType 与 widgetOutline 约束。",
            ]
        )
        try:
            outline = await self.llm.complete_text(system_prompt, user_prompt)
        except Exception:
            outline = ""
        outline = (outline or "").strip()
        if outline:
            return self._compact_openmaic_requirement(topic, outline, interaction_policy)
        return "\n".join(
            [
                f"请生成一节关于“{topic}”的中文互动课堂。",
                "只围绕当前知识点展开，不扩展到同章或后续章节的其他知识点。",
                "最多 3 个场景：概念讲解 1 个、交互/代码演示 1 个、随堂测验 1 个。",
                "总时长控制在 6-8 分钟，每个场景 1-3 分钟。",
                f"学生画像：{self._profile_text(profile)}",
                f"知识图谱约束：{self._graph_text(graph_constraints)}",
                "语音要求：启用 enableTTS；使用 OpenMAIC 已配置的阿里云百炼 Qwen TTS，教师、助教、学生使用不同发音人。",
                "OpenMAIC 交互策略：",
                interaction_policy.requirement_text,
                "必须基于随附 pdfContent.text 中的 MySQL 原文证据组织教学内容。",
            ]
        )

    def _compact_openmaic_requirement(self, topic: str, outline: str, interaction_policy: ClassroomInteractionPolicy) -> str:
        return "\n".join(
            [
                f"课程主题：{topic}",
                "范围约束：只围绕当前知识点展开，不扩展到同章或后续章节的其他知识点。",
                "场景约束：最多 3 个场景，建议为：1）概念讲解，2）交互或代码演示，3）随堂测验。",
                "时长约束：总时长控制在 6-8 分钟，每个场景 1-3 分钟。",
                "证据约束：必须基于随附 pdfContent.text 中的 MySQL 原文证据生成，不得编造教材外事实。",
                "资源约束：避免生成大型项目式或多章节课程；不要生成超过 1 个 interactive 场景；不要生成 PBL 场景。",
                "语音约束：提交 OpenMAIC 时启用 enableTTS；使用 OpenMAIC 已配置的阿里云百炼 Qwen TTS，教师、助教、学生使用不同百炼发音人。",
                "交互约束：必须生成 1 个 OpenMAIC interactive 场景，且该场景必须包含 widgetType 与 widgetOutline，不得退化成普通文字罗列。",
                interaction_policy.requirement_text,
                "大纲内容：",
                outline,
            ]
        )

    def _classroom_interaction_policy(
        self,
        topic: str,
        knowledge_context: list[dict],
        graph_constraints: dict,
        analysis_plan: dict,
    ) -> ClassroomInteractionPolicy:
        text = self._interaction_source_text(topic, knowledge_context, graph_constraints, analysis_plan)
        evidence_anchor = self._interaction_evidence_anchor(topic, knowledge_context)
        if self._contains_any(text, ["练习", "挑战", "闯关", "辨析", "判断", "选择", "匹配", "复习", "巩固"]):
            return ClassroomInteractionPolicy(
                widget_type="game",
                title="知识挑战游戏",
                reason="该知识点以巩固、辨析或练习挑战为主，适合用游戏化任务促进记忆和反馈。",
                widget_outline={
                    "gameType": "challenge",
                    "challenge": f"围绕“{topic}”设计可操作的判断、匹配或闯关挑战，反馈必须引用教材证据。",
                },
                requirement_text=self._interaction_requirement_text(
                    "game",
                    "知识挑战游戏",
                    "该知识点以巩固、辨析或练习挑战为主，适合用游戏化任务促进记忆和反馈。",
                    {
                        "gameType": "challenge",
                        "challenge": f"围绕“{topic}”设计可操作的判断、匹配或闯关挑战，反馈必须引用教材证据。",
                    },
                    evidence_anchor,
                ),
            )
        if self._contains_any(
            text,
            [
                "递归",
                "调用栈",
                "栈",
                "堆",
                "指针",
                "内存",
                "算法",
                "结构",
                "关系",
                "抽象",
                "对象",
                "类",
                "链表",
                "树",
                "图",
                "状态",
            ],
        ):
            return ClassroomInteractionPolicy(
                widget_type="visualization3d",
                title="抽象结构 3D 可视化",
                reason="该知识点包含抽象结构、状态变化或空间关系，适合用 3D 可视化帮助理解。",
                widget_outline={"visualizationType": "structure", "objects": self._visualization_objects(topic, text)},
                requirement_text=self._interaction_requirement_text(
                    "visualization3d",
                    "抽象结构 3D 可视化",
                    "该知识点包含抽象结构、状态变化或空间关系，适合用 3D 可视化帮助理解。",
                    {"visualizationType": "structure", "objects": self._visualization_objects(topic, text)},
                    evidence_anchor,
                ),
            )
        if self._contains_any(text, ["代码", "编程", "程序", "函数", "open", "输入", "输出", "调试", "文件", "读写", "实操", "上机"]):
            return ClassroomInteractionPolicy(
                widget_type="code",
                title="在线编程实验",
                reason="该知识点需要通过浏览器内编码和即时运行来形成操作经验。",
                widget_outline={"language": self._programming_language_for_topic(text)},
                requirement_text=self._interaction_requirement_text(
                    "code",
                    "在线编程实验",
                    "该知识点需要通过浏览器内编码和即时运行来形成操作经验。",
                    {"language": self._programming_language_for_topic(text)},
                    evidence_anchor,
                ),
            )
        return ClassroomInteractionPolicy(
            widget_type="simulation",
            title="过程模拟实验",
            reason="该知识点适合通过参数调整、流程推进或动态演示补足被动听讲的不足。",
            widget_outline={"concept": topic, "keyVariables": self._simulation_variables(topic, text)},
            requirement_text=self._interaction_requirement_text(
                "simulation",
                "过程模拟实验",
                "该知识点适合通过参数调整、流程推进或动态演示补足被动听讲的不足。",
                {"concept": topic, "keyVariables": self._simulation_variables(topic, text)},
                evidence_anchor,
            ),
        )

    def _interaction_source_text(
        self,
        topic: str,
        knowledge_context: list[dict],
        graph_constraints: dict,
        analysis_plan: dict,
    ) -> str:
        current = graph_constraints.get("current_node") or {}
        parent = graph_constraints.get("parent") or {}
        context_text = " ".join(str(item.get("content") or "") for item in knowledge_context[:3])
        blueprint = str(analysis_plan.get("resource_blueprint") or "")
        return f"{topic} {current.get('name') or ''} {current.get('node_type') or ''} {parent.get('name') or ''} {context_text} {blueprint}".lower()

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        return any(keyword.lower() in text for keyword in keywords)

    def _interaction_requirement_text(
        self,
        widget_type: str,
        title: str,
        reason: str,
        widget_outline: dict,
        evidence_anchor: str = "",
    ) -> str:
        evidence_line = f"- 证据锚点：{evidence_anchor}" if evidence_anchor else "- 证据锚点：使用随附 pdfContent.text 中最相关的 MySQL 原文块。"
        return "\n".join(
            [
                f"- 场景类型：interactive",
                f"- 交互标题：{title}",
                f"- 选择理由：{reason}",
                f"- widgetType: {widget_type}",
                f"- widgetOutline: {widget_outline}",
                evidence_line,
                "- 场景要求：教师先用 1 个教材证据引入，再引导学生操作交互控件，最后用随堂测验验证掌握。",
                "- 事实约束：交互中的对象、代码、变量、反馈解释必须来自 MySQL 原文证据与知识图谱约束。",
            ]
        )

    def _interaction_evidence_anchor(self, topic: str, knowledge_context: list[dict]) -> str:
        for item in knowledge_context[:2]:
            content = " ".join(str(item.get("content") or "").split())
            if not content:
                continue
            locator = item.get("source_locator") or item.get("heading") or item.get("chunk_id") or "本地知识库"
            snippet = content[:80]
            return f"{locator}：{snippet}"
        return topic

    def _programming_language_for_topic(self, text: str) -> str:
        if "c语言" in text or "c 语言" in text or "printf" in text or "scanf" in text:
            return "c"
        return "python"

    def _visualization_objects(self, topic: str, text: str) -> list[str]:
        if "递归" in text or "调用栈" in text:
            return ["函数入口", "调用栈帧", "递归深度", "返回路径"]
        if "指针" in text or "内存" in text:
            return ["变量", "内存地址", "指针引用", "数据对象"]
        if "树" in text:
            return ["根节点", "子节点", "层级关系", "遍历路径"]
        return [topic, "核心概念", "关系结构", "状态变化"]

    def _simulation_variables(self, topic: str, text: str) -> list[str]:
        variables = []
        for keyword in ["输入", "条件", "循环次数", "参数", "返回值", "文件指针", "执行步骤"]:
            if keyword.lower() in text:
                variables.append(keyword)
        return variables or [topic, "步骤", "结果"]

    def _openmaic_pdf_text(self, knowledge_context: list[dict]) -> str:
        lines = []
        for item in knowledge_context[:5]:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            lines.append(
                f"[chunk #{item.get('chunk_id')} | {item.get('source_locator') or item.get('heading') or '本地知识库'}]\n{content}"
            )
        return "\n\n".join(lines)

    def _profile_text(self, profile: StudentProfile | None) -> str:
        if profile is None:
            return "未提供确认画像。"
        return (
            f"{profile.major}{profile.grade}；目标：{profile.learning_goal}；基础：{profile.knowledge_foundation}；"
            f"学习风格：{profile.learning_style}；薄弱点：{'、'.join(profile.weak_points)}；"
            f"资源偏好：{'、'.join(profile.resource_preference)}。"
        )

    def _graph_text(self, graph_constraints: dict) -> str:
        current = graph_constraints.get("current_node") or {}
        parent = graph_constraints.get("parent") or {}
        predecessors = "、".join(item.get("name", "") for item in graph_constraints.get("predecessors") or [] if item.get("name"))
        successors = "、".join(item.get("name", "") for item in graph_constraints.get("successors") or [] if item.get("name"))
        related = "、".join(item.get("name", "") for item in graph_constraints.get("related") or [] if item.get("name"))
        return (
            f"当前节点：{current.get('name') or ''}；父章节：{parent.get('name') or ''}；"
            f"前置：{predecessors or '无'}；后续：{successors or '无'}；相关：{related or '无'}。"
        )
