# 03 MCP 服务接口契约

> 三个自定义 MCP Server 封装 challengecup 后端（FastAPI + MySQL + Neo4j）的核心业务能力，供 AgentArts 工作流以 MCP 工具方式调用。
> 协议：MCP streamableHttp（`http://<host>:<port>/mcp`）；实现：官方 Python SDK（FastMCP）。
> 数据隔离硬约束：所有工具都要求 `user_id + course_id`，服务端校验课程归属，防止跨用户/跨课程读写。

## 0. 通用约定

- **返回格式**：所有工具返回 JSON 对象。成功带 `ok: true`；失败带 `ok: false, error_type, message`，不抛未处理异常，便于工作流判断节点消费。
- **error_type 枚举**：`course_not_found`（课程不存在或不属于该用户）、`profile_not_found`、`graph_missing`（Neo4j 无该课程子图）、`validation_error`（参数不合法）、`storage_error`（MySQL/Neo4j 不可用）。
- **安全**：可选环境变量 `MCP_ACCESS_TOKEN`，设置后所有请求必须携带 `Authorization: Bearer <token>`。
- **复用**：三个 Server 直接复用 `apps/api/app` 的 SQLAlchemy 模型与服务（单一数据源，避免逻辑漂移）；连接配置读取仓库根目录 `.env`（`DATABASE_URL`、`NEO4J_URI/USER/PASSWORD`）。

## 1. profile-server（端口 8100）

职责：学生画像持久化、画像访谈消息记录、画像随学随新事件。

| 工具 | 参数 | 返回 |
| --- | --- | --- |
| `get_student_profile` | `user_id:int, course_id:int` | `{ok, exists, student_id, profile, completion_score, confidence_score, updated_at}`；不存在时 `exists:false` |
| `save_student_profile` | `user_id, course_id, profile:object, source?="agentarts_interview"` | 校验并补全 14 维画像（`with_completion_score`），upsert `student_profiles`；`{ok, student_id, profile, completion_score, confidence_score, created}` |
| `append_interview_message` | `user_id, course_id, role:"user"\|"assistant", content:string` | get-or-create 该课程访谈；追加消息；`{ok, interview_id, turn_count, messages:[最近10条{role,content}], status}` |
| `list_interview_messages` | `user_id, course_id, limit?=20` | `{ok, messages}` |
| `record_profile_event` | `user_id, course_id, event_type:string, topic:string, knowledge_node_id?="", detail?="", score?:float, event_payload?:object, evidence_strength?:string, lesson_session_id?:int` | 走 `DynamicProfileService.record_event`（画像增量更新 + 更新日志 + 路径重规划判定）；`{ok, event_id, changed_dimensions, update_reason, replan_required, profile_summary}` |
| `list_profile_events` | `user_id, course_id, limit?=50` | `{ok, events:[{id,event_type,topic,knowledge_node_id,score,evidence_strength,created_at}]}` |
| `list_profile_update_logs` | `user_id, course_id, limit?=20` | `{ok, logs:[{changed_dimensions, update_reason, confidence_delta, created_at}]}` |
| `list_path_revisions` | `user_id, course_id, limit?=20` | `{ok, revisions:[{trigger_type, trigger_node_id, change_summary, created_at}]}` |

事件类型约定（与现有画像更新规则一致）：
强证据 `assessment_submitted / quiz_submitted / code_attempt_passed / lesson_completed / exercise_submitted`；中证据 `profile_interview_answered / openmaic_classroom_viewed / mind_map_interacted / code_attempt_run / tutor_question_asked / feedback_submitted / document_viewed`。

## 2. graph-server（端口 8101）

职责：课程知识图谱查询与约束导出、原文证据回表（Agentic RAG 的"最终证据源"）。

| 工具 | 参数 | 返回 |
| --- | --- | --- |
| `get_course_graph` | `user_id, course_id` | `{ok, nodes:[{id,name,node_type,level,parent_id,difficulty,summary,mastery_status,...}], edges:[{id,source_node_id,target_node_id,relation_type,reason}]}`（复用 `CourseService.get_knowledge_graph`，含掌握度合并） |
| `get_node_constraints` | `user_id, course_id, node_id` | `{ok, node, parent, children, prerequisites, successors, related, mastery}`——资源生成与辅导的"图谱约束"输入 |
| `get_knowledge_evidence` | `user_id, course_id, node_id, limit?=6` | `{ok, evidence:[{chunk_id, heading, source_locator, content, material_id}]}`；优先按节点 `source_chunk_ids` 精确回表，退化按节点名 LIKE 检索 |
| `search_course_chunks` | `user_id, course_id, query:string, limit?=8` | `{ok, chunks:[同上]}`——关键词 LIKE 检索兜底（不依赖 Milvus） |

