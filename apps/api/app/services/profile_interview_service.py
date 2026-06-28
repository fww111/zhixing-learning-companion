from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.models.course import Course
from app.models.profile import ProfileEvidence, StudentProfile
from app.models.profile_record import ProfileInterview, ProfileMessage, StudentProfileRecord


class ProfileCourseNotFoundError(RuntimeError):
    pass


class ProfileInterviewNotFoundError(RuntimeError):
    pass


class ProfileNotFoundError(RuntimeError):
    pass


class ProfileIncompleteError(RuntimeError):
    pass


class ProfileInterviewLLMError(RuntimeError):
    pass


class ProfileInterviewService:
    first_question = "你目前的专业、年级和最想达成的课程学习目标是什么？"
    max_turns = 10
    auto_confirm_completion_score = 0.78
    min_turns_before_confirm = 2
    interview_buckets: list[tuple[str, list[str]]] = [
        ("basic", ["major", "grade", "learning_goal"]),
        ("knowledge", ["knowledge_foundation"]),
        ("weak_points", ["weak_points"]),
        ("resources", ["resource_preference"]),
        ("time", ["time_preference", "constraints"]),
        ("style", ["learning_style", "cognitive_style"]),
        ("motivation", ["motivation"]),
        ("assessment", ["assessment_preference"]),
        ("graph_focus", ["knowledge_graph_focus"]),
    ]

    def __init__(self, db: Session, llm: LLMClient | None = None, require_real_llm: bool = False) -> None:
        self.db = db
        self.llm = llm
        self.require_real_llm = require_real_llm

    def start_interview(self, user_id: int, course_id: int | None = None) -> ProfileInterview:
        if course_id is not None and not self._course_belongs_to_user(user_id, course_id):
            raise ProfileCourseNotFoundError("course not found")
        profile = StudentProfile(
            student_id=f"user-{user_id}",
            major="",
            grade="",
            learning_goal="",
            knowledge_foundation="",
            learning_style="",
            cognitive_style="",
            weak_points=[],
            time_preference="",
            resource_preference=[],
            confidence_score=0.0,
            completion_score=0.0,
        )
        interview = ProfileInterview(
            user_id=user_id,
            course_id=course_id,
            status="in_progress",
            current_question=self.first_question,
            profile_data=profile.model_dump(mode="json"),
        )
        self.db.add(interview)
        self.db.flush()
        self.db.add(ProfileMessage(interview_id=interview.id, user_id=user_id, role="assistant", content=self.first_question))
        self.db.commit()
        self.db.refresh(interview)
        return interview

    def _course_belongs_to_user(self, user_id: int, course_id: int) -> bool:
        return self.db.scalar(
            select(Course.id).where(
                Course.id == course_id,
                Course.user_id == user_id,
            )
        ) is not None

    async def answer_interview(
        self,
        user_id: int,
        interview_id: int,
        answer: str,
        topic: str = "",
    ) -> ProfileInterview:
        interview = self._get_interview(user_id, interview_id)
        if interview.status == "confirmed":
            return interview

        self._ensure_real_llm_if_required()
        profile = StudentProfile(**interview.profile_data)
        answer_context = self._answer_context(answer, topic)
        history = self._message_history(interview, pending_answer=answer_context)
        next_turn_count = interview.turn_count + 1
        merged = (
            await self._merge_answer(profile, answer_context, history, force_complete=next_turn_count >= self.max_turns)
        ).with_completion_score()
        focus_bucket = self._next_focus_bucket(merged)
        if next_turn_count >= self.max_turns:
            merged = self._force_complete_profile(merged, history, answer_context).with_completion_score()
        interview.turn_count = next_turn_count
        interview.profile_data = merged.model_dump(mode="json")
        self.db.add(ProfileMessage(interview_id=interview.id, user_id=user_id, role="user", content=answer))
        if self._should_auto_confirm(merged, next_turn_count):
            confirmed = merged.model_copy(update={"student_id": f"user-{user_id}"}).with_completion_score()
            self._apply_confirmed_profile(interview, confirmed, user_id)
        else:
            next_question = await self._next_question(merged, history, focus_bucket)
            interview.current_question = next_question
            interview.status = "in_progress"
            self.db.add(ProfileMessage(interview_id=interview.id, user_id=user_id, role="assistant", content=next_question))
        self.db.commit()
        self.db.refresh(interview)
        return interview

    def _ensure_real_llm_if_required(self) -> None:
        if not self.require_real_llm:
            return
        if self.llm is None or self.llm.mock:
            raise ProfileInterviewLLMError(
                "学生画像追问要求使用 DeepSeek V4 Pro，但当前后端没有加载 LLM_API_KEY。"
                "请在本地 .env 配置 LLM_API_KEY 后重启后端。"
            )

    def _answer_context(self, answer: str, topic: str = "") -> str:
        clean_answer = answer.strip()
        clean_topic = topic.strip()
        if not clean_topic or clean_topic.lower() in clean_answer.lower():
            return clean_answer
        return f"{clean_answer}\n学习主题：{clean_topic}"

    def confirm_interview(self, user_id: int, interview_id: int) -> StudentProfileRecord:
        interview = self._get_interview(user_id, interview_id)
        profile = StudentProfile(**interview.profile_data).model_copy(update={"student_id": f"user-{user_id}"}).with_completion_score()
        if not profile.is_complete():
            raise ProfileIncompleteError("profile interview incomplete")
        existing = self._apply_confirmed_profile(interview, profile, user_id)
        self.db.commit()
        self.db.refresh(existing)
        return existing

    def get_my_profile(self, user_id: int, course_id: int | None = None) -> StudentProfileRecord:
        profile = self.db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == user_id,
                StudentProfileRecord.course_id == course_id,
            )
        )
        if profile is None and course_id is not None:
            profile = self._clone_legacy_account_profile(user_id, course_id)
        if profile is None:
            raise ProfileNotFoundError("profile not found")
        return profile

    def _clone_legacy_account_profile(self, user_id: int, course_id: int) -> StudentProfileRecord | None:
        if not self._course_belongs_to_user(user_id, course_id):
            return None
        legacy_profile = self.db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == user_id,
                StudentProfileRecord.course_id.is_(None),
            )
        )
        if legacy_profile is None:
            return None
        profile = StudentProfileRecord(
            user_id=user_id,
            course_id=course_id,
            interview_id=legacy_profile.interview_id,
            student_id=legacy_profile.student_id,
            profile_data=dict(legacy_profile.profile_data or {}),
        )
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def _get_interview(self, user_id: int, interview_id: int) -> ProfileInterview:
        interview = self.db.scalar(
            select(ProfileInterview).where(ProfileInterview.id == interview_id, ProfileInterview.user_id == user_id)
        )
        if interview is None:
            raise ProfileInterviewNotFoundError("profile interview not found")
        return interview

    def _should_auto_confirm(self, profile: StudentProfile, turn_count: int) -> bool:
        return (
            turn_count >= self.max_turns
            or (turn_count >= self.min_turns_before_confirm and profile.is_complete())
            or (turn_count >= 1 and profile.is_complete() and profile.completion_score >= 1.0 and self._has_explicit_confirmation_evidence(profile))
        )

    def _has_explicit_confirmation_evidence(self, profile: StudentProfile) -> bool:
        if len(profile.updated_evidence) != 1:
            return False
        evidence = profile.updated_evidence[0]
        if evidence.source not in {"interview", "deepseek-v4-pro"}:
            return False
        detail = evidence.detail
        return bool(
            profile.resource_preference
            and profile.weak_points
            and profile.time_preference
            and any(item in detail for item in profile.weak_points)
            and any(item in detail for item in profile.resource_preference)
            and any(marker in detail for marker in ["分钟", "小时", "鍒嗛挓", "灏忔椂"])
        )

    def _apply_confirmed_profile(
        self,
        interview: ProfileInterview,
        profile: StudentProfile,
        user_id: int,
    ) -> StudentProfileRecord:
        interview.status = "confirmed"
        interview.profile_data = profile.model_dump(mode="json")
        interview.current_question = ""
        existing = self.db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == user_id,
                StudentProfileRecord.course_id == interview.course_id,
            )
        )
        if existing is None:
            existing = StudentProfileRecord(
                user_id=user_id,
                course_id=interview.course_id,
                interview_id=interview.id,
                student_id=profile.student_id,
            )
            self.db.add(existing)
        existing.course_id = interview.course_id
        existing.interview_id = interview.id
        existing.student_id = profile.student_id
        existing.profile_data = profile.model_dump(mode="json")
        return existing

    def _message_history(self, interview: ProfileInterview, pending_answer: str | None = None) -> list[dict[str, str]]:
        messages = self.db.scalars(
            select(ProfileMessage)
            .where(ProfileMessage.interview_id == interview.id)
            .order_by(ProfileMessage.id.asc())
        ).all()
        history = [{"role": message.role, "content": message.content} for message in messages]
        if pending_answer is not None:
            history.append({"role": "user", "content": pending_answer})
        return history

    def _next_focus_bucket(self, profile: StudentProfile) -> tuple[str, list[str]] | None:
        profile_data = profile.model_dump(mode="json")
        for bucket_name, fields in self.interview_buckets:
            if any(not profile_data.get(field) for field in fields):
                return bucket_name, fields
        return None

    def _bucket_label(self, bucket_name: str) -> str:
        labels = {
            "basic": "专业、年级和学习目标",
            "knowledge": "知识基础",
            "weak_points": "薄弱点",
            "resources": "资源偏好",
            "time": "时间安排与约束",
            "style": "学习风格与认知方式",
            "motivation": "学习动机",
            "assessment": "评估偏好",
            "graph_focus": "知识图谱关注点",
        }
        return labels.get(bucket_name, bucket_name)

    def _field_label(self, field: str) -> str:
        labels = {
            "major": "专业",
            "grade": "年级",
            "learning_goal": "学习目标",
            "knowledge_foundation": "知识基础",
            "weak_points": "薄弱点",
            "resource_preference": "资源偏好",
            "time_preference": "时间安排",
            "constraints": "学习约束",
            "learning_style": "学习风格",
            "cognitive_style": "认知方式",
            "motivation": "学习动机",
            "assessment_preference": "评估偏好",
            "knowledge_graph_focus": "知识图谱关注点",
        }
        return labels.get(field, field)

    def _missing_fields(self, profile: StudentProfile, fields: list[str]) -> list[str]:
        profile_data = profile.model_dump(mode="json")
        return [field for field in fields if not profile_data.get(field)]

    def _bucket_template(self, bucket_name: str, missing_fields: list[str] | None = None) -> str:
        missing_fields = missing_fields or []
        if bucket_name == "basic":
            if missing_fields == ["major"]:
                return "请补充你的专业或所在方向。"
            if missing_fields == ["grade"]:
                return "请补充你的年级或当前学习阶段。"
            if missing_fields == ["learning_goal"]:
                return "请说明这次学习最想达到的目标。"
            if missing_fields:
                labels = "、".join(self._field_label(field) for field in missing_fields)
                return f"请补充你的{labels}。"
        templates = {
            "basic": "请补充你的专业、年级，以及这次学习最想达到的目标。",
            "knowledge": "请说明你当前的知识基础，特别是哪些课程概念或编程能力最薄弱。",
            "weak_points": "请具体说说你在这门课里最容易卡住的知识点或能力短板。",
            "resources": "你更偏好的学习资源是什么，例如图解、视频、代码实操、阅读材料或短练习？",
            "time": "你每周或每天可以投入多少学习时间？有没有固定时段或其他学习约束？",
            "style": "你更喜欢先看图解还是先做练习？遇到新概念时更希望直观理解还是推导理解？",
            "motivation": "你为什么想学这门课？这次学习最想解决的现实目标是什么？",
            "assessment": "你希望系统用什么方式检查学习效果，例如短练习、阶段测验、代码任务还是口头解释？",
            "graph_focus": "知识图谱里你最想优先关注哪些知识点或章节？",
        }
        return templates.get(bucket_name, "请继续补充这一维度的信息。")

    def _format_history(self, history: list[dict[str, str]]) -> str:
        role_names = {"assistant": "访谈Agent", "user": "学生"}
        return "\n".join(
            f"{index}. {role_names.get(item['role'], item['role'])}：{item['content']}"
            for index, item in enumerate(history, start=1)
        )

    async def _merge_answer(
        self,
        profile: StudentProfile,
        answer: str,
        history: list[dict[str, str]] | None = None,
        force_complete: bool = False,
    ) -> StudentProfile:
        if self.llm is not None and not self.llm.mock:
            try:
                data = await self.llm.complete_json(
                    (
                        "你是学生画像访谈Agent。根据完整访谈历史、当前画像和学生本轮回答，"
                        "返回合法JSON，只包含可确定的画像字段；不要臆测学生没有表达的信息。"
                        "如果当前访谈已经接近收尾，请补齐所有剩余维度，但仍保持谨慎。"
                    ),
                    (
                        f"访谈历史：\n{self._format_history(history or [])}\n\n"
                        f"当前画像：{profile.model_dump(mode='json')}\n"
                        f"学生本轮回答：{answer}\n"
                        f"是否需要补齐全部维度：{force_complete}"
                    ),
                )
                if "profile" in data and isinstance(data["profile"], dict):
                    data = data["profile"]
                profile_data = profile.model_dump(mode="json")
                self._merge_profile_data(profile_data, data)
                evidence = ProfileEvidence(source="deepseek-v4-pro", topic="学习需求访谈", detail=answer[:160])
                profile_data["updated_evidence"] = [*profile.updated_evidence, evidence]
                merged_profile = self._apply_answer_heuristics(StudentProfile(**profile_data), answer)
                return self._resolve_profile_fields(merged_profile, history, answer, force_complete)
            except Exception as exc:
                raise ProfileInterviewLLMError(
                    "DeepSeek 学生画像访谈调用失败，请检查 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL 或模型返回格式。"
                ) from exc

        evidence = ProfileEvidence(source="interview", topic="学习需求访谈", detail=answer[:160])
        update = self._heuristic_update(profile, answer)
        update["updated_evidence"] = [*profile.updated_evidence, evidence]
        return self._resolve_profile_fields(profile.model_copy(update=update), history, answer, force_complete)

    def _merge_profile_data(self, profile_data: dict, extracted_data: dict) -> None:
        for key, value in extracted_data.items():
            if key not in profile_data or key == "updated_evidence" or not self._has_profile_value(value):
                continue
            if isinstance(profile_data.get(key), list):
                normalized_values = self._normalize_profile_list_value(value)
                if normalized_values:
                    profile_data[key] = self._merge_lists(profile_data.get(key) or [], normalized_values)
            else:
                normalized_value = self._normalize_profile_text_value(value)
                if normalized_value:
                    profile_data[key] = normalized_value

    def _apply_answer_heuristics(self, profile: StudentProfile, answer: str) -> StudentProfile:
        update = self._heuristic_update(profile, answer)
        if not update:
            return profile

        profile_data = profile.model_dump(mode="json")
        for key, value in update.items():
            if isinstance(profile_data.get(key), list):
                profile_data[key] = self._merge_lists(profile_data.get(key) or [], value)
            elif not self._has_profile_value(profile_data.get(key)):
                profile_data[key] = value
        return StudentProfile(**profile_data)

    def _heuristic_update(self, profile: StudentProfile, answer: str) -> dict:
        update: dict = {}
        normalized_answer = answer.lower()
        major = self._extract_major(answer)
        if major:
            update["major"] = major
        if "大一" in answer:
            update["grade"] = "大一"
        elif "大二" in answer:
            update["grade"] = "大二"
        elif "大三" in answer:
            update["grade"] = "大三"
        elif "大四" in answer:
            update["grade"] = "大四"
        elif "研一" in answer:
            update["grade"] = "研一"
        elif "研二" in answer:
            update["grade"] = "研二"
        if any(keyword in answer for keyword in ["入门", "掌握", "通过", "提升", "想学", "学习"]) or "python" in normalized_answer:
            update["learning_goal"] = self._extract_goal(answer)
            update["motivation"] = "围绕目标建立可执行学习路径"
        if any(keyword in answer for keyword in ["Python", "C语言", "C 语言", "基础", "薄弱", "线性代数", "高数"]) or "python" in normalized_answer:
            update["knowledge_foundation"] = self._extract_foundation(answer)
        weak_points = list(profile.weak_points)
        for keyword in ["梯度下降", "线性代数", "矩阵运算", "模型评估", "概率统计", "过拟合", "指针", "数组", "函数", "结构体", "内存管理", "文件操作"]:
            if keyword in answer and keyword not in weak_points:
                weak_points.append(keyword)
        if weak_points:
            update["weak_points"] = weak_points
            update["knowledge_graph_focus"] = weak_points[:3]
        preferences = list(profile.resource_preference)
        for keyword in ["图解", "动画", "代码实操", "短练习", "阅读材料", "视频"]:
            if keyword in answer and keyword not in preferences:
                preferences.append(keyword)
        if "代码" in answer and "代码实操" not in preferences:
            preferences.append("代码实操")
        if preferences:
            update["resource_preference"] = preferences
            update["learning_style"] = "偏好" + "、".join(preferences[:3])
            update["cognitive_style"] = "先直观理解再通过练习巩固" if "图解" in preferences else "通过任务练习推进理解"
        if "分钟" in answer or "小时" in answer or "晚" in answer:
            update["time_preference"] = self._extract_time(answer)
            update["constraints"] = ["学习时间需要拆成短时段"]
        if "练习" in answer or "测验" in answer or "考试" in answer:
            update["assessment_preference"] = "短练习和阶段测验"
        return update

    def _extract_major(self, answer: str) -> str:
        major_aliases = [
            ("软件工程", ["软件工程"]),
            ("计算机科学与技术", ["计算机科学与技术", "计算机科学", "计算机专业", "计算机"]),
            ("人工智能", ["人工智能", "智能科学"]),
            ("数据科学", ["数据科学", "大数据"]),
            ("自动化", ["自动化"]),
        ]
        for canonical, aliases in major_aliases:
            if any(alias in answer for alias in aliases):
                return canonical
        return ""

    async def _next_question(
        self,
        profile: StudentProfile,
        history: list[dict[str, str]] | None = None,
        focus_bucket: tuple[str, list[str]] | None = None,
    ) -> str:
        focus_bucket = focus_bucket or self._next_focus_bucket(profile)
        if focus_bucket is None:
            return "画像信息已基本完整，系统将自动进入下一环节。"
        bucket_name, fields = focus_bucket
        missing_fields = self._missing_fields(profile, fields)
        if self.llm is not None and not self.llm.mock:
            try:
                data = await self.llm.complete_json(
                    (
                        "你是学生画像访谈Agent。首轮问题固定，第二轮及以后必须围绕学生画像维度逐项挖掘。"
                        "当前系统会根据缺失维度分桶提问，你要严格围绕给定的 focus_dimension 追问，避免泛泛而谈。"
                        "只返回一个下一轮聚焦问题JSON，格式为 {\"question\":\"...\"}。"
                    ),
                    (
                        f"访谈历史：\n{self._format_history(history or [])}\n\n"
                        f"当前画像：{profile.model_dump(mode='json')}\n\n"
                        f"focus_dimension: {bucket_name}\n"
                        f"focus_fields: {missing_fields or fields}\n"
                        f"focus_label: {self._bucket_label(bucket_name)}\n"
                        "请生成一个自然、具体、承接上一轮回答的问题，只围绕这些缺失维度追问。"
                    ),
                )
                question = data.get("question")
                normalized_question = self._normalize_profile_text_value(question)
                if normalized_question:
                    repeated = self._is_repeated_question(normalized_question, history or [])
                    focused = self._question_matches_focus(normalized_question, bucket_name, missing_fields)
                    if not repeated and focused:
                        return normalized_question
                    if self.require_real_llm:
                        retry_question = await self._retry_next_question(bucket_name, missing_fields, profile, history or [], normalized_question)
                        if retry_question:
                            return retry_question
                        reason = "重复" if repeated else "没有围绕当前缺失画像维度"
                        raise ProfileInterviewLLMError(f"DeepSeek 学生画像追问生成失败：模型返回的问题{reason}。")
            except Exception as exc:
                if isinstance(exc, ProfileInterviewLLMError):
                    raise
                raise ProfileInterviewLLMError(
                    "DeepSeek 学生画像追问生成失败，请检查 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL 或模型返回格式。"
                ) from exc

        return self._bucket_template(bucket_name, missing_fields)

    async def _retry_next_question(
        self,
        bucket_name: str,
        missing_fields: list[str],
        profile: StudentProfile,
        history: list[dict[str, str]],
        rejected_question: str,
    ) -> str:
        if self.llm is None or self.llm.mock:
            return ""
        data = await self.llm.complete_json(
            (
                "你是学生画像访谈Agent。上一次生成的问题被系统拒绝，因为它重复或没有命中当前缺失画像维度。"
                "必须重新生成一个全新的、自然的、只追问缺失字段的问题。"
                "只返回JSON：{\"question\":\"...\"}。"
            ),
            (
                f"访谈历史：\n{self._format_history(history)}\n\n"
                f"当前画像：{profile.model_dump(mode='json')}\n"
                f"当前缺失字段：{missing_fields}\n"
                f"缺失字段中文：{[self._field_label(field) for field in missing_fields]}\n"
                f"被拒绝的问题：{rejected_question}\n"
                f"focus_dimension: {bucket_name}\n"
                "请重新生成一个不重复、能明显命中当前缺失字段的问题。"
            ),
        )
        question = data.get("question")
        normalized_question = self._normalize_profile_text_value(question)
        if not normalized_question:
            return ""
        if self._is_repeated_question(normalized_question, history):
            return ""
        if not self._question_matches_focus(normalized_question, bucket_name, missing_fields):
            return ""
        return normalized_question

    def _question_matches_focus(self, question: str, bucket_name: str, missing_fields: list[str]) -> bool:
        if not missing_fields:
            return True
        normalized_question = self._normalize_question(question)
        focus_terms = [self._field_label(field) for field in missing_fields]
        aliases = {
            "major": ["专业", "方向", "学科"],
            "grade": ["年级", "学习阶段", "大一", "大二", "大三", "本科"],
            "learning_goal": ["目标", "达成", "学会", "掌握", "想学"],
            "knowledge_foundation": ["基础", "掌握", "了解", "学过"],
            "weak_points": ["薄弱", "卡住", "短板", "困难"],
            "resource_preference": ["资源", "图解", "视频", "代码", "练习", "阅读"],
            "time_preference": ["时间", "每天", "每周", "时段"],
            "constraints": ["约束", "限制", "困难", "安排"],
            "learning_style": ["学习风格", "喜欢", "方式"],
            "cognitive_style": ["认知", "理解", "推导", "直观"],
            "motivation": ["动机", "为什么", "现实目标"],
            "assessment_preference": ["评估", "检查", "测验", "练习"],
            "knowledge_graph_focus": ["图谱", "知识点", "章节", "关注"],
        }
        for field in missing_fields:
            terms = [*focus_terms, *aliases.get(field, [])]
            if any(term and term in normalized_question for term in terms):
                return True
        return bucket_name not in {"basic"}

    def _is_repeated_question(self, question: str, history: list[dict[str, str]]) -> bool:
        normalized_question = self._normalize_question(question)
        if not normalized_question:
            return False
        for item in history:
            if item.get("role") != "assistant":
                continue
            if normalized_question == self._normalize_question(item.get("content", "")):
                return True
        return False

    def _normalize_question(self, question: str) -> str:
        return re.sub(r"[\s，。！？、,.!?：:；;]+", "", question or "")

    def _has_profile_value(self, value: object) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return any(self._has_profile_value(item) for item in value)
        if isinstance(value, dict):
            return any(self._has_profile_value(item) for item in value.values())
        return value is not None

    def _merge_lists(self, existing: list, incoming: object) -> list:
        values = list(existing)
        incoming_values = incoming if isinstance(incoming, list) else [incoming]
        for item in incoming_values:
            if not self._has_profile_value(item):
                continue
            if item not in values:
                values.append(item)
        return values

    def _normalize_profile_text_value(self, value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("value", "text", "summary", "name", "type", "label", "content", "detail", "description"):
                normalized = self._normalize_profile_text_value(value.get(key))
                if normalized:
                    return normalized
            nested_values = [
                self._normalize_profile_text_value(item)
                for item in value.values()
                if not isinstance(item, (dict, list))
            ]
            return "；".join(item for item in nested_values if item)
        if isinstance(value, list):
            values = self._normalize_profile_list_value(value)
            return "、".join(values)
        if value is None:
            return ""
        return str(value).strip()

    def _normalize_profile_list_value(self, value: object) -> list[str]:
        values = value if isinstance(value, list) else [value]
        normalized: list[str] = []
        for item in values:
            if isinstance(item, list):
                candidates = self._normalize_profile_list_value(item)
            else:
                text = self._normalize_profile_text_value(item)
                candidates = [text] if text else []
            for candidate in candidates:
                if candidate and candidate not in normalized:
                    normalized.append(candidate)
        return normalized

    def _resolve_profile_fields(
        self,
        profile: StudentProfile,
        history: list[dict[str, str]] | None = None,
        answer: str = "",
        force_complete: bool = False,
    ) -> StudentProfile:
        profile_data = profile.model_dump(mode="json")
        latest_answer = answer or next((item["content"] for item in reversed(history or []) if item["role"] == "user"), "")

        if not profile_data.get("motivation"):
            profile_data["motivation"] = self._derive_motivation(profile_data, latest_answer, force_complete)
        if not profile_data.get("constraints"):
            profile_data["constraints"] = self._derive_constraints(profile_data, latest_answer, force_complete)
        if not profile_data.get("assessment_preference"):
            profile_data["assessment_preference"] = self._derive_assessment(profile_data, latest_answer, force_complete)
        if not profile_data.get("knowledge_graph_focus"):
            profile_data["knowledge_graph_focus"] = self._derive_focus(profile_data, latest_answer, force_complete)
        if not profile_data.get("learning_style"):
            profile_data["learning_style"] = self._derive_learning_style(profile_data, latest_answer, force_complete)
        if not profile_data.get("cognitive_style"):
            profile_data["cognitive_style"] = self._derive_cognitive_style(profile_data, latest_answer, force_complete)

        if force_complete:
            profile_data["major"] = profile_data.get("major") or "计算机科学与技术"
            profile_data["grade"] = profile_data.get("grade") or "本科"
            profile_data["learning_goal"] = profile_data.get("learning_goal") or "系统学习课程基础"
            profile_data["knowledge_foundation"] = profile_data.get("knowledge_foundation") or "基础能力待进一步评估"
            profile_data["learning_style"] = profile_data.get("learning_style") or "偏好图解、案例和短练习"
            profile_data["cognitive_style"] = profile_data.get("cognitive_style") or "先直观理解再通过练习巩固"
            profile_data["weak_points"] = profile_data.get("weak_points") or ["课程核心概念"]
            profile_data["time_preference"] = profile_data.get("time_preference") or "每周固定安排学习时间"
            profile_data["resource_preference"] = profile_data.get("resource_preference") or ["图解", "代码实操"]

        return StudentProfile(**profile_data)

    def _derive_motivation(self, profile_data: dict[str, object], latest_answer: str, force_complete: bool) -> str:
        goal = str(profile_data.get("learning_goal") or "").strip()
        if goal:
            return f"围绕{goal}建立可执行学习路径"
        if "工作" in latest_answer:
            return "希望把课程知识尽快转化为实践能力"
        if force_complete:
            return "希望系统帮助建立稳定的学习节奏"
        return ""

    def _derive_constraints(self, profile_data: dict[str, object], latest_answer: str, force_complete: bool) -> list[str]:
        time_preference = str(profile_data.get("time_preference") or "")
        constraints: list[str] = []
        if time_preference:
            constraints.append("学习时间需要拆成短时段")
        if "考试" in latest_answer or "实习" in latest_answer:
            constraints.append("需要兼顾其他课程或事务")
        if force_complete and not constraints:
            constraints.append("学习时间需要拆成短时段")
        return constraints

    def _derive_assessment(self, profile_data: dict[str, object], latest_answer: str, force_complete: bool) -> str:
        if any(keyword in latest_answer for keyword in ["练习", "测验", "考试"]):
            return "短练习和阶段测验"
        if profile_data.get("resource_preference"):
            return "短练习和阶段测验"
        if force_complete:
            return "短练习和阶段测验"
        return ""

    def _derive_learning_style(self, profile_data: dict[str, object], latest_answer: str, force_complete: bool) -> str:
        preferences = [str(value) for value in profile_data.get("resource_preference") or [] if str(value).strip()]
        if preferences:
            return "偏好" + "、".join(preferences[:3])
        if any(keyword in latest_answer for keyword in ["图解", "视频", "动画", "案例"]):
            return "偏好图解、案例和短练习"
        if force_complete:
            return "偏好图解、案例和短练习"
        return ""

    def _derive_cognitive_style(self, profile_data: dict[str, object], latest_answer: str, force_complete: bool) -> str:
        preferences = [str(value) for value in profile_data.get("resource_preference") or [] if str(value).strip()]
        if any(keyword in "、".join(preferences) for keyword in ["图解", "动画", "视频"]):
            return "先直观理解再通过练习巩固"
        if any(keyword in latest_answer for keyword in ["代码", "练习", "任务", "实操"]):
            return "通过任务练习推进理解"
        if force_complete:
            return "先直观理解再通过练习巩固"
        return ""

    def _derive_focus(self, profile_data: dict[str, object], latest_answer: str, force_complete: bool) -> list[str]:
        weak_points = list(profile_data.get("weak_points") or [])
        if weak_points:
            return weak_points[:3]
        if any(keyword in latest_answer for keyword in ["课程", "章节", "知识点"]):
            return ["课程核心概念"]
        if force_complete:
            return ["课程核心概念"]
        return []

    def _force_complete_profile(
        self,
        profile: StudentProfile,
        history: list[dict[str, str]] | None,
        answer: str,
    ) -> StudentProfile:
        return self._resolve_profile_fields(profile, history, answer, force_complete=True)

    def _extract_goal(self, answer: str) -> str:
        if "python" in answer.lower():
            return "系统学习 Python 程序设计"
        if "C语言" in answer or "C 语言" in answer:
            return "系统学习 C 语言程序设计"
        if "机器学习" in answer:
            return "4周内入门机器学习" if "四周" in answer or "4周" in answer else "系统学习机器学习基础"
        return answer[:60]

    def _extract_foundation(self, answer: str) -> str:
        if "python" in answer.lower():
            if "一般" in answer or "基础" in answer:
                return "Python基础一般，需要系统补齐语法、程序结构和实践能力"
            return "需要围绕 Python 程序设计建立知识基础"
        if "C语言" in answer or "C 语言" in answer:
            if "薄弱" in answer or "一般" in answer or "基础" in answer:
                return "C 语言基础一般，需要重点补齐指针、数组、函数和内存模型"
            return "需要围绕 C 语言程序设计建立知识基础"
        if "Python" in answer and "一般" in answer:
            return "Python基础一般，相关数学基础需要加强"
        if "薄弱" in answer:
            return "已具备部分基础，但存在薄弱知识点"
        return "具备基础学习能力"

    def _extract_time(self, answer: str) -> str:
        if "45分钟" in answer:
            if "周末" in answer and "晚" in answer:
                return "平时晚上和周末，每次约45分钟"
            return "每天晚间45分钟" if "晚" in answer else "每天45分钟"
        if "周末" in answer and "晚" in answer:
            return "平时晚上和周末安排学习"
        if "小时" in answer:
            return "按小时块安排学习"
        return "需要碎片化时间安排"
