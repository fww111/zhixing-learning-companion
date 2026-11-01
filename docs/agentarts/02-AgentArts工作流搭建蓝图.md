# 02 AgentArts 工作流搭建蓝图

> 本文档是在华为云 AgentArts 控制台搭建"知行学习伙伴"的节点级操作蓝图。
> 搭建顺序：知识库 → MCP 服务接入 → 画像访谈工作流 → 资源生成工作流 → 辅导子智能体 → 路径评估工作流 → 多智能体应用组装 → 发布。

## 0. 前置准备

1. 开通 AgentArts 服务，创建工作空间（低代码开发）。
2. MaaS 接入：开通 ModelArts Studio，部署 `DeepSeek-V4-Pro` 与 `GLM-5`，在 AgentArts「模型」中完成授权，命名 `deepseek-v4-pro`、`glm-5`。
3. 部署三个 MCP Server（见《03-MCP服务接口契约》），得到三个 streamableHttp 地址：
   - `http://<host>:8100/mcp` profile-server
   - `http://<host>:8101/mcp` graph-server
   - `http://<host>:8102/mcp` assessment-server
4. AgentArts「MCP」→ 自定义接入，逐一登记三个 MCP 服务并调试连通；「插件」→ 基于 API 创建 OpenMAIC 插件（`POST {OPENMAIC_BASE_URL}/api/generate-classroom`，Body 为 JSON）。

## 1. 知识库构建

1. 「知识库」→ 新建 `cpp-algorithms`（主）、`python-course`（辅助）两个知识库。
2. 上传《C++算法学习》教材语料：`data/seed/cpp_algorithms/corpus/chapter-01.md` ~ `chapter-08.md`（8 个文件，33 个小节，Markdown 结构 `# 章 / ## 节`）；分段方式选**按标题分层**（与章节结构对齐），分段长度参考 512 tokens，重叠 50。
3. 对 `cpp-algorithms` 执行**命中测试**（如"什么是时间复杂度"、"二分查找怎么写"、"背包问题状态转移"），记录命中率截图（答辩素材）。
4. 命中测试不理想的段落回调分段策略（优先保证"小节标题 + 小节正文"在同一段）。
5. 检索质量用数据说话：本地已内置**检索自动评估闭环**（`apps/api/app/services/kb_evaluation_service.py`，借鉴伯乐项目）——自动构造评测集（anchor+干扰段落→LLM 生成 query/gold），跑 recall@1/3/5/10 与 f1@k，`?error_only=true` 筛坏例。教材类语料用 book 预设、题库类用 QA 预设（`chunking_service.py`），评估报告作为平台分段策略选择的依据，见《05-技术借鉴与增强》。

> 说明：平台知识库负责语义召回；**最终引用给学生的原文证据**仍通过 graph-server 的 `get_knowledge_evidence` 从 MySQL 原文 chunk 回表获取，形成"向量召回 + 原文回表"双保险，这是防幻觉设计的一部分。

## 2. 多智能体应用骨架

「多智能体应用」→ 新建 `zhixing-learning-companion`。

多 Agent 控制器配置：
- 主控模型：`deepseek-v4-pro`
- 意图分类提示词（四类）：
  1. `profile_interview`：构建/更新学习画像、回答访谈问题
  2. `resource_learning`：学习某个知识点、生成学习资源
  3. `tutoring`：提问求助、答疑、传图提问
  4. `path_assessment`：查看/更新学习路径、提交评估、错题重做
- 全局变量（会话级）：`user_id`（数值，由 Demo 前端登录态注入）、`course_id`（数值）、`course_name`（字符串）。

## 3. 子应用 A：画像访谈工作流（对话型）

```text
开始(用户输入)
 → 消息节点: 判断是否首问
     条件1 无访谈记录: 固定首问"请介绍一下你的专业、年级和学习目标"
 → 大模型节点 next_question
     输入: 历史消息(MCP append_interview_message 返回) + 画像维度缺口
     提示词要点: 每次只追问一个缺口维度；8 轮内收敛；语气自然
 → 提问器节点: 展示问题并收集学生回答
 → MCP 节点 profile-server.append_interview_message(role="user", content=回答)
 → 大模型节点 extract_profile
     输出 JSON Schema: StudentProfile 各维度（见 03 文档 §2.2）
 → MCP 节点 profile-server.save_student_profile(profile=extract_profile 输出)
 → 判断节点: 画像 completion_score >= 0.75
     是 → 结束节点(消息: 画像已生成，展示画像摘要卡片)
     否 → 循环回到 next_question
```

## 4. 子应用 B：个性化资源生成工作流（任务型，核心）