关系类型：`prerequisite / contains / applies_to / common_mistake / case_supports`。

## 3. assessment-server（端口 8102）

职责：学习评估、掌握度、学习路径规划、错题归档。

| 工具 | 参数 | 返回 |
| --- | --- | --- |
| `submit_comprehensive_assessment` | `user_id, course_id, assessment:object`（`ComprehensiveAssessmentSubmit` Schema，见 §4.1） | 完整评估闭环：合并课堂状态 → `EvaluatorAgent` 评分 → 掌握度写入 → 画像事件；`{ok, report:{final_score,passed,mastery_status,dimension_scores,feedback,weak_points,next_adjustment}, profile_update:{changed_dimensions,replan_required,...}}` |
| `submit_learning_event` | `user_id, course_id, event:object`（`LearningEvent` Schema） | 轻量学习事件评估（观看资源等）；`{ok, report, profile_update}` |
| `get_node_mastery` | `user_id, course_id, node_id?=""` | `node_id` 为空返回全部节点掌握度列表；`{ok, masteries:[{node_id,topic,mastery_score,mastery_status,detail,updated_at}]}` |
| `plan_learning_path` | `user_id, course_id, plan_type?="main"\|"remedial", focus_node_id?="", chapter_id?="", max_nodes?=18` | 复用 `LearningPathService.plan_course_path`；`{ok, path:{plan_type,current_stage_id,stages:[...],schedule_summary,weekly_time_budget_minutes,...}}`；画像/图谱缺失返回 `profile_not_found`/`graph_missing` |
| `list_wrong_questions` | `user_id, course_id, limit?=100` | 从 `assessment_submitted` 事件归档错题；`{ok, wrong_questions:[{topic, knowledge_node_id, kind:"quiz"\|"code", question, options, correct_answer_index, selected_answer_index, expected_output, actual_output, final_score, created_at}]}` |

掌握状态枚举（`mastery_status`）：`not_started / severe_weak / basic / good / proficient`；`basic` 及以下视为未通过（通过线 `final_score >= 0.75`，`good` 与 `proficient` 为通过）。

## 4. 关键 Schema

### 4.1 ComprehensiveAssessmentSubmit（评估输入）

```json
{
  "student_id": "student-xxxx",
  "topic": "循环嵌套",
  "course_id": 1,
  "knowledge_node_id": "py-2-3",
  "classroom_completed": true,
  "notes_completed": true,
  "mind_map_completed": false,
  "code_lab_completed": true,
  "quiz_answers": [
    {"id": "q1", "dimension": "概念", "correct": true, "prompt": "题干",
     "options": ["A","B","C","D"], "correct_answer_index": 2, "selected_answer_index": 2, "weight": 1.0}
  ],
  "code_attempt": {"prompt": "任务要求", "code": "学生代码", "expected_output": "期望输出",
                   "actual_output": "实际输出", "passed": false, "attempts": 2},
  "detail": "补充说明"
}
```

### 4.2 StudentProfile（画像，14 维）

```json
{
  "student_id": "student-xxxx", "major": "计算机科学与技术", "grade": "大二",
  "learning_goal": "4周内完成Python课程并独立完成小项目",
  "knowledge_foundation": "有C语言基础，Python零基础",
  "learning_style": "偏好图解、案例和短练习", "cognitive_style": "先直观理解再推导",
  "weak_points": ["列表切片", "字典遍历"], "time_preference": "每天晚间45分钟",
  "resource_preference": ["动画", "代码实操"], "motivation": "课程需要+兴趣",
  "constraints": ["晚间时间有限"], "assessment_preference": "短练习和阶段测验",
  "knowledge_graph_focus": ["列表切片"], "confidence_score": 0.62, "completion_score": 0.8
}
```

## 5. 部署

### 5.1 本地运行（uv）

```bash
cd apps/mcp
uv sync
# 需要仓库根目录 .env 提供 DATABASE_URL / NEO4J_*；未配置 MCP_ACCESS_TOKEN 时无鉴权
uv run python -m mcp_servers.profile_server      # 0.0.0.0:8100
uv run python -m mcp_servers.graph_server        # 0.0.0.0:8101
uv run python -m mcp_servers.assessment_server   # 0.0.0.0:8102
```

### 5.2 Docker（用于部署到华为云/AgentArts 运行时）

```bash
docker build -t zhixing-mcp-servers -f apps/mcp/Dockerfile .
docker run -d --env-file .env -p 8100:8100 -p 8101:8101 -p 8102:8102 zhixing-mcp-servers
```

单镜像同时暴露三个端口；在 AgentArts 高代码运行时或 ECS 上部署后，将三个 `/mcp` 地址登记到平台 MCP 列表并完成连通性调试。