```text
开始(user_id, course_id, node_id)
 ├─ MCP 节点 graph-server.get_node_constraints   → 前置/后继/父章节/子节点
 ├─ MCP 节点 graph-server.get_knowledge_evidence → MySQL 原文证据 chunks
 ├─ MCP 节点 profile-server.get_student_profile  → 画像
 ├─ 知识检索节点 → 平台知识库语义召回(扩展查询: 节点名/父章节/前置)
 │
 ├─ 大模型节点 analysis_plan（分析规划 Agent）
 │    输入: 画像摘要 + 图谱约束 + 证据标题清单
 │    输出: ResourceBlueprint（教学目标/难度档/各资源形态要点/证据引用计划）
 │
 ├─ 并行聚合: 6 个大模型节点（共享 analysis_plan + 证据原文 + 画像约束）
 │    ├─ document   讲解文档(Markdown)
 │    ├─ mind_map   思维导图(树状 JSON)
 │    ├─ video      视频脚本+分镜
 │    ├─ code_lab   代码实操(含起始代码与期望输出，不含答案)
 │    ├─ exercise   练习题(选择/填空/编程, 含 correct_answer_index)
 │    └─ reading    拓展阅读
 │
 ├─ 反思精炼循环（最多 2 轮）:
 │    大模型节点 fact_check（deepseek-v4-pro）
 │      提示词: 逐条判断生成内容是否被证据原文支撑，输出 violations[]
 │    大模型节点 pedagogy_check（glm-5）
 │      提示词: 难度/表达/资源形态是否匹配画像，输出 adjustments[]
 │    大模型节点 debate（deepseek-v4-pro vs glm-5 结论合并）
 │      输出: conflicts[], risk_level
 │    大模型节点 decision
 │      输出枚举: accepted | retrieve_more | revise
 │    判断节点:
 │      revise        → 回到并行聚合（携带修改意见）
 │      retrieve_more → 回到知识检索（扩展查询词）
 │      accepted / 轮次用尽 → 继续
 │
 ├─ 插件节点 OpenMAIC.generate-classroom(requirement=课堂大纲)
 │    异步: 返回 job_id；HTTP 请求节点轮询任务直至拿到 classroom url
 │
 └─ 结束节点: 输出 resource_package(JSON) + 审计轨迹
      (analysis_plan, graph_constraints, evidence, verification, pedagogy, debate, decision)
```

提示词资产从 `apps/api/app/llm/prompts.py` 与 `apps/api/app/agents/*_agent.py` 迁移改写，保持输出 JSON Schema 一致，便于前端复用现有渲染组件。

## 5. 子应用 C：智能辅导子智能体（单智能体）

- 类型：单智能体应用（对话型），模型 `deepseek-v4-pro`；传图场景走多模态模型。
- 知识库：挂载当前课程知识库（`course_name` → 知识库映射）。
- 工具：MCP `graph-server.get_node_constraints`（提供知识点上下文）、MCP `graph-server.search_course_chunks`（关键词补充检索）。
- 提示词要点：回答必须基于课程证据；先直接回答 → 再解释 → 给一个易错点 → 建议下一步练习；证据不足时明确说明并引导学生补充章节信息；不暴露 chunk 原文与内部调试信息。
- 每次回答后调用 MCP `profile-server.record_profile_event(event_type="tutor_question_asked")`（画像随学随新证据）。

## 6. 子应用 D：学习路径与评估工作流（任务型）

### 6.1 提交评估

```text
开始(user_id, course_id, assessment JSON)
 → MCP 节点 assessment-server.submit_comprehensive_assessment
     （内部完成: 综合评分 → 掌握度写入 → 画像事件 → 返回 report + profile_update）
 → 大模型节点: 用自然语言解读评估报告（弱项、反馈、下一步建议）
 → 判断节点: report.passed == false
     是 → MCP 节点 assessment-server.plan_learning_path(plan_type="remedial", focus_node_id=本次节点)
     否 → MCP 节点 assessment-server.plan_learning_path(plan_type="main")
 → 结束节点: 输出报告解读 + 新路径摘要
```

### 6.2 生成/刷新路径

```text
开始(user_id, course_id)
 → MCP 节点 assessment-server.plan_learning_path
 → 大模型节点: 把 stages 转成学生可读的周计划讲解
 → 结束节点
```

## 7. 发布配置

1. 多智能体应用 → 发布 → **API 服务**（开启流式 SSE）：得到 `POST /v1/{app_id}/chat/completions` 形态的调用地址与 API Key；Demo 前端通过自有后端代理转发（API Key 不落前端）。
2. 同一应用 → 发布 → **网页应用**：生成可分享 URL，作为无前端兜底演示入口。
3. 决赛前将 Demo 前端与 MCP Server 部署到华为云 ECS（赛题云资源支持），保证可在线访问。

## 8. 观测与效果评估

1. 观测：应用发布后自动产生 Trace/会话数据；在「智能体观测」中查看调用链、会话分析，截图用于答辩展示多 Agent 协作过程。
2. 评估：
   - 构建评测集（48 条）：以《C++算法学习》8 章 33 节为输入空间，每章 2 个知识点 × 3 种画像（零基础/有C基础/冲刺竞赛），以资源包 JSON 为输出。
   - 评估器：`正确性`、`幻觉`、`任务完成度` 预置评估器 + 自定义 Rubric（教学适配度）。
   - 离线评估任务跑两版提示词（v1 vs v2），对比报告进入 PPT 与设计方案文档。

## 9. 验收清单

- [ ] 四类意图路由正确（分别用样例问句验证）
- [ ] 画像访谈 8 轮内生成完整画像，MySQL `student_profiles` 出现记录
- [ ] 资源生成 6 分支并行输出齐全，辩论/决策轨迹可在观测中回放
- [ ] 评估未达标时 `knowledge_node_masteries` 更新且路径出现薄弱点专项任务
- [ ] 错题重做后掌握度与画像联动更新
- [ ] SSE 流式在 Demo 前端正常渲染
- [ ] 平台网页发布入口可访问
